"""
Die Doku-Struktur bewachen.

Der alte flache Index war „massiv outdated": zwei Dateien standen gar nicht
drin, und niemand hat es gemerkt, weil nichts es geprüft hat. Ein Index, den
man von Hand pflegen MUSS und der still veralten KANN, veraltet.

Deshalb hier vier Regeln als Test:
  1. Jeder Bereichs-Ordner hat einen eigenen INDEX.md.
  2. Jede Datei in einem Bereich ist in dessen Index verlinkt.
  3. Der Haupt-Index verlinkt jeden Bereich.
  4. Jeder memory/-Verweis im ganzen Repo zeigt auf eine existierende Datei —
     auch aus Code-Kommentaren heraus.

Regel 4 ist die, die beim Verschieben weh tut, und genau deshalb steht sie hier.
"""
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "memory")

CODE_ENDUNGEN = (".md", ".py", ".html", ".js", ".sh", ".txt")
NICHT_BETRETEN = (".git", ".claude", "venv", "node_modules", "__pycache__",
                  "zentrale-new-design")
VERWEIS = re.compile(r"memory/[A-Za-z0-9_/]+\.md")


def bereiche():
    return sorted(d for d in os.listdir(MEM)
                  if os.path.isdir(os.path.join(MEM, d)) and not d.startswith("."))


def test_es_gibt_ueberhaupt_bereiche():
    assert bereiche(), "memory/ hat keine Bereichs-Ordner mehr"


@pytest.mark.parametrize("bereich", bereiche())
def test_jeder_bereich_hat_einen_index(bereich):
    assert os.path.exists(os.path.join(MEM, bereich, "INDEX.md")), \
        f"memory/{bereich}/ hat keinen INDEX.md"


@pytest.mark.parametrize("bereich", bereiche())
def test_jede_datei_steht_im_bereichs_index(bereich):
    """So ist der alte Index verrottet: Dateien kamen dazu, der Index nicht."""
    ordner = os.path.join(MEM, bereich)
    index = open(os.path.join(ordner, "INDEX.md"), encoding="utf-8").read()
    fehlend = [f for f in sorted(os.listdir(ordner))
               if f.endswith(".md") and f != "INDEX.md" and f not in index]
    assert not fehlend, \
        f"nicht in memory/{bereich}/INDEX.md verlinkt: {fehlend}"


def test_haupt_index_verlinkt_jeden_bereich():
    haupt = open(os.path.join(MEM, "INDEX.md"), encoding="utf-8").read()
    fehlend = [b for b in bereiche() if f"{b}/INDEX.md" not in haupt]
    assert not fehlend, f"nicht in memory/INDEX.md verlinkt: {fehlend}"


def test_haupt_index_verlinkt_die_flachen_dateien():
    haupt = open(os.path.join(MEM, "INDEX.md"), encoding="utf-8").read()
    flach = [f for f in sorted(os.listdir(MEM))
             if f.endswith(".md") and f != "INDEX.md"]
    fehlend = [f for f in flach if f not in haupt]
    assert not fehlend, f"flache Datei nicht im Haupt-Index: {fehlend}"


def test_kein_verweis_zeigt_ins_leere():
    """Beim Verschieben brechen Verweise aus Code-Kommentaren genauso wie die
    aus der Doku - sie fallen nur später auf."""
    tot = []
    for wurzel, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in NICHT_BETRETEN]
        for f in files:
            if not f.endswith(CODE_ENDUNGEN):
                continue
            pfad = os.path.join(wurzel, f)
            try:
                inhalt = open(pfad, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for treffer in VERWEIS.findall(inhalt):
                if not os.path.exists(os.path.join(ROOT, treffer)):
                    tot.append(f"{os.path.relpath(pfad, ROOT)} → {treffer}")
    assert not tot, "tote Doku-Verweise:\n  " + "\n  ".join(sorted(set(tot)))


def test_haupt_index_bleibt_ein_index():
    """Der Haupt-Index soll Bereiche nennen, nicht Themen. Wächst er wieder zur
    Themen-Tabelle, ist genau der Zustand zurück, gegen den umgebaut wurde."""
    haupt = open(os.path.join(MEM, "INDEX.md"), encoding="utf-8").read()
    tiefe_verweise = [t for t in VERWEIS.findall(haupt)
                      if t.count("/") >= 2 and not t.endswith("INDEX.md")]
    assert not tiefe_verweise, \
        f"Haupt-Index verlinkt einzelne Themen statt Bereiche: {tiefe_verweise}"
