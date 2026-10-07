import com.genexus.*;
import com.genexus.db.*;
import org.json.*;

import java.io.*;
import java.lang.reflect.*;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Savepoint;
import java.sql.Statement;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.*;

/**
 * Motor de ejecucion de GxPruebas. Corre dentro de la JVM con el classpath de una KB (las clases que
 * genero GeneXus) y ejecuta cualquier procedimiento o Data Provider por reflexion.
 *
 * Protocolo: una linea JSON por pedido en stdin; una linea por respuesta en stdout, con el prefijo MARCA
 * (lo que no lleva la marca se ignora). Todo lo que el codigo generado escriba en System.out / System.err
 * se captura y vuelve en "consola".
 *
 * Pedidos:
 *   {"id":1, "cmd":"ping"}
 *   {"id":2, "cmd":"describir", "clase":"com.generales.generales.interfases.registro.set"}
 *   {"id":3, "cmd":"ejecutar", "clase":"...", "args":[{"modo":"in","valor":{...}}, {"modo":"out"}], "timeoutMs":60000}
 *   {"id":4, "cmd":"sql", "ds":"GENERALES", "query":"select ...", "max":500}
 *   {"id":5, "cmd":"rollback"}   {"id":6, "cmd":"commit"}   {"id":7, "cmd":"salir"}
 *   {"id":8, "cmd":"marcar", "ds":["GENERALES"], "otros":["SISTEMA"]}   {"id":9, "cmd":"volver"}   {"id":10, "cmd":"avanzar"}
 *
 * La transaccion queda abierta entre pedidos: el que llama decide cuando hacer rollback o commit. Asi un
 * escenario puede ejecutar varios objetos, consultar la base con SQL (ve los cambios sin confirmar,
 * porque usa la misma conexion) y deshacer todo al final.
 *
 * "marcar" pone un savepoint en la conexion de cada datasource (despues del script previo de una suite) y
 * "volver" deshace todo lo posterior: en esos datasources hasta el savepoint, en los demas por completo. Asi
 * cada caso arranca de la base que dejo el script, sin volver a correrlo. Hasta el fin de la transaccion, el
 * commit y el rollback de los objetos en esos datasources se simulan con savepoints (ver Protegida). Si el
 * savepoint se perdio (cambio la conexion), "volver" lo informa en "perdidos". Con los casos encadenados, "avanzar"
 * no deshace nada: el fin de un caso cuenta como un commit simulado (un rollback en el siguiente vuelve ahi).
 */
public class GxMotor {

   static final String MARCA = "\u0001GXR ";
   static final int MAX_CONSOLA = 200_000;

   static PrintStream proto;
   static PrintStream diag;
   static final ByteArrayOutputStream consola = new ByteArrayOutputStream();
   static ModelContext ctx;
   static int rh;
   static String ns;
   static final List<String> dataSources = new ArrayList<>();
   static final ScheduledExecutorService guardian = Executors.newSingleThreadScheduledExecutor(r -> {
      Thread t = new Thread(r, "gxmotor-guardian");
      t.setDaemon(true);
      return t;
   });
   static Date fechaNula;

   public static void main(String[] args) throws Exception {
      proto = new PrintStream(new FileOutputStream(FileDescriptor.out), true, StandardCharsets.UTF_8);
      diag = new PrintStream(new FileOutputStream(FileDescriptor.err), true, StandardCharsets.UTF_8);
      PrintStream captura = new PrintStream(new OutputStream() {
         @Override public void write(int b) {
            synchronized (consola) { if (consola.size() < MAX_CONSOLA) consola.write(b); }
         }
         @Override public void write(byte[] b, int off, int len) {
            synchronized (consola) {
               int n = Math.min(len, MAX_CONSOLA - consola.size());
               if (n > 0) consola.write(b, off, n);
            }
         }
      }, true, StandardCharsets.UTF_8);
      System.setOut(captura);
      System.setErr(captura);

      ns = args[0];
      if (args.length > 1 && !args[1].isBlank()) dataSources.addAll(Arrays.asList(args[1].split(",")));

      long t0 = System.nanoTime();
      try {
         Class<?> cfg = Class.forName(ns + ".GXcfg");
         ApplicationContext.getInstance().setCurrentLocation("");
         Application.init(cfg);
         ctx = new ModelContext(cfg);
         // Un solo handle para todo: cada handle nuevo abre conexiones que no se liberan.
         rh = Application.getNewRemoteHandle(ctx);
         fechaNula = calcularFechaNula();
      } catch (Throwable e) {
         JSONObject r = new JSONObject();
         r.put("evento", "error_inicio");
         r.put("error", traza(e));
         r.put("consola", tomarConsola());
         enviar(r);
         System.exit(2);
      }
      JSONObject listo = new JSONObject();
      listo.put("evento", "listo");
      listo.put("ns", ns);
      listo.put("java", System.getProperty("java.version"));
      listo.put("ms", (System.nanoTime() - t0) / 1_000_000);
      listo.put("consola", tomarConsola());
      enviar(listo);

      BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
      String linea;
      while ((linea = in.readLine()) != null) {
         if (linea.isBlank()) continue;
         JSONObject req;
         try {
            req = new JSONObject(linea);
         } catch (Exception e) {
            JSONObject r = new JSONObject();
            r.put("ok", false);
            r.put("error", "Pedido invalido: " + e.getMessage());
            enviar(r);
            continue;
         }
         atender(req);
      }
      System.exit(0);
   }

   /**
    * El pedido se atiende en el hilo principal: GeneXus guarda el ModelContext por hilo y en otro hilo
    * las conexiones fallan. El limite de tiempo lo controla un guardian: si se cumple, responde y termina
    * la JVM (la base descarta la transaccion abierta al cortarse la conexion).
    */
   static void atender(JSONObject req) {
      Object id = req.opt("id");
      String cmd = req.optString("cmd");
      long timeout = req.optLong("timeoutMs", 120_000);
      tomarConsola();
      long t0 = System.nanoTime();
      java.util.concurrent.atomic.AtomicBoolean terminado = new java.util.concurrent.atomic.AtomicBoolean(false);
      ScheduledFuture<?> guardia = guardian.schedule(() -> {
         if (!terminado.compareAndSet(false, true)) return;
         JSONObject r = new JSONObject();
         r.put("id", id);
         r.put("ok", false);
         r.put("timeout", true);
         r.put("error", "Tiempo agotado (" + timeout + " ms). El motor se reinicia y la transaccion se descarta.");
         r.put("ms", (System.nanoTime() - t0) / 1_000_000.0);
         r.put("consola", tomarConsola());
         enviar(r);
         Runtime.getRuntime().halt(3);
      }, timeout, TimeUnit.MILLISECONDS);
      JSONObject r;
      try {
         r = despachar(cmd, req);
      } catch (Throwable e) {
         r = new JSONObject();
         r.put("ok", false);
         r.put("error", mensaje(e));
         r.put("excepcion", traza(e));
      }
      guardia.cancel(false);
      if (!terminado.compareAndSet(false, true)) return;
      r.put("id", id);
      r.put("ms", (System.nanoTime() - t0) / 1_000_000.0);
      r.put("consola", tomarConsola());
      enviar(r);
      if ("salir".equals(cmd)) System.exit(0);
   }

   static JSONObject despachar(String cmd, JSONObject req) throws Exception {
      switch (cmd) {
         case "ping": {
            JSONObject r = new JSONObject();
            r.put("ok", true);
            r.put("ns", ns);
            return r;
         }
         case "describir": return describir(req.getString("clase"));
         case "ejecutar": return ejecutar(req);
         case "sql": return sql(req);
         case "rollback": return finTransaccion(false);
         case "commit": return finTransaccion(true);
         case "marcar": return marcar(req.optJSONArray("ds"), req.optJSONArray("otros"));
         case "volver": return terminarCaso(true);
         case "avanzar": return terminarCaso(false);
         case "salir": {
            JSONObject r = new JSONObject();
            r.put("ok", true);
            return r;
         }
         default: throw new IllegalArgumentException("Comando desconocido: " + cmd);
      }
   }

   // ------------------------------------------------------------------ describir

   static Method metodoExecute(Class<?> c) {
      Method mejor = null;
      for (Method m : c.getMethods()) {
         if (!m.getName().equals("execute") || Modifier.isStatic(m.getModifiers())) continue;
         if (mejor == null || m.getParameterCount() > mejor.getParameterCount()) mejor = m;
      }
      if (mejor == null) throw new IllegalArgumentException("La clase " + c.getName() + " no tiene un metodo execute: no es un procedimiento ni un Data Provider.");
      return mejor;
   }

   static JSONObject describir(String clase) throws Exception {
      Class<?> c = Class.forName(clase);
      Method m = metodoExecute(c);
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("clase", clase);
      r.put("superclase", c.getSuperclass() == null ? "" : c.getSuperclass().getName());
      JSONArray ps = new JSONArray();
      Type[] gen = m.getGenericParameterTypes();
      Class<?>[] raw = m.getParameterTypes();
      for (int i = 0; i < raw.length; i++) {
         JSONObject p = new JSONObject();
         boolean porRef = raw[i].isArray();
         Class<?> base = porRef ? raw[i].getComponentType() : raw[i];
         Type baseGen = porRef ? componente(gen[i]) : gen[i];
         p.put("indice", i);
         p.put("porReferencia", porRef);
         p.put("tipoJava", nombreTipo(baseGen));
         p.put("clase", clasificar(base));
         try {
            p.put("plantilla", plantilla(base, baseGen, 0));
         } catch (Throwable e) {
            p.put("plantilla", JSONObject.NULL);
            p.put("errorPlantilla", mensaje(e));
         }
         ps.put(p);
      }
      r.put("parametros", ps);
      return r;
   }

   static Type componente(Type t) {
      if (t instanceof GenericArrayType) return ((GenericArrayType) t).getGenericComponentType();
      if (t instanceof Class && ((Class<?>) t).isArray()) return ((Class<?>) t).getComponentType();
      return t;
   }

   static String nombreTipo(Type t) {
      if (t instanceof Class) return ((Class<?>) t).getSimpleName();
      if (t instanceof ParameterizedType) {
         ParameterizedType p = (ParameterizedType) t;
         StringBuilder sb = new StringBuilder(((Class<?>) p.getRawType()).getSimpleName()).append('<');
         Type[] a = p.getActualTypeArguments();
         for (int i = 0; i < a.length; i++) {
            if (i > 0) sb.append(", ");
            sb.append(nombreTipo(a[i]));
         }
         return sb.append('>').toString();
      }
      return t.getTypeName();
   }

   static String clasificar(Class<?> c) {
      if (GXSimpleCollection.class.isAssignableFrom(c)) return "coleccion";
      if (GxUserType.class.isAssignableFrom(c)) return "sdt";
      if (c == String.class) return "texto";
      if (c == boolean.class || c == Boolean.class) return "booleano";
      if (Date.class.isAssignableFrom(c)) return "fecha";
      if (c.isPrimitive() || Number.class.isAssignableFrom(c)) return "numero";
      if (c == UUID.class) return "guid";
      return "otro";
   }

   static Class<?> claseElemento(Type t) {
      if (t instanceof ParameterizedType) {
         Type a = ((ParameterizedType) t).getActualTypeArguments()[0];
         if (a instanceof Class) return (Class<?>) a;
         if (a instanceof ParameterizedType) return (Class<?>) ((ParameterizedType) a).getRawType();
      }
      return String.class;
   }

   static Object plantilla(Class<?> c, Type gen, int prof) throws Exception {
      if (GXSimpleCollection.class.isAssignableFrom(c)) {
         JSONArray a = new JSONArray();
         if (prof < 6) {
            Class<?> el = claseElemento(gen);
            a.put(plantilla(el, el, prof + 1));
         }
         return a;
      }
      if (GxUserType.class.isAssignableFrom(c)) {
         Object inst = nuevaInstancia(c);
         // Las subestructuras y colecciones quedan en null hasta que alguien llama al getter, y en ese
         // estado no salen en el JSON. Llamar a los getters las inicializa con sus nombres reales.
         for (Method g : c.getMethods()) {
            if (g.getParameterCount() != 0 || !g.getName().startsWith("getgxTv_")) continue;
            Class<?> rt = g.getReturnType();
            if (GxUserType.class.isAssignableFrom(rt) || GXSimpleCollection.class.isAssignableFrom(rt)) {
               try { g.invoke(inst); } catch (Throwable ignorar) { }
            }
         }
         String js = ((GxUserType) inst).toJSonString(false, true);
         Object o = parsear(js);
         if (o instanceof JSONObject && prof < 6) completar(c, (JSONObject) o, prof);
         return o;
      }
      return defecto(c);
   }

   /** Completa las colecciones y subestructuras vacias de la plantilla con un elemento de ejemplo. */
   static void completar(Class<?> c, JSONObject o, int prof) {
      for (String k : new ArrayList<>(o.keySet())) {
         Object v = o.get(k);
         boolean arrVacio = v instanceof JSONArray && ((JSONArray) v).isEmpty();
         if (!arrVacio && !(v instanceof JSONObject)) continue;
         Method g = getter(c, k);
         if (g == null) continue;
         try {
            Class<?> rt = g.getReturnType();
            if (arrVacio && GXSimpleCollection.class.isAssignableFrom(rt)) {
               Class<?> el = claseElemento(g.getGenericReturnType());
               JSONArray a = new JSONArray();
               a.put(plantilla(el, el, prof + 1));
               o.put(k, a);
            } else if (v instanceof JSONObject && GxUserType.class.isAssignableFrom(rt)) {
               o.put(k, plantilla(rt, rt, prof + 1));
            }
         } catch (Throwable ignorar) {
         }
      }
   }

   static Method getter(Class<?> c, String campo) {
      String fin = "_" + campo.toLowerCase(Locale.ROOT);
      for (Method m : c.getMethods()) {
         String n = m.getName().toLowerCase(Locale.ROOT);
         if (m.getParameterCount() == 0 && n.startsWith("getgxtv_") && n.endsWith(fin)) return m;
      }
      return null;
   }

   static Object defecto(Class<?> c) {
      switch (clasificar(c)) {
         case "texto": return "";
         case "booleano": return false;
         case "numero": return 0;
         case "fecha": return "";
         case "guid": return "00000000-0000-0000-0000-000000000000";
         default: return JSONObject.NULL;
      }
   }

   // ------------------------------------------------------------------ ejecutar

   static JSONObject ejecutar(JSONObject req) throws Exception {
      Class<?> c = Class.forName(req.getString("clase"));
      Method m = metodoExecute(c);
      JSONArray args = req.optJSONArray("args");
      if (args == null) args = new JSONArray();
      Class<?>[] raw = m.getParameterTypes();
      Type[] gen = m.getGenericParameterTypes();
      if (args.length() != raw.length)
         throw new IllegalArgumentException("El objeto recibe " + raw.length + " parametros y llegaron " + args.length() + ".");

      Object[] valores = new Object[raw.length];
      for (int i = 0; i < raw.length; i++) {
         JSONObject a = args.getJSONObject(i);
         String modo = a.optString("modo", "in");
         Object v = a.has("valor") ? a.get("valor") : null;
         try {
            if (raw[i].isArray()) {
               Class<?> base = raw[i].getComponentType();
               Object arr = Array.newInstance(base, 1);
               Object val = "out".equals(modo) || v == null ? valorInicial(base, componente(gen[i])) : aJava(base, componente(gen[i]), v);
               Array.set(arr, 0, val);
               valores[i] = arr;
            } else {
               valores[i] = v == null ? valorInicial(raw[i], gen[i]) : aJava(raw[i], gen[i], v);
            }
         } catch (Exception e) {
            throw new IllegalArgumentException("Parametro " + (i + 1) + ": " + mensaje(e), e);
         }
      }

      Object obj = nuevoObjeto(c);
      JSONObject r = new JSONObject();
      long t0 = System.nanoTime();
      Throwable falla = null;
      try {
         m.invoke(obj, valores);
      } catch (InvocationTargetException e) {
         falla = e.getCause();
      }
      r.put("msEjecucion", (System.nanoTime() - t0) / 1_000_000.0);

      JSONArray salidas = new JSONArray();
      for (int i = 0; i < raw.length; i++) {
         Object v = raw[i].isArray() ? Array.get(valores[i], 0) : valores[i];
         try {
            salidas.put(aJson(v));
         } catch (Throwable e) {
            salidas.put("<<no se pudo serializar: " + mensaje(e) + ">>");
         }
      }
      r.put("salidas", salidas);
      if (falla != null) {
         r.put("ok", false);
         r.put("error", mensaje(falla));
         r.put("excepcion", traza(falla));
      } else {
         r.put("ok", true);
      }
      return r;
   }

   static Object nuevoObjeto(Class<?> c) throws Exception {
      try {
         return c.getConstructor(int.class, ModelContext.class).newInstance(rh, ctx);
      } catch (NoSuchMethodException e) {
         return c.getConstructor(int.class).newInstance(rh);
      }
   }

   static Object nuevaInstancia(Class<?> c) throws Exception {
      try { return c.getConstructor(int.class, ModelContext.class).newInstance(rh, ctx); } catch (NoSuchMethodException ignorar) { }
      try { return c.getConstructor(ModelContext.class).newInstance(ctx); } catch (NoSuchMethodException ignorar) { }
      try { return c.getConstructor(int.class).newInstance(rh); } catch (NoSuchMethodException ignorar) { }
      return c.getConstructor().newInstance();
   }

   @SuppressWarnings({"unchecked", "rawtypes"})
   static Object nuevaColeccion(Class<?> c, Type gen) throws Exception {
      Class<?> el = claseElemento(gen);
      if (GXBaseCollection.class.isAssignableFrom(c) && GxUserType.class.isAssignableFrom(el)) {
         String item = el.getSimpleName().startsWith("Sdt") ? el.getSimpleName().substring(3) : el.getSimpleName();
         return new GXBaseCollection(el, item, "", rh);
      }
      return new GXSimpleCollection(el, "internal", "");
   }

   static Object valorInicial(Class<?> c, Type gen) throws Exception {
      if (GXSimpleCollection.class.isAssignableFrom(c)) return nuevaColeccion(c, gen);
      if (GxUserType.class.isAssignableFrom(c)) return nuevaInstancia(c);
      if (c == String.class) return "";
      if (c == boolean.class || c == Boolean.class) return false;
      if (Date.class.isAssignableFrom(c)) return fechaNula;
      if (c == UUID.class) return new UUID(0, 0);
      if (c == BigDecimal.class) return BigDecimal.ZERO;
      if (c.isPrimitive() || Number.class.isAssignableFrom(c)) return numero(c, BigDecimal.ZERO);
      return null;
   }

   static Object aJava(Class<?> c, Type gen, Object v) throws Exception {
      if (v == JSONObject.NULL) return valorInicial(c, gen);
      if (GXSimpleCollection.class.isAssignableFrom(c)) {
         Object col = nuevaColeccion(c, gen);
         String js = v instanceof String ? (String) v : v.toString();
         if (!((GXSimpleCollection<?>) col).fromJSonString(js)) throw new IllegalArgumentException("GeneXus no pudo leer la coleccion desde el JSON.");
         return col;
      }
      if (GxUserType.class.isAssignableFrom(c)) {
         Object inst = nuevaInstancia(c);
         String js = v instanceof String ? (String) v : v.toString();
         if (!((GxUserType) inst).fromJSonString(js)) throw new IllegalArgumentException("GeneXus no pudo leer el SDT desde el JSON.");
         return inst;
      }
      if (c == String.class) return v instanceof String ? v : String.valueOf(v);
      if (c == boolean.class || c == Boolean.class) {
         if (v instanceof Boolean) return v;
         String s = String.valueOf(v).trim().toLowerCase(Locale.ROOT);
         return s.equals("true") || s.equals("1") || s.equals("si") || s.equals("s");
      }
      if (Date.class.isAssignableFrom(c)) return fecha(String.valueOf(v));
      if (c == UUID.class) return UUID.fromString(String.valueOf(v).trim());
      if (c == BigDecimal.class || c.isPrimitive() || Number.class.isAssignableFrom(c)) {
         String s = String.valueOf(v).trim();
         return numero(c, s.isEmpty() ? BigDecimal.ZERO : new BigDecimal(s));
      }
      throw new IllegalArgumentException("Tipo de parametro no soportado: " + c.getName());
   }

   static Object numero(Class<?> c, BigDecimal d) {
      if (c == int.class || c == Integer.class) return d.intValue();
      if (c == long.class || c == Long.class) return d.longValue();
      if (c == short.class || c == Short.class) return d.shortValue();
      if (c == byte.class || c == Byte.class) return d.byteValue();
      if (c == double.class || c == Double.class) return d.doubleValue();
      if (c == float.class || c == Float.class) return d.floatValue();
      if (c == BigInteger.class) return d.toBigInteger();
      return d;
   }

   static Date fecha(String s) throws Exception {
      s = s.trim();
      if (s.isEmpty() || s.startsWith("0000-00-00") || s.equals("00/00/0000")) return fechaNula;
      String[] formatos = {"yyyy-MM-dd'T'HH:mm:ss.SSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd'T'HH:mm", "yyyy-MM-dd", "dd/MM/yyyy HH:mm:ss", "dd/MM/yyyy"};
      for (String f : formatos) {
         SimpleDateFormat df = new SimpleDateFormat(f);
         df.setLenient(false);
         try {
            if (s.length() == f.replace("'", "").length()) return df.parse(s);
         } catch (Exception ignorar) {
         }
      }
      throw new IllegalArgumentException("Fecha no reconocida: '" + s + "'. Usar aaaa-mm-dd o aaaa-mm-ddThh:mm:ss");
   }

   static Date calcularFechaNula() {
      for (String cn : new String[]{"com.genexus.GXutil", "com.genexus.CommonUtil"}) {
         try {
            return (Date) Class.forName(cn).getMethod("nullDate").invoke(null);
         } catch (Throwable ignorar) {
         }
      }
      return new GregorianCalendar(1, Calendar.JANUARY, 1).getTime();
   }

   static Object aJson(Object v) throws Exception {
      if (v == null) return JSONObject.NULL;
      if (v instanceof GxUserType) return parsear(((GxUserType) v).toJSonString(false, true));
      if (v instanceof GXSimpleCollection) return parsear(((GXSimpleCollection<?>) v).toJSonString(false));
      if (v instanceof Date) return textoFecha((Date) v);
      if (v instanceof UUID) return v.toString();
      if (v instanceof Number || v instanceof Boolean || v instanceof String) return v;
      if (v instanceof Character) return v.toString();
      return String.valueOf(v);
   }

   static String textoFecha(Date d) {
      if (d == null || (fechaNula != null && d.equals(fechaNula))) return "";
      Calendar c = Calendar.getInstance();
      c.setTime(d);
      if (c.get(Calendar.YEAR) <= 1) return "";
      boolean sinHora = c.get(Calendar.HOUR_OF_DAY) == 0 && c.get(Calendar.MINUTE) == 0 && c.get(Calendar.SECOND) == 0 && c.get(Calendar.MILLISECOND) == 0;
      return new SimpleDateFormat(sinHora ? "yyyy-MM-dd" : "yyyy-MM-dd'T'HH:mm:ss").format(d);
   }

   static Object parsear(String js) {
      if (js == null) return JSONObject.NULL;
      String t = js.trim();
      try {
         if (t.startsWith("{")) return new JSONObject(t);
         if (t.startsWith("[")) return new JSONArray(t);
      } catch (Exception ignorar) {
      }
      return js;
   }

   // ------------------------------------------------------------------ base de datos

   /** El nombre del datasource tal como lo conoce la KB (sin nombre: el ultimo, como en las consultas). */
   static String nombreDs(String ds) {
      if (ds == null || ds.isBlank()) return dataSources.isEmpty() ? "DEFAULT" : dataSources.get(dataSources.size() - 1);
      for (String d : dataSources) if (d.equalsIgnoreCase(ds.trim())) return d;
      return ds.trim();
   }

   static Connection conexion(String ds) throws Exception {
      com.genexus.db.driver.GXConnection c = DBConnectionManager.getInstance().getConnection(ctx, rh, nombreDs(ds), false, true);
      return c.getJDBCConnection();
   }

   static JSONObject sql(JSONObject req) throws Exception {
      String q = req.getString("query").trim();
      while (q.endsWith(";")) q = q.substring(0, q.length() - 1).trim();
      int max = req.optInt("max", 500);
      Connection cn = conexion(req.optString("ds", ""));
      JSONObject r = new JSONObject();
      try (Statement st = cn.createStatement()) {
         st.setMaxRows(max + 1);
         boolean hayFilas = st.execute(q);
         if (!hayFilas) {
            r.put("ok", true);
            r.put("actualizadas", st.getUpdateCount());
            return r;
         }
         try (ResultSet rs = st.getResultSet()) {
            ResultSetMetaData md = rs.getMetaData();
            JSONArray cols = new JSONArray();
            for (int i = 1; i <= md.getColumnCount(); i++) cols.put(md.getColumnLabel(i));
            JSONArray filas = new JSONArray();
            boolean truncado = false;
            while (rs.next()) {
               if (filas.length() >= max) { truncado = true; break; }
               JSONArray f = new JSONArray();
               for (int i = 1; i <= md.getColumnCount(); i++) f.put(valorSql(rs.getObject(i)));
               filas.put(f);
            }
            r.put("ok", true);
            r.put("columnas", cols);
            r.put("filas", filas);
            r.put("truncado", truncado);
         }
      }
      return r;
   }

   static Object valorSql(Object v) {
      if (v == null) return JSONObject.NULL;
      if (v instanceof java.sql.Timestamp || v instanceof java.sql.Date || v instanceof java.sql.Time) return v.toString();
      if (v instanceof java.time.temporal.TemporalAccessor) return v.toString();
      if (v instanceof byte[]) return "<binario " + ((byte[]) v).length + " bytes>";
      if (v instanceof Number || v instanceof Boolean || v instanceof String) return v;
      return String.valueOf(v);
   }

   static JSONObject finTransaccion(boolean confirmar) {
      desactivar();
      JSONObject r = new JSONObject();
      JSONArray errores = new JSONArray();
      for (String ds : todosLosDs()) finDs(ds, confirmar, errores);
      r.put("ok", errores.isEmpty());
      r.put("errores", errores);
      return r;
   }

   static List<String> todosLosDs() {
      return dataSources.isEmpty() ? List.of("DEFAULT") : dataSources;
   }

   static void finDs(String ds, boolean confirmar, JSONArray errores) {
      try {
         if (confirmar) DBConnectionManager.getInstance().commit(ctx, rh, ds);
         else DBConnectionManager.getInstance().rollback(ctx, rh, ds);
      } catch (Throwable e) {
         String m = mensaje(e);
         // Un datastore que nunca se uso no tiene conexion: no es un error.
         if (!m.toLowerCase(Locale.ROOT).contains("not connected") && !m.toLowerCase(Locale.ROOT).contains("no connection"))
            errores.put(ds + ": " + m);
      }
   }

   // ------------------------------------------------------------------ script previo: savepoint y commits simulados

   /**
    * Envuelve la conexion JDBC de un datasource (el campo "con" de GXConnection, por donde GeneXus hace commit y
    * rollback). Mientras esta activa, el commit de un objeto no llega a la base: pone el savepoint "gxp_commit"
    * (lo confirmado) y el rollback vuelve al ultimo commit o, si no hubo, al savepoint del script previo. Asi
    * nada confirma el script y los objetos que hacen commit se pueden probar igual.
    */
   static final class Protegida implements InvocationHandler {
      final Connection real;
      Savepoint previo, confirmado;
      boolean activa;
      int commits, rollbacks;

      Protegida(Connection real) { this.real = real; }

      public Object invoke(Object proxy, Method m, Object[] a) throws Throwable {
         if (activa && (a == null || a.length == 0)) {
            if (m.getName().equals("commit")) {
               confirmado = real.setSavepoint("gxp_commit");
               commits++;
               return null;
            }
            if (m.getName().equals("rollback")) {
               real.rollback(confirmado != null ? confirmado : previo);
               rollbacks++;
               return null;
            }
         }
         try {
            return m.invoke(real, a);
         } catch (InvocationTargetException e) {
            throw e.getCause();
         }
      }
   }

   static final Map<String, Protegida> protegidas = new LinkedHashMap<>();

   /** La Protegida instalada en la conexion actual del datasource (la instala si hace falta). */
   static Protegida proteger(String ds) throws Exception {
      com.genexus.db.driver.GXConnection gx = DBConnectionManager.getInstance().getConnection(ctx, rh, ds, false, true);
      Field f = com.genexus.db.driver.GXConnection.class.getDeclaredField("con");
      f.setAccessible(true);
      Connection actual = (Connection) f.get(gx);
      if (Proxy.isProxyClass(actual.getClass()) && Proxy.getInvocationHandler(actual) instanceof Protegida)
         return (Protegida) Proxy.getInvocationHandler(actual);
      Protegida p = new Protegida(actual);
      f.set(gx, Proxy.newProxyInstance(Connection.class.getClassLoader(), new Class<?>[]{Connection.class}, p));
      return p;
   }

   static void desactivar() {
      for (Protegida p : protegidas.values()) {
         p.activa = false;
         p.previo = p.confirmado = null;
      }
      protegidas.clear();
   }

   /** Savepoint del script previo en los datasources "ds" (obligatorios) y "otros" (los que se puedan). */
   static JSONObject marcar(JSONArray lista, JSONArray otros) throws Exception {
      desactivar();
      JSONArray marcados = new JSONArray();
      JSONArray errores = new JSONArray();
      for (int k = 0; k < 2; k++) {
         JSONArray l = k == 0 ? lista : otros;
         for (int i = 0; l != null && i < l.length(); i++) {
            String ds = nombreDs(l.optString(i, ""));
            if (protegidas.containsKey(ds)) continue;
            try {
               Protegida p = proteger(ds);
               p.previo = p.real.setSavepoint("gxp_previo");
               p.confirmado = null;
               p.commits = p.rollbacks = 0;
               p.activa = true;
               protegidas.put(ds, p);
               marcados.put(ds);
            } catch (Exception e) {
               if (k == 0) {
                  desactivar();
                  throw e;
               }
               errores.put(ds + ": " + mensaje(e));
            }
         }
      }
      JSONObject r = new JSONObject();
      r.put("ok", true);
      r.put("ds", marcados);
      r.put("errores", errores);
      return r;
   }

   /**
    * Al terminar un caso. volver: al savepoint del script previo en los datasources marcados y rollback en los
    * demas. Si no (casos encadenados): lo hecho queda y pasa a ser lo confirmado, como un commit simulado.
    * Devuelve los commits y rollbacks que simularon los objetos durante el caso.
    */
   static JSONObject terminarCaso(boolean volver) {
      JSONArray perdidos = new JSONArray();
      JSONArray errores = new JSONArray();
      int restaurados = 0, commits = 0, rollbacks = 0;
      Set<String> lista = new LinkedHashSet<>(todosLosDs());
      lista.addAll(protegidas.keySet());
      for (String ds : lista) {
         Protegida p = protegidas.get(ds);
         if (p == null) {
            if (volver) finDs(ds, false, errores);
            continue;
         }
         try {
            if (proteger(ds) != p) throw new IllegalStateException("cambio la conexion");
            if (volver) {
               p.real.rollback(p.previo);
               p.confirmado = null;
            } else {
               p.confirmado = p.real.setSavepoint("gxp_commit");
            }
            commits = Math.max(commits, p.commits);  // un commit de GeneXus llega a todos los datasources
            rollbacks = Math.max(rollbacks, p.rollbacks);
            p.commits = p.rollbacks = 0;
            restaurados++;
         } catch (Throwable e) {
            perdidos.put(ds + ": " + mensaje(e));
            p.activa = false;
            protegidas.remove(ds);
         }
      }
      JSONObject r = new JSONObject();
      r.put("ok", perdidos.isEmpty() && errores.isEmpty());
      r.put("puntos", restaurados);
      r.put("commits", commits);
      r.put("rollbacks", rollbacks);
      r.put("perdidos", perdidos);
      r.put("errores", errores);
      return r;
   }

   // ------------------------------------------------------------------ utilidades

   static void enviar(JSONObject r) {
      synchronized (proto) {
         proto.print(MARCA);
         proto.println(r.toString());
         proto.flush();
      }
   }

   static String tomarConsola() {
      synchronized (consola) {
         String s = consola.toString(StandardCharsets.UTF_8);
         consola.reset();
         return s;
      }
   }

   static String mensaje(Throwable e) {
      if (e == null) return "";
      String m = e.getMessage();
      return e.getClass().getSimpleName() + (m == null ? "" : ": " + m);
   }

   static String traza(Throwable e) {
      StringWriter sw = new StringWriter();
      e.printStackTrace(new PrintWriter(sw));
      return sw.toString();
   }
}
