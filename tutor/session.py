# tutor/session.py
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
# LanguageProfile (tutor/langs/); welcher Anbieter/welches Modell aus der
# Provider-Registry (tutor/providers.py). Backend-Dispatch nach provider.kind:
#   ollama        → core/ai.py (lokal, Default, offline)
#   anthropic     → tutor/cloud.py (Claude, Sashas Pfad)
#   openai_compat → tutor/openai_compat.py (Qwen/DeepSeek/Mistral/…)
#
# ── Privacy ───────────────────────────────────────────────────────────
# Provider mit trains_on_data werden NICHT verboten, aber bei Session-Beginn
# LAUT geflaggt (Log + privacy_notice() fürs UI). Siehe memory/tutor/tutor_system.md.
#
# ── Thread-Safety ─────────────────────────────────────────────────────
# _active/_history werden von Flask und Event-Loop gelesen/geschrieben → Lock.

import os
import time
import socket
import threading
from threading import Lock
from collections import deque
from urllib.parse import urlparse
import ai                       # basic core: chat_stream + is_available
from . import tools             # Vokabel-Tools + Sandbox-Allowlist
from . import langs             # Sprach-/Persona-Profile
from . import providers         # Provider-Registry des Tutors
from . import config            # tutor/data/tutor_config.json (Sprache/Provider/Modell)
from . import memory            # eigenes Grob-Gedächtnis pro Persona
from . import debug             # Devtools-Ereignisbus (zeitgestempelt)

_lock     = Lock()
_active   = False
_history  = deque(maxlen=100)   # Tutor-Gesprächsverlauf (separat vom Chat-History)
_privacy  = None               # gesetzte Privacy-Warnung der laufenden Session (oder None)
_session_lang = None           # Sprache/Persona der laufenden Session (für History+Memory)

# ── Ausdruck im Zimmer (vom Modell per express-Tool gesetzt) ─────────────────
# Die KI drückt sich selbst aus (statt hardcoded-Random): stance = anhaltende
# Haltung/Bewegung, gesture = einmalige Geste (gid zählt hoch, damit das Fenster
# sie GENAU EINMAL abspielt). Das Zimmer pollt /api/tutor/room_state.
_STANCES  = {"idle", "sit", "stand", "pace", "wander", "come_closer", "sleep"}
_GESTURES = {"wave", "nod", "look", "stretch", "arms_up", "cross_arms", "shrug"}
_FACES    = {"neutral", "happy", "sad", "surprised", "tired", "puzzled"}  # anhaltende Mimik
_expr     = {"stance": "idle", "gesture": None, "gid": 0, "face": "neutral"}


def set_expression(action: str):
    """Vom express-Tool aufgerufen: setzt Haltung, Mimik ODER löst eine Geste aus."""
    a = (action or "").strip().lower()
    with _lock:
        if a in _STANCES:
            _expr["stance"] = a
        elif a in _GESTURES:
            _expr["gesture"] = a
            _expr["gid"] += 1
        elif a in _FACES:
            _expr["face"] = a


def set_face(face: str):
    """Mimik direkt setzen (z.B. von der Stimmung/sozialen Batterie getrieben)."""
    f = (face or "").strip().lower()
    if f in _FACES:
        with _lock:
            _expr["face"] = f


# ── Soziale Batterie / Stimmung ──────────────────────────────────────────────
# Sashas Idee: die Persona hat eine „soziale Batterie". Sie sinkt langsam mit der
# Zeit (niemand da) und wird beim Quatschen mit Sasha wieder aufgeladen. Niedrig =
# lustloser/müder (färbt die Mimik im Fenster). ZEITBASIERT berechnet (kein
# Ticker-Thread): Level + Zeitstempel, aktueller Wert = Level − Decay·Δt.
_BAT_DECAY_PER_MIN = 3.5    # sinkt langsam (≈ 30 min von voll auf leer)
_BAT_REFILL        = 9.0    # pro echtem Sasha-Turn (Quatschen lädt auf)
_battery = {"level": 60.0, "ts": time.time()}


def _battery_now() -> float:
    lvl = _battery["level"] - _BAT_DECAY_PER_MIN * (time.time() - _battery["ts"]) / 60.0
    return max(0.0, min(100.0, lvl))


def battery_bump(amount: float):
    """Batterie ändern (positiv = aufladen beim Quatschen)."""
    with _lock:
        _battery["level"] = max(0.0, min(100.0, _battery_now() + amount))
        _battery["ts"] = time.time()


# ── Gedanken-Bild/Übersetzung (comprehensible input statt Text-Wand) ─────────
# Sashas Idee: die Persona kann „in Gedanken" ein Bild ODER die Übersetzung zu
# einem Wort zeigen, statt es mit Text zu erklären. id zählt hoch → das Fenster
# zeigt es GENAU EINMAL (und blendet es dann aus).
_thought = {"word": "", "meaning": "", "id": 0}


def set_thought(word: str, meaning: str = ""):
    with _lock:
        _thought["word"] = (word or "").strip()
        _thought["meaning"] = (meaning or "").strip()
        _thought["id"] += 1


# ── Presence-Reaktion (Sasha tauct im Raum auf) ──────────────────────────────
# Sashas Roleplay-Idee: die Persona merkt, wenn du reinkommst. WICHTIG — der
# Presence-AUTO-START bleibt bewusst pausiert (memory/tutor/tutor_system.md,
# Sequencing): dieser Ping STARTET NIE eine Session. Läuft die Session schon,
# reagiert sie nur NONVERBAL (schaut hoch, hellt auf, kleiner Batterie-Schub) —
# KEIN erzwungener Cloud-Turn (genau der schlechte Auto-Trigger, der 05-14 zur
# Deaktivierung führte). Gedrosselt, damit PIR-Zucken sie nicht nervös macht.
_presence = {"ts": 0.0}
_PRESENCE_COOLDOWN = 90.0    # s zwischen zwei Reaktionen


# ── Musik (die Persona legt was auf) ─────────────────────────────────────────
# Feature 7: die Persona kann im Zimmer Musik nach Stimmung auflegen. Der State
# ist nur ein WUNSCH (action/mood, id-getriggert) — das ABSPIELEN macht das
# Fenster (pygame.mixer.music, Bibliothek data/persona_music/<mood>/). Kein Audio
# mitgeliefert (Lizenz) → Content-Lücke; Mechanik läuft, sobald Dateien da sind.
_MUSIC_MOODS = {"chill", "happy", "focus", "sad", "energetic"}
_music = {"action": "", "mood": "", "id": 0}   # action: "play" | "stop"


def play_music(mood: str = "chill") -> str:
    m = (mood or "chill").strip().lower()
    if m not in _MUSIC_MOODS:
        m = "chill"
    with _lock:
        _music["action"] = "play"; _music["mood"] = m; _music["id"] += 1
    return m


def stop_music():
    with _lock:
        _music["action"] = "stop"; _music["mood"] = ""; _music["id"] += 1


# ── Fernseher (die Persona macht den TV an) ──────────────────────────────────
# Feature 8: im Zimmer steht ein TV; die Persona kann etwas „anmachen" (nach
# Stimmung/Level). State = an/aus + Titel (id-getriggert). Echtes Video-Playback
# ist DEFERRED (keine Files, Lizenz, pygame-Video schwach) — das Fenster zeigt den
# TV als AN mit dem Titel auf dem Schirm; sie referenziert es im Gespräch.
_tv = {"on": False, "title": "", "id": 0}


def tv_on(title: str = ""):
    with _lock:
        _tv["on"] = True; _tv["title"] = (title or "").strip(); _tv["id"] += 1


def tv_off():
    with _lock:
        _tv["on"] = False; _tv["title"] = ""; _tv["id"] += 1


def presence_ping() -> bool:
    """Presence-Sensor: Sasha ist im Raum. Reagiert nur bei AKTIVER Session,
    nonverbal + gedrosselt. True = hat sichtbar reagiert."""
    with _lock:
        if not _active:
            return False
        now = time.time()
        if now - _presence["ts"] < _PRESENCE_COOLDOWN:
            return False
        _presence["ts"] = now
        _expr["gesture"] = "look"; _expr["gid"] += 1   # schaut zu ihr rüber
        _expr["face"] = "happy"                          # hellt auf
    battery_bump(6.0)    # jemand ist da → hebt die Laune (nimmt _lock selbst)
    return True


def room_state() -> dict:
    """Aktueller Ausdrucks-Zustand + Stimmung fürs Zimmer-Fenster (leichtgewichtig).
    Enthält auch den ASSESSMENT-GATE-Stand: mode ('assessment' = Drill, Zimmer zu /
    'room' = Persona frei), Kern-Deckung + gerampter TTS-Speed. Das Fenster
    rendert danach den Drill-Screen oder das Zimmer."""
    lang = active_lang()
    try:
        got, total = tools.core_coverage(lang)
        # Das Gate hängt am LERNSTAND, NICHT an einer aktiven KI-Session: der
        # deterministische Drill läuft ohne Session (_active=False). Früher gab
        # bool(_active) hier fälschlich mode='room' → das Zimmer sprang bei 1 %
        # auf „freigeschaltet". Jetzt rein aus assessment_active.
        assess = tools.assessment_active(lang)
        speed = tools.tts_speed_for(lang)
    except Exception:
        got, total, assess, speed = 0, 0, False, 1.0
    with _lock:
        bat = _battery_now()
        mood = "happy" if bat >= 68 else ("low" if bat < 32 else "ok")
        return {"stance": _expr["stance"], "gesture": _expr["gesture"],
                "gesture_id": _expr["gid"], "face": _expr["face"],
                "battery": int(bat), "mood": mood, "active": _active,
                "thought_word": _thought["word"], "thought_meaning": _thought["meaning"],
                "thought_id": _thought["id"],
                "music_action": _music["action"], "music_mood": _music["mood"],
                "music_id": _music["id"],
                "tv_on": _tv["on"], "tv_title": _tv["title"], "tv_id": _tv["id"],
                # Assessment-Gate:
                "mode": "assessment" if assess else "room",
                "core_got": got, "core_total": total,
                "core_ratio": round(got / total, 3) if total else 0.0,
                "tts_speed": speed}

def _history_window() -> int:
    """Wieviele der letzten Turns ans Modell gesendet werden (Kosten-Hebel: die
    API ist zustandslos, sendet sonst die ganze History pro Turn neu). Storage
    bleibt bei maxlen=100; gesendet wird nur das Fenster."""
    try:
        return int(config.setting("history_window", 30))
    except (TypeError, ValueError):
        return 30


def _resolve():
    """Löst Sprache → Profil → Provider → Modell auf. Werte kommen aus der lokalen
    Config (data/tutor_config.json), per Env übersteuerbar (siehe tutor_config:
    Precedence Env > Config > Profil-Default). Wird der Provider gewechselt, ohne
    ein Modell zu setzen, greift das default_model des Providers."""
    lang          = config.setting("lang", "zh")
    prof          = langs.get(lang)
    provider_name = config.setting("provider", prof["provider"])
    provider      = providers.get(provider_name)
    model         = config.setting("model", None)
    if not model:
        model = prof["model"] if provider_name == prof["provider"] else provider.get("default_model")
    return prof, provider_name, provider, model


def active_lang() -> str:
    """Die Sprache, um die es JETZT geht — die EINE Quelle für alle.

    Läuft eine Session, ist es DEREN Sprache (beim Start eingefroren), sonst die
    aus der Config. Wichtig: tools.py fragt das hier und NICHT config direkt.
    Sonst würde ein `/lang fr` mitten in einer zh-Session die nächsten Tool-Calls
    in die fr-Dateien schreiben und beide Lernstände verderben."""
    return _session_lang or config.setting("lang", "zh")


def backend_kind() -> str:
    """'ollama' (lokal) | 'anthropic' | 'openai_compat' (beide = Cloud) — welche
    Art Backend der aktuell aufgelöste Provider braucht.

    Teil des KONTRAKTS zum Kern: core/tutor_port.py fragt das, um die ZENTRALE-
    Drossel (cloud_enabled/local_enabled) anzuwenden. Der Tutor selbst kennt die
    Drossel nicht — siehe available()."""
    _prof, _pname, provider, _model = _resolve()
    return provider.get("kind") or "ollama"


_REACH_TTL   = 5.0
_reach_cache = {}   # host → (t, ok)


def _reachable(host: str, port: int = 443, timeout: float = 2.0) -> bool:
    """Leichter TCP-Erreichbarkeits-Check, kurz gecacht (status() wird gepollt)."""
    if not host:
        return False
    hit = _reach_cache.get(host)
    now = time.time()
    if hit and (now - hit[0]) < _REACH_TTL:
        return hit[1]
    ok = False
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        ok = True
    except Exception:
        ok = False
    _reach_cache[host] = (now, ok)
    return ok


def available() -> bool:
    """Ist der Tutor mit dem aktuell aufgelösten Provider nutzbar?

    REIN KAPAZITÄT: ist das Backend meines Providers erreichbar — lokaler
    Provider → Ollama da; Cloud-Provider → Key gesetzt + Host erreichbar.

    Kennt die ZENTRALE-Drossel (cloud_enabled/local_enabled) BEWUSST NICHT.
    Die ist Core-Policy und sitzt in core/tutor_port.py — der Port fragt erst
    die Drossel, dann das hier. Vorher hing der Tutor über ai_backends direkt an
    der Core-Config; damit war er nicht rausziehbar und die Drossel wohnte in
    einer Tutor-Datei (Umbau 2026-07-16). Wer den Tutor GATEN will, fragt den
    Port, nicht das hier."""
    _prof, _pname, provider, _model = _resolve()
    if provider.get("kind") == "ollama":
        return ai.is_available()
    key = provider.get("key_env")
    if key and not os.environ.get(key):
        return False
    base = provider.get("base_url") or "https://api.anthropic.com"
    return _reachable(urlparse(base).hostname)


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
    lang = config.setting("lang", "zh")

    notice = None
    if providers.trains_on_data(pname):
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

    # KEIN rohes History-Replay mehr über Sessions (führte zu Filler-Loops und ist
    # auch unnötig): Kontinuität kommt aus den GROB-Notizen (memory.context,
    # unten in den System-Prompt gehängt). _history ist reiner In-Session-Puffer.
    with _lock:
        _active       = True
        _session_lang = lang
        _history      = deque(maxlen=100)
        _privacy      = notice
        _expr["stance"] = "idle"; _expr["gesture"] = None; _expr["face"] = "neutral"
        _battery["level"] = 55.0; _battery["ts"] = time.time()   # frische Batterie


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


# Nudge = neutrale LAGE-MELDUNG (kein Verhaltensbefehl mehr). Früher stand hier
# "frag ob sie da ist" → sie fragte ewig im selben Wortlaut. Jetzt beschreiben wir
# nur die SITUATION (still + Sensorik), und ihre Persona (mag kein Ignoriert-
# werden) reagiert selbst — mal genervt, mal macht sie ihr Ding, mal stupst sie.
# Wird NUR gesendet, nie in der History gespeichert (Sasha hat's nicht gesagt).
# focus: Fenster fokussiert? (jemand schaut zu)  True/False/None(unbekannt)
# sound: Mikro-Ambient — Rascheln? (Phase 2, vorerst None/unbenutzt)
# Lage-Meldungen sind HINTERGRUND (keine echte Rede von Sasha). WICHTIG: bei
# Fast-Null-Wortschatz greift sie sonst ein konkretes Wort daraus auf und echot es
# (Bug: 旁白 „…窗户…" → sie sagt „窗户！"). Darum (a) klar als Hintergrund + „nicht
# nachplappern" markiert, (b) keine aufgreifbaren Nomen.
#
# Die Texte kommen aus dem SPRACH-PROFIL (prof['situation']) — sie MÜSSEN in der
# Zielsprache sein. Standen früher hart chinesisch hier; eine es-Session bekam so
# eine chinesische Meta-Lage und Lucía kippte in einen Echo-Loop ('¿cansada?').
# Fallback (base.DEFAULTS['situation']) nur für ungetunte Skizzen.


def _situation_of(prof) -> dict:
    sit = prof.get("situation")
    if sit:
        return sit
    from .langs import base
    return base.DEFAULTS["situation"]


def _nudge_situation(prof, focus=None, sound=None) -> str:
    sit = _situation_of(prof)
    bits = [sit["nudge_idle"]]                       # eine Weile keine Regung
    if focus is True and sit.get("nudge_focus_yes"):
        bits.append(sit["nudge_focus_yes"])          # jemand schaut, sagt aber nichts
    elif focus is False and sit.get("nudge_focus_no"):
        bits.append(sit["nudge_focus_no"])           # niemand schaut zu
    if sound is True and sit.get("nudge_sound"):
        bits.append(sit["nudge_sound"])              # ein Geräusch, ungewiss
    return sit["prefix"] + sit.get("join", ", ").join(bits) + sit["suffix"]


def _opening_situation(prof, focus=None) -> str:
    """Öffnen = Wahrnehmungs-Ereignis (wie Fokus/Stille): Sasha kommt gerade rein.
    Neutrale HINTERGRUND-Meldung → sie begrüßt/reagiert aus ihrer Person (variabel),
    statt stale History degeneriert fortzusetzen ('我在'-Bug). Zielsprache aus dem
    Profil (siehe oben)."""
    sit = _situation_of(prof)
    s = sit["open"]                                  # Sasha ist gerade rübergekommen
    if focus is True and sit.get("open_focus"):
        s += sit["open_focus"]                       # und schaut dich an
    return sit["prefix"] + s + sit["suffix"]


def respond_stream(user_text: str = None, nudge: bool = False,
                   focus=None, sound=None):
    """
    Generator: schickt die History (+ optionale neue User-Nachricht) an das
    aufgelöste Backend mit dem Sprach-System-Prompt und den Tutor-Tools.
    Yieldet Token für Token fürs Browser-Streaming.

    user_text=None → KI startet das Gespräch (Session-Beginn).
    nudge=True     → Stille: statt eines Befehls kriegt sie eine neutrale Lage-
                     Meldung (mit Fokus-/Ambient-Sensorik), reagiert selbst aus
                     ihrem Charakter. Nur gesendet, nicht in der History.
    """
    if user_text is not None:
        push_message("user", user_text)
        battery_bump(_BAT_REFILL)     # echtes Quatschen lädt die soziale Batterie

    prof, pname, provider, model = _resolve()
    lang = active_lang()

    # spoken DETERMINISTISCH aus der User-Eingabe: jedes getrackte Wort, das Sasha
    # gerade selbst benutzt hat, → spoken +1 (die KI zählt nicht). Vor dem Kontext-
    # Bau, damit der Status im Prompt schon aktuell ist.
    if user_text:
        try:
            tools.note_spoken(user_text, lang)
        except Exception:
            pass

    # Kosten-Hebel: nur die letzten N Turns senden (zustandslose API).
    if user_text is None and not nudge:
        # Öffnen/Session-Start: NUR die Lage-Meldung „Sasha kommt rein", KEIN roher
        # Verlauf. Sonst kapert ein (mit „你在吗？"-Fillern) verseuchter Verlauf den
        # Gruß und sie fällt in eine Frage-/Echo-Schleife. Kontinuität kommt aus
        # persona_memory (Zusammenfassung im System-Prompt), nicht aus History-Replay.
        history = [{"role": "user", "content": _opening_situation(prof, focus)}]
    else:
        history = get_history()[-_history_window():]
        if nudge:
            history = history + [{"role": "user", "content": _nudge_situation(prof, focus, sound)}]

    # Hartes Assessment-Gate: solange der Kern-Wortschatz NICHT gemeistert ist,
    # spricht die Persona im DRILL-/Prüf-Prompt (Wort für Wort, kein Zimmer-Leben)
    # — das Persona-Zimmer bleibt zu, bis ≥GRADUATE_AT gefestigt sind. Trägt die
    # Sprache keinen assessment_prompt/kein Curriculum, gibt es kein Gate.
    _gate = bool(prof.get("assessment_prompt")) and tools.assessment_active(lang)
    system  = prof["assessment_prompt"] if _gate else prof["system_prompt"]

    # Vokabel-Kontext ans Prompt-Ende hängen: welche Wörter Sasha lernt, damit
    # die Persona sich ans begrenzte Set hält. Ersetzt das frühere "ruf zu Beginn
    # get_confirmed_vocab() auf". WICHTIG: der Hinweis kommt aus dem Profil in der
    # ZIELSPRACHE (prof['vocab_hint']) — ein deutscher Block hier kippt qwen zurück
    # ins Deutsche/Monolog (gegen echtes qwen verifiziert). Kein Hinweis im Profil
    # (Skizzen) → keine Injektion. Tools increment/introduce bleiben verfügbar.
    hint = prof.get("vocab_hint")
    if hint:
        try:
            # Die KI kriegt die Liste {wort: STATUS} — nie die Zahlen (spoken/listened).
            # Status-Label kommt in der ZIELSPRACHE (prof['status_labels']); neutral
            # formuliert (KEINE Drill-Verben — „übe/afiánza" ließ qwen abfragen).
            # HINWEIS: bei sehr vielen Wörtern wird das lang → Embedding-Auswahl ist der
            # nächste, noch offene Schritt (dann nur die relevanten Wörter senden).
            sl = tools.vocab_status_list(lang)          # [(wort, status)]
            structs = tools.structure_list(lang)
            lab = prof.get("vocab_labels") or {}
            slab = prof.get("status_labels") or {}
            join = lab.get("join", ", ")
            sep = lab.get("sep", "; ")
            parts = []
            if sl:
                parts.append(join.join(f"{w} ({slab.get(s, s)})" for w, s in sl))
            if structs:
                parts.append(lab.get("structs", "Satzmuster: ") + join.join(structs))
            if parts:
                system = system + "\n\n" + hint.format(words=sep.join(parts))
            # Erwartung skalieren (fast immer leer nach dem Umbau — Register trägt
            # der Prompt). Paket-DATEN (langs/<lang>/expect.json), Zielsprache.
            exp = langs.expect(lang, len(sl) + len(structs))
            if exp:
                system = system + "\n" + exp
        except Exception:
            pass

    # Kern-Syllabus ans Prompt-Ende: WELCHE Kern-Wörter noch dran sind + der
    # Deckungs-Stand. So arbeitet die Persona das feste Grund-Vokabular aktiv ab
    # (statt sich rein aufs Emergente zu verlassen). Template aus dem Paket in
    # der ZIELSPRACHE (prof['core_hint']); fehlt es → keine Injektion. Nach der
    # Graduierung (Kern gemeistert) fällt der Hinweis weg — kein Nachkarten, ab
    # da trägt die Konversation sich selbst (Register kommt aus der expect-Leiter).
    core_hint = prof.get("core_hint")
    if core_hint and not tools.core_graduated(lang):
        try:
            got, total = tools.core_coverage(lang)
            if total:
                join = (prof.get("vocab_labels") or {}).get("join", ", ")
                todo = join.join(e["word"] for e in tools.core_todo(lang, 6))
                system = system + "\n\n" + core_hint.format(
                    got=got, total=total, words=todo or "—")
        except Exception:
            pass

    # Persona-Gedächtnis: was die Persona aus früheren Gesprächen über Sasha
    # weiß, an den System-Prompt hängen. Nur ihr EIGENER Store (nie Sashas
    # Core-Graph) → keine private Info an die Cloud. Query = die neue User-
    # Nachricht (bei Begrüßung None → Sasha/Heute-Anker).
    mem_ctx = memory.context(user_text, lang)
    if mem_ctx:
        system = system + "\n\n" + mem_ctx

    # Devtools: was die KI KRIEGT — voller System-Prompt (inkl. Vokabel-Kontext +
    # Lage-Meldung + Gedächtnis), die Messages, Provider/Modell, verfügbare Tools.
    debug.emit('ai.req',
               phase=('start' if (user_text is None and not nudge) else 'nudge' if nudge else 'respond'),
               lang=lang, provider=pname, model=model,
               system=system, messages=history,
               tools=[t['function']['name'] for t in tools.tools_for(lang)])

    # Backend-Dispatch nach provider.kind. Alle haben dieselbe chat_stream()-
    # Signatur (yieldet Plain-Text-Tokens); der Tutor bleibt sauberes Addon.
    kind = provider.get("kind")
    if kind == "anthropic":
        from . import cloud as tutor_cloud
        stream = tutor_cloud.chat_stream(
            messages=history, model=model, system=system,
            tools=tools.tools_for(lang), tool_executor=tools.execute_tool)
    elif kind == "openai_compat":
        from . import openai_compat as tutor_openai_compat
        stream = tutor_openai_compat.chat_stream(
            messages=history, model=model, system=system,
            tools=tools.tools_for(lang), tool_executor=tools.execute_tool,
            _provider=provider)
    else:  # 'ollama' → lokaler Default über core/ai.py
        stream = ai.chat_stream(
            messages=history, system=system,
            tools=tools.tools_for(lang), tool_executor=tools.execute_tool)

    full_response = []
    for token in stream:
        full_response.append(token)
        yield token

    full = "".join(full_response)
    # Devtools: was die KI AUSGIBT — die ROH-Antwort (inkl. dem, was das Zimmer sonst
    # versteckt: (Regie-Klammern), geleakte Tool-Zeilen; die Bereinigung passiert
    # erst im Frontend via _clean_speech).
    debug.emit('ai.out', phase=('nudge' if nudge else 'respond'), lang=lang, raw=full)

    # Nudge-Antworten sind AMBIENTES Verhalten (sie reagiert auf Stille), kein
    # Gespräch — NICHT ins Gedächtnis (sonst füllt sich die persistente History mit
    # „我在"-Fillern und beim nächsten Öffnen plappert sie die nach). Nur echte
    # Turns + der Eröffnungsgruß landen im Verlauf.
    if nudge:
        return
    push_message("assistant", full)

    # Nach dem Turn: KEIN roher Verlauf mehr auf Disk — nur die GROB-Notizen im
    # Hintergrund verdichten (memory.remember, läuft lokal/Cloud, darf das
    # Streaming nicht blockieren).
    if user_text:   # Begrüßungs-Turn (user_text=None) nicht verdichten
        # provider/model mitgeben: fällt die Verdichtung mangels Ollama auf die
        # Cloud zurück, nutzt sie denselben Anbieter, der eh gerade redet.
        threading.Thread(
            target=memory.remember,
            args=(user_text, full, lang, pname, model), daemon=True).start()

        # Kern-Syllabus: einmaliger Graduierungs-Meilenstein (ALLE Kern-Wörter
        # durch, GRADUATE_AT=1.0). check_graduation() feuert genau EINMAL — der Zustand
        # liegt in data/<lang>/progress.json, NICHT in den Persona-Notizen.
        try:
            if tools.check_graduation(lang):
                got, total = tools.core_coverage(lang)
                import state
                state.push_log(
                    f"🎓 Kern-Wortschatz gemeistert ({prof.get('name', lang)}): "
                    f"{got}/{total} Kern-Wörter — ab jetzt freie Konversation.")
        except Exception:
            pass
