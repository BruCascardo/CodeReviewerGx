"""Reportes de una corrida: totales, texto de las fallas de un caso (consola, notificaciones) y JUnit XML."""
from xml.sax.saxutils import escape, quoteattr

from ..comparacion import describir, texto_grupo


NUEVA, ARREGLADA, SIGUE = "nueva", "arreglada", "sigue"
_MAL = ("falla", "error")


def cambio(anterior, actual):
    """Que le paso a un caso respecto de su corrida anterior, segun el estado de antes y el de ahora:
    NUEVA (andaba y ahora no), ARREGLADA (no andaba y ahora si), SIGUE (seguia sin andar) o None (sin cambio, o sin
    un estado anterior con el que comparar: un caso que se corre por primera vez no es una falla nueva)."""
    if actual in _MAL:
        return NUEVA if anterior == "ok" else SIGUE if anterior in _MAL else None
    return ARREGLADA if actual == "ok" and anterior in _MAL else None


def cambios(casos):
    """Cuantos casos de la corrida tienen cada cambio: {"nueva": n, "arreglada": n, "sigue": n}."""
    t = dict.fromkeys((NUEVA, ARREGLADA, SIGUE), 0)
    for c in casos:
        if c.get("cambio"):
            t[c["cambio"]] += 1
    return t


def totales(casos):
    t = {"ok": 0, "falla": 0, "error": 0, "omitido": 0}
    for c in casos:
        t[c["estado"]] = t.get(c["estado"], 0) + 1
    return t


def _lineas_paso(p):
    lineas = [f"Paso '{p['nombre']}': {p['estado'].upper()}"]
    if p.get("error"):
        lineas.append(f"  error: {p['error']}")
    if p.get("resumen"):
        for g in p["resumen"]:
            org = " [salida aprobada]" if g.get("origen") == "lineaBase" else ""
            lineas.append(f"  {texto_grupo(g)}{org}")
    else:
        for d in p.get("diferencias", []):
            org = " (linea base)" if d.get("origen") == "lineaBase" else ""
            lineas.append(f"  {d['ruta']}{org}: esperado {describir(d['esperado'])}, obtenido {describir(d['obtenido'])}"
                          + (f" - {d['mensaje']}" if d.get("mensaje") else ""))
    for v in p.get("verificaciones", []):
        if not v["ok"]:
            lineas.append(f"  {v['ruta']} {v['op']} {describir(v['valor'])}: obtenido {describir(v['obtenido'])} - {v['mensaje']}")
    lineas.extend(f"  aviso: {a}" for a in p.get("advertencias", []))
    return lineas


def texto_fallas(caso, max_lineas=40) -> str:
    """Lo que salio mal en un caso (y los avisos), en lineas legibles."""
    lineas = []
    for p in caso.get("pasos", []):
        if p["estado"] in ("ok", "omitido"):
            lineas.extend(f"  aviso ({p['nombre']}): {a}" for a in p.get("advertencias", []))
        else:
            lineas.extend(_lineas_paso(p))
    lineas.extend(f"  aviso: {a}" for a in caso.get("advertencias", []))
    if len(lineas) > max_lineas:
        lineas = lineas[:max_lineas] + [f"  ... ({len(lineas) - max_lineas} lineas mas)"]
    return "\n".join(lineas)


def junit(corridas) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?>', "<testsuites>"]
    for c in corridas:
        t = c.get("totales") or totales(c["casos"])
        out.append(f'  <testsuite name={quoteattr(c["suiteNombre"])} tests="{len(c["casos"])}" failures="{t["falla"]}" '
                   f'errors="{t["error"]}" skipped="{t["omitido"]}" time="{c.get("ms", 0) / 1000:.3f}">')
        for caso in c["casos"]:
            out.append(f'    <testcase classname={quoteattr(c["suite"])} name={quoteattr(caso["nombre"])} time="{caso["ms"] / 1000:.3f}">')
            detalle = texto_fallas(caso)
            if caso["estado"] == "falla":
                out.append(f'      <failure message="fallo">{escape(detalle)}</failure>')
            elif caso["estado"] == "error":
                out.append(f'      <error message="error">{escape(detalle)}</error>')
            elif caso["estado"] == "omitido":
                out.append("      <skipped/>")
            out.append("    </testcase>")
        out.append("  </testsuite>")
    out.append("</testsuites>")
    return "\n".join(out)
