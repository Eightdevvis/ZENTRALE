# core/kachel_fokus.py
#
# Quelle für Kacheln der App `fokus` (Listen), Art `liste`. Der Hub
# (core/kacheln.py) fragt hier an — dieselbe Schnittstelle, die später eine
# ausgezogene Listen-App über HTTP bedient (memory/hub/hub_bauplan.md
# „Kacheln"). 2026-10-10.
#
# Bezug als Adresse, z. B.
#   zentrale://fokus/liste?erledigte=false&liste=l_einkauf
# Die Liste selbst hat die Adresse zentrale://fokus/<liste> (ein Eintrag:
# zentrale://fokus/<liste>/<eintrag>) — die kommt bei „oeffnen" zurück.
#
# KEIN eigener Look (Sasha 2026-10-11: „Programm und Kachel teilen EIN
# Bild"): das Bild kommt aus core/listen_bild.py, derselben Quelle, die die
# Vollansicht (tui/ansichten/fokus.py) malt — oberste Ebene der Liste,
# Bernstein oben, Einträge als Kästen. Ändert sich das Design dort, ändert
# sich die Kachel mit. `erledigte` = die abgeschlossenen statt der offenen
# (wie enter auf den Bernstein); `tiefe` ist veraltet (eine Ebene wie im
# Programm) und wird nur noch für alte Adressen angenommen.
#
# NUR LESEN (Sasha 2026-10-10: Enter/`o` = nur öffnen). Gelesen wird über
# lists.read_lists(), das garantiert nicht schreibt — auch nicht die
# einmalige »week«-Migration. Die Listen gehören Sasha.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import adressen
import kachel_parameter
import listen_bild
import lists
from kachel_form import KachelFehler, KachelWeg

APP = "fokus"
RECHTE = ("lesen",)
TIEFE_GRENZE = 9                  # nur noch für alte Adressen (tiefe veraltet)

# Katalog-Eintrag. ttl: Listen ändern sich öfter als der Kalender (abhaken
# in der TUI), eine halbe Minute reicht. Parameter als JSON Schema
# (core/kachel_parameter.py, 2026-10-10); die Liste wählt man aus den
# vorhandenen — die trägt parameter_jetzt() beim Katalog frisch ein. Geprüft
# wird nur die Form (ein Text): gibt es die Liste nicht mehr, heißt das „weg".
ARTEN = {"liste": {
    "titel": "liste",
    "min": (12, 7),                 # Kopf + Bernstein + Trennlinie + ein Kasten
    "bevorzugt": (36, 12),
    "ttl": 30,
    "parameter": {
        "$schema": kachel_parameter.ENTWURF,
        "type": "object",
        "properties": {
            "liste": {"title": "liste", "description": "←→ blättert durch die listen",
                      "type": "string", "minLength": 1},
            "erledigte": {"title": "erledigte",
                          "description": "die abgeschlossenen zeigen statt der offenen",
                          "type": "boolean", "default": False},
            # Veraltet seit 2026-10-11: die Liste zeigt wie die Vollansicht
            # EINE Ebene (Ordner als ▸-Kasten). Bleibt nur, damit alte
            # Adressen gültig sind; Dialoge lassen `deprecated` weg.
            "tiefe": {"title": "ebenen", "description": "veraltet, ohne wirkung",
                      "type": "integer", "minimum": 1, "maximum": TIEFE_GRENZE,
                      "deprecated": True},
        },
        "required": ["liste", "erledigte"],
        "additionalProperties": False,
    },
}}

# ── Daten ─────────────────────────────────────────────────────────────

def _liste(lid):
    """Die Liste mit dieser id — oder KachelWeg (gelöscht, eingeordnet)."""
    for l in lists.read_lists():
        if isinstance(l, dict) and l.get("id") == lid:
            return l
    raise KachelWeg(lid)


def parameter_jetzt(art, schema):
    """Katalog: die Listen von jetzt zur Wahl (oneOf mit Namen). Keine
    Liste → None, dann lässt sich keine Kachel anlegen."""
    wahl = [(l["id"], l.get("name") or l["id"])
            for l in lists.read_lists() if isinstance(l, dict) and l.get("id")]
    return kachel_parameter.mit_auswahl(schema, "liste", wahl) if wahl else None


def _pruefen(art, ref):
    if art not in ARTEN:
        raise KachelFehler("unbekannte art: %s" % art)
    if not isinstance(ref, dict) or not isinstance(ref.get("liste"), str):
        raise KachelFehler("liste fehlt")
    tiefe = ref.get("tiefe", 3)                   # veraltet, ohne Wirkung (oben)
    if isinstance(tiefe, bool) or not isinstance(tiefe, int) or not 1 <= tiefe <= TIEFE_GRENZE:
        raise KachelFehler("ebenen: 1 bis %d" % TIEFE_GRENZE)
    return ref["liste"], bool(ref.get("erledigte"))


# ── Schnittstelle für den Hub ─────────────────────────────────────────
# Gezeichnet wird NUR über listen_bild — kein eigener Look hier (Wächter:
# tests/test_listen_bild.py).

def kachel(art, ref, w, h, oben=0):
    """Inhalt der Kachel in w×h Zellen → {zeilen, text, oben, oben_max}:
    die oberste Ebene der Liste, genau wie die Vollansicht sie zeigt."""
    lid, erledigte = _pruefen(art, ref)
    lst = _liste(lid)
    pfad, items = [str(lst.get("name") or lid)], lst.get("items")
    b = listen_bild.ebene(items, w, h, pfad, nur_erledigte=erledigte, oben=oben or 0)
    return {"zeilen": b["zeilen"], "oben": b["oben"], "oben_max": b["oben_max"],
            "text": listen_bild.klartext(pfad, items, erledigte)}


def bevorzugt(art, ref):
    """Bevorzugte Innengröße für GENAU diese Liste → (w, h): so hoch, dass
    alles Platz hat (höchstens 22 Zeilen), so breit wie der längste Titel
    (24 bis 48)."""
    lid, erledigte = _pruefen(art, ref)
    lst = _liste(lid)
    w, h = listen_bild.bevorzugt(lst.get("items"), [str(lst.get("name") or lid)], erledigte)
    return max(24, min(48, w)), max(ARTEN["liste"]["min"][1], min(22, h))


def aktion(art, ref, was):
    """„oeffnen" → die Adresse der Liste, zentrale://fokus/<liste>. Welche
    Ansicht das wird, entscheidet die Oberfläche."""
    lid, _e = _pruefen(art, ref)
    if was != "oeffnen":
        raise KachelFehler("unbekannte aktion: %s" % was)
    _liste(lid)                                   # weg? → „weg", nicht ins Leere zeigen
    return {"zeige": {"adresse": adressen.bauen(APP, [lid])}}
