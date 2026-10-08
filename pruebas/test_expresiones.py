"""Valores de una clave calculados en la base (gxp/campos/expresiones.py) y fechas relativas (gxp/suites/fechas.py).

    python -m unittest pruebas.test_expresiones
"""
import datetime as dt
import unittest
from unittest import mock

import gxp.campos as campos
from gxp.campos import expresiones, indice
from gxp.suites import fechas


def _indice():
    ix = indice.Indice()
    ix.agregar_tabla(indice.Tabla("cbhCupon", ["CuponId"], "CuponTipo", "", "int",
                                  ["CuponId", "CuponTipo", "CuponEstado"], {"CuponEstado": 283}))
    ix.agregar_tabla(indice.Tabla("cbhCuponDetalle", ["CuponId", "CuponDetSec"], None, "", "int",
                                  ["CuponId", "CuponDetSec", "Importe"]))
    ix.agregar_tabla(indice.Tabla("cbhLoteDetalle", ["LoteId", "LoteDetSec"], None, "", "int",
                                  ["LoteId", "LoteDetSec", "CuponId"]))
    ix.agregar_tabla(indice.Tabla("gntTipo", ["TipoCod"], None, "", "char"))
    ix.valores[283] = [{"valor": "PRO", "nombre": "EN_PROCESO", "descripcion": "En proceso"},
                       {"valor": "PEN", "nombre": "PENDIENTE", "descripcion": "Pendiente"}]
    return ix


class Parsear(unittest.TestCase):
    def test_atributo_tabla_y_condiciones(self):
        p = expresiones.parsear("con_hijos", "CuponId:cbhCuponDetalle|CuponEstado=PENDIENTE, CuponId != 3")
        self.assertEqual((p.atributo, p.hija), ("CuponId", "cbhCuponDetalle"))
        self.assertEqual(p.condiciones, [("CuponEstado", "=", "PENDIENTE", (), ()), ("CuponId", "<>", "3", (), ())])

    def test_condicion_sobre_otra_tabla(self):
        p = expresiones.parsear("existente", "CargoCuotaNumero|!cbhCuponDetalle . cbhCupon.CuponEstado=EN_PROCESO,"
                                             "cbhCargo.!cbhAplicacion,X=${ultimo.A|B=1,C=2}")
        self.assertEqual(p.condiciones, [("CuponEstado", "=", "EN_PROCESO", ("cbhCuponDetalle", "cbhCupon"), (True, False)),
                                         ("", "", "", ("cbhCargo", "cbhAplicacion"), (False, True)),
                                         ("X", "=", "${ultimo.A|B=1,C=2}", (), ())])
        self.assertEqual([c.texto() for c in p.condiciones],
                         ["!cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO", "cbhCargo.!cbhAplicacion", "X=${ultimo.A|B=1,C=2}"])

    def test_mal_escritas(self):
        for f, resto in [("existente", ""), ("existente", "CuponId|Cupon Estado"), ("siguiente", "CuponId|A=1"),
                         ("existente", "CuponId|!CuponEstado=PEN"), ("existente", "CuponId|cbhCupon.=1"),
                         ("existente", "CuponId:otra"), ("nada", "CuponId")]:
            with self.subTest(f=f, resto=resto), self.assertRaises(ValueError):
                expresiones.parsear(f, resto)


class Consulta(unittest.TestCase):
    def setUp(self):
        self.ix = _indice()

    def q(self, funcion, resto):
        return expresiones.consulta(self.ix, expresiones.parsear(funcion, resto))[1]

    def test_siguiente_existente_ultimo(self):
        self.assertEqual(self.q("siguiente", "CuponId"), "select coalesce(max(CuponId), 0) + 1 as valor from cbhCupon")
        self.assertEqual(self.q("existente", "cuponid"), "select t.CuponId as valor from cbhCupon t order by t.CuponId limit 1")
        self.assertEqual(self.q("ultimo", "CuponId"), "select t.CuponId as valor from cbhCupon t order by t.CuponId desc limit 1")

    def test_condicion_con_nombre_del_valor_del_dominio(self):
        self.assertIn("where t.CuponEstado = 'PEN' and t.CuponId > 10",
                      self.q("existente", "CuponId|CuponEstado=PENDIENTE,CuponId>10"))
        self.assertIn("t.CuponEstado = 'pendiente'", self.q("existente", "CuponId|CuponEstado='pendiente'"))  # entre comillas: tal cual
        self.assertIn("t.CuponTipo = 'O''Brien'", self.q("existente", "CuponId|CuponTipo=O'Brien"))

    def test_numero_con_comillas_si_el_atributo_es_texto(self):
        # SQL Server convierte la columna char a int si se compara con un numero, y falla con los que no lo son.
        ix = indice.Indice()
        ix.agregar_tabla(indice.Tabla("cbhNivel", ["NivEmpr", "NivId"], None, "", "int", ["NivEmpr", "NivId", "NivOrden"],
                                      tipos={"NivEmpr": "char", "NivId": "int", "NivOrden": "numeric"}))
        q = expresiones.consulta(ix, expresiones.parsear("existente", "NivId|NivEmpr=1,NivOrden=2"))[1]
        self.assertIn("where t.NivEmpr = '1' and t.NivOrden = 2", q)

    def test_hijas_por_nivel_y_por_clave_foranea(self):
        q = self.q("con_hijos", "CuponId")
        self.assertIn("(exists (select 1 from cbhCuponDetalle h where h.CuponId = t.CuponId) or "
                      "exists (select 1 from cbhLoteDetalle h where h.CuponId = t.CuponId))", q)
        q = self.q("sin_hijos", "CuponId:cbhLoteDetalle")
        self.assertIn("where not exists (select 1 from cbhLoteDetalle h", q)
        self.assertNotIn("cbhCuponDetalle", q)

    def test_errores(self):
        for f, resto in [("siguiente", "TipoCod"), ("existente", "Nada"), ("existente", "CuponId|Otro=1"), ("existente", "CuponId|CuponEstado"),
                         ("con_hijos", "CuponId:gntTipo"), ("con_hijos", "TipoCod")]:
            with self.subTest(f=f, resto=resto), self.assertRaises(ValueError):
                self.q(f, resto)


def _indice_cuotas():
    """cbhCargoCuota <- cbhCuponDetalle -> cbhCupon, y cbhAplicacion -> cbhCargoCuota; cbhCargo arriba de la cuota."""
    ix = indice.Indice()
    ix.agregar_tabla(indice.Tabla("cbhCargo", ["CargoId"], None, "", "int", ["CargoId", "CargoEstado"]))
    ix.agregar_tabla(indice.Tabla("cbhCargoCuota", ["CargoId", "CargoCuotaNumero"], None, "", "int",
                                  ["CargoId", "CargoCuotaNumero", "CargoCuotaEstado"]))
    ix.agregar_tabla(indice.Tabla("cbhCupon", ["CuponId"], None, "", "int", ["CuponId", "CuponEstado", "CuponTipo"],
                                  {"CuponEstado": 283}))
    ix.agregar_tabla(indice.Tabla("cbhCuponDetalle", ["CuponId", "CuponDetSec"], None, "", "int",
                                  ["CuponId", "CuponDetSec", "CargoId", "CargoCuotaNumero", "CuponDetImporte"]))
    ix.agregar_tabla(indice.Tabla("cbhAplicacion", ["AplId"], None, "", "int", ["AplId", "CargoId", "CargoCuotaNumero"]))
    ix.valores[283] = [{"valor": "PRO", "nombre": "EN_PROCESO", "descripcion": "En proceso"}]
    return ix


class OtrasTablas(unittest.TestCase):
    def setUp(self):
        self.ix = _indice_cuotas()
        self.cuota = self.ix.todas["cbhcargocuota"]

    def q(self, resto, funcion="existente"):
        return expresiones.consulta(self.ix, expresiones.parsear(funcion, resto))[1]

    def test_relaciones_hacia_abajo_y_hacia_arriba(self):
        r = {o.nombre: (cols, hija) for o, cols, hija in self.ix.relaciones(self.cuota)}
        self.assertEqual(r, {"cbhCargo": (["CargoId"], False), "cbhCuponDetalle": (["CargoId", "CargoCuotaNumero"], True),
                             "cbhAplicacion": (["CargoId", "CargoCuotaNumero"], True)})

    def test_caminos_mas_cortos(self):
        cs = self.ix.caminos(self.cuota)
        self.assertEqual([[p[0].nombre for p in c] for c in cs["cbhcupon"]], [["cbhCuponDetalle", "cbhCupon"]])
        self.assertEqual(len(cs["cbhcupondetalle"][0]), 1)  # directo, aunque tambien se llega por cbhCargo

    def test_no_baja_por_un_catalogo(self):
        ix = self.ix
        ix.agregar_tabla(indice.Tabla("gntMoneda", ["MonId"], None, "", "int", ["MonId"]))
        ix.agregar_tabla(indice.Tabla("cbhIngreso", ["IngId"], None, "", "int", ["IngId", "MonId"]))
        ix.todas["cbhcupon"].atributos.append("MonId")
        ix.todas["cbhcupon"]._minus = None
        ix._relaciones.clear()
        cs = ix.caminos(ix.todas["cbhcupon"])
        self.assertIn("gntmoneda", cs)
        self.assertNotIn("cbhingreso", cs)        # misma moneda que el cupon: no
        self.assertIn("cbhcargocuota", cs)        # bajando por el detalle y subiendo: si
        self.assertIn("cbhaplicacion", ix.caminos(self.cuota))
        self.assertEqual([p[0].nombre for p in ix.camino(ix.todas["cbhcupon"], ["gntMoneda", "cbhIngreso"])],
                         ["gntMoneda", "cbhIngreso"])  # escrito a mano, vale igual

    def test_exists_por_el_camino(self):
        q = self.q("CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO")
        self.assertEqual(q, "select t.CargoCuotaNumero as valor from cbhCargoCuota t where "
                            "exists (select 1 from cbhCuponDetalle r1 where r1.CargoId = t.CargoId and r1.CargoCuotaNumero = t.CargoCuotaNumero"
                            " and exists (select 1 from cbhCupon r2 where r2.CuponId = r1.CuponId and r2.CuponEstado = 'PRO'))"
                            " order by t.CargoId, t.CargoCuotaNumero limit 1")

    def test_una_tabla_sola_va_por_el_camino_mas_corto(self):
        self.assertEqual(self.q("CargoCuotaNumero|cbhCupon.CuponEstado=EN_PROCESO"),
                         self.q("CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO"))

    def test_mismo_camino_misma_fila_y_negadas_aparte(self):
        q = self.q("CargoCuotaNumero|cbhCuponDetalle.CuponDetImporte>0,cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO,"
                   "cbhCuponDetalle.cbhCupon.CuponTipo=LIQ,!cbhAplicacion.AplId>0,cbhCargo.CargoEstado=ACT,CargoCuotaEstado=PEN")
        self.assertEqual(q.count("from cbhCuponDetalle"), 1)
        self.assertEqual(q.count("from cbhCupon "), 1)
        self.assertIn("r1.CuponDetImporte > 0 and exists (select 1 from cbhCupon r2 where r2.CuponId = r1.CuponId"
                      " and r2.CuponEstado = 'PRO' and r2.CuponTipo = 'LIQ')", q)
        self.assertIn("not exists (select 1 from cbhAplicacion r3 where r3.CargoId = t.CargoId and "
                      "r3.CargoCuotaNumero = t.CargoCuotaNumero and r3.AplId > 0)", q)
        self.assertIn("exists (select 1 from cbhCargo r4 where r4.CargoId = t.CargoId and r4.CargoEstado = 'ACT')", q)
        self.assertIn("where t.CargoCuotaEstado = 'PEN' and ", q)

    def test_solo_el_camino_y_negada_en_el_medio(self):
        q = self.q("CargoId|cbhCargoCuota.!cbhCuponDetalle,!cbhCuponDetalle")
        self.assertIn("where exists (select 1 from cbhCargoCuota r1 where r1.CargoId = t.CargoId and not exists "
                      "(select 1 from cbhCuponDetalle r2 where r2.CargoId = r1.CargoId and r2.CargoCuotaNumero = r1.CargoCuotaNumero))"
                      " and not exists (select 1 from cbhCuponDetalle r3 where r3.CargoId = t.CargoId)", q)

    def test_misma_fila(self):
        conds = "cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO,CargoCuotaEstado=PEN,CargoId>3"
        r = expresiones.misma_fila(self.ix, "${ultimo.CargoCuotaNumero|cbhcupon.CuponEstado=EN_PROCESO,CargoCuotaEstado=PEN,CargoId>3}")
        cargo = "${ultimo.cbhCargoCuota.CargoId|" + conds + "}"  # el camino corto queda escrito entero
        self.assertEqual(r, {"CargoId": cargo, "CargoCuotaNumero": "${ultimo.CargoCuotaNumero|CargoId=" + cargo + "," + conds + "}"})
        for e in r.values():  # lo que escribe se vuelve a leer y arma la consulta
            m = expresiones._VARIABLE.match(e)
            t, q = expresiones.consulta(self.ix, expresiones.parsear(m[1], m[2].replace("=" + cargo, "=7")))
            self.assertEqual(t.nombre, "cbhCargoCuota")  # todas las partes, de la misma tabla
        _, q = expresiones.consulta(self.ix, expresiones.parsear("ultimo", cargo[len("${ultimo."):-1]))
        self.assertTrue(q.startswith("select t.CargoId as valor from cbhCargoCuota t where t.CargoCuotaEstado = 'PEN'"))
        hijas = ",".join(f"!{h.nombre}" for h in self.ix.hijas(self.cuota))  # sin filas en ninguna
        self.assertEqual(expresiones.misma_fila(self.ix, "${sin_hijos.CargoCuotaNumero}")["CargoId"],
                         "${existente.cbhCargoCuota.CargoId|" + hijas + "}")
        self.assertEqual(expresiones.misma_fila(self.ix, "${existente.CargoCuotaNumero}")["CargoId"],
                         "${existente.cbhCargoCuota.CargoId}")
        for e in ("${siguiente.CargoCuotaNumero}", "${con_hijos.CargoCuotaNumero}", "${existente.cbhCargoCuota.CargoId}", "hola"):
            with self.subTest(e=e), self.assertRaises(ValueError):
                expresiones.misma_fila(self.ix, e)

    def test_relacionados_de_la_tabla_de_la_condicion(self):
        texto = "${existente.CargoCuotaNumero|cbhCupon.CuponEstado=EN_PROCESO,cbhCuponDetalle.CuponDetImporte>0,CargoCuotaEstado=PEN}"
        vs = expresiones.misma_fila(self.ix, texto)
        r = expresiones.relacionados(self.ix, texto, vs, ["CuponId", "CargoId", "CuponDetImporte", "Otro"])
        self.assertEqual(list(r), ["CuponId"])  # ni la clave propia ni los que no son claves
        self.assertEqual(r["CuponId"], {"tabla": "cbhCuponDetalle", "expresion":
            "${existente.cbhCuponDetalle.CuponId|CargoId=" + vs["CargoId"] + ",CargoCuotaNumero=" + vs["CargoCuotaNumero"]
            + ",cbhCupon.CuponEstado=EN_PROCESO,CuponDetImporte>0}"})
        m = expresiones._VARIABLE.match(r["CuponId"]["expresion"])  # se vuelve a leer y arma la consulta
        _, q = expresiones.consulta(self.ix, expresiones.parsear(m[1], m[2].replace(vs["CargoCuotaNumero"], "2").replace(vs["CargoId"], "7")))
        self.assertEqual(q, "select t.CuponId as valor from cbhCuponDetalle t where t.CargoId = 7 and t.CargoCuotaNumero = 2 "
                            "and t.CuponDetImporte > 0 and exists (select 1 from cbhCupon r1 where r1.CuponId = t.CuponId and "
                            "r1.CuponEstado = 'PRO') order by t.CuponId, t.CuponDetSec limit 1")

    def test_relacionados_sin_misma_fila_y_casos_sin(self):
        texto = "${ultimo.CargoCuotaNumero|CargoId=5,cbhCuponDetalle}"
        self.assertEqual(expresiones.relacionados(self.ix, texto, {}, ["CuponId"])["CuponId"]["expresion"],
                         "${ultimo.cbhCuponDetalle.CuponId|CargoId=5,CargoCuotaNumero=" + texto + "}")
        self.assertEqual(expresiones.relacionados(self.ix, "${con_hijos.CargoCuotaNumero:cbhCuponDetalle|CargoId=5}", {}, ["CuponId"])
                         ["CuponId"]["expresion"], "${existente.cbhCuponDetalle.CuponId|CargoId=5,CargoCuotaNumero="
                                                   "${con_hijos.CargoCuotaNumero:cbhCuponDetalle|CargoId=5}}")
        for e in ("${existente.CargoCuotaNumero|CargoId=5,!cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}",  # en ningun cupon
                  "${existente.CargoCuotaNumero|cbhCuponDetalle}",  # sin CargoId: no se sabe de que fila
                  "${siguiente.CargoCuotaNumero}", "hola"):
            with self.subTest(e=e):
                self.assertEqual(expresiones.relacionados(self.ix, e, {}, ["CuponId"]), {})

    def test_relacionados_por_un_camino_mas_largo(self):
        # Desde el cupon: el CargoId de la cuota del detalle, volviendo por el detalle hasta el cupon.
        ix = self.ix
        r = expresiones.relacionados(ix, "${existente.CuponId|cbhCuponDetalle.cbhCargoCuota.CargoCuotaEstado=PEN}", {}, ["CargoCuotaNumero"])
        e = "${existente.CuponId|cbhCuponDetalle.cbhCargoCuota.CargoCuotaEstado=PEN}"
        self.assertEqual(r["CargoCuotaNumero"], {"tabla": "cbhCuponDetalle", "expresion":
                         "${existente.cbhCuponDetalle.CargoCuotaNumero|CuponId=" + e + ",cbhCargoCuota.CargoCuotaEstado=PEN}"})
        ix.agregar_tabla(indice.Tabla("cbhCliente", ["CliId"], None, "", "int", ["CliId"]))
        ix.todas["cbhcargo"].atributos.append("CliId")
        ix.todas["cbhcargo"]._minus = None
        ix._relaciones.clear()
        r = expresiones.relacionados(ix, "${existente.CargoCuotaNumero|CargoId=5,cbhCargo.CargoEstado=ACT}", {}, ["CliId"])
        self.assertEqual(r["CliId"]["expresion"], "${existente.cbhCargo.CliId|cbhCargoCuota.CargoId=5,cbhCargoCuota.CargoCuotaNumero="
                         "${existente.CargoCuotaNumero|CargoId=5,cbhCargo.CargoEstado=ACT},CargoEstado=ACT}")
        m = expresiones._VARIABLE.match(r["CliId"]["expresion"].replace("${existente.CargoCuotaNumero|CargoId=5,cbhCargo.CargoEstado=ACT}", "2"))
        _, q = expresiones.consulta(ix, expresiones.parsear(m[1], m[2]))
        self.assertIn("exists (select 1 from cbhCargoCuota r1 where r1.CargoId = t.CargoId and r1.CargoId = 5 and r1.CargoCuotaNumero = 2)", q)

    def test_atributo_de_una_tabla(self):
        p = expresiones.parsear("existente", "cbhCargoCuota.CargoCuotaEstado|CargoId=3")
        self.assertEqual((p.tabla, p.atributo), ("cbhCargoCuota", "CargoCuotaEstado"))
        _, q = expresiones.consulta(self.ix, p)
        self.assertEqual(q, "select t.CargoCuotaEstado as valor from cbhCargoCuota t where t.CargoCuotaEstado is not null and t.CargoId = 3 "
                            "order by t.CargoId, t.CargoCuotaNumero limit 1")
        for resto in ("cbhNada.CargoId", "cbhCargoCuota.Nada", "x-y.CargoId"):
            with self.subTest(resto=resto), self.assertRaises(ValueError):
                expresiones.consulta(self.ix, expresiones.parsear("existente", resto))
        with self.assertRaises(ValueError):
            expresiones.parsear("siguiente", "cbhCargoCuota.CargoCuotaNumero")

    def test_invertir_toma_el_otro_extremo(self):
        q = lambda f, inv: expresiones.consulta(self.ix, expresiones.parsear(f, "CargoCuotaNumero|cbhCuponDetalle"), inv)[1]
        self.assertTrue(q("existente", True).endswith("order by t.CargoId desc, t.CargoCuotaNumero desc limit 1"))
        self.assertTrue(q("ultimo", True).endswith("order by t.CargoId, t.CargoCuotaNumero limit 1"))
        self.assertEqual(expresiones.consulta(self.ix, expresiones.parsear("siguiente", "CargoCuotaNumero"), True),
                         expresiones.consulta(self.ix, expresiones.parsear("siguiente", "CargoCuotaNumero")))

    def test_errores(self):
        ix = self.ix
        ix.agregar_tabla(indice.Tabla("cbhLote", ["LoteId"], None, "", "int", ["LoteId", "CuponId", "CargoId", "CargoCuotaNumero"]))
        ix._relaciones.clear()
        for resto, msg in [("CargoCuotaNumero|cbhCuponDetalle.cbhCupon.Nada=1", "Nada no es un atributo de cbhCupon"),
                           ("CargoCuotaNumero|cbhCargo.cbhCupon.CuponEstado=1", "cbhCupon no esta relacionada con cbhCargo"),
                           ("CargoCuotaNumero|gntOtra.X=1", "no es una tabla de la KB"),
                           ("CargoCuotaNumero|cbhCupon.CuponEstado=1", "mas de un camino")]:
            with self.subTest(resto=resto), self.assertRaises(ValueError) as c:
                self.q(resto)
            self.assertIn(msg, str(c.exception))


class Resolver(unittest.TestCase):
    def test_valor_con_el_tipo_de_la_clave(self):
        ix = _indice()
        with mock.patch.object(expresiones.indice, "de_kb", return_value=ix), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": [{"valor": "60"}]})):
            self.assertEqual(expresiones.resolver(None, "siguiente", "CuponId"), 60)
        with mock.patch.object(expresiones.indice, "de_kb", return_value=ix), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": [{"valor": "0012 "}]})):
            self.assertEqual(expresiones.resolver(None, "existente", "TipoCod"), "0012")  # un char sigue siendo texto

    def test_sin_filas_dice_que_no_hay(self):
        with mock.patch.object(expresiones.indice, "de_kb", return_value=_indice()), \
                mock.patch.object(expresiones.motor, "ejecutar_sql", return_value=({"ok": True}, {"filas": []})):
            with self.assertRaises(ValueError) as c:
                expresiones.resolver(None, "existente", "CuponId|CuponEstado=EN_PROCESO")
        self.assertIn("no hay ningun CuponId en cbhCupon que cumpla CuponEstado = EN_PROCESO", str(c.exception))


class Filtros(unittest.TestCase):
    def test_atributos_para_el_armador(self):
        ix = _indice()
        ix.dominios[283] = "Cobranzas.CuponEstado"
        with mock.patch.object(campos.indice, "de_kb", return_value=ix):
            f = campos.filtros(None, "CuponDetSec")
        self.assertEqual((f["tabla"], f["hijas"]), ("cbhCuponDetalle", []))
        self.assertEqual([(a["nombre"], a["clave"], a["tablaDe"]) for a in f["atributos"]],
                         [("CuponDetSec", False, "cbhCuponDetalle"), ("CuponId", True, "cbhCupon"), ("Importe", False, None)])
        with mock.patch.object(campos.indice, "de_kb", return_value=ix):
            f = campos.filtros(None, "CuponId")
        self.assertEqual(f["hijas"], ["cbhCuponDetalle", "cbhLoteDetalle"])
        estado = next(a for a in f["atributos"] if a["nombre"] == "CuponEstado")
        self.assertEqual((estado["dominio"], [v["nombre"] for v in estado["valores"]]),
                         ("Cobranzas.CuponEstado", ["EN_PROCESO", "PENDIENTE"]))
        self.assertEqual([a["nombre"] for a in f["atributos"]], ["CuponId", "CuponEstado", "CuponTipo"])  # el enumerado antes

    def test_no_es_clave(self):
        with mock.patch.object(campos.indice, "de_kb", return_value=_indice()), self.assertRaises(KeyError):
            campos.filtros(mock.Mock(nombre="X"), "Importe")


class Fechas(unittest.TestCase):
    AHORA = dt.datetime(2026, 1, 31, 10, 30, 0)  # sabado

    def f(self, e):
        return fechas.calcular(e, self.AHORA)

    def test_relativas(self):
        casos = {"hoy": "2026-01-31", "hoy+1": "2026-02-01", "hoy-31d": "2025-12-31", "hoy+1m": "2026-02-28",
                 "hoy-1a": "2025-01-31", "inicio_mes": "2026-01-01", "fin_mes": "2026-01-31", "fin_mes+1": "2026-02-28",
                 "inicio_mes-1": "2025-12-01", "inicio_anio": "2026-01-01", "fin_anio-1": "2025-12-31",
                 "habil_siguiente": "2026-02-02", "habil_anterior": "2026-01-30", "fecha_vacia": "",
                 "ahora+2h": "2026-01-31T12:30:00", "ahora-30min": "2026-01-31T10:00:00", "ahora+1d": "2026-02-01T10:30:00"}
        for e, esperado in casos.items():
            with self.subTest(e=e):
                self.assertEqual(self.f(e), esperado)

    def test_no_es_fecha_o_unidad_invalida(self):
        self.assertIsNone(self.f("cupon"))
        self.assertIsNone(self.f("hoy.x"))
        for e in ("hoy+2h", "fin_mes+1a", "ahora+1m"):
            with self.subTest(e=e), self.assertRaises(ValueError):
                self.f(e)


if __name__ == "__main__":
    unittest.main()
