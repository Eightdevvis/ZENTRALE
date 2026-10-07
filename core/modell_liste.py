# core/modell_liste.py
#
# Welche Modelle ein Anbieter WIRKLICH hat — vom Anbieter selbst gefragt,
# gecacht, mit der Tabelle in providers.py als Rückfall.
#
# 2026-10-07, Sasha: „/modell sollte einfach alle anzeigen die available is".
# Vorher bot /modell nur Standard + billig aus providers.py an; ein neues
# Modell ging nur, wenn man seinen Namen schon kannte.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md): fragt per net (Log im
# Terminal, wie jeder Netz-Zugriff), kennt die KI-Schleife nicht.
#
# ── Woher ──────────────────────────────────────────────────────────────
#   anthropic      GET https://api.anthropic.com/v1/models (seitenweise,
#                  x-api-key + anthropic-version)
#   openai_compat  GET {base_url}/models (Bearer)
# Der Schlüssel geht nur im Kopf der Anfrage mit; net loggt nur die Adresse.
#
# ── Nur Chat-Modelle ───────────────────────────────────────────────────
# OpenAI-kompatible Anbieter liefern alles mit: Embeddings, Sprache, Bilder,
# Moderation, Video. Gefiltert wird mit einer schlichten Wortliste auf dem
# Namen (_KEIN_CHAT) — die Anbieter sagen den Typ nicht einheitlich mit, eine
# Liste von Wortstücken ist dafür ehrlich genug. Lieber ein Exot zu viel in
# der Liste (Sasha wählt ihn nicht) als ein Chat-Modell zu wenig.
# Anthropic liefert nur Chat-Modelle; dort wird nicht gefiltert.
#
# ── Cache (Entscheidung 2026-10-07) ───────────────────────────────────
# Eine Datei pro Rechner unter ~/.cache/zentrale/modelle.json (umlenkbar per
# modell_cache_dir bzw. XDG_CACHE_HOME), 24 h gültig. NICHT data/: data/
# synct zwischen den Rechnern (neueste Datei gewinnt) — eine Liste, die
# jeder Rechner in einer Minute selbst neu holen kann, gehört nicht in den
# Sync, und zwei Rechner würden sich die Datei gegenseitig überschreiben.
# Ein Fehlschlag wird 10 Minuten gemerkt, damit /modell offline nicht bei
# jedem Öffnen auf eine Zeitüberschreitung wartet.
#
# Schalter: modell_liste_holen = aus → nie fragen, nur die Tabelle (offline,
# Tests).

import json
import os
import time

import ai_config
import dateien
import net
import providers

GUELTIG_S = 24 * 3600
FEHLER_GUELTIG_S = 10 * 60
ZEITLIMIT_S = 6

# Wortstücke im Modellnamen, die KEIN Text-Chat-Modell sind.
_KEIN_CHAT = (
    "embed", "embedding", "bge-", "rerank",            # Vektoren, Sortieren
    "whisper", "tts", "audio", "speech", "transcribe",  # Sprache
    "asr", "paraformer", "cosyvoice", "sambert", "realtime",
    "dall-e", "image", "imagen", "wanx", "flux", "stable-diffusion",  # Bilder
    "sora", "veo", "video",                             # Video
    "moderation", "guard",                              # Prüfen statt reden
    "babbage", "davinci",                               # nur alte Vervollständigung
)


def ist_chat(modell: str) -> bool:
    """Ist das (dem Namen nach) ein Text-Chat-Modell?"""
    n = (modell or "").lower()
    return bool(n) and not any(stueck in n for stueck in _KEIN_CHAT)


def _cache_pfad() -> str:
    eigen = ai_config.setting("modell_cache_dir")
    if eigen:
        basis = os.path.abspath(os.path.expanduser(str(eigen)))
    else:
        cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        basis = os.path.join(cache, "zentrale")
    return os.path.join(basis, "modelle.json")


def _cache_lesen() -> dict:
    try:
        with open(_cache_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_schreiben(name: str, eintrag: dict):
    d = _cache_lesen()
    d[name] = eintrag
    try:
        os.makedirs(os.path.dirname(_cache_pfad()), exist_ok=True)
        dateien.json_schreiben(_cache_pfad(), d)
    except OSError as e:
        print(f"[modell_liste] Cache nicht schreibbar: {e}")


def _holen_json(url: str, kopf: dict) -> dict:
    """Eine Anfrage. Eigene Funktion, damit Tests das Netz ersetzen."""
    return json.loads(net.get(url, timeout=ZEITLIMIT_S, headers=kopf).decode("utf-8"))


def _ids(antwort) -> list:
    """{"data": [{"id"}]} (beide Dialekte), {"models": […]} oder eine Liste."""
    if isinstance(antwort, dict):
        eintraege = antwort.get("data", antwort.get("models", []))
    else:
        eintraege = antwort
    raus = []
    for e in eintraege or []:
        mid = e.get("id") or e.get("name") if isinstance(e, dict) else e
        if isinstance(mid, str) and mid.strip():
            mid = mid.strip()
            # Gemini (OpenAI-kompatibel) meldet „models/gemini-…"; im Aufruf
            # geht der kurze Name.
            if mid.startswith("models/"):
                mid = mid[len("models/"):]
            raus.append(mid)
    return raus


def _vom_anbieter(name: str) -> list:
    """Die Modell-Namen, wie der Anbieter sie meldet. Wirft bei Fehlern."""
    p = providers.get(name)
    key = os.environ.get(p.get("key_env") or "", "")
    if p.get("kind") == "anthropic":
        basis = (p.get("base_url") or "https://api.anthropic.com").rstrip("/")
        kopf = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        raus, nach = [], None
        for _ in range(10):                     # Seiten; 10 × 1000 reicht
            url = f"{basis}/v1/models?limit=1000" + (f"&after_id={nach}" if nach else "")
            antwort = _holen_json(url, kopf)
            raus += _ids(antwort)
            if not (isinstance(antwort, dict) and antwort.get("has_more")
                    and antwort.get("last_id")):
                break
            nach = antwort["last_id"]
        return raus
    if p.get("kind") == "openai_compat":
        url = (p.get("base_url") or "").rstrip("/") + "/models"
        return [m for m in _ids(_holen_json(url, {"Authorization": f"Bearer {key}"}))
                if ist_chat(m)]
    raise ValueError(f"mit {name} kann ZENTRALE nicht reden")


def tabelle(name: str) -> list:
    """Standard und billig aus providers.py (der Rückfall)."""
    p = providers.get(name)
    return [m for m in (p.get("default_model"), p.get("cheap_model")) if m]


def _holen_an() -> bool:
    return str(ai_config.setting("modell_liste_holen", "an")).strip().lower() \
        not in ("aus", "off", "0", "nein", "false")


def holen(name: str, *, jetzt: float | None = None) -> tuple:
    """Die Chat-Modelle dieses Anbieters. -> (liste, quelle)

    quelle: "anbieter" (frisch oder aus dem Cache) oder "tabelle"
    (kein Schlüssel, ausgeschaltet, Fehler — dann providers.py).
    Sortiert: was die Tabelle nennt zuerst, dann alphabetisch."""
    p = providers.get(name)
    if not p or not p.get("kind"):
        return tabelle(name), "tabelle"
    if not (p.get("key_env") and os.environ.get(p["key_env"])) or not _holen_an():
        return tabelle(name), "tabelle"
    jetzt = time.time() if jetzt is None else jetzt
    eintrag = _cache_lesen().get(name) or {}
    alter = jetzt - float(eintrag.get("zeit") or 0)
    if eintrag.get("modelle") and alter < GUELTIG_S:
        return _sortiert(name, eintrag["modelle"]), "anbieter"
    if eintrag.get("fehler") and alter < FEHLER_GUELTIG_S:
        return _rueckfall(name, eintrag), "tabelle"
    try:
        modelle = sorted(set(_vom_anbieter(name)))
    except Exception as e:
        grund = str(e)[:200] or type(e).__name__
        print(f"[modell_liste] {name}: Liste nicht holbar ({grund}) — Tabelle")
        # Die alte Liste bleibt im Eintrag: lieber gestern als nur zwei.
        _cache_schreiben(name, {"zeit": jetzt, "fehler": grund,
                                "modelle_alt": eintrag.get("modelle")
                                or eintrag.get("modelle_alt") or []})
        return _rueckfall(name, _cache_lesen().get(name) or {}), "tabelle"
    if not modelle:
        _cache_schreiben(name, {"zeit": jetzt, "fehler": "leere Liste"})
        return tabelle(name), "tabelle"
    _cache_schreiben(name, {"zeit": jetzt, "modelle": modelle})
    return _sortiert(name, modelle), "anbieter"


def _rueckfall(name: str, eintrag: dict) -> list:
    alt = eintrag.get("modelle_alt") or []
    return _sortiert(name, alt) if alt else tabelle(name)


def _sortiert(name: str, modelle) -> list:
    vorne = [m for m in tabelle(name) if m in modelle]
    return vorne + sorted(m for m in set(modelle) if m not in vorne)
