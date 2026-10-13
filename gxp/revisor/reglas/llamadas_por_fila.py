"""Llamadas, consultas y cargas de Business Components por cada fila de una grilla (N+1).

En un Web Panel o Web Component:
  - el Load de una grilla con tabla base (Event Grid.Load) corre una vez por cada registro: todo lo que esta
    en el evento corre por fila;
  - el de una grilla sin tabla base corre una vez y carga las filas con Grid.Load() dentro de un bucle (For
    Each, Do While, For in): corre por fila lo que esta en ese bucle.
Si la navegacion no dice si la grilla tiene tabla base, se decide por el codigo: con un Grid.Load() dentro de un
bucle se toma como sin tabla base. Un Event Load sin nombre de grilla solo se mira si el objeto tiene una grilla:
en un panel sin grilla (los General de WorkWithPlus) corre una vez, para el registro que muestra.

Marca, en lo que corre por fila (siguiendo los Do a las subrutinas):
  - las llamadas a procedimientos y Data Providers (tambien &x = Proc(...));
  - los For Each (una consulta por fila);
  - las cargas de un Business Component (&bc.Load(...)).
"""
from . import Regla, registrar
from ..estructura import Bloque, armar, nombre_sub
from ..prolog import Comp

DETALLE = ("Corre una vez por cada fila de la grilla: con 10 filas por pagina son 10 llamadas, y cada una puede hacer "
           "sus propias consultas. Trae el dato en la consulta de la grilla (un atributo de la tabla extendida o una "
           "formula), calculalo una vez antes de cargar la grilla, o carga la grilla desde un Data Provider o "
           "procedimiento que lo resuelva en una sola consulta. Si es inevitable, agrega una excepcion en "
           "revisor.json con el motivo.")

# Clases de objeto de las referencias o(N, 'Nombre') que cuentan: procedimiento y Data Provider.
CLASES = {1, 33}
BUCLES = {"foreach", "dowhile", "forin", "forline", "forselected"}


def _cargas(toks, salida):
    """[(tipo de token, nombre)] de los X.load( de una sentencia: 3 es un control (la grilla), 23 una variable (un BC)."""
    for t in toks:
        if isinstance(t, Comp):
            a = t.args
            if (t.nombre == "t" and a and isinstance(a[0], list) and len(a[0]) >= 2 and isinstance(a[0][-1], Comp)
                    and a[0][-1].args and a[0][-1].args[0] == "load(" and isinstance(a[0][-2], Comp)):
                prev = a[0][-2].args
                salida.append((prev[1] if len(prev) > 1 else None, str(prev[0])))
            _cargas(a, salida)
        elif isinstance(t, list):
            _cargas(t, salida)
    return salida


def _nodos(rama_o_bloque):
    """Las sentencias y bloques de un bloque (todas sus ramas) o de una rama."""
    if isinstance(rama_o_bloque, Bloque):
        for r in rama_o_bloque.ramas:
            yield from r.nodos
    else:
        yield from rama_o_bloque.nodos


@registrar
class LlamadasPorFila(Regla):
    id = "llamadas-por-fila"
    titulo = "No llamar a procedimientos ni consultar la base por cada fila de una grilla"
    severidad = "advertencia"
    parametros = {
        # Objetos que se pueden llamar por fila (ultimo tramo del nombre, en cualquier modulo).
        "permitidos": [],
    }

    def aplica(self, fu, ctx):
        return fu.tipo == "web"

    def revisar(self, fu, ctx):
        prog = armar(fu)
        con_tabla = ctx.loads_con_tabla(fu.nombre)
        permitidos = {p.lower() for p in self.conf["permitidos"]}
        marcadas = set()
        for nodo in prog.cuerpo.nodos:
            if not (isinstance(nodo, Bloque) and nodo.tipo == "event"):
                continue
            evento = nodo.inicio.texto.split(None, 1)[-1].strip()
            if not (evento.lower() == "load" or evento.lower().endswith(".load")):
                continue
            grilla = evento[:-5] if evento.lower().endswith(".load") else ""
            if not grilla and not ctx.tiene_grilla(fu.nombre):
                continue
            for region, cabecera in self._por_fila(nodo, grilla, evento, con_tabla, prog):
                for s, via in self._recorrer(region, prog, set(), None):
                    if s.linea in marcadas:
                        continue
                    accesos = self._accesos(s, permitidos)
                    if not accesos:
                        continue
                    marcadas.add(s.linea)
                    mensaje = accesos[0][0] + (f" (y {len(accesos) - 1} mas)" if len(accesos) > 1 else "")
                    donde = f"la grilla {grilla}" if grilla else "la grilla"
                    extra = f" (por Do '{via[0]}' de la linea {via[1]})" if via else ""
                    yield self.hallazgo(fu, s, f"{mensaje} por cada fila de {donde}{extra}", detalle=DETALLE, ctx=ctx,
                                        evento=evento, **accesos[0][1], **({"porBucle": cabecera} if cabecera else {}))

    # ------------------------------------------------------------------ que corre por fila

    def _por_fila(self, evento, grilla, nombre, con_tabla, prog):
        """[(region, linea del bucle o None)]: lo que corre una vez por fila en el evento Load."""
        if con_tabla is not None and nombre.lower() in con_tabla:
            return [(evento, None)]
        bucles = self._bucles_con_carga(evento, grilla, prog, set())
        if bucles:
            return [(b, b.inicio.linea) for b in bucles]
        if con_tabla is None:
            return [(evento, None)]  # sin navegacion y sin Grid.Load() en un bucle: se toma como con tabla base
        return []

    def _bucles_con_carga(self, bloque, grilla, prog, subs):
        """Los bucles mas internos del evento que cargan una fila de la grilla (Grid.Load()), directamente o por un
        Do. Tambien los que estan en una subrutina que llama el evento."""
        salida = []
        for n in _nodos(bloque):
            if isinstance(n, Bloque):
                internos = self._bucles_con_carga(n, grilla, prog, subs)
                if internos:
                    salida += internos
                elif n.tipo in BUCLES and self._carga(n, grilla, prog, set()):
                    salida.append(n)
            elif n.clave == "do":
                sub = nombre_sub(n)
                if sub not in subs and sub in prog.subs:
                    subs.add(sub)
                    salida += self._bucles_con_carga(prog.subs[sub], grilla, prog, subs)
        return salida

    def _carga(self, bloque, grilla, prog, subs):
        for n in _nodos(bloque):
            if isinstance(n, Bloque):
                if self._carga(n, grilla, prog, subs):
                    return True
                continue
            if any(tipo == 3 and (not grilla or nombre.lower() == grilla.lower()) for tipo, nombre in _cargas(n.tokens, [])):
                return True
            if n.clave == "do":
                sub = nombre_sub(n)
                if sub not in subs and sub in prog.subs:
                    subs.add(sub)
                    if self._carga(prog.subs[sub], grilla, prog, subs):
                        return True
        return False

    def _recorrer(self, region, prog, subs, via):
        """(sentencia, via) de lo que corre en la region, entrando en los Do. 'via': (sub, linea del primer Do)."""
        for n in _nodos(region):
            if isinstance(n, Bloque):
                yield n.inicio, via
                yield from self._recorrer(n, prog, subs, via)
                continue
            yield n, via
            if n.clave == "do":
                sub = nombre_sub(n)
                if sub not in subs and sub in prog.subs:
                    subs.add(sub)
                    yield from self._recorrer(prog.subs[sub], prog, subs, via or (sub, n.linea))

    def _accesos(self, s, permitidos):
        """[(mensaje, datos)] de lo que hace la sentencia contra la base."""
        if s.clave == "foreach":
            return [("For Each (una consulta)", {"acceso": "foreach"})]
        salida = []
        for clase, obj in s.objetos():
            if clase in CLASES and obj.split(".")[-1].lower() not in permitidos:
                salida.append((f"Llama a {obj}", {"acceso": "llamada", "llamado": obj}))
        for tipo, nombre in _cargas(s.tokens, []):
            if tipo == 23:
                salida.append((f"Carga el Business Component &{s._fuente.variable(nombre)}", {"acceso": "bc"}))
        return salida
