"""Reglas de buenas practicas.

Cada regla es una clase en un archivo de esta carpeta, registrada con @registrar. Para agregar una buena
practica nueva alcanza con un archivo nuevo (y, si tiene parametros, su entrada en revisor.json): el revisor
carga todos los modulos de la carpeta.

    @registrar
    class MiRegla(Regla):
        id = "mi-regla"                     # el que se usa en revisor.json, en las excepciones y en --regla
        titulo = "Una linea que diga que controla"
        severidad = "error"                 # o "advertencia"; revisor.json la puede cambiar
        parametros = {"umbral": 3}          # valores por defecto; revisor.json los puede pisar

        def aplica(self, fu, ctx):          # True si la regla tiene sentido para el objeto
            return fu.tipo == "proc"

        def revisar(self, fu, ctx):         # genera los hallazgos
            for s in fu.sentencias:
                if ...:
                    yield self.hallazgo(fu, s, "Que esta mal", detalle="Por que lo marco y como se arregla")

'fu' es un fuente.Fuente (sentencias, parametros, variables, propiedades) y 'ctx' un revisor.Contexto
(la KB, el Java generado, el fuente de otros objetos).
"""
import hashlib
import importlib
import pkgutil
from dataclasses import asdict, dataclass, field

SEVERIDADES = ("error", "advertencia")

REGLAS = {}  # id -> clase


@dataclass
class Hallazgo:
    regla: str
    severidad: str
    kb: str
    objeto: str
    tipo: str
    linea: int            # 0 si es de una propiedad del objeto y no de una linea
    mensaje: str
    codigo: str = ""      # la sentencia GX, reconstruida
    detalle: str = ""     # por que se marco y como se arregla
    huella: str = ""      # identifica el hallazgo aunque se muevan las lineas (nuevo / preexistente)
    datos: dict = field(default_factory=dict)

    def dict(self):
        return asdict(self)


class Regla:
    id = ""
    titulo = ""
    severidad = "error"
    parametros = {}

    def __init__(self, conf=None):
        conf = dict(conf or {})
        self.activa = conf.pop("activa", True)
        sev = conf.pop("severidad", self.severidad)
        self.severidad = sev if sev in SEVERIDADES else self.severidad
        self.conf = {**self.parametros, **conf}

    def aplica(self, fu, ctx):
        return True

    def revisar(self, fu, ctx):
        return []

    def hallazgo(self, fu, sentencia, mensaje, detalle="", severidad=None, ctx=None, **datos):
        """Hallazgo sobre una sentencia (o sobre el objeto si sentencia es None)."""
        codigo = sentencia.texto if sentencia is not None else ""
        linea = sentencia.linea if sentencia is not None else 0
        base = f"{self.id}|{fu.nombre.lower()}|{' '.join(codigo.split()).lower() or mensaje.lower()}"
        return Hallazgo(regla=self.id, severidad=severidad or self.severidad, kb=getattr(ctx, "kb_nombre", ""),
                        objeto=fu.nombre, tipo=fu.tipo_texto, linea=linea, mensaje=mensaje, codigo=codigo,
                        detalle=detalle, huella=hashlib.sha1(base.encode("utf-8")).hexdigest()[:16], datos=datos)


def registrar(cls):
    if not cls.id:
        raise ValueError(f"La regla {cls.__name__} no tiene id")
    if cls.id in REGLAS and REGLAS[cls.id] is not cls:
        raise ValueError(f"Hay dos reglas con el id '{cls.id}'")
    REGLAS[cls.id] = cls
    return cls


def cargar():
    """Importa todos los modulos de esta carpeta (cada uno registra sus reglas). Devuelve REGLAS."""
    for m in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{m.name}")
    return REGLAS
