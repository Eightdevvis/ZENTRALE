# tui/ansichten/gespraechsliste.py
#
# Die Gesprächsliste im KI-Chat (Claude-Web-Plan Phase 2, 2026-10-07):
# eine Überlagerung IM Chat-Kasten — sie nimmt den Platz des Verlaufs ein,
# solange sie offen ist. Geöffnet mit Tab (bei leerer Eingabe) oder /liste.
#
# Warum Überlagerung statt Seitenleiste: der Chat-Kasten ist auf 80×24 nur
# gut 40 Spalten breit; eine Seitenleiste daneben ließe für den Verlauf zu
# wenig übrig. Die Liste braucht den Platz nur kurz — zum Wählen.
#
# Tasten: ↑↓ wählen · Enter öffnen · n neu · r umbenennen · a archivieren
# (im Archiv: zurückholen) · z Archiv zeigen · / filtern nach Titel · Esc/Tab zu.
# Filtern startet mit '/', weil r, a, n, z sonst zugleich Befehl und
# Suchbuchstabe wären.
#
# Reine Helfer (alter_text, filtern, listen_zeilen) sind ohne curses und ohne
# HTTP testbar (tests/test_gespraechsliste.py).

import curses
import urllib.error
from datetime import datetime, timezone

from . import eingabe
from .basis import api_call

ERINNERUNGEN = "erinnerungen"       # dieselbe id wie core/gespraeche.py


# ── Reine Helfer ─────────────────────────────────────────────────────────

def alter_text(ts, jetzt=None):
    """'vor 2 Std.' & Co. aus einem UTC-ISO-Zeitstempel. Müll → ''."""
    try:
        dann = datetime.fromisoformat(str(ts))
        if dann.tzinfo is None:
            dann = dann.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return ""
    jetzt = jetzt or datetime.now(timezone.utc)
    s = (jetzt - dann).total_seconds()
    if s < 60:
        return "gerade"
    if s < 3600:
        return "vor %d Min." % (s // 60)
    if s < 86400:
        return "vor %d Std." % (s // 3600)
    if s < 2 * 86400:
        return "gestern"
    if s < 7 * 86400:
        return "vor %d Tagen" % (s // 86400)
    lokal = dann.astimezone()
    if lokal.year == jetzt.astimezone().year:
        return lokal.strftime("%d.%m.")
    return lokal.strftime("%d.%m.%y")


def filtern(eintraege, suche):
    """Einträge, deren Titel alle Wörter der Suche enthält (Groß/klein egal)."""
    woerter = (suche or "").lower().split()
    if not woerter:
        return list(eintraege)
    return [e for e in eintraege
            if all(w in str(e.get("titel") or "").lower() for w in woerter)]


def listen_zeilen(eintraege, idx, breite, jetzt=None, aktiv=None):
    """Die Liste als Zeilen. -> [(text, art)], art: "gewaehlt" | "ungelesen" |
    "normal". Links Zeiger und ●, rechts das Alter; der Titel wird gekürzt."""
    raus = []
    for i, e in enumerate(eintraege):
        zeiger = "›" if i == idx else " "
        punkt = "●" if e.get("ungelesen") else ("·" if e.get("id") == aktiv else " ")
        alter = alter_text(e.get("letzte"), jetzt)
        platz = max(1, breite - 4 - len(alter) - 1)
        titel = str(e.get("titel") or "neues gespräch").replace("\n", " ")
        if len(titel) > platz:
            titel = titel[:max(1, platz - 1)] + "…"
        text = "%s %s %s" % (zeiger, punkt, titel.ljust(platz))
        text = (text + " " + alter)[:breite]
        art = "gewaehlt" if i == idx else ("ungelesen" if e.get("ungelesen") else "normal")
        raus.append((text, art))
    return raus


# ── Die Überlagerung ─────────────────────────────────────────────────────

class Gespraechsliste:
    """Zustand liegt in chat.AI["liste"] (None = zu):
    {eintraege, idx, suche, suchen, umbenennen, archiv, aktiv}."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI

    # ── Daten ──────────────────────────────────────────────────────────
    def holen(self, archiv=False):
        """GET /api/gespraeche → (eintraege, aktiv) oder None."""
        try:
            d = api_call("/api/gespraeche" + ("?archiv=1" if archiv else ""))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        return [e for e in d.get("gespraeche") or [] if isinstance(e, dict)], d.get("aktiv")

    def oeffnen(self, archiv=False):
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst danach wechseln (esc stoppt)"
            return
        d = self.holen(archiv)
        if d is None:
            AI["msg"] = "keine verbindung — liste nicht geladen"
            return
        eintraege, aktiv = d
        idx = next((i for i, e in enumerate(eintraege) if e.get("id") == AI.get("gid")), 0)
        AI["liste"] = {"eintraege": eintraege, "idx": idx, "suche": "", "suchen": False,
                       "umbenennen": None, "archiv": archiv, "aktiv": aktiv}
        AI["msg"] = ""

    def schliessen(self):
        self.AI["liste"] = None

    def sichtbar(self):
        L = self.AI["liste"]
        return filtern(L["eintraege"], L["suche"])

    def gewaehlt(self):
        L, s = self.AI["liste"], self.sichtbar()
        if not s:
            return None
        L["idx"] = max(0, min(L["idx"], len(s) - 1))
        return s[L["idx"]]

    # ── Tasten ─────────────────────────────────────────────────────────
    def taste(self, ch):
        L = self.AI["liste"]
        if L["umbenennen"] is not None:
            self._taste_umbenennen(ch)
            return
        if L["suchen"]:
            self._taste_suchen(ch)
            return
        n = len(self.sichtbar())
        if ch in (27, 9):                                  # Esc, Tab
            self.schliessen()
        elif ch == curses.KEY_UP and n:
            L["idx"] = (L["idx"] - 1) % n
        elif ch == curses.KEY_DOWN and n:
            L["idx"] = (L["idx"] + 1) % n
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE) and n:
            L["idx"] = max(0, min(n - 1, L["idx"] + (-5 if ch == curses.KEY_PPAGE else 5)))
        elif ch in (10, 13, curses.KEY_ENTER):
            e = self.gewaehlt()
            if e:
                self.schliessen()
                self.chat.gespraech_oeffnen(e["id"])
        elif ch == ord("/"):
            L["suchen"] = True
        elif ch == ord("n"):
            self.schliessen()
            self.chat.neues_gespraech()
        elif ch == ord("z"):
            self.oeffnen(archiv=not L["archiv"])
        elif ch == ord("r"):
            e = self.gewaehlt()
            if e and e["id"] == ERINNERUNGEN:
                self.AI["msg"] = "„erinnerungen“ behält seinen namen"
            elif e:
                t = str(e.get("titel") or "")
                L["umbenennen"] = {"text": t, "cur": len(t), "u8": b""}
        elif ch == ord("a"):
            self._archivieren()

    def _taste_suchen(self, ch):
        L = self.AI["liste"]
        if ch == 27:
            L["suche"], L["suchen"] = "", False
        elif ch in (10, 13, curses.KEY_ENTER, curses.KEY_DOWN, curses.KEY_UP):
            L["suchen"] = False
        else:
            L["suche"], _cur, L["u8_suche"] = self._tippen(
                L["suche"], len(L["suche"]), L.get("u8_suche", b""), ch)
            L["idx"] = 0

    def _taste_umbenennen(self, ch):
        L = self.AI["liste"]
        u = L["umbenennen"]
        if ch == 27:
            L["umbenennen"] = None
        elif ch in (10, 13, curses.KEY_ENTER):
            e = self.gewaehlt()
            L["umbenennen"] = None
            if e and u["text"].strip():
                self.chat.titel_setzen(e["id"], u["text"])
                self.oeffnen(L["archiv"])
        else:
            u["text"], u["cur"], u["u8"] = self._tippen(u["text"], u["cur"], u["u8"], ch)

    @staticmethod
    def _tippen(text, pos, u8, ch):
        """Eine Taste in einem einzeiligen Feld (Umlaute als UTF-8-Bytes)."""
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            text, pos = eingabe.zurueck(text, pos)
        elif ch == curses.KEY_LEFT:
            text, pos = eingabe.links(text, pos)
        elif ch == curses.KEY_RIGHT:
            text, pos = eingabe.rechts(text, pos)
        elif isinstance(ch, int) and 32 <= ch <= 126:
            text, pos = eingabe.einfuegen(text, pos, chr(ch), grenze=120)
        elif isinstance(ch, int) and 128 <= ch <= 255:
            u8, z = eingabe.utf8_byte(u8, ch)
            if z is not None and eingabe.druckbar(z):
                text, pos = eingabe.einfuegen(text, pos, z, grenze=120)
        return text, pos, u8

    def _archivieren(self):
        AI, L = self.AI, self.AI["liste"]
        e = self.gewaehlt()
        if not e:
            return
        if e["id"] == ERINNERUNGEN:
            AI["msg"] = "„erinnerungen“ bleibt in der liste"
            return
        an = not L["archiv"]
        try:
            api_call("/api/gespraeche/%s/archiv" % e["id"], "POST", {"an": an})
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht archiviert"
            return
        if an and e["id"] == AI.get("gid"):
            self.chat.leeren()              # das offene Gespräch ist jetzt im Archiv
        self.oeffnen(L["archiv"])
        AI["msg"] = ("archiviert — z zeigt das archiv" if an else "zurückgeholt")

    # ── Zeichnen ───────────────────────────────────────────────────────
    def zeichnen(self, by, bx, bh, bw):
        z = self.chat.z
        C, addclip = z.C, z.addclip
        L = self.AI["liste"]
        inx, inw = bx + 2, max(6, bw - 4)
        kopf = "archiv" if L["archiv"] else "gespräche"
        if L["suche"] or L["suchen"]:
            kopf += "  · suche: " + L["suche"] + ("▌" if L["suchen"] else "")
        addclip(by + 1, inx, kopf, inw, C["acc"])

        if L["umbenennen"] is not None:
            fuss = ["neuer titel: " + L["umbenennen"]["text"] + "▌",
                    "enter speichern · esc abbrechen"]
        elif L["suchen"]:
            fuss = ["tippen sucht im titel · enter fertig · esc suche weg"]
        else:
            fuss = ["↑↓ wählen · enter öffnen · n neu · r umbenennen · "
                    + ("a zurückholen" if L["archiv"] else "a archivieren")
                    + " · z " + ("zurück" if L["archiv"] else "archiv")
                    + " · / suchen · esc zu"]
        msg = self.AI.get("msg")
        if msg:
            fuss = [msg] + fuss
        # Lange Hinweise umbrechen statt abschneiden (schmale Fenster).
        zeilen_fuss = []
        for f in fuss:
            zeilen_fuss += [f[i:i + inw] for i in range(0, len(f), inw)] or [""]
        oben, unten = by + 3, by + bh - 2 - len(zeilen_fuss)
        platz = max(1, unten - oben + 1)

        s = self.sichtbar()
        if not s:
            leer = "keine treffer" if L["suche"] else (
                "archiv ist leer" if L["archiv"] else "noch keine gespräche — n beginnt eins")
            addclip(oben, inx, leer, inw, C["faint"])
        else:
            idx = max(0, min(L["idx"], len(s) - 1))
            start = max(0, min(idx - platz // 2, len(s) - platz))
            stile = {"gewaehlt": C["bright"] | curses.A_BOLD, "ungelesen": C["acc"],
                     "normal": C["dim"]}
            for i, (text, art) in enumerate(listen_zeilen(s, idx, inw, aktiv=self.AI.get("gid"))
                                            [start:start + platz]):
                addclip(oben + i, inx, text, inw, stile[art])
        y = by + bh - 1 - len(zeilen_fuss)
        for i, f in enumerate(zeilen_fuss):
            addclip(y + i, inx, f, inw, C["warn"] if (msg and i == 0) else C["faint"])
