"""Comandos grafo (quien usa a quien, en todas las KBs) y ui (interfaz grafica)."""
from .consola import c, error
from .. import grafo

_MARCA = {"P": " [solo en la version publicada]", "L": "", "LP": ""}


def cmd_grafo(a):
    grafo.actualizar(forzar=a.rearmar, log=lambda t: print(c(t, "gris"), flush=True))
    if not a.objeto:
        d = grafo.compacto()
        print(f"{len(d['nodos'])} objetos y {len(d['aristas'])} relaciones en {len(d['kbs'])} KBs. Se ven en la pestana Grafo de la interfaz.")
        return 0
    hallados = grafo.vecinos(a.objeto, a.kb)
    if not hallados:
        error(f"No encuentro '{a.objeto}'.")
        return 2
    for nodo, lo_usan, usa in hallados:
        kb, nombre, tipo = nodo[:3]
        print(c(f"\n{nombre}  ({tipo}, {kb or 'tabla'})" + _MARCA.get(nodo[5], ""), "negrita"))
        for titulo, lista in (("Lo usan", lo_usan), ("Usa", usa)):
            # Las de otras KBs van primero (vecinos las ordena asi) y resaltadas: es lo que se rompe sin que se note.
            otras = sum(1 for v, *_ in lista if v[0] and kb and v[0] != kb)
            print(f"  {titulo} ({len(lista)}" + (c(f", {otras} de otras KBs", "amarillo") if otras else "") + "):")
            for vecino, t, o, *extra in lista:
                externa = vecino[0] and kb and vecino[0] != kb
                texto = f"{vecino[0] or 'tabla':16} {vecino[1]}"
                detalle = f"{t} {extra[0]}" if t == "servicio" and extra else t
                print(f"  {c('>', 'amarillo') if externa else ' '} {c(texto, 'negrita') if externa else texto}  "
                      f"{c(detalle, 'gris')}{_MARCA.get(o, '')}")
    return 0


def cmd_ui(a):
    from ..web.servidor import servir
    servir(a.puerto, abrir=not a.no_abrir)


def registrar(sub):
    p = sub.add_parser("ui", help="interfaz grafica")
    p.add_argument("--puerto", type=int)
    p.add_argument("--no-abrir", action="store_true")
    p.set_defaults(fn=cmd_ui)

    p = sub.add_parser("grafo", help="relaciones entre objetos de todas las KBs (quien usa a quien)")
    p.add_argument("--objeto", help="muestra quien lo usa y que usa (nombre completo o final)")
    p.add_argument("--kb", help="si el nombre esta en varias KBs")
    p.add_argument("--rearmar", action="store_true", help="rearma todo aunque no haya habido builds")
    p.set_defaults(fn=cmd_grafo)
