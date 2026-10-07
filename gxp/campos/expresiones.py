"""Valores que las ${variables} de los casos calculan en la base al ejecutar, a partir de la clave de una tabla:

    ${siguiente.CuponId}                          el ultimo CuponId de cbhCupon, mas uno: uno que no existe
    ${existente.CuponId}                          el primero que existe (el de clave mas chica)
    ${ultimo.CuponId}                             el ultimo que existe
    ${existente.CuponId|CuponEstado=EN_PROCESO}   el primero que cumple las condiciones (separadas por coma)
    ${con_hijos.CuponId}                          uno que tiene filas en alguna tabla que lo referencia
    ${con_hijos.CuponId:cbhCuponDetalle}          ... en esa tabla
    ${sin_hijos.CuponId}                          uno que no tiene filas en ninguna (o, con :tabla, en esa)

Las condiciones son Atributo=valor (tambien !=, <, >, <=, >=) sobre atributos de la misma tabla. En un atributo de
un dominio enumerado se puede usar el nombre del valor (EN_PROCESO) en lugar del valor guardado (PRO). Un valor
entre comillas se toma como texto tal cual. Las tablas hijas son las que tienen toda la clave entre sus atributos
(los niveles subordinados y las que la referencian con una clave foranea).
"""
import re
from decimal import Decimal

from .. import motor
from . import indice

FUNCIONES = ("siguiente", "existente", "ultimo", "con_hijos", "sin_hijos")
_COND = re.compile(r"^\s*(\w+)\s*(<=|>=|!=|<>|=|<|>)\s*(.*?)\s*$")
_IDENT = re.compile(r"^\w+$")


class Pedido:
    def __init__(self, funcion, atributo, hija="", condiciones=()):
        self.funcion = funcion
        self.atributo = atributo
        self.hija = hija                      # tabla hija de con_hijos / sin_hijos, o ""
        self.condiciones = list(condiciones)  # [(atributo, operador SQL, valor como se escribio)]


def parsear(funcion, resto):
    """'CuponId:tabla|A=1,B=X' -> Pedido. ValueError si esta mal escrito."""
    if funcion not in FUNCIONES:
        raise ValueError(f"funcion desconocida '{funcion}': las que hay son {', '.join(FUNCIONES)}")
    cabeza, _, conds = resto.partition("|")
    atributo, _, hija = cabeza.partition(":")
    atributo, hija = atributo.strip(), hija.strip()
    if not _IDENT.match(atributo):
        raise ValueError(f"falta el atributo: se escribe ${{{funcion}.Atributo}}")
    if hija and (funcion not in ("con_hijos", "sin_hijos") or not _IDENT.match(hija)):
        raise ValueError(f"':{hija}' solo va en con_hijos y sin_hijos, con el nombre de una tabla")
    condiciones = []
    for c in conds.split(",") if conds.strip() else []:
        m = _COND.match(c)
        if not m:
            raise ValueError(f"condicion invalida '{c.strip()}': se escribe Atributo=valor (o !=, <, >, <=, >=)")
        condiciones.append((m[1], "<>" if m[2] == "!=" else m[2], m[3]))
    if funcion == "siguiente" and condiciones:
        raise ValueError("siguiente no lleva condiciones: es el ultimo de toda la tabla, mas uno")
    return Pedido(funcion, atributo, hija, condiciones)


def _tabla(ix, atributo):
    t = ix.tablas.get(atributo.lower())
    if t is None:
        raise ValueError(f"{atributo} no es la clave de ninguna tabla de la KB")
    return t


def _literal_sql(ix, t, columna, valor):
    v = str(valor)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    else:
        dom = next((d for a, d in t.enumerados.items() if a.lower() == columna.lower()), None)
        nombre = next((e["valor"] for e in ix.valores.get(dom, []) if str(e["nombre"]).lower() == v.lower()), None)
        if nombre is not None:
            v = nombre
        if re.fullmatch(r"-?\d+(\.\d+)?", str(v)):
            return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def hijas(ix, t, nombre=""):
    hs = ix.hijas(t)
    if nombre:
        elegidas = [h for h in hs if h.nombre.lower() == nombre.lower()]
        if not elegidas:
            otras = ", ".join(h.nombre for h in hs) or "ninguna"
            raise ValueError(f"{nombre} no tiene la clave de {t.nombre} (la tienen: {otras})")
        return elegidas
    return hs


def consulta(ix, p):
    """(tabla, select) del pedido. ValueError si no se puede armar."""
    t = _tabla(ix, p.atributo)
    k = t.claves[-1]
    if p.funcion == "siguiente":
        if not t.numerica:
            raise ValueError(f"{k} es de tipo {t.tipo or 'desconocido'}: el siguiente solo se calcula para claves numericas")
        return t, f"select coalesce(max({k}), 0) + 1 as valor from {t.nombre}"
    donde = []
    for c, op, v in p.condiciones:
        if not t.tiene(c):
            raise ValueError(f"{c} no es un atributo de {t.nombre}")
        donde.append(f"t.{c} {op} {_literal_sql(ix, t, c, v)}")
    if p.funcion in ("con_hijos", "sin_hijos"):
        hs = hijas(ix, t, p.hija)
        if not hs and p.funcion == "con_hijos":
            raise ValueError(f"ninguna tabla de la KB tiene la clave de {t.nombre}")
        subs = [f"exists (select 1 from {h.nombre} h where " + " and ".join(f"h.{c} = t.{c}" for c in t.claves) + ")"
                for h in hs]
        if p.funcion == "con_hijos":
            donde.append("(" + " or ".join(subs) + ")")
        else:
            donde.extend("not " + s for s in subs)
    orden = " desc" if p.funcion == "ultimo" else ""
    q = f"select t.{k} as valor from {t.nombre} t"
    if donde:
        q += " where " + " and ".join(donde)
    return t, q + " order by " + ", ".join(f"t.{c}{orden}" for c in t.claves) + " limit 1"


def _convertir(t, v):
    """El valor con el tipo de la clave: un char '0012' sigue siendo texto."""
    if not t.numerica:
        return v.rstrip() if isinstance(v, str) else v
    if isinstance(v, str):
        try:
            d = Decimal(v.strip())
            return int(d) if d == d.to_integral_value() else float(d)
        except ArithmeticError:
            return v.rstrip()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def resolver(kb, funcion, resto, en_transaccion=True):
    """El valor de ${funcion.resto}. Con en_transaccion usa la conexion del caso que esta corriendo (ve lo que hizo
    el script previo y los pasos anteriores); si no, toma el motor y termina con rollback. ValueError si no se
    puede calcular o no hay ninguna fila que cumpla."""
    p = parsear(funcion, resto)
    ix = indice.de_kb(kb)
    t, q = consulta(ix, p)
    if en_transaccion:
        r, datos = motor.ejecutar_sql(kb, "", q, 60000, 1)
    else:
        r, datos = motor.consulta_suelta(kb, "", q, maximo=1)
    if not r.get("ok"):
        raise ValueError(r.get("error") or f"no se pudo consultar {t.nombre}")
    if not datos.get("filas"):
        conds = ", ".join(f"{c} {op} {v}" for c, op, v in p.condiciones)
        nombres = [h.nombre for h in hijas(ix, t, p.hija)]
        que = {"con_hijos": " con filas en " + " o en ".join(nombres),
               "sin_hijos": " sin filas en " + " ni en ".join(nombres)}.get(p.funcion, "")
        raise ValueError(f"no hay ningun {t.claves[-1]} en {t.nombre}{que}" + (f" que cumpla {conds}" if conds else ""))
    return _convertir(t, next(iter(datos["filas"][0].values())))
