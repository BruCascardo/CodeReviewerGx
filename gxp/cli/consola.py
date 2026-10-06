"""Salida por consola de los comandos: colores (solo si es una terminal) y JSON."""
import json
import sys

COLORES = sys.stdout.isatty()
_CODIGOS = {"verde": "32", "rojo": "31", "amarillo": "33", "gris": "90", "negrita": "1"}


def c(texto, color):
    if not COLORES:
        return texto
    return f"\x1b[{_CODIGOS[color]}m{texto}\x1b[0m"


def imprimir_json(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def error(texto):
    print(texto, file=sys.stderr)
