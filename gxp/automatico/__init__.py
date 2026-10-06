"""Pruebas automaticas despues de cada build de GeneXus.

Se suscribe a la vigilancia de builds (gxp/vigilancia.py) para las KBs de config.json -> "despuesDelBuild".
Cuando GeneXus recompila una y pasan 'esperaSeg' segundos sin mas cambios:
  1. Con 'revisar' (activo por defecto), revisa las buenas practicas de los objetos que el build volvio a
     especificar (gxp/revisor, modo 'cambiados') y avisa los hallazgos NUEVOS respecto de la linea base.
  2. Corre las suites de esa KB (o solo los casos con 'etiqueta') y deja las corridas en el Historial
     marcadas como "build".
  3. Avisa en la consola, en la interfaz y con una notificacion de Windows.
Al empezar a vigilar arma en segundo plano la linea base de revision de las KBs que no la tienen.

Vigila un solo proceso a la vez (la interfaz o 'gxpruebas.py vigilar'): si ya hay uno, el otro lo
informa y no vigila. Las corridas usan la transaccion de cada suite (rollback por defecto): un objeto
con Commit on exit graba igual, en cada build.

  build.py    revisar y correr las suites de una KB
  resumen.py  textos del resultado (consola, interfaz, notificacion)
"""
import threading
import time

from .build import agregar_revision, correr_kb, hay_nuevos, revisar_kb
from .resumen import lineas_consola, notificacion, texto_resumen, texto_revision
from .. import kbs, vigilancia
from ..config import CACHE
from ..notificaciones import notificar
from ..revisor import revisor

MAX_ULTIMAS = 20

_lock = threading.Lock()
_estado = {"activo": False, "motivo": None, "etiqueta": "", "kbs": {}, "ultimas": [], "seq": 0, "error": None}
_bloqueo = None  # archivo abierto mientras este proceso vigila
_suscripcion = None


def estado():
    """Copia del estado, para la interfaz: KBs vigiladas (esperando / build / revisando / corriendo) y
    ultimos resultados."""
    with _lock:
        error = _estado["error"] or (_suscripcion.error if _suscripcion else None)
        return {**_estado, "error": error, "kbs": {k: dict(v) for k, v in _estado["kbs"].items()},
                "ultimas": list(_estado["ultimas"])}


def _poner_kb(nombre, est):
    with _lock:
        _estado["kbs"][nombre] = {"estado": est, "desde": time.time()}


def _poner_error(texto):
    with _lock:
        _estado["error"] = texto


def _tomar_bloqueo():
    """True si este proceso puede vigilar (nadie mas lo esta haciendo). El bloqueo dura lo que el proceso."""
    global _bloqueo
    CACHE.mkdir(parents=True, exist_ok=True)
    f = open(CACHE / "automatico.lock", "a+")
    try:
        f.seek(0)
        try:
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _bloqueo = f
    return True


def _kbs_vigiladas(conf):
    nombres = conf.get("kbs") or []
    if isinstance(nombres, str):
        nombres = [nombres]
    if "*" in nombres:
        return list(kbs.descubrir().values()), []
    salida, faltan = [], []
    for n in nombres:
        try:
            salida.append(kbs.obtener(n))
        except KeyError:
            faltan.append(n)
    return salida, faltan


def _registrar(res):
    with _lock:
        _estado["seq"] += 1
        res["seq"] = _estado["seq"]
        _estado["ultimas"] = ([res] + _estado["ultimas"])[:MAX_ULTIMAS]


def procesar_build(kb, conf):
    """Revisa y corre las suites de la KB. Devuelve el resultado (con su revision)."""
    rev = None
    try:
        if conf.get("revisar", True):
            _poner_kb(kb.nombre, "revisando")
            rev = revisar_kb(kb)
        _poner_kb(kb.nombre, "corriendo")
        res = correr_kb(kb, (conf.get("etiqueta") or "").strip())
    finally:
        _poner_kb(kb.nombre, "esperando")
    if rev is not None:
        agregar_revision(res, rev)
    return res


def _al_terminar_build(conf, al_terminar, url_base):
    todas = "*" in (conf.get("kbs") or [])

    def atender(kb):
        res = procesar_build(kb, conf)
        if todas and not res["corridas"] and not res["errores"] and not hay_nuevos(res.get("revision")):
            return  # con "*" no se avisa por las KBs sin pruebas ni problemas nuevos
        _registrar(res)
        if al_terminar:
            al_terminar(res)
        if conf.get("notificar", True):
            err = notificar(*notificacion(res, url_base))
            if err:
                _poner_error(f"No se pudo mostrar la notificacion: {err}")
    return atender


def _lineas_base(lista):
    """Arma la linea base de revision de las KBs que no la tienen, para que el primer build ya distinga lo
    nuevo. Si un build llega antes, su revision espera (mismo lock) o arma la de esa KB."""
    for kb in lista:
        try:
            revisor.asegurar_linea_base(kb)
        except Exception as e:
            _poner_error(f"No se pudo armar la linea base de revision de {kb.nombre}: {e}")


def iniciar(conf, al_terminar=None, url_base=None):
    """Empieza a atender los builds de las KBs de 'conf'. Devuelve (vigilando, mensaje para la consola)."""
    lista, faltan = _kbs_vigiladas(conf)
    aviso = f" (no encuentro: {', '.join(faltan)})" if faltan else ""
    if not lista:
        msg = "Pruebas despues del build: no hay KBs para vigilar" + aviso + ". Revisa 'kbs' en config.json."
        with _lock:
            _estado["motivo"] = msg
        return False, msg
    if not _tomar_bloqueo():
        msg = "Pruebas despues del build: ya las esta vigilando otra ventana de GxPruebas; esta no las corre."
        with _lock:
            _estado["motivo"] = msg
        return False, msg
    etiqueta = (conf.get("etiqueta") or "").strip()
    with _lock:
        _estado.update(activo=True, motivo=None, etiqueta=etiqueta)
    for kb in lista:
        _poner_kb(kb.nombre, "esperando")
    global _suscripcion
    nombres_vigilados = {k.nombre for k in lista}
    _suscripcion = vigilancia.suscribir("automatico", _al_terminar_build(conf, al_terminar, url_base),
                         al_detectar=lambda kb: _poner_kb(kb.nombre, "build"),
                         filtro=lambda kb: kb.nombre in nombres_vigilados,
                         espera=float(conf.get("esperaSeg") or 15))
    if "*" in (conf.get("kbs") or []):
        nombres = "todas las KBs" if conf.get("revisar", True) else "todas las KBs con suites"
    else:
        nombres = ", ".join(k.nombre for k in lista)
    que = f"los casos con la etiqueta '{etiqueta}'" if etiqueta else "todas sus suites"
    revisa = ""
    if conf.get("revisar", True):
        revisa = " Antes revisa las buenas practicas de los objetos del build."
        threading.Thread(target=_lineas_base, args=(lista,), daemon=True, name="gxp-revisor-base").start()
    return True, (f"Pruebas despues del build: activas para {nombres}{aviso}; corre {que} "
                  f"{int(float(conf.get('esperaSeg') or 15))} s despues de que termina cada build.{revisa}")


__all__ = ["estado", "iniciar", "procesar_build", "correr_kb", "revisar_kb", "agregar_revision", "hay_nuevos",
           "lineas_consola", "notificacion", "texto_resumen", "texto_revision"]
