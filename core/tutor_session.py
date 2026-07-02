# core/tutor_session.py
#
# Verwaltet den State einer aktiven Sprachtutor-Session.
#
# ── Was ist eine Session? ─────────────────────────────────────────────
# Eine Session beginnt manuell (Dashboard-Hotkey). Die KI begrüßt zuerst in
# der Zielsprache. Der User antwortet (Mikrofon + Space). Das geht hin und
# her bis die Session manuell beendet wird.
#
# ── Framework, nicht Chinesisch-Tutor ─────────────────────────────────
# Welche Sprache (System-Prompt, Vokabeln, Lesehilfe) kommt aus dem
# LanguageProfile (tutor_langs.py); welcher Anbieter/welches Modell aus der
# Provider-Registry (tutor_providers.py). Backend-Dispatch nach provider.kind:
#   ollama        → core/ai.py (lokal, Default, offline)
#   anthropic     → core/tutor_cloud.py (Claude, Sashas Pfad)
#   openai_compat → core/tutor_openai_compat.py (Qwen/DeepSeek/Mistral/…)
#
# ── Privacy ───────────────────────────────────────────────────────────
# Provider mit trains_on_data werden NICHT verboten, aber bei Session-Beginn
# LAUT geflaggt (Log + privacy_notice() fürs UI). Siehe memory/tutor_system.md.
#
# ── Thread-Safety ─────────────────────────────────────────────────────
# _active/_history werden von Flask und Event-Loop gelesen/geschrieben → Lock.

import os
from threading import Lock
from collections import deque
import ai
import tutor
import tutor_langs
import tutor_providers
import tutor_config   # lädt data/tutor_config.json, injiziert Keys, liefert Settings

_lock     = Lock()
_active   = False
_history  = deque(maxlen=100)   # Tutor-Gesprächsverlauf (separat vom Chat-History)
_privacy  = None               # gesetzte Privacy-Warnung der laufenden Session (oder None)

def _history_window() -> int:
    """Wieviele der letzten Turns ans Modell gesendet werden (Kosten-Hebel: die
    API ist zustandslos, sendet sonst die ganze History pro Turn neu). Storage
    bleibt bei maxlen=100; gesendet wird nur das Fenster."""
    try:
        return int(tutor_config.setting("history_window", 30))
    except (TypeError, ValueError):
        return 30


def _resolve():
    """Löst Sprache → Profil → Provider → Modell auf. Werte kommen aus der lokalen
    Config (data/tutor_config.json), per Env übersteuerbar (siehe tutor_config:
    Precedence Env > Config > Profil-Default). Wird der Provider gewechselt, ohne
    ein Modell zu setzen, greift das default_model des Providers."""
    lang          = tutor_config.setting("lang", "zh")
    prof          = tutor_langs.get(lang)
    provider_name = tutor_config.setting("provider", prof["provider"])
    provider      = tutor_providers.get(provider_name)
    model         = tutor_config.setting("model", None)
    if not model:
        model = prof["model"] if provider_name == prof["provider"] else provider.get("default_model")
    return prof, provider_name, provider, model


def available() -> bool:
    """Ist der Tutor mit dem aktuell aufgelösten Provider nutzbar? Kapazitäts-
    basiert (Backend des Providers erreichbar) statt kassetten-hart (ki_aus):
    lokaler Provider → Ollama da; Cloud-Provider → cloud da (Internet + Key +
    Kill-Switch an). So läuft der Tutor auch auf laptop/tui, sobald ein Backend
    erreichbar ist."""
    import ai_backends
    _prof, _pname, provider, _model = _resolve()
    st = ai_backends.status()
    if provider.get("kind") == "ollama":
        return bool(st.get("local"))
    return bool(st.get("cloud"))   # anthropic / openai_compat → cloud


def privacy_notice():
    """Gibt die Privacy-Warnung der laufenden Session zurück (oder None).
    Für /api/tutor/status → UI-Banner."""
    with _lock:
        return _privacy


def is_active() -> bool:
    """Gibt zurück ob gerade eine Tutor-Session läuft."""
    with _lock:
        return _active


def activate():
    """
    Aktiviert den Session-State (manueller Start via /api/tutor/start).
    Setzt _active=True, leert die History, und FLAGGT laut, falls der gewählte
    Provider auf Nutzdaten trainiert.
    """
    global _active, _history, _privacy
    prof, pname, provider, model = _resolve()

    notice = None
    if tutor_providers.trains_on_data(pname):
        notice = (f"⚠ DATENSCHUTZ: Provider '{pname}' ({provider.get('jurisdiction')}) "
                  f"trainiert/nutzt offiziell deine Eingaben. Modell {model}, "
                  f"Sprache {prof['name']}.")
        try:
            import state
            state.push_log("⚠⚠⚠ TUTOR PRIVACY-WARNUNG ⚠⚠⚠")
            state.push_log(notice)
        except Exception:
            pass
        print(notice)

    with _lock:
        _active  = True
        _history = deque(maxlen=100)
        _privacy = notice


def deactivate():
    """Beendet die Session. History bleibt für eventuelle Nachbetrachtung."""
    global _active, _privacy
    with _lock:
        _active  = False
        _privacy = None


def get_history() -> list:
    """Gibt die aktuelle Gesprächshistory als Liste zurück (thread-safe)."""
    with _lock:
        return list(_history)


def push_message(role: str, content: str):
    """Fügt eine Nachricht zur Session-History hinzu."""
    with _lock:
        _history.append({"role": role, "content": content})


def respond_stream(user_text: str = None):
    """
    Generator: schickt die History (+ optionale neue User-Nachricht) an das
    aufgelöste Backend mit dem Sprach-System-Prompt und den Tutor-Tools.
    Yieldet Token für Token fürs Browser-Streaming.

    user_text=None → KI startet das Gespräch (Session-Beginn).
    """
    if user_text is not None:
        push_message("user", user_text)

    prof, pname, provider, model = _resolve()

    # Kosten-Hebel: nur die letzten N Turns senden (zustandslose API).
    history = get_history()[-_history_window():]
    system  = prof["system_prompt"]

    # Backend-Dispatch nach provider.kind. Alle haben dieselbe chat_stream()-
    # Signatur (yieldet Plain-Text-Tokens); der Tutor bleibt sauberes Addon.
    kind = provider.get("kind")
    if kind == "anthropic":
        import tutor_cloud
        stream = tutor_cloud.chat_stream(
            messages=history, model=model, system=system,
            tools=tutor.TUTOR_TOOLS, tool_executor=tutor.execute_tool)
    elif kind == "openai_compat":
        import tutor_openai_compat
        stream = tutor_openai_compat.chat_stream(
            messages=history, model=model, system=system,
            tools=tutor.TUTOR_TOOLS, tool_executor=tutor.execute_tool,
            _provider=provider)
    else:  # 'ollama' → lokaler Default über core/ai.py
        stream = ai.chat_stream(
            messages=history, system=system,
            tools=tutor.TUTOR_TOOLS, tool_executor=tutor.execute_tool)

    full_response = []
    for token in stream:
        full_response.append(token)
        yield token

    push_message("assistant", "".join(full_response))
