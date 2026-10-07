"""Ayuda para completar la entrada de un objeto: que valores admite cada campo.

  dominios.py  campos de la entrada y su dominio, de la especificacion del objeto (valores de los enumerados)
  indice.py    tablas de la KB con su clave y su descriptor, y dominios enumerados, de las transacciones
  expresiones.py  ${existente.CuponId|...} y demas: valores de una clave calculados en la base al ejecutar

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


def _literal(v):
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).strip()
    return "'" + s.replace("\\", "\\\\").replace("'", "''") + "'"


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
    donde, usados = [], {}
    minus = {str(k).lower(): v for k, v in (filtros or {}).items()}
    for k in t.claves[:-1]:
        v = minus.get(k.lower())
        if _usable(v):
            donde.append(f"{k} = {_literal(v)}")
            usados[k] = v
    buscar = (buscar or "").strip()
    if buscar:
        patron = _literal("%" + re.sub(r"([%_])", r"\\\1", buscar) + "%")
        o = [f"CAST({t.claves[-1]} AS CHAR) LIKE {patron}"]
        if t.descripcion:
            o.append(f"{t.descripcion} LIKE {patron}")
        donde.append("(" + " OR ".join(o) + ")")
    q = f"select {', '.join(cols)} from {t.nombre}"
    if donde:
        q += " where " + " and ".join(donde)
    q += " order by " + ", ".join(t.claves)
    r, datos = motor.consulta_suelta(kb, "", q, maximo=maximo)
    if not r.get("ok"):
        raise motor.MotorError(r.get("error") or "No se pudieron leer los valores")
    return {**t.json(), "consulta": q, "filtros": usados, "columnas": datos.get("columnas", []),
            "filas": datos.get("filas", []), "truncado": datos.get("truncado", False),
            "dinamicas": [] if buscar else dinamicas(kb, t, filtros)}


def opciones_dinamicas(ix, t, filtros=None):
    """[(expresion, texto)] de las ${variables} que se ofrecen para la clave de 't' (ver expresiones.py). Los
    demas campos de la clave que esten en 'filtros' (CuponId para CuponCuotaSec) quedan como condicion, tambien
    si son una ${variable}: la expresion queda anidada y se calcula al ejecutar."""
    k = t.claves[-1]
    minus = {str(c).lower(): v for c, v in (filtros or {}).items()}
    padres = [(c, str(minus[c.lower()]).strip()) for c in t.claves[:-1]
              if minus.get(c.lower()) is not None and not isinstance(minus[c.lower()], (dict, list))
              and str(minus[c.lower()]).strip() not in ("", "0")]
    base = ",".join(f"{c}={v}" for c, v in padres)

    def expr(funcion, extra=""):
        conds = ",".join(x for x in (base, extra) if x)
        return f"${{{funcion}.{k}{'|' + conds if conds else ''}}}"
    ops = []
    if t.numerica:
        ops.append((f"${{siguiente.{k}}}", "no existe: el último + 1"))
    ops += [(expr("existente"), "el primero que existe"), (expr("ultimo"), "el último que existe")]
    hs = ix.hijas(t)
    if hs:
        nombres = ", ".join(h.nombre for h in hs)
        ops += [(expr("con_hijos"), f"con filas en {nombres}"), (expr("sin_hijos"), f"sin filas en {nombres}")]
    for col, dom in t.enumerados.items():
        for e in ix.valores.get(dom, []):
            desc = f" ({e['descripcion']})" if e.get("descripcion") and e["descripcion"] != e["nombre"] else ""
            ops.append((expr("existente", f"{col}={e['nombre']}"), f"{col} = {e['nombre']}{desc}"))
    return ops


def dinamicas(kb, t, filtros=None):
    """Las opciones de opciones_dinamicas() con el valor que darian hoy: [{valor, texto, hoy}] o, si no se
    puede calcular (no hay ninguna fila que cumpla), {valor, texto, error}."""
    ops = opciones_dinamicas(indice.de_kb(kb), t, filtros)
    salida = [{"valor": v, "texto": texto, **r} for (v, texto), r in zip(ops, previsualizar(kb, [v for v, _ in ops]))]
    # Las de un valor de dominio que hoy no tiene filas, al final (las de la clave quedan en su orden).
    return sorted(salida, key=lambda d: "error" in d and d["texto"].split(" = ")[0] in t.enumerados)


def previsualizar(kb, textos, variables=None):
    """Lo que daria hoy cada texto con ${variables}: [{hoy}] o [{error}]. Todas en una transaccion que se
    deshace, con las predefinidas, las fechas relativas y las de la base (y 'variables', si se pasan)."""
    from ..suites.variables import VariableIndefinida, mensaje_error, sustituir, variables_base  # suites importa campos
    salida = []
    # Las fechas no necesitan la base: sin funciones de la base, no se toma el motor (puede estar corriendo una suite).
    base = any(f"{f}." in str(e) for e in textos for f in expresiones.FUNCIONES)
    with motor.motor(kb).lock if base else contextlib.nullcontext():
        try:
            vars_ = variables_base({"variables": variables or {}}, None, {"id": "previsualizar"}, kb if base else None)
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
