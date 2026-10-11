# core/tabelle_formel.py
#
# Excel-Formeln: in der Datei stehen sie IMMER im Excel-Standard — englische
# Funktionsnamen, Komma als Trenner, Punkt als Dezimalzeichen (so speichert
# auch das deutsche Excel; die Anzeige übersetzt erst beim Öffnen). Die KI
# und Sasha denken oft deutsch („=SUMMEWENN(C:C;"bezahlt";B:B)", Gespräch
# 20261011-081303) — das wird hier SICHER übersetzt: nur bekannte Namen, nur
# außerhalb von Text in Anführungszeichen, und jeder Funktionsname muss
# danach eine echte Excel-Funktion sein. Sonst Abbruch mit Grund, nie ein
# stilles „#NAME?" in Sashas Tabelle.
#
# Entscheidung 2026-10-11: übersetzen statt englische verlangen — die KI
# schreibt im Gespräch deutsch, und ein Abbruch bei jeder SUMME wäre ein
# Werkzeug, das an der KI scheitert statt ihr zu helfen.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): reiner Text.

import re

MAX_LAENGE = 8192                 # Excel: höchstens 8.192 Zeichen je Formel

# Deutsch → Englisch (die gängigen; Sasha: Kosten, Summen, Bedingungen, Datum).
DEUTSCH = {
    "SUMME": "SUM", "SUMMEWENN": "SUMIF", "SUMMEWENNS": "SUMIFS",
    "SUMMENPRODUKT": "SUMPRODUCT", "PRODUKT": "PRODUCT",
    "WENN": "IF", "WENNFEHLER": "IFERROR", "WENNS": "IFS", "UND": "AND", "ODER": "OR",
    "NICHT": "NOT", "WAHR": "TRUE", "FALSCH": "FALSE",
    "MITTELWERT": "AVERAGE", "MITTELWERTWENN": "AVERAGEIF", "MITTELWERTWENNS": "AVERAGEIFS",
    "ANZAHL": "COUNT", "ANZAHL2": "COUNTA", "ANZAHLLEEREZELLEN": "COUNTBLANK",
    "ZÄHLENWENN": "COUNTIF", "ZÄHLENWENNS": "COUNTIFS",
    "RUNDEN": "ROUND", "AUFRUNDEN": "ROUNDUP", "ABRUNDEN": "ROUNDDOWN",
    "GANZZAHL": "INT", "KÜRZEN": "TRUNC", "REST": "MOD", "WURZEL": "SQRT", "POTENZ": "POWER",
    "MAXWENNS": "MAXIFS", "MINWENNS": "MINIFS", "KGRÖSSTE": "LARGE", "KKLEINSTE": "SMALL",
    "RANG": "RANK",
    "HEUTE": "TODAY", "JETZT": "NOW", "DATUM": "DATE", "JAHR": "YEAR", "MONAT": "MONTH",
    "TAG": "DAY", "STUNDE": "HOUR", "WOCHENTAG": "WEEKDAY", "KALENDERWOCHE": "WEEKNUM",
    "EDATUM": "EDATE", "MONATSENDE": "EOMONTH", "NETTOARBEITSTAGE": "NETWORKDAYS",
    "SVERWEIS": "VLOOKUP", "WVERWEIS": "HLOOKUP", "XVERWEIS": "XLOOKUP",
    "VERGLEICH": "MATCH", "XVERGLEICH": "XMATCH",
    "VERKETTEN": "CONCATENATE", "TEXTKETTE": "CONCAT", "TEXTVERKETTEN": "TEXTJOIN",
    "LINKS": "LEFT", "RECHTS": "RIGHT", "TEIL": "MID", "LÄNGE": "LEN", "GROSS": "UPPER",
    "KLEIN": "LOWER", "GLÄTTEN": "TRIM", "WERT": "VALUE", "WECHSELN": "SUBSTITUTE",
    "ISTLEER": "ISBLANK", "ISTZAHL": "ISNUMBER", "ISTFEHLER": "ISERROR", "ISTTEXT": "ISTEXT",
    "ZEILE": "ROW", "SPALTE": "COLUMN", "EINDEUTIG": "UNIQUE", "SORTIEREN": "SORT",
    "TEILERGEBNIS": "SUBTOTAL",
}

# Neuere Funktionen stehen in der Datei mit „_xlfn." davor — sonst zeigt
# Excel „#NAME?". openpyxl kennt sie nicht, deshalb hier.
NEU = {"XLOOKUP", "XMATCH", "UNIQUE", "FILTER", "SORT", "SORTBY", "SEQUENCE", "CONCAT",
       "TEXTJOIN", "IFS", "SWITCH", "MAXIFS", "MINIFS", "LET", "IFNA"}

_NAME = re.compile(r"(?<![A-Za-z0-9_.ÄÖÜäöüß$!])(_xlfn\.)?([A-Za-zÄÖÜäöüß][A-Za-z0-9_.ÄÖÜäöüß]*)\s*\(")
_WAHRHEIT = re.compile(r"(?<![A-Za-z0-9_.ÄÖÜäöüß$!:])(WAHR|FALSCH)(?![A-Za-z0-9_.(ÄÖÜäöüß])",
                       re.IGNORECASE)


class FormelFehler(ValueError):
    """Die Formel ließe sich nicht sicher speichern — der Text ist für die KI."""


def _bekannt() -> set:
    try:
        from openpyxl.utils.formulas import FORMULAE
        return set(FORMULAE) | NEU
    except ImportError:            # ohne openpyxl gibt es ohnehin keine xlsx
        return set(DEUTSCH.values()) | NEU


def _stuecke(formel: str):
    """[(text, in_anfuehrung)] — Text in "…" und Blattnamen in '…' bleiben
    unberührt ("" bzw. '' sind maskierte Anführungszeichen)."""
    raus, i, n, start = [], 0, len(formel), 0
    while i < n:
        z = formel[i]
        if z in "\"'":
            if start < i:
                raus.append((formel[start:i], False))
            j = i + 1
            while j < n:
                if formel[j] == z and j + 1 < n and formel[j + 1] == z:
                    j += 2
                    continue
                if formel[j] == z:
                    break
                j += 1
            if j >= n:
                raise FormelFehler(f"Anführungszeichen {z} nicht geschlossen")
            raus.append((formel[i:j + 1], True))
            i = start = j + 1
            continue
        i += 1
    if start < n:
        raus.append((formel[start:], False))
    return raus


def uebersetzen(formel: str) -> tuple:
    """„=SUMMEWENN(C:C;"bezahlt";B:B)" → („=SUMIF(C:C,"bezahlt",B:B)",
    ["SUMMEWENN→SUMIF"]). Wirft FormelFehler (Grund für die KI)."""
    f = str(formel or "").strip()
    if not f.startswith("="):
        raise FormelFehler("eine Formel beginnt mit =")
    if "\n" in f or "\r" in f:
        raise FormelFehler("eine Formel steht in einer Zeile")
    if len(f) > MAX_LAENGE:
        raise FormelFehler(f"zu lang (höchstens {MAX_LAENGE} Zeichen)")
    stuecke = _stuecke(f)
    deutsch_trenner = any(";" in t for t, quote in stuecke if not quote)
    bekannt, uebersetzt, unbekannt = _bekannt(), [], []

    def name(m):
        vorsatz, n = m.group(1), m.group(2)
        gross = n.upper()
        en = DEUTSCH.get(gross, gross)
        if en != gross:
            uebersetzt.append(f"{n}→{en}")
        if en not in bekannt:
            unbekannt.append(n)
        return ("_xlfn." if (en in NEU or vorsatz) else "") + en + "("

    raus = []
    for text, quote in stuecke:
        if quote:
            raus.append(text)
            continue
        text = _NAME.sub(name, text)
        text = _WAHRHEIT.sub(lambda m: {"WAHR": "TRUE", "FALSCH": "FALSE"}[m.group(1).upper()],
                             text)
        if deutsch_trenner:
            text = re.sub(r"(?<=\d),(?=\d)", ".", text)    # 2,5 → 2.5
            text = text.replace(";", ",")
        raus.append(text)
    if unbekannt:
        raise FormelFehler("diese Funktion kennt Excel nicht: " + ", ".join(sorted(set(unbekannt)))
                           + " (englische Namen wie SUM, SUMIF, IF — oder die deutschen "
                             "wie SUMME, SUMMEWENN, WENN)")
    if deutsch_trenner:
        uebersetzt.append("; → ,")
    return "".join(raus), uebersetzt


def anzeigen(formel: str) -> str:
    """Für die KI lesbar: ohne „_xlfn."."""
    return str(formel).replace("_xlfn.", "")
