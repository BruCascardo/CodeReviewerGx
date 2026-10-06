"""Reportes de una corrida: totales, texto de las fallas de un caso (consola, notificaciones) y JUnit XML."""
from xml.sax.saxutils import escape, quoteattr

from ..comparacion import describir, texto_grupo


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
