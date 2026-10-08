/* GxPruebas - pantalla Grafo: objetos y relaciones de todas las KBs. */
"use strict";

const G = {
  datos: null,        // {nodos, aristas, kbs, version}
  version: -1,
  sal: [], ent: [],   // por nodo: [[destino, tipo, origen], ...] salientes y entrantes
  modo: almacen.leer("grafo.modo", "objetos"),   // objetos | modulos
  filtroKbs: new Set(almacen.leer("grafo.kbs", [])),
  tipos: new Set(almacen.leer("grafo.tipos", ["Procedure", "DataProvider", "Transaction", "Web Panel", "API", "SDT", "Dominio", "Tabla"])),
  relaciones: new Set(almacen.leer("grafo.rel", ["llama", "transaccion", "sdt", "lee", "escribe"])),
  ocultarGenerados: almacen.leer("grafo.ocultarGen", true),
  verFixes: almacen.leer("grafo.fixes", false),
  soloOtrasKbs: almacen.leer("grafo.soloOtras", false),   // el dibujo muestra solo lo de otras KBs
  foco: null,         // {tipo: "n"|"m", id}
  historial: [],
  cy: null,
  mod: null,          // agregado por modulo (se recalcula al cambiar filtros)
  cargando: false,
};

const TIPOS_GRAFO = [["Procedure", "Proc"], ["DataProvider", "DP"], ["Transaction", "Trn"], ["Web Panel", "WP"], ["API", "API"],
  ["SDT", "SDT"], ["Dominio", "Dom"], ["Tabla", "Tabla"]];
const RELACIONES = [["llama", "llama"], ["servicio", "vía sitServicio", "Lo llama pasando el id del servicio (tabla sitServicio), no directamente"],
  ["transaccion", "transacción / BC"], ["sdt", "usa SDT"], ["lee", "lee tabla"], ["escribe", "escribe tabla"]];
// Las relaciones que no existian cuando se guardo el filtro arrancan activas.
for (const [r] of RELACIONES) if (!almacen.leer("grafo.relVistas", ["llama", "transaccion", "sdt", "lee", "escribe"]).includes(r)) G.relaciones.add(r);
const COLORES_KB = ["#2f6fed", "#1f9d55", "#d97706", "#b4277c", "#7c3aed", "#0891b2", "#dc2626", "#65a30d", "#c2410c", "#475569", "#db2777", "#0d9488"];
const MAX_COLUMNA = 40;   // mas que esto en una columna se agrupa por modulo

// ---------------------------------------------------------------------- datos

const N = (i) => G.datos.nodos[i];  // [kb, nombre, tipo, modulo, descripcion, origen, generado]
const kbBase = (kb) => (kb || "").replace(/_Fixes\w*$/i, "");
const esFixes = (kb) => /_Fixes/i.test(kb || "");
// Un objeto de otra KB que el foco (las tablas no cuentan): es lo que el grafo tiene que hacer ver.
const esExterna = (j, kbFoco) => !!N(j)[0] && N(j)[0] !== kbFoco && N(j)[2] !== "Tabla";
const textoRel = (it) => it.t === "servicio" ? `vía sitServicio${it.s ? ` (${it.s})` : ""}` : it.t;

function colorKb(kb) {
  if (!kb) return "#8b93a2";
  const lista = [...new Set(Object.keys(G.datos.kbs).map(kbBase))].sort();
  return COLORES_KB[lista.indexOf(kbBase(kb)) % COLORES_KB.length];
}

async function cargarGrafo(silencioso = false) {
  if (G.cargando) return;
  G.cargando = true;
  if (!silencioso) vaciar($("#grafo-lista"), h("div", { class: "vacio" }, cargando("Armando el grafo de todas las KBs (la primera vez tarda unos segundos)…")));
  try {
    const d = await GET("/api/grafo");
    G.datos = d;
    G.version = d.version;
    const n = d.nodos.length;
    G.sal = Array.from({ length: n }, () => []);
    G.ent = Array.from({ length: n }, () => []);
    for (const [a, b, t, o, s] of d.aristas) { G.sal[a].push([b, t, o, s]); G.ent[b].push([a, t, o, s]); }
    if (!G.filtroKbs.size) Object.keys(d.kbs).filter((k) => !esFixes(k)).forEach((k) => G.filtroKbs.add(k));
    G.mod = null;
    pintarFiltrosGrafo();
    buscarGrafo();
    if (G.foco) enfocar(G.foco, false);
    else pintarInicioGrafo();
  } catch (e) {
    vaciar($("#grafo-lista"), h("div", { class: "vacio" }, "No se pudo cargar el grafo: " + e.message));
  } finally {
    G.cargando = false;
  }
}

// Se rearma solo despues de cada build: la pantalla se entera consultando la version.
async function vigilarGrafo() {
  if (document.hidden || E.vista !== "grafo" || !G.datos) return;
  try {
    const est = await GET("/api/grafo/estado");
    $("#grafo-estado").textContent = est.armando ? `actualizando ${est.armando}…` : "";
    if (est.version !== G.version && !est.armando) {
      await cargarGrafo(true);
      const c = est.ultimoCambio;
      if (c) toast(`Grafo actualizado después del build de ${c.kbs.join(", ")}`, "ok");
    }
  } catch { /* sin servidor: se reintenta */ }
}

function visible(i) {
  const [kb, nombre, tipo, , , , gen] = N(i);
  if (tipo === "Tabla") return G.tipos.has("Tabla") && (!kb || G.filtroKbs.has(kb));
  if (!G.filtroKbs.has(kb)) return false;
  if (G.ocultarGenerados && gen) return false;
  return G.tipos.has(tipo) || !TIPOS_GRAFO.some(([t]) => t === tipo);
}

function vecinos(i, dir) {
  const lista = dir === "sal" ? G.sal[i] : G.ent[i];
  const vistos = new Map();
  for (const [j, t, o, s] of lista) {
    if (!G.relaciones.has(t) || !visible(j)) continue;
    const prev = vistos.get(j);
    if (!prev) vistos.set(j, { j, t, o, s });
    else if (!prev.o.includes("L") && o.includes("L")) vistos.set(j, { j, t, o, s });
  }
  return [...vistos.values()];
}

// ---------------------------------------------------------------------- filtros y busqueda

function pintarFiltrosGrafo() {
  const chips = (lista, activos, alCambiar) => lista.map(([v, t, titulo]) => h("button", {
    class: activos.has(v) ? "activa" : "", title: titulo || "",
    onclick: (ev) => { activos.has(v) ? activos.delete(v) : activos.add(v); ev.currentTarget.classList.toggle("activa"); alCambiar(); },
  }, t));
  const kbsLista = Object.keys(G.datos.kbs).filter((k) => G.verFixes || !esFixes(k)).sort();
  const alCambiar = () => { guardarFiltrosGrafo(); G.mod = null; buscarGrafo(); if (G.foco) enfocar(G.foco, false); };
  vaciar($("#grafo-filtros"),
    h("div", { class: "fila-filtro" }, h("span", { class: "etq" }, "KBs"),
      h("div", { class: "filtros" }, kbsLista.map((k) => {
        const b = h("button", { class: G.filtroKbs.has(k) ? "activa" : "", title: infoKb(k),
          onclick: (ev) => { G.filtroKbs.has(k) ? G.filtroKbs.delete(k) : G.filtroKbs.add(k); ev.currentTarget.classList.toggle("activa"); alCambiar(); } },
        h("span", { class: "punto-kb", style: { background: colorKb(k) } }), k.replace(/_Fixes\w*/i, " (fix)"));
        return b;
      }))),
    h("div", { class: "fila-filtro" }, h("span", { class: "etq" }, "Tipos"), h("div", { class: "filtros" }, chips(TIPOS_GRAFO, G.tipos, alCambiar))),
    h("div", { class: "fila-filtro" }, h("span", { class: "etq" }, "Relac."), h("div", { class: "filtros" }, chips(RELACIONES, G.relaciones, alCambiar))),
    h("div", { class: "fila" },
      h("label", { class: "chk chico" }, h("input", { type: "checkbox", checked: G.ocultarGenerados,
        onchange: (ev) => { G.ocultarGenerados = ev.target.checked; alCambiar(); } }), "Ocultar WorkWithPlus y GAM"),
      h("label", { class: "chk chico", title: "El dibujo muestra solo los objetos de otras KBs (el panel de la derecha sigue mostrando todo)" },
        h("input", { type: "checkbox", checked: G.soloOtrasKbs, onchange: (ev) => { G.soloOtrasKbs = ev.target.checked; alCambiar(); } }), "Dibujar solo otras KBs"),
      h("label", { class: "chk chico" }, h("input", { type: "checkbox", checked: G.verFixes,
        onchange: (ev) => { G.verFixes = ev.target.checked; if (!G.verFixes) [...G.filtroKbs].filter(esFixes).forEach((k) => G.filtroKbs.delete(k)); pintarFiltrosGrafo(); alCambiar(); } }), "KBs de FIXES")));
}

function infoKb(k) {
  const i = G.datos.kbs[k] || {};
  const pub = (i.publicados || []).map((p) => `${p.jar} ${p.version}`).join(", ");
  return `Grafo armado: ${i.fecha || "-"}` + (pub ? `\nVersión publicada que se compara: ${pub}` : "\nNinguna KB usa su módulo publicado");
}

function guardarFiltrosGrafo() {
  almacen.guardar("grafo.kbs", [...G.filtroKbs]);
  almacen.guardar("grafo.tipos", [...G.tipos]);
  almacen.guardar("grafo.rel", [...G.relaciones]);
  almacen.guardar("grafo.relVistas", RELACIONES.map(([r]) => r));
  almacen.guardar("grafo.soloOtras", G.soloOtrasKbs);
  almacen.guardar("grafo.ocultarGen", G.ocultarGenerados);
  almacen.guardar("grafo.fixes", G.verFixes);
}

function buscarGrafo() {
  if (!G.datos) return;
  const q = $("#grafo-buscar").value.trim().toLowerCase();
  const lista = $("#grafo-lista");
  if (G.modo === "modulos") return pintarListaModulos(q);
  const terminos = q.split(/\s+/).filter(Boolean);
  const res = [];
  if (terminos.length) {
    for (let i = 0; i < G.datos.nodos.length && res.length < 300; i++) {
      if (!visible(i)) continue;
      const [kb, nombre, tipo] = N(i);
      const texto = `${nombre} ${kb} ${tipo}`.toLowerCase();
      if (terminos.every((t) => texto.includes(t))) res.push(i);
    }
    // Primero los que empiezan o terminan con lo buscado.
    const ultimo = terminos[terminos.length - 1];
    res.sort((a, b) => puntaje(b, ultimo) - puntaje(a, ultimo) || N(a)[1].localeCompare(N(b)[1]));
  }
  vaciar(lista, !terminos.length
    ? h("div", { class: "vacio" }, "Buscá cualquier objeto o tabla de cualquier KB. Varias palabras se combinan: ", h("code", null, "registro get generales"), ".")
    : !res.length ? h("div", { class: "vacio" }, "Nada coincide con los filtros actuales.")
      : res.map((i) => itemNodo(i)));
}

function puntaje(i, t) {
  const n = N(i)[1].toLowerCase();
  const c = corto(n);
  return (c === t ? 4 : 0) + (c.startsWith(t) ? 2 : 0) + (n.endsWith(t) ? 1 : 0);
}

function itemNodo(i, extra) {
  const [kb, nombre, tipo, , , origen] = N(i);
  return h("div", { class: "item item-grafo" + (G.foco?.tipo === "n" && G.foco.id === i ? " sel" : ""), onclick: () => enfocar({ tipo: "n", id: i }) },
    h("div", { class: "nombre" }, h("span", { class: "punto-kb", style: { background: colorKb(kb) } }), corto(nombre),
      origen === "P" ? h("span", { class: "pill aviso", title: "Solo está en la versión publicada del módulo, no en la KB local" }, "solo publicado") : null),
    h("div", { class: "sub" }, h("span", { class: `tipo-n t-${slug(tipo)}` }, tipo), " ", kb || "tabla", modulo(nombre) ? ` · ${modulo(nombre)}` : "", extra || ""));
}

// ---------------------------------------------------------------------- modulos

function claveModulo(i) {
  const [kb, nombre, tipo] = N(i);
  if (tipo === "Tabla") return `T|${kb}`;
  return `${kb}|${modulo(nombre) || "(raíz)"}`;
}
function nombreModulo(m) {
  const [kb, mod] = m.split("|");
  return kb === "T" ? `Tablas de ${mod || "otras bases"}` : mod;
}

function agregadoModulos() {
  if (G.mod) return G.mod;
  const objetos = new Map();    // modulo -> [i]
  const enlaces = new Map();    // "a>b" -> {a, b, n, pares: [[i, j, t, o]]}
  for (let i = 0; i < G.datos.nodos.length; i++) {
    if (!visible(i)) continue;
    const m = claveModulo(i);
    if (!objetos.has(m)) objetos.set(m, []);
    objetos.get(m).push(i);
  }
  for (let i = 0; i < G.datos.nodos.length; i++) {
    if (!visible(i)) continue;
    const ma = claveModulo(i);
    for (const [j, t, o] of G.sal[i]) {
      if (!G.relaciones.has(t) || !visible(j)) continue;
      const mb = claveModulo(j);
      if (ma === mb) continue;
      const k = ma + ">" + mb;
      let e = enlaces.get(k);
      if (!e) enlaces.set(k, e = { a: ma, b: mb, pares: [] });
      e.pares.push([i, j, t, o]);
    }
  }
  const sal = new Map(), ent = new Map();
  for (const e of enlaces.values()) {
    if (!sal.has(e.a)) sal.set(e.a, []);
    if (!ent.has(e.b)) ent.set(e.b, []);
    sal.get(e.a).push(e); ent.get(e.b).push(e);
  }
  return (G.mod = { objetos, enlaces, sal, ent });
}

function pintarListaModulos(q) {
  const M = agregadoModulos();
  const res = [...M.objetos.keys()].filter((m) => !q || m.toLowerCase().includes(q))
    .sort((a, b) => (M.ent.get(b)?.length || 0) - (M.ent.get(a)?.length || 0)).slice(0, 300);
  vaciar($("#grafo-lista"), res.length ? res.map((m) => {
    const [kb] = m.split("|");
    const usado = (M.ent.get(m) || []).length, usa = (M.sal.get(m) || []).length;
    return h("div", { class: "item item-grafo" + (G.foco?.tipo === "m" && G.foco.id === m ? " sel" : ""), onclick: () => enfocar({ tipo: "m", id: m }) },
      h("div", { class: "nombre" }, h("span", { class: "punto-kb", style: { background: colorKb(kb === "T" ? m.split("|")[1] : kb) } }), nombreModulo(m)),
      h("div", { class: "sub" }, `${kb === "T" ? "tablas" : kb} · ${M.objetos.get(m).length} objetos · lo usan ${usado} módulos · usa ${usa}`));
  }) : h("div", { class: "vacio" }, "Ningún módulo coincide."));
}

// ---------------------------------------------------------------------- foco y dibujo

function enfocar(foco, apilar = true) {
  if (apilar && G.foco && (G.foco.tipo !== foco.tipo || G.foco.id !== foco.id)) G.historial.push(G.foco);
  G.foco = foco;
  $$("#grafo-lista .item.sel").forEach((e) => e.classList.remove("sel"));
  if (foco.tipo === "n") { dibujarObjeto(foco.id); detalleObjeto(foco.id); }
  else { dibujarModulo(foco.id); detalleModulo(foco.id); }
  $("#grafo-volver").disabled = !G.historial.length;
}

function volverGrafo() {
  const f = G.historial.pop();
  if (f) enfocar(f, false);
}

function asegurarCy() {
  if (G.cy) return G.cy;
  if (typeof cytoscape === "undefined") {
    vaciar($("#grafo-lienzo"), h("div", { class: "vacio-grande" }, h("h3", null, "No se pudo cargar Cytoscape"),
      h("div", null, "La pantalla usa cytoscape.js desde cdn.jsdelivr.net. Revisá la conexión a internet y recargá.")));
    return null;
  }
  const css = getComputedStyle(document.documentElement);
  const v = (n) => css.getPropertyValue(n).trim();
  G.cy = cytoscape({
    container: $("#grafo-lienzo"),
    wheelSensitivity: 0.25,
    minZoom: 0.1, maxZoom: 3,
    style: [
      { selector: "node", style: {
        "label": "data(etq)", "font-size": 11, "color": v("--texto"), "text-valign": "center", "text-halign": "center",
        "background-color": "data(color)", "background-opacity": 0.14, "border-width": 1.5, "border-color": "data(color)",
        "shape": "round-rectangle", "width": "label", "height": 22, "padding": "6px", "font-family": v("--sans") } },
      { selector: "node[forma = 'tabla']", style: { "shape": "barrel" } },
      { selector: "node[forma = 'sdt']", style: { "shape": "cut-rectangle" } },
      { selector: "node[forma = 'grupo']", style: { "border-style": "dashed", "background-opacity": 0.06, "font-style": "italic" } },
      { selector: "node[forma = 'modulo']", style: { "shape": "round-rectangle", "height": 28, "font-size": 12 } },
      { selector: "node.foco", style: { "background-opacity": 0.35, "border-width": 3, "font-weight": "bold", "font-size": 13 } },
      // Otra KB: relleno fuerte, borde grueso y el nombre de la KB debajo. Lo de la misma KB queda atenuado.
      { selector: "node.externa", style: { "background-opacity": 0.42, "border-width": 3, "font-weight": "bold", "font-size": 12,
        "text-wrap": "wrap", "height": 36, "padding": "8px" } },
      { selector: "node.atenuado", style: { "opacity": 0.5 } },
      { selector: "node.publicado", style: { "border-style": "dotted", "border-color": v("--aviso") } },
      { selector: "node:selected", style: { "overlay-color": v("--acento"), "overlay-opacity": 0.12 } },
      { selector: "edge", style: {
        "width": 1.3, "line-color": v("--borde-fuerte"), "target-arrow-color": v("--borde-fuerte"), "target-arrow-shape": "triangle",
        "arrow-scale": 0.8, "curve-style": "bezier" } },
      { selector: "edge[tipo = 'sdt']", style: { "line-style": "dotted" } },
      { selector: "edge[tipo = 'transaccion']", style: { "line-style": "dashed" } },
      { selector: "edge[tipo = 'lee']", style: { "line-color": "#0891b2", "target-arrow-color": "#0891b2" } },
      { selector: "edge[tipo = 'escribe']", style: { "line-color": "#dc2626", "target-arrow-color": "#dc2626", "width": 2 } },
      { selector: "edge[tipo = 'servicio']", style: { "line-style": "dashed", "line-dash-pattern": [9, 3, 2, 3] } },
      { selector: "edge.externa", style: { "width": 2.6, "line-color": "data(color)", "target-arrow-color": "data(color)" } },
      { selector: "edge.atenuado", style: { "opacity": 0.45 } },
      { selector: "edge.publicado", style: { "line-color": v("--aviso"), "target-arrow-color": v("--aviso"), "line-style": "dashed",
        "label": "solo publicado", "font-size": 9, "color": v("--aviso"), "text-rotation": "autorotate" } },
      { selector: "edge[n > 1]", style: { "width": "mapData(n, 1, 200, 1.5, 9)", "label": "data(n)", "font-size": 10, "color": v("--texto-2"),
        "text-background-color": v("--panel"), "text-background-opacity": 1, "text-background-padding": 2 } },
      { selector: "edge.externa[n > 1]", style: { "width": "mapData(n, 1, 200, 2.6, 10)" } },
    ],
  });
  G.cy.on("tap", "node", (ev) => {
    const d = ev.target.data();
    if (d.grupo) return detalleGrupo(d);
    if (d.ref !== undefined && d.ref !== null) enfocar(d.tipoRef === "m" ? { tipo: "m", id: d.ref } : { tipo: "n", id: d.ref });
  });
  G.cy.on("tap", "edge", (ev) => { const d = ev.target.data(); if (d.pares) detalleEnlace(d); });
  return G.cy;
}

// Columnas: lo que usa al foco a la izquierda, lo que el foco usa a la derecha (y las tablas mas a la derecha).
function dibujarColumnas(centro, izq, der, tablas) {
  const cy = asegurarCy();
  if (!cy) return;
  const elems = [];
  const sep = 30, dx = 300;
  const columna = (items, x) => {
    const y0 = -((items.length - 1) * sep) / 2;
    items.forEach((it, k) => { it.position = { x, y: y0 + k * sep }; elems.push(it); });
  };
  columna([centro], 0);
  columna(izq.nodos, -dx);
  columna(der.nodos, dx);
  if (tablas) columna(tablas.nodos, dx * (der.nodos.length ? 2 : 1));
  elems.push(...izq.aristas, ...der.aristas, ...(tablas ? tablas.aristas : []));
  cy.elements().remove();
  cy.add(elems);
  cy.layout({ name: "preset", fit: true, padding: 40 }).run();
  if (cy.zoom() > 1.3) cy.zoom({ level: 1.3, position: { x: 0, y: 0 } });
  cy.center(cy.$(".foco"));
}

function datoNodo(i, id, extra = {}, externa = false) {
  const [kb, nombre, tipo, , , origen] = N(i);
  return { group: "nodes", data: { id, ref: i, tipoRef: "n", etq: corto(nombre) + (externa ? `\n${kb}` : ""),
    color: colorKb(kb), forma: tipo === "Tabla" ? "tabla" : tipo === "SDT" ? "sdt" : "", ...extra },
    classes: `${origen === "P" ? "publicado" : ""} ${externa ? "externa" : ""}` };
}

// Agrupa una columna por modulo si tiene demasiados elementos. Los objetos de otras KBs van arriba, resaltados,
// y quedan sueltos (sin agrupar) mientras entren en la columna: se agrupan los de la KB del foco.
function columnaObjetos(foco, items, lado) {
  const nodos = [], aristas = [];
  const kbFoco = N(foco)[0];
  const arista = (de, a, it, clases = "") => aristas.push({ group: "edges", data: { id: `e${lado}${de}>${a}`, source: de, target: a, tipo: it.t,
    color: colorKb(N(it.j)[0]) }, classes: `${clases} ${it.o === "P" ? "publicado" : ""}` });
  const externos = items.filter((it) => esExterna(it.j, kbFoco));
  let sueltos = items, agrupar = [];
  if (items.length > MAX_COLUMNA) {
    if (externos.length && externos.length <= MAX_COLUMNA) {
      sueltos = externos;
      agrupar = items.filter((it) => !esExterna(it.j, kbFoco));
    } else {
      sueltos = [];
      agrupar = items;
    }
  }
  sueltos.slice().sort((p, q) => esExterna(q.j, kbFoco) - esExterna(p.j, kbFoco) || (N(p.j)[0] + N(p.j)[1]).localeCompare(N(q.j)[0] + N(q.j)[1]))
    .forEach((it) => {
      const id = `${lado}${it.j}`;
      const ext = esExterna(it.j, kbFoco);
      nodos.push(datoNodo(it.j, id, {}, ext));
      lado === "i" ? arista(id, "f", it, ext ? "externa" : "") : arista("f", id, it, ext ? "externa" : "");
    });
  // Por modulo; si ni asi entran en la columna, por KB (un objeto muy usado: cuantos de cada KB).
  const agrupados = (clave) => {
    const g = new Map();
    for (const it of agrupar) {
      const m = clave(it.j);
      if (!g.has(m)) g.set(m, []);
      g.get(m).push(it);
    }
    return g;
  };
  let grupos = agrupados(claveModulo);
  const porKb = grupos.size > MAX_COLUMNA;
  if (porKb) grupos = agrupados((j) => N(j)[2] === "Tabla" ? `T|${N(j)[0]}` : `${N(j)[0]}|*`);
  const extG = (m) => m.split("|")[0] !== kbFoco && !m.startsWith("T|");
  [...grupos.entries()].sort((a, b) => extG(b[0]) - extG(a[0]) || b[1].length - a[1].length).forEach(([m, lista]) => {
    const id = `${lado}g${m}`;
    const kb = m.split("|")[0];
    const ext = extG(m) ? "externa" : "";
    if (lista.length === 1) {
      nodos.push(datoNodo(lista[0].j, id, {}, !!ext));
    } else {
      const titulo = porKb && !m.startsWith("T|") ? `KB ${kb}` : nombreModulo(m);
      nodos.push({ group: "nodes", data: { id, etq: `${titulo}  (${lista.length})` + (ext && !porKb ? `\n${kb}` : ""), color: colorKb(kb === "T" ? "" : kb),
        forma: "grupo", grupo: true, modulo: m, titulo, porKb, lista: lista.map((x) => x.j), lado }, classes: ext });
    }
    const d = { t: lista[0].t, o: lista.every((x) => x.o === "P") ? "P" : "L" };
    const e = lado === "i" ? { source: id, target: "f" } : { source: "f", target: id };
    aristas.push({ group: "edges", data: { id: `e${id}`, ...e, tipo: d.t, n: lista.length, color: colorKb(kb === "T" ? "" : kb) },
      classes: `${ext} ${d.o === "P" ? "publicado" : ""}` });
  });
  return { nodos, aristas };
}

function dibujarObjeto(i) {
  const kb = N(i)[0];
  const solo = (lista) => G.soloOtrasKbs && N(i)[2] !== "Tabla" ? lista.filter((x) => esExterna(x.j, kb)) : lista;
  const izq = solo(vecinos(i, "ent").filter((x) => !["lee", "escribe"].includes(x.t)));
  const derTodos = vecinos(i, "sal");
  const der = solo(derTodos.filter((x) => !["lee", "escribe"].includes(x.t)));
  const tab = G.soloOtrasKbs ? [] : derTodos.filter((x) => ["lee", "escribe"].includes(x.t));
  // Una tabla enfocada: a la izquierda quien la lee o escribe.
  dibujarColumnas(datoNodo(i, "f", {}), columnaObjetos(i, izq, "i"), columnaObjetos(i, der, "d"), columnaObjetos(i, tab, "t"));
  if (!G.cy) return;
  G.cy.$("#f").addClass("foco");
  atenuarLocales();
  pintarLeyenda();
}

// Si hay objetos de otras KBs, lo de la misma KB queda en segundo plano.
function atenuarLocales() {
  if (!G.cy.nodes(".externa").length) return;
  const locales = G.cy.nodes().not(".externa").not("#f").not("[forma = 'tabla']").filter((n) => !String(n.data("ref") ?? "").startsWith("T|"));
  locales.addClass("atenuado");
  locales.connectedEdges().addClass("atenuado");
}

function dibujarModulo(m) {
  const M = agregadoModulos();
  const kbFoco = m.split("|")[0];
  const extM = (mm) => mm.split("|")[0] !== kbFoco && !mm.startsWith("T|");
  const nodoMod = (mm, id) => {
    const kb = mm.split("|")[0];
    const ext = id !== "f" && extM(mm);
    return { group: "nodes", data: { id, ref: mm, tipoRef: "m", etq: `${nombreModulo(mm)} (${M.objetos.get(mm)?.length || 0})` + (ext ? `\n${kb}` : ""),
      color: colorKb(kb === "T" ? "" : kb), forma: "modulo" }, classes: ext ? "externa" : "" };
  };
  const col = (lista, lado) => {
    const nodos = [], aristas = [];
    const LIM = 60;
    const delOtro = (e) => lado === "i" ? e.a : e.b;
    if (G.soloOtrasKbs) lista = lista.filter((e) => extM(delOtro(e)));
    lista.sort((a, b) => extM(delOtro(b)) - extM(delOtro(a)) || b.pares.length - a.pares.length);
    if (lista.length > LIM) {
      // El resto se ve en el panel de detalle; aca queda un nodo que lo indica.
      const id = lado + "resto";
      nodos.push({ group: "nodes", data: { id, etq: `+ ${lista.length - LIM} módulos más (ver el panel)`, color: "#8b93a2", forma: "grupo" } });
      aristas.push({ group: "edges", data: { id: "e" + id, source: lado === "i" ? id : "f", target: lado === "i" ? "f" : id } });
    }
    lista.slice(0, LIM).forEach((e) => {
      const otro = lado === "i" ? e.a : e.b;
      const id = lado + otro;
      nodos.push(nodoMod(otro, id));
      const ext = otro.split("|")[0] !== m.split("|")[0] && !otro.startsWith("T|") ? "externa" : "";
      const pub = e.pares.every((p) => p[3] === "P") ? "publicado" : "";
      aristas.push({ group: "edges", data: { id: "e" + id, source: lado === "i" ? id : "f", target: lado === "i" ? "f" : id,
        n: e.pares.length, pares: e.pares, a: e.a, b: e.b, color: colorKb(otro.startsWith("T|") ? "" : otro.split("|")[0]) }, classes: `${ext} ${pub}` });
    });
    return { nodos, aristas };
  };
  dibujarColumnas(nodoMod(m, "f"), col([...(M.ent.get(m) || [])], "i"), col([...(M.sal.get(m) || [])], "d"));
  if (!G.cy) return;
  G.cy.$("#f").addClass("foco");
  atenuarLocales();
  pintarLeyenda();
}

function pintarLeyenda() {
  vaciar($("#grafo-leyenda"),
    h("span", null, "← lo usan"), h("span", null, "usa →"),
    h("span", null, h("i", { class: "ley l-ext-nodo" }), "otra KB"),
    h("span", null, h("i", { class: "ley l-llama" }), "llama"),
    h("span", null, h("i", { class: "ley l-srv" }), "vía sitServicio"),
    h("span", null, h("i", { class: "ley l-trn" }), "BC / transacción"),
    h("span", null, h("i", { class: "ley l-sdt" }), "SDT"),
    h("span", null, h("i", { class: "ley l-lee" }), "lee"),
    h("span", null, h("i", { class: "ley l-escribe" }), "escribe"),
    h("span", null, h("i", { class: "ley l-pub" }), "solo en la versión publicada"));
}

function pintarInicioGrafo() {
  if (G.cy) G.cy.elements().remove();
  vaciar($("#grafo-detalle"), h("div", { class: "vacio-grande chico" },
    h("h3", null, G.modo === "modulos" ? "Elegí un módulo" : "Buscá un objeto"),
    h("div", null, G.modo === "modulos"
      ? "Vas a ver qué módulos lo usan, cuáles usa, y qué objetos suyos se usan desde afuera."
      : "Vas a ver quién lo usa y qué usa, en su KB y en las otras, y las tablas que lee y escribe. Clic en un nodo para moverte; clic en un grupo para ver sus objetos.")));
  const tot = G.datos ? `${G.datos.nodos.length.toLocaleString()} objetos y ${G.datos.aristas.length.toLocaleString()} relaciones en ${Object.keys(G.datos.kbs).length} KBs` : "";
  $("#grafo-estado").textContent = tot;
}

// ---------------------------------------------------------------------- panel de detalle

function agrupado(items, alClic, abiertos = false) {
  // items: [{j, t, o, s}] -> por KB y modulo
  const grupos = new Map();
  for (const it of items) {
    const k = N(it.j)[2] === "Tabla" ? "Tablas" : `${N(it.j)[0]} · ${modulo(N(it.j)[1]) || "(raíz)"}`;
    if (!grupos.has(k)) grupos.set(k, []);
    grupos.get(k).push(it);
  }
  return [...grupos.entries()].sort((a, b) => b[1].length - a[1].length).map(([k, lista]) => h("details", { class: "grupo-det", open: grupos.size <= (abiertos ? 10 : 4) || undefined },
    h("summary", null, h("span", { class: "punto-kb", style: { background: colorKb(N(lista[0].j)[0]) } }), k, h("span", { class: "muted" }, ` (${lista.length})`)),
    lista.sort((a, b) => N(a.j)[1].localeCompare(N(b.j)[1])).map((it) => h("div", { class: "fila-rel", onclick: () => alClic(it.j) },
      h("span", { class: `tipo-n t-${slug(N(it.j)[2])}` }, N(it.j)[2]), " ", corto(N(it.j)[1]),
      it.t !== "llama" ? h("span", { class: "muted" }, ` · ${textoRel(it)}`) : null,
      it.o === "P" ? h("span", { class: "pill aviso" }, "solo publicado") : null))));
}

// Lo de otras KBs va primero y en su propio recuadro: es lo que se rompe sin que se note desde la KB del objeto.
function seccion(titulo, items, vacio, kbFoco) {
  const alClic = (j) => enfocar({ tipo: "n", id: j });
  const externos = kbFoco ? items.filter((x) => esExterna(x.j, kbFoco)) : [];
  const locales = items.filter((x) => !externos.includes(x));
  return h("div", { class: "seccion-det" }, h("h4", null, titulo, h("span", { class: "muted" }, ` ${items.length}`)),
    !items.length ? h("div", { class: "muted chico" }, vacio)
      : !externos.length ? agrupado(items, alClic)
        : [h("div", { class: "bloque-externo" }, h("div", { class: "etq-externo" }, `Otras KBs · ${externos.length}`), agrupado(externos, alClic, true)),
          locales.length ? [h("div", { class: "etq-local" }, `${kbFoco} · ${locales.length}`), agrupado(locales, alClic)] : null]);
}

function detalleObjeto(i) {
  const [kb, nombre, tipo, mod, desc, origen] = N(i);
  const usan = vecinos(i, "ent");
  const usa = vecinos(i, "sal");
  const externos = usan.filter((x) => N(x.j)[0] !== kb || modulo(N(x.j)[1]) !== mod);
  const kbsExt = new Set(usan.filter((x) => N(x.j)[0] && N(x.j)[0] !== kb).map((x) => N(x.j)[0]));
  const soloPub = [...usan, ...usa].filter((x) => x.o === "P");
  const avisos = [];
  if (origen === "P") avisos.push(h("div", { class: "aviso-det" }, "Este objeto está en la versión publicada del módulo pero no en la KB local: tu KB está atrasada o se borró localmente."));
  if (soloPub.length) avisos.push(h("div", { class: "aviso-det" }, `${soloPub.length} relación(es) existen solo en la versión publicada del módulo (no en tu KB local).`));
  vaciar($("#grafo-detalle"),
    h("div", { class: "cab-det" },
      h("div", { class: "muted chico" }, h("span", { class: "punto-kb", style: { background: colorKb(kb) } }), kb || "tabla", mod ? ` · ${mod}` : ""),
      h("h3", null, corto(nombre)),
      h("div", { class: "fila" }, h("span", { class: `tipo-n t-${slug(tipo)}` }, tipo),
        h("button", { class: "btn chico fantasma", title: "Copiar el nombre completo", onclick: () => copiar(nombre) }, "copiar nombre"),
        mod ? h("button", { class: "btn chico fantasma", onclick: () => { cambiarModoGrafo("modulos"); enfocar({ tipo: "m", id: claveModulo(i) }); } }, "ver su módulo") : null),
      desc ? h("div", { class: "muted" }, desc) : null),
    avisos,
    tipo !== "Tabla" ? h("div", { class: "resumen-det" },
      h("div", { class: kbsExt.size ? "destacado" : "" }, h("b", null, kbsExt.size), kbsExt.size === 1 ? " KB externa lo usa" : " KBs externas lo usan",
        kbsExt.size ? h("div", { class: "kbs-ext" }, [...kbsExt].sort().map((k) => h("span", null, h("span", { class: "punto-kb", style: { background: colorKb(k) } }), k))) : null),
      h("div", null, h("b", null, usan.length), " lo usan"),
      h("div", null, h("b", null, externos.length), " desde fuera de su módulo")) : null,
    seccion(tipo === "Tabla" ? "La leen o escriben" : "Lo usan", usan, "Nadie lo usa (con los filtros actuales).", tipo === "Tabla" ? "" : kb),
    tipo !== "Tabla" ? seccion("Usa", usa.filter((x) => !["lee", "escribe"].includes(x.t)), "No usa otros objetos.", kb) : null,
    tipo !== "Tabla" ? seccion("Tablas", usa.filter((x) => ["lee", "escribe"].includes(x.t)), "No lee ni escribe tablas.") : null);
}

function detalleModulo(m) {
  const M = agregadoModulos();
  const objs = M.objetos.get(m) || [];
  const ent = M.ent.get(m) || [], sal = M.sal.get(m) || [];
  // Superficie publica: objetos del modulo que se usan desde afuera, con cuantos los usan.
  const usados = new Map();
  for (const e of ent) for (const [i, j] of e.pares) { if (!usados.has(j)) usados.set(j, new Set()); usados.get(j).add(i); }
  const circulares = ent.filter((e) => sal.some((s) => s.b === e.a)).map((e) => e.a);
  const kbs = new Set(ent.map((e) => e.a.split("|")[0]).filter((k) => k !== "T" && k !== m.split("|")[0]));
  vaciar($("#grafo-detalle"),
    h("div", { class: "cab-det" },
      h("div", { class: "muted chico" }, m.startsWith("T|") ? "tablas" : m.split("|")[0]),
      h("h3", null, nombreModulo(m)),
      h("div", { class: "muted chico" }, conteoTipos(objs))),
    circulares.length ? h("div", { class: "aviso-det" }, "Dependencia circular con: ",
      circulares.map((c, k) => [k ? ", " : "", h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); enfocar({ tipo: "m", id: c }); } }, nombreModulo(c))])) : null,
    h("div", { class: "resumen-det" },
      h("div", null, h("b", null, ent.length), " módulos lo usan"),
      h("div", null, h("b", null, kbs.size), " KBs externas"),
      h("div", null, h("b", null, sal.length), " módulos que usa")),
    h("div", { class: "seccion-det" }, h("h4", null, "Se usan desde afuera", h("span", { class: "muted" }, ` ${usados.size} de ${objs.length}`)),
      usados.size ? [...usados.entries()].sort((a, b) => b[1].size - a[1].size).slice(0, 200).map(([j, s]) => h("div", { class: "fila-rel", onclick: () => { cambiarModoGrafo("objetos"); enfocar({ tipo: "n", id: j }); } },
        h("span", { class: `tipo-n t-${slug(N(j)[2])}` }, N(j)[2]), " ", corto(N(j)[1]), h("span", { class: "muted" }, ` · ${s.size} objeto(s) de afuera`)))
        : h("div", { class: "muted chico" }, "Ningún objeto del módulo se usa desde otro módulo.")),
    listaModulos("Módulos que lo usan", ent, (e) => e.a),
    listaModulos("Módulos que usa", sal, (e) => e.b),
    h("div", { class: "seccion-det" }, h("h4", null, "Sus objetos", h("span", { class: "muted" }, ` ${objs.length}`)),
      h("details", null, h("summary", null, "ver todos"), objs.slice().sort((a, b) => N(a)[1].localeCompare(N(b)[1])).map((j) => h("div", { class: "fila-rel", onclick: () => { cambiarModoGrafo("objetos"); enfocar({ tipo: "n", id: j }); } },
        h("span", { class: `tipo-n t-${slug(N(j)[2])}` }, N(j)[2]), " ", corto(N(j)[1]))))));
}

function listaModulos(titulo, enlaces, otro) {
  return h("div", { class: "seccion-det" }, h("h4", null, titulo, h("span", { class: "muted" }, ` ${enlaces.length}`)),
    enlaces.length ? h("details", { open: enlaces.length <= 12 || undefined }, h("summary", null, "ver la lista"),
      enlaces.slice().sort((a, b) => b.pares.length - a.pares.length).map((e) => {
        const m = otro(e), kb = m.split("|")[0];
        return h("div", { class: "fila-rel", onclick: () => enfocar({ tipo: "m", id: m }) },
          h("span", { class: "punto-kb", style: { background: colorKb(kb === "T" ? "" : kb) } }), nombreModulo(m),
          h("span", { class: "muted" }, ` · ${kb === "T" ? "tablas" : kb} · ${e.pares.length} relación(es)`),
          h("a", { href: "#", class: "chico", style: { marginLeft: "6px" }, onclick: (ev) => { ev.preventDefault(); ev.stopPropagation(); detalleEnlace({ ...e, a: e.a, b: e.b }); } }, "ver"));
      })) : h("div", { class: "muted chico" }, "Ninguno."));
}

function conteoTipos(objs) {
  const c = {};
  for (const j of objs) c[N(j)[2]] = (c[N(j)[2]] || 0) + 1;
  return Object.entries(c).sort((a, b) => b[1] - a[1]).map(([t, n]) => `${n} ${t}`).join(" · ");
}

function detalleGrupo(d) {
  vaciar($("#grafo-detalle"),
    h("div", { class: "cab-det" }, h("div", { class: "muted chico" }, d.porKb ? (d.lado === "i" ? "Lo usan, desde" : "Usa, de") : d.lado === "i" ? "Lo usan, desde el módulo" : "Usa, del módulo"),
      h("h3", null, d.titulo || nombreModulo(d.modulo)), h("div", { class: "muted chico" }, `${d.lista.length} objetos`),
      h("div", { class: "fila" }, h("button", { class: "btn chico", onclick: () => enfocar(G.foco, false) }, "← volver al detalle"),
        !d.modulo.startsWith("T|") && !d.porKb ? h("button", { class: "btn chico fantasma", onclick: () => { cambiarModoGrafo("modulos"); enfocar({ tipo: "m", id: d.modulo }); } }, "ver el módulo") : null)),
    d.lista.slice().sort((a, b) => N(a)[1].localeCompare(N(b)[1])).map((j) => itemNodo(j)));
}

function detalleEnlace(d) {
  vaciar($("#grafo-detalle"),
    h("div", { class: "cab-det" }, h("div", { class: "muted chico" }, `${d.pares.length} relaciones`),
      h("h3", null, `${nombreModulo(d.a)} → ${nombreModulo(d.b)}`),
      h("button", { class: "btn chico", onclick: () => enfocar(G.foco, false) }, "← volver al detalle")),
    d.pares.slice().sort((p, q) => N(p[0])[1].localeCompare(N(q[0])[1])).slice(0, 500).map(([i, j, t, o]) => h("div", { class: "fila-rel par" },
      h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); cambiarModoGrafo("objetos"); enfocar({ tipo: "n", id: i }); } }, corto(N(i)[1])),
      h("span", { class: "muted" }, ` ${t} → `),
      h("a", { href: "#", onclick: (ev) => { ev.preventDefault(); cambiarModoGrafo("objetos"); enfocar({ tipo: "n", id: j }); } }, corto(N(j)[1])),
      o === "P" ? h("span", { class: "pill aviso" }, "solo publicado") : null)));
}

// ---------------------------------------------------------------------- inicio de la pantalla

function cambiarModoGrafo(modo) {
  if (G.modo === modo) return;
  G.modo = modo;
  $("#grafo-buscar").value = "";
  almacen.guardar("grafo.modo", modo);
  $$("#grafo-modo button").forEach((b) => b.classList.toggle("activa", b.dataset.modo === modo));
  $("#grafo-buscar").placeholder = modo === "modulos" ? "Buscar módulo…  ( / )" : "Buscar objeto o tabla en todas las KBs…  ( / )";
  buscarGrafo();
}

function abrirGrafo() {
  if (!G.inicializado) {
    G.inicializado = true;
    $("#grafo-buscar").addEventListener("input", () => { clearTimeout(G.tBuscar); G.tBuscar = setTimeout(buscarGrafo, 120); });
    $("#grafo-buscar").addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") { clearTimeout(G.tBuscar); buscarGrafo(); const p = $("#grafo-lista .item"); if (p) p.click(); }
    });
    $$("#grafo-modo button").forEach((b) => b.addEventListener("click", () => { cambiarModoGrafo(b.dataset.modo); G.foco = null; pintarInicioGrafo(); }));
    $$("#grafo-modo button").forEach((b) => b.classList.toggle("activa", b.dataset.modo === G.modo));
    $("#grafo-buscar").placeholder = G.modo === "modulos" ? "Buscar módulo…  ( / )" : "Buscar objeto o tabla en todas las KBs…  ( / )";
    $("#grafo-volver").addEventListener("click", volverGrafo);
    $("#grafo-ajustar").addEventListener("click", () => G.cy && G.cy.fit(undefined, 40));
    setInterval(vigilarGrafo, 8000);
  }
  if (!G.datos) cargarGrafo();
  else if (G.cy) G.cy.resize();
}
