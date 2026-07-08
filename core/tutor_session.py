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
import threading
from threading import Lock
from collections import deque
import ai
import tutor
import tutor_langs
import tutor_providers
import tutor_config   # lädt data/tutor_config.json, injiziert Keys, liefert Settings
import persona_memory # eigenes Gedächtnis + persistente History pro Persona

_lock     = Lock()
_active   = False
_history  = deque(maxlen=100)   # Tutor-Gesprächsverlauf (separat vom Chat-History)
_privacy  = None               # gesetzte Privacy-Warnung der laufenden Session (oder None)
_session_lang = None           # Sprache/Persona der laufenden Session (für History+Memory)

# ── Ausdruck im Zimmer (vom Modell per express-Tool gesetzt) ─────────────────
# Die KI drückt sich selbst aus (statt hardcoded-Random): stance = anhaltende
# Haltung/Bewegung, gesture = einmalige Geste (gid zählt hoch, damit das Fenster
# sie GENAU EINMAL abspielt). Das Zimmer pollt /api/tutor/room_state.
_STANCES  = {"idle", "sit", "stand", "pace", "wander", "come_closer"}
_GESTURES = {"wave", "nod", "look", "stretch"}
_expr     = {"stance": "idle", "gesture": None, "gid": 0}


def set_expression(action: str):
    """Vom express-Tool aufgerufen: setzt Haltung ODER löst eine Geste aus."""
    a = (action or "").strip().lower()
    with _lock:
        if a in _STANCES:
            _expr["stance"] = a
        elif a in _GESTURES:
            _expr["gesture"] = a
            _expr["gid"] += 1


def room_state() -> dict:
    """Aktueller Ausdrucks-Zustand fürs Zimmer-Fenster (pollt das leichtgewichtig)."""
    with _lock:
        return {"stance": _expr["stance"], "gesture": _expr["gesture"],
                "gesture_id": _expr["gid"], "active": _active}

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
    Setzt _active=True, LÄDT die persistente History der Persona (sie vergisst
    dich zwischen Sessions nicht mehr), und FLAGGT laut, falls der gewählte
    Provider auf Nutzdaten trainiert.
    """
    global _active, _history, _privacy, _session_lang
    prof, pname, provider, model = _resolve()
    lang = tutor_config.setting("lang", "zh")

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

    # Persistente History der Persona laden statt zu flushen — der Mitbewohner
    # knüpft beim Öffnen an eure letzten Gespräche an.
    prior = persona_memory.load_history(lang)
    with _lock:
        _active       = True
        _session_lang = lang
        _history      = deque(prior, maxlen=100)
        _privacy      = notice
        _expr["stance"] = "idle"; _expr["gesture"] = None   # frisch, keine Alt-Geste


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


# Nudge-Text (Zielsprache-neutral gehalten, mit chinesischer Anweisung): wird
# NUR gesendet, nie in der History gespeichert — Sasha hat das ja nicht gesagt.
_NUDGE_PROMPT = ("（旁白：Sasha 有一会儿没出声了。你可以看看她、招手，或者轻声问一句"
                 "她在不在——很简短，一句就够。用 express 工具做动作。）")


def respond_stream(user_text: str = None, nudge: bool = False):
    """
    Generator: schickt die History (+ optionale neue User-Nachricht) an das
    aufgelöste Backend mit dem Sprach-System-Prompt und den Tutor-Tools.
    Yieldet Token für Token fürs Browser-Streaming.

    user_text=None → KI startet das Gespräch (Session-Beginn).
    nudge=True     → Stille-Anstoß: die KI reagiert von selbst (schauen/winken/
                     kurz nachfragen). Der Anstoß-Text wird NUR gesendet, nicht
                     in der History gespeichert.
    """
    if user_text is not None:
        push_message("user", user_text)

    prof, pname, provider, model = _resolve()
    lang = _session_lang or tutor_config.setting("lang", "zh")

    # Kosten-Hebel: nur die letzten N Turns senden (zustandslose API).
    history = get_history()[-_history_window():]
    if nudge:
        history = history + [{"role": "user", "content": _NUDGE_PROMPT}]
    system  = prof["system_prompt"]

    # Vokabel-Kontext ans Prompt-Ende hängen: welche Wörter Sasha lernt, damit
    # die Persona sich ans begrenzte Set hält. Ersetzt das frühere "ruf zu Beginn
    # get_confirmed_vocab() auf". WICHTIG: der Hinweis kommt aus dem Profil in der
    # ZIELSPRACHE (prof['vocab_hint']) — ein deutscher Block hier kippt qwen zurück
    # ins Deutsche/Monolog (gegen echtes qwen verifiziert). Kein Hinweis im Profil
    # (Skizzen) → keine Injektion. Tools increment/introduce bleiben verfügbar.
    hint = prof.get("vocab_hint")
    if hint:
        try:
            words = "、".join(tutor.term_list())
            if words:
                system = system + "\n\n" + hint.format(words=words)
        except Exception:
            pass

    # Persona-Gedächtnis: was die Persona aus früheren Gesprächen über Sasha
    # weiß, an den System-Prompt hängen. Nur ihr EIGENER Store (nie Sashas
    # Core-Graph) → keine private Info an die Cloud. Query = die neue User-
    # Nachricht (bei Begrüßung None → Sasha/Heute-Anker).
    mem_ctx = persona_memory.context(user_text, lang)
    if mem_ctx:
        system = system + "\n\n" + mem_ctx

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

    full = "".join(full_response)
    push_message("assistant", full)

    # Nach dem Turn: History persistieren (Persona vergisst dich nicht) und den
    # Turn in IHR Gedächtnis verdichten. Beides im Hintergrund — der Extraktor
    # läuft lokal (Ollama), darf das Streaming nicht blockieren.
    persona_memory.save_history(get_history(), lang)
    if user_text:   # Begrüßungs-Turn (user_text=None) nicht verdichten
        # provider/model mitgeben: fällt die Verdichtung mangels Ollama auf die
        # Cloud zurück, nutzt sie denselben Anbieter, der eh gerade redet.
        threading.Thread(
            target=persona_memory.remember,
            args=(user_text, full, lang, pname, model), daemon=True).start()
