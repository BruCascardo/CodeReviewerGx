"""La revision en el flujo de despues del build (gxp/automatico), con la KB falsa de test_lineabase."""
import unittest

from gxp import automatico
from gxp.revisor.pruebas.test_lineabase import COMMIT, LLAMA_PRC_COMMIT, ConKBFalsa


def resultado_suites(corridas=0, falla=0):
    """Lo que devuelve automatico.correr_kb, sin correr nada."""
    res = {"kb": "Falsa", "etiqueta": "", "corridas": [{"id": "x"}] * corridas, "errores": [],
           "totales": {"ok": corridas - falla, "falla": falla, "error": 0, "omitido": 0}, "fallas": [],
           "estado": "falla" if falla else ("ok" if corridas else "sin_pruebas")}
    res["texto"] = automatico.texto_resumen(res)
    return res


class DespuesDelBuild(ConKBFalsa):
    def test_error_nuevo_hace_fallar_el_build(self):
        self.escribir("X.P", COMMIT)
        automatico.revisar_kb(self.kb)                  # arma la linea base
        self.escribir("X.P", COMMIT + "\n" + LLAMA_PRC_COMMIT)  # el "build" agrega una llamada a prcCommit
        rev = automatico.revisar_kb(self.kb)
        self.assertEqual(rev["modo"], "cambiados")
        self.assertEqual(rev["nuevos"], {"error": 1, "advertencia": 0})
        self.assertEqual([(h["objeto"], h["linea"]) for h in rev["primeros"]], [("X.P", 9)])

        res = resultado_suites(corridas=2)
        automatico.agregar_revision(res, rev)
        self.assertEqual(res["estado"], "falla")
        self.assertEqual(res["texto"], "2 ok, 1 error nuevo de buenas prácticas")
        consola = "\n".join(automatico.lineas_consola(res))
        self.assertIn("NUEVO ERROR", consola)
        self.assertIn("X.P linea 9", consola)
        self.assertIn("(1 que ya estaban)", consola)

    def test_sin_cambios_no_cambia_el_estado(self):
        self.escribir("X.P", COMMIT)
        automatico.revisar_kb(self.kb)
        rev = automatico.revisar_kb(self.kb)
        res = resultado_suites(corridas=1)
        automatico.agregar_revision(res, rev)
        self.assertEqual(res["estado"], "ok")
        self.assertEqual(res["texto"], "1 ok, buenas prácticas: nada nuevo")
        self.assertFalse(automatico.hay_nuevos(rev))

    def test_kb_sin_suites_con_problemas_nuevos(self):
        self.escribir("X.P", "")
        automatico.revisar_kb(self.kb)
        self.escribir("X.P", COMMIT)
        res = resultado_suites()
        automatico.agregar_revision(res, automatico.revisar_kb(self.kb))
        self.assertEqual(res["estado"], "falla")
        self.assertEqual(res["texto"], "no hay suites, 1 error nuevo de buenas prácticas")

    def test_textos(self):
        t = automatico.texto_revision
        self.assertEqual(t({"nuevos": {"error": 2, "advertencia": 0}}), "2 errores nuevos de buenas prácticas")
        self.assertEqual(t({"nuevos": {"error": 0, "advertencia": 1}}), "1 advertencia nueva de buenas prácticas")
        self.assertEqual(t({"nuevos": {"error": 1, "advertencia": 3}}),
                         "1 error y 3 advertencias nuevos de buenas prácticas")
        self.assertEqual(t({"error": "x"}), "no se pudo revisar las buenas prácticas")


if __name__ == "__main__":
    unittest.main()
