"""Estado general, KBs, motores y ayuda."""
from ..rutas import ErrorApi, kb, ruta
from ... import VERSION, automatico, comparacion, compartido, kbs, motor, suites
from ...config import CFG


@ruta("GET", "/api/estado")
def estado(_q, _b):
    return {
        "version": VERSION,
        "kbs": [k.resumen() for k in kbs.descubrir().values()],
        "motores": [m.info() for m in motor.motores()],
        "opcionesSuite": CFG["opcionesSuite"],
        "automatico": automatico.estado(),
        "compartido": {"activo": compartido.activo(), "base": compartido.descripcion(), "error": compartido.ultimo_error()},
    }


@ruta("GET", "/api/kbs")
def listar_kbs(q, _b):
    return [k.resumen() for k in kbs.descubrir(refrescar=bool(q.get("refrescar"))).values()]


@ruta("POST", "/api/motor")
def accion_motor(_q, b):
    m = motor.motor(kb(b.get("kb")))
    acc = b.get("accion")
    if acc in ("detener", "reiniciar"):
        m.detener("pedido desde la interfaz")
    if acc in ("iniciar", "reiniciar"):
        try:
            m.iniciar()
        except motor.MotorError as e:
            raise ErrorApi(str(e), 500)
    return m.info()


@ruta("GET", "/api/motor/log")
def log_motor(q, _b):
    m = motor.motor(kb(q.get("kb")))
    return {"info": m.info(), "log": m.cola_log(int(q.get("n") or 300))}


@ruta("GET", "/api/ayuda")
def ayuda(_q, _b):
    return {"operadores": comparacion.descripcion_operadores(), "docSuite": suites.__doc__, "docComparar": comparacion.__doc__}
