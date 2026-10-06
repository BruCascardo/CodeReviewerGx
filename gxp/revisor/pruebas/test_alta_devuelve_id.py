import unittest

from gxp.revisor import transacciones
from gxp.revisor.pruebas import asignar, asignar_campo, fin_si, leer, linea, metodo, si
from gxp.revisor.reglas import cargar

# &Bc es un BC de X.Entidad (clave EntId), &Hijo de X.EntidadHija (clave EntId, HijoSec) y &Hist de
# X.EntidadHistorial (clave HistSec): ver Ctx.
VARIABLES = r"""
attri_i('Inset',[ inSet,o('X\inSet'),0,0,'',0,'in Set','',1 ]).
attri_i('Outset',[ outSet,o('X\outSet'),0,0,'',0,'out Set','',2 ]).
attri_i('Bc',[ 'Bc',o('X\Entidad'),0,0,'',0,'x','',3 ]).
attri_i('Hijo',[ 'Hijo',o('X\EntidadHija'),0,0,'',0,'x','',4 ]).
attri_i('Id',[ 'Id',int,9,0,'',0,'x','',5 ]).
attri_i('Hist',[ 'Hist',o('X\EntidadHistorial'),0,0,'',0,'x','',7 ]).
attri_i('Item',[ 'Item',o('X\Item'),0,0,'',0,'x','',6 ]).
"""
SALIDA = "rule_i(0,parmio([ [ 'Inset',in ],[ 'Outset',out ] ]))."
SIN_SALIDA = "rule_i(0,parmio([ [ 'Inset',in ] ]))."


def campo(var, nombre):
    return f"t([ t('{var}',23,0,0),t('{nombre}',3,0,0) ],29,0,0)"


def var(nombre):
    return f"t('{nombre}',23,0,0)"


NEW = ("t('new(',1,0,0)", "t(')',4,0,0)")
NUMERADOR = ("t('udp(',1,0,0)", "t(o(1,'X\\Numerador'),28,0,0)", "t(')',4,0,0)")


def a_salida(n, nombre, *valor):
    """&outSet.<nombre> = valor"""
    return linea(n, 107, campo("Outset", nombre), "t(=,10,0,0)", *valor)


class Trn:
    def __init__(self, nombre, claves, autonumeradas=()):
        self.nombre, self.claves, self.autonumeradas = nombre, claves, set(autonumeradas)


class Ctx:
    kb_nombre = "Prueba"

    def __init__(self, autonumerada=True):
        self.trns = {"x\\entidad": Trn("X.Entidad", ["EntId"], ["EntId"] if autonumerada else []),
                     "x\\entidadhija": Trn("X.EntidadHija", ["EntId", "HijoSec"], ["HijoSec"]),
                     "x\\entidadhistorial": Trn("X.EntidadHistorial", ["HistSec"], ["HistSec"])}

    def transaccion(self, tipo):
        return self.trns.get(tipo.lower())


def revisar(*lineas, nombre="X.Entidad_Crear", parm=SALIDA, ctx=None):
    fu = leer(nombre, "\n".join(lineas), extra=VARIABLES + parm)
    regla = cargar()["alta-devuelve-id"]()
    ctx = ctx or Ctx()
    if not regla.aplica(fu, ctx):
        return None
    return [(h.linea, h.severidad, h.mensaje) for h in regla.revisar(fu, ctx)]


CREA = [asignar(1, "Bc", *NEW), asignar_campo(2, "Bc", "Nombre", campo("Inset", "Nombre")), metodo(3, "Bc", "Insert")]


class AltaDevuelveId(unittest.TestCase):
    def test_alta_que_no_devuelve_la_clave_autonumerada(self):
        self.assertEqual(revisar(*CREA), [(3, "advertencia", "Crea Entidad y no devuelve su clave (EntId)")])

    def test_devuelve_la_clave(self):
        self.assertEqual(revisar(*CREA, a_salida(4, "Id", campo("Bc", "Entid"))), [])

    def test_devuelve_la_clave_a_traves_de_una_variable(self):
        self.assertEqual(revisar(*CREA, asignar(4, "Id", campo("Bc", "Entid")), a_salida(5, "Id", var("Id"))), [])

    def test_devuelve_la_clave_en_una_coleccion(self):
        # &Item.Id = &Bc.EntId / &outSet.Ids.Add(&Item)
        self.assertEqual(revisar(*CREA, asignar_campo(4, "Item", "Id", campo("Bc", "Entid")),
                                 linea(5, 107, "t([ t('Outset',23,0,0),t('Ids',3,0,0),t('add(',1,0,0) ],31,0,0)",
                                       var("Item"), "t(')',4,0,0)")), [])

    def test_clave_que_viene_de_la_entrada_no_se_exige(self):
        fu = [asignar(1, "Bc", *NEW), asignar(2, "Id", campo("Inset", "Id")), asignar_campo(3, "Bc", "Entid", var("Id")),
              metodo(4, "Bc", "Save")]
        self.assertEqual(revisar(*fu, ctx=Ctx(autonumerada=False)), [])

    def test_clave_de_un_numerador_se_exige(self):
        fu = [asignar(1, "Id", *NUMERADOR), asignar(2, "Bc", *NEW), asignar_campo(3, "Bc", "Entid", var("Id")),
              metodo(4, "Bc", "Save")]
        self.assertEqual(revisar(*fu, ctx=Ctx(autonumerada=False)),
                         [(4, "advertencia", "Crea Entidad y no devuelve su clave (EntId)")])

    def test_new_antes_del_load_es_una_modificacion(self):
        fu = [asignar(1, "Bc", *NEW), metodo(2, "Bc", "Load", campo("Inset", "Id")),
              asignar_campo(3, "Bc", "Nombre", campo("Inset", "Nombre")), metodo(4, "Bc", "Save")]
        self.assertEqual(revisar(*fu), [])

    def test_alta_o_modificacion_con_la_clave_de_la_entrada(self):
        # Como Generales.Interfases.Registro.Set: Load / If Fail() / new() con la clave que mando el que llama.
        fu = [metodo(1, "Bc", "Load", campo("Inset", "Id")),
              si(2, "t([ t('Bc',23,0,0),t('fail(',1,0,0) ],31,0,0)", "t(')',4,0,0)"),
              asignar(3, "Bc", *NEW), asignar_campo(4, "Bc", "Entid", campo("Inset", "Id")), fin_si(5),
              metodo(6, "Bc", "Save")]
        self.assertEqual(revisar(*fu, ctx=Ctx(autonumerada=False)), [])

    def test_la_hija_no_se_exige(self):
        fu = [*CREA, a_salida(4, "Id", campo("Bc", "Entid")),
              asignar(5, "Hijo", *NEW), asignar_campo(6, "Hijo", "Entid", campo("Bc", "Entid")), metodo(7, "Hijo", "Insert")]
        self.assertEqual(revisar(*fu), [])

    def test_historial_no_se_exige(self):
        hist = [asignar(4, "Hist", *NEW), asignar_campo(5, "Hist", "Texto", campo("Inset", "Nombre")),
                metodo(6, "Hist", "Insert")]
        self.assertEqual(revisar(*hist, nombre="X.EntidadHistorial_Grabar"), [])
        self.assertEqual(revisar(*hist, nombre="X.EntidadHistorial_Grabar", parm=SIN_SALIDA), [])
        # Si ademas crea la entidad, esa si se exige.
        self.assertEqual(revisar(*CREA, *hist), [(3, "advertencia", "Crea Entidad y no devuelve su clave (EntId)")])

    def test_bc_que_llega_cargado_no_se_juzga(self):
        fu = [metodo(1, "Bc", "FromJson", campo("Inset", "Json")), metodo(2, "Bc", "Save")]
        self.assertEqual(revisar(*fu), [])

    def test_sin_parametros_de_salida(self):
        self.assertEqual(revisar(*CREA, parm=SIN_SALIDA),
                         [(3, "advertencia", "Crea Entidad y no tiene parametros de salida para devolver su id")])
        self.assertEqual(revisar(*CREA, parm=SIN_SALIDA, nombre="X.Proceso"), [])  # sin nombre de alta no se exige

    def test_nombre_de_otra_operacion(self):
        self.assertEqual(revisar(*CREA, nombre="X.Entidad_Actualizar"), [])
        self.assertEqual(len(revisar(*CREA, nombre="X.Entidad")), 1)  # sin decir nada: se revisa


class Transacciones(unittest.TestCase):
    def test_clave_y_autonumerados(self):
        tr = transacciones._armar(r"""
spec_i([ trn,90,'Registros','Generales\Interfases\gntItfRegistro',[],spa,'18_0_15' ]).
rule_i(0,datastore(1,'USER_PASSWORD','no se lee')).
attri_i(600,[ 'ItfId',int,6,0,'ZZZZZ9',0,'Interfase','',0 ]).
attri_i(614,[ 'ItfRegTipo',char,10,0,'',0,'Tipo de Registro','',0 ]).
att_prop_i(2,600,'AUTONUMBER','-1',d).
att_prop_i(2,614,'AUTONUMBER','0',d).
a_i(20,163,r,98,[],[ [ [ 163,600,600 ] ],'IGNTINTERFASE',[] ]).
a_i(19,163,t,163,[],[ [ [ [],600,600 ],[ [],614,614 ] ],'IGNTITFREGISTRO',[] ]).
""")
        self.assertEqual((tr.nombre, tr.claves, tr.autonumeradas),
                         ("Generales.Interfases.gntItfRegistro", ["ItfId", "ItfRegTipo"], {"ItfId"}))

    def test_no_es_transaccion(self):
        self.assertIsNone(transacciones._armar("spec_i([ proc,1,'P','X\\P',0,spa,'18_0_15' ])."))


if __name__ == "__main__":
    unittest.main()
