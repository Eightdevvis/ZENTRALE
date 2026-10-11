"""
Keine Riesen-Dateien in memory/ — dasselbe Muster wie die Riesen im Code
(tests/test_kern_bauplan.py, „Altlast: Riesen").

Warum: memory/ki/ki_system.md war am 2026-10-11 auf 2.065 Zeilen gewachsen,
weil Agenten bei jeder Änderung einen Abschnitt an die Sammeldatei gehängt
haben. Eine Datei, die niemand mehr ganz liest, widerspricht sich still.

Die Regel steht in memory/doku_regeln.md (Regel 9): höchstens 600 Zeilen je
memory/**/*.md, ausgenommen memory/archive/. Wer heute drüber liegt, steht mit
seiner Zahl unter „Altlast: Riesen-Dateien" und darf nur SCHRUMPFEN: ist eine
erledigt, verlangt der Test, sie auszutragen. So kann die Liste nicht still
veralten.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEM = os.path.join(ROOT, "memory")
REGELN = os.path.join(MEM, "doku_regeln.md")

RIESE_DOKU = 600

# Archiv: abgelegte Dokumente, die nicht mehr wachsen.
UEBERSPRINGEN = ("archive",)


# ── Doku-Regeln lesen ──────────────────────────────────────────────────

def _abschnitt(ueberschrift):
    with open(REGELN, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"^##+ [^\n]*" + re.escape(ueberschrift) + r"[^\n]*\n", text, re.M)
    assert m, f"Abschnitt fehlt in memory/doku_regeln.md: {ueberschrift}"
    rest = text[m.end():]
    n = re.search(r"^##+ ", rest, re.M)
    return rest[:n.start()] if n else rest


def altlast_riesen():
    """'bereich/datei.md' → eingefrorene Zeilenzahl."""
    raus = {}
    for line in _abschnitt("Altlast: Riesen-Dateien").splitlines():
        if line.startswith("| `"):
            zellen = [z.strip() for z in line.strip().strip("|").split("|")]
            raus[re.findall(r"`([^`]+)`", zellen[0])[0]] = int(zellen[1].replace(".", ""))
    return raus


# ── memory/ lesen ──────────────────────────────────────────────────────

def doku_dateien():
    for w, ordner, dateien in os.walk(MEM):
        if os.path.relpath(w, MEM) == ".":
            ordner[:] = [o for o in ordner if o not in UEBERSPRINGEN]
        for f in dateien:
            if f.endswith(".md"):
                yield os.path.join(w, f)


def riesen_in_memory():
    """'bereich/datei.md' → Zeilen, für alle über der Grenze."""
    raus = {}
    for pfad in doku_dateien():
        with open(pfad, encoding="utf-8") as f:
            n = f.read().count("\n")
        if n > RIESE_DOKU:
            raus[os.path.relpath(pfad, MEM)] = n
    return raus


def zeilen(rel):
    pfad = os.path.join(MEM, rel)
    if not os.path.exists(pfad):
        return None
    with open(pfad, encoding="utf-8") as f:
        return f.read().count("\n")


# ── Tests ──────────────────────────────────────────────────────────────

def test_die_altlasten_liste_ist_lesbar():
    assert altlast_riesen(), (
        "Unter 'Altlast: Riesen-Dateien' in memory/doku_regeln.md steht keine "
        "Zeile. Ist die Liste leer, weil alles zerlegt ist: diesen Test löschen "
        "oder umschreiben — nicht still grün werden lassen.")


def test_keine_neuen_riesen():
    bekannt = altlast_riesen()
    neu = {k: v for k, v in riesen_in_memory().items() if k not in bekannt}
    assert not neu, (
        f"Neu über der Grenze ({RIESE_DOKU} Zeilen):\n  " +
        "\n  ".join(f"memory/{k}: {v}" for k, v in sorted(neu.items())) +
        "\nAufteilen, bevor es weitergeht: neues Thema = eigene Datei + Zeile "
        "im INDEX.md des Bereichs; die alte Datei bekommt nur einen Verweis "
        "(memory/doku_regeln.md, Regel 9). Nicht auf die Altlasten-Liste setzen.")


def test_riesen_wachsen_nicht():
    gewachsen = {}
    for k, grenze in altlast_riesen().items():
        ist = zeilen(k)
        if ist is not None and ist > grenze:
            gewachsen[k] = (ist, grenze)
    assert not gewachsen, (
        "Eingefrorene Riesen-Dateien sind gewachsen:\n  " +
        "\n  ".join(f"memory/{k}: {ist} statt höchstens {g}"
                    for k, (ist, g) in sorted(gewachsen.items())) +
        "\nDas Neue gehört in eine eigene Datei (Regel 9); die Riesen werden "
        "nur noch kleiner.")


def test_geschrumpfte_riesen_senken_ihre_grenze():
    kleiner = {}
    for k, grenze in altlast_riesen().items():
        ist = zeilen(k)
        if ist is None or ist < grenze:
            kleiner[k] = (ist, grenze)
    assert not kleiner, (
        "Gut gemacht — kleiner geworden. In memory/doku_regeln.md unter "
        "'Altlast: Riesen-Dateien' die Grenze senken (oder die Zeile "
        "streichen, wenn unter der Grenze oder die Datei weg ist):\n  " +
        "\n  ".join(
            f"memory/{k}: " +
            ("streichen (Datei weg)" if ist is None else
             "streichen" if ist <= RIESE_DOKU else f"auf {ist}") +
            f" (steht {g})" for k, (ist, g) in sorted(kleiner.items())))
