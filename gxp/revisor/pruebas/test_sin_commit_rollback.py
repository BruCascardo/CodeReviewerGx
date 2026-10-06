import unittest

from gxp.revisor.configuracion import Configuracion
from gxp.revisor.pruebas import leer
from gxp.revisor.reglas import cargar

COMMIT = "b_line_i(8,1,1,cmd,0,[ t('',132,8,0) ])."
ROLLBACK = "b_line_i(9,1,1,cmd,0,[ t('',157,9,0) ])."
LLAMA_PRC_COMMIT = "b_line_i(36,1,1,cmd,0,[ t('',104,36,0),t(o(1,'Asegurados\\Global\\prcCommit'),28,15,2) ])."
LLAMA_OTRO = "b_line_i(40,1,1,cmd,0,[ t('',104,40,0),t(o(1,'Sistema\\Global\\prcLog'),28,15,2) ])."
JAVA_COMMIT = "b_line_i(3,1,1,cmd,0,[ t('',166,3,0),t(' context.commitDataStores(\"x\");',3,0,5) ])."


class Ctx:
    kb_nombre = "Prueba"

    def __init__(self, confirma=None):
        self.confirma = confirma

    def java_confirma(self, objeto):
        return self.confirma


def revisar(fu, ctx=None, conf=None):
    regla = cargar()["sin-commit-rollback"](conf)
    ctx = ctx or Ctx()
    if not regla.aplica(fu, ctx):
        return []
    return list(regla.revisar(fu, ctx))


class SinCommitRollback(unittest.TestCase):
    def test_commit_y_rollback_en_procedimiento(self):
        hs = revisar(leer("X.P", COMMIT + "\n" + ROLLBACK, props={"TRNEND": "No"}))
        self.assertEqual([(h.linea, h.severidad) for h in hs], [(8, "error"), (9, "error")])

    def test_llamada_a_prccommit(self):
        hs = revisar(leer("X.P", LLAMA_PRC_COMMIT + "\n" + LLAMA_OTRO))
        self.assertEqual(len(hs), 1)
        self.assertEqual(hs[0].linea, 36)
        self.assertIn("Asegurados.Global.prcCommit", hs[0].mensaje)
        self.assertEqual(hs[0].codigo, "Asegurados.Global.prcCommit()")

    def test_llamada_como_funcion_a_prccommit(self):
        linea = "b_line_i(5,1,1,cmd,0,[ t('',107,5,0),t('Ok',23,0,0),t(=,10,0,0),t('udp(',1,0,0),t('Ok',3,0,0),t(5,3,0,0),t(')',4,0,0) ])."
        extra = r"function_i(1,'Ok',yes,udp,o(1,'Sistema\Global\prcCommit'),[],5,'Ok',[ [] ])."
        hs = revisar(leer("X.P", linea, extra=extra))
        self.assertEqual([h.linea for h in hs], [5])

    def test_web_panel_puede(self):
        self.assertEqual(revisar(leer("X.W", COMMIT + "\n" + LLAMA_PRC_COMMIT, tipo="web")), [])

    def test_web_component_puede(self):
        self.assertEqual(revisar(leer("X.W", COMMIT, tipo="web", props={"WEB_COMP": "Yes"})), [])

    def test_commit_on_exit(self):
        fu = leer("X.P", "", props={"TRNEND": "Yes"})
        self.assertEqual([h.severidad for h in revisar(fu, Ctx(confirma=True))], ["error"])
        self.assertEqual([h.severidad for h in revisar(fu, Ctx(confirma=False))], ["advertencia"])
        self.assertEqual(revisar(fu, Ctx(confirma=True))[0].linea, 0)

    def test_transaccion_confirma_por_diseno(self):
        self.assertEqual(revisar(leer("X.T", "", tipo="trn", props={"TRNEND": "Yes"}), Ctx(confirma=True)), [])
        self.assertEqual(len(revisar(leer("X.T", COMMIT, tipo="trn"))), 1)

    def test_java_nativo(self):
        hs = revisar(leer("X.P", JAVA_COMMIT))
        self.assertEqual([h.severidad for h in hs], ["advertencia"])
        sql = "b_line_i(4,1,1,cmd,0,[ t('',166,4,0),t(' ExecuteDirectSQL.execute(context, h, ds, \"Commit\") ;',3,0,5) ])."
        self.assertEqual(len(revisar(leer("X.P", sql))), 1)

    def test_java_nativo_que_no_es_commit(self):
        lineas = "\n".join([
            "b_line_i(1,1,1,cmd,0,[ t('',166,1,0),t(' [!&BigDecimal!] = heap.getCommitted();',3,0,5) ]).",
            "b_line_i(2,1,1,cmd,0,[ t('',166,2,0),t(' json.put(\"x\", connection.getUncommitedChanges());',3,0,5) ]).",
        ])
        self.assertEqual(revisar(leer("X.P", lineas)), [])

    def test_parametros_desde_revisor_json(self):
        hs = revisar(leer("X.P", LLAMA_OTRO), conf={"objetosCommit": ["prcLog"]})
        self.assertEqual(len(hs), 1)
        hs = revisar(leer("X.P", COMMIT), conf={"severidad": "advertencia"})
        self.assertEqual(hs[0].severidad, "advertencia")

    def test_huella_estable_si_se_mueve_la_linea(self):
        a = revisar(leer("X.P", COMMIT))[0]
        b = revisar(leer("X.P", COMMIT.replace("(8,", "(20,").replace(",8,0", ",20,0")))[0]
        self.assertNotEqual(a.linea, b.linea)
        self.assertEqual(a.huella, b.huella)


class Excepciones(unittest.TestCase):
    def test_excepcion_con_motivo(self):
        conf = Configuracion({"excepciones": [
            {"regla": "sin-commit-rollback", "objeto": "*.prcCommit", "motivo": "centraliza el commit"},
            {"regla": "sin-commit-rollback", "objeto": "X.*"},  # sin motivo: no se aplica
        ]})
        self.assertEqual(len(conf.excepciones), 1)
        self.assertEqual(len(conf.avisos), 1)
        h = revisar(leer("Sistema.Global.prcCommit", COMMIT))[0]
        self.assertEqual(conf.excepcion(h)["motivo"], "centraliza el commit")
        h = revisar(leer("X.P", COMMIT))[0]
        self.assertIsNone(conf.excepcion(h))

    def test_ignorar(self):
        conf = Configuracion({"ignorar": ["WWPBaseObjects.*"]})
        self.assertIsNotNone(conf.ignorado(leer("WWPBaseObjects.Algo", "")))
        self.assertIsNone(conf.ignorado(leer("Generales.Algo", "")))
        # WorkWithPlus marca lo que genera para que GXtest no lo cuente en la cobertura.
        self.assertIsNotNone(conf.ignorado(leer("Generales.XLoadDVCombo", "", props={"gxtest_ignoreForTestCoverage": "-1"})))
        self.assertIsNone(conf.ignorado(leer("Generales.X", "", props={"gxtest_ignoreForTestCoverage": "0"})))
        # Un objeto sin carpeta no por eso es generado.
        fu = leer("Sistema.Blob.schBlob_Persistir", "")
        fu.propiedades.pop("Folder", None)
        self.assertIsNone(conf.ignorado(fu))
        # La especificacion _BC de una transaccion repite su codigo.
        fu = leer("Generales.gntEmpresa_BC", "", tipo="trn")
        fu.propiedades.pop("Folder", None)
        self.assertIsNotNone(conf.ignorado(fu))


if __name__ == "__main__":
    unittest.main()
