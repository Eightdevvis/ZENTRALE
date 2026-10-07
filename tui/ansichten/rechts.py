# tui/ansichten/rechts.py
#
# Die rechte Seite des Chats wie bei Claude Web (2026-10-07):
#   - DOKUMENT: ein Ablage-Dokument neben dem Verlauf (Titel ▾ für die
#     Fassungen, ⤢ groß = nimmt Mitte und rechts, × schließen). Der Zustand
#     ist der von ablage.Ablageliste (AI["ablage"] mit direkt=True und
#     „lesen") — Blättern und Fassungen macht weiter sie.
#   - OUTPUTS: Kärtchen der Dokumente dieses Gesprächs mit kurzer Vorschau,
#     darunter „Used in this session" (welche Werkzeuge, Skills, Gedächtnis —
#     aus den Schritten im Verlauf, verlauf.benutzt).
# Auf schmalen Schirmen ersetzt beides den Verlauf (chat_layout.aufteilen).

import curses
import threading
import urllib.error
import urllib.parse

from . import verlauf as V
from .ablage import lese_zeilen
from .basis import api_call
from .chat_ablage import TRENNER


def dokumente(log):
    """Die Dokumente dieses Gesprächs, neueste zuerst. -> [(id, titel)]"""
    raus, gesehen = [], set()
    for rolle, text in reversed(log):
        if rolle == "ablage":
            doc_id, _, titel = str(text).partition(TRENNER)
            if doc_id and doc_id not in gesehen:
                gesehen.add(doc_id)
                raus.append((doc_id, titel or "dokument"))
    return raus


def vorschau_zeilen(dok, breite, n=3):
    """Die ersten n Zeilen mit Inhalt eines Dokuments (für ein Kärtchen)."""
    raus = []
    for text, _stil in lese_zeilen(dok, max(6, breite)):
        if text.strip():
            raus.append(text[:breite])
        if len(raus) >= n:
            break
    return raus


class Rechts:
    """Zustand: AI["rechts"] None | "outputs" | "dokument", AI["gross"],
    AI["owahl"] (gewähltes Kärtchen), AI["vorschau"] {id: zeilen}."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        for k, v in (("rechts", None), ("gross", False), ("owahl", 0), ("vorschau", {})):
            self.AI.setdefault(k, v)

    # ── Was offen ist ──────────────────────────────────────────────────
    def dokument_offen(self):
        A = self.AI.get("ablage")
        return bool(A and A.get("direkt") and A.get("lesen"))

    def art(self):
        """Was rechts gerade steht: "dokument" | "outputs" | None."""
        if self.dokument_offen():
            return "dokument"
        return "outputs" if self.AI.get("rechts") == "outputs" else None

    def outputs_umschalten(self):
        AI = self.AI
        if AI.get("rechts") == "outputs" and not self.dokument_offen():
            AI["rechts"] = None
            if AI.get("fokus") == "rechts":
                AI["fokus"] = "eingabe"
            return
        if self.dokument_offen():
            self.chat.ablageliste.schliessen()
        AI["rechts"] = "outputs"
        AI["owahl"] = 0
        self.vorschau_holen()

    def vorschau_holen(self):
        """Die Kärtchen brauchen ein paar Zeilen je Dokument — im Hintergrund."""
        AI = self.AI
        fehlt = [d for d, _t in dokumente(AI["log"]) if d not in AI["vorschau"]]

        def los():
            for doc_id in fehlt:
                try:
                    dok = api_call("/api/ablage/" + urllib.parse.quote(doc_id, safe=""))
                except (urllib.error.URLError, OSError, ValueError):
                    dok = None
                with self.chat.AI_LOCK:
                    AI["vorschau"][doc_id] = vorschau_zeilen(dok, 40) if isinstance(dok, dict) \
                        else ["(nicht geladen)"]
        if fehlt:
            threading.Thread(target=los, daemon=True).start()

    def dokument_zeigen(self, doc_id):
        """Ein Dokument rechts öffnen (Kärtchen, ▤-Zeile im Verlauf)."""
        self.chat.ablageliste.lesen(doc_id, direkt=True)
        if self.dokument_offen():
            self.AI["fokus"] = "rechts"

    def schliessen(self):
        AI = self.AI
        if self.dokument_offen():
            self.chat.ablageliste.schliessen()
            AI["gross"] = False
        else:
            AI["rechts"] = None
        AI["fokus"] = "eingabe"

    def gross_umschalten(self):
        self.AI["gross"] = not self.AI.get("gross")

    def fassung_waehlen(self):
        """▾ am Titel: die Fassungen zur Auswahl (Fuß des Chats)."""
        A = self.AI.get("ablage") or {}
        L = A.get("lesen") or {}
        kopf = (L.get("dok") or {}).get("kopf") or {}
        n = int(kopf.get("fassung") or 1)
        if n <= 1:
            self.AI["msg"] = "dieses dokument hat nur eine fassung"
            return
        doc_id = kopf.get("id")
        optionen = [("fassung %d%s" % (k, " (neueste)" if k == n else ""), k)
                    for k in range(n, 0, -1)]
        self.AI["wahl"] = {"titel": "fassung wählen", "optionen": optionen,
                           "idx": n - int(L.get("fassung") or n),
                           "aktion": lambda k: self.chat.ablageliste.lesen(doc_id, k, direkt=True)}

    # ── Tasten ─────────────────────────────────────────────────────────
    def tasten(self):
        if self.art() == "dokument":
            A = self.AI["ablage"]
            kopf = A["lesen"]["dok"].get("kopf") or {}
            mehr = int(kopf.get("fassung") or 1) > 1
            return ([("↑↓", "scroll"), ("pgup pgdn", "page")]
                    + ([("←→", "versions"), ("v", "pick version")] if mehr else [])
                    + [("f", "normal size" if self.AI.get("gross") else "full size"),
                       ("esc", "close")])
        n = len(dokumente(self.AI["log"]))
        return (([("↑↓", "select")] if n > 1 else []) + ([("enter", "open")] if n else [])
                + [("esc", "back to reply"), ("ctrl+o", "hide outputs")])

    def taste(self, ch):
        AI = self.AI
        if self.art() == "dokument":
            if ch in (ord("f"), ord("F")):
                self.gross_umschalten()
            elif ch in (ord("v"), ord("V")):
                self.fassung_waehlen()
            elif ch == 27:
                self.schliessen()
            else:
                self.chat.ablageliste.taste(ch)
                if not self.dokument_offen():
                    AI["fokus"] = "eingabe"
            return
        docs = dokumente(AI["log"])
        if ch == 27:
            AI["fokus"] = "eingabe"
        elif ch == 15:                               # Strg+O
            self.outputs_umschalten()
        elif ch in (curses.KEY_UP, curses.KEY_DOWN) and docs:
            AI["owahl"] = (AI.get("owahl", 0) + (1 if ch == curses.KEY_DOWN else -1)) % len(docs)
        elif ch in (10, 13, curses.KEY_ENTER) and docs:
            self.dokument_zeigen(docs[min(AI.get("owahl", 0), len(docs) - 1)][0])

    # ── Zeichnen ───────────────────────────────────────────────────────
    def zeichnen(self, top, x, h, w):
        if self.art() == "dokument":
            self._dokument(top, x, h, w)
        else:
            self._outputs(top, x, h, w)

    def _dokument(self, top, x, h, w):
        chat, AI = self.chat, self.AI
        C, addclip = chat.z.C, chat.z.addclip
        L = AI["ablage"]["lesen"]
        dok = L["dok"]
        kopf = dok.get("kopf") or {}
        n = int(kopf.get("fassung") or 1)
        fokus = AI.get("fokus") == "rechts"
        # Kopf: Titel ▾ (Fassungen) …… ⤢ ×
        knoepfe = " ⤢  × "
        titel = str(kopf.get("titel") or "dokument")
        rest = (" ▾ v%d/%d" % (L["fassung"], n)) if n > 1 else ""
        tw = max(1, w - 2 - len(rest) - len(knoepfe))
        if len(titel) > tw:
            titel = titel[:max(1, tw - 1)] + "…"
        addclip(top, x + 1, titel, w - 2, C["acc"] | (curses.A_BOLD if fokus else 0))
        if rest:
            addclip(top, x + 1 + len(titel), rest, len(rest), C["dim"])
            chat.klickbar(top, x + 1 + len(titel), len(rest), self.fassung_waehlen)
        kx = x + w - len(knoepfe)
        addclip(top, kx, knoepfe, len(knoepfe), C["dim"])
        chat.klickbar(top, kx, 3, self.gross_umschalten)
        chat.klickbar(top, kx + 3, 3, self.schliessen)
        chat.klickbar(top, x, max(1, kx - x), lambda: chat.fokus_setzen("rechts"))
        addclip(top + 1, x + 1, "─" * (w - 2), w - 2, C["faint"])
        oben, platz = top + 2, max(1, h - 2)
        iw = max(6, min(w - 4, 100))
        ix = x + max(2, (w - iw) // 2)
        zeilen = lese_zeilen(dok, iw)
        chat.ablageliste._seite = max(1, platz - 1)
        L["scroll"] = max(0, min(L["scroll"], max(0, len(zeilen) - platz)))
        stile = {"": C["bright"], "kopf": C["acc"], "code": C["dim"],
                 "liste": C["bright"], "leise": C["faint"]}
        for i, (text, stil) in enumerate(zeilen[L["scroll"]:L["scroll"] + platz]):
            addclip(oben + i, ix, text, iw, stile.get(stil, C["bright"]))
        if len(zeilen) > platz:
            stand = "%d%%" % (100 * min(len(zeilen), L["scroll"] + platz) // len(zeilen))
            addclip(top + 1, x + w - len(stand) - 2, stand, len(stand), C["faint"])
        chat.rad_flaeche(oben, x, platz, w, "dokument")

    def _outputs(self, top, x, h, w):
        chat, AI = self.chat, self.AI
        C, addclip = chat.z.C, chat.z.addclip
        fokus = AI.get("fokus") == "rechts"
        addclip(top, x + 1, "Outputs", w - 5, C["acc"] | (curses.A_BOLD if fokus else 0))
        addclip(top, x + w - 3, "×", 1, C["dim"])
        chat.klickbar(top, x + w - 4, 3, self.outputs_umschalten)
        y = top + 2
        docs = dokumente(AI["log"])
        ende = top + h
        if not docs:
            addclip(y, x + 1, "no documents in this chat yet", w - 2, C["faint"])
            y += 2
        kw = max(8, w - 2)
        for k, (doc_id, titel) in enumerate(docs):
            vor = (AI.get("vorschau") or {}).get(doc_id) or ["…"]
            hoehe = 2 + len(vor[:3]) + 1
            if y + hoehe + 1 > ende:
                break
            gew = fokus and k == AI.get("owahl", 0)
            rahmen = (C["bright"] | curses.A_BOLD) if gew else C["faint"]
            addclip(y, x + 1, "┌" + "─" * (kw - 2) + "┐", kw, rahmen)
            for j, zeile in enumerate(vor[:3]):
                addclip(y + 1 + j, x + 1, "│", 1, rahmen)
                addclip(y + 1 + j, x + 3, zeile, kw - 4, C["dim"])
                addclip(y + 1 + j, x + kw, "│", 1, rahmen)
            addclip(y + hoehe - 2, x + 1, "└" + "─" * (kw - 2) + "┘", kw, rahmen)
            addclip(y + hoehe - 1, x + 1, titel, kw, C["bright"] if gew else C["dim"])
            for r in range(hoehe):
                chat.klickbar(y + r, x + 1, kw, lambda d=doc_id: self.dokument_zeigen(d))
            y += hoehe + 1
        if y + 2 >= ende:
            return
        addclip(y, x + 1, "─" * (w - 2), w - 2, C["faint"])
        addclip(y + 1, x + 1, "Used in this session", w - 2, C["acc"])
        y += 2
        benutzt = V.benutzt(AI["log"])
        if not benutzt:
            addclip(y, x + 1, "nothing yet", w - 2, C["faint"])
        for wort, anzahl, detail in benutzt:
            if y >= ende:
                break
            links = "%s%s" % (wort, " ×%d" % anzahl if anzahl > 1 else "")
            addclip(y, x + 1, links, w - 2, C["dim"])
            if detail and len(links) + 3 < w - 2:
                addclip(y, x + 3 + len(links), detail, w - 4 - len(links), C["faint"])
            y += 1
