"""Funciones de la API, una por ruta, agrupadas por pantalla. Importar este paquete registra todas las rutas
(gxp/web/rutas.py). Para agregar una: una funcion con @ruta("GET", "/api/...") en el modulo de su pantalla."""
from . import general, grafo, objetos, revision, suites  # noqa: F401
