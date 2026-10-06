"""Configuracion: config.json en la carpeta de GxPruebas, con valores por defecto."""
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CACHE = RAIZ / ".cache"
SUITES = RAIZ / "suites"
RESULTADOS = RAIZ / "resultados"
UI = RAIZ / "ui"
MOTOR_FUENTE = RAIZ / "motor" / "GxMotor.java"

DEFECTO = {
    # Carpetas donde se buscan KBs: cualquier carpeta (hasta 3 niveles) con JavaModel\web\build\classes.
    "raicesKB": [r"C:\KBGXSERVER\CORE", r"C:\KBGXSERVER\FIXES"],
    "puerto": 8765,
    "java": "java",
    "javac": "javac",
    "opcionesJvm": ["-Xss8m", "-Xmx2g", "-Dfile.encoding=UTF-8"],
    # Minutos sin uso tras los que se apaga el motor de una KB (libera conexiones a la base).
    "motorInactivoMin": 15,
    "timeoutMsDefecto": 120000,
    # Pruebas automaticas despues de cada build (ver gxp/automatico). Funcionan mientras la interfaz
    # esta abierta, o con 'gxpruebas.py vigilar'.
    "despuesDelBuild": {
        "activo": False,
        "kbs": [],              # KBs a vigilar; ["*"] = todas las que tengan suites
        "etiqueta": "",         # solo los casos con esta etiqueta ("" = todos los casos)
        "esperaSeg": 15,        # segundos sin cambios en el build antes de correr
        "notificar": True,      # notificacion de Windows con el resultado
        "revisar": True,        # revisa las buenas practicas de los objetos del build (gxp/revisor)
    },
    # Opciones por defecto de las suites (cada suite las puede pisar).
    "opcionesSuite": {
        "transaccion": "rollback",
        "recortarEspacios": True,
        "toleranciaNumerica": 0.000001,
        "listasParciales": False,
        "timeoutMs": 120000,
    },
}


def cargar():
    cfg = json.loads(json.dumps(DEFECTO))
    archivo = RAIZ / "config.json"
    if archivo.exists():
        try:
            propio = json.loads(archivo.read_text(encoding="utf-8"))
        except Exception as e:  # pragma: no cover
            raise SystemExit(f"config.json invalido: {e}")
        for k, v in propio.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg


CFG = cargar()
