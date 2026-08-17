#!/usr/bin/env python3
"""
Live-Probe gegen das ECHTE Cloud-Modell: redet sie noch Müll?

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
Eigener Graph, eigener Kalender, eigenes Transkript in einem Wegwerf-Ordner.
`data/` wird NICHT angefasst — weder gelesen noch geschrieben. Der Grund
steht in der Projekt-Historie: eine frühere Probe hat ihre Testknoten in
Sashas echtem Cloud-Graphen hinterlassen.

── Was rausgeht ────────────────────────────────────────────────────────
Erfundene Testdaten (Fieber, Zahnarzt, Sport) plus der System-Prompt. Keine
echten Termine, keine echten Konzepte. Kosten: gut ein Dutzend kurze Calls,
Chat auf dem Chat-Modell, Extraktion auf dem billigen — Cent-Bereich.

    venv/bin/python scripts/gedaechtnis_probe.py
    venv/bin/python scripts/gedaechtnis_probe.py --nur extraktion
    venv/bin/python scripts/gedaechtnis_probe.py --zeige-kontext
"""
import argparse
import os
import re
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
MONAT  = HEUTE.strftime("%Y-%m")
# Der Krankheits-Zeitraum liegt bewusst UNSCHARF im Graphen: nur der Monat.
# Genau daraus hat sie am 17.08.2026 ein "bis gestern" gemacht.

_TAG_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ── Wegwerf-Umgebung ───────────────────────────────────────────────────

def sandkasten():
    """Graph, Kalender und Transkript in einen Temp-Ordner umbiegen.

    Muss VOR dem ersten Import von cloud/kalender passieren bzw. die
    Modul-Globals direkt überschreiben — die Pfade werden beim Import
    festgelegt.
    """
    ordner = tempfile.mkdtemp(prefix="zentrale_probe_")
    import kalender, cloud, transkript
    from pathlib import Path

    kalender.CAL_PATH = Path(ordner) / "kalender.json"
    cloud.CLOUD_GRAPH = os.path.join(ordner, "graph.json")
    for name in ("_DIR", "DIR", "TRANS_DIR", "_ORDNER"):
        if hasattr(transkript, name):
            setattr(transkript, name, os.path.join(ordner, "transkripte"))
    return ordner


def szenario_bauen():
    """Der Ausgangszustand, der den echten Fehler nachstellt.

    Kalender: heute NICHTS, morgen drei Termine, in sechs Tagen einer.
    Graph:    Krankheit nur auf den MONAT datiert, dazu ein Erzähltag-Anker.
    """
    import kalender, graph, cloud

    # Store wie im Betrieb anmelden, BEVOR geseedet wird — sonst legt der
    # Seed seine Knoten ohne Vektor an und wir würden nur den wörtlichen
    # Einstieg testen, nicht den echten Doppelweg.
    cloud.prepare_store()

    kalender.add_entry("termine", MORGEN.isoformat(), "Zahnarzt", time="09:00")
    kalender.add_entry("termine", MORGEN.isoformat(), "Fahrschule", time="19:00")
    kalender.add_entry("termine", (HEUTE + timedelta(days=6)).isoformat(),
                       "Geigenstunde", time="17:45")

    graph.add_turn_extraction(
        [{"name": n, "type": t} for n, t in [
            ("Sasha", "person"), ("Krankheit", "state"), ("Fieber", "state"),
            ("Schüttelfrost", "state"), ("Sport", "concept"),
            (MONAT, "time-month")]],
        [{"from": "Sasha", "to": "Krankheit", "rel": "fühlt"},
         {"from": "Krankheit", "to": "Fieber", "rel": "hat"},
         {"from": "Krankheit", "to": "Schüttelfrost", "rel": "hat"},
         # NUR der Monat — der Tag ist ehrlich unbekannt.
         {"from": "Fieber", "to": MONAT, "rel": "geschah-am"},
         {"from": "Sasha", "to": "Sport", "rel": "kann"}],
        store=cloud.CLOUD_GRAPH)


# ── Ein Turn fahren, mitschreiben was passiert ─────────────────────────

def turn(frage):
    """Eine Frage durchs echte Cloud-Backend. Gibt (text, tools) zurück."""
    import ai, cloud, state

    gerufen = []
    echt = ai._execute_tool

    def mitschreiben(name, args):
        gerufen.append(name)
        return echt(name, args)

    ai._execute_tool = mitschreiben
    state.wait_permission = lambda: "nein"      # nichts schreiben lassen
    state.request_permission = lambda **k: None
    try:
        text = ""
        for ev in cloud.chat_stream([{"role": "user", "content": frage}]):
            if isinstance(ev, str):
                text += ev
        return text.strip(), gerufen
    finally:
        ai._execute_tool = echt


# ── Die Fallen ─────────────────────────────────────────────────────────
#
# Jede: (Titel, Frage, Prüfung(text, tools) -> None | Grund)

def _kein_erfundener_tag(text, tools):
    """Sie darf den Krankheits-Tag nicht erfinden — er steht nirgends."""
    tage = set(_TAG_RE.findall(text))
    frei = {t for t in tage if not t.startswith(MONAT)}
    if frei:
        return f"nennt Tages-Daten, die nirgends stehen: {sorted(frei)}"
    for wort in ("gestern", "vorgestern"):
        if wort in text.lower():
            return f"behauptet einen konkreten Tag ({wort!r}), der unbekannt ist"
    return None


def _weiss_dass_es_august_war(text, tools):
    """Und sie muss trotzdem etwas sagen können — sonst ist der Kontext
    ein Käfig statt einer Auskunft."""
    monatsname = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                  "August", "September", "Oktober", "November",
                  "Dezember"][HEUTE.month - 1]
    if monatsname.lower() in text.lower() or MONAT in text:
        return None
    return "nennt den Monat nicht, obwohl er im Graphen steht"


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
    ("Krankheits-Tag wird nicht erfunden",
     "wann hatte ich eigentlich fieber?",
     lambda t, w: _kein_erfundener_tag(t, w) or _weiss_dass_es_august_war(t, w)),

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


# ── Extraktions-Fallen (die andere Hälfte) ─────────────────────────────
#
# Was sie SAGT, ist das eine. Was der Extraktor daraus in den Graphen
# schreibt, ist das andere — und genau das hat den Schaden angerichtet.

def kanten_aus(user_text, ai_text):
    """Einen Turn verdichten und die frisch entstandenen Kanten liefern."""
    import json, consolidation, cloud

    vorher = set()
    if os.path.exists(cloud.CLOUD_GRAPH):
        with open(cloud.CLOUD_GRAPH, encoding="utf-8") as f:
            vorher = {(e["from"], e["rel"], e["to"])
                      for e in json.load(f)["edges"]}
    consolidation.extract_turn_into_graph(user_text, ai_text,
                                          store=cloud.CLOUD_GRAPH)
    with open(cloud.CLOUD_GRAPH, encoding="utf-8") as f:
        nachher = {(e["from"], e["rel"], e["to"])
                   for e in json.load(f)["edges"]}
    return nachher - vorher


def _kein_tages_datum(kanten):
    schlimm = [k for k in kanten
               if k[1] == "geschah-am" and _TAG_RE.fullmatch(k[2])]
    return f"datiert auf einen TAG statt gröber: {schlimm}" if schlimm else None


def _heutiges_datum_da(kanten):
    heute = HEUTE.isoformat()
    if any(k[1] == "geschah-am" and k[2] == heute for k in kanten):
        return None
    return "datiert die Gegenwart NICHT auf heute — zu vorsichtig"


def _kein_sport_ereignis(kanten):
    schlimm = [k for k in kanten if k[0] == "Sport" and k[1] == "geschah-am"]
    return f"macht aus der Frage ein Ereignis: {schlimm}" if schlimm else None


EXTRAKTIONS_FAELLE = [
    ("Unscharfe Vergangenheit wird nicht auf heute gestempelt",
     "ich hatte vor ein paar tagen ganz schlimmen schüttelfrost",
     "Klingt unangenehm. Ist es jetzt weg?",
     _kein_tages_datum),

    ("Gegenwart wird ganz normal auf heute datiert",
     "ich hab grad fieber, mir ist total schlecht",
     "Dann leg dich hin. Misst du mal nach?",
     _heutiges_datum_da),

    ("Aus einer Frage wird kein Ereignis",
     "kann ich heute wieder sport machen?",
     "Kalendarisch steht nichts im Weg.",
     _kein_sport_ereignis),
]


# ── Ablauf ─────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--nur", choices=["chat", "extraktion"])
    p.add_argument("--zeige-kontext", action="store_true",
                   help="bei jedem Fehlschlag den Kontext mit ausgeben")
    a = p.parse_args()

    import ai_config  # noqa: F401 — Import-Effekt: Keys aus data/ai_config.json
    import providers
    if not providers.configured():
        sys.exit("Kein Cloud-Key in data/ai_config.json — nichts zu proben.")

    ordner = sandkasten()
    print(f"Sandkasten: {ordner}")
    print(f"Anbieter:   {providers.configured()}\n")
    try:
        szenario_bauen()
        import cloud, usage
        vorher_kosten = usage.heute_euro()

        fehler = 0
        if a.nur != "extraktion":
            print("── Antworten " + "─" * 55)
            for titel, frage, pruefung in FAELLE:
                text, tools = turn(frage)
                grund = pruefung(text, tools)
                fehler += bool(grund)
                print(f"\n{'✗' if grund else '✓'} {titel}")
                print(f"    frage:  {frage}")
                print(f"    tools:  {tools or '—'}")
                print(f"    sagt:   {text[:400]}")
                if grund:
                    print(f"    PROBLEM: {grund}")
                    if a.zeige_kontext:
                        import graph
                        print("    kontext:\n" + graph.context_for_query(
                            frage, store=cloud.CLOUD_GRAPH, max_chars=1500))

        if a.nur != "chat":
            print("\n── Was in den Graphen geschrieben wird " + "─" * 29)
            for titel, user_text, ai_text, pruefung in EXTRAKTIONS_FAELLE:
                kanten = kanten_aus(user_text, ai_text)
                grund = pruefung(kanten)
                fehler += bool(grund)
                print(f"\n{'✗' if grund else '✓'} {titel}")
                print(f"    sasha:  {user_text}")
                for k in sorted(kanten):
                    print(f"            {k[0]} -[{k[1]}]-> {k[2]}")
                if grund:
                    print(f"    PROBLEM: {grund}")

        gesamt = (len(FAELLE) if a.nur != "extraktion" else 0) + \
                 (len(EXTRAKTIONS_FAELLE) if a.nur != "chat" else 0)
        print(f"\n{'─' * 68}\n{gesamt - fehler}/{gesamt} Fallen bestanden.")
        print(f"Kosten dieses Laufs: {usage.heute_euro() - vorher_kosten:.4f} €")
        return 1 if fehler else 0
    finally:
        shutil.rmtree(ordner, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
