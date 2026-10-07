# tui/ansichten/chat_gespraeche.py
#
# Was der Chat mit GESPRÄCHEN tut (Claude-Web-Plan Phase 2, 2026-10-07):
# neu, öffnen, umbenennen, archivieren, wiederholen, bearbeiten, Verlauf
# laden und im Hintergrund nachsehen, ob irgendwo etwas Neues steht.
#
# Ein Mixin für die Klasse Chat (chat.py) — eigene Datei, damit chat.py beim
# Zeichnen und Tippen bleibt. Die Methoden lesen self.AI / self.AI_LOCK wie
# der Rest des Chats. Speicher und Regeln: core/gespraeche.py (Backend).

import threading
import time
import urllib.error

from .basis import api_call


def verlauf_aus(h):
    """Die Nachrichten von /api/chat/history als Verlaufs-Zeilen.
    -> [(rolle, text)]. Seit 2026-10-07 mit Denken und Werkzeugen der
    Antwort davor, in der Reihenfolge, in der sie live erschienen."""
    log = []
    for m in h if isinstance(h, list) else []:
        if not isinstance(m, dict):
            continue
        txt = (m.get("content") or "").strip()
        if m.get("role") == "user":
            if txt:
                log.append(("user", txt))
            continue
        if (m.get("denken") or "").strip():
            log.append(("denken", m["denken"].strip()))
        for w in m.get("werkzeuge") or []:
            if isinstance(w, dict):
                name = str(w.get("name") or "?")
                if w.get("fehler"):
                    log.append(("werkzeug_fehler", "%s(%s) ✗" % (name, w.get("args") or "")))
                else:
                    log.append(("werkzeug", "%s(%s)" % (name, w.get("args") or "")))
        if txt:
            log.append(("ai", txt))
    return log


def ai_verlauf_holen(gid=None):
    """Den Verlauf eines Gesprächs vom Backend holen (ohne gid: das aktive).
    -> (log, nachrichten) oder None. Holen markiert es als gelesen."""
    try:
        h = api_call("/api/chat/history" + ("?gespraech=" + gid if gid else ""))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(h, list):
        return None
    return verlauf_aus(h), h


class GespraechsSteuerung:

    # ── Laden ──────────────────────────────────────────────────────────
    def verlauf_laden(self, gid=None):
        """Verlauf (ohne gid: das aktive Gespräch) + Liste holen und
        übernehmen. Läuft im Hintergrund; scheitert still."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        geholt = ai_verlauf_holen(gid)
        stand = self.liste.holen()
        with AI_LOCK:
            if AI["streaming"]:
                return                 # eine laufende Antwort nie zerreißen
            if stand is not None:
                eintraege, aktiv = stand
                AI["gespraeche"] = eintraege
                AI["gid"] = gid or aktiv
                AI["titel"] = next((e.get("titel") or "" for e in eintraege
                                    if e.get("id") == AI["gid"]), "")
            elif gid:
                AI["gid"] = gid
            if geholt is not None:
                AI["log"], nachrichten = geholt
                AI["n_server"] = len(nachrichten)
                AI["n"] = len(AI["log"])
            AI["loaded"] = True
            self._neu_markieren()

    def ai_load_history(self):
        """Beim Öffnen des Chats: Status für den Titel, dann den Verlauf."""
        self.status_holen()
        self.verlauf_laden()

    def _neu_markieren(self):
        """● im Titel: ungelesen ist etwas in einem Gespräch, das gerade
        NICHT vor Sasha liegt (unter AI_LOCK aufrufen)."""
        AI = self.AI
        AI["neu"] = any(e.get("ungelesen") and not (AI["active"] and e.get("id") == AI.get("gid"))
                        for e in AI.get("gespraeche") or [])

    def ai_poll(self):
        """Alle 20 s die Gesprächsliste holen: Titel, ● für Ungelesenes, und
        das offene Gespräch neu laden, wenn dort etwas dazukam (die KI hat
        von sich aus gesprochen, oder der andere Rechner hat geschrieben).

        Während eines Streams wird nichts angefasst — dort wächst die
        Antwort Token für Token und würde vom Übernehmen zerrissen."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        while True:
            time.sleep(20)
            try:
                with AI_LOCK:
                    if AI["streaming"] or not AI["loaded"]:
                        continue
                stand = self.liste.holen()
                if stand is None:
                    continue
                eintraege, aktiv = stand
                neu_laden = False
                with AI_LOCK:
                    if AI["streaming"]:
                        continue
                    AI["gespraeche"] = eintraege
                    mein = next((e for e in eintraege if e.get("id") == AI.get("gid")), None)
                    if mein:
                        AI["titel"] = mein.get("titel") or ""
                        neu_laden = AI["active"] and (mein.get("anzahl", 0) != AI["n_server"]
                                                      or mein.get("ungelesen"))
                    self._neu_markieren()
                if neu_laden:
                    self.verlauf_laden(AI["gid"])
            except Exception:
                pass          # ein Poll, der die TUI abschiesst, waere schlimmer

    # ── Wechseln ───────────────────────────────────────────────────────
    def leeren(self):
        """Anzeige auf „neues Gespräch" (ohne Backend-Aufruf)."""
        with self.AI_LOCK:
            AI = self.AI
            AI["log"], AI["n"], AI["scroll"], AI["n_server"] = [], 0, 0, 0
            AI["gid"], AI["titel"], AI["ersetzt"] = None, "", None

    def neues_gespraech(self):
        """/neu, n in der Liste: das nächste Senden beginnt ein neues
        Gespräch. Das alte bleibt in der Liste (seit 2026-10-07)."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
            return
        try:
            api_call("/api/chat/clear", "POST", {})
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — kein neues gespräch"
            return
        self.leeren()
        AI["msg"] = "neues gespräch"

    def gespraech_oeffnen(self, gid):
        """Ein Gespräch aus der Liste öffnen (auf diesem Rechner aktiv)."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
            return
        try:
            api_call("/api/gespraeche/aktiv", "POST", {"id": gid})
        except urllib.error.HTTPError:
            AI["msg"] = "das gespräch gibt es nicht mehr"
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht gewechselt"
            return
        self.leeren()
        with self.AI_LOCK:
            AI["gid"] = gid
            AI["msg"] = ""
        threading.Thread(target=self.verlauf_laden, args=(gid,), daemon=True).start()

    # ── Ändern ─────────────────────────────────────────────────────────
    def titel_setzen(self, gid, titel):
        AI = self.AI
        try:
            r = api_call("/api/gespraeche/%s/titel" % gid, "POST", {"titel": titel})
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "umbenennen ging nicht"
            return
        if gid == AI.get("gid") and isinstance(r, dict):
            AI["titel"] = r.get("titel") or titel
        AI["msg"] = "umbenannt"

    def befehl_titel(self, arg):
        """/titel <text> benennt das offene Gespräch um; ohne Text zeigt es ihn."""
        AI = self.AI
        if not AI.get("gid"):
            AI["msg"] = "noch kein gespräch — erst etwas schreiben"
        elif not arg:
            AI["msg"] = "titel: %s · /titel <neuer titel> ändert ihn" % (AI.get("titel") or "—")
        elif AI["gid"] == "erinnerungen":
            AI["msg"] = "„erinnerungen“ behält seinen namen"
        else:
            self.titel_setzen(AI["gid"], arg)

    def archivieren_aktuell(self):
        """/archiv: das offene Gespräch ins Archiv, dann ein neues."""
        AI = self.AI
        gid = AI.get("gid")
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
        elif not gid:
            AI["msg"] = "noch kein gespräch — nichts zu archivieren"
        elif gid == "erinnerungen":
            AI["msg"] = "„erinnerungen“ bleibt in der liste"
        else:
            try:
                api_call("/api/gespraeche/%s/archiv" % gid, "POST", {"an": True})
            except (urllib.error.URLError, OSError, ValueError):
                AI["msg"] = "keine verbindung — nicht archiviert"
                return
            self.leeren()
            AI["msg"] = "archiviert — neues gespräch · tab, dann z zeigt das archiv"

    def wiederholen(self):
        """/wiederholen: letzte Antwort verwerfen, letzte eigene Nachricht neu."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
            return
        with AI_LOCK:
            letzte = max((i for i, (r, _t) in enumerate(AI["log"]) if r == "user"), default=None)
            if letzte is None or not AI.get("gid"):
                AI["msg"] = "nichts zu wiederholen"
                return
            frage = AI["log"][letzte][1]
            del AI["log"][letzte + 1:]
        self.senden(frage, wiederholen=True)

    def bearbeiten(self):
        """/bearbeiten: die letzte eigene Nachricht in die Eingabe holen;
        Senden ersetzt ab dort (der Rest des Gesprächs danach zählt nicht
        mehr, bleibt aber gespeichert)."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
            return
        if not AI.get("gid"):
            AI["msg"] = "noch nichts zu bearbeiten"
            return
        try:
            h = api_call("/api/chat/history?gespraech=" + AI["gid"])
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung"
            return
        letzte = next((m for m in reversed(h if isinstance(h, list) else [])
                       if isinstance(m, dict) and m.get("role") == "user"), None)
        if not letzte:
            AI["msg"] = "noch nichts zu bearbeiten"
            return
        AI["input"] = letzte.get("content") or ""
        AI["cur"] = len(AI["input"])
        AI["ersetzt"] = letzte.get("id")
        AI["msg"] = "bearbeiten: enter schickt neu (ab hier ersetzt) · esc bricht ab"
