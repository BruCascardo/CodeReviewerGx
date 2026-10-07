# GxPruebas: instrucciones para Claude

GxPruebas ejecuta y prueba los procedimientos y Data Providers de cualquier KB de GeneXus compilada en Java (`C:\KBGXSERVER\CORE\<KB>`), sin el IDE. Usalo para **validar con datos reales** lo que cambia en la KB, en lugar de razonar solo sobre el Java generado.

El formato de las suites, los operadores y los comodines están en `LEEME.md`.

## Comandos

Todos se corren desde esta carpeta (`C:\Users\xiku\Desktop\GxPruebas`).

```bat
python gxpruebas.py describir --kb Generales --objeto Generales.Interfases.Registro.Set
python gxpruebas.py ejecutar  --kb Generales --objeto Generales.Interfases.Registro.Get --entrada "{\"inGet\":{\"ItfId\":1,\"RegTipo\":\"DETALLE\"}}"
python gxpruebas.py ejecutar  --kb Generales --objeto ... --entrada @archivo.json --sql "GENERALES: select ..."
python gxpruebas.py sql       --kb Generales --ds GENERALES "select ..."
python gxpruebas.py plan      --kb Generales --objeto Generales.Empresas.Get [--detalle]   :: EXPLAIN de sus sentencias SQL y recomendaciones de indices
python gxpruebas.py correr    [suite] [--kb KB] [--filtro texto] [--etiqueta e] [--detalle]
python gxpruebas.py correr    <suite> --grabar        :: aprueba las salidas: solo si el usuario confirma que son las correctas
python gxpruebas.py validaciones --kb Generales --objeto ... --entrada @ok.json [--caso]   :: filas de validacion (campo vacio, dominio, id que no existe) con lo que devuelve hoy cada una
python gxpruebas.py objetos   --kb Generales --buscar texto
python gxpruebas.py grafo     --objeto Generales.Interfases.Registro.Get   :: quien lo usa y que usa, en todas las KBs
python gxpruebas.py generar   --kb Generales [--solo texto]   :: suites auto-* de regresion (solo lectura); --todas para todas las KBs
python gxpruebas.py revisar   --kb Generales --objeto Generales.Interfases.Registro.Set --fuente    :: fuente GX real del objeto
python gxpruebas.py revisar   --kb Generales --objeto Generales.Interfases.Registro.Set --detalle   :: buenas practicas
```

- **Para leer el código de un objeto, usá `revisar --fuente`**: es el fuente GX tal como está en el IDE (sacado de la especificación), no el Java generado. Citá los números de línea que muestra.
- **Antes de proponer código GX**, corré `revisar --objeto` sobre lo que vas a tocar y respetá las buenas prácticas que marca (están en `LEEME.md`, sección «Revisor de buenas prácticas»). No agregues excepciones a `revisor.json` sin que el usuario lo pida y dé el motivo.
- Los avisos «Buenas practicas (...)» en un paso de `ejecutar` o `correr` vienen del control del `sdtOutput` devuelto (Ok y mensajes, éxito = `Type` Debug). No hacen fallar el caso: mostráselos al usuario igual.
- **Después de un build**, `revisar --kb X --cambiados` revisa lo que el build volvió a especificar y marca **NUEVO** lo que no estaba antes. Si la vigilancia del build está activa, eso ya corrió: mirá la revisión más reciente en `resultados\revisiones\` (`"origen": "build"`). Mostrale al usuario primero los hallazgos nuevos.

- **Antes de cambiar un objeto compartido**, mirá con `grafo --objeto` quién lo usa (también desde otras KBs) para saber qué puede romperse. Las relaciones marcadas «solo en la versión publicada» existen en el `.jar` publicado del módulo pero no en la KB local.
- Las suites `suites\<KB>\auto-*.json` (etiqueta `auto`) las genera `generar`: no las edites a mano salvo para `omitir`. Si un caso `auto` falla después de un build, es que cambió la salida de un objeto de solo lectura: mostrale al usuario la diferencia, no la vuelvas a grabar. Si queda en error con «ya no es de solo lectura», el objeto empezó a escribir o hacer commit: confirmalo con el usuario y regenerá.

- `describir` da los parámetros y una **entrada de ejemplo** con la estructura exacta de los SDT. Usala como base para la `--entrada` y para los casos.
- `ejecutar` y `sql` terminan con **rollback**, salvo `--commit`. **No uses `--commit` sin que el usuario lo pida.**
- `correr` devuelve el código 0 si todo pasó y 1 si hubo fallas o errores. Por cada falla imprime la ruta, el valor esperado y el obtenido.
- La primera ejecución de cada comando tarda unos segundos, porque levanta una JVM con la KB.
- Con la interfaz abierta (o `gxpruebas.py vigilar`), las suites de las KBs de `despuesDelBuild` en `config.json` corren solas después de cada build y quedan en el Historial marcadas como `"origen": "build"`. Para saber si el último build pasó, mirá la corrida más reciente de esa suite en `resultados\` antes de volver a correrla.

## Base compartida

Si `.env` (o el entorno) define `GXP_DB_HOST`, las suites, `revisor.json` y `opcionesSuite`/`despuesDelBuild` de `config.json` se leen y graban en la base MySQL compartida del equipo, no en los archivos (ver «Base compartida» en `LEEME.md`). `python gxpruebas.py compartido estado` dice si está activa.

- Con la base activa, **no edites `suites\<KB>\*.json` ni `revisor.json` esperando que se use**: para crear o cambiar una suite, escribí el JSON y subilo con `compartido subir suites\<KB>\<tema>.json` (con `--pisar` si ya existe), o usá `compartido editar <suite>`. Los cambios al revisor (excepciones, `ignorar`) se hacen con `compartido editar revisor`, y siguen necesitando que el usuario los pida.
- Lo que grabás ahí lo ven todos los desarrolladores al instante: no subas ni pises suites sin que el usuario lo pida. `subir --pisar` reemplaza el trabajo de otro (queda en `compartido historial`).
- Si un guardado falla con «cambió desde que la abriste», otro la modificó: volvé a leerla y repetí el cambio; no fuerces.
- Nunca muestres ni copies el contenido de `.env` (tiene la contraseña).

## Cuándo usarlo

1. **Antes de proponer código GX para un bug:** reproducilo con `ejecutar`. Si te sirve, agregá un `--sql` que muestre el estado de la tabla.
2. **Después de que el usuario aplique el cambio y compile:** corré la suite que corresponda. Si no hay, creá un caso que cubra el bug en `suites\<KB>\<tema>.json`.
3. **Al diseñar una API nueva:** escribí los casos primero, con `esperado` y `verificaciones` sobre `Output.Ok` y `Output.Messages[*].Code`. Corrélos cuando el usuario compile.

## Reglas para escribir casos

- Un caso por comportamiento, con pasos encadenados. Por ejemplo: Set, después SQL para verificar la fila, después Get, después Delete y después SQL para confirmar que no quedó.
- Usá `guardar` y `${variable}` para pasar las claves entre pasos.
- Usá `datos` para el mismo caso con varias entradas, por ejemplo para validaciones de campos obligatorios.
- Escribí en `verificaciones` lo que el caso prueba (la regla de negocio, el código de error esperado) y dejá que la `lineaBase` (salida aprobada) cubra el resto. Aprobala con `correr <suite> --grabar` **solo si el usuario confirma** que la salida actual es la correcta: corre cada caso dos veces y marca en `volatiles` lo que cambia solo, así que no hace falta escribir `ignorar` para fechas o ids nuevos.
- Para listados con datos de la base que cambian, poné `"comparar": "estructura"` en el paso: controla campos, tipos, `Ok` y códigos de mensaje, sin comparar valores.
- Para no escribir valores esperados a mano, usá la entrada de un paso anterior: `"esperado": {"outGet": {"Registro": {"Fin": "${set.entrada.inSet.Fin}"}}}`. Las variables también se reemplazan en `lineaBase` y se conservan al aprobar: un campo que depende de un valor guardado (un id nuevo) puede quedar como `"${cupon}"` en la salida aprobada. Siempre entre comillas: `"ItfId": "${idItf}"`.
- Si un caso falla contra la salida aprobada, no la vuelvas a grabar para que pase: mostrale al usuario qué cambió y que decida si es correcto.
- Los `Character` de GeneXus vuelven rellenos con espacios. `recortarEspacios: true` (el valor por defecto) los ignora al comparar.
- GeneXus **omite** del JSON las colecciones y subestructuras que nunca se cargaron. Para «no trajo nada» usá `{"op": "vacio"}`: también pasa si la ruta no existe. La salida aprobada y `esperado` (con `[]`) ya tratan una colección omitida como vacía.
- Si la salida tiene `Output.Ok` y `Output.Messages`, verificá también el `Code` del mensaje, no solo `Ok`.
- No escribas ids a mano que dependan de la base: usá `${siguiente.CuponId}` (uno que no existe), `${existente.CuponId|CuponEstado=PENDIENTE}` (uno que cumple), `${con_hijos.CuponId}` / `${sin_hijos.CuponId}`, y fechas relativas (`${hoy+30}`, `${fin_mes}`, `${habil_siguiente}`). Están en `LEEME.md` («Valores calculados en la base»).
- Para las validaciones de un objeto (obligatorios, valores de dominio, id inexistente), partí de `validaciones --entrada` con una entrada que termina bien: mostrale al usuario las filas que hoy se aceptan y deberían fallar antes de armar el caso.
- Para que las salidas no dependan de los datos de la base, la suite puede tener `scriptPrevio` (`[{"ds", "sql"}]`, sentencias separadas por `;`): corre una vez, cada caso arranca de la base que deja y al final se deshace todo. Con script previo, cargá en cada caso los datos que necesita y escribí valores esperados concretos. Usá `delete from`, nunca `truncate`/`drop`/`alter` (se rechazan: confirmarían la transacción). Antes de agregar o cambiar el script de una suite existente, avisale al usuario: cambia la base sobre la que corren todos sus casos y sus salidas aprobadas.
- Por defecto cada caso arranca de la base del script, sin lo que hicieron los anteriores. Con `"opciones": {"casosEncadenados": true}` cada caso sigue de lo que dejó el anterior (el caso 1 crea un cupón, el 2 lo usa): ahí el orden de los casos importa y correr solo algunos (`--filtro`, `--etiqueta`) puede hacer fallar a los que dependen de otros. Preferí casos aislados salvo que el usuario quiera probar un flujo de varios pasos entre casos. Con casos encadenados, lo que un caso guarda con `guardar` llega como `${variable}` a los casos siguientes; con casos aislados, solo a los pasos siguientes del mismo caso.
- Con `ejecutar`, `--sql-previo "DS: delete from ...; ..."` corre esas sentencias antes del objeto, igual que el script previo.

## Limitaciones

- Trabaja contra el **Java compilado**. Si el usuario no compiló, se prueba la versión anterior. `describir` avisa si la especificación y el Java tienen distinta cantidad de parámetros.
- Los objetos con `Commit on exit = Yes` graban igual: el resultado lo avisa con «hace commit por su cuenta». Con script previo (o `--sql-previo`) no: el motor simula su commit con un savepoint y el caso lo avisa.
- No ejecuta Web Panels ni transacciones con su pantalla. Una transacción se prueba a través de un procedimiento que use su Business Component.
