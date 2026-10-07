"""Pantalla Explorar y SQL: catalogo de objetos, detalle, describir, ejecutar y consultas."""
from ..rutas import ErrorApi, kb, mensaje, ruta
from ... import campos, catalogo, motor, plan, suites


@ruta("GET", "/api/objetos")
def objetos(q, _b):
    lista = catalogo.objetos(kb(q.get("kb")), solo_ejecutables=q.get("todos") != "1")
    return [{k: o[k] for k in ("nombre", "descripcion", "tipo", "ejecutable", "parametros", "warnings", "errores")} for o in lista]


@ruta("GET", "/api/objeto")
def objeto(q, _b):
    k = kb(q.get("kb"))
    try:
        info = catalogo.buscar(k, q.get("nombre", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    fuente = k.fuente_java(info["nombre"])
    return {**info, **catalogo.detalle(info["nvg"]), "claseJava": k.clase_java(info["nombre"]), "fuenteJava": str(fuente),
            "existeFuente": fuente.exists(), "haceCommit": catalogo.hace_commit(k, info["nombre"])}


@ruta("GET", "/api/describir")
def describir(q, _b):
    try:
        d = motor.describir(kb(q.get("kb")), q.get("nombre", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    except motor.NoEjecutable as e:
        raise ErrorApi(str(e), 409)
    return {"parametros": d["parametros"], "plantillaEntrada": d["plantillaEntrada"], "aviso": d["aviso"]}


@ruta("GET", "/api/campos")
def ayuda_campos(q, _b):
    """Dominio enumerado o tabla de la que es clave cada campo de la entrada (para los combos del formulario)."""
    try:
        return campos.de_objeto(kb(q.get("kb")), q.get("nombre", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("POST", "/api/valoresClave")
def valores_clave(_q, b):
    """Valores que existen en la base para un campo que es la clave de una tabla."""
    try:
        return campos.valores(kb(b.get("kb")), b.get("atributo", ""), b.get("filtros"), b.get("buscar", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    except motor.MotorError as e:
        raise ErrorApi(str(e), 400)


@ruta("POST", "/api/plan")
def plan_ejecucion(_q, b):
    """Plan de ejecucion (EXPLAIN) de las sentencias SQL del objeto, con recomendaciones."""
    try:
        return plan.calcular(kb(b.get("kb")), b.get("nombre", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    except plan.SinFuente as e:
        raise ErrorApi(str(e), 409)
    except motor.MotorError as e:
        raise ErrorApi(str(e), 400)


@ruta("POST", "/api/ejecutar")
def ejecutar(_q, b):
    return suites.ejecutar_suelto(kb(b.get("kb")), b.get("objeto"), b.get("entrada"), b.get("sql"),
                                  b.get("transaccion", "rollback"), b.get("variables"), b.get("opciones"), b.get("timeoutMs"))


@ruta("POST", "/api/sql")
def sql(_q, b):
    r, datos = motor.consulta_suelta(kb(b.get("kb")), b.get("ds", ""), b.get("query", ""), int(b.get("timeoutMs") or 60000),
                                     int(b.get("max") or 1000), confirmar=bool(b.get("confirmar")))
    if not r.get("ok"):
        raise ErrorApi(r.get("error") or "Error de SQL", 400)
    return {**datos, "ms": r.get("ms")}
