"""Recorrido de los caminos de un fuente GX siguiendo el Ok y los mensajes de un sdtOutput.

Lo usa la regla salida-ok-mensajes. Recorre la estructura (estructura.py) llevando un conjunto de estados;
cada estado es un camino posible y dice:

  ok      None (nunca se asigno: vale False), True, False o DESCONOCIDO
  error   si se agrego un mensaje de tipo Error (True, False o DESCONOCIDO)
  exito   el mensaje de exito agregado: None, "debug", "info" o DESCONOCIDO
  env     valores conocidos de variables: tipos de mensaje (&MsgType = MessageTypes.Error) y booleanos
          (&HayError = True), con la sentencia que les dio el valor. Sirven para resolver los If que
          dependen de ellos y para senalar donde se eligio el tipo de un mensaje.

y de donde salio cada cosa (la sentencia), para poder senalar la linea. El tipo de un mensaje se senala donde
se eligio (&MsgType = MessageTypes.Info), que es lo que hay que cambiar, aunque el mensaje se agregue en una sub.

  - If y Do Case: si la condicion se puede evaluar con lo que se sabe, se sigue solo la rama que corresponde;
    si no, todas. En la rama del If &x = MessageTypes.Error se sabe que &x es Error.
  - Do 'sub': se recorre el cuerpo de la sub en el lugar, con los valores del momento (asi se resuelve un
    'AGREGARMENSAJE' que mira &MsgType). Un Return adentro de una sub termina el programa, como en GX.
  - Bucles: el cuerpo se recorre una vez y lo que depende de la iteracion queda DESCONOCIDO.
  - Return y el final del programa son las salidas: Analisis.salidas tiene el estado con que se llega a cada una.

Las salidas (sdtOutput) se reconocen por texto: '&outset.output', '&sdtoutput'. Los mensajes se agregan con
&salida.Messages.Add(&Mensaje) (el tipo sale de &Mensaje.Type) o con un ayudante configurado, como
Sistema.Output.AddMessage(texto, tipo, &salida). Lo que entra en la coleccion vieja &salida.Errores es un
error. Pasar la salida a cualquier otro objeto, asignarla entera o tocar sus mensajes de otra forma
(FromJson, Clear) la deja DESCONOCIDA.
"""
import re
from typing import NamedTuple

from . import estructura, fuente
from .prolog import Comp

DESCONOCIDO = "?"
TIPOS_MENSAJE = ("error", "warning", "info", "debug")
MAX_ESTADOS = 400  # por punto del programa; con mas, se dejan de seguir las variables


class Estado(NamedTuple):
    ok: object = None
    ok_s: object = None          # sentencia que asigno el Ok
    error: object = False
    error_s: object = None       # primer mensaje de error
    exito: object = None
    exito_s: object = None       # mensaje de exito (el primero Info, o el Debug)
    env: tuple = ()              # ((variable, valor, sentencia), ...) ordenado por variable

    def con(self, **cambios):
        return self._replace(**cambios)

    def valor(self, var):
        return next((v for k, v, _ in self.env if k == var), None)

    def origen(self, var):
        return next((s for k, _, s in self.env if k == var), None)

    def poner(self, var, valor, s=None):
        env = [x for x in self.env if x[0] != var and not x[0].startswith(var + ".")]
        if valor is not None:
            env.append((var, valor, s))
        return self._replace(env=tuple(sorted(env, key=lambda x: x[0])))


class Complejo(Exception):
    """Demasiados caminos: el objeto no se analiza."""


# ---------------------------------------------------------------------- texto de las sentencias

def partir_argumentos(texto):
    """'"a, b", f(x, y), &z' -> ['"a, b"', 'f(x, y)', '&z'] (comas de primer nivel, fuera de comillas)."""
    partes, nivel, actual, comilla = [], 0, [], None
    for ch in texto:
        if comilla:
            actual.append(ch)
            if ch == comilla:
                comilla = None
            continue
        if ch in "\"'":
            comilla = ch
        elif ch == "(":
            nivel += 1
        elif ch == ")":
            nivel -= 1
        elif ch == "," and nivel == 0:
            partes.append("".join(actual).strip())
            actual = []
            continue
        actual.append(ch)
    if "".join(actual).strip():
        partes.append("".join(actual).strip())
    return partes


def llamada(texto):
    """'Modulo.Proc(a, b)' -> ('modulo.proc', ['a', 'b']); None si no es una llamada."""
    m = re.match(r"^([\w.]+)\((.*)\)$", texto.strip(), re.S)
    if not m:
        return None
    nombre = re.sub(r"\.(call|udp)$", "", m.group(1).lower())
    return nombre, partir_argumentos(m.group(2))


def asignacion(fu, s):
    """(izquierda, derecha) en minusculas si la sentencia es 'x = expr'; None si no."""
    t = s.tokens
    if s.clave == "asignacion" and len(t) >= 2 and isinstance(t[1], Comp) and t[1].nombre == "t" and t[1].args[0] == "=":
        return fuente.texto(fu, t[:1]).lower(), fuente.texto(fu, t[2:]).strip().lower()
    return None


def tipo_literal(texto):
    m = re.fullmatch(r"messagetypes\.(\w+)", texto.strip().lower())
    return m.group(1) if m and m.group(1) in TIPOS_MENSAJE else None


_VARIABLE = re.compile(r"&[\w.]+")


# ---------------------------------------------------------------------- analisis

class Analisis:
    def __init__(self, fu, salidas, ayudantes=None):
        """salidas: expresiones en minusculas de los sdtOutput ('&outset.output'). ayudantes:
        {'sistema.output.addmessage': {'tipo': 2, 'salida': 3}} (posiciones desde 1; tipo None = desconocido)."""
        self.fu = fu
        self.prog = estructura.armar(fu)
        self.salidas_sdt = [x.lower() for x in salidas]
        self.ayudantes = {k.lower(): v for k, v in (ayudantes or {}).items()}
        self.salidas = []        # [(Estado, sentencia Return o None si llega al final)]
        self.asigna_ok = False   # alguna asignacion de Ok que puede ser True
        self._subs = []          # [(nombre, sentencia Do)] de las subs que se estan recorriendo
        self._cortes = []

    def correr(self):
        fin = self._rama(self.prog.cuerpo, {Estado()})
        self.salidas += [(e, None) for e in fin]
        return self

    # -------------------------------------------------------------- recorrido

    def _rama(self, rama, estados):
        for nodo in rama.nodos:
            if not estados:
                break
            estados = self._nodo(nodo, estados)
            if len(estados) > MAX_ESTADOS:
                estados = {e.con(env=()) for e in estados}
                if len(estados) > MAX_ESTADOS:
                    raise Complejo(f"mas de {MAX_ESTADOS} caminos")
        return estados

    def _nodo(self, nodo, estados):
        if isinstance(nodo, estructura.Bloque):
            if nodo.tipo in ("sub", "event"):
                return estados
            if nodo.tipo == "if":
                return self._if(nodo, estados)
            if nodo.tipo == "docase":
                return self._case(nodo, estados)
            if nodo.es_bucle:
                return self._bucle(nodo, estados)
            salen = set()  # New / When duplicate y el resto: cualquiera de sus ramas
            for rama in nodo.ramas:
                salen |= self._rama(rama, estados)
            return salen
        return self._sentencia(nodo, estados)

    def _if(self, b, estados):
        cond = _sin_palabra(b.inicio.texto, "if")
        salen = set()
        for e in estados:
            v, si, no = self._condicion(cond, e)
            if v is not False:
                salen |= self._rama(b.ramas[0], {si})
            if v is not True:
                salen |= self._rama(b.ramas[1], {no}) if len(b.ramas) > 1 else {no}
        return salen

    def _case(self, b, estados):
        salen = set()
        for e in self._rama(b.ramas[0], estados):
            pendientes = {e}
            for rama in b.ramas[1:]:
                if rama.cabecera.clave == "otherwise":
                    salen |= self._rama(rama, pendientes)
                    pendientes = set()
                    break
                siguen = set()
                for p in pendientes:
                    v, si, no = self._condicion(_sin_palabra(rama.cabecera.texto, "case"), p)
                    if v is not False:
                        salen |= self._rama(rama, {si})
                    if v is not True:
                        siguen.add(no)
                pendientes = siguen
            salen |= pendientes
        return salen

    def _bucle(self, b, estados):
        cuerpo = b.ramas[0]
        otras = b.ramas[1:]  # When none
        salen = set()
        for e in estados:
            self._cortes.append(set())
            vueltas = self._rama(cuerpo, {e}) | self._cortes.pop()
            if not otras:
                vueltas.add(e)  # puede no entrar nunca
            if vueltas:
                salen.add(_resumir(vueltas))
            for rama in otras:
                salen |= self._rama(rama, {e})
        return salen

    def _sentencia(self, s, estados):
        if s.clave == "return":
            self.salidas += [(e, s) for e in estados]
            return set()
        if s.clave == "exit" and self._cortes:
            self._cortes[-1].update(estados)
            return set()
        if s.clave == "do":
            nombre = estructura.nombre_sub(s)
            sub = self.prog.subs.get(nombre)
            if sub is None or any(n == nombre for n, _ in self._subs):
                return estados
            self._subs.append((nombre, s))
            try:
                return self._rama(sub.ramas[0], estados)
            finally:
                self._subs.pop()
        return {self._efecto(s, e) for e in estados}

    # -------------------------------------------------------------- efectos de una sentencia

    def _mensaje(self, e, s, tipo, origen=None):
        """Agrega un mensaje. 'origen': donde se asigno el tipo, si salio de una variable."""
        s = origen or s
        if tipo == "error":
            return e if e.error is True else e.con(error=True, error_s=s)
        if tipo == "debug":
            return e.con(exito="debug", exito_s=s)
        if tipo == "info":
            return e.con(exito="info", exito_s=s) if e.exito is None else e
        if tipo == "warning":
            return e
        return e.con(error=e.error if e.error is True else DESCONOCIDO,
                     exito=e.exito if e.exito == "debug" else DESCONOCIDO)

    def _es_salida(self, expr):
        return expr in self.salidas_sdt

    def _contiene_salida(self, expr):
        """La salida entera, o la variable que la contiene (&outset para &outset.output)."""
        return any(x == expr or x.startswith(expr + ".") for x in self.salidas_sdt)

    def _campo_salida(self, expr):
        """'messages', 'errores', 'ok'... si expr es un campo de una salida (&outset.output.messages)."""
        for x in self.salidas_sdt:
            if expr.startswith(x + "."):
                return expr[len(x) + 1:]
        return None

    def _efecto(self, s, e):
        a = asignacion(self.fu, s)
        if a:
            return self._asignar(s, e, *a)
        texto = s.texto.strip()
        m = re.match(r"^(&[\w.]+)\.(\w+)\((.*)\)$", texto, re.S)
        if m:  # metodo de una variable: &x.Messages.Add(&m), &x.Errores.FromJson(...)
            return self._metodo(s, e, m.group(1).lower(), m.group(2).lower(), m.group(3).strip().lower())
        ll = llamada(texto)
        if ll:
            return self._llamar(s, e, *ll)
        return e

    def _metodo(self, s, e, objeto, metodo, arg):
        campo = self._campo_salida(objeto)
        if campo == "messages":
            if metodo != "add":
                return self._mensaje(e, s, None)
            if not _VARIABLE.fullmatch(arg):
                return self._mensaje(e, s, None)
            return self._mensaje(e, s, e.valor(arg + ".type"), e.origen(arg + ".type"))
        if campo == "errores":  # la coleccion vieja de errores (sdtError): todo lo que entra es un error
            return self._mensaje(e, s, "error" if metodo == "add" else None)
        if self._contiene_salida(objeto) or self._pasa_salida(arg + "()"):
            return _desconocida(e)
        return e

    def _asignar(self, s, e, izq, der):
        campo = self._campo_salida(izq)
        if campo == "ok":
            v = self._valor(der, e)
            if v is not False:
                self.asigna_ok = True
            return e.con(ok=v if isinstance(v, bool) else DESCONOCIDO, ok_s=s)
        if campo in ("messages", "errores"):
            return self._mensaje(e, s, None)
        if self._contiene_salida(izq):
            if der.startswith("new("):
                return Estado(env=e.env)
            return _desconocida(e)
        if self._pasa_salida(der):
            e = _desconocida(e)
        v = self._valor(der, e)
        if v is DESCONOCIDO:
            return e.poner(izq, None)
        # &Message.Type = &MsgType: el origen es donde se eligio el tipo, no la copia.
        return e.poner(izq, v, (_VARIABLE.fullmatch(der) and e.origen(der)) or s)

    def _llamar(self, s, e, nombre, args):
        ayu = self.ayudantes.get(nombre)
        if ayu:
            pos_salida = ayu.get("salida")
            if pos_salida and len(args) >= pos_salida and self._es_salida(args[pos_salida - 1].lower()):
                pos_tipo = ayu.get("tipo")
                arg = args[pos_tipo - 1].lower() if pos_tipo and len(args) >= pos_tipo else ""
                tipo = self._valor(arg, e) if arg else None
                origen = e.origen(arg) if _VARIABLE.fullmatch(arg) else None
                return self._mensaje(e, s, tipo if tipo in TIPOS_MENSAJE else None, origen)
        if any(self._contiene_salida(x.lower()) for x in args):
            return _desconocida(e)
        return e

    def _pasa_salida(self, expr):
        """La expresion le pasa la salida a otro objeto: Proc(&x, &sdtOutput)."""
        return "(" in expr and any(self._contiene_salida(v) for v in _VARIABLE.findall(expr))

    # -------------------------------------------------------------- valores y condiciones

    def _valor(self, expr, e):
        """Valor de una expresion: tipo de mensaje, True/False, o DESCONOCIDO."""
        expr = expr.strip()
        t = tipo_literal(expr)
        if t:
            return t
        if expr in ("true", "false"):
            return expr == "true"
        if _VARIABLE.fullmatch(expr):
            actual = self._actual(expr, e)
            return DESCONOCIDO if actual is None else actual
        v, _, _ = self._condicion(expr, e)
        return DESCONOCIDO if v is None else v

    def _condicion(self, cond, e):
        """(True | False | None si no se sabe, estado si es verdadera, estado si es falsa)."""
        cond = _sin_parentesis(cond.strip().lower())
        for op in (" or ", " and "):
            partes = _partir_logico(cond, op)
            if len(partes) > 1:
                vals = [self._condicion(p, e)[0] for p in partes]
                if op == " and ":
                    v = False if False in vals else (True if all(x is True for x in vals) else None)
                else:
                    v = True if True in vals else (False if all(x is False for x in vals) else None)
                return v, e, e
        if cond.startswith("not "):
            v, si, no = self._condicion(cond[4:], e)
            return (None if v is None else not v), no, si
        m = re.fullmatch(r"(&[\w.]+)\.count\s*(<>|>|=)\s*0", cond)
        if m and self._campo_salida(m.group(1)) in ("errores", "messages"):
            hay = self._hay_mensajes(e, self._campo_salida(m.group(1)))
            return (None if hay is None else (hay if m.group(2) != "=" else not hay)), e, e
        m = re.fullmatch(r"(&[\w.]+)\s*(=|<>)\s*(.+)", cond)
        if m:
            var, op, der = m.groups()
            literal = tipo_literal(der)
            if literal is None and der in ("true", "false"):
                literal = der == "true"
            if literal is None:
                return None, e, e
            actual = self._actual(var, e)
            if actual is None:
                si = e.poner(var, literal) if op == "=" else e
                no = e.poner(var, literal) if op == "<>" else e
                return None, si, no
            igual = actual == literal
            return (igual if op == "=" else not igual), e, e
        if _VARIABLE.fullmatch(cond):
            actual = self._actual(cond, e)
            if actual is None:
                return None, e.poner(cond, True), e.poner(cond, False)
            return (bool(actual) if isinstance(actual, bool) else None), e, e
        return None, e, e

    def _hay_mensajes(self, e, campo):
        """Si la coleccion tiene algo: Errores solo recibe errores; Messages, ademas, otros tipos que no se
        cuentan (con un error se sabe que tiene algo; sin errores, no se sabe)."""
        if e.error is True:
            return True
        if campo == "errores" and e.error is False:
            return False
        return None

    def _actual(self, var, e):
        """Valor conocido de una variable, o None. El Ok de la salida sale del estado (sin asignar = False)."""
        for x in self.salidas_sdt:
            if var == x + ".ok":
                if e.ok is None:
                    return False
                return e.ok if isinstance(e.ok, bool) else None
        return e.valor(var)


# ---------------------------------------------------------------------- ayudantes

def _sin_palabra(texto, palabra):
    t = texto.strip()
    return t[len(palabra):].strip() if t.lower().startswith(palabra + " ") else t


def _sin_parentesis(t):
    while t.startswith("(") and t.endswith(")") and _balanceado(t[1:-1]):
        t = t[1:-1].strip()
    return t


def _balanceado(t):
    nivel = 0
    for ch in t:
        nivel += ch == "("
        nivel -= ch == ")"
        if nivel < 0:
            return False
    return nivel == 0


def _partir_logico(cond, op):
    partes, nivel, inicio, i = [], 0, 0, 0
    while i < len(cond):
        ch = cond[i]
        nivel += ch == "("
        nivel -= ch == ")"
        if nivel == 0 and cond.startswith(op, i):
            partes.append(cond[inicio:i].strip())
            inicio = i + len(op)
            i = inicio
            continue
        i += 1
    partes.append(cond[inicio:].strip())
    return partes


def _desconocida(e):
    return e.con(ok=DESCONOCIDO, error=DESCONOCIDO, exito=DESCONOCIDO)


def _resumir(estados):
    """Un estado para todas las vueltas de un bucle: lo que no coincide queda DESCONOCIDO."""
    estados = list(estados)
    if len(estados) == 1:
        return estados[0]
    base = estados[0]
    cambios = {}
    for campo, origen in (("ok", "ok_s"), ("error", "error_s"), ("exito", "exito_s")):
        valores = {getattr(x, campo) for x in estados}
        if len(valores) > 1:
            cambios[campo] = DESCONOCIDO
        origenes = [getattr(x, origen) for x in estados if getattr(x, origen) is not None]
        cambios[origen] = origenes[0] if origenes else None
    comunes = set(base.env)
    for x in estados[1:]:
        comunes &= set(x.env)
    cambios["env"] = tuple(sorted(comunes, key=lambda x: x[0]))
    return base.con(**cambios)
