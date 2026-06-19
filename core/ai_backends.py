# core/ai_backends.py
#
# AI-Backend-Verfügbarkeit – die zentrale „welche KI ist hier erreichbar?"-Schicht.
#
# ── Idee (geräte- + modulweise) ─────────────────────────────────────────
#   1. GERÄT fragt: welche Backends sind da?  →  local (Ollama) / cloud (Online)
#      PC: meist beide. Laptop: mal local (PC via SSH), mal cloud, mal nichts.
#   2. Kein Backend da  → kein AI-Render (datengetrieben, nicht mehr kassetten-hart).
#   3. MODUL fragt: „mein Backend da?" → nein: Modul deaktiviert („backend not here").
#
# ── Multi-Backend (vorbereitet) ─────────────────────────────────────────
# Ein Modul kann MEHRERE Backends akzeptieren (MODULE_BACKENDS) – es ist
# verfügbar, sobald IRGENDEINES davon da ist. Aktuell nutzt das nur der Tutor
# (local ODER cloud); die Struktur ist aber allgemein, damit weitere Module
# später einfach „kann beides" werden können.
#
# ── cloud = da, wenn Internet an ───────────────────────────────────────
# Cloud gilt als verfügbar, wenn ein Cloud-Provider konfiguriert ist (Key in
# der Env, via tutor_config aus data/tutor_config.json) UND sein Host erreichbar
# ist (= Internet an). Offline → cloud=False, auch wenn ein Key gesetzt ist.
#
# Nebenwirkungsarm + kurz gecacht, weil die Erkennung Netz-Pings macht.

import os
import time
import socket
from urllib.parse import urlparse

import ai                # is_available() pingt Ollama /api/tags
import tutor_config      # injiziert Provider-Keys in os.environ (Import-Effekt)
import tutor_providers   # Provider-Registry: kind / key_env / base_url

LOCAL = "local"
CLOUD = "cloud"

# Welche Backends ein Modul nutzen KANN (geordnete Präferenz). Verfügbar, sobald
# eines davon da ist. Tutor = beide → Multi-Backend strukturell vorbereitet.
MODULE_BACKENDS = {
    "chat":  (LOCAL,),
    "news":  (LOCAL,),
    "tutor": (LOCAL, CLOUD),
}

_CACHE_TTL = 5.0
_cache = {"t": 0.0, "val": None}


def local_ok() -> bool:
    """Lokales Ollama erreichbar?"""
    return ai.is_available()


def cloud_provider() -> str:
    """Name eines KONFIGURIERTEN Cloud-Providers (Key gesetzt) – oder None.
    Konfiguriert = openai_compat/anthropic-Provider, dessen key_env in der Env
    gesetzt ist (Keys kommen via tutor_config aus data/tutor_config.json)."""
    for name, p in tutor_providers.PROVIDERS.items():
        if p.get("kind") in ("openai_compat", "anthropic"):
            env = p.get("key_env")
            if env and os.environ.get(env):
                return name
    return None


def _reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    """Leichter Erreichbarkeits-Check (TCP-Connect, kein HTTP)."""
    if not host:
        return False
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def status(fresh: bool = False) -> dict:
    """Geräte-Status der AI-Backends (kurz gecacht – die Erkennung pingt Netz).

    Rückgabe:
      { "local": bool, "cloud": bool, "cloud_provider": str|None,
        "any": bool, "modules": { "chat": bool, "news": bool, "tutor": bool } }
    """
    now = time.time()
    if not fresh and _cache["val"] is not None and (now - _cache["t"]) < _CACHE_TTL:
        return _cache["val"]

    local = local_ok()
    prov  = cloud_provider()
    cloud = False
    if prov:
        base = tutor_providers.get(prov).get("base_url") or "https://api.openai.com"
        cloud = _reachable(urlparse(base).hostname)

    st = {LOCAL: local, CLOUD: cloud, "cloud_provider": prov, "any": (local or cloud)}
    st["modules"] = {m: any(st.get(b) for b in bk) for m, bk in MODULE_BACKENDS.items()}

    _cache["t"], _cache["val"] = now, st
    return st


def any_ai() -> bool:
    """Ist überhaupt irgendein AI-Backend da? (sonst: kein AI-Render)"""
    return status()["any"]


def cloud_ok() -> bool:
    return status()[CLOUD]


def module_backends(module: str) -> tuple:
    """Welche Backends das Modul akzeptiert (geordnete Präferenz)."""
    return MODULE_BACKENDS.get(module, (LOCAL,))


def module_ok(module: str) -> bool:
    """Hat das Modul mindestens EIN nutzbares Backend? (sonst: 'backend not here')"""
    st = status()
    return any(st.get(b) for b in module_backends(module))
