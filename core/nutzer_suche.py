# core/nutzer_suche.py
#
# Suchen und Auflisten im Nutzerordner (core/nutzer_ordner.py: Input/,
# Output/) — für find_files, search_files und list_files auf gross.
#
# 2026-10-09, Sasha: „300 einträge dateiliste soll was sein? schließlich
# findest du dateien nich durch listen, sondern einfach mit.. grep magic. und
# wie machst du die regel gegen falsche nicht da meldungen?" Darum:
#   - find_files sucht nach Namen mit Platzhaltern (wie find),
#   - search_files nach Text in Dateien (wie grep),
#   - list_files zeigt EINEN Ordner (wie ls), keinen ganzen Baum,
# und JEDE Suche sagt, wie vollständig sie war: durchsuchte Ordner, Zahl der
# Dateien, „Suche vollständig: N Treffer" oder „Suche NICHT vollständig:
# abgebrochen nach …". Diese Zeile steht immer GANZ VORN und in fester Form —
# der Prüfer „nicht da" (core/ehrlichkeit.py) liest sie: „gibt es nicht" darf
# die KI nur nach einer vollständigen Suche ohne Treffer sagen.
#
# Gesperrt wie bei read_file: versteckte Dateien/Ordner und Dateien, die nach
# Schlüssel aussehen (context._is_secret).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import fnmatch
import os
from dataclasses import dataclass

import context
import nutzer_ordner

MAX_NAMEN = 50              # find_files zeigt so viele, zählt aber alle
MAX_TEXT_TREFFER = 100      # search_files bricht danach ab
MAX_DATEI_BYTES = 2 * 1024 * 1024   # größere Dateien durchsucht search_files nicht
MAX_GANG = 20_000           # so viele Dateien läuft eine Suche höchstens ab
MAX_LISTE = 200             # list_files zeigt so viele Einträge eines Ordners
AUSZUG = 160                # Zeichen je Trefferzeile

VOLL = "Suche vollständig"
NICHT_VOLL = "Suche NICHT vollständig"


@dataclass
class Ergebnis:
    text: str
    vollstaendig: bool
    treffer: int
    fehler: bool = False


class _Fehler(Exception):
    pass


def _startorte(ordner) -> list:
    """Wo gesucht wird: ohne Angabe Input/ und Output/, sonst der genannte
    Ordner darin (nie hinaus)."""
    if not str(ordner or "").strip():
        return [nutzer_ordner.unterordner(u) for u in nutzer_ordner.UNTERORDNER]
    pfad = nutzer_ordner.aufloesen(ordner)
    if pfad is None:
        raise _Fehler(f"[Fehler: „{ordner}“ liegt nicht in Input/ oder Output/ — "
                      f"gesucht wird nur dort]")
    if not os.path.isdir(pfad):
        raise _Fehler(f"[Fehler: Ordner „{ordner}“ gibt es nicht in Input/ oder Output/]")
    return [pfad]


def _gesperrt(name: str) -> bool:
    return name.startswith(".") or context._is_secret(name)


def _ablaufen(orte: list):
    """-> (pfad, ist_ordner) für alles Sichtbare unter den Orten."""
    for ort in orte:
        for wo, ordner, dateien in os.walk(ort):
            ordner[:] = sorted(o for o in ordner if not _gesperrt(o)
                               and not os.path.islink(os.path.join(wo, o)))
            for o in ordner:
                yield os.path.join(wo, o), True
            for d in sorted(dateien):
                if not _gesperrt(d):
                    yield os.path.join(wo, d), False


def _orte_text(orte: list, dateien: int) -> str:
    namen = ", ".join(nutzer_ordner.anzeige(o).rstrip("/") + "/" for o in orte)
    return f"durchsucht: {namen} ({dateien} Dateien)"


def _groesse(pfad: str) -> str:
    try:
        return f"{max(1, round(os.path.getsize(pfad) / 1024))} KB"
    except OSError:
        return "?"


def _passt_name(name: str, muster: str) -> bool:
    n = name.casefold()
    m = muster.casefold()
    if any(z in m for z in "*?["):
        return fnmatch.fnmatchcase(n, m)
    # Ohne Platzhalter: Namensteil; Trenner egal („chefkoch-ai" ~ „Chefkoch ai").
    flach = lambda t: "".join(z for z in t if z not in " -_.")  # noqa: E731
    return m in n or (flach(m) and flach(m) in flach(n))


def finden(muster: str, ordner: str = "") -> Ergebnis:
    """Dateien und Ordner nach Namen: `*.zip`, `*chefkoch*` oder ein
    Namensteil. Zeigt höchstens MAX_NAMEN, zählt alle."""
    muster = str(muster or "").strip()
    if not muster:
        return Ergebnis("[Fehler: kein Name oder Muster angegeben, z. B. '*.zip']", False, 0, True)
    try:
        orte = _startorte(ordner)
    except _Fehler as e:
        return Ergebnis(str(e), False, 0, True)
    treffer, dateien, abbruch = [], 0, ""
    for pfad, ist_ordner in _ablaufen(orte):
        if not ist_ordner:
            dateien += 1
            if dateien > MAX_GANG:
                abbruch = f"abgebrochen nach {MAX_GANG} Dateien"
                break
        if _passt_name(os.path.basename(pfad), muster):
            treffer.append((pfad, ist_ordner))
    treffer.sort(key=lambda t: (t[0].count(os.sep), t[0].casefold()))
    if abbruch:
        kopf = f"{NICHT_VOLL}: {abbruch} — {_orte_text(orte, dateien - 1)}. Bis dahin {len(treffer)} Treffer."
    else:
        kopf = f"{VOLL}: {len(treffer)} Treffer — {_orte_text(orte, dateien)}."
    zeilen = [kopf]
    for pfad, ist_ordner in treffer[:MAX_NAMEN]:
        zeilen.append(f"  {nutzer_ordner.anzeige(pfad)}/  (Ordner)" if ist_ordner
                      else f"  {nutzer_ordner.anzeige(pfad)}  ({_groesse(pfad)})")
    if len(treffer) > MAX_NAMEN:
        zeilen.append(f"  … {len(treffer) - MAX_NAMEN} weitere Treffer nicht gezeigt — "
                      f"Muster genauer fassen oder ordner angeben.")
    return Ergebnis("\n".join(zeilen), not abbruch, len(treffer))


def _ist_binaer(kopf: bytes) -> bool:
    return b"\x00" in kopf


def textsuche(text: str, ordner: str = "", muster: str = "") -> Ergebnis:
    """Text in Dateien, wie grep -i -F: Groß/Klein egal, feste Zeichenkette.
    Treffer als „pfad:zeile: auszug". Binärdateien zählen als übersprungen
    (kein Text — die Suche bleibt vollständig); Dateien über MAX_DATEI_BYTES
    werden nicht durchsucht, dann ist die Suche NICHT vollständig."""
    nadel = str(text or "")
    if not nadel.strip():
        return Ergebnis("[Fehler: kein Text zum Suchen angegeben]", False, 0, True)
    try:
        orte = _startorte(ordner)
    except _Fehler as e:
        return Ergebnis(str(e), False, 0, True)
    nadel_k = nadel.casefold()
    muster = str(muster or "").strip()
    treffer, dateien, binaer, zu_gross, abbruch = [], 0, 0, 0, ""
    for pfad, ist_ordner in _ablaufen(orte):
        if ist_ordner:
            continue
        if muster and not _passt_name(os.path.basename(pfad), muster):
            continue
        dateien += 1
        if dateien > MAX_GANG:
            dateien -= 1
            abbruch = f"abgebrochen nach {MAX_GANG} Dateien"
            break
        try:
            if os.path.getsize(pfad) > MAX_DATEI_BYTES:
                zu_gross += 1
                continue
            with open(pfad, "rb") as f:
                roh = f.read()
        except OSError:
            zu_gross += 1                 # nicht lesbar: ehrlich als nicht durchsucht
            continue
        if _ist_binaer(roh[:8192]):
            binaer += 1
            continue
        for nr, zeile in enumerate(roh.decode("utf-8", errors="replace").splitlines(), 1):
            if nadel_k in zeile.casefold():
                auszug = " ".join(zeile.split())
                if len(auszug) > AUSZUG:
                    auszug = auszug[:AUSZUG - 1] + "…"
                treffer.append(f"  {nutzer_ordner.anzeige(pfad)}:{nr}: {auszug}")
                if len(treffer) >= MAX_TEXT_TREFFER:
                    abbruch = f"abgebrochen nach {MAX_TEXT_TREFFER} Treffern"
                    break
        if abbruch:
            break
    nebenbei = f" Übersprungen: {binaer} Binärdateien." if binaer else ""
    if abbruch:
        kopf = f"{NICHT_VOLL}: {abbruch} — {_orte_text(orte, dateien)}.{nebenbei}"
    elif zu_gross:
        kopf = (f"{NICHT_VOLL}: {zu_gross} Dateien über {MAX_DATEI_BYTES // 2**20} MB "
                f"oder unlesbar, nicht durchsucht — {_orte_text(orte, dateien)}. "
                f"{len(treffer)} Treffer im Rest.{nebenbei}")
    else:
        kopf = f"{VOLL}: {len(treffer)} Treffer — {_orte_text(orte, dateien)}.{nebenbei}"
    return Ergebnis("\n".join([kopf] + treffer), not (abbruch or zu_gross), len(treffer))


def auflisten(ordner: str = "") -> Ergebnis:
    """EIN Ordner wie ls: Unterordner mit „/", Dateien mit Größe. Ohne
    Angabe Input/."""
    try:
        pfad = _startorte(ordner or nutzer_ordner.INPUT)[0]
    except _Fehler as e:
        return Ergebnis(str(e), False, 0, True)
    try:
        namen = sorted(n for n in os.listdir(pfad) if not _gesperrt(n))
    except OSError as e:
        return Ergebnis(f"[Fehler: Ordner nicht lesbar ({e})]", False, 0, True)
    ordner_ = [n for n in namen if os.path.isdir(os.path.join(pfad, n))]
    dateien = [n for n in namen if n not in ordner_]
    eintraege = [f"  {n}/" for n in ordner_] + \
                [f"  {n}  ({_groesse(os.path.join(pfad, n))})" for n in dateien]
    name = nutzer_ordner.anzeige(pfad).rstrip("/") + "/"
    voll = len(eintraege) <= MAX_LISTE
    if voll:
        kopf = f"{name} — {len(eintraege)} Einträge, vollständig."
    else:
        kopf = (f"{name} — {len(eintraege)} Einträge, NICHT vollständig gezeigt "
                f"(erste {MAX_LISTE}); gezielt suchen mit find_files.")
    if not eintraege:
        kopf = f"{name} — leer."
    return Ergebnis("\n".join([kopf] + eintraege[:MAX_LISTE]), voll, len(eintraege))
