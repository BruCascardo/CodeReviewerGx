import unittest

from gxp.revisor.pruebas import asignar, leer
from gxp.revisor.reglas import cargar

VARIABLES = """
attri_i('Usada',[ 'Usada',int,9,0,'',0,'x','',1 ]).
"""


def revisar(*lineas, tipo="proc"):
    fu = leer("X.P", "\n".join(lineas), extra=VARIABLES, tipo=tipo)
    regla = cargar()["variables-sin-declarar"]()
    if not regla.aplica(fu, None):
        return None
    return [(h.severidad, h.mensaje) for h in regla.revisar(fu, None)]


class VariablesSinDeclarar(unittest.TestCase):
    def test_marca_la_que_se_usa_sin_declarar(self):
        hs = revisar(asignar(1, "Usada", "t(1,3,0,0)"), asignar(3, "Fantasma", "t(1,3,0,0)"),
                     asignar(4, "fantasma", "t(1,3,0,0)"))
        self.assertEqual(hs, [("advertencia", "La variable &Fantasma se usa y no esta declarada")])

    def test_todas_declaradas(self):
        self.assertEqual(revisar(asignar(1, "Usada", "t(1,3,0,0)")), [])

    def test_no_aplica_a_otros_tipos(self):
        self.assertIsNone(revisar(asignar(1, "Fantasma", "t(1,3,0,0)"), tipo="web"))
