# core/memory.py
#
# KI-Memory-System v2 für ZENTRALE. Zwei Speicher-Schichten:
#
#   STM (Kurzzeitgedächtnis, data/ai_stm.json)
#     - Pro Session, volatil.
#     - Liste aller Turns (User + AI) mit Timestamp, Tags, Rolle.
#     - Plus rollender Summary-Text der gesamten Session (beide Seiten).
#     - Wird durch Konsolidierung (Phase E) ins LTM überführt und geleert.
#
#   LTM (Langzeitgedächtnis, data/ai_ltm.json)
#     - Persistent, überlebt Neustarts.
#     - Strukturierte Einträge mit Embedding-Slot für semantische Suche
#       (Phase B befüllt die Embeddings, Phase C nutzt sie für Retrieval).
#     - Jeder Eintrag weiß, ob User oder AI ihn produziert hat (who_said).
#       Das ist der wichtigste Hebel gegen Selbst-Widersprüche der AI.
#
# Detail-Plan & Phasen: memory/ki_memory_plan.md
#
# Public API (alles unten ausführlich kommentiert):
#   LTM:  load(), save(...), forget(id), format_for_prompt()
#   STM:  stm_load(), stm_append(...), stm_get_summary(),
#         stm_set_summary(...), stm_clear()
#
# Migration: alte data/ai_memory.json (v1, flach) wird beim ersten
# Aufruf automatisch auf das neue Schema gemappt und nach
# data/ai_memory.v1.json.bak gesichert. Idempotent - wenn v2 schon
# existiert, passiert nichts.

import json
import os
import shutil
from datetime import datetime
from threading import Lock

import embeddings  # Phase B: Vektoren für semantische Suche generieren

# ── Dateipfade ─────────────────────────────────────────────────────────
# Alle Memory-Files leben unter ../data/ (relativ zu core/).
_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
_LTM_FILE = os.path.join(_DATA_DIR, 'ai_ltm.json')
_STM_FILE = os.path.join(_DATA_DIR, 'ai_stm.json')
_V1_FILE  = os.path.join(_DATA_DIR, 'ai_memory.json')        # alt (v1)
_V1_BAK   = os.path.join(_DATA_DIR, 'ai_memory.v1.json.bak')  # Backup nach Migration

# ── Schema-Konstanten ──────────────────────────────────────────────────
# schema_version steht in den JSON-Files mit drin, damit zukünftige
# Migrationen den Stand erkennen können.
LTM_SCHEMA_VERSION = 2
STM_SCHEMA_VERSION = 1

# Erlaubte Enum-Werte. Werden bei Save validiert; unerlaubte Werte
# fallen defensiv auf den Default zurück (kein Crash bei buggy AI-Calls).
#
# Typen-Bedeutungen:
#   fact:        objektive Information über User, System, Welt
#   preference:  wie der User Dinge bevorzugt (Stil, Reaktionsart)
#   commitment:  was die AI versprochen hat / TODOs
#   technical:   Konfigurationen, Code-Details, System-Internals
#   capability:  was die AI nachweislich kann (gelernt im Gespräch)
#   limit:       was die AI nicht kann (User-Korrektur, vermeidet
#                erneutes falsches Versprechen am gleichen Thema)
LTM_TYPES  = ['fact', 'preference', 'commitment', 'technical', 'capability', 'limit']
WHO_VALUES = ['user', 'ai']
STM_ROLES  = ['user', 'ai']

# Mapping v1-Type → v2-Type für die Migration. Begründung im Plan-Doc:
#   - 'summary' (v1) war eine zusammenfassende Aussage → 'fact' (v2).
#   - 'todo' (v1) war ein offener Punkt → 'commitment' (v2).
_V1_TYPE_MAP = {
    'fact':      'fact',
    'summary':   'fact',
    'todo':      'commitment',
    'technical': 'technical',
}

# ── Locks für Thread-Safety ────────────────────────────────────────────
# Flask-Thread (Web-Requests) und Event-Loop (Auto-Save in Phase D)
# könnten gleichzeitig schreiben. LTM und STM kriegen je einen eigenen
# Lock - sie sind unabhängige Files, kein Grund sie zu serialisieren.
_ltm_lock = Lock()
_stm_lock = Lock()


# ── Atomic Write Helper ────────────────────────────────────────────────
def _write_atomic(path: str, data: dict):
    """
    Schreibt JSON atomar: erst in .tmp, dann os.replace().

    So bleibt das File entweder komplett alt oder komplett neu -
    kein halbgeschriebener Zustand, falls der Prozess mitten im
    Schreiben crasht. Wichtig weil das STM in Phase D potenziell
    sehr oft (nach jedem Turn) geschrieben wird.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, path)


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  LTM  -  Langzeitgedächtnis                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝

def _migrate_v1_if_needed():
    """
    Wenn data/ai_memory.json (v1) existiert UND data/ai_ltm.json (v2)
    NICHT existiert: einmalige Migration. Sonst no-op.

    Migration mapped v1-Einträge auf v2-Schema:
      - id              → übernommen
      - content         → übernommen
      - type            → über _V1_TYPE_MAP gemappt
      - saved_at        → created_at (umbenannt)
      - who_said        → 'user' (historische Konvention: User hat's gesagt,
                          AI hat's via save_memory-Tool persistiert)
      - tags            → [] (Phase B/D befüllt das ggf. nachträglich)
      - embedding       → None (Phase B backfillt)

    Das v1-File wird nach Migration nach ai_memory.v1.json.bak
    verschoben, NICHT gelöscht - paranoid ist hier gut.
    """
    if os.path.exists(_LTM_FILE):
        return  # v2 schon da → bereits migriert (oder neu angelegt)
    if not os.path.exists(_V1_FILE):
        return  # gar keine alte Memory da → nichts zu tun

    with open(_V1_FILE, 'r', encoding='utf-8') as f:
        v1_entries = json.load(f)

    v2_entries = []
    next_id = 0
    for e in v1_entries:
        v1_type = e.get('type', 'fact')
        v2_type = _V1_TYPE_MAP.get(v1_type, 'fact')
        v2_entries.append({
            'id':         next_id,
            'content':    e.get('content', ''),
            'embedding':  None,
            'type':       v2_type,
            'who_said':   'user',
            'created_at': e.get('saved_at') or datetime.now().isoformat(),
            'tags':       [],
        })
        next_id += 1

    _write_atomic(_LTM_FILE, {
        'schema_version': LTM_SCHEMA_VERSION,
        'next_id':        next_id,
        'entries':        v2_entries,
    })

    # v1 nicht löschen, sondern als Backup behalten. Falls die Migration
    # subtile Fehler produziert hat, kann man manuell vergleichen.
    shutil.move(_V1_FILE, _V1_BAK)


def _load_ltm_raw() -> dict:
    """
    Lädt das LTM-File ohne Lock. Nur intern aufrufen (Caller muss den
    Lock halten). Initialisiert eine leere Struktur, wenn das File noch
    nicht da ist.

    Triggert die v1→v2-Migration einmalig, falls nötig.
    """
    _migrate_v1_if_needed()
    if not os.path.exists(_LTM_FILE):
        return {
            'schema_version': LTM_SCHEMA_VERSION,
            'next_id':        0,
            'entries':        [],
        }
    with open(_LTM_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # Defensive: falls jemand das File manuell editiert hat und Felder
    # fehlen, hier nochmal Defaults setzen statt KeyError.
    data.setdefault('schema_version', LTM_SCHEMA_VERSION)
    data.setdefault('entries', [])
    data.setdefault('next_id', len(data['entries']))
    return data


def _write_ltm_raw(data: dict):
    """Schreibt das LTM-File atomar. Lock muss schon gehalten werden."""
    _write_atomic(_LTM_FILE, data)


def load() -> list:
    """
    Gibt die LTM-Einträge als Liste zurück.

    Backward-compatible Public API: vor v2 war die Memory auf Disk
    direkt eine flache Liste, und der Caller (app.py /api/memory,
    ai.py format_for_prompt) erwartet das weiter.

    Wer Metadaten (schema_version, next_id) braucht, soll _load_ltm_raw
    benutzen - aber das ist intern.
    """
    with _ltm_lock:
        return _load_ltm_raw()['entries']


def save(content: str,
         type: str = 'fact',
         who_said: str = 'user',
         tags: list = None) -> str:
    """
    Speichert einen neuen LTM-Eintrag.

    Wird aktuell vom save_memory-Tool in ai.py aufgerufen (mit nur
    content + type). In Phase D übernimmt Auto-Save den Großteil, der
    Tool-Pfad bleibt aber für explizite Saves erhalten ("merk dir das").
    In Phase F kommen who_said und tags als Tool-Argumente dazu, ältere
    Caller funktionieren wegen der Defaults weiterhin.

    Rückgabe: String, den die KI als Tool-Result sieht.
    """
    # Defensive Validierung: ungültige Werte → Default, kein Crash.
    if type not in LTM_TYPES:
        type = 'fact'
    if who_said not in WHO_VALUES:
        who_said = 'user'
    if tags is None:
        tags = []

    # Embedding wird VOR dem Lock generiert. Ollama-Embed-Call dauert
    # ~50–200 ms je nach Text-Länge - wir wollen den Lock nicht so lange
    # halten und andere Threads (Auto-Save in Phase D) blockieren. Wenn
    # Ollama down ist liefert embed_document() None, der Eintrag wird
    # trotzdem gespeichert (kann später per backfill_missing_embeddings
    # nachgereicht werden).
    #
    # WICHTIG: embed_document, nicht embed_query. nomic-embed-text legt
    # Dokumente und Queries in unterschiedlichen Vektorraum-Regionen ab.
    vec = embeddings.embed_document(content)

    with _ltm_lock:
        data = _load_ltm_raw()
        new_id = data['next_id']
        data['entries'].append({
            'id':         new_id,
            'content':    content,
            'embedding':  vec,
            'type':       type,
            'who_said':   who_said,
            'created_at': datetime.now().isoformat(),
            'tags':       tags,
        })
        data['next_id'] = new_id + 1
        _write_ltm_raw(data)

    return f"✓ Gespeichert [{type}/{who_said}]: {content}"


def backfill_missing_embeddings() -> int:
    """
    Generiert Embeddings für alle LTM-Einträge, die noch keines haben
    (embedding == None). Wird genutzt für v1→v2-migrierte Einträge und
    für Einträge, die gespeichert wurden während Ollama gerade down war.

    Returns: Anzahl der nachgefüllten Einträge.

    Läuft sequenziell. Bei sehr großem LTM kann das einen Moment dauern -
    pro Eintrag ein HTTP-Call an Ollama. Aber: 100 Einträge × 100 ms =
    10 Sekunden, das ist OK für eine einmalige Maintenance-Operation.
    """
    # Erst außerhalb des Locks alle Embeddings generieren - jeder
    # einzelne Embed-Call dauert ~50–200 ms, und wir wollen den Lock
    # nicht für die ganze Dauer halten. Wir lesen den aktuellen Stand
    # einmal, generieren die fehlenden Vektoren, und schreiben dann
    # alles in einem atomaren Block zurück.
    with _ltm_lock:
        data = _load_ltm_raw()
        missing = [e for e in data['entries'] if e.get('embedding') is None and e.get('content')]

    if not missing:
        return 0

    # Embeddings außerhalb des Locks generieren - alles Document-Seite,
    # weil die Einträge ja im LTM liegen (keine Queries).
    generated = {}  # id → vector
    for e in missing:
        vec = embeddings.embed_document(e['content'])
        if vec is not None:
            generated[e['id']] = vec

    if not generated:
        return 0  # Ollama nicht erreichbar - nichts geändert

    # Jetzt mit Lock zurückschreiben. Frischer Reload, falls ein anderer
    # Thread in der Zwischenzeit gespeichert hat - dann wachsen die IDs
    # einfach weiter, unsere Updates greifen trotzdem auf die richtigen
    # Einträge (per ID).
    with _ltm_lock:
        data = _load_ltm_raw()
        for e in data['entries']:
            if e['id'] in generated:
                e['embedding'] = generated[e['id']]
        _write_ltm_raw(data)

    return len(generated)


def forget(entry_id: int) -> str:
    """
    Löscht einen Eintrag nach seiner ID.

    Wichtige Änderung zu v1: IDs werden NICHT mehr neu vergeben nach
    dem Löschen. Lücken sind OK und auch beabsichtigt - sonst könnten
    bestehende AI-Referenzen ("siehe Memory-Eintrag 7") nach einem
    Delete plötzlich auf eine andere Aussage zeigen.
    """
    with _ltm_lock:
        data = _load_ltm_raw()
        match = [e for e in data['entries'] if e['id'] == entry_id]
        if not match:
            return f"Kein Eintrag mit ID {entry_id}"
        removed = match[0]
        data['entries'] = [e for e in data['entries'] if e['id'] != entry_id]
        _write_ltm_raw(data)
    return f"✓ Gelöscht: {removed['content']}"


def format_for_prompt(query: str = None, k: int = 5) -> str:
    """
    Formatiert relevante LTM-Einträge als Text für den System-Prompt.

    Modi:
      - query=None  → backward-compatible: dumpt alle Einträge. Sinnvoll
                      für Fälle wo es noch keinen User-Query gibt (z.B.
                      Tutor-Initialisierung) oder fürs Debugging.
      - query=str   → semantische Top-K-Suche via Embedding-Cosinus.
                      Nur die k relevantesten Einträge landen im Prompt.

    Phase C umgeleitet: vorher Phase-A-Verhalten (dump everything) -
    skaliert nur bis ~50 Einträge bevor das Context-Window leidet.

    Fallback-Verhalten bei query!=None:
      - Wenn Embedding-Call fehlschlägt (Ollama down): keine LTM-Injection
        in den Prompt (lieber leer als die ganze Memory dumpen, was bei
        großem LTM den Context killt).
      - Wenn KEINER der Einträge ein Embedding hat (z.B. direkt nach
        Migration vor Backfill): alle Einträge nehmen, sicher ist sicher.

    Format jeder Zeile: [id][type][who_said] content
    """
    entries = load()
    if not entries:
        return ""

    relevant = _select_relevant_entries(entries, query, k)
    if not relevant:
        return ""

    lines = ["## Deine persistente Memory (über Sitzungen hinweg gespeichert):"]
    for e in relevant:
        who = e.get('who_said', 'user')
        lines.append(f"  [{e['id']}][{e['type']}][{who}] {e['content']}")
    return "\n".join(lines)


def _select_relevant_entries(entries: list, query: str, k: int) -> list:
    """
    Wählt die Einträge aus, die im Prompt landen sollen.

    Ausgegliedert aus format_for_prompt, weil die Logik mehrere
    Sonderfälle hat und sich in Phase E (Konsolidierung) wahrscheinlich
    nochmal erweitert (Recency-Bias, Type-Filter etc.).
    """
    # Mode 1: kein Query → alle Einträge (backward compat)
    if not query:
        return entries

    # Mode 2: Query da → semantisches Top-K. embed_query, NICHT
    # embed_document - asymmetrische Suche, sonst matchen wir den
    # Dokumenten-Vektorraum mit einem Dokumenten-Vektor und kriegen
    # lexikalisches Geräusch (Eigennamen-Matches statt Thema).
    qvec = embeddings.embed_query(query)
    if qvec is None:
        # Embedding-Service down. Lieber gar keine LTM-Injection als
        # alle dumpen - bei großem LTM würde das den Context sprengen.
        return []

    # Wir geben k aus den Einträgen mit Embedding zurück, sortiert nach
    # Cosinus-Ähnlichkeit. Einträge ohne Embedding fallen raus.
    scored = embeddings.top_k(qvec, entries, k=k)
    if scored:
        return [e for e, _score in scored]

    # Kein einziger Eintrag hatte ein Embedding → vermutlich noch nicht
    # gebackfilled (z.B. direkt nach v1-Migration). Dann lieber alle
    # zeigen, damit die KI überhaupt was hat.
    return entries


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  STM  -  Kurzzeitgedächtnis                                          ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Datenmodell:
#   { schema_version, list: [{ts, role, text, tags}, ...], summary: str }
#
# Phase A liefert nur die CRUD-Funktionen. Befüllt wird das Ding in
# Phase D (Auto-Save), geleert wird's in Phase E (Konsolidierung).

def _load_stm_raw() -> dict:
    """
    Lädt das STM-File ohne Lock. Nur intern aufrufen. Initialisiert
    eine leere Struktur, wenn das File noch nicht da ist.
    """
    if not os.path.exists(_STM_FILE):
        return {
            'schema_version': STM_SCHEMA_VERSION,
            'list':           [],
            'summary':        '',
        }
    with open(_STM_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault('schema_version', STM_SCHEMA_VERSION)
    data.setdefault('list', [])
    data.setdefault('summary', '')
    return data


def _write_stm_raw(data: dict):
    """Schreibt das STM-File atomar. Lock muss schon gehalten werden."""
    _write_atomic(_STM_FILE, data)


def stm_load() -> dict:
    """
    Gibt das gesamte STM-Objekt zurück: {'list': [...], 'summary': str}.

    Caller, die nur eines brauchen, sollten lieber stm_get_summary() bzw.
    die Liste über stm_load()['list'] holen - der Lock wird hier einmal
    geholt und wieder freigegeben.
    """
    with _stm_lock:
        return _load_stm_raw()


def stm_append(role: str, text: str, tags: list = None):
    """
    Hängt einen Turn ans STM-Listen-Ende. Wird in Phase D vom Auto-Save
    aufgerufen - sowohl für User-Messages als auch für AI-Responses, das
    ist der entscheidende Punkt für Konsistenz-Checks.

    role muss 'user' oder 'ai' sein - alles andere wird auf 'user'
    zurückgemappt (defensiv).
    """
    if role not in STM_ROLES:
        role = 'user'
    if tags is None:
        tags = []
    with _stm_lock:
        data = _load_stm_raw()
        data['list'].append({
            'ts':   datetime.now().isoformat(),
            'role': role,
            'text': text,
            'tags': tags,
        })
        _write_stm_raw(data)


def stm_get_summary() -> str:
    """Gibt den aktuellen rollenden Session-Summary zurück. Leer wenn keiner."""
    with _stm_lock:
        return _load_stm_raw().get('summary', '')


def stm_set_summary(summary: str):
    """
    Überschreibt den STM-Summary komplett. Wird in Phase D vom
    Auto-Save gepflegt - nach jedem Turn wird der Summary durch einen
    kleinen LLM-Call neu berechnet (oder inkrementell verlängert).
    """
    with _stm_lock:
        data = _load_stm_raw()
        data['summary'] = summary
        _write_stm_raw(data)


def stm_clear():
    """
    Leert das STM komplett: Liste UND Summary. Wird in Phase E vom
    Konsolidator aufgerufen, nachdem alles wertvolle ins LTM promotet
    wurde. Auch nutzbar als /clear-Variante im Chat.
    """
    with _stm_lock:
        _write_stm_raw({
            'schema_version': STM_SCHEMA_VERSION,
            'list':           [],
            'summary':        '',
        })
