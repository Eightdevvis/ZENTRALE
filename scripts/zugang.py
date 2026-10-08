#!/usr/bin/env python3
"""Zugangsschlüssel des Backends (memory/betrieb/zugang.md).

Sasha tippt Shell-Befehle selbst; hier nur in Worten, was die Zusätze tun:
  status (oder nichts)   Modus, ob ein Schlüssel da ist, wer zuletzt ohne kam
  anlegen                neuen Schlüssel anlegen (nur beim allerersten Mal)
  erneuern               neuen Schlüssel statt des alten (alle Geräte brauchen ihn dann neu)
  zeigen                 die Schlüssel-Zeile zum Ablegen in KeePass
  eingeben               Schlüssel aus KeePass auf diesem Rechner ablegen
  link [adresse]         Browser-Link, 10 Minuten gültig (setzt einen Keks)
  modus aus|melden|an    die Tür umschalten (live, wenn ZENTRALE läuft)
"""

import argparse
import getpass
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "core"))

import ai_config  # noqa: E402
import zugang  # noqa: E402

# Die Steuerung geht immer an DIESEN Rechner: /api/zugang antwortet nur lokal.
LOKAL = os.environ.get("ZENTRALE_ZUGANG_LOKAL_URL", "http://localhost:5000")


def _backend(methode="GET", daten=None):
    """→ Antwort des laufenden Kerns, oder None, wenn keiner läuft."""
    body = json.dumps(daten).encode() if daten is not None else None
    req = urllib.request.Request(LOKAL + "/api/zugang", data=body, method=methode,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None


_MODUS_TEXT = {"aus": "aus — keine Prüfung",
               "melden": "melden — alle dürfen rein, wer ohne Schlüssel kommt, steht im Log",
               "an": "an — ohne Schlüssel kein Zugang (außer von diesem Rechner)"}


def _status():
    b = _backend()
    m = b["modus"] if b else zugang.modus()
    print(f"Tür: {_MODUS_TEXT[m]}" + ("" if b else "  (ZENTRALE läuft gerade nicht)"))
    print(f"Schlüssel: {'da' if zugang.vorhanden() else 'FEHLT'} ({zugang.pfad()})")
    if b and b.get("ohne_schluessel"):
        print("Zuletzt ohne passenden Schlüssel (neueste zuletzt):")
        for e in b["ohne_schluessel"][-15:]:
            was = "durchgelassen" if e["durchgelassen"] else "abgewiesen"
            print(f"  {e['am']}  {e['von']:<15} {e['pfad']}  {e['grund']} — {was}")
    elif b:
        print("Seit dem Start kam niemand ohne Schlüssel.")
    return 0


def _modus(neu):
    b = _backend("POST", {"modus": neu})
    if b is None:
        # Kein laufender Kern → direkt in die Einstellungen; gilt beim Start.
        ai_config.set_override("zugang", neu, persist=True)
        print(f"Gespeichert: {_MODUS_TEXT[neu]}. Gilt ab dem nächsten Start von ZENTRALE.")
    else:
        print(f"Umgeschaltet: {_MODUS_TEXT[b['modus']]}.")
    if neu == "an" and not zugang.vorhanden():
        print("Achtung: auf diesem Rechner liegt noch kein Schlüssel — von anderen "
              "Geräten kommt so niemand rein.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("was", nargs="?", default="status",
                    choices=["status", "anlegen", "erneuern", "zeigen", "eingeben", "link", "modus"])
    ap.add_argument("wert", nargs="?")
    ap.add_argument("--ja", action="store_true", help="beim Erneuern nicht nachfragen")
    a = ap.parse_args(argv)
    try:
        if a.was == "status":
            return _status()
        if a.was == "anlegen":
            print(f"Angelegt: {zugang.anlegen()}")
            print("Als Nächstes: mit „zeigen“ die Zeile holen und in KeePass ablegen.")
            return 0
        if a.was == "erneuern":
            if not a.ja and input("Alle anderen Geräte brauchen danach den neuen Schlüssel. "
                                  "Wirklich erneuern? (ja/nein) ").strip().lower() != "ja":
                print("Nichts geändert.")
                return 1
            print(f"Erneuert: {zugang.anlegen(erneuern=True)}")
            print("Jetzt den Eintrag in KeePass ersetzen und den neuen Schlüssel auf die "
                  "anderen Geräte bringen. Alte Browser-Links und Kekse gelten nicht mehr.")
            return 0
        if a.was == "zeigen":
            k = zugang.laden()
            if not k:
                print("Auf diesem Rechner liegt kein Zugangsschlüssel.", file=sys.stderr)
                return 1
            print(k)
            return 0
        if a.was == "eingeben":
            zeile = getpass.getpass("Schlüssel aus KeePass (wird nicht angezeigt): ")
            print(f"Abgelegt: {zugang.ablegen(zeile)}")
            return 0
        if a.was == "link":
            marke = zugang.link_marke()
            if not marke:
                print("Auf diesem Rechner liegt kein Zugangsschlüssel.", file=sys.stderr)
                return 1
            adresse = a.wert or "http://localhost:5000/api/state"
            trenner = "&" if "?" in adresse else "?"
            print(f"{adresse}{trenner}zugang={marke}")
            print("Gilt 10 Minuten. Einmal im Browser öffnen — danach merkt er sich "
                  "den Zugang 30 Tage.", file=sys.stderr)
            return 0
        if a.was == "modus":
            if a.wert not in zugang.MODI:
                print("Modus ist aus, melden oder an.", file=sys.stderr)
                return 2
            return _modus(a.wert)
    except zugang.SchluesselFehler as e:
        print(str(e), file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
