# core/kalender_rhythmus.py
#
# Der Tagesrhythmus: wann bei einem Menschen meist was passiert — Schlaf,
# Essen, „coming down" am Abend. Sasha, 10.10.2026: „‚ich werde gegen 10
# hungrig' ist kein termin … eine leichte hintergrund ebene … der rythmus
# eines menschen ist variabel … die ki muss ihn bearbeiten können".
#
# Eine Phase ist eine Routine (RRULE, time, ende?, label) in der Ebene
# `rhythmus`, mit dem Feld `motiv` (Schlüssel aus MOTIVE). Sie ist nie ein
# Termin: keine Kollision, kein Alarm, keine Rückfrage, keine Abwesenheit
# (core/kalender_konflikte.py). In .ics: TRANSP:TRANSPARENT (belegt nicht)
# und X-ZENTRALE-MOTIV. Phasen dürfen über Mitternacht gehen (Ende vor
# Beginn = endet am Folgetag), normale Termine weiterhin nicht.
#
# Unterstes Modul neben kalender_fehler: nur Konstanten und reine Prüfungen,
# damit kalender, kalender_ics, kalender_ics_abbildung und
# kalender_konflikte es ohne Import-Kreis benutzen können. Schreiben:
# core/kalender_kennung.py (phase_anlegen, phase_aendern, …).

from kalender_fehler import KalenderAbgelehnt

EBENE = "rhythmus"

# FESTE Konstante (nicht aus Daten gebaut): das KI-Schema bleibt pro Prozess
# gleich. Erweitern = hier eine Zeile anfügen; Schlüssel nie umbenennen
# (sie stehen in den .ics-Dateien als X-ZENTRALE-MOTIV).
MOTIVE = {
    "nachthimmel": {"name": "Nachthimmel", "was": "Abend, runterkommen, coming down"},
    "schlaf":      {"name": "Schlaf",      "was": "schlafen, im Bett"},
    "essen":       {"name": "Essen",       "was": "hungrig, Mahlzeit"},
    "sonne":       {"name": "Sonne",       "was": "aufwachen, Morgen, Tageslicht"},
    "fokus":       {"name": "Fokus",       "was": "konzentriert arbeiten, lernen"},
    "sport":       {"name": "Sport",       "was": "Bewegung, Training"},
    "ruhe":        {"name": "Ruhe",        "was": "Pause, nichts müssen"},
    "unterwegs":   {"name": "Unterwegs",   "was": "Weg, Pendeln, draußen"},
}


def motive() -> list[dict]:
    """Der Katalog als Liste (für GET /api/calendar/motive und das KI-Schema)."""
    return [{"schluessel": k, **v} for k, v in MOTIVE.items()]


def motiv_pruefen(wert) -> str:
    """Schlüssel aus MOTIVE (Groß/Klein egal) → Schlüssel; sonst Ablehnung."""
    k = wert.strip().lower() if isinstance(wert, str) else None
    if not k or k not in MOTIVE:
        raise KalenderAbgelehnt("MOTIV-UNBEKANNT",
                                f"Motiv {wert!r} gibt es nicht; erlaubt: {', '.join(MOTIVE)}")
    return k


def ist_phase(e: dict, layer: str | None = None) -> bool:
    """Gehört ein Eintrag (aus entries_in_range oder mit Ebene) zum Rhythmus?"""
    return (layer if layer is not None else (e or {}).get("layer")) == EBENE


def ueber_mitternacht(beginn, ende) -> bool:
    """'23:00','07:00' → True (endet am Folgetag). Nur bei sauberem HH:MM."""
    if not (isinstance(beginn, str) and isinstance(ende, str)):
        return False
    if len(beginn) != 5 or len(ende) != 5 or beginn[2] != ":" or ende[2] != ":":
        return False
    return ende < beginn
