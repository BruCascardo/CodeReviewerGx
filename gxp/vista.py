"""Vista previa de Web Panels y Web Components: la pantalla corre en el motor de pantallas de la KB (ver
motor/Pantallas.java), no en Tomcat, y se muestra en un iframe de Explorar.

La interfaz abre /vista/<KB>/<sesion>/servlet/<clase>?<query>. Lo que pide esa pagina queda debajo del mismo
prefijo (es el "context path" que ve GeneXus):
  - static/... y los demas archivos (js, css, imagenes) salen de la KB (JavaModel\\web\\js, JavaModel\\web,
    UCSupportFiles) o de la carpeta publicada en Tomcat (CLIENT_STATIC_DIR del model.ini);
  - servlet/com.x.y o com.x.y, si la clase existe en la KB, va al motor: la carga de la pagina, los eventos
    (AJAX), las grillas y los Web Components.
Nada se confirma en la base: el motor de pantallas simula los commit y reiniciar() deshace todo. Mientras
tanto, lo que grabo deja filas bloqueadas (la master page de WorkWithPlus graba en WWP_WebClient en cada
pantalla): despues de 'vistaDeshacerMin' minutos sin pedidos se deshace solo.
"""
import base64
import re
import threading
import time
from pathlib import Path

from . import motor
from .config import CFG

ROL = "pantallas"
# Cabeceras que no se pasan al motor: las del transporte, y la compresion (la respuesta se manda tal cual).
_SIN_PASAR = {"host", "connection", "content-length", "accept-encoding", "keep-alive", "transfer-encoding", "upgrade"}
_SIN_DEVOLVER = {"content-length", "transfer-encoding", "content-encoding", "connection"}
_CLASE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")

_lock = threading.Lock()
_estado = {}     # kb -> {pedidos, commits, rollbacks, ultimaExcepcion, desde, ultimoUso}
_permisos = {}   # (kb, sesion) -> "todos" | "ninguno"
_carpetas = {}   # kb -> [carpetas de archivos estaticos]
_deshecho = {}   # kb -> cuando se deshizo solo por inactividad
_vigilante = None


def _motor(kb):
    return motor.motor(kb, ROL)


def _nuevo():
    return {"pedidos": 0, "commits": 0, "rollbacks": 0, "ultimaExcepcion": None, "desde": time.time(), "ultimoUso": None}


def estado(kb):
    m = _motor(kb)
    with _lock:
        e = dict(_estado.get(kb.nombre) or {**_nuevo(), "desde": None})
        deshecho = _deshecho.get(kb.nombre)
    return {**e, "deshechoSolo": deshecho, "deshacerMin": CFG["vistaDeshacerMin"], "motor": m.info()}


def _vigilar():
    """Deshace lo de las pantallas que pasaron 'vistaDeshacerMin' minutos sin pedidos (suelta los bloqueos)."""
    while True:
        time.sleep(20)
        limite = float(CFG["vistaDeshacerMin"]) * 60
        with _lock:
            quietas = [k for k, e in _estado.items() if e.get("ultimoUso") and time.time() - e["ultimoUso"] > limite]
        for nombre in quietas:
            m = next((x for x in motor.motores() if x.kb.nombre == nombre and x.rol == ROL), None)
            if m is None or not m.vivo() or m.ocupado or not m.lock.acquire(blocking=False):
                continue
            try:
                reiniciar(m.kb)
                with _lock:
                    _deshecho[nombre] = time.time()
            except Exception:
                pass
            finally:
                m.lock.release()


def _sumar(kb, r, ruta):
    global _vigilante
    with _lock:
        if _vigilante is None:
            _vigilante = threading.Thread(target=_vigilar, daemon=True, name="gxp-vista")
            _vigilante.start()
        e = _estado.setdefault(kb.nombre, _nuevo())
        _deshecho.pop(kb.nombre, None)
        e["ultimoUso"] = time.time()
        e["pedidos"] += 1
        e["commits"] += r.get("commits") or 0
        e["rollbacks"] += r.get("rollbacks") or 0
        if r.get("excepcion"):
            e["ultimaExcepcion"] = {"ruta": ruta, "traza": r["excepcion"][:20000], "cuando": time.time()}


def url(kb, objeto, parametros, sesion, permisos="todos"):
    """La URL con la que se abre la pantalla en la vista previa (los parametros se cifran como en un link())."""
    clase = kb.clase_java(objeto)
    with _lock:
        _permisos[(kb.nombre, sesion)] = permisos if permisos in ("todos", "ninguno") else "todos"
    r = _motor(kb).pedir("pantalla_query", clase=clase, parametros=[str(p) for p in parametros or []])
    if not r.get("ok"):
        raise motor.MotorError(r.get("error") or "No se pudo armar la URL de la pantalla")
    q = r.get("query") or ""
    return f"/vista/{kb.nombre}/{sesion}/servlet/{clase}" + (f"?{q}" if q else "")


def reiniciar(kb):
    """Deshace todo lo que hicieron las pantallas de la KB y olvida sus sesiones."""
    m = _motor(kb)
    with _lock:
        _estado.pop(kb.nombre, None)
    if not m.vivo():
        return {"ok": True, "errores": []}
    r = m.pedir("pantalla_reiniciar", sesiones=True)
    return {"ok": bool(r.get("ok")), "errores": r.get("errores") or []}


def es_pantalla(kb, ruta):
    """True si la ruta (servlet/com.x.y o com.x.y) es una pantalla de la KB (tiene su clase _impl)."""
    clase = ruta[len("servlet/"):] if ruta.startswith("servlet/") else ruta
    if not _CLASE.match(clase):
        return False
    return kb.clases.joinpath(*clase.split(".")).with_name(clase.rsplit(".", 1)[1] + "_impl.class").exists()


def liberar_otras(kb):
    """Deshace lo pendiente de las vistas previas de las otras KBs. Todas comparten tablas de la base de Sistema
    (la master page de WorkWithPlus graba en WWP_WebClient en cada pantalla): si una deja filas bloqueadas, las
    pantallas de otra KB esperan y fallan."""
    with _lock:
        otras = [n for n, e in _estado.items() if n != kb.nombre and e.get("ultimoUso")]
    for nombre in otras:
        m = next((x for x in motor.motores() if x.kb.nombre == nombre and x.rol == ROL), None)
        if m is None or not m.vivo() or not m.lock.acquire(timeout=30):
            continue
        try:
            reiniciar(m.kb)
        except Exception:
            pass
        finally:
            m.lock.release()


def pedido(kb, sesion, metodo, ruta, query, cuerpo: bytes, headers, host):
    """Un pedido de la pagina al motor. Devuelve (estado, cabeceras, cuerpo)."""
    liberar_otras(kb)
    hs = {k: v for k, v in headers.items() if k.lower() not in _SIN_PASAR}
    with _lock:
        permisos = _permisos.get((kb.nombre, sesion), "todos")
    r = _motor(kb).pedir("pantalla", timeout_ms=180000, sesion=sesion, metodo=metodo, ruta=ruta, query=query,
                         cuerpo=base64.b64encode(cuerpo or b"").decode("ascii"), headers=hs,
                         contexto=f"/vista/{kb.nombre}/{sesion}", host=host, permisos=permisos)
    if not r.get("ok"):
        texto = (r.get("error") or "Error del motor de pantallas") + "\n\n" + (r.get("excepcion") or "")
        return 500, {"Content-Type": "text/plain; charset=utf-8"}, texto.encode("utf-8")
    _sumar(kb, r, ruta)
    salida = {k: v for k, v in (r.get("headers") or {}).items() if k.lower() not in _SIN_DEVOLVER}
    datos = base64.b64decode(r.get("cuerpo") or "")
    _grabar(kb, sesion, metodo, ruta, query, cuerpo, hs, int(r.get("estado") or 200), salida, datos)
    return int(r.get("estado") or 200), salida, datos


# ---------------------------------------------------------------------- grabacion de casos

_grabaciones = {}  # (kb, sesion) -> [pedidos] mientras se graba


def grabar(kb, sesion, activo):
    """Empieza (deshaciendo todo antes, para que el caso arranque de la base sin cambios) o termina de grabar lo
    que hace la sesion. Devuelve la cantidad de pedidos grabados."""
    clave = (kb.nombre, sesion)
    if activo:
        reiniciar(kb)
        with _lock:
            _grabaciones[clave] = []
            _ultimas.pop(clave, None)
        return 0
    with _lock:
        lista = _grabaciones.get(clave)
        if lista is not None:
            _grabaciones[clave] = None  # terminada: queda para guardarla
        return len(lista or [])


def grabacion(kb, sesion):
    """(grabando, pedidos grabados) de la sesion."""
    with _lock:
        clave = (kb.nombre, sesion)
        if clave in _grabaciones and _grabaciones[clave] is not None:
            return True, list(_grabaciones[clave])
        return False, list(_ultimas.get(clave) or [])


_ultimas = {}  # (kb, sesion) -> la ultima grabacion terminada


def _grabar(kb, sesion, metodo, ruta, query, cuerpo, headers, estado_http, cabeceras, datos):
    clave = (kb.nombre, sesion)
    with _lock:
        lista = _grabaciones.get(clave)
        if lista is None:
            return
        tipo = cabeceras.get("Content-Type", "")
        texto = datos.decode("utf-8", "replace") if ("json" in tipo or "html" in tipo or "text" in tipo) else ""
        lista.append({"metodo": metodo, "ruta": ruta, "query": query or "", "cuerpo": (cuerpo or b"").decode("utf-8", "replace"),
                      "tipo": headers.get("Content-Type") or headers.get("content-type") or "", "cabeceras": dict(headers),
                      "respuesta": {"estado": estado_http, "tipo": tipo, "cuerpo": texto}})
        _ultimas[clave] = lista


# ---------------------------------------------------------------------- archivos estaticos

def carpetas(kb):
    """Donde se buscan los archivos de la pagina: la KB (lo recien generado) y la carpeta publicada en Tomcat."""
    with _lock:
        if kb.nombre in _carpetas:
            return _carpetas[kb.nombre]
    lista = [kb.web / "js", kb.web, kb.web / "UCSupportFiles"]
    try:
        texto = (kb.carpeta / "model.ini").read_text(encoding="latin-1", errors="replace")
        for m in re.finditer(r"^CLIENT_STATIC_DIR=(.+)$", texto, re.M):
            p = Path(m.group(1).strip())
            if p.is_dir() and p not in lista:
                lista.append(p)
    except OSError:
        pass
    lista = [p for p in lista if p.is_dir()]
    with _lock:
        _carpetas[kb.nombre] = lista
    return lista


def archivo(kb, ruta):
    """El archivo de la KB que corresponde a una ruta de la pagina (static/gxgral.js, Resources/x.css...), o None."""
    rel = ruta[len("static/"):] if ruta.startswith("static/") else ruta
    if not rel or ".." in rel.split("/"):
        return None
    for base in carpetas(kb):
        p = (base / rel).resolve()
        try:
            p.relative_to(base.resolve())
        except ValueError:
            continue
        if p.is_file():
            return p
    return None
