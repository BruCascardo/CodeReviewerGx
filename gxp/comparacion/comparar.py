"""Comparacion de una salida con lo esperado. Cada funcion agrega las diferencias que encuentra a 'diffs':
{ruta, tipo (valor|falta|sobra|largo|tipo|clave), esperado, obtenido, mensaje}.

  - parcial ("esperado"): solo se controla lo que esta en el esperado.
  - total ("lineaBase", modo "todo"): todo tiene que coincidir, salvo las rutas de 'ignorar'. En las rutas
    'volatiles' (valores que cambian solos: fechas, ids nuevos) solo se controla el tipo.
  - estructura ("lineaBase", modo "estructura"): las mismas claves y tipos, mas Ok y los codigos de mensaje
    (campos_clave). Para salidas con datos de la base que cambian.

'ign' es la ruta con la que se evalua 'ignorar' (ver rutas.unir_ign); los que llaman pasan solo 'ruta'.
"""
import json

from .igualdad import comodin, escalar_igual
from .rutas import clave, obtener, patron_de, unir, unir_ign
from .valores import recortado, tipo_json, vacio_estructural


def _diff(ruta, tipo, esperado, obtenido, mensaje=""):
    return {"ruta": ruta or "$", "tipo": tipo, "esperado": esperado, "obtenido": obtenido, "mensaje": mensaje}


def parcial(e, o, ruta, opts, diffs, ign=None):
    """El obtenido 'o' tiene que contener todo lo del esperado 'e'."""
    ign = ruta if ign is None else ign
    if opts.ignorada(ign) and ign:
        return
    if isinstance(e, dict):
        if not isinstance(o, dict):
            diffs.append(_diff(ruta, "tipo", e, o, "se esperaba un objeto"))
            return
        for k, v in e.items():
            r, ri = unir(ruta, k), unir_ign(ign, k)
            if opts.ignorada(ri):
                continue
            kk = clave(o, k)
            if kk is None:
                # GeneXus omite las colecciones vacias: esperar [] (o <<vacio>>) y no recibir la clave coincide.
                if not (vacio_estructural(v) or v in ("<<vacio>>", "<<cualquiera>>")):
                    diffs.append(_diff(r, "falta", v, None, "no existe en la salida"))
            else:
                parcial(v, o[kk], r, opts, diffs, ri)
        return
    if isinstance(e, list):
        if not isinstance(o, list):
            diffs.append(_diff(ruta, "tipo", e, o, "se esperaba una lista"))
            return
        if opts.listas_parciales:
            for i, ve in enumerate(e):
                if not any(not diferencias_parciales(ve, vo, opts) for vo in o):
                    diffs.append(_diff(unir(ruta, i), "falta", ve, None, "ningun elemento de la lista coincide"))
            return
        if len(e) != len(o):
            diffs.append(_diff(ruta, "largo", len(e), len(o), f"la lista tiene {len(o)} elementos y se esperaban {len(e)}"))
        for i in range(min(len(e), len(o))):
            parcial(e[i], o[i], unir(ruta, i), opts, diffs, unir_ign(ign, i, len(o)))
        return
    if not escalar_igual(e, o, opts):
        c = comodin(e, o, opts)
        diffs.append(_diff(ruta, "valor", e, o, c[1] if c else ""))


def diferencias_parciales(e, o, opts):
    d = []
    parcial(e, o, "", opts, d)
    return d


def total(e, o, ruta, opts, diffs, ign=None, avisos=None):
    """Igualdad completa, salvo rutas ignoradas. Un indice negativo en 'ignorar' cuenta desde el final de
    la lista de la salida. En las rutas volatiles solo se controla el tipo.
    Con 'avisos' (una lista: comparacion contra la salida aprobada), un campo simple nuevo en la salida va
    ahi y no es una diferencia. Sin 'avisos' (verificacion 'igual'), es una diferencia."""
    ign = ruta if ign is None else ign
    if ign and opts.ignorada(ign):
        return
    if ign and opts.volatil(ign):
        if e is not None and o is not None and tipo_json(e) != tipo_json(o):
            diffs.append(_diff(ruta, "tipo", e, o, f"cambio el tipo: era {tipo_json(e)}, ahora {tipo_json(o)} "
                                                  "(es un valor que cambia solo: se controla el tipo)"))
        return
    if isinstance(e, dict) and isinstance(o, dict):
        for k, v in e.items():
            r, ri = unir(ruta, k), unir_ign(ign, k)
            if opts.ignorada(ri):
                continue
            kk = clave(o, k)
            if kk is None:
                if not vacio_estructural(v):
                    omitida = " (GeneXus la omite cuando queda vacia)" if isinstance(v, (list, dict)) else ""
                    diffs.append(_diff(r, "falta", v, None, "ya no esta en la salida" + omitida))
            else:
                total(v, o[kk], r, opts, diffs, ri, avisos)
        for k, v in o.items():
            if clave(e, k) is not None or opts.ignorada(unir_ign(ign, k)) or vacio_estructural(v):
                continue
            r = unir(ruta, k)
            if avisos is not None and not isinstance(v, (list, dict)):
                avisos.append(r)
            else:
                diffs.append(_diff(r, "sobra", None, v, "aparecio en la salida (antes no venia o venia vacia)"
                                   if isinstance(v, (list, dict)) else "es nuevo en la salida"))
        return
    if isinstance(e, list) and isinstance(o, list):
        if len(e) != len(o):
            diffs.append(_diff(ruta, "largo", len(e), len(o), f"la lista tiene {len(o)} elementos y la aprobada {len(e)}"))
        for i in range(min(len(e), len(o))):
            total(e[i], o[i], unir(ruta, i), opts, diffs, unir_ign(ign, i, len(o)), avisos)
        return
    if isinstance(e, (dict, list)) or isinstance(o, (dict, list)):
        diffs.append(_diff(ruta, "tipo", e, o, "cambio el tipo"))
        return
    if not escalar_igual(e, o, opts):
        diffs.append(_diff(ruta, "valor", e, o))


def _modelo_lista(lista):
    """Un elemento con todas las claves que aparecen en los elementos de la lista (para comparar la forma)."""
    if all(isinstance(x, dict) for x in lista):
        modelo = {}
        for x in lista:
            for k, v in x.items():
                if k not in modelo or vacio_estructural(modelo[k]):
                    modelo[k] = v
        return modelo
    return lista[0]


def estructura(e, o, ruta, opts, diffs, ign=None, avisos=None):
    """Misma forma: las mismas claves con los mismos tipos. No compara valores ni largos de listas (cada
    elemento de la salida se compara con la forma de los elementos aprobados)."""
    ign = ruta if ign is None else ign
    if (ign and opts.ignorada(ign)) or e is None or o is None:
        return
    if isinstance(e, dict) and isinstance(o, dict):
        for k, v in e.items():
            ri = unir_ign(ign, k)
            if opts.ignorada(ri):
                continue
            kk = clave(o, k)
            if kk is None:
                if not isinstance(v, (list, dict)):  # una coleccion puede no venir: GeneXus la omite si esta vacia
                    diffs.append(_diff(unir(ruta, k), "falta", v, None, "ya no esta en la salida"))
            else:
                estructura(v, o[kk], unir(ruta, k), opts, diffs, ri, avisos)
        if avisos is not None:
            for k, v in o.items():
                if clave(e, k) is None and not isinstance(v, (list, dict)) and not opts.ignorada(unir_ign(ign, k)):
                    avisos.append(unir(ruta, k))
        return
    if isinstance(e, list) and isinstance(o, list):
        if e and o:
            modelo = _modelo_lista(e)
            for i, x in enumerate(o):
                estructura(modelo, x, unir(ruta, i), opts, diffs, unir_ign(ign, i, len(o)), avisos)
        return
    te, to = tipo_json(e), tipo_json(o)
    if te != to:
        diffs.append(_diff(ruta, "tipo", e, o, f"cambio el tipo: era {te}, ahora {to}"))


def campos_clave(e, o, opts, diffs):
    """Compara Ok y los codigos de mensaje (opts.campos_clave) de cada parametro de salida. Los codigos se
    comparan como conjunto con repeticiones: el orden de los mensajes no importa, la cantidad si."""
    if not isinstance(e, dict) or not isinstance(o, dict):
        return
    for k in sorted({*e.keys(), *o.keys()}, key=str.lower):
        for campo in opts.campos_clave:
            ruta = f"{k}.{campo}"
            if opts.ignorada(ruta.replace("[*]", "[0,-1]")):
                continue
            ee, ve, multiple = obtener(e, ruta)
            eo, vo, _ = obtener(o, ruta)
            if multiple:
                a = sorted(json.dumps(recortado(x, opts), ensure_ascii=False) for x in ve)
                b = sorted(json.dumps(recortado(x, opts), ensure_ascii=False) for x in vo)
                if a != b:
                    diffs.append(_diff(ruta, "clave", ve, vo, "cambiaron los codigos de mensaje"))
            elif (ee or eo) and (ee != eo or not escalar_igual(ve, vo, opts)):
                diffs.append(_diff(ruta, "clave", ve if ee else None, vo if eo else None, "cambio el resultado"))


def aprobada(e, o, opts, modo="todo"):
    """Compara la salida 'o' con la aprobada 'e'. Devuelve (diferencias, avisos). Un campo nuevo en la
    salida es un aviso, no una falla."""
    diffs, nuevos = [], []
    if modo == "estructura":
        campos_clave(e, o, opts, diffs)
        estructura(e, o, "", opts, diffs, avisos=nuevos)
    else:
        total(e, o, "", opts, diffs, avisos=nuevos)
    avisos = [f"Campo nuevo en la salida: {p}. Si esta bien, acepta la salida para dejar de ver este aviso."
              for p in dict.fromkeys(patron_de(r) for r in nuevos)]
    return diffs, avisos
