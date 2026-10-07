/* GxPruebas - componentes reutilizables (sin dependencias). */
"use strict";

// ---------------------------------------------------------------------- DOM
function h(tag, attrs, ...hijos) {
  const e = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
      else if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v);
      else if (k === "dataset") Object.assign(e.dataset, v);
      else if (k === "html") e.innerHTML = v;
      else if (k === "value") e.value = v;
      else if (k === "checked") e.checked = !!v;
      else e.setAttribute(k, v === true ? "" : v);
    }
  }
  agregar(e, hijos);
  return e;
}
function agregar(e, hijos) {
  for (const c of hijos.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    e.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return e;
}
function vaciar(e, ...hijos) { e.replaceChildren(); return agregar(e, hijos); }
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

// ---------------------------------------------------------------------- utilidades
const clonar = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
const json = (v, sangria = 2) => JSON.stringify(v, null, sangria);
function fmtMs(ms) {
  if (ms === null || ms === undefined) return "";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60000)} min ${Math.round((ms % 60000) / 1000)} s`;
}
function fmtFecha(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function rutaHija(base, k) {
  if (typeof k === "number") return `${base}[${k}]`;
  return base ? `${base}.${k}` : String(k);
}
function corto(nombre) { const p = (nombre || "").split("."); return p[p.length - 1]; }
function modulo(nombre) { const p = (nombre || "").split("."); p.pop(); return p.join("."); }
function resumirValor(v, max = 80) {
  let s = typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v);
  if (s === undefined) s = String(v);
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
const almacen = {
  leer(k, def) { try { const v = localStorage.getItem("gxp." + k); return v === null ? def : JSON.parse(v); } catch { return def; } },
  guardar(k, v) { try { localStorage.setItem("gxp." + k, JSON.stringify(v)); } catch { /* sin almacenamiento */ } },
};
function copiar(texto) {
  navigator.clipboard?.writeText(texto).then(() => toast("Copiado al portapapeles", "ok", 1500), () => toast("No se pudo copiar", "error"));
}
function descargar(nombre, contenido, tipo = "application/json") {
  const a = h("a", { href: URL.createObjectURL(new Blob([contenido], { type: tipo })), download: nombre });
  document.body.appendChild(a); a.click(); a.remove();
}

// ---------------------------------------------------------------------- API
async function api(metodo, ruta, cuerpo) {
  const op = { method: metodo, headers: {} };
  if (cuerpo !== undefined) { op.body = JSON.stringify(cuerpo); op.headers["Content-Type"] = "application/json"; }
  let r;
  try { r = await fetch(ruta, op); } catch (e) { throw new Error("No hay conexión con GxPruebas. ¿Cerraste la ventana del servidor?"); }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(datos.error || `Error ${r.status}`); e.datos = datos; throw e; }
  return datos;
}
const GET = (ruta, q) => api("GET", q ? `${ruta}?${new URLSearchParams(q)}` : ruta);
const POST = (ruta, cuerpo) => api("POST", ruta, cuerpo);

// ---------------------------------------------------------------------- avisos, modales, menus
function toast(msg, tipo = "", ms = 4000) {
  const t = h("div", { class: `toast ${tipo}`, onclick: () => t.remove() }, msg);
  $("#avisos").appendChild(t);
  if (ms) setTimeout(() => t.remove(), tipo === "error" ? Math.max(ms, 8000) : ms);
  return t;
}
function modal({ titulo, cuerpo, botones = [], ancho = false, alCerrar }) {
  const velo = h("div", { class: "velo" });
  const cerrar = () => { velo.remove(); document.removeEventListener("keydown", tecla); alCerrar && alCerrar(); };
  const tecla = (ev) => { if (ev.key === "Escape") cerrar(); };
  const pie = h("div", { class: "pie" });
  for (const b of botones) {
    pie.appendChild(h("button", {
      class: `btn ${b.prim ? "prim" : ""} ${b.peligro ? "peligro" : ""}`,
      onclick: async () => { if (b.accion) { const r = await b.accion(); if (r === false) return; } cerrar(); },
    }, b.texto));
  }
  const m = h("div", { class: `modal ${ancho ? "ancho" : ""}` },
    h("div", { class: "cab" }, h("h3", null, titulo), h("button", { class: "btn fantasma icono", onclick: cerrar, title: "Cerrar (Esc)" }, "✕")),
    h("div", { class: "cuerpo" }, cuerpo),
    botones.length ? pie : null);
  velo.appendChild(m);
  velo.addEventListener("mousedown", (ev) => { if (ev.target === velo) cerrar(); });
  document.addEventListener("keydown", tecla);
  document.body.appendChild(velo);
  setTimeout(() => { const f = m.querySelector("input, textarea, select"); f && f.focus(); }, 30);
  return { cerrar, elemento: m };
}
function confirmar(texto, { si = "Aceptar", peligro = false } = {}) {
  return new Promise((ok) => {
    let respuesta = false;
    modal({
      titulo: "Confirmar", cuerpo: h("div", { style: { whiteSpace: "pre-wrap" } }, texto),
      botones: [{ texto: "Cancelar" }, { texto: si, prim: !peligro, peligro, accion: () => { respuesta = true; } }],
      alCerrar: () => ok(respuesta),
    });
  });
}
function pedirTexto(titulo, etiqueta, valor = "") {
  return new Promise((ok) => {
    const inp = h("input", { type: "text", value: valor, style: { width: "100%" } });
    let r = null;
    const m = modal({
      titulo, cuerpo: h("div", null, h("div", { class: "muted", style: { marginBottom: "6px" } }, etiqueta), inp),
      botones: [{ texto: "Cancelar" }, { texto: "Aceptar", prim: true, accion: () => { r = inp.value; } }],
      alCerrar: () => ok(r),
    });
    inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { r = inp.value; m.cerrar(); } });
  });
}
let menuAbierto = null;
function menu(x, y, titulo, opciones) {
  cerrarMenu();
  const m = h("div", { class: "menu" }, titulo ? h("div", { class: "titulo-menu" }, titulo) : null,
    opciones.map((o) => o === "-" ? h("div", { class: "sep", style: { margin: "4px 0" } }) :
      h("button", { onclick: () => { cerrarMenu(); o.accion(); } }, o.texto)));
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.min(x, innerWidth - r.width - 8) + "px";
  m.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
  menuAbierto = m;
  setTimeout(() => document.addEventListener("mousedown", cerrarMenuFuera), 0);
}
function cerrarMenuFuera(ev) { if (menuAbierto && !menuAbierto.contains(ev.target)) cerrarMenu(); }
function cerrarMenu() { menuAbierto?.remove(); menuAbierto = null; document.removeEventListener("mousedown", cerrarMenuFuera); }

function pill(texto, clase = "") { return h("span", { class: `pill ${clase}` }, texto); }
const NOMBRE_ESTADO = { ok: "OK", falla: "Falla", error: "Error", omitido: "Omitido", corriendo: "Corriendo" };
function pillEstado(e) { return pill(NOMBRE_ESTADO[e] || e, e === "ok" ? "ok" : e === "falla" ? "falla" : e === "error" ? "error" : ""); }
function cargando(texto = "Cargando…") { return h("span", { class: "muted" }, h("span", { class: "cargando" }), " ", texto); }

function subpestanas(pestanas, inicial) {
  // pestanas: [{id, texto, n, render: () => Node}]
  const barra = h("div", { class: "subpestanas" });
  const cuerpo = h("div");
  let actual = inicial || pestanas[0]?.id;
  const pintar = () => {
    vaciar(barra, pestanas.map((p) => h("button", { class: p.id === actual ? "activa" : "", onclick: () => { actual = p.id; pintar(); } },
      p.texto, p.n !== undefined && p.n !== null ? h("span", { class: "n" }, p.n) : null)));
    const p = pestanas.find((x) => x.id === actual) || pestanas[0];
    vaciar(cuerpo, p ? p.render() : null);
  };
  pintar();
  return h("div", null, barra, cuerpo);
}

// ---------------------------------------------------------------------- arbol JSON
/**
 * opciones: { alClic(ruta, valor, evento), resaltar: Set de rutas, abrirHasta: profundidad, raiz: ruta base,
 *             marcas(ruta) -> [{texto, clase, title}] etiquetas al lado del valor (clase "apagada" atenua la rama) }
 * Los textos muestran los espacios finales (tipicos de los Character de GeneXus) como "·".
 */
function arbolJson(valor, opciones = {}) {
  const { alClic, resaltar = new Set(), abrirHasta = 3, raiz = "", marcas } = opciones;
  const marcado = (ruta) => resaltar.has(ruta);
  const valorHoja = (v) => {
    if (v === null || v === undefined) return h("span", { class: "z" }, "null");
    if (typeof v === "boolean") return h("span", { class: "b" }, String(v));
    if (typeof v === "number") return h("span", { class: "n" }, String(v));
    const s = String(v);
    const m = s.match(/ +$/);
    if (m && s.trim() !== "") {
      return h("span", { class: "s" }, '"', s.slice(0, s.length - m[0].length),
        h("span", { class: "esp", title: `${m[0].length} espacio(s) al final` }, "·".repeat(Math.min(m[0].length, 40))), '"');
    }
    return h("span", { class: "s" }, JSON.stringify(s));
  };
  const etiquetas = (li, ruta) => {
    const ms = marcas ? marcas(ruta) || [] : [];
    if (ms.some((m) => m.clase === "apagada")) li.classList.add("apagado");
    return ms.map((m) => h("span", { class: `marca ${m.clase || ""}`, title: m.title || "" }, m.texto));
  };
  const nodo = (k, v, ruta, prof) => {
    const li = h("li");
    const etiqueta = k === null ? null : h("span", { class: "k" }, typeof k === "number" ? `[${k}]` : k, ": ");
    if (v && typeof v === "object") {
      const esLista = Array.isArray(v);
      const claves = esLista ? v.map((_, i) => i) : Object.keys(v);
      const tg = h("span", { class: "tg" }, "▾");
      const meta = h("span", { class: "meta" }, esLista ? `[${v.length}]` : `{${claves.length}}`);
      const cab = h("span", { class: `hoja ${marcado(ruta) ? "dif" : ""}`, title: ruta || "$" }, etiqueta, meta);
      if (alClic) cab.addEventListener("click", (ev) => { ev.stopPropagation(); alClic(ruta, v, ev); });
      li.append(tg, cab, ...etiquetas(li, ruta));
      const ul = h("ul");
      for (const c of claves) ul.appendChild(nodo(c, v[c], rutaHija(ruta, c), prof + 1));
      li.appendChild(ul);
      // Se abre solo lo que tiene adentro una diferencia o una marca (salvo las que apagan la rama).
      // (en una lista, solo los primeros elementos: una regla con [*] marca a todos)
      const interesa = (typeof k !== "number" || k < 3) && ul.querySelector(".dif, .marca:not(.apagada)");
      if ((prof >= abrirHasta && !interesa) || claves.length === 0) li.classList.add("cerrado");
      if (claves.length === 0) tg.textContent = " ";
      tg.addEventListener("click", () => { li.classList.toggle("cerrado"); tg.textContent = li.classList.contains("cerrado") ? "▸" : "▾"; });
      if (li.classList.contains("cerrado") && claves.length) tg.textContent = "▸";
    } else {
      const hoja = h("span", { class: `hoja ${marcado(ruta) ? "dif" : ""}`, title: ruta }, etiqueta, valorHoja(v));
      if (alClic) hoja.addEventListener("click", (ev) => { ev.stopPropagation(); alClic(ruta, v, ev); });
      li.append(h("span", { class: "tg" }, " "), hoja, ...etiquetas(li, ruta));
    }
    return li;
  };
  const cont = h("div", { class: "arbol" });
  if (valor === undefined) return agregar(cont, [h("span", { class: "z" }, "(sin datos)")]);
  const ul = h("ul");
  if (valor && typeof valor === "object") {
    const claves = Array.isArray(valor) ? valor.map((_, i) => i) : Object.keys(valor);
    if (!claves.length) ul.appendChild(h("li", null, h("span", { class: "meta" }, Array.isArray(valor) ? "[]" : "{}")));
    for (const c of claves) ul.appendChild(nodo(c, valor[c], rutaHija(raiz, c), 1));
  } else ul.appendChild(nodo(null, valor, raiz, 1));
  cont.appendChild(ul);
  return cont;
}

// ---------------------------------------------------------------------- editor JSON (texto)
// Los errores de JSON más comunes al escribir un caso a mano, explicados.
function pistaJson(t) {
  const pistas = [];
  const sinComillas = t.match(/[:[,]\s*(\$\{[^}"]*\})/);
  if (sinComillas) pistas.push(`Las variables van entre comillas: "${sinComillas[1]}" (si el valor es solo la variable, conserva su tipo: un número sigue siendo número).`);
  if (/,\s*[}\]]/.test(t)) pistas.push("Sobra una coma antes de un } o un ]: el último elemento no lleva coma.");
  return pistas.length ? " → " + pistas.join(" ") : "";
}

function editorJson(valor, { alCambiar, filas = 14, placeholder = "" } = {}) {
  const ta = h("textarea", { class: "codigo", rows: filas, spellcheck: "false", placeholder });
  ta.value = valor === undefined ? "" : json(valor);
  const estado = h("div", { class: "chico muted", style: { minHeight: "18px", marginTop: "3px" } });
  const validar = () => {
    const t = ta.value.trim();
    if (!t) { estado.textContent = ""; alCambiar && alCambiar(undefined, true); return true; }
    try {
      const v = JSON.parse(t);
      estado.textContent = "JSON válido"; estado.style.color = "var(--ok)";
      alCambiar && alCambiar(v, true);
      return true;
    } catch (e) {
      estado.textContent = "JSON inválido: " + e.message + pistaJson(t); estado.style.color = "var(--falla)";
      alCambiar && alCambiar(undefined, false);
      return false;
    }
  };
  ta.addEventListener("input", validar);
  ta.addEventListener("keydown", (ev) => {
    if (ev.key === "Tab" && !ev.shiftKey) {
      ev.preventDefault();
      const s = ta.selectionStart;
      ta.setRangeText("  ", s, ta.selectionEnd, "end");
      validar();
    }
  });
  const formatear = () => { try { ta.value = json(JSON.parse(ta.value)); validar(); } catch { validar(); } };
  const cont = h("div", null, ta, h("div", { class: "fila", style: { justifyContent: "space-between" } }, estado,
    h("button", { class: "btn chico fantasma", onclick: formatear, title: "Formatear" }, "{ } Formatear")));
  cont.poner = (v) => { ta.value = v === undefined ? "" : json(v); validar(); };
  cont.valor = () => { try { return ta.value.trim() ? JSON.parse(ta.value) : undefined; } catch { return undefined; } };
  cont.valido = validar;
  cont.textarea = ta;
  return cont;
}

// ---------------------------------------------------------------------- formulario a partir de una plantilla
/**
 * Formulario editable para un valor JSON. 'plantilla' (opcional) da el elemento modelo de cada lista
 * para el boton "+ agregar". alCambiar(valor) se llama en cada cambio.
 * opciones.combo(ruta, padre) (opcional) da los valores sugeridos de un campo (ver listaValores), o null.
 */
function formularioJson(valorInicial, plantilla, alCambiar, opciones = {}) {
  let datos = clonar(valorInicial) ?? {};
  const cont = h("div", { class: "form-json" });
  const cerrados = new Set();
  const modeloDe = (ruta) => {
    // busca en la plantilla el primer elemento de la lista en esa ruta (indices -> 0)
    const partes = ruta.replace(/\[\d+\]/g, "[0]");
    let v = plantilla;
    for (const m of partes.matchAll(/([^.[\]]+)|\[(\d+)\]/g)) {
      if (v === undefined || v === null) return undefined;
      v = m[1] !== undefined ? v[m[1]] : v[Number(m[2])];
    }
    return Array.isArray(v) && v.length ? clonar(v[0]) : undefined;
  };
  const avisar = () => alCambiar && alCambiar(clonar(datos));
  const entrada = (v, poner) => {
    if (typeof v === "boolean") return h("input", { type: "checkbox", checked: v, onchange: (ev) => { poner(ev.target.checked); avisar(); } });
    const inp = h("input", { type: "text", value: v === null ? "" : String(v), class: typeof v === "number" ? "num" : "" });
    if (typeof v === "number") {
      inp.title = "Número";
      inp.addEventListener("input", () => {
        const t = inp.value.trim();
        if (/^-?\d+(\.\d+)?$/.test(t)) { poner(Number(t)); inp.style.borderColor = ""; avisar(); }
        else if (t === "" ) { poner(0); avisar(); }
        else inp.style.borderColor = "var(--falla)";
      });
    } else {
      inp.addEventListener("input", () => { poner(inp.value); avisar(); });
    }
    return inp;
  };
  // Campo con valores sugeridos: el texto se sigue pudiendo escribir (${variables}, valores invalidos).
  const conCombo = (inp, ruta, padre) => {
    const c = opciones.combo && opciones.combo(ruta, padre);
    if (!c) return { control: inp };
    const desc = h("span", { class: "combo-desc" });
    const ponerDesc = () => { const t = c.textoDe ? c.textoDe(inp.value) : ""; desc.textContent = t || ""; desc.title = t || ""; };
    const abrir = () => listaValores(caja, c, inp.value, (valor) => {
      inp.value = String(valor);
      inp.dispatchEvent(new Event("input"));
      inp.focus();
    });
    inp.addEventListener("input", ponerDesc);
    inp.addEventListener("keydown", (ev) => { if ((ev.key === "ArrowDown" && ev.altKey) || ev.key === "F4") { ev.preventDefault(); abrir(); } });
    const caja = h("div", { class: "combo" }, inp,
      h("button", { class: "btn chico fantasma icono", type: "button", title: `${c.titulo}\nVer los valores (Alt+↓)`, tabindex: -1, onclick: abrir }, "▾"), desc);
    ponerDesc();
    return { control: caja, titulo: c.titulo };
  };
  const render = (v, ruta, poner) => {
    if (Array.isArray(v)) {
      const caja = h("div");
      v.forEach((item, i) => {
        const r = rutaHija(ruta, i);
        caja.appendChild(h("div", { class: "item-lista" },
          h("button", { class: "btn fantasma icono chico quitar", title: "Quitar elemento", onclick: () => { v.splice(i, 1); avisar(); pintar(); } }, "✕"),
          h("div", { class: "idx" }, `[${i}]`),
          item && typeof item === "object" ? render(item, r, (nv) => { v[i] = nv; })
            : celda(item, r, v, (nv) => { v[i] = nv; })));
      });
      caja.appendChild(h("button", {
        class: "btn chico", onclick: () => {
          const modelo = modeloDe(ruta) ?? (v.length ? clonar(v[v.length - 1]) : "");
          v.push(modelo); avisar(); pintar();
        },
      }, "+ agregar elemento"));
      return caja;
    }
    if (v && typeof v === "object") {
      const caja = h("div");
      for (const k of Object.keys(v)) {
        const r = rutaHija(ruta, k);
        const hijo = v[k];
        if (hijo && typeof hijo === "object") {
          const fs = h("fieldset", { class: cerrados.has(r) ? "cerrado" : "" },
            h("legend", { onclick: () => { fs.classList.toggle("cerrado"); fs.classList.contains("cerrado") ? cerrados.add(r) : cerrados.delete(r); } },
              (cerrados.has(r) ? "▸ " : "▾ ") + k, h("span", { class: "muted" }, Array.isArray(hijo) ? `  [${hijo.length}]` : "")),
            render(hijo, r, (nv) => { v[k] = nv; }));
          caja.appendChild(fs);
        } else {
          const { control, titulo } = celda(hijo, r, v, (nv) => { v[k] = nv; }, true);
          caja.appendChild(h("div", { class: "campo" }, h("label", { title: titulo ? `${r}\n${titulo}` : r }, k), control));
        }
      }
      if (!Object.keys(v).length) caja.appendChild(h("div", { class: "muted chico" }, "(sin campos)"));
      return caja;
    }
    return h("div", { class: "campo" }, h("label", null, ruta || "valor"), entrada(v, (nv) => { datos = nv; }));
  };
  // Control de un valor simple, con su combo si lo tiene. 'padre' es el objeto o lista que lo contiene.
  function celda(v, ruta, padre, poner, conTitulo = false) {
    const inp = entrada(v, poner);
    const r = typeof v === "boolean" ? { control: inp } : conCombo(inp, ruta, padre);
    return conTitulo ? r : r.control;
  }
  const pintar = () => vaciar(cont, render(datos, "", (nv) => { datos = nv; }));
  pintar();
  cont.poner = (v) => { datos = clonar(v) ?? {}; pintar(); };
  cont.valor = () => clonar(datos);
  return cont;
}

// ---------------------------------------------------------------------- lista de valores (combo)
/**
 * Lista desplegable debajo de 'ancla' para elegir un valor. 'fuente' es
 *   {titulo, valores: [{valor, texto}]}                                  valores fijos (dominio enumerado)
 *   {titulo, cargar: async (buscar) => ({valores, truncado, nota})}      valores de la base
 * Con 'cargar', si la lista vino truncada, lo que se escribe en el filtro se busca en la base.
 * alElegir(valor) recibe el valor elegido.
 */
function listaValores(ancla, fuente, actual, alElegir) {
  cerrarMenu();
  const filtro = h("input", { type: "text", placeholder: "Filtrar…", spellcheck: "false" });
  const lista = h("div", { class: "lista-valores" });
  const pie = h("div", { class: "pie-valores" });
  const m = h("div", { class: "menu combo-menu" }, h("div", { class: "titulo-menu" }, fuente.titulo), filtro, lista, pie);
  const igual = (v) => String(v.valor).trim() === String(actual ?? "").trim();
  let valores = fuente.valores || null, truncado = false, nota = "", error = "", activo = 0, visibles = [], buscado = "", espera = null;
  const elegir = (v) => { cerrarMenu(); alElegir(v.valor); };
  const marcar = () => $$("button", lista).forEach((b, i) => b.classList.toggle("activo", i === activo));
  const mover = (d) => {
    activo = Math.max(0, Math.min(activo + d, visibles.length - 1));
    marcar();
    $$("button", lista)[activo]?.scrollIntoView({ block: "nearest" });
  };
  const pintar = () => {
    const t = filtro.value.trim().toLowerCase();
    visibles = (valores || []).filter((v) => !t || String(v.valor).toLowerCase().includes(t) || (v.texto || "").toLowerCase().includes(t));
    activo = Math.max(0, Math.min(activo, visibles.length - 1));
    const aviso = (x) => h("div", { class: "muted chico", style: { padding: "6px 10px" } }, x);
    vaciar(lista, error ? h("div", { class: "error-caja chico" }, error)
      : valores === null ? aviso(cargando("Consultando la base…"))
      : visibles.length ? visibles.map((v, i) => h("button", {
          type: "button", class: igual(v) ? "elegido" : "",
          onmousedown: (ev) => ev.preventDefault(), onclick: () => elegir(v),
          onmousemove: () => { if (activo !== i) { activo = i; marcar(); } },
        }, h("span", { class: "mono" }, String(v.valor)), v.texto ? h("span", { class: "muted" }, v.texto) : null))
      : aviso("Sin coincidencias."));
    pie.textContent = [nota, truncado ? `Se muestran los primeros ${valores.length}: lo que escribas se busca en la base.` : ""].filter(Boolean).join(" ");
    pie.style.display = pie.textContent ? "" : "none";
    marcar();
  };
  const cargar = async (buscar) => {
    buscado = buscar;
    try {
      const r = await fuente.cargar(buscar);
      if (buscado !== buscar) return;
      ({ valores, truncado = false, nota = "" } = r);
      error = "";
    } catch (e) { error = e.message; valores = []; }
    if (menuAbierto !== m) return;
    pintar();
    if (!buscar) { activo = Math.max(0, visibles.findIndex(igual)); mover(0); }
  };
  filtro.addEventListener("input", () => {
    activo = 0; pintar();
    // Si la base tiene mas filas que las traidas, se busca en la base (y se vuelve a la lista completa al borrar).
    if (fuente.cargar && (truncado || buscado)) {
      clearTimeout(espera);
      espera = setTimeout(() => cargar(filtro.value.trim()), 300);
    }
  });
  filtro.addEventListener("keydown", (ev) => {
    if (ev.key === "ArrowDown") { ev.preventDefault(); mover(1); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); mover(-1); }
    else if (ev.key === "Enter") { ev.preventDefault(); if (visibles[activo]) elegir(visibles[activo]); }
    else if (ev.key === "Escape" || ev.key === "Tab") { if (ev.key === "Escape") { ev.preventDefault(); ev.stopPropagation(); } cerrarMenu(); ancla.querySelector("input")?.focus(); }
  });
  document.body.appendChild(m);
  const r = ancla.getBoundingClientRect();
  m.style.minWidth = Math.max(r.width, 260) + "px";
  m.style.left = Math.max(8, Math.min(r.left, innerWidth - m.offsetWidth - 8)) + "px";
  const abajo = innerHeight - r.bottom - 10;
  if (abajo >= 240 || abajo >= r.top) { m.style.top = (r.bottom + 2) + "px"; m.style.maxHeight = abajo + "px"; }
  else { m.style.bottom = (innerHeight - r.top + 2) + "px"; m.style.maxHeight = (r.top - 10) + "px"; }
  menuAbierto = m;
  setTimeout(() => document.addEventListener("mousedown", cerrarMenuFuera), 0);
  pintar();
  activo = Math.max(0, visibles.findIndex(igual));
  mover(0);
  filtro.focus();
  if (valores === null) cargar("");
}

// ---------------------------------------------------------------------- tablas
function tablaFilas(columnas, filas, { max = 2000 } = {}) {
  if (!filas || !filas.length) return h("div", { class: "muted chico", style: { padding: "8px" } }, "Sin filas.");
  const cols = columnas && columnas.length ? columnas : Object.keys(filas[0]);
  const celda = (v) => {
    if (v === null || v === undefined) return h("td", { class: "mono" }, h("span", { class: "muted" }, "NULL"));
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    const m = s.match(/ +$/);
    return h("td", { class: "mono" }, m && s.trim() ? [s.trimEnd(), h("span", { class: "muted", title: `${m[0].length} espacios` }, "·".repeat(Math.min(m[0].length, 20)))] : s);
  };
  return h("div", { class: "tabla-scroll" }, h("table", { class: "tabla" },
    h("thead", null, h("tr", null, cols.map((c) => h("th", null, c)))),
    h("tbody", null, filas.slice(0, max).map((f) => h("tr", null, cols.map((c) => celda(Array.isArray(f) ? f[cols.indexOf(c)] : f[c])))))));
}

// ---------------------------------------------------------------------- script previo
// Bloques {ds, sql}: el script previo de una suite o el SQL previo de Explorar. Cada bloque puede tener varias
// sentencias separadas por ";". El elemento devuelto tiene .valor(): los bloques que tienen texto.
function editorScript(bloques, datasources, { alCambiar, filas = 5, placeholder = "" } = {}) {
  const lista = clonar(bloques || []);
  const cont = h("div");
  const avisar = () => alCambiar && alCambiar(lista);
  const pintar = () => vaciar(cont, lista.map((b, i) => {
    if (!b.ds && datasources.length) b.ds = datasources[datasources.length - 1]; // el que se usa sin nombre
    const opciones = [...datasources, ...(b.ds && !datasources.includes(b.ds) ? [b.ds] : [])];
    return h("div", { class: "fila", style: { marginBottom: "6px", alignItems: "flex-start", flexWrap: "nowrap" } },
      h("select", { style: { width: "auto", flex: "none" }, onchange: (ev) => { b.ds = ev.target.value; avisar(); } }, opciones.map((d) => h("option", { value: d, selected: d === b.ds ? "" : null }, d))),
      h("textarea", { class: "codigo", rows: filas, spellcheck: "false", placeholder, style: { flex: 1, width: "auto", minWidth: 0 }, oninput: (ev) => { b.sql = ev.target.value; avisar(); } }, b.sql || ""),
      h("button", { class: "btn fantasma icono", title: "Quitar", onclick: () => { lista.splice(i, 1); avisar(); pintar(); } }, "✕"));
  }), h("button", { class: "btn chico", onclick: () => { lista.push({ ds: datasources[datasources.length - 1] || "", sql: "" }); avisar(); pintar(); } },
    lista.length ? "+ otro datasource" : "+ sentencias"));
  pintar();
  cont.valor = () => lista.filter((b) => (b.sql || "").trim()).map((b) => ({ ds: b.ds || "", sql: b.sql }));
  return cont;
}

// El resultado del script previo: una línea (sentencias, filas cambiadas, tiempo) y el detalle por sentencia.
function vistaScript(sp, titulo = "Script previo") {
  if (!sp) return null;
  const sents = sp.bloques.flatMap((b) => b.sentencias);
  const filas = sents.reduce((a, s) => a + (s.actualizadas || 0), 0);
  const det = h("div", { style: { display: sp.estado === "ok" ? "none" : "block", marginTop: "6px" } },
    sp.bloques.map((b) => h("div", { style: { marginBottom: "6px" } },
      b.ds ? h("div", { class: "chico muted" }, b.ds) : null,
      b.sentencias.length ? tablaFilas(["Sentencia", "Filas", "ms"], b.sentencias.map((s) => ({
        Sentencia: s.sql, Filas: s.actualizadas ?? (s.filas !== undefined ? `${s.filas} (consulta)` : "—"), ms: s.ms,
      }))) : null,
      b.error ? h("div", { class: "error-caja" }, b.error) : null)));
  const cab = h("div", { class: "fila", style: { cursor: "pointer" }, title: "Ver cada sentencia" },
    h("span", { class: `punto-estado ${sp.estado}` }), h("b", null, titulo), pillEstado(sp.estado),
    h("span", { class: "muted chico" }, `${sents.length} sentencia${sents.length === 1 ? "" : "s"} · ${filas} filas cambiadas · ${fmtMs(sp.ms)}`,
      sp.veces > 1 ? ` · corrió ${sp.veces} veces` : ""),
    h("span", { class: "espacio" }), h("span", { class: "chico muted" }, "detalle ▾"));
  cab.addEventListener("click", () => { det.style.display = det.style.display === "none" ? "block" : "none"; });
  return h("div", { style: { border: "1px solid var(--borde)", borderRadius: "8px", padding: "8px 10px", marginBottom: "8px", background: "var(--panel-2)" } }, cab, det);
}

// Casos encadenados: las variables que el caso recibió de los anteriores (lo que guardaron con «guardar»).
function variablesRecibidas(vars) {
  return h("div", { class: "chico", style: { margin: "0 0 8px" } }, h("span", { class: "muted" }, "Recibió de los casos anteriores: "),
    Object.entries(vars).map(([k, v], i) => [i ? ", " : "", h("code", null, "${" + k + "}"), " = ", h("code", null, resumirValor(v, 40))]));
}

// ---------------------------------------------------------------------- resultado de un caso
/**
 * Muestra el resultado de un caso (pasos, diferencias, verificaciones, salidas): Explorar e Historial. La
 * pantalla Suites usa la ficha del caso (casos.js), que ademas muestra y edita lo que controla cada paso.
 * ctx: { caso (definicion), alVerificar(pasoIdx, ruta, valor, ev), abrirTodo }
 */
function vistaResultado(res, ctx = {}) {
  const cont = h("div");
  const ms = res.ms !== undefined ? fmtMs(res.ms) : "";
  cont.appendChild(h("div", { class: `banda ${res.estado}` },
    h("span", { class: `punto-estado ${res.estado}` }), NOMBRE_ESTADO[res.estado] || res.estado,
    h("span", { style: { fontWeight: 400 } }, res.nombre ? ` · ${res.nombre}` : ""),
    h("span", { class: "der" }, res.transaccion ? `transacción: ${res.transaccion} · ` : "", ms)));
  if (res.scriptPrevio) cont.appendChild(vistaScript(res.scriptPrevio, ctx.tituloScript));
  if (res.variablesRecibidas) cont.appendChild(variablesRecibidas(res.variablesRecibidas));
  for (const a of res.advertencias || []) cont.appendChild(h("div", { class: "aviso-caja" }, "⚠ ", a));
  const pasos = res.pasos || [];
  const sinPrep = pasos.filter((p) => !p.preparacion);
  pasos.forEach((p, i) => {
    const idxDef = p.preparacion ? -1 : sinPrep.indexOf(p);
    cont.appendChild(vistaPaso(p, idxDef, res, ctx, (ctx.abrirTodo && !p.preparacion) || pasos.length === 1 || p.estado !== "ok"));
  });
  if (!pasos.length && !res.scriptPrevio) cont.appendChild(h("div", { class: "muted" }, "El caso no tiene pasos."));
  return cont;
}

// Una línea por grupo de diferencias (el servidor las agrupa: Registros[*].Importe cambió en 12 de 40).
function gruposDiferencias(p) {
  return p.resumen || (p.diferencias || []).map((d) => ({ ruta: d.ruta, tipo: d.tipo, origen: d.origen, mensaje: d.mensaje, cantidad: 1, ejemplos: [d] }));
}
const esCampoClave = (ruta) => /\.Output\.Ok$|\.Output\.Messages(\[\*\])?(\.Code)?$/i.test(ruta);
function textoCambio(g) {
  const ej = g.ejemplos[0];
  if (g.tipo === "falta") return "ya no está en la salida";
  if (g.tipo === "sobra") return "apareció en la salida";
  if (g.tipo === "largo") return `tenía ${ej.esperado} elementos, ahora ${ej.obtenido}`;
  if (g.tipo === "clave") return "cambió el resultado (Ok o códigos de mensaje)";
  if (g.tipo === "tipo") return g.mensaje || "cambió el tipo";
  if (g.tipo === "error") return g.mensaje || "error";
  return g.origen === "lineaBase" ? "cambió" : (g.mensaje || "no es el esperado");
}

function vistaPaso(p, idx, res, ctx, abierto) {
  const vOk = (p.verificaciones || []).filter((v) => v.ok).length;
  const vMal = (p.verificaciones || []).length - vOk;
  const grupos = gruposDiferencias(p);
  const def = ctx.caso && idx >= 0 ? ctx.caso.pasos[idx] : null;
  const volatiles = def?.volatiles || [];
  const cab = h("div", { class: "cab" },
    h("span", { class: `punto-estado ${p.estado}` }),
    h("span", { class: "nombre" }, p.preparacion ? "Preparación: " : "", p.nombre),
    p.tipo === "sql" ? pill("SQL", "acento") : p.objeto && p.objeto !== p.nombre ? h("span", { class: "muted mono chico" }, p.objeto) : null,
    pillEstado(p.estado),
    grupos.length ? pill(`${grupos.length} cambio${grupos.length > 1 ? "s" : ""}`, "falla") : null,
    vOk ? pill(`✔ ${vOk}`, "ok") : null, vMal ? pill(`✖ ${vMal}`, "falla") : null,
    p.conLineaBase ? h("span", { class: "pill acento", title: p.comparar === "estructura" ? "Se controla que la salida tenga la misma forma (campos y tipos), Ok y los códigos de mensaje. No se comparan los valores." : "Toda la salida tiene que coincidir con la aprobada." }, p.comparar === "estructura" ? "compara: estructura" : "compara: todo") : null,
    volatiles.length ? h("span", { class: "pill", title: "Cambian solos en cada ejecución: solo se controla que existan y tengan el mismo tipo.\n" + volatiles.join("\n") }, `${volatiles.length} cambian solos`) : null,
    p.lineaBaseGrabada ? pill("salida aprobada", "aviso") : null,
    p.errorEsperado ? pill("error esperado", "acento") : null,
    h("span", { class: "espacio" }), h("span", { class: "muted chico" }, fmtMs(p.ms)));
  const cuerpo = h("div", { class: "cuerpo" });
  const caja = h("div", { class: `paso ${abierto ? "abierto" : ""}` }, cab, cuerpo);
  let pintado = false;
  const pintar = () => {
    if (pintado) return; pintado = true;
    for (const a of p.advertencias || []) cuerpo.appendChild(h("div", { class: "aviso-caja" }, "⚠ ", a));
    if (p.error) cuerpo.appendChild(h("div", { class: "error-caja" }, p.error));
    if (p.estado === "omitido") cuerpo.appendChild(h("div", { class: "muted" }, "No se ejecutó porque falló un paso anterior."));
    if (grupos.length) {
      const cuantos = (g) => g.de && g.cantidad > 1 ? ` · en ${g.cantidad} de ${g.de} elementos` : g.cantidad > 1 ? ` · ${g.cantidad} veces` : "";
      cuerpo.appendChild(h("table", { class: "tabla difs", style: { marginBottom: "10px" } },
        h("thead", null, h("tr", null, h("th", null, "Qué cambió"), h("th", null, p.conLineaBase ? "Aprobado" : "Esperado"), h("th", null, "Obtenido"))),
        h("tbody", null, grupos.map((g) => h("tr", null,
          h("td", null, h("code", null, g.ruta), h("div", { class: "chico muted" }, textoCambio(g), cuantos(g), g.origen === "lineaBase" ? "" : " · según «esperado»")),
          h("td", { class: "esp" }, g.tipo === "sobra" ? "—" : resumirValor(g.ejemplos[0].esperado, 140)),
          h("td", { class: "obt" }, g.tipo === "falta" ? "—" : resumirValor(g.ejemplos[0].obtenido, 140)))))));
      if (p.diferenciasOmitidas) cuerpo.appendChild(h("div", { class: "muted chico", style: { marginBottom: "8px" } }, `(${p.diferenciasOmitidas} diferencias más, incluidas en los totales)`));
    }
    if ((p.verificaciones || []).length) {
      cuerpo.appendChild(h("div", { style: { marginBottom: "8px" } }, p.verificaciones.map((v) => h("div", { class: `verif ${v.ok ? "ok" : "mal"}` },
        h("span", { class: "ic" }, v.ok ? "✔" : "✖"),
        h("span", null, h("code", null, v.ruta || "$"), " ", h("b", null, v.op.replace("_", " ")), v.cada ? " (cada uno)" : "", " ",
          v.valor !== undefined && v.valor !== null ? h("code", null, resumirValor(v.valor, 100)) : "",
          v.descripcion ? h("span", { class: "muted" }, ` — ${v.descripcion}`) : "",
          !v.ok ? h("div", { class: "chico", style: { color: "var(--falla)" } }, `obtenido ${resumirValor(v.obtenido, 160)}${v.mensaje ? " · " + v.mensaje : ""}`) : null)))));
    }
    const resaltar = new Set([...(p.diferencias || []).map((d) => d.ruta), ...grupos.flatMap((g) => g.ejemplos.map((e) => e.ruta))]);
    const pests = [];
    if (p.datos !== undefined && p.datos !== null) {
      if (p.tipo === "sql" && p.datos.filas) {
        pests.push({ id: "filas", texto: "Filas", n: p.datos.cantidad, render: () => tablaFilas(p.datos.columnas, p.datos.filas) });
      }
      pests.push({
        id: "salida", texto: p.tipo === "sql" ? "Árbol" : "Salida", render: () => arbolJson(p.datos, {
          resaltar, abrirHasta: 3,
          alClic: ctx.alVerificar ? (ruta, valor, ev) => ctx.alVerificar(idx, ruta, valor, ev, p) : undefined,
        }),
      });
      pests.push({ id: "json", texto: "JSON", render: () => h("pre", { class: "bloque" }, json(p.datos)) });
    }
    if (p.entrada) pests.push({ id: "entrada", texto: "Entrada", render: () => h("pre", { class: "bloque" }, json(p.entrada)) });
    if (p.sql) pests.push({ id: "consulta", texto: "Consulta", render: () => h("pre", { class: "bloque" }, (p.ds ? `-- ${p.ds}\n` : "") + p.sql) });
    if (p.excepcion) pests.push({ id: "excepcion", texto: "Excepción", render: () => h("pre", { class: "bloque err" }, p.excepcion) });
    if (p.consola) pests.push({ id: "consola", texto: "Consola", render: () => h("pre", { class: "bloque" }, p.consola) });
    if (pests.length) cuerpo.appendChild(subpestanas(pests, p.excepcion && p.estado === "error" ? "excepcion" : pests[0].id));
    const acciones = h("div", { class: "fila", style: { marginTop: "8px" } });
    if (p.datos !== undefined && p.datos !== null) {
      acciones.appendChild(h("button", { class: "btn chico", onclick: () => copiar(json(p.datos)) }, "Copiar salida"));
      if (ctx.alVerificar) acciones.appendChild(h("span", { class: "muted chico" }, "Tip: hacé clic en un valor de la salida para agregar una verificación."));
    }
    if (acciones.childNodes.length) cuerpo.appendChild(acciones);
  };
  cab.addEventListener("click", () => { caja.classList.toggle("abierto"); pintar(); });
  if (abierto) pintar();
  return caja;
}

/** Menu para crear una verificacion a partir de un valor de la salida. Llama a alElegir(verificacion).
 *  alOtra() (opcional) abre el editor completo de verificaciones. */
function menuVerificacion(ev, ruta, valor, alElegir, alOtra, alVariable) {
  const r = ruta || "$";
  const esObj = valor && typeof valor === "object";
  const ops = [];
  if (!esObj) {
    ops.push({ texto: `Es igual a ${resumirValor(typeof valor === "string" ? valor.trimEnd() : valor, 40)}`, accion: () => alElegir({ ruta, op: "igual", valor: typeof valor === "string" ? valor.trimEnd() : valor }) });
    if (typeof valor === "string" && valor.trim()) ops.push({ texto: "Contiene…", accion: async () => { const t = await pedirTexto("Contiene", `Texto que tiene que contener ${r}`, valor.trim()); if (t !== null) alElegir({ ruta, op: "contiene", valor: t }); } });
    if (typeof valor === "number") {
      ops.push({ texto: "Es mayor o igual a…", accion: async () => { const t = await pedirTexto("Mayor o igual", r, String(valor)); if (t !== null) alElegir({ ruta, op: "mayor_igual", valor: Number(t) }); } });
    }
  } else if (Array.isArray(valor)) {
    ops.push({ texto: `Tiene ${valor.length} elementos`, accion: () => alElegir({ ruta, op: "largo", valor: valor.length }) });
    ops.push({ texto: "Tiene al menos 1 elemento", accion: () => alElegir({ ruta, op: "largo_min", valor: 1 }) });
    ops.push({ texto: "Es igual a esta lista completa", accion: () => alElegir({ ruta, op: "igual", valor }) });
  } else {
    ops.push({ texto: "Coincide con este objeto (parcial)", accion: () => alElegir({ ruta, op: "coincide", valor }) });
  }
  // Generalizar el indice: Registros[2].Tipo -> Registros[*].Tipo
  if (/\[\d+\]/.test(ruta) && !esObj) {
    const g = ruta.replace(/\[\d+\](?!.*\[\d+\])/, "[*]");
    ops.push({ texto: `Alguno de ${g} es ${resumirValor(typeof valor === "string" ? valor.trimEnd() : valor, 30)}`, accion: () => alElegir({ ruta: g, op: "contiene", valor: typeof valor === "string" ? valor.trimEnd() : valor }) });
  }
  ops.push("-");
  ops.push({ texto: "Existe", accion: () => alElegir({ ruta, op: "existe" }) });
  ops.push({ texto: "No está vacío", accion: () => alElegir({ ruta, op: "no_vacio" }) });
  ops.push({ texto: `Es de tipo ${valor === null ? "nulo" : Array.isArray(valor) ? "lista" : typeof valor === "number" ? "numero" : typeof valor === "boolean" ? "booleano" : typeof valor === "string" ? "texto" : "objeto"}`,
    accion: () => alElegir({ ruta, op: "tipo", valor: valor === null ? "nulo" : Array.isArray(valor) ? "lista" : typeof valor === "number" ? "numero" : typeof valor === "boolean" ? "booleano" : typeof valor === "string" ? "texto" : "objeto" }) });
  if (alOtra) ops.push({ texto: "Otra condición…", accion: alOtra });
  ops.push("-");
  ops.push({ texto: "No comparar este campo (cambia y no es un error)", accion: () => alElegir({ ignorar: ruta.replace(/\[\d+\]/g, "[*]") }) });
  if (alVariable) ops.push({ texto: "Guardar como variable… (para usarla como ${nombre})", accion: alVariable });
  ops.push({ texto: "Copiar ruta", accion: () => copiar(ruta) });
  menu(ev.clientX, ev.clientY, r, ops);
}
