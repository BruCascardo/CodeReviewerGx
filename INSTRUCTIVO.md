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

> Al terminar se hace **rollback**: no queda nada grabado en la base. Para grabar de verdad, elegí **Commit**.

## 3. Guardarlo como prueba

Si la salida que viste es la correcta:

1. Apretá **Guardar como caso…**.
2. Elegí una suite existente o **Nueva suite**, y ponele nombre al caso.
3. En **Comparar con esta salida** dejá **Toda la salida**. Elegí **Solo la estructura** si es un listado con datos de la base que cambian.
4. En **Además, siempre tiene que cumplirse**, `Ok` y los códigos de mensaje ya vienen marcados. Marcá algo más solo si es lo que el caso prueba (por ejemplo, un importe calculado).
5. Apretá **Guardar**. GxPruebas lo ejecuta una vez más para detectar lo que cambia solo (fechas, ids nuevos): en esos campos solo controla que existan.

> Si la ejecución terminó en una excepción y eso es lo esperado, el diálogo ofrece **Tiene que terminar con este error**.

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
| Ves «hace commit» | Ese objeto graba igual, aunque se haga rollback. Probalo con cuidado. |
