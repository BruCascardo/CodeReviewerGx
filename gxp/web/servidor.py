"""Servidor web local de GxPruebas: sirve la interfaz (ui/) y la API JSON (gxp/web/api). Escucha solo en
127.0.0.1 y solo acepta pedidos a la API de la propia interfaz."""
import json
import mimetypes
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import api  # noqa: F401  (registra las rutas)
from .rutas import RUTAS, Archivo, ErrorApi
from .. import VERSION, automatico, compartido, grafo, motor
from ..config import CFG, UI

_LOCALES = ("127.0.0.1", "localhost")


class Manejador(BaseHTTPRequestHandler):
    server_version = "GxPruebas/" + VERSION

    def log_message(self, *args):
        pass

    def _responder(self, codigo, cuerpo: bytes, tipo="application/json; charset=utf-8", extra=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, codigo, obj):
        self._responder(codigo, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def _origen_permitido(self):
        """Solo pedidos de la propia interfaz (evita que otra pagina del navegador use la API). El Origin se
        compara entero (host y puerto): con startswith pasaba http://localhost.otro-sitio.com."""
        puerto = self.server.server_address[1]
        origen = self.headers.get("Origin")
        host = (self.headers.get("Host") or "").split(":")[0]
        if origen:
            o = urlparse(origen)
            origen_ok = o.scheme == "http" and o.hostname in _LOCALES and o.port == puerto
        else:
            origen_ok = True
        return host in _LOCALES and origen_ok

    def _api(self, metodo, camino, q):
        if not self._origen_permitido():
            return self._json(403, {"error": "Origen no permitido"})
        fn = RUTAS.get((metodo, camino))
        if not fn:
            return self._json(404, {"error": f"No existe {metodo} {camino}"})
        cuerpo = {}
        largo = int(self.headers.get("Content-Length") or 0)
        if largo:
            try:
                cuerpo = json.loads(self.rfile.read(largo).decode("utf-8"))
            except Exception as e:
                return self._json(400, {"error": f"JSON invalido: {e}"})
        try:
            r = fn(q, cuerpo)
        except ErrorApi as e:
            return self._json(e.codigo, {"error": str(e)})
        except motor.MotorError as e:
            return self._json(500, {"error": str(e), "motor": True})
        except compartido.Conflicto as e:
            return self._json(409, {"error": str(e)})
        except (compartido.SinConexion, compartido.SinPermiso) as e:
            return self._json(503, {"error": f"Base compartida: {e}"})
        except Exception as e:
            return self._json(500, {"error": f"{type(e).__name__}: {e}", "traza": traceback.format_exc()})
        if isinstance(r, Archivo):
            return self._responder(200, r.contenido, r.tipo, {"Content-Disposition": f'attachment; filename="{r.nombre}"'})
        return self._json(200, r)

    def _estatico(self, camino):
        ruta = camino.lstrip("/") or "index.html"
        archivo = (UI / ruta).resolve()
        if UI.resolve() not in archivo.parents or not archivo.is_file():
            archivo = UI / "index.html"
        tipo = mimetypes.guess_type(str(archivo))[0] or "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript",):
            tipo += "; charset=utf-8"
        self._responder(200, archivo.read_bytes(), tipo)

    def _manejar(self, metodo):
        u = urlparse(self.path)
        if u.path.startswith("/api/"):
            return self._api(metodo, u.path, {k: v[0] for k, v in parse_qs(u.query).items()})
        self._estatico(u.path)

    def do_GET(self):
        self._manejar("GET")

    def do_POST(self):
        self._manejar("POST")

    def do_PUT(self):
        self._manejar("PUT")

    def do_DELETE(self):
        self._manejar("DELETE")


def servir(puerto=None, abrir=True):
    puerto = int(puerto or CFG["puerto"])
    mimetypes.add_type("application/javascript", ".js")
    mimetypes.add_type("text/css", ".css")
    srv = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{puerto}/"
    print(f"GxPruebas {VERSION} escuchando en {url}  (Ctrl+C para salir)")
    conf = CFG["despuesDelBuild"]
    if conf.get("activo"):
        _, msg = automatico.iniciar(conf, lambda res: print("\n".join(automatico.lineas_consola(res)), flush=True), url)
        print(msg, flush=True)
    # El grafo de objetos se rearma solo despues de cada build (solo las KBs que cambiaron).
    grafo.vigilar(al_cambiar=lambda kbs_: print(f"Grafo actualizado: {', '.join(kbs_)}", flush=True))
    if abrir:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        print("Cerrando motores...")
        motor.detener_todos()
        srv.server_close()
