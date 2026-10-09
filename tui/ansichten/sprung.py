# tui/ansichten/sprung.py
#
# Wohin `o` auf einer Kachel springen kann (2026-10-10). Die App sagt über
# den Hub, welche Ansicht an welchem Ziel aufgeht ({"zeige": {ansicht,
# ziel}}, POST /api/kachel/aktion); hier steht, welche Ansichten so
# ansprungbar sind. Der Desk kennt keine davon — er bekommt nur `zeigen`.
# Neue Ziele (Listen, Graphen …) kommen als Eintrag in `ziele` dazu.

from datetime import date


def zeigen_fuer(DESK, kalender):
    """-> zeigen(ansicht, ziel) -> bool (False: kenne ich nicht)."""

    def kalender_zeigen(ziel):
        DESK["active"] = False
        kalender.oeffnen()
        try:
            kalender.bedienung.setze_tag(date.fromisoformat(str(ziel)))
        except ValueError:
            pass                        # kein Datum: heute, wie beim Öffnen
        return True

    ziele = {"kalender": kalender_zeigen}

    def zeigen(ansicht, ziel):
        f = ziele.get(ansicht)
        return bool(f and f(ziel))
    return zeigen
