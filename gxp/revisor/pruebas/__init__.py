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
