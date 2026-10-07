"""Corrida de una suite: los casos elegidos, el script previo, el progreso, la grabacion de salidas aprobadas y el
resultado."""
import datetime as dt
import random
import time

from . import almacen, resultados
from .ejecucion import correr_caso
from .grabacion import aplicar_grabacion, segunda_ejecucion
from .script import Entorno
from .reportes import totales
from .. import efectos, kbs
from ..config import CFG
from ..util import slug


def _elegir_casos(suite, casos_ids, etiqueta, filtro):
    casos = suite["casos"]
    if casos_ids:
        ids = set(casos_ids)
        casos = [c for c in casos if c["id"] in ids]
    if etiqueta:
        casos = [c for c in casos if etiqueta in (c.get("etiquetas") or [])]
    if filtro:
        f = filtro.lower()
        casos = [c for c in casos if f in c["id"].lower() or f in c["nombre"].lower()]
    return casos


def _grabar(caso, rs, segunda, motivo, opciones):
    """Aprueba las salidas de la primera ejecucion; lo que cambio en la segunda queda como volatil."""
    n, avisos = aplicar_grabacion(caso, rs, segunda, motivo, opciones.get("camposClave"))
    if avisos and rs:
        rs[0]["advertencias"].extend(avisos)
    return n


def correr_suite(suite_id, casos_ids=None, etiqueta=None, filtro=None, grabar=False, progreso=None, cancelado=lambda: False,
                 origen=None):
    """Corre la suite (o los casos elegidos por id, etiqueta o filtro de texto) y guarda el resultado.
    'progreso' recibe la corrida cada vez que termina un caso. Con 'grabar', aprueba las salidas obtenidas.
    'origen': de donde salio la corrida ("build" = automatica despues de un build); queda en el resultado."""
    suite = almacen.cargar(suite_id)
    kb = kbs.obtener(suite["kb"])
    opciones = {**CFG["opcionesSuite"], **(suite.get("opciones") or {})}
    casos = _elegir_casos(suite, casos_ids, etiqueta, filtro)
    inicio = dt.datetime.now()
    corrida = {"id": f"{inicio:%Y%m%d_%H%M%S}_{slug(suite_id)[:40]}_{random.randint(100, 999)}", "suite": suite["_id"],
               "suiteNombre": suite["nombre"], "kb": kb.nombre, "inicio": inicio.isoformat(timespec="seconds"),
               "grabar": grabar, "casos": [], "estado": "corriendo", "total": sum(len(c.get("datos") or [None]) for c in casos)}
    if origen:
        corrida["origen"] = origen
    if any("auto" in (c.get("etiquetas") or []) for c in casos):
        efectos.revalidar()  # pudo haber un build desde la ultima corrida
    if progreso:
        progreso(corrida)
    t0 = time.time()
    grabadas = 0
    # Con script previo o casos encadenados, toda la corrida es una transaccion (ver script.py).
    with Entorno(kb, suite, opciones) as entorno:
        if entorno.activo:
            corrida["encadenados"] = entorno.encadenados
            if entorno.resultado:
                corrida["scriptPrevio"] = entorno.resultado
            if progreso:
                progreso(corrida)
        primeras = []  # encadenados al aprobar: (caso, resultados), se graban despues de la segunda pasada
        for caso in casos:
            if cancelado():
                break
            t_caso = time.time()
            rs = correr_caso(kb, suite, caso, opciones, grabar, cancelado, entorno)
            if grabar and not cancelado():
                if entorno.encadenados:
                    primeras.append((caso, rs))
                else:
                    # Se corre dos veces: lo que da distinto con la misma entrada (fechas, ids nuevos) es volatil.
                    segunda, motivo = segunda_ejecucion(kb, suite, caso, opciones, t_caso, entorno)
                    grabadas += _grabar(caso, rs, segunda, motivo, opciones)
            corrida["casos"].extend(rs)
            if entorno.resultado:
                corrida["scriptPrevio"] = entorno.resultado  # se vuelve a correr si un caso lo pierde
            if progreso:
                progreso(corrida)
        if primeras and not cancelado():
            # Encadenados: la segunda ejecucion de cada caso tiene que partir de lo mismo que la primera, asi que se
            # vuelve a correr toda la cadena desde el principio.
            time.sleep(max(0.0, 1.1 - (time.time() - t0)))
            entorno.reiniciar()
            for caso, rs in primeras:
                if cancelado():
                    break
                segunda = correr_caso(kb, suite, caso, opciones, True, cancelado, entorno)
                grabadas += _grabar(caso, rs, segunda, None, opciones)
            if progreso:
                progreso(corrida)
    if grabar and grabadas:
        almacen.guardar(suite["_id"], suite)
    corrida["fin"] = dt.datetime.now().isoformat(timespec="seconds")
    corrida["ms"] = int((time.time() - t0) * 1000)
    corrida["totales"] = totales(corrida["casos"])
    t = corrida["totales"]
    corrida["estado"] = "cancelada" if cancelado() else ("ok" if t["falla"] == 0 and t["error"] == 0 else "falla")
    corrida["lineasBaseGrabadas"] = grabadas
    resultados.guardar_corrida(corrida)
    resultados.actualizar_estado(corrida)
    if progreso:
        progreso(corrida)
    return corrida
