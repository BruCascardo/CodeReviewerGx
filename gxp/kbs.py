"""Descubrimiento de KBs, lectura de su client.cfg (namespace y datasources) y firma de su build."""
import hashlib
import os
import re
from pathlib import Path

from .config import CFG


class KB:
    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.nombre = carpeta.name
        self.web = carpeta / "JavaModel" / "web"
        self.clases = self.web / "build" / "classes" / "java" / "main"
        self.libs = self.web / "build" / "libs"
        self.fuentes = self.web / "src" / "main" / "java"
        self.ns = None
        self.datasources = []  # [{"nombre": "GENERALES", "base": "generales"}]
        self._leer_cfg()

    def _leer_cfg(self):
        cfgs = sorted(self.clases.glob("com/*/client.cfg")) or sorted(self.clases.rglob("client.cfg"))
        if not cfgs:
            return
        texto = cfgs[0].read_text(encoding="latin-1", errors="replace")
        m = re.search(r"^NAME_SPACE=\s*(\S+)", texto, re.M)
        self.ns = m.group(1) if m else None
        secciones = {}
        actual = None
        for linea in texto.splitlines():
            linea = linea.strip()
            if linea.startswith("[") and linea.endswith("]"):
                actual = linea[1:-1]
                secciones[actual] = {}
            elif actual and "=" in linea:
                k, v = linea.split("=", 1)
                secciones[actual][k.strip()] = v.strip()
        nombres = []
        for k, v in (secciones.get(self.ns) or {}).items():
            if re.fullmatch(r"DataSource\d+", k):
                nombres.append((int(k[10:]), v))
        for _, n in sorted(nombres):
            sec = secciones.get(f"{self.ns}|{n}", {})
            self.datasources.append({"nombre": n, "base": sec.get("CS_DBNAME", "")})

    @property
    def valida(self):
        return self.ns is not None and self.clases.exists()

    def clase_java(self, objeto: str) -> str:
        """Nombre de la clase Java de un objeto GeneXus (Generales.Interfases.Registro.Set -> com.generales.generales.interfases.registro.set)."""
        return f"{self.ns}.{objeto.lower()}"

    def fuente_java(self, objeto: str) -> Path:
        return self.fuentes.joinpath(*self.clase_java(objeto).split(".")).with_suffix(".java")

    def firma_build(self) -> str:
        """Cambia cada vez que GeneXus compila la KB: el compileJava de Gradle reescribe su marcador cuando
        compila algo, o cambia algun .jar de build/libs. Es estable entre procesos: se puede guardar en disco.
        La usan el motor (para reiniciarse), el grafo (para rearmarse) y la vigilancia de builds."""
        partes = []
        try:
            partes.append((self.web / "build" / "tmp" / "compileJava" / "previous-compilation-data.bin").stat().st_mtime_ns)
        except OSError:
            partes.append(0)
        try:
            for e in sorted(os.scandir(self.libs), key=lambda e: e.name):
                if e.name.endswith(".jar"):
                    st = e.stat()
                    partes.append((e.name, st.st_size, st.st_mtime_ns))
        except OSError:
            pass
        return hashlib.sha1(repr(partes).encode()).hexdigest()

    def resumen(self):
        return {
            "nombre": self.nombre,
            "carpeta": str(self.carpeta),
            "ns": self.ns,
            "datasources": self.datasources,
            "compilada": self.clases.exists(),
        }


_cache = {}


def descubrir(refrescar=False):
    if _cache and not refrescar:
        return _cache
    _cache.clear()
    for raiz in CFG["raicesKB"]:
        r = Path(raiz)
        if not r.exists():
            continue
        candidatas = [r] + [p for p in r.glob("*") if p.is_dir()] + [p for p in r.glob("*/*") if p.is_dir()]
        for c in candidatas:
            if (c / "JavaModel" / "web" / "build" / "classes" / "java" / "main").exists():
                kb = KB(c)
                if kb.valida:
                    nombre = kb.nombre
                    if nombre in _cache:  # mismo nombre en otra raiz
                        nombre = f"{c.parent.name}/{c.name}"
                        kb.nombre = nombre
                    _cache[nombre] = kb
    return _cache


def principales():
    """Las KBs sin las repetidas: si dos raices tienen una KB con el mismo nombre, la segunda se llama
    'raiz/KB' (ver descubrir) y no se incluye."""
    return [k for k in descubrir().values() if "/" not in k.nombre]


def obtener(nombre: str) -> KB:
    kbs = descubrir()
    if nombre in kbs:
        return kbs[nombre]
    for k, v in kbs.items():
        if k.lower() == (nombre or "").lower():
            return v
    kbs = descubrir(refrescar=True)
    if nombre in kbs:
        return kbs[nombre]
    raise KeyError(f"No encuentro la KB '{nombre}'. Disponibles: {', '.join(sorted(kbs)) or 'ninguna'}")
