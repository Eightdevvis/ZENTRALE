# core/textbloecke.py
#
# Ein kleines Markdown in Blöcke zerlegen: Überschriften, Absätze, Listen,
# Tabellen, Code, Linie — und Absätze in Stücke „normal/fett".
#
# 2026-10-08, Skills pdf und word (memory/ki/pdf_word.md). Die KI schreibt den
# Inhalt einer neuen PDF- oder Word-Datei als Markdown (das schreibt sie
# ohnehin am sichersten), und beide Schreiber bauen aus DENSELBEN Blöcken
# ihre Seiten. Zwei Zerleger liefen auseinander: dieselbe Tabelle sähe im
# PDF anders aus als im Word.
#
# Bewusst klein: was hier nicht steht (Bilder, Fußnoten, verschachtelte
# Tabellen), bleibt Text. Kursiv (*x*) wird nicht erkannt — ein einzelnes
# Sternchen ist in Rechnungen und Listen zu oft gemeint, wie es dasteht.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md), weiß nichts von Dateien.

import re
from dataclasses import dataclass, field

UEBERSCHRIFT = "ueberschrift"
ABSATZ = "absatz"
LISTE = "liste"
TABELLE = "tabelle"
CODE = "code"
LINIE = "linie"


@dataclass
class Block:
    art: str
    text: str = ""
    ebene: int = 0                  # Überschrift 1–3
    geordnet: bool = False          # Liste: 1. 2. 3. statt Punkte
    punkte: list = field(default_factory=list)   # Liste: [(ebene, nummer|None, text)]
    zeilen: list = field(default_factory=list)   # Tabelle: [[zelle, …], …]
    kopf: bool = False              # Tabelle: erste Zeile ist Kopf


_UEBERSCHRIFT = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_PUNKT = re.compile(r"^(\s*)[-*+•]\s+(.*)$")
_NUMMER = re.compile(r"^(\s*)(\d{1,4})[.)]\s+(.*)$")
_TRENNER = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LINIE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _zellen(zeile: str) -> list:
    """| a | b \\| c | → ["a", "b | c"]."""
    z = zeile.strip()
    if z.startswith("|"):
        z = z[1:]
    if z.endswith("|") and not z.endswith("\\|"):
        z = z[:-1]
    teile = re.split(r"(?<!\\)\|", z)
    return [t.strip().replace("\\|", "|") for t in teile]


def bloecke(text: str) -> list:
    """Markdown → [Block]. Leere Zeilen trennen Absätze; eine Zeile, die mit
    | beginnt, gehört zu einer Tabelle."""
    zeilen = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raus = []
    absatz = []

    def absatz_fertig():
        if absatz:
            raus.append(Block(ABSATZ, " ".join(z.strip() for z in absatz)))
            absatz.clear()

    i = 0
    while i < len(zeilen):
        zeile = zeilen[i]
        roh = zeile.strip()
        if roh.startswith("```"):
            absatz_fertig()
            code = []
            i += 1
            while i < len(zeilen) and not zeilen[i].strip().startswith("```"):
                code.append(zeilen[i].rstrip())
                i += 1
            raus.append(Block(CODE, "\n".join(code)))
            i += 1
            continue
        if not roh:
            absatz_fertig()
            i += 1
            continue
        m = _UEBERSCHRIFT.match(roh)
        if m:
            absatz_fertig()
            raus.append(Block(UEBERSCHRIFT, m.group(2), ebene=min(3, len(m.group(1)))))
            i += 1
            continue
        if _LINIE.match(roh) and not absatz:
            raus.append(Block(LINIE))
            i += 1
            continue
        if roh.startswith("|"):
            absatz_fertig()
            tab = []
            kopf = False
            while i < len(zeilen) and zeilen[i].strip().startswith("|"):
                if _TRENNER.match(zeilen[i]):
                    kopf = kopf or len(tab) == 1
                else:
                    tab.append(_zellen(zeilen[i]))
                i += 1
            breite = max(len(r) for r in tab) if tab else 0
            tab = [r + [""] * (breite - len(r)) for r in tab]
            if tab:
                raus.append(Block(TABELLE, zeilen=tab, kopf=kopf))
            continue
        if _PUNKT.match(zeile) or _NUMMER.match(zeile):
            absatz_fertig()
            geordnet = bool(_NUMMER.match(zeile))
            punkte = []
            while i < len(zeilen):
                z = zeilen[i]
                mp, mn = _PUNKT.match(z), _NUMMER.match(z)
                if mn:
                    ebene = min(2, len(mn.group(1).expandtabs(4)) // 2)
                    punkte.append((ebene, int(mn.group(2)), mn.group(3).strip()))
                elif mp:
                    ebene = min(2, len(mp.group(1).expandtabs(4)) // 2)
                    punkte.append((ebene, None, mp.group(2).strip()))
                elif z.strip() and z.startswith((" ", "\t")) and punkte:
                    e, n, t = punkte[-1]          # Fortsetzungszeile
                    punkte[-1] = (e, n, t + " " + z.strip())
                else:
                    break
                i += 1
            raus.append(Block(LISTE, geordnet=geordnet, punkte=punkte))
            continue
        absatz.append(zeile)
        i += 1
    absatz_fertig()
    return raus


_FETT = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def stuecke(text: str) -> list:
    """Ein Absatz → [(text, fett)]. **fett** und __fett__ werden erkannt;
    `code` verliert die Striche, [text](url) wird „text (url)"."""
    text = _LINK.sub(lambda m: m.group(1) if m.group(1) == m.group(2)
                     else f"{m.group(1)} ({m.group(2)})", str(text or ""))
    text = re.sub(r"`([^`]+)`", r"\1", text)
    raus, pos = [], 0
    for m in _FETT.finditer(text):
        if m.start() > pos:
            raus.append((text[pos:m.start()], False))
        raus.append((m.group(1) or m.group(2), True))
        pos = m.end()
    if pos < len(text):
        raus.append((text[pos:], False))
    return [s for s in raus if s[0]]


def klartext(text: str) -> str:
    """Ein Absatz ohne Auszeichnung — für Belege und Vergleiche."""
    return "".join(t for t, _ in stuecke(text))
