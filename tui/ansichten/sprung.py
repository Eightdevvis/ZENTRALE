# tui/ansichten/sprung.py
#
# Der Adress-Router der TUI (2026-10-10, „ein Objekt, eine Adresse",
# memory/system/hub_bauplan.md „Adressen"). Eine App sagt nur, WAS aufgehen
# soll — eine Adresse zentrale://<app>/<pfad>?… (z. B. als Antwort auf `o`
# einer Kachel, POST /api/kachel/aktion). Welche Ansicht das in der TUI
# wird, steht hier: je App ein Handler (pfad, abfrage) -> bool, eingetragen
# in einem Router. Der Desk kennt keine davon — er bekommt nur `zeigen`.
# Neue Ziele kommen als `registrieren(app, handler)` dazu, keine if-Kette
# (Listen `fokus` und Graphen `graph` seit 2026-10-10). Später nutzen Links
# in Notizen denselben Router.

from datetime import date
from urllib.parse import parse_qsl, unquote, urlsplit

SCHEMA = "zentrale"


def lesen(adresse):
    """Adresse → (app, pfad, abfrage) oder None, wenn es keine ist. Nur
    urllib.parse, wie core/adressen.py."""
    try:
        t = urlsplit(str(adresse))
    except ValueError:
        return None
    if t.scheme != SCHEMA or not t.netloc:
        return None
    pfad = tuple(unquote(p) for p in t.path.split("/")[1:] if p)
    return t.netloc, pfad, dict(parse_qsl(t.query, keep_blank_values=True))


class Router:
    """App → Handler(pfad, abfrage) -> bool (False: kann ich nicht)."""

    def __init__(self):
        self._apps = {}

    def registrieren(self, app, handler):
        self._apps[app] = handler
        return handler

    def kennt(self, adresse):
        a = lesen(adresse)
        return bool(a and a[0] in self._apps)

    def zeigen(self, adresse):
        a = lesen(adresse)
        if a is None or a[0] not in self._apps:
            return False
        app, pfad, abfrage = a
        return bool(self._apps[app](pfad, abfrage))


def kalender_tag(pfad, abfrage):
    """Welcher Tag zu einer Kalender-Adresse gehört: zentrale://kalender/
    <JJJJ-MM-TT>, bei einem Ausschnitt dessen `von`; sonst None (= heute)."""
    for kandidat in ([pfad[0]] if pfad else []) + [abfrage.get("von")]:
        try:
            return date.fromisoformat(str(kandidat))
        except ValueError:
            continue
    return None


def eintrag_id(text):
    """Abschnitt einer Adresse → id eines Listen-Eintrags. Einträge zählen
    in core/lists.py als ganze Zahlen; was keine ist, bleibt Text."""
    return int(text) if str(text).isdigit() else text


def router_fuer(DESK, kalender, fokus=None, graphen=None):
    """Der Router der TUI mit allem, was heute ansprungbar ist."""
    router = Router()

    def kalender_zeigen(pfad, abfrage):
        DESK["active"] = False
        kalender.oeffnen()
        tag = kalender_tag(pfad, abfrage)
        if tag is not None:
            kalender.bedienung.setze_tag(tag)
        return True

    def fokus_zeigen(pfad, abfrage):
        """zentrale://fokus/<liste>[/<eintrag>] → das Listen-Werkzeug dort
        (2026-10-10). Ohne Pfad (z. B. eine Kachel-Adresse) → nicht meins."""
        if not pfad or pfad[0] == "liste":
            return False
        DESK["active"] = False
        return fokus.zeige_liste(pfad[0], eintrag_id(pfad[1]) if len(pfad) > 1 else None)

    def graph_zeigen(pfad, abfrage):
        """zentrale://graph/<gid> → das Graph-Werkzeug mit genau dem Graphen."""
        if len(pfad) != 1 or pfad[0] == "verlauf":
            return False
        DESK["active"] = False
        return graphen.zeige_graph(pfad[0])

    router.registrieren("kalender", kalender_zeigen)
    if fokus is not None:
        router.registrieren("fokus", fokus_zeigen)
    if graphen is not None:
        router.registrieren("graph", graph_zeigen)
    return router
