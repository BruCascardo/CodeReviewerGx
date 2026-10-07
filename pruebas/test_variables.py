"""${variables} de los casos (gxp.suites.variables): reemplazo, salida aprobada con variables y aprobacion."""
import unittest

from gxp.suites.variables import VariableIndefinida, con_variables, reponer_variables, sustituir


class Sustituir(unittest.TestCase):
    def test_conserva_el_tipo(self):
        self.assertEqual(sustituir({"ItfId": "${idItf}", "t": "itf ${idItf}"}, {"idItf": 1}), {"ItfId": 1, "t": "itf 1"})

    def test_estricto_falla_si_no_existe(self):
        with self.assertRaises(VariableIndefinida):
            sustituir({"a": "${nada}"}, {})

    def test_no_estricto_deja_el_texto(self):
        self.assertEqual(sustituir({"a": "${nada}", "b": "x ${nada} y", "c": "${v}"}, {"v": 2}, estricto=False),
                         {"a": "${nada}", "b": "x ${nada} y", "c": 2})

    def test_con_variables(self):
        self.assertTrue(con_variables({"Registros": [{"ItfId": "${idItf}"}]}))
        self.assertFalse(con_variables({"Registros": [{"ItfId": 1, "t": "$ {no}"}]}))


class Reponer(unittest.TestCase):
    def test_conserva_las_variables_donde_estaban(self):
        anterior = {"Registros": [{"ItfId": "${idItf}", "Nombre": "A"}, {"ItfId": "${idItf}", "Nombre": "B"}], "Ok": True}
        nuevo = {"Registros": [{"ItfId": 1, "Nombre": "A2"}, {"ItfId": 1, "Nombre": "B"}, {"ItfId": 1, "Nombre": "C"}],
                 "Ok": True, "Nuevo": 5}
        self.assertEqual(reponer_variables(anterior, nuevo), {
            "Registros": [{"ItfId": "${idItf}", "Nombre": "A2"}, {"ItfId": "${idItf}", "Nombre": "B"}, {"ItfId": 1, "Nombre": "C"}],
            "Ok": True, "Nuevo": 5})

    def test_campo_que_ya_no_esta_se_va(self):
        self.assertEqual(reponer_variables({"a": "${x}", "b": 1}, {"b": 2}), {"b": 2})

    def test_sin_anterior(self):
        self.assertEqual(reponer_variables(None, {"a": 1}), {"a": 1})


if __name__ == "__main__":
    unittest.main()
