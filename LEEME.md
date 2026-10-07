# GxPruebas

Pruebas genéricas sobre el Java que genera GeneXus, con interfaz gráfica y línea de comandos.

Ejecuta **cualquier procedimiento o Data Provider** de cualquier KB compilada, sin el IDE ni Tomcat. Cada caso corre en una transacción que por defecto se deshace al final: se puede dar de alta, modificar y borrar sin dejar datos en la base. Con un **script previo**, la suite arranca de una base conocida (por ejemplo, vacía) y las salidas no dependen de los datos que haya (ver «Script previo»).

## Cómo se usa

- **Interfaz gráfica:** doble clic en `GxPruebas.bat`. Abre `http://127.0.0.1:8765` en el navegador. Cerrar la ventana negra apaga todo.
- **Línea de comandos:** `python gxpruebas.py --help`.

### Requisitos

- Python 3.9 o superior.
- Java 17: `java` y `javac` en el PATH.
- La KB compilada al menos una vez: tienen que existir `JavaModel\web\build\classes` y `build\libs`.
- La base de datos de la KB levantada (MySQL local).

No hace falta instalar nada más: no usa librerías externas. La única excepción es la **base compartida** (ver más abajo), que necesita PyMySQL: `python -m pip install -r requirements.txt`.

## Flujo recomendado

1. Compilá en GeneXus (Build).
2. En **Explorar**, elegí el objeto. GxPruebas arma un formulario a partir de los SDT de entrada, con **combos** en los campos de un dominio enumerado y en los que son la clave de una tabla (ver más abajo). Ejecutalo y mirá la salida. Si querés ver qué cambió en la base, agregá **consultas SQL después**: corren en la misma transacción, así que ven los cambios antes del rollback.
3. **Guardar como caso**: queda en una suite (`suites\<KB>\<suite>.json`) y la salida que viste queda **aprobada**. Al guardar se ejecuta una vez más: lo que da distinto (fechas, ids nuevos) se marca como «cambia solo». Marcá lo que además tiene que cumplirse siempre: GxPruebas lo sugiere, con `Ok` y los códigos de mensaje ya marcados. Si la ejecución terminó en excepción, el caso queda como «tiene que terminar con este error».
4. En **Suites**, corré todo después de cada cambio, o dejá que corra solo después de cada build. Si algo cambió, ves un resumen («`Registros[*].Importe`: 100 → 110 en 12 de 40 elementos»). Si el cambio es correcto, **aceptá la salida**; si es un campo que puede cambiar, **dejá de compararlo**. Al abrir un caso, cada paso muestra **Qué controla** y se configura ahí mismo (ver «Configurar un caso» más abajo).

## Qué hay en cada pantalla

| Pantalla | Para qué |
|---|---|
| **Explorar** | Catálogo de procedimientos y Data Providers sacado de la especificación. Para cada uno: parámetros con su dirección y tipo Java, entrada como formulario (con combos) o JSON, **SQL previo** (por ejemplo, para vaciar tablas antes de ejecutar; se puede copiar el script previo de una suite), consultas SQL después, rollback o commit, salida en árbol (los espacios finales de los `Character` se ven como `·`), consola, excepción, navegación (tablas, índices, filtros) con el **plan de ejecución** y sus recomendaciones, y warnings de especificación. |
| **Suites** | Casos con sus pasos. Cada fila dice qué controla el caso y, si falló, por qué. Al abrir un caso, cada paso muestra **Qué controla** (salida aprobada, verificaciones, esperado, campos que no se comparan, valores que cambian solos, variables que guarda) con el resultado de la última corrida, y se edita ahí mismo. La salida aparece marcada con lo que se controla. Correr todo, los seleccionados o los fallidos; aprobar salidas. Script previo (arriba de los casos, con el resultado de la última corrida), opciones, variables y preparación por suite. |
| **Historial** | Todas las corridas, con su detalle y descarga en JUnit XML o JSON. |
| **Revisión** | Las buenas prácticas de cada objeto, **lo recién modificado primero** (por la fecha de su especificación), agrupado en Hoy, Ayer, Esta semana, etc. Filtros: todos, con problemas o solo **nuevos**; búsqueda; una KB o todas. Cada objeto despliega sus hallazgos (línea, sentencia, cómo arreglarlo) y **Ver fuente** muestra el código GX con las líneas marcadas. **Revisar cambios** revisa lo modificado desde la última revisión (lo mismo que hace solo el build). |
| **SQL** | Consultas contra cualquier datasource de la KB, usando la misma conexión que la aplicación. Siempre con rollback. |
| **Ayuda** | El formato de los casos, los operadores, los comodines y las variables. |

## Formato de una suite

```json
{
  "nombre": "Interfases - Registro",
  "kb": "Generales",
  "opciones": { "transaccion": "rollback", "recortarEspacios": true },
  "variables": { "itf": 1 },
  "scriptPrevio": [ { "ds": "GENERALES", "sql": "delete from gntItfRegCampo;\ndelete from gntItfRegistro;" } ],
  "preparacion": [],
  "casos": [
    {
      "nombre": "Alta y verificación en la tabla",
      "etiquetas": ["alta"],
      "datos": [ { "tipo": "AAA" }, { "tipo": "BBB" } ],
      "pasos": [
        {
          "nombre": "Alta",
          "objeto": "Generales.Interfases.Registro.Set",
          "entrada": { "inSet": { "ItfId": "${itf}", "Tipo": "${tipo}", "Nombre": "x", "Fin": "LF" } },
          "esperado": { "outSet": { "Output": { "Ok": true } } },
          "verificaciones": [
            { "ruta": "outSet.Output.Messages[*].Code", "op": "contiene", "valor": "OK" }
          ],
          "guardar": { "regTipo": "outSet.RegTipo" }
        },
        {
          "nombre": "Quedó grabado",
          "sql": "select count(*) as n from gntItfRegistro where ItfRegTipo = '${regTipo}'",
          "ds": "GENERALES",
          "verificaciones": [ { "ruta": "filas[0].n", "op": "igual", "valor": 1 } ]
        }
      ]
    }
  ]
}
```

Cada paso se puede validar de cuatro formas, y se pueden combinar:

- **`lineaBase`:** la **salida aprobada**. No hace falta escribirla: se aprueba la salida que viste («Guardar como caso», «Sí: aceptar esta salida», «Aprobar salidas actuales» o `correr --grabar`). Se compara así:
  - Por defecto, toda la salida tiene que coincidir.
  - Con `"comparar": "estructura"` solo se controlan los campos, sus tipos, `Ok` y los códigos de mensaje (como conjunto: el orden no importa). Sirve para listados con datos de la base que cambian.
  - En las rutas de `volatiles` (se detectan solas, ejecutando dos veces) solo se controla que el campo exista y tenga el mismo tipo. Las rutas de `ignorar` no se comparan.
  - Lo que **no** es una falla: un campo nuevo en la salida (queda como aviso hasta que aceptes la salida) y una colección que GeneXus omite del JSON por estar vacía (cuenta como vacía).
  - `Ok` y los códigos de mensaje nunca se marcan como volátiles ni se ofrecen para ignorar.
- **`verificaciones`:** reglas `{ruta, op, valor, cada}` con lo que el caso exige siempre (por ejemplo, «falla con el código REQUERIDO»). Siguen valiendo aunque se acepte una salida nueva: si la salida no las cumple, GxPruebas pregunta antes de aceptarla. Los operadores son `igual`, `distinto`, `contiene`, `no_contiene`, `empieza`, `termina`, `regex`, `mayor`, `mayor_igual`, `menor`, `menor_igual`, `entre`, `en`, `existe`, `no_existe`, `vacio`, `no_vacio`, `largo`, `largo_min`, `largo_max`, `tipo` y `coincide`. Con `"omitirSiVacio": true`, la verificación no se controla si su `valor` queda vacío: sirve con `datos`, cuando el valor sale de una columna que en algunas filas no aplica (`"valor": "${codigo}"` en una fila sin código).
- **`esperado`:** coincidencia parcial. Solo se controla lo que está escrito. Esperar `[]` (o `<<vacio>>`) coincide con una colección que GeneXus omitió.
- **`esperaError`:** el paso tiene que terminar con una excepción. Opcionalmente, con `errorContiene`.

**Rutas.** Se escriben como `outList.Registros[0].Tipo`. `[*]` toma todos los elementos y `[-1]` el último (también en `ignorar`: si la lista cambió de largo respecto de la línea base, cuenta desde el final de la salida). Para una consulta SQL, la salida es `{filas: [...], cantidad: n}`.

**Comodines** (en `esperado` y `lineaBase`): `<<cualquiera>>`, `<<no_vacio>>`, `<<vacio>>`, `<<numero>>`, `<<texto>>`, `<<fecha>>`, `<<fechahora>>`, `<<regex:...>>`, `<<contiene:...>>`, `<<mayor:n>>`, `<<menor:n>>`, `<<distinto:x>>`.

**Variables.** `${x}` se reemplaza por:

- las `variables` de la suite;
- la fila de `datos`;
- lo que se guardó con `guardar`;
- la salida de un paso anterior: `${alta.outSet.RegTipo}`, con el nombre del paso en minúsculas;
- lo que se le mandó a un paso anterior: `${alta.entrada.inSet.Tipo}`. Sirve para no escribir valores esperados a mano: por ejemplo, que el Get devuelva lo que recibió el Set;
- las predefinidas `${hoy}`, `${ahora}`, `${aleatorio}`, `${uuid}` y `${caso}`;
- las fechas relativas (ver abajo);
- los valores de una clave que se calculan en la base (ver abajo).

**Valores calculados en la base.** Sirven para que un caso no dependa de un id escrito a mano que mañana puede no existir (o existir). Se calculan la primera vez que se usan en el caso, dentro de su transacción (ven lo que dejaron el script previo y los pasos anteriores), y quedan fijos para el resto del caso. El atributo es el último de la clave primaria de una tabla de las transacciones de la KB, igual que en los combos.

| Variable | Qué da |
|---|---|
| `${siguiente.CuponId}` | El último + 1 (`max(CuponId) + 1` de `cbhCupon`): un id que **no existe**. Solo para claves numéricas. |
| `${existente.CuponId}` / `${ultimo.CuponId}` | El primero / el último que existe. |
| `${existente.CuponId\|CuponEstado=PENDIENTE}` | El primero que cumple las condiciones: `Atributo=valor` separadas por coma, con `=`, `!=`, `<`, `>`, `<=`, `>=`, sobre atributos de la tabla. En un atributo de un dominio enumerado se puede usar el nombre del valor (`PENDIENTE`) en lugar del guardado (`PEN`); entre comillas, el valor se toma tal cual. También con `ultimo`. |
| `${con_hijos.CuponId}` / `${sin_hijos.CuponId}` | Uno con (o sin) filas en las tablas que lo referencian: los niveles subordinados y las que tienen el atributo como clave foránea. `${con_hijos.CuponId:cbhCuponDetalle}` mira solo esa tabla. Sirve para «no se puede borrar porque tiene detalle». También llevan condiciones. |

Una variable puede ir dentro de otra: `${existente.CuponCuotaSec|CuponId=${cupon}}`. Y el valor de una columna de `datos` puede ser una de estas expresiones (`"CuponId": "${siguiente.CuponId}"`): se calcula igual. Si no hay ninguna fila que cumpla, el paso queda en error con el motivo («no hay ningún CuponId en cbhCupon que cumpla CuponEstado = EN_PROCESO»). Usan sintaxis de MySQL (`limit 1`).

**Fechas relativas.** Se calculan al ejecutar, desde la misma hora que `${ahora}`: `${hoy+30}`, `${hoy-1}`, `${hoy+2m}` (meses), `${hoy-1a}` (años), `${ahora+2h}`, `${ahora-30min}`, `${ahora+1d}`, `${inicio_mes}`, `${fin_mes}`, `${fin_mes+1}` (el del mes que viene), `${inicio_anio}`, `${fin_anio-1}`, `${habil_siguiente}` y `${habil_anterior}` (de lunes a viernes, sin feriados) y `${fecha_vacia}` (`""`, la fecha vacía de GeneXus). Van como `AAAA-MM-DD` (fecha y hora: `AAAA-MM-DDTHH:MM:SS`).

Las variables se reemplazan en `entrada`, `sql`, `esperado`, `verificaciones` y también en la salida aprobada (`lineaBase`): con `"ItfId": "${idItf}"` ahí, el campo tiene que dar el valor que tenga la variable en esa corrida. Al aprobar una salida nueva, los campos donde había una variable la conservan. En `lineaBase`, una variable que no existe se compara como texto (por si la salida real tiene un `${...}` propio).

**Al aprobar, las variables calculadas quedan como variables.** Si el paso usó una variable que se calcula al ejecutar (de la base o una fecha relativa) y la salida devuelve ese mismo valor, en la salida aprobada se guarda la variable y no el valor de ese día. Así, si el objeto devuelve el id que recibió, el caso sigue pasando cuando la base crece. Las reglas son:

- variable de la base (`${siguiente.CuponId}`): solo en un campo que se llama como el atributo (`CuponId`) y tiene ese valor (un `Importe` que justo vale 60 no se toca);
- fecha relativa (`${hoy+30}`): en cualquier campo con esa fecha;
- adentro de un texto («No existe el cupón 60»): el valor como palabra suelta (no dentro de una fecha, una hora u otro número), si tiene 2 caracteres o más y ninguna otra variable del paso dio el mismo valor.

Vale para «Guardar como caso», para «aceptar esta salida» y para «Aprobar salidas actuales» (`correr --grabar`). Los campos que quedaron con una variable se avisan al aprobar. En «Generar validaciones», lo mismo pasa con el texto del mensaje de error de cada fila.

En la pantalla Suites, el panel **Variables** muestra cada `${variable}` de la suite: de dónde sale (variables de la suite, columna de `datos`, o qué caso y paso la guarda), el último valor que tomó, qué casos la usan, y un aviso si no le va a llegar a alguno (casos aislados, un caso que corre antes del que la guarda, o una variable que nadie define).

Lo que se guarda con `guardar` llega a los pasos siguientes **del mismo caso**. Con **casos encadenados** también llega a los casos que corren después (ver «Casos aislados o encadenados»). Para guardar un valor sin escribir JSON: clic en él en la salida del caso → «Guardar como variable». La explicación completa, con ejemplos, está en Opciones de la suite → Variables → «¿Cómo funcionan las variables?».

- **`scriptPrevio`** (opcional): corre una vez antes de todos los casos y cada caso arranca de la base que deja (ver «Script previo»).
- **`opciones.casosEncadenados`** (opcional): `true` para que cada caso siga de lo que dejó el anterior, en lugar de arrancar de cero (ver «Casos aislados o encadenados»).
- **`preparacion`** (opcional): pasos que corren al principio de **cada** caso, dentro de su transacción.
- Un paso `sql` puede tener varias sentencias separadas por `;`: corren en orden y la salida es la de la última.

### Script previo

Sirve para que las salidas no varíen según los datos que haya en la base: el script deja la base en un estado conocido (por ejemplo, vacía) y los casos cargan solo los datos que necesitan, con resultados que se saben de antemano. Se escribe en **Suites → Más → Opciones** (uno o varios bloques, cada uno en un datasource) y se ve arriba de los casos.

Con script previo, **toda la corrida es una sola transacción**:

1. Rollback, el script (una sola vez) y un savepoint en cada datasource MySQL de la KB.
2. Cada caso, y cada fila de `datos`, corre y al terminar vuelve al savepoint (o, con casos encadenados, sigue: ver abajo).
3. Al final, rollback de todo, el script incluido: la base queda como estaba.

#### Casos aislados o encadenados

En **Opciones → Entre un caso y otro** se elige qué ve cada caso:

- **Cada caso arranca de cero** (por defecto): al terminar, la base vuelve a como la dejó el script. Ningún caso ve lo que hicieron los anteriores, así que se puede correr uno solo, los fallidos o en cualquier orden, y da lo mismo. Sin script previo, cada caso corre en su propia transacción, como siempre.
- **Cada caso sigue de lo que dejó el anterior** (`"opciones": {"casosEncadenados": true}`): lo que hace un caso queda para el siguiente. Por ejemplo, el caso 1 crea un cupón y el 2 lo usa. Lo que un caso guarda con `guardar` llega como `${variable}` a los casos que corren después: el caso 1 hace `"guardar": {"cupon": "outSet.CuponId"}` y el caso 2 usa `"${cupon}"`. Solo pasa lo de `guardar` (no `${paso.salida...}`), y si una fila de `datos` tiene una columna con el mismo nombre, gana la columna. El resultado de cada caso muestra qué variables recibió. Si un caso usa una variable que guarda otro y no le llega, el error dice qué caso la guarda y por qué no llegó. Igual toda la corrida es una transacción y al final se deshace, con o sin script previo. El orden de los casos importa: si corrés solo algunos (seleccionados, fallidos, `--filtro`, `--etiqueta`), los que dependen de otros pueden fallar, y GxPruebas lo advierte. Al aprobar salidas, la cadena se corre dos veces completa (desde el script) para detectar lo que cambia solo. Un caso guardado desde Explorar en una suite encadenada no se vuelve a ejecutar solo: aprobá su salida corriendo la suite con «Aprobar salidas actuales».

Mientras dura la corrida, el **commit y el rollback de los objetos se simulan**: el motor envuelve la conexión de GeneXus y un commit pone otro savepoint en lugar de confirmar, y un rollback vuelve al último commit o, si no hubo, al inicio del caso (encadenados) o a la base del script. Así nada confirma el script (la base quedaría vacía de verdad) y los objetos que hacen commit en la misma unidad de trabajo, como una llamada a `prcCommit`, se prueban igual. El caso lo avisa («se simularon con savepoints»). Lo que corre en **otra unidad de trabajo** (procedimientos con *Execute in new LUW*, como `Sistema.Global.PrcLog`) usa otra conexión: su commit confirma solo lo suyo (el log) y no toca esta transacción.

Para que el script no se pueda confirmar:

- No se aceptan sentencias que en MySQL confirman la transacción solas (`truncate`, `drop`, `alter`, `create`, `rename`, `lock`…) ni las que la manejan (`commit`, `rollback`, `savepoint`, `set autocommit`). Para vaciar una tabla, `delete from` (las hijas primero, o `set foreign_key_checks = 0` al principio y `= 1` al final). Esto vale para cualquier paso SQL, con o sin script.
- Un caso con `"transaccion": "commit"` no se ejecuta (tampoco con casos encadenados).
- Si igual se pierde el savepoint (se reinició el motor por un tiempo agotado o un build), el caso lo avisa y el script se vuelve a correr para los siguientes.

Si el script termina con error, no se corre ningún caso: cada uno queda en error con el motivo, y el detalle por sentencia (filas cambiadas, error) está en la corrida. Mientras corre una suite con script, el motor de la KB queda tomado: Explorar espera a que termine.

En **Explorar**, el **SQL previo** hace lo mismo antes de cada ejecución (es por KB, no por objeto). Al guardar como caso, se ofrece usarlo como script previo de la suite o como primeros pasos del caso.

### Configurar un caso (pantalla Suites)

Al abrir un caso, cada paso tiene dos partes:

- **Qué controla**: sale de la definición del caso, así que se ve aunque nunca se haya corrido. Cada control lleva ✔ o ✖ según la última corrida (con lo obtenido cuando falla), o ○ si todavía no se corrió con él.
  - **Salida aprobada**: «Toda la salida» o «Solo estructura», o «Aprobar la salida de esta corrida» si no tiene.
  - **Verificaciones**: se agregan con **+ Agregar verificación** o haciendo clic en un valor de la salida. El editor autocompleta el campo con las rutas de la última salida, muestra su valor y dice si la verificación se cumple con esa salida antes de guardarla.
  - **Esperado**, **Tiene que terminar con error**, **No se comparan**, **Cambian solos** y **Guarda**: se ven y se quitan desde ahí.
  - Si el paso no controla nada, lo avisa: da OK siempre que no termine con error.
- **Salida de la corrida**: el árbol marca lo que ya se controla («✔ verificado», «no se compara», «cambia solo», «→ ${variable}») y abre solo las ramas con marcas o diferencias. Si hubo cambios contra la salida aprobada, arriba aparece **Qué cambió**, con «Sí: aceptar esta salida» y «No comparar» por campo.

Cada cambio se guarda en la suite al momento. Hasta que vuelvas a correr el caso, la fila dice «cambiado, sin correr» y la ficha avisa que el resultado es de antes. En la lista, cada caso resume qué controla («Controla: salida aprobada · 3 verificaciones») y, si falló, por qué («1 verificación no se cumple · 2 cambios en la salida»). Lo demás (nombre, etiquetas, entrada, datos) se edita con **Editar JSON**.

## Pruebas automáticas después de cada build

GxPruebas puede correr las suites solo, cada vez que GeneXus compila la KB. Se configura en `config.json`:

```json
"despuesDelBuild": {
  "activo": true,
  "kbs": ["Generales"],
  "etiqueta": "",
  "esperaSeg": 15,
  "notificar": true,
  "revisar": true
}
```

- **`kbs`:** las KBs a vigilar. `["*"]` vigila todas: corre las suites de las que tienen y revisa las buenas prácticas de todas.
- **`etiqueta`:** si tiene un valor (por ejemplo `"auto"`), corre solo los casos con esa etiqueta. Vacía, corre todas las suites de la KB.
- **`esperaSeg`:** cuántos segundos sin cambios en el build hay que esperar antes de correr, para no arrancar mientras GeneXus todavía está compilando.
- **`notificar`:** muestra una notificación de Windows con el resultado. Al hacerle clic, se abre la corrida en la interfaz.
- **`revisar`:** antes de las suites, revisa las **buenas prácticas** de los objetos que el build volvió a especificar (ver «Revisor de buenas prácticas») y avisa los problemas **nuevos**. Un error nuevo cuenta como falla del build aunque las suites pasen. Por defecto está activo.

Funciona mientras la interfaz está abierta (`GxPruebas.bat`). Para vigilar sin la interfaz: `python gxpruebas.py vigilar` (toma la misma configuración; `--kb`, `--etiqueta` y `--espera` la pisan). Vigila una sola ventana a la vez: si ya hay una, la otra lo avisa y no corre nada.

El build se detecta igual que el reinicio del motor: cambia el marcador de compilación de Gradle (`build\tmp\compileJava`) o algún `.jar` de `build\libs`. Si el build no compiló nada nuevo, no se corre nada. Al abrir GxPruebas no se corre nada: solo se prueban los builds que terminan con la vigilancia ya activa.

Los resultados quedan en el **Historial** con la marca «después del build», en la consola y, si la interfaz está abierta, en un aviso.

> Las suites corren con su transacción (rollback por defecto), pero un objeto con **Commit on exit = Yes** graba igual, **en cada build**. Si tenés suites así, dejalas fuera con una `etiqueta`.

## Grafo de objetos y módulos

La pestaña **Grafo** muestra los objetos de **todas las KBs** y cómo se relacionan, dentro de cada KB y entre KBs. También se puede consultar desde la consola: `python gxpruebas.py grafo --objeto Generales.Interfases.Registro.Get`.

- **Objetos:** buscá cualquier procedimiento, Data Provider, transacción, Web Panel, API, SDT, dominio o tabla. Se ve quién lo usa (a la izquierda), qué usa (a la derecha) y las tablas que lee o escribe. Los vecinos de otra KB tienen la línea más gruesa. Si son muchos, se agrupan por módulo: clic en el grupo para ver sus objetos.
- **Módulos:** para cada módulo, qué módulos lo usan y cuáles usa (con la cantidad de relaciones), desde cuántas KBs, **qué objetos suyos se usan desde afuera** (su superficie pública) y las **dependencias circulares**.
- **De dónde sale:** las llamadas, los Business Components y los SDT, de las referencias del Java generado (entre KBs, por el paquete: `com.terceros.*` es de Terceros). Las tablas, de la navegación de la especificación.
- **Versión publicada de los módulos:** cada KB tiene en `build\libs` los `.jar` de los módulos que usa (por ejemplo `Terceros.jar` 23.15.4). GxPruebas los lee y marca en naranja las relaciones y objetos que están **solo en la versión publicada** y no en tu KB local: así se ve lo que tiene la versión publicada aunque tu KB esté atrasada, sin leer CI. Lo que otros agregaron en CI y todavía no se publicó en un módulo no se puede ver.
- **Se actualiza solo:** con la interfaz abierta, después de cada build se rearma el grafo de esa KB (unos segundos) y la pantalla se refresca sola. Los datos quedan en `.cache\grafo`.
- La pantalla usa cytoscape.js desde `cdn.jsdelivr.net`: necesita conexión a internet.

## Suites generadas (regresión de toda la KB)

`python gxpruebas.py generar --kb Generales` (o `--todas`) arma suites `suites\<KB>\auto-<módulo>.json` con un caso por cada procedimiento o Data Provider **de solo lectura**, para detectar si un cambio rompió otra cosa:

- **Qué objetos entran:** los que, contando todo lo que llaman (también en otras KBs), no escriben en la base, no hacen commit ni rollback y no usan HTTP, mail, archivos, shell ni submit. Se deja afuera lo generado por WorkWithPlus y GAM, los `*UltSec` y los que no tienen parámetros de salida. Tienen que terminar sin excepción en menos de 10 s.
- **Con qué entrada:** los campos de la entrada se buscan por nombre entre las columnas de las bases de la KB y se completan con una fila real (la tabla que más campos cubre). Además hay un caso con la entrada vacía, si da otra salida.
- **Qué controlan:** que la salida no cambie respecto de la aprobada. Si alguna lista tiene más de 50 elementos, se compara solo la estructura (son datos que cambian).
- **Etiqueta `auto`.** Al correr, si el objeto (o algo que llama) dejó de ser de solo lectura, el caso **no se ejecuta** y queda en error con el motivo, para no grabar en cada build.
- Se generan **sin salida aprobada**: aprobalas con `correr --kb <KB> --etiqueta auto --grabar` cuando la KB compilada esté en un estado bueno.
- **Regenerar** agrega los objetos nuevos y saca los que ya no son de solo lectura; los casos existentes quedan como están. Para dejar un caso afuera, marcalo con `"omitir": true` (si lo borrás, vuelve). `--solo texto` regenera solo esos objetos.
- El informe de la generación (qué se descartó y por qué) queda en `.cache\generar-<kb>.json`.

## Base compartida (equipo)

Las suites y la configuración del equipo pueden vivir en una base **MySQL compartida** en lugar de en archivos, para que todos los desarrolladores lean y graben las mismas. Se activa con variables de entorno; sin ellas, GxPruebas sigue usando los archivos locales.

**Qué se comparte:**

| En la base | Antes estaba en |
| --- | --- |
| Las suites (con sus salidas aprobadas) | `suites\<KB>\<suite>.json` |
| Configuración del revisor: reglas, **objetos ignorados** y excepciones | `revisor.json` |
| `opcionesSuite` y `despuesDelBuild` | `config.json` |

Queda **local** lo propio de cada máquina: el resto de `config.json` (carpetas de las KBs, Java, puerto), el historial de corridas (`resultados\`) y la línea base del revisor (`.cache\`). Si `config.json` local tiene `opcionesSuite` o `despuesDelBuild`, pisa a lo de la base solo en esa máquina.

**Configuración.** Copiá `.env.ejemplo` como `.env` (no va al repositorio) y completá los datos. Las variables de entorno de Windows con el mismo nombre tienen prioridad.

```ini
GXP_DB_HOST=gascode.com.ar
GXP_DB_PORT=3306
GXP_DB_USER=...
GXP_DB_PASSWORD=...
GXP_DB_NAME=gxpruebas
```

Opcionales: `GXP_USUARIO` (el nombre que queda en cada cambio; por defecto, el usuario de Windows), `GXP_DB_SSL=no` (no cifrar; por defecto cifra si el servidor lo permite), `GXP_DB_SSL_CA` (verifica el certificado del servidor) y `GXP_EDITOR` (editor de `compartido editar`; por defecto, Notepad).

**Comandos:**

```bat
python gxpruebas.py compartido estado                 :: si está configurada, si responde y qué tiene
python gxpruebas.py compartido inicializar            :: crea la base y las tablas (lo hace solo 'subir')
python gxpruebas.py compartido subir [archivos] [--pisar]   :: sube las suites locales, revisor.json y lo compartido de config.json
python gxpruebas.py compartido editar revisor         :: abre la configuración del revisor en el editor y la sube al cerrarlo
python gxpruebas.py compartido editar config          :: opcionesSuite y despuesDelBuild
python gxpruebas.py compartido editar interfases-registro   :: el JSON de una suite
python gxpruebas.py compartido historial <revisor|config|suite>
python gxpruebas.py compartido restaurar <suite> [--version N]   :: recupera una suite borrada o vuelve a una versión
python gxpruebas.py compartido papelera               :: suites borradas
python gxpruebas.py compartido bajar [--carpeta X]    :: copia todo a archivos (respaldo)
```

**La primera vez** (una sola persona): `compartido subir` sube todo lo local. Lo que ya está en la base con otro contenido no se toca y se lista como `distinta`: `--pisar` lo reemplaza (la versión de la base queda en el historial). Al subir `config.json` se sacan de ese archivo `opcionesSuite` y `despuesDelBuild`, porque si no pisarían siempre a los de la base.

**Cómo funciona:**

- Dos tablas: `gxp_documentos` (un documento por suite y por configuración, con su versión, quién y cuándo lo cambió) y `gxp_historial` (las 20 versiones anteriores de cada uno). El JSON va comprimido en el formato de `COMPRESS()` de MySQL: `SELECT UNCOMPRESS(contenido) FROM gxp_documentos WHERE clave = 'revisor'` lo muestra.
- **Cambios simultáneos:** al guardar una suite se controla que nadie la haya cambiado desde que se abrió. Si alguien lo hizo, no se pisa: la interfaz muestra «cambió desde que la abriste» y hay que volver a abrirla.
- **Borrar** una suite solo la marca: `compartido papelera` y `compartido restaurar` la recuperan.
- **Sin conexión:** lo que se leyó queda copiado en `.cache\compartido\`. Si la base no responde, se usa esa copia con un aviso (en la interfaz, el indicador «base compartida» se pone en rojo) y no se puede grabar hasta que vuelva.
- `opcionesSuite` y `despuesDelBuild` se leen al arrancar: después de cambiarlos, reiniciá la interfaz.
- Con la base activa, la carpeta `suites\` y `revisor.json` locales **no se usan**. Para cambiar una suite a mano: `compartido editar <suite>`, o editá el archivo y subilo con `compartido subir suites\<KB>\<suite>.json --pisar`.
- Las pruebas unitarias (`python -m unittest`) usan siempre los archivos locales.

## Revisor de buenas prácticas

`python gxpruebas.py revisar --kb Generales` revisa el **fuente GX** de los objetos (no el Java) contra las buenas prácticas del equipo. Devuelve el código 1 si encuentra algún error.

```bat
python gxpruebas.py revisar --kb Generales                                  :: toda la KB (resumen por regla y módulo)
python gxpruebas.py revisar --kb Generales --objeto Generales.Interfases.Registro.Set --detalle
python gxpruebas.py revisar --todas                                          :: todas las KBs
python gxpruebas.py revisar --kb Generales --objeto ... --fuente             :: muestra el fuente GX reconstruido
python gxpruebas.py revisar --kb Generales --cambiados                       :: solo lo que cambió desde la última revisión
python gxpruebas.py revisar --reglas                                         :: reglas y su configuración
```

**De dónde sale el fuente.** La especificación deja en `GXSPC*\GEN*\<Módulo>\...\<Objeto>.sp0` (o `.sp1`, según la KB) el código de cada objeto, ya tokenizado línea por línea, además de los parámetros, las variables con su tipo y las propiedades. El revisor lo lee y reconstruye el código como se ve en el IDE (`--fuente`). Si el objeto no se especificó después del último cambio, se revisa la versión anterior. Las condiciones `Where` de los `For Each` no vienen en el fuente.

**Reglas** (una por archivo en `gxp\revisor\reglas\`):

| Regla | Qué controla |
|---|---|
| `sin-commit-rollback` | Solo los Web Panels y Web Components confirman. En cualquier otro objeto marca `Commit`, `Rollback`, las llamadas a `prcCommit` / `prcRollback` (de cualquier módulo) y el código Java nativo con commit (advertencia). En los procedimientos marca además **Commit on exit = Yes**: es error si el Java confirma y advertencia si hoy no confirma porque el objeto no graba. Las transacciones confirman por diseño: solo se les marca un commit explícito. |
| `salida-ok-mensajes` | Los procedimientos con un parámetro de salida que es un `sdtOutput` o lo tiene adentro (`&outSet.Output`) devuelven `Ok` y mensajes coherentes. Recorre los caminos del fuente y, en cada salida (`Return` o fin), marca: un mensaje de tipo **Error con `Ok = True`**; un **`Ok = False` sin mensaje de Error**; **`Ok` sin asignar** (un Boolean arranca en False: devuelve False aunque salga bien); **`Ok = True` sin mensaje de éxito**, que es `Type = MessageTypes.Debug` (un `Info` como éxito es advertencia: hay que pasarlo a Debug); y mensajes agregados a un **`sdtOutput` propio que nunca se copia a la salida** (se pierden). Sigue las subs (`Do 'AGREGARMENSAJE'`) con los valores del momento, banderas como `&HayError` y `Errores.Count`. `Sistema.Output.AddMessage` y `AddMessages` solo agregan el mensaje, no tocan el `Ok`: otros ayudantes así se configuran en `ayudantes`. Los caminos que no puede seguir (la salida pasada a otro objeto, lo que depende de las vueltas de un bucle) no los juzga. |
| `alta-devuelve-id` | Un procedimiento que **crea una entidad con un Business Component** devuelve su clave (advertencia: es heurística, y cada hallazgo dice por qué lo tomó como alta). Es alta un `.Insert()`, un `.InsertOrUpdate()` o un `.Save()` sobre un `new()` o sobre un BC que no se cargó (`Load` / `If Fail()` / `new()` también cuenta; un `new()` seguido del `Load` solo limpia la variable). La clave y los autonumerados salen de la especificación de la transacción. Solo exige lo que **el que llama no conoce**: lo autonumerado, lo que sale de un numerador o de la base; lo que viene de los parámetros de entrada, no. La puede devolver directo (`&out.Id = &bc.Id`), a través de una variable, en un ítem que va a una colección de la salida o con el BC entero. No exige la clave de las entidades hijas que crea el mismo objeto. Si el nombre es de alta (`nombresAlta`: Crear, Set, Registrar…) se revisa siempre; si es de otra operación (`nombresOtraOperacion`: Actualizar, Obtener, Importar…), o el objeto además modifica otra entidad, el alta se toma como secundaria y no se exige. Tampoco se exige en los **historiales y logs** (`entidadesExcluidas`, sobre el nombre de la transacción: `…Historial`, `…Hist`, `…Log`). Todavía no cubre el comando `New`. |

**Capa dinámica de `salida-ok-mensajes`.** Cada vez que un paso de una suite (o Explorar, o `ejecutar`) corre un objeto, se controla el `sdtOutput` que devolvió de verdad: `Ok = false` con algún mensaje `Type` 1 (Error) o algo en `Errores`; `Ok = true` sin Errores y con un mensaje `Type` 3 (Debug). Lo que no cumple queda como **aviso del paso** («Buenas practicas (error): outSet.Output: ...»), sin hacer fallar el caso. Respeta `activa` y las excepciones de `revisor.json`. Cubre lo que el análisis del fuente no puede seguir.

**`revisor.json`** (en la carpeta de GxPruebas):

- `reglas`: por regla, `activa`, `severidad` (`error` o `advertencia`) y sus parámetros (`revisar --reglas` los lista con sus valores).
- `ignorar`: objetos que no se revisan, por nombre completo con comodines (`WWPBaseObjects.*`, `GAM*`).
- `ignorarGeneradosPorPattern`: deja afuera lo que genera WorkWithPlus. Se reconoce por la propiedad que esos objetos traen para que GXtest no los cuente en la cobertura. Las especificaciones `_BC` de las transacciones no se revisan nunca: repiten el código de la transacción.
- `excepciones`: `{"regla", "objeto", "motivo"}`, con `kb` y `linea` opcionales. **El motivo es obligatorio**: una excepción sin motivo no se aplica y se avisa. Los hallazgos cubiertos quedan en el resultado como `excepcionados`, con su motivo.

Cada hallazgo trae la línea, la sentencia GX, por qué se marcó, cómo se arregla (`--detalle`) y una **huella** que no cambia si la línea se mueve. Los resultados quedan en `resultados\revisiones\` (los últimos 100).

**Nuevos y preexistentes.** Cada KB tiene una **línea base** (`.cache\revisor\<kb>.json`) con la fecha de la especificación de cada objeto y las huellas de sus hallazgos en la última revisión. Con eso:

- `--cambiados` revisa solo los objetos cuya especificación cambió desde entonces (los que volvió a especificar un build). Si la KB no tiene línea base, revisa todo y la arma.
- **NUEVO** es lo que introdujo la **última modificación** del objeto: lo que no estaba antes de ese cambio (o todo, si el objeto se creó después de la línea base). La marca se conserva al volver a revisar, desde la consola o la interfaz, hasta que el objeto se modifica otra vez. Lo que ya estaba se muestra igual, sin la marca: al tocar un objeto viejo se ven todos sus problemas, pero solo los nuevos hacen fallar el build.
- La línea base la actualizan solo las revisiones completas: toda la KB o `--cambiados`, con todas las reglas activas. Revisar un objeto con `--objeto` (por ejemplo, mientras lo editás) no la toca, así que lo que introdujiste sigue contando como nuevo en el build.
- Al empezar a vigilar builds, GxPruebas arma en segundo plano la línea base de las KBs que no la tienen.

**Agregar una regla:** un archivo nuevo en `gxp\revisor\reglas\` con una clase `@registrar` (el formato está en `gxp\revisor\reglas\__init__.py`) y sus pruebas en `gxp\revisor\pruebas\`. Toda la interpretación de los códigos de GeneXus está en `gxp\revisor\fuente.py`: las reglas trabajan con sentencias (`s.clave == "commit"`, `s.objetos()`, `s.texto`), no con números. Las pruebas corren sin las KBs:

```bat
python -m unittest discover -s gxp/revisor/pruebas -t .
```

## Línea de comandos

```bat
python gxpruebas.py correr                                   :: todas las suites; código 1 si algo falla
python gxpruebas.py correr interfases-registro --detalle
python gxpruebas.py correr --kb Generales --etiqueta alta --junit resultados.xml
python gxpruebas.py correr interfases-registro --grabar      :: aprueba las salidas actuales (corre dos veces cada caso)
python gxpruebas.py ejecutar --kb Generales --objeto Generales.Interfases.Registro.List --entrada "{\"inList\":{\"ItfId\":1}}"
python gxpruebas.py ejecutar --kb Generales --objeto ... --entrada @entrada.json --sql "GENERALES: select ..."
python gxpruebas.py ejecutar --kb Generales --objeto ... --sql-previo "GENERALES: delete from a; delete from b"   :: como el script previo
python gxpruebas.py describir --kb Generales --objeto Generales.Interfases.Registro.Set
python gxpruebas.py validaciones --kb Generales --objeto ... --entrada @entrada.json [--caso]   :: casos de validación a partir de una entrada que termina bien
python gxpruebas.py objetos --kb Generales --buscar interfases
python gxpruebas.py sql --kb Generales --ds GENERALES "select * from gntInterfase"
python gxpruebas.py plan --kb Generales --objeto Generales.Empresas.Get [--detalle]   :: plan de ejecución y recomendaciones
python gxpruebas.py suites
python gxpruebas.py vigilar --kb Generales --etiqueta auto   :: corre las suites después de cada build
python gxpruebas.py revisar --kb Generales --objeto ...      :: buenas prácticas en el fuente GX
```

## Plan de ejecución

En **Explorar**, pestaña **Navegación**, **Calcular plan de ejecución** (o `gxpruebas.py plan`) toma las sentencias SQL que GeneXus generó para el objeto (los cursores del `.java`, también los dinámicos de los filtros opcionales), le pide a MySQL el `EXPLAIN` de cada una y las revisa contra los índices de la base. No ejecuta las sentencias: termina con rollback.

Para el `EXPLAIN`, cada `?` se reemplaza por el valor de una fila real de la tabla: con un valor que no existe, MySQL resuelve la búsqueda por clave antes de ejecutar y no muestra el plan. Las consultas dinámicas se analizan con todos sus filtros opcionales puestos.

Recomendaciones (de mayor a menor nivel: alto, medio, bajo):

| Regla | Qué detecta |
|---|---|
| `sin-indice` | Ningún índice empieza por las columnas filtradas: recorre toda la tabla. Alto si es un `UPDATE` o `DELETE`. |
| `join-sin-indice` | La tabla del join no tiene índice por las columnas de la relación: la recorre por cada fila de la otra. |
| `tabla-completa` | `SELECT` sin filtros sobre una tabla de 1000 filas o más. |
| `orden-sin-indice` | El `ORDER BY` no sale de un índice: MySQL ordena aparte (filesort). Bajo si el filtro ya usa un índice. |
| `like-comodin` | `LIKE '%...'` (buscar «contiene»): no puede usar índice. |
| `funcion-columna` | `UPPER(col) = ...`: la función sobre la columna impide usar el índice. |
| `recorrido-completo`, `recorre-indice` | MySQL recorre toda la tabla o un índice entero (solo si lee 100 filas o más). |
| `poco-selectivo` | Lee muchas filas por un índice y descarta casi todas con filtros que no están en el índice. |
| `tabla-temporal` | MySQL arma una tabla temporal (GROUP BY, fórmulas de agregación, orden por otra tabla). |
| `consulta-anidada` | Un For Each adentro de otro, sobre otra tabla: una consulta por cada registro de afuera (N+1). |

Lo que sale de los índices no depende de los datos: mantiene su nivel aunque la base local tenga pocas filas, y sube uno si la tabla ya tiene 10.000 o más. Lo que solo dice el `EXPLAIN` depende de los datos locales, que pueden ser muy distintos de los de producción: la pantalla avisa qué tablas tienen menos de 100 filas. Si el `EXPLAIN` muestra que MySQL sí usa un índice, se descarta lo que dijo el análisis de índices para esa tabla.

## Combos en el formulario de entrada

Al lado de algunos campos del formulario aparece **▾** (o `Alt+↓` / `F4` en el campo). El campo se sigue pudiendo escribir a mano: `${variable}`, valores inválidos para probar validaciones, etc.

- **Dominio enumerado** (`Fin` de tipo `Generales\RegistroFin`): los valores del dominio con su descripción. Salen de la especificación del objeto o, si no los trae, de la de las transacciones.
- **Clave de una tabla** (`ItfId`): los valores que hay en la base, con el atributo descriptor de la transacción (`select ItfId, ItfNombre from gntInterfase`). Un campo es clave de una tabla si se llama igual que el último atributo de su clave primaria: `ItfId` es la de `gntInterfase`, no la de `gntItfRegistro`. Si la clave es compuesta, se filtra por los otros campos de la clave que estén en el mismo nivel de la entrada (`CargoPlanSec` por el `CargoId` de la misma cuota). Se traen las primeras 300 filas; si hay más, lo que se escribe en el filtro se busca en la base (por el valor o la descripción). La consulta corre en el motor y termina con rollback.

  Arriba de los valores, en cursiva, aparecen las **variables que se calculan al ejecutar** (ver «Valores calculados en la base»), con el valor que darían hoy: `${siguiente.X}` (no existe), `${existente.X}`, `${ultimo.X}`, `${con_hijos.X}` y `${sin_hijos.X}` si alguna tabla la referencia, y `${existente.X|Atributo=VALOR}` por cada valor de los atributos de dominio enumerado de la tabla. Las que hoy no encuentran ninguna fila quedan apagadas, al final. Si la clave es compuesta, las condiciones incluyen los otros campos de la clave del mismo nivel (también si son una `${variable}`). Elegir una de estas, y no el número, hace que el caso siga sirviendo aunque cambie la base.
- **Fecha** (`date` o `datetime` en la especificación): las fechas relativas (`${hoy}`, `${hoy+30}`, `${fin_mes}`, `${habil_siguiente}`, `${fecha_vacia}`…) con el valor que darían hoy.

Los campos numéricos aceptan una `${variable}` además de un número.

Limitaciones: solo se reconocen las tablas de las transacciones de la misma KB, y un campo con otro nombre que el atributo (`Id`, `Tipo`) no tiene combo de claves. Las consultas usan la sintaxis de MySQL (`CAST(... AS CHAR)`).

## Generar validaciones

En Explorar, con una entrada que **termina bien**, **Generar validaciones…** propone un caso con una fila de `datos` por cada cosa que conviene probar:

- **obligatorio**: cada campo vacío (`""` en un texto o una fecha, `0` en un número; `"0"` en una clave numérica que viene como texto). Los booleanos no.
- **lista**: cada colección sin elementos (adentro de las listas no se generan filas por campo).
- **dominio**: cada valor del dominio enumerado del campo, salvo el que ya tiene.
- **no existe**: `${siguiente.X}` en un campo que es la clave numérica de una tabla.
- y la entrada tal cual («entrada valida»).

Las ejecuta todas (cada una con rollback; si el objeto hace commit por su cuenta, el commit se simula) y muestra qué devuelve hoy cada una. Vienen marcadas las que fallan y las de dominio; un campo vacío que **se acepta** queda sin marcar con el aviso «lo acepta: no es obligatorio, o falta validarlo», para que decidas si es un bug. En «Se espera» corregís lo que el caso va a exigir (por ejemplo, que falle donde hoy lo acepta: el caso va a fallar hasta que se arregle el objeto).

El caso guardado usa `${columna}` en cada campo que cambia y cada fila trae su resultado esperado en las columnas `ok`, `codigo` y `mensaje`. Las verificaciones controlan `Ok` y el código del mensaje o, en las filas que fallan sin código, el texto del mensaje de error (`omitirSiVacio`). Si la salida no tiene un sdtOutput (Ok y mensajes), el caso queda sin verificaciones: aprobá su salida desde Suites.

Desde la consola: `python gxpruebas.py validaciones --kb Cobranzas --objeto Cobranzas.Cupones.CambiarEstado --entrada @entrada.json` muestra las filas con lo que devuelve cada una, y con `--caso` imprime el caso (JSON) con las filas marcadas.

## Cómo funciona por dentro

- **Catálogo:** lee los XML de navegación (`GXSPC*\GEN*\NVG\**.xml`) que deja la especificación. De ahí salen los objetos, los parámetros con `in`/`out`/`inout`, la navegación y los warnings.
- **Motor:** `motor\GxMotor.java` corre en una JVM por KB, con el classpath de la KB. Inicializa GeneXus con el `client.cfg` de la KB, ejecuta `execute(...)` por reflexión y convierte los JSON a SDT y al revés con la serialización de GeneXus. Las consultas SQL usan la misma conexión: por eso ven los cambios sin confirmar.
- **Sin bloquear tus builds:** los `.jar` de `build\libs` se copian a `.cache\jars`, compartida entre KBs: un mismo `.jar` se guarda una sola vez aunque lo usen varias KBs (se identifica por un hash de su contenido, que se calcula la primera vez y queda en `indice.json`). Cada vez que arranca un motor se borran las copias que ya no usa ninguna KB (las que están abiertas por un motor en marcha quedan para la próxima). Si GeneXus recompila, el motor se reinicia solo en el siguiente pedido. Si pasan 15 minutos sin uso, se apaga y libera las conexiones.
- **Resultados:** se guardan en `resultados\` como JSON (las últimas 300 corridas). Las suites borradas van a `.papelera\` (con la base compartida, quedan marcadas en la base).

### Dónde está cada cosa

`gxpruebas.py` solo arranca la línea de comandos. La lógica está en paquetes de `gxp\`, cada uno con su API en el `__init__.py` y la lista de sus módulos en el docstring:

| Paquete | Qué hace |
| --- | --- |
| `kbs.py`, `catalogo.py`, `config.py`, `util.py` | KBs encontradas, objetos y parámetros, `config.json`, lectura y escritura de JSON |
| `campos\` | combos del formulario: dominio de cada campo de la entrada, tablas con su clave y valores de la base; `${existente.X}` y demás valores calculados en la base |
| `plan\` | plan de ejecución: sentencias SQL del `.java`, `EXPLAIN`, índices de la base y recomendaciones |
| `motor\` | el proceso Java de cada KB: describir, ejecutar, SQL, fin de transacción, savepoint del script previo |
| `suites\` | formato y almacén de las suites, script previo, ejecución de pasos y casos, variables y fechas relativas, salidas aprobadas, corridas, reportes, generador de validaciones |
| `comparacion\` | comparación con `esperado` y la salida aprobada, operadores de `verificaciones`, volátiles |
| `generacion\`, `efectos.py` | suites `auto-*` y la detección de objetos de solo lectura |
| `revisor\` | fuente GX desde la especificación, reglas de buenas prácticas, línea base, pantalla Revisión |
| `compartido\` | base compartida (MySQL): conexión y `.env`, documentos con versión, historial y copia local |
| `grafo\` | quién usa a quién, en todas las KBs y en los `.jar` publicados |
| `vigilancia.py`, `automatico\`, `notificaciones.py` | detección de builds y lo que corre después de cada uno |
| `cli\` | comandos de consola: cada módulo registra los suyos con `registrar(sub)` |
| `web\` | servidor de la interfaz; las rutas están en `web\api\`, un módulo por pantalla, con `@ruta("GET", "/api/...")` |

Las dependencias van en un solo sentido: `cli` y `web` usan los paquetes de dominio, y nunca al revés.

Las pruebas unitarias corren sin las KBs:

```bat
python -m unittest discover -s . -p "test_*.py" -t .
```

## Cuidados

- Un objeto con **Commit on exit = Yes**, o que hace `Commit` explícito, graba aunque el caso haga rollback. La interfaz lo marca con «⚠ hace commit», y la corrida lo avisa. Con script previo no: ese commit se simula.
- La **base local** es la que dice el `client.cfg` de la KB. Si la volvés a descargar con tus scripts, las líneas base que dependen de los datos pueden cambiar.
- Los procedimientos que dependen de la **sesión web** (GAM, WebSession, HttpRequest) pueden comportarse distinto fuera de Tomcat.
- La interfaz escucha solo en `127.0.0.1`.
