#!/usr/bin/env python3
"""Konfliktlöser für vdirsyncer: „lokal gewinnt“, aber nur in einem engen Fall.

Anlass 24.10.2026: ein Termin wurde hochgeladen, Google schrieb ihn um (das
tut Google mit fast jedem hochgeladenen Termin), und kurz danach wurde er in
ZENTRALE noch einmal geändert. vdirsyncer sah „changed on both sides“, und
weil das Paar `conflict_resolution = null` hat, brach jeder Lauf für diesen
Termin mit einem Fehler ab.

Der Adapter (core/adapter_vdirsyncer.bauen) trägt diesen Löser für die
Kalender-Paare ein, deren Konfliktregel leer ist. vdirsyncer ruft ihn so:

    kalender_konflikt.py --lokal a|b <datei_a> <datei_b>

und erwartet, dass danach beide Dateien gleich sind. Lokal gewinnt NUR, wenn
  * beide Fassungen dieselbe UID tragen, die auf „@zentrale“ endet (ein in
    ZENTRALE angelegter Termin), und
  * die lokale Fassung echt neuer ist (LAST-MODIFIED, sonst DTSTAMP — jeweils
    der jüngste Wert in der Datei).
Sonst Exit 1: vdirsyncer meldet den Konflikt wie bisher, nichts wird
überschrieben. Google-Fassungen liegen ohnehin im Tagesarchiv der
Nur-Lese-Kopie (scripts/kalender_sync.py).

Ohne Abhängigkeiten (läuft im Prozess von vdirsyncer als eigenes Programm).
"""

import re
import sys
from datetime import datetime, timezone

_ENTFALTEN = re.compile(r"\r?\n[ \t]")


def _zeilen(text: str) -> list:
    return _ENTFALTEN.sub("", text).splitlines()


def _werte(text: str, name: str) -> list:
    raus = []
    for z in _zeilen(text):
        kopf, _, wert = z.partition(":")
        if kopf.split(";", 1)[0].upper() == name and wert:
            raus.append(wert.strip())
    return raus


def _zeit(wert: str):
    """iCalendar-Zeit in UTC (nur die eindeutige Form …Z), sonst None."""
    try:
        return datetime.strptime(wert, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def stand(text: str):
    """(Feld, jüngste Zeit) aus LAST-MODIFIED, nur ohne sie aus DTSTAMP;
    None = unklar (Feld fehlt oder ist nicht eindeutig lesbar)."""
    for name in ("LAST-MODIFIED", "DTSTAMP"):
        werte = _werte(text, name)
        if werte:
            zeiten = [_zeit(w) for w in werte]
            return (name, max(zeiten)) if all(zeiten) else None
    return None


def entscheiden(lokal: str, fern: str) -> str | None:
    """→ None, wenn lokal gewinnt; sonst der Grund, es nicht zu tun."""
    uid_l, uid_f = set(_werte(lokal, "UID")), set(_werte(fern, "UID"))
    if len(uid_l) != 1 or uid_l != uid_f:
        return "UID nicht eindeutig gleich"
    if not next(iter(uid_l)).endswith("@zentrale"):
        return "kein ZENTRALE-Termin"
    t_l, t_f = stand(lokal), stand(fern)
    if t_l is None or t_f is None or t_l[0] != t_f[0]:
        return "Änderungszeit nicht lesbar"
    if t_l[1] <= t_f[1]:
        return "Google-Fassung ist nicht älter"
    return None


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 4 or argv[0] != "--lokal" or argv[1] not in ("a", "b"):
        print("Aufruf: kalender_konflikt.py --lokal a|b <a> <b>", file=sys.stderr)
        return 2
    pfad_a, pfad_b = argv[2], argv[3]
    pfad_l, pfad_f = (pfad_a, pfad_b) if argv[1] == "a" else (pfad_b, pfad_a)
    with open(pfad_l, encoding="utf-8") as f:
        lokal = f.read()
    with open(pfad_f, encoding="utf-8") as f:
        fern = f.read()
    grund = entscheiden(lokal, fern)
    if grund:
        print("Konflikt bleibt (%s) — bitte von Hand lösen." % grund, file=sys.stderr)
        return 1
    with open(pfad_f, "w", encoding="utf-8") as f:
        f.write(lokal)
    print("Konflikt gelöst: die neuere ZENTRALE-Fassung gewinnt.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
