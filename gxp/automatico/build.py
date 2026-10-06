"""Lo que se hace con cada build: revisar las buenas practicas de lo que cambio y correr las suites de la KB."""
import datetime as dt

from .resumen import texto_resumen
from .. import suites
from ..revisor import revisor


def correr_kb(kb, etiqueta=""):
    """Corre las suites de la KB (si hay etiqueta, solo las que tienen casos con ella). Devuelve el resumen."""
    todas = suites.almacen.listar(kb.nombre)
    lista = [s for s in todas if not s.get("error") and (not etiqueta or etiqueta in s.get("etiquetas", []))]
    res = {"kb": kb.nombre, "etiqueta": etiqueta, "inicio": dt.datetime.now().isoformat(timespec="seconds"),
           "corridas": [], "totales": {"ok": 0, "falla": 0, "error": 0, "omitido": 0}, "errores": [], "fallas": []}
    # Una suite con el JSON roto no se puede correr: se informa en vez de saltearla en silencio.
    for s in todas:
        if s.get("error") and s["id"].lower().startswith(kb.nombre.lower() + "/"):
            res["errores"].append(f"{s['id']}: {s['error']}")
    for s in lista:
        try:
            cor = suites.correr_suite(s["id"], etiqueta=etiqueta or None, origen="build")
        except Exception as e:
            res["errores"].append(f"{s['id']}: {e}")
            continue
        res["corridas"].append({"id": cor["id"], "suite": s["id"], "nombre": cor["suiteNombre"], "estado": cor["estado"],
                                "totales": cor["totales"]})
        for k, v in cor["totales"].items():
            res["totales"][k] = res["totales"].get(k, 0) + v
        for caso in cor["casos"]:
            if caso["estado"] in ("falla", "error"):
                res["fallas"].append({"suite": cor["suiteNombre"], "caso": caso["nombre"], "estado": caso["estado"],
                                      "corrida": cor["id"], "detalle": suites.texto_fallas(caso, 12)})
    res["fin"] = dt.datetime.now().isoformat(timespec="seconds")
    t = res["totales"]
    if not lista and not res["errores"]:
        res["estado"] = "sin_pruebas"
    elif t["falla"] or t["error"] or res["errores"]:
        res["estado"] = "falla"
    else:
        res["estado"] = "ok"
    res["texto"] = texto_resumen(res)
    # La corrida que conviene abrir: la primera con fallas, o la primera.
    res["corridaVer"] = (res["fallas"][0]["corrida"] if res["fallas"]
                         else (res["corridas"][0]["id"] if res["corridas"] else None))
    return res


def revisar_kb(kb):
    """Revisa las buenas practicas de los objetos que el build volvio a especificar. Devuelve un resumen
    para el resultado del build (los hallazgos completos quedan en resultados/revisiones)."""
    try:
        r = revisor.revisar(kb, cambiados=True, origen="build")
    except Exception as e:  # la revision nunca frena las pruebas
        return {"error": f"{e}"}
    orden = {"error": 0, "advertencia": 1}
    nuevos = sorted((h for h in r["hallazgos"] if h["nuevo"]), key=lambda h: (orden[h["severidad"]], h["objeto"], h["linea"]))
    return {"archivo": r.get("archivo"), "modo": r["modo"], "revisados": r["revisados"], "totales": r["totales"],
            "nuevos": r["nuevos"], "errores": [f"{e['objeto']}: {e['error']}" for e in r["errores"][:5]],
            "primeros": [{k: h[k] for k in ("objeto", "linea", "severidad", "mensaje", "regla", "codigo")}
                         for h in nuevos[:10]]}


def agregar_revision(res, rev):
    """Suma la revision al resultado del build. Un error de buenas practicas nuevo cuenta como falla."""
    res["revision"] = rev
    if (rev.get("nuevos") or {}).get("error") and res["estado"] in ("ok", "sin_pruebas"):
        res["estado"] = "falla"
    res["texto"] = texto_resumen(res)


def hay_nuevos(rev):
    n = (rev or {}).get("nuevos") or {}
    return bool(n.get("error") or n.get("advertencia") or (rev or {}).get("error"))
