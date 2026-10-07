"""Variables anidadas y dinamicas (gxp.suites.variables), 'omitirSiVacio' y el generador de validaciones
(gxp.suites.validaciones). No necesitan las KBs.

    python -m unittest pruebas.test_validaciones
"""
import unittest

from gxp.comparacion import Opciones
from gxp.suites import ejecucion, validaciones
from gxp.suites.variables import VariableIndefinida, mensaje_error, sustituir


class Anidadas(unittest.TestCase):
    def test_la_de_adentro_primero(self):
        pedidos = []
        vars_ = {"cupon": 7, "existente": lambda resto: pedidos.append(resto) or 3}
        self.assertEqual(sustituir("${existente.CuponCuotaSec|CuponId=${cupon}}", vars_), 3)
        self.assertEqual(pedidos, ["CuponCuotaSec|CuponId=7"])
        self.assertEqual(sustituir("x ${existente.A|B=${cupon}} y ${cupon}", vars_), "x 3 y 7")

    def test_el_valor_de_una_columna_de_datos_puede_ser_otra_variable(self):
        vars_ = {"CuponId": "${siguiente.CuponId}", "siguiente": lambda resto: 60}
        self.assertEqual(sustituir({"inCerrar": {"CuponId": "${CuponId}"}}, vars_), {"inCerrar": {"CuponId": 60}})

    def test_no_estricto_deja_el_texto_completo(self):
        self.assertEqual(sustituir("${existente.A|B=${nada}}", {}, estricto=False), "${existente.A|B=${nada}}")
        with self.assertRaises(VariableIndefinida):
            sustituir("${existente.A|B=${nada}}", {})

    def test_sin_cerrar_queda_como_texto(self):
        self.assertEqual(sustituir("a ${b", {"b": 1}), "a ${b")

    def test_fechas_desde_la_hora_del_caso(self):
        vars_ = {"ahora": "2026-01-31T10:30:00"}
        self.assertEqual(sustituir({"d": "${hoy+1}", "f": "${fin_mes+1}", "h": "${ahora+2h}"}, vars_),
                         {"d": "2026-02-01", "f": "2026-02-28", "h": "2026-01-31T12:30:00"})
        with self.assertRaises(VariableIndefinida) as c:
            sustituir("${hoy+2h}", vars_)
        self.assertIn("No se pudo calcular ${hoy+2h}", mensaje_error(c.exception))


class OmitirSiVacio(unittest.TestCase):
    def test_no_controla_la_verificacion_si_el_valor_queda_vacio(self):
        paso = {"verificaciones": [
            {"ruta": "out.Ok", "op": "igual", "valor": "${ok}"},
            {"ruta": "out.Messages[*].Code", "op": "contiene", "valor": "${codigo}", "omitirSiVacio": True}]}
        datos = {"out": {"Ok": False, "Messages": [{"Code": "ERR"}]}}
        for codigo, controladas in (("", 1), ("ERR", 2)):
            res = {"verificaciones": [], "diferencias": []}
            ejecucion._verificaciones(paso, datos, {"ok": False, "codigo": codigo}, Opciones(), res)
            self.assertEqual(len(res["verificaciones"]), controladas)
            self.assertTrue(all(v["ok"] for v in res["verificaciones"]))


class Generador(unittest.TestCase):
    AYUDAS = {
        "inset.cuponid": {"clave": {"atributo": "CuponId", "claves": ["CuponId"], "numerica": True}},
        "inset.estado": {"valores": [{"valor": "PEN", "nombre": "PENDIENTE"}, {"valor": "PAG", "nombre": "PAGADO"}]},
    }
    ENTRADA = {"inSet": {"CuponId": "5", "Estado": "PEN", "Nombre": "x", "Activo": True, "Importe": 0,
                         "Items": [{"Orden": 1}], "Datos": {"Nombre": "y"}}}

    def test_filas_propuestas(self):
        filas = [(t, r, v) for t, r, v, _ in validaciones._candidatas(self.ENTRADA, self.AYUDAS)]
        self.assertEqual(filas, [
            ("obligatorio", "inSet.CuponId", "0"),              # un id largo viene como texto: vacio es "0"
            ("no_existe", "inSet.CuponId", "${siguiente.CuponId}"),
            ("obligatorio", "inSet.Estado", ""),
            ("dominio", "inSet.Estado", "PAG"),                 # el que ya tiene, no
            ("obligatorio", "inSet.Nombre", ""),
            ("lista", "inSet.Items", []),                       # sin filas por campo adentro de la lista
            ("obligatorio", "inSet.Datos.Nombre", ""),
        ])                                                      # ni booleanos ni campos que ya estan vacios

    def test_columnas_con_nombres_repetidos(self):
        self.assertEqual(validaciones._columnas(["inSet.Nombre", "inSet.Datos.Nombre", "inSet.Estado"]),
                         {"inSet.Nombre": "inSet_Nombre", "inSet.Datos.Nombre": "inSet_Datos_Nombre", "inSet.Estado": "Estado"})

    def test_armar_caso(self):
        filas = [
            {"tipo": "base", "ruta": "", "valor": None, "prueba": "entrada valida", "ok": True, "codigo": "OK"},
            {"tipo": "obligatorio", "ruta": "inSet.Estado", "valor": "", "prueba": "Estado vacio", "ok": False,
             "codigo": "", "mensaje": "Falta el estado"},
        ]
        caso = validaciones.armar_caso("X.Set", self.ENTRADA, {"inSet.Estado": "Estado", "inSet.Nombre": "Nombre"}, filas,
                                       ruta_salida="outSet.Output")
        paso = caso["pasos"][0]
        self.assertEqual(paso["entrada"]["inSet"]["Estado"], "${Estado}")
        self.assertEqual(paso["entrada"]["inSet"]["Nombre"], "x")  # ninguna fila lo cambia: queda fijo
        self.assertEqual(caso["datos"], [
            {"prueba": "entrada valida", "Estado": "PEN", "ok": True, "codigo": "OK", "mensaje": ""},
            {"prueba": "Estado vacio", "Estado": "", "ok": False, "codigo": "", "mensaje": "Falta el estado"}])
        self.assertEqual([v["ruta"] for v in paso["verificaciones"]],
                         ["outSet.Output.Ok", "outSet.Output.Messages[*].Code", "outSet.Output.Messages[*].Texto"])
        self.assertEqual(caso["etiquetas"], ["validacion"])

    def test_sin_sdt_output_no_verifica(self):
        caso = validaciones.armar_caso("X.Get", {"Id": 1}, {"Id": "Id"}, [{"tipo": "obligatorio", "ruta": "Id", "valor": 0,
                                                                        "prueba": "Id vacio"}])
        self.assertNotIn("verificaciones", caso["pasos"][0])
        self.assertEqual(caso["datos"], [{"prueba": "Id vacio", "Id": 0}])


if __name__ == "__main__":
    unittest.main()
