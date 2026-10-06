"""Pantalla Revision: hallazgos del revisor de buenas practicas, fuente GX y revision de lo cambiado."""
from ..rutas import ErrorApi, kb, kbs_del_pedido, mensaje, ruta
from ...revisor import panel


@ruta("GET", "/api/revision")
def revision(q, _b):
    try:
        desde = int(q.get("desde") or 0)
    except ValueError:
        desde = 0
    return panel.objetos(kbs_del_pedido(q), texto=q.get("texto", ""), filtro=q.get("filtro", "todos"), desde=desde)


@ruta("GET", "/api/revision/fuente")
def fuente_revision(q, _b):
    try:
        return panel.fuente_objeto(kb(q.get("kb")), q.get("objeto", ""))
    except KeyError as e:
        raise ErrorApi(mensaje(e), 404)


@ruta("POST", "/api/revision/revisar")
def revisar_cambios(_q, b):
    return panel.revisar_cambios(kbs_del_pedido(b))
