"""Corridas en segundo plano (interfaz): se inicia una, se consulta su progreso y se puede cancelar."""
import threading
import traceback
import uuid

from . import almacen
from .corridas import correr_suite

_trabajos = {}  # id -> {"corrida": dict, "cancelar": bool}
_lock = threading.Lock()


def iniciar(suite_id, casos=None, etiqueta=None, filtro=None, grabar=False):
    """Arranca la corrida en un hilo y devuelve el id del trabajo. KeyError si la suite no existe."""
    almacen.cargar(suite_id)  # valida que exista antes de arrancar
    tid = uuid.uuid4().hex[:12]
    trabajo = {"corrida": {"estado": "esperando", "casos": [], "suite": suite_id}, "cancelar": False}

    def progreso(c):
        trabajo["corrida"] = c

    def correr():
        try:
            correr_suite(suite_id, casos or None, etiqueta or None, filtro or None, bool(grabar), progreso,
                         lambda: trabajo["cancelar"])
        except Exception as e:
            trabajo["corrida"] = {**trabajo["corrida"], "estado": "error", "error": str(e), "traza": traceback.format_exc()}

    with _lock:
        _trabajos[tid] = trabajo
    threading.Thread(target=correr, daemon=True, name=f"gxp-corrida-{tid}").start()
    return tid


def estado(tid, desde=0):
    """La corrida en curso, con los casos desde 'desde' (los anteriores ya los tiene quien consulta).
    KeyError si no existe el trabajo."""
    t = _trabajos.get(tid)
    if not t:
        raise KeyError("No existe el trabajo")
    c = dict(t["corrida"])  # copia: el hilo de la corrida le sigue agregando claves
    casos = list(c.pop("casos", []))
    return {**c, "casos": casos[desde:], "cantidad": len(casos)}


def cancelar(tid):
    t = _trabajos.get(tid)
    if t:
        t["cancelar"] = True
