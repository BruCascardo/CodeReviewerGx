"""Lo que la pantalla de una transaccion hace y su Business Component no.

Las APIs graban con el Business Component: lo que solo esta en la pantalla (reglas que usan variables del form,
reglas con [web], eventos como After Trn) no corre cuando se graba desde un procedimiento. Compara el Java de la
pantalla con el del BC (ver gxp/revisor/pantalla_bc.py) y marca:
  - las llamadas a procedimientos que graban en la base;
  - las llamadas en una regla seguidas de un error (validaciones);
  - los mensajes de error de una regla que el BC no tiene.
Las reglas no estan en el fuente que lee el revisor: esos hallazgos van sin linea. Los de un evento llevan la
linea de la llamada.
"""
from . import Regla, registrar

TEXTOS = {
    "graba": "La pantalla graba con {objeto} ({lugar}) y el Business Component no",
    "valida": "La pantalla valida con {objeto} ({lugar}) y el Business Component no",
    "error": "Solo la pantalla da el error «{mensaje}» ({lugar})",
}
DETALLE = ("Un procedimiento o una API que graba con el Business Component no lo ejecuta, asi que puede grabar lo que la "
           "pantalla no deja. Si es una regla de negocio, hace que corra tambien en el BC: que no use variables de la "
           "pantalla ni lleve [web], o pasala a un procedimiento que llamen la pantalla y las APIs. Si es propio de la "
           "pantalla (subir un archivo, cargar un combo), agrega una excepcion en revisor.json con el motivo.")


@registrar
class LogicaSoloEnPantalla(Regla):
    id = "logica-solo-en-pantalla"
    titulo = "Lo que valida o graba la pantalla de una transaccion tambien lo hace su Business Component"
    severidad = "advertencia"

    def aplica(self, fu, ctx):
        return fu.tipo == "trn" and not fu.es_bc

    def revisar(self, fu, ctx):
        for d in ctx.diferencias_bc(fu.nombre):
            s = self._sentencia(fu, d["objeto"]) if d["objeto"] else None
            yield self.hallazgo(fu, s, TEXTOS[d["tipo"]].format(**{"mensaje": "", **d}), detalle=DETALLE, ctx=ctx,
                                diferencia=d["tipo"], **({"llamado": d["objeto"]} if d["objeto"] else {}))

    @staticmethod
    def _sentencia(fu, objeto):
        """La sentencia del fuente (un evento) que llama al objeto, o None (las reglas no estan en el fuente)."""
        corto = objeto.split(".")[-1].lower()
        for s in fu.sentencias:
            if not s.generada and any(o.split(".")[-1].lower() == corto for _c, o in s.objetos()):
                return s
        return None
