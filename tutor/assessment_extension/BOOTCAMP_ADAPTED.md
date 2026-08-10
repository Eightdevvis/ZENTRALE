# Bootcamp-Lösung für die aktuelle Architektur

## 🔄 Was hat sich geändert?

**Deine neue Architektur ist bereits ideal für Bootcamp:**

1. **Memory ist GROB** (Fakten + Topics) — perfekt um zu tracken ob Bootcamp vorbei ist
2. **History ist persistent** — Lerner vergisst nicht zwischen Sessions
3. **vocab_hint wird injiziert** in System-Prompt — KI sieht automatisch verfügbare Vokabeln
4. **Tools sind Sandbox** — sauber isoliert

**Also: MINIMAL invasiv. Meine alte Lösung war zu kompliziert.**

---

## 🎯 Die neue, schlankere Lösung

### 1. Tier-Support in `tutor/tools.py` (nur 3 neue Funktionen)

```python
# In tools.py hinzufügen:

def get_tier_1_vocab() -> str:
    """Nur Tier-1-Vokabeln (Bootcamp-Set). NUR wenn phase='bootcamp'."""
    with _lock:
        entries = _load_raw()
    tier1 = [e for e in entries if e.get('tier') == 1]
    confirmed = [e for e in tier1 if e.get('confirmed')]
    testing = [e for e in tier1 if not e.get('confirmed')]
    
    result = [f"Tier 1 ({len(confirmed)}/{len(tier1)} confirmed):"]
    for e in tier1:
        status = "✓" if e.get('confirmed') else "○"
        result.append(f"  {status} {e['word']}")
    return "\n".join(result)


def get_tier1_mastery() -> float:
    """Prozentsatz von Tier-1-Vokabeln die confirmed sind."""
    with _lock:
        entries = _load_raw()
    tier1 = [e for e in entries if e.get('tier') == 1]
    if not tier1:
        return 0.0
    confirmed = sum(1 for e in tier1 if e.get('confirmed'))
    return confirmed / len(tier1)


def is_bootcamp_complete() -> bool:
    """Ist der Lerner ready zum Spawn? (≥75% Tier 1 confirmed)"""
    return get_tier1_mastery() >= 0.75
```

**Das ist alles!** Keine komplexe neue Datei-Struktur.

### 2. Vokabelliste: `tutor/data/vocab_tier1_de.json`

Ist bereits erstellt (siehe outputs). Just copy & paste in `tutor/data/`.

```json
[
  {
    "word": "ich",
    "tier": 1,
    "priority": "critical",
    "category": "pronoun",
    "correct_use": 0,
    "confirmed": false
  },
  // ... 74 more
]
```

### 3. Assessment als Session-Opener (in `tutor/session.py`)

**NICHT** als separates Bootcamp-System. Sondern: **wenn Lerner NEU ist, speichern wir ein Flag.**

```python
# In tutor/session.py, in der activate() Funktion:

def activate():
    global _active, _history, _privacy, _session_lang
    prof, pname, provider, model = _resolve()
    lang = config.setting("lang", "zh")
    
    # NEU: Ist der Lerner neu? Wenn ja → Assessment-Flag setzen
    from . import memory
    notes = memory._load_notes(lang)
    if not notes.get("facts") and not notes.get("topics"):
        # Erste Session! → Memory ein "phase: bootcamp" Fact setzen
        notes["facts"].append("bootcamp_phase")
        memory._save_notes(notes, lang)
    
    # Rest wie vorher...
    with _lock:
        _active       = True
        _session_lang = lang
        _history      = deque(maxlen=100)
        _privacy      = notice
```

### 4. KI-Prompt-Anpassung (in `tutor/langs.py` für Deutsch)

**WENN** der Lerner im Bootcamp ist, änder dich den Prompt:

```python
# In tutor/langs.py, z.B. in der Deutsch-Sektion:

"de": {
    "name": "Deutsch",
    "persona_name": "...deine Persona...",
    # ...bestehender Code...
    "system_prompt": _BOOTCAMP_PROMPT if is_in_bootcamp(lang) else _CONVERSATIONAL_PROMPT,
    # Existing vocab_hint bleibt wie es ist
}

# Helper:
def is_in_bootcamp(lang: str) -> bool:
    from . import memory, tools
    notes = memory._load_notes(lang)
    # Noch im Bootcamp wenn <75% Tier 1 confirmed
    return tools.get_tier1_mastery() < 0.75 and "bootcamp_phase" in str(notes.get("facts"))

_BOOTCAMP_PROMPT = """
(Wie dein bestehendes prompt, aber mit Bootcamp-Regeln)
- Ein Wort pro Zug max
- Immer show_thought
- Langsam sprechen
- Viel Gestik (express)
Du siehst die verfügbaren Wörter in der Vokabel-Injektion unten.
"""

_CONVERSATIONAL_PROMPT = """
(Dein bestehendes prompt, für normale Konversation)
"""
```

### 5. Auto-Spawn (nach jeder Session)

**Nutze die bestehende `memory.remember()` Funktion um zu tracken:**

```python
# In tutor/session.py, am Ende von chat_turn():

# Existierender Code führt memory.remember() auf...
threading.Thread(
    target=memory.remember,
    args=(user_text, full, lang, pname, model), 
    daemon=True).start()

# NEU: Nach Session Check ob Spawn passieren soll
from . import tools
if tools.is_bootcamp_complete():
    notes = memory._load_notes(lang)
    if "bootcamp_phase" in str(notes.get("facts")):
        # Entferne bootcamp_phase flag → Prompt wird conversational
        notes["facts"] = [f for f in notes["facts"] if f != "bootcamp_phase"]
        notes["facts"].append("🎉 Tutor spawned!")  # Victory marker
        memory._save_notes(notes, lang)
        # Nächste Session wird automatisch conversational (is_in_bootcamp() = False)
```

---

## 📊 Zusammenfassung: Was ändert sich?

| Teil | Alte Lösung | Neue Lösung |
|------|-------------|------------|
| Assessment | Separate UI + LEARNER_PROFILE JSON | Flag in Memory (bootcamp_phase) |
| Tier-Support | Komplexe tutor_bootcamp_assessment.py | 3 Funktionen in tools.py |
| Spawn-Check | Separate SpawnManager Klasse | is_bootcamp_complete() + memory flag |
| Prompt-Switch | Unterschiedliche KI-Prompts je Phase | is_in_bootcamp(lang) in langs.py |
| Vokabelliste | vocab_tier1_de.json + neue Struktur | vocab_tier1_de.json (copy & paste) |

**Resultat:** Statt 5 neuer Python-Files + Dokumentation = nur **Änderungen in 3 bestehenden Files** (tools.py, session.py, langs.py) + 1 Vokabel-JSON.

---

## 🚀 Konkrete Änderungen (Copy-Paste)

### A. `tutor/tools.py` — Am Ende hinzufügen:

```python
# ── Bootcamp-Support: Tier-1-Vokabeln + Mastery ─────────────────────────────

def get_tier_1_vocab() -> str:
    """Gibt nur Tier-1-Vokabeln zurück (das Bootcamp-Vokabular-Set)."""
    with _lock:
        entries = _load_raw()
    
    tier1 = [e for e in entries if e.get('tier') == 1]
    if not tier1:
        return "[Tier 1 nicht konfiguriert]"
    
    confirmed = [e for e in tier1 if e.get('confirmed')]
    testing = [e for e in tier1 if not e.get('confirmed')]
    
    result = [f"Tier 1 Bootcamp ({len(confirmed)}/{len(tier1)} confirmed)"]
    
    # Gruppiert nach Priority
    for priority in ['critical', 'high', 'medium', 'low']:
        words = [e for e in tier1 if e.get('priority') == priority]
        if words:
            result.append(f"\n[{priority.upper()}]")
            for e in words:
                status = "✓" if e.get('confirmed') else "○"
                result.append(f"  {status} {e['word']}")
    
    return "\n".join(result)


def get_tier1_mastery() -> float:
    """Rückgabe: 0.0–1.0, Anteil der confirmed Tier-1-Vokabeln."""
    with _lock:
        entries = _load_raw()
    
    tier1 = [e for e in entries if e.get('tier') == 1]
    if not tier1:
        return 0.0
    
    confirmed = sum(1 for e in tier1 if e.get('confirmed'))
    return confirmed / len(tier1)


def is_bootcamp_complete() -> bool:
    """True wenn Tier 1 zu ≥75% mastered (ready für Spawn)."""
    return get_tier1_mastery() >= 0.75


def get_bootcamp_status() -> str:
    """Kurze Status-Meldung für UI/Log."""
    mastery = get_tier1_mastery()
    pct = int(mastery * 100)
    
    if mastery >= 0.75:
        return f"🎉 Bootcamp complete! {pct}% Tier 1 mastered — Tutor spawns next session!"
    else:
        needed = int((0.75 - mastery) * 75)
        return f"Bootcamp: {pct}% Tier 1 mastered. {needed} words left until spawn."
```

### B. `tutor/session.py` — In `activate()` hinzufügen:

```python
def activate():
    global _active, _history, _privacy, _session_lang
    prof, pname, provider, model = _resolve()
    lang = config.setting("lang", "zh")
    
    # ── Bootcamp First-Time Setup ──────────────────────────────────────
    # Wenn Lerner NEU ist (kein Memory), markier bootcamp_phase
    from . import memory
    notes = memory._load_notes(lang)
    if not notes.get("facts") and not notes.get("topics"):
        # Erste Session: starten wir im Bootcamp
        notes["facts"] = ["bootcamp_phase"]
        notes["topics"] = []
        memory._save_notes(notes, lang)
        print(f"[Tutor] {lang}: Bootcamp-Phase gestartet (Tier 1)")
    
    # ── Check nach Session: Ist Bootcamp vorbei? ──────────────────────
    # (wird in chat_turn() gemacht, nach memory.remember())
    
    # Rest des bestehenden activate() Code...
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
    
    with _lock:
        _active       = True
        _session_lang = lang
        _history      = deque(maxlen=100)
        _privacy      = notice
        # ... rest
```

### C. In `chat_turn()`, am END nach memory.remember():

```python
def chat_turn(user_text: str | None, nudge: bool = False, focus: bool | None = None,
              sound: bool | None = None) -> str:
    # ... existing code ...
    
    # Am Ende, nach memory.remember():
    threading.Thread(
        target=memory.remember,
        args=(user_text, full, lang, pname, model), daemon=True).start()
    
    # ── NEU: Auto-Spawn Check ──────────────────────────────────────────
    # Wenn Bootcamp vorbei, entfern bootcamp_phase flag
    if user_text is not None:  # Nur auf echte Turns, nicht Nudges
        from . import tools
        if tools.is_bootcamp_complete():
            notes = memory._load_notes(lang)
            if "bootcamp_phase" in str(notes.get("facts")):
                # Bootcamp beendet!
                notes["facts"] = [f for f in notes["facts"] 
                                if f != "bootcamp_phase"]
                notes["facts"].append("tutor_spawned")
                memory._save_notes(notes, lang)
                
                print(f"[Tutor] {lang}: SPAWN! Bootcamp complete, conversational mode.")
                try:
                    import state
                    state.push_log(f"🎉 Tutor spawned for {lang}! Bootcamp complete.")
                except Exception:
                    pass
```

### D. `tutor/langs.py` — Helper + Prompt-Switch:

```python
# Am Anfang der Datei:

def _is_in_bootcamp(lang: str) -> bool:
    """Check: läuft noch Bootcamp für diese Sprache?"""
    try:
        from . import memory, tools
        # Bootcamp wenn: bootcamp_phase flag gesetzt UND <75% Tier 1
        notes = memory._load_notes(lang)
        facts = notes.get("facts", [])
        mastery = tools.get_tier1_mastery()
        return "bootcamp_phase" in facts and mastery < 0.75
    except Exception:
        return False  # Bei Fehler: normal mode


_BOOTCAMP_SYSTEM_ZH = """你是一个中文教学助手，专为初学者设计。

【重要规则】
- 一次只讲一个词或短短的词组（最多2-3个字）
- 每个词都用 show_thought() 展示（图片 + 文字）
- 说话很慢，重复3-5次
- 多用 express() 做手势（wave, nod, smile, 等等）
- 学生会跟你重复，你鼓励她
- 如果听不懂，就用图片再次解释

【你在学的词汇】请看下面列出的 Tier 1 词汇，只用这些词。
"""

_CONVERSATIONAL_SYSTEM_ZH = """你是一个友好的中文聊天伙伴，住在这个房间里。

我们已经聊过很多次了，你大概记得一些关于她的事。
使用下面列出的已掌握词汇（80%的时间），加上在学的词汇（20%的时间）。
自然地交谈，但保持简单句子。
"""

# Dann in PROFILES["zh"]:
"de": {
    # ... bestehender Code ...
    "system_prompt": (_BOOTCAMP_SYSTEM_ZH if _is_in_bootcamp("zh") else _CONVERSATIONAL_SYSTEM_ZH),
    # ... rest ...
},

# Für Deutsch:
_BOOTCAMP_SYSTEM_DE = """Du bist ein Deutschlehrer für absolute Anfänger.

【Wichtig】
- Ein Wort pro Zug (max 2-3)
- show_thought() für jeden
- Langsam sprechen (0.7x speed)
- Viel Gestik (express)
- Der Lerner wiederholt
- Bei Verständnis: increment_correct_use()

Du siehst die verfügbaren Wörter unten (Tier 1).
"""

_CONVERSATIONAL_SYSTEM_DE = """Du bist ein freundlicher Deutschsprachpartner.

Wir haben schon viel geredet, ich merke mir ungefähr was über dich.
Normale, einfache Konversation.
Nutze bestätigte Wörter (80%), neue Wörter (20%).
"""

# (Die "de" Einträge existieren noch nicht — diese sind SKIZZEN gemäß dem Code)
```

---

## ✅ Integration Checklist

- [ ] `tutor/data/vocab_tier1_de.json` kopieren (aus outputs)
- [ ] In `tutor/tools.py`: die 4 neuen Funktionen am Ende hinzufügen
- [ ] In `tutor/session.py`: `activate()` + `chat_turn()` updaten
- [ ] In `tutor/langs.py`: `_is_in_bootcamp()` + Prompts hinzufügen
- [ ] Test: `python -c "from tutor.tools import get_tier1_mastery; print(get_tier1_mastery())"`
- [ ] Testen: neuer Lerner startet → sieht "bootcamp_phase" im Memory

---

## 🎯 Was passiert jetzt?

1. **Lerner startet App (neu)**
   - `activate()` setzt `bootcamp_phase` flag
   - `is_in_bootcamp("de")` → True
   - System-Prompt wird zu `_BOOTCAMP_SYSTEM_DE`
   - KI kriegt `get_tier_1_vocab()` in den Prompt

2. **Bootcamp Sessionen (2-4 Wochen)**
   - Ein Wort pro Zug
   - show_thought + repeat
   - `increment_correct_use()` wird aufgerufen
   - Nach ~15 Sessions: ~56 Wörter confirmed (75% von 75)

3. **Spawn Check (nach jeder Session)**
   - `is_bootcamp_complete()` → True
   - Flag `bootcamp_phase` entfernt
   - `tutor_spawned` flag gesetzt
   - Nächste Session: `is_in_bootcamp()` → False
   - System-Prompt → `_CONVERSATIONAL_SYSTEM_DE`

4. **Normal Mode ab jetzt**
   - Echte Konversation
   - Tier 2 Wörter organisch dazulernen

---

## 💡 Warum ist das besser als die alte Lösung?

1. **Nutzt bestehende Infrastruktur** (Memory, History, Prompts)
2. **Keine neuen Dateien/Strukturen** außer vocab_tier1_de.json
3. **Minimal invasiv** — nur 3 kleine Funktionen + 2 Prompt-Varianten
4. **Respektiert die Architektur** — keine separate Assessment-UI, keine neue Session-Logik
5. **Einfacher zu testen** — nur boolean + Vokabeln-Zähler

---

## 📝 Nächste Schritte

1. Lese diese Dokumentation durch
2. Copy vocab_tier1_de.json
3. Merge die 3 Code-Änderungen
4. Test
5. Deploy!
