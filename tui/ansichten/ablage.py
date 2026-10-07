# tui/ansichten/ablage.py
#
# Die Ablage im KI-Chat (Claude-Web-Plan Phase 5, 2026-10-07): Dokumente,
# die die KI angelegt hat, Dateien aus der Sandbox und Anhänge. Wie die
# Gesprächsliste eine Überlagerung IM Chat-Kasten (gespraechsliste.py): auf
# 80×24 ist neben dem Verlauf kein Platz für eine zweite Spalte.
#
# Zwei Zustände: die LISTE (/ablage) und das LESEN eines Dokuments —
# bildschirmfüllend im Kasten, gezeichnet mit demselben Markdown wie die
# Antworten (text.md_zeilen), wie Post und Notizen es auch im Kasten tun.
# Kein externer Pager: die TUI müsste dafür curses verlassen und neu
# aufbauen, und auf dem Pi-Kiosk gibt es kein less hinter dem Bild. Esc führt
# immer eine Stufe zurück.
#
# Tasten Liste: ↑↓ Bild↑↓ wählen · Enter lesen · a archivieren (im Archiv:
# zurückholen) · z Archiv · Esc zu.  Lesen: ↑↓ Bild↑↓ Pos1 Ende blättern ·
# ←→ ältere/neuere Fassung · Esc zurück.
#
# Reine Helfer (listen_zeilen, lese_zeilen) sind ohne curses testbar
# (tests/test_ablage_tui.py).

import curses
import urllib.error
import urllib.parse

from .basis import api_call
from .gespraechsliste import alter_text
from .text import md_zeilen

ART_KURZ = {"markdown": "text", "text": "text", "code": "code", "csv": "tabelle",
            "bild": "bild"}
HERKUNFT_KURZ = {"ki": "", "sandbox": "aus code", "anhang": "anhang"}


# ── Reine Helfer ─────────────────────────────────────────────────────────

def listen_zeilen(eintraege, idx, breite, jetzt=None):
    """Die Liste als Zeilen. -> [(text, art)], art "gewaehlt" | "normal".
    Links Titel, rechts Art · Alter; darunter (eingerückt) das Gespräch,
    wenn Platz ist — der Titel gibt zuerst nach."""
    raus = []
    for i, e in enumerate(eintraege):
        zeiger = "›" if i == idx else " "
        art = ART_KURZ.get(e.get("art"), e.get("art") or "")
        herkunft = HERKUNFT_KURZ.get(e.get("herkunft"), "")
        rechts = " · ".join(t for t in (herkunft or art, alter_text(e.get("geaendert"), jetzt)) if t)
        gespraech = str(e.get("gespraech_titel") or "").replace("\n", " ")
        platz = max(1, breite - 2 - len(rechts) - 1)
        titel = str(e.get("titel") or "ohne titel").replace("\n", " ")
        if (e.get("fassung") or 1) > 1:
            titel += " (v%d)" % e["fassung"]
        if gespraech and breite >= 60:
            titel += " — " + gespraech
        if len(titel) > platz:
            titel = titel[:max(1, platz - 1)] + "…"
        text = ("%s %s %s" % (zeiger, titel.ljust(platz), rechts))[:breite]
        raus.append((text, "gewaehlt" if i == idx else "normal"))
    return raus


def lese_zeilen(dok, breite):
    """Ein Dokument (GET /api/ablage/<id>) als Zeilen. -> [(text, stil)],
    stil "" | "kopf" | "code" | "liste" (wie md_zeilen) | "leise"."""
    kopf = dok.get("kopf") or {}
    art = kopf.get("art")
    if art == "bild" or dok.get("inhalt") is None:
        groesse = int(dok.get("bytes") or 0)
        zeilen = ["ein bild (%d kb) — im terminal nicht zu zeigen." % max(1, groesse // 1024),
                  "es liegt hier:", str(dok.get("pfad") or "?")]
        raus = []
        for z in zeilen:
            raus += [(z[i:i + breite], "leise") for i in range(0, len(z), max(1, breite))] or [("", "")]
        return raus
    text = str(dok.get("inhalt") or "")
    if art == "markdown":
        return [(z, stil or "") for z, stil in md_zeilen(text, max(6, breite))]
    # Code, CSV, Text: wörtlich, nur hart umbrochen (Einrückung zählt).
    raus = []
    stil = "code" if art in ("code", "csv") else ""
    for zeile in text.expandtabs(4).split("\n"):
        if not zeile:
            raus.append(("", stil))
        for i in range(0, len(zeile), max(1, breite)):
            raus.append((zeile[i:i + breite], stil))
    return raus


# ── Die Überlagerung ─────────────────────────────────────────────────────

class Ablageliste:
    """Zustand in chat.AI["ablage"] (None = zu):
    {eintraege, idx, archiv, lesen: None | {dok, scroll, fassung},
     direkt: True, wenn aus dem Chat heraus gelesen wird (Esc → Chat)}."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI

    # ── Daten ──────────────────────────────────────────────────────────
    def holen(self, archiv=False):
        try:
            d = api_call("/api/ablage" + ("?archiv=1" if archiv else ""))
        except (urllib.error.URLError, OSError, ValueError):
            return None
        if not isinstance(d, dict):
            return None
        return [e for e in d.get("dokumente") or [] if isinstance(e, dict)]

    def oeffnen(self, archiv=False):
        AI = self.AI
        eintraege = self.holen(archiv)
        if eintraege is None:
            AI["msg"] = "keine verbindung — ablage nicht geladen"
            return
        AI["ablage"] = {"eintraege": eintraege, "idx": 0, "archiv": archiv,
                        "lesen": None, "direkt": False}
        AI["msg"] = ""

    def lesen(self, doc_id, fassung=None, direkt=False):
        """Ein Dokument zum Lesen öffnen (aus der Liste oder direkt aus dem
        Chat: Enter auf dem letzten „▤")."""
        AI = self.AI
        pfad = "/api/ablage/" + urllib.parse.quote(str(doc_id), safe="")
        if fassung:
            pfad += "?fassung=%d" % int(fassung)
        try:
            dok = api_call(pfad, timeout=10)
        except urllib.error.HTTPError:
            AI["msg"] = "das dokument gibt es nicht (mehr)"
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — dokument nicht geladen"
            return
        if not isinstance(dok, dict):
            return
        if AI.get("ablage") is None:
            AI["ablage"] = {"eintraege": [], "idx": 0, "archiv": False,
                            "lesen": None, "direkt": direkt}
        AI["ablage"]["lesen"] = {"dok": dok, "scroll": 0,
                                 "fassung": dok.get("fassung") or 1}
        AI["msg"] = ""

    def schliessen(self):
        self.AI["ablage"] = None

    def gewaehlt(self):
        A = self.AI["ablage"]
        if not A["eintraege"]:
            return None
        A["idx"] = max(0, min(A["idx"], len(A["eintraege"]) - 1))
        return A["eintraege"][A["idx"]]

    # ── Tasten ─────────────────────────────────────────────────────────
    def taste(self, ch):
        A = self.AI["ablage"]
        if A["lesen"] is not None:
            self._taste_lesen(ch)
            return
        n = len(A["eintraege"])
        if ch == 27:
            self.schliessen()
        elif ch == curses.KEY_UP and n:
            A["idx"] = (A["idx"] - 1) % n
        elif ch == curses.KEY_DOWN and n:
            A["idx"] = (A["idx"] + 1) % n
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE) and n:
            A["idx"] = max(0, min(n - 1, A["idx"] + (-5 if ch == curses.KEY_PPAGE else 5)))
        elif ch in (10, 13, curses.KEY_ENTER):
            e = self.gewaehlt()
            if e:
                self.lesen(e["id"])
        elif ch == ord("z"):
            self.oeffnen(archiv=not A["archiv"])
        elif ch == ord("a"):
            self._archivieren()

    def _taste_lesen(self, ch):
        A = self.AI["ablage"]
        L = A["lesen"]
        seite = max(1, getattr(self, "_seite", 10))
        if ch == 27:
            if A.get("direkt"):
                self.schliessen()
            else:
                A["lesen"] = None
        elif ch == curses.KEY_UP:
            L["scroll"] = max(0, L["scroll"] - 1)
        elif ch == curses.KEY_DOWN:
            L["scroll"] += 1
        elif ch == curses.KEY_PPAGE:
            L["scroll"] = max(0, L["scroll"] - seite)
        elif ch in (curses.KEY_NPAGE, 32):
            L["scroll"] += seite
        elif ch in (curses.KEY_HOME, curses.KEY_FIND):
            L["scroll"] = 0
        elif ch in (curses.KEY_END, curses.KEY_SELECT):
            L["scroll"] = 10 ** 6            # zeichnen() setzt es aufs Ende
        elif ch in (curses.KEY_LEFT, curses.KEY_RIGHT):
            kopf = L["dok"].get("kopf") or {}
            neu = L["fassung"] + (-1 if ch == curses.KEY_LEFT else 1)
            if 1 <= neu <= int(kopf.get("fassung") or 1):
                self.lesen(kopf.get("id"), neu, direkt=A.get("direkt"))
            else:
                self.AI["msg"] = ("das ist die erste fassung" if neu < 1
                                  else "das ist die neueste fassung")

    def _archivieren(self):
        AI, A = self.AI, self.AI["ablage"]
        e = self.gewaehlt()
        if not e:
            return
        an = not A["archiv"]
        try:
            api_call("/api/ablage/%s/archiv" % urllib.parse.quote(e["id"], safe=""),
                     "POST", {"an": an})
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht archiviert"
            return
        idx = A["idx"]
        self.oeffnen(A["archiv"])
        if AI.get("ablage"):
            AI["ablage"]["idx"] = idx
        AI["msg"] = "archiviert — z zeigt das archiv" if an else "zurückgeholt"

    # ── Zeichnen ───────────────────────────────────────────────────────
    def zeichnen(self, by, bx, bh, bw):
        A = self.AI["ablage"]
        if A["lesen"] is not None:
            self._zeichnen_lesen(by, bx, bh, bw)
        else:
            self._zeichnen_liste(by, bx, bh, bw)

    def _fuss(self, texte, inw):
        msg = self.AI.get("msg")
        if msg:
            texte = [msg] + texte
        zeilen = []
        for f in texte:
            zeilen += [f[i:i + inw] for i in range(0, len(f), inw)] or [""]
        return zeilen, bool(msg)

    def _zeichnen_liste(self, by, bx, bh, bw):
        z = self.chat.z
        C, addclip = z.C, z.addclip
        A = self.AI["ablage"]
        inx, inw = bx + 2, max(6, bw - 4)
        addclip(by + 1, inx, "ablage · archiv" if A["archiv"] else "ablage", inw, C["acc"])
        fuss, mit_msg = self._fuss(
            ["↑↓ wählen · enter lesen · " + ("a zurückholen" if A["archiv"] else "a archivieren")
             + " · z " + ("zurück" if A["archiv"] else "archiv") + " · esc zu"], inw)
        oben, unten = by + 3, by + bh - 2 - len(fuss)
        platz = max(1, unten - oben + 1)
        if not A["eintraege"]:
            addclip(oben, inx, "archiv ist leer" if A["archiv"] else
                    "noch nichts abgelegt — die ki legt hier dokumente ab, "
                    "/anhang <pfad> gibt ihr eine datei", inw, C["faint"])
        else:
            idx = max(0, min(A["idx"], len(A["eintraege"]) - 1))
            start = max(0, min(idx - platz // 2, len(A["eintraege"]) - platz))
            stile = {"gewaehlt": C["bright"] | curses.A_BOLD, "normal": C["dim"]}
            for i, (text, art) in enumerate(listen_zeilen(A["eintraege"], idx, inw)
                                            [start:start + platz]):
                addclip(oben + i, inx, text, inw, stile[art])
        y = by + bh - 1 - len(fuss)
        for i, f in enumerate(fuss):
            addclip(y + i, inx, f, inw, C["warn"] if (mit_msg and i == 0) else C["faint"])

    def _zeichnen_lesen(self, by, bx, bh, bw):
        z = self.chat.z
        C, addclip = z.C, z.addclip
        L = self.AI["ablage"]["lesen"]
        dok = L["dok"]
        kopf = dok.get("kopf") or {}
        inx, inw = bx + 2, max(6, bw - 4)
        n = int(kopf.get("fassung") or 1)
        titel = str(kopf.get("titel") or "")
        rechts = " · fassung %d/%d" % (L["fassung"], n) if n > 1 else ""
        addclip(by + 1, inx, (titel[:max(1, inw - len(rechts))] + rechts), inw, C["acc"])
        fuss, mit_msg = self._fuss(
            ["↑↓ bild↑↓ blättern" + (" · ←→ fassung" if n > 1 else "") + " · esc zurück"], inw)
        oben, unten = by + 3, by + bh - 2 - len(fuss)
        platz = max(1, unten - oben + 1)
        self._seite = max(1, platz - 1)
        zeilen = lese_zeilen(dok, inw)
        L["scroll"] = max(0, min(L["scroll"], max(0, len(zeilen) - platz)))
        stile = {"": C["bright"], "kopf": C["acc"], "code": C["dim"],
                 "liste": C["bright"], "leise": C["faint"]}
        for i, (text, stil) in enumerate(zeilen[L["scroll"]:L["scroll"] + platz]):
            addclip(oben + i, inx, text, inw, stile.get(stil, C["bright"]))
        if len(zeilen) > platz:
            stand = "%d–%d von %d" % (L["scroll"] + 1, min(len(zeilen), L["scroll"] + platz),
                                       len(zeilen))
            addclip(by + 2, inx + max(0, inw - len(stand)), stand, len(stand), C["faint"])
        y = by + bh - 1 - len(fuss)
        for i, f in enumerate(fuss):
            addclip(y + i, inx, f, inw, C["warn"] if (mit_msg and i == 0) else C["faint"])
