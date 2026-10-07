"""Plan de ejecucion de las sentencias SQL de un objeto y recomendaciones.

  sentencias.py  SQL de los cursores del Java generado (tambien los dinamicos) y su lectura
  reglas.py      hallazgos: contra los indices de la base, del EXPLAIN de MySQL y de la navegacion GX

calcular() saca las sentencias del .java, lee de information_schema las filas y los indices de cada tabla, y
pide el EXPLAIN de cada sentencia. Los ? se reemplazan por valores de una fila real de la tabla: con un valor
que no existe, MySQL resuelve la clave al optimizar y no muestra el plan ("no matching row in const table").
Todo corre en el motor de la KB y termina con rollback (EXPLAIN no ejecuta la sentencia).
"""
import time

from .. import catalogo, motor
from . import reglas, sentencias

_NUMERICOS = {"tinyint", "smallint", "mediumint", "int", "integer", "bigint", "decimal", "numeric", "float",
              "double", "bit", "year"}
_FECHAS = {"date", "datetime", "timestamp"}


class SinFuente(ValueError):
    """El objeto no tiene el .java generado."""


def _in(nombres):
    return ", ".join(sentencias.literal(n.lower()) for n in sorted(nombres))


def _sql(kb, ds, q, timeout_ms):
    r, datos = motor.ejecutar_sql(kb, ds, q, timeout_ms, maximo=5000)
    if not r.get("ok"):
        raise motor.MotorError(r.get("error") or "Error de SQL")
    return datos.get("filas", [])


def _metadatos(kb, ds, tablas, timeout_ms):
    """{tabla en minusculas: {nombre, filas, indices: {nombre: {columnas, unico}}, columnas: {col: tipo}}}."""
    if not tablas:
        return {}
    meta = {}
    donde = f"TABLE_SCHEMA = database() AND LOWER(TABLE_NAME) IN ({_in(tablas)})"
    for f in _sql(kb, ds, f"select TABLE_NAME, TABLE_ROWS from information_schema.TABLES where {donde}", timeout_ms):
        meta[f["TABLE_NAME"].lower()] = {"nombre": f["TABLE_NAME"], "filas": reglas._n(f["TABLE_ROWS"]),
                                         "indices": {}, "columnas": {}}
    q = ("select TABLE_NAME, INDEX_NAME, NON_UNIQUE, COLUMN_NAME from information_schema.STATISTICS "
         f"where {donde} order by TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX")
    for f in _sql(kb, ds, q, timeout_ms):
        m = meta.get(f["TABLE_NAME"].lower())
        if m is not None:
            i = m["indices"].setdefault(f["INDEX_NAME"], {"columnas": [], "unico": str(f["NON_UNIQUE"]) == "0"})
            i["columnas"].append(f["COLUMN_NAME"])
    for f in _sql(kb, ds, f"select TABLE_NAME, COLUMN_NAME, DATA_TYPE from information_schema.COLUMNS where {donde}", timeout_ms):
        m = meta.get(f["TABLE_NAME"].lower())
        if m is not None:
            m["columnas"][f["COLUMN_NAME"].lower()] = (f["DATA_TYPE"] or "").lower()
    return meta


def _muestras(kb, ds, lista, meta, timeout_ms):
    """{columna en minusculas: valor} de una fila real de cada tabla, para las columnas que se comparan con ?.
    En GeneXus la columna es el atributo, y su nombre es unico en la KB: alcanza con el nombre."""
    pedidas = {}
    for s in lista:
        for parte in s.todas():
            for c in parte.condiciones:
                if c.valor == "?":
                    t = parte.tabla(c.alias)
                    if t and t.lower() in meta and c.columna.lower() in meta[t.lower()]["columnas"]:
                        pedidas.setdefault(t.lower(), set()).add(c.columna.lower())
    valores = {}
    for t, cols in pedidas.items():
        cols = sorted(cols - set(valores))
        if not cols:
            continue
        q = f"select {', '.join(f'`{c}`' for c in cols)} from `{meta[t]['nombre']}` limit 1"
        try:
            filas = _sql(kb, ds, q, timeout_ms)
        except motor.MotorError:
            continue
        for k, v in (filas[0] if filas else {}).items():
            if v is not None:
                valores.setdefault(k.lower(), v)
    return valores


def _valor(meta, muestras):
    tipos = {}
    for m in meta.values():
        for c, t in m["columnas"].items():
            tipos.setdefault(c, t)

    def valor(_alias, columna):
        c = columna.lower()
        if c in muestras:
            return sentencias.literal(muestras[c])
        t = tipos.get(c)
        if t in _NUMERICOS:
            return "1"
        if t in _FECHAS:
            return "'2000-01-01'"
        return "'a'" if t else None
    return valor


def calcular(kb, nombre, timeout_ms=60000):
    """{objeto, sentencias: [...], hallazgos: [...], tablas, resumen, avisos, ms}. Cada sentencia: cursor, ds,
    tipo, dinamica, sql, explicado (el SQL con los valores de prueba), plan (filas del EXPLAIN), error,
    hallazgos. Los hallazgos llevan cursor (o None si salen de la navegacion) y estan ordenados por nivel."""
    t0 = time.time()
    info = catalogo.buscar(kb, nombre)  # KeyError si no existe
    fuente = kb.fuente_java(info["nombre"])
    if not fuente.exists():
        raise SinFuente(f"No encuentro el Java generado de {info['nombre']} ({fuente.name}): hace Build en GeneXus.")
    lista = sentencias.de_java(fuente.read_text(encoding="utf-8", errors="ignore"))
    try:
        niveles = catalogo.detalle(info["nvg"])["niveles"]
    except Exception:
        niveles = []
    validos = {d["nombre"].upper() for d in kb.datasources}
    meta_total, salida, avisos = {}, [], []
    m = motor.motor(kb)
    with m.lock:
        try:
            for ds in sorted({s.ds for s in lista}):
                dsq = ds if ds.upper() in validos else ""
                del_ds = [s for s in lista if s.ds == ds]
                tablas = {t for s in del_ds for p in s.todas() for t in p.tablas.values() if not t.startswith("#")}
                try:
                    meta = _metadatos(kb, dsq, tablas, timeout_ms)
                    valor = _valor(meta, _muestras(kb, dsq, del_ds, meta, timeout_ms))
                except motor.MotorError as e:
                    avisos.append(f"No se pudieron leer los índices del datastore {ds or 'por defecto'}: {e}")
                    meta, valor = {}, (lambda a, c: None)
                meta_total.update(meta)
                for s in del_ds:
                    salida.append(_explicar(kb, dsq, s, meta, valor, timeout_ms))
        finally:
            motor.fin_transaccion(kb, "rollback")

    hallazgos = []
    for i, x in enumerate(salida):
        for h in x["hallazgos"]:
            hallazgos.append({**h, "cursor": x["cursor"], "sentencia": i})
    for h in reglas.anidadas(niveles, meta_total):
        hallazgos.append({**h, "cursor": None, "sentencia": None})
    hallazgos = reglas.ordenar(hallazgos)
    chicas = sorted(mt["nombre"] for mt in meta_total.values() if mt["filas"] is not None and mt["filas"] < reglas.POCAS)
    if chicas:
        avisos.append(f"En la base local {len(chicas)} de {len(meta_total)} tablas tienen menos de {reglas.POCAS} filas "
                      f"({', '.join(chicas[:8])}{'…' if len(chicas) > 8 else ''}): el plan de MySQL puede ser otro en "
                      "producción. Lo que sale de los índices no depende de los datos.")
    if any(s["dinamica"] for s in salida):
        avisos.append("Las consultas dinámicas se analizan con todos sus filtros opcionales puestos.")
    return {
        "objeto": info["nombre"], "fuenteJava": str(fuente),
        "sentencias": salida, "hallazgos": hallazgos,
        "tablas": {mt["nombre"]: {"filas": mt["filas"], "indices": mt["indices"]} for mt in meta_total.values()},
        "resumen": {n: sum(1 for h in hallazgos if h["nivel"] == n) for n in reglas.NIVELES},
        "avisos": avisos, "ms": round((time.time() - t0) * 1000),
    }


def _explicar(kb, ds, s, meta, valor, timeout_ms):
    x = {"cursor": s.cursor, "ds": s.ds, "tipo": s.tipo, "dinamica": s.dinamica, "sql": s.sql, "explicado": None,
         "tablas": sorted({t for p in s.todas() for t in p.tablas.values() if not t.startswith("#")}),
         "plan": [], "error": None, "hallazgos": []}
    previos = reglas.por_indices(s, meta)
    if s.tipo in ("select", "update", "delete") and x["tablas"]:
        x["explicado"] = sentencias.sustituir(s.sql, valor)
        try:
            x["plan"] = _sql(kb, ds, "EXPLAIN " + x["explicado"], timeout_ms)
        except motor.MotorError as e:
            x["error"] = str(e)
    nuevos = reglas.por_explain(s, x["plan"], meta, previos)
    x["hallazgos"] = reglas.ordenar([h for h in previos if not h.pop("descartar", False)] + nuevos)
    if any("const table" in str(f.get("Extra")) for f in x["plan"]):
        x["nota"] = ("Búsqueda por clave única: MySQL la resuelve antes de ejecutar y, como la tabla está vacía o no "
                     "tiene ese valor en la base local, no detalla el resto del plan.")
    return x
