"""Ayuda para completar la entrada de un objeto: que valores admite cada campo.

  dominios.py  campos de la entrada y su dominio, de la especificacion del objeto (valores de los enumerados)
  indice.py    tablas de la KB con su clave y su descriptor, y dominios enumerados, de las transacciones
  expresiones.py  ${existente.CuponId|...} y demas: valores de una clave calculados en la base al ejecutar

filtros() describe lo que se puede elegir para armar una de esas ${variables} sin escribirla (el armador de
Explorar): que funcion, en que tabla hija y sobre que atributos poner condiciones.

de_objeto() dice, por ruta del campo, si es de un dominio enumerado (con sus valores) o si es la clave de una
tabla; valores() trae de la base los valores de esa clave, para elegirlos en un combo.
"""
import contextlib
import re

from .. import catalogo, motor
from ..revisor import fuente
from . import dominios, expresiones, indice

MAXIMO = 300  # filas que se traen para un combo de claves


def de_objeto(kb, nombre):
    """{ruta: ayuda} de los campos de la entrada que la tienen. La ruta va en minusculas y con [*] en las
    colecciones (inset.items[*].itfid). La ayuda es
        {"dominio": "Generales\\RegistroFin", "valores": [{valor, nombre, descripcion}]}   dominio enumerado
        {"dominio": "Generales\\Id", "clave": {tabla, atributo, claves, descripcion, titulo}}  clave de una tabla
        {"tipo": "date"} o {"tipo": "dtime"}                                                  fecha o fecha-hora
    """
    info = catalogo.buscar(kb, nombre)  # KeyError si no existe
    ruta = fuente.ubicar(kb, info["nombre"])
    if ruta is None:
        return {}
    es = dominios.leer(ruta)
    ix = indice.de_kb(kb)
    salida = {}
    for r, campo, dom, tipo in dominios.hojas(es, info["parametros"]):
        if tipo in ("date", "dtime"):
            salida[r] = {"tipo": tipo}
            continue
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


def _literal(v, mysql=True):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).strip()
    if mysql:  # solo MySQL escapa con \\
        s = s.replace("\\", "\\\\")
    return "'" + s.replace("'", "''") + "'"


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
    sel = [c if t.col(c) == c else f"{t.col(c)} as {c}" for c in cols]  # con el nombre del atributo
    lit = lambda v: _literal(v, t.dbms == indice.MYSQL)  # noqa: E731
    donde, usados = [], {}
    minus = {str(k).lower(): v for k, v in (filtros or {}).items()}
    for k in t.claves[:-1]:
        v = minus.get(k.lower())
        if _usable(v):
            donde.append(f"{t.col(k)} = {lit(v)}")
            usados[k] = v
    buscar = (buscar or "").strip()
    if buscar:
        patron = lit("%" + re.sub(r"([%_])", r"\\\1", buscar) + "%")
        o = [f"{t.como_texto(t.col(t.claves[-1]))} LIKE {patron}"]
        if t.descripcion:
            o.append(f"{t.col(t.descripcion)} LIKE {patron}")
        donde.append("(" + " OR ".join(o) + ")")
    q = f"select {', '.join(sel)} from {t.ref}"
    if donde:
        q += " where " + " and ".join(donde)
    q += " order by " + ", ".join(t.col(c) for c in t.claves)
    r, datos = motor.consulta_suelta(kb, t.datastore, q, maximo=maximo)
    if not r.get("ok"):
        raise motor.MotorError(r.get("error") or "No se pudieron leer los valores")
    return {**t.json(), "consulta": q, "filtros": usados, "columnas": datos.get("columnas", []),
            "filas": datos.get("filas", []), "truncado": datos.get("truncado", False)}


SALTOS = 3  # hasta cuantas tablas de distancia se ofrecen las relacionadas en el armador


def _atributos(ix, t, primero=None, claves=()):
    """[{nombre, tipo, clave, tablaDe, dominio, valores}] de los atributos de 't': 'primero' (si se pasa), los de
    'claves' (clave=True), los de un dominio enumerado (con sus 'valores') y el resto. 'tablaDe' es la tabla de la
    que el atributo es la clave (para ofrecer sus valores), o None."""
    claves = {c.lower() for c in claves}
    enums = {a.lower(): d for a, d in t.enumerados.items()}

    def att(nombre):
        dom = enums.get(nombre.lower())
        duena = ix.tablas.get(nombre.lower())
        a = {"nombre": nombre, "tipo": t.tipos.get(nombre, ""), "clave": nombre.lower() in claves,
             "tablaDe": duena.nombre if duena else None}
        if dom is not None:
            a["dominio"] = ix.dominios.get(dom, "")
            a["valores"] = ix.valores.get(dom, [])
        return a
    resto = [a for a in t.atributos if not primero or a.lower() != primero.lower()]
    orden = sorted(resto, key=lambda a: (a.lower() not in claves, a.lower() not in enums))
    return ([att(primero)] if primero else []) + [att(a) for a in orden]


def filtros(kb, atributo):
    """Lo que hace falta para armar una ${funcion.atributo|condiciones} eligiendo en vez de escribiendo:
        {tabla, atributo, titulo, numerica, hijas: [tabla], atributos: [...], relacionadas: [...]}
    'atributos' son los de la tabla sobre los que se puede poner una condicion (ver _atributos; clave=True en las
    demas partes de la clave). 'relacionadas' son las tablas sobre las que tambien se puede (ver
    expresiones.py), cada una por su camino mas corto: [{tabla, titulo, camino: [tabla], pasos: [hija|padre]}],
    las mas cercanas primero. Sus atributos se piden con atributos_de()."""
    ix = indice.de_kb(kb)
    t = ix.tablas.get((atributo or "").lower())
    if t is None:
        raise KeyError(f"{atributo} no es la clave de ninguna tabla de la KB {kb.nombre}")
    relacionadas = [{"tabla": c[-1][0].nombre, "titulo": c[-1][0].titulo, "camino": [p[0].nombre for p in c],
                     "pasos": ["hija" if p[2] else "padre" for p in c]}
                    for cs in ix.caminos(t, SALTOS).values() for c in cs]
    relacionadas.sort(key=lambda r: (len(r["camino"]), r["camino"]))
    return {**t.json(), "hijas": [h.nombre for h in ix.hijas(t)], "relacionadas": relacionadas,
            "atributos": _atributos(ix, t, t.claves[-1], t.claves[:-1])}


def atributos_de(kb, tabla, datastore=None):
    """Los atributos de una tabla de la KB, para poner condiciones sobre ella (ver _atributos). 'datastore': el de
    la tabla de la que se parte, si hay otra con el mismo nombre en otro datastore."""
    ix = indice.de_kb(kb)
    t = ix.tabla(tabla, datastore)
    if t is None:
        raise KeyError(f"{tabla} no es una tabla de la KB {kb.nombre}")
    return {**t.json(), "atributos": _atributos(ix, t, claves=t.claves)}


def misma_fila(kb, texto):
    """{atributo: ${variable}} de todas las partes de la clave, para que sean de la misma fila que cumple (ver
    expresiones.misma_fila). ValueError si no se puede."""
    return expresiones.misma_fila(indice.de_kb(kb), texto)


def completar(kb, texto, misma=False, hermanos=()):
    """Lo que el armador completa junto con la variable 'texto': {variables, relacionados}. 'variables' son las de
    todas las partes de la clave si 'misma' (ver misma_fila; si no, {}) y 'relacionados', los 'hermanos' (otros
    campos de la entrada) que salen de esa misma fila o de una tabla de sus condiciones (ver
    expresiones.relacionados): {CuponId: {tabla, expresion}}. ValueError si no se puede."""
    ix = indice.de_kb(kb)
    variables = expresiones.misma_fila(ix, texto) if misma else {}
    return {"variables": variables, "relacionados": expresiones.relacionados(ix, texto, variables, hermanos)}


def previsualizar(kb, textos, variables=None, sql_previo=None):
    """Lo que daria hoy cada texto con ${variables}: [{hoy}] o [{error}]. Todas en una transaccion que se
    deshace, con las predefinidas, las fechas relativas y las de la base (y 'variables', si se pasan). Con
    'sql_previo' ([{ds, sql}], el de Explorar), las de la base se calculan despues de correrlo, como al ejecutar."""
    from ..suites.script import bloques, correr_script  # suites importa campos
    from ..suites.variables import VariableIndefinida, mensaje_error, sustituir, variables_base
    salida = []
    # Las fechas no necesitan la base: sin funciones de la base, no se toma el motor (puede estar corriendo una suite).
    base = any(f"{f}." in str(e) for e in textos for f in expresiones.FUNCIONES)
    previo = bloques(sql_previo) if base else []
    with motor.motor(kb).lock if base else contextlib.nullcontext():
        try:
            vars_ = variables_base({"variables": variables or {}}, None, {"id": "previsualizar"}, kb if base else None)
            if previo:
                r = correr_script(kb, previo, vars_, 60000)
                if r["estado"] != "ok":
                    return [{"error": f"el SQL previo fallo: {r.get('error')}"} for _ in textos]
            for e in textos:
                try:
                    salida.append({"hoy": sustituir(e, vars_)})
                except VariableIndefinida as x:
                    salida.append({"error": x.motivo or mensaje_error(x)})
        finally:
            if base:
                motor.fin_transaccion(kb, "rollback")
    return salida


def siguiente(kb, atributo, en_transaccion=False):
    """El ultimo valor de la clave 'atributo' en su tabla, mas uno: uno que no existe (ver expresiones.py)."""
    return expresiones.resolver(kb, "siguiente", atributo, en_transaccion)
