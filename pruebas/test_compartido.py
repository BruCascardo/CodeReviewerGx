"""Base compartida sin servidor: formato del contenido, .env y el almacen de suites contra un compartido falso."""
import os
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from gxp import compartido
from gxp.compartido import conexion
from gxp.suites import almacen


class Formato(unittest.TestCase):
    def test_ida_y_vuelta(self):
        datos = {"nombre": "Suite ñandú", "casos": [{"id": "a", "pasos": []}] * 50}
        self.assertEqual(compartido.desempaquetar(compartido.empaquetar(datos)), datos)

    def test_es_el_formato_de_compress_de_mysql(self):
        # UNCOMPRESS(): 4 bytes con el largo original (little endian) y despues zlib.
        blob = compartido.empaquetar({"a": 1})
        original = zlib.decompress(blob[4:])
        self.assertEqual(int.from_bytes(blob[:4], "little"), len(original))


class Env(unittest.TestCase):
    def test_no_pisa_las_variables_definidas(self):
        with tempfile.TemporaryDirectory() as d:
            env = Path(d) / ".env"
            env.write_text('# comentario\nGXP_PRUEBA_A = "con comillas"\nGXP_PRUEBA_B=archivo\n\nsin igual\n', encoding="utf-8")
            with mock.patch.object(conexion, "ENV", env), mock.patch.dict(os.environ, {"GXP_PRUEBA_B": "entorno"}):
                conexion.cargar_env()
                self.assertEqual(os.environ["GXP_PRUEBA_A"], "con comillas")
                self.assertEqual(os.environ["GXP_PRUEBA_B"], "entorno")
            os.environ.pop("GXP_PRUEBA_A", None)

    def test_sin_host_no_esta_activo(self):
        with mock.patch.dict(os.environ, {"GXP_DB_HOST": ""}):
            self.assertFalse(compartido.activo())


class Falso:
    """compartido en memoria, con el control de version de grabar()."""

    def __init__(self):
        self.docs = {}

    def leer(self, tipo, clave):
        d = self.docs.get((tipo, clave.lower()))
        if d is None:
            raise KeyError(clave)
        return {"clave": d["clave"], "datos": d["datos"], "version": d["version"], "actualizado": "", "por": "yo"}

    def grabar(self, tipo, clave, datos, kb="", resumen=None, version=None):
        d = self.docs.get((tipo, clave.lower()))
        if d and version is not None and version != d["version"]:
            raise compartido.Conflicto("cambio")
        nueva = (d["version"] if d else 0) + 1
        self.docs[(tipo, clave.lower())] = {"clave": d["clave"] if d else clave, "datos": datos, "version": nueva,
                                            "kb": kb, "resumen": resumen}
        return nueva

    def borrar(self, tipo, clave):
        self.docs.pop((tipo, clave.lower()))

    def listar(self, tipo, borrados=False):
        return [{"clave": d["clave"], "kb": d["kb"], "resumen": d["resumen"], "version": d["version"], "actualizado": "", "por": "yo"}
                for (t, _), d in sorted(self.docs.items()) if t == tipo]


class AlmacenCompartido(unittest.TestCase):
    def setUp(self):
        self.falso = Falso()
        parches = [mock.patch.object(almacen.compartido, n, getattr(self.falso, n)) for n in ("leer", "grabar", "borrar", "listar")]
        parches += [mock.patch.object(almacen.compartido, "activo", lambda: True), mock.patch.object(almacen, "estado", dict)]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)

    def test_guardar_cargar_y_listar(self):
        sid = almacen.guardar_nueva({"nombre": "Registro", "kb": "Generales", "casos": [{"nombre": "uno", "objeto": "X"}]})
        self.assertEqual(sid, "Generales/registro")
        s = almacen.cargar("Generales\\registro.json")
        self.assertEqual((s["_id"], s["_version"], s["casos"][0]["pasos"]), ("Generales/registro", 1, [{"objeto": "X"}]))
        self.assertEqual([x["id"] for x in almacen.listar("generales")], ["Generales/registro"])
        self.assertEqual(almacen.listar("Generales")[0]["casos"], 1)
        self.assertEqual(almacen.ids_de("Generales", "reg"), ["Generales/registro"])

    def test_conflicto_si_otro_grabo_en_el_medio(self):
        almacen.guardar("Generales/a", {"nombre": "A", "kb": "Generales"})
        mia, otra = almacen.cargar("Generales/a"), almacen.cargar("Generales/a")
        almacen.guardar(otra["_id"], otra)
        self.assertEqual(otra["_version"], 2)
        with self.assertRaises(compartido.Conflicto):
            almacen.guardar(mia["_id"], mia)

    def test_no_sale_de_la_carpeta_de_suites(self):
        with self.assertRaises(ValueError):
            almacen.cargar("../config")


if __name__ == "__main__":
    unittest.main()
