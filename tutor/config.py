# tutor/config.py
#
# Lokale Tutor-Konfiguration aus tutor/data/tutor_config.json – damit man NICHT
# bei jedem Start die Modell-Wahl per `export` ins Terminal halten muss.
# Ideal zum Durchprobieren mehrerer Modelle: Datei editieren, neu starten.
# Hält NUR: lang / provider / model / history_window.
#
# ── KEINE Keys hier (Umbau 2026-07-16) ──────────────────────────────────
# Der API-Key-Store gehört dem KERN (core/ai_config.py → data/ai_config.json)
# und injiziert die Keys beim Import in os.environ; der Cloud-Pfad
# (tutor/openai_compat.py, tutor/cloud.py) liest sie von dort. Vorher lagen die
# Keys hier — und weil ai_backends dafür in den Tutor griff, hing der halbe Kern
# an einer Tutor-Datei. Das ist jetzt getrennt: tutor/data/ enthält NIE ein
# Secret, damit ein vergessener .gitignore-Eintrag hier nichts leaken kann.
# NICHT wieder Keys hier reinlegen.
#
# Standalone (tutor/ als eigenes Projekt, ohne ZENTRALE): dann kommen die Keys
# aus der Env (`export DASHSCOPE_API_KEY=…`) — hier bleibt es bei der Wahl.
#
# ── Sicherheit ──────────────────────────────────────────────────────────
# tutor/data/*.json ist in .gitignore → die Datei wandert NIE ins Repo.
# Vorlage: tutor/data/tutor_config.json.example.
#
# ── Precedence ──────────────────────────────────────────────────────────
#   Env-Var  >  Config-Datei  >  Legacy-Datei  >  Profil-Default
# So bleibt die Config der bequeme Default, ein einmaliges `TUTOR_PROVIDER=…`
# im Terminal übersteuert sie aber für ein schnelles Experiment.
#
# ── Migration ───────────────────────────────────────────────────────────
# Gelesen wird tutor/data/tutor_config.json; fehlt ein Wert, greift die alte
# Heimat data/tutor_config.json (Legacy). Damit laufen Knoten, die den
# tutor/-Ordner noch nicht haben, unverändert weiter. Geschrieben wird immer
# die neue Datei.

import os
import json

_DIR         = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "data", "tutor_config.json")
_LEGACY_PATH = os.path.join(_DIR, "..", "data", "tutor_config.json")

_config = {}
_legacy = {}


def _read(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[tutor.config] {path} konnte nicht gelesen werden: {e}")
        return {}


def _load():
    global _config, _legacy
    _config = _read(_CONFIG_PATH)
    _legacy = _read(_LEGACY_PATH)


_overrides = {}   # Runtime-Overrides (Live-Umschalten in ZENTRALE, ohne Neustart)

_load()


def setting(name: str, default=None):
    """Wert für eine Tutor-Einstellung.
    Precedence: Runtime-Override > Env (TUTOR_<NAME>) > tutor/data/tutor_config.json
    > data/tutor_config.json (Legacy) > default.
    Einstellungen: lang, provider, model, history_window."""
    if name in _overrides:
        return _overrides[name]
    env = os.environ.get("TUTOR_" + name.upper())
    if env not in (None, ""):
        return env
    for src in (_config, _legacy):
        val = src.get(name)
        if val not in (None, ""):
            return val
    return default


def set_override(name: str, value, persist: bool = False):
    """Setzt eine Einstellung zur LAUFZEIT (live, ohne Neustart). Leerer Wert
    löscht den Override. persist=True schreibt zusätzlich in
    tutor/data/tutor_config.json (überlebt Neustart)."""
    if value in (None, ""):
        _overrides.pop(name, None)
    else:
        _overrides[name] = value
    if persist:
        if value in (None, ""):
            _config.pop(name, None)
        else:
            _config[name] = value
        _save()


def _save():
    """Schreibt die Tutor-Wahl zurück nach tutor/data/tutor_config.json.
    Die Legacy-Datei (data/tutor_config.json) wird NIE geschrieben — dort liegen
    auf alten Knoten noch Keys, die gehören uns nicht mehr."""
    try:
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[tutor.config] Speichern fehlgeschlagen: {e}")
