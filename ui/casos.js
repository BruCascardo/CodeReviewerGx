/* GxPruebas - ficha de un caso en la pantalla Suites.
 *
 * Cada paso muestra siempre "Qué controla" (sale de la definicion del caso, aunque nunca se haya corrido):
 * salida aprobada y como se compara, verificaciones con su resultado, lo que no se compara, lo que cambia
 * solo, el esperado parcial, si tiene que fallar y lo que guarda para los pasos siguientes. Todo se edita
 * ahi mismo. Abajo, el resultado de la ultima corrida, con la salida marcada segun lo que se controla.
 */
"use strict";

// op -> [frase, tipo de valor, sufijo]. Tipos: uno, ninguno, dos (entre), lista (en), numero, tipo, json.
const OPERADORES = {
  igual: ["es igual a", "uno"], distinto: ["es distinto de", "uno"],
  contiene: ["contiene", "uno"], no_contiene: ["no contiene", "uno"],
  empieza: ["empieza con", "uno"], termina: ["termina con", "uno"], regex: ["cumple el patrón", "uno"],
  mayor: ["es mayor que", "uno"], mayor_igual: ["es mayor o igual a", "uno"],
  menor: ["es menor que", "uno"], menor_igual: ["es menor o igual a", "uno"],
  entre: ["está entre", "dos"], en: ["es uno de", "lista"],
  existe: ["existe", "ninguno"], no_existe: ["no existe", "ninguno"],
  vacio: ["está vacío", "ninguno"], no_vacio: ["no está vacío", "ninguno"],
  largo: ["tiene exactamente", "numero", "elementos"], largo_min: ["tiene al menos", "numero", "elementos"],
  largo_max: ["tiene como máximo", "numero", "elementos"],
  tipo: ["es de tipo", "tipo"], coincide: ["coincide (en parte) con", "json"],
};
const TIPOS_JSON = ["texto", "numero", "booleano", "lista", "objeto", "nulo"];

/** Lo obtenido por una verificacion, corto: las listas como «lista de N elementos». */
const textoObtenido = (o) => Array.isArray(o) ? `lista de ${o.length} elemento${o.length === 1 ? "" : "s"}${o.length && o.length <= 5 && o.every((x) => x === null || typeof x !== "object") ? ": " + o.map((x) => resumirValor(x, 30)).join(", ") : ""}` : resumirValor(o, 160);
const tieneLineaBase = (def) => def.lineaBase !== undefined && def.lineaBase !== null;
const claveVerif = (v) => `${v.ruta}|${v.op}|${JSON.stringify(v.valor ?? null)}|${!!v.cada}`;

/** Texto legible de una verificacion: «Cada outList.Registros[*].ItfId es igual a 1». */
function textoVerificacion(v) {
  const [frase, tipo, sufijo] = OPERADORES[v.op] || [v.op.replace("_", " "), "uno"];
  let valor = null;
  if (tipo === "dos" && Array.isArray(v.valor)) valor = [h("code", null, resumirValor(v.valor[0], 40)), " y ", h("code", null, resumirValor(v.valor[1], 40))];
  else if (tipo !== "ninguno" && v.valor !== undefined) valor = h("code", null, resumirValor(v.valor, 80));
  const suf = sufijo && Number(v.valor) === 1 ? sufijo.replace(/s$/, "") : sufijo;
  return [v.cada ? "Cada " : "", h("code", null, v.ruta || "$"), ` ${frase} `, valor, suf ? ` ${suf}` : ""];
}

/** RegExp que reconoce las rutas concretas de la salida (Registros[3].Tipo) que corresponden a una ruta
 *  configurada (Registros[*].Tipo, Registros[-1].Tipo). Con 'rama', tambien las de adentro. */
function patronRuta(r, rama = false) {
  const p = (r || "").replace(/[.^$+?()|{}\\]/g, "\\$&")
    .replace(/\[\*\]|\[-\d+\]/g, "\\[\\d+\\]").replace(/\[(\d+)\]/g, "\\[$1\\]");
  return new RegExp(`^${p}${rama ? "(\\.|\\[|$)" : "$"}`, "i");
}

/** Valor de una ruta en una salida (para mostrar el valor actual en el editor). [*] devuelve la lista. */
function valorEn(datos, ruta) {
  const partes = (ruta || "").match(/[^.[\]]+|\[(-?\d+|\*)\]/g) || [];
  let actuales = [datos], comodin = false;
  for (const p of partes) {
    const sig = [];
    const idx = p.startsWith("[") ? p.slice(1, -1) : null;
    for (const a of actuales) {
      if (a === null || typeof a !== "object") continue;
      if (idx === "*") { comodin = true; sig.push(...(Array.isArray(a) ? a : Object.values(a))); }
      else if (idx !== null) { const n = Number(idx); if (Array.isArray(a) && a.at(n) !== undefined) sig.push(a.at(n)); }
      else { const k = Object.keys(a).find((x) => x === p) ?? Object.keys(a).find((x) => x.toLowerCase() === p.toLowerCase()); if (k !== undefined) sig.push(a[k]); }
    }
    actuales = sig;
  }
  if (comodin) return { existe: true, valor: actuales };
  return actuales.length ? { existe: true, valor: actuales[0] } : { existe: false };
}

/** Todas las rutas de una salida, con su variante [*] para las listas (para autocompletar). */
function rutasDe(datos, max = 400) {
  const salida = new Set();
  const rec = (v, r) => {
    if (salida.size > max) return;
    if (r) salida.add(r);
    if (Array.isArray(v)) {
      v.slice(0, 3).forEach((x, i) => rec(x, `${r}[${i}]`));
      if (v.length && v[0] && typeof v[0] === "object") rec(v[0], `${r}[*]`);
      else if (v.length) salida.add(`${r}[*]`);
    } else if (v && typeof v === "object") Object.keys(v).forEach((k) => rec(v[k], r ? `${r}.${k}` : k));
  };
  rec(datos, "");
  return [...salida];
}

// ---------------------------------------------------------------------- resumen para la lista de casos

/** Lo que controla un caso, en una linea: «salida aprobada · 3 verificaciones · 2 campos sin comparar». */
function resumenControles(caso) {
  const ps = caso.pasos || [];
  const n = (f) => ps.reduce((a, p) => a + f(p), 0);
  const partes = [];
  const lb = ps.filter(tieneLineaBase);
  if (lb.length) partes.push(lb.some((p) => p.comparar === "estructura") ? "salida aprobada (estructura)" : "salida aprobada");
  const v = n((p) => (p.verificaciones || []).length);
  if (v) partes.push(`${v} verificaci${v === 1 ? "ón" : "ones"}`);
  if (ps.some((p) => p.esperado && Object.keys(p.esperado).length)) partes.push("esperado");
  if (ps.some((p) => p.esperaError)) partes.push("tiene que fallar");
  const ign = n((p) => (p.ignorar || []).length);
  if (ign) partes.push(`${ign} campo${ign === 1 ? "" : "s"} sin comparar`);
  return partes;
}

/** Por que fallo un resultado: «2 verificaciones no se cumplen · 3 cambios en la salida». */
function motivoFalla(resultados) {
  let verif = 0, cambios = 0, errores = 0;
  for (const r of resultados) for (const p of r.pasos || []) {
    verif += (p.verificaciones || []).filter((v) => !v.ok).length;
    cambios += gruposDiferencias(p).length;
    if (p.estado === "error") errores++;
  }
  const partes = [];
  if (errores) partes.push(`${errores} paso${errores > 1 ? "s" : ""} con error`);
  if (verif) partes.push(`${verif} verificaci${verif === 1 ? "ón no se cumple" : "ones no se cumplen"}`);
  if (cambios) partes.push(`${cambios} cambio${cambios > 1 ? "s" : ""} en la salida`);
  return partes.join(" · ");
}

// ---------------------------------------------------------------------- ficha del caso

/**
 * ctx: { caso, resultados: [resultado por fila], fecha (de la corrida), sinCorrer,
 *        guardar(mutar(caso), mensaje), correr(), aceptar(paso, datos, fila, pr), editarJson() }
 */
function fichaCaso(ctx) {
  const { caso, resultados } = ctx;
  const cont = h("div", { class: "ficha" });
  const barra = h("div", { class: "fila ficha-barra" },
    resultados.length ? h("span", { class: "muted chico" }, ctx.fecha ? `Resultado de la corrida del ${fmtFecha(ctx.fecha)}` : "Resultado de esta corrida")
      : h("span", { class: "muted chico" }, "Todavía no se corrió: abajo está lo que va a controlar."),
    h("span", { class: "espacio" }),
    h("button", { class: "btn chico", disabled: !!E.trabajo, onclick: ctx.correr }, "▶ Correr este caso"),
    h("button", { class: "btn chico", onclick: ctx.editarJson, title: "Nombre, etiquetas, entrada, datos: todo el caso como JSON" }, "Editar JSON"));
  cont.appendChild(barra);
  if (ctx.sinCorrer && resultados.length) {
    cont.appendChild(h("div", { class: "aviso-caja fila" }, "Cambiaste lo que controla este caso después de esta corrida: el resultado de abajo puede no reflejarlo.",
      h("span", { class: "espacio" }), h("button", { class: "btn chico prim", disabled: !!E.trabajo, onclick: ctx.correr }, "▶ Correr ahora")));
  }
  if (caso.datos?.length) cont.appendChild(tablaDatos(caso));
  if (resultados.length > 1) {
    cont.appendChild(subpestanas(resultados.map((r, i) => ({
      id: String(i), texto: [h("span", { class: `punto-estado ${r.estado}`, style: { marginRight: "5px" } }), `Fila ${i + 1}`],
      render: () => pasosCaso(ctx, r),
    })), String(Math.max(0, resultados.findIndex((r) => r.estado !== "ok")))));
  } else cont.appendChild(pasosCaso(ctx, resultados[0] || null));
  return cont;
}

function tablaDatos(caso) {
  const cols = [...new Set(caso.datos.flatMap((d) => Object.keys(d)))];
  return h("div", { class: "datos-caso" },
    h("div", { class: "chico" }, h("b", null, `Se repite con ${caso.datos.length} filas de datos`), h("span", { class: "muted" }, " (las columnas se usan como ${variable})")),
    tablaFilas(cols.map((c) => "${" + c + "}"), caso.datos.map((d) => Object.fromEntries(cols.map((c) => ["${" + c + "}", d[c]])))));
}

function pasosCaso(ctx, res) {
  const prs = (res?.pasos || []).filter((p) => !p.preparacion);
  const preps = (res?.pasos || []).filter((p) => p.preparacion);
  const cont = h("div");
  for (const a of res?.advertencias || []) cont.appendChild(h("div", { class: "aviso-caja" }, "⚠ ", a));
  for (const p of preps) if (p.estado !== "ok") cont.appendChild(h("div", { class: "error-caja" }, `Preparación «${p.nombre}»: ${p.error || NOMBRE_ESTADO[p.estado]}`));
  const n = ctx.caso.pasos.length;
  ctx.caso.pasos.forEach((def, i) => cont.appendChild(tarjetaPaso(ctx, def, prs[i] || null, i, res, n)));
  if (!n) cont.appendChild(h("div", { class: "muted" }, "El caso no tiene pasos: agregalos con «Editar JSON»."));
  return cont;
}

function tarjetaPaso(ctx, def, pr, i, res, total) {
  const verifMal = (pr?.verificaciones || []).filter((v) => !v.ok).length;
  const grupos = pr ? gruposDiferencias(pr) : [];
  const estado = pr ? pr.estado : "sin-correr";
  const cab = h("div", { class: "cab" },
    h("span", { class: "num-paso" }, i + 1),
    h("span", { class: "nombre" }, def.nombre || corto(def.objeto) || "Consulta"),
    def.sql !== undefined ? pill("SQL", "acento") : h("span", { class: "muted mono chico" }, def.objeto),
    pr ? pillEstado(pr.estado) : pill("sin correr"),
    verifMal ? pill(`✖ ${verifMal} verificación${verifMal > 1 ? "es" : ""}`, "falla") : null,
    grupos.length ? pill(`${grupos.length} cambio${grupos.length > 1 ? "s" : ""}`, "falla") : null,
    h("span", { class: "espacio" }), pr?.ms !== undefined ? h("span", { class: "muted chico" }, fmtMs(pr.ms)) : null);
  const cuerpo = h("div", { class: "cuerpo" });
  const abierto = estado !== "ok" || total === 1 || E.pasosAbiertos?.has(`${ctx.caso.id}|${i}`);
  const caja = h("div", { class: `paso ${abierto ? "abierto" : ""} estado-${estado}` }, cab, cuerpo);
  let pintado = false;
  const pintar = () => {
    if (pintado) return;
    pintado = true;
    for (const a of pr?.advertencias || []) cuerpo.appendChild(h("div", { class: "aviso-caja" }, "⚠ ", a));
    if (pr?.error && !pr.errorEsperado) cuerpo.appendChild(h("div", { class: "error-caja" }, pr.error));
    if (pr?.estado === "omitido") cuerpo.appendChild(h("div", { class: "muted", style: { marginBottom: "8px" } }, "No se ejecutó porque falló un paso anterior."));
    cuerpo.appendChild(controlesPaso(ctx, def, pr, i, res));
    if (grupos.length) cuerpo.appendChild(cambiosPaso(ctx, def, pr, i, res, grupos));
    if (pr) cuerpo.appendChild(salidaPaso(ctx, def, pr, i, res));
  };
  cab.addEventListener("click", () => {
    caja.classList.toggle("abierto");
    const k = `${ctx.caso.id}|${i}`;
    E.pasosAbiertos = E.pasosAbiertos || new Set();
    caja.classList.contains("abierto") ? E.pasosAbiertos.add(k) : E.pasosAbiertos.delete(k);
    pintar();
  });
  if (abierto) pintar();
  return caja;
}

// ---------------------------------------------------------------------- "Qué controla"

function controlesPaso(ctx, def, pr, i, res) {
  const cambiar = (mutar, mensaje) => ctx.guardar((caso) => mutar(caso.pasos[i]), mensaje);
  const nombrePaso = def.nombre || corto(def.objeto) || "Consulta";
  const filas = [];
  const fila = (titulo, ayuda, ...contenido) => filas.push(h("div", { class: "control" },
    h("div", { class: "control-t" }, titulo, ayuda ? h("span", { class: "ayuda", title: ayuda }, "?") : null),
    h("div", { class: "control-c" }, contenido)));
  const icono = (ok, titulo) => h("span", { class: `ic-control ${ok === null ? "pend" : ok ? "ok" : "mal"}`, title: titulo || "" }, ok === null ? "○" : ok ? "✔" : "✖");
  const sinCorrer = "Todavía no se corrió con este control";

  // 1. Terminar con error
  if (def.esperaError) {
    const mal = pr && (pr.diferencias || []).some((d) => d.tipo === "error");
    fila("Resultado", "El paso pasa si termina con una excepción (y, si se indica, con ese texto).",
      icono(pr ? !mal && pr.estado !== "error" : null, pr ? "" : sinCorrer),
      h("span", null, "Tiene que terminar con error", def.errorContiene ? [" que contenga ", h("code", null, def.errorContiene)] : null),
      h("button", { class: "btn chico fantasma", onclick: () => cambiar((p) => { delete p.esperaError; delete p.errorContiene; }, `«${nombrePaso}» ya no espera un error`) }, "Quitar"));
  }

  // 2. Salida aprobada
  if (!def.esperaError) {
    if (tieneLineaBase(def)) {
      const estr = def.comparar === "estructura";
      const cambios = pr ? gruposDiferencias(pr).filter((g) => g.origen === "lineaBase").length : null;
      const seg = h("div", { class: "grupo-seg chico" }, [["todo", "Toda la salida"], ["estructura", "Solo estructura"]].map(([m, t]) => h("button", {
        class: (estr ? "estructura" : "todo") === m ? "activa" : "",
        title: m === "todo" ? "Cada valor tiene que coincidir con la salida aprobada (salvo lo que no se compara y lo que cambia solo)."
          : "Para listados con datos de la base que cambian: solo se controlan los campos, sus tipos, Ok y los códigos de mensaje.",
        onclick: () => (estr ? "estructura" : "todo") !== m && cambiar((p) => { if (m === "estructura") p.comparar = "estructura"; else delete p.comparar; },
          m === "estructura" ? `«${nombrePaso}» compara solo la estructura, Ok y los códigos de mensaje` : `«${nombrePaso}» compara toda la salida`),
      }, t)));
      fila("Salida aprobada", "Se compara con la salida que aprobaste («Guardar como caso» o «Aceptar esta salida»).",
        icono(pr && pr.estado !== "error" ? cambios === 0 : null, pr ? "" : sinCorrer),
        h("span", null, "Se compara contra la aprobada:"), seg,
        cambios ? h("span", { class: "chico", style: { color: "var(--falla)" } }, `${cambios} cambio${cambios > 1 ? "s" : ""} (abajo)`) : null,
        h("span", { class: "espacio" }),
        h("button", { class: "btn chico fantasma", title: "Dejar de comparar la salida (quedan solo las verificaciones)",
          onclick: async () => { if (await confirmar(`¿Quitar la salida aprobada de «${nombrePaso}»? Solo quedarían las verificaciones.`, { si: "Quitar", peligro: true })) cambiar((p) => { delete p.lineaBase; delete p.comparar; delete p.volatiles; }, "Salida aprobada quitada"); } }, "Quitar"));
    } else {
      fila("Salida aprobada", "Sin salida aprobada, la salida no se compara: solo cuentan las verificaciones.",
        h("span", { class: "muted" }, "No tiene: la salida no se compara."),
        pr?.datos != null && pr.estado !== "error"
          ? h("button", { class: "btn chico", onclick: () => ctx.aceptar(i, pr.datos, res?.fila, pr) }, "Aprobar la salida de esta corrida") : null);
    }
  }

  // 3. Verificaciones
  const verifs = def.verificaciones || [];
  const resultadoDe = (v, k) => {
    const rs = pr?.verificaciones || [];
    return rs.find((r) => claveVerif(r) === claveVerif(v)) || (rs.length === verifs.length ? rs[k] : null);
  };
  const lista = h("div", { class: "lista-verif" }, verifs.map((v, k) => {
    const r = resultadoDe(v, k);
    return h("div", { class: `verif ${r ? (r.ok ? "ok" : "mal") : "pend"}` },
      icono(r ? r.ok : null, r ? "" : sinCorrer),
      h("div", { class: "verif-texto" },
        h("div", null, textoVerificacion(v)),
        v.descripcion ? h("div", { class: "muted chico" }, v.descripcion) : null,
        r && !r.ok ? h("div", { class: "chico", style: { color: "var(--falla)" } }, `Obtenido: ${textoObtenido(r.obtenido)}${r.mensaje ? " · " + r.mensaje : ""}`) : null),
      h("button", { class: "btn fantasma icono chico", title: "Editar", onclick: () => editorVerificacion({ v, datos: pr?.datos, alGuardar: (nv) => cambiar((p) => { p.verificaciones[k] = nv; }, "Verificación modificada") }) }, "✎"),
      h("button", { class: "btn fantasma icono chico", title: "Quitar", onclick: () => cambiar((p) => { p.verificaciones.splice(k, 1); if (!p.verificaciones.length) delete p.verificaciones; }, "Verificación quitada") }, "✕"));
  }), h("button", {
    class: "btn chico", style: { alignSelf: "flex-start" },
    onclick: () => editorVerificacion({ datos: pr?.datos, alGuardar: (nv) => cambiar((p) => { (p.verificaciones = p.verificaciones || []).push(nv); }, "Verificación agregada") }),
  }, "+ Agregar verificación"));
  fila("Verificaciones", "Reglas que se tienen que cumplir siempre, aunque aceptes una salida nueva. También se agregan haciendo clic en un valor de la salida.", lista);

  // 4. Esperado (parcial)
  if (def.esperado && Object.keys(def.esperado).length) {
    const lineas = rutasHoja(def.esperado);
    const mal = pr ? (pr.diferencias || []).filter((d) => d.origen !== "lineaBase" && d.tipo !== "error").length : null;
    fila("Esperado", "Coincidencia parcial: solo se controla lo que está escrito (admite comodines como <<no_vacio>>).",
      icono(pr && pr.estado !== "error" ? !mal : null, pr ? "" : sinCorrer),
      h("div", { class: "chico mono" }, lineas.slice(0, 6).map(([r, v]) => h("div", null, r, " = ", resumirValor(v, 60))),
        lineas.length > 6 ? h("div", { class: "muted" }, `y ${lineas.length - 6} más`) : null),
      h("span", { class: "espacio" }),
      h("button", { class: "btn chico fantasma", onclick: () => editarJsonPaso(def.esperado, "Esperado (coincidencia parcial)", (nv) => cambiar((p) => { if (nv && Object.keys(nv).length) p.esperado = nv; else delete p.esperado; }, "Esperado modificado")) }, "Editar"));
  }

  // 5. Lo que no se compara y lo que cambia solo
  const chips = (rutas, quitar, titulo) => h("div", { class: "chips" }, rutas.map((r) => h("span", { class: "chip", title: titulo }, h("code", null, r),
    h("button", { title: "Quitar", onclick: () => quitar(r) }, "✕"))));
  if ((def.ignorar || []).length) {
    fila("No se comparan", "Campos que no se comparan con la salida aprobada: pueden cambiar sin que el caso falle.",
      chips(def.ignorar, (r) => cambiar((p) => { p.ignorar = p.ignorar.filter((x) => x !== r); if (!p.ignorar.length) delete p.ignorar; }, `Se vuelve a comparar ${r}`), "Clic en ✕ para volver a compararlo"));
  }
  if ((def.volatiles || []).length) {
    fila("Cambian solos", "Detectados al correr dos veces (fechas, ids nuevos): solo se controla que existan y que su tipo no cambie.",
      chips(def.volatiles, (r) => cambiar((p) => { p.volatiles = p.volatiles.filter((x) => x !== r); if (!p.volatiles.length) delete p.volatiles; }, `${r} se compara completo`), "Clic en ✕ para compararlo completo"));
  }

  // 6. Variables que guarda
  if (def.guardar && Object.keys(def.guardar).length) {
    fila("Guarda", "Valores de la salida que usan los pasos siguientes como ${variable}.",
      h("div", { class: "chips" }, Object.entries(def.guardar).map(([k, r]) => h("span", { class: "chip" },
        h("code", null, "${" + k + "}"), " ← ", h("code", null, r),
        h("button", { title: "Quitar", onclick: () => cambiar((p) => { delete p.guardar[k]; if (!Object.keys(p.guardar).length) delete p.guardar; }, `Ya no se guarda \${${k}}`) }, "✕")))));
  }

  const nada = !def.esperaError && !tieneLineaBase(def) && !verifs.length && !(def.esperado && Object.keys(def.esperado).length);
  return h("div", { class: "controles" },
    h("div", { class: "controles-cab" }, h("b", null, "Qué controla"),
      pr?.datos != null ? h("span", { class: "muted chico" }, "· también podés hacer clic en un valor de la salida") : null),
    nada ? h("div", { class: "aviso-caja" }, "Este paso no controla nada: da OK siempre que no termine con error. Aprobá la salida o agregá una verificación.") : null,
    filas);
}

/** [[ruta, valor]] de las hojas de un objeto (para mostrar el esperado). */
function rutasHoja(v, r = "", salida = []) {
  if (v && typeof v === "object" && Object.keys(v).length) {
    for (const [k, x] of Object.entries(v)) rutasHoja(x, Array.isArray(v) ? `${r}[${k}]` : r ? `${r}.${k}` : k, salida);
  } else salida.push([r || "$", v]);
  return salida;
}

function editarJsonPaso(valor, titulo, alGuardar) {
  const ed = editorJson(valor, { filas: 14 });
  modal({
    titulo, cuerpo: ed,
    botones: [{ texto: "Cancelar" }, { texto: "Guardar", prim: true, accion: () => { if (!ed.valido()) { toast("El JSON no es válido", "error"); return false; } alGuardar(ed.valor()); } }],
  });
}

// ---------------------------------------------------------------------- cambios y salida

function cambiosPaso(ctx, def, pr, i, res, grupos) {
  const cuantos = (g) => g.de && g.cantidad > 1 ? ` · en ${g.cantidad} de ${g.de} elementos` : g.cantidad > 1 ? ` · ${g.cantidad} veces` : "";
  const contraAprobada = grupos.some((g) => g.origen === "lineaBase");
  const ignorar = (ruta) => ctx.guardar((caso) => {
    const p = caso.pasos[i];
    if (!(p.ignorar = p.ignorar || []).includes(ruta)) p.ignorar.push(ruta);
  }, `No se compara más ${ruta}`);
  return h("div", { class: "cambios" },
    h("div", { class: "fila", style: { marginBottom: "6px" } },
      h("b", null, contraAprobada ? "Qué cambió contra la salida aprobada" : "Qué no coincide"),
      h("span", { class: "espacio" }),
      contraAprobada && pr.datos != null && pr.estado !== "error"
        ? [h("span", { class: "muted chico" }, "¿El cambio es correcto?"),
          h("button", { class: "btn chico prim", title: "Esta salida pasa a ser la aprobada", onclick: () => ctx.aceptar(i, pr.datos, res?.fila, pr) }, "Sí: aceptar esta salida")] : null),
    h("table", { class: "tabla difs" },
      h("thead", null, h("tr", null, h("th", null, "Campo"), h("th", null, contraAprobada ? "Aprobado" : "Esperado"), h("th", null, "Obtenido"), h("th", null, ""))),
      h("tbody", null, grupos.map((g) => h("tr", null,
        h("td", null, h("code", null, g.ruta), h("div", { class: "chico muted" }, textoCambio(g), cuantos(g), g.origen === "lineaBase" ? "" : " · según «esperado»")),
        h("td", { class: "esp" }, g.tipo === "sobra" ? "—" : resumirValor(g.ejemplos[0].esperado, 140)),
        h("td", { class: "obt" }, g.tipo === "falta" ? "—" : resumirValor(g.ejemplos[0].obtenido, 140)),
        h("td", null, g.origen === "lineaBase" && g.tipo !== "clave" && !esCampoClave(g.ruta)
          ? h("button", { class: "btn chico", title: "Este campo puede cambiar: no compararlo más", onclick: () => ignorar(g.ruta) }, "No comparar") : null))))),
    pr.diferenciasOmitidas ? h("div", { class: "muted chico" }, `(${pr.diferenciasOmitidas} diferencias más, incluidas en los totales)`) : null);
}

/** Etiquetas de la salida segun lo que controla el paso. */
function marcasPaso(def, pr) {
  const reglas = [];
  const verifs = def.verificaciones || [];
  verifs.forEach((v, k) => {
    const r = (pr?.verificaciones || []).find((x) => claveVerif(x) === claveVerif(v)) || ((pr?.verificaciones || []).length === verifs.length ? pr.verificaciones[k] : null);
    const frase = `${v.cada ? "Cada " : ""}${v.ruta} ${(OPERADORES[v.op] || [v.op])[0]} ${v.valor !== undefined ? resumirValor(v.valor, 40) : ""}`;
    reglas.push({ p: patronRuta(v.ruta), m: { texto: r ? (r.ok ? "✔ verificado" : "✖ verificado") : "○ verificado", clase: r ? (r.ok ? "ok" : "mal") : "", title: frase } });
  });
  for (const r of def.ignorar || []) reglas.push({ p: patronRuta(r), m: { texto: "no se compara", clase: "apagada", title: `«${r}» no se compara con la salida aprobada` } });
  for (const r of def.volatiles || []) reglas.push({ p: patronRuta(r), m: { texto: "cambia solo", clase: "vol", title: "Solo se controla que exista y su tipo" } });
  for (const [k, r] of Object.entries(def.guardar || {})) reglas.push({ p: patronRuta(r), m: { texto: "→ ${" + k + "}", clase: "guarda", title: "Se guarda para los pasos siguientes" } });
  return (ruta) => reglas.filter((x) => x.p.test(ruta)).map((x) => x.m);
}

function salidaPaso(ctx, def, pr, i, res) {
  const agregarVerif = (v) => ctx.guardar((caso) => {
    const p = caso.pasos[i];
    if (v.ignorar) { if (!(p.ignorar = p.ignorar || []).includes(v.ignorar)) p.ignorar.push(v.ignorar); }
    else (p.verificaciones = p.verificaciones || []).push(v);
  }, v.ignorar ? `No se compara más ${v.ignorar}` : "Verificación agregada");
  const alClic = (ruta, valor, ev) => menuVerificacion(ev, ruta, valor, agregarVerif,
    () => editorVerificacion({ v: { ruta, op: valor && typeof valor === "object" ? "no_vacio" : "igual", valor: typeof valor === "string" ? valor.trimEnd() : valor && typeof valor === "object" ? undefined : valor }, datos: pr.datos, alGuardar: agregarVerif }));
  const resaltar = new Set([...(pr.diferencias || []).map((d) => d.ruta), ...gruposDiferencias(pr).flatMap((g) => g.ejemplos.map((e) => e.ruta))]);
  const pests = [];
  if (pr.datos !== undefined && pr.datos !== null) {
    if (pr.tipo === "sql" && pr.datos.filas) pests.push({ id: "filas", texto: "Filas", n: pr.datos.cantidad, render: () => tablaFilas(pr.datos.columnas, pr.datos.filas) });
    pests.push({
      id: "salida", texto: pr.tipo === "sql" ? "Árbol" : "Salida",
      render: () => h("div", null,
        h("div", { class: "muted chico", style: { margin: "2px 0 4px" } }, "Clic en un valor para verificarlo o dejar de compararlo. Las marcas muestran lo que ya se controla."),
        arbolJson(pr.datos, { resaltar, abrirHasta: 3, alClic, marcas: marcasPaso(def, pr) })),
    });
    pests.push({ id: "json", texto: "JSON", render: () => h("div", null, h("button", { class: "btn chico", style: { marginBottom: "4px" }, onclick: () => copiar(json(pr.datos)) }, "Copiar"), h("pre", { class: "bloque" }, json(pr.datos))) });
  }
  if (pr.entrada) pests.push({ id: "entrada", texto: "Entrada", render: () => h("pre", { class: "bloque" }, json(pr.entrada)) });
  if (pr.sql) pests.push({ id: "consulta", texto: "Consulta", render: () => h("pre", { class: "bloque" }, (pr.ds ? `-- ${pr.ds}\n` : "") + pr.sql) });
  if (pr.excepcion) pests.push({ id: "excepcion", texto: "Excepción", render: () => h("pre", { class: "bloque err" }, pr.excepcion) });
  if (pr.consola) pests.push({ id: "consola", texto: "Consola", render: () => h("pre", { class: "bloque" }, pr.consola) });
  if (!pests.length) return h("div");
  return h("div", { class: "salida-paso" }, h("div", { class: "controles-cab" }, h("b", null, "Salida de la corrida")),
    subpestanas(pests, pr.excepcion && pr.estado === "error" ? "excepcion" : pests.find((p) => p.id === "salida") ? "salida" : pests[0].id));
}

// ---------------------------------------------------------------------- editor de una verificacion

/** Modal para crear o editar una verificacion. 'datos' (la ultima salida, opcional) da las rutas para
 *  autocompletar, el valor actual y la vista previa. alGuardar(verificacion). */
function editorVerificacion({ v = {}, datos, alGuardar }) {
  const hayDatos = datos !== undefined && datos !== null;
  const idLista = `rutas-${Math.random().toString(36).slice(2)}`;
  const ruta = h("input", { type: "text", value: v.ruta || "", list: idLista, placeholder: "outList.Registros[*].Tipo", spellcheck: "false", class: "mono" });
  const dl = h("datalist", { id: idLista }, hayDatos ? rutasDe(datos).map((r) => h("option", { value: r })) : null);
  const actual = h("div", { class: "chico muted mono", style: { minHeight: "18px", overflowWrap: "anywhere" } });
  const op = h("select", null, Object.entries(OPERADORES).map(([k, [frase]]) => h("option", { value: k, selected: (v.op || "igual") === k ? "" : null }, frase)));
  const valor = h("input", { type: "text", spellcheck: "false" });
  const valor2 = h("input", { type: "text", spellcheck: "false" });
  const valorTipo = h("select", null, TIPOS_JSON.map((t) => h("option", { value: t }, t)));
  const valorJson = h("textarea", { class: "codigo", rows: 5, spellcheck: "false" });
  const cada = h("input", { type: "checkbox", checked: !!v.cada });
  const filaCada = h("label", { class: "chk" }, cada, "Que se cumpla para cada elemento (si no, se evalúa sobre la lista)");
  const desc = h("input", { type: "text", value: v.descripcion || "", placeholder: "Opcional. Por ejemplo: «sin tipo de registro da REQUERIDO»" });
  const previa = h("div", { class: "previa-verif chico" });
  const cajaValor = h("div", { class: "fila", style: { gap: "6px", flexWrap: "nowrap" } });

  const texto = (x) => x === undefined ? "" : typeof x === "string" ? x : JSON.stringify(x);
  // Lo que se escribe se interpreta como JSON si se puede (12, true, null, [1,2]); si no, es texto. Si el
  // valor actual del campo es texto, se queda como texto ("001" no pasa a 1).
  const leer = (t) => {
    const actualEsTexto = typeof valorEn(datos, ruta.value.trim()).valor === "string";
    if (actualEsTexto && !/^[[{]/.test(t.trim())) return t;
    try { return JSON.parse(t); } catch { return t; }
  };
  const tipo = () => OPERADORES[op.value][1];
  const pintarValor = () => {
    const t = tipo();
    vaciar(cajaValor,
      t === "uno" || t === "lista" ? valor : null,
      t === "dos" ? [valor, h("span", { class: "muted" }, "y"), valor2] : null,
      t === "numero" ? [valor, h("span", { class: "muted" }, OPERADORES[op.value][2] || "")] : null,
      t === "tipo" ? valorTipo : null,
      t === "json" ? valorJson : null,
      t === "ninguno" ? h("span", { class: "muted chico" }, "(no lleva valor)") : null);
    // Si el campo es un objeto o una lista, el valor se escribe como JSON: se sugiere con el valor actual.
    const a = valorEn(datos, ruta.value.trim());
    const compuesto = a.existe && a.valor !== null && typeof a.valor === "object";
    valor.placeholder = t === "lista" ? "valores separados por coma" : t === "numero" ? "N"
      : compuesto ? `un JSON, por ejemplo ${resumirValor(a.valor, 60)}` : "valor";
    valor.style.width = t === "dos" ? "auto" : "100%";
    filaCada.style.display = /\[\*\]/.test(ruta.value) ? "" : "none";
  };
  // valores iniciales
  const t0 = (OPERADORES[v.op || "igual"] || [])[1];
  if (t0 === "dos" && Array.isArray(v.valor)) { valor.value = texto(v.valor[0]); valor2.value = texto(v.valor[1]); }
  else if (t0 === "lista" && Array.isArray(v.valor)) valor.value = v.valor.map(texto).join(", ");
  else if (t0 === "tipo") valorTipo.value = v.valor || "texto";
  else if (t0 === "json") valorJson.value = v.valor === undefined ? "" : json(v.valor);
  else valor.value = texto(v.valor);

  const armar = () => {
    const t = tipo();
    const r = { ruta: ruta.value.trim(), op: op.value };
    if (t === "uno") r.valor = leer(valor.value);
    else if (t === "dos") r.valor = [leer(valor.value), leer(valor2.value)];
    else if (t === "lista") r.valor = valor.value.split(",").map((x) => leer(x.trim())).filter((x) => x !== "");
    else if (t === "numero") r.valor = Number(valor.value);
    else if (t === "tipo") r.valor = valorTipo.value;
    else if (t === "json") { try { r.valor = JSON.parse(valorJson.value); } catch { r.valor = undefined; r.invalido = "el valor no es un JSON válido"; } }
    if (cada.checked && /\[\*\]/.test(r.ruta)) r.cada = true;
    if (desc.value.trim()) r.descripcion = desc.value.trim();
    if (t === "numero" && Number.isNaN(r.valor)) r.invalido = "el valor tiene que ser un número";
    // Un valor vacio casi siempre es que falta escribirlo (para '' esta la condicion «está vacío»).
    if ((t === "uno" || t === "lista" || t === "numero") && !valor.value.trim()) r.invalido = "el valor";
    if (t === "dos" && (!valor.value.trim() || !valor2.value.trim())) r.invalido = "los dos valores";
    if (!r.ruta) r.invalido = "falta el campo";
    return r;
  };
  let espera = null, ultimo = 0;
  const actualizar = () => {
    pintarValor();
    const rv = ruta.value.trim();
    if (hayDatos && rv) {
      const a = valorEn(datos, rv);
      const mostrar = Array.isArray(a.valor) ? `lista de ${a.valor.length} elemento${a.valor.length === 1 ? "" : "s"}: ${resumirValor(a.valor, 120)}` : resumirValor(a.valor, 200);
      actual.textContent = a.existe ? `Valor en la última salida: ${mostrar}` : "Ese campo no está en la última salida.";
    } else actual.textContent = hayDatos ? "" : "Corré el caso para ver los valores y probar la verificación.";
    clearTimeout(espera);
    if (!hayDatos) return;
    espera = setTimeout(async () => {
      const r = armar();
      if (r.invalido) { vaciar(previa, h("span", { class: "muted" }, `Falta completar: ${r.invalido}.`)); return; }
      const n = ++ultimo;
      try {
        const x = await POST("/api/verificar", { datos, verificacion: r });
        if (n !== ultimo) return;
        vaciar(previa, x.ok ? h("span", { class: "ok-texto" }, "✔ Con la última salida se cumple.")
          : h("span", { class: "mal-texto" }, `✖ Con la última salida no se cumple: obtenido ${textoObtenido(x.obtenido)}${x.mensaje ? " · " + x.mensaje : ""}`));
      } catch (e) { vaciar(previa, h("span", { class: "mal-texto" }, e.message)); }
    }, 250);
  };
  [ruta, valor, valor2, valorJson, desc].forEach((x) => x.addEventListener("input", actualizar));
  [op, valorTipo, cada].forEach((x) => x.addEventListener("change", actualizar));
  actualizar();

  modal({
    titulo: v.ruta ? "Verificación" : "Nueva verificación",
    cuerpo: h("div", { class: "form-grid" },
      h("label", null, "Campo"), h("div", null, ruta, dl, actual),
      h("label", null, "Condición"), op,
      h("label", null, "Valor"), h("div", { class: "celda-valor" }, cajaValor, filaCada),
      h("label", null, "Por qué"), desc,
      h("div", { class: "fila-previa" }, previa)),
    botones: [{ texto: "Cancelar" }, {
      texto: "Guardar", prim: true, accion: () => {
        const r = armar();
        if (r.invalido) { toast(`No se puede guardar: ${r.invalido}`, "error"); return false; }
        alGuardar(r);
      },
    }],
  });
}
