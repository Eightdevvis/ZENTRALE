# core/werkzeug_erzeuger/aktive.py
#
# Welche Anbindungen gerade eingeschaltet sind und welche Werkzeuge daraus
# werden (2026-10-11). Das Register (core/werkzeug_register.py) ruft
# `werkzeuge()` einmal beim Import: wie beim Kalender ist das Schema damit pro
# Prozess fest (Prompt-Cache). Standard ist AUS — Sasha schaltet eine
# Anbindung mit der Einstellung anbindung_<name> = an ein (das ist die Freigabe
# aus der Pipe, Schritt 4).
#
# Eine kaputte Datei darf den Start nie verhindern: sie fällt aus, und
# FEHLER sagt warum (die Werkstatt zeigt es an).

from . import allgemein, anbindung
from . import werkzeuge as _werkzeuge

FEHLER = {}          # name → [Meldungen] der Anbindungen, die nicht geladen werden konnten
QUELLEN = {}         # name → Quelle der geladenen und eingeschalteten


def laden() -> dict:
    """Alle eingeschalteten Anbindungen laden (frisch). -> QUELLEN."""
    FEHLER.clear()
    QUELLEN.clear()
    for name, info in anbindung.auflisten().items():
        if not anbindung.eingeschaltet(name):
            continue
        try:
            besch = anbindung.laden(info["pfad"])
            QUELLEN[name] = allgemein.quelle_aus(besch)
        except anbindung.AnbindungFehler as e:
            FEHLER[name] = e.meldungen
        except Exception as e:      # noqa: BLE001 — Start nie verhindern
            FEHLER[name] = [f"{e.__class__.__name__}: {e}"]
    return QUELLEN


def werkzeuge(belegte_namen=()) -> list:
    """Die Werkzeug-Einträge aller eingeschalteten Anbindungen. Ein Name, den
    es schon gibt, wird NIE überschrieben (die Prüfung verlangt die Vorsilbe
    des Namens, das hier ist der zweite Riegel)."""
    raus, belegt = [], set(belegte_namen)
    for name, quelle in laden().items():
        for w in _werkzeuge(quelle):
            if w.name in belegt:
                FEHLER.setdefault(name, []).append(f"{w.name}: Werkzeugname ist schon vergeben — übersprungen")
                continue
            belegt.add(w.name)
            raus.append(w)
    return raus
