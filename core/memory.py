# core/memory.py
#
# Persistente Memory für die ZENTRALE-KI.
#
# Speichert Fakten, Zusammenfassungen, TODOs und technische Notizen
# in data/ai_memory.json auf Disk – überlebt Neustarts.
#
# Die KI schreibt selbst in die Memory über das save_memory-Tool,
# wenn sie etwas für wichtig hält oder der User es explizit sagt.
# Der User kann Einträge per /forget löschen.
#
# Beim Start jedes Chats wird die gesamte Memory als Teil des
# System-Prompts injiziert – die KI "erinnert" sich also automatisch.

import json
import os
from datetime import datetime
from threading import Lock

_MEMORY_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'ai_memory.json')
_lock = Lock()  # Thread-safe: Flask-Thread und Event-Loop teilen diesen State nicht,
                # aber sicher ist sicher falls später mal mehrere Threads schreiben.

# Erlaubte Typen für Memory-Einträge
TYPES = ['fact', 'summary', 'todo', 'technical']


def _load_raw() -> list:
    """Lädt Memory-Einträge direkt ohne Lock (nur intern nutzen)."""
    if not os.path.exists(_MEMORY_FILE):
        return []
    with open(_MEMORY_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _write_raw(entries: list):
    """Schreibt Einträge auf Disk (nur intern, Lock muss bereits gehalten werden)."""
    os.makedirs(os.path.dirname(_MEMORY_FILE), exist_ok=True)
    with open(_MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def load() -> list:
    """Gibt alle Memory-Einträge zurück (thread-safe)."""
    with _lock:
        return _load_raw()


def save(content: str, type: str = 'fact') -> str:
    """
    Speichert einen neuen Memory-Eintrag.
    Wird von der KI über das save_memory-Tool aufgerufen.
    Gibt eine Bestätigungsstring zurück (den die KI sieht).
    """
    type = type if type in TYPES else 'fact'
    with _lock:
        entries = _load_raw()
        entries.append({
            'id':       len(entries),   # fortlaufende ID für /forget
            'type':     type,
            'content':  content,
            'saved_at': datetime.now().isoformat(),
        })
        _write_raw(entries)
    return f"✓ Gespeichert [{type}]: {content}"


def forget(index: int) -> str:
    """
    Löscht einen Eintrag nach seiner ID.
    Wird über /forget N im Chat aufgerufen.
    IDs werden nach dem Löschen neu vergeben (immer 0-basiert).
    """
    with _lock:
        entries = _load_raw()
        match = [e for e in entries if e['id'] == index]
        if not match:
            return f"Kein Eintrag mit ID {index}"
        removed = match[0]
        entries = [e for e in entries if e['id'] != index]
        # IDs neu vergeben damit sie lückenlos bleiben
        for i, e in enumerate(entries):
            e['id'] = i
        _write_raw(entries)
    return f"✓ Gelöscht: {removed['content']}"


def format_for_prompt() -> str:
    """
    Formatiert alle Memory-Einträge als Text für den System-Prompt.
    Wird vor jedem AI-Call aufgerufen und an den System-Prompt angehängt.
    Leerer String wenn keine Einträge vorhanden.
    """
    entries = load()
    if not entries:
        return ""
    lines = ["## Deine persistente Memory (über Sitzungen hinweg gespeichert):"]
    for e in entries:
        lines.append(f"  [{e['id']}][{e['type']}] {e['content']}")
    return "\n".join(lines)
