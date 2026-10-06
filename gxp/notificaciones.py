"""Notificaciones de Windows (sin librerias: WinRT desde PowerShell)."""
import base64
import subprocess
from xml.sax.saxutils import escape, quoteattr

from .util import SIN_VENTANA

_PLANTILLA_PS = """$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml(@'
{xml}
'@)
$app = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


def notificar(titulo, lineas, url=None):
    """Muestra una notificacion con un titulo y hasta dos lineas. Con url, el clic la abre en el navegador.
    Devuelve None si salio bien, o el error."""
    textos = "".join(f"<text>{escape(t)}</text>" for t in [titulo, *lineas][:3])
    lanzar = f' activationType="protocol" launch={quoteattr(url)}' if url else ""
    xml = f'<toast{lanzar}><visual><binding template="ToastGeneric">{textos}</binding></visual></toast>'
    script = _PLANTILLA_PS.format(xml=xml.replace("\n", " "))
    cod = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", cod],
                           capture_output=True, text=True, timeout=30, creationflags=SIN_VENTANA)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    if r.returncode:
        return (r.stderr or r.stdout).strip()[-500:] or f"PowerShell termino con codigo {r.returncode}"
    return None
