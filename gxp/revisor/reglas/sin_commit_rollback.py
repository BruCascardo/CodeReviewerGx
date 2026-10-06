"""Solo los Web Panels y Web Components confirman o deshacen la transaccion.

Marca, en cualquier otro objeto:
  - las sentencias Commit y Rollback;
  - las llamadas a los procedimientos que lo hacen por su cuenta (prcCommit, prcRollback de cualquier modulo);
  - codigo Java nativo que hace commit o rollback (advertencia: puede ser otra cosa);
  - en los procedimientos, la propiedad Commit on exit = Yes. Es error si el Java generado confirma
    (commitDataStores) y advertencia si hoy no lo hace: GeneXus genera el commit al salir solo cuando el
    objeto actualiza la base con sus propios comandos (New, For Each), no a traves de un Business Component.

Las transacciones confirman por su cuenta por diseno: solo se les marca un Commit o Rollback explicito.
"""
import re

from . import Regla, registrar

ARREGLO = ("La transaccion la confirma (o la deshace) el Web Panel o Web Component que inicia la operacion. "
           "Saca el commit de aca y, si hace falta, ponelo en el Web Panel que llama a este objeto. Si este caso "
           "esta justificado, agrega una excepcion en revisor.json con el motivo.")

# commitDataStores, "Commit" en un ExecuteDirectSQL... pero no heap.getCommitted() ni getUncommitedChanges().
_JAVA_COMMIT = re.compile(r"\b(commit|rollback)(datastores)?\b", re.I)


@registrar
class SinCommitRollback(Regla):
    id = "sin-commit-rollback"
    titulo = "Solo los Web Panels y Web Components hacen commit o rollback"
    severidad = "error"
    parametros = {
        # Tipos de objeto (spec_i) que pueden confirmar: web = Web Panel y Web Component.
        "tiposPermitidos": ["web"],
        # Procedimientos que confirman o deshacen por su cuenta (ultimo tramo del nombre, en cualquier modulo).
        "objetosCommit": ["prcCommit", "prcRollback"],
        # Tipos en los que se controla la propiedad Commit on exit.
        "commitOnExit": ["proc", "mnproc"],
    }

    def aplica(self, fu, ctx):
        return fu.tipo not in self.conf["tiposPermitidos"] and fu.tipo != "sdt"

    def revisar(self, fu, ctx):
        nombres = {n.lower() for n in self.conf["objetosCommit"]}
        for s in fu.sentencias:
            if s.generada:
                continue
            if s.clave in ("commit", "rollback"):
                yield self.hallazgo(fu, s, f"{s.texto} explicito: solo los Web Panels y Web Components pueden hacerlo",
                                    detalle=ARREGLO, ctx=ctx)
            elif s.clave in ("java", "csharp") and _JAVA_COMMIT.search(s.texto):
                yield self.hallazgo(fu, s, "Codigo nativo que parece hacer commit o rollback",
                                    detalle=ARREGLO, severidad="advertencia", ctx=ctx)
            else:
                for _clase, obj in s.objetos():
                    if obj.split(".")[-1].lower() in nombres:
                        yield self.hallazgo(fu, s, f"Llama a {obj}, que hace commit o rollback",
                                            detalle=ARREGLO, ctx=ctx, llamado=obj)
        if fu.tipo in self.conf["commitOnExit"] and fu.commit_on_exit:
            confirma = ctx.java_confirma(fu.nombre)
            if confirma is False:
                yield self.hallazgo(
                    fu, None, "Commit on exit = Yes",
                    detalle="Hoy el Java generado no confirma al terminar: GeneXus genera ese commit solo si el "
                            "objeto actualiza la base con sus propios comandos (New, For Each), no con un Business "
                            "Component. Confirmaria en cuanto se agregue uno. Cambia la propiedad Commit on exit a No.",
                    severidad="advertencia", ctx=ctx)
            else:
                yield self.hallazgo(
                    fu, None, "Commit on exit = Yes: confirma la transaccion al terminar",
                    detalle="Cambia la propiedad Commit on exit a No. " + ARREGLO, ctx=ctx)
