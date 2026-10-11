# tui/ansichten/gespraechsliste.py
#
# Die Gesprächsliste im KI-Chat (Claude-Web-Plan Phase 2, 2026-10-07).
# Seit dem Umbau nach Claude Web (2026-10-07) steht sie in der Seitenleiste
# (seitenleiste.py zeichnet sie); hier liegen Zustand, Daten und Tasten.
# Geöffnet mit Tab (bei leerer Eingabe) oder /chats.
#
# Tasten (Tastentabelle Gespraechsliste.TASTEN, im Chat „liste:…"): ↑↓
# wählen (↑ über dem ersten: Menü der Leiste) · Enter öffnen · n neu ·
# r umbenennen · a archivieren (im Archiv: zurückholen) · z Archiv zeigen ·
# / filtern nach Titel · Tab Leiste zu · Esc zurück zur Eingabe.
# Filtern startet mit '/', weil r, a, n, z sonst zugleich Befehl und
# Suchbuchstabe wären.
#
# Reine Helfer (alter_text, filtern, listen_zeilen) sind ohne curses und ohne
# HTTP testbar (tests/test_gespraechsliste.py).

import urllib.error
from datetime import datetime, timezone

from . import eingabe
from .basis import api_call
from .chat_teil import ChatTeil, menge, tabelle
from .seitenleiste import MENUE

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
    """Einträge, deren Titel (oder Projektname, seit Phase 6) alle Wörter der
    Suche enthält (Groß/klein egal) — „geige" findet so auch alle Gespräche
    im Projekt Geige."""
    woerter = (suche or "").lower().split()
    if not woerter:
        return list(eintraege)
    return [e for e in eintraege
            if all(w in ("%s %s" % (e.get("titel") or "", e.get("projekt_name") or "")).lower()
                   for w in woerter)]


def listen_zeilen(eintraege, idx, breite, jetzt=None, aktiv=None):
    """Die Liste als Zeilen. -> [(text, art)], art: "gewaehlt" | "ungelesen" |
    "normal". Links Zeiger und ●, rechts das Alter; der Titel wird gekürzt."""
    raus = []
    for i, e in enumerate(eintraege):
        zeiger = "›" if i == idx else " "
        punkt = ("●" if e.get("ungelesen") else "…" if e.get("laeuft")
                 else "·" if e.get("id") == aktiv else " ")
        alter = alter_text(e.get("letzte"), jetzt)
        platz = max(1, breite - 4 - len(alter) - 1)
        titel = str(e.get("titel") or "neues gespräch").replace("\n", " ")
        if e.get("projekt_name"):          # Projekt vorn an der Zeile (Phase 6)
            titel = "%s · %s" % (e["projekt_name"], titel)
        if len(titel) > platz:
            titel = titel[:max(1, platz - 1)] + "…"
        text = "%s %s %s" % (zeiger, punkt, titel.ljust(platz))
        text = (text + " " + alter)[:breite]
        art = "gewaehlt" if i == idx else ("ungelesen" if e.get("ungelesen") else "normal")
        raus.append((text, art))
    return raus


# ── Die Liste ────────────────────────────────────────────────────────────

def _liste(archiv):
    """Ansichten liste/archiv mit :eins, :leer (dort wählen ↓ bzw. Enter,
    r und a nichts — ↑ führt immer ins Menü)."""
    a, z = (("restore", "back") if archiv else ("archive", "archive list"))
    hinten = [("n", "neu", "new"), ("z", "archivliste", z), ("/", "suchen", "search"),
              ("tab", "zuklappen", "hide chats"), ("esc", "zurueck", "back to reply"),
              ("f6", "fokus_weiter", "next pane")]
    mit = [("enter", "oeffnen", "open"), ("r", "umbenennen", "rename")]
    return {"": [("↑↓", "waehlen", "select"), ("pgup pgdn", "blaettern")] + mit
            + hinten[:1] + [("a", "archiv", a)] + hinten[1:],
            ":eins": [("↑", "waehlen", "menu")] + mit + hinten[:1] + [("a", "archiv", a)]
            + hinten[1:],
            ":leer": [("↑", "waehlen", "menu")] + hinten}


class Gespraechsliste(ChatTeil):
    """Zustand liegt in chat.AI["liste"] (None = zu):
    {eintraege, idx, suche, suchen, umbenennen, archiv, aktiv}.

    Ansichten: liste/archiv (+ :eins, :leer), suche (Tippen filtert),
    umbenennen (Feld)."""

    TASTEN = tabelle(dict(
        [("liste" + k, v) for k, v in _liste(False).items()]
        + [("archiv" + k, v) for k, v in _liste(True).items()]
        + [("suche", [("type", "suche_tippen", "filter"), ("⌫", "suche_tippen"),
                      ("enter", "suche_fertig", "done"), ("↑↓", "suche_fertig"),
                      ("esc", "suche_leeren", "clear filter"),
                      ("f6", "fokus_weiter", "next pane")]),
           ("umbenennen", [("enter", "name_fertig", "save"), ("esc", "name_ab", "cancel"),
                           ("type", "name_tippen"), ("⌫ ←→", "name_tippen"),
                           ("f6", "fokus_weiter", "next pane")])]))

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
        # Projekt des nächsten neuen Gesprächs (Phase 6) — für den Kasten-Titel.
        self.AI["neu_projekt"] = d.get("neu_projekt")
        return [e for e in d.get("gespraeche") or [] if isinstance(e, dict)], d.get("aktiv")

    def oeffnen(self, archiv=False):
        AI = self.AI
        # Seit 2026-10-09 auch während einer Antwort: sie läuft im
        # Hintergrund weiter (chat_strom.py).
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

    # ── Tasten (Tastentabelle, im Chat unter „liste:…") ────────────────
    def ansicht(self):
        L = self.AI["liste"]
        if L["umbenennen"] is not None:
            return "umbenennen"
        if L["suchen"]:
            return "suche"
        return ("archiv" if L["archiv"] else "liste") + menge(len(self.sichtbar()))

    def aktion_waehlen(self, taste):
        """↑↓; ↑ über dem ersten Gespräch geht ins Menü der Seitenleiste."""
        L, n = self.AI["liste"], len(self.sichtbar())
        if taste == "up" and L["idx"] <= 0:
            self.AI["seite_menu"] = len(MENUE) - 1
        elif n:
            L["idx"] = (L["idx"] + (1 if taste == "down" else -1)) % n

    def aktion_blaettern(self, taste):
        L, n = self.AI["liste"], len(self.sichtbar())
        L["idx"] = max(0, min(n - 1, L["idx"] + (-5 if taste == "pgup" else 5)))

    def aktion_oeffnen(self, _t):
        if self.gewaehlt():
            self.chat.seite.chat_oeffnen(self.AI["liste"]["idx"])

    def aktion_umbenennen(self, _t):
        e = self.gewaehlt()
        if e and e["id"] == ERINNERUNGEN:
            self.AI["msg"] = "„erinnerungen“ behält seinen namen"
        elif e:
            t = str(e.get("titel") or "")
            self.AI["liste"]["umbenennen"] = {"text": t, "cur": len(t), "u8": b""}

    def aktion_neu(self, _t):
        self.schliessen()
        self.chat.neues_gespraech()
        if self.AI.get("fokus") == "seite":
            self.AI["fokus"] = "eingabe"         # neues Gespräch → tippen

    def aktion_archiv(self, _t):
        self._archivieren()

    def aktion_archivliste(self, _t):
        self.oeffnen(archiv=not self.AI["liste"]["archiv"])

    def aktion_suchen(self, _t):
        self.AI["liste"]["suchen"] = True

    def aktion_zuklappen(self, _t):
        self.chat.seite.zuklappen()

    def aktion_zurueck(self, _t):
        self.AI["fokus"] = "eingabe"

    # Suche: Tippen filtert, Enter (oder ↑↓) ist fertig, Esc leert.
    def aktion_suche_tippen(self, taste):
        L = self.AI["liste"]
        L["suche"], _cur, L["u8_suche"] = self._tippen(
            L["suche"], len(L["suche"]), L.get("u8_suche", b""), taste)
        L["idx"] = 0

    def aktion_suche_fertig(self, _t):
        self.AI["liste"]["suchen"] = False

    def aktion_suche_leeren(self, _t):
        L = self.AI["liste"]
        L["suche"], L["suchen"] = "", False

    # Umbenennen: ein einzeiliges Feld.
    def aktion_name_tippen(self, taste):
        u = self.AI["liste"]["umbenennen"]
        u["text"], u["cur"], u["u8"] = self._tippen(u["text"], u["cur"], u["u8"], taste)

    def aktion_name_fertig(self, _t):
        L = self.AI["liste"]
        u, e = L["umbenennen"], self.gewaehlt()
        L["umbenennen"] = None
        if e and u["text"].strip():
            self.chat.titel_setzen(e["id"], u["text"])
            self.oeffnen(L["archiv"])

    def aktion_name_ab(self, _t):
        self.AI["liste"]["umbenennen"] = None

    @staticmethod
    def _tippen(text, pos, u8, taste):
        """Eine Taste (neutraler Name oder Zeichen) in einem einzeiligen Feld."""
        if taste == "backspace":
            return eingabe.zurueck(text, pos) + (u8,)
        if taste in ("left", "right"):
            return (eingabe.links if taste == "left" else eingabe.rechts)(text, pos) + (u8,)
        u8, z = eingabe.getippt(u8, taste)
        if z:
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
