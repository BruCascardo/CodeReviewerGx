"""Ayuda de los campos de la entrada (gxp/campos), con fragmentos de .sp0 reales (no necesitan las KBs).

    python -m unittest pruebas.test_campos
"""
import unittest
from unittest import mock

import gxp.campos as campos
from gxp.campos import dominios, indice

# Procedimiento Generales.Interfases.Registro.Set: recibe &inSet (SDT con un campo de un dominio enumerado y
# una coleccion de SDT) y &Tipo (variable de un dominio enumerado).
PROC = r"""
rule_i(0,datastore(1,'USER_PASSWORD','no se lee')).
attri_i('Inset',[ inSet,o('Generales\Interfases\Registro\inSet'),0,0,'',0,'in Set','',9 ]).
attri_i('Tipo',[ 'Tipo',char,1,0,'',0,'Tipo','',3 ]).
attri_i('Lista',[ 'Lista',o(objectcollection('Generales\Interfases\Registro\inSet')),0,0,'',0,'','',4 ]).
struct_dt_i([ 26,934,0 ],name,'Generales\Interfases\Registro\inSet').
struct_dt_elem_i([ 26,934,0 ],1,name,'Itfid').
struct_dt_elem_i([ 26,934,0 ],1,basedon,179).
struct_dt_elem_i([ 26,934,0 ],1,type,[ 4,6,0 ]).
struct_dt_elem_i([ 26,934,0 ],1,collection,'False').
struct_dt_elem_i([ 26,934,0 ],2,name,'Fin').
struct_dt_elem_i([ 26,934,0 ],2,basedon,296).
struct_dt_elem_i([ 26,934,0 ],2,type,[ 5,4,0 ]).
struct_dt_elem_i([ 26,934,0 ],3,name,'Items').
struct_dt_elem_i([ 26,934,0 ],3,type,[ [ 26,934,7 ],4,0 ]).
struct_dt_elem_i([ 26,934,0 ],3,collection,'True').
struct_dt_elem_i([ 26,934,7 ],1,name,'Orden').
struct_dt_elem_i([ 26,934,7 ],1,basedon,604).
struct_dt_elem_i([ 26,934,7 ],1,type,[ 4,4,0 ]).
enumerated_i(2,'Tipo',293).
enum_value_i(2,296,'"CR"','CR','"CR"',[ none ]).
enum_value_i(2,296,'"CRLF"','CRLF','"CR+LF"',[ none ]).
enum_value_info_i(2,296,'Generales\RegistroFin').
enum_value_i(2,37,'0','Warning','"Warning"',[ none ]).
dom_info_i(179,[ 'Generales\Id' ]).
"""

PARAMS = [{"nombre": "inSet", "io": "in", "atributo": False}, {"nombre": "Tipo", "io": "in", "atributo": False},
          {"nombre": "Lista", "io": "in", "atributo": False}, {"nombre": "outSet", "io": "out", "atributo": False}]

# Transaccion gntInterfase: un nivel, clave ItfId, descriptor ItfNombre; trae tambien gntItfRegistro (otra
# transaccion) y los valores del dominio InterfaseTipo.
TRN = r"""
attri_i(600,[ 'ItfId',int,6,0,'ZZZZZ9',0,'Interfase','',0 ]).
attri_i(601,[ 'ItfNombre',svchar,50,0,'@!',0,'Nombre','',0 ]).
attri_i(614,[ 'ItfRegTipo',char,10,0,'',0,'Tipo','',0 ]).
table_i(98,[ gntInterfase,[ 600,601 ],gntInterfase,gntInterfase ]).
table_i(163,[ gntItfRegistro,[ 600,614 ],'',gntItfRegistro ]).
index_i(98,[ 'IGNTINTERFASE1',u,[ 601 ],'IgntInterfase1' ]).
index_i(98,[ 'IGNTINTERFASE',u,[ 600 ],'IgntInterfase' ]).
index_i(163,[ 'IGNTITFREGISTRO',u,[ 600,614 ],'IgntItfRegistro' ]).
trn_level_i(98,[ [ 600,601 ],'Generales\Interfases\gntInterfase','Interfases','Generales\Interfases\gntInterfase','',601 ]).
enum_value_i(2,293,'"S"','SALIDA','"Salida"',[ none ]).
enum_value_i(2,293,'"E"','ENTRADA','"Entrada"',[ none ]).
enum_value_info_i(2,293,'Generales\InterfaseTipo').
"""


class Dominios(unittest.TestCase):
    def test_hojas_de_la_entrada(self):
        es = dominios.armar(PROC)
        hojas = {r: (campo, dom) for r, campo, dom, _tipo in dominios.hojas(es, PARAMS)}
        self.assertEqual(hojas, {
            "inset.itfid": ("Itfid", 179), "inset.fin": ("Fin", 296), "inset.items[*].orden": ("Orden", 604),
            "tipo": ("Tipo", 293),
            "lista[*].itfid": ("Itfid", 179), "lista[*].fin": ("Fin", 296), "lista[*].items[*].orden": ("Orden", 604),
        })

    def test_valores_de_los_enumerados(self):
        es = dominios.armar(PROC)
        self.assertEqual(es.dominios[296], "Generales\\RegistroFin")
        self.assertEqual(es.valores[296], [{"valor": "CR", "nombre": "CR", "descripcion": "CR"},
                                           {"valor": "CRLF", "nombre": "CRLF", "descripcion": "CR+LF"}])
        self.assertEqual(es.valores[37][0]["valor"], 0)  # enumerado numerico
        self.assertEqual(es.dominios[179], "Generales\\Id")


class Indice(unittest.TestCase):
    def test_tablas_de_la_transaccion(self):
        ix = indice.armar(TRN)
        # Solo las tablas de los niveles de la transaccion; la clave es el indice I+tabla, no el primero.
        self.assertEqual(list(ix.tablas), ["itfid"])
        t = ix.tablas["itfid"]
        self.assertEqual((t.nombre, t.claves, t.descripcion, t.titulo), ("gntInterfase", ["ItfId"], "ItfNombre", "Interfases"))
        self.assertEqual([v["valor"] for v in ix.valores[293]], ["S", "E"])
        self.assertEqual(ix.dominios[293], "Generales\\InterfaseTipo")
        self.assertTrue(t.numerica)  # ItfId es int: se le puede calcular el siguiente

    def _externa(self, ds, nombre, dbms, *props):
        """TRN con su tabla en otro datastore (las propiedades fv de la tabla, como las escribe GeneXus)."""
        return TRN + "\n".join([
            "rule_i(0,datastore(2,'USER_ID',root)).", f"rule_i(0,datastore(2,'NAME','{nombre}')).",
            f"rule_i(0,datastore(2,'DBMS',{dbms})).", "rule_i(0,datastore(1,'NAME','Generales')).",
            "rule_i(0,datastore(1,'DBMS',18)).", "rule_i(0,p(0,0,fv,7,[ table,98 ])).", f"rule_i(0,p(0,0,fv,7,[ datastore,{ds} ])).",
            *props, "map_i(98,a,600,[ 'InterfaseId' ]).", "map_i(98,a,601,[ 'ItfNombre' ]).", ""])

    def test_datastore_y_columnas_fisicas(self):
        # Una tabla de otro datastore (GAM) cuyos atributos tienen otro nombre en la base (como la User de GAM).
        # La conexion del datastore no se lee: solo su nombre y su motor.
        from gxp.campos import expresiones
        ix = indice.armar(self._externa(2, "GAM", 18))
        t = ix.tablas["itfid"]
        self.assertEqual((t.datastore, t.dbms, t.columnas), ("GAM", "18", {"ItfId": "InterfaseId"}))
        self.assertEqual((t.col("itfid"), t.col("ItfNombre")), ("InterfaseId", "ItfNombre"))
        self.assertEqual(indice.armar(TRN).tablas["itfid"].datastore, "")  # sin la propiedad: el principal
        self.assertEqual(indice.armar(self._externa(1, "Generales", 18)).tablas["itfid"].datastore, "")  # el principal
        _, q = expresiones.consulta(ix, expresiones.parsear("ultimo", "ItfId|ItfNombre=X"))
        # En otro datastore puede haber claves nulas: no sirven de entrada
        self.assertEqual(q, "select t.InterfaseId as valor from gntInterfase t where t.InterfaseId is not null and t.ItfNombre = 'X' "
                            "order by t.InterfaseId desc limit 1")
        otra = indice.Tabla("gntItfLog", ["LogId"], None, "", "int", ["LogId", "ItfId"])
        ix.agregar_tabla(otra)
        self.assertEqual(ix.relaciones(otra), [])  # en otro datastore: no se puede unir

    def test_dialecto_del_motor(self):
        from gxp.campos import expresiones
        sql = lambda trn, resto="ItfId|ItfNombre=O'Brien\\": expresiones.consulta(indice.armar(trn), expresiones.parsear("existente", resto))[1]
        sqlserver = self._externa(2, "NorteWeb", 12, "rule_i(0,p(0,12,fv,7,[ 'NAME','Interfase' ])).", "rule_i(0,p(0,12,fv,7,[ 'SCHEMA',dbo ])).")
        self.assertEqual(sql(sqlserver), "select top 1 t.[InterfaseId] as valor from dbo.[Interfase] t where t.[InterfaseId] is not null "
                                         "and t.[ItfNombre] = 'O''Brien\\' order by t.[InterfaseId]")
        # En SQL Server el numero va entre comillas: sirve tambien si la columna externa es texto
        self.assertIn("t.[InterfaseId] = '7'", sql(sqlserver, "ItfId|ItfId=7"))
        db2 = self._externa(2, "NORTE", 9).replace("'InterfaseId'", "'T@ID'")
        self.assertEqual(sql(db2), "select t.T@ID as valor from gntInterfase t where t.T@ID is not null and t.ItfNombre = 'O''Brien\\' "
                                   "order by t.T@ID fetch first 1 rows only")
        mysql = TRN + "map_i(98,a,600,[ 'T@ID' ]).\n"
        self.assertEqual(sql(mysql), "select t.`T@ID` as valor from gntInterfase t where t.ItfNombre = 'O''Brien\\\\' "
                                     "order by t.`T@ID` limit 1")  # solo MySQL escapa la barra

    def test_subtipo_se_queda_con_la_clave_mas_corta(self):
        ix = indice.Indice()
        ix.agregar_tabla(indice.Tabla("gntItfRegistro", ["ItfId", "RegId"], None, ""))
        ix.agregar_tabla(indice.Tabla("gntRegistro", ["RegId"], "RegNombre", ""))
        self.assertEqual(ix.tablas["regid"].nombre, "gntRegistro")


class Siguiente(unittest.TestCase):
    def setUp(self):
        self.ix = indice.Indice()
        self.ix.agregar_tabla(indice.Tabla("cbhCupon", ["CuponId"], None, "", "int"))
        self.ix.agregar_tabla(indice.Tabla("gntTipo", ["TipoCod"], None, "", "char"))

    def test_maximo_mas_uno_de_toda_la_tabla(self):
        with mock.patch.object(campos.indice, "de_kb", return_value=self.ix),                 mock.patch.object(campos.motor, "consulta_suelta", return_value=({"ok": True}, {"filas": [{"siguiente": "60"}]})) as q:
            self.assertEqual(campos.siguiente(None, "cuponid"), 60)
        self.assertEqual(q.call_args[0][2], "select coalesce(max(CuponId), 0) + 1 as valor from cbhCupon")

    def test_en_transaccion_usa_la_conexion_del_caso(self):
        with mock.patch.object(campos.indice, "de_kb", return_value=self.ix),                 mock.patch.object(campos.motor, "consulta_suelta") as suelta,                 mock.patch.object(campos.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": [{"siguiente": 1}]})):
            self.assertEqual(campos.siguiente(None, "CuponId", en_transaccion=True), 1)
        suelta.assert_not_called()

    def test_clave_no_numerica(self):
        with mock.patch.object(campos.indice, "de_kb", return_value=self.ix):
            with self.assertRaises(ValueError):
                campos.siguiente(None, "TipoCod")


class DeObjeto(unittest.TestCase):
    def test_enumerados_del_objeto_del_indice_y_claves(self):
        ix = indice.armar(TRN)
        with mock.patch.object(campos.catalogo, "buscar", return_value={"nombre": "X.Set", "parametros": PARAMS}), \
                mock.patch.object(campos.fuente, "ubicar", return_value="X.sp0"), \
                mock.patch.object(campos.dominios, "leer", return_value=dominios.armar(PROC)), \
                mock.patch.object(campos.indice, "de_kb", return_value=ix):
            d = campos.de_objeto(None, "X.Set")
        self.assertEqual(d["inset.fin"]["dominio"], "Generales\\RegistroFin")
        self.assertEqual(len(d["inset.fin"]["valores"]), 2)
        # La variable &Tipo es de un dominio que el objeto no describe: los valores salen de la transaccion.
        self.assertEqual([v["valor"] for v in d["tipo"]["valores"]], ["S", "E"])
        self.assertEqual(d["inset.itfid"]["clave"]["tabla"], "gntInterfase")
        self.assertEqual(d["inset.itfid"]["dominio"], "Generales\\Id")
        self.assertNotIn("inset.items[*].orden", d)


class Valores(unittest.TestCase):
    def consulta(self, atributo, filtros=None, buscar=""):
        ix = indice.Indice()
        ix.agregar_tabla(indice.Tabla("gntItfRegistro", ["ItfId", "ItfRegTipo"], None, ""))
        ix.agregar_tabla(indice.Tabla("gntInterfase", ["ItfId"], "ItfNombre", ""))
        kb = mock.Mock(nombre="Generales")
        with mock.patch.object(campos.indice, "de_kb", return_value=ix), \
\
                mock.patch.object(campos.motor, "consulta_suelta", return_value=({"ok": True}, {"filas": []})) as cs:
            r = campos.valores(kb, atributo, filtros, buscar)
        return cs.call_args.args[2], r

    def test_filtra_por_los_otros_campos_de_la_clave(self):
        q, r = self.consulta("itfregtipo", {"itfid": 3, "Otro": "x"})
        self.assertEqual(q, "select ItfId, ItfRegTipo from gntItfRegistro where ItfId = 3 order by ItfId, ItfRegTipo")
        self.assertEqual(r["filtros"], {"ItfId": 3})

    def test_no_filtra_por_variables_ni_vacios(self):
        for v in ("${itf}", "", None, "<<no_vacio>>"):
            q, _ = self.consulta("ItfRegTipo", {"ItfId": v})
            self.assertNotIn("where", q)

    def test_buscar_escapa_el_texto(self):
        q, _ = self.consulta("ItfId", buscar="o'b_1%")
        self.assertIn(r"ItfNombre LIKE '%o''b\\_1\\%%'", q)

    def test_atributo_que_no_es_clave(self):
        with self.assertRaises(KeyError):
            self.consulta("ItfNombre")


if __name__ == "__main__":
    unittest.main()
