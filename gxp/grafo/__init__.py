"""Grafo de objetos y relaciones de todas las KBs (pantalla 'Grafo' y comando 'grafo').

Nodos: procedimientos, Data Providers, transacciones, Web Panels, APIs y SDT de cada KB (de la especificacion
y del Java generado), y las tablas. Relaciones:
  - llama / transaccion / sdt: referencias en el Java generado de cada objeto (tambien entre KBs, por el
    namespace del paquete: com.terceros.* es de la KB Terceros).
  - lee / escribe: tablas de la navegacion (NVG) de la especificacion.
  - servicio: el objeto usa un id de servicio y la tabla de servicios dice que ese id es un procedimiento
    (los procedimientos de Servicios se llaman asi, no directamente). Ver servicios.py.

Origen de cada relacion y objeto:
  - L (local): sale de la KB local (fuentes Java y especificacion).
  - P (publicado): sale del .jar del modulo que las otras KBs tienen en build/libs (por ejemplo Terceros.jar
    con Implementation-Version 23.15.4). Es la version publicada del modulo: muestra relaciones que tiene la
    version publicada y la KB local no (porque la KB local esta atrasada o adelantada), sin leer CI.

Cada KB se guarda en .cache/grafo/kb-<kb>.json con la firma de su build: se rearma solo cuando GeneXus compila.
Los archivos Java ya leidos se recuerdan por fecha, asi que despues de un build solo se releen los que cambiaron.

  indices.py  que objeto es cada clase, referencias de cada archivo, modulos publicados (.jar)
  armado.py   armado del grafo de una KB
  servicios.py  llamadas por medio de la tabla de servicios (sitServicio)
"""
import re
import threading
import time

from .armado import VERSION_FORMATO, ArmadoKB, firma_kb, modulo
from . import servicios
from .indices import DIR, MemoriaArchivos, Universo
from .. import kbs, vigilancia
from ..util import escribir_json, leer_json

GENERADOS = re.compile(r"(^|\.)(WWPBaseObjects|WorkWithPlus\w*|GAM\w*)\.|^GAM|LoadDVCombo$|^WorkWithPlus|^WWPBaseObjects", re.I)
_lock = threading.RLock()
_estado = {"version": 0, "kbs": {}, "armando": None, "error": None, "ultimoCambio": None}


def _universos():
    """Un universo por raiz de KBs (CORE, FIXES): las referencias entre KBs se resuelven dentro de la raiz."""
    raices = {}
    for k in kbs.descubrir().values():
        raices.setdefault(str(k.carpeta.parent), []).append(k)
    return [Universo(lista) for lista in raices.values()]


def _archivo_kb(nombre):
    return DIR / f"kb-{re.sub(r'[^A-Za-z0-9_-]', '_', nombre)}.json"


def cargar_kb(nombre):
    d = leer_json(_archivo_kb(nombre))
    return d if d and d.get("formato") == VERSION_FORMATO else None


def armar_kb(kb, universo, log=lambda t: None, ids_servicio=frozenset()):
    """Datos del grafo de una KB (ver armado.py)."""
    return ArmadoKB(kb, universo).armar(MemoriaArchivos(kb.nombre, ids_servicio), log)


def actualizar(forzar=False, log=lambda t: None, solo=None):
    """Rearma las KBs cuyo build cambio (o todas con forzar). Devuelve la lista de KBs rearmadas.
    Con 'solo', las demas KBs se rearman solo si cambiaron los servicios conocidos (no su build)."""
    rearmadas = []
    ids = frozenset(servicios.dominio())
    fsrv = servicios.firma(ids)
    with _lock:
        for u in _universos():
            for kb in u.kbs.values():
                previo = _estado["kbs"].get(kb.nombre) or cargar_kb(kb.nombre)
                if not forzar and previo and previo.get("firma") == firma_kb(kb, fsrv):
                    _estado["kbs"][kb.nombre] = previo
                    continue
                if solo and kb.nombre not in solo and not (
                        previo and previo.get("firma") == firma_kb(kb, previo.get("firmaServicios", ""))):
                    if previo:
                        _estado["kbs"][kb.nombre] = previo
                    continue
                _estado["armando"] = kb.nombre
                try:
                    datos = armar_kb(kb, u, log, ids)
                except Exception as e:  # una KB rota no corta las demas
                    _estado["error"] = f"{kb.nombre}: {e}"
                    log(f"{kb.nombre}: error al armar el grafo: {e}")
                    continue
                finally:
                    _estado["armando"] = None
                escribir_json(_archivo_kb(kb.nombre), datos)
                _estado["kbs"][kb.nombre] = datos
                rearmadas.append(kb.nombre)
    # La tabla de servicios se relee despues de cada build (o si nunca se leyo), fuera del lock: levanta
    # el motor de la KB de la tabla.
    tabla_cambio = False
    if ids and (rearmadas or forzar or not servicios.hay_tabla()):
        antes = servicios.tabla()
        tabla_cambio = servicios.leer_tabla(log) is not None and servicios.tabla() != antes
    if rearmadas or tabla_cambio:
        with _lock:
            _estado["version"] += 1
            _estado["ultimoCambio"] = {"kbs": rearmadas or ["tabla de servicios"], "fecha": time.strftime("%H:%M:%S")}
    return rearmadas


def estado():
    return {"version": _estado["version"], "armando": _estado["armando"], "error": _estado["error"],
            "ultimoCambio": _estado["ultimoCambio"],
            "kbs": {n: {"fecha": d.get("fecha"), "nodos": len(d["nodos"]), "aristas": len(d["aristas"]),
                        "publicados": d.get("publicados")} for n, d in _estado["kbs"].items()}}


def poner_error(texto):
    _estado["error"] = texto


def compacto():
    """Todas las KBs juntas, en formato compacto para la interfaz: nodos como listas e indices en las aristas."""
    with _lock:
        datos = dict(_estado["kbs"])
    nodos, idx = [], {}
    duenas = {}
    # Duena de cada tabla: con preferencia, una KB de CORE (las de FIXES tienen las mismas tablas).
    for d in sorted(datos.values(), key=lambda d: "_fixes" in d["kb"].lower()):
        for tid, k in (d.get("duenasTablas") or {}).items():
            duenas.setdefault(tid, k)
    # Primero los nodos con datos propios (de su KB), despues los que solo aparecen como destino.
    for d in datos.values():
        for nid, n in d["nodos"].items():
            if n["kb"] == d["kb"] or n["tipo"] == "Tabla":
                if nid in idx:
                    if n["tipo"] == "Tabla":
                        continue
                    nodos[idx[nid]][5] = "".join(sorted(set(nodos[idx[nid]][5] + n["origen"])))
                    continue
                idx[nid] = len(nodos)
                kb_n = duenas.get(nid, "") if n["tipo"] == "Tabla" else n["kb"]
                nodos.append([kb_n, n["nombre"], n["tipo"], modulo(n["nombre"]) if n["tipo"] != "Tabla" else "",
                              n.get("descripcion", ""), n["origen"], 1 if GENERADOS.search(n["nombre"]) else 0])
    for d in datos.values():
        for nid, n in d["nodos"].items():
            if nid not in idx:
                idx[nid] = len(nodos)
                kb_n = n["kb"]
                nodos.append([kb_n, n["nombre"], n["tipo"] or "Objeto", modulo(n["nombre"]), "", n["origen"] or "?",
                              1 if GENERADOS.search(n["nombre"]) else 0])
    aristas = []
    for d in datos.values():
        for de, a, tipo, origen in d["aristas"]:
            if de in idx and a in idx:
                aristas.append([idx[de], idx[a], tipo, origen])
    universos = {n: str(kbs.obtener(n).carpeta.parent) for n in datos}
    aristas += _aristas_servicio(datos, nodos, idx, universos)
    return {"version": _estado["version"], "columnas": ["kb", "nombre", "tipo", "modulo", "descripcion", "origen", "generado"],
            "nodos": nodos, "aristas": aristas,
            "kbs": {n: {"fecha": d.get("fecha"), "publicados": d.get("publicados"), "universo": universos[n]}
                    for n, d in datos.items()}}


def _aristas_servicio(datos, nodos, idx, universos):
    """[de, a, "servicio", "L", id del servicio]: el objeto usa el id y la tabla de servicios dice que ese id es
    el procedimiento 'a' (de la misma raiz de KBs que el que lo usa: CORE o FIXES)."""
    tabla = servicios.tabla()
    if not tabla:
        return []
    por_nombre = {}
    for i, n in enumerate(nodos):
        if n[2] in ("Procedure", "DataProvider", "API", "Solo Java"):
            por_nombre.setdefault(n[1].lower(), []).append(i)
    salida = []
    for d in datos.values():
        for de_id, ids in (d.get("servicios") or {}).items():
            de = idx.get(de_id)
            if de is None:
                continue
            u = universos.get(nodos[de][0])
            for sid in ids:
                ruta = tabla.get(sid)
                if not ruta:
                    continue
                for a in por_nombre.get(servicios.nombre_objeto(ruta), ()):
                    if a != de and universos.get(nodos[a][0]) == u:
                        salida.append([de, a, "servicio", "L", sid])
    return salida


def vecinos(nombre, kb=None, maximo=5):
    """Para el comando 'grafo --objeto': [(nodo, [(vecino, tipo, origen)] que lo usan, [...] que usa)]."""
    d = compacto()
    nodos, aristas = d["nodos"], d["aristas"]
    q = nombre.lower()
    hallados = [i for i, n in enumerate(nodos) if n[1].lower() == q or n[1].lower().endswith("." + q)]
    if kb:
        hallados = [i for i in hallados if nodos[i][0].lower() == kb.lower()]
    sal, ent = {}, {}
    for x, y, t, o, *extra in aristas:
        sal.setdefault(x, []).append((y, t, o, *extra))
        ent.setdefault(y, []).append((x, t, o, *extra))
    # Primero lo de otras KBs, que es lo que se rompe sin que se note.
    clave = lambda kb: lambda v: (nodos[v[0]][0] in (kb, ""), nodos[v[0]][0], nodos[v[0]][1])
    return [(nodos[i], [(nodos[v[0]], *v[1:]) for v in sorted(ent.get(i, []), key=clave(nodos[i][0]))],
             [(nodos[v[0]], *v[1:]) for v in sorted(sal.get(i, []), key=clave(nodos[i][0]))]) for i in hallados[:maximo]]


def vigilar(al_cambiar=None, espera=5):
    """Rearma el grafo de cada KB cuando GeneXus termina de compilarla, y una vez al empezar (por los builds
    hechos con la interfaz cerrada). 'al_cambiar' recibe la lista de KBs rearmadas."""
    def rearmar(kb=None):
        try:
            r = actualizar(solo=[kb.nombre] if kb else None)
        except Exception as e:
            poner_error(f"Error al actualizar el grafo: {e}")
            return
        if r and al_cambiar:
            al_cambiar(r)

    threading.Thread(target=rearmar, daemon=True, name="gxp-grafo-inicio").start()
    vigilancia.suscribir("grafo", rearmar, espera=espera)
