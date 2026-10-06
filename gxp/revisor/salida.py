"""Capa dinamica de la regla salida-ok-mensajes: controla los sdtOutput de una ejecucion real.

La regla estatica (reglas/salida_ok_mensajes.py) no juzga los caminos que no puede seguir. Esta capa mira lo
que el objeto devolvio de verdad, cada vez que un paso de una suite (o Explorar) lo ejecuta:

  - Ok = false: tiene que venir al menos un mensaje de tipo Error;
  - Ok = true: ningun Error y un mensaje de exito (Debug). Si el exito es un Info, advertencia.

Un sdtOutput se reconoce en el JSON como un objeto con 'Ok' booleano y 'Messages', 'Errores' o 'Log'
(GeneXus omite las colecciones vacias). No hace fallar el caso: deja avisos en el paso.
"""
from . import configuracion
from .reglas import Hallazgo, Regla

REGLA = "salida-ok-mensajes"
TIPOS = {0: "warning", 1: "error", 2: "info", 3: "debug"}  # GeneXus MessageTypes
_CAMPOS = ("messages", "errores", "log")


def _clave(d, nombre):
    """El valor de un campo sin distinguir mayusculas (GeneXus respeta la capitalizacion del SDT)."""
    for k, v in d.items():
        if k.lower() == nombre:
            return v
    return None


def _es_salida(d):
    ok = _clave(d, "ok")
    return isinstance(ok, bool) and any(k.lower() in _CAMPOS for k in d)


def salidas(datos, ruta=""):
    """[(ruta, dict)] de los sdtOutput que hay en una salida."""
    hallados = []
    if isinstance(datos, dict):
        if _es_salida(datos):
            hallados.append((ruta or "$", datos))
        for k, v in datos.items():
            hallados += salidas(v, f"{ruta}.{k}" if ruta else k)
    elif isinstance(datos, list):
        for i, v in enumerate(datos):
            hallados += salidas(v, f"{ruta}[{i}]")
    return hallados


def problemas(d):
    """[(severidad, mensaje)] de un sdtOutput."""
    mensajes = [m for m in _clave(d, "messages") or [] if isinstance(m, dict)]
    tipos = [TIPOS.get(_clave(m, "type")) for m in mensajes]
    errores = tipos.count("error") + len(_clave(d, "errores") or [])
    if _clave(d, "ok") is False:
        if not errores:
            return [("error", "Ok = false sin ningun mensaje de tipo Error")]
        return []
    if errores:
        return [("error", f"Ok = true con {errores} mensaje(s) de tipo Error")]
    if "debug" in tipos:
        return []
    if "info" in tipos:
        return [("advertencia", "el mensaje de exito es de tipo Info (2): tiene que ser Debug (3)")]
    return [("error", "Ok = true sin mensaje de exito (Type Debug)")]


def controlar(kb_nombre, objeto, datos, conf=None):
    """Avisos (texto) sobre los sdtOutput de la salida de 'objeto', o [] si la regla esta desactivada en
    revisor.json o una excepcion cubre al objeto."""
    conf = conf or configuracion.cargar()
    if not Regla(conf.reglas.get(REGLA)).activa:
        return []
    avisos = []
    for ruta, d in salidas(datos):
        for severidad, mensaje in problemas(d):
            h = Hallazgo(regla=REGLA, severidad=severidad, kb=kb_nombre, objeto=objeto, tipo="", linea=0, mensaje=mensaje)
            if conf.excepcion(h) is None:
                avisos.append(f"Buenas practicas ({severidad}): {ruta}: {mensaje} [{REGLA}]")
    return avisos
