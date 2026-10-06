"""Clave de las transacciones, leida de su especificacion (<Modulo>/.../<Transaccion>.sp0).

Sirve para saber que atributos identifican a lo que graba un Business Component y cuales son autonumerados:

    spec_i([ trn,90,'Registros de Interfases','Generales\\Interfases\\gntItfRegistro',...]).
    attri_i(600,[ 'ItfId',int,6,0,'ZZZZZ9',0,'Interfase','',0 ]).
    att_prop_i(2,600,'AUTONUMBER','-1',d).                                  <- '-1' autonumerado, '0' no
    a_i(19,163,t,163,[],[ [ [ [],600,600 ],[ [],614,614 ] ],'IGNTITFREGISTRO',[] ]).   <- clave de la tabla 163

La clave es la de la tabla del primer nivel (la primera regla 't' de una tabla sobre si misma). Las lineas
datastore (datos de conexion) no se leen.
"""
import threading
from pathlib import Path

from . import fuente, prolog

_cache = {}
_lock = threading.Lock()


class Transaccion:
    def __init__(self, nombre):
        self.nombre = nombre        # Generales.Interfases.gntItfRegistro
        self.claves = []            # ['ItfId', 'ItfRegTipo']
        self.autonumeradas = set()  # {'ItfId'} si lo fuera


def leer(ruta):
    """Transaccion de un .sp0, o None si el objeto no es una transaccion o no se le encuentra la clave."""
    ruta = Path(ruta)
    mt = ruta.stat().st_mtime_ns
    with _lock:
        previo = _cache.get(str(ruta))
        if previo and previo[0] == mt:
            return previo[1]
    with open(ruta, encoding="cp1252", errors="replace") as f:
        texto = f.read()
    tr = _armar(texto)
    with _lock:
        _cache[str(ruta)] = (mt, tr)
    return tr


def _armar(texto):
    tr, nombres, auto, claves = None, {}, {}, None
    for nombre, c in prolog.clausulas(texto, ["spec_i", "attri_i", "att_prop_i", "a_i"], saltear=("rule_i(0,datastore(",)):
        a = c.args
        if nombre == "spec_i":
            if a[0][0] != "trn":
                return None
            tr = Transaccion(str(a[0][3]).replace("\\", "."))
        elif nombre == "attri_i" and isinstance(a[0], int):
            nombres[a[0]] = str(a[1][0])
        elif nombre == "att_prop_i" and len(a) >= 4 and a[2] == "AUTONUMBER":
            auto[a[1]] = a[3] == "-1"
        elif nombre == "a_i" and claves is None and len(a) >= 6 and a[2] == "t" and a[1] == a[3]:
            try:
                claves = [x[1] for x in a[5][0]]
            except (TypeError, IndexError):
                pass
    if tr is None or not claves:
        return None
    tr.claves = [nombres.get(x, str(x)) for x in claves]
    tr.autonumeradas = {nombres.get(x, str(x)) for x in claves if auto.get(x)}
    return tr


def de_tipo(kb, tipo):
    """La transaccion de un tipo de variable ('Generales\\Interfases\\gntItfRegistro'), o None si el tipo no es
    un Business Component de esta KB."""
    if "\\" not in tipo or "(" in tipo:
        return None
    ruta = fuente.ubicar(kb, tipo.replace("\\", "."))
    return leer(ruta) if ruta else None
