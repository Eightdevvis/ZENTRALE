"""Wächter E4 (memory/hub/kern_auszug_inventur.md Abschnitt E, 2026-10-22):
jede Route, die die TUI ruft, steht in openapi.yaml — oder gehört einer App,
die sie selbst beschreibt (`routen` im app.toml, der Hub reicht weiter).

Warum: ZENTRALE soll auf jedem Format laufen (Leitlinie „überall
deploybar", hub_bauplan.md). Ein Dart- oder JS-Knoten muss jede Funktion aus
der Doku bauen können, nicht aus dem Python der TUI.

Am 2026-10-22 waren die meisten Routen nicht beschrieben. Sie stehen als
Altlast in memory/hub/routen_altlast.md — die Liste darf nur SCHRUMPFEN:
eine neue unbeschriebene Route wird rot, und eine beschriebene Altlast
verlangt, ausgetragen zu werden.
"""
import ast
import os
import re

import yaml

import app_weiterleitung

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALTLAST = os.path.join(ROOT, "memory", "hub", "routen_altlast.md")


def tui_pfade():
    """Alle /api/…-Pfade, die in tui/ als Text stehen (auch der feste Anfang
    eines f-Strings). Alles ab ? oder % fällt weg; ein Pfad, der auf / endet,
    ist ein Anfang (dahinter kommt eine Kennung)."""
    raus = set()
    for ordner, _d, dateien in os.walk(os.path.join(ROOT, "tui")):
        if "__pycache__" in ordner:
            continue
        for d in dateien:
            if not d.endswith(".py"):
                continue
            with open(os.path.join(ordner, d), encoding="utf-8") as f:
                baum = ast.parse(f.read())
            for k in ast.walk(baum):
                text = None
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    text = k.value
                elif isinstance(k, ast.JoinedStr) and k.values and \
                        isinstance(k.values[0], ast.Constant):
                    text = k.values[0].value
                if text and text.startswith("/api/"):
                    raus.add(re.split(r"[?%\s]", text, maxsplit=1)[0])
    return raus


def beschriebene_vorlagen():
    with open(os.path.join(ROOT, "openapi.yaml"), encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return list(spec["paths"])


def beschrieben(pfad, vorlagen, app_praefixe):
    for p in app_praefixe:
        if pfad == p or pfad.startswith(p + "/"):
            return True
    for v in vorlagen:
        muster = "^" + re.sub(r"\\{[^}]+\\}", "[^/]+", re.escape(v)) + "$"
        if re.match(muster, pfad):
            return True
        if pfad.endswith("/") and re.match(muster, pfad + "x"):
            return True          # Anfang + Kennung = eine beschriebene Vorlage
    return False


def altlast():
    with open(ALTLAST, encoding="utf-8") as f:
        return set(re.findall(r"^\| `(/api/[^`]*)` \|", f.read(), re.M))


def _offen():
    vorlagen = beschriebene_vorlagen()
    praefixe = list(app_weiterleitung.routen_tabelle())
    return {p for p in tui_pfade() if not beschrieben(p, vorlagen, praefixe)}


def test_pfade_werden_gefunden():
    pfade = tui_pfade()
    assert "/api/kachel" in pfade and "/api/lists/" in pfade and len(pfade) > 50


def test_keine_neue_unbeschriebene_route():
    neu = sorted(_offen() - altlast())
    assert not neu, (
        "Die TUI ruft Routen, die nirgends beschrieben sind:\n  " + "\n  ".join(neu) +
        "\nIn openapi.yaml beschreiben (oder sie gehören einer App, die sie "
        "laut `routen` besitzt). NICHT in routen_altlast.md eintragen — die "
        "Liste darf nur schrumpfen.")


def test_beschriebene_altlasten_sind_ausgetragen():
    erledigt = sorted(altlast() - _offen())
    assert not erledigt, (
        "Gut gemacht — beschrieben (oder nicht mehr gerufen):\n  " + "\n  ".join(erledigt) +
        "\nStreich sie in memory/hub/routen_altlast.md.")
