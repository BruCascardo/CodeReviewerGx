"""Suite de prueba rapida de las pantallas de una KB (comando 'generar --pantallas').

Un caso por Web Panel que se abre sin parametros: lo abre en el motor de pantallas (sin Tomcat ni login, sin
grabar nada) y falla si la pantalla da una excepcion o un error HTTP. Corre despues de cada build con las demas
suites: avisa si un cambio rompio una pantalla que nadie abrio.

Se escribe en suites/<KB>/auto-pantallas.json, con las etiquetas 'auto' y 'pantalla' y sin salida aprobada: asi
solo controla que abra. Aprobando la salida ('correr --grabar') ademas se compara la estructura de lo que muestra
(variables y columnas de la grilla), no los datos. Al regenerar, los casos que ya existen quedan como estan.
"""
import re
import time

from .. import catalogo, pantallas_pasos
from ..motor import MotorError
from ..suites import almacen

SUITE = "auto-pantallas"
ETIQUETAS = ["auto", "pantalla"]
LIMITE_MS = 15000
# Generados por GAM y WorkWithPlus (paginas de administracion, popups de filtros): no son de la aplicacion.
EXCLUIR = re.compile(r"^(GAM|WWPBaseObjects\.|WorkWithPlus|GeneXus\.)", re.I)
DESCRIPCION = ("Generada por 'gxpruebas.py generar --pantallas': un caso por Web Panel que se abre sin parametros. "
               "Lo abre en el motor de pantallas (sin grabar nada) y falla si da una excepcion o un error HTTP. "
               "Para dejar uno afuera, marcalo con 'omitir' (no lo borres: al regenerar vuelve).")


def suite_id(kb):
    return f"{kb.nombre}/{SUITE}"


def candidatos(kb):
    """(Web Panels que se abren sin parametros, {objeto: motivo de exclusion})."""
    lista, excluidos = [], {}
    for o in catalogo.objetos(kb, solo_ejecutables=True, con_web=True):
        if o["tipo"] != "WebPanel":
            continue
        n = o["nombre"]
        if o.get("master"):
            excluidos[n] = "master page"
        elif EXCLUIR.search(n):
            excluidos[n] = "generado (GAM / WorkWithPlus)"
        elif any(p["io"] != "out" for p in o["parametros"]):
            excluidos[n] = "tiene parametros de entrada"
        else:
            lista.append(o)
    return lista, excluidos


def generar_kb(kb, log=print):
    """Genera (o completa) la suite auto-pantallas de la KB. Devuelve el informe."""
    t0 = time.time()
    lista, excluidos = candidatos(kb)
    try:
        previa = almacen.cargar(suite_id(kb))
    except KeyError:
        previa = {}
    vigentes = {o["nombre"].lower() for o in lista}
    casos = [c for c in previa.get("casos") or []
             if {(p.get("pantalla") or "").lower() for p in c.get("pasos") or []} <= vigentes]
    ya = {(p.get("pantalla") or "").lower() for c in casos for p in c.get("pasos") or []}
    nuevos = [o for o in lista if o["nombre"].lower() not in ya]
    log(f"{kb.nombre}: {len(lista)} pantallas sin parametros ({len(excluidos)} descartadas); {len(ya)} ya tenian caso, "
        f"se prueban {len(nuevos)}")
    informe = {"kb": kb.nombre, "descartados": dict(excluidos), "casos": 0}
    with pantallas_pasos.CasoDePantallas(kb) as caso:
        for i, o in enumerate(nuevos, 1):
            paso = {"nombre": "Abrir", "pantalla": o["nombre"], "parametros": []}
            try:
                t = time.time()
                r, _ = pantallas_pasos.ejecutar_paso(kb, paso, LIMITE_MS * 2)
                ms = (time.time() - t) * 1000
            except MotorError as e:
                informe["descartados"][o["nombre"]] = f"el motor fallo: {e}"[:300]
                continue
            finally:
                caso.m.pedir("pantalla_reiniciar", sesiones=True)
            if not r.get("ok"):
                informe["descartados"][o["nombre"]] = (r.get("error") or "error")[:300]
            elif ms > LIMITE_MS:
                informe["descartados"][o["nombre"]] = f"tarda {int(ms)} ms"
            else:
                casos.append({"id": almacen.slug(o["nombre"]), "nombre": f"{o['nombre']} abre", "etiquetas": list(ETIQUETAS),
                              "pasos": [paso]})
            if i % 25 == 0 or i == len(nuevos):
                log(f"  {i}/{len(nuevos)}  ({int(time.time() - t0)} s)")
    if casos:
        opciones = previa.get("opciones") or {}
        almacen.guardar(suite_id(kb), {"nombre": f"Auto - Pantallas de {kb.nombre}", "kb": kb.nombre, "descripcion": DESCRIPCION,
                                       "opciones": {**opciones, "transaccion": "rollback"}, "variables": previa.get("variables") or {},
                                       "preparacion": [], "casos": sorted(casos, key=lambda c: c["id"])})
    informe["casos"] = len(casos)
    informe["segundos"] = int(time.time() - t0)
    malas = {n: m for n, m in informe["descartados"].items() if n.lower() in vigentes}
    log(f"{kb.nombre}: {len(casos)} pantallas en {suite_id(kb)} ({informe['segundos']} s)"
        + (f"; {len(malas)} no abren:" if malas else ""))
    for n, m in sorted(malas.items())[:30]:
        log(f"    {n}: {m.splitlines()[0][:160]}")
    return informe
