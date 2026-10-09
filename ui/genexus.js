/* GxPruebas - pantalla GeneXus: Update y Build de las KBs con MSBuild (gxp/genexus.py).
   Se eligen una, varias o todas las KBs; Update y Build son botones independientes. */
"use strict";

const GX = {
  sel: new Set(almacen.leer("gx.sel", [])),   // KBs tildadas
  forzar: almacen.leer("gx.forzar", false),   // Build: rehacer todo
  kbs: [],
  trabajos: [],
  error: null,
  logId: null,                                // trabajo cuyo log se ve
  logDesde: 0,
  logLineas: [],
  timer: null,
  armada: false,
};

const NOMBRE_GX = { update: "Update", build: "Build" };
const ESTADO_GX = { en_cola: ["En cola", "aviso"], corriendo: ["En curso", "acento"], ok: ["OK", "ok"], error: ["Error", "falla"], cancelado: ["Cancelado", ""] };
const activoGx = (t) => t.estado === "en_cola" || t.estado === "corriendo";

function pintarGx() {
  if (!GX.armada) armarGx();
  refrescarGx();
  detenerRefrescoGx();
  GX.timer = setInterval(refrescarGx, 2000);
}

function detenerRefrescoGx() { clearInterval(GX.timer); GX.timer = null; }

function armarGx() {
  const cont = $("#contenido-genexus");
  const forzar = h("input", { type: "checkbox", checked: GX.forzar });
  forzar.addEventListener("change", () => { GX.forzar = forzar.checked; almacen.guardar("gx.forzar", GX.forzar); });
  vaciar(cont,
    h("h2", { class: "titulo" }, "GeneXus: Update y Build"),
    h("div", { class: "muted chico", style: { marginBottom: "10px" } },
      "Corre los targets Update y Build de TeamDev.msbuild sobre las KBs que tildes. Son independientes: podés hacer Update de unas y Build de otras. ",
      "Una KB hace una cosa a la vez; KBs distintas corren en paralelo. Una KB abierta en el IDE no se puede procesar."),
    h("div", { class: "error-caja", id: "gx-error", hidden: true }),
    h("div", { class: "subtitulo" },
      h("button", { class: "btn prim", id: "gx-update", onclick: () => ejecutarGx("update"), title: "UpdateFromServer: trae los cambios del servidor" }, "Update"),
      h("button", { class: "btn prim", id: "gx-build", onclick: () => ejecutarGx("build"), title: "BuildAll: especifica, genera y compila lo desactualizado" }, "Build"),
      h("label", { class: "chk", title: "ForceRebuild: rehace todo en vez de solo lo desactualizado" }, forzar, "Build completo (rebuild)"),
      h("span", { class: "espacio" }),
      h("span", { class: "muted chico", id: "gx-info" })),
    h("div", { class: "tabla-scroll", style: { maxHeight: "none" } },
      h("table", { class: "tabla" },
        h("thead", null, h("tr", null,
          h("th", { style: { width: "28px" } }, h("input", { type: "checkbox", id: "gx-todas", title: "Todas / ninguna", onchange: (ev) => {
            GX.sel = ev.target.checked ? new Set(GX.kbs.filter(seleccionableGx).map((k) => k.nombre)) : new Set();
            guardarSelGx(); pintarTablaGx();
          } })),
          h("th", null, "KB"), h("th", null, "Update"), h("th", null, "Build"))),
        h("tbody", { id: "gx-filas" }))),
    h("h3", { class: "titulo-seccion", id: "gx-log-titulo" }, "Salida"),
    h("pre", { id: "gx-log", class: "mono", style: { maxHeight: "360px", overflow: "auto", background: "var(--panel-2)", border: "1px solid var(--borde)", borderRadius: "6px", padding: "8px 10px", whiteSpace: "pre-wrap", overflowWrap: "anywhere", margin: 0 } },
      "Elegí un trabajo de la tabla para ver su salida."));
  GX.armada = true;
}

const seleccionableGx = (k) => !k.enIde;
function guardarSelGx() { almacen.guardar("gx.sel", [...GX.sel]); }

async function refrescarGx() {
  try {
    const r = await GET("/api/gx/estado");
    GX.kbs = r.kbs; GX.trabajos = r.trabajos; GX.error = r.error;
    const mias = new Set(GX.kbs.map((k) => k.nombre));
    for (const n of [...GX.sel]) if (!mias.has(n)) GX.sel.delete(n);
  } catch (e) {
    GX.error = e.message;
  }
  pintarTablaGx();
  if (GX.logId) await refrescarLogGx();
}

function fmtSegGx(s) {
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function celdaTrabajoGx(k, accion) {
  const t = k[accion];
  if (!t) return h("span", { class: "muted" }, "—");
  const [txt, clase] = ESTADO_GX[t.estado] || [t.estado, ""];
  const partes = [pill(txt, clase), h("span", { class: "muted chico" }, ` #${t.id}${t.segundos != null ? ` ${fmtSegGx(t.segundos)}` : ""}`)];
  if (activoGx(t)) partes.push(" ", h("button", { class: "btn chico fantasma peligro", title: "Cancelar", onclick: (ev) => { ev.stopPropagation(); cancelarGx(t.id); } }, "✕"));
  if ((t.estado === "error" || t.estado === "cancelado") && t.mensaje) partes.push(h("div", { class: "chico", style: { color: "var(--falla)" } }, t.mensaje));
  return h("div", { style: { cursor: "pointer" }, title: "Ver la salida", onclick: () => verLogGx(t.id) }, partes);
}

function pintarTablaGx() {
  const filas = $("#gx-filas");
  if (!filas) return;
  const err = $("#gx-error");
  err.hidden = !GX.error; err.textContent = GX.error || "";
  vaciar(filas, ...GX.kbs.map((k) => {
    const chk = h("input", { type: "checkbox", checked: GX.sel.has(k.nombre), disabled: !seleccionableGx(k) });
    chk.addEventListener("change", () => { chk.checked ? GX.sel.add(k.nombre) : GX.sel.delete(k.nombre); guardarSelGx(); pintarTablaGx(); });
    return h("tr", { class: GX.sel.has(k.nombre) ? "sel" : "" },
      h("td", null, chk),
      h("td", null, h("b", null, k.nombre), " ", k.enIde ? pill("abierta en el IDE", "aviso") : null,
        h("div", { class: "muted chico mono" }, k.carpeta)),
      h("td", null, celdaTrabajoGx(k, "update")),
      h("td", null, celdaTrabajoGx(k, "build")));
  }));
  const posibles = GX.kbs.filter(seleccionableGx);
  $("#gx-todas").checked = posibles.length > 0 && posibles.every((k) => GX.sel.has(k.nombre));
  const n = GX.sel.size;
  $("#gx-update").disabled = $("#gx-build").disabled = n === 0 || !!GX.error;
  const activos = GX.trabajos.filter(activoGx).length;
  $("#gx-info").textContent = `${n} KB${n === 1 ? "" : "s"} elegida${n === 1 ? "" : "s"}${activos ? ` · ${activos} trabajo${activos === 1 ? "" : "s"} activo${activos === 1 ? "" : "s"}` : ""}`;
}

async function ejecutarGx(accion) {
  const kbs = [...GX.sel];
  if (!kbs.length) return;
  if (accion === "build" && GX.forzar && !await confirmar(`Rebuild completo de ${kbs.length} KB${kbs.length === 1 ? "" : "s"}: puede tardar mucho. ¿Seguir?`, { si: "Rebuild" })) return;
  try {
    const r = await POST("/api/gx/ejecutar", { accion, kbs, forzar: GX.forzar });
    const omitidas = r.filter((x) => x.omitido);
    const lanzadas = r.filter((x) => x.id);
    if (lanzadas.length) toast(`${NOMBRE_GX[accion]}: ${lanzadas.length} KB${lanzadas.length === 1 ? "" : "s"} en marcha`, "ok");
    if (omitidas.length) toast(omitidas.map((x) => `${x.kb}: ${x.omitido}`).join("\n"), "error");
    if (lanzadas.length === 1) verLogGx(lanzadas[0].id);
  } catch (e) { toast(e.message, "error"); }
  refrescarGx();
}

async function cancelarGx(id) {
  try { await POST("/api/gx/cancelar", { id }); } catch (e) { toast(e.message, "error"); }
  refrescarGx();
}

function verLogGx(id) {
  GX.logId = id; GX.logDesde = 0; GX.logLineas = [];
  refrescarLogGx();
}

async function refrescarLogGx() {
  const id = GX.logId;
  let r;
  try { r = await GET("/api/gx/log", { id, desde: GX.logDesde }); } catch (e) { return; }
  if (id !== GX.logId) return;
  const caja = $("#gx-log");
  const abajo = caja.scrollHeight - caja.scrollTop - caja.clientHeight < 30;
  if (r.desde > GX.logDesde) GX.logLineas.push("…");  // se descartaron lineas viejas
  GX.logLineas.push(...r.lineas);
  GX.logDesde = r.desde + r.lineas.length;
  const t = r.trabajo;
  $("#gx-log-titulo").textContent = `Salida: ${NOMBRE_GX[t.accion]} de ${t.kb} (#${t.id}) · ${(ESTADO_GX[t.estado] || [t.estado])[0]}`;
  caja.textContent = GX.logLineas.join("\n") || "(sin salida todavía)";
  if (abajo) caja.scrollTop = caja.scrollHeight;
}
