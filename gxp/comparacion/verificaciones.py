"""Verificaciones de un paso: {"ruta", "op", "valor", "cada"} -> resultado con ok, mensaje y lo obtenido.

Para agregar un operador: una funcion (obtenido, obtenido recortado, valor, opciones) -> (cumple, mensaje si
no cumple) y su entrada en OPERADORES, con la descripcion que muestra la ayuda. 'existe' y 'no_existe' miran
si la ruta existe; el resto, salvo 'vacio', falla si la ruta no existe.
"""
import re
from collections import namedtuple

from .comparar import diferencias_parciales, total
from .igualdad import escalar_igual
from .rutas import clave, obtener
from .valores import a_numero, describir, tipo_json, vacio

Operador = namedtuple("Operador", "descripcion funcion")


def _orden(a, b):
    na, nb = a_numero(a), a_numero(b)
    if na is not None and nb is not None:
        return (na > nb) - (na < nb)
    sa, sb = str(a), str(b)
    return (sa > sb) - (sa < sb)


def _igual(o, r, valor, opts):
    if isinstance(valor, (dict, list)):
        d = []
        total(valor, o, "", opts, d)
        return (not d), f"{len(d)} diferencia(s)"
    return escalar_igual(valor, o, opts), "es distinto"


def _coincide(o, r, valor, opts):
    d = diferencias_parciales(valor, o, opts)
    return (not d), "; ".join(f"{x['ruta']}: {x['mensaje'] or 'distinto'}" for x in d[:5])


def _contiene(o, valor, opts):
    if isinstance(o, list):
        return any((not diferencias_parciales(valor, x, opts)) if isinstance(valor, (dict, list))
                   else escalar_igual(valor, x, opts) for x in o)
    if isinstance(o, dict):
        return clave(o, str(valor)) is not None
    return str(valor) in ("" if o is None else str(o))


def _comparacion(cmp, nombre):
    return lambda o, r, valor, opts: (cmp(_orden(r, valor)), f"no es {nombre} que {valor}")


def _entre(o, r, valor, opts):
    if not (isinstance(valor, list) and len(valor) == 2):
        return False, "'entre' necesita [desde, hasta]"
    return (_orden(r, valor[0]) >= 0 and _orden(r, valor[1]) <= 0), f"no esta entre {valor[0]} y {valor[1]}"


def _largo(cmp):
    def f(o, r, valor, opts):
        try:
            n = len(r)
        except TypeError:
            return False, "no tiene largo"
        return cmp(n, int(valor)), f"tiene {n}"
    return f


OPERADORES = {
    "igual": Operador("Es igual al valor (objetos y listas: igualdad completa)", _igual),
    "distinto": Operador("Es distinto del valor", lambda o, r, v, opts: (not escalar_igual(v, o, opts), "es igual")),
    "contiene": Operador("Texto: contiene el valor. Lista: algun elemento coincide. Objeto: tiene esa clave",
                         lambda o, r, v, opts: (_contiene(o, v, opts), "no lo contiene")),
    "no_contiene": Operador("Lo contrario de contiene", lambda o, r, v, opts: (not _contiene(o, v, opts), "lo contiene")),
    "empieza": Operador("El texto empieza con el valor", lambda o, r, v, opts: (str(r or "").startswith(str(v)), "no empieza asi")),
    "termina": Operador("El texto termina con el valor", lambda o, r, v, opts: (str(r or "").endswith(str(v)), "no termina asi")),
    "regex": Operador("El texto cumple la expresion regular",
                      lambda o, r, v, opts: (bool(re.search(str(v), "" if o is None else str(r))), "no cumple el patron")),
    "mayor": Operador("Mayor que el valor (numeros; textos/fechas: orden alfabetico)", _comparacion(lambda c: c > 0, "mayor")),
    "mayor_igual": Operador("Mayor o igual", _comparacion(lambda c: c >= 0, "mayor igual")),
    "menor": Operador("Menor que el valor", _comparacion(lambda c: c < 0, "menor")),
    "menor_igual": Operador("Menor o igual", _comparacion(lambda c: c <= 0, "menor igual")),
    "entre": Operador("Entre [desde, hasta], inclusive", _entre),
    "en": Operador("Es igual a alguno de los valores de la lista",
                   lambda o, r, v, opts: (any(escalar_igual(x, o, opts) for x in (v if isinstance(v, list) else [v])),
                                          "no esta en la lista")),
    "existe": Operador("La ruta existe", None),
    "no_existe": Operador("La ruta no existe", None),
    "vacio": Operador("Vacio a la manera de GeneXus: '', 0, false, [], {} o nulo", lambda o, r, v, opts: (vacio(r), "no esta vacio")),
    "no_vacio": Operador("No esta vacio", lambda o, r, v, opts: (not vacio(r), "esta vacio")),
    "largo": Operador("La lista/texto tiene exactamente N elementos/caracteres", _largo(lambda n, v: n == v)),
    "largo_min": Operador("Tiene al menos N elementos", _largo(lambda n, v: n >= v)),
    "largo_max": Operador("Tiene como maximo N elementos", _largo(lambda n, v: n <= v)),
    "tipo": Operador("Tipo JSON: texto, numero, booleano, lista, objeto, nulo",
                     lambda o, r, v, opts: (tipo_json(o) == str(v), f"es {tipo_json(o)}")),
    "coincide": Operador("Coincidencia parcial con un objeto/lista (como 'esperado')", _coincide),
}


def _aplicar(op, o, valor, opts, existe):
    """(ok, mensaje) de un operador sobre un valor."""
    if op == "existe":
        return existe, "la ruta no existe"
    if op == "no_existe":
        return (not existe), "la ruta existe"
    if not existe and op != "vacio":
        return False, "la ruta no existe"
    operador = OPERADORES.get(op)
    if operador is None:
        return False, f"operador desconocido '{op}'"
    r = o.rstrip() if isinstance(o, str) and opts.recortar else o
    return operador.funcion(o, r, valor, opts)


def verificar(datos, v, opts):
    """v = {"ruta", "op", "valor", "cada"} -> resultado con ok/mensaje/obtenido. Con [*] en la ruta y
    'cada', el operador se aplica a cada elemento; sin 'cada', al conjunto."""
    ruta = v.get("ruta", "")
    op = (v.get("op") or "igual").strip()
    valor = v.get("valor")
    existe, o, comodin = obtener(datos, ruta)
    if comodin and v.get("cada"):
        if not o:
            ok, msg = False, "la ruta no tiene elementos"
        else:
            fallas = []
            for i, x in enumerate(o):
                okx, m = _aplicar(op, x, valor, opts, True)
                if not okx:
                    fallas.append(f"[{i}] {describir(x)} {m}")
            ok, msg = (not fallas), "; ".join(fallas[:5])
    else:
        if comodin:
            existe = bool(o)
        ok, msg = _aplicar(op, o, valor, opts, existe)
    return {"ruta": ruta, "op": op, "valor": valor, "cada": bool(v.get("cada")), "obtenido": o, "ok": ok,
            "mensaje": "" if ok else msg, "descripcion": v.get("descripcion", "")}
