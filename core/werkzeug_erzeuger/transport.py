# core/werkzeug_erzeuger/transport.py
#
# Wie der allgemeine Adapter ein Programm WIRKLICH anspricht (2026-10-11).
# Drei Wege, alle klein und ohne Fremdpaket:
#   HttpTransport    urllib, mit Zeitlimit; der Absender ist austauschbar
#                    (Tests fahren den Flask-Test-Client statt des Netzes)
#   McpTransport     schlanker stdio-Client des Model Context Protocol:
#                    initialize, tools/list, tools/call — Zeilen-JSON-RPC über
#                    stdin/stdout eines Kindprozesses. Kein SDK, kein Paket.
#   PythonTransport  nur für mitgelieferte Vorlagen und Tests
#
# Alle drei liefern eine `Antwort`; was ein Fehler ist, entscheidet danach der
# Adapter nach den Fehler-Regeln der Beschreibung. Schlüssel kommen nur über
# ai_config.setting(<Name der Einstellung>) und stehen nie in einem Fehlertext.

import importlib
import json
import os
import queue
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import ai_config

MAX_ANTWORT = 2_000_000          # Bytes; mehr liest kein Aufruf
PROTOKOLL = "2025-06-18"         # MCP-Version, die wir anbieten (der Server darf eine ältere nennen)


@dataclass
class Antwort:
    """Was zurückkam. fehler: HTTP >= 400 oder MCP isError."""
    status: int | None = None
    daten: Any = None
    text: str = ""
    fehler: bool = False
    mcp_fehler: bool = False


class TransportFehler(Exception):
    """Der Aufruf kam nicht (sicher) an. `gesendet`: ob die Anfrage schon
    raus war — dann ist bei Schreibendem unklar, ob es geklappt hat."""

    def __init__(self, code: str, grund: str, gesendet: bool = False):
        super().__init__(grund)
        self.code, self.grund, self.gesendet = code, grund, gesendet


def _einstellung(name: str) -> str:
    wert = ai_config.setting(name)
    if not wert:
        raise TransportFehler("AUTH-FEHLT", f"Die Einstellung „{name}“ ist nicht gesetzt.")
    return str(wert)


def _lesen_json(roh: bytes, inhaltsart: str = ""):
    text = roh.decode("utf-8", "replace")
    try:
        return json.loads(text) if text.strip() else None, text
    except ValueError:
        return None, text


# ── HTTP ───────────────────────────────────────────────────────────────

def _urllib_senden(methode, url, kopf, body, zeitlimit):
    if urllib.parse.urlsplit(url).scheme not in ("http", "https"):
        raise TransportFehler("NICHT-ERREICHBAR", "nur http/https")
    req = urllib.request.Request(url, data=body, headers=kopf, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=zeitlimit) as r:     # noqa: S310 — Schema schränkt auf http(s) ein
            return r.status, r.read(MAX_ANTWORT)
    except urllib.error.HTTPError as e:
        return e.code, e.read(MAX_ANTWORT)


class HttpTransport:
    def __init__(self, basis: str, auth: dict | None = None, zeitlimit: int = 15, sender=None):
        self.basis = basis.rstrip("/")
        self.auth, self.zeitlimit = auth, zeitlimit
        self.sender = sender or _urllib_senden

    def _kopf(self) -> dict:
        kopf = {"Accept": "application/json"}
        if self.auth:
            wert = _einstellung(self.auth["einstellung"])
            if self.auth["art"] == "bearer":
                kopf["Authorization"] = "Bearer " + wert
            else:
                kopf[self.auth["kopfzeile"]] = wert
        return kopf

    def aufrufen(self, a: dict) -> Antwort:
        url = self.basis + a["pfad"]
        if a.get("abfrage"):
            url += "?" + urllib.parse.urlencode(
                {k: ("true" if v is True else "false" if v is False else v)
                 for k, v in a["abfrage"].items()})
        kopf, body = self._kopf(), None
        if a.get("body") is not None:
            body = json.dumps(a["body"], ensure_ascii=False).encode("utf-8")
            kopf["Content-Type"] = "application/json"
        try:
            status, roh = self.sender(a["methode"], url, kopf, body, self.zeitlimit)
        except TransportFehler:
            raise
        except (urllib.error.URLError, ConnectionError) as e:
            grund = getattr(e, "reason", e)
            raise TransportFehler("NICHT-ERREICHBAR", f"Das Programm antwortet nicht ({grund}).")
        except TimeoutError:
            raise TransportFehler("ZEITUEBERSCHREITUNG",
                                  f"Keine Antwort innerhalb von {self.zeitlimit} Sekunden.", gesendet=True)
        except OSError as e:
            raise TransportFehler("NICHT-ERREICHBAR", f"Verbindung gescheitert ({e.__class__.__name__}).")
        daten, text = _lesen_json(roh)
        return Antwort(status=status, daten=daten, text=text, fehler=status >= 400)

    def schliessen(self):
        pass


# ── MCP über stdio ─────────────────────────────────────────────────────

class McpTransport:
    """Ein MCP-Server als Kindprozess. Startet beim ersten Aufruf, bleibt für
    weitere offen, wird mit schliessen() beendet."""

    def __init__(self, kommando: list, umgebung: dict | None = None, zeitlimit: int = 20):
        self.kommando = [sys.executable if k == "{python}" else k for k in kommando]
        self.umgebung, self.zeitlimit = umgebung or {}, zeitlimit
        self._p, self._zeilen, self._id = None, queue.Queue(), 0
        self._lock = threading.RLock()
        self.server = {}

    # -- Prozess --
    def _starten(self):
        env = dict(os.environ)
        for var, einstellung in self.umgebung.items():
            env[var] = _einstellung(einstellung)
        wurzel = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        try:
            self._p = subprocess.Popen(self.kommando, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, env=env, cwd=wurzel, text=True,
                                       encoding="utf-8", bufsize=1)
        except OSError as e:
            raise TransportFehler("NICHT-ERREICHBAR", f"Der Server ließ sich nicht starten ({e.__class__.__name__}).")
        threading.Thread(target=self._leser, args=(self._p, self._zeilen), daemon=True).start()
        res = self._anfrage("initialize", {"protocolVersion": PROTOKOLL, "capabilities": {},
                                           "clientInfo": {"name": "zentrale", "version": "1"}})
        self.server = res.get("serverInfo") or {}
        self._senden({"jsonrpc": "2.0", "method": "notifications/initialized"})

    @staticmethod
    def _leser(p, q):
        for zeile in p.stdout:
            q.put(zeile)
        q.put(None)

    def _senden(self, nachricht: dict):
        try:
            self._p.stdin.write(json.dumps(nachricht, ensure_ascii=False) + "\n")
            self._p.stdin.flush()
        except (OSError, ValueError):
            raise TransportFehler("NICHT-ERREICHBAR", "Der Server ist nicht mehr da.")

    def _anfrage(self, methode: str, params: dict | None = None) -> dict:
        self._id += 1
        mine = self._id
        self._senden({"jsonrpc": "2.0", "id": mine, "method": methode, "params": params or {}})
        while True:
            try:
                zeile = self._zeilen.get(timeout=self.zeitlimit)
            except queue.Empty:
                raise TransportFehler("ZEITUEBERSCHREITUNG",
                                      f"Keine Antwort innerhalb von {self.zeitlimit} Sekunden.", gesendet=True)
            if zeile is None:
                raise TransportFehler("NICHT-ERREICHBAR", "Der Server hat sich beendet.", gesendet=True)
            try:
                nachricht = json.loads(zeile)
            except ValueError:
                continue                    # Müll auf stdout ist kein Protokoll
            if not isinstance(nachricht, dict) or nachricht.get("id") != mine:
                continue                    # Benachrichtigungen u. ä.
            if "error" in nachricht:
                fehler = nachricht["error"] or {}
                raise TransportFehler("ABGELEHNT", str(fehler.get("message") or "Fehler des Servers")[:300])
            return nachricht.get("result") or {}

    def _bereit(self):
        if self._p is None or self._p.poll() is not None:
            self._zeilen = queue.Queue()
            self._starten()

    # -- Aufrufe --
    def werkzeuge(self) -> list:
        """tools/list — die Selbstbeschreibung des Servers (zum Ansehen)."""
        with self._lock:
            self._bereit()
            return self._anfrage("tools/list").get("tools") or []

    def aufrufen(self, a: dict) -> Antwort:
        with self._lock:
            self._bereit()
            res = self._anfrage("tools/call", {"name": a["werkzeug"], "arguments": a.get("argumente") or {}})
        texte = [c.get("text", "") for c in res.get("content") or [] if c.get("type") == "text"]
        text = "\n".join(texte)
        daten = res.get("structuredContent")
        if daten is None and text:
            daten, _ = _lesen_json(text.encode("utf-8"))
            if daten is None:
                daten = {"text": text}
        ist_fehler = bool(res.get("isError"))
        return Antwort(daten=daten, text=text, fehler=ist_fehler, mcp_fehler=ist_fehler)

    def schliessen(self):
        with self._lock:
            p, self._p = self._p, None
        if p is not None and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(timeout=2)
            except Exception:       # noqa: BLE001
                p.kill()


# ── Python (nur Vorlagen und Tests) ────────────────────────────────────

class PythonTransport:
    def __init__(self, modul: str):
        self.modul = modul

    def aufrufen(self, a: dict) -> Antwort:
        try:
            fn = getattr(importlib.import_module(self.modul), a["funktion"])
        except (ImportError, AttributeError) as e:
            raise TransportFehler("NICHT-ERREICHBAR", f"{self.modul}.{a['funktion']} gibt es nicht ({e})")
        try:
            daten = fn(a.get("argumente") or {})
        except Exception as e:      # noqa: BLE001 — ein Fehler des Programms ist eine Ablehnung, kein Absturz
            return Antwort(daten={"fehler": str(e)}, text=str(e), fehler=True)
        return Antwort(daten=daten, text=json.dumps(daten, ensure_ascii=False, default=str))

    def schliessen(self):
        pass
