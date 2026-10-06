"""Vigilancia de builds de GeneXus: un solo hilo mira la firma de build de cada KB (kbs.KB.firma_build) y
avisa a los suscriptores.

  - al_detectar(kb): cambio la firma (GeneXus esta compilando).
  - al_terminar(kb): la firma no cambio mas durante 'espera' segundos (el build termino).

Cada suscriptor procesa sus avisos en su propio hilo, en orden: uno lento (las pruebas despues del build) no
demora a los otros (el grafo). Al arrancar no se avisa nada: solo se toma la situacion actual.
"""
import queue
import threading
import time
import traceback

from . import kbs

INTERVALO = 3  # segundos entre revisiones


class Suscripcion:
    def __init__(self, nombre, al_terminar, al_detectar=None, filtro=None, espera=15):
        self.nombre = nombre
        self.al_terminar = al_terminar
        self.al_detectar = al_detectar
        self.filtro = filtro            # kb -> bool: las KBs que le interesan (None = todas)
        self.espera = float(espera)
        self.error = None
        self._cola = queue.Queue()
        threading.Thread(target=self._atender, daemon=True, name=f"gxp-{nombre}").start()

    def interesa(self, kb):
        return self.filtro is None or self.filtro(kb)

    def avisar(self, evento, kb):
        self._cola.put((evento, kb))

    def _atender(self):
        while True:
            evento, kb = self._cola.get()
            fn = self.al_terminar if evento == "terminado" else self.al_detectar
            if fn is None:
                continue
            try:
                fn(kb)
                self.error = None
            except Exception as e:  # un aviso que falla no frena a los siguientes
                self.error = f"{self.nombre}: {e}\n{traceback.format_exc()[-1500:]}"


class Vigilante:
    def __init__(self):
        self.suscripciones = []
        self._vistas = {}  # kb -> {"firma", "cambio"}
        self._lock = threading.Lock()
        self._hilo = None

    def suscribir(self, nombre, al_terminar, al_detectar=None, filtro=None, espera=15):
        s = Suscripcion(nombre, al_terminar, al_detectar, filtro, espera)
        with self._lock:
            self.suscripciones.append(s)
            if self._hilo is None:
                self._hilo = threading.Thread(target=self._vigilar, daemon=True, name="gxp-vigilancia")
                self._hilo.start()
        return s

    def revisar(self, ahora=None):
        """Una pasada: detecta cambios de firma y builds terminados (lo llama el hilo cada INTERVALO s)."""
        ahora = ahora or time.time()
        with self._lock:
            subs = list(self.suscripciones)
        for kb in kbs.descubrir().values():
            interesados = [s for s in subs if s.interesa(kb)]
            if not interesados:
                continue
            f = kb.firma_build()
            v = self._vistas.get(kb.nombre)
            if v is None:
                self._vistas[kb.nombre] = {"firma": f, "cambio": None, "avisados": set()}
                continue
            if f != v["firma"]:
                v["firma"], v["cambio"], v["avisados"] = f, ahora, set()
                for s in interesados:
                    s.avisar("detectado", kb)
            elif v["cambio"]:
                # Si GeneXus vuelve a compilar mientras se atiende el aviso, cambia la firma y se avisa otra vez.
                for s in interesados:
                    if s.nombre not in v["avisados"] and ahora - v["cambio"] >= s.espera:
                        v["avisados"].add(s.nombre)
                        s.avisar("terminado", kb)
                if all(s.nombre in v["avisados"] for s in interesados):
                    v["cambio"] = None

    def _vigilar(self):
        while True:
            try:
                self.revisar()
            except Exception:  # nunca se deja de vigilar por un error (una KB que no se puede leer, etc.)
                pass
            time.sleep(INTERVALO)


_vigilante = Vigilante()


def suscribir(nombre, al_terminar, al_detectar=None, filtro=None, espera=15):
    """Suscribe a los builds de las KBs (todas, o las que acepta 'filtro'). Arranca la vigilancia si hace falta."""
    return _vigilante.suscribir(nombre, al_terminar, al_detectar, filtro, espera)
