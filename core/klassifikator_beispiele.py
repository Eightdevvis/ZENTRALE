# core/klassifikator_beispiele.py
#
# Beispiele für einen späteren eigenen Klassifikator (2026-10-10): jede
# geprüfte Antwort der gross-Schiene als eine Zeile — ihre Sätze mit der
# Satzart laut Wortliste, die Selbstauskunft der KI, die Befunde des Prüfers
# und das Werkzeug-Protokoll in Kurzform. Daraus lassen sich Etiketten
# machen (scripts/beispiele_etikettieren.py → SetFit), ohne Sashas Gespräche
# noch einmal durchgehen zu müssen.
#
# ── Ablage: eine Datei pro Monat und Rechner, nur anhängen ──────────────
#   data/klassifikator_beispiele/<YYYY-MM>-<knoten>.jsonl
# Eine Datei pro Rechner wie bei den Bewertungen (core/rueckmeldungen.py):
# der Sync ist „neueste Datei gewinnt". Monatlich, damit keine Datei
# endlos wächst und Altes sich als Ganzes beiseitelegen lässt.
#
# Datenschutz: NUR lokal. Nicht im Abgleich (core/abgleich_auswahl.py,
# Positivliste — bewusst nicht erweitert), gitignored, geht an keinen
# Anbieter. Etikettieren per Cloud-Modell macht nur das Skript, und nur mit
# --wirklich.
#
# Einstellung `beispiele_sammeln` (an|aus, Standard an); Ort umlenkbar mit
# `klassifikator_beispiele_dir` (Env ZENTRALE_KLASSIFIKATOR_BEISPIELE_DIR;
# Tests, tests/conftest.py).
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md): nur Dateien.

import json
import os
import threading
from datetime import datetime

import ai_config
import dateien

_lock = threading.Lock()


def ordner() -> str:
    eigen = ai_config.setting("klassifikator_beispiele_dir")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                        "data", "klassifikator_beispiele"))


def an() -> bool:
    wert = str(ai_config.setting("beispiele_sammeln", "an") or "").strip().lower()
    return wert not in ("aus", "0", "false", "nein", "off")


def schreiben(datensatz: dict, *, knoten: str | None = None, jetzt: datetime | None = None):
    """Eine Zeile anhängen. -> Pfad oder None (aus). Wirft nie: ein
    Beispiel darf keinen Zug kosten."""
    if not an():
        return None
    try:
        jetzt = jetzt or datetime.now()
        kn = dateien.sicherer_name(knoten or dateien.knoten())
        zeile = {"ts": jetzt.isoformat(timespec="seconds"), "knoten": kn, **datensatz}
        roh = (json.dumps(zeile, ensure_ascii=False, default=str) + "\n").encode("utf-8")
        os.makedirs(ordner(), exist_ok=True)
        pfad = os.path.join(ordner(), f"{jetzt:%Y-%m}-{kn}.jsonl")
        # Wie core/rueckmeldungen.py: ein write() mit O_APPEND, fsync — nach
        # einem Absturz fehlt höchstens die letzte Zeile.
        with _lock:
            fd = os.open(pfad, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, roh)
                os.fsync(fd)
            finally:
                os.close(fd)
        return pfad
    except Exception:
        return None


def lesen(wo: str | None = None) -> list:
    """Alle Beispiele (alle Monate, alle Rechner), kaputte Zeilen übersprungen."""
    wo = wo or ordner()
    raus = []
    if not os.path.isdir(wo):
        return raus
    for name in sorted(os.listdir(wo)):
        if not name.endswith(".jsonl"):
            continue
        with open(os.path.join(wo, name), encoding="utf-8") as f:
            for zeile in f:
                try:
                    raus.append(json.loads(zeile))
                except ValueError:
                    continue
    return raus
