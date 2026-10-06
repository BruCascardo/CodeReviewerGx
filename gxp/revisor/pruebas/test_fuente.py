import unittest

from gxp.revisor import prolog
from gxp.revisor.pruebas import leer

# Fragmento de Generales.Interfases.Registro.Set (lineas reales de su .sp0).
REGISTRO_SET = r"""
b_line_i(5,1,1,cmd,0,[ t('',107,5,0),t([ t('Outset',23,0,0),t('Output',3,0,0),t('Ok',3,0,0) ],29,0,0),t(=,10,0,0),t('TRUE',40,0,0) ]).
b_line_i(11,1,1,cmd,0,[ t('',109,11,0),t('null(',1,11,13),t('Regtipo',23,0,4),t(')',4,0,22) ]).
b_line_i(12,1,1,cmd,0,[ t('',107,12,0),t('Msgcode',23,0,0),t(=,10,0,0),t('"REQUERIDO"',3,0,0) ]).
b_line_i(13,1,1,cmd,0,[ t('',107,13,0),t('Msgtype',23,0,0),t(=,10,0,0),t([ 37,'Error' ],44,0,0) ]).
b_line_i(15,1,1,cmd,0,[ t('',145,15,0),t('''AGREGARMENSAJE''',3,15,8) ]).
b_line_i(16,1,1,cmd,0,[ t('',118,16,0) ]).
b_line_i(17,1,1,cmd,0,[ t('',111,17,0) ]).
b_line_i(36,1,1,cmd,0,[ t('',107,36,0),t([ t('Gntitfregistro',23,36,1),t('save(',1,36,17) ],31,36,1),t(')',4,0,23) ]).
b_line_i(43,1,1,cmd,0,[ t('',107,43,0),t('Msgtexto',23,0,0),t(=,10,0,0),t('format(',1,0,0),t('"Registro ''%1'' creado."',3,0,0),t(',',7,0,0),t('Regtipo',23,0,0),t(')',4,0,0) ]).
b_line_i(49,1,1,cmd,0,[ t('',143,49,0),t('''AGREGARMENSAJESBC''',3,49,5) ]).
b_line_i(50,1,2,cmd,0,[ t('',107,50,0),t('Bcmessages',23,0,0),t(=,10,0,0),t([ t('Gntitfregistro',23,0,0),t('getmessages(',1,0,0) ],31,0,0),t(')',4,0,0) ]).
b_line_i(51,1,2,cmd,0,[ t('',107,51,0),t('GXV1',23,0,0),t(=,10,0,0),t(1,3,0,0) ]).
b_line_i([ 51,2 ],1,2,cmd,0,[ t('',114,51,0),t('GXV1',23,0,0),t(<=,10,0,0),t([ t('Bcmessages',23,51,20),t('Count',3,51,0) ],29,51,0) ]).
b_line_i([ 51,3 ],1,2,cmd,0,[ t('',107,51,0),t('Bcmessage',23,0,0),t(=,10,0,0),t([ t('Bcmessages',23,0,0),t('item(',1,0,0) ],31,0,0),t('GXV1',23,0,0),t(')',4,0,0) ]).
b_line_i(52,1,2,cmd,1,[ t('',109,52,0),t([ t('Bcmessage',23,52,6),t('Type',3,52,17) ],29,52,17),t(=,10,1,22),t([ 37,'Error' ],44,52,24) ]).
b_line_i(56,1,2,cmd,1,[ t('',145,56,0),t('''AGREGARMENSAJE''',3,56,7) ]).
b_line_i(57,1,2,cmd,1,[ t('',111,57,0) ]).
b_line_i([ 58,1 ],1,2,cmd,1,[ t('',107,58,0),t('GXV1',23,1,0),t(=,10,1,0),t('GXV1',23,1,0),t(+,5,1,0),t(1,3,1,0) ]).
b_line_i([ 58,2 ],1,2,cmd,1,[ t('',115,58,0) ]).
b_line_i(59,1,2,cmd,2,[ t('',144,59,0) ]).
"""

VARIABLES = r"""
attri_i('Inset',[ inSet,o('Generales\Interfases\Registro\inSet'),0,0,'',0,'in Set','',8 ]).
attri_i('Outset',[ outSet,o('Generales\Interfases\Registro\outSet'),0,0,'',0,'out Set','',9 ]).
attri_i('Regtipo',[ 'RegTipo',char,10,0,'',0,'Tipo de Registro','',12 ]).
attri_i('Msgtype',[ 'MsgType',int,2,0,'Z9',0,'Msg Type','',17 ]).
attri_i('Msgcode',[ 'MsgCode',svchar,128,0,'',0,'Msg Code','',15 ]).
attri_i('Msgtexto',[ 'MsgTexto',svchar,1000,0,'',0,'Msg Texto','',16 ]).
attri_i('Gntitfregistro',[ gntItfRegistro,o('Generales\Interfases\gntItfRegistro'),0,0,'',0,'x','',10 ]).
attri_i('Bcmessages',[ 'BCMessages',o(objectcollection('GeneXus\Common\Messages.Message')),0,0,'',0,'x','',19 ]).
attri_i('Bcmessage',[ 'BCMessage',o('GeneXus\Common\Messages.Message'),0,0,'',0,'x','',18 ]).
attri_i(3490,[ 'MovTipoParteUsrIns',char,100,0,'',0,'Usuario Insert','',0 ]).
rule_i(0,parmio([ [ 'Inset',in ],[ 'Outset',out ] ])).
enum_value_info_i(2,37,'GeneXus\MessageTypes').
"""

ESPERADO = """\
    5  &outSet.Output.Ok = True
   11  If null(&RegTipo)
   12      &MsgCode = "REQUERIDO"
   13      &MsgType = MessageTypes.Error
   15      Do 'AGREGARMENSAJE'
   16      Return
   17  EndIf
   36  &gntItfRegistro.Save()
   43  &MsgTexto = format("Registro '%1' creado.", &RegTipo)
   49  Sub 'AGREGARMENSAJESBC'
   50      &BCMessages = &gntItfRegistro.GetMessages()
   51      For &BCMessage in &BCMessages
   52          If &BCMessage.Type = MessageTypes.Error
   56              Do 'AGREGARMENSAJE'
   57          EndIf
   58      EndFor
   59  EndSub"""


class Prolog(unittest.TestCase):
    def test_terminos(self):
        t = prolog.leer("b_line_i([ 51,2 ],1,cmd,[ t(<=,10,0,0),t('''A''',3),t(-1,3),t(o(1,'S\\X'),28) ]).")
        self.assertEqual(t.nombre, "b_line_i")
        self.assertEqual(t.args[0], [51, 2])
        toks = t.args[3]
        self.assertEqual(toks[0].args[0], "<=")
        self.assertEqual(toks[1].args[0], "'A'")
        self.assertEqual(toks[2].args[0], -1)
        self.assertEqual(toks[3].args[0], prolog.Comp("o", [1, "S\\X"]))

    def test_atomos_con_acento(self):
        t = prolog.leer("attri_i(1038,[ 'EmpAreaId',int,6,0,'ZZZZZ9',0,Área,'',0 ]).")
        self.assertEqual(t.args[1][6], "Área")

    def test_clausula_ilegible_no_se_lleva_las_siguientes(self):
        texto = "x_i(1).\nx_i(no se puede leer, ).\nx_i(2).\nx_i(3).\n"
        ilegibles = [0]
        self.assertEqual([c.args[0] for _, c in prolog.clausulas(texto, ["x_i"], ilegibles=ilegibles)], [1, 2, 3])
        self.assertEqual(ilegibles, [1])

    def test_saltea_predicados(self):
        texto = "a(1).\nrule_i(0,datastore(1,'X','y')).\nb(2).\n"
        self.assertEqual([n for n, _ in prolog.clausulas(texto, ["a", "rule_i"], saltear=("rule_i(0,datastore(",))], ["a"])


class Fuente(unittest.TestCase):
    def setUp(self):
        self.fu = leer("Generales.Interfases.Registro.Set", REGISTRO_SET, extra=VARIABLES)

    def test_datos_del_objeto(self):
        fu = self.fu
        self.assertEqual(fu.tipo, "proc")
        self.assertEqual(fu.nombre, "Generales.Interfases.Registro.Set")
        self.assertEqual(fu.parametros, [("inSet", "in"), ("outSet", "out")])
        self.assertEqual(fu.variables["Outset"]["tipo"], "Generales\\Interfases\\Registro\\outSet")
        self.assertEqual(fu.desconocidas, set())
        self.assertFalse(fu.generado_por_pattern)

    def test_texto_reconstruido(self):
        self.assertEqual(self.fu.texto(), ESPERADO)

    def test_claves(self):
        claves = {s.linea: s.clave for s in self.fu.sentencias if not s.generada}
        self.assertEqual(claves[11], "if")
        self.assertEqual(claves[15], "do")
        self.assertEqual(claves[51], "forin")
        self.assertEqual(claves[58], "endfor")


class Codigos(unittest.TestCase):
    def test_new_case_commit(self):
        fu = leer("X.P", r"""
b_line_i(2,1,1,cmd,0,[ t('',152,2,0) ]).
b_line_i(3,1,1,cmd,0,[ t('',153,3,0),t('A',23,0,7),t(=,10,0,34),t(1,3,0,0) ]).
b_line_i(4,1,1,cmd,0,[ t('',117,4,0) ]).
b_line_i(5,1,1,cmd,0,[ t('',107,5,0),t(3490,2,15,0),t(=,10,15,0),t('"x"',3,0,0) ]).
b_line_i(6,1,1,cmd,0,[ t('',129,6,0) ]).
b_line_i(7,1,1,cmd,0,[ t('',157,7,0) ]).
b_line_i(8,1,1,cmd,0,[ t('',127,8,0) ]).
b_line_i(9,1,1,cmd,0,[ t('',164,9,0) ]).
b_line_i(10,1,1,cmd,0,[ t('',132,10,0) ]).
b_line_i(11,1,1,cmd,0,[ t('',154,11,0) ]).
b_line_i(12,1,1,cmd,0,[ t('',104,12,0),t(o(1,'Servicios\Global\prcCommit'),28,0,1) ]).
""", extra=VARIABLES)
        self.assertEqual(fu.texto(), """\
    2  Do Case
    3      Case &A = 1
    4          New
    5              MovTipoParteUsrIns = "x"
    6          When duplicate
    7              Rollback
    8          EndNew
    9      Otherwise
   10          Commit
   11  EndCase
   12  Servicios.Global.prcCommit()""")
        self.assertEqual(fu.sentencias[-1].objetos(), [(1, "Servicios.Global.prcCommit")])

    def test_llamada_como_funcion_y_metodo_en_cadena(self):
        lineas = r"""
b_line_i(21,1,3,cmd,6,[ t('',107,21,0),t('Fechastring',23,6,0),t(=,10,6,0),t('udp(',1,6,0),t('Fechastring',3,6,0),t(21,3,6,0),t('Json',23,6,0),t(',',7,6,0),t(1,3,6,0),t(')',4,6,0) ]).
b_line_i(22,1,3,cmd,6,[ t('',107,22,0),t('A',23,0,0),t(=,10,6,0),t([ t('Col',23,20,75),[ t('item(',1,0,91),t('1',3,0,97),t(')',4,0,98) ],t('Registro',3,20,100) ],29,20,100) ]).
"""
        extra = r"function_i(1,'Fechastring',yes,udp,o(1,'Generales\Global\JSON_Property'),[],21,'Fechastring',[ [ t('Json',23) ] ])."
        fu = leer("X.P", lineas, extra=extra)
        self.assertEqual(fu.sentencias[0].texto, "&Fechastring = Generales.Global.JSON_Property(&Json, 1)")
        self.assertEqual(fu.sentencias[0].objetos(), [(1, "Generales.Global.JSON_Property")])
        self.assertEqual(fu.sentencias[1].texto, "&A = &Col.Item(1).Registro")

    def test_extensiones_de_especificacion(self):
        from gxp.revisor.fuente import es_spec
        self.assertTrue(es_spec("Set.sp0"))
        self.assertTrue(es_spec("Set.sp1"))  # algunas KBs usan .sp1
        self.assertFalse(es_spec("GXSDT_outSet.sp0"))
        self.assertFalse(es_spec("SubViews1.ari"))

    def test_codigo_desconocido_no_rompe(self):
        fu = leer("X.P", "b_line_i(1,1,1,cmd,0,[ t('',999,1,0),t('A',23,0,0) ]).")
        self.assertEqual(fu.desconocidas, {999})
        self.assertEqual(fu.sentencias[0].clave, "desconocida")
        self.assertIn("999", fu.sentencias[0].texto)


if __name__ == "__main__":
    unittest.main()
