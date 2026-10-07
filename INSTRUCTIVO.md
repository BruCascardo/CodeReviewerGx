# GxPruebas: instructivo rápido

## 1. Abrir

1. Compilá la KB en GeneXus (Build).
2. Hacé doble clic en **`GxPruebas.bat`**. Se abre el navegador.
3. Arriba a la izquierda, elegí la **KB**.

> No cierres la ventana negra mientras la uses: si la cerrás, se apaga todo.

## 2. Probar un objeto

1. Andá a la pestaña **Explorar** y buscá el objeto. Por ejemplo, escribí `registro list`.
2. Hacé clic en el objeto. Aparece un formulario con los parámetros de entrada.
3. Completá los valores. Por ejemplo, `ItfId = 1`.
4. Apretá **▶ Ejecutar** (o `Ctrl+Enter`).
5. A la derecha ves la salida. Hacé clic en ▸ para desplegar.

**Opcional:** con **+ consulta** agregás un `select` que corre después del objeto, para ver qué grabó en la tabla.

**Opcional:** con **SQL previo** escribís sentencias que corren *antes* del objeto, por ejemplo `delete from tabla;` para probar con la tabla vacía. **Copiar de una suite** trae el script previo de una suite. También se deshace al final.

> Al terminar se hace **rollback**: no queda nada grabado en la base. Para grabar de verdad, elegí **Commit**.

## 3. Guardarlo como prueba

Si la salida que viste es la correcta:

1. Apretá **Guardar como caso…**.
2. Elegí una suite existente o **Nueva suite**, y ponele nombre al caso.
3. En **Comparar con esta salida** dejá **Toda la salida**. Elegí **Solo la estructura** si es un listado con datos de la base que cambian.
4. En **Además, siempre tiene que cumplirse**, `Ok` y los códigos de mensaje ya vienen marcados. Marcá algo más solo si es lo que el caso prueba (por ejemplo, un importe calculado).
5. Apretá **Guardar**. GxPruebas lo ejecuta una vez más para detectar lo que cambia solo (fechas, ids nuevos): en esos campos solo controla que existan.

> Si la ejecución terminó en una excepción y eso es lo esperado, el diálogo ofrece **Tiene que terminar con este error**.

> Si usaste **SQL previo**, el diálogo pregunta qué hacer con él: usarlo como **script previo de la suite** (corre una vez antes de todos sus casos) o agregarlo como primeros pasos del caso.

### Script previo: pruebas que no dependen de los datos

En **Suites → Más → Opciones**, el **Script previo** deja la base como la necesitás antes de correr la suite, por ejemplo vacía. Corre una sola vez y al final se deshace todo, el script incluido. Usá `delete from` (no `truncate`: confirmaría la transacción y no se acepta).

En **Entre un caso y otro** elegís:

- **Cada caso arranca de cero** (recomendado): cada caso parte de la base que dejó el script, sin ver lo que hicieron los anteriores. Podés correr uno solo o en cualquier orden.
- **Cada caso sigue de lo que dejó el anterior**: por ejemplo, el caso 1 crea un cupón y el 2 lo usa. El orden importa: si corrés solo algunos casos, los que dependen de otros pueden fallar.

## 4. Volver a validar después de cada cambio

1. Cambiá lo que necesites en GeneXus y compilá.
2. Andá a la pestaña **Suites** y elegí la suite.
3. Apretá **▶ Correr todo**.
4. Mirá el estado de cada caso:
   - 🟢 **OK**: sigue funcionando igual.
   - 🔴 **Falla**: hacé clic en el caso. Vas a ver qué cambió, agrupado (por ejemplo, «`Registros[*].Importe`: 100 → 110 en 12 de 40 elementos»), con lo que define el resultado (`Ok`, códigos de mensaje) primero.
   - 🟣 **Error**: el objeto dio una excepción. Vas a ver el detalle en la pestaña *Excepción*.
5. Si falló, decidí:
   - **El cambio es correcto** (cambiaste el comportamiento a propósito): **Es correcto: aceptar esta salida**.
   - **Es un campo que no importa:** **Ignorar** en esa fila.
   - **Los datos de la base cambian solos** (por ejemplo, un listado): **Comparar solo estructura**.
   - **Es un error:** corregilo en GeneXus y volvé a compilar.

Un campo nuevo en la salida no hace fallar el caso: aparece como aviso hasta que aceptes la salida.

**Automático:** con GxPruebas abierto, las suites de las KBs configuradas corren solas unos segundos después de cada build. Te avisa con una notificación de Windows: hacé clic en ella para ver el resultado. Qué KBs y qué casos se corren se configura en `config.json` (ver «Pruebas automáticas después de cada build» en `LEEME.md`).

## 5. Otras pestañas

- **Historial:** todas las corridas anteriores.
- **SQL:** consultas a la base. También terminan con rollback.
- **Ayuda:** el formato completo de los casos y los operadores.

## Trabajar con la base compartida del equipo

Las suites, los objetos ignorados del revisor y la configuración del equipo están en una base MySQL compartida: lo que guarda uno lo ven todos.

**La primera vez, en tu PC:**

1. Bajá el proyecto: `git clone https://github.com/BruCascardo/CodeReviewerGx GxPruebas`.
2. Instalá la librería de MySQL: `python -m pip install -r requirements.txt`.
3. Copiá `.env.ejemplo` como `.env` y completá usuario y contraseña (te los pasa quien administra la base). `.env` no se sube al repositorio.
4. Si tus KBs no están en `C:\KBGXSERVER\CORE` o `C:\KBGXSERVER\FIXES`, cambiá `raicesKB` en `config.json`.
5. Probá la conexión: `python gxpruebas.py compartido estado`. Tiene que decir «conectado» y cuántas suites hay.
6. Abrí `GxPruebas.bat`. Arriba a la derecha aparece **base compartida** con la luz verde.

**En el día a día** no cambia nada: guardás casos, aprobás salidas y borrás suites desde la interfaz, y queda en la base.

- Si dos personas cambian la misma suite a la vez, la segunda ve «cambió desde que la abriste»: volvé a abrir la suite y repetí el cambio.
- Para cambiar los objetos ignorados o las excepciones del revisor: `python gxpruebas.py compartido editar revisor`.
- Si borraste una suite por error: `python gxpruebas.py compartido papelera` y `python gxpruebas.py compartido restaurar <suite>`.
- Si la luz de **base compartida** está en rojo, no hay conexión: ves la última copia que bajaste, pero no se puede guardar nada hasta que vuelva.

## Desde la consola (opcional)

Correr todas las pruebas de una KB:

```bat
python gxpruebas.py correr --kb Generales
```

Ejecutar un objeto suelto:

```bat
python gxpruebas.py ejecutar --kb Generales --objeto Generales.Interfases.Registro.List --entrada "{\"inList\":{\"ItfId\":1}}"
```

## Si algo no anda

| Problema | Qué hacer |
|---|---|
| El objeto no aparece en la lista | Especificá o compilá la KB en GeneXus. |
| Aparece «motor con error» | Hacé clic en ☰ (arriba a la derecha) para ver el log, y en ⟳ para reiniciar. |
| Error de conexión a la base | Revisá que MySQL esté levantado. |
| «sin conexion con la base compartida» | Revisá `.env` y que tu red llegue al puerto 3306 del servidor (`python gxpruebas.py compartido estado`). |
| «falta la libreria PyMySQL» | `python -m pip install -r requirements.txt` |
| Ves «hace commit» | Ese objeto graba igual, aunque se haga rollback. Probalo con cuidado. |
