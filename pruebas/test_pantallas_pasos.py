"""Pasos de pantalla (gxp/pantallas_pasos.py): lo que no necesita el motor ni las KBs.

    python -m unittest pruebas.test_pantallas_pasos
"""
import json
import unittest
from unittest import mock

from gxp import pantallas_pasos as pp


class KbFalsa:
    nombre = "Generales"


EVT = {
    "REFRESH": [[{"av": "GRID_nFirstRecordOnPage", "type": "int"}, {"ctrl": "GRID", "prop": "Rows"}, {"ctrl": "vSEL"},
                 {"av": "AV1Sel", "fld": "vSEL", "type": "svchar"}, {"av": "AV2Nombre", "fld": "vNOMBRE"}], []],
    "'DOINSERT'": [[{"av": "AV2Nombre", "fld": "vNOMBRE"}, {"av": "A1Id", "fld": "ID", "grid": 78}], []],
    "ENTER": [[{"postForm": True}, {"av": "Gx_mode", "fld": "vMODE"}, {"av": "AV3Id", "fld": "vID", "hsh": True}], []],
}


class Js(unittest.TestCase):
    def test_literal_de_genexus(self):
        self.assertEqual(pp.js("{handler:'e1',iparms:[{av:'A',fld:'B',pic:'',hsh:true,type:'int'},{ctrl:'GRID',prop:'Rows'}],n:-2.5,x:null}"),
                         {"handler": "e1", "iparms": [{"av": "A", "fld": "B", "pic": "", "hsh": True, "type": "int"},
                                                      {"ctrl": "GRID", "prop": "Rows"}], "n": -2.5, "x": None})

    def test_textos_con_comillas_escapadas(self):
        self.assertEqual(pp.js("['it\\'s', \"a\\\"b\"]"), ["it's", 'a"b'])


class Parametros(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(pp, "evt_parms", lambda kb, obj: EVT)
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_orden_y_nombres(self):
        meta = pp.parametros_evento(KbFalsa(), "x", ["REFRESH"])
        self.assertEqual(pp.nombres(meta), ["GRID_nFirstRecordOnPage", "GRID.Rows", "vSEL.combo", "vSEL", "vNOMBRE"])

    def test_varios_eventos_sin_repetir_y_la_grilla_gana(self):
        meta = pp.parametros_evento(KbFalsa(), "x", ["REFRESH", "'DOINSERT'"])
        self.assertEqual(pp.nombres(meta), ["GRID_nFirstRecordOnPage", "GRID.Rows", "vSEL.combo", "vSEL", "vNOMBRE", "ID"])

    def test_post_form_no_ocupa_lugar(self):
        self.assertEqual(pp.nombres(pp.parametros_evento(KbFalsa(), "x", ["ENTER"])), ["vMODE", "vID"])


class Grabacion(unittest.TestCase):
    def test_cambios_del_formulario(self):
        fp = {"Z175MonSimbolo": "US$", "MONSIMBOLO": "U$Z", "Z23MonId": "2", "MONID": "2", "Mode": "UPD"}
        self.assertEqual(pp._cambios_formulario(fp), {"MONSIMBOLO": ("US$", "U$Z")})

    def test_recarga_de_grilla_ida_y_vuelta(self):
        q = "gxajaxGridRefresh_Grid,10,%7B%22s%22%3A%22MONNOMBRE%22%7D,MONNOMBRE,DOL%20X,gx-no-cache=123"
        accion, valores = pp._accion_de(q)
        self.assertEqual(accion, "gxajaxGridRefresh_Grid")
        self.assertEqual([pp._valor_query(v) for v in valores], ["10", {"s": "MONNOMBRE"}, "MONNOMBRE", "DOL X"])
        self.assertEqual(",".join(pp._query_valor(pp._valor_query(v)) for v in valores), "10,%7B%22s%22%3A%22MONNOMBRE%22%7D,MONNOMBRE,DOL%20X")
        self.assertIsNone(pp._accion_de("dyncomponent,W0038,,2"))

    def test_prefijo_de_la_sesion(self):
        p = pp._prefijo(KbFalsa(), "v1")
        self.assertEqual(p.sub("@", "http://localhost:8765/vista/Generales/v1/servlet/x y /vista/Generales/v1/z"), "@/servlet/x y @/z")


class Salida(unittest.TestCase):
    def test_pagina(self):
        html = ("<html><head><title>Monedas</title></head><body>"
                "<input type=\"hidden\" name=\"GridContainerDataV\" value='[[\"1\",\"PESOS\"],[\"2\",\"DOLARES\"]]'/>"
                "<input type=\"hidden\" name=\"GXState\" value='{\"vPGMNAME\":\"X\",\"vNOMBRE_MPAGE\":\"no\",\"gxhash_vPGMNAME\":\"gxpruebas\","
                "\"vLINK\":\"/vista/Generales/prueba/servlet/com.x\"}'/></body></html>")
        d = pp.salida(KbFalsa(), "prueba", {"estado": 200, "tipo": "text/html", "cuerpo": html})
        self.assertEqual(d, {"estado": 200, "titulo": "Monedas", "grillas": {"Grid": [["1", "PESOS"], ["2", "DOLARES"]]},
                             "valores": {"vPGMNAME": "X", "vLINK": "servlet/com.x"}})

    def test_evento(self):
        j = {"gxValues": [{"CmpContext": "", "IsMasterPage": "false", "AV1Filtro": "DOL"}],
             "gxHiddens": {"gxhash_vX": "gxpruebas", "GX_AUTH_X": "gxpruebas", "vPGMNAME": "X", "GRID_nEOF": "1"},
             "gxGrids": [{"GridName": "Grid", "CmpContext": "", "0": {"Props": [["MONID_0001", "2", ""], ["MONNOMBRE_0001", "DOLARES"]]}}],
             "gxProps": [{"CmpContext": "", "BTNINSERT": {"Visible": "0", "Class": "x"}, "vSEL": {"Values": "{}"}}],
             "gxMessages": {"MAIN": [{"text": "Hecho"}]}}
        d = pp.salida(KbFalsa(), "prueba", {"estado": 200, "tipo": "application/json", "cuerpo": json.dumps(j)})
        self.assertEqual(d["valores"], {"AV1Filtro": "DOL"})
        self.assertEqual(d["ocultos"], {"vPGMNAME": "X", "GRID_nEOF": "1"})
        self.assertEqual(d["grillas"], {"Grid": [{"MONID": "2", "MONNOMBRE": "DOLARES"}]})
        self.assertEqual(d["propiedades"], {"BTNINSERT": {"Visible": "0"}})
        self.assertEqual(d["mensajes"], [{"text": "Hecho"}])


class Caso(unittest.TestCase):
    def test_es_de_pantallas(self):
        self.assertTrue(pp.es_de_pantallas({"pasos": [{"sql": "x"}, {"pantalla": "A.B"}]}))
        self.assertFalse(pp.es_de_pantallas({"pasos": [{"objeto": "A.B"}]}))

    def test_nombre_del_caso(self):
        pasos = [{"pantalla": "A.WW", "parametros": []}, {"pantalla": "A.WW", "evento": "REFRESH"},
                 {"pantalla": "A.Trn", "parametros": ["UPD", "2"]}, {"pantalla": "A.Trn", "evento": "ENTER"}]
        self.assertEqual(pp.nombre_caso(pasos), "WW → Trn (2 eventos)")


if __name__ == "__main__":
    unittest.main()
