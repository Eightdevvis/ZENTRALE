# core/ablage_suche.py
#
# Suchen und Auflisten in der Ablage — für find_files, search_files und
# list_files auf gross.
#
# 2026-10-11, Sasha: „ja einfach nur die ablage dann" — wie Claude Web gibt es
# EINEN Ort für Dateien, die Ablage (~/Zentrale/Ablage, core/ablage_sichtbar.py).
# Die Ordner Input/ und Output/ sind für die KI abgebaut; die Suche, die es
# dort gab (core/nutzer_suche.py, 2026-10-09), sucht jetzt hier. Geblieben
# ist ihr Versprechen: JEDE Suche sagt in fester Form ganz vorn, wie
# vollständig sie war („Suche vollständig: N Treffer — …" / „Suche NICHT
# vollständig: …"). Der Prüfer „nicht da" (core/ehrlichkeit.py) liest diese
# Zeile: „gibt es nicht" darf die KI nur nach einer vollständigen Suche ohne
# Treffer sagen.
#
# Durchsucht wird der Titel (find_files) bzw. der Text (search_files): bei
# Text-Dokumenten der Inhalt, bei PDF/Word/Excel der gelesene Text
# (core/ablage_text.py, gemerkt nach Inhalt). Bilder und Zips haben keinen
# Text — sie zählen als übersprungen, die Suche bleibt vollständig.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import fnmatch
import time
from dataclasses import dataclass

import ablage
import ablage_text

MAX_NAMEN = 50              # find_files zeigt so viele, zählt aber alle
MAX_TEXT_TREFFER = 100      # search_files bricht danach ab
MAX_GANG = 5_000            # so viele Dokumente läuft eine Suche höchstens ab
MAX_LISTE = 200             # list_files zeigt so viele
ZEIT_S = 30.0               # länger sucht search_files nicht (PDFs lesen kostet)
AUSZUG = 160

VOLL = "Suche vollständig"
NICHT_VOLL = "Suche NICHT vollständig"


@dataclass
class Ergebnis:
    text: str
    vollstaendig: bool
    treffer: int
    fehler: bool = False


def _passt_name(name: str, muster: str) -> bool:
    n = name.casefold()
    m = muster.casefold()
    if any(z in m for z in "*?["):
        return fnmatch.fnmatchcase(n, m)
    # Ohne Platzhalter: Namensteil; Trenner egal („chefkoch-ai" ~ „Chefkoch ai").
    flach = lambda t: "".join(z for z in t if z not in " -_.")  # noqa: E731
    return m in n or (flach(m) and flach(m) in flach(n))


def _ort(papierkorb: bool) -> str:
    return "Papierkorb der Ablage" if papierkorb else "Ablage"


def zeile(k: dict) -> str:
    """Wie ein Dokument in Listen steht: Titel, id, Art, Fassung, wem."""
    fassung = f", Fassung {k['fassung']}" if (k.get("fassung") or 1) > 1 else ""
    wem = "von Sasha" if ablage.von_sasha(k) else "von dir"
    korb = " — im Papierkorb" if ablage.im_papierkorb(k) else ""
    return f"  „{k.get('titel')}“ — id {k['id']}, {k.get('art')}{fassung}, {wem}{korb}"


def _dokumente(papierkorb: bool) -> list:
    return ablage.liste(papierkorb=papierkorb) + ([] if papierkorb else
                                                  ablage.liste(archivierte=True))


def finden(muster: str, papierkorb: bool = False) -> Ergebnis:
    """Dokumente nach Titel: `*.pdf`, `*chefkoch*` oder ein Titelteil."""
    muster = str(muster or "").strip()
    if not muster:
        return Ergebnis("[Fehler: kein Name oder Muster angegeben, z. B. '*.pdf']", False, 0, True)
    doks = _dokumente(papierkorb)
    abbruch = len(doks) > MAX_GANG
    doks = doks[:MAX_GANG]
    treffer = [k for k in doks if _passt_name(str(k.get("titel") or ""), muster)
               or _passt_name(f"{k.get('titel')}{k.get('endung') or ''}", muster)]
    ort = f"durchsucht: {_ort(papierkorb)} ({len(doks)} Dokumente)"
    kopf = (f"{NICHT_VOLL}: abgebrochen nach {MAX_GANG} Dokumenten — {ort}. "
            f"Bis dahin {len(treffer)} Treffer." if abbruch else
            f"{VOLL}: {len(treffer)} Treffer — {ort}.")
    zeilen = [kopf] + [zeile(k) for k in treffer[:MAX_NAMEN]]
    if len(treffer) > MAX_NAMEN:
        zeilen.append(f"  … {len(treffer) - MAX_NAMEN} weitere Treffer nicht gezeigt — "
                      f"Muster genauer fassen.")
    return Ergebnis("\n".join(zeilen), not abbruch, len(treffer))


def _text(k: dict) -> str | None:
    """Der durchsuchbare Text — None: hat keinen (Bild, Zip)."""
    if k.get("art") in ablage.DATEIEN:
        erg = ablage_text.text(k["id"])
        if erg.get("fehler"):
            raise ValueError(erg["fehler"])
        return erg.get("text") or ""
    if k.get("art") in ablage.BINAER or k.get("art") == "zip":
        return None
    return ablage.lesen(k["id"])["inhalt"] or ""


def textsuche(text: str, muster: str = "", papierkorb: bool = False) -> Ergebnis:
    """Text in Dokumenten, wie grep -i -F. Treffer als „„Titel“ (id …):zeile:
    auszug". Ein Dokument, das sich nicht lesen ließ, oder ein Abbruch nach
    Zeit/Trefferzahl → NICHT vollständig."""
    nadel = str(text or "")
    if not nadel.strip():
        return Ergebnis("[Fehler: kein Text zum Suchen angegeben]", False, 0, True)
    nadel_k, muster = nadel.casefold(), str(muster or "").strip()
    start = time.monotonic()
    treffer, gesehen, ohne_text, unlesbar, abbruch = [], 0, 0, 0, ""
    for k in _dokumente(papierkorb):
        if muster and not _passt_name(str(k.get("titel") or ""), muster):
            continue
        if gesehen >= MAX_GANG:
            abbruch = f"abgebrochen nach {MAX_GANG} Dokumenten"
            break
        if time.monotonic() - start > ZEIT_S:
            abbruch = f"abgebrochen nach {int(ZEIT_S)} Sekunden"
            break
        gesehen += 1
        try:
            inhalt = _text(k)
        except (ValueError, OSError, ablage.Unbekannt):
            unlesbar += 1
            continue
        if inhalt is None:
            ohne_text += 1
            continue
        for nr, z in enumerate(inhalt.splitlines(), 1):
            if nadel_k in z.casefold():
                auszug = " ".join(z.split())
                if len(auszug) > AUSZUG:
                    auszug = auszug[:AUSZUG - 1] + "…"
                treffer.append(f"  „{k.get('titel')}“ (id {k['id']}):{nr}: {auszug}")
                if len(treffer) >= MAX_TEXT_TREFFER:
                    abbruch = f"abgebrochen nach {MAX_TEXT_TREFFER} Treffern"
                    break
        if abbruch:
            break
    ort = f"durchsucht: {_ort(papierkorb)} ({gesehen} Dokumente)"
    nebenbei = f" Ohne Text (Bild, Zip): {ohne_text}." if ohne_text else ""
    if abbruch:
        kopf = f"{NICHT_VOLL}: {abbruch} — {ort}.{nebenbei}"
    elif unlesbar:
        kopf = (f"{NICHT_VOLL}: {unlesbar} Dokumente nicht lesbar, nicht durchsucht — "
                f"{ort}. {len(treffer)} Treffer im Rest.{nebenbei}")
    else:
        kopf = f"{VOLL}: {len(treffer)} Treffer — {ort}.{nebenbei}"
    return Ergebnis("\n".join([kopf] + treffer), not (abbruch or unlesbar), len(treffer))


def auflisten(papierkorb: bool = False) -> Ergebnis:
    """Die Ablage wie ls, neueste zuerst (archivierte am Ende)."""
    doks = _dokumente(papierkorb)
    eintraege = [zeile(k) for k in doks]
    voll = len(eintraege) <= MAX_LISTE
    ort = _ort(papierkorb)
    if not eintraege:
        kopf = f"{ort} — leer."
    elif voll:
        kopf = f"{ort} — {len(eintraege)} Dokumente, vollständig (neueste zuerst)."
    else:
        kopf = (f"{ort} — {len(eintraege)} Dokumente, NICHT vollständig gezeigt "
                f"(neueste {MAX_LISTE}); gezielt suchen mit find_files.")
    return Ergebnis("\n".join([kopf] + eintraege[:MAX_LISTE]), voll, len(eintraege))
