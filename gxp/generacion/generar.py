"""Genera suites de regresion para los objetos de solo lectura de una KB (comando 'generar').

1. Candidatos: los procedimientos y Data Providers sin efectos (gxp/efectos.py: no escriben en la base, no
   hacen commit ni rollback, no usan HTTP, mail, archivos, shell ni submit, contando todo lo que llaman).
   Se dejan afuera los generados por WorkWithPlus y GAM y los que devuelven el proximo id.
2. Entrada: la plantilla de 'describir', completada con una fila real de la base (esquema.py). Cada objeto
   queda con un caso con esos datos y otro con la entrada vacia (si da otra salida).
3. Ejecuta cada entrada (con rollback) y se queda con las que terminan sin excepcion y en poco tiempo.
4. Escribe suites/<KB>/auto-<modulo>.json con la etiqueta 'auto' y sin salida aprobada: se aprueba con
   'correr --grabar'. Al regenerar, los casos que ya existen quedan como estan (con su salida aprobada,
   'omitir', etc.); se agregan los objetos nuevos y se sacan los que ya no son de solo lectura.
"""
import json
import re
import time

from .esquema import Esquema, entrada_real
from .. import catalogo
from ..config import CACHE
from ..efectos import Analisis, separar
from ..motor import MotorError, describir, ejecutar_objeto, fin_transaccion
from ..suites import almacen
from ..util import escribir_json

ETIQUETA = "auto"
PREFIJO = "auto-"
LIMITE_MS = 10000          # mas lento que esto no entra: las suites corren en cada build
MAX_BYTES = 2_000_000      # salida mas grande que esto no entra
LISTA_ESTRUCTURA = 50      # con una lista de mas elementos se compara solo la estructura (datos que cambian)
MIN_CASOS_SUITE = 10       # los modulos con menos casos van a la suite <KB>.Otros
# Generados por WorkWithPlus o GAM, y los que devuelven el proximo id (cambian con cada alta).
EXCLUIR_NOMBRE = re.compile(r"LoadDVCombo$|^WWPBaseObjects\.|^WorkWithPlus|^GAM|ultsec$|secuencia", re.I)
DESCRIPCION_SUITE = ("Generada por 'gxpruebas.py generar': objetos de solo lectura (no escriben en la base, no hacen "
                     "commit ni tienen efectos externos, contando lo que llaman). Controla que la salida no cambie "
                     "respecto de la aprobada. Para dejar un caso afuera, marcalo con 'omitir' (no lo borres: "
                     "al regenerar vuelve).")


def candidatos(kb, analisis=None):
    """(objetos de solo lectura, {objeto: motivo de exclusion})."""
    analisis = analisis or Analisis()
    lista, excluidos = [], {}
    for o in catalogo.objetos(kb, solo_ejecutables=True):
        n = o["nombre"]
        if EXCLUIR_NOMBRE.search(n.split(".")[-1]) or EXCLUIR_NOMBRE.search(n):
            excluidos[n] = "generado (WorkWithPlus/GAM) o devuelve el proximo id"
            continue
        if not any(p["io"] in ("out", "inout") for p in o["parametros"]):
            excluidos[n] = "no tiene parametros de salida: no hay nada que comparar"
            continue
        motivo = catalogo.motivo_no_ejecutable(kb, o)
        if motivo:
            excluidos[n] = motivo
            continue
        ef, remotas = separar(analisis.efectos(kb, n))
        if ef:
            excluidos[n] = ", ".join(f"{m} ({c})" for m, c in sorted(ef.items()))
            continue
        lista.append({**o, "remotas": remotas})
    return lista, excluidos


def _max_lista(v):
    if isinstance(v, list):
        return max([len(v)] + [_max_lista(x) for x in v])
    if isinstance(v, dict):
        return max([0] + [_max_lista(x) for x in v.values()])
    return 0


def probar(kb, objeto, entrada):
    """Ejecuta con rollback. Devuelve {ok, ms, error, datos}."""
    t0 = time.time()
    try:
        r, datos, _ = ejecutar_objeto(kb, objeto, entrada, LIMITE_MS + 5000)
    except (KeyError, ValueError, MotorError) as e:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "error": str(e)[:300]}
    finally:
        fin_transaccion(kb, "rollback")
    ms = r.get("ms") or (time.time() - t0) * 1000
    if not r.get("ok"):
        return {"ok": False, "ms": ms, "error": ("timeout: " if r.get("timeout") else "") + (r.get("error") or "excepcion")[:300]}
    return {"ok": True, "ms": ms, "datos": datos}


def _grupo(nombre):
    """Modulo de un objeto (los dos primeros tramos del nombre): una suite por modulo."""
    partes = nombre.split(".")
    return ".".join(partes[:2]) if len(partes) > 2 else (partes[0] if len(partes) == 2 else "General")


def _casos_existentes(kb, vigentes, solo):
    """Los casos de las suites auto-* que quedan como estan: los de objetos que siguen siendo de solo lectura
    (y, con 'solo', los que no se regeneran). Devuelve ({grupo: [casos]}, {objetos que ya tienen casos})."""
    grupos, ya = {}, set()
    for sid in almacen.ids_de(kb.nombre, PREFIJO):
        try:
            s = almacen.cargar(sid)
        except (KeyError, ValueError):
            continue
        for c in s["casos"]:
            objs = {(x.get("objeto") or "").lower() for x in c.get("pasos") or []} - {""}
            if not objs or not objs <= vigentes:
                continue
            if solo and any(solo.lower() in x for x in objs):
                continue
            grupos.setdefault(_grupo(c["pasos"][0]["objeto"]), []).append(c)
            ya |= objs
    return grupos, ya


def _casos_de_objeto(kb, o, esquema, informe):
    """Casos de un objeto: con datos reales y con la entrada vacia. Devuelve (casos, motivos si no hubo)."""
    n = o["nombre"]
    try:
        d = describir(kb, n)
    except (MotorError, KeyError, ValueError) as e:
        return [], [f"describir: {e}"[:300]]
    if not d["coincide"]:
        return [], ["el Java compilado no coincide con la especificacion (compilar la KB)"]
    plantilla = d["plantillaEntrada"]
    variantes = []
    if plantilla:
        origen, real = entrada_real(esquema, plantilla)
        if real:
            variantes.append(("", f"datos de {origen}", real))
        else:
            informe["sinEntradaReal"].append(n)
        variantes.append(("-vacia", "entrada vacia", plantilla))
    else:
        variantes.append(("", "sin parametros de entrada", {}))
    casos, salidas, motivos = [], [], []
    for sufijo, desc, entrada in variantes:
        r = probar(kb, n, entrada)
        if not r["ok"]:
            motivos.append(f"{desc}: {r['error']}")
            continue
        if r["ms"] > LIMITE_MS:
            motivos.append(f"{desc}: tarda {int(r['ms'])} ms")
            continue
        texto = json.dumps(r["datos"], ensure_ascii=False, sort_keys=True)
        if len(texto) > MAX_BYTES:
            motivos.append(f"{desc}: salida de {len(texto) // 1000} KB")
            continue
        if texto in salidas:
            continue  # da lo mismo que la otra entrada
        salidas.append(texto)
        casos.append(_caso(n, sufijo, desc, entrada, o["remotas"], r["datos"]))
    return casos, motivos


def _caso(nombre, sufijo, desc, entrada, remotas, datos):
    paso = {"nombre": "Ejecutar", "objeto": nombre, "entrada": entrada}
    nota = "Caso generado: la salida aprobada es la de la KB al generarlo."
    if remotas:
        paso["comparar"] = "estructura"
        nota += (f" Lee de bases compartidas ({', '.join(remotas)}), cuyos datos cambian solos: "
                 "se compara solo la estructura.")
    elif _max_lista(datos) > LISTA_ESTRUCTURA:
        paso["comparar"] = "estructura"
        nota += f" Devuelve listas de mas de {LISTA_ESTRUCTURA} elementos: se compara solo la estructura."
    return {"id": almacen.slug(nombre) + sufijo, "nombre": f"{nombre} ({desc})", "etiquetas": [ETIQUETA],
            "descripcion": nota, "pasos": [paso]}


def _escribir_suites(kb, grupos):
    """Una suite por modulo; los modulos con pocos casos van juntos (cada suite es una corrida en el
    Historial, que guarda las ultimas 300). Las suites auto-* que quedaron sin casos se borran.
    Devuelve (ids escritos, cantidad de casos)."""
    juntos = {}
    for g, casos in grupos.items():
        juntos.setdefault(g if len(casos) >= MIN_CASOS_SUITE else f"{kb.nombre}.Otros", []).extend(casos)
    escritas, total = set(), 0
    for g, casos in sorted(juntos.items()):
        sid = f"{kb.nombre}/{PREFIJO}{almacen.slug(g)}"
        try:
            previa = almacen.cargar(sid)
        except KeyError:
            previa = {}
        opciones = previa.get("opciones") or {}
        almacen.guardar(sid, {"nombre": f"Auto - {g}", "kb": kb.nombre, "descripcion": DESCRIPCION_SUITE,
                              "opciones": {**opciones, "transaccion": "rollback", "timeoutMs": opciones.get("timeoutMs", 30000)},
                              "variables": previa.get("variables") or {}, "preparacion": previa.get("preparacion") or [],
                              "casos": sorted(casos, key=lambda c: c["id"])})
        escritas.add(sid)
        total += len(casos)
    for sid in almacen.ids_de(kb.nombre, PREFIJO):
        if sid not in escritas:
            almacen.borrar(sid)
    return escritas, total


def generar_kb(kb, analisis=None, log=print, solo=None):
    """Genera (o completa) las suites auto-* de la KB. Devuelve el informe."""
    t0 = time.time()
    lista, excluidos = candidatos(kb, analisis)
    vigentes = {o["nombre"].lower() for o in lista}
    if solo:
        lista = [o for o in lista if solo.lower() in o["nombre"].lower()]
    log(f"{kb.nombre}: {len(lista)} objetos de solo lectura ({len(excluidos)} descartados por el analisis)")
    # Los casos que ya existen quedan como estan (con su salida aprobada), salvo los de objetos que ya no
    # son de solo lectura o no existen mas. Con 'solo', se regeneran solo esos objetos.
    grupos, ya = _casos_existentes(kb, vigentes, solo)
    esquema = Esquema(kb)
    informe = {"kb": kb.nombre, "fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "casos": 0, "objetos": len(ya),
               "descartados": dict(excluidos), "sinEntradaReal": []}
    lista = [o for o in lista if o["nombre"].lower() not in ya]
    log(f"  {len(ya)} ya tenian casos; se generan {len(lista)}")
    for i, o in enumerate(lista, 1):
        casos, motivos = _casos_de_objeto(kb, o, esquema, informe)
        if casos:
            grupos.setdefault(_grupo(o["nombre"]), []).extend(casos)
            informe["objetos"] += 1
        else:
            informe["descartados"][o["nombre"]] = "; ".join(motivos)
        if i % 25 == 0 or i == len(lista):
            log(f"  {i}/{len(lista)}  {informe['objetos']} con casos  ({int(time.time() - t0)} s)")
    escritas, informe["casos"] = _escribir_suites(kb, grupos)
    informe["suites"] = sorted(escritas)
    informe["segundos"] = int(time.time() - t0)
    archivo = CACHE / f"generar-{almacen.slug(kb.nombre)}.json"
    escribir_json(archivo, informe, sangria=1)
    log(f"{kb.nombre}: {informe['casos']} casos de {informe['objetos']} objetos en {len(escritas)} suites "
        f"({informe['segundos']} s). Informe: .cache\\{archivo.name}")
    return informe
