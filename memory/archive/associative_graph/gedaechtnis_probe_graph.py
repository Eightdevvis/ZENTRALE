#!/usr/bin/env python3
"""
ARCHIV — der Graph-Teil der Live-Probe `scripts/gedaechtnis_probe.py`.

Woher:  scripts/gedaechtnis_probe.py, Stand Commit 7e9229c (main, 2026-10-14).
        Herausgelöst am 2026-10-14 (Branch graph-archiv). Der Code unten ist
        WÖRTLICH übernommen, nur in diese Datei umsortiert; die Stücke aus
        main() stehen als Text in AUSZUG_MAIN.
Warum:  Der Konzept-Graph ist seit 2026-08-18 abgeschaltet. Falle 1
        („wann hatte ich eigentlich fieber?") und die drei Extraktions-Fallen
        prüfen Graph-Kontext und Graph-Extraktion — bei abgeschaltetem Graph
        melden sie nur Scheinfehler und kosten trotzdem Cent. Die Probe in
        scripts/ läuft weiter mit den Kalender-/Werkzeug-Fallen 2–5.
Läuft:  NICHT. Die Datei liegt nur zum Nachlesen und Zurückholen hier.

Wieder einschalten (Graph + diese Fallen):
  1. Graph an: Env ZENTRALE_GRAPH_KONTEXT=1 (Kontext in den Prompt,
     ki_prompt.GRAPH_KONTEXT) und ZENTRALE_GRAPH_EXTRAKTION=1 (neue
     Extraktionen, consolidation.GRAPH_EXTRAKTION). Code: core/graph.py,
     core/consolidation.py; Beschreibung: memory/ki/konzept_graph.md.
  2. Die Stücke unten zurück in scripts/gedaechtnis_probe.py: den Graph-Seed
     in szenario_bauen(), Falle 1 vorne in FAELLE, EXTRAKTIONS_FAELLE samt
     Hilfsfunktionen, und aus AUSZUG_MAIN die Option --nur, den
     Extraktions-Block und die Graph-Ausgabe bei --zeige-kontext.
  3. sandkasten() biegt cloud.CLOUD_GRAPH bereits in den Wegwerf-Ordner um —
     das muss so bleiben (eine frühere Probe hat Testknoten in Sashas echtem
     Cloud-Graphen hinterlassen).
"""
import os
import re
from datetime import date, timedelta

HEUTE  = date.today()
MORGEN = HEUTE + timedelta(days=1)
MONAT  = HEUTE.strftime("%Y-%m")
# Der Krankheits-Zeitraum liegt bewusst UNSCHARF im Graphen: nur der Monat.
# Genau daraus hat sie am 17.08.2026 ein "bis gestern" gemacht.

_TAG_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ── aus szenario_bauen(): der Graph-Seed ───────────────────────────────

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


# ── Falle 1 (Chat): der Krankheits-Tag ─────────────────────────────────

def _sucht_zustaende_nicht_im_kalender(text, tools):
    """Krankheiten stehen nicht im Kalender — dort danach zu suchen sind
    zwei volle Tool-Runden mit komplettem Praefix fuer garantiert nichts."""
    if tools:
        return (f"durchsucht den Kalender nach einem Zustand ({tools}) — "
                f"da steht garantiert nichts drin")
    return None


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


FALLE_1 = (
    ("Krankheits-Tag wird nicht erfunden",
     "wann hatte ich eigentlich fieber?",
     lambda t, w: (_kein_erfundener_tag(t, w) or _weiss_dass_es_august_war(t, w)
                   or _sucht_zustaende_nicht_im_kalender(t, w))),
)


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


_WOCHE_RE = re.compile(r"^\d{4}-W\d{2}$")


def _wochengenau(kanten):
    """Gröber als ein Tag — aber nicht gröber als nötig.

    "vor ein paar Tagen" ist wochengenau bekannt. Auf den ganzen Monat zu
    werfen verschenkt drei Wochen Genauigkeit, die man ehrlich hat.
    """
    schlimm = [k for k in kanten
               if k[1] == "geschah-am" and _TAG_RE.fullmatch(k[2])]
    if schlimm:
        return f"datiert auf einen TAG statt gröber: {schlimm}"
    zeit = [k for k in kanten if k[1] == "geschah-am"]
    if not zeit:
        return "datiert gar nicht — die Woche wäre bekannt gewesen"
    if not any(_WOCHE_RE.fullmatch(k[2]) for k in zeit):
        return f"gröber als nötig (Woche wäre bekannt): {zeit}"
    return None


def _heutiges_datum_da(kanten):
    heute = HEUTE.isoformat()
    if any(k[1] == "geschah-am" and k[2] == heute for k in kanten):
        return None
    return "datiert die Gegenwart NICHT auf heute — zu vorsichtig"


def _kein_sport_ereignis(kanten):
    schlimm = [k for k in kanten if k[0] == "Sport" and k[1] == "geschah-am"]
    return f"macht aus der Frage ein Ereignis: {schlimm}" if schlimm else None


EXTRAKTIONS_FAELLE = [
    ("Unscharfe Vergangenheit landet wochengenau, nicht auf heute",
     "ich hatte vor ein paar tagen ganz schlimmen schüttelfrost",
     "Klingt unangenehm. Ist es jetzt weg?",
     _wochengenau),

    ("Gegenwart wird ganz normal auf heute datiert",
     "ich hab grad fieber, mir ist total schlecht",
     "Dann leg dich hin. Misst du mal nach?",
     _heutiges_datum_da),

    ("Aus einer Frage wird kein Ereignis",
     "kann ich heute wieder sport machen?",
     "Kalendarisch steht nichts im Weg.",
     _kein_sport_ereignis),
]


# ── Stücke aus main() (wörtlich, nur als Text) ─────────────────────────

AUSZUG_MAIN = r'''
    p.add_argument("--nur", choices=["chat", "extraktion"])

    # … im Chat-Block, bei jedem Fehlschlag mit --zeige-kontext:
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
'''
