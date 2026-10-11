# tui/ansichten/seitenleiste.py
#
# Die Seitenleiste des Chats wie bei Claude Web (2026-10-07): oben Search,
# New, Projects, Files, Customize — je mit Symbol (symbole.py: seit
# 08.10.2026 Braille-Punkte, 4 Felder breit und 2 Zeilen hoch) —, darunter die Gespräche, gruppiert nach Today / Yesterday /
# Datum, ● bei Ungelesenem, ▤ bei einem Gespräch mit Dokument,
# Projektname leise davor. Zugeklappt bleibt eine Spalte Symbole.
#
# Sasha, 07.10.2026: „tab für gespräche auf und zu klappen find ich still
# good." Tab (bei leerer Eingabe) klappt auf und gibt der Leiste den Fokus,
# Tab klappt wieder zu. Esc gibt den Fokus an die Eingabe zurück und lässt
# die Leiste offen.
#
# Die Gespräche selbst (wählen, suchen, umbenennen, archivieren) macht
# weiter gespraechsliste.Gespraechsliste mit ihrem Zustand AI["liste"] —
# hier liegt nur, was die Leiste dazu bringt: das Menü oben, die Gruppen,
# das Zeichnen in einer Spalte, die Mausflächen.

import curses
import urllib.error
from datetime import datetime, timedelta, timezone

from . import symbole
from .basis import api_call
from .chat_layout import LEISTE
from .chat_teil import ChatTeil, tabelle
from .symbole import DOKU

# (Symbol, Beschriftung, Aktion) — die Reihenfolge von Claude Web.
MENUE = [("search", "Search", "suchen"), ("new", "New", "neu"),
         ("projects", "Projects", "projekte"), ("files", "Files", "ablage"),
         ("customize", "Customize", "einstellungen")]
MONATE = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct",
          "Nov", "Dec")


# ── Reine Helfer ─────────────────────────────────────────────────────────

def gruppe(ts, jetzt=None):
    """Überschrift für einen Zeitstempel: Today, Yesterday, sonst „Oct 5"
    (mit Jahr, wenn nicht dieses). Müll → „Older"."""
    try:
        dann = datetime.fromisoformat(str(ts))
        if dann.tzinfo is None:
            dann = dann.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return "Older"
    jetzt = (jetzt or datetime.now(timezone.utc)).astimezone()
    tag = dann.astimezone().date()
    if tag == jetzt.date():
        return "Today"
    if tag == jetzt.date() - timedelta(days=1):
        return "Yesterday"
    text = "%s %d" % (MONATE[tag.month - 1], tag.day)
    return text if tag.year == jetzt.year else "%s %d" % (text, tag.year)


def zeilen(eintraege, breite, jetzt=None, aktiv=None, mit_doku=frozenset()):
    """Die Gespräche als Zeilen der Leiste. -> [(art, index, text)],
    art "kopf" (Gruppe, index None) | "chat" (index in eintraege). Der Titel
    gibt nach, ● und das Blatt bleiben."""
    raus, letzte = [], None
    for i, e in enumerate(eintraege):
        g = gruppe(e.get("letzte"), jetzt)
        if g != letzte:
            if raus:
                raus.append(("luft", None, ""))
            raus.append(("kopf", None, g))
            letzte = g
        punkt = "●" if e.get("ungelesen") else ("…" if e.get("laeuft") else " ")
        doku = " " + DOKU if e.get("id") in mit_doku else ""
        titel = " ".join(str(e.get("titel") or "new chat").split())
        if e.get("projekt_name"):
            titel = "%s · %s" % (e["projekt_name"], titel)
        platz = max(1, breite - 2 - len(doku))
        if len(titel) > platz:
            titel = titel[:max(1, platz - 1)] + "…"
        raus.append(("chat", i, "%s %s%s" % (punkt, titel.ljust(platz), doku)))
    return raus


# ── Die Leiste ───────────────────────────────────────────────────────────

class Seitenleiste(ChatTeil):
    """Zustand: AI["seite"] (None = von selbst, True/False = von Hand),
    AI["seite_menu"] (None = Cursor bei den Gesprächen, sonst Menü-Index),
    AI["mit_doku"] (ids der Gespräche mit Dokument). Die Gespräche: AI["liste"]
    (gespraechsliste.py), solange die Leiste offen ist.

    Tasten: Tastentabelle TASTEN, im Chat „seite:menue"."""

    TASTEN = tabelle({"menue": [
        ("↑↓", "menue_waehlen", "select"), ("enter", "menue_oeffnen", "open"),
        ("tab", "zuklappen", "hide chats"), ("esc", "zurueck", "back to reply"),
        ("f6", "fokus_weiter", "next pane")]})

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        self.AI.setdefault("seite", None)
        self.AI.setdefault("seite_menu", None)
        self.AI.setdefault("mit_doku", frozenset())

    # ── auf/zu ─────────────────────────────────────────────────────────
    def offen(self, bw):
        from .chat_layout import seite_auto
        s = self.AI.get("seite")
        return seite_auto(bw) if s is None else bool(s)

    def aufklappen(self, fokus=True):
        AI = self.AI
        AI["seite"] = True
        if fokus:
            self.fokus()

    def zuklappen(self):
        AI = self.AI
        AI["seite"] = False
        AI["liste"] = None
        if AI.get("fokus") == "seite":
            AI["fokus"] = "eingabe"

    def fokus(self):
        """Fokus in die Leiste: Gespräche frisch holen (und welche ein
        Dokument haben)."""
        AI = self.AI
        AI["fokus"] = "seite"
        if AI.get("liste") is None:
            self.chat.liste.oeffnen(AI.get("liste_archiv", False))
        if AI.get("liste") is None and AI.get("seite_menu") is None:
            AI["seite_menu"] = 0             # während einer Antwort: nur das Menü
        self.doku_holen()

    def doku_holen(self):
        """Welche Gespräche ein Dokument haben (Blatt-Zeichen). Scheitert still."""
        try:
            d = api_call("/api/ablage")
        except (urllib.error.URLError, OSError, ValueError):
            return
        if isinstance(d, dict):
            self.AI["mit_doku"] = frozenset(
                str(k.get("gespraech")) for k in d.get("dokumente") or []
                if isinstance(k, dict) and k.get("gespraech"))

    def eintraege(self):
        """Was die Leiste zeigt: die offene Liste (gefiltert) oder, solange
        sie nicht geladen ist, die Gespräche aus dem letzten Poll."""
        if self.AI.get("liste"):
            return self.chat.markiert(self.chat.liste.sichtbar())
        return self.chat.markiert(list(self.AI.get("gespraeche") or []))

    # ── Menü ───────────────────────────────────────────────────────────
    def menue(self, aktion):
        """Ein Eintrag oben (Klick, Enter, Symbol in der zugeklappten Spalte)."""
        AI, chat = self.AI, self.chat
        if aktion == "suchen":
            self.aufklappen()
            if AI.get("liste"):
                AI["liste"]["suchen"] = True
                AI["seite_menu"] = None
        elif aktion == "neu":
            chat.neues_gespraech()
            AI["fokus"] = "eingabe"
        elif aktion == "projekte":
            chat.projekte.oeffnen()
        elif aktion == "ablage":
            chat.ablageliste.oeffnen()
        elif aktion == "einstellungen":
            chat.einstellungen.oeffnen()
        if aktion in ("projekte", "ablage", "einstellungen") and AI.get("seite_voll"):
            self.zuklappen()                 # schmal: die Leiste deckte alles

    def chat_oeffnen(self, idx):
        """Klick auf ein Gespräch."""
        AI = self.AI
        s = self.eintraege()
        if not 0 <= idx < len(s):
            return
        if AI.get("liste"):
            AI["liste"]["idx"] = idx
        gid = s[idx].get("id")
        self.chat.gespraech_oeffnen(gid)
        AI["liste"] = None
        AI["fokus"] = "eingabe"
        if AI.get("seite_voll"):
            AI["seite"] = False

    # ── Tasten (Tastentabelle, im Chat unter „seite:…") ────────────────
    # Nur das Menü oben; die Gespräche darunter nimmt die Gesprächsliste
    # (gespraechsliste.py, „liste:…"). Welche gerade gilt, sagt Chat.ansicht.
    def menue_offen(self):
        """Cursor im Menü — auch solange die Gespräche noch nicht geladen
        sind (dann landet die erste Taste im Menü)."""
        return self.AI.get("seite_menu") is not None or not self.AI.get("liste")

    def ansicht(self):
        return "menue"

    def aktion_menue_waehlen(self, taste):
        AI, L = self.AI, self.AI.get("liste")
        m = AI.get("seite_menu")
        if m is None:
            AI["seite_menu"] = len(MENUE) - 1
        elif taste == "up":
            AI["seite_menu"] = max(0, m - 1)
        elif m + 1 < len(MENUE):
            AI["seite_menu"] = m + 1
        elif L and self.eintraege():
            AI["seite_menu"] = None              # unter dem Menü: die Gespräche
            L["idx"] = 0

    def aktion_menue_oeffnen(self, _t):
        m = self.AI.get("seite_menu")
        if m is None:
            self.AI["seite_menu"] = len(MENUE) - 1
        else:
            self.menue(MENUE[m][2])

    def aktion_zuklappen(self, _t):
        self.zuklappen()

    def aktion_zurueck(self, _t):
        self.AI["fokus"] = "eingabe"

    # ── Zeichnen ───────────────────────────────────────────────────────
    def _symbol(self, y, x, name, an, unten):
        """Ein Symbol ab (y, x); Zeilen ab `unten` werden nicht gemalt. Mit
        Farben in Grund/Akzent (symbole.FARBEN); ohne Farben oder im
        Halbblock-Modus (ZENTRALE_PIXEL=half) dieselben Punkte in der
        Schriftfarbe der Leiste — Braille kann jedes Terminal."""
        z = self.chat.z
        farbig = z.C.get("pix_bg") is not None and getattr(z, "PIX_MODUS", "mix") != "half"
        thema = "nacht" if sum(z.C.get("pix_bg") or (0, 0, 0)) < 384 else "tag"
        schlicht = (z.C["bright"] | curses.A_BOLD) if an else z.C["dim"]
        for r, zeile in enumerate(symbole.symbol_zellen(name, thema, an)):
            if y + r >= unten:
                break
            for i, (zeichen, fg, bg) in enumerate(zeile):
                z.safe_addstr(y + r, x + i, zeichen, z.pix_attr(fg, bg) if farbig else schlicht)

    def _klickbar(self, y, hoehe, x, w, aktion, unten):
        for r in range(hoehe):
            if y + r < unten:
                self.chat.klickbar(y + r, x, w, aktion)

    def zeichnen_leiste(self, top, x, h):
        """Zugeklappt: eine Spalte Symbole, jedes anklickbar."""
        chat, AI = self.chat, self.AI
        sb, sh = symbole.BREITE, symbole.HOEHE
        lw = LEISTE
        sx, unten = x + (lw - sb) // 2, top + h
        self._symbol(top, sx, "seite", False, unten)
        self._klickbar(top, sh, x, lw, lambda: self.aufklappen(), unten)
        y = top + sh + 1
        for name, _text, aktion in MENUE:
            if y >= unten:
                break
            self._symbol(y, sx, name, False, unten)
            self._klickbar(y, sh, x, lw, lambda a=aktion: self.menue(a), unten)
            y += sh
        if any(e.get("ungelesen") for e in self.eintraege()) and y + 1 < unten:
            chat.z.safe_addstr(y + 1, x + lw // 2, "●", chat.z.C["acc"])

    def zeichnen(self, top, x, h, w):
        """Offen: Menü, Gespräche nach Tagen."""
        chat, AI = self.chat, self.AI
        C, addclip = chat.z.C, chat.z.addclip
        hat_fokus = AI.get("fokus") == "seite"
        L = AI.get("liste")
        m = AI.get("seite_menu") if hat_fokus else None
        sb, sh = symbole.BREITE, symbole.HOEHE
        unten = top + h
        y = top
        for k, (name, text, aktion) in enumerate(MENUE):
            if y >= unten:
                return
            an = m == k
            if aktion == "suchen" and L and (L.get("suchen") or L.get("suche")):
                text = "search: " + L["suche"] + ("▌" if L.get("suchen") else "")
            self._symbol(y, x + 1, name, an, unten)
            # Beschriftung auf der oberen Zeile, wie bei Claude Web oben bündig.
            addclip(y, x + 2 + sb, text, w - 3 - sb,
                    (C["bright"] | curses.A_REVERSE) if an else C["dim"])
            self._klickbar(y, sh, x, w, lambda a=aktion: self.menue(a), unten)
            y += sh
        oben = y + 1
        if L and L.get("archiv"):
            addclip(oben, x + 1, "Archive", w - 2, C["acc"])
            oben += 1
        s = self.eintraege()
        reihen = zeilen(s, w - 2, aktiv=AI.get("gid"), mit_doku=AI.get("mit_doku") or frozenset())
        platz = max(1, top + h - oben)
        idx = L["idx"] if (L and m is None) else -1
        if not s:
            addclip(oben, x + 1, "no chats yet" if not (L and L.get("suche")) else "nothing found",
                    w - 2, C["faint"])
            return
        # die gewählte Zeile sichtbar halten
        pos = next((r for r, (art, i, _t) in enumerate(reihen) if art == "chat" and i == idx), 0)
        start = max(0, min(pos - platz // 2, len(reihen) - platz))
        umb = (L or {}).get("umbenennen")
        for r, (art, i, text) in enumerate(reihen[start:start + platz]):
            y = oben + r
            if art == "kopf":
                addclip(y, x + 1, text, w - 2, C["faint"])
                continue
            if art != "chat":
                continue
            e = s[i]
            if i == idx and umb is not None:
                text = "  " + umb["text"] + "▌"
            gewaehlt = hat_fokus and i == idx
            if gewaehlt:
                attr = C["bright"] | curses.A_REVERSE
            elif e.get("id") == AI.get("gid"):
                attr = C["bright"] | curses.A_BOLD
            else:
                attr = C["acc"] if e.get("ungelesen") else C["dim"]
            addclip(y, x + 1, text, w - 2, attr)
            chat.klickbar(y, x, w, lambda i=i: self.chat_oeffnen(i))
