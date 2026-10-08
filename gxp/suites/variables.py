"""Variables de un caso: ${x} en los pasos se reemplaza por

  - las 'variables' de la suite y la fila de 'datos';
  - lo guardado con 'guardar' en un paso anterior;
  - la salida (o la entrada) de un paso anterior: ${alta.outSet.RegTipo}, ${alta.entrada.inSet.Tipo};
  - las predefinidas ${hoy}, ${ahora}, ${aleatorio}, ${uuid} y ${caso};
  - las fechas relativas ${hoy+30}, ${fin_mes}, ${habil_siguiente}... (fechas.py);
  - los valores de una clave calculados en la base: ${siguiente.CuponId}, ${existente.CuponId|CuponEstado=PRO},
    ${con_hijos.CuponId}... (campos/expresiones.py). Se calculan la primera vez que se usan en la fila del caso,
    dentro de su transaccion, y quedan fijos para el resto de sus pasos.

Las que se calculan al ejecutar (de la base y fechas relativas) quedan anotadas en vars_[CALCULADAS] con el valor
que dieron. Al aprobar una salida, poner_calculadas() pone la variable donde la salida tiene ese valor, para que la
salida aprobada no quede con un id o una fecha fijos.

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
CALCULADAS = "__calculadas__"  # en vars_: {variable como se escribio (sin ${}): valor} de las calculadas al ejecutar


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


def _es_calculada(nombre, vars_):
    """Si ${nombre} se calcula al ejecutar: una funcion de la base (${siguiente.X}) o una fecha relativa."""
    cabeza = re.split(r"[.\[]", nombre, maxsplit=1)[0]
    if callable(vars_.get(cabeza)):
        return True
    return nombre not in vars_ and fechas.calcular_seguro(nombre)


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
            elif _es_calculada(nombre, vars_):
                vars_.setdefault(CALCULADAS, {})[interior.strip()] = v
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


def calculadas(vars_):
    """{"${siguiente.CuponId}": 60, ...}: las variables calculadas al ejecutar que se usaron, con su valor."""
    return {f"${{{k}}}": v for k, v in (vars_.get(CALCULADAS) or {}).items()}


def eligen_fila(pasos):
    """Si en los pasos (resultados) se uso alguna ${variable} que elige una fila de la base (${existente.X|...},
    ${ultimo.X}, con_hijos, sin_hijos): con otra_fila, esa variable pudo dar otro valor."""
    return any(k[2:].split(".")[0] in ("existente", "ultimo", "con_hijos", "sin_hijos")
               for p in pasos or [] for k in (p.get("calculadas") or {}))


# Un valor adentro de un texto: no pegado a letras o numeros, ni a / : - (fechas, horas), ni a un . seguido de numero.
_ANTES, _DESPUES = r"(?<![\w/:.\-])", r"(?![\w/:\-]|\.\d)"


def poner_calculadas(datos, calc):
    """Al aprobar una salida: donde tiene el valor que dio una variable calculada al ejecutar ('calc', de
    calculadas()), pone la variable. Devuelve (datos, [rutas cambiadas]).

      - de la base (${siguiente.CuponId}): un campo que se llama como el atributo (CuponId) y tiene ese valor;
      - fecha relativa (${hoy+30}): cualquier campo con esa fecha;
      - adentro de un texto ("No existe el cupon 60"): el valor como palabra suelta, si tiene 2 caracteres o mas y
        ninguna otra variable dio el mismo valor.
    """
    reglas = []  # (variable, valor como texto, atributo o None)
    for texto, v in (calc or {}).items():
        if isinstance(v, bool) or v is None or str(v).strip() == "":
            continue
        _, _, resto = texto[2:-1].partition(".")  # las fechas relativas no llevan punto: ${hoy+30}
        # ${existente.cbhCargoCuota.CargoId|...}: el atributo es el ultimo nombre antes de las condiciones
        atributo = re.split(r"[|:]", resto)[0].strip().split(".")[-1] if resto else None
        reglas.append((texto, str(v).strip(), atributo))
    if not reglas:
        return datos, []
    por_valor = {}
    for texto, val, _ in reglas:
        por_valor.setdefault(val, []).append(texto)
    en_texto = {val: ts[0] for val, ts in por_valor.items() if len(ts) == 1 and len(val) >= 2}
    patron = re.compile(_ANTES + "(" + "|".join(re.escape(v) for v in sorted(en_texto, key=len, reverse=True)) + ")" + _DESPUES) \
        if en_texto else None
    cambiadas = []

    def poner(x, ruta, clave):
        if isinstance(x, dict):
            return {k: poner(v, f"{ruta}.{k}" if ruta else k, k) for k, v in x.items()}
        if isinstance(x, list):
            return [poner(v, f"{ruta}[{i}]", clave) for i, v in enumerate(x)]
        if isinstance(x, bool) or not isinstance(x, (str, int, float)):
            return x
        s = str(x).strip()
        if s in por_valor:  # el campo entero: solo si es el atributo de la variable (o una fecha)
            for texto, val, atributo in reglas:
                if val == s and (atributo is None or atributo.lower() == str(clave or "").lower()):
                    cambiadas.append(ruta)
                    return texto
            return x
        if isinstance(x, str) and patron:
            nuevo = patron.sub(lambda m: en_texto[m.group(1)], x)
            if nuevo != x:
                cambiadas.append(ruta)
                return nuevo
        return x
    return poner(datos, "", None), cambiadas


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


def variables_base(suite, fila, caso, kb=None, otra_fila=False):
    """Las variables con las que arranca una fila de un caso. Con 'kb', tambien ${siguiente.Atributo}, que se
    calcula en la transaccion del caso (ve lo que dejo el script previo y lo que hicieron los pasos anteriores).
    'otra_fila': las de la base toman la fila del otro extremo (${existente.X} da el ultimo que cumple): lo usa la
    segunda ejecucion al aprobar, para marcar como volatil lo que depende de la fila elegida."""
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
            v[f] = lambda resto, f=f: expresiones.resolver(kb, f, resto, en_transaccion=True, invertir=otra_fila)
    v.update(copy.deepcopy(suite.get("variables") or {}))
    v.update(copy.deepcopy(fila or {}))
    return v
