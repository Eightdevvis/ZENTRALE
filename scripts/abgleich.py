#!/usr/bin/env python3
"""Daten über die Mitte abgleichen (memory/betrieb/abgleich.md).

Sasha tippt Shell-Befehle selbst; hier nur in Worten, was die Zusätze tun:
  status (oder nichts)            letzter Abgleich, Weg, Hinweise
  jetzt                           jetzt abgleichen
  --trocken                       zeigen, was ein Abgleich täte — nichts ändern
  schluessel-anlegen              neuen Schlüssel anlegen (nur beim allerersten Mal)
  schluessel-zeigen-fuer-keepass  die Schlüssel-Zeile zum Ablegen in KeePass
  schluessel-eingeben             Schlüssel aus KeePass auf diesem Rechner ablegen
  umstellen mitte|rsync           den Weg wechseln

--automatisch (Timer und Änderungs-Haken): nur abgleichen, wenn der Weg
„mitte" eingestellt ist, und still sein, wenn nichts zu sagen ist.
"""

import argparse
import getpass
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))

import abgleich  # noqa: E402
import abgleich_mitte  # noqa: E402
import abgleich_schluessel as schluessel  # noqa: E402

TEST_WURZEL_ENV = "ZENTRALE_ABGLEICH_WURZEL"   # nur Tests: anderer ZENTRALE-Ordner


def _wurzel():
    return os.environ.get(TEST_WURZEL_ENV) or ROOT


def _status():
    z = abgleich.zustand()
    print(f"Weg: {'über die Mitte' if z['weg'] == 'mitte' else 'alter rsync-Weg'}"
          f" · Rechner: {z['rechner']}")
    print("Schlüssel: " + ("da" if z["schluessel_da"] else "FEHLT"))
    if z["letzter_erfolg"]:
        print(f"Zuletzt abgeglichen: {z['letzter_erfolg']}"
              f" ({z['geholt']} geholt, {z['gesendet']} gesendet)")
    else:
        print("Noch nie abgeglichen.")
    if z["fehler"]:
        print(f"Letzter Versuch {z['letzter_versuch']}: {z['fehler']}")
    if z["hinweise"]:
        print(f"Hinweise ({len(z['hinweise'])}, neueste zuletzt):")
        for h in z["hinweise"][-10:]:
            print(f"  {h['am'][:16].replace('T', ' ')}  {h['text']}")
        print(f"Aufgehobene Fassungen: {z['konflikte_ordner']}")
    return 0


def _jetzt(trocken, automatisch):
    if automatisch and abgleich.weg() != "mitte":
        return 0                           # Timer läuft, aber noch nicht umgestellt
    try:
        b = abgleich.abgleichen(_wurzel(), trocken=trocken,
                                warten=60.0 if automatisch else 120.0)
    except abgleich.Besetzt:
        if not automatisch:
            print("Ein anderer Abgleich läuft gerade — gleich nochmal.")
        return 0 if automatisch else 1
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler) as e:
        print(str(e))
        return 2
    if automatisch and not (b.geholt or b.gesendet or b.hinweise or b.beiseite):
        return 0
    vorsatz = "Würde " if trocken else ""
    if b.art == "erstbefuellung":
        print("Die Mitte war leer — " + ("würde" if trocken else "wird") + " jetzt mit diesem Rechner gefüllt.")
    elif b.art == "erstabgleich":
        print("Erster Abgleich dieses Rechners: die Mitte gilt, abweichende Fassungen werden aufgehoben.")
    print(f"{vorsatz}holen: {len(b.geholt)} · senden: {len(b.gesendet)}"
          f" · beiseite: {len(b.beiseite)}")
    for rel in (b.geholt if trocken else [])[:30]:
        print("  hier ändern:  " + rel)
    for rel in (b.gesendet if trocken else [])[:30]:
        print("  Mitte ändern: " + rel)
    for h in b.hinweise:
        print("  Hinweis: " + h)
    return 0


def _schluessel_anlegen():
    try:
        p = schluessel.anlegen()
    except schluessel.SchluesselFehler as e:
        print(str(e))
        return 1
    print(f"Schlüssel angelegt: {p}")
    print("Jetzt sofort in KeePass ablegen (Zusatz schluessel-zeigen-fuer-keepass).")
    print("Ohne ihn sind die Daten in der Mitte nicht mehr lesbar.")
    return 0


def _schluessel_zeigen():
    try:
        k = schluessel.laden().decode("ascii")
    except schluessel.SchluesselFehler as e:
        print(str(e))
        return 1
    print("In KeePass einen Eintrag „ZENTRALE Abgleich“ anlegen und diese Zeile")
    print("ins Passwort-Feld kopieren — danach die Zwischenablage leeren:\n")
    print("    " + k + "\n")
    return 0


def _schluessel_eingeben():
    if schluessel.vorhanden():
        print(f"Hier liegt schon ein Schlüssel ({schluessel.pfad()}). Nichts geändert.")
        return 1
    zeile = getpass.getpass("Schlüssel aus KeePass einfügen (wird nicht angezeigt): ")
    try:
        schluessel.pruefen(zeile)
        # Gegen die Mitte prüfen, BEVOR er abgelegt wird: ein Tippfehler soll
        # nicht erst beim nächsten Abgleich auffallen.
        mitte = abgleich.mitte_oeffnen()
        stand, lesen, _ = mitte.holen()
        if stand is not None:
            schluessel.Tresor(zeile.strip().encode("ascii")).auf(lesen(abgleich.INHALT) or b"")
        p = schluessel.ablegen(zeile)
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler) as e:
        print(str(e))
        return 1
    print(f"Schlüssel passt und liegt jetzt in {p}.")
    return 0


def _umstellen(neuer):
    try:
        abgleich.umstellen(neuer)
    except (ValueError, schluessel.SchluesselFehler, abgleich_mitte.MitteFehler) as e:
        print(str(e))
        return 1
    if neuer == "mitte":
        print("Umgestellt: ab jetzt über die Mitte. Den alten Boot-Sync abschalten und")
        print("den Timer einschalten (memory/betrieb/abgleich.md, Übergang).")
    else:
        print("Zurück auf den alten rsync-Weg. Die Mitte bleibt einfach stehen.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("befehl", nargs="?", default="status",
                    choices=["status", "jetzt", "schluessel-anlegen",
                             "schluessel-zeigen-fuer-keepass", "schluessel-eingeben",
                             "umstellen"])
    ap.add_argument("weg", nargs="?", help="bei umstellen: mitte oder rsync")
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--automatisch", action="store_true")
    a = ap.parse_args(argv)
    if a.trocken or a.befehl == "jetzt":
        return _jetzt(a.trocken, a.automatisch)
    if a.befehl == "schluessel-anlegen":
        return _schluessel_anlegen()
    if a.befehl == "schluessel-zeigen-fuer-keepass":
        return _schluessel_zeigen()
    if a.befehl == "schluessel-eingeben":
        return _schluessel_eingeben()
    if a.befehl == "umstellen":
        return _umstellen(a.weg or "")
    return _status()


if __name__ == "__main__":
    sys.exit(main())
