"""Textos del resultado de un build: el resumen de una linea (interfaz, notificacion), las lineas para la
consola y el contenido de la notificacion de Windows."""


def texto_revision(rev):
    if rev.get("error"):
        return "no se pudo revisar las buenas prácticas"
    e, a = (rev.get("nuevos") or {}).get("error", 0), (rev.get("nuevos") or {}).get("advertencia", 0)
    if e and a:
        return f"{e} error{'es' if e > 1 else ''} y {a} advertencia{'s' if a > 1 else ''} nuevos de buenas prácticas"
    if e:
        return f"{e} error nuevo de buenas prácticas" if e == 1 else f"{e} errores nuevos de buenas prácticas"
    if a:
        return f"{a} advertencia nueva de buenas prácticas" if a == 1 else f"{a} advertencias nuevas de buenas prácticas"
    if rev.get("modo") == "completa":
        return "buenas prácticas: línea base armada"
    return "buenas prácticas: nada nuevo"


def texto_resumen(res):
    t = res["totales"]
    if not res["corridas"] and not res["errores"]:
        partes = ["no hay suites" + (f" con casos de la etiqueta '{res['etiqueta']}'" if res.get("etiqueta") else "")]
    else:
        partes = [f"{t['ok']} ok"]
        if t["falla"]:
            partes.append(f"{t['falla']} con fallas")
        if t["error"]:
            partes.append(f"{t['error']} con errores")
        if res["errores"]:
            partes.append(f"{len(res['errores'])} suite(s) sin poder correr")
    if res.get("revision"):
        partes.append(texto_revision(res["revision"]))
    return ", ".join(partes)


def lineas_consola(res):
    """Resumen para imprimir en la consola."""
    marca = {"ok": "OK", "falla": "FALLAS", "sin_pruebas": "SIN PRUEBAS"}.get(res["estado"], res["estado"].upper())
    lineas = [f"[despues del build] {res['kb']}: {marca} - {res['texto']}"]
    for f in res["fallas"][:10]:
        lineas.append(f"  {f['estado'].upper():5} {f['suite']} > {f['caso']}")
        lineas.extend("        " + l for l in f["detalle"].splitlines()[:8])
    if len(res["fallas"]) > 10:
        lineas.append(f"  ... y {len(res['fallas']) - 10} casos mas")
    lineas.extend(f"  no se pudo correr {e}" for e in res["errores"])
    for c in res["corridas"]:
        lineas.append(f"  resultado: resultados\\{c['id']}.json")
    rev = res.get("revision")
    if rev:
        if rev.get("error"):
            lineas.append(f"  buenas practicas: no se pudo revisar: {rev['error']}")
        else:
            t, n = rev["totales"], rev["nuevos"]
            ya = t["error"] + t["advertencia"] - n["error"] - n["advertencia"]
            lineas.append(f"  buenas practicas: {rev['revisados']} objetos del build revisados; {n['error']} errores y "
                          f"{n['advertencia']} advertencias nuevos" + (f" ({ya} que ya estaban)" if ya else ""))
            for h in rev["primeros"]:
                donde = f"linea {h['linea']}" if h["linea"] else "propiedad"
                lineas.append(f"    NUEVO {h['severidad'].upper():11} {h['objeto']} {donde}: {h['mensaje']}")
            lineas.extend(f"    no se pudo revisar {e}" for e in rev.get("errores", []))
            if rev.get("archivo"):
                lineas.append(f"  revision: {rev['archivo']}")
    return lineas


def notificacion(res, url_base):
    """(titulo, lineas, url) de la notificacion de Windows. El clic abre la corrida que conviene ver."""
    ok = res["estado"] == "ok"
    titulo = f"{'✔' if ok else '✖'} Build de {res['kb']}: {res['texto']}"
    lineas = []
    primeros = (res.get("revision") or {}).get("primeros") or []
    if res["fallas"]:
        f = res["fallas"][0]
        lineas.append(f"{f['suite']} › {f['caso']}" + (f" (y {len(res['fallas']) - 1} más)" if len(res["fallas"]) > 1 else ""))
    elif res["errores"]:
        lineas.append(res["errores"][0][:200])
    elif primeros:
        h = primeros[0]
        donde = f" línea {h['linea']}" if h["linea"] else ""
        lineas.append(f"{h['objeto']}{donde}: {h['mensaje']}")
    url = f"{url_base}#corrida={res['corridaVer']}" if url_base and res.get("corridaVer") else url_base
    return titulo, lineas, url
