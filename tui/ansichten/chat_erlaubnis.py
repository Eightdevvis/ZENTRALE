# tui/ansichten/chat_erlaubnis.py
#
# /erlaubnis im KI-Chat: zeigt, was die KI ohne Frage darf („immer" und
# „für dieses Gespräch"), und nimmt es zurück. 2026-10-07 (Sasha: „beides
# einstellbar machen"). Das Gate selbst: core/erlaubnis.py; Routen
# GET /api/erlaubnis, POST /api/erlaubnis/zuruecknehmen.
#
# Eigenes Modul, damit chat.py nur eine Zeile dafür trägt. Die Texte sind
# reine Funktionen (testbar ohne curses und ohne Backend).

import urllib.error

from .basis import api_call


def zeilen(stand):
    """Die Übersicht als Text für den Verlauf."""
    immer = stand.get("immer") or []
    gespraech = stand.get("gespraech") or []
    if not immer and not gespraech:
        return "die ki fragt vor allem, was etwas ändert — nichts ist dauerhaft erlaubt"
    raus = ["ohne fragen erlaubt:"]
    raus += ["  immer: %s" % e.get("was") for e in immer]
    raus += ["  in diesem gespräch: %s" % e.get("was") for e in gespraech]
    return "\n".join(raus)


def auswahl(stand, aktion):
    """Die Auswahl zum Zurücknehmen, oder None, wenn nichts erlaubt ist."""
    optionen = []
    for art, wort in (("immer", "immer"), ("gespraech", "dieses gespräch")):
        for e in stand.get(art) or []:
            optionen.append(("nicht mehr %s: %s" % (wort, e.get("was")),
                             {"werkzeug": e.get("name")}))
    if not optionen:
        return None
    if len(optionen) > 1:
        optionen.append(("alles zurücknehmen", {"alle": True}))
    return {"titel": "erlaubnis zurücknehmen?", "optionen": optionen,
            "idx": 0, "aktion": aktion}


class ErlaubnisSteuerung:
    """Mixin für Chat: self.AI, self.AI_LOCK."""

    def befehl_erlaubnis(self, arg=""):
        AI = self.AI
        try:
            stand = api_call("/api/erlaubnis")
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung zum backend"
            return
        stand = stand if isinstance(stand, dict) else {}
        with self.AI_LOCK:
            AI["log"].append(("hinweis", zeilen(stand)))
            AI["scroll"] = 0
        AI["wahl"] = auswahl(stand, self.erlaubnis_zuruecknehmen)

    def erlaubnis_zuruecknehmen(self, daten):
        AI = self.AI
        try:
            erg = api_call("/api/erlaubnis/zuruecknehmen", "POST", daten)
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung zum backend"
            return
        weg = (erg or {}).get("weg") if isinstance(erg, dict) else None
        AI["msg"] = ("zurückgenommen — die ki fragt wieder" if weg
                     else "war schon nicht mehr erlaubt")
