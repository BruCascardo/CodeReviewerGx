"""Classpath de la JVM de una KB.

- Los .jar de build/libs se copian a una cache compartida (.cache/jars) para que la JVM no los bloquee:
  en Windows un .jar abierto no se puede pisar y GeneXus fallaria al compilar. Al iniciar un motor se
  borran las copias que ya no usa ninguna KB.
- El classpath completo va en el manifiesto de un .jar vacio: evita el limite de largo de la linea de
  comandos de Windows.
- GxMotor.java se compila una vez por KB, contra su classpath.
"""
import hashlib
import os
import shutil
import subprocess
import threading
import time
import zipfile
from pathlib import Path

from ..config import CACHE, CFG, MOTOR_FUENTE
from ..util import SIN_VENTANA, escribir_json, leer_json

ALMACEN = CACHE / "jars"

_lock_indice = threading.Lock()


class ErrorClasspath(Exception):
    pass


def _seguro(nombre):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in nombre)


def carpeta_kb(kb):
    """Carpeta de trabajo del motor de una KB en la cache."""
    return CACHE / "kb" / _seguro(kb.nombre)


# ---------------------------------------------------------------------- cache compartida de .jar

def _archivo_indice():
    return ALMACEN / "indice.json"


def _grabar_indice(indice):
    try:
        escribir_json(_archivo_indice(), indice)
    except OSError:
        pass  # otro proceso lo esta grabando: se recalcula la proxima vez


def _sha1(ruta):
    h = hashlib.sha1()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def _jars_de(kb):
    """[(entrada de build/libs, nombre en la cache)]. El nombre lleva un hash del contenido: las KBs
    comparten la copia de un mismo .jar aunque cada build le ponga otra fecha, y si GeneXus lo cambia
    la copia es otra. El hash se guarda en .cache/jars/indice.json por ruta, tamano y fecha: solo se
    recalcula si el archivo cambio."""
    with _lock_indice:
        indice = leer_json(_archivo_indice(), {})
        cambios = False
        salida = []
        for e in sorted(os.scandir(kb.libs), key=lambda e: e.name):
            if not e.name.endswith(".jar"):
                continue
            st = e.stat()
            previo = indice.get(e.path)
            if previo and previo[0] == st.st_size and previo[1] == st.st_mtime_ns:
                h = previo[2]
            else:
                h = _sha1(e.path)
                indice[e.path] = [st.st_size, st.st_mtime_ns, h]
                cambios = True
            salida.append((e, f"{e.name[:-4]}__{h[:16]}.jar"))
        if cambios:
            _grabar_indice(indice)
    return salida


def copiar_jars(kb):
    """Copia (si hace falta) los .jar de la KB a la cache compartida y devuelve sus rutas."""
    ALMACEN.mkdir(parents=True, exist_ok=True)
    rutas = []
    for e, nombre in _jars_de(kb):
        destino = ALMACEN / nombre
        if not destino.exists():
            tmp = destino.with_name(f"{destino.stem}.{os.getpid()}.tmp")
            shutil.copyfile(e.path, tmp)
            try:
                os.replace(tmp, destino)
            except OSError:
                # Otro proceso lo copio al mismo tiempo y ya lo esta usando.
                tmp.unlink(missing_ok=True)
                if not destino.exists():
                    raise
        rutas.append(str(destino))
    return rutas


def limpiar_cache_jars():
    """Borra de .cache/jars las copias que ya no usa ninguna KB (versiones viejas de cada .jar) y los
    .tmp de copias cortadas. La cache es compartida: lo vigente sale del indice, con las entradas cuyo
    .jar sigue en su build/libs sin cambios (no hace falta calcular hashes de KBs que nunca se usaron).
    Un .jar abierto por un motor que sigue corriendo no se puede borrar en Windows: se deja para la
    proxima vez. Devuelve (archivos borrados, bytes liberados)."""
    if not ALMACEN.exists():
        return 0, 0
    vigentes = set()
    with _lock_indice:
        indice = leer_json(_archivo_indice(), {})
        for ruta, (tam, mtime_ns, h) in list(indice.items()):
            try:
                st = os.stat(ruta)
            except FileNotFoundError:
                del indice[ruta]  # el .jar ya no esta en esa KB
                continue
            except OSError:
                return 0, 0  # no se puede saber si sigue en uso: no se borra nada
            if st.st_size == tam and st.st_mtime_ns == mtime_ns:
                vigentes.add(f"{Path(ruta).name[:-4]}__{h[:16]}.jar")
        _grabar_indice(indice)
    borrados, liberados = 0, 0
    limite_tmp = time.time() - 3600
    for p in ALMACEN.iterdir():
        try:
            st = p.stat()
            if p.suffix == ".jar" and p.name not in vigentes:
                p.unlink()
            elif p.suffix == ".tmp" and st.st_mtime < limite_tmp:
                p.unlink()
            else:
                continue
        except OSError:
            continue  # en uso
        borrados += 1
        liberados += st.st_size
    return borrados, liberados


# ---------------------------------------------------------------------- classpath y GxMotor

def _manifiesto(rutas):
    urls = []
    for r in rutas:
        p = Path(r)
        u = p.as_uri()
        if p.is_dir() and not u.endswith("/"):
            u += "/"
        urls.append(u)
    # Lineas de manifiesto de 72 bytes como maximo; las continuaciones empiezan con un espacio.
    b = ("Class-Path: " + " ".join(urls)).encode("utf-8")
    partes = [b[:70]]
    b = b[70:]
    while b:
        partes.append(b" " + b[:69])
        b = b[69:]
    return b"Manifest-Version: 1.0\r\n" + b"\r\n".join(partes) + b"\r\n\r\n"


def jar_de_classpath(kb, rutas):
    """Un .jar vacio cuyo manifiesto lista el classpath completo: evita el limite de largo de la linea de
    comandos de Windows y los problemas de comillas."""
    carpeta = carpeta_kb(kb)
    carpeta.mkdir(parents=True, exist_ok=True)
    manifiesto = _manifiesto(rutas)
    # El nombre lleva el hash del contenido: un motor corriendo (de la interfaz o de otra consola) tiene su
    # .jar abierto y Windows no deja pisarlo.
    destino = carpeta / f"classpath_{hashlib.sha1(manifiesto).hexdigest()[:12]}.jar"
    if not destino.exists():
        tmp = carpeta / f"classpath_{os.getpid()}.tmp"
        with zipfile.ZipFile(tmp, "w") as z:
            z.writestr("META-INF/MANIFEST.MF", manifiesto)
        os.replace(tmp, destino)
    for viejo in carpeta.glob("classpath_*.jar"):
        if viejo != destino:
            try:
                viejo.unlink()
            except OSError:
                pass  # lo esta usando otro motor
    return destino


def compilar_gxmotor(kb, cp_jar):
    """Compila GxMotor.java contra el classpath de la KB (si cambio el fuente). Devuelve la carpeta de la clase."""
    destino = carpeta_kb(kb) / "motor"
    clase = destino / "GxMotor.class"
    if clase.exists() and clase.stat().st_mtime >= MOTOR_FUENTE.stat().st_mtime:
        return destino
    destino.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([CFG["javac"], "-nowarn", "-encoding", "utf8", "-cp", str(cp_jar), "-d", str(destino), str(MOTOR_FUENTE)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=SIN_VENTANA)
    if r.returncode:
        raise ErrorClasspath("No se pudo compilar GxMotor.java:\n" + (r.stdout + r.stderr)[-4000:])
    return destino


def preparar(kb, log):
    """Deja todo listo para lanzar la JVM de la KB y devuelve su classpath. 'log' recibe lineas para el log."""
    jars = copiar_jars(kb)
    try:
        borrados, liberados = limpiar_cache_jars()
        if borrados:
            log(f"[gxpruebas] cache de jars: {borrados} archivos viejos borrados ({liberados // 1048576} MB)")
    except Exception as e:  # la limpieza nunca impide arrancar
        log(f"[gxpruebas] no se pudo limpiar la cache de jars: {e}")
    cp_jar = jar_de_classpath(kb, [str(kb.clases)] + jars)
    return os.pathsep.join([str(compilar_gxmotor(kb, cp_jar)), str(cp_jar)])
