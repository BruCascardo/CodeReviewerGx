"""Llamadas por medio de la tabla de servicios (sitServicio).

Un procedimiento de Servicios no se llama directamente: el que lo usa pasa el id del servicio (un valor del
dominio enumerado ServicioTipo, por ejemplo COBRANZA_RENDICIONES_CREDITOSSOBRANTES_GET) y la tabla sitServicio
dice a que procedimiento apunta ese id (SerEndPoint = Servicios/WS_Cobranza/Rendiciones/CreditosSobrantes/Get).

  - Quien usa cada servicio: el valor del dominio como literal en el Java del objeto (GeneXus genera los
    valores de un dominio enumerado como texto). No cuentan los combos (addItem), que listan todos los valores.
  - A que objeto apunta: SerEndPoint de la tabla, con '/' en lugar de '.'. La tabla se lee de la base de la KB
    del dominio y se recuerda en .cache/grafo/servicios.json; si la base no responde y no hay nada guardado,
    se usa la descripcion del dominio (que casi siempre es la misma ruta).

Se configura en config.json, clave "grafoServicios" (ver config.py)."""
import hashlib
import re
import time

from .. import kbs
from ..config import CACHE, CFG
from ..util import escribir_json, leer_json

ARCHIVO = CACHE / "grafo" / "servicios.json"
_LITERAL = re.compile(r'"([A-Z][A-Z0-9_]+)"')
_PUT = re.compile(r'domain\.put\("([^"]+)",\s*"([^"]*)"\)')
_COMBO = (".addItem(", "domain.put(")


def _cfg():
    return CFG.get("grafoServicios") or {}


def _kb():
    c = _cfg()
    if not c.get("kb") or not c.get("dominio"):
        return None
    try:
        return kbs.obtener(c["kb"])
    except Exception:
        return None


def dominio():
    """{id del servicio: descripcion} del dominio enumerado ({} si no esta configurado o no se encuentra)."""
    kb = _kb()
    if not kb:
        return {}
    mod, _, nombre = _cfg()["dominio"].rpartition(".")
    ruta = kb.fuente_java(f"{mod}.gxdomain{nombre}" if mod else f"gxdomain{nombre}")
    try:
        return dict(_PUT.findall(ruta.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return {}


def firma(ids):
    """Cambia cuando se agregan o quitan servicios: hay que volver a buscarlos en el Java de cada KB."""
    return hashlib.sha1("\n".join(sorted(ids)).encode()).hexdigest()[:12]


def literales(texto, ids):
    """Ids de servicio que aparecen como literal en un archivo Java (sin contar los combos)."""
    if not ids:
        return []
    hallados = set()
    for m in _LITERAL.finditer(texto):
        if m.group(1) not in ids or m.group(1) in hallados:
            continue
        ini = texto.rfind("\n", 0, m.start()) + 1
        fin = texto.find("\n", m.end())
        linea = texto[ini: fin if fin >= 0 else len(texto)]
        if not any(x in linea for x in _COMBO):
            hallados.add(m.group(1))
    return sorted(hallados)


def leer_tabla(log=lambda t: None):
    """Lee la tabla de servicios de la base y la guarda. Devuelve {id: objeto} o None si no se pudo."""
    kb, c = _kb(), _cfg()
    if not kb or not c.get("tabla"):
        return None
    from ..motor import operaciones
    q = f"select {c['id']}, {c['objeto']} from {c['tabla']}"
    try:
        r, datos = operaciones.consulta_suelta(kb, c.get("ds") or "", q, maximo=100000)
    except Exception as e:
        log(f"Servicios: no se pudo leer {c['tabla']} ({e}); se usa lo guardado.")
        return None
    if not r.get("ok") or "filas" not in datos:
        log(f"Servicios: no se pudo leer {c['tabla']} ({r.get('error')}); se usa lo guardado.")
        return None
    mapa = {}
    for f in datos["filas"]:
        sid, obj = (f.get(c["id"]) or "").strip(), (f.get(c["objeto"]) or "").strip()
        if sid and obj:
            mapa[sid] = obj
    escribir_json(ARCHIVO, {"fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "kb": kb.nombre, "tabla": c["tabla"], "servicios": mapa})
    log(f"Servicios: {len(mapa)} filas de {c['tabla']}")
    return mapa


def tabla():
    """{id: ruta del objeto} guardado (de la tabla), completado con la descripcion del dominio."""
    guardado = (leer_json(ARCHIVO, {}) or {}).get("servicios") or {}
    mapa = {k: v for k, v in dominio().items() if "/" in v} if not guardado else {}
    mapa.update(guardado)
    return mapa


def hay_tabla():
    return ARCHIVO.exists()


def nombre_objeto(ruta):
    """Servicios/WS_Cobranza/Rendiciones/CreditosSobrantes/Get -> servicios.ws_cobranza.rendiciones.creditossobrantes.get"""
    return ruta.strip().strip("/").replace("/", ".").lower()
