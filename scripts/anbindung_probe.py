#!/usr/bin/env python3
"""
Probefahrt einer Anbindungs-Beschreibung — OHNE Modell, ohne Geld.

Je schreibender Aktion: anlegen -> nachlesen -> vergleichen -> zurückbauen
(ändern/löschen mit Probe-Objekt, das die Fahrt selbst anlegt und wegräumt),
je lesender Aktion ein Aufruf. Bericht je Aktion: Stufe, in Ordnung oder
Fehler, warum. Wozu das im Ganzen dient: memory/ki/werkzeug_erzeuger.md,
Abschnitt „Anbindungs-Beschreibung“.

    venv/bin/python scripts/anbindung_probe.py kalender_kern --test-kalender
    venv/bin/python scripts/anbindung_probe.py data/anbindungen/foo.json
    venv/bin/python scripts/anbindung_probe.py foo --nur foo_add --alles
    venv/bin/python scripts/anbindung_probe.py --liste

Name statt Pfad: erst data/anbindungen/<name>.json, dann core/anbindungen/.
--test-kalender   fährt den eigenen Kalender als Wegwerf-Kopie (Test-Client,
                  eigene Datei in /tmp) — Sashas echte Daten bleiben unberührt
--basis URL       ersetzt die Adresse (http); nur gegen eine Test-Kopie!
--alles           führt auch Aktionen aus, die sich nicht zurückbauen lassen
                  (hinterlassen Reste in der Test-Kopie)
Rückgabewert 0 = alles in Ordnung, 1 = mindestens ein Fehler.
"""
import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, "core"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)


def _kalender_kopie():
    """Der eigene Kalender als Wegwerf-Kopie, ergo ein WSGI-Client darauf."""
    tmp = tempfile.mkdtemp(prefix="anbindung_probe_")
    os.environ.setdefault("ZENTRALE_LOKALE_KI", "aus")
    os.environ["ZENTRALE_AI_CONFIG_DIR"] = os.path.join(tmp, "ai_config")
    os.makedirs(os.environ["ZENTRALE_AI_CONFIG_DIR"], exist_ok=True)
    import pathlib
    import kalender
    kalender.CAL_PATH = pathlib.Path(tmp) / "ai_calendar.json"
    kalender.ICS_DIR = None
    os.environ["ZENTRALE_KALENDER_SPEICHER"] = "json"
    from ui.app import app
    return app.test_client()


def _pfad(arg: str) -> str:
    from werkzeug_erzeuger import anbindung
    if os.path.exists(arg):
        return arg
    gefunden = anbindung.auflisten().get(arg)
    if not gefunden:
        sys.exit(f"Keine Anbindung „{arg}“ (weder Pfad noch Name). Vorhanden: "
                 + (", ".join(anbindung.auflisten()) or "keine"))
    return gefunden["pfad"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("anbindung", nargs="?", help="Name oder Pfad der Beschreibung")
    ap.add_argument("--nur", help="nur diese Aktionen (Komma)")
    ap.add_argument("--alles", action="store_true", help="auch Aktionen ohne Rückbau ausführen")
    ap.add_argument("--test-kalender", action="store_true", help="den eigenen Kalender als Wegwerf-Kopie fahren")
    ap.add_argument("--basis", help="Adresse (http) ersetzen")
    ap.add_argument("--ausfuehrlich", action="store_true", help="auch die Schritte erfolgreicher Aktionen")
    ap.add_argument("--json", action="store_true", help="Bericht als JSON")
    ap.add_argument("--liste", action="store_true", help="vorhandene Beschreibungen zeigen")
    a = ap.parse_args(argv)

    client = _kalender_kopie() if a.test_kalender else None     # vor jedem Import von ai_config
    from werkzeug_erzeuger import allgemein, anbindung, probefahrt
    if a.liste:
        for n, i in anbindung.auflisten().items():
            print(f"{n:<20} {i['herkunft']:<8} {'an' if anbindung.eingeschaltet(n) else 'aus'}  {i['pfad']}")
        return 0
    if not a.anbindung:
        ap.error("Name oder Pfad der Beschreibung fehlt")

    sender = probefahrt.wsgi_sender(client) if client else None
    try:
        besch = anbindung.laden(_pfad(a.anbindung))
    except anbindung.AnbindungFehler as e:
        print("Die Beschreibung ist nicht in Ordnung:")
        for m in e.meldungen:
            print("  -", m)
        return 1
    if a.basis and besch["transport"]["art"] == "http":
        besch["transport"]["basis"] = a.basis
    quelle = allgemein.quelle_aus(besch, sender=sender)
    try:
        zeilen = probefahrt.fahren(besch, quelle, nur=a.nur.split(",") if a.nur else None, alles=a.alles)
    finally:
        quelle.adapter.schliessen()
    print(json.dumps(zeilen, ensure_ascii=False, indent=2) if a.json
          else probefahrt.bericht(zeilen, a.ausfuehrlich))
    return 0 if probefahrt.gruen(zeilen) else 1


if __name__ == "__main__":
    sys.exit(main())
