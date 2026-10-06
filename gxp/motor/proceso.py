"""Un proceso Java (GxMotor) por KB, que inicializa GeneXus y atiende pedidos por stdin/stdout en JSON.

- Si GeneXus recompila la KB (cambia su firma de build), el motor se reinicia solo en el siguiente pedido.
- Despues de un rato sin uso se apaga para liberar las conexiones a la base (Gestor).
- 'lock' es reentrante: quien necesita varios pedidos seguidos sin que se mezclen otros (un caso de
  prueba completo, con su transaccion) lo toma durante todo el trabajo.
"""
import json
import queue
import subprocess
import threading
import time
from collections import deque

from . import classpath
from ..config import CFG
from ..util import SIN_VENTANA

MARCA = "\x01GXR "  # prefijo de las lineas del protocolo en el stdout de GxMotor


class MotorError(Exception):
    pass


class Motor:
    def __init__(self, kb):
        self.kb = kb
        self.proc = None
        self.estado = "apagado"
        self.lock = threading.RLock()
        self.cola = queue.Queue()
        self.log = deque(maxlen=600)
        self.firma = None
        self.inicio = None
        self.ultimo_uso = time.time()
        self.ultimo_error = None
        self.seq = 0
        self.ocupado = False
        self.pedidos = 0
        self.ms_inicio = None

    # ------------------------------------------------------------------ ciclo de vida

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self):
        with self.lock:
            if self.vivo():
                return
            self.estado = "iniciando"
            self.ultimo_error = None
            t0 = time.time()
            try:
                self.firma = self.kb.firma_build()
                cp = classpath.preparar(self.kb, self.log.append)
                cmd = [CFG["java"], *CFG["opcionesJvm"], "-cp", cp, "GxMotor", self.kb.ns,
                       ",".join(d["nombre"] for d in self.kb.datasources)]
                self.log.append(f"[gxpruebas] iniciando motor: cwd={self.kb.web}")
                self.cola = queue.Queue()
                self.proc = subprocess.Popen(cmd, cwd=str(self.kb.web), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                             stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                                             bufsize=1, creationflags=SIN_VENTANA)
                # Cada lector escribe en la cola de SU proceso: si leyera self.cola, el fin de un motor
                # anterior podria caer en la cola del nuevo y cortar su arranque.
                threading.Thread(target=self._leer, args=(self.proc.stdout, self.cola, True), daemon=True).start()
                threading.Thread(target=self._leer, args=(self.proc.stderr, self.cola, False), daemon=True).start()
                msg = self._esperar(lambda m: "evento" in m, 180)
                if msg.get("evento") != "listo":
                    raise MotorError("El motor no pudo iniciar GeneXus:\n" + (msg.get("error") or "") + "\n" + (msg.get("consola") or ""))
                self.inicio = time.time()
                self.ms_inicio = int((time.time() - t0) * 1000)
                self.estado = "listo"
                self.ultimo_uso = time.time()
                if msg.get("consola"):
                    self.log.append(msg["consola"])
            except classpath.ErrorClasspath as e:
                self._fallo(e)
                raise MotorError(str(e)) from e
            except Exception as e:
                self._fallo(e)
                raise

    def _fallo(self, e):
        self.ultimo_error = str(e)
        self.estado = "error"
        self._matar()

    def _leer(self, flujo, cola, protocolo):
        for linea in flujo:
            if protocolo and linea.startswith(MARCA):
                try:
                    cola.put(json.loads(linea[len(MARCA):]))
                except Exception:
                    self.log.append("[protocolo] " + linea[:500])
            else:
                self.log.append(linea.rstrip("\n")[:2000])
        if protocolo:
            cola.put({"_fin": True})

    def _esperar(self, cond, segundos):
        limite = time.time() + segundos
        while True:
            resto = limite - time.time()
            if resto <= 0:
                raise MotorError(f"El motor no respondio en {int(segundos)} s")
            try:
                m = self.cola.get(timeout=min(resto, 1.0))
            except queue.Empty:
                if not self.vivo():
                    raise MotorError("El motor se cerro inesperadamente:\n" + self.cola_log(40))
                continue
            if m.get("_fin"):
                raise MotorError("El motor se cerro inesperadamente:\n" + self.cola_log(40))
            if cond(m):
                return m

    def cola_log(self, n=60):
        return "\n".join(list(self.log)[-n:])

    def _matar(self):
        p = self.proc
        self.proc = None
        if p and p.poll() is None:
            try:
                p.kill()
            except Exception:
                pass

    def detener(self, motivo="manual"):
        with self.lock:
            if self.vivo():
                try:
                    self.proc.stdin.write(json.dumps({"id": -1, "cmd": "salir"}) + "\n")
                    self.proc.stdin.flush()
                    self.proc.wait(5)
                except Exception:
                    pass
            self._matar()
            self.estado = "apagado"
            self.log.append(f"[gxpruebas] motor detenido ({motivo})")

    def recompilada(self):
        return self.vivo() and self.firma is not None and self.kb.firma_build() != self.firma

    # ------------------------------------------------------------------ pedidos

    def pedir(self, cmd, timeout_ms=None, **datos):
        """Manda un pedido al motor y espera la respuesta (un dict). Lo inicia si hace falta."""
        with self.lock:
            if self.recompilada():
                self.detener("GeneXus recompilo la KB")
            if not self.vivo():
                self.iniciar()
            self.seq += 1
            timeout_ms = int(timeout_ms or CFG["timeoutMsDefecto"])
            msg = {"id": self.seq, "cmd": cmd, "timeoutMs": timeout_ms, **datos}
            self.ocupado = True
            self.estado = "ocupado"
            try:
                self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
                r = self._esperar(lambda m: m.get("id") == msg["id"], timeout_ms / 1000 + 20)
            except (OSError, ValueError) as e:
                self._matar()
                self.estado = "error"
                raise MotorError(f"Se perdio la comunicacion con el motor: {e}\n" + self.cola_log(40))
            except MotorError:
                self._matar()
                self.estado = "error"
                raise
            finally:
                self.ocupado = False
                self.ultimo_uso = time.time()
                self.pedidos += 1
            if r.get("timeout"):
                try:
                    self.proc.wait(10)
                except Exception:
                    pass
                self._matar()
                self.estado = "apagado"
            elif self.vivo():
                self.estado = "listo"
            if r.get("consola"):
                self.log.append(r["consola"].rstrip()[:5000])
            return r

    def info(self):
        return {
            "kb": self.kb.nombre,
            "estado": self.estado,
            "pid": self.proc.pid if self.vivo() else None,
            "inicio": self.inicio if self.vivo() else None,
            "msInicio": self.ms_inicio,
            "pedidos": self.pedidos,
            "recompilada": self.recompilada() if not self.ocupado else False,
            "error": self.ultimo_error,
        }


class Gestor:
    """Los motores de todas las KBs. Apaga los que pasan 'motorInactivoMin' minutos sin uso."""

    def __init__(self):
        self.motores = {}
        self.lock = threading.Lock()
        threading.Thread(target=self._vigilar, daemon=True, name="gxp-motores").start()

    def motor(self, kb):
        with self.lock:
            m = self.motores.get(kb.nombre)
            if m is None:
                m = self.motores[kb.nombre] = Motor(kb)
            return m

    def _vigilar(self):
        while True:
            time.sleep(30)
            limite = CFG["motorInactivoMin"] * 60
            for m in list(self.motores.values()):
                if m.vivo() and not m.ocupado and time.time() - m.ultimo_uso > limite:
                    if m.lock.acquire(blocking=False):
                        try:
                            m.detener("inactividad")
                        finally:
                            m.lock.release()

    def detener_todos(self):
        for m in list(self.motores.values()):
            m.detener("cierre")


# ---------------------------------------------------------------------- gestor unico (se crea al primer uso)

_gestor = None
_lock_gestor = threading.Lock()


def gestor():
    """El gestor de motores del proceso. Se crea recien cuando se lo necesita: importar el paquete no
    arranca hilos."""
    global _gestor
    with _lock_gestor:
        if _gestor is None:
            _gestor = Gestor()
        return _gestor


def motor(kb):
    """El motor de una KB (no lo inicia: arranca solo con el primer pedido)."""
    return gestor().motor(kb)


def motores():
    """Los motores creados en este proceso."""
    return list(_gestor.motores.values()) if _gestor else []


def detener_todos():
    if _gestor:
        _gestor.detener_todos()
