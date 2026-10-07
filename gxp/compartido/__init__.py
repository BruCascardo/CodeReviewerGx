"""Base compartida: las suites y la configuracion del equipo (config general y revisor) en una base MySQL que
leen y graban todos los desarrolladores. Se activa con GXP_DB_HOST (ver conexion.py); sin eso, GxPruebas
trabaja con los archivos locales como siempre.

Cada documento (tipo, clave) guarda su JSON comprimido en el formato de COMPRESS() de MySQL (se lee con
SELECT UNCOMPRESS(contenido)), una version que sube en cada grabacion, y quien y cuando lo cambio. Al grabar,
la version anterior pasa a gxp_historial (quedan las ultimas HISTORIAL por documento). Borrar solo marca el
documento: se recupera con restaurar().

Grabar con la version que se leyo (version=) falla con Conflicto si otro lo cambio en el medio, en lugar de
pisar su cambio.

Lo que se lee queda copiado en .cache/compartido/: un documento se vuelve a bajar solo si cambio su version,
y si la base no responde se usa esa copia (con un aviso). Sin conexion no se puede grabar.

  conexion.py   variables de entorno y .env, conexion por hilo, creacion de las tablas
"""
import datetime as dt
import json
import re
import struct
import sys
import zlib

from . import conexion
from .conexion import RAIZ, SinConexion, descripcion, inicializar, parametros, usuario
from ..util import escribir_json, leer_json

SUITE = "suite"
CONFIG = "config"  # claves: "general" (lo compartido de config.json) y "revisor" (revisor.json)
HISTORIAL = 20

NO_INICIALIZADA = "la base compartida no tiene las tablas de GxPruebas: corre 'python gxpruebas.py compartido inicializar'"


class Conflicto(ValueError):
    """Otro desarrollador grabo el documento despues de que se leyo."""


class SinPermiso(Exception):
    """El usuario de la base no puede leer o grabar las tablas de GxPruebas."""


def activo():
    return parametros() is not None


# ---------------------------------------------------------------------------------------------- formato

def empaquetar(datos) -> bytes:
    b = json.dumps(datos, ensure_ascii=False).encode("utf-8")
    return struct.pack("<I", len(b) & 0x3FFFFFFF) + zlib.compress(b, 6)


def desempaquetar(blob):
    return json.loads(zlib.decompress(bytes(blob)[4:]).decode("utf-8"))


def _fecha(v):
    return v.isoformat(sep=" ", timespec="seconds") if isinstance(v, dt.datetime) else (v or None)


# ------------------------------------------------------------------------------------------ copia local

def _dir_cache():
    p = parametros() or {}
    nombre = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{p.get('host')}_{p.get('port')}_{p.get('database')}")
    return RAIZ / ".cache" / "compartido" / nombre


def _archivo_cache(tipo, clave):
    partes = [re.sub(r'[<>:"|?*\\]', "_", x) for x in clave.lower().split("/") if x not in ("", ".", "..")]
    return _dir_cache().joinpath(tipo, *partes).with_suffix(".json")


def _leer_cache(tipo, clave):
    d = leer_json(_archivo_cache(tipo, clave))
    return d if isinstance(d, dict) and "datos" in d else None


_avisos = set()
_ultimo = {"error": None}  # el error de la ultima operacion contra la base (None si anduvo)


def _avisar(e):
    """Avisa una sola vez por proceso que se esta usando la copia local."""
    msg = f"Aviso: sin conexion con la base compartida ({e}). Se usa la copia local; no se puede grabar hasta que vuelva."
    if msg not in _avisos:
        _avisos.add(msg)
        print(msg, file=sys.stderr, flush=True)


def avisos():
    return sorted(_avisos)


def ultimo_error():
    """Por que fallo la ultima operacion contra la base, o None si anduvo (para la interfaz)."""
    return _ultimo["error"]


# ------------------------------------------------------------------------------------------- consultas

def _con_cursor(fn, escribir=False):
    """Corre fn(cursor) con la conexion del hilo. Si escribe, en una transaccion. Traduce los errores del
    driver a SinConexion (red, base o tablas que no existen), SinPermiso y Conflicto (clave duplicada)."""
    try:
        c = conexion.conexion()
    except SinConexion as e:
        _ultimo["error"] = str(e)
        raise
    err = conexion._driver().err
    try:
        if escribir:
            c.begin()
        with c.cursor() as cur:
            r = fn(cur)
        if escribir:
            c.commit()
        _ultimo["error"] = None
        return r
    except BaseException as e:
        if escribir:
            try:
                c.rollback()
            except Exception:
                pass
        codigo = e.args[0] if isinstance(e, err.MySQLError) and e.args else None
        if codigo in (1044, 1045, 1142, 1143):
            raise SinPermiso(f"el usuario de la base compartida no tiene permiso: {e.args[-1]}")
        if codigo in (1146, 1049):
            raise SinConexion(NO_INICIALIZADA)
        if codigo == 1062:
            raise Conflicto("otro desarrollador lo grabo al mismo tiempo: volve a intentar")
        if isinstance(e, (err.OperationalError, err.InterfaceError, OSError)):
            conexion.descartar()
            _ultimo["error"] = f"{descripcion()}: {e}"
            raise SinConexion(_ultimo["error"])
        raise


def leer(tipo, clave):
    """{'clave', 'datos', 'version', 'actualizado', 'por'}. KeyError si no existe o esta borrado. Si la copia
    local tiene la misma version, no se baja el contenido; sin conexion, devuelve la copia local."""
    previo = _leer_cache(tipo, clave)

    def fn(cur):
        cur.execute("SELECT clave, version, actualizado, actualizado_por, borrado,"
                    " CASE WHEN version = %s THEN NULL ELSE contenido END"
                    " FROM gxp_documentos WHERE tipo = %s AND clave = %s",
                    ((previo or {}).get("version", -1), tipo, clave))
        return cur.fetchone()

    try:
        fila = _con_cursor(fn)
    except SinConexion as e:
        if previo is None:
            raise
        _avisar(e)
        return previo
    if fila is None or fila[4] is not None:
        _archivo_cache(tipo, clave).unlink(missing_ok=True)
        raise KeyError(f"No existe {'la suite' if tipo == SUITE else tipo} {clave}")
    if fila[5] is None and previo is not None:
        return previo
    doc = {"clave": fila[0], "version": fila[1], "actualizado": _fecha(fila[2]), "por": fila[3],
           "datos": desempaquetar(fila[5])}
    escribir_json(_archivo_cache(tipo, clave), doc)
    return doc


def listar(tipo, borrados=False):
    """[{'clave', 'kb', 'resumen', 'version', 'actualizado', 'por'(, 'borrado')}] sin el contenido. Sin
    conexion, la ultima lista que se pudo leer."""
    copia = _dir_cache() / f"{tipo}{'.borrados' if borrados else ''}.lista.json"

    def fn(cur):
        cur.execute("SELECT clave, kb, resumen, version, actualizado, actualizado_por, borrado FROM gxp_documentos"
                    f" WHERE tipo = %s AND borrado IS {'NOT ' if borrados else ''}NULL ORDER BY clave", (tipo,))
        return cur.fetchall()

    try:
        filas = _con_cursor(fn)
    except SinConexion as e:
        previa = leer_json(copia)
        if previa is None:
            raise
        _avisar(e)
        return previa
    salida = []
    for clave, kb, resumen, version, actualizado, por, borrado in filas:
        try:
            resumen = json.loads(resumen) if resumen else None
        except ValueError:
            resumen = None
        d = {"clave": clave, "kb": kb, "resumen": resumen, "version": version, "actualizado": _fecha(actualizado), "por": por}
        if borrados:
            d["borrado"] = _fecha(borrado)
        salida.append(d)
    escribir_json(copia, salida)
    return salida


def grabar(tipo, clave, datos, kb="", resumen=None, version=None):
    """Graba el documento y devuelve su nueva version. Con 'version' (la que se leyo), falla con Conflicto si
    en la base hay otra: alguien lo cambio despues de que se leyo."""
    contenido = empaquetar(datos)
    ahora = dt.datetime.now().replace(microsecond=0)
    por = usuario()
    resumen_txt = json.dumps(resumen, ensure_ascii=False) if resumen is not None else None

    def fn(cur):
        cur.execute("SELECT clave, version, contenido, actualizado, actualizado_por, borrado FROM gxp_documentos"
                    " WHERE tipo = %s AND clave = %s FOR UPDATE", (tipo, clave))
        fila = cur.fetchone()
        if fila is None:
            cur.execute("INSERT INTO gxp_documentos (tipo, clave, kb, resumen, contenido, version, actualizado, actualizado_por)"
                        " VALUES (%s, %s, %s, %s, %s, 1, %s, %s)", (tipo, clave, kb or "", resumen_txt, contenido, ahora, por))
            return clave, 1
        guardada, actual, previo, cuando, quien, borrado = fila
        if version is not None and borrado is None and int(version) != actual:
            raise Conflicto(f"{clave} cambio desde que la abriste (version {actual}, de {quien or 'otro'} el {_fecha(cuando)}): "
                            "volve a abrirla y repeti el cambio")
        cur.execute("INSERT INTO gxp_historial (tipo, clave, version, contenido, actualizado, actualizado_por, borrado, reemplazado)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (tipo, guardada, actual, previo, cuando, quien, borrado, ahora))
        cur.execute("UPDATE gxp_documentos SET kb = %s, resumen = %s, contenido = %s, version = %s, actualizado = %s,"
                    " actualizado_por = %s, borrado = NULL WHERE tipo = %s AND clave = %s",
                    (kb or "", resumen_txt, contenido, actual + 1, ahora, por, tipo, clave))
        cur.execute("DELETE FROM gxp_historial WHERE tipo = %s AND clave = %s AND version <= %s",
                    (tipo, clave, actual - HISTORIAL))
        return guardada, actual + 1

    guardada, nueva = _con_cursor(fn, escribir=True)
    escribir_json(_archivo_cache(tipo, clave), {"clave": guardada, "version": nueva, "actualizado": _fecha(ahora),
                                                "por": por, "datos": datos})
    return nueva


def borrar(tipo, clave):
    """Marca el documento como borrado (sigue en la base: restaurar() lo recupera). KeyError si no existe."""
    ahora = dt.datetime.now().replace(microsecond=0)

    def fn(cur):
        return cur.execute("UPDATE gxp_documentos SET borrado = %s, actualizado_por = %s"
                           " WHERE tipo = %s AND clave = %s AND borrado IS NULL", (ahora, usuario(), tipo, clave))

    if not _con_cursor(fn, escribir=True):
        raise KeyError(f"No existe {clave}")
    _archivo_cache(tipo, clave).unlink(missing_ok=True)


def historial(tipo, clave):
    """Las versiones del documento, de la mas nueva a la mas vieja: [{'version', 'actualizado', 'por',
    'borrado', 'actual'}]."""
    def fn(cur):
        cur.execute("SELECT version, actualizado, actualizado_por, borrado, 1 FROM gxp_documentos WHERE tipo = %s AND clave = %s"
                    " UNION ALL SELECT version, actualizado, actualizado_por, borrado, 0 FROM gxp_historial"
                    " WHERE tipo = %s AND clave = %s ORDER BY 1 DESC, 5 DESC", (tipo, clave, tipo, clave))
        return cur.fetchall()

    return [{"version": v, "actualizado": _fecha(a), "por": p, "borrado": _fecha(b), "actual": bool(act)}
            for v, a, p, b, act in _con_cursor(fn)]


def restaurar(tipo, clave, version=None):
    """Sin version, recupera el documento borrado. Con version, graba esa version anterior como una nueva.
    Devuelve la version vigente. KeyError si no esta."""
    if version is None:
        def fn(cur):
            return cur.execute("UPDATE gxp_documentos SET borrado = NULL, actualizado_por = %s"
                               " WHERE tipo = %s AND clave = %s AND borrado IS NOT NULL", (usuario(), tipo, clave))
        if not _con_cursor(fn, escribir=True):
            raise KeyError(f"{clave} no esta borrada")
        return leer(tipo, clave)["version"]

    def fn_leer(cur):
        cur.execute("SELECT contenido FROM gxp_historial WHERE tipo = %s AND clave = %s AND version = %s"
                    " ORDER BY id DESC LIMIT 1", (tipo, clave, int(version)))
        return cur.fetchone()

    fila = _con_cursor(fn_leer)
    if fila is None:
        raise KeyError(f"No esta la version {version} de {clave} en el historial")
    actual = listar_uno(tipo, clave)
    return grabar(tipo, clave, desempaquetar(fila[0]), kb=(actual or {}).get("kb", ""),
                  resumen=(actual or {}).get("resumen"))


def listar_uno(tipo, clave):
    """La fila (sin contenido) de un documento, este borrado o no, o None."""
    def fn(cur):
        cur.execute("SELECT clave, kb, resumen, version, borrado FROM gxp_documentos WHERE tipo = %s AND clave = %s", (tipo, clave))
        return cur.fetchone()

    f = _con_cursor(fn)
    if not f:
        return None
    return {"clave": f[0], "kb": f[1], "resumen": json.loads(f[2]) if f[2] else None, "version": f[3], "borrado": _fecha(f[4])}


def estado():
    """Para 'compartido estado' y la interfaz: si esta configurada, si responde y cuantos documentos hay."""
    if not activo():
        return {"activo": False}
    r = {"activo": True, "base": descripcion(), "usuario": usuario()}

    def fn(cur):
        cur.execute("SELECT VERSION()")
        servidor = cur.fetchone()[0]
        cur.execute("SELECT tipo, SUM(borrado IS NULL), SUM(borrado IS NOT NULL), MAX(actualizado) FROM gxp_documentos GROUP BY tipo")
        return servidor, cur.fetchall()

    try:
        servidor, filas = _con_cursor(fn)
    except (SinConexion, SinPermiso) as e:
        r.update(conectado=False, error=str(e))
        return r
    r.update(conectado=True, servidor=servidor,
             documentos={t: {"vigentes": int(v or 0), "borrados": int(b or 0), "ultimoCambio": _fecha(u)} for t, v, b, u in filas})
    return r
