"""Fechas relativas para las ${variables} de los casos, calculadas al ejecutar:

    ${hoy+30}  ${hoy-1}  ${hoy+2m}  ${hoy-1a}     dias (d, por defecto), meses (m) o anios (a) desde hoy
    ${ahora+2h}  ${ahora-30min}  ${ahora+1d}      fecha y hora: horas, minutos o dias
    ${inicio_mes}  ${fin_mes}  ${fin_mes+1}       primer y ultimo dia del mes (con +N / -N, de otro mes)
    ${inicio_anio}  ${fin_anio-1}                 primer y ultimo dia del anio
    ${habil_siguiente}  ${habil_anterior}         el proximo (o el ultimo) dia de lunes a viernes, sin contar hoy
    ${fecha_vacia}                                la fecha vacia de GeneXus ("")

Las fechas van como AAAA-MM-DD y la fecha y hora como AAAA-MM-DDTHH:MM:SS, igual que ${hoy} y ${ahora}.
"""
import calendar
import datetime as dt
import re

FORMATO_FECHA = "%Y-%m-%d"
FORMATO_FECHAHORA = "%Y-%m-%dT%H:%M:%S"
NOMBRES = ("hoy", "ahora", "inicio_mes", "fin_mes", "inicio_anio", "fin_anio", "habil_siguiente", "habil_anterior",
           "fecha_vacia")

_EXPR = re.compile(r"^(hoy|ahora|inicio_mes|fin_mes|inicio_anio|fin_anio)\s*(?:([+-])\s*(\d+)\s*(d|m|a|h|min)?)?$", re.I)


def _sumar_meses(f, n):
    m = f.month - 1 + n
    a, m = f.year + m // 12, m % 12 + 1
    return f.replace(year=a, month=m, day=min(f.day, calendar.monthrange(a, m)[1]))


def _habil(f, paso):
    f += dt.timedelta(days=paso)
    while f.weekday() >= 5:
        f += dt.timedelta(days=paso)
    return f


def calcular_seguro(expresion):
    """True si 'expresion' es una fecha relativa (bien escrita)."""
    try:
        return calcular(expresion) is not None
    except ValueError:
        return False


def calcular(expresion, ahora=None):
    """El valor de una fecha relativa (texto), o None si 'expresion' no es una. ValueError si la unidad no va con
    esa fecha (${hoy+2h})."""
    e = expresion.strip().lower()
    ahora = ahora or dt.datetime.now().replace(microsecond=0)
    hoy = ahora.date()
    if e == "fecha_vacia":
        return ""
    if e in ("habil_siguiente", "habil_anterior"):
        return _habil(hoy, 1 if e == "habil_siguiente" else -1).strftime(FORMATO_FECHA)
    m = _EXPR.match(e)
    if not m:
        return None
    base, signo, n, unidad = m[1], m[2], int(m[3] or 0), (m[4] or "").lower()
    n = -n if signo == "-" else n
    if base == "ahora":
        delta = {"": dt.timedelta(days=n), "d": dt.timedelta(days=n), "h": dt.timedelta(hours=n),
                 "min": dt.timedelta(minutes=n)}.get(unidad)
        if delta is None:
            raise ValueError(f"${{{expresion}}}: con ahora se suman dias (d), horas (h) o minutos (min)")
        return (ahora + delta).strftime(FORMATO_FECHAHORA)
    if unidad in ("h", "min"):
        raise ValueError(f"${{{expresion}}}: a una fecha se le suman dias (d), meses (m) o anios (a); horas solo a ahora")
    if base == "hoy":
        f = {"": lambda: hoy + dt.timedelta(days=n), "d": lambda: hoy + dt.timedelta(days=n),
             "m": lambda: _sumar_meses(hoy, n), "a": lambda: _sumar_meses(hoy, 12 * n)}[unidad]()
    elif unidad not in ("", "m" if base.endswith("mes") else "a"):
        raise ValueError(f"${{{expresion}}}: se escribe {base}+N ({'meses' if base.endswith('mes') else 'anios'})")
    elif base.endswith("mes"):
        f = _sumar_meses(hoy.replace(day=1), n)
        if base == "fin_mes":
            f = f.replace(day=calendar.monthrange(f.year, f.month)[1])
    else:
        f = dt.date(hoy.year + n, 1, 1) if base == "inicio_anio" else dt.date(hoy.year + n, 12, 31)
    return f.strftime(FORMATO_FECHA)
