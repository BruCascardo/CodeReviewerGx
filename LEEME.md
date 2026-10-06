# GxPruebas

Pruebas genéricas sobre el Java que genera GeneXus, con interfaz gráfica y línea de comandos.

Ejecuta **cualquier procedimiento o Data Provider** de cualquier KB compilada, sin el IDE ni Tomcat. Cada caso corre en una transacción que por defecto se deshace al final: se puede dar de alta, modificar y borrar sin dejar datos en la base.

## Cómo se usa

- **Interfaz gráfica:** doble clic en `GxPruebas.bat`. Abre `http://127.0.0.1:8765` en el navegador. Cerrar la ventana negra apaga todo.
- **Línea de comandos:** `python gxpruebas.py --help`.

### Requisitos

- Python 3.9 o superior.
- Java 17: `java` y `javac` en el PATH.
- La KB compilada al menos una vez: tienen que existir `JavaModel\web\build\classes` y `build\libs`.
- La base de datos de la KB levantada (MySQL local).

No hace falta instalar nada más: no usa librerías externas.

## Flujo recomendado

1. Compilá en GeneXus (Build).
2. En **Explorar**, elegí el objeto. GxPruebas arma un formulario a partir de los SDT de entrada. Ejecutalo y mirá la salida. Si querés ver qué cambió en la base, agregá **consultas SQL después**: corren en la misma transacción, así que ven los cambios antes del rollback.
3. **Guardar como caso**: queda en una suite (`suites\<KB>\<suite>.json`) y la salida que viste queda **aprobada**. Al guardar se ejecuta una vez más: lo que da distinto (fechas, ids nuevos) se marca como «cambia solo». Marcá lo que además tiene que cumplirse siempre: GxPruebas lo sugiere, con `Ok` y los códigos de mensaje ya marcados. Si la ejecución terminó en excepción, el caso queda como «tiene que terminar con este error».
4. En **Suites**, corré todo después de cada cambio, o dejá que corra solo después de cada build. Si algo cambió, ves un resumen («`Registros[*].Importe`: 100 → 110 en 12 de 40 elementos»). Si el cambio es correcto, **aceptá la salida**; si es un campo que no importa, **ignoralo**.

## Qué hay en cada pantalla

| Pantalla | Para qué |
|---|---|
| **Explorar** | Catálogo de procedimientos y Data Providers sacado de la especificación. Para cada uno: parámetros con su dirección y tipo Java, entrada como formulario o JSON, consultas SQL después, rollback o commit, salida en árbol (los espacios finales de los `Character` se ven como `·`), consola, excepción, navegación (tablas, índices, filtros) y warnings de especificación. |
| **Suites** | Casos con sus pasos. Correr todo, los seleccionados o los fallidos. Aprobar salidas. Resumen de qué cambió, con «Es correcto: aceptar esta salida», «Ignorar» y «Comparar solo estructura». Editor de casos con ayudantes. Opciones, variables y preparación por suite. |
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

- **`lineaBase`:** la **salida aprobada**. No hace falta escribirla: se aprueba la salida que viste («Guardar como caso», «Aceptar esta salida» o `correr --grabar`). Se compara así:
  - Por defecto, toda la salida tiene que coincidir.
  - Con `"comparar": "estructura"` solo se controlan los campos, sus tipos, `Ok` y los códigos de mensaje (como conjunto: el orden no importa). Sirve para listados con datos de la base que cambian.
  - En las rutas de `volatiles` (se detectan solas, ejecutando dos veces) solo se controla que el campo exista y tenga el mismo tipo. Las rutas de `ignorar` no se comparan.
  - Lo que **no** es una falla: un campo nuevo en la salida (queda como aviso hasta que aceptes la salida) y una colección que GeneXus omite del JSON por estar vacía (cuenta como vacía).
  - `Ok` y los códigos de mensaje nunca se marcan como volátiles ni se ofrecen para ignorar.
- **`verificaciones`:** reglas `{ruta, op, valor, cada}` con lo que el caso exige siempre (por ejemplo, «falla con el código REQUERIDO»). Siguen valiendo aunque se acepte una salida nueva: si la salida no las cumple, GxPruebas pregunta antes de aceptarla. Los operadores son `igual`, `distinto`, `contiene`, `no_contiene`, `empieza`, `termina`, `regex`, `mayor`, `mayor_igual`, `menor`, `menor_igual`, `entre`, `en`, `existe`, `no_existe`, `vacio`, `no_vacio`, `largo`, `largo_min`, `largo_max`, `tipo` y `coincide`.
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
- las predefinidas `${hoy}`, `${ahora}`, `${aleatorio}`, `${uuid}` y `${caso}`.

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
python gxpruebas.py describir --kb Generales --objeto Generales.Interfases.Registro.Set
python gxpruebas.py objetos --kb Generales --buscar interfases
python gxpruebas.py sql --kb Generales --ds GENERALES "select * from gntInterfase"
python gxpruebas.py suites
python gxpruebas.py vigilar --kb Generales --etiqueta auto   :: corre las suites después de cada build
python gxpruebas.py revisar --kb Generales --objeto ...      :: buenas prácticas en el fuente GX
```

## Cómo funciona por dentro

- **Catálogo:** lee los XML de navegación (`GXSPC*\GEN*\NVG\**.xml`) que deja la especificación. De ahí salen los objetos, los parámetros con `in`/`out`/`inout`, la navegación y los warnings.
- **Motor:** `motor\GxMotor.java` corre en una JVM por KB, con el classpath de la KB. Inicializa GeneXus con el `client.cfg` de la KB, ejecuta `execute(...)` por reflexión y convierte los JSON a SDT y al revés con la serialización de GeneXus. Las consultas SQL usan la misma conexión: por eso ven los cambios sin confirmar.
- **Sin bloquear tus builds:** los `.jar` de `build\libs` se copian a `.cache\jars`, compartida entre KBs: un mismo `.jar` se guarda una sola vez aunque lo usen varias KBs (se identifica por un hash de su contenido, que se calcula la primera vez y queda en `indice.json`). Cada vez que arranca un motor se borran las copias que ya no usa ninguna KB (las que están abiertas por un motor en marcha quedan para la próxima). Si GeneXus recompila, el motor se reinicia solo en el siguiente pedido. Si pasan 15 minutos sin uso, se apaga y libera las conexiones.
- **Resultados:** se guardan en `resultados\` como JSON (las últimas 300 corridas). Las suites borradas van a `.papelera\`.

### Dónde está cada cosa

`gxpruebas.py` solo arranca la línea de comandos. La lógica está en paquetes de `gxp\`, cada uno con su API en el `__init__.py` y la lista de sus módulos en el docstring:

| Paquete | Qué hace |
| --- | --- |
| `kbs.py`, `catalogo.py`, `config.py`, `util.py` | KBs encontradas, objetos y parámetros, `config.json`, lectura y escritura de JSON |
| `motor\` | el proceso Java de cada KB: describir, ejecutar, SQL, fin de transacción |
| `suites\` | formato y almacén de las suites, ejecución de pasos y casos, salidas aprobadas, corridas, reportes |
| `comparacion\` | comparación con `esperado` y la salida aprobada, operadores de `verificaciones`, volátiles |
| `generacion\`, `efectos.py` | suites `auto-*` y la detección de objetos de solo lectura |
| `revisor\` | fuente GX desde la especificación, reglas de buenas prácticas, línea base, pantalla Revisión |
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

- Un objeto con **Commit on exit = Yes**, o que hace `Commit` explícito, graba aunque el caso haga rollback. La interfaz lo marca con «⚠ hace commit», y la corrida lo avisa.
- La **base local** es la que dice el `client.cfg` de la KB. Si la volvés a descargar con tus scripts, las líneas base que dependen de los datos pueden cambiar.
- Los procedimientos que dependen de la **sesión web** (GAM, WebSession, HttpRequest) pueden comportarse distinto fuera de Tomcat.
- La interfaz escucha solo en `127.0.0.1`.
