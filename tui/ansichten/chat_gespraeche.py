# tui/ansichten/chat_gespraeche.py
#
# Was der Chat mit GESPRÄCHEN tut (Claude-Web-Plan Phase 2, 2026-10-07):
# neu, öffnen, umbenennen, archivieren, wiederholen, bearbeiten, Verlauf
# laden und im Hintergrund nachsehen, ob irgendwo etwas Neues steht.
#
# Ein Mixin für die Klasse Chat (chat.py) — eigene Datei, damit chat.py beim
# Zeichnen und Tippen bleibt. Die Methoden lesen self.AI / self.AI_LOCK wie
# der Rest des Chats. Speicher und Regeln: core/gespraeche.py (Backend).

import json
import threading
import time
import urllib.error

from . import spur
from .basis import api_call
from .chat_ablage import ablage_eintrag, anhang_eintrag
from .projekte import projekt_name


def pruefung_eintraege(erledigt, offen, log=None):
    """Die dezenten Zeilen des Ehrlichkeits-Prüfers (core/ehrlichkeit.py)
    unter einer Antwort: was Python im Werkzeug-Protokoll sah („✓ Termin
    eingetragen: Zahnarzt") und was die KI zugesagt, aber noch nicht getan
    hat. „offen" gilt fürs ganze Gespräch, steht also nur einmal: ist `log`
    gegeben, fliegen ältere offen-Zeilen dort raus. -> [(rolle, text)]"""
    raus = []
    zeile = (erledigt or {}).get("zeile") if isinstance(erledigt, dict) else ""
    if zeile:
        raus.append(("erledigt", str(zeile)))
    if log is not None:
        log[:] = [e for e in log if e[0] != "offen"]
    if offen:
        raus.append(("offen", "offen: " + " · ".join(str(x) for x in offen)))
    return raus


def quellen_eintraege(quellen):
    """Die gelesenen Seiten eines Zugs als dezente Zeile unter der Antwort
    (Feld `quellen`, core/quellen.py, 2026-10-10): „Quellen: „Titel“ –
    Adresse · …". Python zieht sie aus den Werkzeug-Ergebnissen, die KI
    schreibt keine Adressen ab. -> [("quellen", text)] oder []."""
    teile = ["„%s“ – %s" % (q.get("titel") or q.get("url"), q.get("url"))
             for q in quellen or [] if isinstance(q, dict) and q.get("url")]
    return [("quellen", "Quellen: " + " · ".join(teile))] if teile else []


def warn_eintraege(warnungen, wechsel=None):
    """Warnzeilen ÜBER einer Antwort (2026-10-09): ein Modellwechsel
    (Budget-Rückfall, Satz vom Backend) und was der Prüfer nach allen
    Korrekturrunden noch fand. -> [("warnung", text)]"""
    raus = []
    if isinstance(wechsel, dict) and wechsel.get("satz"):
        raus.append(("warnung", str(wechsel["satz"])))
    raus += [("warnung", str(w)) for w in warnungen or []]
    return raus


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
            # Anhänge und Dokumente als „▤"-Zeilen (Phase 5, 2026-10-07).
            log += [anhang_eintrag(a) for a in m.get("anhaenge") or [] if isinstance(a, dict)]
            continue
        if (m.get("denken") or "").strip():
            log.append(("denken", m["denken"].strip()))
        for w in m.get("werkzeuge") or []:
            if isinstance(w, dict):
                name = str(w.get("name") or "?")
                # Seit 2026-10-07 mit gekürztem Ergebnis (ui/routen/ki.py,
                # ERGEBNIS_MAX): der Schritt „Used … ›" klappt es auf.
                log.append(("werkzeug", "%s(%s)" % (name, w.get("args") or "")))
                if w.get("fehler"):
                    log.append(("werkzeug_fehler", "%s ✗ %s" % (name, w.get("ergebnis") or "")))
                elif w.get("ergebnis"):
                    log.append(("werkzeug_ergebnis", "↳ " + str(w["ergebnis"])))
        log += [ablage_eintrag(d) for d in m.get("dokumente") or [] if isinstance(d, dict)]
        log += warn_eintraege(m.get("warnungen"), m.get("modell_wechsel"))
        if txt:
            log.append(("ai", txt))
        if m.get("fehler"):        # abgebrochener Zug (2026-10-09): eigener Eintrag
            log.append(("abbruch", " ".join(str(m["fehler"]).split())))
        log += quellen_eintraege(m.get("quellen"))
        log += pruefung_eintraege(m.get("erledigt"), m.get("offen"), log)
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
            if AI["streaming"] and (self.strom_laeuft_hier() or not gid
                                    or gid == self.strom_gid()):
                return                 # eine laufende Antwort nie zerreißen
            if gid and AI.get("gid") not in (None, gid):
                return                 # inzwischen woanders hin gewechselt
            if stand is not None:
                eintraege, aktiv = stand
                AI["gespraeche"] = eintraege
                AI["gid"] = gid or aktiv
                AI["titel"] = next((e.get("titel") or "" for e in eintraege
                                    if e.get("id") == AI["gid"]), "")
                AI["projekt"] = projekt_name(eintraege, AI["gid"], AI.get("neu_projekt"))
            elif gid:
                AI["gid"] = gid
            if geholt is not None:
                AI["log"], nachrichten = geholt
                AI["n_server"] = len(nachrichten)
                AI["n"] = len(AI["log"])
                # Welche Antwort ein Ablauf-Protokoll hat („trace ›", spur.py).
                AI["spuren"] = spur.spuren(AI["log"], nachrichten)
            AI["loaded"] = True
            self._neu_markieren()
            self._neu_hinweis_geben()
            gid_jetzt = AI.get("gid")
        if geholt is not None:             # ids + Bewertungen (bewertung.py)
            self.bewertung.geladen(gid_jetzt, geholt[1])

    def ai_load_history(self):
        """Beim Öffnen des Chats: Status für den Titel, dann den Verlauf."""
        self.status_holen()
        self.verlauf_laden()
        seite = getattr(self, "seite", None)
        if seite is not None:               # Blatt-Zeichen in der Seitenleiste
            seite.doku_holen()

    def neu_woanders(self):
        """Gespräche, die gerade NICHT angezeigt werden und eine Antwort
        haben, die Sasha hier noch nicht gesehen hat (Liste vom Backend
        + fertig im Hintergrund, chat_strom.py). Das offene Gespräch und das
        der noch laufenden Antwort zählen nie. Unter AI_LOCK. -> [gid]"""
        AI = self.AI
        sichtbar = AI.get("gid")
        laeuft = self.strom_gid() if not self.strom_laeuft_hier() else None
        ids = [e.get("id") for e in AI.get("gespraeche") or [] if e.get("ungelesen")]
        ids += [g for g in AI.get("ungesehen") or () if g not in ids]
        return [g for g in ids if g and g != sichtbar and g != laeuft]

    def _neu_hinweis_geben(self):
        """Nach dem Öffnen des Fensters einmal: Hinweis, wenn wirklich etwas
        Neues woanders liegt (unter AI_LOCK; das offene Gespräch ist bekannt)."""
        AI = self.AI
        if not AI.pop("neu_hinweis", False):
            return
        if self.neu_woanders():
            if not AI.get("msg"):
                AI["msg"] = "neues in einem anderen gespräch — tab zeigt die gespräche"
        elif AI.get("msg", "").startswith("neues in einem anderen gespräch"):
            AI["msg"] = ""

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
                    # Läuft die Antwort woanders, darf das offene Gespräch
                    # (ein anderes) wie sonst nachladen (chat_strom.py).
                    if self.strom_laeuft_hier() or not AI["loaded"]:
                        continue
                stand = self.liste.holen()
                if stand is None:
                    continue
                eintraege, aktiv = stand
                neu_laden = False
                with AI_LOCK:
                    if self.strom_laeuft_hier():
                        continue
                    AI["gespraeche"] = eintraege
                    mein = next((e for e in eintraege if e.get("id") == AI.get("gid")), None)
                    if mein:
                        AI["titel"] = mein.get("titel") or ""
                        AI["projekt"] = projekt_name(eintraege, AI["gid"])
                        neu_laden = AI["active"] and (mein.get("anzahl", 0) != AI["n_server"]
                                                      or mein.get("ungelesen"))
                    self._neu_markieren()
                if neu_laden and AI.get("gid") != self.strom_gid():
                    self.verlauf_laden(AI["gid"])
            except Exception:
                pass          # ein Poll, der die TUI abschiesst, waere schlimmer

    # ── Ablauf-Protokoll („trace", spur.py, 2026-10-09) ─────────────────
    def ablauf_holen(self, nid, warten=False):
        """Das Protokoll einer Antwort holen, einmal je Antwort. Im
        Hintergrund (warten=True: gleich hier, für Tests); bis es da ist,
        steht spur.LAEDT in AI["ablaeufe"], bei Fehler ein kurzer Satz."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        gid = AI.get("gid")
        with AI_LOCK:
            ablaeufe = AI.setdefault("ablaeufe", {})
            if not gid or isinstance(ablaeufe.get(nid), list) or ablaeufe.get(nid) == spur.LAEDT:
                return
            ablaeufe[nid] = spur.LAEDT

        def los():
            try:
                # Länger als die üblichen 3 s: ein Protokoll kann groß sein.
                d = api_call("/api/gespraeche/%s/ablauf/%s" % (gid, nid), timeout=15)
                wert = d.get("ablauf") if isinstance(d, dict) else None
                if not isinstance(wert, list):
                    wert = "trace not available"
            except urllib.error.HTTPError:
                wert = "no trace stored for this answer"
            except (urllib.error.URLError, OSError, ValueError):
                wert = "no connection — trace not loaded (click again)"
            with AI_LOCK:
                AI.setdefault("ablaeufe", {})[nid] = wert
                if isinstance(wert, str) and wert.startswith("no connection"):
                    AI["ablaeufe"].pop(nid, None)       # später noch einmal versuchen
                    AI["msg"] = wert

        if warten:
            los()
        else:
            threading.Thread(target=los, daemon=True).start()

    def trace_ablegen(self):
        """/trace: der Ablauf der letzten Antwort als Textdatei in die Ablage."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst danach"
            return
        if not AI.get("gid"):
            AI["msg"] = "noch kein gespräch — nichts nachzulesen"
            return
        try:
            r = api_call("/api/gespraeche/%s/ablauf/letzte/ablage" % AI["gid"], "POST", {},
                         timeout=15)
        except urllib.error.HTTPError as e:
            grund = ""
            try:
                grund = json.loads(e.read().decode("utf-8", "replace")).get("error") or ""
            except Exception:
                pass
            AI["msg"] = grund or "kein ablauf zum ablegen"
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht abgelegt"
            return
        dok = (r or {}).get("dokument") if isinstance(r, dict) else None
        if not dok:
            AI["msg"] = "ablegen ging nicht"
            return
        with self.AI_LOCK:
            self.ablage_event(dok)             # „▤ Ablauf: …" im Verlauf
        AI["msg"] = "trace liegt in der ablage: " + str(dok.get("titel") or "")

    # ── Wechseln ───────────────────────────────────────────────────────
    def leeren(self):
        """Anzeige auf „neues Gespräch" (ohne Backend-Aufruf)."""
        with self.AI_LOCK:
            AI = self.AI
            AI["log"], AI["n"], AI["scroll"], AI["n_server"] = [], 0, 0, 0
            AI["gid"], AI["titel"], AI["ersetzt"] = None, "", None
            AI["projekt"] = ""
            AI["spuren"] = {}

    def _laeuft_text(self):
        """Warum das gerade nicht geht: hier läuft eine Antwort, oder woanders."""
        if self.strom_laeuft_hier():
            return "antwort läuft noch — erst stoppen (ctrl+c)"
        return self.warte_text()

    def neues_gespraech(self):
        """/neu, n in der Liste: das nächste Senden beginnt ein neues
        Gespräch. Das alte bleibt in der Liste (seit 2026-10-07)."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = self._laeuft_text()
            return
        try:
            r = api_call("/api/chat/clear", "POST", {})
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — kein neues gespräch"
            return
        self.leeren()
        # Aus einem Projekt heraus bleibt das neue Gespräch darin (Phase 6).
        AI["projekt"] = str((r or {}).get("name") or "") if isinstance(r, dict) else ""
        AI["msg"] = ("neues gespräch im projekt „%s“" % AI["projekt"]) if AI["projekt"] \
            else "neues gespräch"

    def gespraech_oeffnen(self, gid):
        """Ein Gespräch aus der Liste öffnen (auf diesem Rechner aktiv)."""
        AI = self.AI
        if AI["streaming"]:
            self._oeffnen_waehrend_antwort(gid)
            return
        AI.setdefault("ungesehen", set()).discard(gid)
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

    def _oeffnen_waehrend_antwort(self, gid):
        """Wechseln, während eine Antwort läuft (2026-10-09, wie Claude Web):
        sie läuft im Hintergrund weiter (chat_strom.py). Beim Backend wird
        NICHT gewechselt — das hebt „für dieses Gespräch" auf, und die
        laufende Antwort fragte sonst bei jedem Schritt neu; strom_aus holt
        das nach, wenn sie fertig ist."""
        AI = self.AI
        with self.AI_LOCK:
            if gid == AI.get("gid"):
                return
            if gid is not None and gid == self.strom_gid():
                self.strom_zurueckholen()          # zurück: live weiter
                AI["msg"] = ""
                return
            if self.strom_laeuft_hier():
                self.strom_wegstellen()
            AI["aktiv_nachholen"] = True
            AI.setdefault("ungesehen", set()).discard(gid)
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
            AI["msg"] = "titel: %s · /rename <neuer titel> ändert ihn" % (AI.get("titel") or "—")
        elif AI["gid"] == "erinnerungen":
            AI["msg"] = "„erinnerungen“ behält seinen namen"
        else:
            self.titel_setzen(AI["gid"], arg)

    def archivieren_aktuell(self):
        """/archiv: das offene Gespräch ins Archiv, dann ein neues."""
        AI = self.AI
        gid = AI.get("gid")
        if AI["streaming"]:
            AI["msg"] = self._laeuft_text()
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
            AI["msg"] = self._laeuft_text()
            return
        with AI_LOCK:
            letzte = max((i for i, (r, _t) in enumerate(AI["log"]) if r == "user"), default=None)
            if letzte is None or not AI.get("gid"):
                AI["msg"] = "nichts zu wiederholen"
                return
            frage = AI["log"][letzte][1]
            del AI["log"][letzte + 1:]
            AI["spuren"] = {i: n for i, n in (AI.get("spuren") or {}).items() if i < letzte}
        self.senden(frage, wiederholen=True)

    def bearbeiten(self):
        """/bearbeiten: die letzte eigene Nachricht in die Eingabe holen;
        Senden ersetzt ab dort (der Rest des Gesprächs danach zählt nicht
        mehr, bleibt aber gespeichert)."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = self._laeuft_text()
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
