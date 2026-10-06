"""Ejecucion de pasos y casos contra el motor de la KB.

Un caso corre una vez por fila de 'datos', con el motor tomado en exclusiva y dentro de una transaccion que
al final se deshace (o se confirma, si el caso o la suite dicen "transaccion": "commit"). Cada paso ejecuta un
objeto o una consulta SQL y despues se controla, en este orden: el error esperado, lo 'esperado', las
'verificaciones' y la salida aprobada ('lineaBase').
"""
import re
import time

from .variables import VariableIndefinida, sustituir, variables_base
from .. import catalogo
from ..comparacion import Opciones, aprobada, clave, obtener, parcial, resumir, sugerir, verificar
from ..config import CFG
from ..efectos import efectos_actuales, separar
from ..motor import MotorError, ejecutar_objeto, ejecutar_sql, fin_transaccion, motor
from ..util import slug

MAX_DIFERENCIAS = 200  # en el resultado; el resumen las cuenta todas


def nombre_paso(paso):
    return paso.get("nombre") or paso.get("objeto") or "SQL"


def linea_base_de(paso, fila_idx):
    """La salida aprobada del paso (con 'datos', la de esa fila)."""
    lb = paso.get("lineaBase")
    if fila_idx is None:
        return lb
    if isinstance(lb, list):
        return lb[fila_idx] if fila_idx < len(lb) else None
    return None


def _paso_omitido(paso):
    return {"nombre": nombre_paso(paso), "estado": "omitido", "verificaciones": [], "diferencias": [], "advertencias": []}


# ---------------------------------------------------------------------- un paso

def _ejecutar(kb, paso, vars_, opciones, res):
    """Corre el objeto o la consulta del paso. Devuelve (respuesta del motor, datos)."""
    if paso.get("objeto"):
        entrada = sustituir(paso.get("entrada") or {}, vars_)
        res.update({"tipo": "objeto", "objeto": paso["objeto"], "entrada": entrada})
        r, datos, info = ejecutar_objeto(kb, sustituir(paso["objeto"], vars_), entrada, opciones.get("timeoutMs"))
        res["objeto"] = info["nombre"]
        if opciones.get("transaccion", "rollback") == "rollback" and catalogo.hace_commit(kb, info["nombre"]):
            res["advertencias"].append(f"{info['nombre']} hace commit por su cuenta: sus cambios NO se deshacen con el rollback.")
        return r, datos
    if paso.get("sql"):
        q = sustituir(paso["sql"], vars_)
        res.update({"tipo": "sql", "sql": q, "ds": paso.get("ds", "")})
        return ejecutar_sql(kb, sustituir(paso.get("ds", ""), vars_), q, opciones.get("timeoutMs"), paso.get("max", 1000))
    raise ValueError("El paso no tiene 'objeto' ni 'sql'")


def _error_esperado(paso, r, res):
    """El paso tenia que terminar con una excepcion (opcionalmente, con cierto texto)."""
    if r.get("ok"):
        res["estado"] = "falla"
        res["diferencias"].append({"ruta": "$", "tipo": "error", "esperado": "una excepcion", "obtenido": "termino bien",
                                   "mensaje": "se esperaba que fallara"})
        return
    txt = (paso.get("errorContiene") or "").strip()
    if txt and txt.lower() not in (res.get("error", "") + res.get("excepcion", "")).lower():
        res["estado"] = "falla"
        res["diferencias"].append({"ruta": "$", "tipo": "error", "esperado": txt, "obtenido": res.get("error"),
                                   "mensaje": "el error no contiene el texto esperado"})
    res["errorEsperado"] = True


def _verificaciones(paso, datos, vars_, opts, res):
    """'esperado' (coincidencia parcial) y 'verificaciones'. Una verificacion mal escrita (regex invalida,
    'largo' no numerico) falla sola, sin cortar la corrida."""
    if paso.get("esperado") not in (None, {}, []):
        parcial(sustituir(paso["esperado"], vars_), datos, "", opts, res["diferencias"])
    for v in paso.get("verificaciones") or []:
        v = sustituir(v, vars_)
        try:
            res["verificaciones"].append(verificar(datos, v, opts))
        except (ValueError, TypeError, re.error) as e:
            res["verificaciones"].append({"ruta": v.get("ruta", ""), "op": v.get("op", ""), "valor": v.get("valor"),
                                          "cada": bool(v.get("cada")), "obtenido": None, "ok": False,
                                          "mensaje": f"verificacion invalida: {e}", "descripcion": v.get("descripcion", "")})


def _linea_base(paso, fila_idx, datos, opts, res, grabar):
    if grabar:
        res["lineaBaseGrabada"] = True
        return
    lb = linea_base_de(paso, fila_idx)
    if lb is None:
        return
    modo = paso.get("comparar") or "todo"
    d, avisos = aprobada(lb, datos, opts, modo)
    for x in d:
        x["origen"] = "lineaBase"
    res["diferencias"].extend(d)
    res["advertencias"].extend(avisos)
    res["conLineaBase"] = True
    res["comparar"] = modo


def _guardar_variables(paso, datos, vars_, res):
    """'guardar' y la salida del paso como ${nombre_del_paso...}. Para los objetos, tambien ${paso.entrada...}:
    lo que se le mando (sirve de valor esperado, por ejemplo que el Get devuelva lo que recibio el Set)."""
    for var, ruta in (paso.get("guardar") or {}).items():
        existe, v, _ = obtener(datos, ruta)
        if existe:
            vars_[var] = v
        else:
            res["advertencias"].append(f"guardar '{var}': la ruta '{ruta}' no existe en la salida")
    salida = dict(datos) if isinstance(datos, dict) else datos
    if res.get("tipo") == "objeto" and isinstance(salida, dict) and clave(salida, "entrada") is None:
        salida["entrada"] = res.get("entrada")
    vars_[slug(res["nombre"]).replace("-", "_")] = salida


def correr_paso(kb, paso, vars_, opciones, fila_idx=None, grabar=False):
    t0 = time.time()
    res = {"nombre": nombre_paso(paso), "estado": "ok", "ms": 0, "verificaciones": [], "diferencias": [],
           "advertencias": [], "datos": None}
    try:
        r, datos = _ejecutar(kb, paso, vars_, opciones, res)
    except VariableIndefinida as e:
        res.update({"estado": "error", "error": f"Variable no definida: ${{{e}}}", "ms": int((time.time() - t0) * 1000)})
        return res
    except (KeyError, ValueError, MotorError) as e:
        res.update({"estado": "error", "error": str(e).strip("'\""), "ms": int((time.time() - t0) * 1000)})
        return res

    res["ms"] = round(r.get("ms") or (time.time() - t0) * 1000, 1)
    res["datos"] = datos
    if r.get("consola"):
        res["consola"] = r["consola"][-20000:]
    if not r.get("ok"):
        res["error"] = r.get("error") or "Error"
        if r.get("excepcion"):
            res["excepcion"] = r["excepcion"][-20000:]
    if paso.get("esperaError"):
        _error_esperado(paso, r, res)
        return res
    if not r.get("ok"):
        res["estado"] = "error"
        return res

    opts = Opciones(**{**opciones, "ignorar": paso.get("ignorar") or [], "volatiles": paso.get("volatiles") or []})
    try:
        _verificaciones(paso, datos, vars_, opts, res)
    except VariableIndefinida as e:
        res["estado"] = "error"
        res["error"] = f"Variable no definida: ${{{e}}}"
        return res
    _linea_base(paso, fila_idx, datos, opts, res, grabar)
    _guardar_variables(paso, datos, vars_, res)

    if res["diferencias"]:
        res["resumen"] = resumir(res["diferencias"], datos)
        if len(res["diferencias"]) > MAX_DIFERENCIAS:
            res["diferenciasOmitidas"] = len(res["diferencias"]) - MAX_DIFERENCIAS
            res["diferencias"] = res["diferencias"][:MAX_DIFERENCIAS]
    if res["diferencias"] or any(not v["ok"] for v in res["verificaciones"]):
        res["estado"] = "falla"
    return res


# ---------------------------------------------------------------------- un caso

def ya_no_es_de_lectura(kb, caso):
    """Los casos 'auto' (gxpruebas.py generar) son de objetos de solo lectura y corren solos en cada build.
    Si el Java actual del objeto (o algo que llama) escribe, hace commit o tiene efectos externos, no se
    ejecuta: devuelve el motivo. None si se puede correr."""
    if "auto" not in (caso.get("etiquetas") or []):
        return None
    for p in caso.get("pasos") or []:
        if not p.get("objeto"):
            continue
        try:
            ef, _ = separar(efectos_actuales(kb, catalogo.buscar(kb, p["objeto"])["nombre"]))
        except KeyError:
            continue  # el paso mismo va a informar que no existe
        ef.pop("sin_java", None)
        if ef:
            que = ", ".join(f"{m} (en {c})" for m, c in sorted(ef.items()))
            return (f"No se ejecuto: {p['objeto']} ya no es de solo lectura ({que}). Si el cambio es correcto, "
                    "regenera con 'python gxpruebas.py generar --kb " + kb.nombre + "' o escribile un caso a mano.")
    return None


def correr_caso(kb, suite, caso, opciones, grabar=False, cancelado=lambda: False):
    """Corre un caso (una vez por fila de 'datos'). Devuelve una lista de resultados.
    Toma el motor de la KB en exclusiva durante todo el caso: si dos corridas usaran la misma
    conexion a la vez, el rollback de una desharia los pasos de la otra."""
    with motor(kb).lock:
        filas = caso.get("datos") or [None]
        return [_correr_fila(kb, suite, caso, opciones, fi, fila, grabar, cancelado) for fi, fila in enumerate(filas)]


def _resultado_vacio(caso, fi, fila):
    etiqueta = "" if fila is None else f" [{fi + 1}: " + ", ".join(f"{k}={v}" for k, v in (fila or {}).items())[:80] + "]"
    return {"id": caso["id"] + ("" if fila is None else f"#{fi + 1}"), "casoId": caso["id"],
            "fila": fi if fila is not None else None, "nombre": caso["nombre"] + etiqueta, "estado": "ok", "pasos": [],
            "ms": 0, "advertencias": []}


def _correr_fila(kb, suite, caso, opciones, fi, fila, grabar, cancelado):
    res = _resultado_vacio(caso, fi, fila)
    t0 = time.time()
    modo = caso.get("transaccion") or opciones.get("transaccion", "rollback")
    if caso.get("omitir"):
        res["estado"] = "omitido"
        return res
    motivo = ya_no_es_de_lectura(kb, caso)
    if motivo:
        res["estado"] = "error"
        res["advertencias"].append(motivo)
        res["pasos"].append({"nombre": "Ejecutar", "estado": "error", "error": motivo, "verificaciones": [],
                             "diferencias": [], "advertencias": []})
        return res
    vars_ = variables_base(suite, fila, caso)
    fi_idx = fi if caso.get("datos") else None
    try:
        fin_transaccion(kb, "rollback")  # arranca limpio
        if _preparacion(kb, suite, vars_, opciones, res):
            _pasos(kb, caso, vars_, opciones, fi_idx, grabar, cancelado, res)
    finally:
        ft = fin_transaccion(kb, modo)
        res["transaccion"] = modo
        if not ft.get("ok"):
            res["advertencias"].append("Fin de transaccion con errores: " + "; ".join(ft.get("errores") or []))
    estados = [p["estado"] for p in res["pasos"]]
    if "error" in estados:
        res["estado"] = "error"
    elif "falla" in estados:
        res["estado"] = "falla"
    res["ms"] = int((time.time() - t0) * 1000)
    return res


def _preparacion(kb, suite, vars_, opciones, res):
    """Los pasos de 'preparacion' de la suite. False si alguno no termino bien (el caso no se corre)."""
    for p in suite.get("preparacion") or []:
        pr = correr_paso(kb, p, vars_, opciones)
        pr["preparacion"] = True
        if pr["estado"] != "ok":
            res["pasos"].append(pr)
            res["estado"] = "error"
            return False
    return True


def _pasos(kb, caso, vars_, opciones, fi_idx, grabar, cancelado, res):
    """Los pasos del caso. Despues de una falla, los siguientes se omiten (salvo detenerEnFalla: false)."""
    cortar = False
    for paso in caso["pasos"]:
        if cortar or cancelado():
            res["pasos"].append(_paso_omitido(paso))
            continue
        pr = correr_paso(kb, paso, vars_, opciones, fi_idx, grabar)
        res["pasos"].append(pr)
        if pr["estado"] != "ok":
            cortar = caso.get("detenerEnFalla", True)


# ---------------------------------------------------------------------- ejecucion suelta

def ejecutar_suelto(kb, objeto, entrada=None, sql=(), transaccion="rollback", variables=None, opciones=None, timeout_ms=None):
    """Un objeto, y despues consultas SQL en la misma transaccion (pantalla Explorar y comando 'ejecutar').
    sql: [{"ds", "query"}]. Devuelve el resultado del caso, con las verificaciones sugeridas en cada paso."""
    pasos = [{"nombre": objeto, "objeto": objeto, "entrada": entrada or {}}]
    for i, s in enumerate(sql or []):
        if (s.get("query") or "").strip():
            pasos.append({"nombre": f"SQL {i + 1}", "sql": s["query"], "ds": s.get("ds", "")})
    caso = {"id": "suelta", "nombre": objeto or "", "pasos": pasos, "transaccion": transaccion}
    suite = {"variables": variables or {}, "preparacion": []}
    opts = {**CFG["opcionesSuite"], **(opciones or {})}
    if timeout_ms:
        opts["timeoutMs"] = int(timeout_ms)
    res = correr_caso(kb, suite, caso, opts)[0]
    for p in res["pasos"]:  # para "Guardar como caso": que conviene verificar
        if p.get("datos") is not None:
            p["sugerencias"] = sugerir(p["datos"])
    return res
