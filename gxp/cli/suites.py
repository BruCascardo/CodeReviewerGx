"""Comandos de pruebas: correr, suites, vigilar (despues de cada build) y generar (suites de regresion)."""
import sys
import time
from pathlib import Path

from .consola import c, error, imprimir_json
from .. import kbs, motor, suites
from ..config import CFG


def _texto_script(sp):
    """Una linea con el resultado del script previo (y, si fallo, el error)."""
    n = sum(len(b["sentencias"]) for b in sp["bloques"])
    filas = sum(s.get("actualizadas") or 0 for b in sp["bloques"] for s in b["sentencias"])
    if sp["estado"] == "ok":
        return c(f"  script previo: {n} sentencias, {filas} filas cambiadas, {sp['ms']} ms", "gris")
    return c(f"  script previo con error: {sp.get('error')}", "rojo")


def _imprimir_progreso(detalle):
    """Funcion de progreso para correr_suite: imprime cada caso a medida que termina (y el script previo)."""
    vistos = [0]
    veces = [0]
    marcas = {"ok": c("OK   ", "verde"), "falla": c("FALLA", "rojo"), "error": c("ERROR", "rojo"), "omitido": c("OMIT ", "gris")}

    def progreso(cor):
        sp = cor.get("scriptPrevio")
        if sp and sp.get("veces", 1) != veces[0]:
            veces[0] = sp.get("veces", 1)
            print(_texto_script(sp))
        for caso in cor["casos"][vistos[0]:]:
            print(f"  {marcas[caso['estado']]} {caso['nombre']}  {c(str(caso['ms']) + ' ms', 'gris')}")
            if caso["estado"] in ("falla", "error") or (detalle and caso["estado"] != "omitido"):
                det = suites.texto_fallas(caso)
                if det:
                    print("\n".join("        " + linea for linea in det.splitlines()))
        vistos[0] = len(cor["casos"])
    return progreso


def cmd_correr(a):
    try:
        ids = suites.almacen.resolver(a.suites, a.kb)
    except ValueError as e:
        error(str(e))
        return 1
    if not ids:
        error("No hay suites para correr.")
        return 2
    corridas = []
    total = {"ok": 0, "falla": 0, "error": 0, "omitido": 0}
    for sid in ids:
        if not a.json:
            print(c(f"\n== {sid}", "negrita"))
        try:
            cor = suites.correr_suite(sid, etiqueta=a.etiqueta, filtro=a.filtro, grabar=a.grabar,
                                      progreso=None if a.json else _imprimir_progreso(a.detalle))
        except (motor.MotorError, KeyError, ValueError) as e:
            print(c(f"  No se pudo correr: {e}", "rojo"), file=sys.stderr)
            total["error"] += 1
            continue
        corridas.append(cor)
        if cor.get("encadenados") and (a.filtro or a.etiqueta) and not a.json:
            print(c("  Los casos de esta suite estan encadenados: si corriste solo algunos, los que dependen de otros "
                    "pueden fallar.", "amarillo"))
        for k, v in cor["totales"].items():
            total[k] = total.get(k, 0) + v
        if a.grabar and not a.json:
            print(c(f"  {cor['lineasBaseGrabadas']} salidas aprobadas", "amarillo"))
    if a.junit:
        Path(a.junit).write_text(suites.junit(corridas), encoding="utf-8")
    if a.json:
        imprimir_json({"totales": total, "corridas": corridas})
    else:
        color = "verde" if total["falla"] == 0 and total["error"] == 0 else "rojo"
        print(c(f"\nTotal: {total['ok']} ok, {total['falla']} con fallas, {total['error']} con errores, {total['omitido']} omitidos", color))
        for co in corridas:
            print(c(f"  resultado: resultados\\{co['id']}.json", "gris"))
    return 0 if total["falla"] == 0 and total["error"] == 0 else 1


def cmd_suites(a):
    for s in suites.almacen.listar(a.kb):
        u = s.get("ultimo") or {}
        t = u.get("totales") or {}
        estado = f"{u.get('estado', '-')}: {t.get('ok', 0)} ok / {t.get('falla', 0)} falla / {t.get('error', 0)} error" if u else "sin correr"
        print(f"{s['id']:45} {s['casos']:4} casos   {estado}")


def cmd_vigilar(a):
    from .. import automatico
    conf = {**CFG["despuesDelBuild"]}
    if a.kb:
        conf["kbs"] = a.kb
    if a.etiqueta is not None:
        conf["etiqueta"] = a.etiqueta
    if a.espera:
        conf["esperaSeg"] = a.espera
    if a.sin_notificar:
        conf["notificar"] = False
    if not conf.get("kbs"):
        error("Indica --kb (o 'kbs' en 'despuesDelBuild' de config.json).")
        return 2

    def al_terminar(res):
        lineas = automatico.lineas_consola(res)
        print(c(lineas[0], "verde" if res["estado"] == "ok" else "rojo"))
        print("\n".join(lineas[1:]), flush=True)

    ok, msg = automatico.iniciar(conf, al_terminar)
    print(msg if ok else c(msg, "rojo"))
    if not ok:
        return 2
    print(c("Esperando builds de GeneXus... (Ctrl+C para salir)", "gris"))
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_generar(a):
    from .. import generacion
    from ..efectos import Analisis
    if a.todas:
        lista = kbs.principales()
    elif a.kb:
        lista = [kbs.obtener(n) for n in a.kb]
    else:
        error("Indica --kb (se puede repetir) o --todas.")
        return 2
    analisis = Analisis()
    for kb in lista:
        try:
            generacion.generar_kb(kb, analisis, log=lambda t: print(t, flush=True), solo=a.solo)
        except motor.MotorError as e:
            print(c(f"{kb.nombre}: no se pudo generar: {e}", "rojo"), file=sys.stderr)
        motor.motor(kb).detener("fin de la generacion")
    print(c("\nLas suites quedan sin salida aprobada. Revisalas y aprobalas con: "
            "python gxpruebas.py correr --kb <KB> --etiqueta auto --grabar", "amarillo"))
    return 0


def registrar(sub):
    p = sub.add_parser("correr", help="corre suites")
    p.add_argument("suites", nargs="*")
    p.add_argument("--kb")
    p.add_argument("--etiqueta")
    p.add_argument("--filtro")
    p.add_argument("--grabar", action="store_true", help="graba las salidas como linea base")
    p.add_argument("--junit")
    p.add_argument("--json", action="store_true")
    p.add_argument("--detalle", action="store_true")
    p.set_defaults(fn=cmd_correr)

    p = sub.add_parser("vigilar", help="corre las suites despues de cada build de GeneXus (sin la interfaz)")
    p.add_argument("--kb", action="append", help="KB a vigilar (se puede repetir; '*' = todas). Por defecto, las de config.json")
    p.add_argument("--etiqueta", help="solo los casos con esta etiqueta")
    p.add_argument("--espera", type=int, help="segundos sin cambios en el build antes de correr")
    p.add_argument("--sin-notificar", action="store_true", help="sin notificacion de Windows")
    p.set_defaults(fn=cmd_vigilar)

    p = sub.add_parser("generar", help="genera suites de regresion para los objetos de solo lectura")
    p.add_argument("--kb", action="append", help="KB (se puede repetir)")
    p.add_argument("--todas", action="store_true", help="todas las KBs")
    p.add_argument("--solo", help="regenera solo los objetos cuyo nombre contiene este texto")
    p.set_defaults(fn=cmd_generar)

    p = sub.add_parser("suites", help="lista las suites")
    p.add_argument("--kb")
    p.set_defaults(fn=cmd_suites)
