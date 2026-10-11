# tui/ansichten/chat_teil.py
#
# Was alle Teile des Chats mit eigener Tastentabelle gemeinsam haben
# (Seitenleiste, Gesprächsliste, rechts, Bewertung, Ablage, Gedächtnis,
# Projekte, Einstellungen — Tastentabellen seit 2026-10-11, tasten.py).
# Chat.TASTEN fügt ihre Tabellen mit Tasten.zusammen zusammen; ihre Ansichten
# heißen dort „teil:ansicht".
#
# Strg+C stoppt im ganzen Chat eine laufende Antwort und beendet NIE die TUI
# (zentrale_tui.taste_verteilen reicht Zeichen 3 an Chat.taste) — darum
# steht es in JEDER Ansicht jedes Teils (ungezeigt; die Leiste nennt es, wo
# man auf die Antwort schaut).

from . import tasten as T


def tabelle(ansichten):
    """Tasten(…) eines Teils: jede Ansicht bekommt Strg+C dazu."""
    return T.Tasten({a: list(liste) + [("ctrl+c", "stoppen")]
                     for a, liste in ansichten.items()})


def menge(n):
    """Ansichts-Endung nach der Zahl der Einträge: leer, einer, mehrere.
    Bei einem Eintrag wählt ↑↓ nichts, bei keinem auch Enter nicht."""
    return ":leer" if n == 0 else ":eins" if n == 1 else ""


def freitext(tasten):
    """{ansicht: aktion} der Ansichten mit Freitext („type")."""
    return {a: e["aktion"] for a, liste in tasten.daten().items() for e in liste
            if e["taste"] == "type"}


def verteilen(programm, tasten, ansicht, ch, frei):
    """tasten.verteilen — und die Bytes eines Umlauts (128–255), die die
    Tabelle nicht kennt (curses liefert UTF-8 byteweise), als chr(byte) an
    die Freitext-Aktion der Ansicht (frei = freitext(tasten))."""
    if isinstance(ch, int) and 128 <= ch <= 255:
        if ansicht not in frei:
            return None
        return getattr(tasten.ziel(programm, ansicht), "aktion_" + frei[ansicht])(chr(ch))
    return tasten.verteilen(programm, ansicht, ch)


class ChatTeil:
    """Mixin: self.chat ist der Chat (chat.py); der Teil hat TASTEN und
    ansicht(). Im Chat verteilt Chat.taste über die zusammengefügte Tabelle;
    taste() hier ist derselbe Weg für den Teil allein (Tests)."""

    def taste(self, ch):
        frei = type(self).__dict__.get("_FREI")
        if frei is None:
            frei = type(self)._FREI = freitext(self.TASTEN)
        return verteilen(self, self.TASTEN, self.ansicht(), ch, frei)

    def aktion_stoppen(self, taste):
        return self.chat.aktion_stoppen(taste)

    def aktion_fokus_weiter(self, _taste):
        self.chat.fokus_weiter()
