"""Campos de la entrada de un objeto y el dominio de cada uno, leidos de su especificacion (.sp0).

El .sp0 de un procedimiento trae la estructura de los SDT que usa, con el dominio de cada campo, y los
valores de los dominios enumerados que intervienen:

    attri_i('Inset',[ inSet,o('Generales\\Interfases\\Registro\\inSet'),...]).    <- variable y su tipo
    struct_dt_i([ 26,934,0 ],name,'Generales\\Interfases\\Registro\\inSet').
    struct_dt_elem_i([ 26,934,0 ],5,name,'Fin').
    struct_dt_elem_i([ 26,934,0 ],5,basedon,296).                                 <- dominio del campo
    struct_dt_elem_i([ 26,385,0 ],3,type,[ [ 26,385,1523 ],4,0 ]).                <- campo SDT (o nivel anidado)
    struct_dt_elem_i([ 26,385,0 ],3,collection,'True').
    enum_value_info_i(2,296,'Generales\\RegistroFin').
    enum_value_i(2,296,'"CR"','CR','"CR"',[ none ]).                              <- valor, nombre, descripcion
    enumerated_i(2,'Itftipo',293).                                                <- variable de un dominio enumerado
    enumerated_i(2,602,293).                                                      <- atributo de un dominio enumerado
"""
import threading
from pathlib import Path

from ..revisor import prolog
from ..revisor.prolog import Comp

MAX_PROFUNDIDAD = 6  # SDT dentro de SDT

_PREDICADOS = ["attri_i", "struct_dt_i", "struct_dt_elem_i", "enum_value_i", "enum_value_info_i", "dom_info_i",
               "enumerated_i"]
_cache = {}
_lock = threading.Lock()


class Especificacion:
    def __init__(self):
        self.variables = {}   # nombre real en minusculas -> tipo ('int', 'Mod\\SDT', Comp objectcollection)
        self.enum_vars = {}   # clave de la variable en minusculas ('itftipo') -> id de dominio
        self.atributos = {}   # nombre en minusculas -> id
        self.enum_atts = {}   # id de atributo -> id de dominio
        self.sdts = {}        # 'mod\\sdt' -> id
        self.campos = {}      # id de SDT o nivel -> [(nombre, id de dominio, id de SDT, es coleccion)]
        self.dominios = {}    # id -> 'Modulo\\Dominio'
        self.valores = {}     # id de dominio -> [{valor, nombre, descripcion}]


def _id(v):
    return tuple(_id(x) for x in v) if isinstance(v, list) else v


def _literal(texto):
    """'"S"' -> 'S'; '3' -> 3 (los enumerados numericos vienen sin comillas dobles)."""
    t = str(texto)
    if len(t) >= 2 and t[0] == t[-1] == '"':
        return t[1:-1]
    try:
        return int(t)
    except ValueError:
        try:
            return float(t)
        except ValueError:
            return t


def leer(ruta) -> Especificacion:
    """Especificacion de un .sp0, recordada por fecha del archivo."""
    ruta = Path(ruta)
    mt = ruta.stat().st_mtime_ns
    with _lock:
        previo = _cache.get(str(ruta))
        if previo and previo[0] == mt:
            return previo[1]
    with open(ruta, encoding="cp1252", errors="replace") as f:
        es = armar(f.read())
    with _lock:
        _cache[str(ruta)] = (mt, es)
    return es


def armar(texto) -> Especificacion:
    es = Especificacion()
    elems = {}  # (id, n) -> {name, basedon, type, collection}
    for nombre, c in prolog.clausulas(texto, _PREDICADOS, saltear=("rule_i(0,datastore(",)):
        a = c.args
        if nombre == "attri_i":
            if isinstance(a[0], int):
                es.atributos[str(a[1][0]).lower()] = a[0]
            else:
                es.variables[str(a[1][0]).lower()] = a[1][1]
        elif nombre == "struct_dt_i" and a[1] == "name":
            es.sdts[str(a[2]).lower()] = _id(a[0])
        elif nombre == "struct_dt_elem_i" and a[2] in ("name", "basedon", "type", "collection"):
            elems.setdefault((_id(a[0]), a[1]), {})[a[2]] = a[3]
        elif nombre == "enum_value_i" and len(a) >= 5:
            es.valores.setdefault(a[1], []).append(
                {"valor": _literal(a[2]), "nombre": str(a[3]), "descripcion": str(_literal(a[4]))})
        elif nombre == "enum_value_info_i":
            es.dominios[a[1]] = str(a[2])
        elif nombre == "dom_info_i" and isinstance(a[1], list) and a[1]:
            es.dominios.setdefault(a[0], str(a[1][0]))
        elif nombre == "enumerated_i":
            if isinstance(a[1], int):
                es.enum_atts[a[1]] = a[2]
            else:
                es.enum_vars[str(a[1]).lower()] = a[2]
    for (sid, _n), d in sorted(elems.items(), key=lambda x: (str(x[0][0]), x[0][1])):
        tipo = d.get("type")
        ref = _id(tipo[0]) if isinstance(tipo, list) and tipo and isinstance(tipo[0], list) else None
        dom = d.get("basedon") if isinstance(d.get("basedon"), int) else None
        es.campos.setdefault(sid, []).append((str(d.get("name", "")), dom, ref, d.get("collection") == "True"))
    return es


def _sdt_de(tipo):
    """Tipo de una variable -> ('Mod\\SDT', es coleccion), o (None, False) si no es un SDT."""
    if isinstance(tipo, Comp) and tipo.nombre == "o" and tipo.args:
        t = tipo.args[0]
        if isinstance(t, Comp) and t.nombre == "objectcollection" and t.args:
            return str(t.args[0]), True
        if isinstance(t, str):
            return t, False
    return None, False


def hojas(es: Especificacion, parametros):
    """(ruta, nombre del campo, id de dominio) de cada valor simple de la entrada: los parametros in/inout y,
    adentro de los SDT, cada campo. La ruta va en minusculas y con [*] en las colecciones: inset.items[*].id"""
    for p in parametros:
        if p.get("io") not in ("in", "inout"):
            continue
        nombre, ruta = p["nombre"], p["nombre"].lower()
        if p.get("atributo"):
            yield ruta, nombre, es.enum_atts.get(es.atributos.get(ruta))
            continue
        sdt, coleccion = _sdt_de(es.variables.get(ruta))
        if sdt is None:
            yield ruta, nombre, es.enum_vars.get(ruta)
            continue
        sid = es.sdts.get(sdt.lower())
        if sid is not None:
            yield from _campos(es, sid, ruta + ("[*]" if coleccion else ""), 0)


def _campos(es, sid, prefijo, prof):
    if prof > MAX_PROFUNDIDAD:
        return
    for nombre, dom, ref, coleccion in es.campos.get(sid, []):
        ruta = f"{prefijo}.{nombre.lower()}" + ("[*]" if coleccion else "")
        if ref is not None:
            yield from _campos(es, ref, ruta, prof + 1)
        else:
            yield ruta, nombre, dom
