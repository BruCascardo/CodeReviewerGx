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
import re
import threading
import time
from pathlib import Path

from .. import catalogo
from ..revisor import fuente, prolog
from .dominios import _literal

_PREDICADOS = ["attri_i", "map_i", "table_i", "index_i", "trn_level_i", "enum_value_i", "enum_value_info_i", "dom_info_i",
               "enumerated_i"]
VIGENCIA_SEG = 30  # cada cuanto se mira si cambio alguna transaccion

_cache = {}    # ruta del .sp0 -> (mtime, Indice parcial)
_indices = {}  # kb -> (hora, firma, Indice)
_lock = threading.Lock()


# Donde esta cada tabla. Cada tabla tiene un grupo de propiedades (fv,N) con su id, su datastore y, si es externa,
# su nombre fisico y su esquema:
#   rule_i(0,p(0,0,fv,428,[ table,509 ])).   rule_i(0,p(0,0,fv,428,[ datastore,11 ])).
#   rule_i(0,p(0,12,fv,428,[ 'NAME','CredSobrante' ])).   rule_i(0,p(0,12,fv,428,[ 'SCHEMA',dbo ])).
# Del datastore solo se leen el nombre y el motor (DBMS): las demas propiedades (la conexion) no se tocan.
_FV_TABLA = re.compile(r"rule_i\(0,p\(0,0,fv,(\d+),\[ table,(\d+) \]\)\)")
_FV_DS = re.compile(r"rule_i\(0,p\(0,0,fv,(\d+),\[ datastore,(\d+) \]\)\)")
_FV_PROP = re.compile(r"rule_i\(0,p\(0,12,fv,(\d+),\[ '(NAME|SCHEMA)',('?)([^'\]]*?)\3 \]\)\)")
_DS_NOMBRE = re.compile(r"rule_i\(0,datastore\((\d+),'NAME','([^']*)'\)\)")
_DS_DBMS = re.compile(r"rule_i\(0,datastore\((\d+),'DBMS',(\d+)\)\)")
DS_PRINCIPAL = "1"  # el datastore de la KB
MYSQL, SQLSERVER, DB2_ISERIES = "18", "12", "9"  # codigos de DBMS de GeneXus

NUMERICOS = {"int", "numeric"}  # tipos de la clave a los que se les puede calcular el siguiente (max + 1)


class Tabla:
    def __init__(self, nombre, claves, descripcion, titulo, tipo="", atributos=None, enumerados=None, tipos=None,
                 datastore="", columnas=None, dbms="", fisica="", esquema=""):
        self.nombre = nombre            # gntInterfase
        self.claves = claves            # ['ItfId']
        self.descripcion = descripcion  # 'ItfNombre' o None
        self.titulo = titulo            # 'Interfases' (descripcion del nivel de la transaccion)
        self.tipo = tipo                # tipo GX del ultimo atributo de la clave: 'int', 'char'...
        self.atributos = atributos or list(claves)  # todos los atributos de la tabla (con las claves foraneas)
        self.enumerados = enumerados or {}          # atributo -> id de su dominio enumerado
        self.tipos = tipos or {}                    # atributo -> tipo GX ('int', 'date'...)
        self.datastore = datastore                  # datasource de la tabla si no es el principal ('GAM'), o ""
        self.columnas = columnas or {}              # atributo -> columna fisica, solo las que se llaman distinto
        self.dbms = dbms or MYSQL                   # motor del datastore (codigo de GeneXus): el SQL se arma en su dialecto
        self.fisica = fisica                        # nombre de la tabla en la base, si es distinto (tablas externas)
        self.esquema = esquema                      # esquema de la tabla (dbo), o ""
        self._minus = None                          # atributos en minusculas (para tiene())

    def tiene(self, atributo):
        if self._minus is None:
            self._minus = {a.lower() for a in self.atributos}
        return atributo.lower() in self._minus

    def col(self, atributo):
        """La columna fisica del atributo, lista para el SQL de su motor (casi siempre se llama igual que el atributo:
        no en las tablas externas, como las de GAM o las de otro sistema)."""
        return self._id(self.columnas.get(self.atributo(atributo) or atributo, atributo))

    def _id(self, nombre):
        if self.dbms == SQLSERVER:
            return f"[{nombre}]"
        if self.dbms == MYSQL and not re.fullmatch(r"\w+", nombre):
            return f"`{nombre}`"
        return nombre  # DB2 de iSeries: T@RAMA va tal cual, como lo escribe GeneXus

    @property
    def ref(self):
        """La tabla en el FROM: con su esquema y su nombre fisico si los tiene (dbo.[CredSobrante])."""
        nombre = self._id(self.fisica or self.nombre) if self.dbms == SQLSERVER else (self.fisica or self.nombre)
        return f"{self.esquema}.{nombre}" if self.esquema else nombre

    def una_fila(self, select):
        """'select ... order by ...' para que traiga una sola fila, en el dialecto del motor."""
        if self.dbms == SQLSERVER:
            return "select top 1 " + select[len("select "):]
        if self.dbms == DB2_ISERIES:
            return select + " fetch first 1 rows only"
        return select + " limit 1"

    def como_texto(self, col):
        """CAST de una columna a texto (para buscar con LIKE)."""
        return f"CAST({col} AS CHAR)" if self.dbms == MYSQL else f"CAST({col} AS VARCHAR(200))"

    def atributo(self, nombre):
        """El nombre del atributo como esta en la tabla (CuponEstado para 'cuponestado'), o None."""
        return next((a for a in self.atributos if a.lower() == nombre.lower()), None)

    @property
    def numerica(self):
        return self.tipo in NUMERICOS

    def json(self):
        return {"tabla": self.nombre, "atributo": self.claves[-1], "claves": self.claves, "datastore": self.datastore,
                "descripcion": self.descripcion, "titulo": self.titulo, "numerica": self.numerica}


class Indice:
    def __init__(self):
        self.tablas = {}    # atributo en minusculas -> Tabla
        self.todas = {}     # nombre de la tabla en minusculas -> Tabla ("datastore:nombre" si el nombre se repite)
        self.dominios = {}  # id -> 'Modulo\\Dominio'
        self.valores = {}   # id de dominio enumerado -> [{valor, nombre, descripcion}]
        self._relaciones = {}  # nombre de la tabla en minusculas -> relaciones() (el indice no cambia una vez armado)

    def hijas(self, t):
        """Las tablas que tienen toda la clave de 't' entre sus atributos: los niveles subordinados y las que
        la referencian con una clave foranea (en GeneXus, un atributo con el mismo nombre)."""
        return [o for o, _, hija in self.relaciones(t) if hija]

    def relaciones(self, t):
        """[(Tabla, columnas por las que se unen, es_hija)] de las tablas relacionadas con 't': las hijas (tienen
        toda la clave de 't': su detalle, o una que la referencia) y las padres (toda su clave esta entre los
        atributos de 't': la que 't' referencia). Se une por la clave de la de arriba. Solo las del mismo datastore:
        con otro (GAM) no se puede unir en una consulta."""
        k = t.nombre.lower()
        if k not in self._relaciones:
            r = []
            for o in self.todas.values():
                if o.nombre.lower() == k or o.datastore.lower() != t.datastore.lower():
                    continue
                if all(o.tiene(c) for c in t.claves):
                    r.append((o, list(t.claves), True))
                elif all(t.tiene(c) for c in o.claves):
                    r.append((o, list(o.claves), False))
            self._relaciones[k] = r
        return self._relaciones[k]

    def caminos(self, t, saltos=3):
        """{nombre en minusculas: [caminos]} de las tablas a las que se llega desde 't' en hasta 'saltos' saltos,
        cada una solo por sus caminos mas cortos. Un camino es [(Tabla, columnas, es_hija)] desde la primera tabla
        despues de 't' (ver relaciones()).

        Despues de subir a una tabla por una clave foranea que no es parte de la clave (un catalogo: la moneda, la
        entidad financiera), no se baja a sus otras hijas: «cupones con la misma moneda que algun cargo» no sirve.
        Si se sube por la propia clave (de la cuota a su cargo), si: «cuotas de un cargo que tiene aplicaciones»."""
        salida, frontera, vistas = {}, [[]], {t.nombre.lower()}
        for _ in range(saltos):
            nuevos = {}
            for camino in frontera:
                desde = camino[-1][0] if camino else t
                previa = camino[-2][0] if len(camino) > 1 else t
                solo_arriba = bool(camino) and not camino[-1][2] and not all(c.lower() in {k.lower() for k in previa.claves}
                                                                         for c in camino[-1][1])
                en_camino = {x[0].nombre.lower() for x in camino}
                for paso in self.relaciones(desde):
                    n = paso[0].nombre.lower()
                    if solo_arriba and paso[2]:
                        continue
                    if n not in vistas and n not in en_camino:
                        nuevos.setdefault(n, []).append(camino + [paso])
            if not nuevos:
                break
            salida.update(nuevos)
            vistas.update(nuevos)
            frontera = [c for cs in nuevos.values() for c in cs]
        return salida

    def camino(self, t, nombres, saltos=4):
        """El camino [(Tabla, columnas, es_hija)] de 't' a la ultima tabla de 'nombres' ('cbhCuponDetalle',
        'cbhCupon'). Cada tabla tiene que estar relacionada con la anterior. Con una sola tabla que no esta
        relacionada con 't', el camino mas corto, si hay uno solo. ValueError si no hay o es ambiguo."""
        if len(nombres) == 1 and not any(o.nombre.lower() == nombres[0].lower() for o, _, _ in self.relaciones(t)):
            destino = self.tabla(nombres[0], t.datastore)
            if destino is None:
                raise ValueError(f"{nombres[0]} no es una tabla de la KB")
            cs = self.caminos(t, saltos).get(destino.nombre.lower())
            if not cs:
                raise ValueError(f"{destino.nombre} no esta relacionada con {t.nombre} (ni a {saltos} tablas de distancia)")
            if len(cs) > 1:
                opciones = " o ".join(".".join(p[0].nombre for p in c) for c in cs)
                raise ValueError(f"a {destino.nombre} se llega por mas de un camino: escribi {opciones}")
            return cs[0]
        camino, desde = [], t
        for n in nombres:
            paso = next((x for x in self.relaciones(desde) if x[0].nombre.lower() == n.lower()), None)
            if paso is None:
                raise ValueError(f"{n} no esta relacionada con {desde.nombre}"
                                 + ("" if self.tabla(n) else " (no es una tabla de la KB)"))
            camino.append(paso)
            desde = paso[0]
        return camino

    def tabla(self, nombre, datastore=None, atributo=None):
        """La tabla con ese nombre. Puede haber una con el mismo nombre en otro datastore (PAHEC11 para leer y para
        escribir): se elige la del 'datastore' y la que tiene el 'atributo', si se pasan. None si no hay."""
        candidatas = [t for t in self.todas.values() if t.nombre.lower() == (nombre or "").lower()]
        if datastore is not None:
            candidatas = [t for t in candidatas if t.datastore.lower() == datastore.lower()] or candidatas
        if atributo:
            candidatas = [t for t in candidatas if t.tiene(atributo)] or candidatas
        return candidatas[0] if candidatas else None

    def agregar_tabla(self, t):
        k = t.nombre.lower()
        if k in self.todas and self.todas[k].datastore.lower() != t.datastore.lower():
            k = f"{t.datastore}:{t.nombre}".lower()  # el mismo nombre en otro datastore: se guardan las dos
        self.todas.setdefault(k, t)
        k = t.claves[-1].lower()
        # Si dos tablas terminan su clave en el mismo atributo (subtipos), la de clave mas corta.
        if k not in self.tablas or len(t.claves) < len(self.tablas[k].claves):
            self.tablas[k] = t

    def agregar(self, otro):
        for t in otro.todas.values():
            self.agregar_tabla(t)
        for k, v in otro.dominios.items():
            self.dominios.setdefault(k, v)
        for k, v in otro.valores.items():
            self.valores.setdefault(k, v)


def armar(texto) -> Indice:
    """Indice de una transaccion (vacio si el .sp0 no es de una transaccion)."""
    nombres, tipos, tablas, atts, indices, niveles, enums, fisicas = {}, {}, {}, {}, {}, [], {}, {}
    ix = Indice()
    for nombre, c in prolog.clausulas(texto, _PREDICADOS, saltear=("rule_i(0,datastore(",)):
        a = c.args
        if nombre == "attri_i" and isinstance(a[0], int):
            nombres[a[0]] = str(a[1][0])
            tipos[a[0]] = str(a[1][1]) if len(a[1]) > 1 else ""
        elif nombre == "map_i" and len(a) >= 4 and a[1] == "a" and isinstance(a[3], list) and a[3]:
            fisicas.setdefault(a[0], {})[a[2]] = str(a[3][0])  # map_i(tabla,a,atributo,[ 'Columna' ])
        elif nombre == "table_i":
            tablas[a[0]] = str(a[1][0])
            atts[a[0]] = a[1][1] if len(a[1]) > 1 and isinstance(a[1][1], list) else []
        elif nombre == "enumerated_i" and len(a) >= 3 and isinstance(a[1], int):
            enums[a[1]] = a[2]
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
    ds_nombre, ds_dbms = dict(_DS_NOMBRE.findall(texto)), dict(_DS_DBMS.findall(texto))
    fv_tabla = {fv: int(t) for fv, t in _FV_TABLA.findall(texto)}
    fv_ds = dict(_FV_DS.findall(texto))
    ubicacion = {}  # id de tabla -> (datastore, dbms, nombre fisico, esquema)
    props = {}
    for fv, p, _, v in _FV_PROP.findall(texto):
        props.setdefault(fv, {})[p] = v
    for fv, tid in fv_tabla.items():
        d = fv_ds.get(fv, DS_PRINCIPAL)
        ubicacion[tid] = ("" if d == DS_PRINCIPAL else ds_nombre.get(d, ""), ds_dbms.get(d, ds_dbms.get(DS_PRINCIPAL, "")),
                          props.get(fv, {}).get("NAME", ""), props.get(fv, {}).get("SCHEMA", ""))
    for tid, titulo, desc in niveles:
        tabla = tablas.get(tid)
        if not tabla or not indices.get(tid):
            continue
        pk = next((ids for n, ids in indices[tid] if n.upper() == "I" + tabla.upper()), indices[tid][0][1])
        if not pk or not all(i in nombres for i in pk):
            continue
        descripcion = nombres.get(desc) if desc not in pk else None
        ids = [i for i in atts.get(tid, []) if i in nombres]
        ix.agregar_tabla(Tabla(tabla, [nombres[i] for i in pk], descripcion, titulo, tipos.get(pk[-1], ""),
                               [nombres[i] for i in ids] or None, {nombres[i]: enums[i] for i in ids if i in enums},
                               {nombres[i]: tipos.get(i, "") for i in ids}, ubicacion.get(tid, ("",))[0],
                               {nombres[i]: c for i, c in fisicas.get(tid, {}).items() if i in nombres and c != nombres[i]},
                               *ubicacion.get(tid, ("", "", "", ""))[1:]))
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
