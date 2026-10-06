"""Fuente GX de un objeto, leido de su especificacion (GXSPC*/GEN*/<Modulo>/.../<Objeto>.sp0).
La extension puede ser .sp0, .sp1, ... segun la KB: se toma la mas reciente.

El .sp0 trae el codigo del objeto ya tokenizado, linea por linea:
    b_line_i(36, 1, 1, cmd, 0, [ t('',107,36,0), t([t('Gntitfregistro',23), t('save(',1)],31), t(')',4) ])
El primer token dice que sentencia es (107 = asignacion o invocacion; 109 = If; ...) y el resto es la
expresion. Ademas trae el tipo de objeto (spec_i), las propiedades (rule_i(0,prop(..))), los parametros
(parmio), las variables con su tipo (attri_i con nombre), los atributos y tablas (attri_i y table_i con id)
y los dominios enumerados.

TODA la interpretacion de los codigos de GeneXus esta en este archivo (SENTENCIAS y la funcion texto): las
reglas trabajan sobre Fuente y Sentencia, sin ver numeros. Un codigo que no esta en la tabla no rompe nada:
la sentencia queda con clave 'desconocida' y se informa.
"""
import os
import threading
from pathlib import Path

from . import prolog
from .prolog import Comp

# ---------------------------------------------------------------------- tabla de codigos

# codigo -> (clave, palabra GX, efecto en la indentacion)
#   abre: la siguiente linea va un nivel adentro; cierra: esta linea va un nivel afuera;
#   medio: esta linea va un nivel afuera y la siguiente vuelve adentro (Else, Case).
# Relevado sobre todas las KBs y confirmado con el Java generado (ver la ayuda del comando 'revisar').
SENTENCIAS = {
    100: ("print", "Print", None),
    101: ("print", "Print", None),
    104: ("call", "", None),                      # Proc(&a, &b) / Proc.Call(...)
    107: ("asignacion", "", None),                # &a = expr  y tambien  &bc.Save()
    109: ("if", "If", "abre"),
    110: ("else", "Else", "medio"),
    111: ("endif", "EndIf", "cierra"),
    112: ("definedby", "Defined by", None),
    113: ("delete", "Delete", None),
    114: ("dowhile", "Do While", "abre"),
    115: ("enddo", "EndDo", "cierra"),
    117: ("new", "New", "abre"),
    118: ("return", "Return", None),
    121: ("foreach", "For Each", "abre"),
    122: ("print", "Header/Footer", None),
    127: ("endnew", "EndNew", "cierra"),
    128: ("endfor", "EndFor", "cierra"),
    129: ("whenduplicate", "When duplicate", "medio"),
    132: ("commit", "Commit", None),
    139: ("exit", "Exit", None),                  # dentro de un For Each
    140: ("exit", "Exit", None),                  # dentro de un Do While
    141: ("msg", "Msg(", None),
    143: ("sub", "Sub", "abre"),
    144: ("endsub", "EndSub", "cierra"),
    145: ("do", "Do", None),
    146: ("event", "Event", "abre"),
    147: ("endevent", "EndEvent", "cierra"),
    148: ("return", "Return", None),              # Return dentro de un evento
    149: ("forselected", "For each selected line", "abre"),
    150: ("endfor", "EndFor", "cierra"),
    152: ("docase", "Do Case", "abre"),
    153: ("case", "Case", "medio_case"),
    154: ("endcase", "EndCase", "cierra_case"),
    155: ("load", "Load", None),
    157: ("rollback", "Rollback", None),
    158: ("submit", "Submit", None),
    163: ("callmain", "Call", None),             # llamada generada a la version main del objeto
    164: ("otherwise", "Otherwise", "medio_case"),
    166: ("java", "Java", None),
    167: ("sql", "SQL", None),
    168: ("forline", "For each line in", "abre"),
    170: ("endfor", "EndFor", "cierra"),
    171: ("link", "Link", None),
    183: ("csharp", "CSharp", None),
    188: ("call", "", None),                      # llamada a un objeto web (popup, prompt)
    189: ("blocking", "Blocking", None),
    197: ("declaracion", "", None),
    200: ("call", "", None),                      # metodo de un objeto: Proc.metodo(...)
    # Objetos API: definicion de los servicios
    207: ("apiinicio", "{", "abre"),
    208: ("apifin", "}", "cierra"),
    209: ("apimetodo", "", None),                 # Get_V1(&in, &out)
    210: ("apimapeo", "=>", None),
    211: ("apianotacion", "", None),              # [RestMethod(POST)]
}

# Tipos de objeto de spec_i
TIPOS = {"proc": "Procedure", "mnproc": "Procedure (main)", "web": "Web Panel", "trn": "Transaction",
         "sdt": "SDT", "svcgrp": "API", "sdsvc": "SD service", "sync": "Offline database"}

# Clases de objeto en las referencias o(N, 'Nombre')
CLASE_OBJETO = {1: "procedimiento", 13: "web", 14: "externo", 33: "dataprovider"}


class Sentencia:
    __slots__ = ("linea", "codigo", "clave", "tokens", "nivel", "generada", "_fuente")

    def __init__(self, fuente, linea, codigo, tokens, generada=False):
        self._fuente = fuente
        self.linea = linea            # linea del fuente (int)
        self.codigo = codigo          # codigo GX (int) o None si la linea no es una sentencia (printblock)
        info = SENTENCIAS.get(codigo)
        self.clave = info[0] if info else ("printblock" if codigo is None else "desconocida")
        self.tokens = tokens          # tokens sin el primero (el del codigo)
        self.nivel = 0
        self.generada = generada      # lineas que GeneXus agrega al expandir un For in

    @property
    def texto(self):
        return texto_sentencia(self._fuente, self)

    def objetos(self):
        """[(clase, nombre con punto)] de los objetos que referencia la sentencia: llamadas, submit y las
        llamadas como funcion (&x = Proc(...)), que la especificacion anota aparte (function_i)."""
        salida = []
        _refs(self.tokens, salida, self._fuente.udps, self.linea)
        return salida

    def __repr__(self):
        return f"<{self.linea} {self.clave}: {self.texto}>"


def _udp(toks, i, udps, linea):
    """Si toks[i] abre una llamada como funcion (t('udp(',1), t(Variable,3), t(linea,3)), el objeto llamado."""
    t = toks[i]
    if not (isinstance(t, Comp) and t.nombre == "t" and t.args[0] == "udp(" and i + 2 < len(toks)):
        return None
    var, lin = toks[i + 1], toks[i + 2]
    if not (isinstance(var, Comp) and isinstance(lin, Comp)):
        return None
    return udps.get((str(var.args[0]).lower(), lin.args[0] if isinstance(lin.args[0], int) else linea))


def _refs(toks, salida, udps, linea):
    for i, t in enumerate(toks):
        if isinstance(t, Comp):
            if t.nombre == "o" and len(t.args) == 2 and isinstance(t.args[1], str):
                salida.append((t.args[0], t.args[1].replace("\\", ".")))
            else:
                destino = _udp(toks, i, udps, linea)
                if destino:
                    salida.append(destino)
                _refs(t.args, salida, udps, linea)
        elif isinstance(t, list):
            _refs(t, salida, udps, linea)


class Fuente:
    """Lo que el revisor sabe de un objeto."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.tipo = ""                # proc, web, trn, ... (TIPOS)
        self.nombre = ""              # Generales.Interfases.Registro.Set
        self.propiedades = {}
        self.parametros = []          # [(nombre real, 'in'|'out'|'inout')]
        self.variables = {}           # 'Outset' -> {'nombre': 'outSet', 'tipo': 'Generales\\...\\outSet' | 'char' ...}
        self.atributos = {}           # id -> nombre
        self.tablas = {}              # id -> nombre
        self.enumerados = {}          # id de dominio -> 'MessageTypes'
        self.sentencias = []
        self.desconocidas = set()     # codigos que no estan en SENTENCIAS
        self.udps = {}                # (variable, linea) -> (clase, objeto) de las llamadas &x = Proc(...)
        self.ilegibles = 0            # clausulas de la especificacion que no se pudieron leer

    # ------------------------------------------------------------------ propiedades utiles

    @property
    def tipo_texto(self):
        if self.tipo == "web" and self.propiedades.get("WEB_COMP") == "Yes":
            return "Web Component"
        return TIPOS.get(self.tipo, self.tipo)

    @property
    def commit_on_exit(self):
        """Propiedad Commit on exit (TRNEND en la especificacion). None si el objeto no la tiene."""
        v = self.propiedades.get("TRNEND")
        return None if v is None else v == "Yes"

    @property
    def generado_por_pattern(self):
        """Los objetos que genera WorkWithPlus (LoadDVCombo, ExportReport...) vienen marcados para que GXtest
        no los cuente en la cobertura. La falta de carpeta no sirve: hay objetos escritos a mano sin carpeta."""
        return self.propiedades.get("gxtest_ignoreForTestCoverage") == "-1"

    @property
    def es_bc(self):
        """Especificacion del Business Component de una transaccion (X_BC): repite el codigo de la transaccion."""
        return self.tipo == "trn" and self.nombre.endswith("_BC") and "Folder" not in self.propiedades

    def variable(self, clave):
        if isinstance(clave, int):  # en los reportes a veces viene un atributo por id
            return str(self.atributos.get(clave, clave))
        return self.variables.get(clave, {}).get("nombre", clave)

    def texto(self, numeros=True):
        """Fuente reconstruido, indentado, como texto GX."""
        lineas = []
        for s in self.sentencias:
            if s.generada:
                continue
            pref = f"{s.linea:5}  " if numeros else ""
            lineas.append(pref + "    " * s.nivel + s.texto)
        return "\n".join(lineas)


# ---------------------------------------------------------------------- lectura

_PREDICADOS = ["spec_i", "rule_i", "attri_i", "table_i", "enum_value_info_i", "function_i", "b_line_i"]
_cache = {}
_lock = threading.Lock()


def leer(ruta) -> Fuente:
    """Fuente de un .sp0. Se recuerda por fecha del archivo."""
    ruta = Path(ruta)
    mt = ruta.stat().st_mtime_ns
    with _lock:
        previo = _cache.get(str(ruta))
        if previo and previo[0] == mt:
            return previo[1]
    with open(ruta, encoding="cp1252", errors="replace") as f:
        texto = f.read()
    fu = _armar(ruta, texto)
    with _lock:
        _cache[str(ruta)] = (mt, fu)
    return fu


def _armar(ruta, texto):
    fu = Fuente(ruta)
    crudas = []
    ilegibles = [0]
    for nombre, c in prolog.clausulas(texto, _PREDICADOS, saltear=("rule_i(0,datastore(",), ilegibles=ilegibles):
        a = c.args
        if nombre == "spec_i":
            fu.tipo = str(a[0][0])
            fu.nombre = str(a[0][3]).replace("\\", ".")
        elif nombre == "rule_i":
            r = a[1]
            if not isinstance(r, Comp):
                continue
            if r.nombre == "prop" and len(r.args) == 2:
                v = r.args[1]
                fu.propiedades[str(r.args[0])] = v if isinstance(v, str) else repr(v)
            elif r.nombre == "parmio":
                fu.parametros = [(p[0], p[1]) for p in r.args[0] if isinstance(p, list) and len(p) == 2]
        elif nombre == "attri_i":
            clave, datos = a[0], a[1]
            if isinstance(clave, int):
                fu.atributos[clave] = datos[0]
            else:
                tipo = datos[1]
                if isinstance(tipo, Comp) and tipo.nombre == "o":
                    tipo = _nombre_tipo(tipo.args[0])
                fu.variables[clave] = {"nombre": str(datos[0]), "tipo": str(tipo)}
        elif nombre == "table_i":
            fu.tablas[a[0]] = str(a[1][0])
        elif nombre == "enum_value_info_i":
            fu.enumerados[a[1]] = str(a[2]).split("\\")[-1]
        elif nombre == "function_i" and len(a) >= 7 and isinstance(a[4], Comp) and a[4].nombre == "o":
            # function_i(1, Variable, yes, udp, o(1,'Modulo\Proc'), [], linea, Variable, [argumentos])
            fu.udps[(str(a[1]).lower(), a[6])] = (a[4].args[0], str(a[4].args[1]).replace("\\", "."))
        elif nombre == "b_line_i":
            crudas.append(c)
    # Los parametros vienen con el nombre normalizado ('Outset'): se pasa al nombre real de la variable.
    fu.parametros = [(fu.variable(n), io) for n, io in fu.parametros]
    fu.sentencias = _sentencias(fu, crudas)
    fu.ilegibles = ilegibles[0]
    return fu


def _nombre_tipo(t):
    if isinstance(t, Comp):  # objectcollection('X')
        return f"{t.nombre}({_nombre_tipo(t.args[0])})"
    return str(t)


def _sentencias(fu, crudas):
    salida = []
    for c in crudas:
        linea, toks = c.args[0], c.args[5]
        generada = isinstance(linea, list)
        if generada:
            linea = linea[0]
        if not toks:
            continue
        primero = toks[0]
        if isinstance(primero, Comp) and primero.nombre == "t" and primero.args[0] == "" and isinstance(primero.args[1], int):
            cod = primero.args[1]
            s = Sentencia(fu, linea, cod, toks[1:], generada)
            if cod not in SENTENCIAS:
                fu.desconocidas.add(cod)
        else:  # contenido de un printblock (reportes)
            s = Sentencia(fu, linea, None, toks, generada)
        salida.append(s)
    _for_in(salida)
    _indentar(salida)
    return salida


def _for_in(ss):
    """'For &x in &col' llega expandido: GXV1 = 1 / Do While GXV1 <= &col.Count / &x = &col.Item(GXV1) ...
    GXV1 = GXV1 + 1 / EndDo. Se marca como 'forin' / 'endfor' para mostrarlo como en el IDE."""
    for i, s in enumerate(ss):
        if s.clave != "dowhile" or not s.generada or i == 0:
            continue
        ini = ss[i - 1]
        if ini.clave == "asignacion" and _es_contador(ini.tokens) and ini.linea == s.linea:
            ini.generada = True
            s.clave = "forin"
            s.generada = False
            item = ss[i + 1] if i + 1 < len(ss) else None
            if item is not None and item.generada and item.linea == s.linea:
                item.generada = True
                s.tokens = ("forin", item.tokens, s.tokens)  # (&x = &col.item(GXV1)) y (GXV1 <= &col.Count)
    for i, s in enumerate(ss):
        if s.clave == "enddo" and s.generada:
            prev = ss[i - 1] if i else None
            if prev is not None and prev.generada and prev.linea == s.linea:
                s.clave, s.generada = "endfor", False


def _es_contador(toks):
    return bool(toks) and isinstance(toks[0], Comp) and isinstance(toks[0].args[0], str) and toks[0].args[0].startswith("GXV")


def _efecto(s):
    if s.clave == "forin":
        return "abre"
    if s.clave == "endfor" and s.codigo == 115:
        return "cierra"
    info = SENTENCIAS.get(s.codigo)
    return info[2] if info else None


def _indentar(ss):
    """Nivel de cada sentencia. En un Do Case, cada Case queda un nivel adentro y su cuerpo dos."""
    nivel, pila = 0, []
    for s in ss:
        ef = _efecto(s)
        if ef == "abre":
            s.nivel = nivel
            pila.append("case" if s.clave == "docase" else "bloque")
            nivel += 1
        elif ef == "cierra":
            if pila:
                pila.pop()
            nivel = max(0, nivel - 1)
            s.nivel = nivel
        elif ef == "medio":
            s.nivel = max(0, nivel - 1)
        elif ef == "medio_case":
            if pila and pila[-1] == "case_en":
                nivel = max(0, nivel - 1)
            elif pila:
                pila[-1] = "case_en"
            s.nivel = nivel
            nivel += 1
        elif ef == "cierra_case":
            if pila and pila.pop() == "case_en":
                nivel = max(0, nivel - 1)
            nivel = max(0, nivel - 1)
            s.nivel = nivel
        else:
            s.nivel = nivel


# ---------------------------------------------------------------------- texto GX

_OPS = {".AND.": " and ", ".OR.": " or ", ".NOT.": "not ", "=": " = ", "<=": " <= ", ">=": " >= ",
        "<>": " <> ", "<": " < ", ">": " > ", "+": " + ", "-": " - ", "*": " * ", "/": " / "}


def texto(fu, toks):
    """Expresion GX a partir de los tokens."""
    partes = []
    i = 0
    while i < len(toks):
        destino = _udp(toks, i, fu.udps, None)
        if destino:  # udp(Variable linea ...) -> Modulo.Proc(...)
            partes.append(destino[1] + "(")
            i += 3
            continue
        t = toks[i]
        sig = toks[i + 1] if i + 1 < len(toks) else None
        if (isinstance(t, Comp) and t.args[0] == "udp(" and isinstance(sig, Comp) and sig.args[1] == 28):
            # udp(Proc, args) -> Proc(args)
            partes.append(_token(fu, sig) + "(")
            i += 2
            if i < len(toks) and isinstance(toks[i], Comp) and toks[i].args[1] == 7:
                i += 1
            continue
        partes.append(_token(fu, toks[i]))
        i += 1
    s = "".join(partes)
    return s.replace("( ", "(").replace(" )", ")").strip()


def _token(fu, t):
    if not (isinstance(t, Comp) and t.nombre == "t"):
        if isinstance(t, Comp) and t.nombre == "o":
            return t.args[1].replace("\\", ".")
        if isinstance(t, Comp) and t.nombre == "v":  # 'in &coleccion' o 'in Dominio.Elements()'
            return texto(fu, t.args[0]) if isinstance(t.args[0], list) else _token(fu, t.args[0])
        if isinstance(t, Comp) and t.nombre == "c":  # 'in (a, b)'
            return "(" + ", ".join(texto(fu, x) for x in t.args[0]) + ")"
        return str(t)
    v, k = t.args[0], t.args[1]
    if k == 23:
        return "&" + fu.variable(v)
    if k == 2:
        return str(fu.atributos.get(v, f"attr{v}"))
    if k in (3, 36, 53, 30):
        return str(v)
    if k in (35, 39, 17, 19):  # WHEN, ORDER, IF, OTHERWISE
        return f" {v} "
    if k in (29, 31) and v and isinstance(v[0], Comp) and v[0].args[0] == "udp(":
        return texto(fu, v)  # Proc().Metodo(): la llamada es el primer tramo de la cadena
    if k in (29, 31):
        return ".".join(_miembro(fu, p, i) for i, p in enumerate(v)).replace("(.", "(")
    if k == 1:
        return _funcion(v)
    if k == 0:
        return "("
    if k == 4:
        return ")"
    if k == 7:
        return ", "
    if k in (5, 6, 8, 9, 10):
        return _OPS.get(v, f" {v} ")
    if k == 18:
        return "; "
    if k == 40:
        return "True"
    if k == 41:
        return "False"
    if k == 44:  # [dominio, 'Valor'], o el dominio solo (Dominio.EnumerationDescription(...))
        if isinstance(v, list) and isinstance(v[1], list):  # expresion convertida al dominio: se muestra la expresion
            return texto(fu, v[1])
        if isinstance(v, list):
            return f"{fu.enumerados.get(v[0], 'Enum')}.{v[1]}"
        return fu.enumerados.get(v, f"Dominio{v}")
    if k == 46:  # new: ['Tipo', [t('('), t(')')], n]
        return "new()"
    if k in (28, 72):
        return v.args[1].replace("\\", ".").split(".")[-1] if k == 72 else v.args[1].replace("\\", ".")
    if k == 1002:  # [o(1,'Proc'), 'metodo']
        return f"{v[0].args[1].replace(chr(92), '.')}.{v[1]}"
    if k == 49:  # For &x in &col
        return f"{_token(fu, v[0])} in {_token(fu, v[1])}"
    if k == 69:
        return "<imagen>"
    return f"«{k}:{v}»"


def _miembro(fu, p, i):
    if isinstance(p, Comp) and p.nombre == "t":
        v, k = p.args[0], p.args[1]
        if k == 3 and i > 0:
            return str(v)
        if k == 1:
            return _funcion(v)
    if isinstance(p, list):  # metodo con argumentos en el medio de la cadena: &col.Item(1).Campo
        return texto(fu, p)
    return _token(fu, p)


_FUNC = {"load(": "Load(", "save(": "Save(", "insert(": "Insert(", "update(": "Update(", "delete(": "Delete(",
         "fail(": "Fail(", "success(": "Success(", "add(": "Add(", "item(": "Item(", "getmessages(": "GetMessages(",
         "insertorupdate(": "InsertOrUpdate(", "check(": "Check(", "tojson(": "ToJson(", "fromjson(": "FromJson(",
         "setempty(": "SetEmpty(", "isempty(": "IsEmpty(", "clear(": "Clear(", "remove(": "Remove("}


def _funcion(v):
    return _FUNC.get(v, v)


def texto_sentencia(fu, s):
    if s.clave == "printblock":
        return "  ".join(texto(fu, [t]) for t in s.tokens)
    if s.clave == "forin":
        _, item, _cond = s.tokens
        # item: &x = &col.Item(GXV1)
        var = texto(fu, item[:1])
        col = ""
        if len(item) > 2 and isinstance(item[2], Comp) and isinstance(item[2].args[0], list):
            col = ".".join(_miembro(fu, p, i) for i, p in enumerate(item[2].args[0][:-1]))
        return f"For {var} in {col}"
    if s.clave == "endfor" and s.codigo == 115:
        return "EndFor"
    palabra = SENTENCIAS.get(s.codigo, ("", f"«sentencia {s.codigo}»", None))[1]
    resto = texto(fu, s.tokens)
    if s.clave == "call" and s.tokens:
        cabeza, args = texto(fu, s.tokens[:1]), texto(fu, s.tokens[1:])
        if s.codigo == 200:
            return resto
        return f"{cabeza}({args})" if not args.startswith("(") else cabeza + args
    if s.clave == "submit" and s.tokens:
        return f"{texto(fu, s.tokens[:1])}.Submit({texto(fu, s.tokens[1:])})"
    if s.clave == "foreach":
        partes = []
        for t in s.tokens:
            if isinstance(t, Comp) and t.args[1] == 3 and t.args[0] == "table":
                continue
            if isinstance(t, Comp) and t.args[1] == 3 and isinstance(t.args[0], int):
                partes.append(fu.tablas.get(t.args[0], f"tabla{t.args[0]}"))
                continue
            partes.append(_token(fu, t).strip())
        return ("For Each " + " ".join(partes)).strip()
    if s.clave in ("msg",):
        return "Msg(" + resto
    if s.clave == "apianotacion":
        return f"[{resto}]"
    if s.clave in ("java", "csharp", "sql"):
        return f"{palabra} {resto}"
    if not palabra:
        return resto
    return f"{palabra} {resto}".strip()


# ---------------------------------------------------------------------- ubicacion en la KB

def carpetas_spec(kb):
    """Carpetas GXSPC*/GEN* de la KB que tienen especificaciones (.sp0)."""
    salida = []
    for gxspc in sorted(kb.carpeta.glob("GXSPC*")):
        for gen in sorted(gxspc.glob("GEN*")):
            if gen.is_dir():
                salida.append(gen)
    return salida


def es_spec(nombre):
    """True para Objeto.sp0, Objeto.sp1, ... (sin los GXSDT_, que son la estructura de los SDT)."""
    return len(nombre) > 4 and nombre[-4:-1].lower() == ".sp" and nombre[-1].isdigit() and not nombre.startswith("GXSDT_")


def ubicar(kb, objeto: str):
    """Ruta de la especificacion de un objeto (Generales.Interfases.Registro.Set), o None. Si esta en mas
    de un generador o modelo, o con mas de una extension (.sp0, .sp1), la mas reciente."""
    partes = objeto.strip().split(".")
    cands = []
    for gen in carpetas_spec(kb):
        carpeta = gen.joinpath(*partes[:-1])
        for r in carpeta.glob(partes[-1] + ".sp[0-9]"):
            try:
                cands.append((r.stat().st_mtime, r))
            except OSError:
                continue
    return max(cands)[1] if cands else None


def listar(kb):
    """[(ruta, mtime)] de la especificacion de cada objeto de la KB (sin los GXSDT_ ni la navegacion)."""
    vistos = {}
    for gen in carpetas_spec(kb):
        pila = [str(gen)]
        while pila:
            try:
                with os.scandir(pila.pop()) as it:
                    for e in it:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                if e.name != "NVG":
                                    pila.append(e.path)
                            elif es_spec(e.name):
                                rel = os.path.relpath(e.path, gen)[:-4].lower()
                                mt = e.stat().st_mtime
                                if rel not in vistos or vistos[rel][1] < mt:
                                    vistos[rel] = (e.path, mt)
                        except OSError:
                            continue
            except OSError:
                continue
    return sorted(vistos.values())
