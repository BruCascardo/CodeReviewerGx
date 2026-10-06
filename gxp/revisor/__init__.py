"""Revisor de buenas practicas sobre el fuente GX de los objetos (comando 'revisar').

  prolog.py         lector del formato de la especificacion (terminos Prolog)
  fuente.py         lee el fuente de la especificacion (.sp0); toda la tabla de codigos de GeneXus esta ahi
  estructura.py     bloques del fuente: que esta dentro de que If, Case, For Each o Sub
  sdts.py           estructura de los SDT (GXSDT_*.sp0): en que ruta de un parametro hay un sdtOutput
  flujo.py          caminos del fuente siguiendo el Ok y los mensajes de un sdtOutput
  salida.py         control de los sdtOutput de las ejecuciones reales (capa dinamica, la usan las suites)
  reglas/           una regla por archivo; se registran solas
  configuracion.py  revisor.json: reglas activas, parametros, objetos ignorados y excepciones
  lineabase.py      lo que ya estaba en cada objeto, para marcar lo NUEVO
  revisor.py        corre las reglas y guarda el resultado en resultados/revisiones/
  panel.py          datos de la pantalla Revision
"""
