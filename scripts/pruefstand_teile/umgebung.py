# Die Wegwerf-Umgebung eines Falls: alles, was geschrieben wird, landet in
# einem Temp-Ordner — Sashas data/ wird nur GELESEN (Schlüssel, Einstellungen)
# und die Kosten werden in seine echte Buchhaltung gebucht (eigener Topf
# „pruefstand", kind.topf_setzen — nicht in seine Chat-Kosten).
#
# Zwei Schritte, weil manche Module ihren Ort beim Import festlegen:
#   vorbereiten()  VOR dem Import des Kerns: Env-Variablen (ZENTRALE_*_DIR),
#                  Schlüssel in os.environ, Einstellungen als Kopie OHNE
#                  Schlüssel in einen Temp-Ordner (ai_config schreibt dorthin,
#                  falls ein Werkzeug eine Einstellung ändert).
#   umlenken()     NACH dem Import: Modul-Attribute, die keine Env kennen
#                  (Kalender-Pfad, Graph, Messreihen) — mit Rückweg, damit
#                  der Trockentest in pytest nichts liegen lässt.
#
# Dazu die Attrappen: kein echtes Netz außer zum Modell (die Websuche und
# fetch_url antworten nach Fall-Vorgabe), und ein Skript statt Sasha an den
# Knöpfen (Erlaubnis-Gate, ask_choice).

import json
import os
from urllib.parse import parse_qs, urlparse


def daten_wurzel(code_wurzel: str) -> str:
    """Wo Sashas echtes data/ liegt: im Haupt-Checkout. Aus einem Worktree
    heraus (.claude/worktrees/<name>) ist das der Ordner über .claude."""
    if os.path.exists(os.path.join(code_wurzel, "data", "ai_config.json")):
        return code_wurzel
    teile = os.path.abspath(code_wurzel).split(os.sep)
    if ".claude" in teile:
        return os.sep.join(teile[:teile.index(".claude")])
    return code_wurzel


def vorbereiten(tmp: str, daten: str, einstellungen: dict | None = None) -> dict:
    """Env für einen Fall setzen. -> die Einstellungen (ohne Schlüssel), die gelten."""
    os.makedirs(tmp, exist_ok=True)
    for name, unter in (("GEDAECHTNIS", "gedaechtnis"), ("GESPRAECHE", "gespraeche"),
                        ("TRANSKRIPT", "ai_transcripts"), ("ABLAGE", "ablage"),
                        ("SANDBOX", "sandbox"), ("MODELL_CACHE", "modelle")):
        os.environ[f"ZENTRALE_{name}_DIR"] = os.path.join(tmp, unter)
    os.environ["ZENTRALE_LOKALE_KI"] = "aus"         # kein Ollama, Chat über die Cloud
    os.environ["ZENTRALE_MAIL"] = "off"
    os.environ["ZENTRALE_NOTIFY"] = "0"
    os.environ["ZENTRALE_KALENDER_GIT_SPIEGEL"] = "aus"
    os.environ["ZENTRALE_MODELL_LISTE_HOLEN"] = "aus"
    # Kosten in die echte Buchhaltung (die Kosten sind echt) — Topf
    # „pruefstand", gesetzt in kind.topf_setzen.
    os.environ["ZENTRALE_USAGE_FILE"] = os.path.join(daten, "data", "ai_usage.json")

    echt = {}
    pfad = os.path.join(daten, "data", "ai_config.json")
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8") as f:
            echt = json.load(f) or {}
    for name, wert in (echt.get("keys") or {}).items():
        if wert and not os.environ.get(name):
            os.environ[name] = str(wert)
    # Ohne Monatsdeckel: ab Sashas Deckel wechselte der Chat auf den billigsten
    # Anbieter — mitten in einem Durchgang wäre die Messung dann keine. Der
    # Prüfstand hat seine eigene Grenze (pruefstand_budget_monat, geprüft in
    # scripts/pruefstand.py vor dem Durchgang und vor jedem Fall).
    kopie = {k: v for k, v in echt.items() if k not in ("keys", "budget_monat_euro")}
    kopie.update(einstellungen or {})
    cfg_dir = os.path.join(tmp, "ai_config")
    os.makedirs(cfg_dir, exist_ok=True)
    with open(os.path.join(cfg_dir, "ai_config.json"), "w", encoding="utf-8") as f:
        json.dump(kopie, f, ensure_ascii=False, indent=1)
    os.environ["ZENTRALE_AI_CONFIG_DIR"] = cfg_dir
    for k, v in (einstellungen or {}).items():
        # Nur einfache Werte in die Env: ein dict (chat_models, modell_profile)
        # käme dort als Python-Text an und stäche die Datei-Kopie aus, die es
        # richtig enthält (2026-10-09, --modell im Prüfstand).
        if isinstance(v, (str, int, float, bool)):
            os.environ["ZENTRALE_" + k.upper()] = str(v)
    return kopie


def umlenken(tmp: str):
    """Modul-Attribute auf den Temp-Ordner. -> Funktion, die alles zurückstellt."""
    from pathlib import Path
    import cloud
    import consolidation
    import gedaechtnis
    import gespraeche
    import graph
    import graphs
    import kalender
    import transkript

    alt = []

    def setzen(modul, attr, wert):
        if hasattr(modul, attr):
            alt.append((modul, attr, getattr(modul, attr)))
            setattr(modul, attr, wert)

    setzen(kalender, "CAL_PATH", Path(tmp) / "ai_calendar.json")
    setzen(kalender, "ICS_DIR", None)                      # → tmp/kalender/
    setzen(cloud, "CLOUD_GRAPH", os.path.join(tmp, "graph_cloud.json"))
    setzen(graph, "_DATA_DIR", tmp)
    reihen = os.path.join(tmp, "reihen")
    os.makedirs(reihen, exist_ok=True)
    setzen(graphs, "_DATA_DIR", reihen)
    setzen(graphs, "_REGISTRY", os.path.join(reihen, "graphs.json"))
    setzen(gedaechtnis, "_DIR", os.path.join(tmp, "gedaechtnis"))
    setzen(gespraeche, "_DIR", os.path.join(tmp, "gespraeche"))
    setzen(transkript, "_DIR", os.path.join(tmp, "ai_transcripts"))
    # Nach der Antwort: Transkript/Graph merken. Für die Prüfung belanglos,
    # und mit eingeschaltetem Graphen kostete es pro Zug einen Aufruf.
    setzen(consolidation, "zug_vormerken", lambda *a, **k: None)
    if hasattr(gespraeche, "_cache"):
        gespraeche._cache.clear()
    try:
        import kalender_ics
        kalender_ics.cache_leeren()
    except Exception:
        pass

    def zurueck():
        for modul, attr, wert in reversed(alt):
            setattr(modul, attr, wert)
        if hasattr(gespraeche, "_cache"):
            gespraeche._cache.clear()
    return zurueck


# ── Netz-Attrappe ──────────────────────────────────────────────────────
#
# Ersetzt net.get/post/stream_post — die eine Stelle, über die der Kern ins
# Netz geht (das Modell selbst spricht über das anthropic-SDK, nicht über
# net). So bleibt alles DARÜBER echt: web.suche formatiert die Treffer, wie
# es das immer tut, ki_werkzeuge beschriftet sie, wie es das tut.

class NetzAttrappe:
    """Antwortet nach dem Abschnitt `netz` des Falls:

        netz:
          suche:                       # erste passende Regel gewinnt
            - wenn: ferien             # Teilwort der Suchanfrage (egal ob groß/klein)
              treffer:
                - {titel: …, url: …, text: …}
          seiten:
            - wenn: schulferien.org    # Teilwort der URL
              text: "…"                # Seiteninhalt (Text oder HTML)

    Ohne passende Regel: Suche → keine Treffer, Seite → nicht erreichbar.
    """

    def __init__(self, netz: dict | None):
        netz = netz or {}
        self.suche = netz.get("suche") or []
        self.seiten = netz.get("seiten") or []
        self.protokoll = []            # (art, was, gefunden)

    def _such_regel(self, q: str):
        q = q.casefold()
        for r in self.suche:
            if str(r.get("wenn", "")).casefold() in q:
                return r
        return None

    def get(self, url, timeout=10, headers=None):
        u = urlparse(url)
        params = parse_qs(u.query)
        q = (params.get("q") or [""])[0]
        if q and ("format" in params or "duckduckgo" in u.netloc
                  or u.path.rstrip("/").endswith("search")):
            regel = self._such_regel(q)
            treffer = (regel or {}).get("treffer") or []
            self.protokoll.append(("suche", q, bool(treffer)))
            if "format" in params:                       # SearXNG-JSON
                return json.dumps({"results": [
                    {"url": t.get("url", ""), "title": t.get("titel", ""),
                     "content": t.get("text", "")} for t in treffer]}).encode()
            raise RuntimeError("Prüfstand: DuckDuckGo gibt es hier nicht")
        for s in self.seiten:
            if str(s.get("wenn", "")) in url:
                self.protokoll.append(("seite", url, True))
                text = str(s.get("text", ""))
                if "<" not in text:
                    text = "<html><body><p>" + text.replace("\n", "<br>") + "</p></body></html>"
                return text.encode("utf-8")
        self.protokoll.append(("seite", url, False))
        raise RuntimeError("Verbindung fehlgeschlagen (Seite nicht erreichbar)")

    def post(self, *a, **k):
        raise RuntimeError("Prüfstand: kein Netz außer zum Modell")

    def stream_post(self, *a, **k):
        raise RuntimeError("Prüfstand: kein Netz außer zum Modell")

    def einhaengen(self):
        """-> Rückweg."""
        import net
        alt = (net.get, net.post, net.stream_post)
        net.get, net.post, net.stream_post = self.get, self.post, self.stream_post

        def zurueck():
            net.get, net.post, net.stream_post = alt
        return zurueck


# ── Seiten für den Browser ─────────────────────────────────────────────
#
# Der Browser der KI (core/browser_sitzung.py) fährt ein echtes Chromium und
# geht damit NICHT über net — die Netz-Attrappe sieht ihn nicht. Für Fälle
# mit Browser (2026-10-09, f08) stellt der Prüfstand deshalb einen eigenen
# kleinen Server auf 127.0.0.1 hin, der nur die Seiten des Falls ausliefert
# (Vorbild: der Nachbau in tests/test_browser.py). Im Fall heißt seine
# Adresse {server}; der Fall braucht dazu `einstellungen:
# {browser_lokal_erlaubt: 1}`, sonst sperrt der Browser 127.0.0.1.

def platzhalter(wert, ersatz: dict):
    """{server} & Co. in allen Texten eines Falls ersetzen (Kopie)."""
    if isinstance(wert, str):
        for alt, neu in ersatz.items():
            wert = wert.replace(alt, neu)
        return wert
    if isinstance(wert, dict):
        return {k: platzhalter(v, ersatz) for k, v in wert.items()}
    if isinstance(wert, list):
        return [platzhalter(v, ersatz) for v in wert]
    return wert


class SeitenServer:
    """Liefert die Seiten des Abschnitts `browser.seiten` aus:

        browser:
          seiten:
            - pfad: /                       # mit ?… genau, sonst ohne Anfrage-Teil
              html: "<html>…{server}…</html>"
            - pfad: /alt
              weiter: /neu                  # Weiterleitung (302)

    Ohne Seiten startet nichts (adresse bleibt None). Unbekannter Pfad: 404.
    """

    def __init__(self, seiten: list | None):
        self.seiten = list(seiten or [])
        self.adresse = None
        self.protokoll = []            # aufgerufene Pfade

    def _finden(self, pfad: str):
        ohne = pfad.split("?", 1)[0]
        for s in self.seiten:
            if str(s.get("pfad")) == pfad:
                return s
        return next((s for s in self.seiten if str(s.get("pfad")) == ohne), None)

    def starten(self):
        """-> Rückweg (hält den Server an)."""
        if not self.seiten:
            return lambda: None
        import http.server
        import threading
        server_selbst = self

        class Antwort(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                server_selbst.protokoll.append(self.path)
                s = server_selbst._finden(self.path)
                if s and s.get("weiter"):
                    self.send_response(302)
                    self.send_header("Location", str(s["weiter"]))
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                text = str(s.get("html", "")) if s else "<p>nicht da</p>"
                roh = platzhalter(text, {"{server}": server_selbst.adresse}).encode()
                self.send_response(200 if s else 404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            do_POST = do_GET

        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Antwort)
        self.adresse = f"http://127.0.0.1:{srv.server_address[1]}"
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        def zurueck():
            srv.shutdown()
            srv.server_close()
        return zurueck


# ── Wer an Sashas Stelle die Knöpfe drückt ─────────────────────────────

KEINE_ANTWORT = "__keine__"


class Antworter:
    """Beantwortet Erlaubnis-Fragen und Knopf-Fragen (ask_choice) nach dem
    Abschnitt `antworten` des Falls:

        antworten:
          erlaubnis: ja            # ja | nein — für jedes Erlaubnis-Gate
          knopf: null              # ask_choice: null = der Dialog kommt ohne Wahl zurück
                                   # (so am 08.10.: „Sasha hat gewählt: None."),
                                   # zeitablauf = niemand drückt bis zum Timeout
          regeln:                  # erste passende gewinnt, vor den Vorgaben
            - frage_enthaelt: kraft     # Teilwort von Frage ODER Knöpfen
              waehle: krafttraining     # Knopf, der dieses Teilwort enthält
            - frage_enthaelt: löschen
              erlaubnis: nein

    Ein Zug kann eigene `antworten` haben; die gelten dann vor denen des Falls.
    null bildet den 08.10. nach: der Dialog wurde im Chat nicht angezeigt,
    zurück kam nach Sekunden „keine Wahl" (None), kein Timeout.
    """

    def __init__(self, vorgaben: dict | None):
        self.vorgaben = vorgaben or {}
        self.zug_vorgaben = {}
        self.naechste = []
        self.protokoll = []

    def _regeln(self):
        return list(self.zug_vorgaben.get("regeln") or []) + \
               list(self.vorgaben.get("regeln") or [])

    def _wert(self, schluessel, standard):
        for quelle in (self.zug_vorgaben, self.vorgaben):
            if schluessel in quelle:
                return quelle[schluessel]
        return standard

    def entscheiden(self, frage: dict) -> object:
        """permission-Event → Antwort (Knopf-Text oder None für keine)."""
        text = str(frage.get("frage", ""))
        optionen = [str(o) for o in frage.get("optionen") or []]
        gate = bool(frage.get("erlaubnis"))
        alles = (text + " " + " ".join(optionen)).casefold()
        antwort, grund = None, "Vorgabe"
        regel = next((r for r in self._regeln()
                      if str(r.get("frage_enthaelt", "")).casefold() in alles), None)
        if gate:
            wunsch = str((regel or {}).get("erlaubnis") or self._wert("erlaubnis", "ja"))
            if regel and regel.get("erlaubnis"):
                grund = f"Regel '{regel.get('frage_enthaelt')}'"
            if wunsch.casefold().startswith("j"):
                antwort = next((o for o in optionen if o.casefold().startswith("ja")),
                               "ja")
                # „nur dieses mal": kein Gesprächs-/Dauer-Ja, das in ai_config
                # landen könnte — jede Frage einzeln, wie beim ersten Mal.
                einmal = [o for o in optionen if "nur dieses" in o.casefold()]
                antwort = einmal[0] if einmal else antwort
            else:
                antwort = next((o for o in optionen if o.casefold().startswith("nein")),
                               "nein")
        else:
            if regel and "waehle" in regel:
                grund = f"Regel '{regel.get('frage_enthaelt')}'"
                ziel = regel.get("waehle")
                if ziel is None:
                    antwort = None
                else:
                    antwort = next((o for o in optionen
                                    if str(ziel).casefold() in o.casefold()), str(ziel))
            else:
                knopf = self._wert("knopf", None)
                antwort = None if knopf is None else next(
                    (o for o in optionen if str(knopf).casefold() in o.casefold()),
                    str(knopf))
        self.protokoll.append({"art": "erlaubnis" if gate else "knopf",
                               "frage": text, "optionen": optionen,
                               "antwort": antwort, "grund": grund})
        self.naechste.append(antwort)
        return antwort

    # Ersatz für state.request_permission / state.wait_permission
    def anfragen(self, options=None, timeout_default="nein"):
        self._timeout = timeout_default

    def warten(self, timeout: float = 180.0):
        if self.naechste:
            a = self.naechste.pop(0)
            if isinstance(a, str) and a.casefold() == "zeitablauf":
                return getattr(self, "_timeout", "nein")
            return a
        return getattr(self, "_timeout", "nein")

    def einhaengen(self):
        import state
        alt = (state.request_permission, state.wait_permission)
        state.request_permission, state.wait_permission = self.anfragen, self.warten

        def zurueck():
            state.request_permission, state.wait_permission = alt
        return zurueck
