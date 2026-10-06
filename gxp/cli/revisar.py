"""Comando revisar: buenas practicas en el fuente GX de los objetos, el fuente reconstruido y las reglas."""
import json

from .consola import c, error, imprimir_json
from .. import kbs
from ..revisor import configuracion, fuente, revisor

SEV_COLOR = {"error": "rojo", "advertencia": "amarillo"}
MAX_SIN_DETALLE = 60  # con mas hallazgos que esto, sin --detalle se muestra un resumen


def _cmd_reglas():
    conf = configuracion.cargar()
    for cls in sorted(revisor.cargar_reglas().values(), key=lambda x: x.id):
        r = cls(conf.reglas.get(cls.id))
        estado = c("activa", "verde") if r.activa else c("inactiva", "gris")
        print(f"{c(r.id, 'negrita'):30} {estado}  {r.severidad:11} {r.titulo}")
        for k, v in r.conf.items():
            print(c(f"    {k}: {json.dumps(v, ensure_ascii=False)}", "gris"))
    for av in conf.avisos:
        print(c(av, "amarillo"))
    return 0


def _cmd_fuente(a):
    if not (a.kb and a.objeto):
        error("--fuente necesita --kb y --objeto.")
        return 2
    kb = kbs.obtener(a.kb)
    for o in a.objeto:
        ruta = fuente.ubicar(kb, o)
        if ruta is None:
            error(f"No encuentro la especificacion de '{o}' en {kb.nombre}.")
            return 2
        fu = fuente.leer(ruta)
        print(c(f"{fu.nombre}  ({fu.tipo_texto})", "negrita"))
        print(c(f"  parm({', '.join(f'{io} &{n}' for n, io in fu.parametros)})", "gris"))
        if fu.commit_on_exit is not None:
            print(c(f"  Commit on exit: {'Yes' if fu.commit_on_exit else 'No'}", "gris"))
        if fu.desconocidas:
            print(c(f"  sentencias con codigo desconocido: {sorted(fu.desconocidas)}", "amarillo"))
        if fu.ilegibles:
            print(c(f"  {fu.ilegibles} clausulas de la especificacion no se pudieron leer", "amarillo"))
        print(c(f"  {ruta}", "gris"))
        print(fu.texto())
    return 0


def cmd_revisar(a):
    if a.reglas:
        return _cmd_reglas()
    if a.fuente:
        return _cmd_fuente(a)
    if a.todas:
        lista = kbs.principales()
    elif a.kb:
        lista = [kbs.obtener(a.kb)]
    else:
        error("Indica --kb o --todas.")
        return 2
    hay_error = False
    resultados = []
    for kb in lista:
        res = revisor.revisar(kb, objetos=a.objeto, reglas=a.regla, cambiados=a.cambiados, guardar=not a.sin_guardar,
                              log=None if a.json else (lambda t: print(c(t, "gris"), flush=True)))
        resultados.append(res)
        hay_error |= res["totales"]["error"] > 0 or bool(res["errores"])
        if not a.json:
            imprimir_revision(res, todos=a.detalle or bool(a.objeto) or a.cambiados, detalle=a.detalle)
    if a.json:
        imprimir_json(resultados if len(resultados) > 1 else resultados[0])
    return 1 if hay_error else 0


def _imprimir_hallazgos(hs, detalle):
    por_obj = {}
    for h in hs:
        por_obj.setdefault(h["objeto"], []).append(h)
    for obj, lista in sorted(por_obj.items()):
        print(c(f"\n{obj}  ({lista[0]['tipo']})", "negrita"))
        explicados = set()  # el "como se arregla" se muestra una vez por objeto
        for h in sorted(lista, key=lambda x: x["linea"]):
            donde = f"linea {h['linea']}" if h["linea"] else "propiedad"
            marca = c("NUEVO ", "negrita") if h.get("nuevo") else ""
            print(f"  {c(h['severidad'].upper(), SEV_COLOR[h['severidad']]):11} {donde:10} {marca}{h['mensaje']}  {c('[' + h['regla'] + ']', 'gris')}")
            if h["codigo"]:
                print(c(f"  {'':11} {h['linea']:>5} | {h['codigo'][:150]}", "gris"))
            if detalle and h["detalle"] and h["detalle"] not in explicados:
                explicados.add(h["detalle"])
                print(c(f"  {'':11} {h['detalle']}", "gris"))


def _imprimir_totales(res):
    hs = res["hallazgos"]
    t = res["totales"]
    objetos = len({h["objeto"] for h in hs})
    color = "rojo" if t["error"] else ("amarillo" if t["advertencia"] else "verde")
    n = res.get("nuevos") or {}
    nuevos = n.get("error", 0) + n.get("advertencia", 0)
    que = " cambiados desde la linea base" if res.get("modo") == "cambiados" else ""
    print(c(f"\n{res['kb']}: {res['revisados']} objetos{que} revisados; {t['error']} errores y {t['advertencia']} "
            f"advertencias en {objetos} objetos"
            + (f" ({n.get('error', 0)} errores y {n.get('advertencia', 0)} advertencias nuevos)" if nuevos else ""), color)
          + c(f"  ({len(res['excepcionados'])} cubiertos por excepciones, {len(res['ignorados'])} objetos ignorados)", "gris"))
    if res.get("lineaBaseActualizada") and res["revisados"]:
        print(c("  linea base actualizada: lo marcado ahora deja de contar como nuevo en la proxima revision", "gris"))


def _imprimir_resumen(res):
    for regla, n in sorted(res["porRegla"].items(), key=lambda x: -x[1]):
        print(f"  {regla}: {n}")
    modulos = {}
    for h in res["hallazgos"]:
        m = ".".join(h["objeto"].split(".")[:2])
        modulos[m] = modulos.get(m, 0) + 1
    print("  Por modulo: " + ", ".join(f"{m} {n}" for m, n in sorted(modulos.items(), key=lambda x: -x[1])[:12]))
    print(c("  Con --detalle se ven todos; con --objeto, los de un objeto.", "gris"))


def imprimir_revision(res, todos, detalle):
    """Resultado de revisor.revisar para la consola: los hallazgos (o un resumen si son muchos) y los totales."""
    mostrar = todos or len(res["hallazgos"]) <= MAX_SIN_DETALLE
    if mostrar:
        _imprimir_hallazgos(res["hallazgos"], detalle)
    for e in res["errores"]:
        print(c(f"  no se pudo revisar {e['objeto']}: {e['error']}", "rojo"))
    for av in res["avisos"]:
        print(c(f"  {av}", "amarillo"))
    _imprimir_totales(res)
    if not mostrar:
        _imprimir_resumen(res)
    if res.get("archivo"):
        print(c(f"  resultado: {res['archivo']}", "gris"))


def registrar(sub):
    p = sub.add_parser("revisar", help="revisa las buenas practicas en el fuente GX de los objetos")
    p.add_argument("--kb")
    p.add_argument("--todas", action="store_true", help="todas las KBs")
    p.add_argument("--objeto", action="append", help="solo este objeto (se puede repetir)")
    p.add_argument("--regla", action="append", help="solo esta regla (se puede repetir)")
    p.add_argument("--cambiados", action="store_true", help="solo los objetos que cambiaron desde la ultima revision (los de un build)")
    p.add_argument("--fuente", action="store_true", help="muestra el fuente GX del objeto, sin revisar")
    p.add_argument("--reglas", action="store_true", help="lista las reglas y su configuracion")
    p.add_argument("--detalle", action="store_true", help="todos los hallazgos, con como arreglarlos")
    p.add_argument("--json", action="store_true")
    p.add_argument("--sin-guardar", action="store_true", help="no guarda el resultado en resultados/revisiones")
    p.set_defaults(fn=cmd_revisar)
