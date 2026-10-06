"""Un objeto que devuelve un sdtOutput lo deja coherente: Ok y mensajes dicen lo mismo.

Aplica a los procedimientos con un parametro out o inout que es un sdtOutput o lo tiene adentro
(&outSet.Output). Recorre los caminos del fuente (ver flujo.py) y, en cada salida (Return o fin), controla:

  - si se agrego un mensaje de tipo Error, Ok tiene que ser False. Sistema.Output.AddMessage y
    Messages.Add solo agregan el mensaje: el Ok lo tiene que poner el objeto;
  - si Ok es False, tiene que haber un mensaje de tipo Error;
  - Ok tiene que asignarse: un Boolean de GX arranca en False, asi que sin Ok = True devuelve False aunque
    todo salga bien;
  - si termina con Ok = True, tiene que haber un mensaje de exito, que es Type = MessageTypes.Debug. Un Info
    en su lugar es advertencia: se toma como exito, pero hay que cambiarlo a Debug;
  - los mensajes no se agregan a un sdtOutput propio del objeto que despues no se copia a la salida.

Los caminos que no se pueden seguir (la salida pasada a otro objeto, mensajes de tipo desconocido, lo que
depende de las vueltas de un bucle) no se juzgan: esta regla prefiere callar a inventar. Lo que se le
escapa lo controla la capa dinamica sobre las ejecuciones reales de las suites (gxp/revisor/salida.py).
"""
import re

from . import Regla, registrar
from .. import flujo

D_ERROR_CON_OK = ("Sistema.Output.AddMessage y &x.Messages.Add() solo agregan el mensaje: no tocan el Ok. "
                  "Despues de agregar un mensaje de tipo Error pone {s}.Ok = False.")
D_OK_FALSE = "Cada Ok = False tiene que llevar un mensaje de tipo Error que diga por que fallo."
D_SIN_OK = ("Un Boolean de GX arranca en False: si no se asigna {s}.Ok = True, el objeto devuelve False aunque todo "
            "salga bien. Pone Ok = True al principio y Ok = False junto a cada mensaje de error.")
D_SIN_EXITO = ("Cuando termina bien (Ok = True) tiene que devolver un mensaje de exito: Type = MessageTypes.Debug, "
               "con Code y texto que digan que se hizo.")
D_LOCAL = ("{local} es un sdtOutput propio del objeto y nunca se copia a la salida: sus mensajes se pierden. Agrega los "
           "mensajes directamente a {s} (Sistema.Output.AddMessage(texto, tipo, {s})) o copiala al final: {s} = {local}.")
D_INFO = "El mensaje de exito es Type = MessageTypes.Debug. Info queda para mensajes informativos que no son el exito."


@registrar
class SalidaOkMensajes(Regla):
    id = "salida-ok-mensajes"
    titulo = "El Ok y los mensajes del sdtOutput son coherentes y hay mensaje de exito (Debug)"
    severidad = "error"
    parametros = {
        # SDT de salida (ultimo tramo del nombre, en cualquier modulo).
        "sdt": "sdtOutput",
        # Tipos de objeto que se revisan.
        "tipos": ["proc", "mnproc"],
        # Procedimientos que agregan un mensaje a una salida: posicion (desde 1) del tipo de mensaje y de la
        # salida. tipo null: el tipo no se conoce (copia mensajes de otra coleccion).
        "ayudantes": {
            "Sistema.Output.AddMessage": {"tipo": 2, "salida": 3},
            "Sistema.Output.AddMessages": {"tipo": None, "salida": 2},
        },
    }

    def salidas(self, fu, ctx):
        """({expresion en minusculas: como se escribe} de los sdtOutput que devuelven los parametros out/inout,
        lo mismo para las variables que son un sdtOutput). Las variables se suelen armar y copiar a la salida
        al final (&outSet.Output = &sdtOutput)."""
        sdt = self.conf["sdt"].lower()
        por_nombre = {v["nombre"].lower(): v for v in fu.variables.values()}
        devueltas = {}
        for nombre, io in fu.parametros:
            v = por_nombre.get(nombre.lower())
            if io not in ("out", "inout") or not v:
                continue
            for ruta in ctx.rutas_sdt(v["tipo"], self.conf["sdt"]):
                if "[*]" not in ruta:
                    expr = "&" + nombre + ("." + ruta if ruta else "")
                    devueltas[expr.lower()] = expr
        locales = {}
        if devueltas:
            for v in fu.variables.values():
                expr = "&" + v["nombre"]
                if v["tipo"].split("\\")[-1].lower() == sdt and expr.lower() not in devueltas:
                    locales[expr.lower()] = expr
        return devueltas, locales

    def aplica(self, fu, ctx):
        return fu.tipo in self.conf["tipos"] and bool(self.salidas(fu, ctx)[0])

    def revisar(self, fu, ctx):
        devueltas, locales = self.salidas(fu, ctx)
        nombre = next(iter(devueltas.values()))
        salidas = dict(devueltas)
        for clave, local in locales.items():
            if _se_devuelve(fu, clave, devueltas):
                salidas[clave] = local
            else:
                s = _primer_mensaje(fu, clave, self.conf["ayudantes"])
                if s is not None:
                    yield self.hallazgo(fu, s, f"Agrega mensajes a {local}, que no se devuelve: no llegan a {nombre}",
                                        detalle=D_LOCAL.format(local=local, s=nombre), ctx=ctx)
        try:
            an = flujo.Analisis(fu, salidas, self.conf["ayudantes"]).correr()
        except flujo.Complejo:
            return
        vistos = set()

        def una_vez(clave, h):
            if clave not in vistos:
                vistos.add(clave)
                return [h]
            return []

        delega = any(e.ok == flujo.DESCONOCIDO for e, _ in an.salidas)
        if not an.asigna_ok and not delega:
            yield self.hallazgo(fu, None, f"Nunca asigna {nombre}.Ok = True: siempre devuelve Ok = False",
                                detalle=D_SIN_OK.format(s=nombre), ctx=ctx)
        for e, fin in an.salidas:
            donde = f" (camino que sale en la linea {fin.linea})" if fin is not None else ""
            if e.error is True and e.ok is True:
                yield from una_vez(("error", e.error_s), self.hallazgo(
                    fu, e.error_s, f"Agrega un mensaje de tipo Error pero termina con Ok = True{donde}",
                    detalle=D_ERROR_CON_OK.format(s=nombre), ctx=ctx))
            elif e.ok is False and e.error is False:
                yield from una_vez(("ok-false", e.ok_s), self.hallazgo(
                    fu, e.ok_s, f"Ok = False sin ningun mensaje de tipo Error{donde}", detalle=D_OK_FALSE, ctx=ctx))
            elif e.ok is None and e.error is False and an.asigna_ok:
                yield from una_vez(("sin-ok", fin), self.hallazgo(
                    fu, fin, f"Llega al final sin asignar Ok (devuelve False) y sin mensaje de error{donde}",
                    detalle=D_SIN_OK.format(s=nombre), ctx=ctx))
            elif e.ok is True and e.error is False:
                if e.exito is None:
                    yield from una_vez(("sin-exito", e.ok_s), self.hallazgo(
                        fu, e.ok_s, f"Termina con Ok = True sin mensaje de exito (Type Debug){donde}",
                        detalle=D_SIN_EXITO, ctx=ctx))
                elif e.exito == "info":
                    yield from una_vez(("info", e.exito_s), self.hallazgo(
                        fu, e.exito_s, "El mensaje de exito es de tipo Info: tiene que ser Debug",
                        detalle=D_INFO, severidad="advertencia", ctx=ctx))


def _menciona(texto, var):
    return re.search(re.escape(var) + r"(?![\w])", texto) is not None


def _se_devuelve(fu, local, devueltas):
    """La variable se copia a una salida: &outSet.Output = &sdtOutput (o a un campo, o a todo el parametro)."""
    for s in fu.sentencias:
        a = flujo.asignacion(fu, s)
        if a and _menciona(a[1], local) and any(d == a[0] or d.startswith(a[0] + ".") or a[0].startswith(d + ".")
                                               for d in devueltas):
            return True
    return False


def _primer_mensaje(fu, local, ayudantes):
    """La primera sentencia que le agrega un mensaje a la variable, o None si no recibe mensajes."""
    nombres = {n.lower() for n in ayudantes}
    for s in fu.sentencias:
        if s.generada:
            continue
        texto = s.texto.lower()
        if not _menciona(texto, local):
            continue
        if f"{local}.messages.add(" in texto or f"{local}.errores.add(" in texto:
            return s
        ll = flujo.llamada(texto)
        if ll and ll[0] in nombres:
            return s
    return None
