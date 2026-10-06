"""Verificaciones que vale la pena proponer para una salida ('Guardar como caso' en la interfaz)."""
from .opciones import Opciones
from .valores import con_fecha_de_hoy, describir, recortado, vacio


def _sugerencia(ruta, op, valor, descripcion, marcada=False):
    return {"ruta": ruta, "op": op, "valor": valor, "descripcion": descripcion, "marcada": marcada}


def _de_sql(datos):
    sug = [_sugerencia("cantidad", "igual", datos["cantidad"], f"trae {datos['cantidad']} fila(s)")]
    if datos["cantidad"] == 1 and isinstance(datos.get("filas"), list):
        for k, v in list(datos["filas"][0].items())[:6]:
            if not con_fecha_de_hoy(v):
                v = recortado(v, Opciones())
                sug.append(_sugerencia(f"filas[0].{k}", "igual", v, f"{k} = {describir(v)}"))
    return sug


def _de_resultado(k, out):
    """Ok y los codigos de mensaje del sdtOutput: es lo que define el resultado, van marcados."""
    sug = []
    ok = out.get("Ok") if out else None
    if isinstance(ok, bool):
        sug.append(_sugerencia(f"{k}.Output.Ok", "igual", ok, "termina bien (Ok = true)" if ok else "termina con error (Ok = false)", True))
    mensajes = (out or {}).get("Messages")
    codigos = [m.get("Code") for m in mensajes if isinstance(m, dict) and m.get("Code")] if isinstance(mensajes, list) else []
    distintos = list(dict.fromkeys(c.rstrip() for c in codigos if isinstance(c, str)))
    for c in distintos[:5]:
        sug.append(_sugerencia(f"{k}.Output.Messages[*].Code", "contiene", c,
                               f"{'falla con' if ok is False else 'devuelve'} el mensaje {c}", len(distintos) <= 3))
    return sug


def _de_campo(ruta, campo, x):
    if isinstance(x, list) and x:
        return _sugerencia(ruta, "largo", len(x), f"{campo} trae {len(x)} elemento(s)")
    if isinstance(x, (str, int, float, bool)) and not vacio(x) and not con_fecha_de_hoy(x):
        x = recortado(x, Opciones())
        if isinstance(x, str) and len(x) > 300:
            return _sugerencia(ruta, "largo", len(x), f"{campo} mide {len(x)} caracteres")
        return _sugerencia(ruta, "igual", x, f"{campo} = {describir(x)}")
    return None


def sugerir(datos, maximo=14):
    """El resultado (Ok y codigos de mensaje) marcado, y algunos valores y largos sin marcar.
    Cada sugerencia: {ruta, op, valor, descripcion, marcada}."""
    if not isinstance(datos, dict):
        return []
    if "filas" in datos and "cantidad" in datos:  # consulta SQL
        return _de_sql(datos)
    sug = []
    for k, v in datos.items():
        if not isinstance(v, dict):
            continue
        out = v.get("Output") if isinstance(v.get("Output"), dict) else None
        sug.extend(_de_resultado(k, out))
        for campo, x in v.items():
            if campo == "Output" or len(sug) >= maximo:
                continue
            s = _de_campo(f"{k}.{campo}", campo, x)
            if s:
                sug.append(s)
    return sug[:maximo]
