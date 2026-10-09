"""Update y Build de las KBs de GeneXus sin el IDE, con los mismos targets de MSBuild que trae la instalacion
(<GeneXus>\\TeamDev.msbuild):

  Update  ->  /t:Update   UpdateFromServer: trae los cambios del servidor de la KB (GXserver)
  Build   ->  /t:Build    BuildAll: especifica y genera lo que quedo desactualizado y compila el Java
                          (ForceRebuild=true rehace todo)

Cada pedido es un trabajo que corre en su propio hilo con su propio MSBuild.exe. Update y Build son
independientes: se puede hacer Update de 5 KBs y Build de 3. Reglas:
  - Una KB hace una sola cosa a la vez (GeneXus la bloquea): sus trabajos esperan en cola.
  - Entre KBs distintas corren en paralelo hasta config["genexus"]["paralelo"] (cada MSBuild usa mucha memoria).
  - Una KB abierta en el IDE no se toca: dos procesos sobre la misma KB la corrompen.
  - Antes de un Build se detiene el motor Java de la KB: el build reescribe los .jar y Windows no deja pisar los abiertos.

Si el servidor pide usuario y clave, se toman de GXP_GX_USUARIO y GXP_GX_CLAVE (entorno o .env). Tambien se
pueden fijar ahi GXP_GX_INSTALACION, GXP_GX_MSBUILD y GXP_GX_PARALELO (mandan sobre config.json). Van en un
archivo de respuesta temporal (@archivo.rsp) y no en la linea de comandos, que cualquiera ve en la lista de procesos.
"""
import collections
import datetime as dt
import itertools
import os
import re
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .compartido import conexion
from .config import CFG, RESULTADOS

ACCIONES = {"update": "Update", "build": "Build"}
MSBUILD_X86 = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Microsoft.NET" / "Framework" / "v4.0.30319" / "MSBuild.exe"
MAX_LINEAS = 5000      # lineas de salida que se guardan en memoria por trabajo (el archivo de log las tiene todas)
MAX_TRABAJOS = 200     # trabajos terminados que se recuerdan
CARPETA_LOGS = RESULTADOS / "genexus"

_lock = threading.RLock()
_trabajos = collections.OrderedDict()   # id -> Trabajo
_ids = itertools.count(1)
_locks_kb = {}                          # nombre de KB -> Lock (una cosa a la vez por KB)
_cupo = None                            # Semaphore global (se crea al primer uso, con config)


def _conf():
    return CFG.get("genexus") or {}


def _env(nombre):
    """Variable GXP_GX_* del entorno o del .env de GxPruebas (que no se muestra nunca)."""
    conexion.cargar_env()
    return os.environ.get(nombre, "").strip()


def _opcion(nombre_env, clave, defecto=""):
    """Un ajuste: la variable de entorno / .env manda sobre config.json."""
    return _env(nombre_env) or _conf().get(clave) or defecto


# ---------------------------------------------------------------- instalacion y KBs

def instalacion():
    """Carpeta de GeneXus con TeamDev.msbuild: la de config.json, o la mas nueva de C:\\GeneXus."""
    fija = _opcion("GXP_GX_INSTALACION", "instalacion")
    if fija:
        p = Path(fija)
        if (p / "TeamDev.msbuild").exists():
            return p
        raise RuntimeError(f"GXP_GX_INSTALACION / genexus.instalacion = {fija}: no existe TeamDev.msbuild ahi.")
    candidatas = [p for p in Path(r"C:\GeneXus").glob("GeneXus*") if (p / "TeamDev.msbuild").exists()]
    if not candidatas:
        raise RuntimeError(r"No encuentro GeneXus en C:\GeneXus: indicá la carpeta en .env (GXP_GX_INSTALACION).")
    return max(candidatas, key=lambda p: p.name)


def kbs():
    """Todas las KBs de las raices (compiladas o no): carpetas con <nombre>.gxw, hasta 2 niveles."""
    res = {}
    for raiz in CFG["raicesKB"]:
        r = Path(raiz)
        if not r.exists():
            continue
        for gxw in sorted(list(r.glob("*/*.gxw")) + list(r.glob("*/*/*.gxw"))):
            carpeta = gxw.parent
            if gxw.stem.lower() != carpeta.name.lower():
                continue
            res.setdefault(carpeta.name, {"nombre": carpeta.name, "carpeta": str(carpeta), "raiz": str(r)})
    return sorted(res.values(), key=lambda k: (k["raiz"], k["nombre"].lower()))


_cache_ide = (0.0, set())


def abiertas_en_ide():
    """Carpetas (en minusculas) de las KBs abiertas en algun GeneXus.exe (se lee de su linea de comandos /KB:...)."""
    global _cache_ide
    t, valor = _cache_ide
    if time.time() - t < 4:
        return valor
    carpetas = set()
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='GeneXus.exe'\" | ForEach-Object { $_.CommandLine }"],
            capture_output=True, text=True, timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        for m in re.finditer(r'/KB:"?([^"\r\n]+?)"?\s*(?:/|$)', out, re.I | re.M):
            carpetas.add(os.path.normpath(m.group(1).strip()).lower())
    except Exception:
        pass  # sin PowerShell no se puede saber: MSBuild avisa si la KB esta tomada
    _cache_ide = (time.time(), carpetas)
    return carpetas


def estado_kbs():
    """Las KBs con si estan abiertas en el IDE y su trabajo en curso o ultimo."""
    abiertas = abiertas_en_ide()
    ultimo = {}
    with _lock:
        for t in _trabajos.values():
            ultimo[(t.kb, t.accion)] = t
    res = []
    for k in kbs():
        fila = dict(k, enIde=os.path.normpath(k["carpeta"]).lower() in abiertas)
        for accion in ACCIONES:
            t = ultimo.get((k["nombre"], accion))
            fila[accion] = t.resumen() if t else None
        res.append(fila)
    return res


# ---------------------------------------------------------------- trabajos

class Trabajo:
    def __init__(self, kb, accion, forzar=False):
        self.id = next(_ids)
        self.kb = kb["nombre"]
        self.carpeta = kb["carpeta"]
        self.accion = accion
        self.forzar = forzar
        self.estado = "en_cola"          # en_cola | corriendo | ok | error | cancelado
        self.mensaje = ""
        self.creado = dt.datetime.now()
        self.inicio = None
        self.fin = None
        self.lineas = collections.deque(maxlen=MAX_LINEAS)
        self.total = 0                   # lineas emitidas (los indices de /log cuentan desde 0 aunque se descarten)
        self.errores = []
        self.proc = None
        self.cancelar = threading.Event()
        self.archivo_log = None

    def agregar(self, linea):
        with _lock:
            self.lineas.append(linea)
            self.total += 1
        if self.archivo_log:
            try:
                self.archivo_log.write(linea + "\n")
                self.archivo_log.flush()
            except OSError:
                pass
        if re.search(r"\berror\b", linea, re.I) and len(self.errores) < 30:
            self.errores.append(linea.strip())

    @property
    def activo(self):
        return self.estado in ("en_cola", "corriendo")

    def resumen(self):
        seg = None
        if self.inicio:
            seg = round(((self.fin or dt.datetime.now()) - self.inicio).total_seconds())
        return {"id": self.id, "kb": self.kb, "accion": self.accion, "forzar": self.forzar, "estado": self.estado,
                "mensaje": self.mensaje, "creado": self.creado.isoformat(timespec="seconds"),
                "inicio": self.inicio and self.inicio.isoformat(timespec="seconds"),
                "fin": self.fin and self.fin.isoformat(timespec="seconds"), "segundos": seg,
                "lineas": self.total, "errores": self.errores[:5]}


def _cupo_global():
    global _cupo
    if _cupo is None:
        _cupo = threading.Semaphore(max(1, int(_opcion("GXP_GX_PARALELO", "paralelo", 3))))
    return _cupo


def _escapar(valor):
    """Escape de MSBuild para un valor de propiedad: sin esto un '$', '%', ';' o '@' de la clave se interpretan."""
    for c in "%$;@*?'":
        valor = valor.replace(c, "%%%02X" % ord(c))
    return valor


def _comando(t, rsp):
    gx = instalacion()
    msbuild = Path(_opcion("GXP_GX_MSBUILD", "msbuild", MSBUILD_X86))
    if not msbuild.exists():
        raise RuntimeError(f"No existe {msbuild}. Las tareas de GeneXus son de 32 bits: hace falta el MSBuild de Framework\\v4.0.30319.")
    cmd = [str(msbuild), str(gx / "TeamDev.msbuild"), f"/t:{ACCIONES[t.accion]}", f"/p:WorkingDirectory={t.carpeta}",
           "/nologo", "/v:minimal", "/nr:false", "/m:1"]
    if t.accion == "build" and t.forzar:
        cmd.append("/p:ForceRebuild=true")
    usuario, clave = _env("GXP_GX_USUARIO"), _env("GXP_GX_CLAVE")
    if usuario:
        rsp.write_text(f"/p:ServerUsername={_escapar(usuario)}\n/p:ServerPassword={_escapar(clave)}\n", encoding="utf-8")
        cmd.append(f"@{rsp}")
        t.agregar(f"Credenciales del servidor: usuario '{usuario}', clave de {len(clave)} caracteres (de .env)")
    else:
        t.agregar("Sin credenciales: GXP_GX_USUARIO esta vacio o no se leyo de .env")
    return cmd


def _matar(proc):
    """Cierra MSBuild y todo lo que lanzo (GeneXus levanta procesos hijos: gradle, java...)."""
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _ejecutar(t):
    lock = _locks_kb.setdefault(t.kb, threading.Lock())
    while not lock.acquire(timeout=0.5):
        if t.cancelar.is_set():
            return _terminar(t, "cancelado", "Cancelado antes de empezar")
    try:
        cupo = _cupo_global()
        while not cupo.acquire(timeout=0.5):
            if t.cancelar.is_set():
                return _terminar(t, "cancelado", "Cancelado antes de empezar")
        try:
            if t.cancelar.is_set():
                return _terminar(t, "cancelado", "Cancelado antes de empezar")
            _correr(t)
        finally:
            cupo.release()
    finally:
        lock.release()


def _terminar(t, estado, mensaje):
    t.estado, t.mensaje, t.fin = estado, mensaje, dt.datetime.now()
    if t.archivo_log:
        try:
            t.archivo_log.close()
        except OSError:
            pass


def _correr(t):
    rsp = None
    try:
        if os.path.normpath(t.carpeta).lower() in abiertas_en_ide():
            return _terminar(t, "error", f"{t.kb} esta abierta en el IDE de GeneXus: cerrala antes.")
        CARPETA_LOGS.mkdir(parents=True, exist_ok=True)
        t.inicio = dt.datetime.now()
        t.estado = "corriendo"
        t.archivo_log = open(CARPETA_LOGS / f"{t.kb}_{t.accion}_{t.inicio:%Y%m%d_%H%M%S}.log", "w", encoding="utf-8")
        if t.accion == "build":
            _soltar_jars(t)
        fd, ruta = tempfile.mkstemp(suffix=".rsp", prefix="gxp_")
        os.close(fd)
        rsp = Path(ruta)
        cmd = _comando(t, rsp)
        t.agregar(f"> {ACCIONES[t.accion]} de {t.kb}" + ("  (rebuild completo)" if t.forzar else ""))
        t.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        for crudo in t.proc.stdout:
            t.agregar(crudo.decode("cp1252", errors="replace").rstrip("\r\n"))
        codigo = t.proc.wait()
        if t.cancelar.is_set():
            _terminar(t, "cancelado", "Cancelado")
        elif codigo == 0:
            _terminar(t, "ok", "Terminado")
        else:
            _terminar(t, "error", t.errores[-1] if t.errores else f"MSBuild termino con codigo {codigo}")
    except Exception as e:
        _terminar(t, "error", f"{type(e).__name__}: {e}")
    finally:
        if rsp:
            rsp.unlink(missing_ok=True)


def _soltar_jars(t):
    """El motor Java de la KB tiene abiertos los .jar que el build va a reescribir."""
    try:
        from . import kbs as kbs_java, motor
        k = kbs_java.descubrir().get(t.kb)
        if k:
            motor.motor(k).detener("build de GeneXus")
            t.agregar("Motor Java de la KB detenido (se reinicia solo en el proximo uso).")
    except Exception as e:
        t.agregar(f"Aviso: no pude detener el motor Java: {e}")


def lanzar(nombres, accion, forzar=False):
    """Encola un trabajo por KB. Devuelve [{kb, id | omitido}]; una KB con un trabajo activo de cualquier tipo se omite."""
    if accion not in ACCIONES:
        raise ValueError(f"Accion desconocida: {accion}")
    instalacion()  # falla temprano si no hay GeneXus
    por_nombre = {k["nombre"]: k for k in kbs()}
    res = []
    with _lock:
        activos = {t.kb: t for t in _trabajos.values() if t.activo}
        for n in nombres:
            if n not in por_nombre:
                res.append({"kb": n, "omitido": "No es una KB conocida"})
            elif n in activos:
                res.append({"kb": n, "omitido": f"Ya tiene un {ACCIONES[activos[n].accion]} {'en cola' if activos[n].estado == 'en_cola' else 'en curso'}"})
            else:
                t = Trabajo(por_nombre[n], accion, forzar)
                _trabajos[t.id] = t
                activos[n] = t
                threading.Thread(target=_ejecutar, args=(t,), daemon=True, name=f"gx-{accion}-{n}").start()
                res.append({"kb": n, "id": t.id})
        _podar()
    return res


def _podar():
    viejos = [i for i, t in _trabajos.items() if not t.activo]
    for i in viejos[:max(0, len(viejos) - MAX_TRABAJOS)]:
        del _trabajos[i]


def cancelar(id_):
    t = _trabajos.get(int(id_))
    if not t:
        raise KeyError(f"No existe el trabajo {id_}")
    if t.activo:
        t.cancelar.set()
        if t.proc and t.proc.poll() is None:
            _matar(t.proc)
    return t.resumen()


def trabajos():
    with _lock:
        return [t.resumen() for t in reversed(_trabajos.values())]


def log(id_, desde=0):
    """Lineas del trabajo desde la numero 'desde' (los indices son absolutos)."""
    t = _trabajos.get(int(id_))
    if not t:
        raise KeyError(f"No existe el trabajo {id_}")
    with _lock:
        primera = t.total - len(t.lineas)
        inicio = max(int(desde), primera)
        return {"desde": inicio, "lineas": list(t.lineas)[inicio - primera:], "total": t.total, "trabajo": t.resumen()}
