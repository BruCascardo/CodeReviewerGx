"""Lector de terminos Prolog, el formato de los archivos .sp0 de la especificacion de GeneXus.

Cada clausula es un termino terminado en punto: b_line_i(5,1,1,cmd,0,[ t('',107,5,0),t('Itfid',23,0,0) ]).
Se convierte a Python asi:
  - atomo (cmd, 'Generales\\Set', =, <=)  -> str
  - numero                                -> int o float
  - lista [a,b]                           -> list
  - compuesto f(a,b)                      -> Comp("f", [a, b])
"""
import re
from typing import NamedTuple


class Comp(NamedTuple):
    nombre: str
    args: list

    def __repr__(self):
        return f"{self.nombre}({', '.join(map(repr, self.args))})"


class ErrorProlog(ValueError):
    pass


_TOKEN = re.compile(r"""
    \s*(?:
      (?P<q>'(?:[^']|'')*')                         # atomo entre comillas ('' es una comilla)
    | (?P<n>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(?![^\W\d])     # numero
    | (?P<a>[^\W\d]\w*)                             # atomo o variable (tambien con acentos: Área)
    | (?P<p>[()\[\],|])                             # puntuacion
    | (?P<s>[-+*/\\^<>=~:.?@#&$!;]+)                # atomo simbolico (=, <=, +, <>)
    | (?P<o>[^\s()\[\],|']+)                        # cualquier otro caracter suelto (vinetas de reportes)
    )""", re.X)


def leer(texto: str):
    """Termino de una clausula (con o sin el punto final)."""
    texto = texto.strip()
    if texto.endswith("."):
        texto = texto[:-1]
    toks = []
    pos, fin = 0, len(texto)
    while pos < fin:
        m = _TOKEN.match(texto, pos)
        if not m or m.end() == pos:
            if texto[pos:].strip() == "":
                break
            raise ErrorProlog(f"caracter inesperado en {pos}: {texto[pos:pos + 30]!r}")
        pos = m.end()
        tipo = m.lastgroup
        v = m.group(tipo)
        # Un atomo seguido de '(' sin espacio abre un compuesto.
        abre = pos < fin and texto[pos] == "(" and tipo in ("q", "a", "s")
        toks.append((tipo, v, abre))
    termino, i = _termino(toks, 0)
    if i != len(toks):
        raise ErrorProlog(f"sobra texto despues del termino: {toks[i:i + 3]}")
    return termino


def _atomo(tipo, v):
    if tipo == "q":
        return v[1:-1].replace("''", "'")
    return v


def _termino(toks, i):
    if i >= len(toks):
        raise ErrorProlog("fin inesperado")
    tipo, v, abre = toks[i]
    # Un '-' seguido de un numero despues de '(' / ',' / '[' es un numero negativo, ya resuelto por la regex.
    if tipo == "n":
        return (float(v) if any(c in v for c in ".eE") else int(v)), i + 1
    if tipo == "p":
        if v == "[":
            return _lista(toks, i + 1, "]")
        if v == "(":  # termino entre parentesis
            t, j = _termino(toks, i + 1)
            if j >= len(toks) or toks[j][1] != ")":
                raise ErrorProlog("falta ')'")
            return t, j + 1
        # ',' o ')' sueltos como argumento: GeneXus los escribe como atomos sin comillas (t(',',...) va
        # con comillas, pero por las dudas).
        return v, i + 1
    nombre = _atomo(tipo, v)
    if abre:
        args, j = _lista(toks, i + 2, ")")
        return Comp(nombre, args), j
    return nombre, i + 1


def _lista(toks, i, cierre):
    elems = []
    if i < len(toks) and toks[i][0] == "p" and toks[i][1] == cierre:
        return elems, i + 1
    while True:
        t, i = _termino(toks, i)
        # Operador infijo entre dos terminos: [ 30,[ 215 ] ] - []  ->  Comp("-", [izq, der])
        while i < len(toks) and toks[i][0] == "s" and not toks[i][2]:
            op = toks[i][1]
            der, i = _termino(toks, i + 1)
            t = Comp(op, [t, der])
        elems.append(t)
        if i >= len(toks):
            raise ErrorProlog(f"falta '{cierre}'")
        tipo, v, _ = toks[i]
        if tipo == "p" and v == ",":
            i += 1
            continue
        if tipo == "p" and v == "|":  # cola de lista: [a|B]
            t, i = _termino(toks, i + 1)
            elems.append(t)
            tipo, v, _ = toks[i]
        if tipo == "p" and v == cierre:
            return elems, i + 1
        raise ErrorProlog(f"se esperaba ',' o '{cierre}' y vino {v!r}")


def clausulas(texto: str, predicados, saltear=(), ilegibles=None):
    """(predicado, termino) de las clausulas cuyo predicado esta en 'predicados'. Lee solo esas: el resto
    (estructuras de SDT, datastores, layout) se saltea sin interpretarlo. Una clausula puede ocupar varias
    lineas: se acumula hasta que termina en ')."; 'saltear' es una tupla de prefijos de lineas que no interesan
    (por ejemplo los ~750 rule_i(0,datastore(...)) de cada objeto).

    Una clausula que no se puede leer se descarta sola: si mientras se acumula empieza otra clausula, se
    abandona la anterior (antes se seguian acumulando lineas y se perdian las clausulas validas siguientes).
    Las descartadas se cuentan en 'ilegibles' (una lista de un elemento que se pasa para recibir el total)."""
    pref = tuple(p + "(" for p in predicados)
    actual = None
    for linea in texto.splitlines():
        if actual is not None and _CLAUSULA.match(linea):
            if ilegibles is not None:
                ilegibles[0] += 1
            actual = None
        if actual is None:
            if not linea.startswith(pref) or (saltear and linea.startswith(saltear)):
                continue
            actual = linea
        else:
            actual += "\n" + linea
        if actual.rstrip().endswith(")."):
            try:
                t = leer(actual)
            except ErrorProlog:
                # Puede ser un ')." dentro de un texto que sigue en la linea siguiente: se sigue acumulando.
                continue
            actual = None
            yield t.nombre, t
    if actual is not None and ilegibles is not None:
        ilegibles[0] += 1


_CLAUSULA = re.compile(r"[a-z_]+_i\(")
