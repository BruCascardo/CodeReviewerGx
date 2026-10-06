"""Rutas dentro de una salida: "outSet.Output.Messages[0].Code", "outList.Registros[*].Tipo", "filas[0].cantidad".

  - [n] indice (base 0; negativo cuenta desde el final), [*] todos los elementos.
  - Los nombres se buscan primero exactos y despues sin distinguir mayusculas.
"""
import re

_TOKEN = re.compile(r"([^.\[\]]+)|\[(\*|-?\d+)\]")
_LARGO = ("largo", "length", "count", "cantidad")


def partes_ruta(ruta: str):
    ruta = (ruta or "").strip()
    if ruta in ("", "$", "."):
        return []
    if ruta.startswith("$."):
        ruta = ruta[2:]
    partes = []
    for m in _TOKEN.finditer(ruta):
        if m.group(1) is not None:
            partes.append(m.group(1).strip())
        else:
            g = m.group(2)
            partes.append("*" if g == "*" else int(g))
    return partes


def clave(d: dict, k: str):
    """La clave de 'd' que corresponde a 'k' (exacta, o sin distinguir mayusculas), o None."""
    if k in d:
        return k
    kl = k.lower()
    for x in d:
        if x.lower() == kl:
            return x
    return None


def obtener(datos, ruta):
    """Devuelve (existe, valor, comodin). Con [*] el valor es la lista de coincidencias."""
    partes = partes_ruta(ruta)
    comodin = "*" in partes
    actuales = [datos]
    for p in partes:
        sig = []
        for a in actuales:
            if p == "*":
                if isinstance(a, list):
                    sig.extend(a)
                elif isinstance(a, dict):
                    sig.extend(a.values())
            elif isinstance(p, int):
                if isinstance(a, list) and -len(a) <= p < len(a):
                    sig.append(a[p])
            elif isinstance(a, dict):
                k = clave(a, p)
                if k is not None:
                    sig.append(a[k])
            elif isinstance(a, list) and p.lower() in _LARGO and not comodin:
                sig.append(len(a))
        actuales = sig
    if comodin:
        return True, actuales, True
    if not actuales:
        return False, None, False
    return True, actuales[0], False


def unir(base, k):
    if isinstance(k, int):
        return f"{base}[{k}]"
    return f"{base}.{k}" if base else str(k)


def unir_ign(base, k, largo=None):
    """Como unir(), para la ruta interna con la que se evalua 'ignorar': cada indice va con su forma
    positiva y negativa ([3,-1] es el ultimo de una lista de 4), asi un patron con [-1] tambien coincide."""
    if isinstance(k, int):
        return f"{base}[{k},{k - largo}]"
    return unir(base, k)


def patron_ignorar(p: str):
    """'outList.Registros[*].Fecha' -> regex que acepta cualquier indice; [-1] es el ultimo elemento.
    Se evalua contra la ruta de unir_ign(). Un patron sin [..] tambien cubre todo lo que cuelga de esa ruta."""
    p = p.strip()
    rx = ""
    for parte in partes_ruta(p):
        if parte == "*":
            rx += r"\[\d+,-\d+\]"
        elif isinstance(parte, int):
            rx += rf"\[{parte},-\d+\]" if parte >= 0 else rf"\[\d+,{parte}\]"
        else:
            rx += (r"\." if rx else "") + re.escape(parte)
    return re.compile("^" + rx + r"($|\.|\[)", re.I)


def patron_de(ruta):
    """outList.Registros[3].Fecha -> outList.Registros[*].Fecha"""
    return re.sub(r"\[\d+\]", "[*]", ruta or "")
