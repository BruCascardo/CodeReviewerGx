"""Rutas, comparaciones y verificaciones.

Rutas: "outSet.Output.Messages[0].Code", "outList.Registros[*].Tipo", "filas[0].cantidad".
  - [n] indice (base 0; negativo cuenta desde el final), [*] todos los elementos.
  - Los nombres se buscan primero exactos y despues sin distinguir mayusculas.

Comparacion parcial ("esperado"): solo se controla lo que esta en el esperado.
Comparacion con la salida aprobada ("lineaBase"), con dos modos:
  - "todo" (por defecto): todo tiene que coincidir, salvo las rutas de "ignorar". En las rutas "volatiles"
    (valores que cambian solos entre ejecuciones: fechas, ids nuevos) solo se controla el tipo.
  - "estructura": las mismas claves y tipos, mas Ok y los codigos de mensaje (CAMPOS_CLAVE). Para salidas
    con datos de la base que cambian.
  En los dos: un campo nuevo en la salida es un aviso, no una falla, y una coleccion o subestructura que
  GeneXus omite del JSON por estar vacia equivale a una vacia.

En los valores esperados se pueden usar comodines de texto:
  <<cualquiera>> <<no_vacio>> <<vacio>> <<numero>> <<texto>> <<booleano>> <<fecha>> <<fechahora>>
  <<regex:patron>> <<contiene:texto>> <<empieza:texto>> <<mayor:n>> <<menor:n>> <<distinto:valor>>
"""
# Modulos:
#   rutas.py           lenguaje de rutas (obtener, patrones de 'ignorar')
#   valores.py         numeros, vacios, tipos, texto para mostrar
#   igualdad.py        igualdad de valores simples y comodines (tabla COMODINES)
#   opciones.py        Opciones de comparacion y CAMPOS_CLAVE
#   comparar.py        parcial, total, estructura, aprobada
#   verificaciones.py  operadores (tabla OPERADORES) y verificar
#   resumen.py         agrupado legible de diferencias
#   volatiles.py       valores que cambian solos
#   sugerencias.py     verificaciones propuestas para una salida
from .comparar import aprobada, parcial
from .opciones import CAMPOS_CLAVE, Opciones
from .resumen import resumir, texto_grupo
from .rutas import clave, obtener, patron_de
from .sugerencias import sugerir
from .valores import describir
from .verificaciones import OPERADORES, verificar
from .volatiles import detectar_volatiles, volatiles_por_valor


def descripcion_operadores():
    """{operador: descripcion}, para la ayuda."""
    return {k: op.descripcion for k, op in OPERADORES.items()}


__all__ = ["aprobada", "parcial", "CAMPOS_CLAVE", "Opciones", "resumir", "texto_grupo", "clave", "obtener",
           "patron_de", "sugerir", "describir", "OPERADORES", "verificar", "detectar_volatiles",
           "volatiles_por_valor", "descripcion_operadores"]
