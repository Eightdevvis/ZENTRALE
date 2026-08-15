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
    """
    Welcher Cloud-Provider JETZT dran ist – oder None.

    Drei Dinge entscheiden das, in dieser Reihenfolge:
      1. **Budget aufgebraucht** → der billigste erreichbare Provider. Lieber
         weiterreden auf einem günstigen Modell als gar nicht mehr reden.
      2. **Ausdrückliche Wahl** (`chat_provider`, z.B. 'claude' oder 'grok').
         Ohne Key für genau den → None. Nichts vortäuschen und still auf einen
         anderen Anbieter ausweichen: wohin die Daten gehen, ist keine
         Nebensache.
      3. **'auto'** → erster Provider mit Key aus providers.PREFERENCE.

    Keys kommen via ai_config NUR aus data/ai_config.json.
    """
    if budget_lage()["status"] == "over":
        billig = _billigster_erreichbarer()
        if billig:
            return billig
    want = chat_provider()
    if want != "auto":
        p = providers.get(want)
        if p and os.environ.get(p.get("key_env") or ""):
            return want
        return None
    return providers.configured()


def _erreichbare_provider() -> list:
    """Provider, für die ein Key gesetzt ist UND deren Dialekt der Kern
    spricht. Reine Konfigurations-Frage, kein Netz-Ping."""
    return [n for n, p in providers.PROVIDERS.items()
            if os.environ.get(p.get("key_env") or "")
            and cloud_kind_for(n)]


def _billigster_erreichbarer() -> str | None:
    """Der günstigste erreichbare Provider, gemessen am Ausgabepreis seines
    Modells (Ausgabe kostet ein Vielfaches der Eingabe). Für den
    Budget-Rückfall."""
    import prices
    kandidaten = _erreichbare_provider()
    if not kandidaten:
        return None
    return min(kandidaten,
               key=lambda n: (prices.fuer(chat_model(n))["out"],
                              prices.fuer(chat_model(n))["in"]))


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
        # Erreichbar heißt noch nicht bedienbar: für einen Provider, dessen
        # Dialekt der Kern nicht spricht (kein 'kind' in der Registry), ist
        # Cloud für den Chat schlicht nicht da.
        if st.get(CLOUD) and not cloud_kind_for(st.get("cloud_provider")):
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


def cloud_kind_for(provider: str | None) -> str | None:
    """
    Welchen Dialekt ein Provider spricht — oder None, wenn der Kern mit ihm
    nicht reden kann. 'anthropic' | 'openai_compat'.
    """
    kind = providers.get(provider or "").get("kind")
    return kind if kind in ("anthropic", "openai_compat") else None


def chat_cloud_kind() -> str | None:
    """Dialekt des AKTUELLEN Cloud-Providers (über status(), damit Aufrufer
    und Tests dieselbe Quelle sehen)."""
    return cloud_kind_for(status().get("cloud_provider"))


def chat_cloud_module():
    """
    Das Modul, das den Cloud-Chat bedient — nach Dialekt des Providers.
    Lazy importiert: beide Module ziehen ai/graph nach und sollen nicht schon
    beim Import von ai_backends geladen werden.
    """
    kind = chat_cloud_kind()
    if kind == "anthropic":
        import cloud
        return cloud
    if kind == "openai_compat":
        import cloud_openai
        return cloud_openai
    return None


def chat_available() -> str | None:
    """
    Welches Backend den Chat JETZT bedienen darf — inklusive Kassetten-Regel.
    None heißt: kein Chat. DIE Frage, die alle Chat-Endpoints stellen sollten,
    damit sie nicht auseinanderlaufen.

    Die Regel: eine ki-freie Kassette (laptop/tui) bringt **keine eigene KI**
    mit — deshalb ist LOCAL dort aus. Eine CLOUD-KI ist aber nicht die KI
    dieser Kassette, sondern eine externe Leitung; die darf sie nutzen. Genau
    das ist der Unterwegs-Fall: Laptop ohne Ollama, Chat trotzdem da.

    Vorher war das kassetten-HART (`ki_aus()` → 503, egal was erreichbar ist).
    Derselbe Umbau, den der Tutor 2026-07-16 schon bekommen hat: nicht fragen
    "welche Kassette", sondern "was ist erreichbar".
    """
    import kassette
    b = pick("chat")
    if b == LOCAL and kassette.ki_aus():
        return None
    return b


# ── Wer denkt, womit, wie tief ─────────────────────────────────────────
#
# Drei Regler, die zusammengehören und bewusst getrennt sind:
#
#   chat_provider  WELCHER ANBIETER   'auto' | claude | qwen | grok | …
#   chat_model     WELCHES MODELL     pro Anbieter eigen — 'claude-opus-5'
#                                     bedeutet Grok nichts
#   chat_effort    WIE TIEF           nur Anthropic kennt das; anderswo
#                                     läuft es ins Leere statt zu krachen
#
# Umschalten ist damit eine Config-Zeile, kein Umbau — auch auf einen
# Anbieter, für den heute noch gar kein Key existiert.

def chat_provider() -> str:
    """Ausdrücklich gewählter Cloud-Anbieter, oder 'auto'."""
    v = os.environ.get("ZENTRALE_CHAT_PROVIDER") or \
        ai_config.setting("chat_provider", "auto")
    v = str(v).strip().lower()
    return v if v == "auto" or v in providers.PROVIDERS else "auto"


def set_chat_provider(name: str, persist: bool = True) -> str:
    name = str(name).strip().lower()
    if name != "auto" and name not in providers.PROVIDERS:
        raise ValueError(f"unbekannter Provider: {name!r} — bekannt sind "
                         f"{sorted(providers.PROVIDERS)} oder 'auto'")
    ai_config.set_override("chat_provider", name, persist=persist)
    _cache["val"] = None
    return name


def chat_model(provider: str | None = None) -> str:
    """
    Modell für einen Anbieter. PRO ANBIETER gespeichert, damit ein Wechsel
    hin und zurück nicht jedes Mal die Modellwahl vergisst — und damit nie
    ein Anthropic-Modellname an Grok geschickt wird.

    Reihenfolge: Env → gespeicherte Wahl → default_model des Anbieters.
    """
    # Env meint immer „das Modell, das JETZT läuft" — also nur, wenn nach dem
    # aktuellen Anbieter gefragt wird (provider=None). Sonst käme beim Blick
    # auf einen anderen Anbieter dessen Modell falsch heraus.
    if provider is None:
        env = os.environ.get("ZENTRALE_CLOUD_MODEL")
        if env:
            return env
    name = provider or cloud_provider() or ""
    gespeichert = ai_config.setting("chat_models", None) or {}
    if isinstance(gespeichert, dict) and gespeichert.get(name):
        return str(gespeichert[name])
    return providers.get(name).get("default_model") or ""


def set_chat_model(model: str, provider: str | None = None) -> str:
    """Modell für einen Anbieter festlegen (Default: den aktuellen)."""
    name = provider or cloud_provider() or ""
    if not name:
        raise ValueError("kein Provider aktiv — erst set_chat_provider()")
    gespeichert = dict(ai_config.setting("chat_models", None) or {})
    gespeichert[name] = str(model).strip()
    ai_config.set_override("chat_models", gespeichert, persist=True)
    _cache["val"] = None
    return gespeichert[name]


EFFORT_STUFEN = ("low", "medium", "high", "xhigh", "max")


def chat_effort() -> str:
    """
    Denk-Tiefe. Nur Anthropic kennt den Regler; bei allen anderen ignoriert
    ihn das jeweilige Modul stillschweigend.

    Default 'low': auf Opus 5 ist Denken per Default AN und zählt als OUTPUT,
    und Output ist der teuerste Token (25 $/Mio gegen 5 $ für Input). Ein Turn
    auf 'high' erzeugt schnell das Dreifache an Denk-Token. Fürs Plaudern ist
    das rausgeworfenes Geld.
    """
    v = os.environ.get("ZENTRALE_CHAT_EFFORT") or \
        ai_config.setting("chat_effort", "low")
    v = str(v).strip().lower()
    return v if v in EFFORT_STUFEN else "low"


def set_chat_effort(level: str, persist: bool = True) -> str:
    level = str(level).strip().lower()
    if level not in EFFORT_STUFEN:
        raise ValueError(f"effort: {EFFORT_STUFEN}, nicht {level!r}")
    ai_config.set_override("chat_effort", level, persist=persist)
    return level


# ── Budget ─────────────────────────────────────────────────────────────
#
# Ein Deckel, der NICHT abschaltet, sondern auf den billigsten erreichbaren
# Anbieter zurückfällt. Der Unterschied ist wichtig: eine Assistentin, die
# ab dem 20. des Monats schweigt, ist kaputt. Eine, die ab dem 20. billiger
# denkt, ist immer noch da.

def budget_monat() -> float | None:
    """Monatsdeckel in Euro, oder None (kein Deckel)."""
    v = ai_config.setting("budget_monat_euro", None)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def set_budget_monat(euro: float | None, persist: bool = True):
    ai_config.set_override("budget_monat_euro",
                           None if euro is None else float(euro),
                           persist=persist)
    _cache["val"] = None
    return euro


BUDGET_WARNUNG = 0.8   # ab 80 % des Deckels warnen


def budget_lage() -> dict:
    """
    Wo stehen wir im Monat? {'status': 'ok'|'warn'|'over', 'ausgegeben',
    'limit', 'anteil'}. Ohne Deckel immer 'ok'.
    """
    limit = budget_monat()
    try:
        import usage
        ausgegeben = usage.monat_euro()
    except Exception:
        ausgegeben = 0.0
    if not limit or limit <= 0:
        return {"status": "ok", "ausgegeben": ausgegeben,
                "limit": None, "anteil": 0.0}
    anteil = ausgegeben / limit
    status_ = "over" if anteil >= 1.0 else ("warn" if anteil >= BUDGET_WARNUNG else "ok")
    return {"status": status_, "ausgegeben": ausgegeben,
            "limit": limit, "anteil": anteil}


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
