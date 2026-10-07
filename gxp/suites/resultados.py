"""Resultados de las corridas: resultados/<id>.json (las ultimas 300) y resultados/estado.json, con el
estado de la ultima corrida de cada caso (lo que muestra la interfaz al abrir una suite)."""
import json
import threading
from pathlib import Path

from ..config import RESULTADOS
from ..util import conservar_ultimos, escribir_json, leer_json

MAX_CORRIDAS = 300
_ESTADO = "estado.json"

_lock = threading.Lock()
_resumenes = {}  # nombre de archivo -> resumen. Un resultado no cambia despues de grabado.


def _archivo_estado():
    return RESULTADOS / _ESTADO


def estado():
    """{suite: {caso: {estado, fecha, ms, corrida}, "_resumen": {...}}} de la ultima corrida de cada caso."""
    return leer_json(_archivo_estado(), {})


def estado_suite(suite_id):
    return estado().get(suite_id, {})


def actualizar_estado(corrida):
    with _lock:
        est = estado()
        s = est.setdefault(corrida["suite"], {})
        for c in corrida["casos"]:
            s[c["id"]] = {"estado": c["estado"], "fecha": corrida["fin"], "ms": c["ms"], "corrida": corrida["id"]}
            if c.get("variablesGuardadas"):
                s[c["id"]]["variables"] = _acotar(c["variablesGuardadas"])
        s["_resumen"] = {"fecha": corrida["fin"], "totales": corrida["totales"], "corrida": corrida["id"], "estado": corrida["estado"]}
        escribir_json(_archivo_estado(), est, sangria=1)


def _acotar(variables, maximo=1000):
    """Las variables que guardo un caso, para el estado: un valor muy grande queda resumido."""
    salida = {}
    for k, v in variables.items():
        texto = json.dumps(v, ensure_ascii=False)
        salida[k] = v if len(texto) <= maximo else {"_resumido": texto[:maximo] + "…"}
    return salida


def guardar_corrida(corrida):
    escribir_json(RESULTADOS / f"{corrida['id']}.json", corrida, sangria=1)
    conservar_ultimos(RESULTADOS, "*.json", MAX_CORRIDAS, excepto=(_ESTADO,))


def _archivos_corridas():
    return sorted((p for p in RESULTADOS.glob("*.json") if p.name != _ESTADO), reverse=True)


def listar_corridas(limite=200):
    """Resumen de las ultimas corridas, la mas reciente primero."""
    salida = []
    for p in _archivos_corridas()[:limite]:
        r = _resumenes.get(p.name)
        if r is None:
            c = leer_json(p)
            if c is None:
                continue
            r = _resumenes[p.name] = {k: c.get(k) for k in ("id", "suite", "suiteNombre", "kb", "inicio", "fin", "ms",
                                                              "totales", "estado", "grabar", "origen")}
        salida.append(r)
    return salida


def cargar_corrida(cid):
    """Una corrida completa. OSError si no existe."""
    c = leer_json(RESULTADOS / f"{Path(cid).name}.json")
    if c is None:
        raise FileNotFoundError(cid)
    return c
