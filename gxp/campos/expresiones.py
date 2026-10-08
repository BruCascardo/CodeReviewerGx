"""Valores que las ${variables} de los casos calculan en la base al ejecutar, a partir de la clave de una tabla:

    ${siguiente.CuponId}                          el ultimo CuponId de cbhCupon, mas uno: uno que no existe
    ${existente.CuponId}                          el primero que existe (el de clave mas chica)
    ${ultimo.CuponId}                             el ultimo que existe
    ${existente.CuponId|CuponEstado=EN_PROCESO}   el primero que cumple las condiciones (separadas por coma)
    ${con_hijos.CuponId}                          uno que tiene filas en alguna tabla que lo referencia
    ${con_hijos.CuponId:cbhCuponDetalle}          ... en esa tabla
    ${sin_hijos.CuponId}                          uno que no tiene filas en ninguna (o, con :tabla, en esa)

Las condiciones son Atributo=valor (tambien !=, <, >, <=, >=) sobre atributos de la misma tabla. En un atributo de
un dominio enumerado se puede usar el nombre del valor (EN_PROCESO) en lugar del valor guardado (PRO). Un valor
entre comillas se toma como texto tal cual. Las tablas hijas son las que tienen toda la clave entre sus atributos
(los niveles subordinados y las que la referencian con una clave foranea).

Una condicion tambien puede ser sobre otra tabla relacionada, con el camino delante del atributo:

    ${existente.CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}
        una cuota que esta en algun detalle de cupon cuyo cupon esta en proceso
    ${existente.CargoCuotaNumero|!cbhCuponDetalle.CuponDetSec>0}
        con ! delante de una tabla: que no haya ninguna fila de esa tabla que cumpla (una cuota en ningun cupon)
    ${existente.CargoId|cbhCargoCuota.!cbhCuponDetalle.CuponDetSec>0}
        el ! puede ir en cualquier tabla del camino: un cargo con alguna cuota que no esta en ningun cupon
    ${existente.CargoCuotaNumero|cbhCuponDetalle}  /  ${existente.CargoCuotaNumero|!cbhAplicacion}
        solo el camino, sin condicion: que tenga (o, con !, que no tenga) alguna fila en esa tabla
    ${existente.CargoCuotaNumero|cbhCupon.CuponEstado=EN_PROCESO}
        con una sola tabla que no esta relacionada directamente: por el camino mas corto, si hay uno solo

Cada tabla del camino tiene que estar relacionada con la anterior (ver indice.relaciones). Las condiciones con el
mismo camino (y los mismos !) son sobre la misma fila: cbhCupon.CuponEstado=EN_PROCESO,cbhCupon.CuponTipo=LIQ es un
cupon en proceso y de liquidacion; las que comparten el principio del camino, sobre la misma fila de esas tablas.
Se resuelven con exists anidados, que usan la clave primaria (hacia arriba) o la clave foranea (hacia abajo).

Con la tabla delante del atributo, cualquier atributo de esa tabla (no solo el ultimo de la clave):

    ${existente.cbhCargoCuota.CargoId|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}
        el CargoId de la primera cuota que esta en un cupon en proceso

Asi misma_fila() completa las demas partes de una clave compuesta con la misma fila (ver la funcion).
"""
import itertools
import re
from collections import namedtuple
from decimal import Decimal

from .. import motor
from . import indice

FUNCIONES = ("siguiente", "existente", "ultimo", "con_hijos", "sin_hijos")
_EXISTE = re.compile(r"^\s*((?:!?\s*\w+\s*\.\s*)*!?\s*\w+)\s*$")  # solo el camino: que tenga alguna fila
_COND = re.compile(r"^\s*((?:!?\s*\w+\s*\.\s*)*)(\w+)\s*(<=|>=|!=|<>|=|<|>)\s*(.*?)\s*$")
_VARIABLE = re.compile(r"^\s*\$\{\s*(\w+)\.([\s\S]*)\}\s*$")
_IDENT = re.compile(r"^\w+$")


class Condicion(namedtuple("Condicion", "atributo op valor tablas negadas", defaults=((), ()))):
    """Atributo op valor. 'tablas' es el camino a otra tabla relacionada (vacio: la misma tabla) y 'negadas', por
    cada tabla del camino, si va con ! (que no haya ninguna fila de esa tabla que cumpla lo que sigue)."""

    def texto(self, separador=""):
        camino = ".".join(f"{'!' if n else ''}{x}" for x, n in zip(self.tablas, self.negadas))
        if not self.atributo:  # solo el camino
            return camino
        camino += "." if camino else ""
        op = "!=" if self.op == "<>" else self.op
        return f"{camino}{self.atributo}{separador}{op}{separador}{self.valor}"

    def __str__(self):
        return self.texto(" ")


def partir(texto):
    """'A=1,B=${x|C=2,D=3}' -> ['A=1', 'B=${x|C=2,D=3}']: corta en las comas de afuera de las ${...}."""
    partes, prof, actual = [], 0, []
    for i, ch in enumerate(texto):
        if ch == "$" and texto[i + 1:i + 2] == "{":
            prof += 1
        elif ch == "}" and prof:
            prof -= 1
        if ch == "," and not prof:
            partes.append("".join(actual))
            actual = []
        else:
            actual.append(ch)
    if "".join(actual).strip():
        partes.append("".join(actual))
    return partes


class Pedido:
    def __init__(self, funcion, atributo, hija="", condiciones=(), tabla=""):
        self.funcion = funcion
        self.atributo = atributo
        self.tabla = tabla                    # ${existente.cbhCargoCuota.CargoId}: la tabla, o "" (la de la clave)
        self.hija = hija                      # tabla hija de con_hijos / sin_hijos, o ""
        self.condiciones = list(condiciones)  # [Condicion] (el operador ya en SQL: != es <>)


def parsear(funcion, resto):
    """'CuponId:tabla|A=1,B=X' (o 'Tabla.Atributo|...') -> Pedido. ValueError si esta mal escrito."""
    if funcion not in FUNCIONES:
        raise ValueError(f"funcion desconocida '{funcion}': las que hay son {', '.join(FUNCIONES)}")
    cabeza, _, conds = resto.partition("|")
    atributo, _, hija = cabeza.partition(":")
    atributo, hija = atributo.strip(), hija.strip()
    tabla, _, solo = atributo.rpartition(".")
    tabla, atributo = tabla.strip(), solo.strip()
    if tabla and not _IDENT.match(tabla):
        raise ValueError(f"'{tabla}' no es un nombre de tabla: se escribe ${{{funcion}.Tabla.Atributo}}")
    if tabla and funcion == "siguiente":
        raise ValueError("siguiente es de la clave de una tabla: se escribe ${siguiente.Atributo}, sin la tabla")
    if not _IDENT.match(atributo):
        raise ValueError(f"falta el atributo: se escribe ${{{funcion}.Atributo}}")
    if hija and (funcion not in ("con_hijos", "sin_hijos") or not _IDENT.match(hija)):
        raise ValueError(f"':{hija}' solo va en con_hijos y sin_hijos, con el nombre de una tabla")
    condiciones = []
    for c in partir(conds) if conds.strip() else []:
        m = _COND.match(c)
        if not m and _EXISTE.match(c):
            segmentos = [x.replace(" ", "") for x in c.split(".")]
            condiciones.append(Condicion("", "", "", tuple(x.lstrip("!") for x in segmentos), tuple(x.startswith("!") for x in segmentos)))
            continue
        if not m:
            if c.strip().startswith("!"):
                raise ValueError(f"'{c.strip()}': el ! va delante de otra tabla (!tabla.Atributo=valor: que no tenga "
                                 "ninguna fila que cumpla); en la misma tabla, Atributo!=valor")
            raise ValueError(f"condicion invalida '{c.strip()}': se escribe Atributo=valor (o !=, <, >, <=, >=), "
                             "o tabla.Atributo=valor para otra tabla relacionada")
        segmentos = [x.replace(" ", "") for x in m[1].split(".") if x.strip()]
        tablas = tuple(x.lstrip("!") for x in segmentos)
        negadas = tuple(x.startswith("!") for x in segmentos)
        condiciones.append(Condicion(m[2], "<>" if m[3] == "!=" else m[3], m[4], tablas, negadas))
    if funcion == "siguiente" and condiciones:
        raise ValueError("siguiente no lleva condiciones: es el ultimo de toda la tabla, mas uno")
    return Pedido(funcion, atributo, hija, condiciones, tabla)


def _tabla(ix, p):
    """(Tabla, atributo como esta en ella) del pedido: la tabla nombrada o, si no, la de la que es la clave."""
    if p.tabla:
        t = ix.tabla(p.tabla, atributo=p.atributo)
        if t is None:
            raise ValueError(f"{p.tabla} no es una tabla de la KB")
        if not t.tiene(p.atributo):
            raise ValueError(f"{p.atributo} no es un atributo de {t.nombre}")
        return t, t.atributo(p.atributo)
    t = ix.tablas.get(p.atributo.lower())
    if t is None:
        raise ValueError(f"{p.atributo} no es la clave de ninguna tabla de la KB")
    return t, t.claves[-1]


def _literal_sql(ix, t, columna, valor):
    v = str(valor)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    else:
        dom = next((d for a, d in t.enumerados.items() if a.lower() == columna.lower()), None)
        nombre = next((e["valor"] for e in ix.valores.get(dom, []) if str(e["nombre"]).lower() == v.lower()), None)
        if nombre is not None:
            v = nombre
        # Un numero va sin comillas solo si el atributo es numerico (o no se sabe su tipo): comparar un char con un
        # numero hace que SQL Server convierta la columna y falle con los valores que no son numeros.
        tipo = t.tipos.get(t.atributo(columna) or columna, "")
        # En SQL Server, entre comillas sirve para las dos (convierte el texto al tipo de la columna): las tablas
        # externas pueden tener como texto un atributo que GeneXus ve numerico.
        if re.fullmatch(r"-?\d+(\.\d+)?", str(v)) and (not tipo or tipo in indice.NUMERICOS) and t.dbms != indice.SQLSERVER:
            return str(v)
    v = str(v).replace("\\", "\\\\") if t.dbms == indice.MYSQL else str(v)  # solo MySQL escapa con \\
    return "'" + v.replace("'", "''") + "'"


def hijas(ix, t, nombre=""):
    hs = ix.hijas(t)
    if nombre:
        elegidas = [h for h in hs if h.nombre.lower() == nombre.lower()]
        if not elegidas:
            otras = ", ".join(h.nombre for h in hs) or "ninguna"
            raise ValueError(f"{nombre} no tiene la clave de {t.nombre} (la tienen: {otras})")
        return elegidas
    return hs


def consulta(ix, p, invertir=False):
    """(tabla, select) del pedido. ValueError si no se puede armar. 'invertir': del otro extremo (el ultimo en vez
    del primero y al reves), para ver que cambia en la salida con otra fila que cumple lo mismo."""
    t, k = _tabla(ix, p)
    if p.funcion == "siguiente":
        if not t.numerica:
            raise ValueError(f"{k} es de tipo {t.tipo or 'desconocido'}: el siguiente solo se calcula para claves numericas")
        return t, f"select coalesce(max({t.col(k)}), 0) + 1 as valor from {t.ref}"
    donde, arbol = [], {}
    for c in p.condiciones:
        if not c.tablas:
            if not t.tiene(c.atributo):
                raise ValueError(f"{c.atributo} no es un atributo de {t.nombre}")
            donde.append(f"t.{t.col(c.atributo)} {c.op} {_literal_sql(ix, t, c.atributo, c.valor)}")
            continue
        camino, negadas = _camino(ix, t, c)
        nivel = arbol
        for paso, negada in zip(camino, negadas):
            nodo = nivel.setdefault((negada, paso[0].nombre.lower()), {"paso": paso, "negada": negada, "conds": [], "hijos": {}})
            nivel = nodo["hijos"]
        final = camino[-1][0]
        if not c.atributo:
            continue  # solo el camino: que tenga (o no) alguna fila
        if not final.tiene(c.atributo):
            raise ValueError(f"{c.atributo} no es un atributo de {final.nombre}")
        nodo["conds"].append((final.atributo(c.atributo), c.op, c.valor))
    alias = itertools.count(1)
    donde += [_existe(ix, nodo, "t", alias, t) for nodo in arbol.values()]
    if p.funcion in ("con_hijos", "sin_hijos"):
        hs = hijas(ix, t, p.hija)
        if not hs and p.funcion == "con_hijos":
            raise ValueError(f"ninguna tabla de la KB tiene la clave de {t.nombre}")
        subs = [f"exists (select 1 from {h.ref} h where " + " and ".join(f"h.{h.col(c)} = t.{t.col(c)}" for c in t.claves) + ")"
                for h in hs]
        if p.funcion == "con_hijos":
            donde.append("(" + " or ".join(subs) + ")")
        else:
            donde.extend("not " + s for s in subs)
    if t.datastore or k not in t.claves:
        # Un valor nulo no sirve de entrada: puede haberlo en un atributo que no es de la clave o en una tabla externa.
        donde.insert(0, f"t.{t.col(k)} is not null")
    orden = " desc" if (p.funcion == "ultimo") != invertir else ""
    q = f"select t.{t.col(k)} as valor from {t.ref} t"
    if donde:
        q += " where " + " and ".join(donde)
    return t, t.una_fila(q + " order by " + ", ".join(f"t.{t.col(c)}{orden}" for c in t.claves))


def _camino(ix, t, c):
    """(camino, negadas) de una condicion sobre otras tablas. Una tabla sola (por el camino mas corto) lleva su !
    en la primera del camino: que no tenga ninguna."""
    if not c.atributo and len(c.tablas) == 1 and ix.tabla(c.tablas[0]) is None and t.tiene(c.tablas[0]):
        raise ValueError(f"{c.tablas[0]} es un atributo de {t.nombre}: falta la condicion ({c.tablas[0]}=valor)")
    camino = ix.camino(t, c.tablas)
    negadas = c.negadas if len(c.negadas) == len(camino) else c.negadas[:1] + (False,) * (len(camino) - 1)
    return camino, tuple(negadas)


def _completo(ix, t, c):
    """La condicion con el camino entero (una tabla sola por el camino mas corto) y los nombres como en la KB."""
    if not c.tablas:
        return c._replace(atributo=t.atributo(c.atributo) or c.atributo)
    camino, negadas = _camino(ix, t, c)
    final = camino[-1][0]
    return c._replace(atributo=(final.atributo(c.atributo) or c.atributo) if c.atributo else "",
                      tablas=tuple(x[0].nombre for x in camino), negadas=tuple(negadas))


def _escribir(funcion, atributo, condiciones):
    conds = ",".join(c if isinstance(c, str) else c.texto() for c in condiciones)
    return f"${{{funcion}.{atributo}{'|' + conds if conds else ''}}}"


def misma_fila(ix, texto):
    """Las variables de todas las partes de la clave para que sean de la misma fila. Para
        ${existente.CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}
    da {CargoId: ${existente.cbhCargoCuota.CargoId|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO},
        CargoPlanSec: ${existente.cbhCargoCuota.CargoPlanSec|CargoId=${...},cbhCuponDetalle...},
        CargoCuotaNumero: ${existente.CargoCuotaNumero|CargoId=${...},CargoPlanSec=${...},cbhCuponDetalle...}}
    Cada parte sale de la misma tabla, de la primera (o la ultima) fila que cumple dentro de las partes anteriores:
    juntas, la primera (o la ultima) fila que cumple en el orden de la clave. Sirve para cualquier clave compuesta,
    aunque sus partes no sean tablas (el anio y el mes de un indice). con_hijos y sin_hijos pasan a existente con
    la condicion de tener (o no) filas en la tabla hija. ValueError si no se puede."""
    m = _VARIABLE.match(texto or "")
    if not m:
        raise ValueError("no es una ${variable}")
    p = parsear(m[1], m[2])
    t, _ = _tabla(ix, p)
    if p.tabla:
        raise ValueError("ya es de una tabla: se completa a partir de la variable del ultimo atributo de la clave")
    conds = [_completo(ix, t, c) for c in p.condiciones]
    funcion = p.funcion
    if funcion in ("con_hijos", "sin_hijos"):
        hs = hijas(ix, t, p.hija)
        if funcion == "con_hijos" and len(hs) != 1:
            raise ValueError(f"con filas en cualquiera de {', '.join(h.nombre for h in hs) or 'ninguna'}: elegi una tabla")
        conds += [Condicion("", "", "", (h.nombre,), (funcion == "sin_hijos",)) for h in hs]
        funcion = "existente"
    if funcion not in ("existente", "ultimo"):
        raise ValueError("uno que no existe es de toda la tabla: no tiene otras partes de la clave que completar")
    salida, iguales = {}, []
    for k in t.claves[:-1]:
        salida[k] = _escribir(funcion, f"{t.nombre}.{k}", iguales + conds)
        iguales.append(f"{k}={salida[k]}")
    salida[t.claves[-1]] = _escribir(funcion, t.claves[-1], iguales + conds)
    return salida


def _es_clave(ix, atributo):
    """Si el atributo es parte de la clave de alguna tabla: los que, mal combinados, dan errores de claves."""
    return any(atributo.lower() in {k.lower() for k in t.claves} for t in ix.todas.values())


def relacionados(ix, texto, variables, hermanos):
    """{hermano: {tabla, expresion}} de los 'hermanos' (otros campos de la entrada) que salen de la misma fila que
    eligen las variables de la clave ('variables': las de misma_fila, o {} y se usa 'texto'). Para
        ${existente.CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}   y el hermano CuponId
    da CuponId: ${existente.cbhCuponDetalle.CuponId|CargoId=${...},CargoCuotaNumero=${...},cbhCupon.CuponEstado=EN_PROCESO}:
    el cupon del detalle por el que la cuota cumple la condicion, no otro. Sale de la misma fila (un atributo de su
    tabla) o de la primera tabla de una condicion «con» que lo tiene; de una «sin» no hay fila. Solo los hermanos que
    son parte de la clave de alguna tabla (los demas no dan errores de claves) y que no son de la clave propia."""
    m = _VARIABLE.match(texto or "")
    if not m:
        return {}
    try:
        p = parsear(m[1], m[2])
        t, _ = _tabla(ix, p)
        conds = [_completo(ix, t, c) for c in p.condiciones]
    except ValueError:
        return {}
    if p.tabla or p.funcion == "siguiente":
        return {}
    if p.funcion == "con_hijos":
        hs = hijas(ix, t, p.hija)
        if len(hs) == 1:  # con filas en cualquiera de varias: no se sabe en cual
            conds.append(Condicion("", "", "", (hs[0].nombre,), (False,)))
    funcion = "ultimo" if p.funcion == "ultimo" else "existente"
    # El valor de cada parte de la clave: su variable, o la condicion = de la variable (CargoId=5, puesto a mano).
    vs = {k.lower(): v for k, v in (variables or {}).items()}
    claves = {}
    for k in t.claves[:-1]:
        v = vs.get(k.lower()) or next((c.valor for c in conds if not c.tablas and c.op == "=" and c.atributo.lower() == k.lower()), "")
        if str(v).strip() == "":
            return {}  # sin esa parte no se sabe de que fila
        claves[k] = v
    claves[t.claves[-1]] = vs.get(t.claves[-1].lower()) or texto
    propias = {k.lower() for k in t.claves}
    salida = {}
    for s in hermanos or []:
        if s.lower() in propias or not _es_clave(ix, s):
            continue
        if t.tiene(s):
            salida[s] = {"tabla": t.nombre, "expresion": _escribir(funcion, f"{t.nombre}.{t.atributo(s)}",
                                                                   [f"{k}={v}" for k, v in claves.items()])}
            continue
        for c in conds:
            cadena = []
            for x, negada in zip(c.tablas, c.negadas):
                if negada:
                    break
                cadena.append(x)
                o = ix.tabla(x, t.datastore)
                if o is not None and o.tiene(s):
                    salida[s] = {"tabla": o.nombre, "expresion": _desde(t, cadena, o, s, claves, conds, funcion)}
                    break
            if s in salida:
                break
    return salida


def _desde(t, cadena, o, s, claves, conds, funcion):
    """${funcion.o.s|...} de la fila de 'o' (la ultima de 'cadena', el camino desde 't') que une la fila de 't' con
    'claves' y cumple las condiciones de 'conds' que pasan por ella. Los caminos se dan vuelta: de 'o' hacia 't'."""
    i = len(cadena)
    if i == 1 and all(o.tiene(k) for k in t.claves):  # la referencia directa: tiene la clave de 't'
        nuevas = [f"{o.atributo(k)}={v}" for k, v in claves.items()]
    else:
        atras = ".".join(list(reversed(cadena[:-1])) + [t.nombre])
        nuevas = [f"{atras}.{k}={v}" for k, v in claves.items()]
    for c in conds:
        j = 0  # cuantas tablas del principio comparte con la cadena
        while j < min(len(c.tablas), i) and not c.negadas[j] and c.tablas[j].lower() == cadena[j].lower():
            j += 1
        if j == 0:
            continue  # sobre 't' o por otro lado: ya la cumple la fila de 't'
        vuelta = tuple(reversed(cadena[j - 1:i - 1]))
        tablas = vuelta + tuple(c.tablas[j:])
        if not tablas and not c.atributo:
            continue  # solo el camino hasta 'o': es la fila misma
        nuevas.append(c._replace(tablas=tablas, negadas=(False,) * len(vuelta) + tuple(c.negadas[j:])))
    return _escribir(funcion, f"{o.nombre}.{o.atributo(s)}", nuevas)


def _existe(ix, nodo, arriba, alias, ta):
    """exists (...) de un nodo del arbol de condiciones sobre otras tablas, con los de sus tablas siguientes adentro.
    'arriba' y 'ta': el alias y la Tabla de la que viene."""
    o, columnas, _ = nodo["paso"]
    a = f"r{next(alias)}"
    w = [f"{a}.{o.col(c)} = {arriba}.{ta.col(c)}" for c in columnas]
    w += [f"{a}.{o.col(c)} {op} {_literal_sql(ix, o, c, v)}" for c, op, v in nodo["conds"]]
    w += [_existe(ix, h, a, alias, o) for h in nodo["hijos"].values()]
    return f"{'not ' if nodo['negada'] else ''}exists (select 1 from {o.ref} {a} where {' and '.join(w)})"


def _convertir(tipo, v):
    """El valor con el tipo del atributo: un char '0012' sigue siendo texto."""
    if tipo not in indice.NUMERICOS:
        return v.rstrip() if isinstance(v, str) else v
    if isinstance(v, str):
        try:
            d = Decimal(v.strip())
            return int(d) if d == d.to_integral_value() else float(d)
        except ArithmeticError:
            return v.rstrip()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def resolver(kb, funcion, resto, en_transaccion=True, invertir=False):
    """El valor de ${funcion.resto}. Con en_transaccion usa la conexion del caso que esta corriendo (ve lo que hizo
    el script previo y los pasos anteriores); si no, toma el motor y termina con rollback. ValueError si no se
    puede calcular o no hay ninguna fila que cumpla. 'invertir': la fila del otro extremo (ver consulta)."""
    p = parsear(funcion, resto)
    ix = indice.de_kb(kb)
    t, q = consulta(ix, p, invertir)
    if en_transaccion:
        r, datos = motor.ejecutar_sql(kb, t.datastore, q, 60000, 1)
    else:
        r, datos = motor.consulta_suelta(kb, t.datastore, q, maximo=1)
    if not r.get("ok"):
        raise ValueError(r.get("error") or f"no se pudo consultar {t.nombre}")
    if not datos.get("filas"):
        conds = ", ".join(str(c) for c in p.condiciones)
        nombres = [h.nombre for h in hijas(ix, t, p.hija)]
        que = {"con_hijos": " con filas en " + " o en ".join(nombres),
               "sin_hijos": " sin filas en " + " ni en ".join(nombres)}.get(p.funcion, "")
        k = t.atributo(p.atributo) if p.tabla else t.claves[-1]
        raise ValueError(f"no hay ningun {k} en {t.nombre}{que}" + (f" que cumpla {conds}" if conds else ""))
    tipo = t.tipos.get(t.atributo(p.atributo)) if p.tabla else t.tipo
    return _convertir(tipo, next(iter(datos["filas"][0].values())))
