"""Un procedimiento no usa variables que no declaro.

Marca, en los procedimientos, cada variable que aparece en una sentencia y no esta en la lista de variables
del objeto. Se buscan en los tokens, no en el texto: un "&Token=" dentro de un string no cuenta. Las
variables del sistema (GXV..., Gx_...) no se juzgan. Un hallazgo por variable.
"""
from . import Regla, registrar
from ..prolog import Comp

ARREGLO = ("El objeto usa &{v} pero no la declara. Declarala en la lista de variables con su tipo, o corregi "
           "el nombre si es un error de tipeo.")


def _variables_usadas(tokens):
    """Claves de las variables que aparecen en los tokens de una sentencia, como estan escritas."""
    if isinstance(tokens, Comp):
        if tokens.nombre == "t" and len(tokens.args) > 1 and tokens.args[1] == 23 and isinstance(tokens.args[0], str):
            yield tokens.args[0]
        else:
            yield from _variables_usadas(tokens.args)
    elif isinstance(tokens, (list, tuple)):
        for t in tokens:
            yield from _variables_usadas(t)


@registrar
class VariablesSinDeclarar(Regla):
    id = "variables-sin-declarar"
    titulo = "No hay variables usadas que no estan declaradas en el procedimiento"
    severidad = "advertencia"
    parametros = {
        # Tipos de objeto que se revisan.
        "tipos": ["proc", "mnproc"],
    }

    def aplica(self, fu, ctx):
        return fu.tipo in self.conf["tipos"]

    def revisar(self, fu, ctx):
        declaradas = {k.lower() for k in fu.variables} | {v["nombre"].lower() for v in fu.variables.values()}
        vistas = set()
        for sent in fu.sentencias:
            for clave in _variables_usadas(sent.tokens):
                if (clave.lower() in declaradas or clave.lower() in vistas
                        or clave.upper().startswith(("GXV", "GX_"))):
                    continue
                vistas.add(clave.lower())
                yield self.hallazgo(
                    fu, sent, f"La variable &{fu.variable(clave)} se usa y no esta declarada",
                    detalle=ARREGLO.format(v=fu.variable(clave)), ctx=ctx, variable=clave)
