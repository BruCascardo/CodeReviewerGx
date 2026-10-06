"""Resumen legible de las diferencias: 'Registros[*].Importe: 100 -> 110 en 12 de 40 elementos'."""
from .rutas import obtener, patron_de
from .valores import describir


def _prioridad(g):
    """Primero lo que define el resultado: Ok y los mensajes."""
    r = g["ruta"].lower()
    if g["tipo"] == "clave" or r.endswith(".output.ok"):
        return 0
    if ".output.messages" in r:
        return 1
    return 2


def resumir(diffs, datos):
    """Agrupa las diferencias por ruta generica, con hasta 3 ejemplos y, en las listas, de cuantos elementos."""
    grupos = {}
    for d in diffs:
        p = patron_de(d["ruta"])
        g = grupos.setdefault((p, d["tipo"], d.get("origen")), {
            "ruta": p, "tipo": d["tipo"], "origen": d.get("origen"), "mensaje": d.get("mensaje", ""), "cantidad": 0, "ejemplos": []})
        g["cantidad"] += 1
        if len(g["ejemplos"]) < 3:
            g["ejemplos"].append({"ruta": d["ruta"], "esperado": d["esperado"], "obtenido": d["obtenido"]})
    salida = list(grupos.values())
    for g in salida:
        if "[*]" in g["ruta"]:
            prefijo = g["ruta"][:g["ruta"].rfind("[*]") + 3]
            existe, v, _ = obtener(datos, prefijo)
            g["de"] = len(v) if existe else None
    salida.sort(key=_prioridad)
    return salida


def texto_grupo(g):
    """Una linea legible para un grupo de diferencias."""
    ej = g["ejemplos"][0]
    if g.get("de") and g["cantidad"] > 1:
        cuantos = f" en {g['cantidad']} de {g['de']} elementos"
    else:
        cuantos = f" ({g['cantidad']} veces)" if g["cantidad"] > 1 else ""
    if g["tipo"] == "falta":
        que = "ya no esta"
    elif g["tipo"] == "sobra":
        que = f"aparecio: {describir(ej['obtenido'])}"
    elif g["tipo"] == "largo":
        que = f"tenia {ej['esperado']} elementos, ahora {ej['obtenido']}"
    else:
        que = f"{describir(ej['esperado'])} -> {describir(ej['obtenido'])}"
    extra = f" ({g['mensaje']})" if g.get("mensaje") and g["tipo"] in ("tipo", "clave") else ""
    return f"{g['ruta']}: {que}{cuantos}{extra}"
