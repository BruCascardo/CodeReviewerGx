"""Pantalla GeneXus: Update y Build de las KBs con MSBuild (gxp/genexus.py)."""
from ..rutas import ErrorApi, ruta
from ... import genexus


@ruta("GET", "/api/gx/estado")
def estado(_q, _b):
    try:
        genexus.instalacion()
        error = None
    except RuntimeError as e:
        error = str(e)
    return {"error": error, "kbs": genexus.estado_kbs(), "trabajos": genexus.trabajos()}


@ruta("POST", "/api/gx/ejecutar")
def ejecutar(_q, b):
    nombres = b.get("kbs") or []
    if not nombres:
        raise ErrorApi("Elegí al menos una KB")
    try:
        return genexus.lanzar(nombres, b.get("accion"), bool(b.get("forzar")))
    except (RuntimeError, ValueError) as e:
        raise ErrorApi(str(e))


@ruta("POST", "/api/gx/cancelar")
def cancelar(_q, b):
    try:
        return genexus.cancelar(b.get("id"))
    except (KeyError, TypeError, ValueError) as e:
        raise ErrorApi(str(e), 404)


@ruta("GET", "/api/gx/log")
def log(q, _b):
    try:
        return genexus.log(q.get("id"), q.get("desde") or 0)
    except (KeyError, TypeError, ValueError) as e:
        raise ErrorApi(str(e), 404)
