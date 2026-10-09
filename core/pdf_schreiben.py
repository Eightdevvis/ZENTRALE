# core/pdf_schreiben.py
#
# Ein neues PDF aus Markdown: Überschriften, Absätze (auch **fett**), Listen,
# einfache Tabellen, Code, Seitenzahlen. A4, Helvetica.
#
# 2026-10-08, Skill pdf (memory/ki/pdf_word.md). Eigener kleiner Schreiber
# statt reportlab/fpdf2: beide brauchen Pillow (kein reines Python-Paket, auf
# dem Pi eigens zu bauen), und für Text, Tabellen und Seitenumbruch reichen
# die 14 Grundschriften, die jedes PDF-Programm eingebaut hat — nichts muss
# eingebettet werden. Die Zeichenbreiten (für den Zeilenumbruch) kommen aus
# pypdf (Adobes Core-14-Metriken); fehlen sie, wird geschätzt (Umbruch etwas
# ungenauer, das PDF bleibt gültig).
#
# Grenze, ehrlich gemeldet: die Grundschriften kennen nur westeuropäische
# Zeichen (Windows-1252: Umlaute, ß, €, „“, – …). Pfeile und Vergleiche
# werden umschrieben (→ wird ->), alles andere (Chinesisch, Emoji) wird „?"
# und gezählt — der Ausführer sagt es der KI.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import re
import zlib

import textbloecke as tb

SEITE_B, SEITE_H = 595.28, 841.89        # A4 in Punkt
RAND = 56.7                              # 2 cm
UNTEN = 64.0                             # Platz für die Seitenzahl
INNEN_B = SEITE_B - 2 * RAND

SCHRIFT = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Courier"}
NORMAL, FETT, FEST = "F1", "F2", "F3"
GROESSE = {"text": 11.0, 1: 18.0, 2: 14.0, 3: 12.0, "code": 9.0,
           "tabelle": 9.5, "fuss": 8.0}
ZEILE = 1.35                             # Zeilenabstand je Schriftgröße

# Was die Grundschriften nicht haben, aber gut umschreibbar ist.
_UMSCHREIBEN = {
    "→": "->", "←": "<-", "⇒": "=>", "⇐": "<=", "↔": "<->", "≤": "<=",
    "≥": ">=", "≠": "!=", "≈": "~", "✓": "v", "✔": "v", "✗": "x", "✘": "x",
    "−": "-", "\u2009": " ", "\u202f": " ", "\u200b": "", "\ufeff": "",
    "\t": "    ",
}

try:  # Breiten aus Adobes AFM-Dateien, in pypdf mitgeliefert (privat → vorsichtig)
    from pypdf._codecs.core_font_metrics import CORE_FONT_METRICS as _METRIK
except Exception:  # pragma: no cover — ohne pypdf geschätzt
    _METRIK = {}


def _breiten(name: str) -> dict:
    m = _METRIK.get(name)
    return dict(m.character_widths) if m is not None else {}


_BREITE = {k: _breiten(v) for k, v in SCHRIFT.items()}
_SCHAETZUNG = {NORMAL: 520, FETT: 570, FEST: 600}


def breite(text: str, schrift: str, groesse: float) -> float:
    tabelle = _BREITE.get(schrift) or {}
    if schrift == FEST:
        return len(text) * 0.6 * groesse
    std = tabelle.get("default") or _SCHAETZUNG[schrift]
    return sum(tabelle.get(z, std) for z in text) * groesse / 1000.0


# ── Zeichen ─────────────────────────────────────────────────────────────

class _Zaehler:
    def __init__(self):
        self.ersetzt = 0
        self.beispiele = []

    def sauber(self, text: str) -> str:
        """Nur, was Windows-1252 kennt; der Rest wird umschrieben oder „?"."""
        raus = []
        for z in str(text):
            z = _UMSCHREIBEN.get(z, z)
            try:
                z.encode("cp1252")
                raus.append(z)
            except UnicodeEncodeError:
                self.ersetzt += 1
                if z not in self.beispiele and len(self.beispiele) < 8:
                    self.beispiele.append(z)
                raus.append("?")
        return "".join(raus)


def _pdf_text(text: str) -> bytes:
    """Ein Text als PDF-Zeichenkette (Windows-1252, Klammern geschützt)."""
    roh = text.encode("cp1252", "replace")
    roh = roh.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
    roh = roh.replace(b"\r", b"\\r").replace(b"\n", b"\\n")
    return b"(" + roh + b")"


# ── Zeilen umbrechen ────────────────────────────────────────────────────

def _woerter(stuecke: list, zaehler: _Zaehler) -> list:
    """[(text, fett)] → [(wort, schrift, leerzeichen_davor)]."""
    raus, luecke = [], False
    for text, fett in stuecke:
        schrift = FETT if fett else NORMAL
        for m in re.finditer(r"\S+|\s+", zaehler.sauber(text)):
            if m.group().isspace():
                luecke = True
            else:
                raus.append((m.group(), schrift, luecke))
                luecke = False
    return raus


def umbrechen(stuecke: list, max_b: float, groesse: float, zaehler: _Zaehler) -> list:
    """→ Zeilen, jede [(text, schrift)] mit zusammengelegten Stücken."""
    zeilen, zeile, b = [], [], 0.0
    leer = breite(" ", NORMAL, groesse)
    for wort, schrift, luecke in _woerter(stuecke, zaehler):
        wb = breite(wort, schrift, groesse)
        dazu = (leer if (luecke and zeile) else 0.0) + wb
        if zeile and b + dazu > max_b + 0.01:    # Rundung: genau passend passt
            zeilen.append(zeile)
            zeile, b, luecke, dazu = [], 0.0, False, wb
        if wb > max_b:                     # ein Wort breiter als die Zeile
            stueck = ""
            for z in wort:
                if stueck and breite(stueck + z, schrift, groesse) > max_b:
                    zeilen.append(zeile + [(stueck, schrift)] if zeile else [(stueck, schrift)])
                    zeile, stueck = [], ""
                stueck += z
            zeile, b = [(stueck, schrift)], breite(stueck, schrift, groesse)
            continue
        zeile.append(((" " if luecke and zeile else "") + wort, schrift))
        b += dazu
    if zeile:
        zeilen.append(zeile)
    # gleiche Schrift nebeneinander zusammenlegen
    fertig = []
    for z in zeilen:
        teile = []
        for text, schrift in z:
            if teile and teile[-1][1] == schrift:
                teile[-1] = (teile[-1][0] + text, schrift)
            else:
                teile.append((text, schrift))
        fertig.append(teile)
    return fertig or [[("", NORMAL)]]


# ── Seiten setzen ───────────────────────────────────────────────────────

class _Satz:
    def __init__(self):
        self.seiten = []
        self.zaehler = _Zaehler()
        self.y = 0.0
        self._neu()

    def _neu(self):
        self.seiten.append([])
        self.y = SEITE_H - RAND

    @property
    def ops(self) -> list:
        return self.seiten[-1]

    def platz(self, h: float) -> bool:
        """Passt h noch? Sonst neue Seite. -> True, wenn umgebrochen."""
        if self.y - h < UNTEN and self.y < SEITE_H - RAND - 1:
            self._neu()
            return True
        return False

    def zeile(self, x: float, teile: list, groesse: float, grau: float = 0.0):
        """Eine Textzeile; y ist die Oberkante, die Grundlinie liegt darunter."""
        grund = self.y - groesse * 0.95
        ops = [b"BT", b"%.3f g" % grau if grau else b"0 g",
               b"1 0 0 1 %.2f %.2f Tm" % (x, grund)]
        for text, schrift in teile:
            if text:
                ops.append(b"/%s %.2f Tf %s Tj" % (schrift.encode(), groesse, _pdf_text(text)))
        ops.append(b"ET")
        self.ops.append(b" ".join(ops))

    def linie(self, x1, y1, x2, y2, dicke=0.5, grau=0.0):
        self.ops.append(b"%.2f w %.3f G %.2f %.2f m %.2f %.2f l S"
                        % (dicke, grau, x1, y1, x2, y2))

    def flaeche(self, x, y, b, h, grau):
        self.ops.append(b"%.3f g %.2f %.2f %.2f %.2f re f 0 g" % (grau, x, y - h, b, h))

    # ── Blöcke ──
    def absatz(self, stuecke, x=RAND, max_b=INNEN_B, groesse=None, nach=None):
        groesse = groesse or GROESSE["text"]
        hoch = groesse * ZEILE
        for teile in umbrechen(stuecke, max_b, groesse, self.zaehler):
            self.platz(hoch)
            self.zeile(x, teile, groesse)
            self.y -= hoch
        self.y -= groesse * 0.5 if nach is None else nach

    def ueberschrift(self, text, ebene):
        groesse = GROESSE[ebene]
        if self.y < SEITE_H - RAND - 1:
            self.y -= groesse * 0.6
        # nicht allein unten auf der Seite stehen lassen
        self.platz(groesse * ZEILE * 2 + GROESSE["text"] * ZEILE * 2)
        stuecke = [(t, True) for t, _ in tb.stuecke(text)]
        self.absatz(stuecke, groesse=groesse, nach=groesse * 0.3)

    def liste(self, block):
        groesse = GROESSE["text"]
        for ebene, nummer, text in block.punkte:
            x = RAND + 16 * ebene
            marke = f"{nummer}." if nummer is not None else "•"
            einzug = max(14.0, breite(marke, NORMAL, groesse) + 6)
            zeilen = umbrechen(tb.stuecke(text), INNEN_B - (x - RAND) - einzug,
                               groesse, self.zaehler)
            hoch = groesse * ZEILE
            for i, teile in enumerate(zeilen):
                self.platz(hoch)
                if i == 0:
                    self.zeile(x, [(marke, NORMAL)], groesse)
                self.zeile(x + einzug, teile, groesse)
                self.y -= hoch
            self.y -= 1.5
        self.y -= groesse * 0.4

    def code(self, text):
        groesse = GROESSE["code"]
        hoch = groesse * 1.3
        zeichen = max(10, int((INNEN_B - 12) / (0.6 * groesse)))
        for roh in (text.split("\n") or [""]):
            roh = self.zaehler.sauber(roh)
            for i in range(0, max(1, len(roh)), zeichen):
                self.platz(hoch)
                self.flaeche(RAND, self.y, INNEN_B, hoch, 0.94)
                self.zeile(RAND + 6, [(roh[i:i + zeichen], FEST)], groesse)
                self.y -= hoch
        self.y -= GROESSE["text"] * 0.6

    def trennlinie(self):
        self.platz(12)
        self.y -= 4
        self.linie(RAND, self.y, RAND + INNEN_B, self.y, 0.6, 0.6)
        self.y -= 8

    def tabelle(self, block):
        groesse, pol = GROESSE["tabelle"], 4.0
        hoch = groesse * 1.3
        spalten = len(block.zeilen[0])
        natur = [0.0] * spalten
        for zi, reihe in enumerate(block.zeilen):
            for i, zelle in enumerate(reihe):
                schrift = FETT if (block.kopf and zi == 0) else NORMAL
                w = breite(self.zaehler.sauber(tb.klartext(zelle)), schrift, groesse)
                natur[i] = max(natur[i], min(w, INNEN_B * 0.6) + 2 * pol + 1)
        natur = [max(n, 24.0) for n in natur]
        summe = sum(natur)
        breiten = natur if summe <= INNEN_B else [n * INNEN_B / summe for n in natur]
        zellen = []
        for zi, reihe in enumerate(block.zeilen):
            fett = block.kopf and zi == 0
            zellen.append([umbrechen([(t, f or fett) for t, f in tb.stuecke(z)] or [("", fett)],
                                     max(8.0, breiten[i] - 2 * pol), groesse, self.zaehler)
                           for i, z in enumerate(reihe)])
        gesamt = sum(breiten)
        self.y -= 2

        def reihe_zeichnen(zi, von, n):
            oben = self.y
            h = n * hoch + 2 * pol
            if block.kopf and zi == 0:
                self.flaeche(RAND, oben, gesamt, h, 0.9)
            x = RAND
            for i, b in enumerate(breiten):
                self.y = oben - pol
                for teile in zellen[zi][i][von:von + n]:
                    self.zeile(x + pol, teile, groesse)
                    self.y -= hoch
                x += b
            unten = oben - h
            self.linie(RAND, oben, RAND + gesamt, oben)
            self.linie(RAND, unten, RAND + gesamt, unten)
            x = RAND
            for b in breiten + [0]:
                self.linie(x, oben, x, unten)
                x += b
            self.y = unten

        for zi in range(len(zellen)):
            noch = max(len(c) for c in zellen[zi])
            von = 0
            while noch > 0:
                frei = int((self.y - UNTEN - 2 * pol) // hoch)
                if frei < 1 or (von == 0 and frei < noch and noch * hoch < SEITE_H / 3):
                    self._neu()
                    if block.kopf and zi > 0:
                        reihe_zeichnen(0, 0, max(len(c) for c in zellen[0]))
                    frei = int((self.y - UNTEN - 2 * pol) // hoch)
                n = max(1, min(noch, frei))
                reihe_zeichnen(zi, von, n)
                von += n
                noch -= n
        self.y -= GROESSE["text"] * 0.8


def _setzen(markdown: str) -> _Satz:
    satz = _Satz()
    for b in tb.bloecke(markdown):
        if b.art == tb.UEBERSCHRIFT:
            satz.ueberschrift(b.text, b.ebene)
        elif b.art == tb.ABSATZ:
            satz.absatz(tb.stuecke(b.text))
        elif b.art == tb.LISTE:
            satz.liste(b)
        elif b.art == tb.TABELLE:
            satz.tabelle(b)
        elif b.art == tb.CODE:
            satz.code(b.text)
        elif b.art == tb.LINIE:
            satz.trennlinie()
    return satz


# ── Datei bauen ─────────────────────────────────────────────────────────

def _info_text(text: str) -> bytes:
    """Titel fürs Dokument-Info: ASCII wörtlich, sonst UTF-16 mit BOM."""
    text = " ".join(str(text or "").split())[:200]
    if all(32 <= ord(z) < 127 for z in text):
        return _pdf_text(text)
    return b"<FEFF" + text.encode("utf-16-be").hex().upper().encode() + b">"


def _datei(seiten: list, titel: str) -> bytes:
    """Die Objekte eines PDF 1.4 samt Querverweistabelle. Ohne Datum: gleiche
    Eingabe, gleiche Datei."""
    n = len(seiten)
    objekte = {}
    objekte[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kinder = " ".join(f"{7 + 2 * i} 0 R" for i in range(n)).encode()
    objekte[2] = b"<< /Type /Pages /Kids [" + kinder + b"] /Count %d >>" % n
    for nr, (kurz, name) in zip((3, 4, 5), SCHRIFT.items()):
        objekte[nr] = (b"<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                       b"/Encoding /WinAnsiEncoding >>" % name.encode())
    objekte[6] = b"<< /Title " + _info_text(titel) + b" /Producer (ZENTRALE) >>"
    for i, ops in enumerate(seiten):
        roh = zlib.compress(b"\n".join(ops), 9)
        objekte[7 + 2 * i] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.2f %.2f] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            b"/Contents %d 0 R >>" % (SEITE_B, SEITE_H, 8 + 2 * i))
        objekte[8 + 2 * i] = (b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(roh)
                              + roh + b"\nendstream")
    raus = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    lage = {}
    for nr in sorted(objekte):
        lage[nr] = len(raus)
        raus += b"%d 0 obj\n" % nr + objekte[nr] + b"\nendobj\n"
    xref = len(raus)
    groesste = max(objekte)
    raus += b"xref\n0 %d\n0000000000 65535 f \n" % (groesste + 1)
    for nr in range(1, groesste + 1):
        raus += b"%010d 00000 n \n" % lage[nr]
    raus += (b"trailer\n<< /Size %d /Root 1 0 R /Info 6 0 R >>\nstartxref\n%d\n%%%%EOF\n"
             % (groesste + 1, xref))
    return bytes(raus)


def erzeugen(titel: str, markdown: str) -> tuple:
    """Markdown → (pdf_bytes, {seiten, ersetzt, beispiele}). Leerer Inhalt
    wirft ValueError (ein leeres PDF ist nie gemeint)."""
    if not str(markdown or "").strip():
        raise ValueError("Leerer Inhalt — kein PDF erzeugt.")
    satz = _setzen(markdown)
    seiten = [s for s in satz.seiten if s] or [[]]
    n = len(seiten)
    for i, ops in enumerate(seiten):
        fuss = f"Seite {i + 1} von {n}"
        x = (SEITE_B - breite(fuss, NORMAL, GROESSE["fuss"])) / 2
        satz.seiten = [ops]
        satz.y = UNTEN - 30
        satz.zeile(x, [(fuss, NORMAL)], GROESSE["fuss"], grau=0.45)
    return _datei(seiten, titel), {"seiten": n, "ersetzt": satz.zaehler.ersetzt,
                                   "beispiele": satz.zaehler.beispiele}
