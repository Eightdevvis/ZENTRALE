# tui/ansichten/chat_layout.py
#
# Wie der Chat-Kasten aufgeteilt wird — nach dem Vorbild von Claude Web
# (Sasha, 07.10.2026: „das frontend für unsere ki soll lowk auch einfach
# claude web grad kopieren. natürlich in der tui und ihrem eigenen kantigeren
# stil"). Der Kasten bleibt, wie er ist („der kasten in der mitte is
# basically vollbild lass das so"); aufgeteilt wird sein Inneres.
#
# Skizze, breit (136×30 und mehr):
#
#   ┌ KI-CHAT · cloud (claude) · 0,12€ heute ─────────────────────────────────┐
#   │ ▣▣▣ Search      │ Fahrradschlauch flicken ▾         │ Outputs          × │
#   │ ▣▣▣ New         │                                   │ ┌──────────────┐   │
#   │ ▣▣▣ Projects    │          ┌──────────────────────┐ │ │Packliste     │   │
#   │ ▣▣▣ Files       │          │ wie flicke ich …     │ │ │- Ding 1      │   │
#   │ ▣▣▣ Customize   │          └──────────────────────┘ │ └──────────────┘   │
#   │                 │   Used memory ›                   │ Used in this sess. │
#   │ Today           │   Mit Flickzeug: Loch suchen, …   │  memory   fahrrad  │
#   │ ● Erinnerungen  │   copy · retry                    │                    │
#   │   Fahrradschl…  │  ┌─────────────────────────────┐  │                    │
#   │ Yesterday       │  │ Reply                       │  │                    │
#   │   Steuer… ▘     │  └─────────────────────────────┘  │                    │
#   │                 │   + attach        sonnet · low    │                    │
#   └─────────────────────────────────────────────────────────────────────────┘
#
# Schmal (80×24): Seitenleiste zu (nur eine Spalte Symbole), rechts nichts;
# ein Dokument oder die Outputs ERSETZEN den Verlauf, solange sie offen sind.
# Tab klappt die Seitenleiste auf — reicht der Platz daneben nicht, nimmt sie
# die ganze Breite (wie früher die Gesprächsliste).
#
# Reine Geometrie ohne curses (tests/test_chat_web.py). Ein Bereich ist
# (x, breite) oder None; zwischen zwei Bereichen steht eine Trennspalte „│".

from collections import namedtuple

Bereich = namedtuple("Bereich", "x w")
Aufteilung = namedtuple("Aufteilung", "seite leiste mitte rechts")

SEITE = 28              # offene Seitenleiste
LEISTE = 5              # zugeklappt: eine Spalte Symbole (3 breit + Rand)
LEISTE_AB = 60          # darunter nicht einmal die Symbole
OUTPUTS = 34            # rechte Leiste „Outputs"
MITTE_MIN = 38          # schmaler wird der Verlauf nie — dann ersetzt rechts ihn
DOKU_NEBEN_AB = 96      # so breit muss der Platz rechts der Seite sein, damit
                        # ein Dokument NEBEN dem Verlauf steht
TEXT_MAX = 92           # der Verlauf wird nicht breiter (lesbar, wie Claude)


def aufteilen(bx, bw, seite_offen=False, rechts=None, gross=False):
    """Das Innere des Kastens (bx, bw = Kasten mit Rahmen) aufteilen.
    rechts: None | "outputs" | "dokument"; gross: Dokument nimmt Mitte und
    rechts. -> Aufteilung(seite, leiste, mitte, rechts)."""
    x0, w = bx + 1, max(0, bw - 2)
    seite = leiste = mitte = rechts_b = None
    if seite_offen:
        if w - SEITE - 1 < MITTE_MIN:
            return Aufteilung(Bereich(x0, w), None, None, None)
        seite = Bereich(x0, SEITE)
        x0, w = x0 + SEITE + 1, w - SEITE - 1
    elif bw >= LEISTE_AB:
        leiste = Bereich(x0, LEISTE)
        x0, w = x0 + LEISTE + 1, w - LEISTE - 1
    if rechts == "dokument":
        if gross or w < DOKU_NEBEN_AB:
            return Aufteilung(seite, leiste, None, Bereich(x0, w))
        dw = (w * 11) // 20                      # das Dokument bekommt etwas mehr
        mw = w - dw - 1
        return Aufteilung(seite, leiste, Bereich(x0, mw), Bereich(x0 + mw + 1, dw))
    if rechts == "outputs":
        if w - OUTPUTS - 1 < MITTE_MIN:
            return Aufteilung(seite, leiste, None, Bereich(x0, w))
        mw = w - OUTPUTS - 1
        return Aufteilung(seite, leiste, Bereich(x0, mw), Bereich(x0 + mw + 1, OUTPUTS))
    mitte = Bereich(x0, w)
    return Aufteilung(seite, leiste, mitte, rechts_b)


def spalte(bereich, rand=2, hoechstens=TEXT_MAX):
    """Die Textspalte in einem Bereich: links/rechts `rand` Luft, nie
    breiter als `hoechstens`, dann mittig (wie Claude Web)."""
    if bereich is None:
        return None
    w = max(6, bereich.w - 2 * rand)
    if w > hoechstens:
        return Bereich(bereich.x + (bereich.w - hoechstens) // 2, hoechstens)
    return Bereich(bereich.x + rand, w)


def seite_auto(bw):
    """Ist die Seitenleiste von sich aus offen? Nur, wenn daneben noch ein
    bequemer Verlauf bleibt (Sasha, 07.10.: auf 80×24 zu)."""
    return bw - 2 - SEITE - 1 >= 2 * MITTE_MIN + 20
