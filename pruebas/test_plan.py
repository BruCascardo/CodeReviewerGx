"""Plan de ejecucion (gxp/plan): lectura del SQL del Java generado y recomendaciones (no necesitan las KBs).

    python -m unittest pruebas.test_plan
"""
import unittest

from gxp.plan import reglas, sentencias

JAVA = r'''
final  class list__generales extends DataStoreHelperBase implements ILocalDataStoreHelper
{
   protected Object[] conditional_P014M5( ModelContext context , String AV13SearchTxt )
   {
      java.lang.StringBuffer sWhereString = new java.lang.StringBuffer();
      sSelectString = " `AgrId`, `AgrNivelNombre`, `AgrNivel`" ;
      sFromString = " FROM `gntAgrNivel`" ;
      sOrderString = "" ;
      addWhere(sWhereString, "(`AgrId` = ?)");
      if ( ! (GXutil.strcmp("", AV13SearchTxt)==0) )
      {
         addWhere(sWhereString, "(`AgrNivelNombre` like CONCAT('%', ?))");
      }
      sOrderString += " ORDER BY `AgrNivelNombre`" ;
      scmdbuf = "SELECT " + sSelectString + sFromString + sWhereString + sOrderString + "" + " LIMIT " + "?" + ", " + "?" ;
      GXv_Object5[0] = scmdbuf ;
      return GXv_Object5 ;
   }

   public Cursor[] getCursors( )
   {
      return new Cursor[] {
          new ForEachCursor("P014U2", "SELECT `ItfId` FROM `gntInterfase` WHERE `ItfId` = ? ORDER BY `ItfId` ",false, GX_NOMASK, false, this,1, GxCacheFrequency.OFF,true )
         ,new ForEachCursor("P014M3", "SELECT T1.`AgrNivel`, T2.`AgrNombre` FROM (`gntAgrNivelClave` T1 INNER JOIN `gntAgrupacion` T2 ON T2.`AgrId` = T1.`AgrId`) WHERE T1.`AgrId` = ? and T1.`AgrNivel` > ? ORDER BY T1.`AgrId`, T1.`AgrNivel`",false, GX_NOMASK, false, this,1, GxCacheFrequency.OFF,true )
         ,new ForEachCursor("P014M5", "scmdbuf",false, GX_NOMASK, false, this,100, GxCacheFrequency.OFF,false )
         ,new UpdateCursor("P014U4", "DELETE FROM `gntItfRegistro`  WHERE `ItfId` = ? AND `ItfRegTipo` = ?", GX_NOMASK)
         ,new UpdateCursor("P014U5", "INSERT INTO `gntItfRegistro`(`ItfId`, `ItfRegTipo`) VALUES(?, ?)", GX_NOMASK)
      };
   }

   public String getDataStoreName( )
   {
      return "GENERALES";
   }
}
'''


def meta(**tablas):
    """meta(tabla=(filas, {indice: [columnas]}))"""
    return {t.lower(): {"nombre": t, "filas": f, "columnas": {},
                        "indices": {n: {"columnas": c, "unico": n == "PRIMARY"} for n, c in idx.items()}}
            for t, (f, idx) in tablas.items()}


def reglas_de(hallazgos):
    return sorted((h["regla"], h["tabla"], h["nivel"]) for h in hallazgos)


class Sentencias(unittest.TestCase):
    def setUp(self):
        self.ss = {s.cursor: s for s in sentencias.de_java(JAVA)}

    def test_cursores_tipos_y_datastore(self):
        self.assertEqual(list(self.ss), ["P014U2", "P014M3", "P014M5", "P014U4", "P014U5"])
        self.assertEqual([s.tipo for s in self.ss.values()], ["select", "select", "select", "delete", "insert"])
        self.assertTrue(all(s.ds == "GENERALES" for s in self.ss.values()))

    def test_dinamica_con_todos_los_filtros(self):
        s = self.ss["P014M5"]
        self.assertTrue(s.dinamica)
        self.assertEqual(s.sql, "SELECT  `AgrId`, `AgrNivelNombre`, `AgrNivel` FROM `gntAgrNivel` WHERE (`AgrId` = ?) and "
                                "(`AgrNivelNombre` like CONCAT('%', ?)) ORDER BY `AgrNivelNombre` LIMIT ?, ?")
        self.assertEqual(s.like_inicial, [("", "AgrNivelNombre")])

    def test_join_tablas_condiciones_y_orden(self):
        s = self.ss["P014M3"]
        self.assertEqual(s.tablas, {"T1": "gntAgrNivelClave", "T2": "gntAgrupacion"})
        conds = {(c.alias, c.columna, c.op, c.valor) for c in s.condiciones}
        self.assertIn(("T1", "AgrId", "=", "?"), conds)
        self.assertIn(("T1", "AgrNivel", ">", "?"), conds)
        self.assertIn(("T2", "AgrId", "=", "T1.`AgrId`"), conds)
        self.assertIn(("T1", "AgrId", "=", "T2.`AgrId`"), conds)  # la relacion vale para las dos tablas
        self.assertEqual(s.orden, [("T1", "AgrId"), ("T1", "AgrNivel")])

    def test_subconsulta_de_formula(self):
        s = sentencias.leer("C", "", "SELECT COALESCE( T1.`Total`, 0) AS Total FROM (SELECT SUM(`Importe`) AS Total, "
                                     "`IngId` FROM `cbhIngValor` WHERE `IngId` = ? GROUP BY `IngId` ) T1 WHERE T1.`IngId` = ?")
        self.assertEqual(s.principal, "")
        self.assertEqual([p.principal for p in s.todas()], ["", "cbhIngValor"])
        self.assertEqual([(c.columna, c.valor) for c in s.subconsultas[0].condiciones], [("IngId", "?")])

    def test_sustituir_parametros(self):
        valores = {"itfid": "7", "itfregtipo": "'DET'"}
        q = sentencias.sustituir(self.ss["P014U4"].sql, lambda a, c: valores.get(c.lower()))
        self.assertEqual(q, "DELETE FROM `gntItfRegistro`  WHERE `ItfId` = 7 AND `ItfRegTipo` = 'DET'")
        q = sentencias.sustituir(self.ss["P014M5"].sql, lambda a, c: None)
        self.assertTrue(q.endswith("(`AgrId` = 1) and (`AgrNivelNombre` like CONCAT('%', 'a')) "
                                   "ORDER BY `AgrNivelNombre` LIMIT 0, 100"), q)
        self.assertEqual(sentencias.literal("o'b"), "'o''b'")


class PorIndices(unittest.TestCase):
    def test_filtro_por_la_clave_no_dice_nada(self):
        s = sentencias.leer("C", "", "SELECT `ItfId` FROM `gntInterfase` WHERE `ItfId` = ? ORDER BY `ItfId`")
        self.assertEqual(reglas.por_indices(s, meta(gntInterfase=(5, {"PRIMARY": ["ItfId"]}))), [])

    def test_filtro_por_la_segunda_columna_de_la_clave(self):
        s = sentencias.leer("C", "", "UPDATE `gntPerSubTipo` SET `Marca`=1 WHERE `PerSubTipoId` <> ?")
        h = reglas.por_indices(s, meta(gntPerSubTipo=(3, {"PRIMARY": ["PerTipo", "PerSubTipoId"]})))
        self.assertEqual(reglas_de(h), [("sin-indice", "gntPerSubTipo", "alto")])  # UPDATE: alto aunque sea chica
        self.assertIn("PerSubTipoId", h[0]["sugerencia"])

    def test_distinto_usa_indice_como_rango(self):
        s = sentencias.leer("C", "", "SELECT `CargoId` FROM `cbhCargo` WHERE (`CargoPlanPagoId` <> 0) AND (`CargoEstado` = 'PEN')")
        h = reglas.por_indices(s, meta(cbhCargo=(1741, {"PRIMARY": ["CargoId"], "ICBHCARGO": ["CargoPlanPagoId"]})))
        self.assertEqual(h, [])

    def test_tabla_grande_sube_el_nivel(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` WHERE `Estado` = ?")
        h = reglas.por_indices(s, meta(t=(50000, {"PRIMARY": ["A"]})))
        self.assertEqual(reglas_de(h), [("sin-indice", "t", "alto")])

    def test_join_sin_indice_en_la_tabla_de_adentro(self):
        s = sentencias.leer("C", "", "SELECT T1.`A` FROM (`t1` T1 INNER JOIN `t2` T2 ON T2.`Ref` = T1.`A`) WHERE T1.`A` = ?")
        h = reglas.por_indices(s, meta(t1=(10, {"PRIMARY": ["A"]}), t2=(10, {"PRIMARY": ["Id"]})))
        self.assertEqual(reglas_de(h), [("join-sin-indice", "t2", "alto")])

    def test_like_funcion_y_orden(self):
        s = sentencias.leer("C", "", "SELECT `Id` FROM `t` WHERE `Pais` = ? and (`Nombre` like CONCAT('%', ?)) "
                                     "and UPPER(`Codigo`) = ? ORDER BY `Nombre`")
        h = reglas.por_indices(s, meta(t=(10, {"PRIMARY": ["Id"], "IPAIS": ["Pais"]})))
        # El orden se hace sobre lo que filtra el indice IPAIS: bajo.
        self.assertEqual(reglas_de(h), [("funcion-columna", "t", "medio"), ("like-comodin", "t", "bajo"),
                                        ("orden-sin-indice", "t", "bajo")])

    def test_orden_salteando_las_columnas_fijadas(self):
        s = sentencias.leer("C", "", "SELECT `B` FROM `t` WHERE `A` = ? ORDER BY `A`, `B`")
        self.assertEqual(reglas.por_indices(s, meta(t=(10, {"PRIMARY": ["A", "B"]}))), [])

    def test_lectura_completa_de_tabla_grande(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` ORDER BY `A`")
        self.assertEqual(reglas_de(reglas.por_indices(s, meta(t=(5000, {"PRIMARY": ["A"]})))), [("tabla-completa", "t", "medio")])
        self.assertEqual(reglas.por_indices(s, meta(t=(50, {"PRIMARY": ["A"]}))), [])


class PorExplain(unittest.TestCase):
    def test_confirma_y_no_repite(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` WHERE `Estado` = ?")
        m = meta(t=(500, {"PRIMARY": ["A"]}))
        previos = reglas.por_indices(s, m)
        nuevos = reglas.por_explain(s, [{"table": "t", "type": "ALL", "rows": 480, "filtered": 10, "Extra": "Using where"}], m, previos)
        self.assertEqual(nuevos, [])
        self.assertEqual(previos[0]["origen"], "indices+explain")
        self.assertIn("MySQL lo confirma", previos[0]["detalle"])

    def test_mysql_usa_un_indice_descarta_el_analisis(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` WHERE `Estado` = ?")
        m = meta(t=(500, {"PRIMARY": ["A"]}))
        previos = reglas.por_indices(s, m)
        reglas.por_explain(s, [{"table": "t", "type": "ref", "key": "IOTRO", "rows": 3, "Extra": None}], m, previos)
        self.assertTrue(previos[0].get("descartar"))

    def test_solo_explain_con_pocas_filas_no_dice_nada(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` WHERE `A` = ?")
        m = meta(t=(5, {"PRIMARY": ["A"]}))
        plan = [{"table": "t", "type": "ALL", "possible_keys": "PRIMARY", "rows": 5, "Extra": "Using temporary"}]
        self.assertEqual(reglas.por_explain(s, plan, m, []), [])

    def test_poco_selectivo(self):
        s = sentencias.leer("C", "", "SELECT `A` FROM `t` WHERE `B` = ? and `C` = ?")
        plan = [{"table": "t", "type": "ref", "key": "IB", "rows": 20000, "filtered": 2, "Extra": "Using where"}]
        self.assertEqual(reglas_de(reglas.por_explain(s, plan, meta(t=(90000, {"IB": ["B"]})), [])),
                         [("poco-selectivo", "t", "medio")])


class Navegacion(unittest.TestCase):
    def test_for_each_anidado_sobre_otra_tabla(self):
        niveles = [{"tipo": "For Each", "linea": "3", "tabla": "gntPerTipoDocumento", "subniveles": [
            {"tipo": "For First", "linea": "14", "tabla": "gntRegEx", "subniveles": []},
            {"tipo": "For Each", "linea": "20", "tabla": "gntPerTipoDocumento", "subniveles": []}]}]
        h = reglas.anidadas(niveles, meta(gntPerTipoDocumento=(20000, {})))
        self.assertEqual(reglas_de(h), [("consulta-anidada", "gntRegEx", "medio")])
        self.assertIn("línea 3", h[0]["titulo"])


if __name__ == "__main__":
    unittest.main()
