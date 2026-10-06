"""Utilidades de archivos y textos que usan todos los modulos (sin dependencias de GxPruebas)."""
import json
import os
import re
import subprocess
from pathlib import Path


def leer_json(ruta, defecto=None):
    """Contenido de un JSON, o 'defecto' si no existe o esta roto."""
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defecto


def escribir_json(ruta, datos, sangria=None):
    """Graba un JSON de forma atomica: escribe un temporal y lo renombra, asi un lector (u otro proceso de
    GxPruebas) nunca ve el archivo a medio escribir. El temporal lleva el pid: dos procesos no se pisan."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(f"{ruta.stem}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=sangria), encoding="utf-8")
        os.replace(tmp, ruta)
    finally:
        tmp.unlink(missing_ok=True)


def recorrer(raiz, extension, saltear=()):
    """(ruta, ruta relativa a raiz, os.DirEntry) de cada archivo con esa extension debajo de raiz.
    Usa os.scandir: en Windows la fecha viene con el listado de la carpeta, sin pedirla archivo por archivo.
    'saltear': nombres de carpetas que no se recorren. Las carpetas que no se pueden leer se saltean."""
    raiz = str(raiz)
    pila = [raiz]
    extension = extension.lower()
    while pila:
        try:
            with os.scandir(pila.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            if e.name not in saltear:
                                pila.append(e.path)
                        elif e.name.lower().endswith(extension):
                            yield e.path, os.path.relpath(e.path, raiz), e
                    except OSError:
                        continue
        except OSError:
            continue


def conservar_ultimos(carpeta, patron, cantidad, excepto=()):
    """Borra los archivos mas viejos (por nombre, que empieza con la fecha) y deja los ultimos 'cantidad'."""
    viejos = sorted(p for p in Path(carpeta).glob(patron) if p.name not in excepto)
    for p in viejos[:-cantidad] if cantidad else viejos:
        try:
            p.unlink()
        except OSError:
            pass  # en uso: queda para la proxima vez


def slug(texto: str) -> str:
    """Texto -> identificador para nombres de archivo e ids ("Alta de un registro" -> "alta-de-un-registro")."""
    s = re.sub(r"[^\w\-]+", "-", (texto or "").strip().lower(), flags=re.U).strip("-")
    return s or "suite"


# Para subprocess en Windows: sin abrir una ventana de consola.
SIN_VENTANA = getattr(subprocess, "CREATE_NO_WINDOW", 0)
