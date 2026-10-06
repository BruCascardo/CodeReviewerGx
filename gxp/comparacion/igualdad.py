"""Igualdad de valores simples y comodines de texto en los valores esperados.

  <<cualquiera>> <<no_vacio>> <<vacio>> <<numero>> <<texto>> <<booleano>> <<fecha>> <<fechahora>>
  <<regex:patron>> <<contiene:texto>> <<empieza:texto>> <<mayor:n>> <<menor:n>> <<distinto:valor>>

Para agregar un comodin: una entrada en COMODINES. Cada funcion recibe (obtenido, obtenido recortado,
argumento, opciones) y devuelve (cumple, mensaje si no cumple).
"""
import math
import re

from .valores import a_numero, es_numero, recortado, vacio


def _mayor_menor(cual):
    def f(o, _r, arg, _opts):
        n, a = a_numero(o), a_numero(arg)
        if n is None or a is None:
            return False, "no es numerico"
        return (n > a if cual == "mayor" else n < a), f"no es {cual} que {arg}"
    return f


COMODINES = {
    "cualquiera": lambda o, r, arg, opts: (True, ""),
    "no_vacio": lambda o, r, arg, opts: (not vacio(r), "esta vacio"),
    "vacio": lambda o, r, arg, opts: (vacio(r), "no esta vacio"),
    "numero": lambda o, r, arg, opts: (es_numero(o), "no es un numero"),
    "texto": lambda o, r, arg, opts: (isinstance(o, str), "no es texto"),
    "booleano": lambda o, r, arg, opts: (isinstance(o, bool), "no es booleano"),
    "fecha": lambda o, r, arg, opts: (bool(isinstance(o, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", o.strip())),
                                      "no es una fecha aaaa-mm-dd"),
    "fechahora": lambda o, r, arg, opts: (
        bool(isinstance(o, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?.*)?", o.strip())),
        "no es fecha/hora"),
    "regex": lambda o, r, arg, opts: (bool(re.search(arg, "" if o is None else str(r))), f"no cumple /{arg}/"),
    "contiene": lambda o, r, arg, opts: (arg in ("" if o is None else str(o)), f"no contiene '{arg}'"),
    "empieza": lambda o, r, arg, opts: (str(o or "").startswith(arg), f"no empieza con '{arg}'"),
    "mayor": _mayor_menor("mayor"),
    "menor": _mayor_menor("menor"),
    "distinto": lambda o, r, arg, opts: (not escalar_igual(arg, o, opts), f"es igual a {arg}"),
}


def comodin(e, o, opts):
    """Evalua un comodin <<...>>. Devuelve None si 'e' no es comodin, o (ok, mensaje)."""
    if not (isinstance(e, str) and e.startswith("<<") and e.endswith(">>")):
        return None
    nombre, _, arg = e[2:-2].partition(":")
    f = COMODINES.get(nombre.strip().lower())
    if f is None:
        return False, f"comodin desconocido {e}"
    return f(o, recortado(o, opts), arg, opts)


def escalar_igual(e, o, opts):
    """Igualdad de dos valores simples: comodines, numeros con tolerancia y textos sin espacios finales."""
    c = comodin(e, o, opts)
    if c is not None:
        return c[0]
    if es_numero(e) or es_numero(o):
        a, b = a_numero(e), a_numero(o)
        if a is None or b is None:
            return False
        return math.isclose(a, b, rel_tol=0, abs_tol=opts.tol) if opts.tol else a == b
    if isinstance(e, str) and isinstance(o, str):
        return (e.rstrip() == o.rstrip()) if opts.recortar else e == o
    return e == o
