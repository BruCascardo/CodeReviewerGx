import unittest

from gxp.revisor import pantalla_bc
from gxp.revisor.pruebas import leer, linea, llamar
from gxp.revisor.reglas import cargar

# Fragmentos del Java que genera GeneXus para la pantalla (x_impl.java) y el BC (x_bc.java) de una transaccion.
IMPL = r'''
   public void beforeValidate2585( )
   {
      /* Before Validate Rules */
      if ( ( isIns( )  || isUpd( )  ) && ! new com.generales.personas.perentfinanciera_validacbu(remoteHandle, context).executeUdp( AV7EntFinId) )
      {
         httpContext.GX_msglist.addItem("El CBU no coincide con la Entidad Financiera seleccionada", 1, "");
         AnyError = (short)(1) ;
      }
      if ( (0==AV7EntFinId) )
      {
         httpContext.GX_msglist.addItem("Por favor seleccione una Entidad Financiera", 1, "");
         AnyError = (short)(1) ;
      }
      if ( (0==A1Id) )
      {
         httpContext.GX_msglist.addItem("El Id es requerido", 1, "ID");
         AnyError = (short)(1) ;
      }
   }

   public void afterConfirm2585( )
   {
      new com.generales.personas.persona_nombrecompleto(remoteHandle, context).execute( A1Id, GXv_char1) ;
      new com.generales.personas.ambitos_grabar(remoteHandle, context).execute( A1Id) ;
      new com.generales.wwpbaseobjects.gntentfinanciera_loaddvcombo(remoteHandle, context).execute( ) ;
      new com.generales.personas.ya_en_el_bc(remoteHandle, context).execute( A1Id) ;
   }

   public void e120Z2( )
   {
      /* After Trn Routine */
      new com.generales.personas.otro_grabar(remoteHandle, context).execute( A1Id) ;
      httpContext.GX_msglist.addItem("Un mensaje de un evento", 1, "");
   }
'''

BC = r'''
   public void beforeValidate2585( )
   {
      /* Before Validate Rules */
      if ( (0==A1Id) )
      {
         httpContext.GX_msglist.addItem("El Id es requerido", 1, "ID");
         AnyError = (short)(1) ;
      }
   }

   public void afterConfirm2585( )
   {
      new com.generales.personas.ya_en_el_bc(remoteHandle, context).execute( A1Id) ;
   }
'''

GRABAN = {"com.generales.personas.ambitos_grabar", "com.generales.personas.otro_grabar", "com.generales.personas.ya_en_el_bc"}


class Comparar(unittest.TestCase):
    def setUp(self):
        self.difs = pantalla_bc.comparar(IMPL, BC, lambda c: c in GRABAN)

    def test_diferencias(self):
        self.assertEqual([(d["tipo"], d["clase"].rsplit(".", 1)[-1] or d["mensaje"], d["lugar"]) for d in self.difs], [
            ("valida", "perentfinanciera_validacbu", "regla Before Validate"),
            ("error", "El CBU no coincide con la Entidad Financiera seleccionada", "regla Before Validate"),
            ("error", "Por favor seleccione una Entidad Financiera", "regla Before Validate"),
            ("graba", "ambitos_grabar", "regla After Confirm"),
            ("graba", "otro_grabar", "evento After Trn"),
        ])

    def test_lo_que_no_se_informa(self):
        clases = {d["clase"] for d in self.difs}
        self.assertNotIn("com.generales.personas.persona_nombrecompleto", clases)  # solo lee
        self.assertNotIn("com.generales.wwpbaseobjects.gntentfinanciera_loaddvcombo", clases)  # combo
        self.assertNotIn("com.generales.personas.ya_en_el_bc", clases)  # el BC tambien lo llama
        self.assertNotIn("El Id es requerido", {d.get("mensaje") for d in self.difs})  # el BC tambien lo da
        self.assertNotIn("Un mensaje de un evento", {d.get("mensaje") for d in self.difs})  # los eventos no son reglas

    def test_prefijo_de_otra_clase_no_cuenta_como_igual(self):
        impl = "   public void afterConfirm1( )\n   {\n      new com.x.grabar(remoteHandle, context).execute( ) ;\n   }\n"
        bc = "   public void afterConfirm1( )\n   {\n      new com.x.grabar_todo(remoteHandle, context).execute( ) ;\n   }\n"
        self.assertEqual([d["clase"] for d in pantalla_bc.comparar(impl, bc, lambda c: True)], ["com.x.grabar"])


class Ctx:
    kb_nombre = "Prueba"

    def __init__(self, difs):
        self.difs = difs

    def diferencias_bc(self, objeto):
        return self.difs


def revisar(fu, difs):
    regla = cargar()["logica-solo-en-pantalla"]()
    ctx = Ctx(difs)
    if not regla.aplica(fu, ctx):
        return []
    return list(regla.revisar(fu, ctx))


class LogicaSoloEnPantalla(unittest.TestCase):
    DIFS = [
        {"tipo": "graba", "clase": "com.g.otro_grabar", "objeto": "Generales.Personas.Otro_Grabar", "lugar": "evento After Trn"},
        {"tipo": "valida", "clase": "com.g.validacbu", "objeto": "Generales.Personas.ValidaCbu", "lugar": "regla Before Validate"},
        {"tipo": "error", "clase": "", "objeto": "", "mensaje": "Seleccione una entidad", "lugar": "regla Before Validate"},
    ]

    def test_hallazgos(self):
        fu = leer("X.T", "\n".join([linea(10, 146, "t('''After Trn''',3,0,0)"), llamar(11, "Generales\\Personas\\Otro_Grabar"),
                                    linea(12, 147)]), tipo="trn")
        hs = revisar(fu, self.DIFS)
        self.assertEqual([(h.linea, h.datos["diferencia"]) for h in hs], [(11, "graba"), (0, "valida"), (0, "error")])
        self.assertEqual(hs[0].mensaje, "La pantalla graba con Generales.Personas.Otro_Grabar (evento After Trn) y el Business Component no")
        self.assertEqual(hs[2].mensaje, "Solo la pantalla da el error «Seleccione una entidad» (regla Before Validate)")
        self.assertEqual(hs[1].severidad, "advertencia")

    def test_solo_transacciones(self):
        # La especificacion X_BC del Business Component no llega: el revisor la ignora (configuracion.ignorado).
        self.assertEqual(revisar(leer("X.P", ""), self.DIFS), [])


if __name__ == "__main__":
    unittest.main()
