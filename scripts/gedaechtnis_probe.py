#!/usr/bin/env python3
"""
Live-Probe gegen das ECHTE Cloud-Modell (Kalender + Werkzeuge): redet sie
noch Müll?

Die Fallen-Tests (`tests/test_gedaechtnis_faelle.py`) prüfen, was RAUSGEHT
— ohne Modell, deterministisch, in jedem Testlauf. Diese Probe prüft, was
ZURÜCKKOMMT. Beides braucht es: ein sauberer Kontext nützt nichts, wenn das
Modell trotzdem danebenliegt, und eine richtige Antwort ist wertlos, wenn
sie geraten war.

── Die Denkweise dahinter ──────────────────────────────────────────────
Nicht die Intelligenz wird getestet, sondern der KÄFIG. Jede Falle hier ist
so gebaut, dass ein schlaues Modell sie mit dem, was wir ihm hinlegen,
lösen KANN. Fällt es trotzdem rein, liegt es an uns — dann fehlt im
Kontext etwas, oder es steht etwas Irreführendes drin. Deshalb wird bei
jedem Fehlschlag der Kontext mit ausgegeben, nicht nur das Urteil.

── Isolation (wichtig) ─────────────────────────────────────────────────
Alles, was der Kopf und die Werkzeuge lesen oder schreiben, liegt in einem
Wegwerf-Ordner: Kalender, Transkript, Datei-Gedächtnis
(Steckbrief, Ziele, Hausregeln), Ablage, Gespräche, Rückmeldungen,
Klassifikator-Beispiele, Nutzerordner, Desk, Shop, Apps, Anbindungen,
Sandbox (Liste: _UMLENKUNGEN unten, wie tests/conftest.py). Von `data/`
wird nur angefasst, was keine Inhalte von Sasha trägt:
`data/ai_config.json` wird GELESEN (Keys und Einstellungen, sonst ginge
kein Aufruf raus), `data/ascii/` ebenso (mitgelieferte Bilder, im Repo),
und die Kosten werden in `data/ai_usage.json` GEBUCHT (echtes Geld, gehört
in die echte Buchhaltung und unter den Budget-Deckel).
Der Grund für den Riegel steht in der Projekt-Historie: eine frühere Probe
hat ihre Testknoten in Sashas echtem Cloud-Graphen hinterlassen, und bis
2026-10-14 schickte die Probe Sashas echten Steckbrief-Kopf mit raus.

── Was rausgeht ────────────────────────────────────────────────────────
Erfundene Testdaten (Zahnarzt, Fahrschule, Geigenstunde) plus der
System-Prompt. Keine echten Termine, kein echtes Gedächtnis.

── Graph-Fallen: archiviert ────────────────────────────────────────────
Falle 1 (Fieber/Monat) und die Extraktions-Fallen prüften den
Konzept-Graphen (aus seit 2026-08-18, seit 2026-10-31 aus dem Code). Sie
liegen wörtlich in memory/archive/associative_graph/gedaechtnis_probe_graph.py.

── Kosten ──────────────────────────────────────────────────────────────
Standard laeuft ALLES auf dem billigen Modell: rund 2 Cent fuer den ganzen
Lauf. Das ist keine Sparversion mit Qualitaetsverlust — es ist die HAERTERE
Probe. Getestet wird der Kaefig, nicht die Intelligenz: kommt ein kleines
Modell mit unserem Kontext zurecht, kommt ein grosses erst recht zurecht.
--voll faehrt das echte Chatmodell (teurer) und beantwortet die andere
Frage: reicht es auch im Alltag.

    venv/bin/python scripts/gedaechtnis_probe.py
    venv/bin/python scripts/gedaechtnis_probe.py --voll --zeige-kontext
"""
import argparse
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

HEUTE  = date.today()
MORGEN = HEUTE + timedelta(days=1)


# ── Wegwerf-Umgebung ───────────────────────────────────────────────────

# Env-Riegel der Module, relativ zum Wegwerf-Ordner — dieselben wie in
# tests/conftest.py. Bewusst NICHT dabei: ZENTRALE_AI_CONFIG_DIR (die Keys
# werden gebraucht) und ZENTRALE_USAGE_FILE (echte Kosten, echte Buchung).
_UMLENKUNGEN = {
    "ZENTRALE_TRANSKRIPT_DIR":              "ai_transcripts",
    "ZENTRALE_GEDAECHTNIS_DIR":             "gedaechtnis",
    "ZENTRALE_GESPRAECHE_DIR":              "gespraeche",
    "ZENTRALE_ABLAGE_DIR":                  "ablage",
    "ZENTRALE_RUECKMELDUNGEN_DIR":          "rueckmeldungen",
    "ZENTRALE_KLASSIFIKATOR_BEISPIELE_DIR": "klassifikator_beispiele",
    "ZENTRALE_NUTZER_ORDNER":               "nutzer",
    "ZENTRALE_SANDBOX_DIR":                 "sandbox",
    "ZENTRALE_DESK_ORDNER":                 "desk",
    "ZENTRALE_SHOP_ORDNER":                 "shop",
    "ZENTRALE_APPS_ORDNER":                 "apps",
    "ZENTRALE_ANBINDUNGEN_DIR":             "anbindungen",
}


def sandkasten():
    """Alles, was Kopf und Werkzeuge lesen oder schreiben, in einen
    Temp-Ordner umbiegen.

    Muss VOR dem ersten Import der core-Module laufen: die meisten Pfade
    werden beim Import aus der Env festgelegt. Wo es keinen Env-Riegel gibt
    (Kalender), werden die Modul-Globals danach direkt gesetzt;
    Gedächtnis und Transkript zusätzlich, falls sie doch schon geladen sind.
    """
    ordner = tempfile.mkdtemp(prefix="zentrale_probe_")
    for name, unter in _UMLENKUNGEN.items():
        os.environ[name] = os.path.join(ordner, unter)

    import kalender, gedaechtnis, transkript
    from pathlib import Path

    kalender.CAL_PATH = Path(ordner) / "kalender.json"
    kalender.ICS_DIR = None          # = kalender/ neben CAL_PATH
    gedaechtnis._DIR = os.environ["ZENTRALE_GEDAECHTNIS_DIR"]
    for name in ("_DIR", "DIR", "TRANS_DIR", "_ORDNER"):
        if hasattr(transkript, name):
            setattr(transkript, name, os.path.join(ordner, "ai_transcripts"))
    return ordner


def szenario_bauen():
    """Der Ausgangszustand: heute NICHTS, morgen zwei Termine, in sechs
    Tagen einer. (Der Graph-Teil — Krankheit nur auf den Monat datiert —
    liegt im Archiv, siehe Kopf.)"""
    import kalender

    kalender.add_entry("termine", MORGEN.isoformat(), "Zahnarzt", time="09:00")
    kalender.add_entry("termine", MORGEN.isoformat(), "Fahrschule", time="19:00")
    kalender.add_entry("termine", (HEUTE + timedelta(days=6)).isoformat(),
                       "Geigenstunde", time="17:45")


# ── Ein Turn fahren, mitschreiben was passiert ─────────────────────────

def turn(frage, modell=None):
    """Eine Frage durchs echte Cloud-Backend. Gibt (text, tools) zurück.

    Das Turn-Speichern wird stillgelegt: es spart pro Frage einen
    Konsolidierungs-Call, und ein Probe-Zug gehört in kein Gedächtnis.
    (Solange die Graph-Fallen dabei waren, hielt es zudem die Messung
    sauber — am 17.08. hatte die Konsolidierung der Chat-Phase einen
    Fehlschlag der Extraktions-Fallen vorgetäuscht.)
    """
    import cloud, consolidation, ki_werkzeuge, state

    gerufen = []
    echt = ki_werkzeuge.ausfuehren
    echt_save = consolidation.zug_vormerken

    def mitschreiben(name, args):
        gerufen.append(name)
        return echt(name, args)

    ki_werkzeuge.ausfuehren = mitschreiben
    consolidation.zug_vormerken = lambda *a, **k: None
    state.wait_permission = lambda: "nein"      # nichts schreiben lassen
    state.request_permission = lambda **k: None
    try:
        text = ""
        for ev in cloud.chat_stream([{"role": "user", "content": frage}],
                                    model=modell):
            if isinstance(ev, str):
                text += ev
        return text.strip(), gerufen
    finally:
        ki_werkzeuge.ausfuehren = echt
        consolidation.zug_vormerken = echt_save


# ── Die Fallen ─────────────────────────────────────────────────────────
#
# Jede: (Titel, Frage, Prüfung(text, tools) -> None | Grund)

def _kein_sport_behauptet(text, tools):
    """Nach Sport zu FRAGEN heißt nicht, Sport gemacht zu haben."""
    t = text.lower()
    treffer = [s for s in ("hast du bereits", "hast du schon", "warst du schon",
                           "du hast heute sport", "laut kalender sport",
                           "steht sport") if s in t]
    if treffer:
        return f"behauptet Sport für heute: {treffer}"
    return None


def _ohne_tool_beantwortet(text, tools):
    """Der Imprint soll die Tool-Runde sparen."""
    if "read_calendar" in tools:
        return f"ruft trotzdem read_calendar (Tools: {tools})"
    return None


def _mit_tool_beantwortet(text, tools):
    """Und für alles jenseits des nahen Horizonts MUSS sie das Tool rufen."""
    if "read_calendar" not in tools:
        return "antwortet ohne read_calendar — also aus dem geklebten Block"
    return None


def _nennt_morgen_termine(text, tools):
    fehlt = [w for w in ("Zahnarzt", "Fahrschule") if w.lower() not in text.lower()]
    return f"nennt {fehlt} nicht" if fehlt else None


FAELLE = [
    ("Frage nach Sport ist kein erledigter Sport",
     "kann ich heute wieder sport machen?",
     _kein_sport_behauptet),

    ("Naher Horizont ohne Tool-Runde",
     "was hab ich morgen vor?",
     lambda t, w: _ohne_tool_beantwortet(t, w) or _nennt_morgen_termine(t, w)),

    ("Ferner Horizont MIT Tool-Runde",
     "was steht nächste woche an?",
     _mit_tool_beantwortet),

    ("Heute ist leer, und das darf sie sagen",
     "hab ich heute noch irgendwas?",
     lambda t, w: _ohne_tool_beantwortet(t, w)),
]


# ── Ablauf ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--voll", action="store_true",
                   help="auf dem echten Chat-Modell statt dem billigen "
                        "(teurer; das billige ist die HÄRTERE Probe)")
    p.add_argument("--zeige-kontext", action="store_true",
                   help="bei jedem Fehlschlag den Kalender-Imprint mit ausgeben")
    a = p.parse_args()

    # ZUERST umbiegen, dann importieren — siehe sandkasten().
    ordner = sandkasten()
    try:
        import ai_config  # noqa: F401 — Import-Effekt: Keys aus data/ai_config.json
        import providers
        if not providers.configured():
            sys.exit("Kein Cloud-Key in data/ai_config.json — nichts zu proben.")

        # Standardmaessig das BILLIGE Modell. Das ist keine Sparmassnahme mit
        # Qualitaetsverlust, sondern die haertere Probe: getestet wird der
        # Kaefig, nicht die Intelligenz. Kommt ein kleines Modell mit unserem
        # Kontext zurecht, kommt ein grosses erst recht zurecht — und wenn
        # nicht, liegt es an uns.
        name = providers.configured()
        modell = None if a.voll else providers.cheap_model(name)
        print(f"Sandkasten: {ordner}")
        print(f"Anbieter:   {name}")
        print(f"Modell:     {modell or 'Standard-Chatmodell (--voll)'}\n")

        szenario_bauen()
        import usage
        vorher_kosten = usage.heute_euro()

        fehler = 0
        print("── Antworten " + "─" * 55)
        for titel, frage, pruefung in FAELLE:
            text, tools = turn(frage, modell)
            grund = pruefung(text, tools)
            fehler += bool(grund)
            print(f"\n{'✗' if grund else '✓'} {titel}")
            print(f"    frage:  {frage}")
            print(f"    tools:  {tools or '—'}")
            print(f"    sagt:   {text[:400]}")
            if grund:
                print(f"    PROBLEM: {grund}")
                if a.zeige_kontext:
                    import ki_prompt
                    print("    kontext:\n" + (ki_prompt._imprint_prompt() or "—"))

        print(f"\n{'─' * 68}\n{len(FAELLE) - fehler}/{len(FAELLE)} Fallen bestanden.")
        print(f"Kosten dieses Laufs: {usage.heute_euro() - vorher_kosten:.4f} €")
        return 1 if fehler else 0
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
