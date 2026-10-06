"""Generacion de suites de regresion para los objetos de solo lectura (comando 'generar').

  generar.py  candidatos, prueba de cada objeto y escritura de las suites auto-*
  esquema.py  entradas con datos reales de la base
"""
from .generar import ETIQUETA, PREFIJO, candidatos, generar_kb

__all__ = ["ETIQUETA", "PREFIJO", "candidatos", "generar_kb"]
