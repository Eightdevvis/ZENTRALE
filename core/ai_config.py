# core/ai_config.py
#
# ZENTRALEs eigene AI-Konfiguration: die Kill-Switches (cloud/local) und der
# API-Key-Store der Maschine.
#
# ── Warum es diese Datei gibt ───────────────────────────────────────────
# cloud_enabled/local_enabled sind ZENTRALE-INTERN: sie sagen, welche KI-Leitung
# diese Maschine überhaupt benutzen darf (Datenschutz-/Kosten-Drossel). Sie
# lagen bis 2026-07-16 in core/tutor_config.py und damit in data/tutor_config.json
# — d.h. der Kern (ai_backends → chat/news/EXTERNAL) hing an einer Tutor-Datei.
# Das war der Pfeil verkehrt herum: der Tutor ist ein Addon, kein versteckter
# Core. Jetzt gehört die Drossel dem Core; der Tutor ist nur noch ein Konsument
# (und wird über core/tutor_port.py gegated, ohne selbst davon zu wissen).
#
# ── Keys: EINE Quelle (data/ai_config.json), Punkt ──────────────────────
# Der Key-Store ist MASCHINEN-Ebene, nicht Modul-Ebene: nicht-leere Keys aus
# ai_config.json["keys"] wandern beim Import in os.environ (Env gewinnt, falls
# gesetzt), damit die SDKs (openai/anthropic) sie wie gewohnt finden.
#
# **Single Source of Truth (Stand 2026-07-17):** Keys werden NUR aus
# data/ai_config.json injiziert — NICHT mehr aus der Legacy-Datei
# data/tutor_config.json. Vorher las _inject_keys aus BEIDEN → derselbe
# DASHSCOPE-Key lag doppelt (in zwei Dateien, die zwischen drei Knoten rsyncen)
# und ein Key-Wechsel hätte still nur halb gegriffen. Liegt in der Legacy-Datei
# noch ein keys-Block, wird er IGNORIERT und laut angemahnt (siehe _inject_keys)
# — dort gehört kein Secret mehr hin.
#
# ── Migration der SWITCHES (kein Secret) ────────────────────────────────
# cloud_enabled/local_enabled werden weiter aus ai_config.json gelesen, mit
# data/tutor_config.json als Fallback (setting()). Das ist harmlos (kein Key)
# und hält alte Knoten am Laufen, bis sie ihr eigenes ai_config.json haben.
# Vorlage: data/ai_config.json.example.
#
# ── Sicherheit ──────────────────────────────────────────────────────────
# data/*.json ist in .gitignore → die Datei (mit Keys) wandert NIE ins Repo.
# Zusätzlich sperrt core/context.py ai_config.json gegen die lokale KI
# (Secret-Denylist) — die Whitelist `data/*.json` würde sie sonst lesbar machen.

import os
import json

_DIR          = os.path.join(os.path.dirname(__file__), "..", "data")
_CONFIG_PATH  = os.path.join(_DIR, "ai_config.json")
_LEGACY_PATH  = os.path.join(_DIR, "tutor_config.json")   # Migrations-Fallback

_config = {}
_legacy = {}


def _read(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        print(f"[ai_config] {os.path.basename(path)} nicht lesbar: {e}")
        return {}


def _load():
    global _config, _legacy
    _config = _read(_CONFIG_PATH)
    _legacy = _read(_LEGACY_PATH)


def _inject_keys():
    """API-Keys in os.environ legen (Env gewinnt). NUR aus data/ai_config.json —
    die EINE Quelle. Ein keys-Block in der Legacy-Datei wird bewusst NICHT
    injiziert, sondern nur angemahnt (dort gehört kein Secret mehr hin)."""
    for name, val in (_config.get("keys") or {}).items():
        if val and not os.environ.get(name):
            os.environ[name] = str(val)

    stale = [k for k, v in (_legacy.get("keys") or {}).items() if v]
    if stale:
        print("[ai_config] WARNUNG: data/tutor_config.json enthält noch Keys "
              f"({', '.join(sorted(stale))}) — sie werden IGNORIERT (Single Source "
              "of Truth: data/ai_config.json). Bitte den keys-Block dort entfernen.")


_overrides = {}   # Runtime-Overrides (Live-Umschalten, ohne Neustart)

_load()
_inject_keys()


def setting(name: str, default=None):
    """Wert für eine Core-AI-Einstellung.
    Precedence: Runtime-Override > Env (ZENTRALE_<NAME>) > ai_config.json >
    tutor_config.json (Legacy) > default.
    Einstellungen: cloud_enabled, local_enabled."""
    if name in _overrides:
        return _overrides[name]
    env = os.environ.get("ZENTRALE_" + name.upper())
    if env not in (None, ""):
        return env
    for src in (_config, _legacy):
        val = src.get(name)
        if val not in (None, ""):
            return val
    return default


def set_override(name: str, value, persist: bool = False):
    """Setzt eine Einstellung zur LAUFZEIT (live, ohne Neustart). Leerer Wert
    löscht den Override. persist=True schreibt zusätzlich nach
    data/ai_config.json (überlebt Neustart). Keys werden hier NICHT angefasst.

    Persistiert wird IMMER in die neue Datei — damit wächst die Migration von
    selbst, sobald Sasha das erste Mal /cloud off drückt."""
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
    """Schreibt die Core-AI-Config zurück nach data/ai_config.json.
    Die Legacy-Datei wird NIE geschrieben — der Tutor besitzt sie."""
    try:
        os.makedirs(_DIR, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(_config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ai_config] Speichern fehlgeschlagen: {e}")
