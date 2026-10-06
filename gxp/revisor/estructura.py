"""Estructura de bloques de un fuente GX: que sentencias estan dentro de que If, Case, For Each o Sub.

Se arma a partir de las claves de las sentencias (fuente.py), sin ver codigos de GeneXus:

    Programa
      cuerpo: Rama                      las sentencias del programa principal, en orden
      subs:   {'agregarmensaje': Bloque}

    Rama:   una secuencia de nodos (Sentencia o Bloque). 'cabecera' es la sentencia que la abre: el If, el
            Else, cada Case, el When none... (None en el cuerpo del programa).
    Bloque: una estructura de control con sus ramas, en orden. Un If con Else tiene dos ramas; un Do Case,
            una por Case (mas la primera, vacia, entre el Do Case y el primer Case); un For Each con When
            none, dos.

Las sentencias que GeneXus genera (s.generada) no forman parte de la estructura.
"""

ABRE = {"if", "dowhile", "new", "foreach", "sub", "event", "forselected", "docase", "forline", "forin", "apiinicio"}
MEDIO = {"else", "whenduplicate", "whennone", "case", "otherwise"}
CIERRA = {"endif", "enddo", "endnew", "endfor", "endsub", "endevent", "endcase", "apifin"}

# Los que repiten su cuerpo (el resto de los bloques que abren se recorren una vez).
BUCLES = {"dowhile", "foreach", "forselected", "forline", "forin"}


class Rama:
    __slots__ = ("cabecera", "nodos")

    def __init__(self, cabecera=None):
        self.cabecera = cabecera
        self.nodos = []

    def __repr__(self):
        return f"<Rama {self.cabecera.linea if self.cabecera else 'programa'}: {len(self.nodos)} nodos>"


class Bloque:
    __slots__ = ("inicio", "ramas", "fin")

    def __init__(self, inicio):
        self.inicio = inicio
        self.ramas = [Rama(inicio)]
        self.fin = None

    @property
    def tipo(self):
        return self.inicio.clave

    @property
    def es_bucle(self):
        return self.tipo in BUCLES

    def __repr__(self):
        return f"<Bloque {self.tipo} {self.inicio.linea}-{self.fin.linea if self.fin else '?'}>"


class Programa:
    __slots__ = ("cuerpo", "subs")

    def __init__(self):
        self.cuerpo = Rama()
        self.subs = {}


def nombre_sub(s):
    """'AGREGARMENSAJE' de un Sub o un Do, en minusculas y sin comillas."""
    return s.texto.split(None, 1)[-1].strip().strip("'\"").strip().lower()


def armar(fu) -> Programa:
    prog = Programa()
    pila = []  # bloques abiertos
    actual = prog.cuerpo
    for s in fu.sentencias:
        if s.generada:
            continue
        if s.clave in ABRE:
            b = Bloque(s)
            actual.nodos.append(b)
            pila.append(b)
            actual = b.ramas[0]
            if s.clave == "sub":
                prog.subs[nombre_sub(s)] = b
        elif s.clave in MEDIO and pila:
            rama = Rama(s)
            pila[-1].ramas.append(rama)
            actual = rama
        elif s.clave in CIERRA and pila:
            pila.pop().fin = s
            actual = pila[-1].ramas[-1] if pila else prog.cuerpo
        else:
            actual.nodos.append(s)
    return prog
