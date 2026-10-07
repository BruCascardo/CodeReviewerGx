"""Sentencias SQL de un objeto, sacadas del Java que genera GeneXus, y su lectura (tablas, filtros, orden).

Cada clase X__<datastore> del .java tiene los cursores con su SQL:

    final  class list__generales extends DataStoreHelperBase implements ILocalDataStoreHelper
       new ForEachCursor("P014U3", "SELECT `ItfId`, ... FROM `gntItfRegistro` WHERE `ItfId` = ? ORDER BY `ItfId`, `ItfRegTipo` ", ...)
       new UpdateCursor("P014U4", "DELETE FROM `gntItfRegistro`  WHERE `ItfId` = ? AND `ItfRegTipo` = ?", ...)
       public String getDataStoreName( ) { return "GENERALES"; }

Los cursores dinamicos (filtros opcionales) tienen "scmdbuf" en lugar del SQL: se arma con su metodo
conditional_<cursor>, poniendo todos los filtros opcionales (el peor caso para los indices es otro, pero asi
se ven todos los filtros que puede llegar a tener).
"""
import re
from dataclasses import dataclass, field

_CLASE = re.compile(r"final\s+class\s+(\w+)\s+extends\s+DataStoreHelperBase")
_CURSOR = re.compile(r'new\s+(ForEachCursor|UpdateCursor)\(\s*"(\w+)"\s*,\s*"((?:[^"\\]|\\.)*)"')
_DS = re.compile(r'getDataStoreName\s*\(\s*\)\s*\{\s*return\s+"(\w+)"')
_JSTR = r'"((?:[^"\\]|\\.)*)"'


def _java(s):
    return re.sub(r"\\(.)", r"\1", s)


@dataclass
class Condicion:
    alias: str           # T1, o '' si la sentencia no usa alias
    columna: str
    op: str              # =, <, >=, like, in, ...
    valor: str           # '?', 'T2.`ItfId`', una constante
    funcion: str = ""    # UPPER si la columna esta adentro de una funcion: UPPER(`Nombre`) = ?

    @property
    def es_join(self):
        return "`" in self.valor


@dataclass
class Sentencia:
    cursor: str
    ds: str
    sql: str
    tipo: str                      # select, update, delete, insert
    dinamica: bool = False
    tablas: dict = field(default_factory=dict)   # alias ('' si no hay) -> tabla
    condiciones: list = field(default_factory=list)
    orden: list = field(default_factory=list)    # [(alias, columna)]
    like_inicial: list = field(default_factory=list)  # columnas con like '%...'
    con_or: bool = False
    limite: str = ""               # '1', '?, ?', ''
    subconsultas: list = field(default_factory=list)  # [Sentencia] de los (SELECT ...) internos

    def tabla(self, alias):
        return self.tablas.get(alias) or (next(iter(self.tablas.values())) if len(self.tablas) == 1 else "")

    @property
    def principal(self):
        """La primera tabla del FROM (la que se recorre); '' si es una subconsulta."""
        t = next(iter(self.tablas.values()), "")
        return "" if t.startswith("#") else t

    def todas(self):
        """La sentencia y sus subconsultas (cada una con sus tablas, filtros y orden)."""
        yield self
        for sub in self.subconsultas:
            yield from sub.todas()


def de_java(texto):
    """Sentencias de un .java generado, en el orden de los cursores."""
    salida = []
    clases = list(_CLASE.finditer(texto))
    for i, m in enumerate(clases):
        cuerpo = texto[m.end(): clases[i + 1].start() if i + 1 < len(clases) else len(texto)]
        dm = _DS.search(cuerpo)
        ds = dm.group(1) if dm else ""
        for cm in _CURSOR.finditer(cuerpo):
            sql, dinamica = _java(cm.group(3)).strip(), False
            if sql == "scmdbuf":
                sql, dinamica = _dinamica(texto, cm.group(2)), True
                if not sql:
                    continue
            salida.append(leer(cm.group(2), ds, sql, dinamica))
    return salida


def _dinamica(texto, cursor):
    """SQL de un cursor dinamico, armado con su metodo conditional_<cursor> con todos los filtros."""
    m = re.search(r"Object\[\]\s+conditional_" + re.escape(cursor) + r"\s*\(", texto)
    if not m:
        return ""
    fin = texto.find("return GXv_Object", m.end())
    cuerpo = texto[m.end(): fin if fin > 0 else len(texto)]
    sel = re.search(r"sSelectString\s*=\s*" + _JSTR, cuerpo)
    frm = re.search(r"sFromString\s*=\s*" + _JSTR, cuerpo)
    if not sel or not frm:
        return ""
    wheres = []
    for w in re.finditer(r"addWhere\(\s*sWhereString\s*,\s*" + _JSTR, cuerpo):
        if _java(w.group(1)) not in wheres:
            wheres.append(_java(w.group(1)))
    orden = re.search(r"sOrderString\s*\+=\s*" + _JSTR, cuerpo)
    sql = "SELECT " + _java(sel.group(1)) + _java(frm.group(1))
    if wheres:
        sql += " WHERE " + " and ".join(wheres)
    if orden:
        sql += _java(orden.group(1))
    lim = re.search(r'scmdbuf\s*=.*?" LIMIT "\s*\+\s*"\?"(\s*\+\s*", "\s*\+\s*"\?")?', cuerpo)
    if lim:
        sql += " LIMIT ?, ?" if lim.group(1) else " LIMIT ?"
    return sql


# ---------------------------------------------------------------------- lectura del SQL

_COL = r"(?:(T\d+)\.)?`(\w+)`"
_OPS = r"(<>|!=|<=|>=|=|<|>|\blike\b|\bin\b)"
_VAL = r"(?:T\d+\.)?`\w+`|\?|'[^']*'|-?\d+(?:\.\d+)?|CONCAT\([^)]*\)|\([^)]*\)"
_COND = re.compile(r"(?:(\w+)\(\s*)?" + _COL + r"\s*\)?\s*" + _OPS + r"\s*(" + _VAL + ")", re.I)


def _clausula(sql, inicio, fin_palabras):
    m = re.search(inicio, sql, re.I)
    if not m:
        return ""
    resto = sql[m.end():]
    f = re.search(fin_palabras, resto, re.I)
    return resto[: f.start()] if f else resto


def _subconsultas(sql):
    """(sql con cada '(SELECT ...)' cambiado por `#subN`, [textos de las subconsultas])."""
    subs, salida, i = [], [], 0
    while True:
        j = sql.upper().find("(SELECT", i)
        if j < 0:
            salida.append(sql[i:])
            break
        nivel, k = 0, j
        while k < len(sql):
            nivel += {"(": 1, ")": -1}.get(sql[k], 0)
            if nivel == 0:
                break
            k += 1
        salida.append(sql[i:j] + f"`#sub{len(subs)}`")
        subs.append(sql[j + 1: k])
        i = k + 1
    return "".join(salida), subs


def leer(cursor, ds, sql, dinamica=False):
    tipo = sql.split(None, 1)[0].lower() if sql.strip() else ""
    s = Sentencia(cursor, ds, sql, tipo if tipo in ("select", "update", "delete", "insert") else "otro", dinamica)
    sql, subs = _subconsultas(sql)
    s.subconsultas = [leer(cursor, ds, x) for x in subs]
    if s.tipo == "insert":
        m = re.search(r"INSERT\s+INTO\s+`(\w+)`", sql, re.I)
        if m:
            s.tablas[""] = m.group(1)
        return s
    if s.tipo == "update":
        desde = _clausula(sql, r"^\s*UPDATE\b", r"\bSET\b")
    else:
        desde = _clausula(sql, r"\bFROM\b", r"\b(WHERE|ORDER\s+BY|GROUP\s+BY|LIMIT|FOR\s+UPDATE)\b")
    # Tablas: `nombre` [alias] que no vienen despues de un punto (T1.`col` es una columna del ON).
    for m in re.finditer(r"(?<![.\w])(?<!\w\()`(#?\w+)`(?:\s+(T\d+))?", desde):
        s.tablas.setdefault(m.group(2) or "", m.group(1))
    donde = _clausula(sql, r"\bWHERE\b", r"\b(ORDER\s+BY|GROUP\s+BY|LIMIT|FOR\s+UPDATE)\b")
    for texto in (donde, desde):  # las condiciones del WHERE y las del ON de los joins
        for m in _COND.finditer(texto):
            c = Condicion(m.group(2) or "", m.group(3), m.group(4).lower(), m.group(5).strip(), (m.group(1) or "").upper())
            s.condiciones.append(c)
            otra = re.fullmatch(_COL, c.valor) if c.op == "=" else None
            if otra:  # T2.`a` = T1.`b`: la relacion sirve a las dos tablas
                s.condiciones.append(Condicion(otra.group(1) or "", otra.group(2), "=", f"{c.alias}.`{c.columna}`"))
            if m.group(4).lower() == "like" and re.match(r"(CONCAT\(\s*'%'|'%)", m.group(5).strip(), re.I):
                s.like_inicial.append((m.group(2) or "", m.group(3)))
    s.con_or = bool(re.search(r"\bor\b", donde, re.I))
    orden = _clausula(sql, r"\bORDER\s+BY\b", r"\b(LIMIT|FOR\s+UPDATE)\b")
    s.orden = [(a or "", c) for a, c in re.findall(_COL, orden)]
    lim = re.search(r"\bLIMIT\s+([^)]+?)\s*(?:FOR\s+UPDATE)?\s*$", sql, re.I)
    s.limite = lim.group(1).strip() if lim else ""
    return s


# ---------------------------------------------------------------------- parametros

def sustituir(sql, valor):
    """SQL con cada ? reemplazado por un literal. valor(alias, columna) devuelve el literal para un ? que se
    compara con esa columna, o None (queda 1)."""
    partes, ult, en_limite = [], 0, 0
    for m in re.finditer(r"\?", sql):
        antes = sql[: m.start()]
        partes.append(sql[ult: m.start()])
        ult = m.end()
        if re.search(r"\bLIMIT\s*$", antes, re.I):
            # LIMIT ?, ? (desde, cantidad) o LIMIT ? (cantidad)
            en_limite = 1
            partes.append("0" if re.match(r"\s*,", sql[m.end():]) else "100")
            continue
        if en_limite:
            partes.append("100")
            continue
        c = re.search(_COL + r"\s*\)?\s*" + _OPS + r"\s*(?:CONCAT\([^?]*|\([^?]*)?$", antes, re.I)
        lit = valor(c.group(1) or "", c.group(2)) if c else None
        if c and re.search(r"CONCAT\([^?]*$", antes, re.I):
            lit = "'a'"  # like CONCAT('%', ?): cualquier texto
        partes.append(lit if lit is not None else "1")  # (? = 1): marca de filtro opcional activo
    partes.append(sql[ult:])
    return "".join(partes)


def literal(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"
