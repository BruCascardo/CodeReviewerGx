"""Datos de la pantalla Revision (gxp/revisor/panel.py), con la KB falsa de test_lineabase."""
import unittest
from unittest import mock

from gxp.revisor import panel
from gxp.revisor.pruebas.test_lineabase import COMMIT, LLAMA_PRC_COMMIT, ConKBFalsa


class Panel(ConKBFalsa):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(panel, "VIGENCIA_LISTADO", 0)  # sin cache entre pedidos
        p.start()
        self.parches.append(p)

    def nombres(self, **kw):
        return [o["objeto"] for o in panel.objetos([self.kb], **kw)["objetos"]]

    def test_orden_filtros_y_nuevos(self):
        self.escribir("X.Viejo", COMMIT)
        self.escribir("X.Limpio", "")
        self.escribir("X.Medio", COMMIT)
        self.revisar()  # linea base
        self.escribir("X.Reciente", LLAMA_PRC_COMMIT)  # creado despues: todo lo suyo es nuevo

        # Lo recien modificado primero, aunque todavia no lo haya revisado un build.
        self.assertEqual(self.nombres(), ["X.Reciente", "X.Medio", "X.Limpio", "X.Viejo"])
        o = panel.objetos([self.kb])["objetos"][0]
        self.assertTrue(o["cambio"])
        self.assertEqual([h["nuevo"] for h in o["hallazgos"]], [True])

        self.assertEqual(self.nombres(filtro="problemas"), ["X.Reciente", "X.Medio", "X.Viejo"])
        self.assertEqual(self.nombres(filtro="nuevos"), ["X.Reciente"])
        self.assertEqual(self.nombres(texto="medio"), ["X.Medio"])

        # Despues de revisar los cambios sigue siendo nuevo (lo introdujo su ultima modificacion).
        panel.revisar_cambios([self.kb])
        o = panel.objetos([self.kb], filtro="nuevos")["objetos"]
        self.assertEqual([(x["objeto"], x["cambio"]) for x in o], [("X.Reciente", False)])

    def test_paginas(self):
        for i in range(5):
            self.escribir(f"X.P{i}", "")
        self.revisar()
        r = panel.objetos([self.kb], limite=2)
        self.assertEqual([o["objeto"] for o in r["objetos"]], ["X.P4", "X.P3"])
        r = panel.objetos([self.kb], limite=2, desde=r["siguiente"])
        self.assertEqual([o["objeto"] for o in r["objetos"]], ["X.P2", "X.P1"])
        r = panel.objetos([self.kb], limite=2, desde=r["siguiente"])
        self.assertEqual([o["objeto"] for o in r["objetos"]], ["X.P0"])
        self.assertIsNone(r["siguiente"])

    def test_ignorados_no_aparecen(self):
        self.escribir("WWPBaseObjects.Algo", COMMIT)
        self.escribir("X.P", "")
        with mock.patch("gxp.revisor.configuracion.cargar",
                        lambda: panel.configuracion.Configuracion({"ignorar": ["wwpbaseobjects.*"]})):
            self.revisar()
            self.assertEqual(self.nombres(), ["X.P"])

    def test_fuente_con_hallazgos(self):
        self.escribir("X.P", COMMIT + "\n" + LLAMA_PRC_COMMIT)
        f = panel.fuente_objeto(self.kb, "X.P")
        self.assertEqual([l["texto"] for l in f["lineas"]], ["Commit", "X.Global.prcCommit()"])
        self.assertEqual(sorted(h["linea"] for h in f["hallazgos"]), [8, 9])


if __name__ == "__main__":
    unittest.main()
