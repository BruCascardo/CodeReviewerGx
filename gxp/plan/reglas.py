"""Recomendaciones sobre el plan de ejecucion de las sentencias de un objeto.

Hay dos fuentes, y cada hallazgo dice de cual sale:
  - los indices de la base (analisis del SQL contra information_schema): no dependen de cuantos datos haya;
  - el EXPLAIN de MySQL: dice lo que hace el optimizador con los datos de la base local, que pueden ser pocos.

Reglas (la clave va en cada hallazgo):
  sin-indice          ningun indice empieza por las columnas filtradas: recorre toda la tabla
  join-sin-indice     la tabla del join no tiene indice por las columnas de la relacion
  tabla-completa      SELECT sin filtros sobre una tabla grande
  orden-sin-indice    el ORDER BY no sale de un indice: ordena aparte (filesort)
  like-comodin        LIKE '%...': no puede usar indice
  funcion-columna     UPPER(`col`) = ...: la funcion sobre la columna impide usar el indice
  recorrido-completo  MySQL recorre la tabla aunque hay indices (type ALL)
  recorre-indice      MySQL recorre un indice entero (type index)
  poco-selectivo      lee muchas filas para quedarse con pocas (filtered bajo)
  tabla-temporal      usa una tabla temporal (GROUP BY, DISTINCT, orden de otra tabla)
  consulta-anidada    un For Each adentro de otro: una consulta por cada registro (N+1)

Niveles: alto, medio, bajo. Lo que sale de los indices tiene su nivel aunque la tabla tenga pocas filas en la
base local (en produccion puede tener muchas mas), y sube uno si ya tiene MUCHAS. Lo que solo dice el EXPLAIN
se muestra si lee al menos POCAS filas.
"""
NIVELES = ("alto", "medio", "bajo")
POCAS = 100
MUCHAS = 10000


def _n(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def nivel_por_filas(filas, base="medio"):
    """El nivel de la regla, un escalon mas alto si la tabla ya es grande en la base local. No baja con pocas
    filas: la base local suele tener muchos menos datos que produccion."""
    if filas is not None and filas >= MUCHAS and base != "alto":
        return NIVELES[NIVELES.index(base) - 1]
    return base


def _hallazgo(regla, nivel, tabla, titulo, detalle="", sugerencia="", origen="indices"):
    return {"regla": regla, "nivel": nivel, "tabla": tabla, "titulo": titulo, "detalle": detalle,
            "sugerencia": sugerencia, "origen": origen}


def _cols(lista):
    return ", ".join(lista)


def _filas_txt(filas):
    return f"~{filas:,} filas".replace(",", ".") if filas is not None else "una cantidad desconocida de filas"


# ---------------------------------------------------------------------- analisis contra los indices

def _condiciones_de(parte, alias):
    unica = len(parte.tablas) == 1
    return [c for c in parte.condiciones if c.alias == alias or (unica and not c.alias)]


def _prefijo_usable(indice, iguales, rangos):
    """Columnas del indice que sirven para buscar: las de '=' en cualquier orden y despues una de rango."""
    usadas = []
    for col in indice:
        if col in iguales:
            usadas.append(col)
            continue
        if col in rangos:
            usadas.append(col)
        break
    return usadas


def _sirve_para_ordenar(indice, iguales, orden):
    """True si recorrer el indice ya da el orden pedido (salteando las columnas fijadas con '=')."""
    resto = [c for c in orden if c not in iguales]
    if not resto:
        return True
    cols = list(indice)
    while cols and cols[0] in iguales:
        cols.pop(0)
    return cols[: len(resto)] == resto


def por_indices(sent, meta):
    """Hallazgos del SQL contra los indices de 'meta' ({tabla en minusculas: {filas, indices}})."""
    salida = []
    for parte in sent.todas():
        principal = next(iter(parte.tablas), None)
        for alias, tabla in parte.tablas.items():
            m = meta.get(tabla.lower()) if not tabla.startswith("#") else None
            if not m:
                continue
            salida += _tabla(parte, alias, tabla, m, alias == principal)
    return salida


def _tabla(parte, alias, tabla, m, es_principal):
    salida = []
    filas, indices = m.get("filas"), m.get("indices") or {}
    idx_cols = {n: [c.lower() for c in i["columnas"]] for n, i in indices.items()}
    conds = _condiciones_de(parte, alias)
    # La tabla de afuera no puede buscar por las columnas del join (todavia no tiene el valor de la otra).
    buscables = [c for c in conds if not c.funcion and (c.alias, c.columna) not in parte.like_inicial
                 and not (es_principal and c.es_join)]
    iguales = {c.columna.lower() for c in buscables if c.op in ("=", "in")}
    rangos = {c.columna.lower() for c in buscables if c.op in ("<", ">", "<=", ">=", "<>", "!=", "like")}
    filtros = sorted({c.columna for c in buscables}, key=str.lower)
    mejor = max((_prefijo_usable(cols, iguales, rangos) for cols in idx_cols.values()), key=len, default=[])
    base = "alto" if parte.tipo in ("update", "delete") else "medio"
    accion = {"update": "El UPDATE", "delete": "El DELETE"}.get(parte.tipo, "La consulta")
    lista_idx = "; ".join(f"{n} ({_cols(i['columnas'])})" for n, i in indices.items())

    if filtros and not mejor:
        joins = sorted({c.columna for c in buscables if c.es_join}, key=str.lower)
        if joins and not es_principal:
            salida.append(_hallazgo(
                "join-sin-indice", nivel_por_filas(filas, "alto"), tabla,
                f"El join con {tabla} no tiene índice por {_cols(joins)}",
                f"Por cada fila de la tabla de afuera recorre {tabla} ({_filas_txt(filas)} en la base local). "
                + (f"Índices: {lista_idx}." if indices else "La tabla no tiene índices."),
                f"Agregá un índice en la transacción de {tabla} sobre ({_cols(joins)})."))
        else:
            salida.append(_hallazgo(
                "sin-indice", nivel_por_filas(filas, base), tabla,
                f"Ningún índice de {tabla} sirve para filtrar por {_cols(filtros)}: recorre toda la tabla",
                f"{accion} lee todas las filas de {tabla} ({_filas_txt(filas)} en la base local) y descarta las que no cumplen. "
                + (f"Índices: {lista_idx}." if indices else "La tabla no tiene índices."),
                f"Agregá un índice de usuario en la transacción de {tabla} que empiece por "
                f"{_cols(_sugerido(buscables))}, o filtrá por los atributos de un índice que ya exista."))
    elif not conds and es_principal and parte.tipo == "select" and parte.limite.strip() != "1" \
            and filas is not None and filas >= POCAS * 10:
        salida.append(_hallazgo(
            "tabla-completa", nivel_por_filas(filas, "medio"), tabla,
            f"Lee toda la tabla {tabla} sin filtros",
            f"La consulta no tiene WHERE: trae toda la tabla ({_filas_txt(filas)} en la base local).",
            "Si no hacen falta todas, filtrá en el For Each por atributos de un índice."))

    for a, col in parte.like_inicial:
        if a == alias or (not a and len(parte.tablas) == 1):
            salida.append(_hallazgo(
                "like-comodin", nivel_por_filas(filas, "bajo"), tabla,
                f"LIKE que empieza con % sobre {col}: no puede usar índice",
                f"Buscar «contiene» obliga a revisar cada fila de {tabla} ({_filas_txt(filas)} en la base local).",
                "Si alcanza con «empieza con», usá like '&texto%' (sin % adelante): ahí sí sirve un índice."))
    for c in conds:
        if c.funcion:
            salida.append(_hallazgo(
                "funcion-columna", nivel_por_filas(filas, "medio"), tabla,
                f"{c.funcion}({c.columna}) en el filtro: la función impide usar el índice",
                f"MySQL tiene que calcular {c.funcion}() en cada fila de {tabla}.",
                "Compará la columna sin transformarla (guardá el dato normalizado o usá una collation "
                "que no distinga mayúsculas)."))

    if es_principal and parte.orden and indices:
        orden = [col.lower() for a, col in parte.orden if a == alias or (not a and len(parte.tablas) == 1)]
        if len(orden) == len(parte.orden) and \
                not any(_sirve_para_ordenar(cols, iguales, orden) for cols in idx_cols.values()):
            # Si el filtro usa un indice, se ordenan solo las filas que cumplen: suele ser poco.
            salida.append(_hallazgo(
                "orden-sin-indice", "bajo" if mejor else nivel_por_filas(filas, "medio"), tabla,
                f"Ningún índice de {tabla} da el orden {_cols(c for _, c in parte.orden)}",
                "MySQL tiene que leer todas las filas que cumplen el filtro y ordenarlas antes de devolver "
                "la primera (filesort).",
                f"Usá en el For Each un order que coincida con un índice, o agregá un índice sobre "
                f"({_cols(c for _, c in parte.orden)})."))
    return salida


def _sugerido(conds):
    """Columnas para un indice nuevo: primero las de '=', despues las de rango."""
    vistos, salida = set(), []
    for c in sorted(conds, key=lambda c: c.op not in ("=", "in")):
        if c.columna.lower() not in vistos:
            vistos.add(c.columna.lower())
            salida.append(c.columna)
    return salida


# ---------------------------------------------------------------------- EXPLAIN

def por_explain(sent, plan, meta, previos):
    """Hallazgos del EXPLAIN (filas de la consulta 'explain ...'). 'previos' son los del analisis de indices
    de la misma sentencia: si ya dicen lo mismo, se les agrega el dato de MySQL en lugar de repetir."""
    salida = []
    alias_tabla = {}
    for parte in sent.todas():
        alias_tabla.update({a: t for a, t in parte.tablas.items() if a and not t.startswith("#")})
    for fila in plan or []:
        t = fila.get("table") or ""
        if not t or t.startswith("<"):
            continue
        tabla = alias_tabla.get(t, t)
        filas_tabla = (meta.get(tabla.lower()) or {}).get("filas")
        leidas = _n(fila.get("rows"))
        filtrado = _n(fila.get("filtered"))
        extra = fila.get("Extra") or ""
        tipo = (fila.get("type") or "").upper()
        posibles = fila.get("possible_keys")
        ya = {h["regla"] for h in previos if h["tabla"] == tabla}
        # MySQL encontro como usar un indice: lo que dijo el analisis de indices sobre el filtro no corre.
        if tipo in ("CONST", "EQ_REF", "REF", "RANGE", "REF_OR_NULL", "INDEX_MERGE", "SYSTEM") and fila.get("key"):
            for h in previos:
                if h["tabla"] == tabla and h["regla"] in ("sin-indice", "join-sin-indice"):
                    h["descartar"] = True

        def sumar(regla, texto):
            for h in previos:
                if h["tabla"] == tabla and h["regla"] == regla:
                    h["detalle"] += " " + texto
                    h["origen"] = "indices+explain"
                    return True
            return False

        if tipo == "ALL" and (leidas or 0) >= POCAS or tipo == "ALL" and ya & {"sin-indice", "join-sin-indice", "tabla-completa"}:
            texto = f"MySQL lo confirma: recorre {tabla} ({_filas_txt(leidas)} estimadas)."
            if not (sumar("sin-indice", texto) or sumar("join-sin-indice", texto) or sumar("tabla-completa", texto)
                    or "like-comodin" in ya or "funcion-columna" in ya):
                salida.append(_hallazgo(
                    "recorrido-completo", "bajo" if posibles else nivel_por_filas(filas_tabla, "medio"), tabla,
                    f"MySQL recorre toda la tabla {tabla}",
                    f"Lee {_filas_txt(leidas)}." + (
                        f" Tiene índices que podría usar ({posibles}) pero no le conviene con los datos de la base "
                        "local: con más datos puede cambiar." if posibles else ""),
                    "" if posibles else "Revisá los filtros del For Each: ninguno llega a un índice.",
                    origen="explain"))
        elif tipo == "INDEX" and leidas is not None and leidas >= POCAS and not (sumar("tabla-completa", f"MySQL recorre el índice {fila.get('key')} entero.")
                                      or sumar("sin-indice", f"MySQL recorre el índice {fila.get('key')} entero.")):
            salida.append(_hallazgo(
                "recorre-indice", nivel_por_filas(filas_tabla, "bajo"), tabla,
                f"MySQL recorre el índice {fila.get('key')} de {tabla} entero",
                f"Lee {_filas_txt(leidas)} en el orden del índice (suele ser para dar el ORDER BY sin filtrar).",
                "Si hay filtros, que empiecen por las columnas del índice.", origen="explain"))
        if "Using filesort" in extra and not sumar("orden-sin-indice", "MySQL lo confirma (Using filesort).") \
                and leidas is not None and leidas >= POCAS:
            salida.append(_hallazgo(
                "orden-sin-indice", nivel_por_filas(leidas, "bajo"), tabla,
                f"MySQL ordena las filas de {tabla} aparte (filesort)",
                f"Ordena {_filas_txt(leidas)} después de leerlas.", "Que el order del For Each coincida con el índice que "
                "usa el filtro.", origen="explain"))
        if "Using temporary" in extra and leidas is not None and leidas >= POCAS:
            salida.append(_hallazgo(
                "tabla-temporal", nivel_por_filas(leidas, "bajo"), tabla,
                f"MySQL arma una tabla temporal para {tabla}",
                "Pasa con GROUP BY, DISTINCT, fórmulas de agregación o un orden por columnas de otra tabla.",
                "Si es una fórmula (sum, count), mirá si la tabla tiene índice por las columnas que la relacionan.",
                origen="explain"))
        if "Using join buffer" in extra and not sumar("join-sin-indice", "MySQL lo confirma (Using join buffer)."):
            salida.append(_hallazgo(
                "join-sin-indice", nivel_por_filas(filas_tabla, "alto"), tabla,
                f"MySQL junta {tabla} sin índice (join buffer)",
                f"Por cada fila de la otra tabla recorre {tabla}.", f"Agregá un índice en {tabla} por las columnas del join.",
                origen="explain"))
        if tipo not in ("ALL", "INDEX") and leidas is not None and filtrado is not None and leidas >= 1000 and filtrado <= 10:
            salida.append(_hallazgo(
                "poco-selectivo", "medio", tabla,
                f"Lee {_filas_txt(leidas)} de {tabla} para quedarse con ~{filtrado}%",
                f"Usa el índice {fila.get('key')}, pero después descarta casi todo con filtros que no están en el índice.",
                "Agregá al índice las columnas del filtro que descarta (o un índice nuevo con todas).",
                origen="explain"))
    return salida


# ---------------------------------------------------------------------- navegacion GX

def anidadas(niveles, meta):
    """For Each adentro de otro For Each (sobre otra tabla): una consulta por cada registro de afuera."""
    salida = []

    def recorrer(n):
        for sub in n.get("subniveles") or []:
            if sub.get("tabla") and n.get("tabla") and sub["tabla"].lower() != n["tabla"].lower():
                filas = (meta.get(n["tabla"].lower()) or {}).get("filas")
                nivel = "medio" if filas is not None and filas >= MUCHAS else "bajo"
                salida.append(_hallazgo(
                    "consulta-anidada", nivel, sub["tabla"],
                    f"Por cada registro de {n['tabla']} (línea {n.get('linea')}) se consulta {sub['tabla']} "
                    f"(línea {sub.get('linea')})",
                    f"{n.get('tipo') or 'For Each'} con un {sub.get('tipo') or 'For Each'} adentro: son 1 + N consultas "
                    f"({n['tabla']}: {_filas_txt(filas)} en la base local).",
                    "Es lo normal para recorrer un detalle; si el de adentro solo trae un dato, puede ir en el mismo "
                    "For Each (tabla extendida) o en una fórmula.", origen="navegacion"))
            recorrer(sub)

    for n in niveles or []:
        recorrer(n)
    return salida


def ordenar(hallazgos):
    return sorted(hallazgos, key=lambda h: NIVELES.index(h["nivel"]))
