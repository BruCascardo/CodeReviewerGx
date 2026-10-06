"""Estructura de los SDT, leida de su especificacion (GXSDT_<Nombre>.sp0, junto a la de los objetos).

Sirve para saber si un parametro lleva adentro un SDT dado y en que ruta: el parametro &outSet es de tipo
Generales\\Interfases\\Registro\\outSet, que tiene un campo Output de tipo Sistema\\Global\\sdtOutput.

En el .sp0 cada SDT (y cada nivel anidado) tiene un id, y sus campos dicen el id de su tipo:
    struct_dt_i([ 26,930,0 ],name,'Generales\\Interfases\\Registro\\outSet').
    struct_dt_elem_i([ 26,930,0 ],3,name,'Output').
    struct_dt_elem_i([ 26,930,0 ],3,type,[ [ 26,385,0 ],4,0 ]).      <- tipo SDT: el id va primero
    struct_dt_elem_i([ 26,930,0 ],3,collection,'False').
    struct_dt_i([ 26,385,0 ],name,'Sistema\\Global\\sdtOutput').     <- el nombre de los SDT que usa
"""
import threading
from pathlib import Path

from . import fuente, prolog

MAX_PROFUNDIDAD = 4  # SDT dentro de SDT

_cache = {}
_lock = threading.Lock()


class Estructura:
    def __init__(self):
        self.raiz = None
        self.nombres = {}    # id -> 'Modulo\\SDT' (el propio, sus niveles y los SDT que usa)
        self.campos = {}     # id -> [(nombre, id del tipo SDT o None, es coleccion)]


def _id(v):
    return tuple(v) if isinstance(v, list) else v


def leer(ruta) -> Estructura:
    ruta = Path(ruta)
    mt = ruta.stat().st_mtime_ns
    with _lock:
        previo = _cache.get(str(ruta))
        if previo and previo[0] == mt:
            return previo[1]
    with open(ruta, encoding="cp1252", errors="replace") as f:
        texto = f.read()
    est = Estructura()
    datos = {}  # (id, n) -> {name, type, collection}
    for nombre, c in prolog.clausulas(texto, ["spec_i", "struct_dt_i", "struct_dt_elem_i"]):
        a = c.args
        if nombre == "spec_i":
            est.raiz = _id(a[0][1])
        elif nombre == "struct_dt_i" and a[1] == "name":
            est.nombres[_id(a[0])] = str(a[2])
        elif nombre == "struct_dt_elem_i" and a[2] in ("name", "type", "collection"):
            datos.setdefault((_id(a[0]), a[1]), {})[a[2]] = a[3]
    for (sid, _n), d in sorted(datos.items()):
        tipo = d.get("type")
        ref = _id(tipo[0]) if isinstance(tipo, list) and tipo and isinstance(tipo[0], list) else None
        est.campos.setdefault(sid, []).append((str(d.get("name", "")), ref, d.get("collection") == "True"))
    with _lock:
        _cache[str(ruta)] = (mt, est)
    return est


def _ubicar(kb, tipo):
    partes = tipo.split("\\")
    return fuente.ubicar(kb, ".".join(partes[:-1] + ["GXSDT_" + partes[-1]]))


def _es(nombre, buscado):
    return nombre.split("\\")[-1].lower() == buscado.lower()


def rutas(kb, tipo, buscado, _prof=0):
    """Rutas dentro de un valor de tipo 'tipo' (Modulo\\...\\SDT) donde hay un SDT 'buscado' (ultimo tramo del
    nombre, sin distinguir mayusculas): '' si el tipo mismo lo es, 'Output', 'Items[*].Output'..."""
    if _es(tipo, buscado):
        return [""]
    if _prof >= MAX_PROFUNDIDAD or "\\" not in tipo:
        return []
    ruta = _ubicar(kb, tipo)
    if ruta is None:
        return []
    est = leer(ruta)
    return _en(kb, est, est.raiz, buscado, _prof)


def _en(kb, est, sid, buscado, prof):
    salida = []
    for nombre, ref, coleccion in est.campos.get(sid, []):
        if ref is None:
            continue
        campo = nombre + ("[*]" if coleccion else "")
        if ref in est.campos:  # nivel anidado del mismo SDT
            internas = _en(kb, est, ref, buscado, prof)
        elif ref in est.nombres:
            internas = rutas(kb, est.nombres[ref], buscado, prof + 1)
        else:
            internas = []
        salida += [campo + ("." + r if r else "") for r in internas]
    return salida
