"""Script previo de una suite (y SQL previo de Explorar) y casos encadenados: toda la corrida en una transaccion.

El script previo deja la base en un estado conocido antes de los casos, por ejemplo vacia, para que las salidas
no dependan de los datos que haya:

    "scriptPrevio": [{"ds": "GENERALES", "sql": "delete from tabla_hija;\\ndelete from tabla;"}]

(un texto suelto es un bloque en el datasource por defecto). Cada bloque puede tener varias sentencias
separadas por ';'.

Como corre (Entorno), con script previo o con "opciones": {"casosEncadenados": true}:
  1. rollback, el script (si hay) y un savepoint en cada datasource que usa el script y en los demas MySQL de
     la KB (una sola vez por corrida);
  2. cada caso (cada fila de 'datos') corre y al terminar:
     - aislados (por defecto): vuelve al savepoint. El siguiente arranca de la base que dejo el script, sin lo
       que hizo el anterior. Los datasources sin savepoint se deshacen enteros;
     - encadenados: lo hecho queda y el siguiente sigue de ahi (el caso 1 crea un cupon, el 2 lo usa). Lo que
       un caso guarda con 'guardar' llega como ${variable} a los casos que corren despues (salvo que la fila
       de 'datos' tenga una columna con ese nombre);
  3. al final, rollback de todo, script incluido: la base queda como estaba.

Para que nada confirme la corrida (con script, la base quedaria vacia de verdad):
  - el motor simula el commit y el rollback de los objetos en los datasources con savepoint: un commit marca
    otro savepoint y un rollback vuelve al ultimo (GxMotor.Protegida). El fin de cada caso encadenado cuenta
    como un commit. Lo que corre en otra unidad de trabajo (procedimientos con "Execute in new LUW", como
    Sistema.Global.PrcLog) usa otra conexion: su commit no toca esta transaccion;
  - no se aceptan sentencias que en MySQL hacen commit implicito (truncate, drop, alter...);
  - no se ejecutan casos con "transaccion": "commit";
  - si igual se pierde el savepoint (cambio la conexion, se reinicio el motor), el caso queda avisado y se
    vuelve a empezar (con el script, si hay) para los siguientes.
Sin script previo ni casos encadenados, cada caso corre en su transaccion como siempre.
"""
import copy
import re
import time

from .variables import VariableIndefinida, mensaje_error, sustituir, variables_base
from .. import efectos
from ..motor import MotorError, avanzar, ejecutar_sql, fin_transaccion, marcar, motor, volver

# Sentencias que en MySQL confirman la transaccion abierta (commit implicito) o la manejan por su cuenta.
_CONFIRMAN = {"truncate", "drop", "alter", "create", "rename", "grant", "revoke", "lock", "unlock", "analyze",
              "optimize", "repair", "flush", "install", "uninstall"}
_TRANSACCION = {"commit", "rollback", "savepoint", "release", "begin", "start", "xa"}


# ---------------------------------------------------------------------- sentencias

def sentencias(texto):
    """Separa un script en sentencias por ';' (fuera de textos y comentarios). Saltea las vacias o que son
    solo comentarios. Devuelve [(sentencia, sentencia sin comentarios)]."""
    texto = texto or ""
    salida, todo, codigo = [], [], []
    n, i = len(texto), 0

    def cerrar():
        s, c = "".join(todo).strip(), " ".join("".join(codigo).split())
        if c:
            salida.append((s, c))
        todo.clear()
        codigo.clear()

    while i < n:
        ch = texto[i]
        if ch in "'\"`":
            j = i + 1
            while j < n:
                if texto[j] == "\\" and ch != "`":
                    j += 2
                    continue
                if texto[j] == ch:
                    if j + 1 < n and texto[j + 1] == ch:  # comilla duplicada
                        j += 2
                        continue
                    break
                j += 1
            todo.append(texto[i:j + 1])
            codigo.append(texto[i:j + 1])
            i = j + 1
        elif ch == "#" or (texto.startswith("--", i) and (i + 2 >= n or texto[i + 2] in " \t\r\n")):
            j = texto.find("\n", i)
            j = n if j < 0 else j
            todo.append(texto[i:j])
            codigo.append(" ")
            i = j
        elif texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            j = n if j < 0 else j + 2
            todo.append(texto[i:j])
            codigo.append(" ")
            i = j
        elif ch == ";":
            cerrar()
            i += 1
        else:
            todo.append(ch)
            codigo.append(ch)
            i += 1
    cerrar()
    return salida


def prohibida(codigo):
    """Por que no se puede usar la sentencia (sin comentarios) dentro de una prueba, o None."""
    palabras = codigo.lower().replace("(", " ").split()
    if not palabras:
        return None
    p = palabras[0]
    if p in ("create", "drop") and len(palabras) > 1 and palabras[1] == "temporary":
        return None
    if p in _CONFIRMAN:
        return (f"«{p.upper()}» no se puede usar: en MySQL confirma la transaccion (commit implicito) y nada se "
                "podria deshacer. Para vaciar una tabla usa «delete from tabla».")
    if p in _TRANSACCION or (p == "set" and ("autocommit" in codigo.lower() or palabras[1:2] == ["transaction"])):
        return f"«{codigo[:40]}» no se puede usar: la transaccion la maneja GxPruebas y la deshace al final."
    return None


def correr_sql(kb, ds, texto, timeout_ms, maximo=1000):
    """Una o varias sentencias en la conexion del motor, en orden. Devuelve (respuesta, datos) como
    ejecutar_sql: los datos son los de la ultima sentencia. ValueError si alguna no se puede usar."""
    lista = sentencias(texto)
    if not lista:
        raise ValueError("La consulta esta vacia")
    for s, c in lista:
        motivo = prohibida(c)
        if motivo:
            raise ValueError(motivo)
    r, datos = {}, {}
    for k, (s, _) in enumerate(lista):
        r, datos = ejecutar_sql(kb, ds, s, timeout_ms, maximo)
        if not r.get("ok"):
            if len(lista) > 1:
                r = {**r, "error": f"Sentencia {k + 1} de {len(lista)}: {r.get('error') or 'Error'}"}
            return r, datos
    return r, datos


def bloques(script):
    """El script previo normalizado: [{"ds", "sql"}] sin bloques vacios. Acepta un texto suelto y "query"
    (el nombre de las consultas de Explorar) en lugar de "sql"."""
    if not script:
        return []
    if isinstance(script, str):
        script = [{"ds": "", "sql": script}]
    salida = []
    for b in script:
        if isinstance(b, str):
            b = {"ds": "", "sql": b}
        sql = (b.get("sql") if b.get("sql") is not None else b.get("query")) or ""
        if sql.strip():
            salida.append({"ds": b.get("ds") or "", "sql": sql})
    return salida


def correr_script(kb, lista, vars_, timeout_ms):
    """Corre los bloques del script. Devuelve {estado, ms, bloques: [{ds, estado, error, sentencias}]}: cada
    sentencia con las filas que cambio (o la cantidad que trajo, si es un select). Se corta en el primer error."""
    t0 = time.time()
    salida = {"estado": "ok", "bloques": []}
    for b in lista:
        rb = {"ds": b["ds"], "estado": "ok", "sentencias": []}
        salida["bloques"].append(rb)
        try:
            texto = sustituir(b["sql"], vars_)
            partes = sentencias(texto)
            for s, c in partes:
                motivo = prohibida(c)
                if motivo:
                    raise ValueError(motivo)
            for s, _ in partes:
                r, datos = ejecutar_sql(kb, b["ds"], s, timeout_ms, 50)
                sent = {"sql": s if len(s) <= 400 else s[:400] + "…", "ms": round(r.get("ms") or 0, 1)}
                rb["sentencias"].append(sent)
                if not r.get("ok"):
                    raise ValueError(r.get("error") or "Error de SQL")
                if "actualizadas" in datos:
                    sent["actualizadas"] = datos["actualizadas"]
                else:
                    sent["filas"] = datos.get("cantidad", 0)
        except VariableIndefinida as e:
            rb.update(estado="error", error=mensaje_error(e))
        except (ValueError, MotorError) as e:
            rb.update(estado="error", error=str(e).strip("'\""))
        if rb["estado"] != "ok":
            salida["estado"] = "error"
            salida["error"] = (f"[{b['ds']}] " if b["ds"] else "") + rb["error"]
            break
    salida["ms"] = int((time.time() - t0) * 1000)
    return salida


# ---------------------------------------------------------------------- entorno de una corrida

class Entorno:
    """La transaccion de una corrida: toma el motor de la KB en exclusiva mientras dura. Con script previo o con
    casos encadenados, toda la corrida es una transaccion: al entrar corre el script y marca el savepoint, entre
    caso y caso vuelve al savepoint (o, encadenados, sigue) y al salir deshace todo. Si no, cada caso arranca y
    termina su propia transaccion."""

    def __init__(self, kb, suite, opciones):
        self.kb = kb
        self.suite = suite
        self.opciones = opciones
        self.bloques = bloques(suite.get("scriptPrevio"))
        self.encadenados = bool(opciones.get("casosEncadenados"))
        self.activo = bool(self.bloques) or self.encadenados
        self.resultado = None  # el de la ultima vez que corrio el script (None sin script)
        self.veces = 0
        self.guardadas = {}  # encadenados: lo que guardaron los casos anteriores con 'guardar'
        self._marcados = []
        self._error = None  # por que no se pueden correr los casos
        self._lock = None

    def __enter__(self):
        self._lock = motor(self.kb).lock
        self._lock.acquire()
        try:
            if self.activo:
                self._preparar()
        except BaseException:
            self._lock.release()
            raise
        return self

    def __exit__(self, *_):
        try:
            if self.activo:
                fin_transaccion(self.kb, "rollback")
        finally:
            self._lock.release()

    def listo(self):
        return self._error is None

    def reiniciar(self):
        """Vuelve a empezar: rollback, el script y el savepoint (la segunda pasada al aprobar casos encadenados)."""
        if self.activo:
            self._preparar()

    def _preparar(self):
        fin_transaccion(self.kb, "rollback")
        self._error = None
        self._marcados = []
        self.guardadas = {}  # vuelve a empezar: nada de lo que guardaron los casos anteriores sigue en la base
        if self.bloques:
            self.veces += 1
            vars_ = variables_base(self.suite, None, {"id": "script-previo"}, self.kb)
            self.resultado = correr_script(self.kb, self.bloques, vars_, self.opciones.get("timeoutMs"))
            self.resultado["veces"] = self.veces
            if self.resultado["estado"] != "ok":
                self._error = f"El script previo no termino bien: {self.resultado.get('error')}"
                fin_transaccion(self.kb, "rollback")
                return
        remotos = efectos.datastores_remotos(self.kb)
        otros = [d["nombre"] for d in self.kb.datasources if d["nombre"].upper() not in remotos]
        try:
            self._marcados = marcar(self.kb, [b["ds"] for b in self.bloques], otros)
        except MotorError as e:
            self._error = f"No se pudo marcar el punto de partida: {e}"
            if self.resultado:
                self.resultado.update(estado="error", error=self._error)
            fin_transaccion(self.kb, "rollback")

    def recibir(self, vars_, fila):
        """Encadenados: suma a las variables de una fila lo que guardaron los casos anteriores (una columna de la
        fila con el mismo nombre gana). Devuelve lo que agrego."""
        if not self.encadenados:
            return {}
        recibidas = {k: v for k, v in self.guardadas.items() if k not in (fila or {})}
        vars_.update(copy.deepcopy(recibidas))
        return recibidas

    def recordar(self, vars_, claves):
        """Encadenados: al terminar una fila, lo que se guardo con 'guardar' queda para los casos siguientes."""
        if self.encadenados:
            for k in claves:
                if k in vars_:
                    self.guardadas[k] = copy.deepcopy(vars_[k])

    def antes(self, caso, modo):
        """Al empezar una fila de un caso. Devuelve el motivo por el que no se puede correr, o None."""
        if not self.activo:
            fin_transaccion(self.kb, "rollback")  # arranca limpio
            return None
        if self._error:
            return self._error
        if modo == "commit":
            que = "con casos encadenados" if self.encadenados else "con script previo"
            return (f"No se ejecuto: {que} los casos no pueden correr con commit (confirmaria todo lo anterior). "
                    "Sacale \"transaccion\": \"commit\".")
        return None

    def despues(self, modo):
        """Al terminar una fila: deshace lo que hizo o, encadenados, lo deja para el siguiente. Devuelve
        (transaccion, avisos para el caso)."""
        if not self.activo:
            ft = fin_transaccion(self.kb, modo)
            return modo, ([] if ft.get("ok") else ["Fin de transaccion con errores: " + "; ".join(ft.get("errores") or [])])
        if self._error:
            fin_transaccion(self.kb, "rollback")
            return "rollback", []
        r = avanzar(self.kb) if self.encadenados else volver(self.kb)
        avisos = []
        if r.get("commits") or r.get("rollbacks"):
            hechos = [f"{n} {q}" for n, q in ((r.get("commits"), "commit"), (r.get("rollbacks"), "rollback")) if n]
            avisos.append(f"Los objetos hicieron {' y '.join(hechos)} por su cuenta: se simularon con savepoints y no "
                          "llegaron a la base.")
        if r.get("ok") and r.get("puntos") == len(self._marcados):
            return ("encadenada: sigue en el caso siguiente" if self.encadenados else "rollback al script previo"), avisos
        motivo = "; ".join([*(r.get("perdidos") or []), *(r.get("errores") or [])]) or "se reinicio el motor"
        self._preparar()
        if self.encadenados:
            return "rollback", [*avisos, f"Durante el caso se perdio lo que venian haciendo los casos anteriores ({motivo}). "
                                         "Se volvio a empezar" + (" desde el script previo" if self.bloques else "") +
                                         ": los casos siguientes no ven lo que hicieron los anteriores."]
        return "rollback", [*avisos, f"Durante el caso se perdio la base que deja el script previo ({motivo}). Lo que "
                                     "siguio pudo no correr sobre esa base. El script se volvio a correr para los "
                                     "casos siguientes."]
