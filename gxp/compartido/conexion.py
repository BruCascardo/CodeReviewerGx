"""Conexion a la base compartida (MySQL). Los datos salen de las variables de entorno GXP_DB_* o, si no
estan definidas, del archivo .env de la carpeta de GxPruebas (que no va al repositorio).

  GXP_DB_HOST      servidor; si no esta, GxPruebas trabaja con los archivos locales
  GXP_DB_PORT      puerto (3306)
  GXP_DB_USER      usuario
  GXP_DB_PASSWORD  contrasena
  GXP_DB_NAME      base (gxpruebas)
  GXP_DB_SSL       "no" para no cifrar; por defecto cifra si el servidor lo permite
  GXP_DB_SSL_CA    certificado de la CA (PEM): con esto ademas se verifica el servidor
  GXP_USUARIO      nombre que queda en cada cambio (por defecto, el usuario de Windows)
"""
import os
import sys
import threading
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
ENV = RAIZ / ".env"

# Segundos que se espera la conexion, y que se deja de intentar despues de una falla (para no esperar el
# timeout en cada lectura mientras no hay red).
TIMEOUT_SEG = 8
PAUSA_TRAS_FALLA_SEG = 30

DDL = (
    """CREATE TABLE IF NOT EXISTS gxp_documentos (
        tipo            VARCHAR(20)  NOT NULL,
        clave           VARCHAR(190) NOT NULL,
        kb              VARCHAR(100) NOT NULL DEFAULT '',
        resumen         TEXT         NULL,
        contenido       LONGBLOB     NOT NULL,
        version         INT          NOT NULL,
        actualizado     DATETIME     NOT NULL,
        actualizado_por VARCHAR(100) NOT NULL DEFAULT '',
        borrado         DATETIME     NULL,
        PRIMARY KEY (tipo, clave)
    ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
    """CREATE TABLE IF NOT EXISTS gxp_historial (
        id              BIGINT       NOT NULL AUTO_INCREMENT,
        tipo            VARCHAR(20)  NOT NULL,
        clave           VARCHAR(190) NOT NULL,
        version         INT          NOT NULL,
        contenido       LONGBLOB     NOT NULL,
        actualizado     DATETIME     NOT NULL,
        actualizado_por VARCHAR(100) NOT NULL DEFAULT '',
        borrado         DATETIME     NULL,
        reemplazado     DATETIME     NOT NULL,
        PRIMARY KEY (id),
        KEY ix_gxp_historial_doc (tipo, clave, version)
    ) DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci""",
)


class SinConexion(Exception):
    """No se pudo llegar a la base compartida."""


def cargar_env():
    """Pasa las variables de .env al entorno, sin pisar las que ya estan definidas. Formato: CLAVE=valor por
    linea; '#' comenta; las comillas que rodean el valor se sacan."""
    try:
        lineas = ENV.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, v = linea.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ.setdefault(k, v)


cargar_env()


def _en_pruebas_unitarias():
    """python -m unittest: las pruebas usan siempre los archivos locales, aunque haya una base configurada."""
    return getattr(sys.modules.get("__main__"), "__package__", None) == "unittest"


def parametros():
    """Los datos de conexion, o None si no hay base compartida configurada."""
    host = os.environ.get("GXP_DB_HOST", "").strip()
    if not host or _en_pruebas_unitarias():
        return None
    return {
        "host": host,
        "port": int(os.environ.get("GXP_DB_PORT") or 3306),
        "user": os.environ.get("GXP_DB_USER", ""),
        "password": os.environ.get("GXP_DB_PASSWORD", ""),
        "database": os.environ.get("GXP_DB_NAME") or "gxpruebas",
        "ssl": os.environ.get("GXP_DB_SSL", "").strip().lower(),
        "ssl_ca": os.environ.get("GXP_DB_SSL_CA", "").strip(),
    }


def usuario():
    return (os.environ.get("GXP_USUARIO") or os.environ.get("USERNAME") or os.environ.get("USER") or "")[:100]


def descripcion():
    p = parametros()
    return f"{p['user']}@{p['host']}:{p['port']}/{p['database']}" if p else ""


_local = threading.local()
_falla = {"hasta": 0.0, "motivo": ""}


def _driver():
    try:
        import pymysql
    except ImportError:
        raise SinConexion("falta la libreria PyMySQL: instalala con 'python -m pip install -r requirements.txt'")
    return pymysql


def _abrir(con_base=True):
    p = parametros()
    if not p:
        raise SinConexion("no hay base compartida configurada (falta GXP_DB_HOST)")
    pymysql = _driver()
    args = dict(host=p["host"], port=p["port"], user=p["user"], password=p["password"], charset="utf8mb4",
                connect_timeout=TIMEOUT_SEG, read_timeout=120, write_timeout=120, autocommit=True)
    if con_base:
        args["database"] = p["database"]
    if p["ssl"] in ("no", "0", "false", "off"):
        args["ssl_disabled"] = True
    elif p["ssl_ca"]:
        args.update(ssl_ca=p["ssl_ca"], ssl_verify_cert=True, ssl_verify_identity=True)
    try:
        return pymysql.connect(**args)
    except pymysql.err.OperationalError as e:
        raise SinConexion(f"{descripcion()}: {e.args[-1] if e.args else e}")


def descartar():
    """Cierra la conexion del hilo (despues de un error de red): la proxima vez se abre otra."""
    c = getattr(_local, "conexion", None)
    _local.conexion = None
    if c is not None:
        try:
            c.close()
        except Exception:
            pass


def conexion():
    """La conexion del hilo (se reutiliza y se reconecta si se corto). SinConexion si no se puede."""
    if time.time() < _falla["hasta"]:
        raise SinConexion(_falla["motivo"])
    c = getattr(_local, "conexion", None)
    try:
        if c is not None:
            c.ping(reconnect=True)
        else:
            c = _local.conexion = _abrir()
    except SinConexion as e:
        _local.conexion = None
        _falla.update(hasta=time.time() + PAUSA_TRAS_FALLA_SEG, motivo=str(e))
        raise
    except Exception as e:
        _local.conexion = None
        motivo = f"{descripcion()}: {e}"
        _falla.update(hasta=time.time() + PAUSA_TRAS_FALLA_SEG, motivo=motivo)
        raise SinConexion(motivo)
    _falla["hasta"] = 0.0
    return c


def inicializar():
    """Crea la base (si el usuario puede) y las tablas que falten."""
    p = parametros()
    c = _abrir(con_base=False)
    try:
        with c.cursor() as cur:
            try:
                cur.execute(f"CREATE DATABASE IF NOT EXISTS `{p['database']}` DEFAULT CHARACTER SET utf8mb4")
            except _driver().err.Error:
                pass  # sin permiso para crear bases: alcanza con que ya exista
            cur.execute(f"USE `{p['database']}`")
            for sentencia in DDL:
                cur.execute(sentencia)
    finally:
        c.close()
    _falla["hasta"] = 0.0
