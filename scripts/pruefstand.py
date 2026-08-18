#!/usr/bin/env python3
"""
Prüfstand: das ganze Gedächtnis- und Verhaltensgerüst gegen das echte Modell.

Die Fallen-Tests (`tests/test_gedaechtnis*.py`) prüfen, was RAUSGEHT — ohne
Modell, in jedem Testlauf. Dieser Prüfstand prüft, was ZURÜCKKOMMT, und
zwar breit: Gedächtnis, Kalender, Erlaubnis-Gate, Zeit, Persönlichkeit.
Gedacht als Abnahme VOR dem nächsten Umbau, nicht als tägliche Suite.

── Isolation, und zwar vollständig ─────────────────────────────────────
Sasha benutzt ZENTRALE parallel. Also bekommt dieser Lauf einen eigenen
Wegwerf-Ordner für ALLES, was geschrieben wird:

    Gedächtnis   gedaechtnis._DIR
    Kalender     kalender.CAL_PATH
    Graph        cloud.CLOUD_GRAPH
    Messreihen   graphs._DATA_DIR      ← leicht zu übersehen; create_series
                                          und log_series schreiben dorthin
    Transkript   transkript._DIR

Was NICHT umgebogen wird: `data/ai_usage.json`. Dieser Lauf kostet echtes
Geld, und das gehört in die echte Buchhaltung.

Am Ende werden Prüfsummen über ALLE Dateien in data/ von vorher und
nachher verglichen. Der Grund steht in der Projekt-Historie: eine frühere
Probe hat ihre Testknoten in Sashas echtem Graphen hinterlassen.

── Kosten ──────────────────────────────────────────────────────────────
Default ist das billige Modell (wenige Cent). Mit --voll läuft es auf dem
echten Chatmodell — teurer, aber nur das beantwortet die Frage, ob es im
Alltag trägt. Achtung: das billige Modell bleibt nach einem Werkzeug-Aufruf
gerne stumm (gemessen 18.08.2026). Das zählt hier als Fehlschlag und ist
auch einer — nur eben einer des Modells, nicht des Gerüsts.

    venv/bin/python scripts/pruefstand.py --voll
    venv/bin/python scripts/pruefstand.py --nur gedaechtnis
    venv/bin/python scripts/pruefstand.py --voll --zeige-alles
"""
import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

HEUTE = date.today()
MORGEN = HEUTE + timedelta(days=1)
DATEN = os.path.join(ROOT, "data")


# ── Wegwerf-Umgebung ───────────────────────────────────────────────────

def sandkasten():
    """Jeden Schreibweg in einen Temp-Ordner umbiegen. Gibt den Ordner."""
    from pathlib import Path
    import cloud, gedaechtnis, graphs, kalender, transkript

    ordner = tempfile.mkdtemp(prefix="zentrale_pruefstand_")
    gedaechtnis._DIR = os.path.join(ordner, "gedaechtnis")
    kalender.CAL_PATH = Path(ordner) / "kalender.json"
    cloud.CLOUD_GRAPH = os.path.join(ordner, "graph.json")
    graphs._DATA_DIR = os.path.join(ordner, "reihen")
    graphs._REGISTRY = os.path.join(graphs._DATA_DIR, "graphs.json")
    transkript._DIR = os.path.join(ordner, "transkripte")
    os.makedirs(graphs._DATA_DIR, exist_ok=True)
    return ordner


def pruefsummen() -> dict:
    """(Pfad → sha1) über alles unter data/. Der Beweis für die Isolation."""
    aus = {}
    for wurzel, _, dateien in os.walk(DATEN):
        for name in dateien:
            pfad = os.path.join(wurzel, name)
            try:
                with open(pfad, "rb") as f:
                    aus[pfad] = hashlib.sha1(f.read()).hexdigest()
            except OSError:
                pass
    return aus


def szenario():
    """Ein glaubwürdiger Ausgangszustand — Sashas Lage im Kleinen."""
    import gedaechtnis, graphs, kalender

    kalender.add_entry("termine", MORGEN.isoformat(), "Zahnarzt", time="10:30")
    kalender.add_routine("routinen", "Fahrschule", "FREQ=WEEKLY;BYDAY=TU,TH",
                         time="19:00", ende="20:00", ort="Fahrschule")
    kalender.add_entry("termine", (HEUTE + timedelta(days=9)).isoformat(),
                       "Mannheim")

    with open(gedaechtnis._pfad("", "sasha"), "w", encoding="utf-8") as f:
        f.write("# Sasha\n\nStudiert Biophysik in Saarbrücken.\n\n"
                "- Fokus und Fertigstellen haben Vorrang vor Breite.\n"
                "- Zweifelt manchmal am Studiengang; dann an die Gründe "
                "erinnern, nicht zum Wechsel raten.\n")
    with open(gedaechtnis._pfad("", "ziele"), "w", encoding="utf-8") as f:
        f.write("# Ziele\n\n- Spagat, L-Sit, Ausdauer für die Zugspitze\n"
                "- Umzug fertig kriegen\n- Führerschein\n")

    gedaechtnis.dossier_notieren(
        "kataloge/ideen",
        "## Fourier-Visualisierer aufm Oszi\n"
        "- thema:     fourier, frequenzen, signale\n"
        "- equipment: arduino, dac, loetkolben\n"
        "- aufwand:   klein\n- status: idee\n- dossier: -\n\n"
        "## Wetterstation mit Funkanbindung\n"
        "- thema:     sensorik, funk, wetter\n"
        "- equipment: esp32, bme280, loetkolben\n"
        "- aufwand:   gross\n- status: idee\n- dossier: -\n")
    gedaechtnis.dossier_notieren(
        "dossiers/umzug",
        "Küche: Regale hängen, Apparatur fehlt. Bad: nichts passiert.")
    gedaechtnis.dossier_notieren(
        "dossiers/spagat",
        "Ziel voller Spagat. Messreihe: spagat_cm. Stand: 22 cm bis Boden "
        "(12.08.). Blockiert vermutlich an den Adduktoren.")
    g = graphs.create_graph("spagat_cm", gtype="number", unit="cm")
    gid = g["id"] if isinstance(g, dict) else "g_spagat_cm"
    graphs.log_value(gid, (HEUTE - timedelta(days=6)).isoformat(), 22)


# ── Einen Turn fahren ──────────────────────────────────────────────────

def turn(frage, modell=None, erlaubnis="nein"):
    """Eine Frage durchs echte Backend. → (text, tools, gate_fragen)."""
    import ai, cloud, state

    tools, gefragt = [], []
    echt_tool, echt_save = ai._execute_tool, ai._async_save_turn

    def mit(name, args):
        tools.append(name)
        return echt_tool(name, args)

    def frage_merken(**kw):
        gefragt.append(kw.get("frage") or str(kw))

    ai._execute_tool = mit
    ai._async_save_turn = lambda *a, **k: None      # spart pro Frage einen Call
    state.request_permission = frage_merken
    state.wait_permission = lambda *a, **k: erlaubnis
    try:
        text = ""
        for ev in cloud.chat_stream([{"role": "user", "content": frage}],
                                    model=modell):
            if isinstance(ev, str):
                text += ev
        return text.strip(), tools, gefragt
    finally:
        ai._execute_tool = echt_tool
        ai._async_save_turn = echt_save


# ── Prüfhelfer ─────────────────────────────────────────────────────────

def _hat(d, *werkzeuge):
    fehlt = [w for w in werkzeuge if w not in d["tools"]]
    return f"ruft {fehlt} nicht (Tools: {d['tools'] or '—'})" if fehlt else None


def _ohne(d, *werkzeuge):
    da = [w for w in werkzeuge if w in d["tools"]]
    return f"ruft {da}, obwohl es das nicht braucht" if da else None


def _nennt(d, *woerter):
    t = d["text"].casefold()
    fehlt = [w for w in woerter if w.casefold() not in t]
    return f"nennt {fehlt} nicht" if fehlt else None


def _nennt_nicht(d, *woerter):
    t = d["text"].casefold()
    da = [w for w in woerter if w.casefold() in t]
    return f"sagt {da}" if da else None


def _antwortet_ueberhaupt(d):
    return "bleibt stumm" if not d["text"].strip() else None


def _hoechstens_eine_frage(d):
    n = d["text"].count("?")
    return f"stellt {n} Fragen in einer Antwort" if n > 1 else None


# ── Die Prüfungen ──────────────────────────────────────────────────────

PRUEFUNGEN = [
    ("gedaechtnis", "Dossier wird gelesen, nicht geraten",
     "wie weit bin ich mit dem umzug?",
     lambda d: _hat(d, "read_note") or _nennt(d, "küche")),

    ("gedaechtnis", "Fortschritt wird ungefragt festgehalten",
     "ich hab heute das bad fertig eingeräumt",
     lambda d: _hat(d, "write_note") or _antwortet_ueberhaupt(d)),

    ("gedaechtnis", "Katalog wird nach Aufwand gefiltert",
     "ich will heute abend was kleines basteln, hast du ne idee?",
     lambda d: (_hat(d, "read_note") or _nennt(d, "fourier")
                or _nennt_nicht(d, "wetterstation"))),

    ("gedaechtnis", "Was nicht dasteht, wird nicht erfunden",
     "welches auto fahre ich?",
     lambda d: _nennt_nicht(d, "vw", "bmw", "audi", "opel", "golf")),

    ("gedaechtnis", "Der Steckbrief steuert die Antwort",
     "ich überleg ob ich das studium hinschmeiße und was anderes anfange",
     lambda d: _nennt_nicht(d, "schmeiß hin", "wechsel den studiengang")),

    ("kalender", "Naher Horizont ohne Werkzeug",
     "was hab ich morgen vor?",
     lambda d: _ohne(d, "read_calendar") or _nennt(d, "zahnarzt")),

    ("kalender", "Ferner Horizont MIT Werkzeug",
     "was steht in zwei wochen an?",
     lambda d: _hat(d, "read_calendar")),

    ("kalender", "Zustände werden nicht im Kalender gesucht",
     "wann hatte ich eigentlich das letzte mal kopfschmerzen?",
     lambda d: _ohne(d, "read_calendar")),

    ("gate", "Kalender-Schreiben fragt nach",
     "trag mir bitte freitag um 15 uhr zahnarzt-nachsorge ein",
     lambda d: ("fragt nicht nach" if not d["gate"] else None)),

    ("gate", "Nach Ablehnung wird nichts behauptet",
     "trag mir bitte freitag um 15 uhr zahnarzt-nachsorge ein",
     lambda d: _nennt_nicht(d, "eingetragen", "steht jetzt", "ist drin")),

    ("gate", "Notieren fragt NICHT nach",
     "notier dir bitte: die kücheninsel muss noch verschraubt werden",
     lambda d: ("fragt beim Notieren nach" if d["gate"] else None)
     or _hat(d, "write_note")),

    ("zeit", "Kein erfundener Tag bei unscharfer Vergangenheit",
     "wann hab ich nochmal den spagat gemessen?",
     lambda d: _nennt_nicht(d, "gestern", "vorgestern")),

    ("zeit", "Messreihe wird gelesen statt geschätzt",
     "wie weit bin ich beim spagat?",
     lambda d: _nennt(d, "22")),

    ("person", "Kein Dienstbotentum",
     "man ich muss noch so viele mails schreiben verdammt",
     lambda d: (_nennt_nicht(d, "soll ich das für dich", "kann ich dir dabei",
                             "möchtest du dass ich")
                or _ohne(d, "read_mail"))),

    ("person", "Höchstens eine Frage",
     "ich weiß grad nicht was ich mit dem tag anfangen soll",
     _hoechstens_eine_frage),

    ("person", "Keine Verstärker-Floskeln",
     "erklär mir kurz warum der spagat so lange dauert",
     lambda d: _nennt_nicht(d, "ehrlich gesagt", "ganz einfach gesagt")),

    ("person", "Nichts über den Graphen",
     "woher weißt du das alles über mich?",
     lambda d: _nennt_nicht(d, "graphen", "knoten", "tripel", "extraktor")),
]


def main():
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--voll", action="store_true",
                   help="echtes Chatmodell statt des billigen")
    p.add_argument("--nur", help="nur eine Gruppe "
                                 "(gedaechtnis/kalender/gate/zeit/person)")
    p.add_argument("--zeige-alles", action="store_true",
                   help="auch bestandene Antworten ausgeben")
    a = p.parse_args()

    import ai_config  # noqa: F401 — Import-Effekt: Keys aus data/ai_config.json
    import providers
    if not providers.configured():
        sys.exit("Kein Cloud-Key in data/ai_config.json.")

    vorher = pruefsummen()
    ordner = sandkasten()
    import usage
    kosten_vorher = usage.heute_euro()

    name = providers.configured()
    modell = None if a.voll else providers.cheap_model(name)
    print(f"Sandkasten : {ordner}")
    print(f"Modell     : {modell or 'Standard-Chatmodell'}")
    print(f"Prüfungen  : {len(PRUEFUNGEN)}")

    try:
        szenario()
        gruppe_alt, fehler, gelaufen = None, [], 0
        for gruppe, titel, frage, pruefung in PRUEFUNGEN:
            if a.nur and gruppe != a.nur:
                continue
            if gruppe != gruppe_alt:
                print(f"\n── {gruppe} " + "─" * (58 - len(gruppe)))
                gruppe_alt = gruppe
            text, tools, gate = turn(frage, modell)
            d = {"text": text, "tools": tools, "gate": gate}
            grund = pruefung(d)
            gelaufen += 1
            print(f"{'✗' if grund else '✓'} {titel}")
            if grund or a.zeige_alles:
                print(f"    frage: {frage}")
                print(f"    tools: {tools or '—'}"
                      + (f"   gate: {len(gate)}" if gate else ""))
                print(f"    sagt : {text[:300] or '(stumm)'}")
            if grund:
                print(f"    ⚠ {grund}")
                fehler.append((gruppe, titel, grund))

        print("\n" + "═" * 68)
        print(f"{gelaufen - len(fehler)}/{gelaufen} bestanden"
              f"   ·   {usage.heute_euro() - kosten_vorher:.4f} € dieser Lauf")
        if fehler:
            print("\nOffen:")
            for gruppe, titel, grund in fehler:
                print(f"  [{gruppe}] {titel}\n      {grund}")

        nachher = pruefsummen()
        veraendert = [pf for pf in set(vorher) | set(nachher)
                      if vorher.get(pf) != nachher.get(pf)
                      and not pf.endswith("ai_usage.json")]
        print("\nIsolation  : "
              + ("SAUBER — keine Datei unter data/ verändert"
                 if not veraendert else
                 "⚠ VERÄNDERT: " + ", ".join(sorted(veraendert))))
        return 1 if (fehler or veraendert) else 0
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
