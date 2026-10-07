"""Script previo de las suites (gxp.suites.script): separacion de sentencias, sentencias prohibidas y el entorno
de una corrida, con un motor falso."""
import threading
import unittest
from unittest import mock

from gxp.suites import script


class Sentencias(unittest.TestCase):
    def test_separa_por_punto_y_coma(self):
        s = script.sentencias("delete from a;\ndelete from b ;  ;\n")
        self.assertEqual([x[0] for x in s], ["delete from a", "delete from b"])

    def test_respeta_textos_y_comentarios(self):
        s = script.sentencias("insert into t values ('a;b', \"c;d\", 'it''s;');  -- fin; de linea\n"
                              "/* bloque; */ delete from `x;y`; # otro; comentario")
        self.assertEqual(len(s), 2)
        self.assertIn("'a;b'", s[0][0])
        self.assertTrue(s[1][1].startswith("delete from `x;y`"))

    def test_saltea_lo_que_es_solo_comentario(self):
        self.assertEqual(script.sentencias("-- nada\n/* tampoco */ ;"), [])

    def test_guion_sin_espacio_no_es_comentario(self):
        self.assertEqual(script.sentencias("select 1--1")[0][1], "select 1--1")


class Prohibidas(unittest.TestCase):
    def test_commit_implicito(self):
        for q in ("truncate table a", "TRUNCATE a", "drop table a", "alter table a add x int", "create table a (x int)",
                  "rename table a to b", "lock tables a write"):
            self.assertIn("commit implicito", script.prohibida(q), q)

    def test_manejo_de_transaccion(self):
        for q in ("commit", "rollback", "start transaction", "begin", "savepoint x", "set autocommit = 1"):
            self.assertIsNotNone(script.prohibida(q), q)

    def test_permitidas(self):
        for q in ("delete from a", "update a set x = 1", "insert into a values (1)", "select * from a",
                  "create temporary table t (x int)", "drop temporary table t", "set foreign_key_checks = 0"):
            self.assertIsNone(script.prohibida(q), q)

    def test_correr_sql_rechaza_antes_de_ejecutar(self):
        with mock.patch.object(script, "ejecutar_sql") as ej:
            with self.assertRaises(ValueError):
                script.correr_sql(None, "", "delete from a; truncate table b", 1000)
            ej.assert_not_called()

    def test_correr_sql_devuelve_la_ultima(self):
        respuestas = iter([({"ok": True}, {"actualizadas": 3}), ({"ok": True}, {"filas": [{"n": 0}], "cantidad": 1})])
        with mock.patch.object(script, "ejecutar_sql", lambda *a: next(respuestas)):
            r, datos = script.correr_sql(None, "", "delete from a; select count(*) n from a", 1000)
        self.assertEqual(datos["filas"], [{"n": 0}])


class Bloques(unittest.TestCase):
    def test_formatos(self):
        self.assertEqual(script.bloques("delete from a"), [{"ds": "", "sql": "delete from a"}])
        self.assertEqual(script.bloques([{"ds": "G", "query": "x"}, {"ds": "H", "sql": "  "}]), [{"ds": "G", "sql": "x"}])
        self.assertEqual(script.bloques(None), [])


class MotorFalso:
    """Lo minimo del motor para el Entorno: lock, sql, marcar, volver y fin de transaccion."""

    def __init__(self):
        self.lock = threading.RLock()
        self.llamadas = []
        self.volver_resp = {"ok": True, "puntos": 1, "commits": 0, "rollbacks": 0, "perdidos": [], "errores": []}

    def sql(self, kb, ds, q, *a):
        self.llamadas.append(("sql", q))
        if "falla" in q:
            return {"ok": False, "error": "tabla inexistente"}, {}
        return {"ok": True, "ms": 1}, {"actualizadas": 2}

    def fin(self, kb, modo):
        self.llamadas.append(("fin", modo))
        return {"ok": True}

    def marcar(self, kb, ds, otros=()):
        self.llamadas.append(("marcar", tuple(ds)))
        return list(ds)

    def volver(self, kb):
        self.llamadas.append(("volver",))
        return self.volver_resp

    def avanzar(self, kb):
        self.llamadas.append(("avanzar",))
        return self.volver_resp


class KBFalsa:
    nombre = "K"
    datasources = [{"nombre": "G"}]


class EntornoTest(unittest.TestCase):
    def setUp(self):
        self.m = MotorFalso()
        for nombre, fn in (("ejecutar_sql", self.m.sql), ("fin_transaccion", self.m.fin), ("marcar", self.m.marcar),
                           ("volver", self.m.volver), ("avanzar", self.m.avanzar), ("motor", lambda kb: self.m)):
            p = mock.patch.object(script, nombre, fn)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(script.efectos, "datastores_remotos", lambda kb: set())
        p.start()
        self.addCleanup(p.stop)
        self.kb = KBFalsa()

    def entorno(self, sql, encadenados=False):
        return script.Entorno(self.kb, {"scriptPrevio": [{"ds": "G", "sql": sql}] if sql else []},
                              {"timeoutMs": 1000, "casosEncadenados": encadenados})

    def test_encadenados_siguen_del_caso_anterior(self):
        with self.entorno("delete from a", encadenados=True) as e:
            for _ in range(2):
                self.assertIsNone(e.antes({}, "rollback"))
                self.assertEqual(e.despues("rollback"), ("encadenada: sigue en el caso siguiente", []))
        self.assertEqual(self.m.llamadas.count(("avanzar",)), 2)
        self.assertNotIn(("volver",), self.m.llamadas)
        self.assertEqual(self.m.llamadas[-1], ("fin", "rollback"))

    def test_encadenados_sin_script(self):
        with self.entorno("", encadenados=True) as e:
            self.assertTrue(e.activo)
            self.assertIsNone(e.resultado)
            self.assertIn(("marcar", ()), self.m.llamadas)
            self.assertIsNone(e.antes({}, "rollback"))
            self.assertIn("encadenados", e.antes({}, "commit"))
        self.assertFalse([x for x in self.m.llamadas if x[0] == "sql"])

    def test_encadenados_reiniciar_vuelve_a_correr_el_script(self):
        with self.entorno("delete from a", encadenados=True) as e:
            e.despues("rollback")
            e.reiniciar()
            self.assertEqual(e.veces, 2)
        self.assertEqual(len([x for x in self.m.llamadas if x[0] == "sql"]), 2)

    def test_encadenados_pasan_lo_guardado_a_los_casos_siguientes(self):
        with self.entorno("", encadenados=True) as e:
            caso1 = {"itf": 1}
            self.assertEqual(e.recibir(caso1, None), {})
            caso1["cupon"] = 77
            e.recordar(caso1, ["cupon", "no_llego"])
            caso2 = {"itf": 1}
            self.assertEqual(e.recibir(caso2, None), {"cupon": 77})
            self.assertEqual(caso2["cupon"], 77)
            fila = {"cupon": 5}
            caso3 = dict(fila)
            e.recibir(caso3, fila)
            self.assertEqual(caso3["cupon"], 5)  # la columna de la fila gana
            e.reiniciar()
            self.assertEqual(e.recibir({}, None), {})  # vuelve a empezar: no queda nada

    def test_aislados_no_pasan_variables(self):
        with self.entorno("delete from a") as e:
            e.recordar({"cupon": 1}, ["cupon"])
            v = {}
            self.assertEqual(e.recibir(v, None), {})
            self.assertNotIn("cupon", v)

    def test_encadenados_si_se_pierde_el_estado_avisa(self):
        with self.entorno("", encadenados=True) as e:
            self.m.volver_resp = {"ok": False, "puntos": 0, "perdidos": ["G: cambio la conexion"], "errores": []}
            tx, avisos = e.despues("rollback")
        self.assertEqual(tx, "rollback")
        self.assertIn("no ven lo que hicieron los anteriores", avisos[-1])

    def test_sin_script_cada_caso_tiene_su_transaccion(self):
        with script.Entorno(self.kb, {}, {}) as e:
            self.assertFalse(e.activo)
            self.assertIsNone(e.antes({}, "commit"))
            self.assertEqual(e.despues("commit"), ("commit", []))
        self.assertEqual(self.m.llamadas, [("fin", "rollback"), ("fin", "commit")])

    def test_script_una_vez_y_rollback_al_final(self):
        with self.entorno("delete from a; delete from b") as e:
            self.assertEqual(e.resultado["estado"], "ok")
            self.assertEqual(len(e.resultado["bloques"][0]["sentencias"]), 2)
            for _ in range(3):
                self.assertIsNone(e.antes({}, "rollback"))
                self.assertEqual(e.despues("rollback"), ("rollback al script previo", []))
        sqls = [x for x in self.m.llamadas if x[0] == "sql"]
        self.assertEqual(len(sqls), 2)  # no se repite por caso
        self.assertEqual(self.m.llamadas[-1], ("fin", "rollback"))
        self.assertEqual(self.m.llamadas.count(("volver",)), 3)

    def test_script_con_error_no_corre_casos(self):
        with self.entorno("delete from a; delete from falla") as e:
            self.assertEqual(e.resultado["estado"], "error")
            self.assertIn("tabla inexistente", e.resultado["error"])
            self.assertIn("script previo", e.antes({}, "rollback"))
        self.assertNotIn(("marcar", ("G",)), self.m.llamadas)

    def test_sentencia_prohibida_en_el_script(self):
        with self.entorno("truncate table a") as e:
            self.assertEqual(e.resultado["estado"], "error")
        self.assertFalse([x for x in self.m.llamadas if x[0] == "sql"])

    def test_no_acepta_casos_con_commit(self):
        with self.entorno("delete from a") as e:
            self.assertIn("commit", e.antes({}, "commit"))

    def test_avisa_commits_simulados(self):
        with self.entorno("delete from a") as e:
            self.m.volver_resp = {**self.m.volver_resp, "commits": 1}
            tx, avisos = e.despues("rollback")
        self.assertEqual(tx, "rollback al script previo")
        self.assertIn("1 commit", avisos[0])

    def test_si_se_pierde_el_savepoint_vuelve_a_correr_el_script(self):
        with self.entorno("delete from a") as e:
            self.m.volver_resp = {"ok": True, "puntos": 0, "perdidos": [], "errores": []}  # el motor se reinicio
            tx, avisos = e.despues("rollback")
            self.assertEqual(e.veces, 2)
            self.assertEqual(e.resultado["veces"], 2)
        self.assertEqual(tx, "rollback")
        self.assertIn("se perdio", avisos[-1])
        self.assertEqual(len([x for x in self.m.llamadas if x[0] == "sql"]), 2)

    def test_toma_el_motor_en_exclusiva(self):
        otro = []
        with self.entorno("delete from a"):
            t = threading.Thread(target=lambda: otro.append(self.m.lock.acquire(timeout=0.05)))
            t.start()
            t.join()
        self.assertEqual(otro, [False])


class PistaVariables(unittest.TestCase):
    SUITE = {"casos": [{"id": "alta", "nombre": "Alta", "pasos": [{"guardar": {"cupon": "outSet.Id"}}]},
                       {"id": "uso", "nombre": "Uso", "pasos": [{}]}]}

    def pista(self, encadenados, error="Variable no definida: ${cupon}"):
        from gxp.suites.ejecucion import _pista_variables
        res = {"pasos": [{"error": error}]}
        _pista_variables(self.SUITE, self.SUITE["casos"][1], mock.Mock(encadenados=encadenados), res)
        return res["pasos"][0]["error"]

    def test_aislados_explica_como_hacer_que_llegue(self):
        self.assertIn("Entre un caso y otro", self.pista(False))

    def test_encadenados_dice_que_caso_la_guarda(self):
        self.assertIn("«Alta»", self.pista(True))

    def test_otra_variable_no_se_toca(self):
        self.assertEqual(self.pista(True, "Variable no definida: ${otra}"), "Variable no definida: ${otra}")


if __name__ == "__main__":
    unittest.main()
