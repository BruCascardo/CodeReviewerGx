"""Catalogo de objetos de una KB a partir de los XML de navegacion que deja la especificacion
(GXSPC*/GEN*/NVG/**.xml). De ahi salen el tipo de objeto, los parametros con su direccion
(in/out/inout), los warnings y errores de especificacion y los niveles de navegacion.

Los XML vienen en Windows-1252 sin declararlo: se decodifican a mano."""
import os
import threading
import xml.etree.ElementTree as ET
from pathlib import Path

EJECUTABLES = {"Procedure", "DataProvider", "Data Provider"}

_lock = threading.Lock()
_cache = {}  # kb -> {ruta: (mtime, datos)}


def _xml(ruta: Path):
    datos = ruta.read_bytes()
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252", errors="replace")
    return ET.fromstring(texto.strip())


def _texto_tokens(e) -> str:
    """Convierte una condicion de navegacion (Attribute/Variable/Token/Sp/...) a texto legible."""
    if e is None:
        return ""
    partes = []
    for h in e:
        t = h.tag
        if t == "Attribute":
            partes.append(h.findtext("AttriName") or "")
        elif t == "Variable":
            partes.append(h.findtext("VarName") or "")
        elif t == "Sp":
            partes.append(" ")
        elif t in ("Token", "Constant", "Value"):
            partes.append(h.text or "")
        elif len(h):
            sub = _texto_tokens(h)
            partes.append(sub)
            if t in ("Condition",):
                partes.append("\n")
        else:
            partes.append(h.text or "")
    return "".join(partes).strip()


def _mensajes(raiz, tag):
    salida = []
    for m in raiz.iter(tag):
        salida.append({"codigo": m.findtext("MsgCode") or "", "texto": _texto_tokens(m.find("Message")) or (m.text or "").strip()})
    return salida


def _parametros(raiz):
    ps = []
    for p in raiz.findall("Parameters/Parameter"):
        io = (p.findtext("IO") or "in").strip()
        nombre = p.findtext("Variable/VarName") or p.findtext("Attribute/AttriName") or ""
        es_attr = p.find("Attribute") is not None
        tipo = ""
        if not nombre:
            # Salida de un Data Provider: solo trae el tipo (<Token>Modulo\sdtX</Token>).
            tipo = (p.findtext("Token") or "").strip()
            nombre = "Salida"
        ps.append({"nombre": nombre.lstrip("&"), "io": io, "atributo": es_attr, **({"tipoGx": tipo} if tipo else {})})
    return ps


def leer_objeto(ruta: Path):
    raiz = _xml(ruta)
    if raiz.tag != "ObjectSpec":
        return None
    o = raiz.find("Object")
    tipo = (o.findtext("ObjClsName") or "").strip()
    nombre = (o.findtext("ObjName") or "").strip()
    return {
        "nombre": nombre,
        "descripcion": (o.findtext("ObjDesc") or "").strip(),
        "tipo": "DataProvider" if tipo == "Data Provider" else tipo,
        "ejecutable": tipo in EJECUTABLES,
        "resultado": (raiz.findtext("Result") or "").strip(),
        "parametros": _parametros(raiz),
        "warnings": len(list(raiz.iter("Warning"))),
        "errores": len(list(raiz.iter("Error"))),
        "nvg": str(ruta),
    }


def _nivel(lv):
    tabla = lv.find("BaseTable/Table")
    d = {
        "tipo": (lv.findtext("LevelType") or "").strip(),
        "linea": (lv.findtext("LevelBeginRow") or "").strip(),
        "tabla": (tabla.findtext("TableName") if tabla is not None else "") or "",
        "tablaDescripcion": (tabla.findtext("Description") if tabla is not None else "") or "",
        "orden": ", ".join(a.findtext("AttriName") or "" for a in lv.findall("Order/Attribute")),
        "indice": (lv.findtext("IndexName") or "").strip(),
        "desde": _texto_tokens(lv.find("OptimizedWhere/StartFrom")),
        "mientras": _texto_tokens(lv.find("OptimizedWhere/LoopWhile")),
        "filtros": _texto_tokens(lv.find("NonOptimizedWhere")),
        "condicion": _texto_tokens(lv.find("Condition")),
        "join": sorted({t.findtext("TableName") or "" for t in lv.findall("NavigationTree//Table")} - {""}),
        "actualiza": sorted({t.findtext("TableName") or "" for t in lv.findall("TablesToUpdate//Table")} - {""}),
        "optimizaciones": [(x.findtext("Type") or "") for x in lv.findall("Optimizations/Optimization")],
        "subniveles": [_nivel(s) for s in lv.findall("Levels/Level")],
    }
    return d


def detalle(ruta: str):
    """Navegacion completa (niveles, mensajes) de un objeto, para la vista de detalle."""
    raiz = _xml(Path(ruta))
    return {
        "listaWarnings": _mensajes(raiz, "Warning"),
        "listaErrores": _mensajes(raiz, "Error"),
        "niveles": [_nivel(lv) for lv in raiz.findall("Levels/Level")],
    }


def _carpetas_nvg(kb):
    return [p for p in kb.carpeta.glob("GXSPC*/GEN*/NVG") if p.is_dir()]


def _xmls(carpeta):
    """(ruta, mtime) de cada .xml debajo de 'carpeta'. Usa os.scandir: en Windows la fecha viene con el
    listado de la carpeta, sin pedirla archivo por archivo como Path.glob + stat."""
    pila = [str(carpeta)]
    while pila:
        try:
            with os.scandir(pila.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            pila.append(e.path)
                        elif e.name.lower().endswith(".xml"):
                            yield e.path, e.stat().st_mtime
                    except OSError:
                        continue
        except OSError:
            continue


def _leer_cacheado(cache, clave, mt):
    """Datos del objeto de un NVG, releyendo el XML solo si cambio su fecha."""
    if clave in cache and cache[clave][0] == mt:
        return cache[clave][1]
    try:
        datos = leer_objeto(Path(clave))
    except Exception:
        datos = None
    cache[clave] = (mt, datos)
    return datos


def objetos(kb, solo_ejecutables=False):
    with _lock:
        previo = _cache.setdefault(kb.nombre, {})
        nuevo = {}
        for nvg in _carpetas_nvg(kb):
            for clave, mt in _xmls(nvg):
                nuevo[clave] = (mt, _leer_cacheado(previo, clave, mt))
        _cache[kb.nombre] = nuevo
    # Un objeto puede aparecer en mas de un modelo/generador: se queda el mas reciente.
    unicos = {}
    for (mt, d) in sorted((v for v in nuevo.values() if v[1]), key=lambda x: x[0]):
        unicos[d["nombre"].lower()] = d
    lista = sorted(unicos.values(), key=lambda d: d["nombre"].lower())
    if solo_ejecutables:
        # 'nogenspc': GeneXus no lo genera (por ejemplo, "Object is unreachable"): no hay Java para ejecutar.
        lista = [d for d in lista if d["ejecutable"] and d["resultado"] != "nogenspc"]
    return lista


def motivo_no_ejecutable(kb, info):
    """Texto que explica por que no se puede ejecutar el objeto, o None si se puede."""
    if not info["ejecutable"]:
        return f"{info['nombre']} es un {info['tipo']}: solo se pueden ejecutar procedimientos y Data Providers"
    if info["resultado"] == "nogenspc":
        return (f"GeneXus no genera {info['nombre']} (la especificacion lo marca como no generado, "
                "por ejemplo 'Object is unreachable'): no hay Java para ejecutar.")
    clase = kb.clases.joinpath(*kb.clase_java(info["nombre"]).split(".")).with_suffix(".class")
    if not clase.exists():
        return f"{info['nombre']} no esta compilado (no existe {clase.name}): hace Build en GeneXus."
    return None


def _buscar_directo(kb, nombre: str):
    """El NVG de un objeto esta en NVG/<Modulo>/<...>/<Nombre>.xml: con el nombre completo se lee ese
    archivo, sin recorrer toda la especificacion (se llama en cada paso de cada caso)."""
    partes = nombre.strip().split(".")
    if not all(partes):
        return None
    encontrados = []
    with _lock:
        cache = _cache.setdefault(kb.nombre, {})
        for nvg in _carpetas_nvg(kb):
            ruta = nvg.joinpath(*partes[:-1], partes[-1] + ".xml")
            try:
                mt = ruta.stat().st_mtime
            except OSError:
                continue
            d = _leer_cacheado(cache, str(ruta), mt)
            if d and d["nombre"].lower() == nombre.strip().lower():
                encontrados.append((mt, d))
    # Como en objetos(): si esta en mas de un modelo/generador, el mas reciente.
    return max(encontrados, key=lambda x: x[0])[1] if encontrados else None


def buscar(kb, nombre: str):
    d = _buscar_directo(kb, nombre)
    if d:
        return d
    n = nombre.lower().strip()
    lista = objetos(kb)
    for d in lista:
        if d["nombre"].lower() == n:
            return d
    # Permite el nombre corto si es unico (Set -> Generales.Interfases.Registro.Set es ambiguo, se avisa).
    candidatos = [d for d in lista if d["nombre"].lower().endswith("." + n)]
    if len(candidatos) == 1:
        return candidatos[0]
    if len(candidatos) > 1:
        raise KeyError(f"'{nombre}' es ambiguo: " + ", ".join(d["nombre"] for d in candidatos[:10]))
    raise KeyError(f"No encuentro el objeto '{nombre}' en la KB {kb.nombre} (¿esta especificado?)")


def hace_commit(kb, objeto: str) -> bool:
    """True si el Java del objeto confirma la transaccion por su cuenta (Commit on exit = Yes o Commit explicito)."""
    f = kb.fuente_java(objeto)
    try:
        return "commitDataStores" in f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
