"""Variables de un caso: ${x} en los pasos se reemplaza por

  - las 'variables' de la suite y la fila de 'datos';
  - lo guardado con 'guardar' en un paso anterior;
  - la salida (o la entrada) de un paso anterior: ${alta.outSet.RegTipo}, ${alta.entrada.inSet.Tipo};
  - las predefinidas ${hoy}, ${ahora}, ${aleatorio}, ${uuid} y ${caso};
  - las fechas relativas ${hoy+30}, ${fin_mes}, ${habil_siguiente}... (fechas.py);
  - los valores de una clave calculados en la base: ${siguiente.CuponId}, ${existente.CuponId|CuponEstado=PRO},
    ${con_hijos.CuponId}... (campos/expresiones.py). Se calculan la primera vez que se usan en la fila del caso,
    dentro de su transaccion, y quedan fijos para el resto de sus pasos.

Si el texto es solo "${x}", se reemplaza por el valor con su tipo (un numero sigue siendo numero). Una variable
puede ir dentro de otra (${existente.CuponCuotaSec|CuponId=${cupon}}) y el valor de una variable puede ser otra
expresion (una columna de 'datos' con "${siguiente.CuponId}"): se resuelve tambien.

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
from . import fechas

_VAR = re.compile(r"\$\{([^}]+)\}")
MAX_ANIDADAS = 5  # una variable cuyo valor es otra variable...


class VariableIndefinida(Exception):
    """Una ${variable} que no existe o (con 'motivo') que no se pudo calcular."""
    def __init__(self, nombre, motivo=None):
        super().__init__(nombre)
        self.motivo = motivo


def mensaje_error(e):
    if e.motivo:
        return f"No se pudo calcular ${{{e}}}: {e.motivo}"
    return f"Variable no definida: ${{{e}}}"


def _valor(nombre, vars_):
    nombre = nombre.strip()
    if nombre in vars_ and not callable(vars_[nombre]):
        return vars_[nombre]
    # ${paso.ruta} -> salida de un paso anterior
    if "." in nombre or "[" in nombre:
        cabeza = re.split(r"[.\[]", nombre, maxsplit=1)[0]
        if callable(vars_.get(cabeza)):
            # ${siguiente.CuponId}: se calcula una vez y queda guardada con su nombre completo
            try:
                vars_[nombre] = vars_[cabeza](nombre[len(cabeza):].lstrip("."))
            except Exception as e:  # noqa: BLE001 (KeyError, ValueError, MotorError: el motivo va al paso)
                raise VariableIndefinida(nombre, str(e).strip("'\"")) from e
            return vars_[nombre]
        if cabeza in vars_:
            existe, v, _ = obtener(vars_[cabeza], nombre[len(cabeza):].lstrip("."))
            if existe:
                return v
    # ${hoy+30}, ${fin_mes}...: desde la misma hora que ${ahora}
    try:
        ahora = dt.datetime.strptime(str(vars_.get("ahora")), fechas.FORMATO_FECHAHORA)
    except ValueError:
        ahora = None
    try:
        f = fechas.calcular(nombre, ahora)
    except ValueError as e:
        raise VariableIndefinida(nombre, str(e)) from e
    if f is not None:
        return f
    raise VariableIndefinida(nombre)


def _como_texto(v):
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def _partes(texto):
    """[(inicio, fin, interior)] de las ${...} de primer nivel de un texto, con las llaves balanceadas: en
    "${a|b=${c}}" hay una sola, con interior "a|b=${c}". Una sin cerrar queda como texto."""
    partes, i = [], 0
    while (i := texto.find("${", i)) >= 0:
        prof, j = 0, i + 1
        while j < len(texto):
            prof += {"{": 1, "}": -1}.get(texto[j], 0)
            if prof == 0:
                break
            j += 1
        if j >= len(texto):
            break
        partes.append((i, j + 1, texto[i + 2:j]))
        i = j + 1
    return partes


def sustituir(obj, vars_, estricto=True, _nivel=0):
    """Reemplaza las ${variables} en cualquier estructura. VariableIndefinida si falta alguna (sin 'estricto',
    la deja como esta)."""
    if isinstance(obj, str):
        partes = _partes(obj) if "${" in obj else []
        if not partes:
            return obj

        def valor(interior, texto):
            nombre = interior
            if "${" in interior:  # las de adentro primero: ${existente.X|CuponId=${cupon}}
                nombre = _como_texto(sustituir(interior, vars_, estricto, _nivel + 1))
                if _partes(nombre):
                    return texto  # sin 'estricto', una de adentro no estaba
            try:
                v = _valor(nombre, vars_)
            except VariableIndefinida:
                if estricto:
                    raise
                return texto
            if isinstance(v, str) and "${" in v and _nivel < MAX_ANIDADAS:
                v = sustituir(v, vars_, estricto, _nivel + 1)
            return v
        inicio = len(obj) - len(obj.lstrip())
        if len(partes) == 1 and partes[0][0] == inicio and partes[0][1] == len(obj.rstrip()):
            return valor(partes[0][2], obj)
        trozos, previo = [], 0
        for i, f, interior in partes:
            trozos += [obj[previo:i], _como_texto(valor(interior, obj[i:f]))]
            previo = f
        return "".join(trozos) + obj[previo:]
    if isinstance(obj, list):
        return [sustituir(x, vars_, estricto, _nivel) for x in obj]
    if isinstance(obj, dict):
        return {k: sustituir(v, vars_, estricto, _nivel) for k, v in obj.items()}
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


def variables_base(suite, fila, caso, kb=None):
    """Las variables con las que arranca una fila de un caso. Con 'kb', tambien ${siguiente.Atributo}, que se
    calcula en la transaccion del caso (ve lo que dejo el script previo y lo que hicieron los pasos anteriores)."""
    ahora = dt.datetime.now()
    v = {
        "hoy": ahora.strftime("%Y-%m-%d"),
        "ahora": ahora.strftime("%Y-%m-%dT%H:%M:%S"),
        "aleatorio": random.randint(100000, 999999),
        "uuid": str(uuid.uuid4()),
        "caso": caso.get("id", ""),
    }
    if kb is not None:
        from ..campos import expresiones  # aca: campos importa el motor
        for f in expresiones.FUNCIONES:
            v[f] = lambda resto, f=f: expresiones.resolver(kb, f, resto, en_transaccion=True)
    v.update(copy.deepcopy(suite.get("variables") or {}))
    v.update(copy.deepcopy(fila or {}))
    return v
