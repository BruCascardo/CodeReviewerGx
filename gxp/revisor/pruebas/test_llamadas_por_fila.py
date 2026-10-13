import unittest

from gxp.revisor.pruebas import do, fin_sub, leer, linea, llamar, metodo, sub
from gxp.revisor.reglas import cargar


def evento(n, grilla="Grid"):
    """Event Grid.Load (o Event Load si grilla es None)."""
    if grilla is None:
        return linea(n, 146, "t('Load',3,0,0)")
    return linea(n, 146, f"t([ t('{grilla}',3,0,0),t('Load',3,0,0) ],29,0,0)")


def fin_evento(n):
    return linea(n, 147)


def cargar_fila(n, grilla="Grid"):
    """Grid.Load()"""
    return linea(n, 107, f"t([ t('{grilla}',3,0,0),t('load(',1,0,0) ],31,0,0)", "t(')',4,0,0)")


def para_cada(n):
    return linea(n, 121)


def fin_para(n):
    return linea(n, 128)


class Ctx:
    kb_nombre = "Prueba"

    def __init__(self, con_tabla=None, grilla=True):
        self.con_tabla = con_tabla
        self.grilla = grilla

    def loads_con_tabla(self, objeto):
        return self.con_tabla

    def tiene_grilla(self, objeto):
        return self.grilla


def revisar(fu, ctx, conf=None):
    regla = cargar()["llamadas-por-fila"](conf)
    if not regla.aplica(fu, ctx):
        return []
    return list(regla.revisar(fu, ctx))


def web(lineas):
    return leer("X.W", "\n".join(lineas), tipo="web")


class LlamadasPorFila(unittest.TestCase):
    def test_grilla_con_tabla_base(self):
        fu = web([evento(10), llamar(11, "Generales\\Personas\\Get"), fin_evento(12)])
        hs = revisar(fu, Ctx({"grid.load"}))
        self.assertEqual([h.linea for h in hs], [11])
        self.assertIn("Llama a Generales.Personas.Get por cada fila de la grilla Grid", hs[0].mensaje)
        self.assertEqual(hs[0].severidad, "advertencia")

    def test_load_que_corre_una_vez(self):
        fu = web([evento(10), llamar(11, "Generales\\Personas\\Get"), fin_evento(12)])
        self.assertEqual(revisar(fu, Ctx(set())), [])

    def test_grilla_sin_tabla_base_marca_solo_el_bucle(self):
        fu = web([evento(10, "Fs"), llamar(11, "X\\Antes"), para_cada(12), llamar(13, "X\\Adentro"), cargar_fila(14, "Fs"),
                  fin_para(15), fin_evento(16)])
        hs = revisar(fu, Ctx(set()))
        self.assertEqual([h.linea for h in hs], [13])
        self.assertEqual(hs[0].datos["porBucle"], 12)

    def test_bucle_que_no_carga_la_grilla(self):
        fu = web([evento(10, "Fs"), para_cada(11), llamar(12, "X\\Adentro"), fin_para(13), fin_evento(14)])
        self.assertEqual(revisar(fu, Ctx(set())), [])

    def test_sigue_los_do(self):
        fu = web([evento(10), do(11, "CARGAR"), fin_evento(12),
                  sub(20, "CARGAR"), llamar(21, "X\\Info"), fin_sub(22)])
        hs = revisar(fu, Ctx({"grid.load"}))
        self.assertEqual([h.linea for h in hs], [21])
        self.assertIn("por Do 'cargar' de la linea 11", hs[0].mensaje)

    def test_for_each_y_carga_de_bc(self):
        fu = web([evento(10), para_cada(11), fin_para(12), metodo(13, "Persona", "Load", "t('Perid',23,0,0)"),
                  fin_evento(14)])
        hs = revisar(fu, Ctx({"grid.load"}))
        self.assertEqual([(h.linea, h.datos["acceso"]) for h in hs], [(11, "foreach"), (13, "bc")])
        self.assertIn("Carga el Business Component &Persona", hs[1].mensaje)

    def test_load_sin_grilla(self):
        fu = web([evento(10, None), llamar(11, "X\\Get"), fin_evento(12)])
        self.assertEqual(revisar(fu, Ctx({"load"}, grilla=False)), [])
        self.assertEqual(len(revisar(fu, Ctx({"load"}, grilla=True))), 1)

    def test_sin_navegacion_y_sin_bucle_se_toma_con_tabla(self):
        fu = web([evento(10), llamar(11, "X\\Get"), fin_evento(12)])
        self.assertEqual(len(revisar(fu, Ctx(None))), 1)

    def test_permitidos(self):
        fu = web([evento(10), llamar(11, "Sistema\\Global\\prcLog"), fin_evento(12)])
        self.assertEqual(revisar(fu, Ctx({"grid.load"}), conf={"permitidos": ["prcLog"]}), [])

    def test_solo_web_panels(self):
        fu = leer("X.P", "\n".join([evento(10), llamar(11, "X\\Get"), fin_evento(12)]))
        self.assertEqual(revisar(fu, Ctx({"grid.load"})), [])


if __name__ == "__main__":
    unittest.main()
