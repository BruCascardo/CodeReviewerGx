"""Datos de la pantalla Revision de la interfaz.

Lista los objetos de una o de todas las KBs ordenados por la fecha de su especificacion (lo recien
modificado primero) y revisa en el momento solo la pagina que se muestra. La linea base permite saltear sin
leerlos los objetos que no cambiaron desde la ultima revision y que esa revision no tuvo en cuenta (ignorados,
SDT) o, con un filtro, los que no tenian problemas.
"""
import datetime as dt
import os
import threading
import time

from . import configuracion, fuente, lineabase, revisor

VIGENCIA_LISTADO = 15  # segundos que se reusa el listado de especificaciones de una KB
FILTROS = ("todos", "problemas", "nuevos")

_listados = {}
_lock = threading.Lock()


def _listar(kb):
    with _lock:
        c = _listados.get(kb.nombre)
        if c and time.time() - c[0] < VIGENCIA_LISTADO:
            return c[1]
    lista = fuente.listar(kb)
    with _lock:
        _listados[kb.nombre] = (time.time(), lista)
    return lista


def olvidar():
    """Despues de una revision: el proximo pedido vuelve a listar."""
    with _lock:
        _listados.clear()


def _nombre(ruta, bases):
    """Nombre del objeto segun su ruta (GEN12\\Generales\\Interfases\\Set.sp0 -> Generales.Interfases.Set)."""
    for b in bases:
        if ruta.startswith(b):
            return ruta[len(b):-4].replace(os.sep, ".")
    return os.path.basename(ruta)[:-4]


def _fecha(mt):
    return dt.datetime.fromtimestamp(mt).isoformat(timespec="seconds")


def objetos(lista_kbs, texto="", filtro="todos", desde=0, limite=40):
    """Pagina de objetos ordenados por fecha de especificacion (descendente), con sus hallazgos.
    'desde' es la posicion donde siguio la pagina anterior ('siguiente' de la respuesta)."""
    if filtro not in FILTROS:
        filtro = "todos"
    conf = configuracion.cargar()
    reglas = revisor.reglas_activas(conf)
    datos, items, kbs_info = {}, [], []
    for kb in lista_kbs:
        lb = lineabase.LineaBase(kb)
        bases = [str(g) + os.sep for g in fuente.carpetas_spec(kb)]
        datos[kb.nombre] = (kb, lb, revisor.Contexto(kb, conf), bases)
        lista = _listar(kb)
        items.extend((mt, kb.nombre, ruta) for ruta, mt in lista)
        kbs_info.append({"kb": kb.nombre, "lineaBase": lb.actualizada,
                         "cambiados": sum(1 for r, mt in lista if lb.cambio(r, mt)) if lb.existe else None})
    items.sort(key=lambda x: -x[0])
    texto = (texto or "").strip().lower()
    salida, siguiente = [], None
    for i in range(max(0, int(desde)), len(items)):
        mt, kbn, ruta = items[i]
        kb, lb, ctx, bases = datos[kbn]
        nombre = _nombre(ruta, bases)
        if texto and texto not in nombre.lower():
            continue
        cambio = lb.cambio(ruta, mt)
        clave = nombre.lower()
        if lb.existe and not cambio:
            if clave not in lb.huellas:
                continue  # la ultima revision no lo tuvo en cuenta: ignorado o sin codigo
            if filtro == "problemas" and not lb.huellas[clave]:
                continue
            if filtro == "nuevos" and not lb.nuevas.get(clave):
                continue
        try:
            fu = fuente.leer(ruta)
        except Exception as e:
            salida.append({"kb": kbn, "objeto": nombre, "fecha": _fecha(mt), "cambio": cambio, "tipo": "",
                           "hallazgos": [], "excepcionados": 0, "errores": [f"no se pudo leer la especificacion: {e}"]})
            continue
        if not fu.nombre or fu.tipo == "sdt" or conf.ignorado(fu):
            continue
        hs, exc, _, errs = revisor.revisar_fuente(fu, reglas, ctx, conf, lb, cambio)
        if filtro == "problemas" and not hs:
            continue
        if filtro == "nuevos" and not any(h["nuevo"] for h in hs):
            continue
        hs.sort(key=lambda h: (h["severidad"] != "error", h["linea"]))
        salida.append({"kb": kbn, "objeto": fu.nombre, "tipo": fu.tipo_texto, "fecha": _fecha(mt), "cambio": cambio,
                       "hallazgos": hs, "excepcionados": len(exc), "errores": [e["error"] for e in errs]})
        if len(salida) >= limite:
            siguiente = i + 1 if i + 1 < len(items) else None
            break
    return {"objetos": salida, "siguiente": siguiente, "kbs": kbs_info, "reglas": [r.id for r in reglas],
            "avisos": conf.avisos}


def fuente_objeto(kb, objeto):
    """Fuente GX reconstruido del objeto, con sus hallazgos por linea."""
    ruta = fuente.ubicar(kb, objeto)
    if ruta is None:
        raise KeyError(f"No encuentro la especificacion de '{objeto}' en {kb.nombre}.")
    fu = fuente.leer(ruta)
    conf = configuracion.cargar()
    lb = lineabase.LineaBase(kb)
    mt = os.stat(ruta).st_mtime
    hs, exc, _, _ = revisor.revisar_fuente(fu, revisor.reglas_activas(conf), revisor.Contexto(kb, conf), conf, lb,
                                           lb.cambio(ruta, mt))
    return {"kb": kb.nombre, "objeto": fu.nombre, "tipo": fu.tipo_texto, "fecha": _fecha(mt), "ruta": str(ruta),
            "parametros": [{"nombre": n, "io": io} for n, io in fu.parametros], "commitOnExit": fu.commit_on_exit,
            "lineas": [{"linea": s.linea, "nivel": s.nivel, "texto": s.texto} for s in fu.sentencias if not s.generada],
            "hallazgos": hs, "excepcionados": exc}


def revisar_cambios(lista_kbs):
    """Revisa lo que cambio desde la ultima revision en cada KB (deja la linea base al dia)."""
    salida = []
    for kb in lista_kbs:
        r = revisor.revisar(kb, cambiados=True, origen="interfaz")
        salida.append({"kb": kb.nombre, "revisados": r["revisados"], "totales": r["totales"], "nuevos": r["nuevos"],
                       "modo": r["modo"], "errores": len(r["errores"])})
    olvidar()
    return salida
