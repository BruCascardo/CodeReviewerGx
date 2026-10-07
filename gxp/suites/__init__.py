"""Suites de prueba: formato, persistencia y ejecucion.

Una suite es un JSON en suites/<KB>/<nombre>.json:

{
  "nombre": "Interfases - Registro",
  "kb": "Generales",
  "descripcion": "...",
  "opciones": {"transaccion": "rollback", "recortarEspacios": true, "toleranciaNumerica": 0.000001,
               "listasParciales": false, "timeoutMs": 120000},
  "variables": {"itf": 1},
  "scriptPrevio": [{"ds": "GENERALES", "sql": "delete from a; delete from b"}],   # opcional, ver script.py
  "preparacion": [ <pasos que corren al principio de cada caso, dentro de su transaccion> ],
  "casos": [
    {
      "id": "alta-registro", "nombre": "Alta de un registro", "etiquetas": ["registro"], "omitir": false,
      "datos": [ {"tipo": "AAA"}, {"tipo": "BBB"} ],         # opcional: el caso se repite por fila
      "transaccion": "rollback",                                # opcional: pisa la de la suite
      "pasos": [
        {"nombre": "Alta", "objeto": "Generales.Interfases.Registro.Set",
         "entrada": {"inSet": {"ItfId": "${itf}", "Tipo": "${tipo}"}},
         "esperado": {"outSet": {"Output": {"Ok": true}}},
         "verificaciones": [{"ruta": "outSet.Output.Messages[*].Code", "op": "contiene", "valor": "OK"}],
         "guardar": {"regTipo": "outSet.RegTipo"},
         "ignorar": ["outSet.Output.Messages[*].Texto"],
         "lineaBase": {...},                                    # salida grabada (o lista por fila de datos)
         "esperaError": false, "errorContiene": ""},
        {"nombre": "Quedo en la tabla", "sql": "select count(*) n from gntItfRegistro where ItfRegTipo='${regTipo}'",
         "ds": "GENERALES", "verificaciones": [{"ruta": "filas[0].n", "op": "igual", "valor": 1}]}
      ]
    }
  ]
}
"""
# Modulos:
#   almacen.py     suites guardadas: formato normalizado, lectura, escritura, listado
#   variables.py   ${variables} de los pasos
#   script.py      script previo: sentencias, entorno de la corrida (savepoint por caso, rollback al final)
#   ejecucion.py   ejecucion de pasos y casos contra el motor; ejecucion suelta (Explorar)
#   grabacion.py   salidas aprobadas y valores que cambian solos
#   corridas.py    corrida de una suite
#   trabajos.py    corridas en segundo plano (interfaz)
#   resultados.py  resultados guardados y estado de la ultima corrida de cada caso
#   reportes.py    totales, texto de las fallas, JUnit XML
#   validaciones.py  casos de validacion generados a partir de una entrada valida
#   fechas.py      fechas relativas de las ${variables}: ${hoy+30}, ${fin_mes}...
from . import almacen, resultados, validaciones
from .corridas import correr_suite
from .ejecucion import correr_caso, ejecutar_suelto
from .grabacion import aceptar_linea_base, volatiles_de_caso
from .reportes import junit, texto_fallas, totales

__all__ = ["almacen", "resultados", "validaciones", "correr_suite", "correr_caso", "ejecutar_suelto", "aceptar_linea_base",
           "volatiles_de_caso", "junit", "texto_fallas", "totales"]
