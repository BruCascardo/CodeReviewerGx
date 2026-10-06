/* GxPruebas - pantalla Revisión: los objetos ordenados por la fecha de su especificación (lo recién
   modificado primero), con los hallazgos del revisor de buenas prácticas (gxp/revisor/panel.py). */
"use strict";

const RV = {
  filtro: almacen.leer("revision.filtro", "todos"),   // todos | problemas | nuevos
  todas: almacen.leer("revision.todas", false),       // todas las KBs o la elegida arriba
  texto: "",
  abiertos: new Set(),                                // "kb|objeto" desplegados
  pedido: 0,                                          // descarta respuestas viejas
  siguiente: null,
  armada: false,
};

const SEVERIDAD = { error: "Error", advertencia: "Advertencia" };

// "hace 5 min", "hace 3 h", "ayer 14:07", "02/10 09:15"
function haceCuanto(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return iso || "";
  const min = Math.round((Date.now() - d) / 60000);
  if (min < 1) return "recién";
  if (min < 60) return `hace ${min} min`;
  if (min < 12 * 60 && d.toDateString() === new Date().toDateString()) return `hace ${Math.round(min / 60)} h`;
  const hora = d.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hour12: false });
  const g = grupoFecha(iso);
  if (g === "Hoy") return `hoy ${hora}`;
  if (g === "Ayer") return `ayer ${hora}`;
  const anio = d.getFullYear() !== new Date().getFullYear() || g === "Antes" ? "numeric" : undefined;
  return `${d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit", year: anio })} ${hora}`;
}

function grupoFecha(iso) {
  const d = new Date(iso);
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const dias = Math.floor((hoy - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 86400000);
  if (dias <= 0) return "Hoy";
  if (dias === 1) return "Ayer";
  if (dias < 7) return "Esta semana";
  if (dias < 31) return "Este mes";
  return "Antes";
}

function armarRevision() {
  const cont = $("#contenido-revision");
  const buscar = h("input", { type: "search", id: "rv-buscar", placeholder: "Buscar objeto…  ( / )", autocomplete: "off", style: { width: "260px" } });
  let espera;
  buscar.addEventListener("input", () => { clearTimeout(espera); espera = setTimeout(() => { RV.texto = buscar.value; cargarRevision(); }, 250); });
  const filtros = h("div", { class: "grupo-seg" }, [["todos", "Todos"], ["problemas", "Con problemas"], ["nuevos", "Nuevos"]].map(([f, t]) =>
    h("button", { class: RV.filtro === f ? "activa" : "", dataset: { f }, onclick: (ev) => {
      RV.filtro = f; almacen.guardar("revision.filtro", f);
      $$("button", ev.target.parentNode).forEach((b) => b.classList.toggle("activa", b.dataset.f === f));
      cargarRevision();
    } }, t)));
  const todas = h("input", { type: "checkbox", checked: RV.todas });
  todas.addEventListener("change", () => { RV.todas = todas.checked; almacen.guardar("revision.todas", RV.todas); cargarRevision(); });
  vaciar(cont,
    h("h2", { class: "titulo" }, "Revisión de buenas prácticas"),
    h("div", { class: "subtitulo" }, buscar, filtros, h("label", { class: "chk" }, todas, "Todas las KBs"), h("span", { class: "espacio" }),
      h("span", { class: "muted chico", id: "rv-info" }),
      h("button", { class: "btn chico", id: "rv-revisar", onclick: revisarCambios, title: "Revisa lo que cambió desde la última revisión y deja la línea base al día (lo mismo que hace solo el build)" }, "Revisar cambios")),
    h("div", { class: "muted chico", style: { margin: "-4px 0 12px" } },
      "Los objetos se ordenan por la fecha de su especificación: lo recién modificado (o compilado) aparece primero. ",
      h("b", null, "Nuevo"), " es lo que introdujo la última modificación del objeto."),
    h("div", { id: "rv-lista" }),
    h("div", { id: "rv-pie", style: { textAlign: "center", marginTop: "10px" } }));
  RV.armada = true;
}

async function pintarRevision() {
  if (!RV.armada) armarRevision();
  await cargarRevision();
}

function paramsRevision(desde = 0) {
  const q = { filtro: RV.filtro, desde, texto: RV.texto || "" };
  if (RV.todas) q.todas = 1; else q.kb = E.kb;
  return q;
}

async function cargarRevision(mas = false) {
  const lista = $("#rv-lista"), pie = $("#rv-pie");
  const n = ++RV.pedido;
  if (!mas) vaciar(lista, h("div", { class: "vacio-grande" }, cargando("Revisando los objetos recién modificados…")));
  else vaciar(pie, cargando());
  let r;
  try { r = await GET("/api/revision", paramsRevision(mas ? RV.siguiente : 0)); } catch (e) {
    if (n === RV.pedido) vaciar(lista, h("div", { class: "error-caja" }, e.message));
    return;
  }
  if (n !== RV.pedido) return;
  RV.siguiente = r.siguiente;
  pintarInfoRevision(r);
  if (!mas) vaciar(lista);
  if (!mas && !r.objetos.length) {
    const que = { todos: "objetos revisables", problemas: "objetos con problemas", nuevos: "problemas nuevos" }[RV.filtro];
    agregar(lista, [h("div", { class: "vacio-grande" }, h("h3", null, `No hay ${que}`), h("div", null, RV.texto ? `que coincidan con «${RV.texto}».` : RV.filtro === "nuevos" ? "La última modificación de cada objeto no introdujo problemas." : ""))]);
  }
  let grupo = mas ? lista.dataset.grupo : null;
  for (const o of r.objetos) {
    const g = grupoFecha(o.fecha);
    if (g !== grupo) { lista.appendChild(h("div", { class: "rv-grupo" }, g)); grupo = g; }
    lista.appendChild(filaObjetoRevision(o));
  }
  lista.dataset.grupo = grupo || "";
  vaciar(pie, r.siguiente != null ? h("button", { class: "btn", onclick: () => cargarRevision(true) }, "Cargar más") : null);
}

function pintarInfoRevision(r) {
  const cambiados = r.kbs.reduce((s, k) => s + (k.cambiados || 0), 0);
  const sinBase = r.kbs.filter((k) => !k.lineaBase).map((k) => k.kb);
  const ultima = r.kbs.map((k) => k.lineaBase).filter(Boolean).sort().pop();
  const info = $("#rv-info");
  vaciar(info,
    sinBase.length ? pill(`sin línea base: ${sinBase.join(", ")}`, "aviso") : null, " ",
    ultima ? `Última revisión ${haceCuanto(ultima)}` : "", " · reglas: ", r.reglas.join(", "));
  info.title = r.kbs.map((k) => `${k.kb}: ${k.lineaBase ? "revisada " + fmtFecha(k.lineaBase) : "sin línea base"}${k.cambiados ? ` · ${k.cambiados} especificaciones cambiaron después` : ""}`).join("\n");
  const btn = $("#rv-revisar");
  btn.textContent = cambiados ? `Revisar cambios (${cambiados})` : "Revisar cambios";
  btn.classList.toggle("prim", cambiados > 0);
  for (const a of r.avisos || []) toast(a, "aviso");
}

function contadoresRevision(o) {
  const e = o.hallazgos.filter((x) => x.severidad === "error").length;
  const a = o.hallazgos.length - e;
  const nuevos = o.hallazgos.filter((x) => x.nuevo).length;
  return h("div", { class: "contadores" },
    nuevos ? pill(`${nuevos} nuevo${nuevos > 1 ? "s" : ""}`, "acento") : null,
    e ? pill(`${e} error${e > 1 ? "es" : ""}`, "error") : null,
    a ? pill(`${a} advertencia${a > 1 ? "s" : ""}`, "aviso") : null,
    !o.hallazgos.length && !o.errores.length ? pill("sin problemas", "ok") : null,
    o.excepcionados ? pill(`${o.excepcionados} con excepción`) : null,
    o.errores.length ? pill("no se pudo revisar", "falla") : null);
}

function filaObjetoRevision(o) {
  const clave = `${o.kb}|${o.objeto}`;
  const e = o.hallazgos.some((x) => x.severidad === "error");
  const estado = o.errores.length ? "falla" : e ? "error" : o.hallazgos.length ? "aviso" : "ok";
  const det = h("div", { class: "rv-det" });
  const fila = h("div", { class: "rv-obj" + (o.hallazgos.some((x) => x.nuevo) ? " nuevo" : "") },
    h("div", { class: "rv-cab", onclick: () => {
      const abierto = !RV.abiertos.has(clave);
      abierto ? RV.abiertos.add(clave) : RV.abiertos.delete(clave);
      det.style.display = abierto ? "block" : "none";
      if (abierto && !det.childNodes.length) agregar(det, [detalleObjetoRevision(o)]);
    } },
      h("span", { class: `punto-estado ${estado}` }),
      h("div", { class: "rv-nombre" }, h("b", null, corto(o.objeto)), h("span", { class: "muted chico" }, ` ${modulo(o.objeto)}`)),
      h("span", { class: "muted chico" }, o.tipo),
      RV.todas ? pill(o.kb) : null,
      contadoresRevision(o),
      h("span", { class: "espacio" }),
      o.cambio ? h("span", { class: "muted chico", title: "Se especificó después de la última revisión: se muestra revisado ahora." }, "● sin revisar en un build ") : null,
      h("span", { class: "muted chico rv-fecha", title: `Especificado el ${fmtFecha(o.fecha)}` }, haceCuanto(o.fecha))),
    det);
  if (RV.abiertos.has(clave)) { det.style.display = "block"; agregar(det, [detalleObjetoRevision(o)]); }
  else det.style.display = "none";
  return fila;
}

function lineaHallazgo(x, conDetalle = true) {
  return h("div", { class: `rv-hallazgo ${x.severidad}` },
    h("div", { class: "fila" },
      pill(SEVERIDAD[x.severidad] || x.severidad, x.severidad === "error" ? "error" : "aviso"),
      x.nuevo ? pill("Nuevo", "acento") : null,
      h("span", { class: "muted chico mono" }, x.linea ? `línea ${x.linea}` : "propiedad"),
      h("span", null, x.mensaje),
      h("span", { class: "muted chico" }, `[${x.regla}]`)),
    x.codigo ? h("div", { class: "mono rv-codigo" }, x.codigo) : null,
    conDetalle && x.detalle ? h("div", { class: "muted chico" }, x.detalle) : null);
}

// El "como se arregla" de cada regla se muestra una sola vez por objeto (en el primer hallazgo que lo trae).
function hallazgosSinRepetir(hs) {
  const vistos = new Set();
  return hs.map((x) => { const nuevo = !vistos.has(x.detalle); vistos.add(x.detalle); return lineaHallazgo(x, nuevo); });
}

function detalleObjetoRevision(o) {
  const ejecutable = o.kb === E.kb && E.objetos.some((x) => x.nombre === o.objeto);
  return h("div", null,
    o.errores.map((e) => h("div", { class: "error-caja" }, e)),
    o.hallazgos.length ? hallazgosSinRepetir(o.hallazgos) : h("div", { class: "muted chico", style: { padding: "4px 0" } }, "Cumple todas las reglas activas."),
    h("div", { class: "fila", style: { marginTop: "8px" } },
      h("button", { class: "btn chico", onclick: () => verFuenteRevision(o.kb, o.objeto) }, "Ver fuente"),
      ejecutable ? h("button", { class: "btn chico", onclick: () => { irA("explorar"); seleccionarObjeto(o.objeto); } }, "Abrir en Explorar") : null,
      h("button", { class: "btn chico fantasma", onclick: () => { copiar(`python gxpruebas.py revisar --kb ${o.kb} --objeto ${o.objeto} --detalle`); toast("Comando copiado", "ok"); } }, "Copiar comando")));
}

async function verFuenteRevision(kb, objeto) {
  let f;
  try { f = await GET("/api/revision/fuente", { kb, objeto }); } catch (e) { toast(e.message, "error"); return; }
  const porLinea = {};
  for (const x of f.hallazgos) (porLinea[x.linea] = porLinea[x.linea] || []).push(x);
  const propiedades = porLinea[0] || [];
  let primera = null;
  const codigo = h("div", { class: "rv-fuente mono" }, f.lineas.map((l) => {
    const hs = porLinea[l.linea];
    const sev = hs ? (hs.some((x) => x.severidad === "error") ? "error" : "advertencia") : "";
    const fila = h("div", { class: `rv-linea ${sev}` },
      h("span", { class: "rv-num" }, l.linea),
      h("span", { class: "rv-txt", style: { paddingLeft: `${l.nivel * 2}ch` } }, l.texto));
    if (hs && !primera) primera = fila;
    return hs ? [fila, ...hs.map((x) => h("div", { class: `rv-nota ${x.severidad}` }, `${x.nuevo ? "NUEVO · " : ""}${x.mensaje}  [${x.regla}]`))] : fila;
  }).flat());
  modal({
    titulo: `${f.objeto} · ${f.tipo}`, ancho: true,
    cuerpo: h("div", null,
      h("div", { class: "fila muted chico", style: { marginBottom: "8px" } },
        h("span", { class: "mono" }, `parm(${f.parametros.map((p) => `${p.io} &${p.nombre}`).join(", ")})`),
        f.commitOnExit != null ? h("span", null, `Commit on exit: ${f.commitOnExit ? "Yes" : "No"}`) : null,
        h("span", null, `Especificado ${haceCuanto(f.fecha)}`), h("span", { class: "espacio" }), pill(f.kb)),
      hallazgosSinRepetir(propiedades),
      f.excepcionados.length ? h("div", { class: "muted chico", style: { margin: "6px 0" } }, `${f.excepcionados.length} hallazgo(s) cubiertos por excepciones de revisor.json: ${[...new Set(f.excepcionados.map((x) => x.motivo))].join(" · ")}`) : null,
      codigo,
      h("div", { class: "muted chico", style: { marginTop: "6px" } }, "Fuente reconstruido de la especificación. Las condiciones Where de los For Each no vienen en ella.")),
    botones: [{ texto: "Cerrar", prim: true }],
  });
  if (primera) setTimeout(() => primera.scrollIntoView({ block: "center" }), 50);
}

async function revisarCambios() {
  const btn = $("#rv-revisar");
  btn.disabled = true;
  const txt = btn.textContent;
  btn.textContent = "Revisando…";
  try {
    const r = await POST("/api/revision/revisar", RV.todas ? { todas: true } : { kb: E.kb });
    const revisados = r.reduce((s, x) => s + x.revisados, 0);
    const nuevos = r.reduce((s, x) => s + (x.nuevos.error || 0) + (x.nuevos.advertencia || 0), 0);
    toast(revisados ? `Revisados ${revisados} objetos cambiados: ${nuevos ? `${nuevos} problemas nuevos` : "nada nuevo"}` : "No hay objetos cambiados desde la última revisión", nuevos ? "error" : "ok");
  } catch (e) { toast(e.message, "error"); }
  btn.disabled = false;
  btn.textContent = txt;
  cargarRevision();
}
