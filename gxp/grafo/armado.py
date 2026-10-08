"""Armado del grafo de una KB: nodos (objetos de la especificacion y del Java, SDT, tablas) y relaciones.

  1. Nodos de la especificacion (procedimientos, transacciones, Web Panels, DP, API).
  2. Relaciones del Java local (referencias entre clases, agrupadas por objeto).
  3. Relaciones de la version publicada del modulo de la KB (si alguna KB tiene su .jar en build/libs).
  4. Tablas que lee y escribe cada objeto (navegacion de la especificacion).
  5. Ids de servicio que usa cada objeto (ver servicios.py): la relacion con el procedimiento se resuelve
     al juntar las KBs (grafo.compacto), con la tabla de servicios.

Origen de cada nodo y relacion: L (local), P (version publicada) o los dos.
"""
import hashlib
import time

from .indices import resolver
from .. import catalogo

VERSION_FORMATO = 4


def modulo(nombre):
    return nombre.rsplit(".", 1)[0] if "." in nombre else ""


def nodo_id(kb_nombre, clave):
    return f"{kb_nombre}|{clave}"


def firma_kb(kb, firma_servicios=""):
    """Cambia cuando GeneXus compila la KB, cambian los servicios conocidos o el formato de los datos del grafo."""
    return hashlib.sha1(f"{VERSION_FORMATO}:{kb.firma_build()}:{firma_servicios}".encode()).hexdigest()


def _tablas_nvg(ruta_nvg):
    """(lee, escribe) de la navegacion de un objeto."""
    try:
        det = catalogo.detalle(ruta_nvg)
    except Exception:
        return set(), set()
    lee, escribe = set(), set()

    def rec(niveles):
        for lv in niveles:
            if lv.get("tabla"):
                lee.add(lv["tabla"])
            lee.update(lv.get("join") or [])
            escribe.update(lv.get("actualiza") or [])
            rec(lv.get("subniveles") or [])
    rec(det.get("niveles") or [])
    return lee - escribe, escribe


class ArmadoKB:
    def __init__(self, kb, universo):
        self.kb = kb
        self.universo = universo
        self.ns_pref = kb.ns + "."
        self.ix_local, self.archivos = universo.fuentes(kb)
        self.trn = universo.transacciones(kb)  # su SDT es el Business Component
        self.especificados = {}                # clave java (paquete.nombre en minusculas) -> objeto del catalogo
        self.nombres_modulo = {}               # paquete en minusculas -> modulo con mayusculas
        self.apis = {}                         # paquete -> [nombres de objetos API]
        self.nodos, self.aristas = {}, {}
        self.servicios = {}                    # id del nodo -> ids de servicio que usa
        self._leer_especificacion()

    def _leer_especificacion(self):
        """Objetos de la especificacion: nombre con mayusculas, tipo, descripcion, tablas."""
        for o in catalogo.objetos(self.kb):
            clave = self.kb.clase_java(o["nombre"])
            self.especificados[clave] = o
            paq = clave.rpartition(".")[0]
            # Cada prefijo del modulo tambien: un paquete que solo tiene SDT toma el nombre de su padre conocido.
            mod = modulo(o["nombre"]).split(".")
            pq = paq.split(".")
            for k in range(len(mod), 0, -1):
                self.nombres_modulo.setdefault(".".join(pq[: len(pq) - (len(mod) - k)]), ".".join(mod[:k]))
            if o["tipo"] == "API":
                p, _, b = clave.rpartition(".")
                self.apis.setdefault(p, []).append(b)

    # ------------------------------------------------------------------ nombres y nodos

    def modulo_de(self, paq):
        """Paquete Java -> modulo con mayusculas (de lo especificado; lo que falta queda como en el paquete)."""
        resto = []
        while paq and paq != self.kb.ns:
            if paq in self.nombres_modulo:
                return ".".join([self.nombres_modulo[paq]] + resto[::-1])
            paq, _, ult = paq.rpartition(".")
            resto.append(ult)
        return ".".join(resto[::-1])

    def nombre_de(self, clave_obj, base, es_sdt):
        paq = clave_obj.rpartition(".")[0]
        if es_sdt or base.startswith("dom:"):
            base = base[4:] if base.startswith("dom:") else base
            mod = self.modulo_de(paq)
            return f"{mod}.{base}" if mod else base
        o = self.especificados.get(f"{paq}.{base.lower()}")
        return o["nombre"] if o else (self.modulo_de(paq) + "." + base if paq.startswith(self.ns_pref) else base)

    def nodo(self, kb_nombre, clave_obj, base, es_sdt, origen, tipo=None):
        nid = nodo_id(kb_nombre, clave_obj)
        n = self.nodos.get(nid)
        if n is None:
            nom = self.nombre_de(clave_obj, base, es_sdt) if kb_nombre == self.kb.nombre else None
            n = self.nodos[nid] = {"kb": kb_nombre, "clave": clave_obj, "nombre": nom or base.replace("dom:", ""),
                                   "tipo": tipo or ("SDT" if es_sdt else "Dominio" if base.startswith("dom:") else ""),
                                   "origen": origen}
        elif origen not in n["origen"]:
            n["origen"] = "".join(sorted(set(n["origen"] + origen)))
        return nid

    def clave_destino(self, ix, fqn, trn=None):
        """Clase -> (clave del objeto, nombre base, es_sdt), corrigiendo los casos en que la clase no se llama
        como el objeto. None si la clase no es de un objeto."""
        trn = self.trn if trn is None else trn
        r = ix.objeto(fqn)
        if not r:
            return None
        clave_obj, base, es_sdt = r
        if es_sdt and clave_obj.replace("sdt:", "") in trn:
            return clave_obj.replace("sdt:", ""), base, False
        # Algunos objetos se generan con una 'a' adelante (awwp_synchandler): es el mismo objeto.
        paq, _, b = clave_obj.rpartition(".")
        if not es_sdt and b.startswith("a") and clave_obj not in self.especificados and f"{paq}.{b[1:]}" in self.especificados:
            return f"{paq}.{b[1:]}", base[1:], False
        # Las clases de un objeto API llevan su nombre adelante (apipersonas_get_v1 es de ApiPersonas).
        if not es_sdt and clave_obj not in self.especificados and "_" in b:
            for o in self.apis.get(paq, ()):
                if b.startswith(o + "_"):
                    return f"{paq}.{o}", o, False
        return clave_obj, base, es_sdt

    def agregar_refs(self, de_id, refs, origen, indices_propios):
        """Relaciones de un objeto con lo que referencia su Java (de esta KB o de otra, por el namespace)."""
        for ref in refs:
            if ref.startswith("com.genexus"):
                continue
            duena = self.universo.duena(ref)
            if duena is None:
                continue
            if duena is self.kb:
                ixs = indices_propios
            else:
                ixs = [self.universo.fuentes(duena)[0]] + [p["indice"] for p in self.universo.publicados().get(duena.ns, [])]
            ix, fqn = resolver(ref, ixs)
            if not ix:
                continue
            r = self.clave_destino(ix, fqn, self.universo.transacciones(duena))
            if not r:
                continue
            clave_obj, base, es_sdt = r
            a_id = nodo_id(duena.nombre, clave_obj)
            if a_id == de_id:
                continue
            if a_id not in self.nodos:
                self.nodo(duena.nombre, clave_obj, base, es_sdt, "L" if duena is self.kb else "")
            k = (de_id, a_id)
            self.aristas[k] = "".join(sorted(set((self.aristas.get(k) or "") + origen)))

    # ------------------------------------------------------------------ etapas

    def _nodos_especificados(self):
        for clave, o in self.especificados.items():
            nid = self.nodo(self.kb.nombre, clave, clave.rpartition(".")[2], False, "L", o["tipo"])
            self.nodos[nid].update(nombre=o["nombre"], descripcion=o["descripcion"])

    def _relaciones_locales(self, memoria):
        """Agrupa los archivos por objeto (x.java, x_impl.java, x_bc.java...) y suma sus referencias."""
        por_objeto = {}
        for fqn, (ruta, st) in self.archivos.items():
            if not fqn.startswith(self.ns_pref):
                continue
            r = self.clave_destino(self.ix_local, fqn)
            if r:
                por_objeto.setdefault(r, []).append((ruta, st))
        for (clave_obj, base, es_sdt), lista in por_objeto.items():
            de_id = self.nodo(self.kb.nombre, clave_obj, base, es_sdt, "L")
            refs, srv = set(), set()
            for ruta, st in lista:
                r, s = memoria.leer(ruta, st)
                refs.update(r)
                srv.update(s)
            self.agregar_refs(de_id, refs, "L", [self.ix_local])
            # Los dominios (gxdomain...) y los SDT tienen los valores, pero no llaman a nadie.
            if srv and not es_sdt and not base.startswith("dom:"):
                self.servicios.setdefault(de_id, set()).update(srv)
        memoria.guardar()

    def _relaciones_publicadas(self, publicados):
        for p in publicados:
            ix = p["indice"]
            por_obj = {}
            for fqn, refs in p["clases"].items():
                r = ix.objeto(fqn)
                if not r or not fqn.startswith(self.ns_pref):
                    continue
                clave_obj, base, es_sdt = r
                if es_sdt and clave_obj.replace("sdt:", "") in self.trn:
                    clave_obj, es_sdt = clave_obj.replace("sdt:", ""), False
                por_obj.setdefault((clave_obj, base, es_sdt), set()).update(refs)
            for (clave_obj, base, es_sdt), refs in por_obj.items():
                de_id = self.nodo(self.kb.nombre, clave_obj, base, es_sdt, "P")
                self.agregar_refs(de_id, refs, "P", [ix, self.ix_local])

    def _tablas(self):
        """Relaciones lee/escribe con las tablas. Devuelve la KB duena de cada tabla que mantiene una
        transaccion de esta KB."""
        tablas = {}
        for clave, o in self.especificados.items():
            lee, escribe = _tablas_nvg(o["nvg"])
            de_id = nodo_id(self.kb.nombre, clave)
            for t, tipo in [(t, "lee") for t in lee] + [(t, "escribe") for t in escribe]:
                tid = f"tabla|{t.lower()}"
                tablas.setdefault(tid, t)
                self.aristas[(de_id, tid, tipo)] = "L"
        for tid, t in tablas.items():
            self.nodos.setdefault(tid, {"kb": "", "clave": tid, "nombre": t, "tipo": "Tabla", "origen": "L"})
        duenas = {}
        for (de, a, *tipo), _ in self.aristas.items():
            if tipo == ["escribe"] and self.nodos.get(de, {}).get("tipo") == "Transaction":
                duenas[a] = self.kb.nombre
        return duenas

    def _lista_aristas(self):
        salida = []
        for k, origen in self.aristas.items():
            de, a = k[0], k[1]
            if len(k) > 2:
                tipo = k[2]
            else:
                tipo = {"SDT": "sdt", "Transaction": "transaccion"}.get(self.nodos.get(a, {}).get("tipo"), "llama")
            salida.append([de, a, tipo, origen])
        return salida

    def armar(self, memoria, log=lambda t: None):
        """{kb, firma, nodos: {id: {...}}, aristas: [[de, a, tipo, origen]], ...}."""
        t0 = time.time()
        self._nodos_especificados()
        self._relaciones_locales(memoria)
        publicados = self.universo.publicados().get(self.kb.ns, [])
        self._relaciones_publicadas(publicados)
        duenas = self._tablas()
        aristas = self._lista_aristas()
        for n in self.nodos.values():
            if n["kb"] == self.kb.nombre and not n.get("tipo"):
                n["tipo"] = "Solo Java"  # hay Java pero no esta en la especificacion (objeto borrado o no generado)
        datos = {"formato": VERSION_FORMATO, "kb": self.kb.nombre, "ns": self.kb.ns, "firma": firma_kb(self.kb, memoria.firma_srv),
                 "fecha": time.strftime("%Y-%m-%d %H:%M:%S"), "segundos": round(time.time() - t0, 1),
                 "publicados": [{"jar": p["jar"], "version": p["version"]} for p in publicados],
                 "duenasTablas": duenas, "nodos": self.nodos, "aristas": aristas,
                 "servicios": {k: sorted(v) for k, v in self.servicios.items()}, "firmaServicios": memoria.firma_srv}
        log(f"{self.kb.nombre}: {len(self.nodos)} nodos, {len(aristas)} relaciones ({datos['segundos']} s)")
        return datos
