"""Indice de la KB armado con la especificacion de las transacciones: las tablas con su clave y su atributo
descriptor, y los dominios enumerados de sus atributos.

Las tablas sirven para ofrecer los valores que existen en la base para un campo que es la clave de una tabla:
un campo ItfId se completa con 'select ItfId, ItfNombre from gntInterfase'.

    table_i(98,[ gntInterfase,[ 600,601,... ],gntInterfase,gntInterfase ]).
    index_i(98,[ 'IGNTINTERFASE',u,[ 600 ],'IgntInterfase' ]).                      <- clave primaria: I + tabla
    trn_level_i(98,[ [ 600,601,... ],'Generales\\Interfases\\gntInterfase','Interfases',...,'',601 ]).
                                                                                       ^ nivel de la transaccion y su descriptor
    attri_i(600,[ 'ItfId',int,6,0,'ZZZZZ9',0,'Interfase','',0 ]).

Un atributo identifica a la tabla de la que es el ultimo atributo de la clave: ItfId a gntInterfase (clave
ItfId), no a gntItfRegistro (clave ItfId, ItfRegTipo).

Los dominios completan lo que no trae la especificacion del objeto: un procedimiento que solo recibe un SDT
con un campo de un dominio enumerado tiene el id del dominio (basedon) pero no siempre sus valores. Los ids de
dominio son de la KB, los mismos en todos los .sp0.
"""
import threading
import time
from pathlib import Path

from .. import catalogo
from ..revisor import fuente, prolog
from .dominios import _literal

_PREDICADOS = ["attri_i", "table_i", "index_i", "trn_level_i", "enum_value_i", "enum_value_info_i", "dom_info_i"]
VIGENCIA_SEG = 30  # cada cuanto se mira si cambio alguna transaccion

_cache = {}    # ruta del .sp0 -> (mtime, Indice parcial)
_indices = {}  # kb -> (hora, firma, Indice)
_lock = threading.Lock()


class Tabla:
    def __init__(self, nombre, claves, descripcion, titulo):
        self.nombre = nombre            # gntInterfase
        self.claves = claves            # ['ItfId']
        self.descripcion = descripcion  # 'ItfNombre' o None
        self.titulo = titulo            # 'Interfases' (descripcion del nivel de la transaccion)

    def json(self):
        return {"tabla": self.nombre, "atributo": self.claves[-1], "claves": self.claves,
                "descripcion": self.descripcion, "titulo": self.titulo}


class Indice:
    def __init__(self):
        self.tablas = {}    # atributo en minusculas -> Tabla
        self.dominios = {}  # id -> 'Modulo\\Dominio'
        self.valores = {}   # id de dominio enumerado -> [{valor, nombre, descripcion}]

    def agregar_tabla(self, t):
        k = t.claves[-1].lower()
        # Si dos tablas terminan su clave en el mismo atributo (subtipos), la de clave mas corta.
        if k not in self.tablas or len(t.claves) < len(self.tablas[k].claves):
            self.tablas[k] = t

    def agregar(self, otro):
        for t in otro.tablas.values():
            self.agregar_tabla(t)
        for k, v in otro.dominios.items():
            self.dominios.setdefault(k, v)
        for k, v in otro.valores.items():
            self.valores.setdefault(k, v)


def armar(texto) -> Indice:
    """Indice de una transaccion (vacio si el .sp0 no es de una transaccion)."""
    nombres, tablas, indices, niveles = {}, {}, {}, []
    ix = Indice()
    for nombre, c in prolog.clausulas(texto, _PREDICADOS, saltear=("rule_i(0,datastore(",)):
        a = c.args
        if nombre == "attri_i" and isinstance(a[0], int):
            nombres[a[0]] = str(a[1][0])
        elif nombre == "table_i":
            tablas[a[0]] = str(a[1][0])
        elif nombre == "index_i" and len(a[1]) >= 3 and a[1][1] == "u":
            indices.setdefault(a[0], []).append((str(a[1][0]), a[1][2]))
        elif nombre == "trn_level_i":
            d = a[1]
            niveles.append((a[0], str(d[2]) if len(d) > 2 else "", d[-1] if isinstance(d[-1], int) else None))
        elif nombre == "enum_value_i" and len(a) >= 5:
            ix.valores.setdefault(a[1], []).append(
                {"valor": _literal(a[2]), "nombre": str(a[3]), "descripcion": str(_literal(a[4]))})
        elif nombre == "enum_value_info_i":
            ix.dominios[a[1]] = str(a[2])
        elif nombre == "dom_info_i" and isinstance(a[1], list) and a[1]:
            ix.dominios.setdefault(a[0], str(a[1][0]))
    for tid, titulo, desc in niveles:
        tabla = tablas.get(tid)
        if not tabla or not indices.get(tid):
            continue
        pk = next((ids for n, ids in indices[tid] if n.upper() == "I" + tabla.upper()), indices[tid][0][1])
        if not pk or not all(i in nombres for i in pk):
            continue
        descripcion = nombres.get(desc) if desc not in pk else None
        ix.agregar_tabla(Tabla(tabla, [nombres[i] for i in pk], descripcion, titulo))
    return ix


def _leer(ruta):
    ruta = Path(ruta)
    mt = ruta.stat().st_mtime_ns
    previo = _cache.get(str(ruta))
    if previo and previo[0] == mt:
        return previo[1]
    with open(ruta, encoding="cp1252", errors="replace") as f:
        ix = armar(f.read())
    _cache[str(ruta)] = (mt, ix)
    return ix


def de_kb(kb) -> Indice:
    """Indice de las transacciones de la KB. La primera vez lee la especificacion de todas (alrededor de un
    segundo); despues, solo las que cambiaron. Durante VIGENCIA_SEG no se vuelve a mirar."""
    with _lock:
        previo = _indices.get(kb.nombre)
        if previo and time.monotonic() - previo[0] < VIGENCIA_SEG:
            return previo[2]
        rutas = []
        for o in catalogo.objetos(kb):
            if o["tipo"] == "Transaction":
                r = fuente.ubicar(kb, o["nombre"])
                if r:
                    rutas.append(r)
        firma = tuple(sorted((str(r), r.stat().st_mtime_ns) for r in rutas))
        if previo and previo[1] == firma:
            _indices[kb.nombre] = (time.monotonic(), firma, previo[2])
            return previo[2]
        ix = Indice()
        for r in rutas:
            try:
                ix.agregar(_leer(r))
            except OSError:
                continue
        _indices[kb.nombre] = (time.monotonic(), firma, ix)
        return ix
