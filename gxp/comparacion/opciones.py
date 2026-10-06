"""Opciones de comparacion (las 'opciones' de una suite, mas 'ignorar' y 'volatiles' de cada paso)."""
from .rutas import patron_ignorar

# Lo que define si un objeto termino bien o mal, segun la convencion de las APIs (Sistema.Global.sdtOutput).
# Rutas relativas a cada parametro de salida. Se pueden cambiar con "camposClave" en las opciones.
CAMPOS_CLAVE = ["Output.Ok", "Output.Messages[*].Code"]


class Opciones:
    def __init__(self, recortarEspacios=True, toleranciaNumerica=1e-6, listasParciales=False, ignorar=None,
                 volatiles=None, camposClave=None, **_):
        self.recortar = recortarEspacios
        self.tol = float(toleranciaNumerica or 0)
        self.listas_parciales = listasParciales
        self.ignorar = [patron_ignorar(i) for i in (ignorar or []) if i and i.strip()]
        self.volatiles = [patron_ignorar(i) for i in (volatiles or []) if i and i.strip()]
        self.campos_clave = camposClave or CAMPOS_CLAVE

    def ignorada(self, ruta):
        return any(p.search(ruta) for p in self.ignorar)

    def volatil(self, ruta):
        return any(p.search(ruta) for p in self.volatiles)
