# core/net.py
#
# Transparenz-Schicht für alle HTTP-Anfragen aus ZENTRALE heraus.
#
# WARUM dieses Modul existiert:
#   Statt urllib direkt zu nutzen, läuft jeder HTTP-Call durch dieses Modul.
#   Jede Anfrage und jede Antwort wird ins ZENTRALE-Terminal geloggt –
#   du siehst live im Dashboard was das System ins Internet schickt und
#   was zurückkommt. Keine versteckten Calls.
#
# NUTZUNG:
#   import net
#   body = net.get("https://example.com/api")
#   body = net.post("http://localhost:11434/api/chat", payload_dict)

import json
import ipaddress
import urllib.request
import urllib.error
from urllib.parse import urlparse
import state  # für push_log – zeigt Requests im Dashboard-Terminal


# Hostnames die wir als "lokal" einstufen (treffen keinen Netzwerk-Stack).
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _is_internet(url: str) -> bool:
    """
    Klassifiziert eine URL als Internet-Ziel (True) oder lokal/LAN (False).

    Heuristik:
      - localhost-Varianten          → lokal     (False)
      - private IP-Ranges (RFC1918)  → LAN       (False)
      - Link-local / loopback IPs    → lokal     (False)
      - mDNS-Namen (*.local)         → LAN       (False)
      - Alles andere (Public-IPs, normale Hostnames) → Internet (True)

    Wird vom Internet-Panel im Dashboard genutzt: nur True-Calls landen
    dort. Die regulären NET-Logs (im großen stdout) bleiben unverändert.

    Bei Parse-Fehlern oder leerem Hostname: defensiv False – wir wollen
    keine Fehl-Alarme im Internet-Panel.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    if not host:
        return False
    if host in _LOCAL_HOSTS:
        return False
    # IP-Literal? → über ipaddress klassifizieren (private/loopback/link-local)
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        # Hostname (kein IP-Literal). mDNS *.local ist LAN, sonst Internet.
        if host.endswith(".local"):
            return False
        return True


def get(url: str, timeout: int = 10) -> bytes:
    """
    Macht einen HTTP GET-Request und gibt den Response-Body als bytes zurück.
    Logt Anfrage + Antwort ins Terminal.
    Wirft bei Fehler eine Exception (mit Log-Eintrag).
    """
    _log_out("GET", url)

    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            _log_in(resp.status, url, len(body))
            return body
    except urllib.error.HTTPError as e:
        # HTTPError = Server hat geantwortet, aber mit Fehlercode (4xx, 5xx)
        _log_err(url, f"HTTP {e.code} {e.reason}")
        raise
    except urllib.error.URLError as e:
        # URLError = gar keine Verbindung (Server down, kein Netz, DNS-Fehler)
        _log_err(url, str(e.reason))
        raise


def post(url: str, payload: dict, timeout: int = 60) -> dict:
    """
    Macht einen HTTP POST-Request mit JSON-Body.
    Gibt die geparste JSON-Antwort als dict zurück.
    Logt Anfrage + Antwort ins Terminal.

    timeout=60 default weil Ollama bei großen Modellen länger braucht.
    """
    _log_out("POST", url)

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            _log_in(resp.status, url, len(body))
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        _log_err(url, f"HTTP {e.code} {e.reason}")
        raise
    except urllib.error.URLError as e:
        _log_err(url, str(e.reason))
        raise


def stream_post(url: str, payload: dict, timeout: int = 60):
    """
    Macht einen HTTP POST und liefert die Antwort als Generator – Zeile für Zeile.

    Ollama's Streaming-Modus schickt die Antwort als NDJSON zurück:
    jede Zeile ist ein eigenständiges JSON-Objekt mit einem Token.
    Wir lesen die Antwort also nicht auf einmal ein (wie post() es tut),
    sondern iterieren über die Zeilen des HTTP-Response-Streams.

    Nutzung (in ai.py):
        for chunk in net.stream_post(url, payload):
            token = chunk["message"]["content"]

    Logt Start und Ende ins Terminal, aber nicht jeden einzelnen Token
    (das wäre viel zu viel Output).
    """
    import urllib.request
    import urllib.error

    _log_out("POST (stream)", url)

    data = json.dumps(payload).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # resp ist ein file-like object – wir können darüber iterieren.
            # Jede Iteration gibt eine Zeile (bytes) zurück.
            for raw_line in resp:
                line = raw_line.strip()
                if line:
                    yield json.loads(line.decode("utf-8"))
            _log_in(200, url, 0)  # Größe unbekannt beim Streaming, 0 als Platzhalter
    except urllib.error.HTTPError as e:
        _log_err(url, f"HTTP {e.code} {e.reason}")
        raise
    except urllib.error.URLError as e:
        _log_err(url, str(e.reason))
        raise


# ── Interne Log-Helfer ─────────────────────────────────────────────────

def _log_out(method: str, url: str):
    """Logt eine ausgehende Anfrage."""
    line = f"NET →  {method} {url}"
    state.push_log(line)
    # Internet-Traffic zusätzlich in den dedizierten Channel spiegeln,
    # damit das Internet-Panel im Dashboard nur die "wirklich raus"-Calls
    # zeigt. Lokale/LAN-Calls landen nur im normalen stdout.
    if _is_internet(url):
        state.push_internet_log(line)


def _log_in(status: int, url: str, size_bytes: int):
    """Logt eine eingehende Antwort mit Status und Größe."""
    line = f"NET ←  {status} {url} ({size_bytes} B)"
    state.push_log(line)
    if _is_internet(url):
        state.push_internet_log(line)


def _log_err(url: str, reason: str):
    """Logt einen fehlgeschlagenen Request."""
    line = f"NET ✗  FAIL {url} – {reason}"
    state.push_log(line)
    if _is_internet(url):
        state.push_internet_log(line)
