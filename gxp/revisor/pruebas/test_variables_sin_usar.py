import unittest

from gxp.revisor.pruebas import asignar, leer
from gxp.revisor.reglas import cargar

VARIABLES = """
attri_i('Usada',[ 'Usada',int,9,0,'',0,'x','',1 ]).
attri_i('Huerfana',[ 'Huerfana',int,9,0,'',0,'x','',2 ]).
attri_i('Gx_out',[ 'Gx_out',char,9,0,'',0,'x','',3 ]).
"""


def revisar(*lineas, tipo="proc"):
    fu = leer("X.P", "\n".join(lineas), extra=VARIABLES, tipo=tipo)
    regla = cargar()["variables-sin-usar"]()
    if not regla.aplica(fu, None):
        return None
    return [(h.severidad, h.mensaje) for h in regla.revisar(fu, None)]


class VariablesSinUsar(unittest.TestCase):
    def test_marca_la_que_no_se_usa(self):
        self.assertEqual(revisar(asignar(1, "Usada", "t(1,3,0,0)")),
                         [("advertencia", "La variable &Huerfana esta declarada y no se usa")])

    def test_todas_usadas(self):
        self.assertEqual(revisar(asignar(1, "Usada", "t(1,3,0,0)"), asignar(2, "Huerfana", "t(1,3,0,0)")), [])

    def test_no_aplica_a_otros_tipos(self):
        self.assertIsNone(revisar(asignar(1, "Usada", "t(1,3,0,0)"), tipo="web"))

