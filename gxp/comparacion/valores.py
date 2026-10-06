"""Clasificacion de valores JSON: numeros, vacios a la manera de GeneXus, tipos y texto para mostrar."""
import datetime as dt
import json
import re


def es_numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def a_numero(v):
    if es_numero(v):
        return float(v)
    if isinstance(v, str):
        s = v.strip()
        if re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", s):
            return float(s)
    return None


def vacio(v):
    """Vacio a la manera de GeneXus: '', 0, false, [], {} o nulo."""
    return (v is None or v == "" or (isinstance(v, str) and v.strip() == "") or v == [] or v == {} or v is False
            or (es_numero(v) and v == 0))


def vacio_estructural(v):
    """[] o {} (o un objeto que solo tiene eso): lo que GeneXus omite del JSON."""
    if isinstance(v, list):
        return not v
    if isinstance(v, dict):
        return all(vacio_estructural(x) for x in v.values())
    return False


def tipo_json(v):
    if v is None:
        return "nulo"
    if isinstance(v, bool):
        return "booleano"
    if es_numero(v):
        return "numero"
    if isinstance(v, str):
        return "texto"
    if isinstance(v, list):
        return "lista"
    return "objeto"


def describir(v):
    """El valor como texto corto, para los mensajes."""
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= 200 else s[:197] + "..."


def recortado(v, opts):
    """Los Character de GeneXus vuelven rellenos con espacios: se recortan si la opcion esta activa."""
    return v.rstrip() if isinstance(v, str) and opts.recortar else v


def con_fecha_de_hoy(v):
    hoy = dt.date.today()
    return isinstance(v, str) and (hoy.strftime("%Y-%m-%d") in v or hoy.strftime("%d/%m/%Y") in v)
