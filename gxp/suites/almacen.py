"""Suites guardadas: suites/<KB>/<nombre>.json. Formato normalizado, lectura, escritura, borrado (a la
papelera) y listado con un resumen por suite."""
import datetime as dt
import json
import threading
from pathlib import Path

from .resultados import estado
from ..config import SUITES
from ..util import escribir_json, slug

_lock = threading.Lock()
_CAMPOS_PASO = ("objeto", "sql", "ds", "entrada", "esperado", "verificaciones", "guardar", "ignorar", "lineaBase",
                "esperaError", "errorContiene")


def _id_de_ruta(p: Path) -> str:
    return p.relative_to(SUITES).with_suffix("").as_posix()


def ruta_suite(suite_id: str) -> Path:
    """Archivo de una suite por su id (Generales/interfases-registro). No deja salir de la carpeta suites."""
    suite_id = suite_id.replace("\\", "/").strip("/")
    if suite_id.endswith(".json"):
        suite_id = suite_id[:-5]
    p = (SUITES / suite_id).with_suffix(".json")
    if SUITES.resolve() not in p.resolve().parents:
        raise ValueError("Ruta de suite invalida")
    return p


def existe(suite_id: str) -> bool:
    return ruta_suite(suite_id).exists()


def normalizar(s: dict) -> dict:
    """Completa los valores por defecto, da un id unico a cada caso y pasa el formato corto (un caso = un
    paso, con 'objeto' o 'sql' en el caso) al de pasos."""
    s = dict(s or {})
    s.setdefault("nombre", "Suite sin nombre")
    s.setdefault("kb", "")
    s.setdefault("descripcion", "")
    s.setdefault("opciones", {})
    s.setdefault("variables", {})
    s.setdefault("preparacion", [])
    casos = []
    usados = set()
    for c in s.get("casos") or []:
        c = dict(c)
        c.setdefault("nombre", c.get("id") or "Caso")
        base = c.get("id") or slug(c["nombre"])
        cid, n = base, 2
        while cid in usados:
            cid, n = f"{base}-{n}", n + 1
        usados.add(cid)
        c["id"] = cid
        c.setdefault("etiquetas", [])
        if "pasos" not in c:  # formato corto: un caso = un paso
            paso = {k: c.pop(k) for k in list(c) if k in _CAMPOS_PASO}
            c["pasos"] = [paso] if paso else []
        casos.append(c)
    s["casos"] = casos
    return s


def cargar(suite_id: str) -> dict:
    """La suite normalizada, con '_id'. KeyError si no existe."""
    p = ruta_suite(suite_id)
    if not p.exists():
        raise KeyError(f"No existe la suite {suite_id}")
    s = normalizar(json.loads(p.read_text(encoding="utf-8")))
    s["_id"] = _id_de_ruta(p)
    return s


def guardar(suite_id: str, s: dict) -> str:
    """Graba la suite (sin las claves internas que empiezan con '_'). Devuelve su id."""
    s = normalizar({k: v for k, v in s.items() if not k.startswith("_")})
    p = ruta_suite(suite_id)
    with _lock:
        escribir_json(p, s, sangria=2)
    return _id_de_ruta(p)


def guardar_nueva(s: dict, pisar=False) -> str:
    """Graba una suite nueva como <KB>/<nombre>. ValueError si falta la KB o ya existe (salvo pisar)."""
    if not s.get("kb"):
        raise ValueError("La suite necesita la KB")
    sid = f"{s['kb']}/{slug(s.get('nombre'))}"
    if existe(sid) and not pisar:
        raise ValueError(f"Ya existe una suite con el nombre '{s.get('nombre')}'")
    return guardar(sid, s)


def borrar(suite_id: str):
    """Mueve la suite a la papelera (.papelera/<nombre>_<fecha>.json)."""
    p = ruta_suite(suite_id)
    if p.exists():
        papelera = SUITES.parent / ".papelera"
        papelera.mkdir(exist_ok=True)
        p.replace(papelera / f"{p.stem}_{dt.datetime.now():%Y%m%d_%H%M%S}.json")


def agregar_caso(suite_id, caso, reemplazar=False, nombre_suite=None, kb=""):
    """Agrega un caso a la suite (la crea si no existe). Con 'reemplazar' y un id, pisa el caso con ese id.
    Devuelve (id de la suite, id del caso)."""
    if existe(suite_id):
        s = cargar(suite_id)
    else:
        s = normalizar({"nombre": nombre_suite or suite_id.split("/")[-1], "kb": kb, "casos": []})
    if reemplazar and caso.get("id"):
        s["casos"] = [caso if c["id"] == caso["id"] else c for c in s["casos"]]
        if not any(c["id"] == caso["id"] for c in s["casos"]):
            s["casos"].append(caso)
    else:
        if not caso.get("id"):
            caso.pop("id", None)
        s["casos"].append(caso)
    suite_id = guardar(suite_id, s)
    caso_id = caso.get("id") if reemplazar else cargar(suite_id)["casos"][-1]["id"]
    return suite_id, caso_id


def ids_de(kb_nombre, prefijo=""):
    """Ids de las suites de una KB cuyo nombre de archivo empieza con 'prefijo'."""
    return [f"{kb_nombre}/{p.stem}" for p in sorted((SUITES / kb_nombre).glob(prefijo + "*.json"))]


_resumenes = {}  # ruta -> (mtime_ns, tamano, resumen): una suite se relee solo si cambio el archivo


def _resumen(p: Path):
    st = p.stat()
    previo = _resumenes.get(str(p))
    if previo and previo[:2] == (st.st_mtime_ns, st.st_size):
        return previo[2]
    try:
        s = normalizar(json.loads(p.read_text(encoding="utf-8")))
        r = {"nombre": s["nombre"], "kb": s["kb"], "descripcion": s["descripcion"], "casos": len(s["casos"]),
             "etiquetas": sorted({e for c in s["casos"] for e in c.get("etiquetas", [])})}
    except Exception as e:
        r = {"nombre": p.stem, "kb": "", "error": str(e), "casos": 0}
    _resumenes[str(p)] = (st.st_mtime_ns, st.st_size, r)
    return r


def listar(kb: str = None):
    """Resumen de cada suite (de una KB o de todas), con el resultado de su ultima corrida. Las suites con
    el JSON roto se listan con 'error' (de cualquier KB: no se sabe de cual son)."""
    SUITES.mkdir(parents=True, exist_ok=True)
    est = estado()
    salida = []
    for p in sorted(SUITES.rglob("*.json")):
        try:
            r = _resumen(p)
        except OSError:
            continue  # se borro mientras se listaba
        sid = _id_de_ruta(p)
        if "error" in r:
            salida.append({"id": sid, **r})
            continue
        if kb and r["kb"].lower() != kb.lower():
            continue
        salida.append({"id": sid, **r, "ultimo": est.get(sid, {}).get("_resumen")})
    return salida


def resolver(nombres, kb=None):
    """Ids de suites a partir de lo que escribe el usuario: id, ruta de archivo o parte unica del nombre.
    Sin nombres, todas (o todas las de la KB). ValueError si no encuentra una o es ambigua."""
    todas = listar(kb)
    if not nombres:
        return [s["id"] for s in todas]
    ids = []
    for n in nombres:
        p = Path(n)
        if p.suffix == ".json" and p.exists():
            ids.append(p.resolve().relative_to(SUITES.resolve()).with_suffix("").as_posix())
            continue
        exactas = [s["id"] for s in todas if s["id"].lower() == n.lower().replace("\\", "/")]
        if exactas:
            ids.extend(exactas)
            continue
        parecidas = [s["id"] for s in todas if n.lower() in s["id"].lower() or n.lower() in s["nombre"].lower()]
        if len(parecidas) == 1:
            ids.append(parecidas[0])
        elif not parecidas:
            raise ValueError(f"No encuentro la suite '{n}'")
        else:
            raise ValueError(f"'{n}' es ambiguo: {', '.join(parecidas)}")
    return ids
