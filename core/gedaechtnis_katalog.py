# core/gedaechtnis_katalog.py
#
# Katalog-Einträge als TEXT: lesen, rendern, ersetzen-oder-anhängen (upsert),
# dazu die Vorlagen. Reine Funktionen ohne Dateisystem — wo die Kataloge
# liegen, weiß core/gedaechtnis.py (seit 2026-10-11 nach Thema,
# themen/<thema>/<name>.katalog.md).
#
# Herausgelöst am 2026-10-11 aus core/gedaechtnis.py, als das Gedächtnis nach
# Themen umzog: die Datei wäre sonst über die Riesen-Grenze gewachsen, und
# diese Hälfte hat mit Pfaden nichts zu tun.
#
# ── Was man LESEN will, wird Prosa. Was man DURCHSEHEN will, wird Katalog ─
# Sasha hat tausende Maker-Ideen; pro Idee ein Dossier wäre unlesbar. Ein
# Katalog-Eintrag ist in zwanzig Sekunden getippt und in einem Rutsch zu
# scannen:
#
#   ## Fourier-Visualisierer aufm Oszi
#   - thema:     fourier, frequenzen, signale
#   - equipment: arduino, dac, loetkolben
#   - aufwand:   klein
#   - status:    idee
#   - dossier:   -
#
# Wird eine Sache ernst, bekommt sie ein DOSSIER, dessen Kopf GENAU dieser
# Block ist — der Code trägt ihn in den Katalog ein (gedaechtnis.
# katalog_abgleichen). Zwei Dinge synchron zu halten geht auf Dauer schief;
# eines kann nicht von sich selbst abweichen. Verbindungen entstehen über
# geteilte `thema`-Stichworte, die die Volltextsuche findet — kein Extraktor
# erfindet Beziehungen (daran ist der Konzept-Graph gescheitert).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import re

# Zustände eines Katalog-Eintrags. Sashas Schnitt, 18.08.2026.
STATUS = ("idee", "priorisiert", "queued", "in_schedule",
          "abgeschlossen", "pausiert")

# Felder eines Eintrags, in dieser Reihenfolge gerendert. `dossier` hinten,
# weil es der Code setzt und nicht der Mensch.
FELDER = ("katalog", "thema", "equipment", "aufwand", "status", "dossier")

_TITEL = re.compile(r"^##\s+(.+?)\s*$")
_FELD = re.compile(r"^-\s*([a-zA-Zaeoeue]+)\s*:\s*(.*?)\s*$")

VORLAGE_KATALOG = """# katalog

> Vorlage fuer einen Katalog-Eintrag. Kopieren, ausfuellen, mit write_note
> in den gewuenschten Katalog schreiben (z.B. name="ideen.katalog").
> Fuer eine Sache, die du ernsthaft verfolgst, nimm stattdessen die
> Dossier-Vorlage — deren Kopf ist genau dieser Block.

## <Titel>
- katalog:   ideen
- thema:     <stichworte, kommagetrennt>
- equipment: <was es braucht, oder ->
- aufwand:   klein | mittel | gross
- status:    idee | priorisiert | queued | in_schedule | abgeschlossen | pausiert
"""

VORLAGE_DOSSIER = """# dossier

> Vorlage fuer ein Dossier (art: dossier). Der KOPF ist zugleich der
> Katalog-Eintrag: der Code zieht ihn heraus, ergaenzt `dossier:` selbst und
> traegt ihn in den unter `katalog:` genannten Katalog ein.
>
> Alles unter dem Kopf ist Prosa: schreib in Saetzen, nicht in Stichworten.

## <Titel>
- katalog:   ideen
- thema:     <stichworte, kommagetrennt>
- equipment: <was es braucht, oder ->
- aufwand:   klein | mittel | gross
- status:    priorisiert

## Ziel
<was am Ende dastehen soll>

## Stand
<wo es gerade steht, mit Datum>

## Naechster Schritt
<das eine, was als naechstes drankommt>

## Messreihe
<Name der Kurve, oder - wenn es nichts zu messen gibt>
"""

VORLAGEN = {"katalog": VORLAGE_KATALOG, "dossier": VORLAGE_DOSSIER}


def kopf_lesen(text: str) -> dict:
    """Den führenden Katalog-Block parsen: erste inhaltliche Zeile `## Titel`,
    darunter `- feld: wert`. Kein Kopf → {} (ein Dossier ohne Kopf ist
    erlaubt, es steht dann nur in keinem Katalog)."""
    if not isinstance(text, str):
        return {}
    zeilen = text.strip().splitlines()
    while zeilen and (not zeilen[0].strip() or zeilen[0].startswith("# ")):
        zeilen.pop(0)
    if not zeilen:
        return {}
    titel = _TITEL.match(zeilen[0])
    if not titel:
        return {}
    kopf = {"titel": titel.group(1)}
    for z in zeilen[1:]:
        feld = _FELD.match(z) if z.strip() else None
        if not feld:
            break
        kopf[feld.group(1).lower()] = feld.group(2)
    return kopf if len(kopf) > 1 else {}


def eintrag_rendern(kopf: dict) -> str:
    zeilen = [f"## {kopf.get('titel', '?')}"]
    breite = max(len(f) for f in FELDER) + 1
    for feld in FELDER:
        wert = (kopf.get(feld) or "").strip() or "-"
        zeilen.append(f"- {(feld + ':'):<{breite}} {wert}")
    return "\n".join(zeilen) + "\n"


def titel_liste(text: str) -> list:
    return [m.group(1).strip() for z in (text or "").splitlines()
            if (m := _TITEL.match(z))]


def hat_titel(text: str, titel: str) -> bool:
    ziel = (titel or "").strip().casefold()
    return any(t.casefold() == ziel for t in titel_liste(text))


def upsert(text: str, titel: str, eintrag: str) -> str:
    """Einen `## Titel`-Abschnitt ersetzen oder anhängen. Ersetzen ist der
    Punkt: ändert sich im Dossier der Status, zieht der Katalog nach, statt
    eine zweite Zeile daneben zu bekommen."""
    zeilen = (text or "").splitlines()
    start = next((i for i, z in enumerate(zeilen)
                  if (m := _TITEL.match(z)) and m.group(1).strip().casefold()
                  == titel.strip().casefold()), None)
    if start is None:
        rumpf = (text or "").rstrip()
        return ((rumpf + "\n\n" + eintrag) if rumpf else eintrag).rstrip() + "\n"
    ende = next((j for j in range(start + 1, len(zeilen)) if _TITEL.match(zeilen[j])),
                len(zeilen))
    neu = zeilen[:start] + eintrag.rstrip().splitlines() + [""] + zeilen[ende:]
    return "\n".join(neu).rstrip() + "\n"


def kopf_setzen(rumpf: str, neuer_kopf: str) -> str:
    """Den führenden Katalog-Block eines Textes ersetzen, Prosa behalten.
    Eine führende `# Titel`-Zeile fällt dabei weg (der Name steht im
    Datei-Kopf)."""
    zeilen = (rumpf or "").splitlines()
    i = 0
    while i < len(zeilen) and (not zeilen[i].strip() or zeilen[i].startswith("# ")):
        i += 1
    if i < len(zeilen) and _TITEL.match(zeilen[i]) and kopf_lesen("\n".join(zeilen[i:])):
        i += 1
        while i < len(zeilen) and (_FELD.match(zeilen[i]) or not zeilen[i].strip()):
            i += 1
    rest = "\n".join(zeilen[i:]).strip()
    return neuer_kopf.strip() + ("\n\n" + rest + "\n" if rest else "\n")


def verweise(text: str) -> list:
    """[(titel, dossier)] aller Einträge mit gesetztem `dossier:`."""
    raus, titel = [], None
    for z in (text or "").splitlines():
        m = _TITEL.match(z)
        if m:
            titel = m.group(1)
            continue
        feld = _FELD.match(z)
        if feld and feld.group(1).lower() == "dossier":
            ziel = feld.group(2).strip()
            if ziel and ziel != "-":
                raus.append((titel, ziel))
    return raus
