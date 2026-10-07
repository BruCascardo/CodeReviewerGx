"""Comandos sobre los objetos de una KB: kbs, objetos, describir, ejecutar, sql, plan."""
import json
import sys
from pathlib import Path

from .consola import c, error, imprimir_json
from .. import catalogo, kbs, motor, plan, suites


def cmd_kbs(a):
    for k in kbs.descubrir().values():
        ds = ", ".join(f"{d['nombre']}({d['base']})" for d in k.datasources)
        print(f"{k.nombre:35} {k.ns:22} {ds}")


def cmd_objetos(a):
    lista = catalogo.objetos(kbs.obtener(a.kb), solo_ejecutables=not a.todos)
    if a.buscar:
        b = a.buscar.lower()
        lista = [o for o in lista if b in o["nombre"].lower()]
    for o in lista:
        ps = ", ".join(f"{p['io']}:{p['nombre']}" for p in o["parametros"])
        marca = c(" [ERRORES]", "rojo") if o["errores"] else ""
        print(f"{o['nombre']}  ({o['tipo']})  parm({ps}){marca}")
    print(c(f"{len(lista)} objetos", "gris"), file=sys.stderr)


def cmd_describir(a):
    kb = kbs.obtener(a.kb)
    try:
        d = motor.describir(kb, a.objeto, timeout_ms=None)
    except (motor.NoEjecutable, motor.MotorError) as e:
        error(str(e))
        return 2
    info = d["info"]
    print(f"{info['nombre']}  ->  {kb.clase_java(info['nombre'])}")
    if d["aviso"]:
        print(c("ATENCION: " + d["aviso"][0].lower() + d["aviso"][1:].rstrip("."), "amarillo"))
    if catalogo.hace_commit(kb, info["nombre"]):
        print(c("ATENCION: hace commit por su cuenta (el rollback no deshace sus cambios)", "amarillo"))
    for i, p in enumerate(d["parametros"]):
        print(f"  {i + 1}. {p['io']:5} {p['nombre']:25} {p.get('tipoJava') or '?'}")
    print("\nEntrada de ejemplo (--entrada):")
    print(json.dumps(d["plantillaEntrada"], ensure_ascii=False, indent=2))
    return 0


def _sql_args(lista):
    """'DS: select ...' -> {"ds", "query"}; sin prefijo, el datasource por defecto."""
    salida = []
    for s in lista or []:
        ds, sep, q = s.partition(":")
        if sep and ds.strip().isidentifier() and " " not in ds.strip():
            salida.append({"ds": ds.strip(), "query": q.strip()})
        else:
            salida.append({"ds": "", "query": s})
    return salida


def cmd_ejecutar(a):
    kb = kbs.obtener(a.kb)
    entrada = {}
    if a.entrada:
        texto = Path(a.entrada[1:]).read_text(encoding="utf-8") if a.entrada.startswith("@") else a.entrada
        entrada = json.loads(texto)
    res = suites.ejecutar_suelto(kb, a.objeto, entrada, _sql_args(a.sql), "commit" if a.commit else "rollback",
                                 timeout_ms=a.timeout, sql_previo=_sql_args(a.sql_previo))
    if a.completo:
        imprimir_json(res)
    else:
        salida = []
        if res.get("scriptPrevio"):
            salida.append({"paso": "SQL previo", **res["scriptPrevio"]})
        for p in res["pasos"]:
            d = {"paso": p["nombre"], "estado": p["estado"], "ms": p.get("ms")}
            for k in ("error", "datos", "advertencias"):
                if p.get(k):
                    d[k] = p[k]
            if p.get("excepcion"):
                d["excepcion"] = p["excepcion"][:3000]
            if p.get("consola"):
                d["consola"] = p["consola"][-3000:]
            salida.append(d)
        imprimir_json(salida if len(salida) > 1 else salida[0])
    return 0 if res["estado"] == "ok" else 1


def cmd_sql(a):
    r, datos = motor.consulta_suelta(kbs.obtener(a.kb), a.ds or "", a.query, maximo=a.max)
    if not r.get("ok"):
        error(r.get("error") or "Error de SQL")
        return 1
    if "filas" in datos:
        cols = datos["columnas"]
        anchos = [min(max([len(str(cn))] + [len(str(f.get(cn))) for f in datos["filas"]]), 60) for cn in cols]
        print("  ".join(str(cn).ljust(w) for cn, w in zip(cols, anchos)))
        print("  ".join("-" * w for w in anchos))
        for f in datos["filas"]:
            print("  ".join(str(f.get(cn))[:60].ljust(w) for cn, w in zip(cols, anchos)))
        print(c(f"{datos['cantidad']} filas" + (" (truncado)" if datos.get("truncado") else ""), "gris"), file=sys.stderr)
    else:
        print(f"{datos.get('actualizadas')} filas actualizadas (se hizo rollback)")
    return 0


_COLOR_NIVEL = {"alto": "rojo", "medio": "amarillo", "bajo": "gris"}


def cmd_plan(a):
    kb = kbs.obtener(a.kb)
    try:
        r = plan.calcular(kb, a.objeto)
    except (KeyError, plan.SinFuente, motor.MotorError) as e:
        error(str(e).strip("'\""))
        return 2
    if a.json:
        imprimir_json(r)
        return 0
    print(f"{r['objeto']}: {len(r['sentencias'])} sentencias, "
          + ", ".join(f"{n} {k}" for k, n in r["resumen"].items() if n) if r["hallazgos"] else
          f"{r['objeto']}: {len(r['sentencias'])} sentencias, sin recomendaciones")
    for av in r["avisos"]:
        print(c("  " + av, "gris"))
    for h in r["hallazgos"]:
        print(c(f"\n[{h['nivel']}] ", _COLOR_NIVEL[h["nivel"]]) + h["titulo"]
              + c(f"  ({h['cursor'] or 'navegacion'}, {h['origen']})", "gris"))
        if h["detalle"]:
            print("    " + h["detalle"])
        if h["sugerencia"]:
            print("    Sugerencia: " + h["sugerencia"])
    if a.detalle:
        for s in r["sentencias"]:
            print(c(f"\n{s['cursor']} {s['tipo'].upper()} ({', '.join(s['tablas'])})", "gris"))
            print("    " + (s["explicado"] or s["sql"]))
            for f in s["plan"]:
                print(f"    {f.get('table')}: {f.get('type')} key={f.get('key')} rows={f.get('rows')} "
                      f"filtered={f.get('filtered')} {f.get('Extra') or ''}")
            if s["error"]:
                print(c("    " + s["error"], "rojo"))
    return 0


def registrar(sub):
    p = sub.add_parser("kbs", help="KBs encontradas")
    p.set_defaults(fn=cmd_kbs)

    p = sub.add_parser("objetos", help="objetos ejecutables de una KB")
    p.add_argument("--kb", required=True)
    p.add_argument("--buscar")
    p.add_argument("--todos", action="store_true", help="incluye objetos no ejecutables")
    p.set_defaults(fn=cmd_objetos)

    p = sub.add_parser("describir", help="parametros y entrada de ejemplo de un objeto")
    p.add_argument("--kb", required=True)
    p.add_argument("--objeto", required=True)
    p.set_defaults(fn=cmd_describir)

    p = sub.add_parser("ejecutar", help="ejecuta un objeto (con rollback, salvo --commit)")
    p.add_argument("--kb", required=True)
    p.add_argument("--objeto", required=True)
    p.add_argument("--entrada", help="JSON {parametro: valor} o @archivo.json")
    p.add_argument("--sql", action="append", help="consulta a correr despues, en la misma transaccion ('DS: select ...')")
    p.add_argument("--sql-previo", action="append",
                   help="sentencias a correr antes del objeto, como el script previo de una suite ('DS: delete from ...; ...')")
    p.add_argument("--commit", action="store_true")
    p.add_argument("--timeout", type=int, default=120000)
    p.add_argument("--completo", action="store_true", help="muestra el resultado completo")
    p.set_defaults(fn=cmd_ejecutar)

    p = sub.add_parser("sql", help="consulta SQL (siempre con rollback)")
    p.add_argument("--kb", required=True)
    p.add_argument("--ds")
    p.add_argument("--max", type=int, default=200)
    p.add_argument("query")
    p.set_defaults(fn=cmd_sql)

    p = sub.add_parser("plan", help="plan de ejecucion (EXPLAIN) de las sentencias SQL de un objeto y recomendaciones")
    p.add_argument("--kb", required=True)
    p.add_argument("--objeto", required=True)
    p.add_argument("--detalle", action="store_true", help="muestra cada sentencia con su EXPLAIN")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_plan)
