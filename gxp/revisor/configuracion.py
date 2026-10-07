"""revisor.json (o, con la base compartida activa, su documento config/revisor): que reglas corren, con que
severidad y parametros, que objetos no se revisan y las excepciones (cada una con su motivo)."""
import fnmatch
import json

from .. import compartido
from ..config import RAIZ

ARCHIVO = RAIZ / "revisor.json"

DEFECTO = {
    # Objetos que no se revisan (nombre completo, con comodines * y ?; sin distinguir mayusculas).
    "ignorar": [],
    # Los objetos que genera un pattern (WorkWithPlus): vienen con gxtest_ignoreForTestCoverage = -1.
    "ignorarGeneradosPorPattern": True,
    # Por regla: {"activa": true, "severidad": "error" | "advertencia", ...parametros de la regla}
    "reglas": {},
    # [{"regla": "sin-commit-rollback", "objeto": "*.prcCommit", "kb": "opcional", "motivo": "obligatorio"}]
    "excepciones": [],
}


class Configuracion:
    def __init__(self, datos=None, origen=None):
        d = json.loads(json.dumps(DEFECTO))
        for k, v in (datos or {}).items():
            d[k] = v
        self.origen = origen
        self.ignorar = [p.lower() for p in d.get("ignorar") or []]
        self.ignorar_pattern = bool(d.get("ignorarGeneradosPorPattern", True))
        self.reglas = d.get("reglas") or {}
        self.avisos = []
        self.excepciones = []
        for i, e in enumerate(d.get("excepciones") or []):
            if not isinstance(e, dict) or not e.get("regla") or not e.get("objeto"):
                self.avisos.append(f"revisor.json: excepcion {i + 1}: le falta 'regla' u 'objeto'; no se aplica")
            elif not str(e.get("motivo", "")).strip():
                self.avisos.append(f"revisor.json: excepcion {i + 1} ({e['regla']} / {e['objeto']}): le falta el 'motivo'; no se aplica")
            else:
                self.excepciones.append(e)

    def ignorado(self, fu):
        """Motivo por el que el objeto no se revisa, o None."""
        n = fu.nombre.lower()
        for p in self.ignorar:
            if fnmatch.fnmatchcase(n, p):
                return f"coincide con '{p}' de 'ignorar'"
        if self.ignorar_pattern and fu.generado_por_pattern:
            return "generado por un pattern"
        if fu.es_bc:
            return "Business Component de una transaccion (se revisa la transaccion)"
        return None

    def excepcion(self, h):
        """La excepcion que cubre al hallazgo, o None."""
        for e in self.excepciones:
            if e["regla"] not in (h.regla, "*"):
                continue
            if e.get("kb") and e["kb"].lower() != (h.kb or "").lower():
                continue
            if e.get("linea") and int(e["linea"]) != h.linea:
                continue
            if fnmatch.fnmatchcase(h.objeto.lower(), e["objeto"].lower()):
                return e
        return None


def cargar():
    if compartido.activo():
        try:
            doc = compartido.leer(compartido.CONFIG, "revisor")
        except KeyError:
            return Configuracion(origen="base compartida (sin configuracion del revisor)")
        conf = Configuracion(doc["datos"], origen=f"base compartida (version {doc['version']}, {doc['por']}, {doc['actualizado']})")
        local = None
        try:
            local = json.loads(ARCHIVO.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        if local is not None and local != doc["datos"]:
            conf.avisos.append("revisor.json local no se usa y es distinto del de la base compartida: los cambios se "
                               "hacen con 'python gxpruebas.py compartido editar revisor'")
        return conf
    if not ARCHIVO.exists():
        return Configuracion(origen=None)
    try:
        datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"revisor.json invalido: {e}")
    return Configuracion(datos, origen=ARCHIVO)
