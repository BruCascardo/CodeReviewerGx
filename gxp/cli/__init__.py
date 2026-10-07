"""Linea de comandos de GxPruebas (gxpruebas.py).

Uso:
  python gxpruebas.py ui                                   abre la interfaz grafica en el navegador
  python gxpruebas.py kbs                                  lista las KBs encontradas
  python gxpruebas.py objetos   --kb Generales [--buscar Interfases]
  python gxpruebas.py describir --kb Generales --objeto Generales.Interfases.Registro.Get
  python gxpruebas.py ejecutar  --kb Generales --objeto Generales.Interfases.Registro.Get \\
                                --entrada "{\\"inGet\\": {\\"ItfId\\": 1, \\"RegTipo\\": \\"DETALLE\\"}}" [--commit] \\
                                [--sql "GENERALES: select count(*) n from gntItfRegistro"]
  python gxpruebas.py sql       --kb Generales --ds GENERALES "select * from gntInterfase"
  python gxpruebas.py plan      --kb Generales --objeto Generales.Empresas.Get [--detalle] [--json]
                                plan de ejecucion (EXPLAIN) de sus sentencias SQL y recomendaciones
  python gxpruebas.py correr    [suite ...] [--kb Generales] [--etiqueta x] [--filtro texto]
                                [--grabar] [--junit salida.xml] [--json] [--detalle]
  python gxpruebas.py suites    [--kb Generales]
  python gxpruebas.py vigilar   [--kb Generales] [--etiqueta auto] [--espera 15] [--sin-notificar]
                                corre las suites despues de cada build (la interfaz lo hace sola si
                                'despuesDelBuild.activo' es true en config.json)

'correr' sin suites corre todas (o todas las de --kb). Devuelve codigo 0 si todo paso, 1 si hubo fallas
o errores, 2 si no se pudo correr. Las suites se nombran por su id (Generales/interfases-registro), por
ruta de archivo o por una parte unica del nombre.

Cada modulo registra sus comandos con registrar(sub) y la logica vive en los paquetes de gxp:
  objetos.py   kbs, objetos, describir, ejecutar, sql, plan
  suites.py    correr, suites, vigilar, generar
  grafo.py     grafo, ui
  revisar.py   revisar
  consola.py   colores y JSON
"""
import argparse
import sys

from . import grafo, objetos, revisar, suites
from .consola import error
from .. import motor

_MODULOS = (grafo, objetos, suites, revisar)


def armar_parser():
    ap = argparse.ArgumentParser(prog="gxpruebas", description=__doc__.split("\n\nCada modulo")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    for m in _MODULOS:
        m.registrar(sub)
    return ap


def main(argv=None):
    ap = armar_parser()
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    try:
        return a.fn(a) or 0
    except KeyError as e:
        error(str(e).strip("'\""))
        return 2
    except motor.MotorError as e:
        error(f"Error del motor: {e}")
        return 2
    finally:
        if a.cmd != "ui":
            motor.detener_todos()


def preparar_consola():
    """La consola de Windows no es UTF-8 por defecto: sin esto, los acentos de las salidas rompen el print."""
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
