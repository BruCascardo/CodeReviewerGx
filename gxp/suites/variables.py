"""Variables de un caso: ${x} en los pasos se reemplaza por

  - las 'variables' de la suite y la fila de 'datos';
  - lo guardado con 'guardar' en un paso anterior;
  - la salida (o la entrada) de un paso anterior: ${alta.outSet.RegTipo}, ${alta.entrada.inSet.Tipo};
  - las predefinidas ${hoy}, ${ahora}, ${aleatorio}, ${uuid} y ${caso}.

Si el texto es solo "${x}", se reemplaza por el valor con su tipo (un numero sigue siendo numero).
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


def sustituir(obj, vars_):
    """Reemplaza las ${variables} en cualquier estructura. VariableIndefinida si falta alguna."""
    if isinstance(obj, str):
        m = _VAR.fullmatch(obj.strip())
        if m:
            return _valor(m.group(1), vars_)
        return _VAR.sub(lambda m: _como_texto(_valor(m.group(1), vars_)), obj)
    if isinstance(obj, list):
        return [sustituir(x, vars_) for x in obj]
    if isinstance(obj, dict):
        return {k: sustituir(v, vars_) for k, v in obj.items()}
    return obj


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
