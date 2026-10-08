/* GxPruebas - aplicacion */
"use strict";

const E = {
  kb: null,
  kbs: [],
  vista: "explorar",
  objetos: [],
  filtros: new Set(["Procedure", "DataProvider"]),
  obj: null,          // detalle del objeto seleccionado
  desc: null,         // describir (tipos y plantilla)
  campos: {},         // ayuda de los campos de la entrada (dominios enumerados y claves): /api/campos
  plan: null,         // plan de ejecucion del objeto seleccionado (/api/plan), o {cargando} / {error}
  entrada: {},
  modoEntrada: almacen.leer("modoEntrada", "form"),
  sqlDespues: [],
  sqlPrevio: [],      // SQL previo de Explorar ({ds, sql}), por KB: corre antes del objeto, como el script previo de una suite
  usarPrevio: false,
  transaccion: "rollback",
  ultimoRes: null,
  pendientes: [],     // verificaciones elegidas desde la salida: {paso, ruta, op, valor} o {paso, ignorar}
  historialSesion: [],
  suites: [],
  suite: null,
  resultados: {},     // casoId(fila) -> resultado de la corrida en curso o cargada
  trabajo: null,
  abiertos: new Set(),
  sinCorrer: new Set(), // casos a los que se les cambio lo que controlan despues de su ultimo resultado
  corridasCache: {},
  scriptCorrida: {},  // suite -> resultado del script previo en la última corrida de esta sesión
};

const slug = (t) => (t || "").trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^\w-]+/g, "-").replace(/^-+|-+$/g, "") || "suite";

// ====================================================================== inicio
async function iniciar() {
  try {
    const est = await GET("/api/estado");
    E.kbs = est.kbs;
  } catch (e) {
    toast(e.message, "error", 0);
    return;
  }
  const sel = $("#kb");
  vaciar(sel, E.kbs.map((k) => h("option", { value: k.nombre }, k.nombre)));
  E.kb = almacen.leer("kb", null);
  if (!E.kbs.some((k) => k.nombre === E.kb)) E.kb = E.kbs[0]?.nombre || null;
  sel.value = E.kb || "";
  sel.addEventListener("change", () => cambiarKb(sel.value));

  $$("#pestanas button").forEach((b) => b.addEventListener("click", () => irA(b.dataset.vista)));
  $("#buscar-objeto").addEventListener("input", pintarListaObjetos);
  $$("#filtros-objetos button").forEach((b) => b.addEventListener("click", () => {
    const f = b.dataset.f;
    E.filtros.has(f) ? E.filtros.delete(f) : E.filtros.add(f);
    b.classList.toggle("activa");
    pintarListaObjetos();
  }));
  $("#buscar-suite").addEventListener("input", pintarListaSuites);
  $("#suites-todas").addEventListener("change", cargarSuites);
  $("#nueva-suite").addEventListener("click", nuevaSuite);
  $("#tutorial-cab").replaceWith(botonTutorial());
  $("#tutorial-vacio").replaceWith(h("div", { style: { marginTop: "14px" } }, botonTutorial("🎓 Ver el tutorial: cómo armar pruebas", "btn")));
  $("#motor-reiniciar").addEventListener("click", () => accionMotor("reiniciar"));
  $("#motor-detener").addEventListener("click", () => accionMotor("detener"));
  $("#motor-log").addEventListener("click", verLogMotor);
  document.addEventListener("keydown", teclas);
  // Al volver de GeneXus: relee el catálogo para que aparezca lo recién especificado o compilado. La
  // Revisión se actualiza en segundo plano y solo si cambió algo (ver refrescarRevision).
  window.addEventListener("focus", () => { if (E.kb) cargarObjetos(); if (E.vista === "revision") refrescarRevision(); });

  if (!E.kb) {
    vaciar($("#detalle-objeto"), h("div", { class: "vacio-grande" }, h("h3", null, "No encontré KBs compiladas"),
      h("div", null, "Revisá 'raicesKB' en config.json. Se buscan carpetas con JavaModel\\web\\build\\classes.")));
    return;
  }
  await cambiarKb(E.kb, true);
  irA(almacen.leer("vista", "explorar"));
  abrirEnlace();
  window.addEventListener("hashchange", abrirEnlace);
  setInterval(() => { if (!document.hidden) refrescarMotor(); }, 2500);
  refrescarMotor();
}

// La notificación de Windows de una corrida automática abre la página con #corrida=<id>.
function abrirEnlace() {
  const enlace = location.hash.match(/^#corrida=(.+)$/);
  if (!enlace) return;
  history.replaceState(null, "", location.pathname);
  irA("historial");
  verCorrida(decodeURIComponent(enlace[1]));
}

async function cambiarKb(kb, inicial = false) {
  E.kb = kb;
  almacen.guardar("kb", kb);
  E.obj = null; E.suite = null; E.resultados = {}; E.firmaObjetos = null;
  vaciar($("#lista-objetos"), h("div", { class: "vacio" }, cargando("Leyendo la especificación…")));
  if (!inicial) {
    vaciar($("#detalle-objeto"), h("div", { class: "vacio-grande" }, h("h3", null, "Elegí un procedimiento o Data Provider")));
    vaciar($("#detalle-suite"), h("div", { class: "vacio-grande" }, h("h3", null, "Elegí una suite"),
      h("div", { style: { marginTop: "14px" } }, botonTutorial("🎓 Ver el tutorial: cómo armar pruebas", "btn"))));
  }
  await Promise.all([cargarObjetos(), cargarSuites()]);
  const ultimo = almacen.leer(`obj.${kb}`, null);
  if (ultimo && E.objetos.some((o) => o.nombre === ultimo) && inicial) seleccionarObjeto(ultimo);
  if (E.vista === "sql") pintarSql();
  if (E.vista === "historial") pintarHistorial();
  if (E.vista === "revision") pintarRevision();
  refrescarMotor();
}

function irA(vista) {
  E.vista = vista;
  almacen.guardar("vista", vista);
  $$("#pestanas button").forEach((b) => b.classList.toggle("activa", b.dataset.vista === vista));
  $$(".vista").forEach((v) => v.classList.toggle("activa", v.id === `vista-${vista}`));
  if (vista === "historial") pintarHistorial();
  if (vista === "sql") pintarSql();
  if (vista === "ayuda") pintarAyuda();
  if (vista === "suites") cargarSuites();
  if (vista === "grafo") abrirGrafo();
  if (vista === "revision") pintarRevision();
}

function teclas(ev) {
  const enCampo = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName);
  if (ev.key === "/" && !enCampo) {
    ev.preventDefault();
    (E.vista === "suites" ? $("#buscar-suite") : E.vista === "grafo" ? $("#grafo-buscar") : E.vista === "revision" ? $("#rv-buscar") : $("#buscar-objeto")).focus();
  }
  if ((ev.ctrlKey || ev.metaKey) && ev.key === "Enter") {
    if (E.vista === "explorar" && E.obj) { ev.preventDefault(); ejecutarObjeto(); }
    if (E.vista === "sql") { ev.preventDefault(); correrSql(); }
  }
}

// ====================================================================== motor
async function refrescarMotor() {
  let est;
  try { est = await GET("/api/estado"); } catch { $("#motor-texto").textContent = "sin conexión"; $("#motor").dataset.estado = "error"; return; }
  const m = est.motores.find((x) => x.kb === E.kb);
  const chip = $("#motor");
  const estado = m ? m.estado : "apagado";
  chip.dataset.estado = estado;
  let txt = { apagado: "motor apagado", iniciando: "iniciando motor…", listo: "motor listo", ocupado: "ejecutando…", error: "motor con error" }[estado] || estado;
  if (m?.recompilada) txt = "KB recompilada: se reinicia en el próximo pedido";
  const au = est.automatico;
  const auKb = au?.kbs?.[E.kb]?.estado;
  if (auKb === "build") txt = "build detectado: espera a que termine para probar…";
  if (auKb === "revisando") { txt = "revisando las buenas prácticas del build…"; chip.dataset.estado = "ocupado"; }
  if (auKb === "corriendo") { txt = "corriendo las pruebas del build…"; chip.dataset.estado = "ocupado"; }
  $("#motor-texto").textContent = txt;
  avisosBuild(au);
  const co = est.compartido || {}, chipCo = $("#compartido");
  chipCo.hidden = !co.activo;
  chipCo.dataset.estado = co.error ? "error" : "listo";
  $("#compartido-texto").textContent = co.error ? "base compartida: sin conexión" : "base compartida";
  chipCo.title = `${co.base || ""}\n\n${co.error ? co.error + "\nSe usa la copia local; no se puede grabar." : "Las suites y la configuración se leen y graban ahí."}`;
  chip.title = m ? `Motor de ${m.kb}\nestado: ${m.estado}${m.pid ? "\npid " + m.pid : ""}${m.msInicio ? "\narranque: " + fmtMs(m.msInicio) : ""}\npedidos: ${m.pedidos}${m.error ? "\n\n" + m.error : ""}` : "Motor Java de la KB (se inicia solo al ejecutar)";
}

// Corridas automáticas después de un build (gxp/automatico): un aviso por cada una que terminó desde
// la última consulta. La primera vez solo se toma el número, para no repetir avisos viejos al abrir la página.
function avisosBuild(au) {
  if (!au) return;
  if (E.autoSeq === undefined) { E.autoSeq = au.seq; return; }
  const nuevas = (au.ultimas || []).filter((r) => r.seq > E.autoSeq).reverse();
  E.autoSeq = au.seq;
  for (const r of nuevas) {
    const ok = r.estado === "ok";
    const nuevo = r.revision?.primeros?.[0];
    const cantNuevos = (r.revision?.nuevos?.error || 0) + (r.revision?.nuevos?.advertencia || 0);
    const t = toast(h("span", null, `${ok ? "✔" : "✖"} Build de ${r.kb}: `, h("b", null, r.texto),
      r.fallas?.length ? h("div", { class: "chico" }, `${r.fallas[0].suite} › ${r.fallas[0].caso}${r.fallas.length > 1 ? ` (y ${r.fallas.length - 1} más)` : ""}`) : null,
      nuevo ? h("div", { class: "chico" }, `Nuevo: ${nuevo.objeto}${nuevo.linea ? ` línea ${nuevo.linea}` : ""}: ${nuevo.mensaje}${cantNuevos > 1 ? ` (y ${cantNuevos - 1} más)` : ""}`) : null,
      r.corridaVer ? [" ", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); ev.stopPropagation(); t.remove(); irA("historial"); verCorrida(r.corridaVer); } }, "Ver")] : null,
      cantNuevos ? [" ", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); ev.stopPropagation(); t.remove(); if (r.kb !== E.kb) { $("#kb").value = r.kb; cambiarKb(r.kb); } RV.filtro = "nuevos"; RV.armada = false; irA("revision"); } }, "Ver revisión")] : null),
      ok ? "ok" : "error", ok ? 8000 : 0);
    if (E.vista === "historial") pintarHistorial();
    if (E.vista === "revision" && r.revision) cargarRevision(false, true);
    if (E.suite && r.corridas?.some((c) => c.suite === E.suite._id)) abrirSuite(E.suite._id);
  }
}

async function accionMotor(accion) {
  if (!E.kb) return;
  $("#motor").dataset.estado = accion === "detener" ? "apagado" : "iniciando";
  $("#motor-texto").textContent = accion === "detener" ? "deteniendo…" : "iniciando motor…";
  try {
    const r = await POST("/api/motor", { kb: E.kb, accion });
    toast(accion === "detener" ? "Motor detenido" : `Motor listo (${fmtMs(r.msInicio)})`, "ok");
  } catch (e) { toast(e.message, "error"); }
  refrescarMotor();
}

async function verLogMotor() {
  const pre = h("pre", { class: "bloque", style: { maxHeight: "60vh" } }, "Cargando…");
  const cargar = async () => {
    try { const r = await GET("/api/motor/log", { kb: E.kb, n: 600 }); pre.textContent = r.log || "(vacío)"; pre.scrollTop = pre.scrollHeight; }
    catch (e) { pre.textContent = e.message; }
  };
  modal({ titulo: `Log del motor · ${E.kb}`, ancho: true, cuerpo: pre, botones: [{ texto: "Actualizar", accion: () => { cargar(); return false; } }, { texto: "Cerrar", prim: true }] });
  cargar();
}

// ====================================================================== explorar
async function cargarObjetos() {
  const kb = E.kb;
  let lista;
  try {
    lista = await GET("/api/objetos", { kb });
  } catch (e) {
    E.objetos = []; E.firmaObjetos = null;
    vaciar($("#lista-objetos"), h("div", { class: "vacio" }, e.message));
    return;
  }
  if (kb !== E.kb) return; // se cambió de KB mientras llegaba
  // Al volver a la ventana se recarga: si no cambió nada, no se repinta (conserva el scroll).
  const firma = kb + "|" + JSON.stringify(lista);
  if (firma === E.firmaObjetos) return;
  E.objetos = lista; E.firmaObjetos = firma;
  pintarListaObjetos();
}

function recientes() { return almacen.leer(`recientes.${E.kb}`, []); }
function marcarReciente(nombre) {
  const r = recientes().filter((x) => x !== nombre);
  r.unshift(nombre);
  almacen.guardar(`recientes.${E.kb}`, r.slice(0, 30));
}

function pintarListaObjetos() {
  const q = $("#buscar-objeto").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const rec = recientes();
  let lista = E.objetos.filter((o) => {
    if (E.filtros.has("recientes") && !rec.includes(o.nombre)) return false;
    if (E.filtros.has("errores") && !o.errores) return false;
    const tipos = ["Procedure", "DataProvider"].filter((t) => E.filtros.has(t));
    if (tipos.length && !tipos.includes(o.tipo)) return false;
    const n = (o.nombre + " " + o.descripcion).toLowerCase();
    return q.every((p) => n.includes(p));
  });
  if (E.filtros.has("recientes")) lista.sort((a, b) => rec.indexOf(a.nombre) - rec.indexOf(b.nombre));
  const total = lista.length;
  lista = lista.slice(0, 400);
  const cont = $("#lista-objetos");
  vaciar(cont, lista.length ? lista.map((o) => h("div", {
    class: `item ${E.obj?.nombre === o.nombre ? "activo" : ""}`, title: o.nombre, onclick: () => seleccionarObjeto(o.nombre),
  }, h("div", { style: { flex: 1, minWidth: 0 } },
    h("div", { class: "t" }, corto(o.nombre), " ", o.tipo === "DataProvider" ? pill("DP", "acento") : null, o.errores ? pill("errores", "falla") : null),
    h("div", { class: "s" }, modulo(o.nombre) || "(raíz)", " · ", o.parametros.map((p) => `${p.io}:${p.nombre}`).join(", ") || "sin parámetros"))))
    : h("div", { class: "vacio" }, "No hay objetos que coincidan."),
  total > lista.length ? h("div", { class: "pie" }, `Mostrando 400 de ${total}. Afiná la búsqueda.`) : h("div", { class: "pie" }, `${total} objetos`));
}

async function seleccionarObjeto(nombre) {
  const det = $("#detalle-objeto");
  vaciar(det, h("div", { class: "vacio-grande" }, cargando(`Cargando ${nombre}…`)));
  E.desc = null; E.campos = {}; E.plan = null; E.ultimoRes = null; E.pendientes = []; E.sqlDespues = []; E.transaccion = "rollback";
  try {
    E.obj = await GET("/api/objeto", { kb: E.kb, nombre });
  } catch (e) {
    vaciar(det, h("div", { class: "error-caja" }, e.message));
    return;
  }
  almacen.guardar(`obj.${E.kb}`, E.obj.nombre);
  marcarReciente(E.obj.nombre);
  pintarListaObjetos();
  const borrador = almacen.leer(`entrada.${E.kb}.${E.obj.nombre}`, null);
  E.entrada = borrador || {};
  E.sqlDespues = almacen.leer(`sql.${E.kb}.${E.obj.nombre}`, []);
  E.sqlPrevio = almacen.leer(`sqlPrevio.${E.kb}`, []);
  E.usarPrevio = almacen.leer(`usarPrevio.${E.kb}`, false);
  pintarObjeto();
  // describir: arranca el motor si hace falta (la primera vez tarda unos segundos). La ayuda de los campos
  // (combos) sale de la especificacion: si falla, el formulario queda sin combos.
  try {
    const [d, campos] = await Promise.all([
      GET("/api/describir", { kb: E.kb, nombre: E.obj.nombre }),
      GET("/api/campos", { kb: E.kb, nombre: E.obj.nombre }).catch(() => ({})),
    ]);
    if (E.obj?.nombre !== nombre) return;
    E.desc = d;
    E.campos = campos;
    if (!borrador) E.entrada = clonar(d.plantillaEntrada);
    pintarObjeto();
  } catch (e) {
    if (E.obj?.nombre !== nombre) return;
    E.desc = { error: e.message };
    pintarObjeto();
  }
  refrescarMotor();
}

function guardarBorrador() {
  if (!E.obj) return;
  almacen.guardar(`entrada.${E.kb}.${E.obj.nombre}`, E.entrada);
  almacen.guardar(`sql.${E.kb}.${E.obj.nombre}`, E.sqlDespues);
  almacen.guardar(`sqlPrevio.${E.kb}`, E.sqlPrevio);
  almacen.guardar(`usarPrevio.${E.kb}`, E.usarPrevio);
}

function pintarObjeto() {
  const o = E.obj;
  const det = $("#detalle-objeto");
  const params = E.desc?.parametros || o.parametros;
  const cab = h("div", null,
    h("h2", { class: "titulo" }, o.nombre),
    h("div", { class: "subtitulo" },
      pill(o.tipo === "DataProvider" ? "Data Provider" : "Procedimiento", "acento"),
      o.descripcion && o.descripcion !== corto(o.nombre) ? h("span", null, o.descripcion) : null,
      o.errores ? pill(`${o.errores} error(es) de especificación`, "falla") : null,
      o.warnings ? pill(`${o.warnings} warning(s)`, "aviso") : null,
      o.haceCommit ? h("span", { class: "pill aviso", title: "El Java del objeto llama a commit: el rollback de GxPruebas no deshace sus cambios" }, "⚠ hace commit") : null,
      h("span", { class: "mono chico muted", title: o.fuenteJava, style: { cursor: "pointer" }, onclick: () => copiar(o.claseJava) }, o.claseJava)));

  const avisos = [];
  if (E.desc?.error) avisos.push(h("div", { class: "error-caja" }, "No se pudo preparar el objeto en el motor Java:\n" + E.desc.error));
  if (E.desc?.aviso) avisos.push(h("div", { class: "aviso-caja" }, "⚠ ", E.desc.aviso));
  if (o.errores) avisos.push(h("div", { class: "aviso-caja" }, "⚠ El objeto tiene errores de especificación: puede que el Java compilado no corresponda a la versión actual."));

  const tablaParams = h("table", { class: "tabla" },
    h("thead", null, h("tr", null, h("th", null, "#"), h("th", null, "Dirección"), h("th", null, "Parámetro"), h("th", null, "Tipo"))),
    h("tbody", null, params.length ? params.map((p, i) => h("tr", null,
      h("td", { class: "muted" }, i + 1), h("td", null, pill(p.io, `io-${p.io}`)),
      h("td", { class: "mono" }, (p.atributo ? "" : "&") + p.nombre),
      h("td", { class: "mono" }, p.tipoJava || (E.desc ? "?" : cargando(""))))) : h("tr", null, h("td", { colspan: 4, class: "muted" }, "Sin parámetros"))));

  const pests = subpestanas([
    { id: "ejecutar", texto: "Ejecutar", render: panelEjecutar },
    { id: "navegacion", texto: "Navegación", n: contarNiveles(o.niveles), render: panelNavegacion },
    { id: "mensajes", texto: "Mensajes", n: (o.warnings || 0) + (o.errores || 0), render: panelMensajes },
  ], almacen.leer("subpestanaObjeto", "ejecutar"));
  pests.querySelector(".subpestanas").addEventListener("click", (ev) => {
    const b = ev.target.closest("button"); if (!b) return;
    const ids = ["ejecutar", "navegacion", "mensajes"];
    const i = Array.from(b.parentNode.children).indexOf(b);
    almacen.guardar("subpestanaObjeto", ids[i]);
  });

  vaciar(det, cab, avisos,
    h("div", { class: "tarjeta" }, h("div", { class: "cab" }, h("h3", null, "Parámetros")), h("div", { class: "cuerpo", style: { padding: 0 } }, tablaParams)),
    pests);
}

// ---------------------------------------------------------------------- combos de la entrada
// La ayuda de /api/campos viene por ruta en minusculas y con [*] en las listas: inset.items[*].itfid
const rutaCampo = (ruta) => ruta.toLowerCase().replace(/\[\d+\]/g, "[*]");
const textosClave = new Map(); // "kb|atributo" -> Map(valor -> texto), de las consultas ya hechas

// Fechas relativas que se ofrecen en los campos de fecha (se calculan al ejecutar: ver gxp/suites/fechas.py).
const FECHAS_RELATIVAS = {
  date: [["hoy", "hoy"], ["hoy+1", "mañana"], ["hoy-1", "ayer"], ["hoy+30", "dentro de 30 días"], ["hoy-30", "hace 30 días"],
    ["hoy+1m", "dentro de un mes"], ["hoy-1a", "hace un año"], ["inicio_mes", "primer día del mes"], ["fin_mes", "último día del mes"],
    ["fin_mes+1", "último día del mes que viene"], ["inicio_anio", "primer día del año"], ["fin_anio", "último día del año"],
    ["habil_siguiente", "próximo día hábil (lunes a viernes)"], ["habil_anterior", "último día hábil"], ["fecha_vacia", "fecha vacía"]],
  dtime: [["ahora", "ahora"], ["ahora+1h", "dentro de una hora"], ["ahora-1h", "hace una hora"], ["ahora+1d", "mañana a esta hora"],
    ["ahora-1d", "ayer a esta hora"], ["fecha_vacia", "fecha vacía"]],
};

/** opciones.combo de formularioJson: valores del dominio enumerado; si el campo es la clave de una tabla, los
 *  que hay en la base (filtrados por los otros campos de la clave que esten en el mismo nivel) y las ${variables}
 *  que se calculan al ejecutar (${siguiente.X}, ${existente.X|...}); si es una fecha, las fechas relativas. */
function comboCampo(kb, ayudas) {
  return (ruta, padre, arriba) => {
    const a = ayudas?.[rutaCampo(ruta)];
    if (!a) return null;
    if (a.tipo === "date" || a.tipo === "dtime") {
      const textos = new Map(FECHAS_RELATIVAS[a.tipo].map(([e, t]) => [`\${${e}}`, t]));
      return {
        titulo: a.tipo === "date" ? "Fechas relativas (se calculan al ejecutar)" : "Fecha y hora relativas (se calculan al ejecutar)",
        textoDe: (x) => textos.get(String(x).trim()),
        cargar: async () => {
          const exprs = [...textos.keys()];
          const r = await POST("/api/variables/previsualizar", { kb, expresiones: exprs });
          return {
            valores: exprs.map((e, i) => ({ valor: e, texto: `${r[i].error ? "?" : r[i].hoy === "" ? "vacía" : r[i].hoy} · ${textos.get(e)}`, destacado: true })),
            nota: "También podés escribir otras: ${hoy+45}, ${hoy-2m}, ${fin_mes-1}, ${ahora+30min}.",
          };
        },
      };
    }
    if (a.valores) {
      const valores = a.valores.map((v) => {
        const texto = [v.descripcion, v.nombre].find((t) => t && t !== String(v.valor)) || "";
        return { valor: v.valor, texto };
      });
      return {
        titulo: `Dominio ${a.dominio || ""}`,
        valores,
        textoDe: (x) => valores.find((v) => String(v.valor) === String(x).trim())?.texto,
      };
    }
    const c = a.clave;
    const clave = `${kb}|${c.atributo}`;
    if (!textosClave.has(clave)) textosClave.set(clave, new Map());
    const textos = textosClave.get(clave);
    const armar = (actual, alElegir) => armarVariableClave(kb, c.atributo, padre, actual, alElegir, arriba ? arriba() : []);
    return {
      titulo: `${c.tabla}${c.titulo && c.titulo !== c.tabla ? ` (${c.titulo})` : ""} · ${c.atributo}`,
      ancho: 520,  // las ${existente.X|Atributo=VALOR} son largas
      textoDe: (x) => textos.get(String(x).trim()) || describirVariableClave(x),
      armar,
      cargar: async (buscar) => {
        const filtros = {};
        if (padre && !Array.isArray(padre)) for (const [k, v] of Object.entries(padre)) if (v === null || typeof v !== "object") filtros[k] = v;
        const r = await POST("/api/valoresClave", { kb, atributo: c.atributo, filtros, buscar });
        const n = r.claves.length;
        const otras = r.claves.slice(0, -1).map((k, i) => [k, i]).filter(([k]) => !(k in r.filtros));
        const valores = r.filas.map((f) => {
          const fila = r.columnas.map((col) => f[col]);
          const desc = r.descripcion ? String(fila[n] ?? "").trim() : "";
          const texto = [otras.map(([k, i]) => `${k}=${fila[i]}`).join(" "), desc].filter(Boolean).join(" · ");
          textos.set(String(fila[n - 1]).trim(), texto);
          return { valor: fila[n - 1], texto };
        });
        // Arriba, el armador de las ${variables} que se calculan al ejecutar (el primero, el ultimo, uno que no
        // existe, uno que cumpla condiciones): asi el caso sigue sirviendo aunque cambie la base.
        valores.unshift({ valor: "Con filtros…", texto: "el primero, el último, uno que no existe o uno que cumpla condiciones",
          destacado: true, accion: armar });
        const usados = Object.entries(r.filtros).map(([k, v]) => `${k} = ${v}`).join(", ");
        return { valores, truncado: r.truncado, nota: usados ? `Filtrado por ${usados}.` : "" };
      },
    };
  };
}

// ---------------------------------------------------------------------- armador de ${existente.X|...}
// Las ${variables} que se calculan en la base (gxp/campos/expresiones.py), armadas eligiendo en vez de escribiendo.
const FUNCIONES_CLAVE = [
  ["existente", "El primero que existe", "el de clave más chica"],
  ["ultimo", "El último que existe", "el de clave más grande: el último creado"],
  ["con_hijos", "El primero con filas en otra tabla", "su detalle, o una tabla que lo referencia"],
  ["sin_hijos", "El primero sin filas en otra tabla", "sin detalle, o sin nada que lo referencie"],
  ["siguiente", "Uno que no existe", "el último + 1, de toda la tabla"],
];
const OPERADORES_CONDICION = [["=", "="], ["!=", "≠"], [">", ">"], [">=", "≥"], ["<", "<"], ["<=", "≤"]];
const RE_CONDICION = /^\s*((?:!?\s*\w+\s*\.\s*)*)(\w+)\s*(<=|>=|!=|<>|=|<|>)\s*([\s\S]*?)\s*$/;
const RE_EXISTE = /^\s*((?:!?\s*\w+\s*\.\s*)*!?\s*\w+)\s*$/;  // solo el camino: que tenga alguna fila

/** 'A=1,B=${x|C=2,D=3}' -> ['A=1', 'B=${x|C=2,D=3}']: corta en las comas de afuera de las ${...}. */
function partirCondiciones(texto) {
  const partes = [];
  let prof = 0, actual = "";
  for (let i = 0; i < texto.length; i++) {
    const ch = texto[i];
    if (ch === "$" && texto[i + 1] === "{") prof++;
    else if (ch === "}" && prof) prof--;
    if (ch === "," && !prof) { partes.push(actual); actual = ""; } else actual += ch;
  }
  if (actual.trim()) partes.push(actual);
  return partes;
}

/** 'cbhCuponDetalle.!cbhCupon' -> {tablas: [...], negadas: [false, true]} */
function partirCamino(texto) {
  const seg = texto.split(".").map((x) => x.replace(/\s/g, "")).filter(Boolean);
  return { tablas: seg.map((x) => x.replace(/^!/, "")), negadas: seg.map((x) => x.startsWith("!")) };
}

/**
 * '${existente.CuponId:tabla|A=1,cbhX.!cbhY.B!=X,!cbhZ}' -> {funcion, tabla, atributo, hija, condiciones}, o null
 * ('tabla' en ${existente.cbhCargoCuota.CargoId}, el atributo de esa tabla; si no, ""). Cada
 * condicion es {atributo, op, valor, tablas, negadas}: 'tablas' es el camino a otra tabla (vacio: la misma) y un
 * atributo vacio, solo el camino (que tenga, o con !, que no tenga, alguna fila).
 */
function parsearVariableClave(texto) {
  const m = /^\s*\$\{\s*(siguiente|existente|ultimo|con_hijos|sin_hijos)\.(?:(\w+)\.)?(\w+)(?::(\w+))?\s*(?:\|([\s\S]*))?\}\s*$/.exec(String(texto ?? ""));
  if (!m) return null;
  const condiciones = [];
  for (const c of partirCondiciones(m[5] || "")) {
    const x = RE_CONDICION.exec(c);
    if (x) { condiciones.push({ atributo: x[2], op: x[3] === "<>" ? "!=" : x[3], valor: x[4], ...partirCamino(x[1]) }); continue; }
    const e = RE_EXISTE.exec(c);
    if (!e) return null;
    condiciones.push({ atributo: "", op: "=", valor: "", ...partirCamino(e[1]) });
  }
  return { funcion: m[1], tabla: m[2] || "", atributo: m[3], hija: m[4] || "", condiciones };
}

const textoCamino = (c) => c.tablas.map((t, i) => `${c.negadas[i] ? "!" : ""}${t}`).join(".");

/** Una condicion como se escribe, o "" si no filtra (sin valor en la misma tabla). En otra tabla, sin valor queda
 *  solo el camino: que tenga (o no) alguna fila. */
function textoCondicion(c) {
  const v = String(c.valor ?? "").trim();
  if (!c.tablas?.length) return v === "" ? "" : `${c.atributo}${c.op}${v}`;
  return c.atributo && v !== "" ? `${textoCamino(c)}.${c.atributo}${c.op}${v}` : textoCamino(c);
}

function escribirVariableClave({ funcion, atributo, hija, condiciones }) {
  const conds = funcion === "siguiente" ? [] : condiciones.map(textoCondicion).filter(Boolean);
  const tabla = hija && (funcion === "con_hijos" || funcion === "sin_hijos") ? `:${hija}` : "";
  return `\${${funcion}.${atributo}${tabla}${conds.length ? "|" + conds.join(",") : ""}}`;
}

/** Lo que pide la variable, en castellano: "el primero con CuponEstado = PENDIENTE y con cbhCupon: CuponEstado = EN_PROCESO". */
function describirVariableClave(texto) {
  const p = parsearVariableClave(texto);
  if (!p) return "";
  const que = { existente: "el primero", ultimo: "el último", siguiente: "no existe: el último + 1",
    con_hijos: `el primero con filas en ${p.hija || "otra tabla"}`, sin_hijos: `el primero sin filas en ${p.hija || "otra tabla"}` }[p.funcion]
    + (p.tabla ? ` de ${p.tabla}` : "");
  const op = (o) => OPERADORES_CONDICION.find(([x]) => x === o)?.[1] || o;
  // Las partes de la clave que puso el armador (CargoId=${...}, tambien por otra tabla: cbhCargoCuota.CargoId=${...},
  // en el CuponId que sale de la misma fila) van al final: «dentro de su CargoId».
  const esDentro = (c) => c.atributo && c.op === "=" && /^\s*\$\{/.test(c.valor);
  const dentro = [...new Set(p.condiciones.filter(esDentro).map((c) => c.atributo))];
  const conds = p.condiciones.filter((c) => !esDentro(c) && (!dentro.includes(c.atributo) || c.tablas.length)).map((c) => {
    const filtro = c.atributo ? `${c.atributo} ${op(c.op)} ${c.valor}` : "";
    if (!c.tablas.length) return filtro;
    const camino = c.tablas.map((t, i) => (i && c.negadas[i] ? `sin ${t}` : t)).join(" › ");
    return `${c.negadas[0] ? "sin" : "con"} ${camino}${filtro ? `: ${filtro}` : ""}`;
  });
  const frase = conds.length ? `${que} ${conds.map((c, i) => (i || /^(con|sin) /.test(c) ? c : `con ${c}`)).join(" y ")}` : que;
  const lista = dentro.length > 1 ? `${dentro.slice(0, -1).join(", ")} y ${dentro[dentro.length - 1]}` : dentro[0];
  return dentro.length ? `${frase} (dentro de su ${lista})` : frase;
}

/** Valor de 'atributo' en el objeto que contiene al campo (sin distinguir mayusculas), si sirve de condicion. */
function valorHermano(padre, atributo) {
  if (!padre || Array.isArray(padre)) return undefined;
  const k = Object.keys(padre).find((x) => x.toLowerCase() === atributo.toLowerCase());
  const v = k === undefined ? undefined : padre[k];
  if (v === null || v === undefined || typeof v === "object") return undefined;
  const t = String(v).trim();
  return t === "" || t === "0" ? undefined : t;
}
const tieneHermano = (padre, atributo) => !!padre && !Array.isArray(padre) && Object.keys(padre).some((x) => x.toLowerCase() === atributo.toLowerCase());

const atributosTablas = new Map(); // "kb|tabla" -> Promise de /api/campos/tabla
function atributosDeTabla(kb, tabla, datastore = "") {
  const k = `${kb}|${datastore}|${tabla.toLowerCase()}`;
  if (!atributosTablas.has(k)) {
    const p = GET("/api/campos/tabla", { kb, tabla, datastore });
    p.catch(() => atributosTablas.delete(k));
    atributosTablas.set(k, p);
  }
  return atributosTablas.get(k);
}

/**
 * Arma una ${funcion.Atributo|condiciones} eligiendo: cual (el primero, el ultimo, uno que no existe, con o sin
 * filas en otra tabla), condiciones sobre los atributos de la tabla (los de un dominio enumerado, en un combo) y
 * sobre las tablas relacionadas (una cuota que este en un cupon en proceso). Muestra lo que daria hoy.
 * 'actual' (la variable que ya tiene el campo) se abre para editarla. Si la clave es compuesta, las otras partes
 * se toman de los campos hermanos (CargoId para CargoCuotaNumero) o, con «misma fila», se completan tambien:
 * alElegir(texto, {CargoId: ${...}, CargoPlanSec: ${...}}). Los demas campos de la entrada (los de 'padre' y los
 * de los objetos de 'arriba') que salen de esa fila o de una tabla de las condiciones se completan tambien: el
 * CuponId de una cuota que esta en un cupon en proceso.
 */
async function armarVariableClave(kb, atributo, padre, actual, alElegir, arriba = []) {
  let f;
  try { f = await GET("/api/campos/filtros", { kb, atributo }); } catch (e) { toast(e.message, "error"); return; }
  const k = f.atributo;
  const propios = new Map(f.atributos.map((a) => [a.nombre.toLowerCase(), a]));
  const otras = new Map();  // tabla en minusculas -> Map(atributo -> info), de las relacionadas ya consultadas
  const cargarTabla = async (tabla) => {
    if (otras.has(tabla.toLowerCase())) return;
    const r = await atributosDeTabla(kb, tabla, f.datastore || "");
    otras.set(tabla.toLowerCase(), new Map(r.atributos.map((a) => [a.nombre.toLowerCase(), a])));
  };
  const atts = (c) => (c.tablas?.length ? otras.get(c.tablas[c.tablas.length - 1].toLowerCase()) : propios) || new Map();
  const att = (c) => atts(c).get(String(c.atributo).toLowerCase()) || { nombre: c.atributo, tipo: "" };

  // Las otras partes de la clave que estan en la entrada (CargoId y CargoPlanSec al lado de CargoCuotaNumero).
  const hermanos = f.claves.slice(0, -1).filter((c) => tieneHermano(padre, c));
  const fijos = hermanos.filter((c) => { const v = valorHermano(padre, c); return v !== undefined && !v.startsWith("${"); });
  const previo = parsearVariableClave(actual);
  const esPropia = (x) => x && !x.tabla && x.atributo.toLowerCase() === k.toLowerCase();  // no ${existente.cbhCargoCuota.CargoId}
  const est = esPropia(previo)
    ? { ...previo, atributo: k } : { funcion: "existente", atributo: k, hija: "", condiciones: [] };
  if (!f.numerica && est.funcion === "siguiente") est.funcion = "existente";
  if (!f.hijas.length && est.funcion.endsWith("_hijos")) est.funcion = "existente";
  // «Misma fila» de entrada si las otras partes no tienen un valor elegido a mano (vacias, 0 o calculadas).
  est.misma = hermanos.length > 0 && fijos.length === 0;
  const esClaveHermana = (c) => !c.tablas.length && hermanos.some((x) => x.toLowerCase() === String(c.atributo).toLowerCase());
  // Las que puso «misma fila» (CargoId=${...}) se vuelven a armar al usar: no se muestran.
  if (est.misma) est.condiciones = est.condiciones.filter((c) => !(esClaveHermana(c) && /^\s*\$\{/.test(c.valor)));
  const agregarHermanos = () => {
    for (const a of f.claves.slice(0, -1)) {
      const v = valorHermano(padre, a);
      if (v !== undefined && !est.condiciones.some((c) => !c.tablas.length && c.atributo.toLowerCase() === a.toLowerCase())) {
        est.condiciones.unshift({ atributo: a, op: "=", valor: v, tablas: [], negadas: [], auto: true });
      }
    }
  };
  if (!esPropia(previo)) {
    if (!est.misma) agregarHermanos();
  }
  // Los demas campos de la entrada que pueden salir de esa fila o de una tabla de sus condiciones (el CuponId de una
  // cuota que esta en un cupon en proceso), al lado del campo o en un nivel de arriba (inAgregar.CuponId para
  // inAgregar.Cuotas[*]): los que ofrece el servidor se completan, salvo los que tienen un valor puesto a mano.
  const dondeEsta = new Map();  // campo en minusculas -> [nombre, objeto que lo tiene], el mas cercano
  for (const o of padre && !Array.isArray(padre) ? [padre, ...arriba] : []) {
    for (const [x, v] of Object.entries(o)) {
      if ((v === null || typeof v !== "object") && !dondeEsta.has(x.toLowerCase())
        && !f.claves.some((c) => c.toLowerCase() === x.toLowerCase())) dondeEsta.set(x.toLowerCase(), [x, o]);
    }
  }
  const candidatos = [...dondeEsta.values()].map(([x]) => x);
  const valorCampo = (x) => valorHermano(dondeEsta.get(x.toLowerCase())?.[1], x);
  const sinCompletar = new Set(candidatos.filter((x) => { const v = valorCampo(x); return v !== undefined && !v.startsWith("${"); }));
  let relacionados = {};  // {CuponId: {tabla, expresion}}, de la ultima consulta
  // Los de un dominio enumerado siempre estan, en «cualquiera»: son los filtros mas comunes (el estado, el tipo).
  for (const a of f.atributos.filter((x) => x.valores)) {
    if (!est.condiciones.some((c) => !c.tablas.length && c.atributo.toLowerCase() === a.nombre.toLowerCase())) {
      est.condiciones.push({ atributo: a.nombre, op: "=", valor: "", tablas: [], negadas: [] });
    }
  }
  for (const c of est.condiciones) c.atributo = att(c).nombre || c.atributo;
  try { await Promise.all([...new Set(est.condiciones.filter((c) => c.tablas.length).map((c) => c.tablas[c.tablas.length - 1]))].map(cargarTabla)); }
  catch (e) { toast(e.message, "error"); }
  for (const c of est.condiciones) if (c.tablas.length && c.atributo) c.atributo = att(c).nombre || c.atributo;

  const funciones = FUNCIONES_CLAVE.filter(([fn]) => (fn !== "siguiente" || f.numerica) && (!fn.endsWith("_hijos") || f.hijas.length));
  const selFuncion = h("select", { onchange: () => { est.funcion = selFuncion.value; pintar(); } },
    funciones.map(([fn, t, d]) => h("option", { value: fn, selected: fn === est.funcion ? "" : null, title: d }, t)));
  const ayudaFuncion = h("span", { class: "muted chico" });
  const cajaHija = h("label", { class: "fila", style: { gap: "6px" } }, h("span", { class: "muted" }, "en"),
    h("select", { onchange: (ev) => { est.hija = ev.target.value; actualizar(); } },
      h("option", { value: "" }, "cualquiera de ellas"),
      f.hijas.map((t) => h("option", { value: t, selected: t.toLowerCase() === est.hija.toLowerCase() ? "" : null }, t))));
  const filas = h("div", { class: "armador-conds" });
  const filasOtras = h("div", { class: "armador-conds" });
  const selAgregar = h("select", { onchange: () => {
    if (!selAgregar.value) return;
    est.condiciones.push({ atributo: selAgregar.value, op: "=", valor: "", tablas: [], negadas: [] });
    pintar();
    const ultima = filas.lastElementChild;
    (ultima?.querySelector("input") || ultima?.querySelectorAll("select")[1])?.focus();
  } });
  // Otra tabla: una lista con filtro, porque pueden ser muchas (las relacionadas hasta 3 tablas de distancia).
  const btnOtra = h("button", { class: "btn chico", type: "button", onclick: () => listaValores(btnOtra, {
    titulo: `Tablas relacionadas con ${f.tabla}`, ancho: 460,
    valores: f.relacionadas.map((r) => ({
      valor: r.camino.join("."),
      texto: [r.titulo && r.titulo !== r.tabla ? r.titulo : "", r.camino.length > 1 ? `por ${r.camino.slice(0, -1).join(" › ")}` : (r.pasos[0] === "hija" ? `la referencia a ${f.tabla}` : `${f.tabla} la referencia`)].filter(Boolean).join(" · "),
      titulo: r.camino.join(" › "),
    })),
  }, "", async (camino) => {
    const r = f.relacionadas.find((x) => x.camino.join(".") === camino);
    try { await cargarTabla(r.tabla); } catch (e) { toast(e.message, "error"); return; }
    est.condiciones.push({ atributo: "", op: "=", valor: "", tablas: [...r.camino], negadas: r.camino.map(() => false) });
    pintar();
    filasOtras.lastElementChild?.querySelectorAll("select")[1]?.focus();
  }) }, "+ condición en otra tabla…");
  const cajaConds = h("div", null,
    h("div", { class: "muted chico", style: { margin: "12px 0 6px" } }, `En ${f.tabla} (las que quedan en «cualquiera» no filtran):`), filas,
    h("div", { style: { marginTop: "6px" } }, selAgregar),
    h("div", { class: "muted chico", style: { margin: "14px 0 6px" } }, "En otras tablas (una cuota que esté en un cupón en proceso, un cupón sin detalle…):"), filasOtras,
    f.relacionadas.length ? h("div", { style: { marginTop: "6px" } }, btnOtra) : h("div", { class: "muted chico" }, "No hay tablas relacionadas."));
  const notaSiguiente = h("div", { class: "muted chico", style: { marginTop: "10px" } },
    `Es el ${k} más grande de toda la tabla ${f.tabla}, más uno: no lleva condiciones.`);
  const chkMisma = h("input", { type: "checkbox", checked: est.misma, onchange: () => {
    est.misma = chkMisma.checked;
    if (est.misma) est.condiciones = est.condiciones.filter((c) => !c.auto);
    else agregarHermanos();
    pintar();
  } });
  const cajaMisma = h("label", { class: "chk armador-misma" }, chkMisma,
    h("span", null, `Completar también ${hermanos.join(" y ")}, para que sean de la misma fila de ${f.tabla}`),
    h("span", { class: "muted chico" }, fijos.length ? ` (reemplaza lo que tienen: ${fijos.map((x) => `${x} = ${valorHermano(padre, x)}`).join(", ")})` : ""));
  const cajaRel = h("div");
  const pintarRel = () => vaciar(cajaRel, Object.entries(relacionados).map(([x, r]) => {
    const chk = h("input", { type: "checkbox", checked: !sinCompletar.has(x), onchange: () => {
      if (chk.checked) sinCompletar.delete(x); else sinCompletar.add(x);
      actualizar();
    } });
    const v = valorCampo(x);
    const deArriba = dondeEsta.get(x.toLowerCase())?.[1] !== padre ? " (en el nivel de arriba)" : "";
    return h("label", { class: "chk armador-misma", title: r.expresion }, chk,
      h("span", null, `Completar también ${x}${deArriba}, con el de ${r.tabla === f.tabla ? "esa fila" : `${r.tabla} de esa fila`}`),
      h("span", { class: "muted chico" }, v !== undefined && !v.startsWith("${") ? ` (reemplaza ${x} = ${v})` : ""));
  }));
  const codigo = h("code", { class: "armador-expr" });
  const hoy = h("div", { class: "armador-hoy" });

  // Valor de una condicion: combo del dominio, o texto con los valores de la base (si es clave de otra tabla) o las fechas relativas.
  const controlValor = (c, a) => {
    if (a.valores) {
      const conocido = c.valor === "" || a.valores.some((v) => v.nombre.toLowerCase() === c.valor.toLowerCase());
      return h("select", { onchange: (ev) => { c.valor = ev.target.value; actualizar(); } },
        h("option", { value: "" }, "(cualquiera)"),
        conocido ? null : h("option", { value: c.valor, selected: "" }, c.valor),
        a.valores.map((v) => h("option", { value: v.nombre, selected: v.nombre.toLowerCase() === c.valor.toLowerCase() ? "" : null },
          [v.nombre, v.descripcion && v.descripcion !== v.nombre ? v.descripcion : "", `(${v.valor})`].filter(Boolean).join(" · "))));
    }
    const inp = h("input", { type: "text", value: c.valor, spellcheck: "false", placeholder: "(cualquiera)",
      oninput: () => { c.valor = inp.value; actualizar(); } });
    const fechas = FECHAS_RELATIVAS[a.tipo];
    let fuente = null;
    if (fechas) {
      fuente = { titulo: "Fechas relativas (se calculan al ejecutar)", valores: fechas.map(([e, t]) => ({ valor: `\${${e}}`, texto: t })) };
    } else if (a.tablaDe && (c.tablas.length || a.nombre.toLowerCase() !== k.toLowerCase())) {
      fuente = {
        titulo: `${a.tablaDe} · ${a.nombre}`, ancho: 420,
        cargar: async (buscar) => {
          // Filtran las otras condiciones con = sobre la misma tabla (CargoId para CargoPlanSec).
          const filtros = {};
          for (const o of est.condiciones) {
            if (o !== c && o.op === "=" && textoCamino(o) === textoCamino(c) && o.atributo && String(o.valor).trim() !== "") filtros[o.atributo] = o.valor;
          }
          const r = await POST("/api/valoresClave", { kb, atributo: a.nombre, filtros, buscar });
          const n = r.claves.length;
          return {
            valores: r.filas.map((fila) => {
              const vs = r.columnas.map((col) => fila[col]);
              return { valor: vs[n - 1], texto: r.descripcion ? String(vs[n] ?? "").trim() : "" };
            }),
            truncado: r.truncado,
          };
        },
      };
    }
    if (!fuente) return inp;
    const caja = h("div", { class: "combo" }, inp, h("button", {
      class: "btn chico fantasma icono", type: "button", title: `${fuente.titulo}\nVer los valores (Alt+↓)`, tabindex: -1,
      onclick: () => listaValores(caja, fuente, inp.value, (v) => { inp.value = String(v); inp.dispatchEvent(new Event("input")); inp.focus(); }),
    }, "▾"));
    inp.addEventListener("keydown", (ev) => { if ((ev.key === "ArrowDown" && ev.altKey) || ev.key === "F4") { ev.preventDefault(); caja.querySelector("button").click(); } });
    return caja;
  };
  const selOp = (c, a) => h("select", { class: "armador-op", onchange: (ev) => { c.op = ev.target.value; actualizar(); } },
    (a.valores ? OPERADORES_CONDICION.slice(0, 2) : OPERADORES_CONDICION).map(([o, t]) => h("option", { value: o, selected: o === c.op ? "" : null }, t)));
  const quitar = (c) => h("button", { class: "btn fantasma icono chico", title: "Quitar la condición",
    onclick: () => { est.condiciones.splice(est.condiciones.indexOf(c), 1); pintar(); } }, "✕");

  const filaPropia = (c) => {
    const a = att(c);
    const titulo = [a.tipo, a.dominio ? `dominio ${a.dominio}` : "", a.clave ? `parte de la clave de ${f.tabla}` : ""].filter(Boolean).join(" · ");
    return h("div", { class: "armador-cond" }, h("span", { class: "mono", title: titulo || null }, c.atributo), selOp(c, a), controlValor(c, a), quitar(c));
  };
  // Condicion en otra tabla: con / sin (alguna fila de esa tabla, por el camino) y, si se elige, un atributo de ella.
  const filaOtra = (c) => {
    const a = att(c);
    const final = c.tablas[c.tablas.length - 1];
    const lista = [...atts(c).values()];
    const camino = c.tablas.map((t, i) => [i ? " › " : "", i && c.negadas[i] ? h("b", null, "sin ") : null,
      i === c.tablas.length - 1 ? h("b", null, t) : t]);
    const selAtt = h("select", { onchange: (ev) => { c.atributo = ev.target.value; c.op = "="; c.valor = ""; pintar(); } },
      h("option", { value: "" }, "(alguna fila, sin condición)"),
      c.atributo && !atts(c).has(c.atributo.toLowerCase()) ? h("option", { value: c.atributo, selected: "" }, c.atributo) : null,
      lista.map((x) => h("option", { value: x.nombre, selected: x.nombre.toLowerCase() === String(c.atributo).toLowerCase() ? "" : null },
        `${x.nombre}${x.valores ? "  (dominio)" : x.tipo ? `  (${x.tipo})` : ""}`)));
    return h("div", { class: "armador-otra" },
      h("div", { class: "armador-otra-cab" },
        h("select", { class: "armador-con", title: "Con: que tenga alguna fila que cumpla. Sin: que no tenga ninguna.",
          onchange: (ev) => { c.negadas[0] = ev.target.value === "sin"; actualizar(); } },
          h("option", { value: "con", selected: c.negadas[0] ? null : "" }, "con"), h("option", { value: "sin", selected: c.negadas[0] ? "" : null }, "sin")),
        h("span", { class: "mono armador-camino", title: `Se une ${[f.tabla, ...c.tablas].join(" › ")} por sus claves` }, camino),
        quitar(c)),
      h("div", { class: "armador-cond" }, selAtt,
        c.atributo ? selOp(c, a) : h("span"),
        c.atributo ? controlValor(c, a) : h("span", { class: "muted chico" }, c.negadas[0] ? `que no tenga ninguna fila en ${final}` : `que tenga alguna fila en ${final}`),
        h("span")));
  };

  const pintar = () => {
    const fn = FUNCIONES_CLAVE.find(([x]) => x === est.funcion);
    ayudaFuncion.textContent = fn ? fn[2] : "";
    cajaHija.style.display = est.funcion.endsWith("_hijos") && f.hijas.length > 1 ? "" : "none";
    cajaConds.style.display = est.funcion === "siguiente" ? "none" : "";
    notaSiguiente.style.display = est.funcion === "siguiente" ? "" : "none";
    cajaMisma.style.display = hermanos.length && est.funcion !== "siguiente" ? "" : "none";
    vaciar(filas, est.condiciones.filter((c) => !c.tablas.length).map(filaPropia));
    vaciar(filasOtras, est.condiciones.filter((c) => c.tablas.length).map(filaOtra));
    // Un atributo comun puede ir mas de una vez (CuponFecha >= ... y CuponFecha <= ...); uno del dominio, una.
    const usados = new Set(est.condiciones.filter((c) => !c.tablas.length).map((c) => c.atributo.toLowerCase()));
    vaciar(selAgregar, h("option", { value: "" }, "+ condición sobre…"),
      f.atributos.filter((a) => !a.valores || !usados.has(a.nombre.toLowerCase()))
        .map((a) => h("option", { value: a.nombre }, `${a.nombre}${a.tipo ? `  (${a.tipo})` : ""}`)));
    actualizar();
  };

  const conMisma = () => est.misma && hermanos.length && est.funcion !== "siguiente";
  // {k: texto} y, con «misma fila», tambien las otras partes de la clave; despues, los demas campos que salen de esa
  // fila (los arma el servidor: misma_fila y relacionados).
  const armar = async () => {
    const texto = escribirVariableClave(est);
    const misma = !!conMisma();
    if (!misma && !candidatos.length) return { [k]: texto };
    const r = await POST("/api/campos/completar", { kb, expresion: texto, mismaFila: misma, hermanos: candidatos });
    const firma = (x) => JSON.stringify(Object.entries(x).map(([n, v]) => [n, v.tabla]));
    if (firma(r.relacionados) !== firma(relacionados)) { relacionados = r.relacionados; pintarRel(); }
    else relacionados = r.relacionados;
    const vars = misma ? r.variables : { [k]: texto };
    for (const [x, v] of Object.entries(r.relacionados)) if (!sinCompletar.has(x)) vars[x] = v.expresion;
    return vars;
  };
  let espera = null, pedido = 0;
  const actualizar = () => {
    codigo.textContent = escribirVariableClave(est);
    vaciar(hoy, cargando("Calculando lo que daría hoy…"));
    clearTimeout(espera);
    const n = ++pedido;
    espera = setTimeout(async () => {
      try {
        const vars = await armar();
        const nombres = Object.keys(vars);
        // Con el SQL previo de Explorar, como al ejecutar (si se cambia el estado de un cupon, se ve aca).
        const sqlPrevio = E.usarPrevio ? E.sqlPrevio : null;
        const r = await POST("/api/variables/previsualizar", { kb, expresiones: Object.values(vars), sqlPrevio });
        if (n !== pedido) return;
        const error = r.find((x) => x.error);
        const conPrevio = sqlPrevio?.some((b) => (b.sql || b.query || "").trim()) ? " (con el SQL previo)" : "";
        vaciar(hoy, error ? h("span", { class: "armador-ninguno" }, `Hoy no da ninguno${conPrevio}: ${error.error}`)
          : [`Hoy${conPrevio} daría `, nombres.length > 1
            ? nombres.map((x, i) => [i ? " · " : "", h("span", { class: "muted" }, `${x} `), h("b", { class: "mono" }, String(r[i].hoy))])
            : h("b", { class: "mono" }, String(r[0].hoy)),
          h("span", { class: "muted" }, " · se vuelve a buscar en cada ejecución")]);
      } catch (e) { if (n === pedido) vaciar(hoy, h("span", { class: "armador-ninguno" }, e.message)); }
    }, 300);
  };

  const cuerpo = h("div", { class: "armador" },
    h("div", { class: "muted chico", style: { marginBottom: "10px" } },
      `Un ${k} de ${f.tabla} que se busca en la base al ejecutar: el caso sigue sirviendo aunque los datos cambien.`),
    h("div", { class: "fila", style: { flexWrap: "wrap", gap: "8px" } }, h("b", null, "Cuál"), selFuncion, cajaHija, ayudaFuncion),
    cajaConds, notaSiguiente,
    h("div", { class: "sep" }),
    cajaMisma, cajaRel,
    h("div", { class: "fila", style: { gap: "6px", alignItems: "flex-start" } }, codigo,
      h("button", { class: "btn chico", title: "Copiar la variable", onclick: () => copiar(codigo.textContent) }, "Copiar")),
    hoy);
  pintar();
  modal({
    titulo: `Valor calculado · ${k} (${f.tabla})`, cuerpo,
    botones: [{ texto: "Cancelar" }, { texto: "Usar", prim: true, accion: async () => {
      let vars;
      try { vars = await armar(); } catch (e) { toast(e.message, "error"); return false; }
      const { [k]: propio, ...otros } = vars;
      alElegir(propio, Object.keys(otros).length ? otros : undefined);
    } }],
  });
}

function contarNiveles(niveles) { let n = 0; const r = (l) => l.forEach((x) => { n++; r(x.subniveles || []); }); r(niveles || []); return n; }

function panelEjecutar() {
  const o = E.obj;
  const cajaEntrada = h("div");
  let editorTexto = null;
  let formulario = null;
  const pintarEntrada = () => {
    if (E.modoEntrada === "json") {
      editorTexto = editorJson(E.entrada, { filas: 16, alCambiar: (v, ok) => { if (ok && v !== undefined) { E.entrada = v; guardarBorrador(); } } });
      vaciar(cajaEntrada, editorTexto);
    } else {
      formulario = formularioJson(E.entrada, E.desc?.plantillaEntrada, (v) => { E.entrada = v; guardarBorrador(); },
        { combo: comboCampo(E.kb, E.campos) });
      vaciar(cajaEntrada, Object.keys(E.entrada || {}).length ? formulario : h("div", { class: "muted chico" },
        E.desc ? "Este objeto no recibe parámetros de entrada." : cargando("Preparando la plantilla (la primera vez se inicia el motor Java)…")));
    }
  };
  const seg = h("div", { class: "grupo-seg" },
    ["form", "json"].map((m) => h("button", {
      class: E.modoEntrada === m ? "activa" : "", onclick: (ev) => {
        E.modoEntrada = m; almacen.guardar("modoEntrada", m);
        $$("button", seg).forEach((b) => b.classList.toggle("activa", b === ev.target));
        pintarEntrada();
      },
    }, m === "form" ? "Formulario" : "JSON")));
  pintarEntrada();

  const listaSql = h("div");
  const ds = (kbActual()?.datasources || []).map((d) => d.nombre);
  const pintarSql = () => vaciar(listaSql, E.sqlDespues.map((s, i) => h("div", { class: "fila", style: { marginBottom: "6px", alignItems: "flex-start" } },
    h("select", { onchange: (ev) => { s.ds = ev.target.value; guardarBorrador(); } }, ds.map((d) => h("option", { value: d, selected: d === s.ds ? "" : null }, d))),
    h("textarea", { class: "codigo", rows: 2, style: { flex: 1, width: "auto" }, oninput: (ev) => { s.query = ev.target.value; guardarBorrador(); } }, s.query || ""),
    h("button", { class: "btn fantasma icono", title: "Quitar", onclick: () => { E.sqlDespues.splice(i, 1); guardarBorrador(); pintarSql(); } }, "✕"))));
  pintarSql();

  // SQL previo: es de la KB (no del objeto), para dejar la base igual antes de probar cualquier objeto.
  const cajaPrevio = h("div");
  const pintarPrevio = () => vaciar(cajaPrevio, E.usarPrevio ? editorScript(E.sqlPrevio, ds, {
    filas: 3, placeholder: "delete from tabla_hija;\ndelete from tabla;",
    alCambiar: (l) => { E.sqlPrevio = l; guardarBorrador(); },
  }) : null);
  pintarPrevio();
  const chkPrevio = h("input", { type: "checkbox", checked: E.usarPrevio, onchange: (ev) => { E.usarPrevio = ev.target.checked; guardarBorrador(); pintarPrevio(); } });
  const copiarDeSuite = async (ev) => {
    const { clientX: x, clientY: y } = ev;
    let lista = [];
    try { lista = (await GET("/api/suites", { kb: E.kb })).filter((s) => s.scriptPrevio); } catch (e) { toast(e.message, "error"); return; }
    if (!lista.length) { toast("Ninguna suite de esta KB tiene script previo", "", 3000); return; }
    menu(x, y, "Copiar el script previo de", lista.map((s) => ({
      texto: s.nombre, accion: async () => {
        try {
          const su = await GET("/api/suite", { id: s.id });
          E.sqlPrevio = clonar(su.scriptPrevio || []); E.usarPrevio = true; chkPrevio.checked = true;
          guardarBorrador(); pintarPrevio();
        } catch (e) { toast(e.message, "error"); }
      },
    })));
  };

  const resultado = h("div", { id: "resultado-ejecucion" });
  pintarResultadoEjecucion(resultado);

  const btnEjecutar = h("button", { class: "btn prim", id: "btn-ejecutar", onclick: ejecutarObjeto, disabled: !E.desc || !!E.desc.error }, "▶ Ejecutar");
  const izquierda = h("div", { class: "tarjeta" },
    h("div", { class: "cab" }, h("h3", null, "Entrada"), h("span", { class: "espacio" }), seg,
      h("button", { class: "btn chico", title: "Volver a la plantilla vacía", onclick: () => { E.entrada = clonar(E.desc?.plantillaEntrada || {}); guardarBorrador(); pintarEntrada(); } }, "Plantilla"),
      h("button", { class: "btn chico", title: "Copiar la entrada como JSON", onclick: () => copiar(json(E.entrada)) }, "Copiar")),
    h("div", { class: "cuerpo" }, cajaEntrada,
      h("div", { class: "sep" }),
      h("div", { class: "fila", style: { marginBottom: "6px" } }, h("label", { class: "chk" }, chkPrevio, h("b", null, "SQL previo")),
        h("span", { class: "muted chico" }, "Corre antes del objeto, en la misma transacción (por ejemplo, para vaciar tablas). Se deshace al final."), h("span", { class: "espacio" }),
        h("button", { class: "btn chico", onclick: copiarDeSuite }, "Copiar de una suite…")),
      cajaPrevio,
      h("div", { class: "sep" }),
      h("div", { class: "fila", style: { marginBottom: "6px" } }, h("b", null, "Consultas SQL después"),
        h("span", { class: "muted chico" }, "Corren en la misma transacción: ven los cambios aunque después se deshagan."), h("span", { class: "espacio" }),
        h("button", { class: "btn chico", onclick: () => { E.sqlDespues.push({ ds: ds[ds.length - 1] || "", query: "select * from " }); guardarBorrador(); pintarSql(); } }, "+ consulta")),
      listaSql,
      h("div", { class: "sep" }),
      h("div", { class: "fila" },
        h("span", { class: "muted" }, "Al terminar:"),
        h("div", { class: "grupo-seg" }, [["rollback", "Rollback"], ["commit", "Commit"]].map(([v, t]) => h("button", {
          class: E.transaccion === v ? "activa" : "", title: v === "commit" ? "Confirma los cambios en la base" : "Deshace todos los cambios (recomendado)",
          onclick: (ev) => { E.transaccion = v; $$("button", ev.target.parentNode).forEach((b) => b.classList.toggle("activa", b === ev.target)); },
        }, t))),
        h("span", { class: "espacio" }),
        h("span", { class: "muted chico" }, h("kbd", null, "Ctrl"), "+", h("kbd", null, "Enter")),
        btnEjecutar,
        h("button", { class: "btn", onclick: generarValidaciones, title: "A partir de esta entrada (que tiene que terminar bien): cada campo vacío, cada valor de su dominio, un id que no existe… Se ejecutan con rollback y se guardan como un caso con datos." }, "Generar validaciones…"),
        h("button", { class: "btn", onclick: guardarComoCaso, disabled: !E.ultimoRes, id: "btn-guardar-caso" }, "Guardar como caso…"))));

  const derecha = h("div", { class: "tarjeta" }, h("div", { class: "cab" }, h("h3", null, "Resultado"), h("span", { class: "espacio" }),
    E.historialSesion.filter((x) => x.objeto === o.nombre).length ? h("button", { class: "btn chico", onclick: verHistorialSesion }, "Ejecuciones anteriores") : null),
  h("div", { class: "cuerpo" }, resultado));
  return h("div", { class: "col2" }, izquierda, derecha);
}

function pintarResultadoEjecucion(cont = $("#resultado-ejecucion")) {
  if (!cont) return;
  if (!E.ultimoRes) {
    vaciar(cont, h("div", { class: "muted", style: { padding: "30px 0", textAlign: "center" } }, "Todavía no lo ejecutaste."));
    return;
  }
  if (E.ultimoRes === "corriendo") { vaciar(cont, h("div", { style: { padding: "30px 0", textAlign: "center" } }, cargando("Ejecutando…"))); return; }
  const res = E.ultimoRes;
  const vista = vistaResultado(res, {
    abrirTodo: true, tituloScript: "SQL previo",
    alVerificar: (idx, ruta, valor, ev) => menuVerificacion(ev, ruta, valor, (v) => {
      E.pendientes.push({ paso: idx, ...v });
      pintarPendientes(pend);
      toast(v.ignorar ? `Se ignorará ${v.ignorar}` : `Verificación agregada: ${v.ruta} ${v.op}`, "ok", 1800);
    }),
  });
  const pend = h("div");
  pintarPendientes(pend);
  vaciar(cont, vista, pend);
}

function pintarPendientes(cont) {
  if (!E.pendientes.length) { vaciar(cont); return; }
  vaciar(cont, h("div", { class: "sep" }),
    h("div", { class: "fila", style: { marginBottom: "6px" } }, h("b", null, `Para el caso de prueba (${E.pendientes.length})`),
      h("span", { class: "muted chico" }, "Se incluyen al guardar como caso."), h("span", { class: "espacio" }),
      h("button", { class: "btn chico fantasma", onclick: () => { E.pendientes = []; pintarPendientes(cont); } }, "Limpiar")),
    h("div", { class: "chips" }, E.pendientes.map((v, i) => h("span", { class: "chip", title: json(v) },
      h("span", null, v.ignorar ? `ignorar ${v.ignorar}` : `${v.ruta || "$"} ${v.op}${v.valor !== undefined ? " " + resumirValor(v.valor, 30) : ""}`),
      h("button", { onclick: () => { E.pendientes.splice(i, 1); pintarPendientes(cont); } }, "✕")))));
}

async function ejecutarObjeto() {
  if (!E.obj || !E.desc || E.desc.error) return;
  if (E.modoEntrada === "json") {
    const ta = $("#detalle-objeto textarea.codigo");
    if (ta) { try { E.entrada = ta.value.trim() ? JSON.parse(ta.value) : {}; } catch (e) { toast("La entrada no es un JSON válido: " + e.message, "error"); return; } }
  }
  if (E.transaccion === "commit" && !(await confirmar("Vas a ejecutar con COMMIT: los cambios quedan grabados en la base.\n¿Seguir?", { si: "Ejecutar con commit", peligro: true }))) return;
  const btn = $("#btn-ejecutar");
  if (btn) btn.disabled = true;
  E.ultimoRes = "corriendo"; E.pendientes = [];
  pintarResultadoEjecucion();
  const t0 = Date.now();
  // Lo que se manda queda junto al resultado: "Guardar como caso" usa esto y no lo que haya en pantalla
  // (si se editó después, la línea base no correspondería a la entrada).
  const enviado = {
    objeto: E.obj.nombre, entrada: clonar(E.entrada), transaccion: E.transaccion,
    sql: clonar(E.sqlDespues.filter((s) => (s.query || "").trim())),
    sqlPrevio: E.usarPrevio ? clonar(E.sqlPrevio.filter((s) => (s.sql || "").trim())) : [],
  };
  try {
    const res = await POST("/api/ejecutar", { kb: E.kb, ...enviado });
    res.enviado = enviado;
    E.ultimoRes = res;
    E.historialSesion.unshift({ fecha: new Date(), objeto: E.obj.nombre, entrada: clonar(E.entrada), res, ms: Date.now() - t0 });
    E.historialSesion = E.historialSesion.slice(0, 50);
  } catch (e) {
    E.ultimoRes = { estado: "error", nombre: E.obj.nombre, enviado, pasos: [{ nombre: E.obj.nombre, estado: "error", error: e.message, verificaciones: [], diferencias: [], advertencias: [] }] };
  }
  if (btn) btn.disabled = false;
  const g = $("#btn-guardar-caso"); if (g) g.disabled = false;
  pintarResultadoEjecucion();
  refrescarMotor();
}

function verHistorialSesion() {
  const lista = E.historialSesion.filter((x) => x.objeto === E.obj.nombre);
  const m = modal({
    titulo: "Ejecuciones de esta sesión", ancho: true,
    cuerpo: h("table", { class: "tabla" }, h("thead", null, h("tr", null, h("th", null, "Hora"), h("th", null, "Estado"), h("th", null, "Entrada"), h("th", null, ""))),
      h("tbody", null, lista.map((x) => h("tr", null,
        h("td", null, x.fecha.toLocaleTimeString()), h("td", null, pillEstado(x.res.estado)),
        h("td", { class: "mono" }, resumirValor(x.entrada, 140)),
        h("td", null, h("button", { class: "btn chico", onclick: () => { E.entrada = clonar(x.entrada); E.ultimoRes = x.res; guardarBorrador(); m.cerrar(); pintarObjeto(); } }, "Restaurar")))))),
  });
}

function panelNavegacion() {
  const raiz = h("div");
  const pintar = () => vaciar(raiz, contenidoNavegacion(pintar));
  pintar();
  return raiz;
}

function contenidoNavegacion(repintar) {
  const o = E.obj;
  const cajaPlan = h("div", { class: "plan" }, vistaPlan(E.plan));
  const barra = h("div", { class: "fila", style: { marginBottom: "8px" } },
    h("button", { class: "btn prim", disabled: !!E.plan?.cargando, onclick: () => calcularPlan(repintar),
      title: "EXPLAIN de MySQL de cada sentencia SQL del objeto (sacadas del Java generado) y recomendaciones" },
    E.plan && !E.plan.cargando ? "↻ Recalcular plan de ejecución" : "Calcular plan de ejecución"),
    h("span", { class: "muted chico" }, "Corre EXPLAIN en la base local (no ejecuta las sentencias) y revisa los índices de cada tabla."));
  if (!o.niveles?.length) return h("div", null, barra, cajaPlan, h("div", { class: "muted", style: { padding: "10px 0" } }, "El objeto no tiene For Each / accesos a la base en su navegación (o usa Business Components)."));
  const nivel = (n) => h("div", { class: "nivel" },
    h("div", { class: "fila" }, h("b", null, n.tipo || "Nivel"), n.tabla ? pill(n.tabla, "acento") : null,
      n.linea ? h("span", { class: "muted chico" }, `línea ${n.linea}`) : null,
      n.indice ? h("span", { class: "chico" }, "índice ", h("code", null, n.indice)) : (n.tabla ? pill("sin índice", "aviso") : null),
      (n.optimizaciones || []).filter(Boolean).map((x) => pill(x))),
    h("dl", null,
      n.tablaDescripcion ? [h("dt", null, "Tabla"), h("dd", null, n.tablaDescripcion)] : null,
      n.orden ? [h("dt", null, "Orden"), h("dd", null, n.orden)] : null,
      n.desde ? [h("dt", null, "Empieza en"), h("dd", null, n.desde)] : null,
      n.mientras ? [h("dt", null, "Mientras"), h("dd", null, n.mientras)] : null,
      n.filtros ? [h("dt", null, "Filtros"), h("dd", null, n.filtros)] : null,
      n.condicion && n.condicion !== n.filtros ? [h("dt", null, "Condición"), h("dd", null, n.condicion)] : null,
      n.join?.length ? [h("dt", null, "Navega"), h("dd", null, n.join.join(", "))] : null,
      n.actualiza?.length ? [h("dt", null, "Actualiza"), h("dd", null, n.actualiza.join(", "))] : null),
    (n.subniveles || []).map(nivel));
  return h("div", null, barra, cajaPlan,
    h("h4", { class: "titulo-seccion" }, "Navegación de GeneXus"),
    h("div", { class: "muted chico", style: { marginBottom: "6px" } }, "Según la última especificación (GXSPC…/NVG). Los filtros que no aparecen en «Empieza en / Mientras» recorren la tabla."), o.niveles.map(nivel));
}

// ---------------------------------------------------------------------- plan de ejecucion
async function calcularPlan(repintar) {
  const nombre = E.obj.nombre;
  E.plan = { cargando: true };
  repintar();
  let r;
  try { r = await POST("/api/plan", { kb: E.kb, nombre }); } catch (e) { r = { error: e.message }; }
  if (E.obj?.nombre !== nombre) return;
  E.plan = r;
  repintar();
}

const CLASE_NIVEL = { alto: "falla", medio: "aviso", bajo: "" };
const ORIGEN_PLAN = { indices: "por los índices", explain: "según el EXPLAIN", "indices+explain": "por los índices y el EXPLAIN", navegacion: "por la navegación GX" };

function vistaPlan(p) {
  if (!p) return null;
  if (p.cargando) return h("div", { class: "muted", style: { padding: "6px 0" } }, cargando("Calculando el plan (EXPLAIN de cada sentencia)…"));
  if (p.error) return h("div", { class: "error-caja" }, "No se pudo calcular el plan:\n" + p.error);
  const detalles = [];
  const abrir = (i) => { const d = detalles[i]; if (!d) return; d.open = true; d.scrollIntoView({ block: "nearest", behavior: "smooth" }); };
  const hallazgo = (x) => h("div", { class: `hallazgo-plan ${x.nivel}` },
    h("div", { class: "fila" }, pill(x.nivel, CLASE_NIVEL[x.nivel]), h("b", null, x.titulo)),
    x.detalle ? h("div", { class: "chico" }, x.detalle) : null,
    x.sugerencia ? h("div", { class: "chico sugerencia" }, h("b", null, "Sugerencia: "), x.sugerencia) : null,
    h("div", { class: "chico muted" }, ORIGEN_PLAN[x.origen] || x.origen,
      x.cursor ? [" · ", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); abrir(x.sentencia); } }, `sentencia ${x.cursor}`)] : null));
  const r = p.resumen || {};
  const cab = h("div", { class: "fila", style: { margin: "4px 0 8px" } },
    h("b", null, p.hallazgos.length ? `${p.hallazgos.length} recomendación(es)` : "Sin recomendaciones"),
    ["alto", "medio", "bajo"].filter((n) => r[n]).map((n) => pill(`${r[n]} ${n}`, CLASE_NIVEL[n])),
    h("span", { class: "muted chico" }, `${p.sentencias.length} sentencia(s) · ${fmtMs(p.ms)}`));
  const columnas = ["table", "type", "possible_keys", "key", "rows", "filtered", "Extra"];
  const sentencia = (s, i) => {
    const d = h("details", { class: "sentencia-plan" },
      h("summary", null,
        h("span", { class: "mono" }, s.cursor), " ", pill(s.tipo.toUpperCase()), s.dinamica ? pill("dinámica", "acento") : null, " ",
        h("span", { class: "muted" }, s.tablas.join(", ")),
        s.hallazgos.length ? [" ", ["alto", "medio", "bajo"].map((n) => { const k = s.hallazgos.filter((x) => x.nivel === n).length; return k ? pill(`${k} ${n}`, CLASE_NIVEL[n]) : null; })] : null,
        s.error ? [" ", pill("error", "falla")] : null),
      h("pre", { class: "bloque sql-plan" }, s.explicado || s.sql),
      s.explicado && s.explicado !== s.sql ? h("div", { class: "chico muted" }, "Los ? se reemplazaron por valores de una fila de la tabla (o de ejemplo) para el EXPLAIN.") : null,
      s.error ? h("div", { class: "error-caja" }, s.error) : null,
      s.nota ? h("div", { class: "chico muted", style: { margin: "4px 0" } }, s.nota) : null,
      s.plan.length ? tablaFilas(columnas, s.plan) : (s.tipo === "insert" ? h("div", { class: "chico muted" }, "INSERT: no tiene plan de acceso.") : null),
      s.hallazgos.map(hallazgo));
    detalles[i] = d;
    return d;
  };
  return h("div", null, cab,
    (p.avisos || []).map((a) => h("div", { class: "aviso-caja" }, a)),
    p.hallazgos.map(hallazgo),
    p.sentencias.length ? h("div", { style: { marginTop: "10px" } }, h("b", { class: "chico" }, "Sentencias"), p.sentencias.map(sentencia))
      : h("div", { class: "muted chico" }, "El Java del objeto no tiene sentencias SQL propias."));
}

function panelMensajes() {
  const o = E.obj;
  const es = o.listaErrores || [], ws = o.listaWarnings || [];
  if (!es.length && !ws.length) return h("div", { class: "muted", style: { padding: "10px 0" } }, "Sin warnings ni errores en la última especificación.");
  const fila = (m, tipo) => h("tr", null, h("td", null, pill(tipo, tipo === "error" ? "falla" : "aviso")), h("td", { class: "mono" }, m.codigo), h("td", null, m.texto));
  return h("table", { class: "tabla" }, h("tbody", null, es.map((m) => fila(m, "error")), ws.map((m) => fila(m, "warning"))));
}

function kbActual() { return E.kbs.find((k) => k.nombre === E.kb); }

// ---------------------------------------------------------------------- guardar como caso
/** El selector de suite de la KB (con «Nueva suite…») de los diálogos que guardan un caso desde Explorar. */
async function selectorSuite() {
  let suites = [];
  try { suites = await GET("/api/suites", { kb: E.kb }); } catch { /* sin suites */ }
  // Las auto-* las genera 'generar' y no se editan a mano: no se proponen por defecto.
  const propias = suites.filter((s) => !/\/auto-/.test(s.id));
  const ultima = almacen.leer(`ultimaSuite.${E.kb}`, null);
  const elegida = (propias.find((s) => s.id === ultima) || propias[0])?.id;
  const sel = h("select", null, suites.map((s) => h("option", { value: s.id, selected: s.id === elegida ? "" : null }, `${s.nombre}  (${s.casos} casos)`)),
    h("option", { value: "__nueva", selected: !elegida ? "" : null }, "➕ Nueva suite…"));
  const nombre = h("input", { type: "text", placeholder: "Nombre de la nueva suite", value: modulo(E.obj.nombre).split(".").slice(1).join(" - ") || E.kb });
  const filaNueva = h("div", { style: { display: sel.value === "__nueva" ? "contents" : "none" } }, h("label", null, "Nueva suite"), nombre);
  sel.addEventListener("change", () => { filaNueva.style.display = sel.value === "__nueva" ? "contents" : "none"; });
  return { suites, sel, nombre, filaNueva };
}

async function guardarComoCaso() {
  const res = E.ultimoRes;
  if (!res || res === "corriendo") return;
  const { suites: suitesKb, sel: selSuite, nombre: nombreSuite, filaNueva } = await selectorSuite();
  const nombreCaso = h("input", { type: "text", value: `${corto(E.obj.nombre)}: ` });
  const etiquetas = h("input", { type: "text", placeholder: "separadas por coma", value: corto(E.obj.nombre).toLowerCase() });
  const pasoObj = res.pasos[0];
  // Lo que se ejecutó de verdad (el resultado de una ejecución vieja restaurada del historial lo trae igual).
  const env = res.enviado || { objeto: E.obj.nombre, entrada: E.entrada, transaccion: E.transaccion, sql: E.sqlDespues.filter((s) => (s.query || "").trim()) };
  if (res.scriptPrevio?.estado === "error") { toast("El SQL previo terminó con error: corregilo y ejecutá de nuevo antes de guardar.", "error"); return; }
  // La salida se obtuvo después del SQL previo: el caso tiene que correr sobre la misma base. Puede pasar a ser
  // el script previo de la suite (corre una vez antes de todos sus casos) o los primeros pasos del caso.
  const previo = env.sqlPrevio || [];
  const firma = (l) => JSON.stringify((l || []).map((b) => [b.ds || "", (b.sql || "").trim()]));
  const selPrevio = h("select");
  const notaPrevio = h("div", { class: "muted chico", style: { marginTop: "3px" } });
  const filaPrevio = h("div", { style: { display: previo.length ? "contents" : "none" } }, h("label", null, "SQL previo"), h("div", null, selPrevio, notaPrevio));
  const actualizarPrevio = async () => {
    if (!previo.length) return;
    const id = selSuite.value;
    let actual = null;
    if (id !== "__nueva") { try { actual = (await GET("/api/suite", { id })).scriptPrevio || null; } catch { /* nueva o borrada */ } }
    if (selSuite.value !== id) return;
    const igual = !!actual && firma(actual) === firma(previo);
    const casos = suitesKb.find((s) => s.id === id)?.casos || 0;
    vaciar(selPrevio, (igual ? [["nada", "Ya es el script previo de la suite"]] : [
      ["suite", actual ? "Usarlo como script previo de la suite (reemplaza el actual)" : "Usarlo como script previo de la suite"],
      ["pasos", "Agregarlo como primeros pasos del caso"],
      ["nada", "No guardarlo"],
    ]).map(([v, t]) => h("option", { value: v }, t)));
    selPrevio.value = igual ? "nada" : actual ? "pasos" : "suite";
    const notar = () => {
      notaPrevio.textContent = selPrevio.value !== "suite" ? ""
        : "Corre una vez antes de todos los casos de la suite y cada caso arranca de esa base." + (casos ? ` Los ${casos} casos que ya tiene también van a correr sobre ella.` : "");
    };
    selPrevio.onchange = notar;
    notar();
  };
  selSuite.addEventListener("change", actualizarPrevio);
  actualizarPrevio();
  // Excepción: el caso pasa si vuelve a terminar con este mismo error (y falla si termina bien o con otro).
  const conExcepcion = pasoObj?.estado === "error" && !!pasoObj.error;
  const textoError = conExcepcion ? pasoObj.error.split("\n")[0].slice(0, 150) : "";
  const chkError = h("input", { type: "checkbox", checked: true });
  const modoCmp = h("select", null,
    h("option", { value: "todo" }, "Toda la salida (recomendado)"),
    h("option", { value: "estructura" }, "Solo la estructura, Ok y los códigos de mensaje"));
  const chkSql = h("input", { type: "checkbox", checked: env.sql.length > 0 });
  // Lo que además tiene que cumplirse siempre: lo que se eligió haciendo clic en la salida y las sugerencias
  // del servidor (Ok y códigos de mensaje ya marcados). Cada una queda como verificación del paso.
  const items = [];
  const clave = (i, v) => `${i}|${v.ruta}|${v.op}|${JSON.stringify(v.valor)}`;
  const vistos = new Set();
  const agregar = (i, v, marcada, prefijo) => {
    const k = v.ignorar ? `${i}|ignorar|${v.ignorar}` : clave(i, v);
    if (vistos.has(k)) return;
    vistos.add(k);
    const chk = h("input", { type: "checkbox", checked: marcada });
    items.push({ paso: i, v, chk, fila: h("label", { class: "chk", title: v.ignorar || `${v.ruta} ${v.op} ${resumirValor(v.valor, 80)}` }, chk,
      prefijo ? h("span", { class: "muted" }, prefijo) : null,
      v.ignorar ? ["No comparar ", h("code", null, v.ignorar)] : (v.descripcion || [h("code", null, v.ruta), ` ${v.op.replace("_", " ")} `, h("code", null, resumirValor(v.valor, 40))])) });
  };
  E.pendientes.forEach(({ paso, ...v }) => agregar(paso, v, true, paso > 0 ? `Consulta ${paso}: ` : ""));
  res.pasos.forEach((p, i) => (p.sugerencias || []).forEach((s) => { const { marcada, ...v } = s; agregar(i, v, marcada && !conExcepcion, i > 0 ? `Consulta ${i}: ` : ""); }));
  const lista = h("div", { style: { display: "flex", flexDirection: "column", gap: "3px", maxHeight: "220px", overflow: "auto" } },
    items.length ? items.map((x) => x.fila) : h("span", { class: "muted chico" }, "Nada para sugerir en esta salida."));
  const cuerpo = h("div", { class: "form-grid" },
    h("label", null, "Suite"), selSuite, filaNueva,
    h("label", null, "Nombre del caso"), nombreCaso,
    h("label", null, "Etiquetas"), etiquetas,
    filaPrevio,
    ...(conExcepcion
      ? [h("label", null, "Resultado"), h("label", { class: "chk" }, chkError, "Tiene que terminar con este error: ", h("code", null, textoError))]
      : [h("label", null, "Comparar con esta salida"), h("div", null, modoCmp,
        h("div", { class: "muted chico", style: { marginTop: "3px" } }, "«Solo la estructura» es para listados con datos de la base que cambian. Los valores que cambian solos (fechas, ids nuevos) se detectan al guardar, ejecutando una vez más.")),
      ]),
    h("label", null, "Además, siempre tiene que cumplirse"), lista,
    ...(env.sql.length ? [h("label", null, "Consultas SQL"), h("label", { class: "chk" }, chkSql, "Guardarlas como pasos del caso")] : []));
  modal({
    titulo: "Guardar como caso de prueba", cuerpo, botones: [{ texto: "Cancelar" }, {
      texto: "Guardar", prim: true, accion: async () => {
        const nuevo = selSuite.value === "__nueva";
        if (nuevo && !nombreSuite.value.trim()) { toast("Poné un nombre para la suite", "error"); return false; }
        const elegidas = (i) => items.filter((x) => x.paso === i && x.chk.checked);
        const verifs = (i) => elegidas(i).filter((x) => !x.v.ignorar).map((x) => x.v);
        const ign = (i) => elegidas(i).filter((x) => x.v.ignorar).map((x) => x.v.ignorar);
        const aprobar = (pr) => !conExcepcion && pr?.estado !== "error" && pr?.datos != null;
        const modo = modoCmp.value === "estructura" ? { comparar: "estructura" } : {};
        const pasos = [{
          nombre: corto(env.objeto), objeto: env.objeto, entrada: clonar(env.entrada), calculadas: pasoObj?.calculadas,
          ...(conExcepcion && chkError.checked ? { esperaError: true, errorContiene: textoError } : {}),
          ...(verifs(0).length ? { verificaciones: verifs(0) } : {}),
          ...(ign(0).length ? { ignorar: ign(0) } : {}),
          ...(aprobar(pasoObj) ? { lineaBase: pasoObj.datos, ...modo } : {}),
        }];
        if (env.sql.length && chkSql.checked && !conExcepcion) {
          env.sql.forEach((s, j) => {
            const pr = res.pasos[j + 1];
            pasos.push({
              nombre: `Consulta ${j + 1}`, sql: s.query, ds: s.ds, calculadas: pr?.calculadas,
              ...(verifs(j + 1).length ? { verificaciones: verifs(j + 1) } : {}),
              ...(ign(j + 1).length ? { ignorar: ign(j + 1) } : {}),
              ...(aprobar(pr) ? { lineaBase: pr.datos, ...modo } : {}),
            });
          });
        }
        const modoPrevio = previo.length ? selPrevio.value : "nada";
        if (modoPrevio === "pasos") pasos.unshift(...previo.map((b, i) => ({ nombre: `SQL previo ${i + 1}`, sql: b.sql, ds: b.ds })));
        const caso = {
          nombre: nombreCaso.value.trim() || corto(E.obj.nombre),
          etiquetas: etiquetas.value.split(",").map((x) => x.trim()).filter(Boolean),
          ...(env.transaccion === "commit" ? { transaccion: "commit" } : {}),
          pasos,
        };
        const id = nuevo ? `${E.kb}/${slug(nombreSuite.value)}` : selSuite.value;
        const espera = toast(cargando("Guardando: se ejecuta una vez más para ver qué valores cambian solos…"), "", 0);
        try {
          const r = await POST("/api/suite/caso", { id, kb: E.kb, nombreSuite: nombreSuite.value.trim(), caso, ...(modoPrevio === "suite" ? { scriptPrevio: previo } : {}) });
          almacen.guardar(`ultimaSuite.${E.kb}`, r.id);
          E.pendientes = [];
          pintarResultadoEjecucion();
          const vol = Object.values(r.volatiles || {}).flat();
          const t = toast(h("span", null, "Caso guardado en ", h("b", null, r.id), ". ",
            h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); t.remove(); irA("suites"); abrirSuite(r.id); } }, "Abrir la suite"),
            vol.length ? h("div", { class: "chico" }, "Cambian solos (se controla que existan y su tipo): ", vol.join(", ")) : null,
            (r.conVariable || []).map((a) => h("div", { class: "chico" }, a)),
            (r.avisos || []).map((a) => h("div", { class: "chico" }, "⚠ ", a))), (r.avisos || []).length ? "error" : "ok", (r.avisos || []).length ? 0 : 9000);
          cargarSuites();
        } catch (e) { toast(e.message, "error"); return false; }
        finally { espera.remove(); }
      },
    }],
  });
}

// ---------------------------------------------------------------------- generar validaciones
/** Propone filas de validación a partir de la entrada actual (que tiene que terminar bien): cada campo vacío, cada
 *  valor de su dominio, un id que no existe… Las ejecuta (con rollback) y muestra qué devuelve hoy cada una. Las
 *  elegidas se guardan como un caso con «datos», con lo que se espera de cada fila (Ok y el código o el mensaje). */
async function generarValidaciones() {
  const recortar = (t, n) => (t.length > n ? t.slice(0, n) + "…" : t);
  const previo = E.usarPrevio ? clonar(E.sqlPrevio.filter((s) => (s.sql || "").trim())) : [];
  const aviso = toast(cargando("Generando las filas de validación y ejecutándolas (con rollback)…"), "", 0);
  let p, sel;
  try {
    [p, sel] = await Promise.all([
      POST("/api/validaciones", { kb: E.kb, objeto: E.obj.nombre, entrada: clonar(E.entrada), sqlPrevio: previo }),
      selectorSuite()]);
  } catch (e) { toast(e.message, "error"); return; } finally { aviso.remove(); }
  if (p.filas.length <= 1) { toast("No hay nada para variar en esta entrada: completá los campos con valores que terminen bien.", "error"); return; }
  const conSalida = !!p.rutaSalida;
  const filas = p.filas.map((f) => {
    const chk = h("input", { type: "checkbox", checked: f.marcada });
    const campo = f.codigo ? "codigo" : "mensaje";
    const espera = h("select", { disabled: !conSalida }, h("option", { value: "true", selected: f.ok === true ? "" : null }, "termina bien"),
      h("option", { value: "false", selected: f.ok === false ? "" : null }, "falla"));
    const motivo = h("input", { type: "text", value: f[campo] || "", disabled: !conSalida, placeholder: campo === "codigo" ? "código" : "mensaje de error",
      title: campo === "codigo" ? "Código de mensaje que tiene que devolver" : "Texto del mensaje de error que tiene que devolver (el objeto no devuelve código)" });
    const hoy = f.estado === "error" ? h("span", { class: "pill falla", title: f.error }, "error")
      : f.ok === false ? h("span", { class: "pill falla" }, "falla") : f.ok === true ? h("span", { class: "pill ok" }, "Ok") : h("span", { class: "muted" }, f.estado);
    const tr = h("tr", null,
      h("td", null, chk),
      h("td", null, f.prueba, f.aviso ? h("div", { class: "muted chico" }, "⚠ ", f.aviso) : null),
      h("td", { class: "mono" }, f.tipo === "base" ? "" : resumirValor(f.valor, 30)),
      h("td", null, hoy, " ", h("span", { class: "muted chico" }, recortar(f.codigo || f.texto || f.error || "", 90))),
      h("td", null, espera),
      h("td", null, motivo));
    return { f, chk, espera, motivo, campo, tr };
  });
  const nombreCaso = h("input", { type: "text", value: `${corto(E.obj.nombre)}: validaciones` });
  const cuerpo = h("div", null,
    h("p", { class: "muted chico" }, "Cada fila es una ejecución con un campo cambiado respecto de tu entrada. «Hoy» es lo que devolvió ahora (con rollback); «Se espera» es lo que el caso va a exigir: corregilo donde lo de hoy sea un error del objeto.",
      conSalida ? "" : " La salida no tiene un sdtOutput (Ok y mensajes): el caso queda sin verificaciones y conviene aprobar su salida desde Suites."),
    h("div", { style: { maxHeight: "48vh", overflow: "auto", marginBottom: "10px" } },
      h("table", { class: "tabla" }, h("thead", null, h("tr", null, h("th", null, ""), h("th", null, "Prueba"), h("th", null, "Valor"), h("th", null, "Hoy"), h("th", null, "Se espera"), h("th", null, "Código o mensaje"))),
        h("tbody", null, filas.map((x) => x.tr)))),
    h("div", { class: "form-grid" }, h("label", null, "Suite"), sel.sel, sel.filaNueva, h("label", null, "Nombre del caso"), nombreCaso,
      ...(previo.length ? [h("label", null, "SQL previo"), h("span", { class: "muted chico" }, "Se agrega como primer paso del caso: corre antes de cada fila.")] : [])));
  modal({
    titulo: `Validaciones de ${corto(E.obj.nombre)}`, ancho: true, cuerpo, botones: [{ texto: "Cancelar" }, {
      texto: "Guardar caso", prim: true, accion: async () => {
        const elegidas = filas.filter((x) => x.chk.checked).map((x) => ({
          ...x.f, ok: x.espera.value === "true", codigo: x.campo === "codigo" ? x.motivo.value.trim() : "",
          mensaje: x.campo === "mensaje" ? x.motivo.value.trim() : "",
        }));
        if (!elegidas.length) { toast("Elegí al menos una fila", "error"); return false; }
        const nueva = sel.sel.value === "__nueva";
        if (nueva && !sel.nombre.value.trim()) { toast("Poné un nombre para la suite", "error"); return false; }
        try {
          const caso = await POST("/api/validaciones/caso", { objeto: p.objeto, entrada: p.entrada, columnas: p.columnas, filas: elegidas,
            nombre: nombreCaso.value.trim(), rutaSalida: p.rutaSalida });
          caso.pasos.unshift(...previo.map((b, i) => ({ nombre: `SQL previo ${i + 1}`, sql: b.sql, ds: b.ds })));
          const id = nueva ? `${E.kb}/${slug(sel.nombre.value)}` : sel.sel.value;
          const r = await POST("/api/suite/caso", { id, kb: E.kb, nombreSuite: sel.nombre.value.trim(), caso, detectarVolatiles: false });
          almacen.guardar(`ultimaSuite.${E.kb}`, r.id);
          const t = toast(h("span", null, `Caso con ${elegidas.length} filas guardado en `, h("b", null, r.id), ". ",
            h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); t.remove(); irA("suites"); abrirSuite(r.id); } }, "Abrir la suite")), "ok", 9000);
          cargarSuites();
        } catch (e) { toast(e.message, "error"); return false; }
      },
    }],
  });
}

// ====================================================================== suites
async function cargarSuites() {
  try {
    E.suites = await GET("/api/suites", $("#suites-todas").checked ? undefined : { kb: E.kb });
  } catch (e) { E.suites = []; }
  pintarListaSuites();
}

function pintarListaSuites() {
  const q = $("#buscar-suite").value.trim().toLowerCase();
  const lista = E.suites.filter((s) => !q || (s.nombre + " " + s.id).toLowerCase().includes(q));
  vaciar($("#lista-suites"), lista.length ? lista.map((s) => {
    const u = s.ultimo;
    const t = u?.totales || {};
    return h("div", { class: `item ${E.suite?._id === s.id ? "activo" : ""}`, onclick: () => abrirSuite(s.id) },
      h("span", { class: `punto-estado ${u ? (u.estado === "ok" ? "ok" : "falla") : ""}`, style: { marginTop: "5px" } }),
      h("div", { style: { flex: 1, minWidth: 0 } },
        h("div", { class: "t" }, s.nombre),
        h("div", { class: "s" }, `${s.casos} casos`, s.kb !== E.kb ? ` · ${s.kb}` : "",
          u ? ` · ${t.ok || 0}✔ ${t.falla || 0}✖ ${t.error || 0}⚠ · ${fmtFecha(u.fecha)}` : " · sin correr"),
        s.error ? h("div", { class: "s", style: { color: "var(--falla)" } }, s.error) : null));
  }) : h("div", { class: "vacio" }, "No hay suites. Creá una o guardá una ejecución como caso."));
}

async function nuevaSuite() {
  const nombre = await pedirTexto("Nueva suite", `Nombre de la suite (KB ${E.kb})`);
  if (!nombre) return;
  try {
    const r = await api("PUT", "/api/suite", { suite: { nombre, kb: E.kb, casos: [] } });
    await cargarSuites();
    irA("suites");
    abrirSuite(r.id);
  } catch (e) { toast(e.message, "error"); }
}

async function abrirSuite(id, conservarResultados = false) {
  try {
    E.suite = await GET("/api/suite", { id });
  } catch (e) { toast(e.message, "error"); return; }
  if (!conservarResultados) { E.resultados = {}; E.abiertos = new Set(); }
  pintarListaSuites();
  pintarSuite();
}

function idsResultado(caso) {
  // un caso con 'datos' produce un resultado por fila: id#1, id#2...
  return caso.datos?.length ? caso.datos.map((_, i) => `${caso.id}#${i + 1}`) : [caso.id];
}

function estadoCaso(caso) {
  const ids = idsResultado(caso);
  const actuales = ids.map((i) => E.resultados[i]).filter(Boolean);
  if (actuales.length) {
    const es = actuales.map((r) => r.estado);
    return { estado: es.includes("error") ? "error" : es.includes("falla") ? "falla" : es.every((x) => x === "omitido") ? "omitido" : "ok", ms: actuales.reduce((a, r) => a + (r.ms || 0), 0), actual: true };
  }
  const est = E.suite._estado || {};
  const previos = ids.map((i) => est[i]).filter(Boolean);
  if (!previos.length) return null;
  const es = previos.map((r) => r.estado);
  return { estado: es.includes("error") ? "error" : es.includes("falla") ? "falla" : "ok", ms: previos.reduce((a, r) => a + (r.ms || 0), 0), fecha: previos[0].fecha, corrida: previos[0].corrida };
}

function pintarSuite() {
  const s = E.suite;
  const det = $("#detalle-suite");
  const filtro = h("input", { type: "search", placeholder: "Filtrar casos…", style: { width: "200px" }, value: E.filtroCasos || "" });
  const etiquetas = [...new Set(s.casos.flatMap((c) => c.etiquetas || []))].sort();
  const selEtq = h("select", null, h("option", { value: "" }, "Todas las etiquetas"), etiquetas.map((e) => h("option", { value: e, selected: E.etiquetaCasos === e ? "" : null }, e)));
  const tabla = h("div");
  const progreso = h("div", { id: "progreso-suite" });
  const corriendo = !!E.trabajo;
  const visibles = () => s.casos.filter((c) => {
    const f = (E.filtroCasos || "").toLowerCase();
    if (f && !(c.nombre + " " + c.id + " " + c.pasos.map((p) => p.objeto || p.sql || "").join(" ")).toLowerCase().includes(f)) return false;
    if (E.etiquetaCasos && !(c.etiquetas || []).includes(E.etiquetaCasos)) return false;
    return true;
  });
  const seleccion = E.seleccion || (E.seleccion = new Set());
  const pintarTabla = () => {
    const vs = visibles();
    const todosSel = vs.length && vs.every((c) => seleccion.has(c.id));
    vaciar(tabla, s.casos.length ? h("table", { class: "tabla" },
      h("thead", null, h("tr", null,
        h("th", { style: { width: "28px" } }, h("input", { type: "checkbox", checked: todosSel, onchange: (ev) => { vs.forEach((c) => ev.target.checked ? seleccion.add(c.id) : seleccion.delete(c.id)); pintarTabla(); actualizarBotones(); } })),
        h("th", { style: { width: "80px" } }, "Estado"), h("th", null, "Caso"), h("th", null, "Pasos"), h("th", { style: { width: "80px" } }, "Tiempo"), h("th", { style: { width: "130px" } }, ""))),
      h("tbody", null, vs.map((c) => filaCaso(c)))) : h("div", { class: "vacio-grande" }, h("h3", null, "La suite no tiene casos"),
      h("div", null, "Agregá uno con ", h("b", null, "+ Caso"), " o desde ", h("b", null, "Explorar → Guardar como caso"), "."),
      h("div", { style: { marginTop: "14px" } }, botonTutorial("🎓 Ver el tutorial: cómo armar pruebas", "btn"))));
  };
  const filaCaso = (c) => {
    const est = estadoCaso(c);
    const abierto = E.abiertos.has(c.id);
    const pasos = c.pasos.map((p) => p.objeto ? corto(p.objeto) : "SQL").join(" → ");
    const actuales = idsResultado(c).map((i) => E.resultados[i]).filter(Boolean);
    const motivo = est && est.estado !== "ok" && actuales.length ? motivoFalla(actuales) : "";
    const controla = resumenControles(c);
    const tr = h("tr", { class: `clic ${abierto ? "sel" : ""}` },
      h("td", { onclick: (ev) => ev.stopPropagation() }, h("input", { type: "checkbox", checked: seleccion.has(c.id), onchange: (ev) => { ev.target.checked ? seleccion.add(c.id) : seleccion.delete(c.id); actualizarBotones(); } })),
      h("td", null, est ? h("span", { class: "fila", style: { gap: "6px" } }, h("span", { class: `punto-estado ${est.estado}` }), h("span", { class: "chico" }, NOMBRE_ESTADO[est.estado]), est.actual ? null : h("span", { class: "muted chico", title: `Resultado del ${fmtFecha(est.fecha)}` }, "·")) : h("span", { class: "muted chico" }, c.omitir ? "omitido" : "sin correr"),
        E.sinCorrer.has(c.id) ? h("div", { class: "chico", style: { color: "var(--aviso)" }, title: "Cambiaste lo que controla: el estado es de antes" }, "cambiado, sin correr") : null),
      h("td", null, h("div", null, h("b", null, c.nombre), c.omitir ? [" ", pill("omitido")] : null),
        motivo ? h("div", { class: "chico", style: { color: "var(--falla)", marginTop: "1px" } }, motivo) : null,
        h("div", { class: "fila", style: { gap: "4px", marginTop: "2px" } }, (c.etiquetas || []).map((e) => pill(e)), c.datos?.length ? pill(`${c.datos.length} filas de datos`, "acento") : null,
          h("span", { class: `chico ${controla.length ? "muted" : ""}`, style: controla.length ? {} : { color: "var(--aviso)" }, title: "Lo que controla el caso" },
            controla.length ? "Controla: " + controla.join(" · ") : "No controla nada todavía"))),
      h("td", { class: "chico mono" }, pasos),
      h("td", { class: "chico muted" }, est ? fmtMs(est.ms) : ""),
      h("td", { onclick: (ev) => ev.stopPropagation() }, h("div", { class: "fila", style: { gap: "2px", flexWrap: "nowrap" } },
        h("button", { class: "btn fantasma icono chico", title: "Correr este caso", disabled: !!E.trabajo, onclick: () => correrSuite({ casos: [c.id] }) }, "▶"),
        h("button", { class: "btn fantasma icono chico", title: "Editar", onclick: () => editarCaso(c.id) }, "✎"),
        h("button", { class: "btn fantasma icono chico", title: "Duplicar", onclick: () => duplicarCaso(c.id) }, "⧉"),
        h("button", { class: "btn fantasma icono chico", title: "Subir", onclick: () => moverCaso(c.id, -1) }, "↑"),
        h("button", { class: "btn fantasma icono chico", title: "Eliminar", onclick: () => borrarCaso(c.id) }, "🗑"))));
    tr.addEventListener("click", () => { abierto ? E.abiertos.delete(c.id) : E.abiertos.add(c.id); pintarTabla(); });
    if (!abierto) return tr;
    const detalle = h("td", { colspan: 6, style: { background: "var(--panel-2)", padding: "10px 14px" } }, detalleCaso(c, est));
    return [tr, h("tr", null, detalle)];
  };
  const btnSel = h("button", { class: "btn", onclick: () => correrSuite({ casos: [...seleccion] }) }, "▶ Correr seleccionados");
  const btnFallidos = h("button", { class: "btn", onclick: () => correrSuite({ casos: s.casos.filter((c) => ["falla", "error"].includes(estadoCaso(c)?.estado)).map((c) => c.id) }) }, "▶ Correr fallidos");
  const actualizarBotones = () => {
    const n = [...seleccion].filter((id) => s.casos.some((c) => c.id === id)).length;
    btnSel.disabled = !n || !!E.trabajo; btnSel.textContent = `▶ Correr seleccionados${n ? ` (${n})` : ""}`;
    btnFallidos.disabled = !!E.trabajo || !s.casos.some((c) => ["falla", "error"].includes(estadoCaso(c)?.estado));
  };
  filtro.addEventListener("input", () => { E.filtroCasos = filtro.value; pintarTabla(); });
  selEtq.addEventListener("change", () => { E.etiquetaCasos = selEtq.value; pintarTabla(); });

  const ult = (s._estado || {})._resumen;
  vaciar(det,
    h("h2", { class: "titulo" }, s.nombre),
    h("div", { class: "subtitulo" }, pill(s.kb || "sin KB", "acento"), h("span", { class: "mono chico" }, s._id), `${s.casos.length} casos`,
      s._version ? h("span", { class: "chico muted", title: "Versión en la base compartida" }, `v${s._version} · ${s._por || "?"} · ${fmtFecha(s._actualizado)}`) : null,
      ult ? h("span", { class: "chico" }, "última corrida ", fmtFecha(ult.fecha), " · ", `${ult.totales.ok}✔ ${ult.totales.falla}✖ ${ult.totales.error}⚠`) : null,
      s.opciones?.transaccion === "commit" ? pill("commit", "aviso") : pill(s.opciones?.transaccion || "rollback"),
      s.opciones?.casosEncadenados ? pill("casos encadenados", "acento") : null),
    s.descripcion ? h("div", { class: "muted", style: { marginBottom: "10px" } }, s.descripcion) : null,
    franjaScript(s),
    panelVariables(s),
    h("div", { class: "tarjeta" },
      h("div", { class: "cab" },
        h("button", { class: "btn prim", disabled: corriendo, onclick: () => correrSuite({}) }, "▶ Correr todo"),
        btnSel, btnFallidos,
        h("button", { class: "btn", disabled: corriendo, title: "Corre los casos (los seleccionados, o todos) y sus salidas actuales pasan a ser las aprobadas", onclick: grabarLineasBase }, "● Aprobar salidas actuales"),
        h("span", { class: "espacio" }),
        filtro, etiquetas.length ? selEtq : null,
        h("button", { class: "btn", onclick: () => editarCaso(null) }, "+ Caso"),
        h("button", { class: "btn", onclick: (ev) => menu(ev.clientX, ev.clientY, null, [
          { texto: "Opciones, script previo, variables y preparación…", accion: editarOpcionesSuite },
          { texto: "Editar JSON completo…", accion: editarJsonSuite },
          { texto: "Duplicar suite", accion: duplicarSuite },
          { texto: "Descargar JSON", accion: () => descargar(`${slug(s.nombre)}.json`, json(limpiarSuite(s))) },
          "-",
          { texto: "Eliminar suite…", accion: borrarSuite },
        ]) }, "Más ▾")),
      progreso,
      h("div", { class: "cuerpo", style: { padding: 0 } }, tabla)));
  pintarTabla();
  actualizarBotones();
  if (E.trabajo) pintarProgreso();
  E.repintarTablaSuite = () => { pintarTabla(); actualizarBotones(); };
}

function detalleCaso(c, est) {
  const ids = idsResultado(c);
  const cont = h("div");
  const mostrar = (resultados, fecha) => vaciar(cont, fichaCaso({
    caso: c, resultados, fecha, sinCorrer: E.sinCorrer.has(c.id),
    correr: () => correrSuite({ casos: [c.id] }),
    editarJson: () => editarCaso(c.id),
    // Cambia la definicion del caso (lo que controla) y la guarda. El resultado que se ve queda viejo.
    guardar: async (mutar, mensaje) => {
      const caso = E.suite.casos.find((x) => x.id === c.id);
      mutar(caso);
      E.sinCorrer.add(c.id);
      await guardarSuite(mensaje);
    },
    aceptar: async (paso, datos, fila, pr) => {
      // Lo principal es no dar por buena una salida incorrecta: si no cumple lo que el caso exige, se pregunta.
      const malas = (pr?.verificaciones || []).filter((v) => !v.ok);
      if (malas.length && !(await confirmar(`Esta salida NO cumple ${malas.length} verificación(es) del caso:\n\n${malas.map((v) => `• ${v.descripcion || `${v.ruta} ${v.op} ${resumirValor(v.valor, 40)}`}`).join("\n")}\n\nSi la aceptás, esas verificaciones van a seguir fallando. ¿Aceptarla igual?`, { si: "Aceptar igual", peligro: true }))) return;
      try {
        const r = await POST("/api/lineabase", { suite: E.suite._id, caso: c.id, paso, fila, datos, calculadas: pr?.calculadas });
        E.sinCorrer.add(c.id);
        toast(h("span", null, "Salida aprobada: de ahora en más se compara contra esta. Corré el caso para confirmarlo.",
          (r.conVariable || []).map((a) => h("div", { class: "chico" }, a))), "ok");
        await abrirSuite(E.suite._id, true);
      } catch (e) { toast(e.message, "error"); }
    },
  }));
  const actuales = ids.map((i) => E.resultados[i]).filter(Boolean);
  if (actuales.length) { mostrar(actuales, actuales[0].fecha || null); return cont; }
  if (est?.corrida) {
    cont.appendChild(cargando("Cargando el último resultado…"));
    obtenerCorrida(est.corrida).then((cor) => {
      const rs = cor.casos.filter((r) => ids.includes(r.id));
      rs.forEach((r) => (E.resultados[r.id] = { ...r, fecha: cor.fin }));
      mostrar(rs.map((r) => E.resultados[r.id]), cor.fin);
    }).catch(() => mostrar([]));
    return cont;
  }
  mostrar([]);
  return cont;
}

async function obtenerCorrida(id) {
  if (!E.corridasCache[id]) E.corridasCache[id] = await GET("/api/corrida", { id });
  return E.corridasCache[id];
}

function limpiarSuite(s) {
  const o = {};
  for (const [k, v] of Object.entries(s)) if (!k.startsWith("_")) o[k] = v;
  return o;
}

async function guardarSuite(mensaje) {
  try {
    await api("PUT", "/api/suite", { id: E.suite._id, version: E.suite._version, suite: limpiarSuite(E.suite) });
    if (mensaje) toast(mensaje, "ok", 2000);
    await abrirSuite(E.suite._id, true);
    cargarSuites();
  } catch (e) { toast(e.message, "error"); }
}

async function correrSuite({ casos, grabar = false }) {
  if (E.trabajo) return;
  if (casos && !casos.length) return;
  const s = E.suite;
  if (s.opciones?.casosEncadenados && casos && casos.length < s.casos.length
    && !(await confirmar("Los casos de esta suite están encadenados: cada uno sigue de lo que dejó el anterior. Si corrés solo algunos, los que dependen de otros pueden fallar.\n¿Seguir?", { si: "Correr igual" }))) return;
  for (const c of s.casos) if (!casos || casos.includes(c.id)) { idsResultado(c).forEach((i) => delete E.resultados[i]); E.sinCorrer.delete(c.id); }
  try {
    const r = await POST("/api/corridas", { suite: s._id, casos, grabar });
    E.trabajo = { id: r.trabajo, suite: s._id, desde: 0, estado: "esperando", casos: [], total: 0, grabar };
  } catch (e) { toast(e.message, "error"); return; }
  pintarSuite();
  sondearTrabajo();
}

async function sondearTrabajo() {
  const t = E.trabajo;
  if (!t) return;
  let r;
  try { r = await GET("/api/trabajo", { id: t.id, desde: t.desde }); } catch (e) { toast(e.message, "error"); E.trabajo = null; return; }
  for (const c of r.casos) { t.casos.push(c); E.resultados[c.id] = c; }
  t.desde = r.cantidad;
  t.estado = r.estado; t.total = r.total || t.total; t.error = r.error;
  if (r.scriptPrevio) E.scriptCorrida[t.suite] = r.scriptPrevio;
  if (E.suite?._id === t.suite) { pintarProgreso(); E.repintarTablaSuite && E.repintarTablaSuite(); }
  if (["esperando", "corriendo"].includes(r.estado)) { setTimeout(sondearTrabajo, 350); return; }
  E.trabajo = null;
  const tot = r.totales || {};
  if (r.estado === "error") toast("La corrida falló: " + (r.error || ""), "error");
  else if (r.scriptPrevio?.estado === "error") toast("El script previo terminó con error: no se corrió ningún caso. " + (r.scriptPrevio.error || ""), "error", 0);
  else toast(`Corrida terminada: ${tot.ok || 0} ok, ${tot.falla || 0} con fallas, ${tot.error || 0} con errores${r.lineasBaseGrabadas ? ` · ${r.lineasBaseGrabadas} salidas aprobadas` : ""}`,
    (tot.falla || tot.error) ? "error" : "ok", 6000);
  if (E.suite?._id === t.suite) await abrirSuite(t.suite, true);
  cargarSuites();
  refrescarMotor();
}

function pintarProgreso() {
  const cont = $("#progreso-suite");
  const t = E.trabajo;
  if (!cont) return;
  if (!t) { vaciar(cont); return; }
  const tot = { ok: 0, falla: 0, error: 0, omitido: 0 };
  t.casos.forEach((c) => (tot[c.estado] = (tot[c.estado] || 0) + 1));
  const pct = t.total ? Math.round((t.casos.length / t.total) * 100) : 0;
  vaciar(cont, h("div", { style: { padding: "10px 14px", borderBottom: "1px solid var(--borde)" } },
    h("div", { class: "fila", style: { marginBottom: "6px" } }, h("span", { class: "cargando" }),
      h("b", null, t.grabar ? "Aprobando salidas…" : "Corriendo…"), h("span", { class: "muted" }, `${t.casos.length} de ${t.total || "?"}`),
      h("div", { class: "contadores" }, pill(`${tot.ok} ok`, "ok"), tot.falla ? pill(`${tot.falla} fallas`, "falla") : null, tot.error ? pill(`${tot.error} errores`, "error") : null),
      h("span", { class: "espacio" }),
      h("button", { class: "btn chico peligro", onclick: () => POST(`/api/trabajo/cancelar?id=${t.id}`) }, "Cancelar")),
    h("div", { class: `progreso ${tot.falla || tot.error ? "falla" : ""}` }, h("div", { style: { width: pct + "%" } }))));
}

async function grabarLineasBase() {
  const s = E.suite;
  const sel = [...(E.seleccion || [])].filter((id) => s.casos.some((c) => c.id === id));
  const ok = await confirmar(`Se van a correr ${sel.length ? sel.length + " casos seleccionados" : "todos los casos"} y sus salidas actuales pasan a ser las aprobadas.\nCada caso se ejecuta dos veces: lo que da distinto (fechas, ids nuevos) se marca como «cambia solo».\n\nHacelo solo cuando sepas que el comportamiento actual es el correcto.`, { si: "Aprobar salidas" });
  if (ok) correrSuite({ casos: sel.length ? sel : undefined, grabar: true });
}

async function moverCaso(id, d) {
  const cs = E.suite.casos;
  const i = cs.findIndex((c) => c.id === id);
  const j = i + d;
  if (j < 0 || j >= cs.length) return;
  [cs[i], cs[j]] = [cs[j], cs[i]];
  await guardarSuite();
}
async function borrarCaso(id) {
  const c = E.suite.casos.find((x) => x.id === id);
  if (!(await confirmar(`¿Eliminar el caso «${c.nombre}»?`, { si: "Eliminar", peligro: true }))) return;
  E.suite.casos = E.suite.casos.filter((x) => x.id !== id);
  await guardarSuite("Caso eliminado");
}
async function duplicarCaso(id) {
  const i = E.suite.casos.findIndex((x) => x.id === id);
  const c = clonar(E.suite.casos[i]);
  delete c.id; c.nombre += " (copia)";
  E.suite.casos.splice(i + 1, 0, c);
  await guardarSuite("Caso duplicado");
}

function editarCaso(id) {
  const s = E.suite;
  const existente = id ? s.casos.find((c) => c.id === id) : null;
  const caso = existente ? clonar(existente) : { nombre: "Nuevo caso", etiquetas: [], pasos: [] };
  const ed = editorJson(caso, { filas: 26 });
  const ds = (E.kbs.find((k) => k.nombre === s.kb)?.datasources || []).map((d) => d.nombre);
  const insertarPaso = (paso) => {
    const v = ed.valor();
    if (!v) { toast("Primero corregí el JSON", "error"); return; }
    (v.pasos = v.pasos || []).push(paso);
    ed.poner(v);
  };
  const objetoInput = h("input", { type: "text", list: "dl-objetos", placeholder: "Objeto a agregar…", style: { width: "100%" } });
  const dl = h("datalist", { id: "dl-objetos" }, E.objetos.map((o) => h("option", { value: o.nombre })));
  const ayudantes = h("div", { style: { display: "flex", flexDirection: "column", gap: "8px" } },
    h("b", null, "Agregar paso"),
    objetoInput, dl,
    h("button", {
      class: "btn", onclick: async () => {
        const nombre = objetoInput.value.trim();
        if (!nombre) { objetoInput.focus(); return; }
        let entrada = {};
        try { const d = await GET("/api/describir", { kb: s.kb, nombre }); entrada = d.plantillaEntrada; } catch (e) { toast(e.message, "error"); return; }
        insertarPaso({ nombre: corto(nombre), objeto: nombre, entrada, esperado: {}, verificaciones: [] });
        objetoInput.value = "";
      },
    }, "+ Paso: ejecutar objeto"),
    h("button", { class: "btn", onclick: () => insertarPaso({ nombre: "Consulta", sql: "select count(*) as n from TABLA where ...", ds: ds[ds.length - 1] || "", verificaciones: [{ ruta: "filas[0].n", op: "igual", valor: 1 }] }) }, "+ Paso: consulta SQL"),
    h("button", {
      class: "btn", onclick: () => {
        const v = ed.valor(); if (!v) return;
        (v.datos = v.datos || []).push({ variable: "valor" }); ed.poner(v);
      },
    }, "+ Fila de datos (parametrizar)"),
    h("div", { class: "sep" }),
    h("div", { class: "chico muted" }, h("b", null, "Recordatorio"), h("br"),
      "• ", h("code", null, "${variable}"), " usa variables de la suite, de ", h("code", null, "datos"), " o de ", h("code", null, "guardar"), ". Va entre comillas: ", h("code", null, "\"ItfId\": \"${idItf}\""), ". Se reemplaza en ", h("code", null, "entrada"), ", ", h("code", null, "sql"), ", ", h("code", null, "esperado"), ", ", h("code", null, "verificaciones"), " y ", h("code", null, "lineaBase"), ".", h("br"),
      "• ", h("code", null, "esperado"), ": coincidencia parcial.", h("br"),
      "• ", h("code", null, "verificaciones"), ": {ruta, op, valor, cada}.", h("br"),
      "• ", h("code", null, "lineaBase"), ": la salida aprobada. Con ", h("code", null, "\"comparar\": \"estructura\""), " solo se controlan campos, tipos, Ok y códigos. ", h("code", null, "volatiles"), ": cambian solos (solo el tipo). ", h("code", null, "ignorar"), ": no se comparan.", h("br"),
      "• ", h("code", null, "esperaError"), ": el paso tiene que fallar.", h("br"),
      "• Comodines: ", h("code", null, "<<no_vacio>>"), " ", h("code", null, "<<regex:...>>"), " ", h("code", null, "<<cualquiera>>"), h("br"),
      h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); irA("ayuda"); } }, "Ver la ayuda completa")));
  const guardar = async (correr) => {
    const v = ed.valor();
    if (!v) { toast("El JSON del caso no es válido", "error"); return false; }
    if (existente) {
      const i = s.casos.findIndex((c) => c.id === id);
      v.id = v.id || id;
      s.casos[i] = v;
    } else s.casos.push(v);
    await guardarSuite("Caso guardado");
    if (correr) {
      const nuevoId = existente ? v.id : E.suite.casos[E.suite.casos.length - 1].id;
      correrSuite({ casos: [nuevoId] });
    }
  };
  modal({
    titulo: existente ? `Editar caso · ${existente.nombre}` : "Nuevo caso", ancho: true,
    cuerpo: h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1fr) 260px", gap: "14px" } }, ed, ayudantes),
    botones: [{ texto: "Cancelar" }, { texto: "Guardar y correr", accion: () => guardar(true) }, { texto: "Guardar", prim: true, accion: () => guardar(false) }],
  });
}

// El script previo de la suite (arriba de los casos): qué hace y, si corrió en esta sesión, cómo terminó.
function franjaScript(s) {
  const sp = s.scriptPrevio || [];
  const enc = !!s.opciones?.casosEncadenados;
  const ultimo = E.scriptCorrida[s._id];
  if (!sp.length && !enc) return null;
  const dss = [...new Set(sp.map((b) => b.ds || "el datasource por defecto"))].join(", ");
  const texto = !sp.length ? "Cada caso sigue de lo que dejó el anterior. Toda la corrida es una transacción y al final se deshace."
    : enc ? `En ${dss}. Corre una vez antes del primer caso; cada caso sigue de lo que dejó el anterior y al final se deshace todo.`
      : `En ${dss}. Corre una vez antes de los casos; cada caso arranca de esa base y al final se deshace todo.`;
  return h("div", { class: "tarjeta", style: { marginBottom: "10px" } },
    h("div", { class: "cab" }, h("h3", null, sp.length ? "Script previo" : "Casos encadenados"),
      sp.length && enc ? pill("casos encadenados", "acento") : null,
      h("span", { class: "muted chico" }, texto),
      h("span", { class: "espacio" }),
      h("button", { class: "btn chico", onclick: editarOpcionesSuite }, "Editar")),
    ultimo ? h("div", { class: "cuerpo" }, vistaScript(ultimo, "Última corrida")) : null);
}

// Explicación de las variables (desplegable en las opciones de la suite).
// Las variables de la suite: de dónde sale cada una, su último valor y qué casos la usan (con avisos si no les llega).
// Las que no hay que definir: predefinidas, fechas relativas (${hoy+30}) y las que se calculan en la base (${existente.X}).
const PREDEFINIDAS = ["hoy", "ahora", "aleatorio", "uuid", "caso", "siguiente", "existente", "ultimo", "con_hijos", "sin_hijos",
  "inicio_mes", "fin_mes", "inicio_anio", "fin_anio", "habil_siguiente", "habil_anterior", "fecha_vacia"];
function variablesDeSuite(s) {
  const vars = new Map(); // nombre -> {origenes: [], valor, hay, fecha, usan: [], avisos: []}
  const de = (k) => vars.get(k) || vars.set(k, { origenes: [], hay: false, usan: [], avisos: [], guardanEn: [] }).get(k);
  for (const [k, v] of Object.entries(s.variables || {})) Object.assign(de(k), { valor: v, hay: true }).origenes.push(["Variables de la suite"]);
  const ultimo = (caso) => {
    // El último valor que guardó el caso: de la corrida de esta sesión o de la última guardada.
    for (const id of idsResultado(caso).slice().reverse()) {
      const r = E.resultados[id];
      if (r?.variablesGuardadas) return { v: r.variablesGuardadas, fecha: null };
    }
    for (const id of idsResultado(caso).slice().reverse()) {
      const e = (s._estado || {})[id];
      if (e?.variables) return { v: e.variables, fecha: e.fecha };
    }
    return null;
  };
  const anotar = (k, u) => {
    if (u && k in u.v) { const x = de(k); x.valor = u.v[k]; x.hay = true; x.fecha = u.fecha; }
  };
  for (const p of s.preparacion || []) for (const [k, r] of Object.entries(p.guardar || {})) {
    de(k).origenes.push(["Preparación, paso «", p.nombre || p.objeto || "SQL", "» ← ", h("code", null, r)]);
    for (const c of s.casos) anotar(k, ultimo(c));
  }
  s.casos.forEach((c, ci) => {
    const cols = [...new Set((c.datos || []).flatMap((f) => Object.keys(f || {})))];
    for (const k of cols) {
      const x = de(k);
      x.origenes.push(["Columna de «datos» del caso «", c.nombre, "»: ", h("code", null, (c.datos || []).map((f) => resumirValor(f?.[k], 20)).join(" · "))]);
      x.porFila = true;
    }
    c.pasos.forEach((p) => {
      for (const [k, r] of Object.entries(p.guardar || {})) {
        de(k).origenes.push(["Guarda el caso «", c.nombre, "», paso «", p.nombre || p.objeto || "SQL", "» ← ", h("code", null, r)]);
        de(k).guardanEn.push(ci);
        anotar(k, ultimo(c));
      }
    });
  });
  // Quién usa cada una (y las que se usan sin estar definidas en ningún lado).
  s.casos.forEach((c, ci) => {
    const pasosPropios = new Set(c.pasos.map((p) => slug(p.nombre || p.objeto || "SQL").replace(/-/g, "_")));
    const usadas = new Set([...JSON.stringify(c.pasos).matchAll(/\$\{\s*([A-Za-z_][\w]*)/g)].map((m) => m[1]));
    for (const k of usadas) {
      if (PREDEFINIDAS.includes(k) || pasosPropios.has(k)) continue;
      const x = de(k);
      x.usan.push(c.nombre);
      if (!x.guardanEn.length || x.guardanEn.includes(ci) || (c.datos || []).some((f) => f && k in f)) continue;
      if (!s.opciones?.casosEncadenados) x.avisos.push(`No le llega a «${c.nombre}»: con casos aislados, lo que guarda un caso no pasa a los demás.`);
      else if (Math.min(...x.guardanEn) > ci) x.avisos.push(`«${c.nombre}» corre antes del caso que la guarda: no le va a llegar.`);
    }
  });
  for (const [k, x] of vars) if (!x.origenes.length) x.avisos.push("No está definida en ningún lado: ni en las variables de la suite, ni en «datos», ni la guarda un paso.");
  return [...vars.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}

function panelVariables(s) {
  const lista = variablesDeSuite(s);
  if (!lista.length) return null;
  const conAviso = lista.filter(([, x]) => x.avisos.length).length;
  const abierto = almacen.leer("panelVariables", false);
  const valor = (x) => {
    if (x.porFila && !x.hay) return h("span", { class: "muted" }, "una por fila de datos");
    if (!x.hay) return h("span", { class: "muted" }, "todavía no se asignó (corré la suite)");
    const v = x.valor && typeof x.valor === "object" && "_resumido" in x.valor ? x.valor._resumido : x.valor;
    return [h("code", null, resumirValor(v, 60)), x.fecha ? h("div", { class: "chico muted" }, fmtFecha(x.fecha)) : null];
  };
  const tabla = h("table", { class: "tabla" },
    h("thead", null, h("tr", null, h("th", null, "Variable"), h("th", null, "De dónde sale"), h("th", null, "Último valor"), h("th", null, "La usan"))),
    h("tbody", null, lista.map(([k, x]) => h("tr", null,
      h("td", null, h("code", null, "${" + k + "}")),
      h("td", null, x.origenes.length ? x.origenes.map((o) => h("div", null, o)) : h("span", { class: "muted" }, "—"),
        x.avisos.map((a) => h("div", { class: "chico", style: { color: "var(--aviso)", marginTop: "2px" } }, "⚠ ", a))),
      h("td", null, valor(x)),
      h("td", { class: "chico" }, x.usan.length ? x.usan.join(", ") : h("span", { class: "muted" }, "ningún caso"))))));
  const det = h("details", { open: abierto || undefined, class: "tarjeta", style: { marginBottom: "10px" } },
    h("summary", { class: "cab", style: { cursor: "pointer" } }, h("h3", null, `Variables (${lista.length})`),
      conAviso ? pill(`${conAviso} con aviso`, "aviso") : null,
      h("span", { class: "muted chico" }, "De dónde sale cada ${variable}, el último valor que tomó y qué casos la usan.")),
    h("div", { class: "cuerpo" }, tabla,
      h("div", { class: "chico muted", style: { marginTop: "6px" } }, "Los valores que guardan los pasos son los de la última corrida. Las variables de la suite se cambian en Más → Opciones."),
      ayudaVariables()));
  det.addEventListener("toggle", () => almacen.guardar("panelVariables", det.open));
  return det;
}

function ayudaVariables() {
  const c = (t) => h("code", null, t);
  const ej = (t) => h("pre", { class: "bloque", style: { margin: "4px 0 8px" } }, t);
  const tit = (t) => h("div", { style: { fontWeight: 600, margin: "10px 0 4px" } }, t);
  const fila = (...cols) => h("tr", null, cols.map((x) => h("td", null, x)));
  return h("details", { class: "ayuda-desplegable" },
    h("summary", null, "¿Cómo funcionan las variables? Tocá acá para ver la explicación y ejemplos"),
    h("div", { class: "cuerpo-ayuda" },
      h("p", null, "Una variable es un valor con nombre. En cualquier parte de un caso (la entrada de un objeto, una consulta SQL, «esperado», una verificación o la salida aprobada) escribís ",
        c("${nombre}"), " y GxPruebas lo reemplaza por su valor. Si el texto es solo ", c('"${nombre}"'), ", el valor mantiene su tipo: un número sigue siendo número."),
      tit("De dónde sale cada variable"),
      h("table", { class: "tabla" },
        h("thead", null, h("tr", null, h("th", null, "Origen"), h("th", null, "Cómo se crea"), h("th", null, "Hasta dónde llega"))),
        h("tbody", null,
          fila("Variables de la suite", ["En este campo: ", c('{"itf": 1}'), " → ", c("${itf}")], "Todos los casos."),
          fila("Columna de «datos»", ["En el caso: ", c('"datos": [{"tipo": "AAA"}, {"tipo": "BBB"}]'), ". El caso se repite una vez por fila."], "Esa fila. Si se llama igual que una variable de la suite, gana la de la fila."),
          fila(["Lo que guarda un paso (", c("guardar"), ")"], ["En el paso: ", c('"guardar": {"cupon": "outSet.CuponId"}'), ". También haciendo clic en un valor de la salida del caso → «Guardar como variable»."],
            ["Los pasos siguientes del mismo caso. Con ", h("b", null, "casos encadenados"), ", también los casos que corren después."]),
          fila("La salida de un paso anterior", ["Automática, con el nombre del paso en minúsculas y _ en vez de espacios: ", c("${alta.outSet.CuponId}")], "Los pasos siguientes del mismo caso."),
          fila("La entrada de un paso anterior", ["Automática: ", c("${alta.entrada.inSet.Importe}"), ". Sirve para no escribir dos veces un valor esperado."], "Los pasos siguientes del mismo caso."),
          fila("Predefinidas", [c("${hoy}"), " ", c("${ahora}"), " ", c("${uuid}"), " ", c("${aleatorio}"), " ", c("${caso}")], "Siempre."),
          fila("Calculadas en la base", [c("${siguiente.CuponId}"), " (uno que no existe: el último + 1), ", c("${existente.CuponId}"), " (el primero), ", c("${ultimo.CuponId}"),
            ", ", c("${existente.CuponId|CuponEstado=PENDIENTE}"), " (el primero que cumple; condiciones separadas por coma, con = != < > <= >=, y el nombre del valor del dominio), ",
            c("${con_hijos.CuponId}"), " y ", c("${sin_hijos.CuponId}"), " (con o sin filas en las tablas que lo referencian; ", c("${con_hijos.CuponId:tabla}"), " para una), ", c("${existente.CargoCuotaNumero|cbhCuponDetalle.cbhCupon.CuponEstado=EN_PROCESO}"), " (una condición en otra tabla, con el camino delante; ", c("!tabla"), " para que no tenga ninguna fila). En Explorar se arman eligiendo, con «Con filtros…» (arriba en el combo del campo) o el botón ƒ: cuál, los filtros (un estado, una fecha, otras tablas) y lo que darían hoy; también completa las otras partes de una clave compuesta con la misma fila."],
            "Se calculan al usarlas por primera vez en el caso (con lo que dejaron el script previo y los pasos anteriores) y quedan fijas para el resto del caso. Pueden llevar otra variable adentro: ${existente.CuponCuotaSec|CuponId=${cupon}}."),
          fila("Fechas relativas", [c("${hoy+30}"), " ", c("${hoy-1}"), " ", c("${hoy+2m}"), " ", c("${hoy-1a}"), " ", c("${ahora+2h}"), " ", c("${ahora-30min}"), " ", c("${inicio_mes}"), " ", c("${fin_mes+1}"), " ",
            c("${inicio_anio}"), " ", c("${fin_anio}"), " ", c("${habil_siguiente}"), " ", c("${habil_anterior}"), " ", c("${fecha_vacia}"), ". En Explorar, el combo de un campo de fecha las ofrece."],
            "Siempre. Se calculan al ejecutar (días por defecto; m meses, a años; con ahora, h horas y min minutos)."))),
      tit("Dentro de un caso: un paso le pasa un valor al siguiente"),
      ej(`"pasos": [
  { "nombre": "Alta", "objeto": "Cupones.Set",
    "entrada": { "inSet": { "Importe": 100 } },
    "guardar": { "cupon": "outSet.CuponId" } },        ← guarda el id que devolvió el Set
  { "nombre": "Uso", "objeto": "Cupones.Usar",
    "entrada": { "inUsar": { "CuponId": "\${cupon}" } } }  ← y lo usa acá
]`),
      tit("De un caso a otro: depende de «Entre un caso y otro»"),
      h("ul", { style: { margin: "0 0 6px", paddingLeft: "18px" } },
        h("li", null, h("b", null, "Cada caso arranca de cero: "), "cada caso empieza solo con las variables de la suite y su fila de datos. Lo que guardó otro caso no le llega: si lo usa, falla con «Variable no definida» y el error dice qué caso la guarda."),
        h("li", null, h("b", null, "Cada caso sigue de lo que dejó el anterior: "), "lo que un caso guarda con ", c("guardar"), " llega como variable a todos los casos que corren después. Solo pasa lo de ", c("guardar"), ": ", c("${alta.outSet...}"), " no pasa de un caso a otro.")),
      ej(`Caso 1 «Crear cupón»:   { "objeto": "Cupones.Set", ..., "guardar": { "cupon": "outSet.CuponId" } }
Caso 2 «Usar cupón»:    { "objeto": "Cupones.Usar", "entrada": { "inUsar": { "CuponId": "\${cupon}" } } }`),
      h("p", { class: "muted chico", style: { margin: "0 0 6px" } }, "Con casos encadenados el orden importa: si corrés solo el caso 2, nadie guardó ", c("${cupon}"), " y falla. Corré la suite completa. Si el caso que se repite por «datos» tiene una columna con el mismo nombre que una variable guardada, en esa fila gana la columna."),
      tit("En la salida aprobada (lineaBase)"),
      h("p", null, "También se reemplazan: si en la salida aprobada ponés ", c('"ItfId": "${idItf}"'), ", ese campo tiene que dar el valor que tenga la variable en esa corrida, aunque cambie de una corrida a otra. Al aprobar una salida nueva, los campos donde pusiste una variable la conservan. Si la variable no existe, el texto se compara tal cual."),
      tit("Dónde ver las variables"),
      h("p", { style: { margin: 0 } }, "En la suite, el panel «Variables» muestra de dónde sale cada una, el último valor que tomó y qué casos la usan, con un aviso si alguna no le va a llegar a un caso.")));
}

function editarOpcionesSuite() {
  const s = E.suite;
  const op = { transaccion: "rollback", recortarEspacios: true, toleranciaNumerica: 0.000001, listasParciales: false, timeoutMs: 120000, ...(s.opciones || {}) };
  const nombre = h("input", { type: "text", value: s.nombre });
  const desc = h("textarea", { rows: 2 }, s.descripcion || "");
  const kb = h("select", null, E.kbs.map((k) => h("option", { value: k.nombre, selected: k.nombre === s.kb ? "" : null }, k.nombre)));
  const tx = h("select", null, [["rollback", "Rollback al terminar cada caso (recomendado)"], ["commit", "Commit al terminar cada caso"]].map(([v, t]) => h("option", { value: v, selected: v === op.transaccion ? "" : null }, t)));
  const recortar = h("input", { type: "checkbox", checked: op.recortarEspacios });
  const listas = h("input", { type: "checkbox", checked: op.listasParciales });
  const tol = h("input", { type: "text", value: String(op.toleranciaNumerica) });
  const tmo = h("input", { type: "text", value: String(op.timeoutMs) });
  // Vacíos se muestran sin {} ni [] para que se vea el ejemplo del placeholder.
  const vars = editorJson(Object.keys(s.variables || {}).length ? s.variables : undefined, {
    filas: 4, placeholder: 'Ejemplo:\n{\n  "itf": 1,\n  "tipoPrueba": "ZZPRUEBA"\n}',
  });
  const prep = editorJson((s.preparacion || []).length ? s.preparacion : undefined, {
    filas: 8, placeholder: 'Ejemplo:\n[\n  { "nombre": "Alta del registro que usan los casos",\n    "objeto": "Generales.Interfases.Registro.Set",\n    "entrada": { "inSet": { "ItfId": "${itf}", "Tipo": "${tipoPrueba}", "Nombre": "x", "Fin": "LF" } },\n    "guardar": { "regTipo": "outSet.RegTipo" } },\n  { "nombre": "Sin movimientos", "sql": "delete from tabla where ...", "ds": "GENERALES" }\n]',
  });
  const nota = (...t) => h("div", { class: "muted chico", style: { marginTop: "3px" } }, ...t);
  const etq = (t) => h("label", { style: { alignSelf: "start", paddingTop: "6px" } }, t);
  const seccion = (t) => h("div", { class: "fila-previa" }, h("b", null, t));
  const dsKb = (E.kbs.find((k) => k.nombre === s.kb)?.datasources || []).map((d) => d.nombre);
  const script = editorScript(s.scriptPrevio || [], dsKb, { filas: 7, placeholder: "delete from tabla_hija;\ndelete from tabla;" });
  const entre = h("select", null, [
    ["aislados", "Cada caso arranca de cero: de la base que deja el script previo (recomendado)"],
    ["encadenados", "Cada caso sigue de lo que dejó el anterior"],
  ].map(([v, t]) => h("option", { value: v, selected: (op.casosEncadenados ? "encadenados" : "aislados") === v ? "" : null }, t)));
  const notaEntre = h("div", { class: "muted chico", style: { marginTop: "3px" } });
  const notar = () => {
    notaEntre.textContent = entre.value === "encadenados"
      ? "Por ejemplo, el caso 1 crea un cupón y el 2 lo usa. Lo que un caso guarda con «guardar» llega como ${variable} a los casos siguientes. Toda la corrida es una transacción y al final se deshace. Si corrés solo algunos casos, los que dependen de otros pueden fallar."
      : "Cada caso (y cada fila de datos) no ve lo que hicieron los anteriores: se puede correr uno solo o en cualquier orden. Sin script previo, cada caso corre en su propia transacción.";
  };
  entre.addEventListener("change", notar);
  notar();
  modal({
    titulo: "Opciones de la suite", ancho: true,
    cuerpo: h("div", { class: "form-grid" },
      h("label", null, "Nombre"), nombre, h("label", null, "Descripción"), desc, h("label", null, "KB"), kb,
      seccion("Antes de los casos"),
      etq("Script previo"), h("div", null, script,
        nota("SQL que corre ", h("b", null, "una sola vez"), ", antes del primer caso, por ejemplo para dejar vacías las tablas que usan. Al final de la corrida se deshace todo, el script incluido. Usá «delete from»: truncate, drop o alter confirmarían la transacción y no se aceptan.")),
      etq("Preparación de cada caso"), h("div", null, prep,
        nota("Pasos que corren ", h("b", null, "al principio de cada caso"), " (y de cada fila de datos), antes de sus propios pasos y en su misma transacción. Sirven para lo que todos los casos necesitan, por ejemplo dar de alta un registro. Se escriben igual que los pasos de un caso: un ",
          h("code", null, "objeto"), " con su ", h("code", null, "entrada"), ", o un ", h("code", null, "sql"), " con su ", h("code", null, "ds"), ". Con ", h("code", null, "guardar"),
          ", un valor de la salida queda como ", h("code", null, "${variable}"), " para los pasos del caso. No se comparan: solo tienen que terminar bien. Si uno falla, el caso queda en error y no se corre.")),
      etq("Entre un caso y otro"), h("div", null, entre, notaEntre),
      seccion("Datos de los casos"),
      etq("Variables"), h("div", null, vars,
        nota("Valores con nombre que los casos usan escribiendo ", h("code", null, "${nombre}"), " en la entrada, en las consultas SQL, en «esperado» y en las verificaciones (por ejemplo ", h("code", null, '"ItfId": "${itf}"'),
          "). Sirven para no repetir un mismo dato en todos los casos y cambiarlo en un solo lugar."),
        ayudaVariables()),
      seccion("Ejecución y comparación"),
      h("label", null, "Transacción"), tx,
      h("label", null, "Comparación"), h("div", { style: { display: "flex", flexDirection: "column", gap: "4px" } },
        h("label", { class: "chk" }, recortar, "Ignorar espacios al final de los textos (Character de GeneXus)"),
        h("label", { class: "chk" }, listas, "Listas parciales en «esperado»: cada elemento esperado tiene que estar, en cualquier orden")),
      h("label", null, "Tolerancia numérica"), tol,
      h("label", null, "Tiempo máximo por paso (ms)"), tmo),
    botones: [{ texto: "Cancelar" }, {
      texto: "Guardar", prim: true, accion: async () => {
        const v = vars.valor(), p = prep.valor();
        if (v === undefined && vars.textarea.value.trim()) { toast("Variables: JSON inválido", "error"); return false; }
        if (p === undefined && prep.textarea.value.trim()) { toast("Preparación: JSON inválido", "error"); return false; }
        if (v !== undefined && (typeof v !== "object" || v === null || Array.isArray(v))) { toast('Variables: tiene que ser un objeto, por ejemplo {"itf": 1}', "error"); return false; }
        if (p !== undefined && (!Array.isArray(p) || p.some((x) => !x || typeof x !== "object" || !(x.objeto || x.sql)))) {
          toast("Preparación: tiene que ser una lista de pasos [ {...}, {...} ], cada uno con «objeto» o «sql»", "error"); return false;
        }
        const sp = script.valor();
        const enc = entre.value === "encadenados";
        if ((sp.length || enc) && tx.value === "commit") { toast(`Con ${sp.length ? "script previo" : "casos encadenados"} la suite no puede correr con commit: confirmaría todo lo anterior.`, "error"); return false; }
        if (sp.length) s.scriptPrevio = sp; else delete s.scriptPrevio;
        const opciones = { ...(s.opciones || {}), transaccion: tx.value, recortarEspacios: recortar.checked, listasParciales: listas.checked, toleranciaNumerica: Number(tol.value) || 0, timeoutMs: Number(tmo.value) || 120000 };
        if (enc) opciones.casosEncadenados = true; else delete opciones.casosEncadenados;
        Object.assign(s, {
          nombre: nombre.value.trim() || s.nombre, descripcion: desc.value, kb: kb.value, variables: v || {}, preparacion: p || [], opciones,
        });
        await guardarSuite("Opciones guardadas");
      },
    }],
  });
}

function editarJsonSuite() {
  const ed = editorJson(limpiarSuite(E.suite), { filas: 30 });
  modal({
    titulo: `JSON de la suite · ${E.suite._id}`, ancho: true, cuerpo: ed,
    botones: [{ texto: "Cancelar" }, {
      texto: "Guardar", prim: true, accion: async () => {
        const v = ed.valor();
        if (!v) { toast("JSON inválido", "error"); return false; }
        E.suite = { ...v, _id: E.suite._id, _version: E.suite._version, _estado: E.suite._estado };
        await guardarSuite("Suite guardada");
      },
    }],
  });
}

async function duplicarSuite() {
  const nombre = await pedirTexto("Duplicar suite", "Nombre de la copia", E.suite.nombre + " (copia)");
  if (!nombre) return;
  try {
    const r = await api("PUT", "/api/suite", { suite: { ...limpiarSuite(E.suite), nombre } });
    await cargarSuites();
    abrirSuite(r.id);
  } catch (e) { toast(e.message, "error"); }
}

async function borrarSuite() {
  if (!(await confirmar(`¿Eliminar la suite «${E.suite.nombre}»?\nSe mueve a la carpeta .papelera, no se borra del disco.`, { si: "Eliminar", peligro: true }))) return;
  try {
    await api("DELETE", `/api/suite?id=${encodeURIComponent(E.suite._id)}`);
    E.suite = null;
    vaciar($("#detalle-suite"), h("div", { class: "vacio-grande" }, h("h3", null, "Suite eliminada")));
    cargarSuites();
  } catch (e) { toast(e.message, "error"); }
}

// ====================================================================== historial
async function pintarHistorial() {
  const cont = $("#contenido-historial");
  vaciar(cont, cargando());
  let lista;
  try { lista = await GET("/api/corridas"); } catch (e) { vaciar(cont, h("div", { class: "error-caja" }, e.message)); return; }
  const soloKb = h("input", { type: "checkbox", checked: almacen.leer("historialSoloKb", true) });
  const tabla = h("div");
  const pintar = () => {
    almacen.guardar("historialSoloKb", soloKb.checked);
    const ls = lista.filter((c) => !soloKb.checked || c.kb === E.kb);
    vaciar(tabla, ls.length ? h("table", { class: "tabla" },
      h("thead", null, h("tr", null, h("th", null, "Fecha"), h("th", null, "Suite"), h("th", null, "KB"), h("th", null, "Resultado"), h("th", null, "Duración"), h("th", null, ""))),
      h("tbody", null, ls.map((c) => {
        const t = c.totales || {};
        return h("tr", { class: "clic", onclick: () => verCorrida(c.id) },
          h("td", null, fmtFecha(c.fin || c.inicio)),
          h("td", null, h("b", null, c.suiteNombre), h("div", { class: "muted mono chico" }, c.suite)),
          h("td", null, c.kb),
          h("td", null, h("div", { class: "contadores" }, pill(`${t.ok || 0} ok`, "ok"), t.falla ? pill(`${t.falla} fallas`, "falla") : null, t.error ? pill(`${t.error} errores`, "error") : null, t.omitido ? pill(`${t.omitido} omitidos`) : null, c.grabar ? pill("aprobó salidas", "aviso") : null, c.origen === "build" ? pill("después del build", "acento") : null)),
          h("td", { class: "muted" }, fmtMs(c.ms)),
          h("td", null, h("a", { href: `/api/junit?id=${encodeURIComponent(c.id)}`, onclick: (ev) => ev.stopPropagation(), title: "Descargar JUnit XML" }, "JUnit")));
      }))) : h("div", { class: "vacio-grande" }, h("h3", null, "Todavía no hay corridas")));
  };
  soloKb.addEventListener("change", pintar);
  vaciar(cont, h("h2", { class: "titulo" }, "Historial de corridas"),
    h("div", { class: "subtitulo" }, h("label", { class: "chk" }, soloKb, `Solo ${E.kb}`), h("span", { class: "muted chico" }, "Se conservan las últimas 300 en la carpeta resultados.")),
    h("div", { class: "tarjeta" }, h("div", { class: "cuerpo", style: { padding: 0 } }, tabla)));
  pintar();
}

async function verCorrida(id) {
  let c;
  try { c = await obtenerCorrida(id); } catch (e) { toast(e.message, "error"); return; }
  const t = c.totales || {};
  const lista = h("div");
  c.casos.forEach((r) => {
    const det = h("div", { style: { display: "none", padding: "8px 0 4px 18px" } });
    const fila = h("div", { class: "fila", style: { padding: "6px 0", borderBottom: "1px solid var(--borde)", cursor: "pointer" } },
      h("span", { class: `punto-estado ${r.estado}` }), h("b", null, r.nombre), pillEstado(r.estado), h("span", { class: "espacio" }), h("span", { class: "muted chico" }, fmtMs(r.ms)));
    fila.addEventListener("click", () => {
      if (!det.childNodes.length) det.appendChild(vistaResultado(r));
      det.style.display = det.style.display === "none" ? "block" : "none";
    });
    lista.append(fila, det);
  });
  const fallidos = [...new Set(c.casos.filter((r) => ["falla", "error"].includes(r.estado)).map((r) => r.casoId))];
  modal({
    titulo: `${c.suiteNombre} · ${fmtFecha(c.fin)}`, ancho: true,
    cuerpo: h("div", null,
      h("div", { class: "fila", style: { marginBottom: "10px" } }, pill(`${t.ok || 0} ok`, "ok"), pill(`${t.falla || 0} fallas`, t.falla ? "falla" : ""), pill(`${t.error || 0} errores`, t.error ? "error" : ""),
        h("span", { class: "muted" }, `${c.kb} · ${fmtMs(c.ms)}`), h("span", { class: "espacio" }),
        h("a", { class: "btn chico", href: `/api/junit?id=${encodeURIComponent(c.id)}` }, "Descargar JUnit"),
        h("button", { class: "btn chico", onclick: () => descargar(`${c.id}.json`, json(c)) }, "Descargar JSON")),
      vistaScript(c.scriptPrevio),
      lista),
    botones: [
      ...(fallidos.length ? [{ texto: `Volver a correr los ${fallidos.length} fallidos`, accion: async () => { irA("suites"); await abrirSuite(c.suite); correrSuite({ casos: fallidos }); } }] : []),
      { texto: "Abrir la suite", accion: async () => { irA("suites"); abrirSuite(c.suite); } },
      { texto: "Cerrar", prim: true },
    ],
  });
}

// ====================================================================== SQL
function pintarSql() {
  const cont = $("#contenido-sql");
  const k = kbActual();
  if (!k) { vaciar(cont); return; }
  const ds = h("select", null, k.datasources.map((d) => h("option", { value: d.nombre }, `${d.nombre} (${d.base})`)));
  ds.value = almacen.leer(`sqlDs.${E.kb}`, k.datasources[k.datasources.length - 1]?.nombre || "");
  const ta = h("textarea", { class: "codigo", rows: 8, id: "sql-texto", spellcheck: "false", placeholder: "select * from ..." }, almacen.leer(`sqlTexto.${E.kb}`, ""));
  const max = h("input", { type: "number", value: 500, style: { width: "90px" } });
  const res = h("div", { id: "sql-resultado" });
  const historial = h("div");
  const pintarHistorialSql = () => {
    const hs = almacen.leer(`sqlHist.${E.kb}`, []);
    vaciar(historial, hs.length ? hs.map((q) => h("div", { class: "item", style: { padding: "6px 10px", borderBottom: "1px solid var(--borde)", cursor: "pointer" }, onclick: () => { ta.value = q.q; ds.value = q.ds; } },
      h("div", { class: "mono chico", style: { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } }, q.q.length > 200 ? q.q.slice(0, 200) + "…" : q.q), h("div", { class: "muted chico" }, q.ds))) : h("div", { class: "muted chico", style: { padding: "10px" } }, "Las consultas que corras aparecen acá."));
  };
  pintarHistorialSql();
  E.correrSqlActual = async () => {
    const q = ta.value.trim();
    if (!q) return;
    almacen.guardar(`sqlTexto.${E.kb}`, ta.value);
    almacen.guardar(`sqlDs.${E.kb}`, ds.value);
    vaciar(res, cargando("Consultando…"));
    try {
      const r = await POST("/api/sql", { kb: E.kb, ds: ds.value, query: q, max: Number(max.value) || 500 });
      const hs = almacen.leer(`sqlHist.${E.kb}`, []).filter((x) => x.q !== q);
      hs.unshift({ q, ds: ds.value }); almacen.guardar(`sqlHist.${E.kb}`, hs.slice(0, 40));
      pintarHistorialSql();
      if (r.filas) {
        const csv = () => [r.columnas.join(";"), ...r.filas.map((f) => r.columnas.map((c) => { const v = f[c]; const s = v === null ? "" : String(v); return /[;"\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(";"))].join("\n");
        vaciar(res, h("div", { class: "fila", style: { marginBottom: "8px" } }, pill(`${r.cantidad} filas${r.truncado ? " (truncado)" : ""}`, "acento"), h("span", { class: "muted chico" }, fmtMs(r.ms)), h("span", { class: "espacio" }),
          h("button", { class: "btn chico", onclick: () => copiar(csv()) }, "Copiar CSV"), h("button", { class: "btn chico", onclick: () => copiar(json(r.filas)) }, "Copiar JSON")),
        tablaFilas(r.columnas, r.filas));
      } else vaciar(res, h("div", { class: "aviso-caja" }, `${r.actualizadas} filas afectadas. Se hizo rollback: no quedó nada grabado.`));
    } catch (e) { vaciar(res, h("div", { class: "error-caja" }, e.message)); }
    refrescarMotor();
  };
  vaciar(cont, h("h2", { class: "titulo" }, `Consultas SQL · ${E.kb}`),
    h("div", { class: "subtitulo" }, h("span", { class: "muted" }, "Usa la conexión del motor Java (la misma configuración que la aplicación). Toda consulta corre en una transacción que se descarta.")),
    h("div", { style: { display: "grid", gridTemplateColumns: "minmax(0,1fr) 300px", gap: "14px", alignItems: "start" } },
      h("div", null, h("div", { class: "tarjeta" }, h("div", { class: "cuerpo" }, ta,
        h("div", { class: "fila", style: { marginTop: "8px" } }, "Datasource", ds, "Máx. filas", max, h("span", { class: "espacio" }), h("span", { class: "muted chico" }, h("kbd", null, "Ctrl"), "+", h("kbd", null, "Enter")),
          h("button", { class: "btn prim", onclick: correrSql }, "▶ Consultar")))),
      h("div", { class: "tarjeta" }, h("div", { class: "cuerpo" }, res))),
      h("div", { class: "tarjeta" }, h("div", { class: "cab" }, h("h3", null, "Recientes")), h("div", { style: { maxHeight: "70vh", overflow: "auto" } }, historial))));
}
function correrSql() { E.correrSqlActual && E.correrSqlActual(); }

// ====================================================================== ayuda
let ayudaPintada = false;
async function pintarAyuda() {
  if (ayudaPintada) return;
  const cont = $("#contenido-ayuda");
  let ops = {};
  try { ops = (await GET("/api/ayuda")).operadores; } catch { /* sin conexion */ }
  ayudaPintada = true;
  const ej = (t) => h("pre", { class: "bloque" }, t);
  vaciar(cont, h("div", { style: { maxWidth: "980px" } },
    h("h2", { class: "titulo" }, "Cómo funciona GxPruebas"),
    h("p", null, botonTutorial("🎓 Tutorial animado: cómo armar pruebas que no dependen de la base", "btn")),
    h("p", null, "GxPruebas ejecuta las clases Java que generó GeneXus, sin pasar por el IDE ni por Tomcat. Lee la especificación (",
      h("code", null, "GXSPC…\\NVG"), ") para saber los objetos y sus parámetros, y usa el ", h("code", null, "client.cfg"), " de la KB para conectarse a la base. ",
      "Cada caso corre en una transacción que por defecto se deshace al final: podés dar de alta, modificar y borrar sin dejar rastros."),
    h("div", { class: "aviso-caja" }, "⚠ Si un procedimiento tiene ", h("b", null, "Commit on exit = Yes"), " o hace ", h("code", null, "Commit"), ", sus cambios quedan grabados aunque el caso haga rollback. GxPruebas lo avisa con «hace commit». Con script previo no pasa: ese commit se simula y no llega a la base."),
    h("h3", null, "Script previo: casos que no dependen de los datos"),
    h("p", null, "Para que las salidas no cambien según lo que haya en la base, la suite puede tener un ", h("b", null, "script previo"),
      " (Suites → Más → Opciones): sentencias que dejan la base en un estado conocido, por ejemplo vacía (",
      h("code", null, "delete from tabla_hija; delete from tabla;"), "). Toda la corrida es una sola transacción:"),
    h("ol", null,
      h("li", null, "El script corre una sola vez, al empezar."),
      h("li", null, "Cada caso (y cada fila de ", h("code", null, "datos"), ") arranca de la base que dejó el script y, al terminar, vuelve a ella: no ve lo que hicieron los casos anteriores, así que se puede correr uno solo, los fallidos o en cualquier orden. Con ", h("b", null, "casos encadenados"), " (en las mismas opciones), cada caso sigue de lo que dejó el anterior: el 1 crea un cupón y el 2 lo usa."),
      h("li", null, "Al final se deshace todo, el script incluido: la base queda como estaba.")),
    h("p", null, "Mientras tanto, el commit y el rollback de los objetos se simulan (no llegan a la base): los objetos que hacen commit se pueden probar igual. Lo que corre en otra unidad de trabajo (", h("i", null, "Execute in new LUW"), ", como PrcLog) usa otra conexión y no toca esta transacción. No se aceptan ",
      h("code", null, "truncate"), ", ", h("code", null, "drop"), " ni ", h("code", null, "alter"), " (en MySQL confirman la transacción) ni casos con commit. En ", h("b", null, "Explorar"),
      ", el ", h("b", null, "SQL previo"), " hace lo mismo antes de cada ejecución, y «Copiar de una suite» trae el script de una suite."),
    h("h3", null, "Flujo de trabajo"),
    h("ol", null,
      h("li", null, "Compilá la KB en GeneXus (Build). El motor detecta la recompilación y se reinicia solo."),
      h("li", null, h("b", null, "Explorar"), ": elegí el objeto, completá la entrada (formulario o JSON) y ejecutá. Agregá consultas SQL para ver qué cambió en la base."),
      h("li", null, h("b", null, "Guardar como caso"), ": la salida que viste queda aprobada. Lo que cambia solo (fechas, ids nuevos) se detecta ejecutando una vez más. Marcá lo que además tiene que cumplirse siempre (Ok y los códigos ya vienen marcados)."),
      h("li", null, h("b", null, "Suites"), ": corré todo después de cada cambio (o dejá que corra solo después de cada build). Abrí un caso para ver «Qué controla» cada paso (salida aprobada, verificaciones, campos que no se comparan) y cambiarlo ahí mismo. Si algo cambió: si es correcto, aceptá la salida; si es un campo que puede cambiar, dejá de compararlo.")),
    h("h3", null, "Formato de un caso"),
    ej(`{
  "nombre": "Alta y consulta",
  "etiquetas": ["alta"],
  "datos": [ {"tipo": "AAA"}, {"tipo": "BBB"} ],          // opcional: se repite por fila
  "pasos": [
    { "nombre": "Alta",
      "objeto": "Generales.Interfases.Registro.Set",
      "entrada": { "inSet": { "ItfId": "\${itf}", "Tipo": "\${tipo}" } },
      "esperado": { "outSet": { "Output": { "Ok": true } } },
      "verificaciones": [ { "ruta": "outSet.Output.Messages[*].Code", "op": "contiene", "valor": "OK" } ],
      "guardar": { "regTipo": "outSet.RegTipo" } },
    { "nombre": "Quedó grabado",
      "sql": "select count(*) as n from gntItfRegistro where ItfRegTipo = '\${regTipo}'",
      "ds": "GENERALES",
      "verificaciones": [ { "ruta": "filas[0].n", "op": "igual", "valor": 1 } ] }
  ]
}`),
    h("h3", null, "Formas de validar"),
    h("table", { class: "tabla" }, h("tbody", null,
      h("tr", null, h("td", null, h("code", null, "esperado")), h("td", null, "Coincidencia ", h("b", null, "parcial"), ": solo se controla lo que escribís. Ideal para «Output.Ok = true».")),
      h("tr", null, h("td", null, h("code", null, "verificaciones")), h("td", null, "Reglas sobre rutas: ", h("code", null, "{ruta, op, valor, cada}"), ". Con ", h("code", null, "[*]"), " la ruta devuelve todos los elementos; con ", h("code", null, "\"cada\": true"), " la regla se aplica a cada uno.")),
      h("tr", null, h("td", null, h("code", null, "lineaBase")), h("td", null, "La ", h("b", null, "salida aprobada"), ". Por defecto tiene que coincidir toda; con ", h("code", null, "\"comparar\": \"estructura\""), " (para listados con datos que cambian) solo los campos, sus tipos, ", h("code", null, "Ok"), " y los códigos de mensaje. Un campo nuevo es un aviso, no una falla, y una colección que GeneXus omite por vacía cuenta como vacía. En ", h("code", null, "volatiles"), " (se detectan solos) solo se controla el tipo; ", h("code", null, "ignorar"), " no se compara.")),
      h("tr", null, h("td", null, h("code", null, "esperaError")), h("td", null, "El paso tiene que terminar con una excepción (opcional ", h("code", null, "errorContiene"), ")."))),
    ),
    h("h3", null, "Operadores"),
    h("table", { class: "tabla" }, h("tbody", null, Object.entries(ops).map(([k, v]) => h("tr", null, h("td", { class: "mono" }, k), h("td", null, v))))),
    h("h3", null, "Comodines en «esperado» y «lineaBase»"),
    h("p", null, ["<<cualquiera>>", "<<no_vacio>>", "<<vacio>>", "<<numero>>", "<<texto>>", "<<booleano>>", "<<fecha>>", "<<fechahora>>", "<<regex:^A\\d+$>>", "<<contiene:texto>>", "<<empieza:texto>>", "<<mayor:0>>", "<<menor:100>>", "<<distinto:valor>>"].map((x) => [h("code", null, x), " "])),
    h("h3", null, "Variables"),
    h("p", null, h("code", null, "${nombre}"), " se reemplaza por: las ", h("b", null, "variables"), " de la suite, la fila de ", h("b", null, "datos"), ", lo que se ", h("b", null, "guardó"), " en pasos anteriores, la salida completa de un paso anterior (", h("code", null, "${alta.outSet.RegTipo}"), ", con el nombre del paso en minúsculas y _ en vez de espacios), lo que se le mandó a un paso anterior (", h("code", null, "${alta.entrada.inSet.Tipo}"), ": por ejemplo, que el Get devuelva lo que recibió el Set) y las predefinidas ",
      h("code", null, "${hoy}"), " ", h("code", null, "${ahora}"), " ", h("code", null, "${aleatorio}"), " ", h("code", null, "${uuid}"), " ", h("code", null, "${caso}"), ". ",
      "Se calculan al ejecutar, así que siguen valiendo aunque la base cambie: ", h("code", null, "${siguiente.CuponId}"), " (el último + 1: no existe), ", h("code", null, "${existente.CuponId}"), ", ",
      h("code", null, "${ultimo.CuponId}"), ", ", h("code", null, "${existente.CuponId|CuponEstado=PENDIENTE}"), ", ", h("code", null, "${con_hijos.CuponId}"), ", ", h("code", null, "${sin_hijos.CuponId}"),
      " y las fechas ", h("code", null, "${hoy+30}"), " ", h("code", null, "${fin_mes}"), " ", h("code", null, "${habil_siguiente}"), " ", h("code", null, "${fecha_vacia}"),
      ". Si el texto es solo la variable, se conserva su tipo (número, objeto…)."),
    h("p", null, "En Explorar, ", h("b", null, "Generar validaciones…"), " parte de una entrada que termina bien y propone una fila por campo vacío, por valor de su dominio, por lista vacía y por id que no existe. Las ejecuta (con rollback), muestra qué devuelve hoy cada una y guarda las elegidas como un caso con «datos» que verifica Ok y el código (o el mensaje) de cada fila. En una verificación, ",
      h("code", null, '"omitirSiVacio": true'), " hace que no se controle si su valor queda vacío (la fila no tiene código)."),
    h("p", null, "Lo que se guarda con ", h("code", null, "guardar"), " llega a los pasos siguientes del mismo caso. Con ", h("b", null, "casos encadenados"),
      " (Opciones de la suite → Entre un caso y otro), también a los casos que corren después: el caso 1 guarda ", h("code", null, "${cupon}"), " y el caso 2 lo usa. Para guardar un valor, hacé clic en él en la salida del caso → «Guardar como variable»."),
    ayudaVariables(),
    h("h3", null, "Línea de comandos"),
    ej(`python gxpruebas.py correr                         todas las suites (código de salida 1 si algo falla)
python gxpruebas.py correr interfases-registro --detalle
python gxpruebas.py correr --kb Generales --junit resultados.xml
python gxpruebas.py correr interfases --grabar      aprueba las salidas actuales (corre dos veces cada caso)
python gxpruebas.py ejecutar --kb Generales --objeto Generales.Interfases.Registro.List --entrada "{\\"inList\\":{\\"ItfId\\":1}}"
python gxpruebas.py describir --kb Generales --objeto Generales.Interfases.Registro.Set
python gxpruebas.py sql --kb Generales --ds GENERALES "select * from gntInterfase"`),
    h("h3", null, "Atajos"),
    h("p", null, h("kbd", null, "/"), " buscar · ", h("kbd", null, "Ctrl"), "+", h("kbd", null, "Enter"), " ejecutar (Explorar y SQL) · ", h("kbd", null, "Esc"), " cerrar ventanas")));
}

iniciar();
