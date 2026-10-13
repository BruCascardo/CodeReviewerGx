"""Lo que la pantalla de una transaccion hace y su Business Component no.

GeneXus genera dos veces cada transaccion que es Business Component: la pantalla (x_impl.java) y el BC
(x_bc.java). Las reglas que usan variables de la pantalla, las que llevan [web] y los eventos (Start, After Trn,
'DoConfirmar') solo estan en la pantalla: un procedimiento o una API que graba con el BC no los ejecuta.

Compara los dos .java y devuelve, de la pantalla:
  - graba:  llamadas a procedimientos que escriben en la base (ellos o lo que llaman, ver efectos.py);
  - valida: llamadas en una regla seguidas de un error (AnyError = 1): la regla Error() de la pantalla;
  - error:  mensajes de error escritos en una regla (Error('...')) que el BC no tiene.
Las llamadas de solo lectura (cargar un combo, armar un texto) no se informan: no cambian lo que se graba.
"""
import re
import threading

# Clases que no son logica de negocio aunque solo las llame la pantalla (ultimo tramo, o parte del paquete).
RUIDO = ("loaddvcombo", "wwpbaseobjects", "workwithplus", "secgamisauth", "genexussecurity", "prclog")

_METODO = re.compile(r"^   (?:public|private|protected)[^\n(]*?\b(\w+)\(", re.M)
_LLAMADA = re.compile(r"new (com\.[\w.]+)\(remoteHandle, context\)\.execute(?:Udp)?\(")
_RUTINA = re.compile(r"/\* (.+?) Routine \*/")
_ERROR = re.compile(r'GX_msglist\.addItem\("((?:[^"\\]|\\.)*)", 1, ')
_ANY_ERROR = "AnyError = (short)(1)"
LINEAS_ERROR = 15  # una llamada "valida" si el error se da en las lineas que siguen

# Metodo de la pantalla -> donde esta en GeneXus
_REGLAS = (
    ("beforeValidate", "regla Before Validate"), ("afterConfirm", "regla After Confirm"),
    ("checkExtendedTable", "reglas"), ("beforeInsert", "regla Before Insert"), ("beforeUpdate", "regla Before Update"),
    ("beforeDelete", "regla Before Delete"), ("beforeComplete", "regla Before Complete"),
    ("onDeleteControls", "reglas del Delete"), ("insert", "regla After Insert"), ("update", "regla After Update"),
    ("delete", "regla After Delete"), ("zm", "reglas"), ("standalone", "reglas"),
)


def _metodos(texto):
    """[(nombre, cuerpo)] de los metodos de un .java generado."""
    ms = list(_METODO.finditer(texto))
    return [(m.group(1), texto[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(texto)]) for i, m in enumerate(ms)]


def _es_evento(metodo):
    return re.fullmatch(r"e\d\w*", metodo) is not None


def _lugar(metodo, cuerpo):
    if _es_evento(metodo):
        r = _RUTINA.search(cuerpo)
        return f"evento {r.group(1)}" if r else "un evento"
    for prefijo, texto in _REGLAS:
        if metodo.startswith(prefijo):
            return texto
    return "la pantalla"


def _ruido(clase):
    c = clase.lower()
    return any(r in c for r in RUIDO)


def _java(s):
    return re.sub(r"\\(.)", r"\1", s)


def comparar(impl, bc, escribe):
    """Diferencias entre el Java de la pantalla ('impl') y el del BC ('bc'). 'escribe(clase)' dice si una clase
    graba en la base. Devuelve [{tipo, clase, lugar, mensaje?}] sin repetir clase ni mensaje."""
    salida, vistos = [], set()
    for metodo, cuerpo in _metodos(impl):
        evento = _es_evento(metodo)
        lineas = cuerpo.splitlines()
        for i, linea in enumerate(lineas):
            for clase in _LLAMADA.findall(linea):
                if clase in vistos or _ruido(clase) or re.search(re.escape(clase) + r"\b", bc):
                    continue
                if escribe(clase):
                    tipo = "graba"
                elif not evento and any(_ANY_ERROR in x for x in lineas[i:i + LINEAS_ERROR]):
                    tipo = "valida"
                else:
                    continue
                vistos.add(clase)
                salida.append({"tipo": tipo, "clase": clase, "lugar": _lugar(metodo, cuerpo)})
            if evento:
                continue
            for m in _ERROR.finditer(linea):
                texto = _java(m.group(1))
                if not texto.strip() or texto in vistos or f'"{m.group(1)}"' in bc:
                    continue
                vistos.add(texto)
                salida.append({"tipo": "error", "clase": "", "lugar": _lugar(metodo, cuerpo), "mensaje": texto})
    return salida


# ---------------------------------------------------------------------- sobre una KB

_lock = threading.Lock()
_cache = {}  # (kb, objeto) -> (fechas, diferencias)


def _fecha(p):
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return None


def archivos(kb, trn):
    """(pantalla, bc) de una transaccion: sus .java (x_impl.java y x_bc.java)."""
    base = kb.fuente_java(trn)
    return base.with_name(base.stem + "_impl.java"), base.with_name(base.stem + "_bc.java")


def es_bc(kb, trn):
    """True si la transaccion es Business Component (tiene x_bc.java)."""
    return archivos(kb, trn)[1].exists()


def diferencias(kb, trn, escribe=None):
    """comparar() sobre el Java actual de la transaccion 'trn' (nombre GX). [] si no es BC o no esta generada.
    Cada diferencia lleva tambien 'objeto': el nombre GX de lo llamado (o la clase, si es de otra KB)."""
    impl, bc = archivos(kb, trn)
    fechas = (_fecha(impl), _fecha(bc))
    if None in fechas:
        return []
    clave = (kb.nombre, trn.lower())
    with _lock:
        previo = _cache.get(clave)
        if previo and previo[0] == fechas:
            return previo[1]
    if escribe is None:
        escribe = lambda c: graba(kb, c)  # noqa: E731
    difs = comparar(impl.read_text(encoding="utf-8", errors="ignore"), bc.read_text(encoding="utf-8", errors="ignore"), escribe)
    nombres = _nombres_gx(kb)
    for d in difs:
        d["objeto"] = nombres.get(d["clase"], d["clase"].rsplit(".", 1)[-1]) if d["clase"] else ""
    with _lock:
        _cache[clave] = (fechas, difs)
    return difs


# ---------------------------------------------------------------------- si una clase graba

_UPDATE = re.compile(r"\bUpdateCursor\b")
_NUEVA_LUW = re.compile(r"super\(\s*true\s*,")
_LEIDAS = {}  # ruta -> (fecha, graba por si misma, corre en otra LUW, clases que llama)


def _bc_graba(texto):
    """True si el Java graba con un Business Component: Save(), Insert()... sobre una variable SdtX de un BC."""
    for paquete, sdt, var in _SDT.findall(texto):
        if re.search(re.escape(var) + r"\.(?:" + "|".join(_GRABA) + r")\(\)", texto):
            return True
    return False


def _clase(ruta):
    """(graba por si misma, corre en una nueva LUW, clases que llama) del .java de una clase (y su _impl)."""
    fecha = _fecha(ruta)
    previo = _LEIDAS.get(str(ruta))
    if previo and previo[0] == fecha:
        return previo[1:]
    textos = []
    for f in (ruta, ruta.with_name(ruta.stem + "_impl.java")):
        try:
            textos.append(f.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    t = "\n".join(textos)
    datos = (bool(_UPDATE.search(t)) or _bc_graba(t), bool(_NUEVA_LUW.search(t)), set(_LLAMADA.findall(t)))
    _LEIDAS[str(ruta)] = (fecha, *datos)
    return datos


def _ubicar(clase, kb):
    """El .java de una clase: en la KB o en la que tiene su namespace (com.sistema... esta en Sistema)."""
    from .. import kbs
    rel = clase.split(".")
    cands = [kb] + [k for k in kbs.descubrir().values() if k.ns and clase.startswith(k.ns + ".") and k is not kb]
    for k in cands:
        p = k.fuentes.joinpath(*rel).with_suffix(".java")
        if p.exists():
            return p
    return None


def graba(kb, clase):
    """True si la clase, o lo que llama en la misma unidad de trabajo, graba en la base: tiene sus propios
    UPDATE/INSERT/DELETE o hace Save/Insert/Update/Delete con un Business Component. No entra en lo que corre en
    una nueva unidad de trabajo (prcLog): eso no es parte de la transaccion de quien llama. Un BC que solo se
    carga (Load) no cuenta, aunque su clase tenga los cursores para grabar."""
    vistos, pila = set(), [clase]
    while pila:
        c = pila.pop()
        if c in vistos or (c != clase and _ruido(c)):
            continue
        vistos.add(c)
        ruta = _ubicar(c, kb)
        if ruta is None:
            continue
        propia, otra_luw, llama = _clase(ruta)
        if c != clase and otra_luw:
            continue
        if propia:
            return True
        pila.extend(llama - vistos)
    return False


def _nombres_gx(kb):
    """{clase Java: nombre GX} de los objetos de la KB."""
    from .. import catalogo
    return {kb.clase_java(o["nombre"]): o["nombre"] for o in catalogo.objetos(kb)}


# ---------------------------------------------------------------------- quien graba con el BC

_SDT = re.compile(r"private (com\.[\w.]+)\.Sdt(\w+) (AV\w+) ;")
_GRABA = ("Save", "Insert", "Update", "InsertOrUpdate", "Delete")


def bcs_que_graba(kb, objeto):
    """Nombres GX de las transacciones con cuyo Business Component graba el objeto (Save, Insert, Update,
    InsertOrUpdate o Delete sobre una variable del BC), segun su Java."""
    try:
        texto = kb.fuente_logica(objeto).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    nombres = None
    salida = []
    for paquete, sdt, var in _SDT.findall(texto):
        if not re.search(re.escape(var) + r"\.(?:" + "|".join(_GRABA) + r")\(\)", texto):
            continue
        clase = f"{paquete}.{sdt.lower()}"
        if not kb.fuentes.joinpath(*clase.split(".")).with_name(sdt.lower() + "_bc.java").exists():
            continue  # un SDT comun, o un BC de otra KB
        if nombres is None:
            nombres = _nombres_gx(kb)
        nombre = nombres.get(clase)
        if nombre and nombre not in salida:
            salida.append(nombre)
    return salida
