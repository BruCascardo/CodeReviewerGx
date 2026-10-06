"""Que entidades crea un objeto con Business Components, que parte de su clave conoce el que llama y cual
devuelve. Lo usa la regla alta-devuelve-id.

Un BC crea cuando:
  - hace .Insert() o .InsertOrUpdate();
  - hace .Save() despues de &bc = new() (Load / If Fail() / new() es alta o modificacion). Un new() seguido
    del Load de la misma variable solo la limpia antes de cargarla: eso es una modificacion;
  - hace .Save() sin Load ni ninguna otra carga (arranca vacio, asi que inserta).
Si el BC llega cargado de otro lado (se asigna entero, FromJson, se le pasa a otro objeto) no se sabe y no
cuenta. Un .Save() despues de Load sin new() es una modificacion.

La clave la conoce el que llama si cada atributo clave se asigna desde los parametros de entrada (directo o a
traves de variables que solo se cargan desde ellos, y funciones como upper o trim). Si sale de un
procedimiento (un numerador), de un atributo de la base, es autonumerada o no se asigna, hay que devolverla.

Se devuelve si algun parametro de salida se asigna desde el atributo del BC (&out.Id = &bc.Id), desde una
variable que tiene ese mismo valor (&bc.Id = &Id ... &out.Id = &Id), o si se devuelve el BC entero.
"""
import re

from . import flujo

_VAR = re.compile(r"&[\w.]+")
_LLAMADA_OBJETO = re.compile(r"(?<![&\w.])[a-z_]\w*\.[\w.]+\(", re.I)   # Modulo.Proc( : no es una funcion de GX
_ATRIBUTO = re.compile(r"(?<![&\w.'\"])([a-z_]\w*)(?![\w.(])", re.I)    # ItfId suelto: un atributo de la base
_PALABRAS = {"and", "or", "not", "true", "false", "null", "new", "in", "like"}
_TEXTOS = re.compile(r'"(?:[^"]|"")*"|\'(?:[^\']|\'\')*\'')


class Entidad:
    """Lo que crea un BC del objeto."""

    def __init__(self, var, trn, motivo, sentencia):
        self.var = var                # '&gnhpersona'
        self.trn = trn                # transacciones.Transaccion
        self.motivo = motivo          # '.Save() despues de new()'
        self.sentencia = sentencia    # el Save / Insert
        self.conocidas = set()        # atributos clave que vienen de la entrada
        self.devueltas = set()        # atributos clave que se devuelven
        self.hija_de = None           # otra Entidad creada cuya clave esta incluida en la de esta

    @property
    def faltan(self):
        return [k for k in self.trn.claves if k.lower() not in self.conocidas | self.devueltas]


class Analisis:
    def __init__(self, fu, ctx):
        self.fu = fu
        self.entradas = {"&" + n.lower() for n, io in fu.parametros if io in ("in", "inout")}
        self.salidas = {"&" + n.lower() for n, io in fu.parametros if io in ("out", "inout")}
        self.bcs = {}
        for v in fu.variables.values():
            trn = ctx.transaccion(v["tipo"])
            if trn is not None:
                self.bcs["&" + v["nombre"].lower()] = trn
        self.asignaciones = []   # [(izq, der, sentencia)] en minusculas
        self.metodos = []        # [(variable, metodo, argumentos, sentencia)]
        for s in fu.sentencias:
            a = flujo.asignacion(fu, s)
            if a:
                self.asignaciones.append((a[0], a[1], s))
                continue
            m = re.match(r"^(&[\w.]+)\.(\w+)\((.*)\)$", s.texto.strip().lower(), re.S)
            if m:
                self.metodos.append((m.group(1), m.group(2), m.group(3), s))
        self.creadas = []
        self.modificadas = []
        if self.bcs:
            self._clasificar()
            if self.creadas:
                de_entrada = self._de_entrada()
                for e in self.creadas:
                    self._claves(e, de_entrada)
                self._hijas()

    @property
    def principales(self):
        return [e for e in self.creadas if e.hija_de is None]

    # -------------------------------------------------------------- que crea cada BC

    def _clasificar(self):
        for var, trn in self.bcs.items():
            metodos = {}
            for v, m, _args, s in self.metodos:
                if v == var:
                    metodos.setdefault(m, s)
            # Un new() seguido del Load de la misma variable solo la limpia antes de cargarla: no es un alta.
            nuevo = otro = False
            for izq, der, s in self.asignaciones:
                if izq == var:
                    if der.startswith("new("):
                        nuevo |= not self._limpia_antes_de_load(var, s)
                    else:
                        otro = True
            if self._se_pasa(var) or "fromjson" in metodos:
                otro = True
            graba = metodos.get("save")
            if "insert" in metodos:
                e = Entidad(var, trn, f".Insert() en la linea {metodos['insert'].linea}", metodos["insert"])
            elif "insertorupdate" in metodos:
                e = Entidad(var, trn, f".InsertOrUpdate() en la linea {metodos['insertorupdate'].linea}",
                            metodos["insertorupdate"])
            elif graba and nuevo:
                que = "Load y new() si no existe (alta o modificacion)" if "load" in metodos else "new()"
                e = Entidad(var, trn, f".Save() en la linea {graba.linea} sobre un {que}", graba)
            elif graba and "load" not in metodos and not otro:
                e = Entidad(var, trn, f".Save() en la linea {graba.linea} sin Load antes", graba)
            else:
                if graba or "update" in metodos:
                    self.modificadas.append(var)
                continue
            self.creadas.append(e)

    def _limpia_antes_de_load(self, var, s):
        """&bc = new() / &bc.Load(...): la sentencia siguiente carga la misma variable."""
        ss = [x for x in self.fu.sentencias if not x.generada]
        i = next((n for n, x in enumerate(ss) if x is s), None)
        if i is None or i + 1 >= len(ss):
            return False
        return ss[i + 1].texto.strip().lower().startswith(var + ".load(")

    def _se_pasa(self, var):
        """El BC se le pasa a otro objeto (Proc(&bc), &x = Proc(&bc)): puede volver cargado."""
        patron = re.compile(re.escape(var) + r"(?![\w.])")
        for s in self.fu.sentencias:
            if s.clave in ("call", "submit") and patron.search(s.texto.lower()):
                return True
        return any(_LLAMADA_OBJETO.search(der) and patron.search(der) for _izq, der, _s in self.asignaciones)

    def _hijas(self):
        for e in self.creadas:
            mias = {k.lower() for k in e.trn.claves}
            for otra in self.creadas:
                if otra is not e and {k.lower() for k in otra.trn.claves} < mias:
                    e.hija_de = otra
                    break

    # -------------------------------------------------------------- de donde sale cada valor

    def _de_entrada(self):
        """Variables cuyo valor sale solo de los parametros de entrada (punto fijo, sin mirar el orden)."""
        por_var = {}
        for izq, der, _s in self.asignaciones:
            por_var.setdefault(izq, []).append(der)
        conocidas = set(por_var)
        cambio = True
        while cambio:
            cambio = False
            for var in list(conocidas):
                if not all(self._expresion_de_entrada(d, conocidas) for d in por_var[var]):
                    conocidas.discard(var)
                    cambio = True
        return conocidas

    def _expresion_de_entrada(self, expr, conocidas):
        sin_textos = _TEXTOS.sub("''", expr)
        if _LLAMADA_OBJETO.search(sin_textos):
            return False
        for nombre in _ATRIBUTO.findall(sin_textos):
            if nombre.lower() not in _PALABRAS and not nombre.isdigit():
                return False
        for v in _VAR.findall(sin_textos):
            if not (self._es_entrada(v) or v in conocidas):
                return False
        return True

    def _es_entrada(self, var):
        return any(var == p or var.startswith(p + ".") for p in self.entradas)

    def _claves(self, e, de_entrada):
        argumentos_load = []
        for v, m, args, _s in self.metodos:
            if v == e.var and m == "load":
                argumentos_load = flujo.partir_argumentos(args)
        for i, k in enumerate(e.trn.claves):
            campo = f"{e.var}.{k.lower()}"
            ders = [der for izq, der, _s in self.asignaciones if izq == campo]
            if ders:
                if all(self._expresion_de_entrada(d, de_entrada) for d in ders):
                    e.conocidas.add(k.lower())
            elif k not in e.trn.autonumeradas and i < len(argumentos_load) and \
                    self._expresion_de_entrada(argumentos_load[i], de_entrada):
                e.conocidas.add(k.lower())
            if self._se_devuelve(e.var, campo):
                e.devueltas.add(k.lower())

    # -------------------------------------------------------------- que se devuelve

    def _a_salida(self, izq):
        return izq.split(".")[0] in self.salidas

    def _se_devuelve(self, bc, campo):
        if bc in self.salidas:
            return True
        iguales = self._iguales(campo)
        entero = re.compile(re.escape(bc) + r"(\.tojson\(\))?$")
        for izq, der, _s in self.asignaciones:
            if self._a_salida(izq) and (any(_menciona(der, x) for x in iguales) or entero.match(der)):
                return True
        # La clave se copia a un campo de otra variable (&Item.Id = &bc.Id) que despues va a la salida
        # (&out.Ids.Add(&Item), &out.Item = &Item).
        contenedores = {izq.split(".")[0] for izq, der, _s in self.asignaciones
                        if "." in izq and der in iguales and not self._a_salida(izq)}
        for izq, der, _s in self.asignaciones:
            if self._a_salida(izq) and der in contenedores:
                return True
        for v, m, args, _s in self.metodos:
            if not self._a_salida(v):
                continue
            if m == "fromjson" and _menciona(args, bc):  # &out.Entidad.FromJson(&bc.ToJson())
                return True
            if m == "add" and any(_menciona(args, c) for c in contenedores):
                return True
        return False

    def _iguales(self, campo):
        """Expresiones que tienen el mismo valor que el atributo: el atributo del BC y las variables que se
        copian a el o desde el (&bc.Id = &Id, &Id = &bc.Id), hasta dos pasos."""
        iguales = {campo}
        for _ in range(2):
            for izq, der, _s in self.asignaciones:
                if izq in iguales and _VAR.fullmatch(der):
                    iguales.add(der)
                if der in iguales and _VAR.fullmatch(izq) and not self._a_salida(izq):
                    iguales.add(izq)
        return iguales


def _menciona(texto, var):
    return re.search(re.escape(var) + r"(?![\w])", texto) is not None
