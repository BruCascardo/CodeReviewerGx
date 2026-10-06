"""Pruebas del revisor, con fragmentos de .sp0 reales (no necesitan las KBs).

    python -m unittest discover -s gxp/revisor/pruebas -t .
"""
import textwrap

from gxp.revisor import fuente


def sp0(nombre, lineas, tipo="proc", props=None, extra=""):
    """Texto de un .sp0 minimo: spec_i, propiedades, variables (extra) y las lineas b_line_i."""
    ruta = "\\".join(nombre.split("."))
    partes = [f"spec_i([ {tipo},1,'{nombre.split('.')[-1]}','{ruta}',0,spa,'18_0_15' ])."]
    props = {"Folder": None, **(props or {})}
    for k, v in props.items():
        if k == "Folder":
            partes.append(f"rule_i(0,prop('Folder',o(8,'{ruta}'))).")
        elif v is not None:
            partes.append(f"rule_i(0,prop('{k}','{v}')).")
    partes.append("rule_i(0,datastore(1,'USER_PASSWORD','no se lee')).")
    partes.append(textwrap.dedent(extra).strip())
    partes.extend(textwrap.dedent(lineas).strip().splitlines())
    return "\n".join(partes) + "\n"


def leer(nombre, lineas, **kw):
    return fuente._armar(f"{nombre}.sp0", sp0(nombre, lineas, **kw))


# ---------------------------------------------------------------------- lineas b_line_i
# Constructores de lineas del .sp0, para armar fragmentos legibles en las pruebas. 'n' es el numero de linea.

def linea(n, codigo, *toks):
    return f"b_line_i({n},1,1,cmd,0,[ t('',{codigo},{n},0){''.join(',' + t for t in toks)} ])."


def tipo(valor):
    """MessageTypes.<valor>"""
    return f"t([ 37,'{valor}' ],44,0,0)"


def asignar(n, var, *valor):
    return linea(n, 107, f"t('{var}',23,0,0)", "t(=,10,0,0)", *valor)


def asignar_campo(n, var, campo, *valor):
    return linea(n, 107, f"t([ t('{var}',23,0,0),t('{campo}',3,0,0) ],29,0,0)", "t(=,10,0,0)", *valor)


def metodo(n, var, nombre, *args):
    """&Var.Nombre(args)"""
    return linea(n, 107, f"t([ t('{var}',23,0,0),t('{nombre.lower()}(',1,0,0) ],31,0,0)", *_con_comas(args),
                 "t(')',4,0,0)")


def si(n, *cond):
    return linea(n, 109, *cond)


def si_igual(n, var, valor_tipo):
    return si(n, f"t('{var}',23,0,0)", "t(=,10,0,0)", tipo(valor_tipo))


def sino(n):
    return linea(n, 110)


def fin_si(n):
    return linea(n, 111)


def volver(n):
    return linea(n, 118)


def _nombre_sub(nombre):
    return "t('''" + nombre + "''',3,0,0)"


def do(n, nombre):
    return linea(n, 145, _nombre_sub(nombre))


def sub(n, nombre):
    return linea(n, 143, _nombre_sub(nombre))


def fin_sub(n):
    return linea(n, 144)


def llamar(n, objeto, *args):
    return linea(n, 104, f"t(o(1,'{objeto}'),28,0,0)", *_con_comas(args))


def _con_comas(args):
    salida = []
    for i, a in enumerate(args):
        if i:
            salida.append("t(',',7,0,0)")
        salida.append(a)
    return salida
