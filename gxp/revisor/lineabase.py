"""Linea base de la revision de cada KB (.cache/revisor/<kb>.json).

Guarda, de la ultima revision completa:
  - la fecha de la especificacion de cada objeto: los que tienen otra fecha son los que volvio a especificar
    un build (o que se agregaron);
  - las huellas de los hallazgos de cada objeto revisado (tambien los cubiertos por excepciones), y cuales de
    ellas introdujo su ultima modificacion.

NUEVO quiere decir "lo introdujo la ultima modificacion del objeto" (ver es_nuevo): si el objeto cambio desde
la linea base, es nuevo lo que no estaba antes; si no cambio, sigue siendo nuevo lo que era nuevo cuando cambio.
Asi la marca no se pierde al volver a revisar (por ejemplo, desde la interfaz) hasta que el objeto cambie otra
vez. Un objeto que no estaba en la linea base (creado despues) tiene todos sus hallazgos nuevos. La huella no
depende del numero de linea.

Solo la actualizan las revisiones completas (toda la KB o los cambiados, con todas las reglas activas): revisar
un objeto suelto con --objeto, o con --regla, no la toca. Asi un hallazgo que aparece al editar un objeto sigue
contando como nuevo en el build siguiente.
"""
import datetime as dt
import json
import os
import threading

from ..config import CACHE

DIR = CACHE / "revisor"
VERSION = 1

_locks = {}
_locks_lock = threading.Lock()


def lock(kb):
    """Un lock por KB: la linea base de una KB la escribe una revision a la vez (en este proceso)."""
    with _locks_lock:
        return _locks.setdefault(kb.nombre, threading.Lock())


class LineaBase:
    def __init__(self, kb):
        self.kb = kb
        self.archivo = DIR / f"{kb.nombre.replace('/', '_').lower()}.json"
        self.fechas = {}    # ruta de la especificacion -> mtime
        self.huellas = {}   # objeto (minusculas) -> {huellas}
        self.nuevas = {}    # objeto (minusculas) -> {huellas que introdujo su ultima modificacion}
        self.existe = False
        self.actualizada = None
        try:
            d = json.loads(self.archivo.read_text(encoding="utf-8"))
            if d.get("version") == VERSION:
                self.fechas = d.get("fechas") or {}
                self.huellas = {k: set(v) for k, v in (d.get("huellas") or {}).items()}
                self.nuevas = {k: set(v) for k, v in (d.get("nuevas") or {}).items()}
                self.actualizada = d.get("actualizada")
                self.existe = True
        except (OSError, ValueError):
            pass

    def cambiados(self, actuales):
        """Rutas de 'actuales' ([(ruta, mtime)]) que no estan en la linea base o tienen otra fecha."""
        return [r for r, mt in actuales if self.cambio(r, mt)]

    def cambio(self, ruta, mtime):
        """True si la especificacion cambio (u objeto nuevo) desde la linea base."""
        return self.fechas.get(str(ruta)) != mtime

    def es_nuevo(self, objeto, huella, cambio):
        """True si el hallazgo lo introdujo la ultima modificacion del objeto, False si no, None si no se sabe
        (no hay linea base, o el objeto no cambio pero no se habia revisado)."""
        if not self.existe:
            return None
        previas = self.huellas.get(objeto.lower())
        if cambio:
            return True if previas is None else huella not in previas
        if previas is None:
            return None
        return huella in self.nuevas.get(objeto.lower(), ())

    def actualizar(self, revisadas, objetos, nuevas, completa, existentes=None):
        """revisadas: {ruta: mtime} de lo que se miro (tambien lo ignorado); objetos: {objeto: [huellas]} de
        lo revisado; nuevas: {objeto: [huellas nuevas]}; existentes: rutas que hay hoy en la KB. Con
        completa=True reemplaza todo; si no, actualiza solo esas entradas y saca las que ya no existen."""
        if completa:
            self.fechas = {str(r): mt for r, mt in revisadas.items()}
            self.huellas, self.nuevas = {}, {}
        else:
            for r, mt in revisadas.items():
                self.fechas[str(r)] = mt
            if existentes is not None:  # lo que se borro de la KB sale de la linea base
                existentes = {str(r) for r in existentes}
                self.fechas = {r: mt for r, mt in self.fechas.items() if r in existentes}
        for o, hs in objetos.items():
            self.huellas[o.lower()] = set(hs)
            self.nuevas[o.lower()] = set(nuevas.get(o, ()))
        self.actualizada = dt.datetime.now().isoformat(timespec="seconds")
        self.existe = True

    def guardar(self):
        DIR.mkdir(parents=True, exist_ok=True)
        datos = {"version": VERSION, "kb": self.kb.nombre, "actualizada": self.actualizada,
                 "fechas": self.fechas, "huellas": {k: sorted(v) for k, v in sorted(self.huellas.items())},
                 "nuevas": {k: sorted(v) for k, v in sorted(self.nuevas.items()) if v}}
        tmp = self.archivo.with_name(f"{self.archivo.stem}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.archivo)
