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
#
# Zurück zum Öffner (2026-10-10): wer `zeigen(adresse, zurueck=…)` ruft,
# kommt wieder dran, sobald die geöffnete Ansicht zu ist (Esc) — statt auf
# der Startseite zu landen. Allgemein, nicht je Ansicht: jede App trägt beim
# Registrieren ihr Zustands-Dict ein (`active`), die Hauptschleife fragt
# nach jeder Taste `nachsehen()`.

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
        self._zustand = {}               # App → Zustands-Dict ihrer Ansicht
        self._rueck = None               # (Zustands-Dict, zurueck) solange offen

    def registrieren(self, app, handler, zustand=None):
        self._apps[app] = handler
        if zustand is not None:
            self._zustand[app] = zustand
        return handler

    def kennt(self, adresse):
        a = lesen(adresse)
        return bool(a and a[0] in self._apps)

    def zeigen(self, adresse, zurueck=None):
        """Ansicht zur Adresse öffnen. `zurueck()` (optional) bringt den
        Öffner wieder, wenn diese Ansicht zugeht."""
        a = lesen(adresse)
        if a is None or a[0] not in self._apps:
            return False
        app, pfad, abfrage = a
        ok = bool(self._apps[app](pfad, abfrage))
        zustand = self._zustand.get(app)
        if ok and zurueck is not None and zustand is not None and zustand.get("active"):
            self._rueck = (zustand, zurueck)
        return ok

    def nachsehen(self):
        """Nach jeder Taste: ist die geöffnete Ansicht zu, kommt der Öffner
        zurück (einmal). → True, wenn zurückgekehrt wurde."""
        if self._rueck is None or self._rueck[0].get("active"):
            return False
        _zustand, zurueck = self._rueck
        self._rueck = None
        zurueck()
        return True


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

    router.registrieren("kalender", kalender_zeigen, getattr(kalender, "K", None))
    if fokus is not None:
        router.registrieren("fokus", fokus_zeigen, getattr(fokus, "L", None))
    if graphen is not None:
        router.registrieren("graph", graph_zeigen, getattr(graphen, "G", None))
    return router
