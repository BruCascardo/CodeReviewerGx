"""Comando compartido: la base compartida de suites y configuracion (gxp/compartido)."""
import datetime as dt
import json
import os
import subprocess
import tempfile
from pathlib import Path

from .consola import c, error
from .. import compartido
from ..config import COMPARTIDAS, RAIZ, SUITES
from ..revisor import configuracion as conf_revisor
from ..suites import almacen
from ..util import escribir_json

# Documentos de configuracion: nombre que se usa en el comando -> (clave en la base, archivo local)
_CONFIGS = {"config": ("general", RAIZ / "config.json"), "revisor": ("revisor", conf_revisor.ARCHIVO)}


def _requiere_activo():
    if not compartido.activo():
        error("No hay base compartida configurada: completa GXP_DB_HOST y los demas datos en .env "
              "(copia .env.ejemplo) o en las variables de entorno.")
        return False
    return True


def _documento(nombre, borrados=False):
    """(tipo, clave) de 'config', 'revisor' o una suite (id o parte unica del nombre)."""
    if nombre.lower() in _CONFIGS:
        return compartido.CONFIG, _CONFIGS[nombre.lower()][0]
    try:
        return compartido.SUITE, almacen.resolver([nombre])[0]
    except ValueError:
        if not borrados:  # una borrada no aparece en el listado: va por su id completo
            raise
        return compartido.SUITE, almacen._id(nombre)


def cmd_estado(_a):
    e = compartido.estado()
    if not e["activo"]:
        print("Base compartida: no configurada. GxPruebas usa los archivos locales (suites\\, config.json, revisor.json).")
        return 0
    print(f"Base compartida: {e['base']}  (los cambios quedan a nombre de '{e['usuario']}')")
    if not e["conectado"]:
        print(c(f"  sin conexion: {e['error']}", "rojo"))
        return 1
    print(c(f"  conectado ({e['servidor']})", "verde"))
    docs = e.get("documentos") or {}
    for t, d in sorted(docs.items()):
        print(f"  {t:8} {d['vigentes']:5} vigentes  {d['borrados']:4} borrados   ultimo cambio: {d['ultimoCambio']}")
    if not docs:
        print("  vacia: subi lo local con 'python gxpruebas.py compartido subir'")
    return 0


def cmd_inicializar(_a):
    if not _requiere_activo():
        return 2
    compartido.inicializar()
    print(c(f"Listo: tablas de GxPruebas en {compartido.descripcion()}", "verde"))
    return 0


def _subir_uno(tipo, clave, datos, kb="", resumen=None, pisar=False):
    """'nueva', 'igual', 'pisada' o 'distinta' (existe con otro contenido y no se piso)."""
    try:
        actual = compartido.leer(tipo, clave)
    except KeyError:
        actual = None
    if actual is not None and actual["datos"] == datos:
        return "igual"
    if actual is not None and not pisar:
        return "distinta"
    compartido.grabar(tipo, clave, datos, kb=kb, resumen=resumen)
    return "pisada" if actual is not None else "nueva"


def _subir_config(nombre, archivo, pisar):
    clave = _CONFIGS[nombre][0]
    datos = json.loads(archivo.read_text(encoding="utf-8"))
    if nombre == "config":
        local = datos
        datos = {k: v for k, v in local.items() if k in COMPARTIDAS}
        if not datos:
            return None
    r = _subir_uno(compartido.CONFIG, clave, datos, pisar=pisar)
    if nombre == "config" and r in ("nueva", "pisada", "igual"):
        # Lo compartido sale de config.json: si quedara, pisaria siempre lo de la base.
        escribir_json(archivo, {k: v for k, v in local.items() if k not in COMPARTIDAS}, sangria=2)
        r += f" (se saco de config.json: {', '.join(datos)})"
    return r


def cmd_subir(a):
    if not _requiere_activo():
        return 2
    compartido.inicializar()
    archivos = [Path(x).resolve() for x in a.archivos] if a.archivos else None
    tareas = []  # (descripcion, funcion)
    if archivos is None:
        tareas += [(str(p.relative_to(RAIZ)), p) for p in sorted(SUITES.rglob("*.json"))]
        tareas += [(p.name, p) for _, p in _CONFIGS.values() if p.exists()]
    else:
        tareas = [(str(p), p) for p in archivos]
    cuentas = {}
    for desc, p in tareas:
        try:
            nombre = next((n for n, (_, f) in _CONFIGS.items() if f.resolve() == p), None)
            if nombre:
                r = _subir_config(nombre, p, a.pisar)
                if r is None:
                    continue
            else:
                if SUITES.resolve() not in p.parents:
                    raise ValueError(f"no esta dentro de {SUITES}")
                s = almacen.normalizar(json.loads(p.read_text(encoding="utf-8")))
                sid = p.relative_to(SUITES.resolve()).with_suffix("").as_posix()
                r = _subir_uno(compartido.SUITE, sid, s, kb=s["kb"], resumen=almacen.resumen_de(s), pisar=a.pisar)
        except (OSError, ValueError) as e:
            r = f"error: {e}"
        clave = r.split(" ")[0].rstrip(":")
        cuentas[clave] = cuentas.get(clave, 0) + 1
        color = {"nueva": "verde", "pisada": "amarillo", "distinta": "amarillo", "igual": "gris"}.get(clave, "rojo")
        if clave != "igual" or a.archivos:
            print(c(f"  {r:10} {desc}", color))
    print(", ".join(f"{n} {k}" for k, n in sorted(cuentas.items())) or "Nada para subir")
    if cuentas.get("distinta"):
        print(c("Las 'distinta' ya estan en la base con otro contenido y no se tocaron. Para reemplazarlas por la "
                "version local, repeti con --pisar (la de la base queda en el historial).", "amarillo"))
    return 1 if any(k.startswith("error") for k in cuentas) else 0


def cmd_bajar(a):
    if not _requiere_activo():
        return 2
    destino = Path(a.carpeta or RAIZ / "exportado" / f"{dt.datetime.now():%Y%m%d_%H%M%S}").resolve()
    n = 0
    for d in compartido.listar(compartido.SUITE):
        doc = compartido.leer(compartido.SUITE, d["clave"])
        escribir_json(destino / "suites" / f"{doc['clave']}.json", doc["datos"], sangria=2)
        n += 1
    for nombre, (clave, archivo) in _CONFIGS.items():
        try:
            escribir_json(destino / archivo.name, compartido.leer(compartido.CONFIG, clave)["datos"], sangria=2)
        except KeyError:
            pass
    print(f"{n} suites y la configuracion en {destino}")
    return 0


def _editor():
    return os.environ.get("GXP_EDITOR") or os.environ.get("EDITOR") or "notepad"


def cmd_editar(a):
    if not _requiere_activo():
        return 2
    tipo, clave = _documento(a.documento)
    try:
        doc = compartido.leer(tipo, clave)
        datos, version = doc["datos"], doc["version"]
    except KeyError:
        if tipo == compartido.SUITE:
            raise
        datos, version = {}, None
    tmp = Path(tempfile.gettempdir()) / f"gxpruebas-{clave.replace('/', '-')}.json"
    escribir_json(tmp, datos, sangria=2)
    print(f"Editando {clave} (version {version or 'nueva'}) en {tmp}. Guarda y cerra el editor para subirlo...")
    while True:
        subprocess.run([*_editor().split(), str(tmp)])
        try:
            nuevos = json.loads(tmp.read_text(encoding="utf-8-sig"))
            break
        except ValueError as e:
            error(f"El JSON no es valido ({e}).")
            if input("Volver a abrirlo? [S/n] ").strip().lower() in ("n", "no"):
                return 1
    tmp.unlink(missing_ok=True)
    if nuevos == datos:
        print("Sin cambios.")
        return 0
    if tipo == compartido.SUITE:
        nuevos["_version"] = version
        almacen.guardar(clave, nuevos)
        version = nuevos["_version"]
    else:
        if clave == "general" and set(nuevos) - set(COMPARTIDAS):
            error(f"Aviso: en la configuracion compartida solo se usan {', '.join(COMPARTIDAS)}; lo demas va en el config.json de cada uno.")
        version = compartido.grabar(tipo, clave, nuevos, version=version)
    print(c(f"Subido: {clave} version {version}", "verde"))
    return 0


def cmd_historial(a):
    if not _requiere_activo():
        return 2
    tipo, clave = _documento(a.documento, borrados=True)
    filas = compartido.historial(tipo, clave)
    if not filas:
        error(f"No hay nada de {clave} en la base compartida")
        return 2
    for f in filas:
        marca = "actual" if f["actual"] else ""
        if f["borrado"] and f["actual"]:
            marca = f"borrada el {f['borrado']}"
        print(f"  v{f['version']:<4} {f['actualizado']}  {f['por']:15} {marca}")
    print(c(f"Para volver a una version: python gxpruebas.py compartido restaurar {a.documento} --version N", "gris"))
    return 0


def cmd_restaurar(a):
    if not _requiere_activo():
        return 2
    tipo, clave = _documento(a.documento, borrados=True)
    v = compartido.restaurar(tipo, clave, a.version)
    print(c(f"{clave}: queda vigente la version {v}", "verde"))
    return 0


def cmd_papelera(_a):
    if not _requiere_activo():
        return 2
    filas = compartido.listar(compartido.SUITE, borrados=True)
    for f in filas:
        print(f"  {f['clave']:60} borrada el {f['borrado']}  ({f['por']})")
    print(f"{len(filas)} suites borradas. Se recuperan con: python gxpruebas.py compartido restaurar <id>")
    return 0


def registrar(sub):
    p = sub.add_parser("compartido", help="base compartida de suites y configuracion (estado, subir, bajar, editar...)")
    s = p.add_subparsers(dest="accion", required=True)
    s.add_parser("estado", help="si esta configurada, si responde y que tiene").set_defaults(fn=cmd_estado)
    s.add_parser("inicializar", help="crea las tablas de GxPruebas").set_defaults(fn=cmd_inicializar)
    q = s.add_parser("subir", help="sube las suites, revisor.json y lo compartido de config.json (o los archivos indicados)")
    q.add_argument("archivos", nargs="*", help="suites\\<KB>\\<suite>.json, revisor.json o config.json (por defecto, todo)")
    q.add_argument("--pisar", action="store_true", help="reemplaza lo que en la base tiene otro contenido")
    q.set_defaults(fn=cmd_subir)
    q = s.add_parser("bajar", help="copia todo lo de la base a una carpeta (respaldo, o para mirarlo)")
    q.add_argument("--carpeta", help="por defecto, exportado\\<fecha>")
    q.set_defaults(fn=cmd_bajar)
    q = s.add_parser("editar", help="abre en el editor 'revisor', 'config' o una suite, y sube el cambio al cerrarlo")
    q.add_argument("documento")
    q.set_defaults(fn=cmd_editar)
    q = s.add_parser("historial", help="versiones de 'revisor', 'config' o una suite")
    q.add_argument("documento")
    q.set_defaults(fn=cmd_historial)
    q = s.add_parser("restaurar", help="recupera una suite borrada, o vuelve a una version (--version)")
    q.add_argument("documento")
    q.add_argument("--version", type=int)
    q.set_defaults(fn=cmd_restaurar)
    s.add_parser("papelera", help="suites borradas").set_defaults(fn=cmd_papelera)
