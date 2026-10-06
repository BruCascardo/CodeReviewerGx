"""Registro de las rutas de la API: cada modulo de gxp/web/api registra sus funciones con @ruta.

Una funcion de la API recibe (query, cuerpo JSON) y devuelve lo que se manda como JSON, o un Archivo para
una descarga. Para responder un error con su codigo HTTP, lanza ErrorApi.
"""
from collections import namedtuple

from .. import kbs

RUTAS = {}  # (metodo, camino) -> funcion

Archivo = namedtuple("Archivo", "contenido tipo nombre")


class ErrorApi(Exception):
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.codigo = codigo


def ruta(metodo, camino):
    def registrar(fn):
        if (metodo, camino) in RUTAS:
            raise ValueError(f"La ruta {metodo} {camino} esta registrada dos veces")
        RUTAS[(metodo, camino)] = fn
        return fn
    return registrar


def mensaje(e):
    """Texto de una excepcion sin las comillas que agrega KeyError."""
    return str(e).strip("'\"")


def kb(nombre):
    """La KB por nombre, o 404."""
    try:
        return kbs.obtener(nombre)
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


def kbs_del_pedido(d):
    """Las KBs de un pedido: una (kb) o todas (todas=1), sin las repetidas por raiz."""
    if str(d.get("todas", "")).lower() in ("1", "true"):
        return kbs.principales()
    return [kb(d.get("kb"))]
