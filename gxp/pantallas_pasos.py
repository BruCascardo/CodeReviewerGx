"""Pasos "pantalla" de las suites: lo que se hizo en la vista previa de una pantalla, repetido en el motor de
pantallas de la KB (ver gxp/vista.py y motor/Pantallas.java).

Un paso es un pedido de la pagina, como lo hizo el navegador mientras se grababa:

  {"nombre": "Abrir gntMonedaWW", "pantalla": "Generales.Comunes.Monedas.gntMonedaWW", "parametros": []}
  {"nombre": "gntMonedaWW: evento REFRESH", "pantalla": "...gntMonedaWW", "evento": "REFRESH",
   "valores": {"vMONNOMBRE1": "DOL", "GRID.Rows": 10, ...}, "pedido": {"objClass": ..., "grids": ...}}
  {"nombre": "gntMonedaView: dyncomponent", "pantalla": "...", "query": "dyncomponent,W0038,,2"}

- "parametros" abre la pantalla como un link(): los valores se cifran al ejecutar.
- Un evento lleva sus parametros con nombre en "valores" (el control, la variable o control.propiedad, como los
  declara el .js de la pantalla en EvtParms). Si no se pudieron nombrar, van en "pedido" tal cual ("parms").
  El resto del pedido (grillas, fila, formulario de una transaccion en fullPost) va en "pedido".
- En el motor de pantallas las firmas de GeneXus son constantes (motor/pantallas/WebSecurityHelper.java): por
  eso un pedido grabado se puede repetir igual dias despues.

La salida de un paso (lo que se compara con la aprobada) es un resumen: la grilla con sus filas, los valores de
las variables, los mensajes, los comandos (redirecciones) y las propiedades que cambian (Visible, Enabled,
Caption). Las URLs no llevan el prefijo de la sesion.
"""
import base64
import html as html_mod
import json
import re
import threading
import time
import urllib.parse

from . import catalogo, motor

ROL = "pantallas"
SESION = "prueba"           # sesion de los pasos de las suites: siempre la misma (las URLs de la salida no cambian)
MARCA = "@@VISTA@@"         # en un pedido grabado, el prefijo /vista/<KB>/<sesion> de la grabacion
PROPIEDADES = ("Visible", "Enabled", "Caption")
_OMITIR_VALORES = {"CmpContext", "IsMasterPage"}

_lock = threading.Lock()
_evtparms = {}  # ruta del .js -> (mtime, {evento: [entrada, salida]})


def contexto(kb, sesion=SESION):
    return f"/vista/{kb.nombre}/{sesion}"


def _prefijo(kb, sesion):
    """El prefijo de la sesion en las URLs, con o sin el servidor adelante (http://localhost:8765/vista/KB/s1)."""
    return re.compile(r"(?:https?://[^/\s\"'<>]+)?" + re.escape(contexto(kb, sesion)))


# Cabeceras del pedido que dicen como responder (AJAX o pagina completa): se graban con el paso.
def _cabeceras(hs):
    return {k: v for k, v in (hs or {}).items()
            if k.lower().startswith(("gx", "x-")) and k.lower() not in ("x-gxauth-token", "x-forwarded-for", "x-forwarded-proto")}


# ---------------------------------------------------------------------- literales de JavaScript

class _Js:
    """Lector de los literales de JavaScript que genera GeneXus ({av:'X',fld:'Y',hsh:true}): claves sin comillas,
    textos entre comillas simples o dobles, numeros, true/false/null."""

    def __init__(self, t):
        self.t, self.i = t, 0

    def _esp(self):
        while self.i < len(self.t) and self.t[self.i] in " \t\r\n":
            self.i += 1

    def valor(self):
        self._esp()
        c = self.t[self.i]
        if c == "{":
            return self._objeto()
        if c == "[":
            return self._lista()
        if c in "'\"":
            return self._texto()
        m = re.compile(r"-?\d+(\.\d+)?|true|false|null|[A-Za-z_$][\w$]*").match(self.t, self.i)
        if not m:
            raise ValueError(f"literal invalido en {self.i}: {self.t[self.i:self.i + 20]!r}")
        self.i = m.end()
        w = m.group(0)
        return {"true": True, "false": False, "null": None}.get(w, float(w) if m.group(1) else (int(w) if w[0] in "-0123456789" else w))

    def _texto(self):
        q = self.t[self.i]
        self.i += 1
        salida = []
        while self.t[self.i] != q:
            if self.t[self.i] == "\\":
                self.i += 1
                salida.append({"n": "\n", "t": "\t"}.get(self.t[self.i], self.t[self.i]))
            else:
                salida.append(self.t[self.i])
            self.i += 1
        self.i += 1
        return "".join(salida)

    def _objeto(self):
        self.i += 1
        d = {}
        while True:
            self._esp()
            if self.t[self.i] == "}":
                self.i += 1
                return d
            if self.t[self.i] in "'\"":
                k = self._texto()
            else:
                m = re.compile(r"[A-Za-z_$][\w$]*").match(self.t, self.i)
                k, self.i = m.group(0), m.end()
            self._esp()
            self.i += 1  # :
            d[k] = self.valor()
            self._esp()
            if self.t[self.i] == ",":
                self.i += 1

    def _lista(self):
        self.i += 1
        lst = []
        while True:
            self._esp()
            if self.t[self.i] == "]":
                self.i += 1
                return lst
            lst.append(self.valor())
            self._esp()
            if self.t[self.i] == ",":
                self.i += 1


def js(texto):
    return _Js(texto).valor()


_EVT = re.compile(r'this\.EvtParms\[("(?:[^"\\]|\\.)*")\]\s*=\s*(\[\[.*?\]\]);\s*$', re.M)


def evt_parms(kb, obj_class):
    """{evento: [parametros de entrada, de salida]} del .js de la pantalla (JavaModel\\web\\js\\<modulo>\\<obj>.js),
    como lo usa el cliente de GeneXus para armar el pedido de un evento. {} si no esta."""
    ruta = kb.web / "js" / (obj_class.replace(".", "/") + ".js")
    try:
        mt = ruta.stat().st_mtime
    except OSError:
        return {}
    with _lock:
        previo = _evtparms.get(str(ruta))
        if previo and previo[0] == mt:
            return previo[1]
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    salida = {}
    for m in _EVT.finditer(texto):
        try:
            salida[json.loads(m.group(1))] = js(m.group(2))
        except (ValueError, IndexError):
            continue
    with _lock:
        _evtparms[str(ruta)] = (mt, salida)
    return salida


def _clave(p):
    """La clave con que el cliente de GeneXus no repite un parametro (gx.ajax.resolveParmKey)."""
    if p.get("av"):
        return p["av"]
    if p.get("ctrl"):
        return p["ctrl"] + p["prop"] if p.get("prop") else p["ctrl"]
    return None


def parametros_evento(kb, obj_class, eventos):
    """Los parametros de entrada de los eventos, en el orden en que los manda el cliente (getParmsMetadata):
    sin repetir y sin el {postForm:true}, que no ocupa lugar (manda el formulario en fullPost)."""
    ep = evt_parms(kb, obj_class)
    u, idx = [], {}
    for ev in eventos or []:
        for p in (ep.get(ev) or [[]])[0]:
            if any(p.get(k) for k in ("postForm", "sPrefix", "sSFPrefix", "sCompEvt")):
                u.append(p)
                continue
            k = _clave(p)
            if not k:
                continue
            if k not in idx:
                idx[k] = len(u)
                u.append(p)
            elif "grid" not in u[idx[k]] and "grid" in p:
                u[idx[k]] = p
    return [p for p in u if not p.get("postForm")]


def nombres(parms_meta):
    """El nombre de cada parametro en 'valores': el control (fld), la variable (av), control.propiedad o, para
    un combo, control.combo. Sin repetir."""
    salida, usados = [], set()
    for p in parms_meta:
        if p.get("fld"):
            n = p["fld"]
        elif p.get("av"):
            n = p["av"]
        elif p.get("ctrl") and p.get("prop"):
            n = f"{p['ctrl']}.{p['prop']}"
        elif p.get("ctrl"):
            n = f"{p['ctrl']}.combo"
        else:
            n = "sPrefix" if p.get("sPrefix") else ("sSFPrefix" if p.get("sSFPrefix") else "parametro")
        base, k = n, 2
        while n in usados:
            n, k = f"{base}#{k}", k + 1
        usados.add(n)
        salida.append(n)
    return salida


# ---------------------------------------------------------------------- recargas de grilla (gxajaxGridRefresh_Grid)

_ACCION = re.compile(r'GXutil\.strcmp\(gxfirstwebparm, "(gxajax\w+_)"\+"(\w+)"\) == 0 \)\s*\{\s*(\w+)\( \)')
_PAR = re.compile(r'GetPar\( "(\w+)"\)|(\w+)\.fromJSonString\( httpContext\.GetNextPar\( \)\)'
                  r'|readJsonSdtValue\(httpContext\.GetNextPar\( \), (\w+)\)|GetNextPar\( \)')
_SEGURO = "-_.!~*'()"  # lo que encodeURIComponent no codifica
_cache_grilla = {}


def nombres_accion(kb, clase, accion):
    """Los nombres de los valores de un pedido como gxajaxGridRefresh_Grid,10,...: en el orden en que los lee el
    objeto (su metodo gx..._invoke en el Java), o None si no se encuentra."""
    base = kb.fuentes.joinpath(*clase.split(".")).with_suffix(".java")
    ruta = base.with_name(base.stem + "_impl.java")
    try:
        mt = ruta.stat().st_mtime
    except OSError:
        return None
    clave = (str(ruta), accion)
    if clave in _cache_grilla and _cache_grilla[clave][0] == mt:
        return _cache_grilla[clave][1]
    texto = ruta.read_text(encoding="utf-8", errors="ignore")
    metodo = next((m.group(3) for m in _ACCION.finditer(texto) if m.group(1) + m.group(2) == accion), None)
    nombres_ = None
    if metodo:
        ini = re.search(r"\n   public void " + re.escape(metodo) + r"\( \)\s*\n   \{", texto)
        if ini:
            fin = texto.find("\n   }", ini.end())
            nombres_ = []
            for m in _PAR.finditer(texto[ini.end():fin]):
                if m.group(1):
                    nombres_.append(m.group(1))
                elif m.group(2):
                    nombres_.append(m.group(2) + ".combo")
                elif m.group(3):
                    nombres_.append(re.sub(r"^AV\d+", "", m.group(3)))
                else:
                    nombres_.append("parametro")
    _cache_grilla[clave] = (mt, nombres_)
    return nombres_


def _valor_query(v):
    v = urllib.parse.unquote(v)
    if v[:1] in "{[":
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def _query_valor(v):
    if not isinstance(v, str):
        v = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    return urllib.parse.quote(v, safe=_SEGURO)


def _accion_de(query):
    """('gxajaxGridRefresh_Grid', [valores]) de una query de recarga de grilla, sin el gx-no-cache; o None."""
    partes = query.split(",")
    if not partes or not re.match(r"^gxajax\w+_\w+$", partes[0]):
        return None
    valores = [p for p in partes[1:] if not p.startswith("gx-no-cache=")]
    return partes[0], valores


# ---------------------------------------------------------------------- de lo grabado a pasos

def _cambios_formulario(full_post):
    """Lo que cambio el usuario en el formulario de una transaccion: cada control contra su valor original, que
    GeneXus manda como Z<numero><Atributo> (Z175MonSimbolo -> MONSIMBOLO)."""
    if not isinstance(full_post, dict):
        return {}
    cambios = {}
    for k, viejo in full_post.items():
        m = re.match(r"^Z\d+(\w+)$", k)
        if not m:
            continue
        ctrl = m.group(1).upper()
        if ctrl in full_post and str(full_post[ctrl]).strip() != str(viejo).strip():
            cambios[ctrl] = (viejo, full_post[ctrl])
    return cambios

def _reemplazar(valor, viejo, nuevo):
    """Reemplaza en todos los textos de un valor. 'viejo' puede ser una expresion regular compilada."""
    if isinstance(valor, str):
        return viejo.sub(nuevo, valor) if isinstance(viejo, re.Pattern) else valor.replace(viejo, nuevo)
    if isinstance(valor, list):
        return [_reemplazar(v, viejo, nuevo) for v in valor]
    if isinstance(valor, dict):
        return {k: _reemplazar(v, viejo, nuevo) for k, v in valor.items()}
    return valor


def _nombres_gx(kb):
    return {kb.clase_java(o["nombre"]): o["nombre"] for o in catalogo.objetos(kb)}


def _clase(ruta):
    return ruta[len("servlet/"):] if ruta.startswith("servlet/") else ruta


def a_pasos(kb, entradas, sesion):
    """Los pasos de un caso a partir de lo que se grabo en la vista previa (gxp/vista.py). Cada paso lleva como
    salida aprobada lo que se vio al grabar."""
    nombres_gx = _nombres_gx(kb)
    m = motor.motor(kb, ROL)
    prefijo = _prefijo(kb, sesion)
    pasos = []
    for e in entradas:
        clase = _clase(e["ruta"])
        nombre = nombres_gx.get(clase, clase)
        corto = nombre.rsplit(".", 1)[-1]
        paso = {"pantalla": nombre}
        if e["metodo"] == "GET":
            r = m.pedir("pantalla_parametros", clase=clase, query=e["query"])
            accion = _accion_de(e["query"])
            nombres_acc = nombres_accion(kb, clase, accion[0]) if accion else None
            if r.get("parametros") is not None:
                lista = r["parametros"]
                paso = {"nombre": f"Abrir {corto}", **paso, "parametros": lista}
            elif accion and nombres_acc is not None and len(nombres_acc) == len(accion[1]):
                que = "recargar la grilla" if "GridRefresh" in accion[0] else accion[0]
                paso = {"nombre": f"{corto}: {que} {accion[0].rsplit('_', 1)[-1]}", **paso, "accion": accion[0],
                        "valores": {n: _valor_query(v) for n, v in zip(nombres_acc, accion[1])}}
            else:
                paso = {"nombre": f"{corto}: {e['query'].split(',')[0][:40] or 'GET'}", **paso, "query": e["query"]}
        else:
            try:
                cuerpo = json.loads(e["cuerpo"] or "{}")
            except ValueError:
                cuerpo = None
            if isinstance(cuerpo, dict) and "events" in cuerpo:
                eventos = cuerpo.get("events") or []
                obj_class = cuerpo.get("objClass") or clase.split(".", 2)[-1]
                meta = parametros_evento(kb, obj_class, eventos)
                parms = cuerpo.get("parms") or []
                pedido = {k: v for k, v in cuerpo.items() if k not in ("events", "parms")}
                cambios = _cambios_formulario(cuerpo.get("fullPost"))
                que = "; ".join(f"{c}: {str(v[0]).strip()} → {str(v[1]).strip()}" for c, v in list(cambios.items())[:3])
                paso = {"nombre": f"{corto}: evento {', '.join(eventos) or '?'}" + (f" ({que})" if que else ""), **paso,
                        "evento": ", ".join(eventos)}
                if meta and len(meta) == len(parms):
                    paso["valores"] = dict(zip(nombres(meta), parms))
                else:
                    pedido["parms"] = parms
                if e["query"] not in ("", "gxajaxEvt"):
                    paso["query"] = e["query"]
                paso["pedido"] = pedido
            else:
                paso = {"nombre": f"{corto}: POST", **paso, "metodo": "POST", "query": e["query"],
                        "formulario": e["cuerpo"], "tipoContenido": e.get("tipo") or ""}
        cab = _cabeceras(e.get("cabeceras"))
        if cab and "pedido" not in paso:
            paso["cabeceras"] = cab
        paso = _reemplazar(paso, prefijo, MARCA)
        if e.get("respuesta"):
            paso["lineaBase"] = salida(kb, sesion, e["respuesta"])
        pasos.append(paso)
    return pasos


def nombre_caso(pasos):
    abiertas = [p["pantalla"].rsplit(".", 1)[-1] for p in pasos if "parametros" in p]
    eventos = [p["evento"] for p in pasos if p.get("evento")]
    base = " → ".join(dict.fromkeys(abiertas)) or "Pantalla"
    return base + (f" ({len(eventos)} evento{'s' if len(eventos) != 1 else ''})" if eventos else "")


# ---------------------------------------------------------------------- salida de un paso

def _gxstate(texto):
    m = re.search(r"""name=["']GXState["'][^>]*value='(.*?)'\s*/?>""", texto, re.S)
    if not m:
        return {}
    try:
        return json.loads(html_mod.unescape(m.group(1)))
    except ValueError:
        return {}


def _filas(valor):
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except ValueError:
            return valor
    return valor


def _sin_fila(ctrl):
    return re.sub(r"_\d{4}$", "", ctrl)


def _grillas_json(grids):
    """gxGrids -> {grilla: [{columna: valor}]}."""
    salida = {}
    for g in grids or []:
        if not isinstance(g, dict):
            continue
        nombre = (g.get("CmpContext") or "") + (g.get("GridName") or "Grilla")
        filas = []
        for k in sorted((k for k in g if k.isdigit()), key=int):
            props = (g[k] or {}).get("Props") or []
            filas.append({_sin_fila(str(p[0])): p[1] for p in props if isinstance(p, list) and len(p) > 1})
        salida[nombre] = filas
    return salida


def salida(kb, sesion, respuesta):
    """El resumen que se compara de una respuesta {estado, tipo, cuerpo (texto)}."""
    estado, tipo, texto = respuesta["estado"], respuesta.get("tipo") or "", respuesta.get("cuerpo") or ""
    d = {"estado": estado}
    if "json" in tipo or texto.lstrip().startswith("{"):
        try:
            j = json.loads(texto)
        except ValueError:
            d["texto"] = texto[:2000]
            return d
        valores = {}
        for bloque in j.get("gxValues") or []:
            cmp = bloque.get("CmpContext") or ""
            for k, v in bloque.items():
                if k not in _OMITIR_VALORES:
                    valores[cmp + k] = v
        ocultos, grillas = {}, _grillas_json(j.get("gxGrids"))
        for k, v in (j.get("gxHiddens") or {}).items():
            if k.endswith("ContainerDataV"):
                grillas.setdefault(k[:-len("ContainerDataV")] + " (datos)", _filas(v))
            elif not k.startswith(("gxhash_", "GX_AUTH_")) and "gxhash_" not in k and k != "GX_CMP_OBJS":
                ocultos[k] = v
        props = {}
        for bloque in j.get("gxProps") or []:
            cmp = bloque.get("CmpContext") or ""
            for ctrl, ps in bloque.items():
                if isinstance(ps, dict):
                    sel = {p: v for p, v in ps.items() if p in PROPIEDADES}
                    if sel:
                        props[cmp + ctrl] = sel
        mensajes = [m for lst in (j.get("gxMessages") or {}).values() for m in (lst if isinstance(lst, list) else [lst])]
        d.update({k: v for k, v in (("valores", valores), ("ocultos", ocultos), ("grillas", grillas),
                                    ("mensajes", mensajes), ("comandos", j.get("gxCommands")),
                                    ("propiedades", props)) if v})
    elif "html" in tipo or texto.lstrip().startswith("<"):
        st = _gxstate(texto)
        t = re.search(r"<title>(.*?)</title>", texto, re.S)
        d["titulo"] = html_mod.unescape(t.group(1)).strip() if t else ""
        # Las filas de cada grilla van en un campo oculto propio (<input name="GridContainerDataV" value='[...]'>).
        grillas = {m.group(1): _filas(html_mod.unescape(m.group(2)))
                   for m in re.finditer(r"""name=["'](\w*?)ContainerDataV["']\s+value='(.*?)'\s*/?>""", texto, re.S)}
        grillas.update({k[:-len("ContainerDataV")]: _filas(v) for k, v in st.items() if k.endswith("ContainerDataV")})
        valores = {k: v for k, v in st.items() if re.match(r"^(W\d{4})?v[A-Z0-9_]+$", k) and not k.endswith("_MPAGE")}
        d.update({k: v for k, v in (("grillas", grillas), ("valores", valores)) if v})
    else:
        d.update({"tipo": tipo, "bytes": len(texto)})
    return _reemplazar(d, re.compile(_prefijo(kb, sesion).pattern + "/"), "")


# ---------------------------------------------------------------------- ejecutar un paso

def ejecutar_paso(kb, paso, timeout_ms=None):
    """Repite el pedido del paso en el motor de pantallas. Devuelve (respuesta, datos) como ejecutar_objeto:
    respuesta con ok, error, excepcion y ms; datos, el resumen que se compara."""
    m = motor.motor(kb, ROL)
    ctx = contexto(kb)
    paso = _reemplazar(paso, MARCA, ctx)
    try:
        clase = kb.clase_java(catalogo.buscar(kb, paso["pantalla"])["nombre"])
    except KeyError:
        clase = paso["pantalla"]
    metodo, query, cuerpo, headers = "GET", paso.get("query") or "", b"", {}
    if "parametros" in paso:
        r = m.pedir("pantalla_query", clase=clase, parametros=[str(v) for v in paso.get("parametros") or []])
        if not r.get("ok"):
            return r, None
        query = r.get("query") or ""
    elif paso.get("accion"):
        valores = paso.get("valores") or {}
        orden = nombres_accion(kb, clase, paso["accion"]) or list(valores)
        query = ",".join([paso["accion"], *(_query_valor(valores.get(n, "")) for n in orden)])
    elif paso.get("evento") or paso.get("pedido") is not None:
        pedido = dict(paso.get("pedido") or {})
        eventos = [e.strip() for e in (paso.get("evento") or "").split(",") if e.strip()] or pedido.get("events") or []
        pedido["events"] = eventos
        if paso.get("valores") is not None:
            meta = parametros_evento(kb, pedido.get("objClass") or clase.split(".", 2)[-1], eventos)
            pedido["parms"] = [paso["valores"].get(n) for n in nombres(meta)]
        metodo, query = "POST", query or "gxajaxEvt"
        cuerpo = json.dumps(pedido, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "GxAjaxRequest": "1", "X-FULL-AJAX-REQUEST": "1",
                   "X-GXAUTH-TOKEN": "gxpruebas"}
    elif paso.get("metodo", "GET").upper() == "POST":
        metodo = "POST"
        cuerpo = (paso.get("formulario") or "").encode("utf-8")
        headers = {"Content-Type": paso.get("tipoContenido") or "application/x-www-form-urlencoded"}
    headers = {**(paso.get("cabeceras") or {}), **headers}
    t0 = time.time()
    r = m.pedir("pantalla", timeout_ms=timeout_ms or 180000, sesion=SESION, metodo=metodo, ruta=f"servlet/{clase}",
                query=query, cuerpo=base64.b64encode(cuerpo).decode("ascii"), headers=headers, contexto=ctx,
                host="localhost:80", permisos=paso.get("permisos") or "todos")
    if not r.get("ok"):
        return r, None
    texto = base64.b64decode(r.get("cuerpo") or "").decode("utf-8", "replace")
    tipo = (r.get("headers") or {}).get("Content-Type", "")
    datos = salida(kb, SESION, {"estado": r.get("estado"), "tipo": tipo, "cuerpo": texto})
    res = {"ok": True, "ms": r.get("ms") or (time.time() - t0) * 1000, "commits": r.get("commits", 0)}
    if r.get("excepcion"):
        res.update({"ok": False, "error": "La pantalla dio una excepcion", "excepcion": r["excepcion"]})
    elif (r.get("estado") or 200) >= 400:
        res.update({"ok": False, "error": f"La pantalla respondio {r.get('estado')}: {texto[:300]}"})
    return res, datos


# ---------------------------------------------------------------------- un caso con pantallas

def es_de_pantallas(caso):
    return any(p.get("pantalla") for p in caso.get("pasos") or [])


class CasoDePantallas:
    """Mientras corre un caso con pasos de pantalla: el motor de pantallas en exclusiva, empezando y terminando
    sin nada de lo anterior (rollback de todo y sesiones nuevas)."""

    def __init__(self, kb):
        self.kb = kb
        self.m = motor.motor(kb, ROL)

    def __enter__(self):
        from . import vista
        vista.liberar_otras(self.kb)  # una vista previa de otra KB puede tener bloqueadas tablas de Sistema
        self.m.lock.acquire()
        try:
            self.m.pedir("pantalla_reiniciar", sesiones=True)
        except BaseException:
            self.m.lock.release()
            raise
        return self

    def __exit__(self, *_):
        try:
            if self.m.vivo():
                self.m.pedir("pantalla_reiniciar", sesiones=True)
        finally:
            self.m.lock.release()
