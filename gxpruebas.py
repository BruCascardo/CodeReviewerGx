#!/usr/bin/env python3
"""GxPruebas: pruebas genericas sobre el Java que genera GeneXus. Los comandos estan en gxp/cli."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
for _flujo in (sys.stdout, sys.stderr):  # antes de importar: la configuracion compartida ya puede avisar algo
    if hasattr(_flujo, "reconfigure"):
        _flujo.reconfigure(encoding="utf-8", errors="replace")

from gxp import cli  # noqa: E402

if __name__ == "__main__":
    cli.preparar_consola()
    sys.exit(cli.main())
