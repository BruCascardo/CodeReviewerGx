"""Vista previa de pantallas (gxp/vista.py): que va al motor y que archivos de la KB se sirven (no necesita las KBs).

    python -m unittest pruebas.test_vista
"""
import tempfile
import unittest
from pathlib import Path

from gxp import vista


class KbFalsa:
    def __init__(self, raiz):
        self.nombre = "Falsa" + raiz.name
        self.carpeta = raiz
        self.web = raiz / "JavaModel" / "web"
        self.clases = self.web / "build" / "classes" / "java" / "main"


def escribir(p, texto=""):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")
    return p


class Vista(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.kb = KbFalsa(raiz)
        escribir(self.kb.clases / "com" / "generales" / "monedas" / "gntmonedaww_impl.class")
        escribir(self.kb.web / "js" / "gxgral.js", "// js")
        escribir(self.kb.web / "Resources" / "Spanish" / "DesignSystem.css", "/* css */")
        self.tomcat = escribir(raiz / "Tomcat" / "static" / "DVelop" / "x.css", "/* publicado */").parents[1]
        escribir(raiz / "model.ini", f"[MODEL 002]\nCLIENT_STATIC_DIR={self.tomcat}\nCLIENT_STATIC_DIR=C:\\no\\existe\n")
        escribir(raiz / "secreto.txt", "no")

    def tearDown(self):
        self.tmp.cleanup()

    def test_es_pantalla(self):
        self.assertTrue(vista.es_pantalla(self.kb, "servlet/com.generales.monedas.gntmonedaww"))
        self.assertTrue(vista.es_pantalla(self.kb, "com.generales.monedas.gntmonedaww"))
        self.assertFalse(vista.es_pantalla(self.kb, "servlet/com.generales.monedas.otra"))
        self.assertFalse(vista.es_pantalla(self.kb, "static/gxgral.js"))
        self.assertFalse(vista.es_pantalla(self.kb, "servlet/../secreto"))

    def test_archivos_de_la_kb_y_de_tomcat(self):
        self.assertEqual(vista.archivo(self.kb, "static/gxgral.js"), (self.kb.web / "js" / "gxgral.js").resolve())
        self.assertEqual(vista.archivo(self.kb, "static/Resources/Spanish/DesignSystem.css").name, "DesignSystem.css")
        self.assertEqual(vista.archivo(self.kb, "static/DVelop/x.css").read_text(encoding="utf-8"), "/* publicado */")
        self.assertIsNone(vista.archivo(self.kb, "static/no-esta.js"))

    def test_no_sale_de_las_carpetas(self):
        self.assertIsNone(vista.archivo(self.kb, "static/../../../secreto.txt"))
        self.assertIsNone(vista.archivo(self.kb, "../secreto.txt"))
        self.assertIsNone(vista.archivo(self.kb, "static/"))


if __name__ == "__main__":
    unittest.main()
