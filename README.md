# GxPruebas

GxPruebas ejecuta y prueba **cualquier procedimiento o Data Provider** de una KB de GeneXus compilada en Java, sin el IDE ni Tomcat.

Todo corre dentro de una transacción que **al final se deshace** (rollback): podés dar de alta, modificar y borrar sin dejar nada en la base.

**Contenido:** [Instalar y abrir](#instalar-y-abrir) · [Explorar](#explorar-probar-un-objeto) · [Suites](#suites-pruebas-que-se-repiten) · [Valores dinámicos](#valores-dinámicos) · [Cómo se controla un paso](#cómo-se-controla-un-paso) · [Pruebas después del build](#pruebas-automáticas-después-de-cada-build) · [Base compartida](#base-compartida) · [Revisor](#revisor-de-buenas-prácticas) · [Otras herramientas](#otras-herramientas) · [Consola](#línea-de-comandos) · [Si algo no anda](#si-algo-no-anda)

---

## Instalar y abrir

**Requisitos:** Python 3.9 o superior, Java 17 (`java` y `javac` en el PATH), la KB compilada al menos una vez y su base MySQL levantada.

**La primera vez:**

1. Bajá el proyecto: `git clone https://github.com/BruCascardo/CodeReviewerGx GxPruebas`.
2. Instalá la librería de MySQL: `python -m pip install -r requirements.txt`.
3. Si usás la [base compartida](#base-compartida) del equipo, copiá `.env.ejemplo` como `.env` y completá usuario y contraseña.
4. Si tus KBs no están en `C:\KBGXSERVER\CORE` o `C:\KBGXSERVER\FIXES`, cambiá `raicesKB` en `config.json`.

**Abrir:** doble clic en **`GxPruebas.bat`**. Se abre el navegador en `http://127.0.0.1:8765`. Arriba a la izquierda elegís la **KB**.

> No cierres la ventana negra mientras lo uses: si la cerrás, se apaga todo. Si actualizaste GxPruebas, cerrala y volvé a abrir el `.bat` para que tome los cambios.

| Pantalla | Para qué |
|---|---|
| **Explorar** | Elegir un objeto, completar su entrada, ejecutarlo y ver la salida. Desde acá se guardan los casos. |
| **Suites** | Los casos guardados: correrlos, ver qué falló y aprobar salidas nuevas. |
| **Historial** | Todas las corridas, con su detalle (se descargan en JUnit XML o JSON). |
| **Revisión** | Buenas prácticas del fuente GX, lo más reciente primero. |
| **Grafo** | Quién usa a quién, en todas las KBs. |
| **SQL** | Consultas a la base de la KB (siempre con rollback). |
| **Ayuda** | Resumen del formato de los casos, operadores y variables. |

---

## Explorar: probar un objeto

1. **Elegí el objeto** en la lista de la izquierda. Podés buscar por nombre (`/` pone el cursor en el buscador).
2. **Completá la entrada.** El formulario sale de los SDT del objeto. Con **JSON** la editás como texto; **Plantilla** vuelve a la entrada vacía.
3. **Usá los combos** (**▾** al lado del campo, o `Alt+↓`). Ofrecen los valores del dominio enumerado, los ids que hay en la base y, arriba de todo, los [valores dinámicos](#valores-dinámicos): un id que no existe, uno en tal estado, hoy+30…
4. **Ejecutá** con **▶ Ejecutar** (o `Ctrl+Enter`). Por defecto termina con **Rollback**: no queda nada grabado. Para grabar de verdad, elegí **Commit**.
5. **Mirá el resultado** a la derecha: la salida en árbol (▸ despliega), el JSON, la entrada que se mandó (con las variables ya reemplazadas) y la excepción, si hubo. Los avisos «Buenas prácticas» marcan un `Ok` o mensajes incoherentes en la salida.

**Ver qué pasó en la base:**

- **+ consulta** agrega un `select` que corre **después** del objeto, en la misma transacción: ve lo que grabó antes de que se deshaga.
- **SQL previo** corre **antes** del objeto, por ejemplo `delete from tabla;` para probar con la tabla vacía. **Copiar de una suite…** trae el script previo de una suite. También se deshace al final.

### Guardar como caso

Si la salida es la correcta, **Guardar como caso…**:

1. Elegí una suite o **➕ Nueva suite…** y ponele nombre al caso.
2. En **Comparar con esta salida** dejá **Toda la salida**. Elegí **Solo la estructura** si es un listado con datos de la base que cambian.
3. En **Además, siempre tiene que cumplirse**, `Ok` y los códigos de mensaje ya vienen marcados. Marcá algo más solo si es lo que el caso prueba.
4. **Guardar.** La salida queda **aprobada** y el caso se ejecuta una vez más para detectar lo que cambia solo (fechas, ids nuevos): de esos campos solo se controla que existan.

Si la ejecución terminó en excepción y es lo esperado, el diálogo ofrece **Tiene que terminar con este error**. Si usaste SQL previo, pregunta si va como script previo de la suite o como primeros pasos del caso.

### Generar validaciones

Con una entrada que **termina bien**, **Generar validaciones…** arma de una vez las pruebas de error del objeto. Propone una fila por cada campo vacío, cada lista vacía, cada valor del dominio y cada id que no existe; las ejecuta (con rollback) y muestra qué devuelve **hoy** cada una.

- Vienen marcadas las que fallan y las de dominio.
- Un campo vacío que el objeto **acepta** queda sin marcar con el aviso «lo acepta: no es obligatorio, o falta validarlo». Fijate si es un bug.
- En **Se espera** corregís lo que el caso va a exigir. Si el objeto acepta algo que tendría que rechazar, poné «falla»: el caso va a fallar hasta que se arregle.

Se guarda como **un caso con una fila de `datos` por prueba**, que verifica `Ok` y el código del mensaje (o el texto, si el objeto no devuelve código).

---

## Suites: pruebas que se repiten

> En la pantalla **Suites**, **🎓 Cómo armar pruebas** (arriba de la lista) abre un tutorial animado de 11 pasos con todo lo de esta sección y la de valores dinámicos.

Una **suite** (`suites\<KB>\<nombre>.json`) tiene **casos**. Un caso prueba **un comportamiento** y tiene uno o más **pasos**: cada paso ejecuta un objeto o una consulta SQL y controla su salida. Cada caso corre en su propia transacción y al final se deshace.

### Volver a validar después de cada cambio

1. Cambiá lo que necesites en GeneXus y compilá.
2. En **Suites**, elegí la suite y apretá **▶ Correr todo** (o los seleccionados, o los fallidos).
3. Mirá cada caso:
   - 🟢 **OK**: sigue funcionando igual.
   - 🔴 **Falla**: hacé clic. **Qué cambió** muestra las diferencias agrupadas («`Registros[*].Importe`: 100 → 110 en 12 de 40 elementos»).
   - 🟣 **Error**: el objeto dio una excepción (pestaña *Excepción*).
4. Si falló, decidí:
   - **El cambio es correcto** (lo cambiaste a propósito): **Sí: aceptar esta salida**.
   - **Es un campo que no importa**: **No comparar** ese campo.
   - **Es un error**: corregilo en GeneXus, compilá y volvé a correr. No aceptes la salida.

Un campo nuevo en la salida no hace fallar el caso: queda como aviso hasta que aceptes la salida. Las **verificaciones** son lo que el caso exige siempre: si no se cumplen, aceptar la salida pide confirmación.

### Configurar un caso

Al abrir un caso, cada paso muestra **Qué controla**, con ✔ / ✖ según la última corrida:

- **Verificaciones**: **+ Agregar verificación**, o **clic en un valor de la salida**. Te dice si se cumple antes de guardarla.
- **Guardar como variable**: clic en un valor de la salida (por ejemplo, el id que devolvió un alta) para usarlo en los pasos siguientes.
- **Esperado**, **No se comparan**, **Cambian solos**, **Guarda**: se ven y se quitan desde ahí.
- Lo demás (nombre, entrada, `datos`) se edita con **Editar JSON**.

### Script previo y casos encadenados

En **Suites → Más → Opciones**:

- **Script previo**: deja la base como la necesitás antes de correr la suite (por ejemplo, vacía), así las salidas no dependen de los datos. Corre una vez; cada caso arranca de la base que deja y al final se deshace todo, el script incluido. Mientras corre, el commit de los objetos **se simula**: nada queda grabado. Usá `delete from` (las hijas primero); `truncate`, `drop`, `alter`, `commit` y similares no se aceptan porque confirmarían la transacción.
- **Entre un caso y otro**:
  - **Cada caso arranca de cero** (recomendado): ningún caso ve lo que hicieron los anteriores. Podés correr uno solo o en cualquier orden.
  - **Cada caso sigue de lo que dejó el anterior** (`"casosEncadenados": true`): el caso 1 crea un cupón y el 2 lo usa con `${cupon}`. El orden importa: si corrés solo algunos, los que dependen de otros pueden fallar.
- **Variables** (para todos los casos) y **Preparación** (pasos al principio de cada caso).

---

## Valores dinámicos

Un caso que dice `"CuponId": 60` («un cupón que no existe») sirve hoy. Cuando alguien cree el cupón 60, el caso falla sin que nada esté mal.

Por eso, en lugar del valor se escribe **cómo conseguirlo**: `"CuponId": "${siguiente.CuponId}"`. Se calcula **cada vez que corre el caso**: hoy da 60, mañana puede dar 61. Lo mismo con fechas: `${hoy+30}` en lugar de `2026-11-06`.

Se escriben **entre comillas**, con `${...}`, en la entrada, en las consultas SQL, en `esperado`, en las verificaciones y en la salida aprobada. Si el texto es solo la variable, conserva su tipo (`60` queda número). En Explorar, los combos las ofrecen con el valor que darían hoy.

### Valores calculados en la base

Ids que se buscan en la base al ejecutar. Se calculan la primera vez que se usan en el caso y **quedan fijos para el resto del caso**. `CuponId` es el último atributo de la clave de una tabla (`cbhCupon`).

| Escribís | Te da | Hoy daría |
|---|---|---|
| `${siguiente.CuponId}` | Uno que **no existe**: el último + 1 (solo claves numéricas). | 60 |
| `${existente.CuponId}` / `${ultimo.CuponId}` | El primero / el último que existe. | 1 / 59 |
| `${existente.CuponId\|CuponEstado=PENDIENTE}` | El primero que cumple la condición. Varias, separadas por coma; con `=`, `!=`, `<`, `>`, `<=`, `>=`. | 1 |
| `${con_hijos.CuponId}` | Uno con filas en alguna tabla que lo referencia (su detalle, o una clave foránea). | 1 |
| `${con_hijos.CuponId:cbhCuponDetalle}` | Uno con filas en **esa** tabla. | 1 |
| `${sin_hijos.CuponId}` | Uno sin filas en ninguna tabla que lo referencia. | |

- En un atributo de **dominio enumerado** podés usar el nombre del valor (`PENDIENTE`) en lugar del guardado (`PEN`). Entre comillas, el valor se toma tal cual: `CuponTipo='LIQ'`.
- **Una variable dentro de otra**, para claves compuestas: `"${ultimo.CuponDetSec|CuponId=${con_hijos.CuponId:cbhCuponDetalle}}"`.
- Si no hay ninguno que cumpla, el paso queda en error y dice por qué.

### Fechas relativas

Ejemplos con hoy = miércoles 7 de octubre de 2026:

| Escribís | Da |
|---|---|
| `${hoy}` · `${hoy+1}` · `${hoy-1}` · `${hoy+30}` | 2026-10-07 · 2026-10-08 · 2026-10-06 · 2026-11-06 |
| `${hoy+2m}` (meses) · `${hoy-1a}` (años) | 2026-12-07 · 2025-10-07 |
| `${inicio_mes}` · `${fin_mes}` · `${fin_mes+1}` | 2026-10-01 · 2026-10-31 · 2026-11-30 |
| `${inicio_anio}` · `${fin_anio}` | 2026-01-01 · 2026-12-31 |
| `${habil_siguiente}` · `${habil_anterior}` (lunes a viernes, sin feriados) | 2026-10-08 · 2026-10-06 |
| `${fecha_vacia}` | `""` (la fecha vacía de GeneXus) |
| `${ahora}` · `${ahora+2h}` · `${ahora-30min}` | 2026-10-07T15:30:00 · 2026-10-07T17:30:00 · … |

### Otras variables

| Escribís | Te da |
|---|---|
| `${itf}` | Una variable de la suite (Opciones → Variables). |
| `${tipo}` | La columna `tipo` de la fila de `datos` que se está corriendo. |
| `${cupon}` | Lo que un paso anterior guardó con `"guardar": {"cupon": "outSet.CuponId"}`. |
| `${alta.outSet.CuponId}` | La salida de un paso anterior (nombre del paso en minúsculas, `_` en lugar de espacios). |
| `${alta.entrada.inSet.Importe}` | Lo que se le **mandó** a un paso anterior. |
| `${aleatorio}`, `${uuid}`, `${caso}` | Un número al azar, un uuid, el id del caso. |

### Ejemplos

Todos estos casos están probados contra la base de Cobranzas.

**1. Un cupón que no existe**

```json
{
  "nombre": "Cerrar un cupón que no existe",
  "pasos": [
    {
      "nombre": "Cerrar",
      "objeto": "Cobranzas.Cupones.Cerrar",
      "entrada": { "inCerrar": { "CuponId": "${siguiente.CuponId}" } },
      "verificaciones": [
        { "ruta": "outCerrar.OutPut.Ok", "op": "igual", "valor": false },
        { "ruta": "outCerrar.OutPut.Messages[0].Texto", "op": "contiene", "valor": "no existe" }
      ]
    }
  ]
}
```

**2. Un cupón en un estado, y verificar en la base lo que quedó**

El segundo paso usa la entrada del primero (`${cambiar_estado.entrada...}`), así consulta el mismo cupón.

```json
{
  "nombre": "Pagar un cupón pendiente",
  "pasos": [
    {
      "nombre": "Cambiar estado",
      "objeto": "Cobranzas.Cupones.CambiarEstado",
      "entrada": { "inCambiarEstado": { "CuponId": "${existente.CuponId|CuponEstado=PENDIENTE}", "CuponEstado": "PAG" } },
      "verificaciones": [ { "ruta": "outCambiarEstado.Output.Ok", "op": "igual", "valor": true } ]
    },
    {
      "nombre": "Quedó pagado",
      "ds": "COBRANZAS",
      "sql": "select CuponEstado from cbhCupon where CuponId = ${cambiar_estado.entrada.inCambiarEstado.CuponId}",
      "verificaciones": [ { "ruta": "filas[0].CuponEstado", "op": "igual", "valor": "PAG" } ]
    }
  ]
}
```

**3. Varias reglas en un solo caso, con `datos`**

El caso corre una vez por fila. Cada columna es una variable, y una columna puede tener un valor dinámico.

```json
{
  "nombre": "Cambiar estado: una fila por regla",
  "datos": [
    { "prueba": "pasa a pagado",            "cupon": "${existente.CuponId|CuponEstado=PENDIENTE}", "estado": "PAG", "ok": true },
    { "prueba": "en proceso no se permite", "cupon": "${existente.CuponId|CuponEstado=PENDIENTE}", "estado": "PRO", "ok": false },
    { "prueba": "ya está pendiente",        "cupon": "${existente.CuponId|CuponEstado=PENDIENTE}", "estado": "PEN", "ok": false },
    { "prueba": "cupón que no existe",      "cupon": "${siguiente.CuponId}",                        "estado": "PAG", "ok": false }
  ],
  "pasos": [
    {
      "nombre": "Cambiar estado",
      "objeto": "Cobranzas.Cupones.CambiarEstado",
      "entrada": { "inCambiarEstado": { "CuponId": "${cupon}", "CuponEstado": "${estado}" } },
      "verificaciones": [ { "ruta": "outCambiarEstado.Output.Ok", "op": "igual", "valor": "${ok}" } ]
    }
  ]
}
```

**Generar validaciones** (en Explorar) arma un caso así automáticamente.

**4. Una regla que depende de otra tabla, con clave compuesta**

Busca un cupón que tiene detalle y **no** está en proceso, toma su última línea y verifica que no se pueda eliminar.

```json
{
  "nombre": "No se puede eliminar una línea de un cupón que no está en proceso",
  "pasos": [
    {
      "nombre": "Eliminar",
      "objeto": "Cobranzas.Cupones.Cuotas.Eliminar",
      "entrada": { "inEliminar": {
        "CuponId":     "${con_hijos.CuponId:cbhCuponDetalle|CuponEstado!=EN_PROCESO}",
        "CuponDetSec": "${ultimo.CuponDetSec|CuponId=${con_hijos.CuponId:cbhCuponDetalle|CuponEstado!=EN_PROCESO}}"
      } },
      "verificaciones": [
        { "ruta": "outEliminar.OutPut.Ok", "op": "igual", "valor": false },
        { "ruta": "outEliminar.OutPut.Messages[0].Texto", "op": "contiene", "valor": "NO SE ENCUENTRA EN PROCESO" }
      ]
    },
    {
      "nombre": "Sigue estando",
      "ds": "COBRANZAS",
      "sql": "select count(*) as n from cbhCuponDetalle where CuponId = ${eliminar.entrada.inEliminar.CuponId} and CuponDetSec = ${eliminar.entrada.inEliminar.CuponDetSec}",
      "verificaciones": [ { "ruta": "filas[0].n", "op": "igual", "valor": 1 } ]
    }
  ]
}
```

**5. Fechas relativas**

```json
{
  "nombre": "Cupones que vencen este mes",
  "pasos": [
    {
      "nombre": "Del mes",
      "ds": "COBRANZAS",
      "sql": "select count(*) as n from cbhCupon where CuponFechaVencimiento between '${inicio_mes}' and '${fin_mes}'",
      "verificaciones": [ { "ruta": "filas[0].n", "op": "mayor_igual", "valor": 0 } ]
    }
  ]
}
```

En una entrada: `"FechaDesde": "${hoy}", "FechaHasta": "${hoy+30}"`. En una consulta SQL, la fecha va entre comillas simples: `'${hoy+30}'`.

### Al aprobar una salida

Si el objeto **devuelve** el valor que le diste (por ejemplo, el `CuponId` que recibió), al aprobar la salida se guarda la variable y no el número de ese día. Así el caso sigue pasando cuando la base cambia. Se hace solo en el campo que se llama como el atributo (`CuponId`), en los campos con una fecha relativa y dentro de los textos («No existe el cupón 60»), y se avisa qué campos quedaron con una variable. Si el objeto devuelve el id en un campo con otro nombre (`Id`), poné la variable a mano en la salida aprobada.

### Errores comunes

| Mensaje | Qué pasa |
|---|---|
| `Variable no definida: ${cupon}` | Nadie la define (variables de la suite, `datos` o `guardar`). Si la guarda otro caso, el mensaje dice cuál y por qué no llegó. |
| `No se pudo calcular ${...}: no hay ningun ... que cumpla ...` | Hoy no hay ninguna fila que cumpla. Revisá la condición o creá el dato antes. |
| `... no es la clave de ninguna tabla` | El atributo tiene que ser el último de la clave de una tabla: `CuponId`, no `CuponTipo`. |
| `... solo se calcula para claves numericas` | `${siguiente.X}` no funciona con claves de texto. |

---

## Cómo se controla un paso

Cada paso se puede controlar de cuatro formas, combinables:

- **Salida aprobada** (`lineaBase`): no se escribe, se aprueba. Por defecto toda la salida tiene que coincidir; con `"comparar": "estructura"`, solo campos, tipos, `Ok` y códigos de mensaje. Los campos «cambian solos» (`volatiles`) solo tienen que existir y tener el mismo tipo; los de `ignorar` no se comparan.
- **Verificaciones**: `{ "ruta", "op", "valor" }`, lo que el caso exige siempre.
- **Esperado**: coincidencia parcial, solo se controla lo que está escrito: `"esperado": {"outSet": {"Output": {"Ok": true}}}`.
- **`esperaError`**: el paso tiene que terminar con una excepción (opcional: `"errorContiene": "texto"`).

| Operador | Se cumple si |
|---|---|
| `igual` / `distinto` | Es (o no) igual al valor. |
| `contiene` / `no_contiene` | Texto: contiene el valor. **Lista: algún elemento es igual al valor.** |
| `empieza`, `termina`, `regex` | El texto empieza, termina o cumple la expresión regular. |
| `mayor`, `mayor_igual`, `menor`, `menor_igual`, `entre` | Comparaciones (`entre`: `[desde, hasta]`). |
| `en` | Es igual a alguno de los valores de la lista. |
| `existe` / `no_existe` | La ruta existe (o no). |
| `vacio` / `no_vacio` | Vacío a la manera de GeneXus (`""`, `0`, `false`, `[]`). También pasa si la ruta no existe: GeneXus omite lo vacío. |
| `largo`, `largo_min`, `largo_max` | Cantidad de elementos o caracteres. |
| `tipo` | `texto`, `numero`, `booleano`, `lista`, `objeto`, `nulo`. |

- **Rutas:** `outList.Registros[0].Tipo`; `[*]` todos los elementos, `[-1]` el último. En SQL la salida es `{ "filas": [...], "cantidad": n }` → `filas[0].n`.
- `"cada": true` con `[*]` aplica el operador a cada elemento. `"omitirSiVacio": true` no controla la verificación si su valor queda vacío (útil con `datos`).
- **Comodines** en `esperado` y la salida aprobada: `<<cualquiera>>`, `<<no_vacio>>`, `<<vacio>>`, `<<numero>>`, `<<texto>>`, `<<fecha>>`, `<<regex:...>>`, `<<contiene:...>>`, `<<mayor:n>>`, `<<menor:n>>`, `<<distinto:x>>`.
- Si la salida tiene `Output.Ok` y `Output.Messages`, verificá también el **código** del mensaje, no solo `Ok`.

**Otros campos de una suite:** `opciones` (`transaccion`, `recortarEspacios`, `casosEncadenados`), `variables`, `scriptPrevio` (`[{"ds", "sql"}]`), `preparacion`; y en cada caso `etiquetas`, `datos`, `omitir`; en cada paso `guardar`. Un paso `sql` puede tener varias sentencias separadas por `;`.

---

## Pruebas automáticas después de cada build

Con GxPruebas abierto, las suites corren solas unos segundos después de cada build, y te avisa con una notificación de Windows (clic para ver el resultado). Se configura en `config.json`:

```json
"despuesDelBuild": { "activo": true, "kbs": ["Generales"], "etiqueta": "", "esperaSeg": 15, "notificar": true, "revisar": true }
```

- `kbs`: las KBs a vigilar (`["*"]`: todas). `etiqueta`: si tiene valor, corre solo los casos con esa etiqueta.
- `revisar`: antes de las suites revisa las buenas prácticas de lo que cambió; un error **nuevo** cuenta como falla del build.
- Sin la interfaz: `python gxpruebas.py vigilar`. Los resultados quedan en el **Historial** marcados «después del build».

> Un objeto con **Commit on exit = Yes** graba igual, en cada build. Dejalo afuera con una etiqueta o dale un script previo a su suite (ahí el commit se simula).

---

## Base compartida

Las suites, la configuración del revisor y `opcionesSuite`/`despuesDelBuild` de `config.json` pueden vivir en una **base MySQL compartida**: lo que guarda uno lo ven todos. Se activa con el archivo `.env` (copiá `.env.ejemplo`; no se sube al repositorio):

```ini
GXP_DB_HOST=gascode.com.ar
GXP_DB_PORT=3306
GXP_DB_USER=...
GXP_DB_PASSWORD=...
GXP_DB_NAME=gxpruebas
```

Probá la conexión con `python gxpruebas.py compartido estado` (tiene que decir «conectado»). En la interfaz, arriba a la derecha, **base compartida** se ve con la luz verde. En el día a día no cambia nada: guardás, aprobás y borrás desde la interfaz.

- Si dos personas cambian la misma suite a la vez, la segunda ve «cambió desde que la abriste»: volvé a abrirla y repetí el cambio.
- Si la luz está en rojo, no hay conexión: ves la última copia, pero no se puede guardar.
- Con la base activa, `suites\` y `revisor.json` locales **no se usan**.

```bat
python gxpruebas.py compartido estado                       :: si está configurada y qué tiene
python gxpruebas.py compartido subir [archivos] [--pisar]   :: sube lo local (la primera vez, una sola persona)
python gxpruebas.py compartido editar <revisor|config|suite>
python gxpruebas.py compartido historial <revisor|config|suite>
python gxpruebas.py compartido papelera                     :: suites borradas
python gxpruebas.py compartido restaurar <suite> [--version N]
python gxpruebas.py compartido bajar [--carpeta X]          :: copia todo a archivos (respaldo)
```

---

## Revisor de buenas prácticas

Revisa el **fuente GX** de los objetos (sacado de la especificación, no el Java). En la interfaz, pestaña **Revisión**; desde la consola:

```bat
python gxpruebas.py revisar --kb Generales                                  :: toda la KB
python gxpruebas.py revisar --kb Generales --objeto ... --detalle           :: un objeto, con cómo arreglarlo
python gxpruebas.py revisar --kb Generales --objeto ... --fuente            :: el fuente GX reconstruido
python gxpruebas.py revisar --kb Generales --cambiados                      :: solo lo que cambió (lo que corre el build)
```

| Regla | Qué controla |
|---|---|
| `sin-commit-rollback` | Solo los Web Panels y Web Components confirman. Marca `Commit`, `Rollback`, llamadas a `prcCommit`/`prcRollback` y **Commit on exit = Yes** en cualquier otro objeto. |
| `salida-ok-mensajes` | Un `sdtOutput` de salida devuelve `Ok` y mensajes coherentes: un Error con `Ok = True`, `Ok = False` sin mensaje de Error, `Ok` sin asignar, o `Ok = True` sin mensaje de éxito (`Type = MessageTypes.Debug`). También se controla en cada ejecución real (avisos «Buenas practicas» del paso). |
| `alta-devuelve-id` | Un procedimiento que crea una entidad con un Business Component devuelve su clave, si el que llama no la conoce (autonumerados, numeradores). Es heurística: advertencia. |

**NUEVO** marca lo que introdujo la última modificación del objeto; solo eso hace fallar el build. Las reglas y las excepciones se configuran en `revisor.json` (`reglas`, `ignorar`, `excepciones` con un **motivo obligatorio**).

---

## Otras herramientas

- **Suites generadas:** `python gxpruebas.py generar --kb X` arma suites `auto-*` con un caso por cada objeto **de solo lectura**, para detectar si un cambio rompió otra cosa. Se aprueban con `correr --kb X --etiqueta auto --grabar`. No las edites a mano (salvo `"omitir": true`).
- **Grafo:** quién usa a quién en todas las KBs, qué objetos de un módulo se usan desde afuera, dependencias circulares y lo que está solo en la versión publicada (`.jar`) del módulo. Consola: `python gxpruebas.py grafo --objeto ...`.
- **Plan de ejecución:** en Explorar → **Navegación** → **Calcular plan de ejecución** (o `gxpruebas.py plan`): el `EXPLAIN` de las sentencias SQL del objeto, con recomendaciones de índices (búsquedas sin índice, `LIKE '%...'`, For Each anidados…).

---

## Línea de comandos

```bat
python gxpruebas.py objetos --kb Cobranzas --buscar cupones
python gxpruebas.py describir --kb Cobranzas --objeto Cobranzas.Cupones.Cerrar          :: parámetros y entrada de ejemplo
python gxpruebas.py ejecutar --kb Cobranzas --objeto Cobranzas.Cupones.Cerrar --entrada "{\"inCerrar\":{\"CuponId\":\"${siguiente.CuponId}\"}}"
python gxpruebas.py ejecutar --kb Cobranzas --objeto ... --entrada @entrada.json --sql "COBRANZAS: select ..." --sql-previo "COBRANZAS: delete from ..."
python gxpruebas.py validaciones --kb Cobranzas --objeto ... --entrada @entrada.json [--caso]
python gxpruebas.py sql --kb Cobranzas --ds COBRANZAS "select * from cbhCupon"
python gxpruebas.py correr                                   :: todas las suites; código 1 si algo falla
python gxpruebas.py correr cupones --kb Cobranzas --detalle
python gxpruebas.py correr cupones --grabar                  :: aprueba las salidas actuales
python gxpruebas.py correr --kb Cobranzas --etiqueta alta --junit resultados.xml
```

`ejecutar` y `sql` terminan con rollback, salvo `--commit`. Las pruebas unitarias de GxPruebas corren sin las KBs: `python -m unittest discover -s . -p "test_*.py" -t .`

---

## Si algo no anda

| Problema | Qué hacer |
|---|---|
| El objeto no aparece en la lista | Especificá o compilá la KB en GeneXus. |
| «motor con error» | Clic en ☰ (arriba a la derecha) para ver el log, y en ⟳ para reiniciar. |
| `No existe POST /api/...` | La interfaz quedó vieja: cerrá la ventana negra y volvé a abrir `GxPruebas.bat`. |
| Error de conexión a la base | Revisá que MySQL esté levantado. |
| «sin conexion con la base compartida» | Revisá `.env` y que llegues al puerto 3306 del servidor (`compartido estado`). |
| «falta la libreria PyMySQL» | `python -m pip install -r requirements.txt` |
| Ves «⚠ hace commit» | Ese objeto graba aunque se haga rollback. Probalo con un script previo (el commit se simula) o con cuidado. |
| Las salidas cambian al bajar otra base | Usá valores dinámicos o un script previo para no depender de los datos. |
| Un objeto de sesión web (GAM, WebSession) se comporta distinto | Fuera de Tomcat no hay sesión web: puede no funcionar igual. |
