# core/tutor_config.py
#
# Lokale Tutor-Konfiguration aus data/tutor_config.json – damit man NICHT bei
# jedem Start Keys und Modell-Wahl per `export` ins Terminal halten muss.
# Ideal zum Durchprobieren mehrerer Modelle: Datei editieren, neu starten.
#
# ── Sicherheit ──────────────────────────────────────────────────────────
# data/*.json ist in .gitignore → die Datei (mit API-Keys) wandert NIE ins
# Repo. Vorlage ohne Secrets: data/tutor_config.json.example.
#
# ── Precedence ──────────────────────────────────────────────────────────
#   Env-Var  >  Config-Datei  >  Profil-Default
# So bleibt die Config der bequeme Default, ein einmaliges `TUTOR_PROVIDER=…`
# im Terminal übersteuert sie aber für ein schnelles Experiment.
#
# ── Keys ────────────────────────────────────────────────────────────────
# Nicht-leere Keys aus config["keys"] werden beim Import in os.environ
# injiziert (nur falls dort noch nicht gesetzt) – so finden die SDKs
# (openai/anthropic) sie wie gewohnt über die Env.

import os
import json

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tutor_config.json")

_config = {}


def _load():
    global _config
    if not os.path.exists(_CONFIG_PATH):
        _config = {}
        return
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            _config = json.load(f) or {}
    except Exception as e:
        print(f"[tutor_config] data/tutor_config.json konnte nicht gelesen werden: {e}")
        _config = {}


def _inject_keys():
    """API-Keys aus der Config in os.environ legen (Env gewinnt, falls gesetzt)."""
    for name, val in (_config.get("keys") or {}).items():
        if val and not os.environ.get(name):
            os.environ[name] = str(val)


_overrides = {}   # Runtime-Overrides (Live-Umschalten in ZENTRALE, ohne Neustart)

_load()
_inject_keys()


def setting(name: str, default=None):
    """Wert für eine Tutor-Einstellung.
    Precedence: Runtime-Override > Env (TUTOR_<NAME>) > Config-Datei > default.
    Einstellungen: lang, provider, model, history_window."""
    if name in _overrides:
        return _overrides[name]
    env = os.environ.get("TUTOR_" + name.upper())
    if env not in (None, ""):
        return env
    val = _config.get(name)
    if val not in (None, ""):
        return val
    return default


def set_override(name: str, value, persist: bool = False):
    """Setzt eine Einstellung zur LAUFZEIT (live, ohne Neustart). Leerer Wert
    löscht den Override. persist=True schreibt zusätzlich in data/tutor_config.json
    (überlebt Neustart). Keys werden hier NICHT angefasst."""
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
    """Schreibt die aktuelle Config (inkl. Keys) zurück nach data/tutor_config.json."""
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[tutor_config] Speichern fehlgeschlagen: {e}")
