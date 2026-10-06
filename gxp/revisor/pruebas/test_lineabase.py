"""Ciclo de la linea base con una KB falsa en una carpeta temporal: primera revision, build que cambia un
objeto y agrega otro, revision de los cambiados (nuevo / preexistente), y que --objeto no toque la linea base."""
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from gxp.revisor import lineabase, revisor
from gxp.revisor.configuracion import Configuracion
from gxp.revisor.pruebas import sp0

COMMIT = "b_line_i(8,1,1,cmd,0,[ t('',132,8,0) ])."
LLAMA_PRC_COMMIT = "b_line_i(9,1,1,cmd,0,[ t('',104,9,0),t(o(1,'X\\Global\\prcCommit'),28,0,1) ])."


class KBFalsa:
    def __init__(self, carpeta):
        self.nombre = "Falsa"
        self.carpeta = Path(carpeta)

    def fuente_java(self, objeto):
        return self.carpeta / "java" / (objeto.lower() + ".java")


class ConKBFalsa(unittest.TestCase):
    """Una KB falsa en una carpeta temporal (sin pruebas propias: la usan las de abajo y otros archivos)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="gxp-revisor-")
        self.gen = Path(self.tmp) / "GXSPC001" / "GEN12"
        (self.gen / "X").mkdir(parents=True)
        self.kb = KBFalsa(self.tmp)
        self.parches = [mock.patch.object(lineabase, "DIR", Path(self.tmp) / "cache"),
                        mock.patch.object(revisor, "DIR", Path(self.tmp) / "revisiones"),
                        mock.patch("gxp.revisor.configuracion.cargar", lambda: Configuracion())]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escribir(self, nombre, lineas):
        ruta = self.gen / "X" / f"{nombre.split('.')[-1]}.sp0"
        ruta.write_text(sp0(nombre, lineas), encoding="cp1252")
        # Cada escritura con otra fecha, aunque pasen en el mismo instante (como un build real).
        self.reloj = getattr(self, "reloj", time.time()) + 10
        os.utime(ruta, (self.reloj, self.reloj))
        return ruta

    def revisar(self, **kw):
        return revisor.revisar(self.kb, guardar=False, **kw)


class LineaBase(ConKBFalsa):
    def test_ciclo(self):
        self.escribir("X.P", COMMIT)
        # Sin linea base: se revisa todo y se arma; no se sabe que es nuevo.
        r = self.revisar(cambiados=True)
        self.assertEqual(r["modo"], "completa")
        self.assertEqual(r["revisados"], 1)
        self.assertEqual([h["nuevo"] for h in r["hallazgos"]], [None])
        self.assertTrue(lineabase.LineaBase(self.kb).existe)

        # Nada cambio: no se revisa nada.
        self.assertEqual(self.revisar(cambiados=True)["revisados"], 0)

        # "Build": P suma una llamada a prcCommit y aparece Q, limpio.
        self.escribir("X.P", COMMIT + "\n" + LLAMA_PRC_COMMIT)
        self.escribir("X.Q", "")
        r = self.revisar(cambiados=True)
        self.assertEqual(r["modo"], "cambiados")
        self.assertEqual(r["revisados"], 2)
        nuevos = {h["linea"]: h["nuevo"] for h in r["hallazgos"]}
        self.assertEqual(nuevos, {8: False, 9: True})  # el Commit ya estaba; la llamada es nueva
        self.assertEqual(r["nuevos"], {"error": 1, "advertencia": 0})

        # Despues de esa revision, la llamada ya no es nueva.
        self.escribir("X.P", COMMIT + "\n" + LLAMA_PRC_COMMIT + "\n")
        r = self.revisar(cambiados=True)
        self.assertEqual({h["linea"]: h["nuevo"] for h in r["hallazgos"]}, {8: False, 9: False})

    def test_objeto_suelto_no_toca_la_linea_base(self):
        self.escribir("X.P", "")
        self.revisar()  # completa: P sin hallazgos
        self.escribir("X.P", COMMIT)
        r = self.revisar(objetos=["X.P"])
        self.assertEqual([h["nuevo"] for h in r["hallazgos"]], [True])
        self.assertNotIn("lineaBaseActualizada", r)
        # El build lo sigue viendo como nuevo.
        r = self.revisar(cambiados=True)
        self.assertEqual(r["revisados"], 1)
        self.assertEqual([h["nuevo"] for h in r["hallazgos"]], [True])

    def test_nuevo_se_conserva_hasta_el_proximo_cambio(self):
        self.escribir("X.P", "")
        self.revisar()
        self.escribir("X.P", COMMIT)
        self.assertEqual([h["nuevo"] for h in self.revisar(cambiados=True)["hallazgos"]], [True])
        # Revisar de nuevo (la KB entera, o el objeto desde la interfaz) no le saca la marca...
        self.assertEqual([h["nuevo"] for h in self.revisar()["hallazgos"]], [True])
        self.assertEqual([h["nuevo"] for h in self.revisar(objetos=["X.P"])["hallazgos"]], [True])
        # ...hasta que el objeto cambia otra vez: lo que ya estaba deja de ser nuevo.
        self.escribir("X.P", COMMIT + "\n" + LLAMA_PRC_COMMIT)
        r = self.revisar(cambiados=True)
        self.assertEqual({h["linea"]: h["nuevo"] for h in r["hallazgos"]}, {8: False, 9: True})

    def test_objeto_creado_despues_tiene_todo_nuevo(self):
        self.escribir("X.P", "")
        self.revisar()
        self.escribir("X.R", COMMIT)
        self.assertEqual([h["nuevo"] for h in self.revisar(cambiados=True)["hallazgos"]], [True])

    def test_objeto_borrado_sale_de_la_linea_base(self):
        q = self.escribir("X.Q", "")
        self.escribir("X.P", "")
        self.revisar()
        q.unlink()
        self.escribir("X.P", COMMIT)
        self.revisar(cambiados=True)
        self.assertNotIn(str(q), lineabase.LineaBase(self.kb).fechas)


if __name__ == "__main__":
    unittest.main()
