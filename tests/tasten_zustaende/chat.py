"""Chat: zu jeder Ansicht der Tastentabelle (tui/ansichten/chat.py, mit den
Teilen) ein Weg dorthin — tests/test_tastentabellen.py drückt dort jede
Taste der Tabelle. Die Daten kommen aus dem gefälschten Backend
(tests/tui_schirm/backend.py); wo eine Ansicht weniger oder mehr Einträge
braucht, wird hier gekürzt oder ergänzt."""
import test_fussleiste as F
from tui import zentrale_tui as zt
from tui.ansichten import chat as C
from tui.ansichten.chat_ablage import TRENNER


def _t(u, *tasten):
    for t in tasten:
        zt.taste_verteilen(u, t if isinstance(t, int) else ord(t))


# ── Eingabe ───────────────────────────────────────────────────────────

def _ohne_dok(u):
    u.AI["log"] = [e for e in u.AI["log"] if e[0] != "ablage"]


def _mit_dok(u):
    u.AI["log"].append(("ablage", "d1" + TRENNER + "Packliste Radtour"))


def _eingabe(art="eingabe", text="", cur=None, dok=False):
    """Eingabefeld: art eingabe | antwort (läuft) | bearbeiten (/edit)."""
    def aufbau(u):
        F._chat(u)
        _ohne_dok(u)
        if dok:
            _mit_dok(u)
        if art == "antwort":
            u.AI.update(streaming=True, strom=7, answer="es war einmal")
        if art == "bearbeiten":
            u.AI["ersetzt"] = "m1"
        # Cursor mitten im Text: dann bewegen/löschen alle Cursor-Tasten etwas.
        u.AI["input"], u.AI["cur"] = text, len(text) // 2 if cur is None else cur
    return aufbau


def _eingaben():
    z = {}
    for art in ("eingabe", "antwort", "bearbeiten"):
        z[art] = _eingabe(art)
        z[art + ":text"] = _eingabe(art, "hallo")
        z[art + ":zeilen"] = _eingabe(art, "eins\nzwei", 6)
        if art != "antwort":
            z[art + ":dokument"] = _eingabe(art, dok=True)
    return z


# ── Frage, Auswahl ────────────────────────────────────────────────────

def _frage(n):
    def aufbau(u):
        F._chat_antwort(u)
        u.AI["perm"] = {"frage": "darf ich?",
                        "optionen": ["ja, nur dieses mal", "ja, für dieses gespräch",
                                     "ja, immer", "nein"][4 - n:]}
    return aufbau


def _wahl(n, filtern=None):
    def aufbau(u):
        F._chat(u)
        optionen = [("stufe %d" % i, {"effort": "s%d" % i}) for i in range(n)]
        u.AI["wahl"] = {"titel": "wählen", "optionen": optionen, "idx": 0}
        if filtern is not None:
            u.AI["wahl"].update(alle=[("aa", {"modell": "aa"}), ("ab", {"modell": "ab"}),
                                      ("b", {"modell": "b"})], filter="")
            C.wahl_filtern(u.AI["wahl"], filtern)
    return aufbau


# ── Verlauf ───────────────────────────────────────────────────────────

LOG = [("user", "frage"), ("denken", "hm, mal sehen"), ("werkzeug", "read_note(name=x)"),
       ("werkzeug_ergebnis", "↳ " + "lang " * 400),
       ("ablage", "d1" + TRENNER + "Packliste Radtour"), ("ai", "antwort")]


def _verlauf(art):
    """Fokus im Verlauf, Ziel der Art `art` gewählt (None: keins, "leer":
    Verlauf ohne Ziele)."""
    def aufbau(u):
        F._chat(u)
        if art == "leer":
            u.AI["log"] = []
        else:
            u.AI["log"] = list(LOG)
            u.AI["spuren"] = {5: "n2"}
            u.AI["ablaeufe"] = {"n2": [{"art": "text", "t": 0.1, "text": "schritt eins"}]}
            u.AI["offen"] = {("schritt", 2), ("trace", 5)}   # „… mehr" und der trace
        F.zeichnen(u)
        u.AI["fokus"], u.AI["vwahl"] = "verlauf", None
        if art not in (None, "leer"):
            u.AI["vwahl"] = next(z for z in u.chat._ziele if z[0] == art)
    return aufbau


# ── Seitenleiste und Gespräche ────────────────────────────────────────

def _liste(n=None, archiv=False):
    def aufbau(u):
        F._liste(u)
        L = u.AI["liste"]
        if n is not None:
            L["eintraege"], L["idx"] = L["eintraege"][1:1 + n], 0
        L["archiv"] = archiv
    return aufbau


def _umbenennen(u):
    F._liste_umbenennen(u)


def _suche(u):
    F._liste_suche(u)
    _t(u, "s")


# ── rechts ────────────────────────────────────────────────────────────

def _eine_fassung(u):
    """Das gefälschte Backend liefert immer d1 (zwei Fassungen) — hier eins
    mit nur einer."""
    L = u.AI["ablage"]["lesen"]
    L["dok"]["kopf"]["fassung"], L["fassung"] = 1, 1


def _dokument(fassungen):
    def aufbau(u):
        F._chat(u)
        u.chat.rechts.dokument_zeigen("d1")
        if fassungen == 1:
            _eine_fassung(u)
    return aufbau


def _outputs(n):
    def aufbau(u):
        F._chat(u)
        _ohne_dok(u)
        for i in range(n):
            u.AI["log"].append(("ablage", "d%d%sDokument %d" % (i + 1, TRENNER, i + 1)))
        u.chat.rechts.outputs_umschalten()
        F.zeichnen(u)
        u.AI["fokus"] = "rechts"
    return aufbau


# ── Bewertung ─────────────────────────────────────────────────────────

def _bewertung(text):
    def aufbau(u):
        F._bewertung(u)
        u.AI["bewertung"].update(text=text, cur=len(text) // 2)
    return aufbau


# ── Überlagerungen ────────────────────────────────────────────────────

def _einstellungen(abschnitt=None, kuerzen=None, akte=None):
    """kuerzen: Zahl der Zeilen, die der Abschnitt behält (:eins, :leer)."""
    def aufbau(u):
        F._einstellungen(abschnitt)(u)
        E = u.AI["einstellungen"]
        if akte is not None:
            E["akte"] = akte
        if kuerzen is not None:
            d = E["daten"]
            if abschnitt == "skills":
                d["gedaechtnis"]["skills"] = d["gedaechtnis"]["skills"][:kuerzen]
            elif abschnitt == "permissions":
                e = d["erlaubnis"]
                e["immer"], e["gespraech"] = e["immer"][:kuerzen], []
            elif abschnitt == "feedback":
                d["rueckmeldungen"] = d["rueckmeldungen"][:kuerzen]
    return aufbau


def _gedaechtnis(abschnitt, skills=None):
    def aufbau(u):
        F._chat(u)
        u.chat.gedaechtnis.oeffnen(abschnitt)
        if skills is not None:
            d = u.AI["gedaechtnis"]["daten"]
            d["skills"] = d["skills"][:skills]
    return aufbau


def _ablage(n=None, archiv=False, korb=False):
    def aufbau(u):
        F._ablage(u)
        A = u.AI["ablage"]
        alle = A["eintraege"] or []
        if n is not None:
            A["eintraege"] = alle[:n]
        A["archiv"], A["korb"] = archiv, korb      # Papierkorb (2026-10-11)
    return aufbau


def _ablage_lesen(fassungen):
    def aufbau(u):
        F._ablage(u)
        u.chat.ablageliste.lesen("d1")
        if fassungen == 1:
            _eine_fassung(u)
    return aufbau


def _projekte(n=None, archiv=False):
    def aufbau(u):
        F._projekte(u)
        P = u.AI["projekte"]
        if n is not None:
            P["liste"], P["idx"] = P["liste"][:n], 0
        P["archiv"] = archiv
    return aufbau


def _projekt(n=None):
    def aufbau(u):
        F._projekt(u)
        d = u.AI["projekte"]["detail"]
        if n is not None:
            g = d.get("gespraeche") or []
            d["gespraeche"] = (g * 2)[:n]
    return aufbau


def _projekt_name(u):
    F._projekt_name(u)
    _t(u, "x", "y")


ZUSTAENDE = dict(
    _eingaben(),
    **{"frage:%d" % n: _frage(n) for n in (2, 3, 4)},
    **{"wahl": _wahl(10), "wahl:eins": _wahl(1), "wahl:leer": _wahl(0),
       "wahl:filter": _wahl(0, "a"), "wahl:filter:eins": _wahl(0, "aa"),
       "wahl:filter:leer": _wahl(0, "zz")},
    **{"verlauf:" + (a or "frei"): _verlauf(a) for a in
       (None, "leer", "schritt", "denken", "voll", "kopieren", "wiederholen", "dok",
        "gut", "schlecht", "trace", "spur")},
    **{"seite:menue": F._seite_menue,
       "liste:liste": _liste(), "liste:liste:eins": _liste(1), "liste:liste:leer": _liste(0),
       "liste:archiv": _liste(archiv=True), "liste:archiv:eins": _liste(1, True),
       "liste:archiv:leer": _liste(0, True),
       "liste:suche": _suche, "liste:umbenennen": _umbenennen},
    **{"rechts:dokument": _dokument(1), "rechts:dokument:fassungen": _dokument(2),
       "rechts:outputs": _outputs(2), "rechts:outputs:eins": _outputs(1),
       "rechts:outputs:leer": _outputs(0)},
    **{"bewertung:leer": _bewertung(""), "bewertung:text": _bewertung("zu knapp")},
    **{"einstellungen:nav": _einstellungen(),
       "einstellungen:skills": _einstellungen("skills"),
       "einstellungen:skills:eins": _einstellungen("skills", 1),
       "einstellungen:skills:leer": _einstellungen("skills", 0),
       "einstellungen:memory": _einstellungen("memory"),
       "einstellungen:memory:themen": _einstellungen("memory", akte=3),
       "einstellungen:usage": _einstellungen("usage"),
       "einstellungen:capabilities": _einstellungen("capabilities"),
       "einstellungen:permissions": _einstellungen("permissions"),
       "einstellungen:permissions:eins": _einstellungen("permissions", 1),
       "einstellungen:permissions:leer": _einstellungen("permissions", 0),
       "einstellungen:model": _einstellungen("model"),
       "einstellungen:feedback": _einstellungen("feedback"),
       "einstellungen:feedback:eins": _einstellungen("feedback", 1),
       "einstellungen:feedback:leer": _einstellungen("feedback", 0)},
    **{"gedaechtnis:" + a: _gedaechtnis(a) for a in
       ("hausregeln", "steckbrief", "ziele", "themen", "skills")},
    **{"gedaechtnis:skills:eins": _gedaechtnis("skills", 1),
       "gedaechtnis:skills:leer": _gedaechtnis("skills", 0)},
    **{"ablage:liste": _ablage(), "ablage:liste:eins": _ablage(1),
       "ablage:liste:leer": _ablage(0), "ablage:archiv": _ablage(archiv=True),
       "ablage:archiv:eins": _ablage(1, True), "ablage:archiv:leer": _ablage(0, True),
       "ablage:korb": _ablage(korb=True), "ablage:korb:eins": _ablage(1, korb=True),
       "ablage:korb:leer": _ablage(0, korb=True),
       "ablage:lesen": _ablage_lesen(1), "ablage:lesen:fassungen": _ablage_lesen(2)},
    **{"projekte:liste": _projekte(), "projekte:liste:eins": _projekte(1),
       "projekte:liste:leer": _projekte(0), "projekte:archiv": _projekte(archiv=True),
       "projekte:archiv:eins": _projekte(1, True), "projekte:archiv:leer": _projekte(0, True),
       "projekte:detail": _projekt(2), "projekte:detail:eins": _projekt(1),
       "projekte:detail:leer": _projekt(0), "projekte:eingabe": _projekt_name},
)
