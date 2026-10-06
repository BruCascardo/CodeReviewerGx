import unittest

from gxp.revisor import salida
from gxp.revisor.configuracion import Configuracion
from gxp.revisor.pruebas import (asignar, asignar_campo, do, fin_si, fin_sub, leer, linea, llamar, si, si_igual,
                                 sino, sub, tipo, volver)
from gxp.revisor.reglas import cargar

# Variables como las declara el .sp0. outSet es un SDT con un campo Output de tipo sdtOutput (ver Ctx).
VARIABLES = r"""
attri_i('Inset',[ inSet,o('X\inSet'),0,0,'',0,'in Set','',1 ]).
attri_i('Outset',[ outSet,o('X\outSet'),0,0,'',0,'out Set','',2 ]).
attri_i('Sdtoutput',[ sdtOutput,o('Sistema\Global\sdtOutput'),0,0,'',0,'sdt Output','',3 ]).
attri_i('Message',[ 'Message',o('Sistema\Global\sdtOutput.Message'),0,0,'',0,'x','',4 ]).
attri_i('Msgtype',[ 'MsgType',int,2,0,'Z9',0,'Msg Type','',5 ]).
attri_i('Hayerror',[ 'HayError',boolean,4,0,'',0,'x','',6 ]).
attri_i('Msgs',[ 'Msgs',o(objectcollection('GeneXus\Common\Messages.Message')),0,0,'',0,'x','',7 ]).
attri_i('M',[ 'M',o('GeneXus\Common\Messages.Message'),0,0,'',0,'x','',8 ]).
rule_i(0,parmio([ [ 'Inset',in ],[ 'Outset',out ] ])).
enum_value_info_i(2,37,'GeneXus\MessageTypes').
"""

OUT = "t([ t('Outset',23,0,0),t('Output',3,0,0) ],29,0,0)"


def ok(n, valor, salida="Outset"):
    v = "t('TRUE',40,0,0)" if valor else "t('FALSE',41,0,0)"
    campo = f"t([ t('{salida}',23,0,0),t('Output',3,0,0),t('Ok',3,0,0) ],29,0,0)" if salida == "Outset" else \
        f"t([ t('{salida}',23,0,0),t('Ok',3,0,0) ],29,0,0)"
    return linea(n, 107, campo, "t(=,10,0,0)", v)


def add_message(n, tipo_msg, salida=OUT):
    """Sistema.Output.AddMessage("x", MessageTypes.<tipo>, <salida>)"""
    return linea(n, 104, "t(o(1,'Sistema\\Output\\AddMessage'),28,0,0)", "t('\"x\"',3,0,0)", "t(',',7,0,0)",
                 tipo(tipo_msg), "t(',',7,0,0)", salida)


def messages_add(n, var="Message"):
    """&outSet.Output.Messages.Add(&Message)"""
    return linea(n, 107, "t([ t('Outset',23,0,0),t('Output',3,0,0),t('Messages',3,0,0),t('add(',1,0,0) ],31,0,0)",
                 f"t('{var}',23,0,0)", "t(')',4,0,0)")


def fuente(*lineas, variables=VARIABLES):
    return leer("X.P", "\n".join(lineas), extra=variables)


class Ctx:
    kb_nombre = "Prueba"
    TIPOS = {"x\\outset": ["Output"], "sistema\\global\\sdtoutput": [""]}

    def rutas_sdt(self, tipo, buscado):
        return self.TIPOS.get(tipo.lower(), [])


def revisar(fu, conf=None):
    regla = cargar()["salida-ok-mensajes"](conf)
    if not regla.aplica(fu, Ctx()):
        return None
    return [(h.linea, h.severidad, h.mensaje.split(" (camino")[0]) for h in regla.revisar(fu, Ctx())]


# El estilo de Generales.Interfases.Registro.Set: la sub AGREGARMENSAJE pone Ok = False si el tipo es Error.
AGREGARMENSAJE = [
    sub(60, "AGREGARMENSAJE"),
    asignar(61, "Message", "t('new(',1,0,0)", "t(')',4,0,0)"),
    asignar_campo(62, "Message", "Type", "t('Msgtype',23,0,0)"),
    messages_add(63),
    si_igual(64, "Msgtype", "Error"),
    ok(65, False),
    fin_si(66),
    fin_sub(67),
]


class Estatica(unittest.TestCase):
    def test_no_aplica_sin_sdtoutput_en_la_salida(self):
        variables = VARIABLES.replace("[ 'Outset',out ]", "[ 'Outset',in ]")
        self.assertIsNone(revisar(fuente(ok(1, True), variables=variables)))

    def test_cumple_con_sub_que_resuelve_el_tipo(self):
        fu = fuente(
            ok(1, True),
            si(5, "t('null(',1,0,0)", "t('Inset',23,0,0)", "t(')',4,0,0)"),
            asignar(6, "Msgtype", tipo("Error")),
            do(7, "AGREGARMENSAJE"),
            volver(8),
            fin_si(9),
            asignar(20, "Msgtype", tipo("Debug")),
            do(21, "AGREGARMENSAJE"),
            *AGREGARMENSAJE)
        self.assertEqual(revisar(fu), [])

    def test_exito_info_se_senala_donde_se_eligio_el_tipo(self):
        fu = fuente(ok(1, True), asignar(20, "Msgtype", tipo("Info")), do(21, "AGREGARMENSAJE"), *AGREGARMENSAJE)
        self.assertEqual(revisar(fu), [(20, "advertencia", "El mensaje de exito es de tipo Info: tiene que ser Debug")])

    def test_error_sin_ok_false(self):
        # AddMessage no toca el Ok: con Ok = True al principio, el error sale con Ok = True.
        fu = fuente(ok(1, True), si(5, "t('Hayerror',23,0,0)"), add_message(6, "Error"), volver(7), fin_si(8),
                    add_message(10, "Debug"))
        self.assertEqual(revisar(fu), [(6, "error", "Agrega un mensaje de tipo Error pero termina con Ok = True")])

    def test_error_con_ok_false(self):
        fu = fuente(ok(1, True), si(5, "t('Hayerror',23,0,0)"), add_message(6, "Error"), ok(7, False), volver(8),
                    fin_si(9), add_message(10, "Debug"))
        self.assertEqual(revisar(fu), [])

    def test_ok_false_sin_mensaje_de_error(self):
        fu = fuente(ok(1, True), si(5, "t('Hayerror',23,0,0)"), add_message(6, "Warning"), ok(7, False), volver(8),
                    fin_si(9), add_message(10, "Debug"))
        self.assertEqual(revisar(fu), [(7, "error", "Ok = False sin ningun mensaje de tipo Error")])

    def test_nunca_asigna_ok_true(self):
        fu = fuente(add_message(10, "Debug"))
        self.assertEqual(revisar(fu), [(0, "error", "Nunca asigna &outSet.Output.Ok = True: siempre devuelve Ok = False")])

    def test_ok_true_sin_mensaje_de_exito(self):
        self.assertEqual(revisar(fuente(ok(1, True))),
                         [(1, "error", "Termina con Ok = True sin mensaje de exito (Type Debug)")])

    def test_bandera_booleana(self):
        # El error prende una bandera y al final Ok se decide con ella: los dos caminos son coherentes.
        fu = fuente(
            asignar(1, "Hayerror", "t('FALSE',41,0,0)"),
            si(2, "t('null(',1,0,0)", "t('Inset',23,0,0)", "t(')',4,0,0)"),
            add_message(3, "Error"), asignar(4, "Hayerror", "t('TRUE',40,0,0)"),
            fin_si(5),
            si(6, "t('Hayerror',23,0,0)"), ok(7, False), sino(8), ok(9, True), add_message(10, "Debug"), fin_si(11))
        self.assertEqual(revisar(fu), [])

    def test_mensajes_de_un_bc_en_un_bucle_no_inventan_caminos(self):
        # For &M in &Msgs / If &M.Type = Error: lo que depende de la vuelta no se juzga.
        fu = fuente(
            ok(1, True),
            si(2, "t('Hayerror',23,0,0)"),
            linea(3, 107, "t('GXV1',23,0,0)", "t(=,10,0,0)", "t(1,3,0,0)").replace("b_line_i(3,", "b_line_i([ 3,0 ],"),
            linea(3, 114, "t('GXV1',23,0,0)", "t(<=,10,0,0)", "t([ t('Msgs',23,0,0),t('Count',3,0,0) ],29,0,0)")
            .replace("b_line_i(3,", "b_line_i([ 3,2 ],"),
            linea(3, 107, "t('M',23,0,0)", "t(=,10,0,0)", "t([ t('Msgs',23,0,0),t('item(',1,0,0) ],31,0,0)",
               "t('GXV1',23,0,0)", "t(')',4,0,0)").replace("b_line_i(3,", "b_line_i([ 3,3 ],"),
            si(4, "t([ t('M',23,0,0),t('Type',3,0,0) ],29,0,0)", "t(=,10,0,0)", tipo("Error")),
            asignar(5, "Msgtype", tipo("Error")),
            do(6, "AGREGARMENSAJE"),
            fin_si(7),
            linea(8, 107, "t('GXV1',23,0,0)", "t(=,10,0,0)", "t('GXV1',23,0,0)", "t(+,5,0,0)", "t(1,3,0,0)")
            .replace("b_line_i(8,", "b_line_i([ 8,1 ],"),
            linea(8, 115).replace("b_line_i(8,", "b_line_i([ 8,2 ],"),
            sino(9),
            asignar(10, "Msgtype", tipo("Debug")), do(11, "AGREGARMENSAJE"),
            fin_si(12),
            *AGREGARMENSAJE)
        self.assertEqual(revisar(fu), [])

    def test_salida_pasada_a_otro_objeto_no_se_juzga(self):
        fu = fuente(llamar(1, "X\\Otro", "t('Inset',23,0,0)", "t('Outset',23,0,0)"))
        self.assertEqual(revisar(fu), [])

    def test_variable_sdtoutput_que_no_se_devuelve(self):
        # Como Cobranzas.PlanesPago.Vencimientos.Validar: los mensajes van a &sdtOutput y se pierden.
        fu = fuente(ok(1, True), add_message(5, "Error", "t('Sdtoutput',23,0,0)"), add_message(9, "Debug"))
        self.assertEqual(revisar(fu)[0],
                         (5, "error", "Agrega mensajes a &sdtOutput, que no se devuelve: no llegan a &outSet.Output"))

    def test_variable_sdtoutput_que_se_copia_a_la_salida(self):
        fu = fuente(
            ok(1, True, salida="Sdtoutput"),
            si(2, "t('Hayerror',23,0,0)"),
            add_message(3, "Error", "t('Sdtoutput',23,0,0)"), ok(4, False, salida="Sdtoutput"),
            sino(5),
            add_message(6, "Debug", "t('Sdtoutput',23,0,0)"),
            fin_si(7),
            linea(8, 107, OUT, "t(=,10,0,0)", "t('Sdtoutput',23,0,0)"))
        self.assertEqual(revisar(fu), [])

    def test_coleccion_errores_y_count(self):
        # Estilo Sistema.Conversacion.CnvEvento_Crear: &sdtOutput.Errores.Add() y Ok = False si Count <> 0.
        variables = VARIABLES.replace("[ 'Outset',out ]", "[ 'Sdtoutput',out ]")
        errores_add = linea(3, 107, "t([ t('Sdtoutput',23,0,0),t('Errores',3,0,0),t('add(',1,0,0) ],31,0,0)",
                         "t('M',23,0,0)", "t(')',4,0,0)")
        fu = fuente(
            ok(1, True, salida="Sdtoutput"),
            si(2, "t('Hayerror',23,0,0)"), errores_add, fin_si(4),
            si(5, "t([ t('Sdtoutput',23,0,0),t('Errores',3,0,0),t('Count',3,0,0) ],29,0,0)", "t(<>,10,0,0)", "t(0,3,0,0)"),
            ok(6, False, salida="Sdtoutput"),
            sino(7),
            add_message(8, "Debug", "t('Sdtoutput',23,0,0)"),
            fin_si(9),
            variables=variables)
        self.assertEqual(revisar(fu), [])

    def test_ayudantes_configurables(self):
        fu = fuente(ok(1, True), llamar(2, "X\\MiAyudante", tipo("Info"), OUT))
        self.assertEqual(revisar(fu), [])  # sin configurar: le pasa la salida a otro objeto, no se juzga
        conf = {"ayudantes": {"X.MiAyudante": {"tipo": 1, "salida": 2}}}
        self.assertEqual(revisar(fu, conf), [(2, "advertencia", "El mensaje de exito es de tipo Info: tiene que ser Debug")])


class Dinamica(unittest.TestCase):
    def controlar(self, datos, conf=None):
        return salida.controlar("Prueba", "X.P", datos, conf or Configuracion())

    def test_ok_false_con_y_sin_error(self):
        sin = {"outSet": {"Output": {"Ok": False, "Messages": [{"Type": 0, "Texto": "aviso"}]}}}
        con = {"outSet": {"Output": {"Ok": False, "Messages": [{"Type": 1, "Texto": "fallo"}]}}}
        self.assertEqual(self.controlar(sin), ["Buenas practicas (error): outSet.Output: Ok = false sin ningun mensaje "
                                               "de tipo Error [salida-ok-mensajes]"])
        self.assertEqual(self.controlar(con), [])

    def test_ok_true(self):
        def con(*tipos):
            return {"Ok": True, "Messages": [{"Type": t} for t in tipos]}
        self.assertEqual(self.controlar(con(3)), [])
        self.assertIn("Info (2)", self.controlar(con(2))[0])
        self.assertIn("sin mensaje de exito", self.controlar({"Ok": True, "Log": ""})[0])
        self.assertIn("mensaje(s) de tipo Error", self.controlar(con(3, 1))[0])

    def test_coleccion_errores(self):
        self.assertEqual(self.controlar({"Ok": False, "Errores": [{"Id": 1}]}), [])

    def test_no_confunde_otros_ok(self):
        self.assertEqual(self.controlar({"Ok": True, "Nombre": "x"}), [])  # sin Messages/Errores/Log

    def test_respeta_revisor_json(self):
        datos = {"Ok": True, "Log": ""}
        apagada = Configuracion({"reglas": {"salida-ok-mensajes": {"activa": False}}})
        excepcion = Configuracion({"excepciones": [{"regla": "salida-ok-mensajes", "objeto": "X.*", "motivo": "prueba"}]})
        self.assertEqual(self.controlar(datos, apagada), [])
        self.assertEqual(self.controlar(datos, excepcion), [])


if __name__ == "__main__":
    unittest.main()
