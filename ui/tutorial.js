/* GxPruebas - tutorial visual: cómo armar una suite con pruebas dinámicas (pantalla Suites). */
"use strict";

// Cada paso es una escena (una maqueta de la pantalla, hecha con los estilos de la app) y un guion que la anima:
// un cursor que se mueve, hace clic y escribe, con una nota que dice qué está pasando. La escena se vuelve a armar
// en cada vuelta. Los elementos que el guion toca se marcan con data-t="nombre".
//
// Acciones del guion: ["nota", texto] ["mover", nombre] ["clic"] ["escribir", nombre, texto] ["texto", nombre, texto]
// ["mostrar", nombre] ["ocultar", nombre] ["clase", nombre, clase] ["quitar", nombre, clase] ["foco", nombre]
// ["esperar", ms]. Con «reducir movimiento» del sistema, se muestra el estado final sin animar.

const TUT_CURSOR = '<svg viewBox="0 0 20 24" width="20" height="24" aria-hidden="true"><path d="M2 1.5v18.5l5.2-4.6 3.3 7.3 3.1-1.4-3.3-7.2 6.9-.4z" fill="#fff" stroke="#1d2330" stroke-width="1.5" stroke-linejoin="round"/></svg>';

// ---------------------------------------------------------------------- piezas de las maquetas
const tq = (n) => `[data-t="${n}"]`;
const tutVentana = (pestana, ...hijos) => h("div", { class: "tut-ventana" },
  h("div", { class: "tut-barra" }, h("span", { class: "tut-logo" }, "✓"),
    ["Explorar", "Suites"].map((p) => h("span", { class: `tut-pest ${p === pestana ? "activa" : ""}` }, p))),
  h("div", { class: "tut-cuerpo" }, ...hijos));
const tutCampo = (nombre, valor, t, { combo = true, desc = "" } = {}) => h("div", { class: "tut-campo" },
  h("label", null, nombre),
  h("span", { class: "tut-input", "data-t": t }, valor),
  combo ? h("span", { class: "tut-desple", "data-t": `${t}-d` }, "▾") : null,
  h("span", { class: "tut-desc tut-oculto", "data-t": `${t}-desc` }, desc));
const tutMenu = (t, titulo, ops, estilo) => h("div", { class: "tut-menu tut-oculto", "data-t": t, style: estilo },
  h("div", { class: "tut-menu-tit" }, titulo),
  ops.map(([valor, texto, op = {}]) => h("div", { class: `tut-op ${op.dinamica ? "dinamica" : ""} ${op.apagada ? "apagada" : ""}`, "data-t": op.t },
    h("span", { class: "mono" }, valor), h("span", { class: "muted" }, texto))));
const tutBoton = (texto, t, clase = "") => h("span", { class: `btn chico ${clase}`, "data-t": t }, texto);
const tutLinea = (clave, valor, t, tipo = "texto", nivel = 1) => h("div", { class: "tut-linea", style: { paddingLeft: `${nivel * 14}px` } },
  h("span", { class: "tut-k" }, clave, ": "), h("span", { class: `tut-v ${tipo}`, "data-t": t }, valor));
const tutModal = (t, titulo, ...hijos) => h("div", { class: "tut-modal tut-oculto", "data-t": t },
  h("div", { class: "tut-modal-cab" }, titulo), h("div", { class: "tut-modal-cuerpo" }, ...hijos));
const tutAviso = (t, texto) => h("div", { class: "tut-toast tut-oculto", "data-t": t }, texto);
const tutCodigo = (...lineas) => h("pre", { class: "tut-codigo" }, lineas.join("\n"));

// Fechas de hoy para el paso de fechas relativas (las mismas reglas que gxp/suites/fechas.py).
function tutFechas() {
  const f = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const hoy = new Date(); hoy.setHours(12, 0, 0, 0);
  const mas = (n) => { const d = new Date(hoy); d.setDate(d.getDate() + n); return d; };
  const finMes = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0, 12);
  let habil = mas(1); while ([0, 6].includes(habil.getDay())) habil = new Date(habil.getTime() + 864e5);
  return { hoy: f(hoy), manana: f(mas(1)), en30: f(mas(30)), finMes: f(finMes), habil: f(habil) };
}

// ---------------------------------------------------------------------- los pasos
const TUT_PASOS = [
  {
    titulo: "Del objeto al caso",
    texto: ["En ", h("b", null, "Explorar"), " elegí el objeto, completá la entrada y ejecutalo (termina con rollback: no graba nada). Si la salida es la correcta, ",
      h("b", null, "Guardar como caso…"), " la deja aprobada en una suite: de ahora en más el caso compara contra ella."],
    escena: () => tutVentana("Explorar",
      h("div", { class: "tut-cols" },
        h("div", { class: "tut-lista" }, ["Cupones.CambiarEstado", "Cupones.Cerrar", "Cupones.Cuotas.Eliminar"].map((o, i) =>
          h("div", { class: "tut-item", "data-t": `obj${i}` }, o))),
        h("div", { class: "tut-panel" },
          tutCampo("CuponId", "0", "cupon", { combo: false }),
          h("div", { class: "tut-fila" }, tutBoton("▶ Ejecutar", "ejecutar", "prim"), tutBoton("Generar validaciones…", "gen"), tutBoton("Guardar como caso…", "guardar")),
          h("div", { class: "tut-salida tut-oculto", "data-t": "salida" },
            h("div", { class: "tut-linea" }, h("span", { class: "pill ok" }, "OK"), h("span", { class: "muted" }, " · transacción: rollback")),
            tutLinea("Ok", "false", "", "bool"), tutLinea("Texto", "\"El cupón no se encuentra en estado EN_PROCESO.\"", "")))),
      tutModal("modal", "Guardar como caso de prueba",
        h("div", { class: "tut-form" }, h("label", null, "Suite"), h("span", { class: "tut-input", "data-t": "suite" }, "Elegí una suite…"),
          h("label", null, "Nombre del caso"), h("span", { class: "tut-input", "data-t": "nombre" }, "Cerrar: "),
          h("label", null, "Siempre se cumple"), h("span", { class: "chico" }, "☑ termina con error (Ok = false)")),
        h("div", { class: "tut-fila fin" }, tutBoton("Guardar", "ok", "prim"))),
      tutAviso("aviso", "✔ Caso guardado en Cobranzas/cupones")),
    guion: [
      ["nota", "1. Elegí el objeto"], ["mover", "obj1"], ["clic"], ["clase", "obj1", "sel"],
      ["nota", "2. Completá la entrada"], ["mover", "cupon"], ["clic"], ["texto", "cupon", ""], ["escribir", "cupon", "5"],
      ["nota", "3. Ejecutá: al terminar se deshace todo"], ["mover", "ejecutar"], ["clic"], ["mostrar", "salida"], ["esperar", 900],
      ["nota", "4. ¿Es lo esperado? Guardalo como caso"], ["mover", "guardar"], ["clic"], ["mostrar", "modal"],
      ["mover", "suite"], ["clic"], ["texto", "suite", "➕ Nueva suite: Cupones"],
      ["mover", "nombre"], ["clic"], ["escribir", "nombre", "cupón pendiente no se cierra"],
      ["mover", "ok"], ["clic"], ["ocultar", "modal"], ["mostrar", "aviso"], ["nota", "La salida queda aprobada y el caso, en la suite"],
    ],
  },
  {
    titulo: "Un id que no existe",
    texto: ["En el combo ", h("b", null, "▾"), " de un campo que es clave de una tabla, arriba de todo (en cursiva) está ", h("b", null, "Con filtros…"),
      ": arma un ", h("b", null, "valor dinámico"), ", que se calcula al ejecutar. «Uno que no existe» es ", h("code", null, "${siguiente.CuponId}"),
      ", el último + 1: un cupón que no existe hoy, y tampoco cuando la base crezca. Elegí la variable, no el número."],
    codigo: '"CuponId": "${siguiente.CuponId}"',
    escena: () => tutVentana("Explorar", h("div", { class: "tut-panel" },
      tutCampo("CuponEstado", "PAG", "estado", { combo: false }),
      tutCampo("CuponId", "0", "cupon", { desc: "no existe: el último + 1" }),
      tutMenu("menu", "cbhCupon · CuponId", [
        ["Con filtros…", "el primero, el último, uno que no existe o uno que cumpla condiciones", { dinamica: true, t: "filtros" }],
        ["1", "LIQ"], ["2", "LIQ"], ["3", "LIQ"]], { top: "92px", left: "120px" }),
      tutModal("armador", "Valor calculado · CuponId (cbhCupon)",
        h("div", { class: "tut-form" }, h("label", null, "Cuál"), h("span", { class: "tut-input", "data-t": "cual" }, "El primero que existe ▾")),
        h("div", { class: "tut-fila" }, h("code", { "data-t": "expr" }, "${existente.CuponId}")),
        h("div", { class: "chico", "data-t": "hoy" }, "Hoy daría 1"),
        h("div", { class: "tut-fila fin" }, tutBoton("Usar", "usar", "prim"))))),
    guion: [
      ["nota", "Abrí el combo del campo (o Alt+↓)"], ["mover", "cupon-d"], ["clic"], ["mostrar", "menu"], ["esperar", 700],
      ["nota", "Arriba, Con filtros… arma los valores que se calculan al ejecutar"], ["mover", "filtros"], ["foco", "filtros"],
      ["clic"], ["ocultar", "menu"], ["mostrar", "armador"],
      ["mover", "cual"], ["clic"], ["texto", "cual", "Uno que no existe ▾"], ["texto", "expr", "${siguiente.CuponId}"], ["texto", "hoy", "Hoy daría 60"],
      ["mover", "usar"], ["clic"], ["ocultar", "armador"],
      ["texto", "cupon", "${siguiente.CuponId}"], ["clase", "cupon", "var"], ["mostrar", "cupon-desc"],
      ["nota", "Hoy da 60; cuando exista el 60, dará 61. El caso sigue sirviendo."], ["esperar", 1800],
    ],
  },
  {
    titulo: "Un registro que cumpla una condición",
    texto: ["¿Necesitás el último cupón ", h("b", null, "pendiente"), "? En el combo, ", h("b", null, "Con filtros…"), " (o el botón ", h("b", null, "ƒ"), " del campo) abre el armador: elegís ",
      h("b", null, "cuál"), " (el primero, el último, con o sin filas en otra tabla) y los filtros, con los dominios de la tabla en un combo. Muestra lo que daría hoy y escribe la variable por vos. ",
      "Con ", h("b", null, "+ condición en otra tabla…"), " filtrás por tablas relacionadas (una cuota que esté en un cupón en proceso) y, si la clave es compuesta, completa las otras partes con la misma fila. También completa los otros campos que salen de ahí (el CuponId del cupón en proceso de esa cuota). ",
      "Con ƒ sobre una variable ya escrita, la abre para cambiarla."],
    codigo: ['"CuponId": "${ultimo.CuponId|CuponEstado=PENDIENTE}"', '"CuponId": "${existente.CuponId|CuponEstado=PENDIENTE,CuponFechaVencimiento<=${hoy+30}}"',
      '"CargoCuotaNumero": "${existente.CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}"'].join("\n"),
    escena: () => tutVentana("Explorar", h("div", { class: "tut-panel" },
      tutCampo("CuponId", "0", "cupon", { desc: "el último con CuponEstado = PENDIENTE" }),
      tutMenu("menu", "cbhCupon · CuponId", [
        ["Con filtros…", "el primero, el último, uno que no existe o uno que cumpla condiciones", { dinamica: true, t: "filtros" }],
        ["1", "LIQ"], ["2", "LIQ"]], { top: "40px", left: "120px" }),
      tutModal("armador", "Valor calculado · CuponId (cbhCupon)",
        h("div", { class: "tut-form" },
          h("label", null, "Cuál"), h("span", { class: "tut-input", "data-t": "cual" }, "El primero que existe ▾"),
          h("label", null, "CuponEstado ="), h("span", { class: "tut-input", "data-t": "estado" }, "(cualquiera) ▾"),
          h("label", null, "CuponTipo ="), h("span", { class: "tut-input" }, "(cualquiera) ▾")),
        h("div", { class: "tut-fila" }, h("code", { "data-t": "expr" }, "${existente.CuponId}")),
        h("div", { class: "chico", "data-t": "hoy" }, "Hoy daría 1"),
        h("div", { class: "tut-fila fin" }, tutBoton("Usar", "usar", "prim"))))),
    guion: [
      ["mover", "cupon-d"], ["clic"], ["mostrar", "menu"],
      ["nota", "Con filtros… abre el armador"], ["mover", "filtros"], ["foco", "filtros"], ["clic"], ["ocultar", "menu"], ["mostrar", "armador"],
      ["nota", "Los dominios de la tabla, en un combo"], ["mover", "estado"], ["clic"], ["texto", "estado", "PENDIENTE · Pendiente ▾"],
      ["texto", "expr", "${existente.CuponId|CuponEstado=PENDIENTE}"], ["texto", "hoy", "Hoy daría 4"],
      ["nota", "El primero o el último"], ["mover", "cual"], ["clic"], ["texto", "cual", "El último que existe ▾"],
      ["texto", "expr", "${ultimo.CuponId|CuponEstado=PENDIENTE}"], ["texto", "hoy", "Hoy daría 57"],
      ["mover", "usar"], ["clic"], ["ocultar", "armador"],
      ["texto", "cupon", "${ultimo.CuponId|CuponEstado=PENDIENTE}"], ["clase", "cupon", "var"], ["mostrar", "cupon-desc"],
      ["nota", "Se busca de nuevo en cada ejecución; si no hay ninguno, el paso lo dice"], ["esperar", 1800],
    ],
  },
  {
    titulo: "Fechas relativas",
    texto: ["En un campo de fecha, el combo ofrece fechas que se calculan al ejecutar: ", h("code", null, "${hoy}"), ", ", h("code", null, "${hoy+30}"), ", ",
      h("code", null, "${fin_mes}"), ", ", h("code", null, "${habil_siguiente}"), "… A mano: ", h("code", null, "+N"), " días, ", h("code", null, "m"), " meses, ",
      h("code", null, "a"), " años (", h("code", null, "${hoy-1a}"), "). En una consulta SQL van entre comillas simples: ", h("code", null, "'${fin_mes}'"), "."],
    codigo: '"FechaDesde": "${hoy}",\n"FechaHasta": "${hoy+30}"',
    escena: () => {
      const f = tutFechas();
      return tutVentana("Explorar", h("div", { class: "tut-panel" },
        tutCampo("FechaDesde", "", "desde"),
        tutCampo("FechaHasta", "", "hasta"),
        tutMenu("menu", "Fechas relativas (se calculan al ejecutar)", [
          ["${hoy}", `${f.hoy} · hoy`, { dinamica: true, t: "hoy" }],
          ["${hoy+1}", `${f.manana} · mañana`, { dinamica: true }],
          ["${hoy+30}", `${f.en30} · dentro de 30 días`, { dinamica: true }],
          ["${fin_mes}", `${f.finMes} · último día del mes`, { dinamica: true }],
          ["${habil_siguiente}", `${f.habil} · próximo día hábil`, { dinamica: true }],
          ["${fecha_vacia}", "vacía · fecha vacía", { dinamica: true }]], { top: "34px", left: "120px" }),
        h("div", { class: "tut-nota-fija tut-oculto", "data-t": "valores" }, `Al ejecutar hoy: ${f.hoy} y ${f.en30}`)));
    },
    guion: [
      ["nota", "El combo de un campo de fecha"], ["mover", "desde-d"], ["clic"], ["mostrar", "menu"], ["esperar", 500],
      ["mover", "hoy"], ["foco", "hoy"], ["clic"], ["ocultar", "menu"], ["texto", "desde", "${hoy}"], ["clase", "desde", "var"],
      ["nota", "O escribí la que necesites"], ["mover", "hasta"], ["clic"], ["escribir", "hasta", "${hoy+30}"], ["clase", "hasta", "var"],
      ["mostrar", "valores"], ["nota", "Mañana van a dar un día más: el caso no queda viejo"], ["esperar", 1800],
    ],
  },
  {
    titulo: "Verificá lo que el caso prueba",
    texto: ["La salida aprobada controla todo, pero conviene decir qué es ", h("b", null, "lo importante"), ": hacé clic en un valor de la salida → ",
      h("b", null, "Agregar verificación"), ". Las verificaciones siguen valiendo aunque después aceptes otra salida. Si la salida tiene ",
      h("code", null, "Ok"), " y mensajes, verificá también el código (o el texto) del mensaje."],
    codigo: '"verificaciones": [\n  { "ruta": "outCerrar.OutPut.Ok", "op": "igual", "valor": false },\n  { "ruta": "outCerrar.OutPut.Messages[0].Texto", "op": "contiene", "valor": "no existe" }\n]',
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-sub" }, "Paso «Cerrar» · Qué controla"),
      h("div", { class: "tut-controles" }, h("div", null, "✔ Salida aprobada (toda la salida)"),
        h("div", { class: "tut-oculto", "data-t": "v1" }, "✔ outCerrar.OutPut.Ok igual false"),
        h("div", { class: "tut-oculto", "data-t": "v2" }, "✔ outCerrar.OutPut.Messages[0].Texto contiene \"no existe\"")),
      h("div", { class: "tut-salida" },
        h("div", { class: "tut-linea" }, h("span", { class: "tut-k" }, "▾ OutPut")),
        tutLinea("Ok", "false", "ok", "bool"),
        h("div", { class: "tut-linea", style: { paddingLeft: "14px" } }, h("span", { class: "tut-k" }, "▾ Messages[0]")),
        tutLinea("Texto", "\"El cupón no existe o no se encuentra en estado EN_PROCESO.\"", "txt", "texto", 2)),
      h("div", { class: "tut-pop tut-oculto", "data-t": "pop", style: { top: "136px", left: "150px" } },
        h("div", { class: "tut-op", "data-t": "agregar" }, "✔ Agregar verificación: Ok igual false"),
        h("div", { class: "tut-op" }, "→ Guardar como variable"), h("div", { class: "tut-op" }, "No comparar este campo")),
      h("div", { class: "tut-pop tut-oculto", "data-t": "pop2", style: { top: "182px", left: "190px" } },
        h("div", { class: "tut-op", "data-t": "agregar2" }, "✔ Agregar verificación: Texto contiene \"no existe\""),
        h("div", { class: "tut-op" }, "→ Guardar como variable")))),
    guion: [
      ["nota", "Clic en el valor que importa"], ["mover", "ok"], ["clic"], ["mostrar", "pop"], ["mover", "agregar"], ["foco", "agregar"], ["clic"],
      ["ocultar", "pop"], ["mostrar", "v1"], ["clase", "ok", "marcado"],
      ["nota", "Y el motivo: el código o el texto del mensaje"], ["mover", "txt"], ["clic"], ["mostrar", "pop2"], ["mover", "agregar2"], ["clic"],
      ["ocultar", "pop2"], ["mostrar", "v2"], ["clase", "txt", "marcado"],
      ["nota", "Ahora el caso dice qué prueba"], ["esperar", 1600],
    ],
  },
  {
    titulo: "Pasá un valor al paso siguiente",
    texto: ["Un alta devuelve un id nuevo que no conocés de antemano. Clic en el valor → ", h("b", null, "Guardar como variable"), " y usalo en los pasos siguientes como ",
      h("code", null, "${cupon}"), ": por ejemplo, en una consulta que verifica que quedó grabado. También podés usar lo que se le mandó a un paso: ",
      h("code", null, "${alta.entrada.inAlta.Importe}"), "."],
    codigo: '{ "nombre": "Alta", ..., "guardar": { "cupon": "outAlta.CuponId" } },\n{ "nombre": "Quedó grabado", "sql": "select CuponEstado from cbhCupon where CuponId = ${cupon}" }',
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-sub" }, "Paso 1 · Alta"),
      h("div", { class: "tut-salida" }, h("div", { class: "tut-linea" }, h("span", { class: "tut-k" }, "▾ outAlta")),
        tutLinea("CuponId", "61", "id", "num"), h("span", { class: "pill acento tut-oculto", "data-t": "guarda" }, "→ ${cupon}")),
      h("div", { class: "tut-pop tut-oculto", "data-t": "pop", style: { top: "78px", left: "130px" } },
        h("div", { class: "tut-op" }, "✔ Agregar verificación"),
        h("div", { class: "tut-op", "data-t": "guardar" }, "→ Guardar como variable")),
      h("div", { class: "tut-pop tut-oculto", "data-t": "nombre-pop", style: { top: "78px", left: "130px" } },
        h("div", { class: "chico muted" }, "Nombre de la variable"), h("span", { class: "tut-input", "data-t": "nombre" }, "")),
      h("div", { class: "tut-sub", style: { marginTop: "14px" } }, "Paso 2 · Quedó grabado (SQL)"),
      h("div", { class: "tut-sql", "data-t": "sql" }, ""),
      h("div", { class: "chico tut-oculto", "data-t": "res", style: { color: "var(--ok)" } }, "✔ filas[0].CuponEstado igual \"PEN\"  (CuponId = 61)"))),
    guion: [
      ["nota", "Clic en el id que devolvió el alta"], ["mover", "id"], ["clic"], ["mostrar", "pop"], ["mover", "guardar"], ["clic"], ["ocultar", "pop"],
      ["mostrar", "nombre-pop"], ["escribir", "nombre", "cupon"], ["esperar", 300], ["ocultar", "nombre-pop"], ["mostrar", "guarda"],
      ["nota", "Usala en el paso siguiente"], ["mover", "sql"], ["clic"],
      ["escribir", "sql", "select CuponEstado from cbhCupon where CuponId = ${cupon}"],
      ["mostrar", "res"], ["nota", "En cada corrida, ${cupon} es el id que acaba de crear"], ["esperar", 1600],
    ],
  },
  {
    titulo: "Generá las validaciones",
    texto: ["Con una entrada que termina bien, ", h("b", null, "Generar validaciones…"), " propone una fila por cada campo vacío, cada valor del dominio y cada id que no existe, y muestra qué devuelve ",
      h("b", null, "hoy"), " cada una. Si algo que debería fallar se acepta (⚠), poné «falla»: el caso va a fallar hasta que se arregle el objeto."],
    escena: () => tutVentana("Explorar", h("div", { class: "tut-panel" },
      tutCampo("CuponEstado", "PAG", "e", { combo: false }), tutCampo("CuponId", "5", "c", { combo: false }),
      h("div", { class: "tut-fila" }, tutBoton("▶ Ejecutar", "", "prim"), tutBoton("Generar validaciones…", "gen"))),
    tutModal("modal", "Validaciones de CambiarEstado",
      h("table", { class: "tut-tabla" },
        h("tr", null, ["", "Prueba", "Hoy", "Se espera"].map((x) => h("th", null, x))),
        [["☑", "entrada valida", "ok", "termina bien"], ["☐", "CuponEstado vacio", "ok", "termina bien", "⚠ lo acepta"],
          ["☑", "CuponEstado = EN_PROCESO", "falla", "falla"], ["☑", "CuponId que no existe", "falla", "falla"]].map(([c, p, hoy, esp, aviso], i) =>
          h("tr", { class: "tut-oculto", "data-t": `r${i}` },
            h("td", { "data-t": `chk${i}` }, c), h("td", null, p, aviso ? h("div", { class: "chico", style: { color: "var(--aviso)" } }, aviso) : null),
            h("td", null, h("span", { class: `pill ${hoy}` }, hoy === "ok" ? "Ok" : "falla")),
            h("td", null, h("span", { class: "tut-input chico", "data-t": `esp${i}` }, esp, " ▾"))))),
      h("div", { class: "tut-fila fin" }, tutBoton("Guardar caso", "guardar", "prim"))),
    tutAviso("aviso", "✔ Caso con 4 filas guardado en Cobranzas/cupones")),
    guion: [
      ["nota", "Partí de una entrada que termina bien"], ["mover", "gen"], ["clic"], ["mostrar", "modal"],
      ["nota", "Cada fila se ejecuta con rollback"], ["mostrar", "r0"], ["mostrar", "r1"], ["mostrar", "r2"], ["mostrar", "r3"], ["esperar", 500],
      ["nota", "Esta acepta un estado vacío: ¿es un bug?"], ["foco", "r1"], ["mover", "chk1"], ["clic"], ["texto", "chk1", "☑"],
      ["mover", "esp1"], ["clic"], ["texto", "esp1", "falla ▾"], ["clase", "esp1", "var"],
      ["nota", "Se guarda como un caso con una fila por prueba"], ["mover", "guardar"], ["clic"], ["ocultar", "modal"], ["mostrar", "aviso"], ["esperar", 1400],
    ],
  },
  {
    titulo: "Una fila por regla: datos",
    texto: ["Para la misma prueba con varias entradas, usá ", h("code", null, "datos"), " (con ", h("b", null, "✎ Editar"), " del caso): el caso corre una vez por fila y cada columna es una variable. ",
      "Una columna puede tener un valor dinámico. Las verificaciones también usan las columnas: ", h("code", null, '"valor": "${ok}"'), "."],
    codigo: '"datos": [\n  { "prueba": "pasa a pagado",       "cupon": "${existente.CuponId|CuponEstado=PENDIENTE}", "estado": "PAG", "ok": true },\n  { "prueba": "cupón que no existe", "cupon": "${siguiente.CuponId}", "estado": "PAG", "ok": false }\n],\n"entrada": { "inCambiarEstado": { "CuponId": "${cupon}", "CuponEstado": "${estado}" } }',
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-fila" }, tutBoton("▶ Correr todo", "correr", "prim"), h("span", { class: "muted chico" }, "Cambiar estado: una fila por regla"), h("span", { class: "pill acento" }, "4 filas de datos")),
      h("table", { class: "tut-tabla" },
        h("tr", null, ["", "prueba", "cupon", "estado", "ok"].map((x) => h("th", null, x))),
        [["pasa a pagado", "${existente.CuponId|CuponEstado=PENDIENTE}", "PAG", "true"], ["en proceso no se permite", "${existente.CuponId|CuponEstado=PENDIENTE}", "PRO", "false"],
          ["ya está pendiente", "${existente.CuponId|CuponEstado=PENDIENTE}", "PEN", "false"], ["cupón que no existe", "${siguiente.CuponId}", "PAG", "false"]].map((f, i) =>
          h("tr", { class: "tut-oculto", "data-t": `f${i}` }, h("td", null, h("span", { class: "punto-estado", "data-t": `p${i}` })),
            f.map((x, j) => h("td", { class: j ? "mono" : "" }, x))))),
      h("div", { class: "tut-sql", "data-t": "entrada" }, '"entrada": { "inCambiarEstado": { "CuponId": "${cupon}", "CuponEstado": "${estado}" } }'))),
    guion: [
      ["nota", "Cada fila es una corrida del caso"], ["mostrar", "f0"], ["mostrar", "f1"], ["mostrar", "f2"], ["mostrar", "f3"],
      ["nota", "Cada columna es una variable de la entrada"], ["mover", "entrada"], ["foco", "entrada"],
      ["nota", "Corré: una vez por fila"], ["mover", "correr"], ["clic"],
      ["clase", "p0", "ok"], ["esperar", 250], ["clase", "p1", "ok"], ["esperar", 250], ["clase", "p2", "ok"], ["esperar", 250], ["clase", "p3", "ok"],
      ["nota", "4 reglas probadas con un solo caso"], ["esperar", 1600],
    ],
  },
  {
    titulo: "Siempre la misma base: script previo",
    texto: ["Si las salidas dependen de los datos que haya, en ", h("b", null, "Más → Opciones"), " escribí un ", h("b", null, "script previo"), " que deje la base como la necesitás. ",
      "Corre una vez, cada caso arranca de ahí y al final se deshace todo, el script incluido. Usá ", h("code", null, "delete from"), " (nunca ", h("code", null, "truncate"), "). ",
      "Dejá «Cada caso arranca de cero» salvo que un caso necesite lo que hizo el anterior."],
    codigo: '"scriptPrevio": [ { "ds": "COBRANZAS", "sql": "delete from cbhCuponDetalle; delete from cbhCupon;" } ]',
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-fila" }, h("b", null, "Cupones"), h("span", { class: "espacio" }), tutBoton("+ Caso", ""), tutBoton("Más ▾", "mas")),
      h("div", { class: "tut-franja tut-oculto", "data-t": "franja" }, "Script previo · COBRANZAS · 2 sentencias · cada caso arranca de cero"),
      tutMenu("menu", "", [["Opciones, script previo, variables y preparación…", "", { t: "opciones" }], ["Editar JSON completo…", ""], ["Duplicar suite", ""]], { top: "40px", right: "14px" })),
    tutModal("modal", "Opciones de la suite",
      h("div", { class: "tut-form" }, h("label", null, "Script previo"), h("div", { class: "tut-sql alto", "data-t": "script" }, ""),
        h("label", null, "Entre un caso y otro"), h("span", { class: "tut-input", "data-t": "modo" }, "Cada caso arranca de cero (recomendado)")),
      h("div", { class: "tut-fila fin" }, tutBoton("Guardar", "ok", "prim")))),
    guion: [
      ["nota", "Más → Opciones"], ["mover", "mas"], ["clic"], ["mostrar", "menu"], ["mover", "opciones"], ["clic"], ["ocultar", "menu"], ["mostrar", "modal"],
      ["nota", "Dejá la base vacía (o como la necesites)"], ["mover", "script"], ["clic"],
      ["escribir", "script", "delete from cbhCuponDetalle;\ndelete from cbhCupon;"],
      ["foco", "modo"], ["mover", "ok"], ["clic"], ["ocultar", "modal"], ["mostrar", "franja"],
      ["nota", "Cada caso carga lo que necesita: las salidas no dependen de la base"], ["esperar", 1600],
    ],
  },
  {
    titulo: "Corré y decidí",
    texto: [h("b", null, "▶ Correr todo"), " después de cada build (o dejá que corra solo). Si un caso falla, abrilo: ", h("b", null, "Qué cambió"), " muestra la diferencia. ",
      "Si el cambio es correcto, ", h("b", null, "Sí: aceptar esta salida"), "; si es un campo que cambia y no importa, ", h("b", null, "No comparar"), ". Si es un error, arreglá el objeto: no aceptes la salida."],
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-fila" }, tutBoton("▶ Correr todo", "correr", "prim"), tutBoton("▶ Correr fallidos", "")),
      h("table", { class: "tut-tabla" },
        [["Cerrar un cupón que no existe", "ok"], ["Pagar un cupón pendiente", "ok"], ["Importe del cupón", "falla"]].map(([n], i) =>
          h("tr", { "data-t": `c${i}` }, h("td", { style: { width: "86px" } }, h("span", { class: "punto-estado", "data-t": `p${i}` }), " ", h("span", { class: "chico muted", "data-t": `e${i}` }, "sin correr")),
            h("td", null, h("b", null, n), h("div", { class: "chico tut-oculto", "data-t": `m${i}`, style: { color: "var(--falla)" } }, "1 cambio en la salida"))))),
      h("div", { class: "tut-cambio tut-oculto", "data-t": "cambio" },
        h("div", null, h("b", null, "Qué cambió: "), h("span", { class: "mono" }, "outGet.Cupon.Importe"), "  ", h("span", { class: "mono", style: { color: "var(--falla)" } }, "100"), " → ",
          h("span", { class: "mono", style: { color: "var(--ok)" } }, "110")),
        h("div", { class: "tut-fila" }, tutBoton("Sí: aceptar esta salida", "aceptar", "prim"), tutBoton("No comparar", ""))))),
    guion: [
      ["nota", "Después de compilar, corré la suite"], ["mover", "correr"], ["clic"],
      ["clase", "p0", "ok"], ["texto", "e0", "OK"], ["esperar", 250], ["clase", "p1", "ok"], ["texto", "e1", "OK"], ["esperar", 250],
      ["clase", "p2", "falla"], ["texto", "e2", "Falla"], ["mostrar", "m2"],
      ["nota", "Abrí el que falló"], ["mover", "c2"], ["clic"], ["mostrar", "cambio"], ["esperar", 600],
      ["nota", "¿El importe nuevo es el correcto? Aceptalo"], ["mover", "aceptar"], ["foco", "aceptar"], ["clic"],
      ["ocultar", "cambio"], ["quitar", "p2", "falla"], ["clase", "p2", "ok"], ["texto", "e2", "OK"], ["ocultar", "m2"],
      ["nota", "Si fuera un error: arreglá el objeto, compilá y volvé a correr"], ["esperar", 1600],
    ],
  },
  {
    titulo: "Qué queda guardado al aprobar",
    texto: ["Si el objeto ", h("b", null, "devuelve"), " el valor de una variable dinámica (el ", h("code", null, "CuponId"), " que recibió, una fecha relativa), al aprobar se guarda la variable y no el número de ese día. ",
      "Se avisa qué campos quedaron así. Si el id vuelve en un campo con otro nombre (", h("code", null, "Id"), "), poné la variable a mano en la salida aprobada."],
    escena: () => tutVentana("Suites", h("div", { class: "tut-panel" },
      h("div", { class: "tut-sub" }, "Salida aprobada del paso «Cerrar»"),
      h("div", { class: "tut-salida mono" },
        h("div", null, "{"),
        h("div", { style: { paddingLeft: "14px" } }, "\"CuponId\": ", h("span", { class: "tut-v num", "data-t": "id" }, "60"), ","),
        h("div", { style: { paddingLeft: "14px" } }, "\"Texto\": \"No existe el cupón ", h("span", { class: "tut-v texto", "data-t": "txt" }, "60"), "\","),
        h("div", { style: { paddingLeft: "14px" } }, "\"Vence\": \"", h("span", { class: "tut-v texto", "data-t": "f" }, tutFechas().en30), "\","),
        h("div", { style: { paddingLeft: "14px" } }, "\"Importe\": ", h("span", { class: "tut-v num" }, "60")),
        h("div", null, "}")),
      h("div", { class: "chico tut-oculto", "data-t": "aviso", style: { marginTop: "8px" } },
        "✔ CuponId, Texto y Vence quedaron con la variable: se comparan contra lo que dé en cada corrida. ", h("span", { class: "muted" }, "Importe vale 60 por casualidad: no se toca.")))),
    guion: [
      ["nota", "La salida de hoy trae el 60 y la fecha de hoy + 30"], ["esperar", 1200],
      ["nota", "Al aprobar, donde está el valor de una variable…"], ["foco", "id"], ["texto", "id", "\"${siguiente.CuponId}\""], ["clase", "id", "var"],
      ["foco", "txt"], ["texto", "txt", "${siguiente.CuponId}"], ["clase", "txt", "var"],
      ["foco", "f"], ["texto", "f", "${hoy+30}"], ["clase", "f", "var"],
      ["mostrar", "aviso"], ["nota", "…queda la variable: el caso sigue pasando cuando la base crece"], ["esperar", 2200],
    ],
  },
];

// ---------------------------------------------------------------------- reproductor
function tutReproducir(lienzo, paso) {
  const reducido = matchMedia("(prefers-reduced-motion: reduce)").matches;
  let vivo = true, pausado = false;
  const esperar = async (ms) => {
    if (reducido) return;
    const fin = Date.now() + ms;
    while (vivo && (pausado || Date.now() < fin)) await new Promise((ok) => setTimeout(ok, Math.min(80, Math.max(0, fin - Date.now())) || 80));
  };
  const vuelta = async () => {
    const escena = paso.escena();
    const cursor = h("div", { class: "tut-cursor", html: TUT_CURSOR, style: reducido ? { display: "none" } : {} });
    const nota = h("div", { class: "tut-nota" });
    vaciar(lienzo, escena, cursor, nota);
    const q = (n) => escena.querySelector(tq(n));
    const centro = (e) => {
      const a = lienzo.getBoundingClientRect(), b = e.getBoundingClientRect();
      return [b.left - a.left + Math.min(b.width / 2, 60), b.top - a.top + b.height / 2];
    };
    // Arranca abajo a la derecha, sin la transición (si no, entra desde la esquina de arriba).
    cursor.style.transition = "none";
    cursor.style.transform = `translate(${lienzo.clientWidth - 40}px, ${lienzo.clientHeight - 50}px)`;
    void cursor.offsetWidth;
    cursor.style.transition = "";
    let pos = null;
    for (const [accion, a, b] of paso.guion) {
      if (!vivo) return;
      const e = typeof a === "string" ? q(a) : null;
      switch (accion) {
        case "nota": nota.textContent = a; nota.classList.add("ver"); break;
        case "mover": if (e) { pos = centro(e); cursor.style.transform = `translate(${pos[0]}px, ${pos[1]}px)`; await esperar(750); } break;
        case "clic":
          cursor.classList.add("clic");
          if (pos && !reducido) { const onda = h("div", { class: "tut-onda", style: { left: `${pos[0]}px`, top: `${pos[1]}px` } }); lienzo.appendChild(onda); setTimeout(() => onda.remove(), 600); }
          await esperar(220); cursor.classList.remove("clic"); await esperar(120); break;
        case "escribir":
          if (!e) break;
          e.classList.add("escribiendo");
          for (const ch of b) { if (!vivo) return; e.textContent += ch; await esperar(ch === "\n" ? 200 : 38); }
          e.classList.remove("escribiendo"); await esperar(250); break;
        case "texto": if (e) e.textContent = b; await esperar(200); break;
        case "mostrar": if (e) { e.classList.remove("tut-oculto"); e.classList.add("tut-aparece"); } await esperar(280); break;
        case "ocultar": if (e) e.classList.add("tut-oculto"); await esperar(120); break;
        case "clase": if (e) e.classList.add(b); await esperar(120); break;
        case "quitar": if (e) e.classList.remove(b); break;
        case "foco": if (e) { e.classList.add("tut-foco"); await esperar(900); e.classList.remove("tut-foco"); } break;
        case "esperar": await esperar(a); break;
      }
    }
    await esperar(1800);
  };
  (async () => { do { await vuelta(); } while (vivo && !reducido); })();
  return { parar() { vivo = false; }, pausar(p) { pausado = p; } };
}

// ---------------------------------------------------------------------- ventana del tutorial
/** Abre el tutorial (en el paso 'inicio', o donde quedó la última vez). */
function abrirTutorial(inicio) {
  almacen.guardar("tutorial.visto", true);
  $$(".tut-abrir").forEach((b) => b.classList.remove("nuevo"));
  let i = Math.min(Math.max(0, inicio ?? almacen.leer("tutorial.paso", 0)), TUT_PASOS.length - 1);
  let rep = null, pausado = false;
  const lienzo = h("div", { class: "tut-lienzo" });
  const titulo = h("h3", { class: "tut-titulo" });
  const texto = h("div", { class: "tut-texto" });
  const codigo = h("div");
  const indice = h("ol", { class: "tut-indice" });
  const contador = h("span", { class: "muted chico" });
  const btnPausa = h("button", { class: "btn chico", title: "Pausar o seguir la animación" }, "⏸ Pausa");
  const btnAnt = h("button", { class: "btn" }, "← Anterior");
  const btnSig = h("button", { class: "btn prim" }, "Siguiente →");
  const ir = (n) => {
    i = Math.min(Math.max(0, n), TUT_PASOS.length - 1);
    almacen.guardar("tutorial.paso", i);
    const p = TUT_PASOS[i];
    rep?.parar();
    titulo.textContent = `${i + 1}. ${p.titulo}`;
    vaciar(texto, p.texto);
    vaciar(codigo, p.codigo ? [h("div", { class: "muted chico", style: { margin: "8px 0 3px" } }, "Así queda en el caso:"), tutCodigo(p.codigo)] : null);
    vaciar(indice, TUT_PASOS.map((x, j) => h("li", { class: j === i ? "activo" : "", onclick: () => ir(j) }, x.titulo)));
    contador.textContent = `Paso ${i + 1} de ${TUT_PASOS.length}`;
    btnAnt.disabled = i === 0;
    btnSig.textContent = i === TUT_PASOS.length - 1 ? "Terminar" : "Siguiente →";
    pausado = false; btnPausa.textContent = "⏸ Pausa";
    rep = tutReproducir(lienzo, p);
  };
  btnPausa.addEventListener("click", () => { pausado = !pausado; rep?.pausar(pausado); btnPausa.textContent = pausado ? "▶ Seguir" : "⏸ Pausa"; });
  btnAnt.addEventListener("click", () => ir(i - 1));
  const teclas = (ev) => {
    if (ev.key === "ArrowRight") { ev.preventDefault(); if (i < TUT_PASOS.length - 1) ir(i + 1); }
    else if (ev.key === "ArrowLeft") { ev.preventDefault(); ir(i - 1); }
    else if (ev.key === " " && ev.target === document.body) { ev.preventDefault(); btnPausa.click(); }
  };
  const cuerpo = h("div", { class: "tut" },
    indice,
    h("div", { class: "tut-principal" },
      lienzo,
      titulo, texto, codigo,
      h("div", { class: "tut-pie" }, contador, btnPausa, h("span", { class: "espacio" }), btnAnt, btnSig)));
  const m = modal({
    titulo: "Tutorial: cómo armar pruebas que no dependen de la base", cuerpo, ancho: true,
    alCerrar: () => { rep?.parar(); document.removeEventListener("keydown", teclas); },
  });
  btnSig.addEventListener("click", () => (i === TUT_PASOS.length - 1 ? m.cerrar() : ir(i + 1)));
  document.addEventListener("keydown", teclas);
  ir(i);
}

/** El botón que abre el tutorial (cabecera de Suites, estados vacíos, Ayuda). Con un punto si nunca se abrió. */
function botonTutorial(texto = "🎓 Cómo armar pruebas", clase = "btn chico") {
  return h("button", { class: `${clase} tut-abrir ${almacen.leer("tutorial.visto", false) ? "" : "nuevo"}`, type: "button",
    title: "Tutorial animado: guardar casos, valores dinámicos, validaciones, datos, script previo y aprobar salidas", onclick: () => abrirTutorial() }, texto);
}
