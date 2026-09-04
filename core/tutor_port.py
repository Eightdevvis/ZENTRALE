# core/tutor_port.py
#
# Der Griff des KERNS am Sprach-Tutor — die einzige Stelle, an der ZENTRALE den
# Tutor anfasst.
#
# ── Warum es diese Datei gibt (Umbau 2026-07-16) ────────────────────────
# Vorher importierten brain.py und ui/app.py direkt tutor_session/tutor_config/
# tutor_providers/tutor_langs, und der Kern (ai_backends → chat/news/EXTERNAL)
# hing über data/tutor_config.json sogar an einer Tutor-Datei. Der Tutor war
# damit ein versteckter Core: rausziehen unmöglich, und ohne die tutor_*.py
# startete ZENTRALE nicht mal.
#
# Jetzt gilt:
#   • Der Kern redet NUR über dieses Modul mit dem Tutor. Kein anderes
#     Core-/UI-Modul importiert tutor_* — bitte so lassen.
#   • Fehlt der Tutor komplett (Ordner weg), sagt present()=False und ZENTRALE
#     läuft normal weiter. Der Import ist lazy + geschützt.
#   • Die POLICY sitzt hier, nicht im Tutor: der Cloud-/Lokal-Kill-Switch
#     (ai_backends) ist ZENTRALE-intern. Der Tutor beantwortet nur „ist mein
#     Backend erreichbar?" (tutor_session.available()); ob er DARF, entscheidet
#     der Kern hier. Deshalb kennt tutor/ die Drossel nicht mehr.
#
# ── Kontrakt zum Tutor (klein halten!) ──────────────────────────────────
# Der Port benutzt vom Tutor nur:
#   tutor.session : is_active, activate, deactivate, available, backend_kind,
#                   respond_stream, room_state, privacy_notice, presence_ping,
#                   _resolve
#   tutor.config  : setting, set_override
#   tutor.providers / tutor.langs : die Registries (nur fürs UI-Listing)
# Das ist die GANZE Schnittstelle zwischen ZENTRALE und tutor/. Wächst sie,
# wächst die Kopplung — also nicht wachsen lassen. Umgekehrt braucht tutor/ vom
# Kern nur ai.chat_stream/is_available (+ optional ai_backends, state.push_log);
# siehe Kopf von tutor/__init__.py.

import os
import sys

import ai_backends

_LOAD_ERR = None

# Der Tutor ist ein PAKET im Projekt-Root (tutor/), kein flaches core/-Modul.
# Der Port legt den Bootstrap hin, damit kein Aufrufer (app.py, main.py, Tests)
# etwas vom Tutor-Pfad wissen muss — die Naht bleibt hier.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ts():
    """tutor.session lazy holen. None → Tutor nicht installiert/kaputt."""
    global _LOAD_ERR
    try:
        if _ROOT not in sys.path:
            sys.path.insert(0, _ROOT)
        from tutor import session
        return session
    except Exception as e:      # tutor/ weg, Dependency fehlt, Syntaxfehler …
        _LOAD_ERR = str(e)
        return None


def present() -> bool:
    """Ist der Tutor auf dieser Maschine überhaupt installiert?"""
    return _ts() is not None


# ── Policy: darf der Tutor? (Kern-Entscheidung, nicht Tutor-Entscheidung) ──

def allowed() -> bool:
    """Erlaubt die ZENTRALE-Drossel den Tutor gerade?
    Cloud-Provider → cloud_enabled; lokaler Provider → local_enabled.
    Das ist der Grund, warum '/cloud off' auch die Persona stummschaltet,
    obwohl der Tutor selbst nichts von cloud_enabled weiß."""
    ts = _ts()
    if ts is None:
        return False
    try:
        if ts.backend_kind() == "ollama":
            return ai_backends.local_enabled()
        return ai_backends.cloud_enabled()
    except Exception:
        return False


def available() -> bool:
    """Ist der Tutor JETZT nutzbar? = installiert UND von der Drossel erlaubt
    UND sein Backend erreichbar. Das ist die Frage, die Fronten stellen."""
    ts = _ts()
    if ts is None or not allowed():
        return False
    try:
        return bool(ts.available())
    except Exception:
        return False


def unavailable_reason() -> str:
    """Warum geht der Tutor gerade nicht? Für ehrliche 503-Texte statt Rätselraten."""
    ts = _ts()
    if ts is None:
        return f"Tutor nicht installiert ({_LOAD_ERR})"
    if not allowed():
        kind = "lokale KI" if _safe(ts.backend_kind, "ollama") == "ollama" else "Cloud"
        return f"{kind} ist per Kill-Switch gedrosselt"
    if not _safe(ts.available, False):
        return "Provider-Backend nicht erreichbar"
    return ""


def _safe(fn, default):
    try:
        return fn()
    except Exception:
        return default


# ── Session (dünn durchgereicht) ────────────────────────────────────────

def is_active() -> bool:
    ts = _ts()
    return bool(ts and _safe(ts.is_active, False))


def activate():
    ts = _ts()
    if ts:
        ts.activate()


def deactivate():
    ts = _ts()
    if ts:
        ts.deactivate()


def respond_stream(**kw):
    """Streamt Tokens. Nur aufrufen, wenn available() — sonst leerer Stream."""
    ts = _ts()
    if ts is None:
        return iter(())
    return ts.respond_stream(**kw)


def room_state() -> dict:
    ts = _ts()
    return _safe(ts.room_state, {}) if ts else {}


def privacy_notice():
    ts = _ts()
    return _safe(ts.privacy_notice, None) if ts else None


def presence_ping() -> bool:
    """Nonverbaler Presence-Ping an die Persona (brain.py). Startet NIE eine
    Session; wirkt nur, wenn schon eine läuft. Respektiert die Drossel."""
    if not available():
        return False
    ts = _ts()
    return bool(_safe(ts.presence_ping, False))


# ── Assessment (deterministische Vokabel-Abfrage, KEIN LLM) ─────────────
# Das harte Gate vor der Persona ist reine Abfrage — das Frontend treibt es,
# nicht die Cloud-AI. Der Port reicht die Kern-Curriculum-Queue + den Lernstand
# durch und verbucht Antworten. Kein Backend-Modell involviert.

def assessment() -> dict:
    """Kern-Wörter + Fortschritt fürs Frontend-Drill (Zimmer). Leer/nicht
    installiert → {present:False}."""
    ts = _ts()
    if ts is None:
        return {"present": False}
    try:
        from tutor import tools, config as tutor_config
        lang = tutor_config.setting("lang", "zh")
        got, total = tools.core_coverage(lang)
        return {
            "present":  True,
            "lang":     lang,
            "mode":     "assessment" if tools.assessment_active(lang) else "room",
            "got":      got, "total": total,
            "ratio":    round(got / total, 3) if total else 0.0,
            "unlocked": tools.core_graduated(lang),
            "speed":    tools.tts_speed_for(lang),
            "queue":    tools.assessment_queue(lang),
            "game":     tools.game_state(lang),
        }
    except Exception as e:
        return {"present": True, "error": str(e), "queue": []}


def assessment_answer(word: str, result: str) -> dict:
    """Eine Drill-Antwort verbuchen (result: known|learned|again) und den neuen
    Stand zurückgeben. Deterministisch, kein Modell."""
    ts = _ts()
    if ts is None:
        return {"present": False}
    try:
        from tutor import tools, config as tutor_config
        lang = tutor_config.setting("lang", "zh")
        return tools.assessment_answer(lang, word, result)
    except Exception as e:
        return {"error": str(e)}


# ── Devtools ────────────────────────────────────────────────────────────
def debug_snapshot() -> dict:
    """Momentaufnahme fürs Devtools-Terminal: komplette User-Vokabel + Assessment-
    Routing (braucht der User noch das Drill?). Live-Events kommen über den
    Ereignisbus tutor/debug.py (SSE-Endpunkt in ui/app.py)."""
    ts = _ts()
    if ts is None:
        return {"present": False}
    try:
        from tutor import tools, config as tutor_config
        lang = tutor_config.setting("lang", "zh")
        return tools.debug_snapshot(lang)
    except Exception as e:
        return {"error": str(e)}


# ── Status + Config (fertig geformt fürs UI) ────────────────────────────

def status() -> dict:
    """Kern-Sicht auf den Tutor. Fronten (Browser/TUI/Zimmer) pollen das."""
    return {
        "present":         present(),
        "active":          is_active(),
        "available":       available(),
        "reason":          unavailable_reason(),
        "privacy_warning": privacy_notice(),
    }


def config(changes: dict | None = None, persist: bool = False) -> dict:
    """Liest (und optional ändert) die Live-Tutor-Konfiguration.
    changes: {lang, provider, model, history_window} — alle optional.
    Gibt die aufgelöste Wahl + wählbare Provider/Sprachen zurück."""
    ts = _ts()
    if ts is None:
        return {"present": False}

    from tutor import config as tutor_config
    from tutor import providers as tutor_providers
    from tutor import langs as tutor_langs

    for k in ("lang", "provider", "model", "history_window"):
        if changes and k in changes:
            tutor_config.set_override(k, changes[k], persist=persist)

    prof, pname, _prov, model = ts._resolve()
    return {
        "present":        True,
        "lang":           tutor_config.setting("lang", "zh"),
        "lang_name":      prof["name"],
        "persona_name":   prof.get("persona_name", prof["name"]),
        "country":        prof.get("country", ""),
        "provider":       pname,
        "model":          model,
        "trains_on_data": tutor_providers.trains_on_data(pname),
        "providers": [
            {"name": n, "default_model": p.get("default_model"),
             "trains_on_data": tutor_providers.trains_on_data(n),
             "jurisdiction": p.get("jurisdiction"), "enabled": p.get("enabled")}
            for n, p in tutor_providers.PROVIDERS.items()
        ],
        # Sortierung: fertige Sprachen zuerst, dann alphabetisch. Die Registry
        # findet die Pakete alphabetisch (ar, es, fr, ru, zh) — ohne das stünde
        # die einzige LIVE-Sprache im UI ganz unten.
        "langs": [
            {"code": c, "name": p["name"], "enabled": p.get("enabled"),
             "persona_name": p.get("persona_name", p["name"]),
             "country": p.get("country", ""),
             "reading": p.get("reading")}      # pinyin/stress/translit/none
            for c, p in sorted(tutor_langs.PROFILES.items(),
                               key=lambda kv: (not kv[1].get("enabled"), kv[0]))
        ],
    }


# ── Spielstände ────────────────────────────────────────────────────────
#
# Mehrere Lernstände nebeneinander, einer ist aktiv (tutor/staende.py). Der
# Kern kennt davon nur diese drei Griffe; wo die Dateien liegen und wie ein
# Stand aussieht, bleibt Sache des Tutors.

def _staende_root():
    """tutor/data/ — die Basis, unter der die Stände liegen."""
    from tutor import tools
    return tools._DATA_ROOT


def staende() -> dict:
    """Alle Spielstände + welcher aktiv ist. Tutor nicht da → present:False."""
    if _ts() is None:
        return {"present": False, "staende": [], "aktiv": None}
    try:
        from tutor import staende as st
        root = _staende_root()
        return {"present": True, "aktiv": st.aktiv(root),
                "staende": st.liste(root)}
    except Exception as e:
        return {"present": True, "error": str(e), "staende": [], "aktiv": None}


def stand_anlegen(name: str = None) -> dict:
    """Neuen Spielstand anlegen UND aktivieren."""
    if _ts() is None:
        return {"ok": False, "error": "Tutor nicht installiert"}
    try:
        from tutor import staende as st
        root = _staende_root()
        sid = st.anlegen(root, name)
        st.waehlen(root, sid)
        _sitzung_beenden()
        return {"ok": True, "aktiv": sid, "staende": st.liste(root)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def stand_waehlen(sid: str) -> dict:
    """Auf einen vorhandenen Spielstand umschalten."""
    if _ts() is None:
        return {"ok": False, "error": "Tutor nicht installiert"}
    try:
        from tutor import staende as st
        root = _staende_root()
        if not st.waehlen(root, sid):
            return {"ok": False, "error": "unbekannter Spielstand: %s" % sid}
        _sitzung_beenden()
        return {"ok": True, "aktiv": sid, "staende": st.liste(root)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _sitzung_beenden():
    """Laufende Persona-Sitzung beenden — sie gehört zum alten Stand.

    Ohne das würde Lucía nach dem Wechsel mit den Erinnerungen des vorigen
    Standes weiterreden: der Verlauf liegt im Speicher der Sitzung, nicht auf
    der Platte. Beim nächsten Start liest sie dann den neuen Stand.
    """
    ts = _ts()
    if ts is not None:
        _safe(ts.deactivate, None)


def stand_loeschen(sid: str) -> dict:
    """Einen Spielstand löschen. Auch den aktiven — dann wird beim nächsten
    Zugriff auf den zuletzt gespielten der übrigen umgeschaltet (oder ein
    neuer angelegt, falls keiner mehr da ist)."""
    if _ts() is None:
        return {"ok": False, "error": "Tutor nicht installiert"}
    try:
        from tutor import staende as st
        root = _staende_root()
        war_aktiv = (st.aktiv(root) == sid)
        if not st.loeschen(root, sid):
            return {"ok": False, "error": "unbekannter Spielstand: %s" % sid}
        if war_aktiv:
            _sitzung_beenden()
        return {"ok": True, "aktiv": st.aktiv(root), "staende": st.liste(root)}
    except Exception as e:
        return {"ok": False, "error": str(e)}
