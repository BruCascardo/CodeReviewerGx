"""Variables de un caso: ${x} en los pasos se reemplaza por

  - las 'variables' de la suite y la fila de 'datos';
  - lo guardado con 'guardar' en un paso anterior;
  - la salida (o la entrada) de un paso anterior: ${alta.outSet.RegTipo}, ${alta.entrada.inSet.Tipo};
  - las predefinidas ${hoy}, ${ahora}, ${aleatorio}, ${uuid} y ${caso}.

Si el texto es solo "${x}", se reemplaza por el valor con su tipo (un numero sigue siendo numero).

En la salida aprobada ('lineaBase') tambien se reemplazan, pero sin exigir que existan (estricto=False): una
variable que no esta definida queda como texto, por si la salida real tiene un "${...}" propio.
"""
import copy
import datetime as dt
import json
import random
import re
import uuid

from ..comparacion import obtener

_VAR = re.compile(r"\$\{([^}]+)\}")


class VariableIndefinida(Exception):
    pass


def _valor(nombre, vars_):
    nombre = nombre.strip()
    if nombre in vars_:
        return vars_[nombre]
    # ${paso.ruta} -> salida de un paso anterior
    if "." in nombre or "[" in nombre:
        cabeza = re.split(r"[.\[]", nombre, 1)[0]
        if cabeza in vars_:
            existe, v, _ = obtener(vars_[cabeza], nombre[len(cabeza):].lstrip("."))
            if existe:
                return v
    raise VariableIndefinida(nombre)


def _como_texto(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def sustituir(obj, vars_, estricto=True):
    """Reemplaza las ${variables} en cualquier estructura. VariableIndefinida si falta alguna (sin 'estricto',
    la deja como esta)."""
    if isinstance(obj, str):
        if "${" not in obj:
            return obj

        def valor(nombre, texto):
            try:
                return _valor(nombre, vars_)
            except VariableIndefinida:
                if estricto:
                    raise
                return texto
        m = _VAR.fullmatch(obj.strip())
        if m:
            return valor(m.group(1), obj)
        return _VAR.sub(lambda m: _como_texto(valor(m.group(1), m.group(0))), obj)
    if isinstance(obj, list):
        return [sustituir(x, vars_, estricto) for x in obj]
    if isinstance(obj, dict):
        return {k: sustituir(v, vars_, estricto) for k, v in obj.items()}
    return obj


def con_variables(obj):
    """True si en algun texto de la estructura hay una ${variable}."""
    if isinstance(obj, str):
        return bool(_VAR.search(obj))
    if isinstance(obj, list):
        return any(con_variables(x) for x in obj)
    if isinstance(obj, dict):
        return any(con_variables(x) for x in obj.values())
    return False


def reponer_variables(plantilla, nuevo):
    """Al aprobar una salida nueva: donde la salida aprobada anterior tenia una ${variable}, se conserva (si el
    campo sigue estando). Lo demas queda con el valor nuevo."""
    if isinstance(plantilla, str) and _VAR.search(plantilla):
        return plantilla
    if isinstance(plantilla, dict) and isinstance(nuevo, dict):
        return {k: reponer_variables(plantilla[k], v) if k in plantilla else v for k, v in nuevo.items()}
    if isinstance(plantilla, list) and isinstance(nuevo, list):
        return [reponer_variables(plantilla[i], v) if i < len(plantilla) else v for i, v in enumerate(nuevo)]
    return nuevo


def variables_base(suite, fila, caso):
    """Las variables con las que arranca una fila de un caso."""
    ahora = dt.datetime.now()
    v = {
        "hoy": ahora.strftime("%Y-%m-%d"),
        "ahora": ahora.strftime("%Y-%m-%dT%H:%M:%S"),
        "aleatorio": random.randint(100000, 999999),
        "uuid": str(uuid.uuid4()),
        "caso": caso.get("id", ""),
    }
    v.update(copy.deepcopy(suite.get("variables") or {}))
    v.update(copy.deepcopy(fila or {}))
    return v
