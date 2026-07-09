# core/tutor.py
#
# Vokabel-Tools für den Mandarin-Sprachtutor.
#
# Diese Funktionen werden als AI-Tools (über ai.py TOOLS-Liste) der KI bereitgestellt.
# Mistral kann sie während einer Tutor-Session aufrufen um die Vokabelliste zu lesen
# und zu schreiben.
#
# ── Konzept: confirmed vs. testing ───────────────────────────────────
#   confirmed = False  → Wort wird gerade gelernt (20%-Pool)
#   confirmed = True   → Wort ist gefestigt (80%-Pool)
#
# ── Auto-Confirm-Schwelle ─────────────────────────────────────────────
#   correct_use >= CONFIRM_THRESHOLD → confirmed wird automatisch auf True gesetzt
#
# ── Wer ruft was auf ─────────────────────────────────────────────────
#   KI zu Session-Beginn:  get_confirmed_vocab() + get_testing_vocab()
#   KI nach korrekter Nutzung: increment_correct_use(word)
#   KI wenn testing_vocab < 10 neue Wörter hat: introduce_new(word, pinyin)

import json
import os
from threading import Lock

_VOCAB_FILE = os.path.join(os.path.dirname(__file__), '..', 'vocab_mandarin.json')
_lock       = Lock()  # Mehrere Threads (Flask + Event-Loop) könnten gleichzeitig lesen/schreiben

# Ab dieser Anzahl korrekter Verwendungen gilt ein Wort als bestätigt.
CONFIRM_THRESHOLD = 5


def _load_raw() -> list:
    """Lädt die Vokabelliste von Disk (ohne Lock – nur intern nutzen)."""
    if not os.path.exists(_VOCAB_FILE):
        return []
    with open(_VOCAB_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_raw(entries: list):
    """Schreibt die Vokabelliste auf Disk (ohne Lock – nur intern nutzen)."""
    with open(_VOCAB_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent='\t', ensure_ascii=False)


def get_confirmed_vocab() -> str:
    """
    Gibt alle bestätigten Vokabeln zurück (confirmed=True).
    KI soll diese ~80% der Zeit im Gespräch verwenden.
    Rückgabe: formatierter String für den AI-Prompt.
    """
    with _lock:
        entries = _load_raw()
    confirmed = [e for e in entries if e.get('confirmed')]
    if not confirmed:
        return "Noch keine bestätigten Vokabeln vorhanden."
    lines = [f"{e['word']} ({e['pinyin']})" for e in confirmed]
    return "Bestätigte Vokabeln (80%-Pool):\n" + "\n".join(lines)


def get_testing_vocab() -> str:
    """
    Gibt alle Vokabeln zurück die noch nicht bestätigt sind (confirmed=False).
    KI soll diese ~20% der Zeit einstreuen.
    Rückgabe: formatierter String + Anzahl (wichtig für introduce_new-Entscheidung).
    """
    with _lock:
        entries = _load_raw()
    testing = [e for e in entries if not e.get('confirmed')]
    count   = len(testing)
    if count == 0:
        return "testing_vocab leer (count=0) – introduce_new aufrufen!"
    lines = [f"{e['word']} ({e['pinyin']}) – {e['correct_use']}x korrekt genutzt" for e in testing]
    return f"Testing-Vokabeln (20%-Pool, count={count}):\n" + "\n".join(lines)


def increment_correct_use(word: str) -> str:
    """
    Erhöht den correct_use-Zähler für ein Wort um 1.
    Wenn correct_use >= CONFIRM_THRESHOLD: Wort wird automatisch als confirmed markiert.

    KI soll dies aufrufen wenn die Lernende das Wort korrekt und sinnvoll verwendet hat.
    Rückgabe: Bestätigungsstring (den die KI sieht, aber nicht vorlesen muss).
    """
    with _lock:
        entries = _load_raw()
        for entry in entries:
            if entry['word'] == word:
                entry['correct_use'] += 1
                # Auto-confirm wenn Schwelle erreicht
                if entry['correct_use'] >= CONFIRM_THRESHOLD and not entry['confirmed']:
                    entry['confirmed'] = True
                    _write_raw(entries)
                    return f"✓ '{word}' jetzt BESTÄTIGT (nach {entry['correct_use']}x korrekter Nutzung)"
                _write_raw(entries)
                return f"✓ correct_use für '{word}' → {entry['correct_use']}/{CONFIRM_THRESHOLD}"
        return f"[Wort '{word}' nicht in der Vokabelliste gefunden]"


def introduce_new(word: str, pinyin: str) -> str:
    """
    Fügt ein neues Wort zur Vokabelliste hinzu (als testing, correct_use=0).
    KI soll dies aufrufen wenn get_testing_vocab() weniger als 10 Wörter zurückgibt.

    word:   chinesische Zeichen, z.B. "你好"
    pinyin: Lautschrift mit Tönen, z.B. "nǐ hǎo"
    Rückgabe: Bestätigungsstring.
    """
    with _lock:
        entries = _load_raw()
        # Duplikate verhindern
        if any(e['word'] == word for e in entries):
            return f"['{word}' bereits in der Vokabelliste vorhanden]"
        entries.append({
            'word':        word,
            'pinyin':      pinyin,
            'correct_use': 0,
            'confirmed':   False,
        })
        _write_raw(entries)
    return f"✓ Neues Wort hinzugefügt: '{word}' ({pinyin})"


def term_list() -> list:
    """Alle Vokabel-Wörter (confirmed + testing) als flache Liste — für den
    Vokabel-Kontext, den tutor_session dem Persona-Prompt anhängt."""
    with _lock:
        entries = _load_raw()
    return [e['word'] for e in entries if e.get('word')]


def vocab_split() -> tuple:
    """(gefestigte Wörter, im-Lernen-Wörter) — für den Vokabel-Kontext, damit die
    KI weiß, worauf sie bauen kann und was sie noch festigen soll (Feinmodell)."""
    with _lock:
        entries = _load_raw()
    solid = [e['word'] for e in entries if e.get('word') and e.get('confirmed')]
    learn = [e['word'] for e in entries if e.get('word') and not e.get('confirmed')]
    return solid, learn


# ── Satz-Strukturen / neue „Sagweisen" (Feinmodell: nicht nur Wörter) ────────
# Parallel zum Vokabel-Pool, aber für Grammatik/Muster („怎么说X", „把-Satz", …).
# Damit die Persona nicht nur neue WÖRTER, sondern auch neue STRUKTUREN stückweise
# einführen kann (Sashas Idee). Mandarin-fest wie die Vokabeldatei.
_STRUCT_FILE      = os.path.join(os.path.dirname(__file__), '..', 'data', 'structures_mandarin.json')
STRUCT_THRESHOLD  = 3


def _struct_load() -> list:
    if not os.path.exists(_STRUCT_FILE):
        return []
    try:
        with open(_STRUCT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def _struct_write(entries: list):
    os.makedirs(os.path.dirname(_STRUCT_FILE), exist_ok=True)
    with open(_STRUCT_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent='\t', ensure_ascii=False)


def get_structures() -> str:
    with _lock:
        e = _struct_load()
    if not e:
        return "还没有句型。她熟了可以用 introduce_structure 加一个新说法。"
    lines = [f"{s['pattern']} — {s.get('note','')}（{s.get('uses',0)}次" +
             ("，已掌握" if s.get('confirmed') else "") + "）" for s in e]
    return "在学的句型/说法:\n" + "\n".join(lines)


def structure_list() -> list:
    with _lock:
        e = _struct_load()
    return [s['pattern'] for s in e if s.get('pattern')]


def introduce_structure(pattern: str, note: str = "") -> str:
    pattern = (pattern or '').strip()
    if not pattern:
        return "[kein Muster]"
    with _lock:
        e = _struct_load()
        if any(s.get('pattern') == pattern for s in e):
            return f"['{pattern}' 已有]"
        e.append({"pattern": pattern, "note": (note or '').strip(), "uses": 0, "confirmed": False})
        _struct_write(e)
    return f"✓ 新句型: {pattern}"


def increment_structure(pattern: str) -> str:
    pattern = (pattern or '').strip()
    with _lock:
        e = _struct_load()
        for s in e:
            if s.get('pattern') == pattern:
                s['uses'] = s.get('uses', 0) + 1
                if s['uses'] >= STRUCT_THRESHOLD and not s.get('confirmed'):
                    s['confirmed'] = True
                    _struct_write(e)
                    return f"✓ 句型 '{pattern}' 已掌握"
                _struct_write(e)
                return f"✓ '{pattern}' {s['uses']}/{STRUCT_THRESHOLD}"
    return f"['{pattern}' 未找到]"


# ── Lokale Landes-News (persona-isoliert) ────────────────────────────────────
# Feature 6: die Persona kann beiläufig ein Thema aus ihrem Land aufbringen.
# WICHTIG: eigener, tutor-isolierter Pool — fasst NIEMALS core/news.py an (das ist
# Sashas DE/World-News der Core-KI; Sandbox). Seed statt echtem Feed (Content-
# Lücke, siehe Feature-Log §6). Der Seed lebt IM CODE (data/*.json ist gitignored,
# rsync-Runtime — käme sonst nicht mit); die Datei hält nur den Rotations-Cursor
# (Runtime-State), bootstrappt beim ersten Aufruf aus dem Seed.
_NEWS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'persona_news_zh.json')

# Leichte, evergreen-nahe Gesprächsthemen aus/über China — casual, kurz. Ling Ling
# bringt sie als „was in China gerade so Thema ist" ein, nicht als eigenes Erlebnis
# (sie ist ehrlich eine KI). Echte tagesaktuelle Meldungen bräuchten einen tutor-
# isolierten China-Feed-Ingest (offen, Content-Lücke).
_NEWS_SEED = [
    "中国很多城市现在几乎只用手机付款，出门都不带现金了",
    "一到秋天，街上就开始卖糖炒栗子，特别香",
    "快到节日的时候，超市里摆满了月饼，各种口味都有",
    "最近好多人喜欢围炉煮茶，一边烤橘子一边聊天",
    "冬天很多人爱去东北看雪、泡温泉",
    "共享单车现在到处都是，骑车上下班的人特别多",
    "外卖在中国太方便了，几分钟就能点到吃的",
    "最近大家都在追一部古装剧，办公室里都在聊",
]


def _news_load() -> dict:
    """Cursor + Items laden. Datei fehlt/kaputt → aus dem Code-Seed. Vorhandene
    Datei ohne items → Seed einsetzen (nur der Cursor ist Runtime-State)."""
    d = {}
    if os.path.exists(_NEWS_FILE):
        try:
            with open(_NEWS_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            d = {}
    if not isinstance(d, dict):
        d = {}
    items = [s for s in (d.get('items') or []) if isinstance(s, str) and s.strip()]
    if not items:
        items = list(_NEWS_SEED)
    return {"cursor": int(d.get('cursor', 0) or 0), "items": items}


def get_local_news() -> str:
    """Ein leichtes Gesprächsthema aus dem Land der Persona (rotierend). Sie soll
    es BEILÄUFIG einstreuen, nicht wie eine Nachrichtensendung vorlesen."""
    with _lock:
        d = _news_load()
        items = [s for s in (d.get('items') or []) if isinstance(s, str) and s.strip()]
        if not items:
            return "（现在没有话题，随便聊聊就好）"
        cur = int(d.get('cursor', 0)) % len(items)
        topic = items[cur]
        d['cursor'] = (cur + 1) % len(items)
        try:
            with open(_NEWS_FILE, 'w', encoding='utf-8') as f:
                json.dump(d, f, indent='\t', ensure_ascii=False)
        except Exception:
            pass
    return f"（可以随口提一句，别像播新闻）中国最近常聊的：{topic}"


def play_music(mood: str = "chill") -> str:
    """Legt im Zimmer Musik nach Stimmung auf (chill/happy/focus/sad/energetic).
    Reicht nur den Wunsch an tutor_session; das Fenster spielt aus seiner lokalen
    Bibliothek (data/persona_music/<mood>/). Reine UI/Audio — kein Core-AI-Zugriff."""
    try:
        import tutor_session
        m = tutor_session.play_music(mood)
        return f"ok（{m}）"
    except Exception:
        return "ok"


def stop_music() -> str:
    """Stoppt die Musik im Zimmer."""
    try:
        import tutor_session
        tutor_session.stop_music()
    except Exception:
        pass
    return "ok"


def express(action: str) -> str:
    """Ausdruck im Zimmer (Haltung/Geste). Reicht die Aktion an tutor_session
    weiter, das den Zustand fürs Fenster hält. Lazy-Import bricht den Zyklus
    tutor↔tutor_session. Reine UI-Bewegung — kein Zugriff auf lokale AI."""
    try:
        import tutor_session
        tutor_session.set_expression(action)
    except Exception:
        pass
    return "ok"


def show_thought(word: str, meaning: str = "") -> str:
    """Zeigt Sasha „in Gedanken" ein Wort + seine Bedeutung (Übersetzung, und im
    Fenster ggf. ein Bild aus data/vocab_images/<wort>.png) — comprehensible input
    statt Text-Erklärung. Reicht an tutor_session weiter (Fenster pollt)."""
    try:
        import tutor_session
        tutor_session.set_thought(word, meaning)
    except Exception:
        pass
    return "ok"


def get_vocab_stats() -> str:
    """
    Gibt eine kurze Statistik über den Lernfortschritt zurück.
    Für das Dashboard und für die KI bei Session-Beginn nützlich.
    """
    with _lock:
        entries = _load_raw()
    total     = len(entries)
    confirmed = sum(1 for e in entries if e.get('confirmed'))
    testing   = total - confirmed
    return f"Vokabeln gesamt: {total} | bestätigt: {confirmed} | im Testing: {testing}"


# ── Tool-Definitionen für ai.py ───────────────────────────────────────
# Diese Liste wird in ai.py in die TOOLS-Liste eingehängt wenn der Tutor-Modus aktiv ist.
# Im normalen Chat-Modus sind die Tutor-Tools NICHT verfügbar (KI nicht verwirren).

TUTOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name":        "get_confirmed_vocab",
            "description": "Gibt alle bestätigten Mandarin-Vokabeln zurück. Zu Session-Beginn aufrufen um den 80%-Pool zu kennen.",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "get_testing_vocab",
            "description": "Gibt alle Vokabeln im Testing-Pool zurück (noch nicht bestätigt). Zu Session-Beginn aufrufen. Falls count < 10: introduce_new aufrufen.",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "increment_correct_use",
            "description": "Erhöht den Zähler für ein korrekt verwendetes Wort. Aufrufen wenn die Lernende das Wort korrekt und sinnvoll in einem Satz genutzt hat.",
            "parameters":  {
                "type":       "object",
                "properties": {
                    "word": {
                        "type":        "string",
                        "description": "Das chinesische Wort (Zeichen), z.B. '你好'",
                    }
                },
                "required": ["word"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "introduce_new",
            "description": "Fügt ein neues Wort zum Testing-Pool hinzu. Nur aufrufen wenn get_testing_vocab weniger als 10 Wörter zurückgibt.",
            "parameters":  {
                "type":       "object",
                "properties": {
                    "word": {
                        "type":        "string",
                        "description": "Chinesisches Zeichen, z.B. '谢谢'",
                    },
                    "pinyin": {
                        "type":        "string",
                        "description": "Pinyin mit Tönen, z.B. 'xiè xie'",
                    },
                },
                "required": ["word", "pinyin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "express",
            "description": "在房间里表达自己（用这个来动/换表情，别写成文字）。姿态：坐下 sit / "
                           "站起 stand / 踱步 pace / 走动 wander / 靠近 come_closer / 睡觉 sleep。"
                           "动作：招手 wave / 点头 nod / 看着她 look / 伸懒腰 stretch / 举起手 "
                           "arms_up / 抱臂 cross_arms / 耸肩 shrug。表情：开心 happy / 难过 sad / "
                           "惊讶 surprised / 累 tired / 平常 neutral。想动、想换表情就自然地用。",
            "parameters":  {
                "type":       "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["sit", "stand", "pace", "wander", "come_closer", "sleep",
                                 "wave", "nod", "look", "stretch", "arms_up", "cross_arms", "shrug",
                                 "happy", "sad", "surprised", "tired", "neutral"],
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "get_structures",
            "description": "看看 Sasha 在学哪些句型/说法（新语法/表达，不只是单词）。",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "introduce_structure",
            "description": "等 Sasha 现有的词熟了，偶尔加一个新句型/新说法（比如 把-字句、怎么说…之类）。别一次加太多。",
            "parameters":  {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "句型，如 '把 X 放在 Y'"},
                    "note":    {"type": "string", "description": "简短说明（可选）"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "increment_structure",
            "description": "Sasha 正确用了某个句型时调用，帮她把它变熟。",
            "parameters":  {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "play_music",
            "description": "想在房间里放点音乐时用（按心情选）。chill 轻松 / happy 开心 / focus 专注 / "
                           "sad 安静 / energetic 有劲儿。放就好，别一直提音乐。",
            "parameters":  {
                "type": "object",
                "properties": {
                    "mood": {"type": "string",
                             "enum": ["chill", "happy", "focus", "sad", "energetic"]},
                },
                "required": ["mood"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "stop_music",
            "description": "把音乐停掉。",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "get_local_news",
            "description": "想跟 Sasha 随口聊聊中国最近的话题时用（比如天气、吃的、节日、大家在聊什么）。"
                           "返回一个话题，你自然地带一句就好，别像播新闻，别一直聊这个。你是 AI，说的是中国的情况，不是你亲身经历。",
            "parameters":  {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name":        "show_thought",
            "description": "想帮 Sasha 懂一个词时，在你脑子里显示这个词和它的意思（图或翻译），"
                           "让她一看就懂——比用一堆话解释好。word 是这个词，meaning 是德语意思。",
            "parameters":  {
                "type": "object",
                "properties": {
                    "word":    {"type": "string", "description": "要解释的词（中文）"},
                    "meaning": {"type": "string", "description": "德语意思/翻译"},
                },
                "required": ["word"],
            },
        },
    },
]


# ── Tool-Dispatcher für ai.py ─────────────────────────────────────────
# ai.py ruft dies auf wenn Mistral ein Tutor-Tool aufruft.

# ── Cloud→Lokal-Sandbox (Choke-Point) ────────────────────────────────
# Dies ist die EINZIGE Stelle, an der eine Tutor-/Cloud-AI etwas "ausführt".
# Sie ist eine GESCHLOSSENE Allowlist. JEDES Tool hier fasst NUR tutor-isolierte
# Ressourcen an: die Vokabel-/Struktur-/News-Dateien (vocab_*.json,
# structures_mandarin.json, persona_news_zh.json) und den UI-Zustand im Zimmer
# (tutor_session: Ausdruck/Gedanke/Presence). Damit kann die Cloud-AI NICHT in
# die lokale AI greifen – kein graph/consolidation, keine lokalen Tools
# (save_memory/read_file/web/mail/…), kein Datei-Whitelist-Zugriff, KEIN Zugriff
# auf core/news.py (Sashas DE/World-News). Wer hier einen Tool-Namen ergänzt,
# erweitert bewusst die Reichweite der Cloud-AI — dann prüfen, dass er wirklich
# nur tutor-eigene Daten berührt.
_ALLOWED = {
    "get_confirmed_vocab":   lambda a: get_confirmed_vocab(),
    "get_testing_vocab":     lambda a: get_testing_vocab(),
    "increment_correct_use": lambda a: increment_correct_use(a.get("word", "")),
    "introduce_new":         lambda a: introduce_new(a.get("word", ""), a.get("pinyin", "")),
    "express":               lambda a: express(a.get("action", "")),
    "get_structures":        lambda a: get_structures(),
    "introduce_structure":   lambda a: introduce_structure(a.get("pattern", ""), a.get("note", "")),
    "increment_structure":   lambda a: increment_structure(a.get("pattern", "")),
    "play_music":            lambda a: play_music(a.get("mood", "chill")),
    "stop_music":            lambda a: stop_music(),
    "get_local_news":        lambda a: get_local_news(),
    "show_thought":          lambda a: show_thought(a.get("word", ""), a.get("meaning", "")),
}


def execute_tool(name: str, args: dict) -> str:
    """Führt ein Tutor-Tool aus. Allowlist-Sandbox: alles außerhalb der 4
    Vokabel-Tools wird abgelehnt UND geflaggt (eine Cloud-AI, die ein lokales
    Tool ruft, soll sichtbar sein, nicht still durchrutschen)."""
    fn = _ALLOWED.get(name)
    if fn is None:
        try:
            import state
            state.push_log(f"⚠ TUTOR-SANDBOX: Tool '{name}' abgelehnt (nicht in der Allowlist)")
        except Exception:
            pass
        return f"[Abgelehnt: '{name}' ist kein Tutor-Tool – die Tutor-/Cloud-AI " \
               f"darf nur Vokabel-Tools nutzen.]"
    return fn(args or {})
