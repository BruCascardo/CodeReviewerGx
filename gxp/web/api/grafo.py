"""Pantalla Grafo."""
from ..rutas import ruta
from ... import grafo


@ruta("GET", "/api/grafo")
def datos_grafo(_q, _b):
    if not grafo.estado()["kbs"]:
        grafo.actualizar()  # primera vez: lee lo guardado en .cache/grafo (o lo arma)
    return grafo.compacto()


@ruta("GET", "/api/grafo/estado")
def estado_grafo(_q, _b):
    return grafo.estado()
