# tutor/tools.py
#
# Die Tools, die die Persona während einer Session aufrufen darf.
#
# ── SPRACH-NEUTRAL (Umbau 2026-07-16) ───────────────────────────────────
# Diese Datei enthält KEINE Sprache mehr — kein Mandarin, keine Pinyin, keine
# China-Themen. Sie ist die Mechanik; was eine Sprache ausmacht, liegt in ihrem
# Paket (tutor/langs/<code>/): Tool-Beschriftung, Regie-Sätze, Seeds.
#
# Vorher war das Gegenteil der Fall und es war kaputt: _VOCAB_FILE & Co. waren
# MODUL-Konstanten, beim Import einmal auf vocab_mandarin.json gesetzt. Ein
# Sprachwechsel zur Laufzeit konnte daran gar nicht vorbei — `/lang fr` ließ
# Jacqueline Französisch reden, aber französische Wörter mit einem 'pinyin'-Feld
# in Sashas Mandarin-Liste schreiben, mit chinesischen Tool-Beschreibungen und
# China-News. Deshalb wird jetzt ALLES pro Aufruf über die aktive Sprache
# aufgelöst.
#
# ── Wo was liegt ────────────────────────────────────────────────────────
#   Lernstand (pro Sprache, Laufzeit, gitignored):
#       tutor/data/<lang>/vocab.json       {word, reading, correct_use, confirmed}
#       tutor/data/<lang>/structures.json  Satzmuster
#       tutor/data/<lang>/news.json        nur der Rotations-Cursor
#       tutor/data/<lang>/tv.json          nur der Rotations-Cursor
#   Sprache (getrackt, kommt mit dem Repo):
#       tutor/langs/<lang>/  Prompt, tool_texts.json, phrases, seeds/
#
# ── 'reading' statt 'pinyin' ────────────────────────────────────────────
# Das Vokabel-Feld heisst generisch `reading`; WAS es bedeutet, sagt das Profil:
# zh=Pinyin, ru=Betonung, ar=Translit, fr/es=leer. Vorher war das Datenmodell
# mandarin-förmig und jede andere Sprache hätte lügen müssen.
#
# ── Konzept: confirmed vs. testing ──────────────────────────────────────
#   confirmed = False  → Wort wird gerade gelernt (20%-Pool)
#   confirmed = True   → Wort ist gefestigt (80%-Pool)
#   correct_use >= CONFIRM_THRESHOLD → confirmed springt automatisch auf True

import json
import os
from threading import Lock

from . import langs

_lock = Lock()   # Flask-Thread + Event-Loop können gleichzeitig lesen/schreiben

CONFIRM_THRESHOLD = 5    # so oft korrekt genutzt → Wort gilt als gefestigt
STRUCT_THRESHOLD  = 3    # so oft genutzt → Satzmuster gilt als gefestigt

_DATA_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


# ── Aktive Sprache + Pfade ──────────────────────────────────────────────

def _lang(lang: str = None) -> str:
    """Die Sprache, um die es JETZT geht.

    Ohne Angabe: die der laufenden Session (session.active_lang()) — NICHT
    direkt die Config. Sonst würde ein `/lang fr` mitten in einer zh-Session
    die nächsten Tool-Calls in die fr-Dateien schreiben und beide Stände
    verderben. Die Session friert ihre Sprache beim Start ein."""
    if lang:
        return lang
    try:
        from . import session
        return session.active_lang()
    except Exception:
        return "zh"


def _dir(lang: str = None) -> str:
    d = os.path.join(_DATA_ROOT, _lang(lang))
    os.makedirs(d, exist_ok=True)
    return d


def _file(name: str, lang: str = None) -> str:
    return os.path.join(_dir(lang), name)


def _prof(lang: str = None) -> dict:
    return langs.get(_lang(lang))


# ── Modell-sichtbare Texte ──────────────────────────────────────────────
# Die Persona LIEST, was ein Tool zurückgibt. Also gehört auch das in ihre
# Sprache (dieselbe Logik wie beim Prompt: fremdsprachiger Text kippt das
# Modell). Ein Sprach-Paket überschreibt über PROFILE['phrases']; hier stehen
# die deutschen Defaults für noch nicht getunte Skizzen.

_DEFAULT_PHRASES = {
    "vocab_none":            "Noch keine bestätigten Vokabeln vorhanden.",
    "vocab_confirmed_header": "Bestätigte Vokabeln (80%-Pool):",
    "vocab_testing_empty":   "testing_vocab leer (count=0) – introduce_new aufrufen!",
    "vocab_testing_header":  "Testing-Vokabeln (20%-Pool, count={count}):",
    "vocab_confirmed_now":   "✓ '{word}' jetzt BESTÄTIGT (nach {uses}x korrekter Nutzung)",
    "vocab_progress":        "✓ correct_use für '{word}' → {uses}/{threshold}",
    "vocab_notfound":        "[Wort '{word}' nicht in der Vokabelliste gefunden]",
    "vocab_dup":             "['{word}' bereits in der Vokabelliste vorhanden]",
    "vocab_added":           "✓ Neues Wort hinzugefügt: '{word}' ({reading})",
    "known_noword":          "[kein Wort]",
    "known_marked":          "✓ '{word}' als bekannt markiert",
    "known_added":           "✓ '{word}' als bekannt hinzugefügt",
    "stats":                 "Vokabeln gesamt: {total} | bestätigt: {confirmed} | im Testing: {testing}",
    "struct_none":           "Noch keine Satzmuster. Wenn sie sicher ist, mit introduce_structure eins einführen.",
    "struct_header":         "Satzmuster/Sagweisen im Lernen:",
    "struct_line":           "{pattern} — {note} ({uses}x{tag})",
    "struct_mastered_tag":   ", gefestigt",
    "struct_nopattern":      "[kein Muster]",
    "struct_dup":            "['{pattern}' bereits vorhanden]",
    "struct_new":            "✓ Neues Muster: {pattern}",
    "struct_mastered":       "✓ Muster '{pattern}' gefestigt",
    "struct_progress":       "✓ '{pattern}' {uses}/{threshold}",
    "struct_notfound":       "['{pattern}' nicht gefunden]",
    "news_none":             "(gerade kein Thema — quatsch einfach weiter)",
    "news_wrap":             "(beiläufig erwähnen, nicht wie Nachrichten vorlesen) Thema aus {country}: {topic}",
    "tv_wrap":               "(Fernseher an — sag beiläufig, was läuft) Läuft: {title} ({level}, {note})",
}


def _phrase(key: str, lang: str = None, **fmt) -> str:
    """Modell-sichtbarer Text: Sprach-Paket zuerst, sonst deutscher Default."""
    p = _prof(lang)
    tmpl = (p.get("phrases") or {}).get(key) or _DEFAULT_PHRASES.get(key, "")
    try:
        return tmpl.format(**fmt)
    except Exception:
        return tmpl


# ── Vokabeln ────────────────────────────────────────────────────────────

def _load_raw(lang: str = None) -> list:
    """Vokabelliste der Sprache von Disk (ohne Lock – nur intern)."""
    path = _file('vocab.json', lang)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _write_raw(entries: list, lang: str = None):
    """Vokabelliste der Sprache auf Disk (ohne Lock – nur intern)."""
    with open(_file('vocab.json', lang), 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent='\t', ensure_ascii=False)


def _reading(e: dict) -> str:
    """Lesehilfe eines Eintrags. Akzeptiert den alten 'pinyin'-Schlüssel, damit
    eine noch nicht migrierte Datei nicht stumm leere Klammern rendert."""
    return e.get('reading') or e.get('pinyin') or ''


def _fmt(e: dict) -> str:
    r = _reading(e)
    return f"{e['word']} ({r})" if r else str(e.get('word', ''))


def get_confirmed_vocab(lang: str = None) -> str:
    """Alle gefestigten Vokabeln (confirmed=True) — der 80%-Pool."""
    with _lock:
        entries = _load_raw(lang)
    confirmed = [e for e in entries if e.get('confirmed')]
    if not confirmed:
        return _phrase("vocab_none", lang)
    return (_phrase("vocab_confirmed_header", lang) + "\n"
            + "\n".join(_fmt(e) for e in confirmed))


def get_testing_vocab(lang: str = None) -> str:
    """Alle Vokabeln im Lernen (confirmed=False) — der 20%-Pool + count."""
    with _lock:
        entries = _load_raw(lang)
    testing = [e for e in entries if not e.get('confirmed')]
    if not testing:
        return _phrase("vocab_testing_empty", lang)
    lines = [f"{_fmt(e)} – {e.get('correct_use', 0)}x" for e in testing]
    return (_phrase("vocab_testing_header", lang, count=len(testing)) + "\n"
            + "\n".join(lines))


def increment_correct_use(word: str, lang: str = None) -> str:
    """+1 auf ein Wort. Ab CONFIRM_THRESHOLD springt es auf confirmed."""
    with _lock:
        entries = _load_raw(lang)
        for e in entries:
            if e['word'] == word:
                e['correct_use'] = e.get('correct_use', 0) + 1
                if e['correct_use'] >= CONFIRM_THRESHOLD and not e.get('confirmed'):
                    e['confirmed'] = True
                    _write_raw(entries, lang)
                    return _phrase("vocab_confirmed_now", lang,
                                   word=word, uses=e['correct_use'])
                _write_raw(entries, lang)
                return _phrase("vocab_progress", lang, word=word,
                               uses=e['correct_use'], threshold=CONFIRM_THRESHOLD)
        return _phrase("vocab_notfound", lang, word=word)


def introduce_new(word: str, reading: str = "", lang: str = None) -> str:
    """Neues Wort in den Lern-Pool. Dedupt selbst (bekannt → no-op)."""
    with _lock:
        entries = _load_raw(lang)
        if any(e['word'] == word for e in entries):
            return _phrase("vocab_dup", lang, word=word)
        entries.append({'word': word, 'reading': reading or '',
                        'correct_use': 0, 'confirmed': False})
        _write_raw(entries, lang)
    return _phrase("vocab_added", lang, word=word, reading=reading or '')


def mark_known(word: str, reading: str = "", lang: str = None) -> str:
    """Vokabel-Check: das kann sie SCHON → direkt als gefestigt ablegen.
    Gegenstück zu show_thought/introduce_new (die etwas NEUES anlegen)."""
    word = (word or "").strip()
    if not word:
        return _phrase("known_noword", lang)
    with _lock:
        entries = _load_raw(lang)
        for e in entries:
            if e['word'] == word:
                e['confirmed'] = True
                if e.get('correct_use', 0) < CONFIRM_THRESHOLD:
                    e['correct_use'] = CONFIRM_THRESHOLD
                _write_raw(entries, lang)
                return _phrase("known_marked", lang, word=word)
        entries.append({'word': word, 'reading': reading or '',
                        'correct_use': CONFIRM_THRESHOLD, 'confirmed': True})
        _write_raw(entries, lang)
    return _phrase("known_added", lang, word=word)


def term_list(lang: str = None) -> list:
    """Alle Wörter (gefestigt + im Lernen) — für den Vokabel-Kontext."""
    with _lock:
        entries = _load_raw(lang)
    return [e['word'] for e in entries if e.get('word')]


def vocab_split(lang: str = None) -> tuple:
    """(gefestigt, im Lernen) — damit die Persona weiß, worauf sie bauen kann."""
    with _lock:
        entries = _load_raw(lang)
    solid = [e['word'] for e in entries if e.get('word') and e.get('confirmed')]
    learn = [e['word'] for e in entries if e.get('word') and not e.get('confirmed')]
    return solid, learn


def get_vocab_stats(lang: str = None) -> str:
    """Kurz-Statistik (Dashboard/Session-Start). KEIN AI-Tool."""
    with _lock:
        entries = _load_raw(lang)
    total     = len(entries)
    confirmed = sum(1 for e in entries if e.get('confirmed'))
    return _phrase("stats", lang, total=total, confirmed=confirmed,
                   testing=total - confirmed)


# ── Kern-Syllabus: festes Grund-Vokabular + Fortschritt ─────────────────
# Zusätzlich zum EMERGENTEN Vokabular (das nur wächst, wenn die Persona zufällig
# ein Wort per show_thought zeigt) trägt eine Sprache optional ein festes
# CURRICULUM: die ersten ~75 Kern-Wörter, die verlässlich drankommen sollen.
#
# Trennung wie überall im Tutor:
#   • Curriculum = SPRACHE, kommt mit dem Repo → tutor/langs/<lang>/core_vocab.json
#     (in PROFILE['core_vocab'], base.load_json). Wird NIE geschrieben.
#   • Lernstand  = LAUFZEIT, gitignored → data/<lang>/vocab.json (confirmed-Flags)
#     + data/<lang>/progress.json (der einmalige Graduierungs-Meilenstein).
# Die Deckung misst sich, indem man die Curriculum-Wörter gegen die als
# confirmed markierten Vokabeln schneidet — kein zweiter Zähler, keine Divergenz.

_PRIO_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
GRADUATE_AT = 0.75    # Anteil gefestigter Kern-Wörter → Kern-Wortschatz „gemeistert"


def _core_list(lang: str = None) -> list:
    """Das Kern-Curriculum der Sprache (Paket-DATEN). Leer → kein Syllabus."""
    return [e for e in (_prof(lang).get("core_vocab") or [])
            if isinstance(e, dict) and e.get("word")]


def _confirmed_words(lang: str = None) -> set:
    with _lock:
        entries = _load_raw(lang)
    return {e["word"] for e in entries if e.get("confirmed") and e.get("word")}


def core_coverage(lang: str = None) -> tuple:
    """(gefestigte Kern-Wörter, Kern-Gesamt). (0,0) wenn die Sprache kein
    Curriculum trägt — der Aufrufer behandelt das als „Feature inaktiv"."""
    core = _core_list(lang)
    if not core:
        return (0, 0)
    confirmed = _confirmed_words(lang)
    got = sum(1 for e in core if e["word"] in confirmed)
    return (got, len(core))


def core_ratio(lang: str = None) -> float:
    got, total = core_coverage(lang)
    return (got / total) if total else 0.0


def core_todo(lang: str = None, n: int = 6) -> list:
    """Die nächsten n noch nicht gefestigten Kern-Wörter, nach Priorität
    (critical→low). Für den Syllabus-Hinweis an die Persona: WAS als Nächstes
    dran ist, damit sie das Curriculum aktiv abarbeitet statt beliebig."""
    core = _core_list(lang)
    if not core:
        return []
    confirmed = _confirmed_words(lang)
    todo = [e for e in core if e["word"] not in confirmed]
    todo.sort(key=lambda e: _PRIO_ORDER.get(e.get("priority"), 9))
    return todo[:max(0, n)]


def core_graduated(lang: str = None) -> bool:
    """Ist die Kern-Schwelle erreicht (≥GRADUATE_AT gefestigt)? Reiner Blick auf
    die Deckung — der EINMALIGE Meilenstein läuft über check_graduation()."""
    total = core_coverage(lang)[1]
    return total > 0 and core_ratio(lang) >= GRADUATE_AT


def core_status(lang: str = None) -> str:
    """Kurze Fortschritts-Zeile für UI/Log (KEIN AI-Tool, deutsch)."""
    got, total = core_coverage(lang)
    if not total:
        return "kein Kern-Syllabus für diese Sprache"
    pct = int(round(100 * got / total))
    tail = " — gemeistert" if core_graduated(lang) else ""
    return f"Kern-Wortschatz: {got}/{total} ({pct}%){tail}"


def _progress_load(lang: str = None) -> dict:
    path = _file('progress.json', lang)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _progress_save(d: dict, lang: str = None):
    try:
        with open(_file('progress.json', lang), 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def check_graduation(lang: str = None) -> bool:
    """Nach einem Turn aufrufen: hat die Lernende gerade ERSTMALS die Kern-
    Schwelle überschritten? Genau EINMAL True (der Meilenstein), danach nie
    wieder — der Zustand liegt in data/<lang>/progress.json.

    BEWUSST NICHT in persona_mem (den Grob-Notizen): dort ist es (a) ein
    Fake-Gedächtnis-Fakt, den die Persona nie „erlebt" hat, und (b) der
    Notiz-Block wandert in den Cloud-Prompt — ein Steuer-Flag hat da nichts zu
    suchen (Sashas Vorgabe: raus aus den facts)."""
    if not core_graduated(lang):
        return False
    prog = _progress_load(lang)
    if prog.get("graduated"):
        return False
    prog["graduated"] = True
    _progress_save(prog, lang)
    return True


# ── Assessment-Gate (hartes Gate vor der Persona) ───────────────────────
# Trägt die Sprache ein Kern-Curriculum UND ist es noch nicht gemeistert, dann
# steckt die Lernende im ASSESSMENT-/Drill-Modus: das Persona-Zimmer bleibt zu,
# die Figur „lebt" nicht — es wird nur geübt (Wort für Wort, Stimme liest vor),
# bis ≥GRADUATE_AT der Kern-Wörter gefestigt sind. Sprachen OHNE Kern-Curriculum
# (z.B. zh) haben kein Gate → sofort Konversation (Verhalten unverändert).

def assessment_active(lang: str = None) -> bool:
    """Steckt die Lernende noch im Assessment (Kern < Schwelle)? → Zimmer gesperrt."""
    total = core_coverage(lang)[1]
    if not total:
        return False           # kein Curriculum → kein Gate
    return not core_graduated(lang)


def tts_speed_for(lang: str = None) -> float:
    """Sprech-Tempo nach Meisterung: im Assessment langsam (0.7) und rampt linear
    hoch bis natürlich (1.0) an der Freischalt-Schwelle; danach immer 1.0. Damit
    Anfänger die einzelnen Wörter klar hören und es mit dem Können schneller wird."""
    if not assessment_active(lang):
        return 1.0
    r = min(core_ratio(lang), GRADUATE_AT) / GRADUATE_AT     # 0..1 über den Drill
    return round(0.7 + 0.3 * r, 2)


# ── Satz-Strukturen (Feinmodell: nicht nur Wörter) ──────────────────────
# Parallel zum Vokabel-Pool, aber für Muster/Grammatik — damit die Persona auch
# neue SAGWEISEN stückweise einführen kann (Sashas Idee), nicht nur Vokabeln.

def _struct_load(lang: str = None) -> list:
    path = _file('structures.json', lang)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _struct_write(entries: list, lang: str = None):
    with open(_file('structures.json', lang), 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent='\t', ensure_ascii=False)


def get_structures(lang: str = None) -> str:
    with _lock:
        e = _struct_load(lang)
    if not e:
        return _phrase("struct_none", lang)
    lines = [_phrase("struct_line", lang, pattern=s['pattern'],
                     note=s.get('note', ''), uses=s.get('uses', 0),
                     tag=_phrase("struct_mastered_tag", lang) if s.get('confirmed') else "")
             for s in e]
    return _phrase("struct_header", lang) + "\n" + "\n".join(lines)


def structure_list(lang: str = None) -> list:
    with _lock:
        e = _struct_load(lang)
    return [s['pattern'] for s in e if s.get('pattern')]


def introduce_structure(pattern: str, note: str = "", lang: str = None) -> str:
    pattern = (pattern or '').strip()
    if not pattern:
        return _phrase("struct_nopattern", lang)
    with _lock:
        e = _struct_load(lang)
        if any(s.get('pattern') == pattern for s in e):
            return _phrase("struct_dup", lang, pattern=pattern)
        e.append({"pattern": pattern, "note": (note or '').strip(),
                  "uses": 0, "confirmed": False})
        _struct_write(e, lang)
    return _phrase("struct_new", lang, pattern=pattern)


def increment_structure(pattern: str, lang: str = None) -> str:
    pattern = (pattern or '').strip()
    with _lock:
        e = _struct_load(lang)
        for s in e:
            if s.get('pattern') == pattern:
                s['uses'] = s.get('uses', 0) + 1
                if s['uses'] >= STRUCT_THRESHOLD and not s.get('confirmed'):
                    s['confirmed'] = True
                    _struct_write(e, lang)
                    return _phrase("struct_mastered", lang, pattern=pattern)
                _struct_write(e, lang)
                return _phrase("struct_progress", lang, pattern=pattern,
                               uses=s['uses'], threshold=STRUCT_THRESHOLD)
    return _phrase("struct_notfound", lang, pattern=pattern)


# ── Landes-Themen (persona-isoliert) ────────────────────────────────────
# Die Persona kann beiläufig ein Thema aus ihrem Land aufbringen.
# WICHTIG: eigener, tutor-isolierter Pool — fasst NIEMALS core/news.py an (das
# ist Sashas DE/World-News der Core-KI; Sandbox). Seed statt echtem Feed
# (Content-Lücke). Der Seed lebt im SPRACH-PAKET (getrackt, kommt mit dem Repo);
# die Datei unter data/<lang>/ hält nur den Rotations-Cursor (Laufzeit).

def _news_items(lang: str = None) -> list:
    return [s for s in ((_prof(lang).get("seeds") or {}).get("news") or [])
            if isinstance(s, str) and s.strip()]


def _cursor(name: str, lang: str = None) -> int:
    path = _file(name, lang)
    if not os.path.exists(path):
        return 0
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return int(json.load(f).get('cursor', 0) or 0)
    except Exception:
        return 0


def _bump(name: str, nxt: int, lang: str = None):
    try:
        with open(_file(name, lang), 'w', encoding='utf-8') as f:
            json.dump({"cursor": nxt}, f)
    except Exception:
        pass


def get_local_news(lang: str = None) -> str:
    """Ein leichtes Gesprächsthema aus dem Land der Persona (rotierend).
    Beiläufig einstreuen, nicht wie eine Nachrichtensendung vorlesen."""
    with _lock:
        items = _news_items(lang)
        if not items:
            return _phrase("news_none", lang)
        cur = _cursor('news.json', lang) % len(items)
        topic = items[cur]
        _bump('news.json', (cur + 1) % len(items), lang)
    return _phrase("news_wrap", lang, topic=topic,
                   country=_prof(lang).get("country", ""))


# ── TV / Mediathek (persona-isoliert) ───────────────────────────────────
# Katalog im SPRACH-PAKET (nur Titel/Meta, kein Video — echtes Playback ist
# deferred). Filtert nach Stimmung, bevorzugt für Anfänger Leichtes.

def watch_tv(mood: str = "chill", lang: str = None) -> str:
    """TV an + etwas Level-gerechtes wählen. Rotiert. Reine UI/Katalog."""
    m = (mood or "chill").strip().lower()
    seed = (_prof(lang).get("seeds") or {}).get("tv") or []
    if not seed:
        return "ok"
    with _lock:
        pool = [e for e in seed if e.get("mood") == m] or list(seed)
        cur = _cursor('tv.json', lang) % len(pool)
        pick = pool[cur]
        _bump('tv.json', (cur + 1) % len(pool), lang)
    try:
        from . import session as tutor_session
        tutor_session.tv_on(pick["title"])
    except Exception:
        pass
    return _phrase("tv_wrap", lang, title=pick.get("title", ""),
                   level=pick.get("level", ""), note=pick.get("note", ""))


def turn_off_tv(lang: str = None) -> str:
    try:
        from . import session as tutor_session
        tutor_session.tv_off()
    except Exception:
        pass
    return "ok"


# ── Zimmer: Musik, Ausdruck, Gedanke ────────────────────────────────────
# Reine UI — reicht nur den Wunsch an session; das Fenster spielt/animiert.

def play_music(mood: str = "chill", lang: str = None) -> str:
    """Musik nach Stimmung; das Fenster spielt aus tutor/data/persona_music/."""
    try:
        from . import session as tutor_session
        return f"ok（{tutor_session.play_music(mood)}）"
    except Exception:
        return "ok"


def stop_music(lang: str = None) -> str:
    try:
        from . import session as tutor_session
        tutor_session.stop_music()
    except Exception:
        pass
    return "ok"


def express(action: str, lang: str = None) -> str:
    """Haltung/Geste/Mimik im Zimmer. Lazy-Import bricht den Zyklus
    tools ↔ session. Reine UI-Bewegung — kein Zugriff auf die lokale AI."""
    try:
        from . import session as tutor_session
        tutor_session.set_expression(action)
    except Exception:
        pass
    return "ok"


def show_thought(word: str, meaning: str = "", reading: str = "",
                 lang: str = None) -> str:
    """Zeigt „in Gedanken" ein Wort + seine Bedeutung (Übersetzung, im Fenster
    ggf. ein Bild aus tutor/data/vocab_images/<wort>.png) — comprehensible input
    statt Text-Erklärung.

    TRACKING-KOPPLUNG: ist das Wort neu, wandert es zugleich in die Vokabelliste
    (introduce_new dedupt selbst). So wächst der Umfang genau mit dem, was die
    Persona real zeigt — der verlässliche Anker fürs Tracking (Sashas Vorgabe)."""
    word = (word or "").strip()
    try:
        from . import session as tutor_session
        tutor_session.set_thought(word, meaning)
    except Exception:
        pass
    if word:
        introduce_new(word, reading, lang)
    return "ok"


# ── Tool-Schema (Struktur sprach-neutral, Texte aus dem Paket) ──────────
# Die STRUKTUR (Namen, Parameter, Enums) ist für alle Sprachen gleich; die
# BESCHRIFTUNG kommt aus tutor/langs/<lang>/tool_texts.json. Fehlt sie, greifen
# die deutschen Defaults unten — genau wie beim Prompt (getunte Sprache bringt
# ihre eigene, Skizze nimmt den generischen Fallback).

_EXPRESS_ACTIONS = ["sit", "stand", "pace", "wander", "come_closer", "sleep",
                    "wave", "nod", "look", "stretch", "arms_up", "cross_arms",
                    "shrug", "happy", "sad", "surprised", "tired", "puzzled",
                    "neutral"]

_TOOL_SPECS = [
    ("get_confirmed_vocab", {}, []),
    ("get_testing_vocab",   {}, []),
    ("increment_correct_use", {"word": "string"}, ["word"]),
    ("introduce_new",       {"word": "string", "reading": "string"}, ["word"]),
    ("express",             {"action": ("string", _EXPRESS_ACTIONS)}, ["action"]),
    ("get_structures",      {}, []),
    ("introduce_structure", {"pattern": "string", "note": "string"}, ["pattern"]),
    ("increment_structure", {"pattern": "string"}, ["pattern"]),
    ("watch_tv",            {"mood": ("string", ["chill", "happy", "focus", "sad"])}, ["mood"]),
    ("turn_off_tv",         {}, []),
    ("play_music",          {"mood": ("string", ["chill", "happy", "focus", "sad", "energetic"])}, ["mood"]),
    ("stop_music",          {}, []),
    ("get_local_news",      {}, []),
    ("mark_known",          {"word": "string", "reading": "string"}, ["word"]),
    ("show_thought",        {"word": "string", "meaning": "string", "reading": "string"}, ["word"]),
]

_DEFAULT_TEXTS = {
    "get_confirmed_vocab":  {"description": "Gibt alle gefestigten Vokabeln zurück (80%-Pool). Zu Session-Beginn aufrufen."},
    "get_testing_vocab":    {"description": "Gibt die Vokabeln im Lernen zurück (20%-Pool). Zu Session-Beginn aufrufen; count < 10 → introduce_new."},
    "increment_correct_use": {"description": "Zähler für ein korrekt verwendetes Wort erhöhen. Aufrufen, wenn sie das Wort korrekt und sinnvoll genutzt hat.",
                              "params": {"word": "Das Wort in der Zielsprache"}},
    "introduce_new":        {"description": "Fügt ein neues Wort zum Lern-Pool hinzu. Nur aufrufen, wenn get_testing_vocab weniger als 10 Wörter zurückgibt.",
                             "params": {"word": "Das Wort in der Zielsprache",
                                        "reading": "Lesehilfe (Aussprache/Umschrift), falls die Sprache eine braucht"}},
    "express":              {"description": "Ausdruck im Zimmer (Haltung/Geste/Mimik) — nutz das zum Bewegen, schreib es NICHT als Text.",
                             "params": {"action": "Haltung, Geste oder Mimik"}},
    "get_structures":       {"description": "Zeigt, welche Satzmuster/Sagweisen sie gerade lernt (nicht nur Wörter)."},
    "introduce_structure":  {"description": "Ab und zu ein neues Satzmuster einführen, wenn die vorhandenen Wörter sitzen. Nicht mehrere auf einmal.",
                             "params": {"pattern": "Das Satzmuster", "note": "Kurze Notiz (optional)"}},
    "increment_structure":  {"description": "Aufrufen, wenn sie ein Satzmuster korrekt verwendet hat.",
                             "params": {"pattern": "Das Satzmuster"}},
    "watch_tv":             {"description": "Fernseher an, etwas Level-gerechtes nach Stimmung. Sag beiläufig, was läuft — kein Vortrag.",
                             "params": {"mood": "Stimmung"}},
    "turn_off_tv":          {"description": "Fernseher aus."},
    "play_music":           {"description": "Musik im Zimmer nach Stimmung auflegen. Einfach auflegen, nicht ständig thematisieren.",
                             "params": {"mood": "Stimmung"}},
    "stop_music":           {"description": "Musik aus."},
    "get_local_news":       {"description": "Ein leichtes Thema aus deinem Land, um beiläufig darüber zu quatschen. Nicht wie Nachrichten vorlesen. Du bist eine KI — das ist nichts, was du selbst erlebt hast."},
    "mark_known":           {"description": "Ein Wort, das sie SCHON kann, als gefestigt ablegen. Gegenstück zu show_thought (das ein NEUES Wort einführt).",
                             "params": {"word": "Das Wort, das sie schon kann",
                                        "reading": "Lesehilfe (falls die Sprache eine braucht)"}},
    "show_thought":         {"description": "Für jedes Wort, das sie noch nicht kennt: zeig es ihr in Gedanken (Bild oder Übersetzung), statt es mit vielen Worten zu erklären. Legt das Wort automatisch mit in die Vokabelliste.",
                             "params": {"word": "Das zu zeigende Wort",
                                        "meaning": "Deutsche Bedeutung/Übersetzung",
                                        "reading": "Lesehilfe (falls die Sprache eine braucht)"}},
}


def tools_for(lang: str = None) -> list:
    """Das Tool-Schema, das die Persona DIESER Sprache sieht (OpenAI-Format).

    Ersetzt die frühere statische TUTOR_TOOLS-Liste: die trug chinesische
    Beschreibungen und ein 'pinyin'-Feld — jede andere Sprache bekam damit
    Anweisungen auf Chinesisch."""
    texts = dict(_DEFAULT_TEXTS)
    for name, t in (_prof(lang).get("tool_texts") or {}).items():
        if isinstance(t, dict):
            merged = dict(texts.get(name) or {})
            merged.update(t)
            texts[name] = merged

    out = []
    for name, params, required in _TOOL_SPECS:
        t = texts.get(name) or {}
        ptexts = t.get("params") or {}
        props = {}
        for pname, spec in params.items():
            typ, enum = (spec, None) if isinstance(spec, str) else spec
            prop = {"type": typ}
            if enum:
                prop["enum"] = enum
            if ptexts.get(pname):
                prop["description"] = ptexts[pname]
            props[pname] = prop
        fn = {"name": name, "description": t.get("description", ""),
              "parameters": {"type": "object", "properties": props}}
        if required:
            fn["parameters"]["required"] = required
        out.append({"type": "function", "function": fn})
    return out


# ── Tool-Dispatcher ─────────────────────────────────────────────────────
#
# ── Cloud→Lokal-Sandbox (Choke-Point) ───────────────────────────────────
# Dies ist die EINZIGE Stelle, an der eine Tutor-/Cloud-AI etwas "ausführt".
# Sie ist eine GESCHLOSSENE Allowlist. JEDES Tool hier fasst NUR tutor-isolierte
# Ressourcen an: die Dateien unter tutor/data/<lang>/ und den UI-Zustand im
# Zimmer (session: Ausdruck/Gedanke/Presence). Damit kann die Cloud-AI NICHT in
# die lokale AI greifen – kein graph/consolidation, keine lokalen Tools
# (save_memory/read_file/web/mail/…), kein Datei-Whitelist-Zugriff, KEIN Zugriff
# auf core/news.py (Sashas DE/World-News). Wer hier einen Tool-Namen ergänzt,
# erweitert bewusst die Reichweite der Cloud-AI — dann prüfen, dass er wirklich
# nur tutor-eigene Daten berührt.

def _read(a: dict) -> str:
    """Lesehilfe aus den Tool-Args. Nimmt auch 'pinyin' an — ein Modell, das den
    alten Namen halluziniert, soll die Angabe nicht stumm verlieren."""
    return a.get("reading") or a.get("pinyin") or ""


_ALLOWED = {
    "get_confirmed_vocab":   lambda a: get_confirmed_vocab(),
    "get_testing_vocab":     lambda a: get_testing_vocab(),
    "increment_correct_use": lambda a: increment_correct_use(a.get("word", "")),
    "introduce_new":         lambda a: introduce_new(a.get("word", ""), _read(a)),
    "express":               lambda a: express(a.get("action", "")),
    "get_structures":        lambda a: get_structures(),
    "introduce_structure":   lambda a: introduce_structure(a.get("pattern", ""), a.get("note", "")),
    "increment_structure":   lambda a: increment_structure(a.get("pattern", "")),
    "watch_tv":              lambda a: watch_tv(a.get("mood", "chill")),
    "turn_off_tv":           lambda a: turn_off_tv(),
    "play_music":            lambda a: play_music(a.get("mood", "chill")),
    "stop_music":            lambda a: stop_music(),
    "get_local_news":        lambda a: get_local_news(),
    "show_thought":          lambda a: show_thought(a.get("word", ""), a.get("meaning", ""), _read(a)),
    "mark_known":            lambda a: mark_known(a.get("word", ""), _read(a)),
}


def execute_tool(name: str, args: dict) -> str:
    """Führt ein Tutor-Tool aus. Allowlist-Sandbox: alles andere wird abgelehnt
    UND geflaggt (eine Cloud-AI, die ein lokales Tool ruft, soll sichtbar sein,
    nicht still durchrutschen)."""
    fn = _ALLOWED.get(name)
    if fn is None:
        try:
            import state
            state.push_log(f"⚠ TUTOR-SANDBOX: Tool '{name}' abgelehnt (nicht in der Allowlist)")
        except Exception:
            pass
        return (f"[Abgelehnt: '{name}' ist kein Tutor-Tool – die Tutor-/Cloud-AI "
                f"darf nur die Tutor-Tools nutzen.]")
    return fn(args or {})
