#!/usr/bin/env python3
"""
Prüfstand: arbeitet die KI ehrlich und richtig? — gemessen an Fällen.

Jeder Fall (tests/pruefstand/faelle/*.yaml) ist eine Lage aus Sashas Alltag:
ein Probe-Kalender, Nachrichten von Sasha, und was danach stimmen muss. Der
Fall läuft über den ECHTEN Weg (POST /api/chat → kern.chat → Werkzeug-
Schleife → echte Werkzeuge) mit dem ECHTEN Cloud-Modell — aber gegen
Wegwerf-Daten. Websuche und Seiten antworten nach Vorgabe des Falls, die
Knöpfe drückt ein Skript. Danach:

  1. Endzustand  stimmt der Kalender? (deterministisch)
  2. Belege      jede Tatsachen-Behauptung gegen die Werkzeug-Ergebnisse
                 (ein Richter-Modell zitiert, Python prüft das Zitat)
  3. Metriken    Aufrufe, Fehler, Löschen+Neu, Rückfragen, Kosten, Laufzeit

KOSTET GELD (ein Durchgang mit allen Fällen etwa 0,5–1 €, gebucht in
data/ai_usage.json — im eigenen Topf „pruefstand", nicht in Sashas Chat-
Kosten; Obergrenze im Monat: Einstellung pruefstand_budget_monat). Deshalb nicht in pytest — dort läuft nur ein
Trockentest mit gefälschtem Modell (tests/test_pruefstand.py).
Wozu, Format der Fälle, wie man misst: memory/ki/pruefstand.md.

    venv/bin/python scripts/pruefstand.py                    # alle Fälle
    venv/bin/python scripts/pruefstand.py --fall f01 --fall f03
    venv/bin/python scripts/pruefstand.py --vergleich main   # dieser Stand gegen main
    venv/bin/python scripts/pruefstand.py --nur-richter <ordner>   # nur neu richten
    venv/bin/python scripts/pruefstand.py --liste
    venv/bin/python scripts/pruefstand.py --entwurf-aus <gespräch-id>[:<nachricht-id>]

Sparen (memory/ki/pruefstand.md, Abschnitt „Sparen"):
    --abbruch-frueh        einen Fall beenden, sobald er sicher verloren ist
    --richter-batch        Richter über die Batches-API (halber Preis, später)
    --abspielen <ordner>   einen aufgezeichneten Durchgang ohne Modell nachfahren (0 €)
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from pruefstand_teile import bericht, faelle, umgebung  # noqa: E402

STANDARD_AUSGABE = os.path.expanduser("~/.cache/zentrale/pruefstand")


# ── Ein Fall im eigenen Prozess ────────────────────────────────────────

def richten(a) -> int:
    """Nur den Richter über ein gespeichertes Fall-Ergebnis (--nur-richter)."""
    tmp = tempfile.mkdtemp(prefix="zentrale_pruefstand_")
    try:
        umgebung.vorbereiten(tmp, a.daten)
        sys.path[:0] = [os.path.join(ROOT, "core"), ROOT]
        from pruefstand_teile import kind
        with open(a.richte, encoding="utf-8") as f:
            erg = json.load(f)
        erg = kind.nur_richten(erg, richter_modell=a.richter)
        with open(a.richte, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False, default=str)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def richter_einzeln(pfad: str, daten: str, richter_modell=None) -> dict:
    """Den normalen Richter über ein gespeichertes Fall-Ergebnis schicken
    (eigener Prozess). -> das neu gerichtete Ergebnis."""
    befehl = [sys.executable, os.path.abspath(__file__), "--richte", pfad,
              "--daten", daten] + (["--richter", richter_modell] if richter_modell else [])
    with open(pfad.replace(".json", ".richter.log"), "w", encoding="utf-8") as lf:
        subprocess.run(befehl, stdout=lf, stderr=subprocess.STDOUT, timeout=1800)
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


def richter_im_batch(ergebnisse: list, ordner: str, daten: str, a) -> list:
    """--richter-batch: alle Richter-Anfragen in einen Batch (halber Preis).
    Scheitert er, richtet der normale Richter Fall für Fall."""
    from pruefstand_teile import richter_batch
    pfade = [os.path.join(ordner, "protokolle", f"{e['id']}.json") for e in ergebnisse]
    try:
        topf_lage(daten)                     # Schlüssel und Kern-Pfad wie für die Grenze
        richter_batch.richten(ergebnisse, modell=a.richter,
                              warten_s=a.richter_batch_warten * 60)
        for e, pfad in zip(ergebnisse, pfade):
            if os.path.exists(pfad):
                with open(pfad, "w", encoding="utf-8") as f:
                    json.dump(e, f, ensure_ascii=False, default=str)
        return ergebnisse
    except Exception as fehler:
        print(f"Richter-Batch ging nicht ({fehler}) — richte normal, Fall für Fall.")
        return [richter_einzeln(pfad, daten, a.richter)
                if os.path.exists(pfad) and e.get("zuege") else e
                for e, pfad in zip(ergebnisse, pfade)]


def nur_richter(a, daten: str) -> int:
    """Einen schon gefahrenen Durchgang neu richten und den Bericht neu
    schreiben. Kostet nur den Richter."""
    ordner = os.path.abspath(a.nur_richter)
    with open(os.path.join(ordner, "ergebnis.json"), encoding="utf-8") as f:
        alt = json.load(f)
    ergebnisse = []
    nur = {f["id"] for f in faelle.finden(a.fall)} if a.fall else None
    for fall in alt["faelle"]:
        pfad = os.path.join(ordner, "protokolle", f"{fall['id']}.json")
        if os.path.exists(pfad) and a.ohne_modell:
            from pruefstand_teile import richter
            with open(pfad, encoding="utf-8") as f:
                fall = richter.neu_pruefen(json.load(f))
            with open(pfad, "w", encoding="utf-8") as f:
                json.dump(fall, f, ensure_ascii=False, default=str)
        elif os.path.exists(pfad) and (nur is None or fall["id"] in nur):
            fall = richter_einzeln(pfad, daten, a.richter)
        z = (fall.get("richter") or {}).get("zaehlung") or {}
        print(f"  {fall['id']:<28}Fehler-Behauptungen {z.get('fehler', '—')}  "
              f"Richter {fall.get('richter_kosten_eur') or 0:.3f} €"
              + (f"  {fall['richter'].get('fehler')}" if (fall.get('richter') or {}).get('fehler') else ""))
        ergebnisse.append(fall)
    alt["faelle"] = ergebnisse
    alt["summen"] = bericht.summen(ergebnisse)
    alt["richter"] = ", ".join(sorted({(e.get("richter") or {}).get("modell") or ""
                                       for e in ergebnisse} - {""}))
    print(f"Bericht: {bericht.schreiben(alt, ordner)}")
    return 0


def einzeln(a) -> int:
    fall = faelle.laden(a.einzeln)
    code = os.path.abspath(a.code or ROOT)
    tmp = tempfile.mkdtemp(prefix="zentrale_pruefstand_")
    try:
        umgebung.vorbereiten(tmp, a.daten, fall.get("einstellungen"))
        sys.path[:0] = [os.path.join(code, "core"), code]
        # Fremde Bibliotheken VOR dem Kern laden: so behalten sie die echten
        # date/datetime-Klassen, wenn die Uhr des Falls verstellt wird (uhr.py).
        import anthropic  # noqa: F401
        import dateutil.rrule  # noqa: F401
        import flask  # noqa: F401
        try:
            import icalendar  # noqa: F401
        except ImportError:
            pass
        from pruefstand_teile import kind
        erg = kind.ausfuehren(fall, code_wurzel=code, tmp=tmp,
                              richter_modell=a.richter, ohne_richter=a.ohne_richter,
                              frueh=a.abbruch_frueh, aufnahme=a.aufnahme,
                              abspielen=a.abspiel_datei)
        with open(a.ergebnis, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False, default=str)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── Ein Durchgang ──────────────────────────────────────────────────────

def stand_von(code: str) -> str:
    try:
        ast = subprocess.run(["git", "-C", code, "rev-parse", "--abbrev-ref", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        sha = subprocess.run(["git", "-C", code, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", code, "status", "--porcelain", "--", "core", "ui"],
                               capture_output=True, text=True).stdout.strip()
        return f"{ast}@{sha}" + (" (+ ungespeicherte Änderungen)" if dirty else "")
    except Exception:
        return code


# Was ein Durchgang mit allen sieben Fällen ungefähr kostet (gemessen
# 08.10.2026: 1,06 € Modell + 0,7 € Richter mit claude-sonnet-5).
SCHAETZUNG_EUR = 1.8


PRUEFSTAND_BUDGET_STANDARD = 5.0   # € im Monat, wenn nichts eingestellt ist


def topf_lage(daten: str):
    """(diesen Monat im Prüfstand-Topf ausgegeben, Obergrenze) — oder None,
    wenn die Buchhaltung nicht lesbar ist.

    Seit 2026-10-09 bucht der Prüfstand in einen eigenen Topf
    (core/usage.py, Herkunft „pruefstand"): Sashas Monatsdeckel und sein
    Rückfall auf den billigsten Anbieter zählen nur noch seinen Chat. Vorher
    hatten Prüfstand-Läufe seinen Deckel (8 €) gerissen und sein Chat fiel
    auf qwen-plus zurück. Der Prüfstand hat dafür seine eigene Grenze im
    Monat, Einstellung `pruefstand_budget_monat` (Standard 5 €)."""
    try:
        os.environ.setdefault("ZENTRALE_USAGE_FILE",
                              os.path.join(daten, "data", "ai_usage.json"))
        os.environ.setdefault("ZENTRALE_AI_CONFIG_DIR", os.path.join(daten, "data"))
        if os.path.join(ROOT, "core") not in sys.path:
            sys.path.insert(0, os.path.join(ROOT, "core"))
        import ai_config
        import usage
        try:
            limit = float(ai_config.setting("pruefstand_budget_monat",
                                            PRUEFSTAND_BUDGET_STANDARD))
        except (TypeError, ValueError):
            limit = PRUEFSTAND_BUDGET_STANDARD
        return float(usage.monat_euro(usage.PRUEFSTAND)), limit
    except Exception as e:
        print(f"Prüfstand-Kosten nicht lesbar: {e}")
        return None


def fingerabdruck(daten: str) -> dict:
    """(Pfad → (Größe, mtime)) unter data/ — der Beleg, dass nichts davon
    geschrieben wurde. Größe+Zeit statt Prüfsumme: data/ hat über 1 GB."""
    aus = {}
    for wurzel, _, dateien in os.walk(os.path.join(daten, "data")):
        for name in dateien:
            p = os.path.join(wurzel, name)
            try:
                s = os.stat(p)
                aus[p] = (s.st_size, s.st_mtime_ns)
            except OSError:
                pass
    return aus


def durchgang(liste: list, *, code: str, daten: str, ordner: str, a) -> dict:
    os.makedirs(os.path.join(ordner, "protokolle"), exist_ok=True)
    ergebnisse = []
    for fall in liste:
        # Die Schätzung vorher kann daneben liegen (ein Fall mit Browser
        # dauert länger): vor jedem Fall nachsehen, ob die Grenze erreicht ist.
        lage = None if (a.trotz_budget or a.abspielen) else topf_lage(daten)
        if lage and lage[0] >= lage[1]:
            print(f"  {fall['id']:<28}ausgelassen — Prüfstand-Grenze erreicht "
                  f"({lage[0]:.2f} € von {lage[1]:.2f} €)")
            ergebnisse.append({"id": fall["id"], "titel": fall.get("titel"),
                               "verdeckt": bool(fall.get("verdeckt")), "zuege": [],
                               "endzustand": [{"was": "Lauf", "ok": False,
                                               "grund": "ausgelassen: Prüfstand-Grenze erreicht"}],
                               "absturz": "ausgelassen (pruefstand_budget_monat)",
                               "metriken": {}})
            continue
        ziel = os.path.join(ordner, "protokolle", f"{fall['id']}.json")
        log = os.path.join(ordner, "protokolle", f"{fall['id']}.log")
        befehl = [sys.executable, os.path.abspath(__file__), "--einzeln", fall["_pfad"],
                  "--code", code, "--daten", daten, "--ergebnis", ziel]
        if a.richter:
            befehl += ["--richter", a.richter]
        if a.ohne_richter or a.richter_batch or a.abspielen:
            befehl.append("--ohne-richter")
        if a.abbruch_frueh:
            befehl.append("--abbruch-frueh")
        if a.abspielen:
            befehl += ["--abspiel-datei", os.path.join(os.path.abspath(a.abspielen),
                                                       "aufnahmen", f"{fall['id']}.json")]
        else:
            os.makedirs(os.path.join(ordner, "aufnahmen"), exist_ok=True)
            befehl += ["--aufnahme", os.path.join(ordner, "aufnahmen", f"{fall['id']}.json")]
        print(f"  {fall['id']:<28}", end="", flush=True)
        t0 = time.monotonic()
        with open(log, "w", encoding="utf-8") as lf:
            r = subprocess.run(befehl, stdout=lf, stderr=subprocess.STDOUT, timeout=3600)
        if r.returncode != 0 or not os.path.exists(ziel):
            erg = {"id": fall["id"], "titel": fall.get("titel"),
                   "verdeckt": bool(fall.get("verdeckt")), "zuege": [],
                   "endzustand": [{"was": "Lauf", "ok": False, "grund": "Prozess gescheitert"}],
                   "absturz": f"Rückgabe {r.returncode}, siehe {log}", "metriken": {}}
        else:
            with open(ziel, encoding="utf-8") as f:
                erg = json.load(f)
        ergebnisse.append(erg)
        z = (erg.get("richter") or {}).get("zaehlung") or {}
        ez = erg.get("endzustand") or []
        print(f"Endzustand {sum(e['ok'] for e in ez)}/{len(ez)}  "
              f"Fehler-Behauptungen {z.get('fehler', '—')}  "
              f"{(erg.get('kosten_eur') or 0) + (erg.get('richter_kosten_eur') or 0):.3f} €  "
              f"{time.monotonic() - t0:.0f} s"
              + ("  (verdeckt)" if erg.get("verdeckt") else "")
              + ("  ABSTURZ" if erg.get("absturz") else ""))
    if a.richter_batch and not a.abspielen and any(e.get("zuege") for e in ergebnisse):
        ergebnisse = richter_im_batch(ergebnisse, ordner, daten, a)
    modelle = sorted({m for e in ergebnisse for m in e.get("modelle") or []})
    richter_modelle = sorted({(e.get("richter") or {}).get("modell") or "" for e in ergebnisse} - {""})
    return {"zeit": datetime.now().strftime("%Y-%m-%d %H:%M"), "code": stand_von(code),
            "modelle": modelle, "richter": ", ".join(richter_modelle),
            "faelle": ergebnisse, "summen": bericht.summen(ergebnisse)}


def topf_text(daten: str) -> str:
    """Eine Zeile für den Bericht: der eigene Topf des Prüfstands."""
    lage = topf_lage(daten)
    if not lage:
        return "nicht lesbar"
    return (f"diesen Monat {lage[0]:.2f} € von {lage[1]:.2f} € (eigener Topf, "
            "nicht in Sashas Chat-Kosten)")


def isolation_text(vorher: dict, nachher: dict) -> str:
    anders = sorted(p for p in set(vorher) | set(nachher)
                    if vorher.get(p) != nachher.get(p) and not p.endswith("ai_usage.json"))
    if not anders:
        return "sauber — unter data/ hat sich außer ai_usage.json nichts verändert"
    return ("⚠ während des Laufs verändert (kann auch die laufende ZENTRALE gewesen "
            "sein): " + ", ".join(os.path.relpath(p) for p in anders[:20])
            + (" …" if len(anders) > 20 else ""))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fall", action="append", default=[],
                   help="nur diesen Fall (id oder Anfang davon); mehrfach möglich")
    p.add_argument("--vergleich", metavar="BRANCH",
                   help="dieselben Fälle zusätzlich gegen diesen Stand fahren")
    p.add_argument("--ausgabe", default=STANDARD_AUSGABE,
                   help=f"wohin der Bericht kommt (Standard {STANDARD_AUSGABE})")
    p.add_argument("--ohne-verdeckte", action="store_true",
                   help="die verdeckten Fälle auslassen")
    p.add_argument("--richter", help="Modell des Richters (Standard: das Chat-Modell)")
    p.add_argument("--ohne-richter", action="store_true", help="Belegpflicht nicht prüfen")
    p.add_argument("--liste", action="store_true", help="Fälle zeigen und beenden")
    p.add_argument("--trotz-budget", action="store_true",
                   help="auch fahren, wenn der Durchgang über die Prüfstand-Grenze "
                        "(pruefstand_budget_monat) ginge")
    p.add_argument("--entwurf-aus", metavar="GESPRAECH[:NACHRICHT]",
                   help="Entwurf eines Falls aus einem gespeicherten Gespräch ausgeben")
    p.add_argument("--nur-richter", metavar="ORDNER",
                   help="einen gefahrenen Durchgang nur neu richten (kostet nur den Richter)")
    p.add_argument("--ohne-modell", action="store_true",
                   help="mit --nur-richter: nur die Zitate neu prüfen, Richter nicht fragen")
    p.add_argument("--abbruch-frueh", action="store_true",
                   help="einen Fall beenden, sobald er sicher verloren ist (spart die restlichen Züge)")
    p.add_argument("--richter-batch", action="store_true",
                   help="Richter über die Message Batches API (halber Preis, Ergebnis später; "
                        "scheitert er, normal)")
    p.add_argument("--richter-batch-warten", type=float, default=30, metavar="MIN",
                   help="so lange höchstens auf den Batch warten (Standard 30 min)")
    p.add_argument("--abspielen", metavar="ORDNER",
                   help="einen aufgezeichneten Durchgang ohne Modell nachfahren (kostet nichts)")
    p.add_argument("--aufnahme", help=argparse.SUPPRESS)
    p.add_argument("--abspiel-datei", help=argparse.SUPPRESS)
    p.add_argument("--einzeln", help=argparse.SUPPRESS)
    p.add_argument("--richte", help=argparse.SUPPRESS)
    p.add_argument("--code", help=argparse.SUPPRESS)
    p.add_argument("--daten", help=argparse.SUPPRESS)
    p.add_argument("--ergebnis", help=argparse.SUPPRESS)
    a = p.parse_args()

    if a.einzeln:
        return einzeln(a)
    daten = a.daten or umgebung.daten_wurzel(ROOT)
    if a.richte:
        a.daten = daten
        return richten(a)
    if a.nur_richter:
        return nur_richter(a, daten)
    if a.liste:
        for f in faelle.alle():
            print(f"{f['id']:<28} {len(f['zuege'])} Züge  "
                  f"{'(verdeckt) ' if f.get('verdeckt') else ''}{f['titel']}")
        return 0
    if a.entwurf_aus:
        gid, _, nid = a.entwurf_aus.partition(":")
        print(faelle.entwurf_aus_gespraech(os.path.join(daten, "data", "gespraeche"),
                                           gid, nid or None))
        return 0

    liste = (faelle.finden(a.fall, mit_verdeckten=not a.ohne_verdeckte) if a.fall
             else faelle.alle(mit_verdeckten=not a.ohne_verdeckte))
    if not os.path.exists(os.path.join(daten, "data", "ai_config.json")):
        sys.exit(f"Keine Einstellungen unter {daten}/data/ai_config.json — ohne Schlüssel kein Modell.")

    if a.abspielen:
        quelle = os.path.join(os.path.abspath(a.abspielen), "aufnahmen")
        da = {os.path.splitext(n)[0] for n in os.listdir(quelle)} if os.path.isdir(quelle) else set()
        fehlen = [f["id"] for f in liste if f["id"] not in da]
        liste = [f for f in liste if f["id"] in da]
        if fehlen:
            print(f"Ohne Aufnahme, ausgelassen: {', '.join(fehlen)}")
        if not liste:
            sys.exit(f"Keine Aufnahmen unter {quelle}.")
    lage = None if a.abspielen else topf_lage(daten)
    if lage:
        ausgegeben, limit = lage
        schaetzung = SCHAETZUNG_EUR * len(liste) / 7 * (2 if a.vergleich else 1)
        print(f"Prüfstand diesen Monat: {ausgegeben:.2f} € von {limit:.2f} € ausgegeben; "
              f"dieser Durchgang etwa {schaetzung:.2f} €.")
        if ausgegeben + schaetzung > limit and not a.trotz_budget:
            sys.exit("Das ginge über die Prüfstand-Grenze im Monat (pruefstand_budget_monat). "
                     "Abbruch; mit --trotz-budget trotzdem fahren. Sashas Chat-Budget "
                     "berührt der Prüfstand nicht mehr.")

    stempel = datetime.now().strftime("%Y-%m-%d_%H%M") + ("_abgespielt" if a.abspielen else "")
    ordner = os.path.join(os.path.abspath(a.ausgabe), stempel)
    print(f"Prüfstand: {len(liste)} Fälle → {ordner}")
    vorher = fingerabdruck(daten)

    print(f"\n{stand_von(ROOT)}")
    d = durchgang(liste, code=ROOT, daten=daten, ordner=ordner, a=a)
    d["isolation"] = isolation_text(vorher, fingerabdruck(daten))
    d["topf"] = topf_text(daten)
    pfad = bericht.schreiben(d, ordner)

    if a.vergleich:
        wt = tempfile.mkdtemp(prefix="zentrale_vergleich_")
        os.rmdir(wt)
        subprocess.run(["git", "-C", ROOT, "worktree", "add", "--detach", wt, a.vergleich],
                       check=True, capture_output=True)
        try:
            print(f"\n{a.vergleich} ({stand_von(wt)})")
            vorher_b = fingerabdruck(daten)
            ob = os.path.join(ordner, "vergleich_" + a.vergleich.replace("/", "_"))
            db = durchgang(liste, code=wt, daten=daten, ordner=ob, a=a)
            db["isolation"] = isolation_text(vorher_b, fingerabdruck(daten))
            bericht.schreiben(db, ob)
            text = bericht.vergleich(d, db, stand_von(ROOT), a.vergleich)
            with open(os.path.join(ordner, "vergleich.md"), "w", encoding="utf-8") as f:
                f.write(text)
            print("\n" + text)
        finally:
            subprocess.run(["git", "-C", ROOT, "worktree", "remove", wt],
                           capture_output=True)

    s = d["summen"]
    print(f"\nEndzustand {s['endzustand_ok']}/{s['faelle']} Fälle "
          f"({s['pruefungen_ok']}/{s['pruefungen']} Prüfungen) · Behauptungen "
          f"{s['belegt']} belegt, {s['vermutung']} Vermutung, {s['unbelegt']} unbelegt, "
          f"{s['falsch']} falsch · {s['kosten_gesamt_eur']:.3f} €")
    print(f"Isolation: {d['isolation']}")
    print(f"Prüfstand-Kosten: {d['topf']}")
    print(f"Bericht: {pfad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
