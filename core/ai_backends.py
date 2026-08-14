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
# der Env, via ai_config aus data/ai_config.json) UND sein Host erreichbar
# ist (= Internet an). Offline → cloud=False, auch wenn ein Key gesetzt ist.
#
# Nebenwirkungsarm + kurz gecacht, weil die Erkennung Netz-Pings macht.

import os
import time
import socket
from urllib.parse import urlparse

import ai                # is_available() pingt Ollama /api/tags
import ai_config         # Kill-Switches + Key-Injection in os.environ (Import-Effekt)
import providers         # Cloud-Registry des Kerns: key_env / base_url

LOCAL = "local"
CLOUD = "cloud"

# Welche Backends ein Modul nutzen KANN (geordnete Präferenz). Verfügbar, sobald
# eines davon da ist. Tutor = beide → Multi-Backend strukturell vorbereitet.
MODULE_BACKENDS = {
    "chat":  (LOCAL, CLOUD),   # seit core/cloud.py existiert (Anthropic-Kernpfad)
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
    Keys kommen via ai_config NUR aus data/ai_config.json (Single Source of
    Truth seit 2026-07-17; ein Legacy-keys-Block in data/tutor_config.json wird
    ignoriert). Nur die Switches cloud/local haben noch den Legacy-Fallback."""
    return providers.configured()


def cloud_enabled() -> bool:
    """Cloud-Kill-Switch: ist Cloud manuell freigegeben? (Default True.)
    Aus → cloud_ok()=False, egal ob Key/Internet da. Datenschutz-/Kosten-Drossel,
    in der Config (data/ai_config.json, key 'cloud_enabled') persistiert.
    Gilt ZENTRALE-weit — auch für den Tutor, den core/tutor_port.py hiermit gated."""
    v = ai_config.setting("cloud_enabled", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "off", "no", "aus", "nein")
    return bool(v)


def set_cloud_enabled(on: bool, persist: bool = True) -> bool:
    """Cloud-Drossel umlegen (live, optional persistiert). Invalidiert den Cache,
    damit EXTERNAL/Gating sofort reagieren. Gibt den neuen Zustand zurück."""
    ai_config.set_override("cloud_enabled", bool(on), persist=persist)
    _cache["val"] = None
    return bool(on)


def local_enabled() -> bool:
    """Lokal-Kill-Switch: ist die lokale KI (Ollama) manuell freigegeben?
    (Default True.) Aus → local gilt als nicht da (Drossel), egal ob Ollama
    läuft. Pendant zu cloud_enabled – so lässt sich auch die lokale Leitung
    drosseln (z.B. TUI-Chat übers PC-Hirn aus). Persistiert in
    data/ai_config.json (key 'local_enabled')."""
    v = ai_config.setting("local_enabled", True)
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "off", "no", "aus", "nein")
    return bool(v)


def set_local_enabled(on: bool, persist: bool = True) -> bool:
    """Lokal-Drossel umlegen (live, optional persistiert). Invalidiert den Cache,
    damit EXTERNAL/Gating sofort reagieren. Gibt den neuen Zustand zurück."""
    ai_config.set_override("local_enabled", bool(on), persist=persist)
    _cache["val"] = None
    return bool(on)


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

    local_en = local_enabled()
    local    = local_en and local_ok()   # Drossel aus → local gilt als nicht da
    prov    = cloud_provider()
    enabled = cloud_enabled()
    cloud   = False
    if prov and enabled:   # Kill-Switch aus → Cloud gilt als nicht da
        base = providers.get(prov).get("base_url") or "https://api.openai.com"
        cloud = _reachable(urlparse(base).hostname)

    st = {LOCAL: local, CLOUD: cloud, "cloud_provider": prov,
          "cloud_enabled": enabled, "local_enabled": local_en, "any": (local or cloud)}
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


def pick(module: str) -> str | None:
    """
    Welches Backend dieses Modul JETZT konkret nutzt — oder None (keins da).

    Unterschied zu module_ok(): das sagt nur OB eins da ist, das hier sagt
    WELCHES. Erstes verfügbares aus der Präferenz-Reihenfolge.

    Für 'chat' gibt es zusätzlich eine bewusste Vorwahl (siehe chat_backend()):
    beide Backends können gleichzeitig da sein, und dann ist die Reihenfolge
    in MODULE_BACKENDS eine Design-Entscheidung, keine Verfügbarkeitsfrage.
    """
    st = status()
    order = module_backends(module)
    if module == "chat":
        # core/cloud.py spricht Anthropic, sonst nichts. Ein gesetzter
        # DashScope-Key macht status()[CLOUD] wahr, hilft dem Kern aber kein
        # Stück — dann ist Cloud für den Chat schlicht nicht da.
        if st.get(CLOUD) and st.get("cloud_provider") != "claude":
            st = dict(st, **{CLOUD: False})
        want = chat_backend()
        if want in (LOCAL, CLOUD):
            # Ausdrückliche Wahl: nur dieses Backend, kein stiller Rückfall auf
            # das andere. Ein stiller Fallback wäre hier gefährlich — der
            # Unterschied ist, ob Sashas Daten das Haus verlassen.
            return want if st.get(want) else None
        # 'auto' → wie jedes andere Modul: erstes verfügbares.
    for b in order:
        if st.get(b):
            return b
    return None


def chat_backend() -> str:
    """
    Vorwahl für den Chat-Kern: 'auto' | 'local' | 'cloud'.

    'auto' (Default) folgt MODULE_BACKENDS — also lokal zuerst, solange Ollama
    läuft. Wer den Cloud-Assistenten WILL (der ganze Grund für core/cloud.py),
    stellt hier 'cloud' ein; sonst gewinnt das lokale 9b weiterhin jeden Turn,
    einfach weil es erreichbar ist.

    Persistiert in data/ai_config.json (key 'chat_backend'), per Env
    ZENTRALE_CHAT_BACKEND übersteuerbar.
    """
    v = os.environ.get("ZENTRALE_CHAT_BACKEND") or ai_config.setting("chat_backend", "auto")
    v = str(v).strip().lower()
    return v if v in (LOCAL, CLOUD, "auto") else "auto"


def set_chat_backend(which: str, persist: bool = True) -> str:
    """Chat-Vorwahl umlegen (live, optional persistiert). Invalidiert den Cache."""
    which = str(which).strip().lower()
    if which not in (LOCAL, CLOUD, "auto"):
        raise ValueError(f"chat_backend: 'auto', '{LOCAL}' oder '{CLOUD}', nicht {which!r}")
    ai_config.set_override("chat_backend", which, persist=persist)
    _cache["val"] = None
    return which
