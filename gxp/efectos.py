"""Efectos de un objeto segun su Java generado: si escribe en la base, hace commit o rollback, o tiene
efectos fuera de la base (HTTP, mail, archivos, shell, submit). Recorre el Java del objeto y, transitivamente,
el de todo lo que llama (tambien en otras KBs, por el namespace del paquete).

Lo usan la generacion de suites (solo entran los objetos sin efectos) y las corridas de los casos 'auto'
(no se ejecuta un objeto que dejo de ser de solo lectura).
"""
import re
import threading
import time
from pathlib import Path

from . import kbs

MARCAS = {
    "commit": re.compile(r"commitDataStores|\.prccommit\b"),
    "escribe": re.compile(r"\bUpdateCursor\b"),
    "rollback": re.compile(r"rollbackDataStores|\.prcrollback\b"),
    "http": re.compile(r"com\.genexus\.internet\.HttpClient\b|GXRestAPIClient|SoapHTTPClient|java\.net\.(URL|Socket|HttpURLConnection)\b"),
    "mail": re.compile(r"GXMailMessage|SMTPSession|POP3Session"),
    "archivo": re.compile(r"com\.genexus\.util\.GX(File|Directory)\b|FileOutputStream|FileWriter|ExcelDocument|com\.genexus\.reports"),
    "shell": re.compile(r"GXutil\.shell|Runtime\.getRuntime\(\)\.exec|ProcessBuilder"),
    "submit": re.compile(r"\.submit\s*\(|executeSubmit|submitImpl"),
}
_REF = re.compile(r"\bcom\.[a-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)+")


_USA_DS = re.compile(r"\bpr_([a-z0-9_]+)\.execute\(")


def _datastores_remotos(kb):
    """Nombres de los datastores de la KB cuyo DBMS no es MySQL, segun su client.cfg."""
    salida = set()
    for cfg in sorted(kb.clases.glob("com/*/client.cfg"))[:1]:
        actual = None
        for linea in cfg.read_text(encoding="latin-1", errors="replace").splitlines():
            linea = linea.strip()
            if linea.startswith("[") and linea.endswith("]"):
                actual = linea[1:-1].split("|")[1].upper() if "|" in linea else None
            elif actual and linea.upper().startswith("DBMS=") and linea[5:].strip().lower() not in ("mysql", "sqlite"):
                salida.add(actual)
    return salida


def separar(efectos):
    """(efectos fuera de leer la base, datastores remotos que lee) de lo que devuelve Analisis.efectos."""
    return ({m: c for m, c in efectos.items() if not m.startswith("ds:")},
            sorted(m[3:] for m in efectos if m.startswith("ds:")))


def _mtime(f):
    try:
        return f.stat().st_mtime_ns
    except OSError:
        return 0


class Analisis:
    """Marcas (escribe, commit, http...) de cada clase, con todo lo que alcanza por llamadas."""
    VIGENCIA = 60  # segundos durante los que no se vuelve a mirar si cambio un archivo ya leido

    def __init__(self):
        self.por_ns = {}
        self.remotas = set()  # datastores que no son MySQL (AS400, SQL Server): datos compartidos que cambian solos
        for k in kbs.descubrir().values():
            if k.ns and "/" not in k.nombre and "_fixes" not in k.nombre.lower():
                self.por_ns.setdefault(k.ns, k)
            self.remotas |= _datastores_remotos(k)
        self._info = {}      # ruta -> (marcas, refs, fechas de los archivos, cuando se reviso)

    def _archivo(self, fqn, kb):
        rel = Path(*fqn.split(".")).with_suffix(".java")
        cands = [kb.fuentes / rel]
        duena = self.por_ns.get(".".join(fqn.split(".")[:2]))
        if duena and duena is not kb:
            cands.append(duena.fuentes / rel)
        return next((c for c in cands if c.exists()), None)

    def _leer(self, ruta, kb):
        """(marcas, refs) de una clase. Se relee si cambio el archivo (revisando la fecha cada VIGENCIA s)."""
        p = Path(ruta)
        archivos = (p, p.with_name(p.stem + "_impl.java"))
        previo = self._info.get(ruta)
        if previo and time.time() - previo[3] < self.VIGENCIA:
            return previo[:2]
        fechas = tuple(_mtime(f) for f in archivos)
        if previo and previo[2] == fechas:
            self._info[ruta] = (*previo[:3], time.time())
            return previo[:2]
        textos = []
        for f in archivos:
            try:
                textos.append(f.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
        t = "\n".join(textos)
        marcas = {m for m, rx in MARCAS.items() if rx.search(t)}
        marcas |= {"ds:" + d.upper() for d in _USA_DS.findall(t) if d.upper() in self.remotas}
        refs = set()
        for r in set(_REF.findall(t)):
            if r.startswith("com.genexus"):
                continue
            partes = r.split(".")
            for i in range(len(partes), 2, -1):  # la referencia puede seguir con .metodo o .campo
                a = self._archivo(".".join(partes[:i]), kb)
                if a:
                    if a != p:
                        refs.add(str(a))
                    break
        self._info[ruta] = (marcas, refs, fechas, time.time())
        return marcas, refs

    def efectos(self, kb, objeto):
        """{marca: clase donde aparece} de todo lo alcanzable desde el objeto."""
        inicio = kb.fuente_java(objeto)
        if not inicio.exists():
            return {"sin_java": inicio.stem}
        vistos, pila, motivo = set(), [str(inicio)], {}
        while pila:
            r = pila.pop()
            if r in vistos:
                continue
            vistos.add(r)
            marcas, refs = self._leer(r, kb)
            for m in marcas:
                motivo.setdefault(m, Path(r).stem)
            pila.extend(refs - vistos)
        return motivo


_compartido = None
_lock_compartido = threading.Lock()


def revalidar():
    """Al empezar una corrida: lo ya leido se vuelve a comparar con la fecha de los archivos (pudo haber un build)."""
    with _lock_compartido:
        if _compartido:
            for k, v in _compartido._info.items():
                _compartido._info[k] = (*v[:3], 0)


def efectos_actuales(kb, objeto):
    """Lo que hace hoy el objeto fuera de leer la base ({marca: clase}), segun el Java actual. Lo usan las
    corridas de los casos 'auto' para no ejecutar un objeto que dejo de ser de solo lectura."""
    global _compartido
    with _lock_compartido:
        if _compartido is None:
            _compartido = Analisis()
        return _compartido.efectos(kb, objeto)
