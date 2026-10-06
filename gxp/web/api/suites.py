"""Pantallas Suites e Historial: suites, casos, corridas en segundo plano, resultados y salidas aprobadas."""
from ..rutas import Archivo, ErrorApi, mensaje, ruta
from ... import suites
from ...suites import almacen, resultados, trabajos


@ruta("GET", "/api/suites")
def listar(q, _b):
    return almacen.listar(q.get("kb") or None)


@ruta("GET", "/api/suite")
def suite(q, _b):
    try:
        s = almacen.cargar(q.get("id", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    s["_estado"] = resultados.estado_suite(s["_id"])
    return s


@ruta("PUT", "/api/suite")
def guardar(_q, b):
    s = b.get("suite") or {}
    if b.get("id"):
        return {"id": almacen.guardar(b["id"], s)}
    try:
        return {"id": almacen.guardar_nueva(s, pisar=bool(b.get("pisar")))}
    except ValueError as e:
        raise ErrorApi(str(e))


@ruta("DELETE", "/api/suite")
def borrar(q, _b):
    almacen.borrar(q.get("id", ""))
    return {"ok": True}


@ruta("POST", "/api/suite/caso")
def agregar_caso(_q, b):
    if not b.get("id"):
        raise ErrorApi("Falta la suite")
    caso = b.get("caso") or {}
    sid, caso_id = almacen.agregar_caso(b["id"], caso, bool(b.get("reemplazar")), b.get("nombreSuite"), b.get("kb", ""))
    r = {"id": sid, "casoId": caso_id}
    # Con salida aprobada: se ejecuta una vez mas para marcar los valores que cambian solos (fechas, ids).
    if b.get("detectarVolatiles", True) and any(p.get("lineaBase") is not None for p in caso.get("pasos") or []):
        r.update(suites.volatiles_de_caso(sid, caso_id))
    return r


@ruta("POST", "/api/lineabase")
def aceptar_linea_base(_q, b):
    suites.aceptar_linea_base(b["suite"], b["caso"], int(b["paso"]), b.get("fila"), b.get("datos"))
    return {"ok": True}


@ruta("POST", "/api/corridas")
def iniciar_corrida(_q, b):
    try:
        return {"trabajo": trabajos.iniciar(b.get("suite"), b.get("casos"), b.get("etiqueta"), b.get("filtro"), b.get("grabar"))}
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("GET", "/api/trabajo")
def trabajo(q, _b):
    try:
        return trabajos.estado(q.get("id", ""), int(q.get("desde") or 0))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("POST", "/api/trabajo/cancelar")
def cancelar(q, _b):
    trabajos.cancelar(q.get("id", ""))
    return {"ok": True}


@ruta("GET", "/api/corridas")
def corridas(q, _b):
    return resultados.listar_corridas(int(q.get("limite") or 200))


def _corrida(cid):
    try:
        return resultados.cargar_corrida(cid)
    except OSError:
        raise ErrorApi("No existe la corrida", 404)


@ruta("GET", "/api/corrida")
def corrida(q, _b):
    return _corrida(q.get("id", ""))


@ruta("GET", "/api/junit")
def junit(q, _b):
    xml = suites.junit([_corrida(q.get("id", ""))])
    return Archivo(xml.encode("utf-8"), "application/xml; charset=utf-8", f"{q.get('id')}.xml")
