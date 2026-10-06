"""Vigilancia de builds (gxp.vigilancia) con KBs falsas y un reloj manual."""
import threading
import unittest
from unittest import mock

from gxp import vigilancia


class KBFalsa:
    def __init__(self, nombre):
        self.nombre = nombre
        self.firma = "1"

    def firma_build(self):
        return self.firma


class Vigilancia(unittest.TestCase):
    def setUp(self):
        self.kbs = {"A": KBFalsa("A"), "B": KBFalsa("B")}
        p = mock.patch("gxp.kbs.descubrir", lambda: self.kbs)
        p.start()
        self.addCleanup(p.stop)
        self.v = vigilancia.Vigilante()
        self.v._hilo = object()  # sin hilo propio: las pasadas se llaman a mano con revisar(ahora)
        self.eventos = []
        self.listo = threading.Semaphore(0)

    def suscribir(self, nombre="s", espera=10, filtro=None):
        def registrar(evento):
            def f(kb):
                self.eventos.append((nombre, evento, kb.nombre))
                self.listo.release()
            return f
        self.v.suscripciones.append(vigilancia.Suscripcion(nombre, registrar("terminado"), registrar("detectado"),
                                                           filtro, espera))

    def esperar(self, n):
        for _ in range(n):
            self.assertTrue(self.listo.acquire(timeout=5), "no llego el aviso")

    def test_ciclo_de_un_build(self):
        self.suscribir()
        self.v.revisar(100)                      # al arrancar: solo toma la situacion actual
        self.assertEqual(self.eventos, [])
        self.kbs["A"].firma = "2"
        self.v.revisar(101)                      # GeneXus empezo a compilar
        self.esperar(1)
        self.v.revisar(105)                      # todavia no paso la espera
        self.v.revisar(111)                      # 10 s sin cambios: termino
        self.esperar(1)
        self.v.revisar(130)                      # no se avisa dos veces
        self.assertEqual(self.eventos, [("s", "detectado", "A"), ("s", "terminado", "A")])

    def test_recompila_durante_la_espera(self):
        self.suscribir()
        self.v.revisar(100)
        self.kbs["B"].firma = "2"
        self.v.revisar(101)
        self.kbs["B"].firma = "3"
        self.v.revisar(108)                      # otro cambio: la espera vuelve a empezar
        self.v.revisar(112)
        self.v.revisar(118)
        self.esperar(3)
        self.assertEqual([e[1] for e in self.eventos], ["detectado", "detectado", "terminado"])

    def test_cada_suscriptor_con_su_espera_y_sus_kbs(self):
        self.suscribir("rapido", espera=2)
        self.suscribir("solo_b", espera=10, filtro=lambda kb: kb.nombre == "B")
        self.v.revisar(100)
        self.kbs["A"].firma = self.kbs["B"].firma = "2"
        self.v.revisar(101)
        self.esperar(3)                          # rapido: A y B; solo_b: B
        self.v.revisar(104)
        self.esperar(2)                          # rapido termina A y B
        self.v.revisar(112)
        self.esperar(1)                          # solo_b termina B
        terminados = sorted((s, kb) for s, ev, kb in self.eventos if ev == "terminado")
        self.assertEqual(terminados, [("rapido", "A"), ("rapido", "B"), ("solo_b", "B")])

    def test_un_aviso_que_falla_no_frena_los_siguientes(self):
        llamados = []
        listo = threading.Event()

        def f(kb):
            llamados.append(kb.nombre)
            if len(llamados) == 1:
                raise RuntimeError("fallo")
            listo.set()
        s = vigilancia.Suscripcion("x", f)
        s.avisar("terminado", self.kbs["A"])
        s.avisar("terminado", self.kbs["B"])
        self.assertTrue(listo.wait(5))
        self.assertEqual(llamados, ["A", "B"])


if __name__ == "__main__":
    unittest.main()
