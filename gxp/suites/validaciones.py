"""Casos de validacion generados a partir de una entrada valida (Explorar: «Generar validaciones»; comando
'validaciones').

Por cada campo de la entrada se propone una fila de 'datos' con ese campo cambiado:

  obligatorio   el campo vacio: '' en un texto o una fecha, 0 en un numero (los booleanos no)
  lista         una coleccion sin elementos (adentro de las listas no se generan filas por campo)
  dominio       un valor del dominio enumerado del campo, uno por fila (salvo el que ya tiene la entrada)
  no_existe     ${siguiente.Clave} en un campo que es la clave numerica de una tabla: un id que no existe

mas la fila 'base', con la entrada tal cual. Todas se ejecutan (cada una con rollback, como va a correr el caso)
para mostrar que devuelve hoy cada una: Ok, codigos y texto de los mensajes del sdtOutput. Si el objeto hace commit
por su cuenta, se corren como con script previo: el commit se simula y nada queda grabado. Con eso armar_caso()
escribe el caso: el paso usa ${columna} en cada campo que cambia, cada fila trae lo que se espera (columnas 'ok',
'codigo' y 'mensaje') y las verificaciones controlan Ok y el codigo del mensaje o, en las filas que fallan sin
codigo, el texto del mensaje de error (las que quedan vacias en una fila no se controlan: omitirSiVacio).
"""
import copy
import re

from .ejecucion import correr_caso
from .script import Entorno, bloques
from .variables import poner_calculadas
from .. import campos, catalogo
from ..config import CFG
from ..revisor import salida as control_salida


def _hojas(v, ruta=""):
    """(ruta, valor) de los valores simples y de las listas (sin entrar en ellas): inSet.Items, inSet.ItfId."""
    if isinstance(v, dict):
        for k, x in v.items():
            r = f"{ruta}.{k}" if ruta else k
            if isinstance(x, (dict,)):
                yield from _hojas(x, r)
            else:
                yield r, x


def _poner(obj, ruta, valor):
    partes = ruta.split(".")
    for k in partes[:-1]:
        obj = obj[k]
    obj[partes[-1]] = valor


def _columnas(rutas):
    """Nombre de la columna de 'datos' de cada ruta: el del campo, o la ruta con _ si dos campos se llaman igual."""
    hoja = lambda r: r.split(".")[-1]
    repetidos = {h for h in map(hoja, rutas) if sum(hoja(r).lower() == h.lower() for r in rutas) > 1}
    return {r: (re.sub(r"\W", "_", r) if hoja(r) in repetidos else hoja(r)) for r in rutas}


def _vacio(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return 0
    return ""


def _candidatas(entrada, ayudas):
    """[(tipo, ruta, valor, texto)] de las filas que se proponen (sin la base)."""
    filas = []
    for ruta, v in _hojas(entrada):
        campo = ruta.split(".")[-1]
        ayuda = ayudas.get(ruta.lower()) or {}
        if isinstance(v, list):
            if v:
                filas.append(("lista", ruta, [], f"{campo} sin elementos"))
            continue
        vacio = _vacio(v)
        if isinstance(v, str) and (ayuda.get("clave") or {}).get("numerica"):
            vacio = "0"  # un id largo viene como texto ("0")
        if vacio is not None and str(v).strip() != str(vacio):
            filas.append(("obligatorio", ruta, vacio, f"{campo} vacio"))
        for e in ayuda.get("valores") or []:
            if str(e["valor"]).strip() != str(v).strip():
                filas.append(("dominio", ruta, e["valor"], f"{campo} = {e.get('nombre') or e['valor']}"))
        clave = ayuda.get("clave")
        if clave and clave.get("numerica") and len(clave.get("claves") or []) == 1:
            filas.append(("no_existe", ruta, f"${{siguiente.{clave['atributo']}}}", f"{campo} que no existe"))
    return filas


def _texto(m):
    return str(control_salida._clave(m, "texto") or control_salida._clave(m, "description") or "").strip()


def _resultado(res):
    """Lo que devolvio una fila: {estado, error, ok, codigos, texto, rutaSalida}."""
    p = (res.get("pasos") or [{}])[-1]
    r = {"estado": p.get("estado") or res.get("estado"), "excepcion": p.get("error") or "", "calculadas": p.get("calculadas")}
    hallados = control_salida.salidas(p.get("datos")) if p.get("datos") is not None else []
    if hallados:
        ruta, d = hallados[0]
        mensajes = [m for m in (control_salida._clave(d, "messages") or []) if isinstance(m, dict)]
        r.update({
            "rutaSalida": ruta, "ok": control_salida._clave(d, "ok"),
            "codigos": [str(control_salida._clave(m, "code") or "").strip() for m in mensajes],
            "texto": " | ".join(_texto(m) for m in mensajes if _texto(m)),
            "error": next((_texto(m) for m in mensajes if control_salida._clave(m, "type") == 1 and _texto(m)), ""),
        })
    return r


def proponer(kb, objeto, entrada, sql_previo=(), timeout_ms=None):
    """Las filas de validacion de 'objeto' a partir de una entrada valida, cada una con lo que devuelve hoy:
    {objeto, entrada, rutaSalida, columnas: {ruta: columna}, filas: [{prueba, tipo, ruta, columna, valor, estado,
    error, ok, codigo, codigos, texto, marcada, aviso}]}."""
    try:
        ayudas = campos.de_objeto(kb, objeto)
    except KeyError:
        ayudas = {}
    candidatas = _candidatas(entrada, ayudas)
    columnas = _columnas(list(dict.fromkeys(r for _, r, _, _ in candidatas)))
    filas = [{"tipo": "base", "ruta": "", "valor": None, "prueba": "entrada valida"}]
    filas += [{"tipo": t, "ruta": r, "valor": v, "prueba": texto, "columna": columnas[r]} for t, r, v, texto in candidatas]
    caso = {**armar_caso(objeto, entrada, columnas, filas, verificar=False), "id": "validaciones"}
    previo = bloques(sql_previo)
    if not previo and catalogo.hace_commit(kb, objeto):
        # Con script previo el motor simula el commit con un savepoint: las filas que terminan bien no graban.
        previo = [{"ds": "", "sql": "select 1"}]
    suite = {"variables": {}, "preparacion": [], "scriptPrevio": previo}
    opts = {**CFG["opcionesSuite"], **({"timeoutMs": int(timeout_ms)} if timeout_ms else {})}
    with Entorno(kb, suite, opts) as ent:
        resultados = correr_caso(kb, suite, caso, opts, entorno=ent)
    ruta_salida = None
    for f, res in zip(filas, resultados):
        r = _resultado(res)
        ruta_salida = ruta_salida or r.get("rutaSalida")
        f.update({k: r.get(k) for k in ("estado", "ok", "codigos", "texto", "calculadas")})
        f["error"] = r.get("excepcion") or ""
        f["codigo"] = next((c for c in r.get("codigos") or [] if c), "")
        # Sin codigo, el texto del primer mensaje de error (en las filas que fallan) identifica el motivo.
        f["mensaje"] = r.get("error") or "" if not f["codigo"] and f.get("ok") is False else ""
        valida = f.get("ok") is False
        if f["estado"] == "error":
            f["marcada"], f["aviso"] = False, "termino con error: " + (f["error"] or "")[:200]
        elif f["tipo"] == "base":
            f["marcada"] = True
            if f.get("ok") is False:
                f["aviso"] = "la entrada de la que se parte no termina bien: las demas filas pueden fallar por otro motivo"
        elif f["tipo"] in ("obligatorio", "lista"):
            f["marcada"] = valida
            if not valida:
                f["aviso"] = "lo acepta: no es obligatorio, o falta validarlo"
        else:
            f["marcada"] = True
    return {"objeto": objeto, "entrada": entrada, "rutaSalida": ruta_salida, "columnas": columnas, "filas": filas}


def armar_caso(objeto, entrada, columnas, filas, nombre=None, ruta_salida=None, verificar=True, etiquetas=("validacion",)):
    """El caso con una fila de 'datos' por cada fila (las de proponer(), las elegidas). Con 'verificar' y
    'ruta_salida' (outCerrar.OutPut), verifica Ok y el codigo con las columnas 'ok' y 'codigo' de cada fila."""
    usadas = {r: c for r, c in columnas.items() if any(f.get("ruta") == r for f in filas)}
    plantilla = copy.deepcopy(entrada)
    base = {}
    for r, c in usadas.items():
        base[c] = copy.deepcopy(_valor_en(entrada, r))
        _poner(plantilla, r, f"${{{c}}}")
    datos = []
    for f in filas:
        fila = {"prueba": f["prueba"], **copy.deepcopy(base)}
        if f.get("ruta") in usadas:
            fila[usadas[f["ruta"]]] = copy.deepcopy(f["valor"])
        if verificar and ruta_salida:
            fila["ok"] = f.get("ok")
            fila["codigo"] = f.get("codigo") or ""
            # "No existe el cupon 60" con ${siguiente.CuponId}: queda la variable, no el 60 de hoy.
            fila["mensaje"] = poner_calculadas(f.get("mensaje") or "", f.get("calculadas"))[0]
        datos.append(fila)
    corto = objeto.split(".")[-1]
    paso = {"nombre": corto, "objeto": objeto, "entrada": plantilla}
    if verificar and ruta_salida:
        paso["verificaciones"] = [
            {"ruta": f"{ruta_salida}.Ok", "op": "igual", "valor": "${ok}", "descripcion": "Ok segun la fila"},
            {"ruta": f"{ruta_salida}.Messages[*].Code", "op": "contiene", "valor": "${codigo}", "omitirSiVacio": True,
             "descripcion": "el codigo de mensaje de la fila"},
            {"ruta": f"{ruta_salida}.Messages[*].Texto", "op": "contiene", "valor": "${mensaje}", "omitirSiVacio": True,
             "descripcion": "el mensaje de error de la fila (si no tiene codigo)"},
        ]
    return {"nombre": nombre or f"{corto}: validaciones", "etiquetas": list(etiquetas), "datos": datos, "pasos": [paso]}


def _valor_en(obj, ruta):
    for k in ruta.split("."):
        obj = obj[k]
    return obj
