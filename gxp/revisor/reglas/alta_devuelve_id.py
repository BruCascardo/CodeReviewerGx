"""Un procedimiento que crea una entidad devuelve su clave (el id).

Es heuristica (advertencia) y cada hallazgo dice por que tomo al objeto como alta. Ver gxp/revisor/altas.py:
que BC crea, que parte de la clave ya conoce el que llama (viene de la entrada) y que se devuelve.

  - Se exige la clave de las entidades principales: las que crea el objeto y no son hijas de otra que
    tambien crea (una hija tiene en su clave la de la otra, como el documento de una persona).
  - Solo se exige lo que el que llama no conoce: lo autonumerado, lo que sale de un numerador o de la base.
  - El alta puede ser secundaria: un objeto que hace otra cosa (consulta, actualiza, importa, marca) y de
    paso crea un registro. Por eso, si el nombre es de alta ('nombresAlta': Crear, Set, Registrar...) se
    revisa siempre; si es de otra operacion ('nombresOtraOperacion': Actualizar, Obtener, Importar...) no
    se revisa; y si no dice, se revisa salvo que el objeto ademas modifique otra entidad.
  - Por ahora solo Business Components: el comando New no trae en el fuente cual es la clave de su tabla.
"""
import re

from . import Regla, registrar
from .. import altas

D_FALTA = ("Lo tome como alta por {motivo}. La clave de {trn} es {claves}{auto}. {faltan} no viene de los parametros "
           "de entrada: el que llama no tiene como saber el id de lo que se creo. Despues del Save, devolvelo en un "
           "parametro de salida: &out.{ejemplo} = {var}.{ejemplo}.")
D_SIN_SALIDA = ("Lo tome como alta por {motivo} y por el nombre. La clave de {trn} es {claves}{auto}. El objeto no tiene "
                "parametros de salida: agrega uno para devolver el id de lo que se creo.")


@registrar
class AltaDevuelveId(Regla):
    id = "alta-devuelve-id"
    titulo = "Un procedimiento que crea una entidad devuelve su clave"
    severidad = "advertencia"
    parametros = {
        "tipos": ["proc", "mnproc"],
        # Ultimo tramo del nombre que dice que el objeto es un alta (expresion regular, sin distinguir mayusculas).
        "nombresAlta": r"^(set|put|crear|alta|agregar|insert|nuev[oa]|registrar|guardar|grabar|new|add)"
                       r"|(set|put|crear|alta|agregar|insert|nuev[oa]|registrar|guardar|grabar|new|add)\d*$",
        # Parte del nombre que dice que el objeto hace otra cosa y el alta es secundaria.
        "nombresOtraOperacion": r"(get|lista|obtener|buscar|consulta|actualizar|modificar|update|delete|eliminar|"
                                r"borrar|baja|cambiar|cambio|mover|marcar|leido|procesar|check|enviar|validar|"
                                r"calcular|importar|carga|migra|confirmar)",
        # Transacciones cuya clave no se exige: historiales y logs (sobre el ultimo tramo del nombre).
        "entidadesExcluidas": r"(hist|historial|history|log|bitacora|auditoria)(_bc)?$",
    }

    def aplica(self, fu, ctx):
        return fu.tipo in self.conf["tipos"]

    def nombre_de_alta(self, fu):
        return re.search(self.conf["nombresAlta"], fu.nombre.split(".")[-1], re.I) is not None

    def nombre_de_otra_operacion(self, fu):
        return re.search(self.conf["nombresOtraOperacion"], fu.nombre.split(".")[-1], re.I) is not None

    def excluida(self, trn):
        return re.search(self.conf["entidadesExcluidas"], trn.nombre.split(".")[-1], re.I) is not None

    def revisar(self, fu, ctx):
        an = altas.Analisis(fu, ctx)
        if not [e for e in an.creadas if not self.excluida(e.trn)]:
            return
        de_alta = self.nombre_de_alta(fu)
        if not de_alta and (self.nombre_de_otra_operacion(fu) or an.modificadas):
            return
        for e in an.principales:
            if self.excluida(e.trn):
                continue
            trn = e.trn.nombre.split(".")[-1]
            datos = dict(motivo=e.motivo, trn=trn, claves=", ".join(e.trn.claves), var=_como_se_escribe(fu, e.var),
                         auto=f" ({', '.join(sorted(e.trn.autonumeradas))} autonumerada)" if e.trn.autonumeradas else "")
            if not an.salidas:
                if de_alta:
                    yield self.hallazgo(fu, e.sentencia, f"Crea {trn} y no tiene parametros de salida para devolver su id",
                                        detalle=D_SIN_SALIDA.format(**datos), ctx=ctx, entidad=e.trn.nombre)
                continue
            faltan = e.faltan
            if faltan:
                yield self.hallazgo(fu, e.sentencia, f"Crea {trn} y no devuelve su clave ({', '.join(faltan)})",
                                    detalle=D_FALTA.format(faltan=", ".join(faltan), ejemplo=faltan[0], **datos),
                                    ctx=ctx, entidad=e.trn.nombre, faltan=faltan)


def _como_se_escribe(fu, var):
    for v in fu.variables.values():
        if "&" + v["nombre"].lower() == var:
            return "&" + v["nombre"]
    return var
