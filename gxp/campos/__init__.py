"""Ayuda para completar la entrada de un objeto: que valores admite cada campo.

  dominios.py  campos de la entrada y su dominio, de la especificacion del objeto (valores de los enumerados)
  indice.py    tablas de la KB con su clave y su descriptor, y dominios enumerados, de las transacciones

de_objeto() dice, por ruta del campo, si es de un dominio enumerado (con sus valores) o si es la clave de una
tabla; valores() trae de la base los valores de esa clave, para elegirlos en un combo.
"""
import re

from .. import catalogo, motor
from ..revisor import fuente
from . import dominios, indice

MAXIMO = 300  # filas que se traen para un combo de claves


def de_objeto(kb, nombre):
    """{ruta: ayuda} de los campos de la entrada que la tienen. La ruta va en minusculas y con [*] en las
    colecciones (inset.items[*].itfid). La ayuda es
        {"dominio": "Generales\\RegistroFin", "valores": [{valor, nombre, descripcion}]}   dominio enumerado
        {"dominio": "Generales\\Id", "clave": {tabla, atributo, claves, descripcion, titulo}}  clave de una tabla
    """
    info = catalogo.buscar(kb, nombre)  # KeyError si no existe
    ruta = fuente.ubicar(kb, info["nombre"])
    if ruta is None:
        return {}
    es = dominios.leer(ruta)
    ix = indice.de_kb(kb)
    salida = {}
    for r, campo, dom in dominios.hojas(es, info["parametros"]):
        ayuda = {}
        nombre_dom = es.dominios.get(dom) or ix.dominios.get(dom)
        if nombre_dom:
            ayuda["dominio"] = nombre_dom
        # Los valores del enumerado: de la especificacion del objeto o, si no los trae, de las transacciones.
        valores_dom = es.valores.get(dom) or ix.valores.get(dom)
        if valores_dom:
            ayuda["valores"] = valores_dom
        elif ix.tablas.get(campo.lower()):
            ayuda["clave"] = ix.tablas[campo.lower()].json()
        if "valores" in ayuda or "clave" in ayuda:
            salida[r] = ayuda
    return salida


def _literal(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).strip()
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


def _usable(v):
    """Un valor de la entrada que sirve de filtro: no vacio, no una ${variable} ni un comodin."""
    if v is None or isinstance(v, (dict, list)):
        return False
    s = str(v).strip()
    return s != "" and "${" not in s and "<<" not in s


def valores(kb, atributo, filtros=None, buscar="", maximo=MAXIMO):
    """Filas de la tabla de la que 'atributo' es la clave: {tabla, claves, descripcion, columnas, filas,
    truncado, filtros}. 'filtros' son los demas campos de la entrada: los que son parte de la clave (ItfId para
    ItfRegTipo) filtran. 'buscar' filtra por la descripcion o por el valor."""
    t = indice.de_kb(kb).tablas.get((atributo or "").lower())
    if t is None:
        raise KeyError(f"{atributo} no es la clave de ninguna tabla de la KB {kb.nombre}")
    cols = t.claves + ([t.descripcion] if t.descripcion else [])
    donde, usados = [], {}
    minus = {str(k).lower(): v for k, v in (filtros or {}).items()}
    for k in t.claves[:-1]:
        v = minus.get(k.lower())
        if _usable(v):
            donde.append(f"{k} = {_literal(v)}")
            usados[k] = v
    buscar = (buscar or "").strip()
    if buscar:
        patron = _literal("%" + re.sub(r"([%_])", r"\\\1", buscar) + "%")
        o = [f"CAST({t.claves[-1]} AS CHAR) LIKE {patron}"]
        if t.descripcion:
            o.append(f"{t.descripcion} LIKE {patron}")
        donde.append("(" + " OR ".join(o) + ")")
    q = f"select {', '.join(cols)} from {t.nombre}"
    if donde:
        q += " where " + " and ".join(donde)
    q += " order by " + ", ".join(t.claves)
    r, datos = motor.consulta_suelta(kb, "", q, maximo=maximo)
    if not r.get("ok"):
        raise motor.MotorError(r.get("error") or "No se pudieron leer los valores")
    return {**t.json(), "consulta": q, "filtros": usados, "columnas": datos.get("columnas", []),
            "filas": datos.get("filas", []), "truncado": datos.get("truncado", False)}
