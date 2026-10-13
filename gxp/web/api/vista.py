"""Vista previa de Web Panels y Web Components en Explorar (ver gxp/vista.py)."""
import re

from ..rutas import ErrorApi, kb, mensaje, ruta
from ... import catalogo, grafo, pantallas_pasos, suites, vista

_SESION = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _sesion(d):
    s = str(d.get("sesion") or "")
    if not _SESION.match(s):
        raise ErrorApi("Sesion de vista previa invalida")
    return s


@ruta("POST", "/api/vista/url")
def url(_q, b):
    """La URL para abrir la pantalla en el iframe, con sus parametros (cifrados como en un link())."""
    k = kb(b.get("kb"))
    try:
        info = catalogo.buscar(k, b.get("objeto", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    if info["tipo"] not in ("WebPanel", "Transaction"):
        raise ErrorApi(f"{info['nombre']} no se puede abrir solo: es un {info['tipo']}")
    if info.get("master"):
        raise ErrorApi(f"{info['nombre']} es una master page: no se abre sola, se ve en las pantallas que la usan")
    return {"url": vista.url(k, info["nombre"], b.get("parametros") or [], _sesion(b), b.get("permisos") or "todos")}


@ruta("GET", "/api/vista/contenedores")
def contenedores(q, _b):
    """Las pantallas de la KB que usan un Web Component: GeneXus no deja abrirlo solo ("WebComponent is not
    allowed to run"), se ve dentro de una de ellas. Cada una con sus parametros de entrada."""
    k = kb(q.get("kb"))
    if not grafo.estado()["kbs"]:
        grafo.actualizar()
    salida, vistos = [], set()
    for _nodo, usan, _usa in grafo.vecinos(q.get("objeto", ""), k.nombre, maximo=1):
        for vecino, *_resto in usan:
            nombre = vecino[1]
            if vecino[0] != k.nombre or vecino[2] != "Web Panel" or nombre in vistos:
                continue
            vistos.add(nombre)
            try:
                info = catalogo.buscar(k, nombre)
            except KeyError:
                continue
            salida.append({"nombre": nombre, "tipo": info["tipo"],
                           "parametros": [p for p in info["parametros"] if p["io"] != "out"]})
    # Primero los Web Panels: un Web Component que contiene a otro tampoco se abre solo.
    return sorted(salida, key=lambda x: (x["tipo"] != "WebPanel", x["nombre"]))[:15]


@ruta("POST", "/api/vista/grabar")
def grabar(_q, b):
    """accion "empezar" (deshace todo antes: el caso arranca de la base sin cambios) o "detener"."""
    k = kb(b.get("kb"))
    n = vista.grabar(k, _sesion(b), b.get("accion") == "empezar")
    return {"pedidos": n}


@ruta("GET", "/api/vista/grabacion")
def grabacion(q, _b):
    """Si se esta grabando la sesion y cuantos pedidos van."""
    grabando, pedidos = vista.grabacion(kb(q.get("kb")), _sesion(q))
    return {"grabando": grabando, "pedidos": len(pedidos)}


@ruta("POST", "/api/vista/pasos")
def pasos(_q, b):
    """Los pasos del caso que sale de lo grabado (sin la salida aprobada), para mostrarlos antes de guardar."""
    k = kb(b.get("kb"))
    sesion = _sesion(b)
    _, pedidos = vista.grabacion(k, sesion)
    lista = pantallas_pasos.a_pasos(k, pedidos, sesion)
    return {"pasos": [{kk: v for kk, v in p.items() if kk != "lineaBase"} for p in lista],
            "nombre": pantallas_pasos.nombre_caso(lista)}


@ruta("POST", "/api/vista/caso")
def guardar_caso(_q, b):
    """Guarda lo grabado como un caso de la suite 'id' (la crea si no existe), con lo que se vio al grabar como
    salida aprobada, y lo vuelve a correr para marcar los valores que cambian solos."""
    k = kb(b.get("kb"))
    sesion = _sesion(b)
    sid = (b.get("id") or "").strip()
    if not sid:
        raise ErrorApi("Falta la suite")
    if suites.almacen.existe(sid) and suites.almacen.cargar(sid).get("scriptPrevio"):
        raise ErrorApi("Esa suite tiene script previo y un caso de pantalla todavia no lo puede usar: elegí otra suite")
    _, pedidos = vista.grabacion(k, sesion)
    if not pedidos:
        raise ErrorApi("No hay nada grabado")
    lista = pantallas_pasos.a_pasos(k, pedidos, sesion)
    omitir = set(b.get("omitir") or [])
    lista = [p for i, p in enumerate(lista) if i not in omitir]
    if not lista:
        raise ErrorApi("No quedo ningun paso para guardar")
    caso = {"nombre": (b.get("nombre") or "").strip() or pantallas_pasos.nombre_caso(lista), "etiquetas": ["pantalla"],
            "pasos": lista}
    suite_id, caso_id = suites.almacen.agregar_caso(sid, caso, False, b.get("nombreSuite"), k.nombre)
    r = {"id": suite_id, "casoId": caso_id}
    r.update(suites.volatiles_de_caso(suite_id, caso_id))
    return r


@ruta("POST", "/api/vista/reiniciar")
def reiniciar(_q, b):
    """Deshace todo lo que grabaron las pantallas de la KB (nunca se confirmo nada) y olvida sus sesiones."""
    return vista.reiniciar(kb(b.get("kb")))


@ruta("GET", "/api/vista/estado")
def estado(q, _b):
    """Pedidos, commits y rollbacks simulados y la ultima excepcion de las pantallas de la KB."""
    return vista.estado(kb(q.get("kb")))
