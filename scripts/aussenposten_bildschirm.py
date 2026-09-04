#!/usr/bin/env python3
"""Stellt den Bildschirm eines Aussenpostens auf die beste verfuegbare Aufloesung.

Warum das noetig ist: X startet auf einem Knoten gern in einem Notmodus. Am Pi
an der Wand stand es auf 1024x768 (4:3), waehrend der angeschlossene Monitor
1920x1080 anbietet — und weil das Panel ein Ultrawide ist, zog es dieses
schmale Bild auf die volle Breite. Alles sah gestreckt aus. Der Knoten wusste
schlicht nicht, woran er haengt.

Dieses Skript liest, was der Monitor per EDID meldet (verfuegbare Modi UND
seine physische Groesse in Millimetern), und waehlt den Modus, der am besten
dazu passt: zuerst nach Seitenverhaeltnis, dann nach Pixelzahl. Ein 21:9-Panel
bekommt also lieber 1920x1080 (16:9) als 1280x1024 (5:4), auch wenn letzteres
mehr Pixel pro Zeile haette.

Reine Standardbibliothek, braucht kein root — es aendert nur die eigene
X-Sitzung. Ohne laufendes X (oder ohne xrandr) tut es gar nichts und meldet
das; ein Knoten ohne Bildschirm soll daran nicht scheitern.

Aufruf:
  aussenposten_bildschirm.py            # besten Modus setzen
  aussenposten_bildschirm.py --zeigen   # nur berichten, nichts aendern
"""

import argparse
import os
import re
import subprocess
import sys


def xrandr(*args):
    umgebung = dict(os.environ)
    umgebung.setdefault("DISPLAY", ":0")
    return subprocess.run(["xrandr", *args], capture_output=True, text=True,
                          timeout=30, env=umgebung)


def lesen():
    """(ausgang, aktuell, modi, mm_breit, mm_hoch) des ersten verbundenen Ausgangs.

    Beispielzeile, die uns interessiert:
      HDMI-1 connected 1024x768+0+0 (normal ...) 797mm x 334mm
    danach eingerueckt die Modi:
         1920x1080     60.00    60.00
    """
    r = xrandr("--query")
    if r.returncode != 0:
        return None
    ausgang = aktuell = None
    mm = (0, 0)
    modi = []
    for zeile in r.stdout.splitlines():
        kopf = re.match(r"^(\S+) connected .*?(\d+)mm x (\d+)mm", zeile)
        if kopf:
            if ausgang:                     # nur der erste verbundene Ausgang
                break
            ausgang = kopf.group(1)
            mm = (int(kopf.group(2)), int(kopf.group(3)))
            aufl = re.search(r"\b(\d+)x(\d+)\+\d+\+\d+", zeile)
            if aufl:
                aktuell = (int(aufl.group(1)), int(aufl.group(2)))
            continue
        if ausgang and zeile.startswith((" ", "\t")):
            m = re.match(r"^\s+(\d+)x(\d+)i?\s", zeile)
            if m and "i " not in zeile[:20]:
                paar = (int(m.group(1)), int(m.group(2)))
                if paar not in modi:
                    modi.append(paar)
        elif ausgang and not zeile.startswith((" ", "\t")):
            break
    if not ausgang or not modi:
        return None
    return ausgang, aktuell, modi, mm[0], mm[1]


def bester(modi, mm_breit, mm_hoch):
    """Der Modus, der am besten zum Panel passt.

    Zuerst das Seitenverhaeltnis (ein gestrecktes Bild faellt sofort auf),
    danach die Pixelzahl. Kennt der Monitor seine physische Groesse nicht,
    entscheidet allein die Pixelzahl.
    """
    if mm_breit > 0 and mm_hoch > 0:
        ziel = mm_breit / mm_hoch
        return max(modi, key=lambda m: (-round(abs(m[0] / m[1] - ziel), 2),
                                        m[0] * m[1]))
    return max(modi, key=lambda m: m[0] * m[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zeigen", action="store_true",
                    help="nur berichten, nichts aendern")
    a = ap.parse_args()

    daten = lesen()
    if not daten:
        print("kein Bildschirm gefunden (kein X, kein xrandr, oder nichts "
              "angeschlossen) — nichts zu tun")
        return 0
    ausgang, aktuell, modi, mm_b, mm_h = daten
    ziel = bester(modi, mm_b, mm_h)

    if mm_b and mm_h:
        print("%s: %dmm x %dmm (Seitenverhaeltnis %.2f)" % (ausgang, mm_b, mm_h,
                                                            mm_b / mm_h))
    print("aktuell: %s   bester Modus: %dx%d   (%d Modi angeboten)"
          % ("%dx%d" % aktuell if aktuell else "unbekannt",
             ziel[0], ziel[1], len(modi)))

    if aktuell == ziel:
        print("passt schon")
        return 0
    if a.zeigen:
        print("(--zeigen: nichts geaendert)")
        return 0

    r = xrandr("--output", ausgang, "--mode", "%dx%d" % ziel)
    if r.returncode != 0:
        print("xrandr fehlgeschlagen: %s" % (r.stderr or "").strip()[:300])
        return 1
    print("gesetzt: %dx%d" % ziel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
