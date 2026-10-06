"""Salidas aprobadas ('lineaBase') y valores que cambian solos ('volatiles').

Al aprobar, cada caso se corre dos veces con la misma entrada: lo que da distinto (fechas, ids nuevos) se
marca como volatil y de esas rutas solo se controla el tipo. Si el caso graba de verdad (commit), no se vuelve
a correr: se marcan solo los valores con la fecha de hoy.
"""
import time

from . import almacen
from .ejecucion import correr_caso, linea_base_de, nombre_paso
from .. import catalogo, kbs
from ..comparacion import detectar_volatiles, volatiles_por_valor
from ..config import CFG


def _sumar_volatiles(paso, nuevas):
    """Agrega rutas volatiles al paso (no se sacan las que ya tenia: una vez detectada, una ruta que cambia
    sola puede coincidir por casualidad en dos ejecuciones seguidas)."""
    todas = sorted(set(paso.get("volatiles") or []) | set(nuevas))
    if todas:
        paso["volatiles"] = todas


def _poner_linea_base(caso, paso, fila, datos):
    """Guarda 'datos' como salida aprobada del paso (con 'datos' en el caso, la de esa fila)."""
    if caso.get("datos") and fila is not None:
        lb = paso.get("lineaBase") if isinstance(paso.get("lineaBase"), list) else []
        while len(lb) <= fila:
            lb.append(None)
        lb[fila] = datos
        paso["lineaBase"] = lb
    else:
        paso["lineaBase"] = datos


def hace_commit(kb, caso, opciones):
    """Motivo por el que no conviene volver a ejecutar el caso (graba de verdad), o None."""
    if (caso.get("transaccion") or opciones.get("transaccion", "rollback")) == "commit":
        return "el caso corre con commit"
    for p in caso["pasos"]:
        if p.get("objeto"):
            try:
                if catalogo.hace_commit(kb, catalogo.buscar(kb, p["objeto"])["nombre"]):
                    return f"{p['objeto']} hace commit por su cuenta"
            except KeyError:
                pass
    return None


def segunda_ejecucion(kb, suite, caso, opciones, inicio):
    """Vuelve a correr el caso para ver que valores cambian solos. Devuelve (resultados, motivo si no se corrio)."""
    motivo = hace_commit(kb, caso, opciones)
    if motivo:
        return None, motivo
    # Al menos un segundo despues: una fecha con hora que cambia sola tiene que poder dar distinto.
    time.sleep(max(0.0, 1.1 - (time.time() - inicio)))
    return correr_caso(kb, suite, caso, opciones, grabar=True), None


def aplicar_grabacion(caso, resultados, segunda=None, motivo_sin_segunda=None, campos=None):
    """Copia las salidas obtenidas como linea base de cada paso y marca como volatiles las rutas que
    cambiaron en la segunda ejecucion (o, sin ella, las que tienen la fecha de hoy). Devuelve (cambios, avisos)."""
    cambios, avisos = 0, []
    otra = {r["id"]: r for r in (segunda or [])}
    for res in resultados:
        if res["estado"] == "error":
            continue
        pasos2 = (otra.get(res["id"]) or {}).get("pasos") or []
        for i, pr in enumerate(res["pasos"]):
            if pr.get("preparacion") or i >= len(caso["pasos"]) or pr.get("datos") is None:
                continue
            paso = caso["pasos"][i]
            _poner_linea_base(caso, paso, res["fila"], pr["datos"])
            if i < len(pasos2) and pasos2[i].get("datos") is not None:
                vol, av = detectar_volatiles(pr["datos"], pasos2[i]["datos"], campos)
            else:
                vol, av = sorted(volatiles_por_valor(pr["datos"])), []
            _sumar_volatiles(paso, vol)
            avisos.extend(f"Paso '{pr['nombre']}': {a}" for a in av)
            cambios += 1
    if cambios and motivo_sin_segunda:
        avisos.append(f"No se volvio a ejecutar para detectar los valores que cambian solos ({motivo_sin_segunda}): "
                      "solo se marcaron los que tienen la fecha de hoy.")
    return cambios, list(dict.fromkeys(avisos))


def volatiles_de_caso(suite_id, caso_id):
    """Para un caso recien guardado con su salida aprobada: lo ejecuta otra vez y marca como volatiles las
    rutas que dieron distinto. Devuelve {"volatiles": {paso: [rutas]}, "avisos": [...]}."""
    suite = almacen.cargar(suite_id)
    caso = next((c for c in suite["casos"] if c["id"] == caso_id), None)
    if caso is None:
        raise KeyError(f"No existe el caso {caso_id}")
    kb = kbs.obtener(suite["kb"])
    opciones = {**CFG["opcionesSuite"], **(suite.get("opciones") or {})}
    salida = {"volatiles": {}, "avisos": []}
    motivo = hace_commit(kb, caso, opciones)
    rs = None if motivo else correr_caso(kb, suite, caso, opciones, grabar=True)
    sin_correr = [{"fila": fi if caso.get("datos") else None, "pasos": []} for fi in range(len(caso.get("datos") or [None]))]
    for res in rs or sin_correr:
        for i, paso in enumerate(caso["pasos"]):
            lb = linea_base_de(paso, res.get("fila") if caso.get("datos") else None)
            if lb is None:
                continue
            pr = res["pasos"][i] if i < len(res["pasos"]) else {}
            if pr.get("datos") is not None:
                vol, av = detectar_volatiles(lb, pr["datos"], opciones.get("camposClave"))
            else:
                vol, av = sorted(volatiles_por_valor(lb)), []
                if rs is not None:
                    av = [f"la segunda ejecucion no termino bien ({pr.get('error') or pr.get('estado', 'sin datos')}): revisa el caso"]
            _sumar_volatiles(paso, vol)
            if paso.get("volatiles"):
                salida["volatiles"][nombre_paso(paso)] = paso["volatiles"]
            salida["avisos"].extend(f"Paso '{nombre_paso(paso)}': {a}" for a in av)
    if motivo:
        salida["avisos"].append(f"No se volvio a ejecutar para detectar los valores que cambian solos ({motivo}): "
                                "solo se marcaron los que tienen la fecha de hoy.")
    salida["avisos"] = list(dict.fromkeys(salida["avisos"]))
    almacen.guardar(suite_id, suite)
    return salida


def aceptar_linea_base(suite_id, caso_id, paso_idx, fila, datos):
    """'Es correcto: aceptar esta salida' de la interfaz."""
    suite = almacen.cargar(suite_id)
    caso = next((c for c in suite["casos"] if c["id"] == caso_id), None)
    if caso is None:
        raise KeyError(f"No existe el caso {caso_id}")
    paso = caso["pasos"][paso_idx]
    _poner_linea_base(caso, paso, fila, datos)
    _sumar_volatiles(paso, volatiles_por_valor(datos))
    almacen.guardar(suite_id, suite)
