"""Operaciones sobre el motor de una KB: describir y ejecutar un objeto, consultas SQL y fin de transaccion.

Todo lo que corre en el motor queda en la transaccion abierta hasta fin_transaccion(): quien encadena
varias operaciones (un caso de prueba) toma motor(kb).lock durante todo el trabajo.
"""
from .proceso import MotorError, motor
from .. import catalogo


class NoEjecutable(ValueError):
    """El objeto existe pero no se puede ejecutar (no es un procedimiento, no esta compilado...)."""


def _info_ejecutable(kb, nombre):
    info = catalogo.buscar(kb, nombre)  # KeyError si no existe
    motivo = catalogo.motivo_no_ejecutable(kb, info)
    if motivo:
        raise NoEjecutable(motivo)
    return info


def describir(kb, nombre, timeout_ms=60000):
    """Parametros del objeto (de la especificacion y del Java compilado) y una entrada de ejemplo con la
    estructura exacta de los SDT. 'aviso' si el Java compilado no coincide con la especificacion."""
    info = _info_ejecutable(kb, nombre)
    r = motor(kb).pedir("describir", timeout_ms=timeout_ms, clase=kb.clase_java(info["nombre"]))
    if not r.get("ok"):
        raise MotorError(r.get("error") or "No se pudo describir el objeto")
    jps = r.get("parametros") or []
    parametros, plantilla = [], {}
    for i, p in enumerate(info["parametros"]):
        jp = jps[i] if i < len(jps) else {}
        parametros.append({**p, "tipoJava": jp.get("tipoJava"), "clase": jp.get("clase"), "plantilla": jp.get("plantilla")})
        if p["io"] in ("in", "inout"):
            plantilla[p["nombre"]] = jp.get("plantilla")
    aviso = None
    if len(jps) != len(info["parametros"]):
        aviso = (f"La especificacion dice {len(info['parametros'])} parametros y el Java compilado tiene {len(jps)}: "
                 "la KB no esta compilada con la ultima version del objeto.")
    return {"info": info, "parametros": parametros, "plantillaEntrada": plantilla, "aviso": aviso,
            "coincide": len(jps) == len(info["parametros"])}


def _entrada_param(entrada, nombre):
    """Valor de un parametro en la entrada (sin distinguir mayusculas). (valor, hay)."""
    if not isinstance(entrada, dict):
        return None, False
    if nombre in entrada:
        return entrada[nombre], True
    for k, v in entrada.items():
        if k.lower() == nombre.lower():
            return v, True
    return None, False


def ejecutar_objeto(kb, objeto, entrada, timeout_ms):
    """Ejecuta un objeto y devuelve (respuesta del motor, {parametro de salida: valor}, info del objeto)."""
    info = _info_ejecutable(kb, objeto)
    args = []
    for p in info["parametros"]:
        v, hay = _entrada_param(entrada or {}, p["nombre"])
        a = {"modo": p["io"]}
        if hay and p["io"] != "out":
            a["valor"] = v
        args.append(a)
    r = motor(kb).pedir("ejecutar", timeout_ms=timeout_ms, clase=kb.clase_java(info["nombre"]), args=args)
    datos = {}
    salidas = r.get("salidas") or []
    for i, p in enumerate(info["parametros"]):
        if p["io"] in ("out", "inout") and i < len(salidas):
            datos[p["nombre"]] = salidas[i]
    return r, datos, info


def ejecutar_sql(kb, ds, query, timeout_ms, maximo=1000):
    """Consulta en la conexion del motor. (respuesta, {filas, cantidad, columnas, truncado} o {actualizadas})."""
    r = motor(kb).pedir("sql", timeout_ms=timeout_ms, ds=ds or "", query=query, max=maximo)
    if not r.get("ok"):
        return r, {}
    if "filas" in r:
        cols = r.get("columnas") or []
        filas = [dict(zip(cols, f)) for f in r["filas"]]
        return r, {"filas": filas, "cantidad": len(filas), "columnas": cols, "truncado": r.get("truncado", False)}
    return r, {"actualizadas": r.get("actualizadas", 0)}


def fin_transaccion(kb, modo):
    """Commit (modo 'commit') o rollback de lo hecho en el motor. Nunca lanza: devuelve {ok, errores}."""
    cmd = "commit" if modo == "commit" else "rollback"
    try:
        return motor(kb).pedir(cmd, timeout_ms=60000)
    except MotorError as e:
        return {"ok": False, "errores": [str(e)]}


def marcar(kb, datasources, otros=()):
    """Savepoint en la conexion de cada datasource (despues del script previo de una suite): en 'datasources'
    tiene que poder y en 'otros', los que se pueda. Hasta el fin de la transaccion, el commit y el rollback de
    los objetos en esos datasources se simulan (no llegan a la base). Devuelve los nombres marcados.
    MotorError si no se pudo."""
    r = motor(kb).pedir("marcar", timeout_ms=60000, ds=list(datasources), otros=list(otros))
    if not r.get("ok"):
        raise MotorError(r.get("error") or "No se pudo marcar el savepoint")
    return r.get("ds") or []


def volver(kb):
    """Deshace lo hecho despues de marcar(): hasta el savepoint en los datasources marcados y todo en los
    demas. Nunca lanza: devuelve {ok, puntos (restaurados), commits y rollbacks (simulados), perdidos, errores}."""
    try:
        return motor(kb).pedir("volver", timeout_ms=60000)
    except MotorError as e:
        return {"ok": False, "puntos": 0, "perdidos": [], "errores": [str(e)]}


def avanzar(kb):
    """Casos encadenados: al terminar un caso no deshace nada; lo hecho pasa a ser lo confirmado (un rollback en
    el caso siguiente vuelve ahi). Nunca lanza: devuelve lo mismo que volver()."""
    try:
        return motor(kb).pedir("avanzar", timeout_ms=60000)
    except MotorError as e:
        return {"ok": False, "puntos": 0, "perdidos": [], "errores": [str(e)]}


def consulta_suelta(kb, ds, query, timeout_ms=60000, maximo=1000, confirmar=False):
    """Una consulta aislada (pantalla SQL, comando 'sql'): toma el motor y termina con rollback, salvo
    confirmar=True. Devuelve (respuesta, datos)."""
    m = motor(kb)
    with m.lock:
        try:
            return ejecutar_sql(kb, ds, query, timeout_ms, maximo)
        finally:
            fin_transaccion(kb, "commit" if confirmar else "rollback")
