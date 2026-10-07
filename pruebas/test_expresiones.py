"""Valores de una clave calculados en la base (gxp/campos/expresiones.py) y fechas relativas (gxp/suites/fechas.py).

    python -m unittest pruebas.test_expresiones
"""
import datetime as dt
import unittest
from unittest import mock

import gxp.campos as campos
from gxp.campos import expresiones, indice
from gxp.suites import fechas


def _indice():
    ix = indice.Indice()
    ix.agregar_tabla(indice.Tabla("cbhCupon", ["CuponId"], "CuponTipo", "", "int",
                                  ["CuponId", "CuponTipo", "CuponEstado"], {"CuponEstado": 283}))
    ix.agregar_tabla(indice.Tabla("cbhCuponDetalle", ["CuponId", "CuponDetSec"], None, "", "int",
                                  ["CuponId", "CuponDetSec", "Importe"]))
    ix.agregar_tabla(indice.Tabla("cbhLoteDetalle", ["LoteId", "LoteDetSec"], None, "", "int",
                                  ["LoteId", "LoteDetSec", "CuponId"]))
    ix.agregar_tabla(indice.Tabla("gntTipo", ["TipoCod"], None, "", "char"))
    ix.valores[283] = [{"valor": "PRO", "nombre": "EN_PROCESO", "descripcion": "En proceso"},
                       {"valor": "PEN", "nombre": "PENDIENTE", "descripcion": "Pendiente"}]
    return ix


class Parsear(unittest.TestCase):
    def test_atributo_tabla_y_condiciones(self):
        p = expresiones.parsear("con_hijos", "CuponId:cbhCuponDetalle|CuponEstado=PENDIENTE, CuponId != 3")
        self.assertEqual((p.atributo, p.hija), ("CuponId", "cbhCuponDetalle"))
        self.assertEqual(p.condiciones, [("CuponEstado", "=", "PENDIENTE"), ("CuponId", "<>", "3")])

    def test_mal_escritas(self):
        for f, resto in [("existente", ""), ("existente", "CuponId|CuponEstado"), ("siguiente", "CuponId|A=1"),
                         ("existente", "CuponId:otra"), ("nada", "CuponId")]:
            with self.subTest(f=f, resto=resto), self.assertRaises(ValueError):
                expresiones.parsear(f, resto)


class Consulta(unittest.TestCase):
    def setUp(self):
        self.ix = _indice()

    def q(self, funcion, resto):
        return expresiones.consulta(self.ix, expresiones.parsear(funcion, resto))[1]

    def test_siguiente_existente_ultimo(self):
        self.assertEqual(self.q("siguiente", "CuponId"), "select coalesce(max(CuponId), 0) + 1 as valor from cbhCupon")
        self.assertEqual(self.q("existente", "cuponid"), "select t.CuponId as valor from cbhCupon t order by t.CuponId limit 1")
        self.assertEqual(self.q("ultimo", "CuponId"), "select t.CuponId as valor from cbhCupon t order by t.CuponId desc limit 1")

    def test_condicion_con_nombre_del_valor_del_dominio(self):
        self.assertIn("where t.CuponEstado = 'PEN' and t.CuponId > 10",
                      self.q("existente", "CuponId|CuponEstado=PENDIENTE,CuponId>10"))
        self.assertIn("t.CuponEstado = 'pendiente'", self.q("existente", "CuponId|CuponEstado='pendiente'"))  # entre comillas: tal cual
        self.assertIn("t.CuponTipo = 'O''Brien'", self.q("existente", "CuponId|CuponTipo=O'Brien"))

    def test_hijas_por_nivel_y_por_clave_foranea(self):
        q = self.q("con_hijos", "CuponId")
        self.assertIn("(exists (select 1 from cbhCuponDetalle h where h.CuponId = t.CuponId) or "
                      "exists (select 1 from cbhLoteDetalle h where h.CuponId = t.CuponId))", q)
        q = self.q("sin_hijos", "CuponId:cbhLoteDetalle")
        self.assertIn("where not exists (select 1 from cbhLoteDetalle h", q)
        self.assertNotIn("cbhCuponDetalle", q)

    def test_errores(self):
        for f, resto in [("siguiente", "TipoCod"), ("existente", "Nada"), ("existente", "CuponId|Otro=1"),
                         ("con_hijos", "CuponId:gntTipo"), ("con_hijos", "TipoCod")]:
            with self.subTest(f=f, resto=resto), self.assertRaises(ValueError):
                self.q(f, resto)


class Resolver(unittest.TestCase):
    def test_valor_con_el_tipo_de_la_clave(self):
        ix = _indice()
        with mock.patch.object(expresiones.indice, "de_kb", return_value=ix), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": [{"valor": "60"}]})):
            self.assertEqual(expresiones.resolver(None, "siguiente", "CuponId"), 60)
        with mock.patch.object(expresiones.indice, "de_kb", return_value=ix), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": [{"valor": "0012 "}]})):
            self.assertEqual(expresiones.resolver(None, "existente", "TipoCod"), "0012")  # un char sigue siendo texto

    def test_sin_filas_dice_que_no_hay(self):
        with mock.patch.object(expresiones.indice, "de_kb", return_value=_indice()), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": []})):
            with self.assertRaises(ValueError) as c:
                expresiones.resolver(None, "existente", "CuponId|CuponEstado=EN_PROCESO")
        self.assertIn("no hay ningun CuponId en cbhCupon que cumpla CuponEstado = EN_PROCESO", str(c.exception))


class Opciones(unittest.TestCase):
    def test_lo_que_ofrece_el_combo(self):
        ix = _indice()
        ops = [v for v, _ in campos.opciones_dinamicas(ix, ix.tablas["cuponid"])]
        self.assertEqual(ops, ["${siguiente.CuponId}", "${existente.CuponId}", "${ultimo.CuponId}", "${con_hijos.CuponId}",
                               "${sin_hijos.CuponId}", "${existente.CuponId|CuponEstado=EN_PROCESO}",
                               "${existente.CuponId|CuponEstado=PENDIENTE}"])

    def test_la_otra_parte_de_la_clave_queda_como_condicion(self):
        ix = _indice()
        t = ix.todas["cbhcupondetalle"]
        ops = [v for v, _ in campos.opciones_dinamicas(ix, t, {"CuponId": "${existente.CuponId}", "Importe": 3})]
        self.assertIn("${existente.CuponDetSec|CuponId=${existente.CuponId}}", ops)
        self.assertIn("${siguiente.CuponDetSec}", ops)  # el siguiente es de toda la tabla: no lleva condicion


class Fechas(unittest.TestCase):
    AHORA = dt.datetime(2026, 1, 31, 10, 30, 0)  # sabado

    def f(self, e):
        return fechas.calcular(e, self.AHORA)

    def test_relativas(self):
        casos = {"hoy": "2026-01-31", "hoy+1": "2026-02-01", "hoy-31d": "2025-12-31", "hoy+1m": "2026-02-28",
                 "hoy-1a": "2025-01-31", "inicio_mes": "2026-01-01", "fin_mes": "2026-01-31", "fin_mes+1": "2026-02-28",
                 "inicio_mes-1": "2025-12-01", "inicio_anio": "2026-01-01", "fin_anio-1": "2025-12-31",
                 "habil_siguiente": "2026-02-02", "habil_anterior": "2026-01-30", "fecha_vacia": "",
                 "ahora+2h": "2026-01-31T12:30:00", "ahora-30min": "2026-01-31T10:00:00", "ahora+1d": "2026-02-01T10:30:00"}
        for e, esperado in casos.items():
            with self.subTest(e=e):
                self.assertEqual(self.f(e), esperado)

    def test_no_es_fecha_o_unidad_invalida(self):
        self.assertIsNone(self.f("cupon"))
        self.assertIsNone(self.f("hoy.x"))
        for e in ("hoy+2h", "fin_mes+1a", "ahora+1m"):
            with self.subTest(e=e), self.assertRaises(ValueError):
                self.f(e)


if __name__ == "__main__":
    unittest.main()
