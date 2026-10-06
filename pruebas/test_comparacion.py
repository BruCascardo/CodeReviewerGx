"""Rutas, comparaciones, verificaciones y volatiles (gxp.comparacion)."""
import datetime as dt
import unittest

from gxp import comparacion as C

SALIDA = {
    "outGet": {
        "Output": {"Ok": True, "Messages": [{"Code": "OK  ", "Type": 3, "Texto": "listo"}]},
        "Registro": {"Id": 7, "Tipo": "DETALLE   ", "Importe": 10.5, "Fecha": "2026-01-02"},
        "Lista": [{"A": 1, "B": "x"}, {"A": 2, "B": "y"}, {"A": 3, "B": "z"}],
    }
}


def diffs_parcial(e, o, **opts):
    d = []
    C.parcial(e, o, "", C.Opciones(**opts), d)
    return d


class Rutas(unittest.TestCase):
    def test_obtener(self):
        self.assertEqual(C.obtener(SALIDA, "outGet.Registro.Id"), (True, 7, False))
        self.assertEqual(C.obtener(SALIDA, "outget.registro.id"), (True, 7, False))  # sin mayusculas
        self.assertEqual(C.obtener(SALIDA, "outGet.Lista[-1].A"), (True, 3, False))
        self.assertEqual(C.obtener(SALIDA, "outGet.Lista[*].A"), (True, [1, 2, 3], True))
        self.assertEqual(C.obtener(SALIDA, "outGet.Lista.largo"), (True, 3, False))
        self.assertEqual(C.obtener(SALIDA, "outGet.NoEsta"), (False, None, False))
        self.assertEqual(C.obtener(SALIDA, "$"), (True, SALIDA, False))

    def test_patron(self):
        self.assertEqual(C.patron_de("out.Lista[3].Fecha"), "out.Lista[*].Fecha")


class Comparacion(unittest.TestCase):
    def test_parcial_y_espacios(self):
        self.assertEqual(diffs_parcial({"outGet": {"Registro": {"Tipo": "DETALLE"}}}, SALIDA), [])
        d = diffs_parcial({"outGet": {"Registro": {"Tipo": "OTRO"}}}, SALIDA)
        self.assertEqual([(x["ruta"], x["tipo"]) for x in d], [("outGet.Registro.Tipo", "valor")])
        d = diffs_parcial({"outGet": {"Registro": {"Tipo": "DETALLE"}}}, SALIDA, recortarEspacios=False)
        self.assertEqual(len(d), 1)

    def test_coleccion_omitida_es_vacia(self):
        self.assertEqual(diffs_parcial({"outGet": {"Otra": []}}, SALIDA), [])
        self.assertEqual(diffs_parcial({"outGet": {"Otra": "<<vacio>>"}}, SALIDA), [])
        self.assertEqual(len(diffs_parcial({"outGet": {"Otra": 1}}, SALIDA)), 1)

    def test_comodines(self):
        casos = {"<<numero>>": 7, "<<texto>>": "a", "<<booleano>>": True, "<<fecha>>": "2026-01-02",
                 "<<fechahora>>": "2026-01-02T10:00:00", "<<regex:^D>>": "DET", "<<contiene:ET>>": "DETALLE",
                 "<<empieza:DE>>": "DETALLE", "<<mayor:5>>": 7, "<<menor:9>>": 7, "<<distinto:3>>": 7,
                 "<<no_vacio>>": "x", "<<vacio>>": "  ", "<<cualquiera>>": None}
        for comodin, valor in casos.items():
            self.assertEqual(diffs_parcial({"v": comodin}, {"v": valor}), [], comodin)
        self.assertEqual(len(diffs_parcial({"v": "<<numero>>"}, {"v": "7"})), 1)
        self.assertIn("comodin desconocido", diffs_parcial({"v": "<<raro>>"}, {"v": 1})[0]["mensaje"])

    def test_tolerancia_numerica(self):
        self.assertEqual(diffs_parcial({"v": 1.0}, {"v": 1.0000001}), [])
        self.assertEqual(len(diffs_parcial({"v": 1.0}, {"v": 1.1})), 1)
        self.assertEqual(diffs_parcial({"v": 10}, {"v": "10"}), [])

    def test_listas(self):
        d = diffs_parcial({"L": [1, 2]}, {"L": [1, 2, 3]})
        self.assertEqual([x["tipo"] for x in d], ["largo"])
        self.assertEqual(diffs_parcial({"L": [{"A": 3}]}, {"L": [{"A": 1}, {"A": 3}]}, listasParciales=True), [])

    def test_aprobada_total(self):
        nueva = {"outGet": {**SALIDA["outGet"], "Registro": {**SALIDA["outGet"]["Registro"], "Importe": 11, "Nuevo": "x"}}}
        d, avisos = C.aprobada(SALIDA, nueva, C.Opciones())
        self.assertEqual([(x["ruta"], x["tipo"]) for x in d], [("outGet.Registro.Importe", "valor")])
        self.assertEqual(len(avisos), 1)
        self.assertIn("outGet.Registro.Nuevo", avisos[0])

    def test_aprobada_ignorar_y_volatiles(self):
        nueva = {"outGet": {**SALIDA["outGet"], "Registro": {**SALIDA["outGet"]["Registro"], "Importe": 99, "Id": 8}}}
        opts = C.Opciones(ignorar=["outGet.Registro.Importe"], volatiles=["outGet.Registro.Id"])
        self.assertEqual(C.aprobada(SALIDA, nueva, opts), ([], []))
        nueva["outGet"]["Registro"]["Id"] = "texto"  # una volatil que cambia de tipo si es diferencia
        self.assertEqual([x["tipo"] for x in C.aprobada(SALIDA, nueva, opts)[0]], ["tipo"])

    def test_ignorar_indice_negativo(self):
        nueva = {"outGet": {**SALIDA["outGet"], "Lista": SALIDA["outGet"]["Lista"][:2] + [{"A": 9, "B": "z"}]}}
        self.assertEqual(C.aprobada(SALIDA, nueva, C.Opciones(ignorar=["outGet.Lista[-1].A"]))[0], [])

    def test_aprobada_estructura(self):
        nueva = {"outGet": {**SALIDA["outGet"], "Lista": [{"A": 5, "B": "q"}], "Registro": {**SALIDA["outGet"]["Registro"], "Importe": 1}}}
        self.assertEqual(C.aprobada(SALIDA, nueva, C.Opciones(), "estructura")[0], [])
        mal = {"outGet": {**nueva["outGet"], "Output": {"Ok": False, "Messages": [{"Code": "ERR", "Type": 1, "Texto": "x"}]}}}
        d = C.aprobada(SALIDA, mal, C.Opciones(), "estructura")[0]
        self.assertEqual(sorted(x["ruta"] for x in d), ["outGet.Output.Messages[*].Code", "outGet.Output.Ok"])


class Verificaciones(unittest.TestCase):
    def v(self, ruta, op, valor=None, **kw):
        return C.verificar(SALIDA, {"ruta": ruta, "op": op, "valor": valor, **kw}, C.Opciones())

    def test_operadores(self):
        bien = [("outGet.Output.Ok", "igual", True), ("outGet.Registro.Tipo", "igual", "DETALLE"),
                ("outGet.Registro.Id", "distinto", 8), ("outGet.Output.Messages[*].Code", "contiene", "OK"),
                ("outGet.Registro.Tipo", "no_contiene", "ZZ"), ("outGet.Registro.Tipo", "empieza", "DET"),
                ("outGet.Registro.Tipo", "termina", "LLE"), ("outGet.Registro.Tipo", "regex", "^D.*E$"),
                ("outGet.Registro.Id", "mayor", 5), ("outGet.Registro.Id", "mayor_igual", 7), ("outGet.Registro.Id", "menor", 9),
                ("outGet.Registro.Id", "menor_igual", 7), ("outGet.Registro.Id", "entre", [1, 10]), ("outGet.Registro.Id", "en", [1, 7]),
                ("outGet.Registro", "existe", None), ("outGet.Nada", "no_existe", None), ("outGet.Nada", "vacio", None),
                ("outGet.Registro.Tipo", "no_vacio", None), ("outGet.Lista", "largo", 3), ("outGet.Lista", "largo_min", 2),
                ("outGet.Lista", "largo_max", 3), ("outGet.Registro.Importe", "tipo", "numero"),
                ("outGet.Registro", "coincide", {"Id": 7}), ("outGet.Lista", "contiene", {"A": 2}),
                ("outGet.Registro.Fecha", "mayor", "2025-12-31"), ("outGet", "contiene", "Registro")]
        for ruta, op, valor in bien:
            r = self.v(ruta, op, valor)
            self.assertTrue(r["ok"], (ruta, op, valor, r["mensaje"]))
        self.assertEqual(set(C.OPERADORES), {op for _, op, _ in bien} | {"vacio"})

    def test_fallas_y_mensajes(self):
        r = self.v("outGet.Registro.Id", "igual", 8)
        self.assertEqual((r["ok"], r["obtenido"], r["mensaje"]), (False, 7, "es distinto"))
        self.assertEqual(self.v("outGet.Nada", "igual", 1)["mensaje"], "la ruta no existe")
        self.assertEqual(self.v("x", "raro", 1)["mensaje"], "la ruta no existe")
        self.assertEqual(self.v("outGet.Registro.Id", "raro", 1)["mensaje"], "operador desconocido 'raro'")
        self.assertEqual(self.v("outGet.Registro.Id", "entre", 3)["mensaje"], "'entre' necesita [desde, hasta]")

    def test_cada(self):
        self.assertTrue(self.v("outGet.Lista[*].A", "mayor", 0, cada=True)["ok"])
        r = self.v("outGet.Lista[*].A", "mayor", 1, cada=True)
        self.assertFalse(r["ok"])
        self.assertIn("[0] 1", r["mensaje"])


class ResumenVolatilesSugerencias(unittest.TestCase):
    def test_resumir(self):
        nueva = {"outGet": {**SALIDA["outGet"], "Lista": [{"A": x["A"] * 10, "B": x["B"]} for x in SALIDA["outGet"]["Lista"]],
                            "Output": {"Ok": False, "Messages": []}}}
        d, _ = C.aprobada(SALIDA, nueva, C.Opciones())
        grupos = C.resumir(d, nueva)
        self.assertEqual(grupos[0]["ruta"], "outGet.Output.Ok")  # lo que define el resultado va primero
        lista = next(g for g in grupos if g["ruta"] == "outGet.Lista[*].A")
        self.assertEqual((lista["cantidad"], lista["de"]), (3, 3))
        self.assertEqual(C.texto_grupo(lista), "outGet.Lista[*].A: 1 -> 10 en 3 de 3 elementos")

    def test_volatiles(self):
        hoy = dt.date.today().strftime("%Y-%m-%d")
        a = {"out": {"Id": 1, "Alta": f"{hoy}T10:00", "Output": {"Ok": True}, "L": [1, 2]}}
        b = {"out": {"Id": 2, "Alta": f"{hoy}T10:00", "Output": {"Ok": False}, "L": [1]}}
        rutas, avisos = C.detectar_volatiles(a, b)
        self.assertEqual(rutas, ["out.Alta", "out.Id", "out.L"])
        self.assertTrue(any("out.Output.Ok cambia" in x for x in avisos))
        self.assertTrue(any("out.L cambia de largo" in x for x in avisos))
        self.assertEqual(C.volatiles_por_valor(a), {"out.Alta"})

    def test_sugerir(self):
        s = C.sugerir(SALIDA)
        marcadas = [(x["ruta"], x["op"], x["valor"]) for x in s if x["marcada"]]
        self.assertEqual(marcadas, [("outGet.Output.Ok", "igual", True), ("outGet.Output.Messages[*].Code", "contiene", "OK")])
        sql = C.sugerir({"filas": [{"n": 3}], "cantidad": 1})
        self.assertEqual([(x["ruta"], x["valor"]) for x in sql], [("cantidad", 1), ("filas[0].n", 3)])

    def test_sugerir_con_messages_raro(self):
        self.assertEqual(C.sugerir({"out": {"Output": {"Ok": True, "Messages": 3}}})[0]["ruta"], "out.Output.Ok")

    def test_describir(self):
        self.assertEqual(C.describir({"a": 1}), '{"a": 1}')
        self.assertTrue(C.describir("x" * 500).endswith("..."))


if __name__ == "__main__":
    unittest.main()
