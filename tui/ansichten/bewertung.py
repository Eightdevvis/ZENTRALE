# tui/ansichten/bewertung.py
#
# Antworten bewerten (2026-10-08). Sasha: „bewertungen für uns um unser
# eigenes system zu verbessern … so dass ich nen kommentar hinzufügen könnte
# wenn ich wollte. also am besten einfach so n kleines modal das aufgeht."
#
# Unter jeder Antwort steht „copy · retry · good · bad" (verlauf.py). Klick
# oder Enter auf good/bad — oder + / − bei einer gewählten Antwort im Verlauf
# — öffnet ein kleines Fenster über dem Chat: „Was war gut? (optional)" mit
# derselben Eingabe wie unten (eingabe.py). Enter speichert (auch leer),
# Alt+Enter = neue Zeile, Tab wechselt gut ↔ schlecht, Esc bricht ab.
#
# Esc speichert NICHT (2026-10-08): ein versehentlicher Klick auf „bad" soll
# keine Spur hinterlassen, und ohne Kommentar speichern ist ohnehin nur ein
# Enter. Danach steht unter der Antwort „good ✓" bzw. „bad ✗" hervorgehoben;
# noch einmal klicken öffnet das Fenster wieder (mit dem alten Kommentar)
# und ändert die Bewertung — im Backend ein neues Ereignis, das letzte gilt
# (core/rueckmeldungen.py).
#
# Welche Antwort welche Nachricht-id hat: der Verlauf der TUI ist eine Liste
# (rolle, text) ohne ids. Die k-te „ai"-Zeile ist die k-te Antwort mit Text
# in /api/chat/history — die ids merkt sich geladen() beim Laden. Fehlt eine
# (eben erst gestreamt) oder passt sie nicht mehr (404, z. B. nach retry),
# wird der Verlauf einmal frisch geholt.
#
# Zustand: AI["bewertung"] (offenes Fenster oder None), AI["bewertungen"]
# {nachricht-id: {wert, kommentar}}, AI["antwort_ids"] (gid, [ids]).

import curses
import urllib.error
import urllib.parse

from . import eingabe, fussleiste
from .basis import api_call

WORT = {1: "good", -1: "bad"}
ZEICHEN = {1: "✓", -1: "✗"}            # einspaltig (unicodedata: „N")
FRAGE = {1: "Was war gut? (optional)", -1: "Was war schlecht? (optional)"}
ZIEL = {1: "gut", -1: "schlecht"}         # Ziel-Art im Verlauf (verlauf.py)
KOMMENTAR_MAX = 2000                      # wie core/rueckmeldungen.KOMMENTAR_MAX
BREITE = 60                               # so breit höchstens
HOEHE = 4                                 # Zeilen der Eingabe höchstens


def antwort_ids(nachrichten):
    """Die ids der Antworten mit Text aus /api/chat/history, in Reihenfolge
    — genau die, die verlauf_aus als „ai"-Zeile zeigt."""
    return [m.get("id") for m in nachrichten or []
            if isinstance(m, dict) and m.get("role") != "user"
            and (m.get("content") or "").strip()]


def antwort_nummer(log, i):
    """Die wievielte Antwort ist log[i]? (0-basiert) — oder None."""
    if not 0 <= i < len(log) or log[i][0] != "ai":
        return None
    return sum(1 for r, _t in log[:i] if r == "ai")


def marken(log, ids, bewertungen):
    """{log-index: wert} für den Verlauf (welche Antwort wie bewertet ist)."""
    raus, k = {}, 0
    for i, (rolle, _t) in enumerate(log):
        if rolle != "ai":
            continue
        if k < len(ids) and ids[k] in bewertungen:
            raus[i] = bewertungen[ids[k]].get("wert")
        k += 1
    return raus


class Bewertung:
    """Das kleine Fenster und alles, was eine Bewertung braucht."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        self.AI.setdefault("bewertung", None)
        self.AI.setdefault("bewertungen", {})
        self.AI.setdefault("antwort_ids", (None, []))

    # ── Laden ──────────────────────────────────────────────────────────
    def geladen(self, gid, nachrichten):
        """Nach dem Laden eines Verlaufs (chat_gespraeche.verlauf_laden):
        ids merken, die Bewertungen dieses Gesprächs holen. Im Hintergrund;
        scheitert still (dann fehlen nur die Häkchen)."""
        ids = antwort_ids(nachrichten)
        holen = {}
        if gid:
            try:
                d = api_call("/api/rueckmeldungen?gespraech=" + urllib.parse.quote(gid, safe=""))
                for e in (d or {}).get("rueckmeldungen") or []:
                    if isinstance(e, dict) and e.get("nachricht"):
                        holen[e["nachricht"]] = {"wert": e.get("wert"),
                                                 "kommentar": e.get("kommentar") or ""}
            except (urllib.error.URLError, OSError, ValueError, AttributeError):
                holen = None
        with self.chat.AI_LOCK:
            self.AI["antwort_ids"] = (gid, ids)
            if holen is not None:
                self.AI["bewertungen"] = holen
            ziel = self.AI.pop("springen", None)
            if ziel and ziel in ids:            # aus Customize → Feedback
                k = ids.index(ziel)
                i = [j for j, (r, _t) in enumerate(self.AI["log"]) if r == "ai"]
                if k < len(i):
                    wert = (self.AI["bewertungen"].get(ziel) or {}).get("wert") or 1
                    self.AI["vwahl"] = (ZIEL.get(wert, "gut"), i[k])
                    self.AI["vwahl_folgen"] = True
                    self.AI["fokus"] = "verlauf"

    def _ids(self):
        gid, ids = self.AI.get("antwort_ids") or (None, [])
        return ids if gid and gid == self.AI.get("gid") else []

    def marken(self, log):
        return marken(log, self._ids(), self.AI.get("bewertungen") or {})

    def _id_holen(self, i, frisch=False):
        """Nachricht-id der Antwort log[i]; frisch=True holt den Verlauf neu."""
        AI = self.AI
        k = antwort_nummer(AI["log"], i)
        if k is None:
            return None
        ids = self._ids()
        if frisch or k >= len(ids):
            if not AI.get("gid"):
                return None
            try:
                h = api_call("/api/chat/history?gespraech=" + AI["gid"])
            except (urllib.error.URLError, OSError, ValueError):
                return None
            ids = antwort_ids(h if isinstance(h, list) else [])
            AI["antwort_ids"] = (AI["gid"], ids)
        return ids[k] if k < len(ids) else None

    # ── Öffnen, speichern ──────────────────────────────────────────────
    def oeffnen(self, i, wert):
        """good/bad unter der Antwort log[i] (Klick, Enter, + / −)."""
        AI = self.AI
        if antwort_nummer(AI["log"], i) is None:
            return
        ids = self._ids()
        k = antwort_nummer(AI["log"], i)
        alt = (AI.get("bewertungen") or {}).get(ids[k]) if k < len(ids) else None
        text = (alt or {}).get("kommentar") or ""
        AI["bewertung"] = {"i": i, "wert": 1 if wert > 0 else -1, "text": text,
                           "cur": len(text), "u8": b""}
        AI["msg"] = ""

    def schliessen(self):
        self.AI["bewertung"] = None

    def umschalten(self):
        B = self.AI["bewertung"]
        B["wert"] = -B["wert"]

    def speichern(self):
        AI, B = self.AI, self.AI["bewertung"]
        if not AI.get("gid"):
            AI["msg"] = "noch kein gespräch — nichts zu bewerten"
            self.schliessen()
            return
        kommentar = B["text"].strip()[:KOMMENTAR_MAX]
        nid = self._id_holen(B["i"])
        for versuch in (0, 1):
            if nid is None:
                break
            try:
                api_call("/api/rueckmeldung", "POST",
                         {"gespraech": AI["gid"], "nachricht": nid, "wert": B["wert"],
                          "kommentar": kommentar})
                break
            except urllib.error.HTTPError as e:
                # 404: die gemerkte id passt nicht mehr (retry, anderer
                # Rechner) — einmal frisch holen.
                if e.code != 404 or versuch:
                    AI["msg"] = "bewertung nicht gespeichert (%s)" % e.code
                    return
                nid = self._id_holen(B["i"], frisch=True)
            except (urllib.error.URLError, OSError, ValueError):
                AI["msg"] = "keine verbindung — bewertung nicht gespeichert"
                return
        if nid is None:
            AI["msg"] = "diese antwort ist noch nicht gespeichert — gleich noch mal"
            return
        AI.setdefault("bewertungen", {})[nid] = {"wert": B["wert"], "kommentar": kommentar}
        AI["msg"] = "bewertung gespeichert%s — danke" % (" mit kommentar" if kommentar else "")
        self.schliessen()

    # ── Tasten ─────────────────────────────────────────────────────────
    def tasten(self):
        return [("enter", "save"), ("alt+enter", "new line"), ("tab", "good/bad"),
                ("esc", "cancel")]

    def taste(self, ch):
        """Eine Taste im offenen Fenster (Chat.taste hat Esc/Alt+Enter
        schon gedeutet: 27 = Esc, TASTE_ALT_ENTER = neue Zeile)."""
        from .chat import TASTE_ALT_ENTER, Chat
        B = self.AI["bewertung"]
        if ch == 27:
            self.schliessen()
            self.AI["msg"] = "nicht bewertet"
        elif ch in (10, 13, curses.KEY_ENTER):
            art, text, pos = eingabe.enter_deuten(B["text"], min(B["cur"], len(B["text"])))
            B["text"], B["cur"] = text, pos
            if art == "senden":
                self.speichern()
        elif ch == 9:
            self.umschalten()
        elif ch == TASTE_ALT_ENTER:
            self._einfuegen("\n")
        elif ch in Chat._BEARBEITEN:
            B["text"], B["cur"] = Chat._BEARBEITEN[ch](B["text"], min(B["cur"], len(B["text"])))
        elif 32 <= ch <= 126:
            self._einfuegen(chr(ch))
        elif 128 <= ch <= 255:                 # ein Byte eines Umlauts (UTF-8)
            B["u8"], zeichen = eingabe.utf8_byte(B.get("u8", b""), ch)
            if zeichen is not None and eingabe.druckbar(zeichen):
                self._einfuegen(zeichen)

    def _einfuegen(self, s):
        B = self.AI["bewertung"]
        B["text"], B["cur"] = eingabe.einfuegen(B["text"], min(B["cur"], len(B["text"])), s,
                                                grenze=KOMMENTAR_MAX)

    # ── Zeichnen ───────────────────────────────────────────────────────
    def zeichnen(self, top, x0, h, w):
        """Das Fenster mittig über dem Chat-Inhalt (top, x0, h, w). Es nimmt
        alle Klicks: was darunter liegt, ist solange nicht anklickbar."""
        chat, B = self.chat, self.AI["bewertung"]
        C, addclip = chat.z.C, chat.z.addclip
        bw = max(20, min(BREITE, w - 4))
        innen = bw - 4
        tz, cy, cx, _oben = eingabe.anzeige(B["text"], min(B["cur"], len(B["text"])),
                                            innen, max(1, min(HOEHE, h - 7)))
        bh = len(tz) + 6
        y0 = top + max(0, (h - bh) // 2)
        x = x0 + max(0, (w - bw) // 2)
        chat.klicks = []                       # das Fenster liegt obenauf
        rahmen = C["acc"]
        leer = " " * (bw - 2)
        addclip(y0, x, "┌" + "─" * (bw - 2) + "┐", bw, rahmen)
        for y in range(y0 + 1, y0 + bh - 1):
            addclip(y, x, "│", 1, rahmen)
            addclip(y, x + 1, leer, bw - 2, C["bright"])
            addclip(y, x + bw - 1, "│", 1, rahmen)
        addclip(y0 + bh - 1, x, "└" + "─" * (bw - 2) + "┘", bw, rahmen)
        # Kopf: good · bad (das gewählte hervorgehoben, Klick wechselt)
        kx = x + 2
        for wert in (1, -1):
            wort = "%s %s" % (WORT[wert], ZEICHEN[wert])
            attr = (C["acc"] | curses.A_REVERSE) if B["wert"] == wert else C["faint"]
            addclip(y0 + 1, kx, wort, len(wort), attr)
            if B["wert"] != wert:
                chat.klickbar(y0 + 1, kx, len(wort), self.umschalten)
            kx += len(wort) + 3
        addclip(y0 + 2, x + 2, FRAGE[B["wert"]], innen, C["dim"])
        for k, t in enumerate(tz):
            addclip(y0 + 3 + k, x + 2, t or " ", innen, C["bright"])
        if cx < innen:
            zeichen = tz[cy][cx] if cx < len(tz[cy]) else " "
            chat.z.safe_addstr(y0 + 3 + cy, x + 2 + cx, zeichen, C["bright"] | curses.A_REVERSE)
        # Fuß: was geht — anklickbar
        fy, fx = y0 + bh - 2, x + 2
        for text, aktion in (("save", self.speichern), ("cancel", self._abbrechen)):
            addclip(fy, fx, "[%s]" % text, len(text) + 2, C["acc"])
            chat.klickbar(fy, fx, len(text) + 2, aktion)
            fx += len(text) + 4
        rest = fussleiste.text([("alt+enter", "new line"), ("tab", "good/bad")])
        if fx + len(rest) < x + bw - 1:
            addclip(fy, fx, rest, x + bw - 1 - fx, C["faint"])

    def _abbrechen(self):
        self.schliessen()
        self.AI["msg"] = "nicht bewertet"
