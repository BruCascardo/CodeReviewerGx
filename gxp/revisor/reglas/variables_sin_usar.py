"""Un procedimiento no declara variables que no usa.

Marca, en los procedimientos, cada variable declarada que no aparece en ninguna sentencia del fuente ni es
un parametro (parm). Las variables del sistema (GXV..., Gx_...) no se juzgan. Un hallazgo por variable.
"""
import re

from . import Regla, registrar

ARREGLO = ("Una variable que no se usa confunde a quien lee el objeto y suele ser resto de un cambio anterior. "
           "Borrala de la lista de variables del objeto. Si se usa desde codigo que el revisor no ve "
           "(por ejemplo Java nativo), agrega una excepcion en revisor.json con el motivo.")


@registrar
class VariablesSinUsar(Regla):
    id = "variables-sin-usar"
    titulo = "No hay variables declaradas que no se usan en el procedimiento"
    severidad = "advertencia"
    parametros = {
        # Tipos de objeto que se revisan.
        "tipos": ["proc", "mnproc"],
    }

    def aplica(self, fu, ctx):
        return fu.tipo in self.conf["tipos"] and bool(fu.variables)

    def revisar(self, fu, ctx):
        usadas = {n.lower() for n, _ in fu.parametros}
        texto = "\n".join(s.texto for s in fu.sentencias).lower()
        usadas |= {m.group(1) for m in re.finditer(r"&(\w+)", texto)}
        for v in sorted(fu.variables.values(), key=lambda v: v["nombre"].lower()):
            nombre = v["nombre"]
            if nombre.lower() in usadas or nombre.upper().startswith(("GXV", "GX_")):
                continue
            yield self.hallazgo(fu, None, f"La variable &{nombre} esta declarada y no se usa",
                                detalle=ARREGLO, ctx=ctx, variable=nombre)
