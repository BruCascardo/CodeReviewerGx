import com.genexus.*;
import com.genexus.servlet.IServletContext;
import com.genexus.servlet.IServletInputStream;
import com.genexus.servlet.IServletOutputStream;
import com.genexus.servlet.http.ICookie;
import com.genexus.servlet.http.IHttpServletRequest;
import com.genexus.servlet.http.IHttpServletResponse;
import com.genexus.servlet.http.IHttpSession;
import org.json.*;

import java.io.*;
import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.util.*;

/**
 * Web Panels, Web Components y transacciones ejecutados en la JVM, como los ejecutaria Tomcat: la vista previa de
 * Explorar. Corre en un motor aparte (GxMotor con el argumento "pantallas"), porque cambia tres cosas de GeneXus en
 * toda la JVM:
 *   - las conexiones: todas (las de cada pedido, que GeneXus abre con un handle nuevo, y las de una nueva unidad de
 *     trabajo como prcLog) son una sola por base, donde nada se confirma: commit pone un savepoint, rollback vuelve
 *     al ultimo commit y close no cierra. reiniciar() deshace todo (ver DriverCompartido);
 *   - la seguridad integrada: no hay login de GAM; el proveedor de seguridad acepta la sesion (sinLogin);
 *   - los permisos de WorkWithPlus: motor/pantallas/secgamisauthbyfunctionalitykey.java va primero en el
 *     classpath y responde segun "permisos" del pedido.
 * El pedido HTTP se arma con Proxy sobre las interfaces de GeneXus (IHttpServletRequest...): no hace falta un
 * contenedor de servlets.
 */
public class Pantallas {

   // ------------------------------------------------------------------ conexiones: una por base, sin confirmar nada

   /**
    * Una conexion compartida: commit y rollback simulados con savepoints; close no cierra. Lo que se graba deja
    * filas bloqueadas hasta reiniciar() (un rollback a un savepoint no las suelta en InnoDB): por eso la espera
    * de un bloqueo es corta y gxp/vista.py deshace todo despues de unos minutos sin uso.
    */
   static final class Compartida implements InvocationHandler {
      static final int ESPERA_BLOQUEO_SEG = 10;
      final Connection real;
      Savepoint inicio;
      Savepoint confirmado;
      int commits, rollbacks;

      Compartida(Connection real) throws SQLException {
         this.real = real;
         real.setAutoCommit(false);
         try (java.sql.Statement st = real.createStatement()) {
            st.execute("SET SESSION innodb_lock_wait_timeout = " + ESPERA_BLOQUEO_SEG);
         } catch (SQLException e) {
            // no es MySQL: queda la espera de la base
         }
         inicio = real.setSavepoint("gxp_inicio");
      }

      public Object invoke(Object proxy, Method m, Object[] a) throws Throwable {
         boolean sinArgs = a == null || a.length == 0;
         switch (m.getName()) {
            case "commit":
               if (sinArgs) {
                  confirmado = real.setSavepoint("gxp_commit");
                  commits++;
                  return null;
               }
               break;
            case "rollback":
               if (sinArgs) {
                  real.rollback(confirmado != null ? confirmado : inicio);
                  rollbacks++;
                  return null;
               }
               break;
            case "close": case "abort": case "setAutoCommit":
               return null;
            case "isClosed":
               return false;
            case "getAutoCommit":
               return false;
            case "hashCode":
               return System.identityHashCode(proxy);
            case "equals":
               return proxy == a[0];
            case "toString":
               return "Compartida(" + real + ")";
         }
         try {
            return m.invoke(real, a);
         } catch (InvocationTargetException e) {
            throw e.getCause();
         }
      }

      /** Deshace todo con un rollback completo, que ademas suelta los bloqueos, y empieza de nuevo. */
      void reiniciar() throws SQLException {
         real.rollback();
         confirmado = null;
         inicio = real.setSavepoint("gxp_inicio");
      }
   }

   /**
    * Va primero entre los drivers de DriverManager, por donde GeneXus abre sus conexiones: para cada url y usuario
    * abre una sola conexion real (con el driver que corresponde) y devuelve siempre la misma, envuelta en Compartida.
    */
   static final class DriverCompartido implements java.sql.Driver {
      static final Map<String, Compartida> abiertas = new LinkedHashMap<>();
      static final Map<String, Connection> envueltas = new HashMap<>();

      static java.sql.Driver real(String url) throws SQLException {
         for (java.sql.Driver d : Collections.list(java.sql.DriverManager.getDrivers()))
            if (!(d instanceof DriverCompartido) && d.acceptsURL(url)) return d;
         return null;
      }

      public Connection connect(String url, Properties info) throws SQLException {
         java.sql.Driver d = real(url);
         if (d == null) return null;
         String clave = url + "|" + (info == null ? "" : info.getProperty("user", ""));
         synchronized (abiertas) {
            Compartida c = abiertas.get(clave);
            if (c != null && !c.real.isClosed()) return envueltas.get(clave);
            Connection cn = d.connect(url, info);
            if (cn == null) return null;
            c = new Compartida(cn);
            Connection p = (Connection) Proxy.newProxyInstance(Connection.class.getClassLoader(), new Class<?>[]{Connection.class}, c);
            abiertas.put(clave, c);
            envueltas.put(clave, p);
            return p;
         }
      }

      public boolean acceptsURL(String url) throws SQLException { return real(url) != null; }
      public java.sql.DriverPropertyInfo[] getPropertyInfo(String url, Properties info) { return new java.sql.DriverPropertyInfo[0]; }
      public int getMajorVersion() { return 1; }
      public int getMinorVersion() { return 0; }
      public boolean jdbcCompliant() { return false; }
      public java.util.logging.Logger getParentLogger() throws java.sql.SQLFeatureNotSupportedException {
         throw new java.sql.SQLFeatureNotSupportedException();
      }
   }

   static void instalarDriver() throws SQLException {
      List<java.sql.Driver> previos = Collections.list(java.sql.DriverManager.getDrivers());
      for (java.sql.Driver d : previos) java.sql.DriverManager.deregisterDriver(d);
      java.sql.DriverManager.registerDriver(new DriverCompartido());
      for (java.sql.Driver d : previos) java.sql.DriverManager.registerDriver(d);
   }

   /** {commits, rollbacks} simulados hasta ahora, sumando las bases. */
   static int[] contadores() {
      int c = 0, r = 0;
      synchronized (DriverCompartido.abiertas) {
         for (Compartida x : DriverCompartido.abiertas.values()) {
            c += x.commits;
            r += x.rollbacks;
         }
      }
      return new int[]{c, r};
   }

   // ------------------------------------------------------------------ seguridad

   /** La seguridad integrada sin login de GAM: el proveedor acepta la sesion; lo demas lo hace el de GeneXus. */
   static void sinLogin() throws Exception {
      Field f = com.genexus.security.GXSecurityProvider.class.getDeclaredField("instance");
      f.setAccessible(true);
      com.genexus.security.SecurityProvider real = com.genexus.security.GXSecurityProvider.getInstance();
      f.set(null, Proxy.newProxyInstance(Pantallas.class.getClassLoader(), new Class<?>[]{com.genexus.security.SecurityProvider.class},
         (p, m, a) -> {
            if (m.getName().equals("checksession") || m.getName().equals("checksessionprm")) {
               for (Object o : a) if (o instanceof boolean[]) ((boolean[]) o)[0] = true;
               return null;
            }
            try {
               return m.invoke(real, a);
            } catch (InvocationTargetException e) {
               throw e.getCause();
            }
         }));
   }

   // ------------------------------------------------------------------ sesiones

   static final Map<String, Map<String, Object>> sesiones = new HashMap<>();
   static final Map<String, Map<String, String>> galletas = new HashMap<>();

   /** Deshace todo lo que hicieron las pantallas (en todas las bases) y, si se pide, olvida las sesiones. */
   static JSONObject reiniciar(boolean tambienSesiones) {
      JSONArray errores = new JSONArray();
      synchronized (DriverCompartido.abiertas) {
         for (Map.Entry<String, Compartida> e : DriverCompartido.abiertas.entrySet()) {
            try {
               e.getValue().reiniciar();
            } catch (Throwable t) {
               errores.put(e.getKey().replaceAll("\\|.*", "") + ": " + GxMotor.mensaje(t));
            }
         }
      }
      if (tambienSesiones) {
         sesiones.clear();
         galletas.clear();
      }
      JSONObject r = new JSONObject();
      r.put("ok", errores.isEmpty());
      r.put("errores", errores);
      return r;
   }

   // ------------------------------------------------------------------ el pedido HTTP

   interface Manejo { Object llamar(Method m, Object[] a) throws Throwable; }

   @SuppressWarnings("unchecked")
   static <T> T simular(Class<T> i, Manejo h) {
      return (T) Proxy.newProxyInstance(i.getClassLoader(), new Class<?>[]{i}, (p, m, a) -> {
         if (m.getDeclaringClass() == Object.class) {
            if (m.getName().equals("hashCode")) return System.identityHashCode(p);
            if (m.getName().equals("equals")) return p == a[0];
            return i.getSimpleName();
         }
         Object r = h.llamar(m, a);
         Class<?> t = m.getReturnType();
         if (r == null && t.isPrimitive()) {
            if (t == boolean.class) return false;
            if (t == int.class) return 0;
            if (t == long.class) return 0L;
         }
         return r;
      });
   }

   /** Parametros de una query o de un cuerpo application/x-www-form-urlencoded. */
   static void parametros(String texto, Map<String, List<String>> salida) {
      if (texto == null || texto.isEmpty()) return;
      for (String par : texto.split("&")) {
         if (par.isEmpty()) continue;
         int i = par.indexOf('=');
         try {
            String k = java.net.URLDecoder.decode(i < 0 ? par : par.substring(0, i), StandardCharsets.UTF_8);
            String v = i < 0 ? "" : java.net.URLDecoder.decode(par.substring(i + 1), StandardCharsets.UTF_8);
            salida.computeIfAbsent(k, x -> new ArrayList<>()).add(v);
         } catch (IllegalArgumentException e) {
            // una query de GeneXus (cifrada, o valores separados por coma) la lee el objeto con GetNextPar
         }
      }
   }

   static Method sinArgs(Class<?> c, String n) throws NoSuchMethodException {
      for (Class<?> k = c; k != null; k = k.getSuperclass())
         for (Method m : k.getDeclaredMethods())
            if (m.getName().equals(n) && m.getParameterCount() == 0) {
               m.setAccessible(true);
               return m;
            }
      throw new NoSuchMethodException(n);
   }

   static ICookie galleta(String nombre, String valor) {
      return simular(ICookie.class, (m, a) -> {
         switch (m.getName()) {
            case "getName": return nombre;
            case "getValue": return valor;
            default: return null;
         }
      });
   }

   static JSONObject respuesta(int estado, String tipo, byte[] cuerpo) {
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("estado", estado);
      r.put("headers", new JSONObject().put("Content-Type", tipo));
      r.put("cuerpo", Base64.getEncoder().encodeToString(cuerpo));
      return r;
   }

   /**
    * La query con la que se abre una pantalla con estos parametros, como la arma GeneXus en un link(): los valores
    * separados por coma y, si el objeto cifra sus parametros (Encrypt URL parameters = Site key, el valor por
    * defecto), cifrados con la clave del sitio y un checksum que incluye el nombre de la clase.
    */
   static String queryDeParametros(String clase, Class<?> stub, JSONArray valores) throws Exception {
      StringBuilder plano = new StringBuilder();
      for (int i = 0; i < valores.length(); i++) {
         if (i > 0) plano.append(',');
         plano.append(GXutil.URLEncode(GXutil.rtrim(valores.optString(i, ""))));
      }
      String cifrado = "";
      if (stub != null) {
         try {
            Object s = stub.getConstructor().newInstance();
            cifrado = String.valueOf(sinArgs(stub, "EncryptURLParameters").invoke(s));
         } catch (NoSuchMethodException e) {
            // sin la propiedad: parametros sin cifrar
         }
      }
      if (!"SITE".equalsIgnoreCase(cifrado)) return plano.toString();
      String tmp = clase + plano;
      String clave = new ModelContext(GxMotor.clasesCfg).getSiteKey();
      return com.genexus.util.Encryption.uriencrypt64(tmp + com.genexus.util.Encryption.checksum(tmp, 6), clave);
   }

   /**
    * {clase, query} -> {parametros}: los valores de una query que armo un link() (la inversa de queryDeParametros),
    * o parametros null si no es de esa clase (otra forma de pedido, como dyncomponent o gxajaxEvt).
    */
   static JSONObject parametrosDeQuery(JSONObject req) throws Exception {
      String clase = req.getString("clase");
      String query = req.optString("query", "");
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("parametros", JSONObject.NULL);
      String plano = null;
      try {
         String s = com.genexus.util.Encryption.uridecrypt64(query, new ModelContext(GxMotor.clasesCfg).getSiteKey());
         if (s != null && s.length() > 6) {
            String tmp = s.substring(0, s.length() - 6);
            if (tmp.startsWith(clase) && com.genexus.util.Encryption.checksum(tmp, 6).equals(s.substring(s.length() - 6)))
               plano = tmp.substring(clase.length());
         }
      } catch (Throwable e) {
         // no esta cifrada
      }
      if (plano == null && !query.contains("=") && !query.startsWith("gx") && !query.startsWith("dyn") && !query.isEmpty())
         plano = query;  // sin cifrar: valores separados por coma
      if (plano == null) return r;
      JSONArray valores = new JSONArray();
      if (!plano.isEmpty())
         for (String v : plano.split(",", -1)) valores.put(java.net.URLDecoder.decode(v, StandardCharsets.UTF_8));
      r.put("parametros", valores);
      return r;
   }

   /**
    * {clase, parametros: [valores]} -> {query}: la query para abrir la pantalla con esos parametros.
    */
   static JSONObject query(JSONObject req) throws Exception {
      String clase = req.getString("clase");
      Class<?> stub = null;
      try {
         stub = Class.forName(clase);
      } catch (ClassNotFoundException e) {
         // sin servlet: sin cifrar
      }
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("query", queryDeParametros(clase, stub, req.optJSONArray("parametros") == null ? new JSONArray() : req.getJSONArray("parametros")));
      return r;
   }

   /**
    * Un pedido HTTP a una pantalla: {sesion, metodo, ruta (servlet/com.x.y o com.x.y), query, cuerpo (base64),
    * headers, contexto ("/vista/Generales/s1"), host ("127.0.0.1:8765"), permisos}. Devuelve {estado, headers,
    * cuerpo (base64), commits y rollbacks simulados durante el pedido, excepcion}.
    */
   static JSONObject pedido(JSONObject req) throws Exception {
      if (!GxMotor.modoPantallas) throw new IllegalStateException("Este motor no es el de pantallas");
      String sesion = req.optString("sesion", "s");
      String metodo = req.optString("metodo", "GET").toUpperCase(Locale.ROOT);
      String ruta = req.getString("ruta").replaceFirst("^/+", "");
      String query = req.optString("query", "");
      byte[] cuerpo = Base64.getDecoder().decode(req.optString("cuerpo", ""));
      String contexto = req.optString("contexto", "");
      String[] host = req.optString("host", "localhost:80").split(":");
      System.setProperty("gxp.permisos", req.optString("permisos", "todos"));
      Map<String, String> headers = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
      JSONObject hs = req.optJSONObject("headers");
      if (hs != null) for (String k : hs.keySet()) headers.put(k, hs.optString(k));

      String clase = ruta.replaceFirst("^servlet/", "");
      Class<?> impl;
      try {
         impl = Class.forName(clase + "_impl");
      } catch (ClassNotFoundException | NoClassDefFoundError e) {
         return respuesta(404, "text/plain; charset=utf-8", ("No encuentro la pantalla compilada (" + clase + "_impl): si es de la KB, falta hacer Build en GeneXus.").getBytes(StandardCharsets.UTF_8));
      }
      Class<?> stub = null;
      try {
         stub = Class.forName(clase);
      } catch (ClassNotFoundException e) {
         // sin servlet: se usa el contexto de la KB
      }

      Map<String, List<String>> params = new LinkedHashMap<>();
      parametros(query, params);
      String tipo = headers.getOrDefault("Content-Type", "");
      if (tipo.startsWith("application/x-www-form-urlencoded")) parametros(new String(cuerpo, StandardCharsets.UTF_8), params);

      Map<String, Object> atributos = sesiones.computeIfAbsent(sesion, x -> new HashMap<>());
      Map<String, String> jar = galletas.computeIfAbsent(sesion, x -> new LinkedHashMap<>());
      Map<String, Object> atributosPedido = new HashMap<>();

      IServletContext servlet = simular(IServletContext.class, (m, a) -> {
         switch (m.getName()) {
            case "getRealPath": return new File(a[0] == null ? "" : String.valueOf(a[0]).replaceFirst("^/+", "")).getAbsolutePath();
            case "getServerInfo": return "GxPruebas";
            case "getMajorVersion": return 5;
            case "getTEMPDIR": return System.getProperty("java.io.tmpdir");
            default: return null;
         }
      });
      IHttpSession ses = simular(IHttpSession.class, (m, a) -> {
         switch (m.getName()) {
            case "getAttribute": return atributos.get((String) a[0]);
            case "setAttribute": atributos.put((String) a[0], a[1]); return null;
            case "removeAttribute": atributos.remove((String) a[0]); return null;
            case "getAttributeNames": return Collections.enumeration(new ArrayList<>(atributos.keySet()));
            case "getId": return "gxpruebas-" + sesion;
            case "invalidate": atributos.clear(); return null;
            default: return null;
         }
      });
      String uri = contexto + "/" + ruta;
      IHttpServletRequest pedido = simular(IHttpServletRequest.class, (m, a) -> {
         switch (m.getName()) {
            case "getMethod": return metodo;
            case "getQueryString": return query.isEmpty() ? null : query;
            case "getContextPath": return contexto;
            case "getServletPath": return "/" + ruta;
            case "getRequestURI": return uri;
            case "getRequestURL": return new StringBuffer("http://" + String.join(":", host) + uri);
            case "getServerName": return host[0];
            case "getServerPort": return host.length > 1 ? Integer.parseInt(host[1]) : 80;
            case "getScheme": return "http";
            case "isSecure": return false;
            case "getRemoteAddr": case "getRemoteHost": return "127.0.0.1";
            case "getHeader": return headers.get((String) a[0]);
            case "getHeaders": {
               String v = headers.get((String) a[0]);
               return Collections.enumeration(v == null ? List.of() : List.of(v));
            }
            case "getHeaderNames": return Collections.enumeration(new ArrayList<>(headers.keySet()));
            case "getParameterNames": return Collections.enumeration(new ArrayList<>(params.keySet()));
            case "getParameterValues": {
               List<String> v = params.get((String) a[0]);
               return v == null ? null : v.toArray(new String[0]);
            }
            case "getCharacterEncoding": return "UTF-8";
            case "getContentType": return tipo.isEmpty() ? null : tipo;
            case "getContentLength": return cuerpo.length;
            case "getReader": return new BufferedReader(new InputStreamReader(new ByteArrayInputStream(cuerpo), StandardCharsets.UTF_8));
            case "getInputStream": {
               InputStream in = new ByteArrayInputStream(cuerpo);
               return simular(IServletInputStream.class, (mm, aa) -> in);
            }
            case "getSession": return ses;
            case "getCookies": {
               List<ICookie> l = new ArrayList<>();
               for (Map.Entry<String, String> e : jar.entrySet()) l.add(galleta(e.getKey(), e.getValue()));
               return l.toArray(new ICookie[0]);
            }
            case "getAttribute": return atributosPedido.get((String) a[0]);
            case "setAttribute": atributosPedido.put((String) a[0], a[1]); return null;
            case "getServletContext": return servlet;
            case "getRealPath": return new File(String.valueOf(a[0]).replaceFirst("^/+", "")).getAbsolutePath();
            case "isRequestedSessionIdValid": return true;
            case "getRequestedSessionId": return "gxpruebas-" + sesion;
            default: return null;
         }
      });

      ByteArrayOutputStream salida = new ByteArrayOutputStream();
      PrintWriter escritor = new PrintWriter(new OutputStreamWriter(salida, StandardCharsets.UTF_8), true);
      JSONObject cabeceras = new JSONObject();
      int[] estado = {200};
      IServletOutputStream flujo = simular(IServletOutputStream.class, (m, a) -> {
         String n = m.getName();
         if (n.equals("getOutputStream")) return salida;
         if (n.equals("write")) {
            if (a[0] instanceof byte[]) {
               if (a.length == 3) salida.write((byte[]) a[0], (int) a[1], (int) a[2]);
               else salida.write((byte[]) a[0]);
            } else {
               salida.write((int) a[0]);
            }
         } else if (n.startsWith("print")) {
            salida.write((a == null || a.length == 0 ? "" : String.valueOf(a[0])).getBytes(StandardCharsets.UTF_8));
            if (n.equals("println")) salida.write('\n');
         }
         return null;
      });
      IHttpServletResponse respuesta = simular(IHttpServletResponse.class, (m, a) -> {
         switch (m.getName()) {
            case "getWriter": return escritor;
            case "getOutputStream": return flujo;
            case "setHeader": case "addHeader": cabeceras.put((String) a[0], String.valueOf(a[1])); return null;
            case "setContentType": cabeceras.put("Content-Type", String.valueOf(a[0])); return null;
            case "setStatus": estado[0] = (int) a[0]; return null;
            case "sendError":
               estado[0] = (int) a[0];
               if (a.length > 1) escritor.print(a[1]);
               return null;
            case "addCookie": {
               ICookie g = (ICookie) a[0];
               jar.put(g.getName(), g.getValue());
               return null;
            }
            case "isCommitted": return false;
            case "getHeaders": return List.of();
            default: return null;
         }
      });

      int[] antes = contadores();
      String excepcion = null;
      com.genexus.internet.HttpAjaxContext http = new com.genexus.internet.HttpAjaxContext(metodo, pedido, respuesta, servlet);
      ModelContext mc = ModelContext.getModelContext(stub != null ? stub : GxMotor.clasesCfg);
      mc.setHttpContext(http);
      http.setContext(mc);
      try {
         Object panel = impl.getConstructor(com.genexus.internet.HttpContext.class).newInstance(http);
         sinArgs(impl, "doExecute").invoke(panel);
      } catch (InvocationTargetException e) {
         excepcion = GxMotor.traza(e.getCause());
      } catch (Throwable e) {
         excepcion = GxMotor.traza(e);
      }
      try {
         http.flushStream();
      } catch (Throwable e) {
         // ya se escribio todo
      }
      escritor.flush();
      if (excepcion != null && salida.size() == 0) {
         estado[0] = 500;
         cabeceras.put("Content-Type", "text/plain; charset=utf-8");
         salida.write(excepcion.getBytes(StandardCharsets.UTF_8));
      }
      int[] despues = contadores();
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("estado", estado[0]);
      r.put("headers", cabeceras);
      r.put("cuerpo", Base64.getEncoder().encodeToString(salida.toByteArray()));
      r.put("commits", despues[0] - antes[0]);
      r.put("rollbacks", despues[1] - antes[1]);
      if (excepcion != null) r.put("excepcion", excepcion);
      return r;
   }
}
