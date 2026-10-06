"""Corre las reglas de buenas practicas sobre los objetos de una KB (comando 'revisar').

Lee el fuente de cada objeto de su especificacion (.sp0, ver fuente.py), corre las reglas activas de
revisor.json que aplican al objeto, separa los hallazgos que cubre una excepcion, marca cuales son nuevos
respecto de la linea base (lineabase.py) y guarda el resultado en resultados/revisiones/.
"""
import datetime as dt
import json
import os
from pathlib import Path

from . import configuracion, fuente, lineabase, sdts, transacciones
from .reglas import SEVERIDADES, cargar as cargar_reglas
from ..config import RESULTADOS

DIR = RESULTADOS / "revisiones"
MAX_GUARDADAS = 100


class Contexto:
    """Lo que una regla puede consultar ademas del fuente del objeto."""

    def __init__(self, kb, conf):
        self.kb = kb
        self.kb_nombre = kb.nombre
        self.conf = conf
        self._java = {}
        self._sdts = {}
        self._trns = {}

    def rutas_sdt(self, tipo, buscado):
        """Rutas dentro de un valor de tipo 'tipo' donde hay un SDT 'buscado' (ver sdts.rutas)."""
        clave = (tipo.lower(), buscado.lower())
        if clave not in self._sdts:
            self._sdts[clave] = sdts.rutas(self.kb, tipo, buscado)
        return self._sdts[clave]

    def transaccion(self, tipo):
        """La transaccion (clave y autonumerados) de un Business Component, o None (ver transacciones.py)."""
        clave = tipo.lower()
        if clave not in self._trns:
            self._trns[clave] = transacciones.de_tipo(self.kb, tipo)
        return self._trns[clave]

    def java(self, objeto):
        """Texto del Java generado del objeto (con su _impl), o None si no esta generado."""
        if objeto not in self._java:
            base = self.kb.fuente_java(objeto)
            textos = []
            for f in (base, base.with_name(base.stem + "_impl.java")):
                try:
                    textos.append(f.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    pass
            self._java[objeto] = "\n".join(textos) if textos else None
        return self._java[objeto]

    def java_confirma(self, objeto):
        """True si el Java del objeto hace commit, False si no, None si no hay Java."""
        t = self.java(objeto)
        return None if t is None else "commitDataStores" in t


def reglas_activas(conf, ids=None):
    """Instancias de las reglas activas (o de las pedidas en 'ids', aunque esten desactivadas)."""
    clases = cargar_reglas()
    if ids:
        faltan = [i for i in ids if i not in clases]
        if faltan:
            raise KeyError(f"No existe la regla {', '.join(faltan)}. Reglas: {', '.join(sorted(clases))}")
    salida = []
    for rid, cls in sorted(clases.items()):
        r = cls(conf.reglas.get(rid))
        if (ids and rid in ids) or (not ids and r.activa):
            salida.append(r)
    return salida


def revisar(kb, objetos=None, reglas=None, cambiados=False, guardar=True, log=None, origen="manual"):
    """Revisa la KB entera, solo 'objetos' (nombres completos) o, con cambiados=True, los objetos cuya
    especificacion cambio desde la linea base (los que volvio a especificar un build). Cada hallazgo lleva
    'nuevo': True si lo introdujo la ultima modificacion del objeto, False si ya estaba, None si no hay linea
    base. Devuelve el resultado como dict."""
    with lineabase.lock(kb):
        return _revisar(kb, objetos, reglas, cambiados, guardar, log, origen)


def asegurar_linea_base(kb, log=None):
    """Si la KB no tiene linea base, la arma con una revision completa. Devuelve True si la armo."""
    with lineabase.lock(kb):
        if lineabase.LineaBase(kb).existe:
            return False
        _revisar(kb, None, None, False, True, log, "linea-base")
        return True


def revisar_fuente(fu, reglas, ctx, conf, lb, cambio):
    """Corre las reglas sobre un objeto. 'cambio': si su especificacion cambio desde la linea base (decide
    que es nuevo, ver LineaBase.es_nuevo). Devuelve (hallazgos, excepcionados, huellas, errores)."""
    hallazgos, excepcionados, huellas, errores = [], [], [], []
    vistas = {}
    for regla in reglas:
        try:
            if not regla.aplica(fu, ctx):
                continue
            for h in regla.revisar(fu, ctx):
                # Dos sentencias iguales en el mismo objeto: la huella lleva el numero de aparicion.
                n = vistas[h.huella] = vistas.get(h.huella, 0) + 1
                if n > 1:
                    h.huella += f"-{n}"
                huellas.append(h.huella)
                d = h.dict()
                d["nuevo"] = lb.es_nuevo(fu.nombre, h.huella, cambio)
                e = conf.excepcion(h)
                if e:
                    excepcionados.append({**d, "motivo": e["motivo"]})
                else:
                    hallazgos.append(d)
        except Exception as e:  # una regla rota no frena al resto
            errores.append({"objeto": fu.nombre, "error": f"regla {regla.id}: {e!r}"})
    return hallazgos, excepcionados, huellas, errores


def _mtime(ruta):
    try:
        return os.stat(ruta).st_mtime
    except OSError:
        return None


def _revisar(kb, objetos, reglas, cambiados, guardar, log, origen):
    conf = configuracion.cargar()
    lista = reglas_activas(conf, reglas)
    ctx = Contexto(kb, conf)
    lb = lineabase.LineaBase(kb)
    res = {"kb": kb.nombre, "origen": origen, "inicio": dt.datetime.now().isoformat(timespec="seconds"),
           "modo": "objetos" if objetos else ("cambiados" if cambiados else "completa"),
           "reglas": [r.id for r in lista], "pedidos": list(objetos or []), "revisados": 0, "ignorados": [],
           "hallazgos": [], "excepcionados": [], "errores": [], "avisos": list(conf.avisos),
           "lineaBase": lb.actualizada}
    existentes = None
    if objetos:
        fechas = {}
        for o in objetos:
            r = fuente.ubicar(kb, o)
            if r is None:
                res["errores"].append({"objeto": o, "error": "no encuentro su especificacion (.sp0): ¿esta especificado?"})
            else:
                fechas[str(r)] = _mtime(r)
    else:
        actuales = fuente.listar(kb)
        if cambiados and lb.existe:
            rutas = lb.cambiados(actuales)
        else:
            if cambiados:
                res["avisos"].append("la KB no tenia linea base: se reviso entera y se armo")
                res["modo"] = "completa"
            rutas = [r for r, _ in actuales]
        existentes = dict(actuales)
        fechas = {r: existentes[r] for r in rutas}  # ruta -> mtime de lo que se mira
    huellas, nuevas = {}, {}  # objeto -> huellas de lo revisado / las que introdujo su ultimo cambio
    for i, (ruta, mt) in enumerate(fechas.items()):
        if log and i and i % 500 == 0:
            log(f"  {i} de {len(fechas)} objetos...")
        try:
            fu = fuente.leer(ruta)
        except Exception as e:
            res["errores"].append({"objeto": Path(ruta).stem, "error": f"no se pudo leer la especificacion: {e}"})
            continue
        if not fu.nombre or fu.tipo == "sdt":
            continue
        if not objetos:  # pedido por nombre se revisa aunque este en 'ignorar'
            motivo = conf.ignorado(fu)
            if motivo:
                res["ignorados"].append({"objeto": fu.nombre, "motivo": motivo})
                continue
        res["revisados"] += 1
        hs, exc, hu, errs = revisar_fuente(fu, lista, ctx, conf, lb, lb.cambio(ruta, mt))
        res["hallazgos"] += hs
        res["excepcionados"] += exc
        res["errores"] += errs
        huellas[fu.nombre] = hu
        nuevas[fu.nombre] = [h["huella"] for h in hs + exc if h["nuevo"]]
    res["fin"] = dt.datetime.now().isoformat(timespec="seconds")
    res["totales"] = {s: sum(1 for h in res["hallazgos"] if h["severidad"] == s) for s in SEVERIDADES}
    res["nuevos"] = {s: sum(1 for h in res["hallazgos"] if h["severidad"] == s and h["nuevo"]) for s in SEVERIDADES}
    res["porRegla"] = {}
    for h in res["hallazgos"]:
        res["porRegla"][h["regla"]] = res["porRegla"].get(h["regla"], 0) + 1
    # Solo una revision con todas las reglas activas y sin --objeto deja la linea base al dia.
    if not objetos and not reglas:
        lb.actualizar(fechas, huellas, nuevas, completa=res["modo"] == "completa", existentes=existentes)
        lb.guardar()
        res["lineaBaseActualizada"] = True
    # Un build que no volvio a especificar nada no deja un archivo vacio.
    if guardar and (res["revisados"] or res["errores"] or res["modo"] != "cambiados"):
        res["archivo"] = str(_guardar(res))
    return res


def _guardar(res):
    DIR.mkdir(parents=True, exist_ok=True)
    marca = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    p = DIR / f"{marca}_{res['kb'].replace('/', '_').lower()}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    viejas = sorted(DIR.glob("*.json"))
    for v in viejas[:-MAX_GUARDADAS]:
        try:
            v.unlink()
        except OSError:
            pass
    return p
