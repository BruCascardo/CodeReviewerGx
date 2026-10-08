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


@ruta("GET", "/api/campos/filtros")
def filtros_clave(q, _b):
    """Funciones, tablas hijas y atributos con los que se arma una ${existente.X|...} sin escribirla."""
    try:
        return campos.filtros(kb(q.get("kb")), q.get("atributo", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("GET", "/api/campos/tabla")
def atributos_tabla(q, _b):
    """Atributos de una tabla relacionada, para poner condiciones sobre ella en el armador."""
    try:
        return campos.atributos_de(kb(q.get("kb")), q.get("tabla", ""), q.get("datastore"))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("POST", "/api/campos/mismaFila")
def misma_fila(_q, b):
    """Las ${variables} de todas las partes de una clave compuesta, para que sean de la misma fila."""
    try:
        return campos.misma_fila(kb(b.get("kb")), b.get("expresion", ""))
    except ValueError as e:
        raise ErrorApi(str(e), 400)


@ruta("POST", "/api/campos/completar")
def completar(_q, b):
    """Las ${variables} de las otras partes de la clave (con «misma fila») y de los demas campos de la entrada que
    salen de esa fila o de una tabla de sus condiciones (el CuponId de una cuota que esta en un cupon en proceso)."""
    try:
        return campos.completar(kb(b.get("kb")), b.get("expresion", ""), bool(b.get("mismaFila")), b.get("hermanos") or [])
    except ValueError as e:
        raise ErrorApi(str(e), 400)


@ruta("POST", "/api/variables/previsualizar")
def previsualizar(_q, b):
    """Lo que daria hoy cada ${variable} (fechas relativas, ${existente.X|...}...): [{hoy} o {error}]."""
    return campos.previsualizar(kb(b.get("kb")), b.get("expresiones") or [], b.get("variables"), b.get("sqlPrevio"))


@ruta("POST", "/api/validaciones")
def validaciones(_q, b):
    """Filas de validacion de un objeto a partir de una entrada valida, con lo que devuelve hoy cada una."""
    try:
        return suites.validaciones.proponer(kb(b.get("kb")), b.get("objeto", ""), b.get("entrada") or {},
                                            b.get("sqlPrevio"), b.get("timeoutMs"))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)
    except motor.MotorError as e:
        raise ErrorApi(str(e), 400)


@ruta("POST", "/api/validaciones/caso")
def validaciones_caso(_q, b):
    """El caso con las filas elegidas (con lo que se espera de cada una, quizas corregido a mano)."""
    return suites.validaciones.armar_caso(b.get("objeto", ""), b.get("entrada") or {}, b.get("columnas") or {},
                                          b.get("filas") or [], b.get("nombre"), b.get("rutaSalida"))


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
                                  b.get("transaccion", "rollback"), b.get("variables"), b.get("opciones"), b.get("timeoutMs"),
                                  b.get("sqlPrevio"))


@ruta("POST", "/api/sql")
def sql(_q, b):
    r, datos = motor.consulta_suelta(kb(b.get("kb")), b.get("ds", ""), b.get("query", ""), int(b.get("timeoutMs") or 60000),
                                     int(b.get("max") or 1000), confirmar=bool(b.get("confirmar")))
    if not r.get("ok"):
        raise ErrorApi(r.get("error") or "Error de SQL", 400)
    return {**datos, "ms": r.get("ms")}
