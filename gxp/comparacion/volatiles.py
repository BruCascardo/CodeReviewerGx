"""Valores que cambian solos entre dos ejecuciones con la misma entrada (fechas, ids nuevos): 'volatiles'.
De esas rutas, al comparar con la salida aprobada, solo se controla el tipo."""
from .comparar import total
from .opciones import CAMPOS_CLAVE, Opciones
from .rutas import patron_de, unir
from .valores import con_fecha_de_hoy


def es_campo_clave(patron, campos=None):
    """Ok y los codigos de mensaje nunca son volatiles: si cambian solos, el caso esta mal armado."""
    p = patron.lower()
    for c in campos or CAMPOS_CLAVE:
        c = c.lower()
        if p == c or p.endswith("." + c):
            return True
    return p.endswith(".output.messages") or p == "output.messages"


def volatiles_por_valor(datos, ruta=""):
    """Rutas con valores que casi seguro cambian solos aunque dos ejecuciones seguidas coincidan (las dos
    en el mismo segundo): textos con la fecha de hoy."""
    salida = set()
    if isinstance(datos, dict):
        for k, v in datos.items():
            salida |= volatiles_por_valor(v, unir(ruta, k))
    elif isinstance(datos, list):
        for i, v in enumerate(datos):
            salida |= volatiles_por_valor(v, unir(ruta, i))
    elif con_fecha_de_hoy(datos):
        salida.add(patron_de(ruta))
    return salida


def detectar_volatiles(d1, d2, campos=None, otra_fila=False):
    """Compara dos ejecuciones con la misma entrada. Devuelve (rutas volatiles, avisos). Ok y los codigos
    de mensaje nunca se marcan como volatiles: si cambian entre dos ejecuciones iguales, es un aviso. Con
    'otra_fila', la segunda tomo otra fila que cumple las mismas condiciones (${existente.X} dio el ultimo)."""
    diffs = []
    total(d1, d2, "", Opciones(), diffs)
    patrones, avisos = set(), []
    for d in diffs:
        p = patron_de(d["ruta"])
        if es_campo_clave(p, campos):
            avisos.append(f"{p} da distinto con otra fila que cumple las mismas condiciones (el ultimo en vez del primero): "
                          "las condiciones de las ${variables} no alcanzan para que el resultado sea siempre el mismo; agregale filtros."
                          if otra_fila else
                          f"{p} cambia entre dos ejecuciones con la misma entrada: revisa el caso (no se puede aprobar un resultado que cambia solo).")
        else:
            patrones.add(p)
    patrones |= {p for p in volatiles_por_valor(d1) if not es_campo_clave(p, campos)}
    for p in sorted(patrones):
        if any(d["tipo"] == "largo" and patron_de(d["ruta"]) == p for d in diffs):
            avisos.append(f"{p} cambia de largo entre dos ejecuciones: de esa lista solo se controla que sea una lista.")
    return sorted(patrones), list(dict.fromkeys(avisos))
