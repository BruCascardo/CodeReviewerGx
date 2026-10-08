"""Indices de clases para el grafo: que objeto es cada clase Java, las referencias que tiene cada archivo
(recordadas en disco por fecha y tamano) y los modulos publicados (.jar de build/libs) de cada namespace."""
import os
import re
import zipfile
from pathlib import Path

from .. import catalogo
from ..config import CACHE
from ..util import escribir_json, leer_json, recorrer
from .servicios import firma as firma_servicios, literales as literales_servicio

DIR = CACHE / "grafo"
_REF = re.compile(r"\bcom\.[a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_$]+)+")
_REF_BYTES = re.compile(rb"com/[a-z][A-Za-z0-9_]*(?:/[A-Za-z0-9_$]+)+")
_SUFIJOS = ("_restinterfacein", "_restinterfaceout", "_restinterface", "_services_rest", "_impl", "_bc")


# ---------------------------------------------------------------------- nombres de clase -> objeto

def _base_clase(nombre, clases_paquete):
    """Nombre de clase Java (sin paquete) -> (nombre base del objeto, es_sdt). None si no es de un objeto."""
    nombre = nombre.split("$")[0]
    if nombre.startswith("StructSdt"):
        nombre = nombre[6:]
    if nombre.startswith("Sdt"):
        n = nombre[3:]
        for suf in ("_RESTInterface", "_RESTInterfaceIN", "_RESTInterfaceOUT"):
            if n.endswith(suf):
                n = n[: -len(suf)]
        # StructSdtColinGet es la coleccion de SdtinGet.
        if n.startswith("Col") and ("Sdt" + n[3:]) in clases_paquete:
            n = n[3:]
        # SdtoutGet_Moneda es un item de SdtoutGet: se recorta mientras exista la clase de arriba.
        while "_" in n and ("Sdt" + n.rsplit("_", 1)[0]) in clases_paquete:
            n = n.rsplit("_", 1)[0]
        return n, True
    b = nombre.lower()
    if "__" in b:  # cursores: get__generales
        b = b.split("__")[0]
    for suf in _SUFIJOS:
        if b.endswith(suf):
            b = b[: -len(suf)]
            break
    if not b or b[0].isdigit():
        return None
    if b.startswith("gxdomain"):  # dominio enumerado
        return "dom:" + b[8:], False
    if b.startswith("gx") or b in ("soapparm",):  # clases propias de GeneXus (gxcfg, gxapplication...)
        return None
    return b, False


class Indice:
    """Clases de un conjunto (fuentes de una KB o un .jar): paquete -> {clase}."""

    def __init__(self):
        self.paquetes = {}

    def agregar(self, fqn):
        paq, _, cls = fqn.rpartition(".")
        self.paquetes.setdefault(paq, set()).add(cls)

    def existe(self, fqn):
        paq, _, cls = fqn.rpartition(".")
        return cls in self.paquetes.get(paq, ())

    def objeto(self, fqn):
        """fqn de clase -> (clave del objeto 'paquete.base' en minusculas, nombre base original, es_sdt) o None."""
        paq, _, cls = fqn.rpartition(".")
        r = _base_clase(cls, self.paquetes.get(paq, ()))
        if not r:
            return None
        base, es_sdt = r
        return (f"{paq}.{'sdt:' if es_sdt else ''}{base.lower()}", base, es_sdt)


def resolver(ref, indices):
    """Referencia de texto (com.x.y.Clase.metodo) -> (indice, fqn de la clase) recortando hasta encontrarla."""
    partes = ref.split(".")
    for i in range(len(partes), 2, -1):
        fqn = ".".join(partes[:i])
        for ix in indices:
            if ix.existe(fqn):
                return ix, fqn
    return None, None


# ---------------------------------------------------------------------- lectura de fuentes con memoria

class MemoriaArchivos:
    """Referencias de cada archivo y los ids de servicio que usa (ver servicios.py), recordados por fecha y
    tamano (en disco, entre corridas). Si cambian los servicios conocidos, se vuelven a leer todos."""

    def __init__(self, nombre, servicios=frozenset()):
        self.ruta = DIR / f"refs-{nombre}.json"
        self.servicios = servicios
        self.firma_srv = firma_servicios(servicios)
        d = leer_json(self.ruta, {})
        self.datos = d.get("archivos", {}) if d.get("servicios") == self.firma_srv else {}
        self.usadas = set()
        self.cambios = 0 if self.datos or not d else 1

    def leer(self, ruta, st):
        """(referencias a clases, ids de servicio) de un archivo Java."""
        clave = str(ruta)
        self.usadas.add(clave)
        firma = f"{st.st_mtime_ns}:{st.st_size}"
        previo = self.datos.get(clave)
        if previo and previo[0] == firma:
            return previo[1], previo[2]
        try:
            texto = Path(ruta).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return [], []
        refs = sorted(set(_REF.findall(texto)))
        srv = literales_servicio(texto, self.servicios)
        self.datos[clave] = [firma, refs, srv]
        self.cambios += 1
        return refs, srv

    def guardar(self):
        viejas = set(self.datos) - self.usadas
        for k in viejas:
            del self.datos[k]
        if self.cambios or viejas:
            escribir_json(self.ruta, {"servicios": self.firma_srv, "archivos": self.datos})


def listar_java(raiz):
    """(fqn, ruta, stat) de cada .java debajo de raiz (el paquete sale de las carpetas)."""
    for ruta, rel, e in recorrer(raiz, ".java"):
        yield rel[:-5].replace(os.sep, "."), ruta, e.stat()


# ---------------------------------------------------------------------- modulos publicados (.jar)

def _version_jar(z):
    try:
        m = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except KeyError:
        return ""
    v = re.search(r"Implementation-Version:\s*(\S+)", m)
    return v.group(1) if v else ""


def _clave_version(v):
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]", v or "0"))


def jars_publicados(raiz_kbs):
    """{ns: (ruta del jar, version)}: para cada namespace de una KB, el .jar mas nuevo que hay en el build/libs
    de las KBs de la misma raiz (CORE o FIXES)."""
    nss = {k.ns for k in raiz_kbs if k.ns}
    mejores = {}
    for k in raiz_kbs:
        try:
            jars = [e for e in os.scandir(k.libs) if e.name.endswith(".jar") and e.name[0].isupper()]
        except OSError:
            continue
        for e in jars:
            try:
                with zipfile.ZipFile(e.path) as z:
                    nombres = [n for n in z.namelist() if n.endswith(".class")]
                    if not nombres:
                        continue
                    ns = ".".join(nombres[0].split("/")[:2])
                    if ns not in nss or "WWPBaseObjects" in e.name:
                        continue
                    v = _version_jar(z)
            except (OSError, zipfile.BadZipFile):
                continue
            # El modulo publicado de una KB se llama como la KB (Terceros.jar); otros jars del mismo
            # namespace (ServiciosCommon.jar) tambien cuentan.
            clave = (ns, e.name)
            if clave not in mejores or _clave_version(v) > _clave_version(mejores[clave][1]):
                mejores[clave] = (e.path, v)
    salida = {}
    for (ns, nombre), (ruta, v) in mejores.items():
        salida.setdefault(ns, []).append({"jar": nombre, "ruta": ruta, "version": v})
    return salida


def leer_jar(ruta):
    """(Indice, {clase fqn: [refs fqn]}) de un .jar, recordado en disco por fecha y tamano."""
    st = os.stat(ruta)
    firma = f"{st.st_mtime_ns}:{st.st_size}"
    cache = DIR / f"jar-{Path(ruta).parent.parent.parent.parent.parent.name}-{Path(ruta).stem}.json"
    d = leer_json(cache, {})
    datos = d.get("clases") if d.get("firma") == firma else None
    if datos is None:
        datos = {}
        with zipfile.ZipFile(ruta) as z:
            for n in z.namelist():
                if not n.endswith(".class"):
                    continue
                fqn = n[:-6].replace("/", ".")
                if "$" in fqn.rsplit(".", 1)[-1]:
                    fqn = fqn.split("$")[0]
                refs = {r.decode("ascii", "ignore").replace("/", ".") for r in _REF_BYTES.findall(z.read(n))}
                datos.setdefault(fqn, set()).update(refs)
        datos = {k: sorted(v) for k, v in datos.items()}
        escribir_json(cache, {"firma": firma, "clases": datos})
    ix = Indice()
    for fqn in datos:
        ix.agregar(fqn)
    return ix, datos


class Universo:
    """Las KBs de una raiz (CORE o FIXES): indices de sus fuentes y de sus modulos publicados."""

    def __init__(self, lista):
        self.kbs = {k.nombre: k for k in lista}
        self.por_ns = {}
        for k in lista:
            if k.ns:
                self.por_ns.setdefault(k.ns, k)
        self._fuentes = {}
        self._pub = None
        self._trn = {}

    def transacciones(self, kb):
        """Claves (paquete.nombre en minusculas) de las transacciones de la KB: su SDT es el Business Component."""
        if kb.nombre not in self._trn:
            self._trn[kb.nombre] = {kb.clase_java(o["nombre"]) for o in catalogo.objetos(kb) if o["tipo"] == "Transaction"}
        return self._trn[kb.nombre]

    def fuentes(self, kb):
        """(Indice de las clases locales, {fqn: (ruta, stat)})."""
        if kb.nombre not in self._fuentes:
            ix, archivos = Indice(), {}
            for fqn, ruta, st in listar_java(kb.fuentes):
                ix.agregar(fqn)
                archivos[fqn] = (ruta, st)
            self._fuentes[kb.nombre] = (ix, archivos)
        return self._fuentes[kb.nombre]

    def publicados(self):
        """{ns: [{jar, version, indice, clases}]}."""
        if self._pub is None:
            self._pub = {}
            for ns, jars in jars_publicados(self.kbs.values()).items():
                for j in jars:
                    try:
                        ix, clases = leer_jar(j["ruta"])
                    except (OSError, zipfile.BadZipFile):
                        continue
                    self._pub.setdefault(ns, []).append({**j, "indice": ix, "clases": clases})
        return self._pub

    def duena(self, fqn):
        return self.por_ns.get(".".join(fqn.split(".")[:2]))
