"""Cambios de un caso respecto de su corrida anterior (suites.reportes) y su resumen en el build."""
import unittest

from gxp.automatico.resumen import lineas_consola, texto_resumen
from gxp.suites.reportes import ARREGLADA, NUEVA, SIGUE, cambio, cambios


class Cambio(unittest.TestCase):
    def test_nueva_si_andaba_y_ahora_no(self):
        self.assertEqual(cambio("ok", "falla"), NUEVA)
        self.assertEqual(cambio("ok", "error"), NUEVA)

    def test_sigue_si_ya_fallaba(self):
        self.assertEqual(cambio("falla", "falla"), SIGUE)
        self.assertEqual(cambio("falla", "error"), SIGUE)

    def test_arreglada(self):
        self.assertEqual(cambio("error", "ok"), ARREGLADA)

    def test_sin_cambio_o_sin_dato(self):
        self.assertIsNone(cambio("ok", "ok"))
        self.assertIsNone(cambio(None, "falla"))  # primera corrida: no se sabe si es nueva
        self.assertIsNone(cambio("omitido", "falla"))
        self.assertIsNone(cambio("falla", "omitido"))

    def test_cuenta(self):
        casos = [{"cambio": NUEVA}, {"cambio": NUEVA}, {"cambio": SIGUE}, {"cambio": None}, {}]
        self.assertEqual(cambios(casos), {NUEVA: 2, ARREGLADA: 0, SIGUE: 1})


class Resumen(unittest.TestCase):
    def res(self, nuevas):
        return {"totales": {"ok": 5, "falla": 2, "error": 0}, "corridas": [1], "errores": [], "nuevas": nuevas}

    def test_texto(self):
        self.assertEqual(texto_resumen(self.res(1)), "5 ok, 2 con fallas, 1 nueva desde el build anterior")
        self.assertEqual(texto_resumen(self.res(2)), "5 ok, 2 con fallas, 2 nuevas desde el build anterior")
        self.assertEqual(texto_resumen(self.res(0)), "5 ok, 2 con fallas")

    def test_consola_marca_la_nueva(self):
        res = {"estado": "falla", "kb": "K", "texto": "x", "errores": [], "corridas": [],
               "fallas": [{"estado": "falla", "suite": "S", "caso": "a", "cambio": NUEVA, "detalle": ""},
                          {"estado": "falla", "suite": "S", "caso": "b", "cambio": SIGUE, "detalle": ""}]}
        lineas = lineas_consola(res)
        self.assertIn("(NUEVA)", lineas[1])
        self.assertNotIn("(NUEVA)", lineas[2])


if __name__ == "__main__":
    unittest.main()
