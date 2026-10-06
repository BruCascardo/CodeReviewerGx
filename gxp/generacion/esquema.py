"""Entradas con datos reales para la generacion de suites.

Los campos de la entrada de un objeto (la plantilla de 'describir') se buscan por nombre entre las columnas de
las bases de la KB (information_schema) y se completan con una fila real de la tabla que mas campos cubre.
"""
import json

from ..motor import MotorError, ejecutar_sql

# Nombres de campo que estan en muchas tablas: solos no alcanzan para elegir de que tabla sacar los datos.
GENERICOS = {"id", "tipo", "nombre", "codigo", "descripcion", "fecha", "estado", "orden", "valor", "texto", "activo",
             "usuario", "cantidad", "pagina", "page", "pagesize", "importe", "numero", "clave", "modo", "mode"}
DS_EXCLUIDOS = {"GAM", "GXOFFLINESTORE"}


class Esquema:
    """Columnas de las bases de la KB, para buscar valores reales de los campos de entrada."""

    def __init__(self, kb):
        self.kb = kb
        self.tablas = {}   # (ds, tabla) -> {"cols": {col_lower: (col, tipo)}, "pk": [col]}
        self.por_col = {}  # col_lower -> [(ds, tabla)]
        for d in kb.datasources:
            if d["nombre"].upper() in DS_EXCLUIDOS:
                continue
            try:
                r, datos = ejecutar_sql(kb, d["nombre"], "select table_name as t, column_name as c, column_key as k, "
                                               "data_type as d from information_schema.columns where table_schema = database() "
                                               "order by table_name, ordinal_position", 30000, 200000)
            except MotorError:
                continue
            for f in datos.get("filas") or []:
                t = self.tablas.setdefault((d["nombre"], f["t"]), {"cols": {}, "pk": []})
                t["cols"][f["c"].lower()] = (f["c"], (f["d"] or "").lower())
                if f["k"] == "PRI":
                    t["pk"].append(f["c"])
                self.por_col.setdefault(f["c"].lower(), []).append((d["nombre"], f["t"]))
        self._filas = {}

    def _coincide(self, tabla, campo):
        """(columna, peso) de la tabla para un campo de entrada, o None."""
        c = campo.lower()
        cols = self.tablas[tabla]["cols"]
        if c in cols:
            return cols[c][0], (0.5 if c in GENERICOS else 3)
        if len(c) >= 5 and c not in GENERICOS:
            fin = [v[0] for k, v in cols.items() if k.endswith(c)]
            if len(fin) == 1:
                return fin[0], 1
        return None

    def valores(self, campos):
        """Para una lista de nombres de campo: (origen, {campo: valor}) de una fila real, o (None, {})."""
        posibles = set()
        for c in {c.lower() for c in campos}:
            posibles.update(self.por_col.get(c, []))
            if len(c) >= 5 and c not in GENERICOS:
                posibles.update(t for k, ts in self.por_col.items() if k.endswith(c) for t in ts)
        orden = []
        for t in posibles:
            m = {c: self._coincide(t, c) for c in set(campos)}
            m = {c: v for c, v in m.items() if v}
            puntaje = sum(v[1] for v in m.values())
            if puntaje < 1:
                continue
            pk = self.tablas[t]["pk"]
            cubre_pk = bool(pk) and all(any(v[0] == p for v in m.values()) for p in pk)
            orden.append(((puntaje, cubre_pk, -len(self.tablas[t]["cols"]), t), t, m))
        # La mejor tabla puede estar vacia en la base local: se prueba con las siguientes.
        for _, (ds, tabla), m in sorted(orden, reverse=True)[:6]:
            cols = sorted({v[0] for v in m.values()})
            fila = self._fila(ds, tabla, tuple(cols))
            if fila:
                return f"{ds}.{tabla}", {c: (fila.get(v[0]), self.tablas[(ds, tabla)]["cols"][v[0].lower()][1]) for c, v in m.items()}
        return None, {}

    def _fila(self, ds, tabla, cols):
        clave = (ds, tabla, cols)
        if clave in self._filas:
            return self._filas[clave]
        info = self.tablas[(ds, tabla)]
        conds = []
        for c in cols:
            tipo = info["cols"][c.lower()][1]
            # Ni nulos ni el valor por defecto de la plantilla (0, ''): esa ya es la entrada vacia.
            if "char" in tipo or "text" in tipo:
                extra = f" and trim(`{c}`) <> ''"
            elif tipo in ("int", "bigint", "smallint", "tinyint", "mediumint", "decimal", "double", "float", "numeric"):
                extra = f" and `{c}` <> 0"
            else:
                extra = ""
            conds.append(f"`{c}` is not null" + extra)
        orden = ", ".join(f"`{c}`" for c in (info["pk"] or cols))
        sel = ", ".join(f"`{c}`" for c in cols)
        fila = None
        for where in (" where " + " and ".join(conds), ""):
            try:
                _, d = ejecutar_sql(self.kb, ds, f"select {sel} from `{tabla}`{where} order by {orden} limit 1", 30000, 1)
            except MotorError:
                break
            if d.get("filas"):
                fila = d["filas"][0]
                break
        self._filas[clave] = fila
        return fila


def _hojas(v, ruta=()):
    if isinstance(v, dict):
        for k, x in v.items():
            yield from _hojas(x, ruta + (k,))
    elif isinstance(v, list):
        if v:
            yield from _hojas(v[0], ruta + (0,))
    else:
        yield ruta, v


def _poner(obj, ruta, valor):
    for k in ruta[:-1]:
        obj = obj[k]
    obj[ruta[-1]] = valor


def _convertir(valor, defecto, tipo_db):
    """Valor de la base con el tipo de la plantilla, o None si no se puede."""
    if valor is None:
        return None
    if isinstance(defecto, bool):
        if isinstance(valor, bool):
            return valor
        return str(valor).strip() in ("1", "true", "True", "S", "Y") if str(valor).strip() else None
    if isinstance(defecto, (int, float)):
        try:
            n = float(valor)
        except (TypeError, ValueError):
            return None
        return int(n) if n.is_integer() else n
    if isinstance(defecto, str):
        s = str(valor)
        if tipo_db in ("date",):
            return s[:10]
        if tipo_db in ("datetime", "timestamp"):
            return s[:19].replace(" ", "T")
        return s.rstrip()
    return None


def entrada_real(esquema, plantilla):
    """(origen, entrada) con los campos completados desde la base, o (None, None) si no se encontro nada."""
    hojas = [(r, v) for r, v in _hojas(plantilla) if isinstance(r[-1], str) and not isinstance(v, (dict, list))]
    nombres = [r[-1] for r, _ in hojas]
    if not nombres:
        return None, None
    origen, vals = esquema.valores(nombres)
    if not vals:
        return None, None
    entrada = json.loads(json.dumps(plantilla))
    puestos = 0
    for r, v in hojas:
        par = vals.get(r[-1])
        if not par:
            continue
        nuevo = _convertir(par[0], v, par[1])
        if nuevo is not None and nuevo != v:
            _poner(entrada, r, nuevo)
            puestos += 1
    return (origen, entrada) if puestos else (None, None)
