# core/consolidation.py
#
# STM → LTM Konsolidierung (Phase E des Memory-Plans).
#
# Was hier passiert:
#   1. Wir nehmen alle rohen Turns aus dem STM (User + AI, role-getrennt).
#   2. Ein LLM-Call extrahiert daraus geerdete Fakten - nur was WIRKLICH
#      gesagt wurde, keine Interpretationen, keine Schlüsse.
#   3. Jeder extrahierte Fakt landet via memory.save() im LTM (mit
#      Embedding, automatischem Timestamp, who_said).
#   4. STM wird komplett geleert (Liste + Summary).
#
# Trigger:
#   - /sleep-Command im Chat (manueller Trigger durch User)
#   - Inaktivität > X Min (lazy-check beim nächsten User-Turn)
#
# Warum diese Architektur:
#   - GROUNDED: Der Konsolidator sieht die ROHEN Turns, nicht den
#     bereits-fabulierten STM-Summary. Damit kann kein "ich habe X
#     gelöscht"-Halluzinations-Drama der KI ins LTM rüber-rutschen.
#     Der Summary war hilfreich für In-Session-Kontext, aber für die
#     Persistenz vertrauen wir nur dem was wörtlich gesagt wurde.
#   - LLM-EXTRAKTION statt naivem Save-All: nicht jeder Turn ist
#     LTM-würdig (Smalltalk, Tool-Diskussionen, Hin-und-Her). Das LLM
#     ist ein guter Filter mit klaren Regeln.
#   - LEEREN nach Konsolidierung: STM ist Session-Speicher. Nach dem
#     Konsolidieren startet die nächste Session bewusst leer - der
#     wichtige Kram lebt im LTM weiter, der Rest verfällt.

import os
import json as _json
from datetime import datetime, date
from threading import Lock

import net      # HTTP-Wrapper mit Logging
import memory   # LTM/STM CRUD (Legacy, wird in Phase G durch graph ersetzt)
import graph    # Konzept-Graph (Phase G)

# ── Konfiguration ──────────────────────────────────────────────────────
OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:14b")

# Inaktivitäts-Schwelle in Sekunden. Nach so langer Stille beim nächsten
# Turn lazy-getriggertes Konsolidieren. 30 Minuten = 1800 Sekunden.
INACTIVITY_THRESHOLD_SEC = 30 * 60

# Tracking: letzter User-Turn (für Lazy-Inaktivitäts-Check) und letzter
# Konsolidierungs-Lauf. Lock weil Flask-Thread und Auto-Save-Threads
# alle hier reinschreiben können.
_state_lock         = Lock()
_last_user_turn_at  = None   # datetime
_last_consolidate_at = None  # datetime


# ── Extraktor-Prompt ──────────────────────────────────────────────────
# Strenges JSON-Format, klare Regeln gegen Halluzination. Das LLM darf
# NUR Fakten extrahieren, die explizit ausgesprochen wurden. Keine
# Schlüsse, keine "wahrscheinlich meinte X dass...".
_EXTRACTOR_SYSTEM_PROMPT = """Du bist ein strenger Memory-Konsolidator. Du liest eine Liste von Chat-Turns zwischen Sasha (User) und einer KI, und extrahierst nur die Fakten daraus, die langfristig wertvoll sind.

ABSOLUTE REGELN:
1. Extrahiere NUR Sachen die WÖRTLICH gesagt wurden. Keine Schlüsse, keine Interpretationen, keine "vermutlich meinte X". Wenn der Fakt nicht explizit im Text steht, taucht er auch nicht im Output auf.
2. Smalltalk, Begrüßungen, Floskeln, Tool-Diskussionen und Klärungsfragen NICHT extrahieren.
3. Wenn die KI etwas behauptet zu tun (z.B. "ich speichere das ab", "ich vergesse das jetzt") und dabei KEINEN Tool-Call hatte: das ist eine Lüge der KI, NICHT als Fakt extrahieren.
4. Bei Widersprüchen oder Korrekturen (User sagt "nein das war anders"): nimm die letzte Version, ignoriere die alte.
5. Fakten vom User (über sich, seine Projekte, Hardware) → who_said = "user".
6. Aussagen der KI über sich selbst, ihre Fähigkeiten/Grenzen → who_said = "ai".

TYPEN:
- fact: Objektive Information über User, System, Welt
- preference: Wie der User Dinge mag (Stil, Reaktionsart, Tonfall)
- commitment: Was die KI versprochen hat / offene TODOs
- technical: Configs, Code-Details, technische Internals
- capability: Was die KI nachweislich kann (im Gespräch belegt)
- limit: Was die KI NICHT kann (vom User korrigiert)

OUTPUT-FORMAT: gültiges JSON-Objekt mit einem Feld "facts", das ein ARRAY enthält. Auch bei nur einem Fakt: das Array haben. Bei keinen Fakten: leeres Array.

WICHTIG: Extrahiere ALLE wertvollen Fakten aus der Liste, nicht nur einen. Wenn die Liste 5 Fakten enthält, müssen 5 Einträge im Array stehen.

Beispiel (zwei verschiedene Fakten aus einer Turn-Liste):
{
  "facts": [
    {"content": "Sashas Pi ist ein Raspberry Pi 3 Model B mit 1 GB RAM", "type": "fact", "who_said": "user"},
    {"content": "Sasha bevorzugt direkte, knappe Antworten ohne Floskeln", "type": "preference", "who_said": "user"}
  ]
}

Beispiel (keine extrahierbaren Fakten):
{"facts": []}"""


def _format_stm_for_extractor(stm_list: list) -> str:
    """
    Formatiert die rohe STM-Liste als nummeriertes Transcript für den
    Extraktor-Prompt. Wir nutzen "user:"/"ai:"-Präfixe damit das Modell
    die Rollen sauber trennt.
    """
    lines = []
    for i, e in enumerate(stm_list):
        role = e.get('role', 'user')
        text = e.get('text', '').strip()
        if not text:
            continue
        lines.append(f"{i:2d}. {role}: {text}")
    return "\n".join(lines)


def _call_extractor(stm_list: list) -> list:
    """
    Macht den LLM-Call der die STM-Liste in strukturierte Fakten umwandelt.

    Returns: Liste von dicts mit Schlüsseln 'content', 'type', 'who_said'.
    Bei Fehlern oder leerer Antwort: leere Liste.
    """
    if not stm_list:
        return []

    transcript = _format_stm_for_extractor(stm_list)
    user_body = f"Hier ist die Turn-Liste:\n\n{transcript}\n\nExtrahiere die langfristig wertvollen Fakten als JSON-Array:"

    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":    OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _EXTRACTOR_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_body},
                ],
                "stream":   False,
                # Ollama unterstützt format="json" - zwingt das Modell
                # zu wohlgeformtem JSON. Wir kapseln das Array in einem
                # Objekt damit Ollama's JSON-Modus glücklich ist.
                "format":   "json",
            },
            timeout=120,
        )
        content = resp.get("message", {}).get("content", "").strip()
    except Exception:
        return []

    return _parse_extractor_output(content)


def _parse_extractor_output(content: str) -> list:
    """
    Parsed die LLM-Antwort defensiv. Das Modell sollte ein JSON-Array
    liefern, aber wir tolerieren auch:
      - Ein Objekt mit "facts"/"results"-Key
      - JSON in Markdown-Code-Fence (```json ... ```)
      - Leading/trailing whitespace

    Returns: Liste von dicts oder [].
    """
    if not content:
        return []

    # Markdown-Fences abstreifen falls vorhanden
    s = content.strip()
    if s.startswith("```"):
        # Erste Zeile (```json oder ```) wegwerfen, letzte Zeile (```) auch
        lines = s.splitlines()
        s = "\n".join(lines[1:-1]) if len(lines) > 2 else ""

    try:
        parsed = _json.loads(s)
    except Exception:
        return []

    # Erlaubte Formen, sortiert nach Wahrscheinlichkeit:
    #   {"facts": [...]}            – unser standard-prompted Format
    #   [{...}, {...}]              – direktes Array (alternativ)
    #   {"content": ..., ...}       – Single-Fact als Objekt (qwen2.5
    #                                  macht das gelegentlich) → wrappen
    if isinstance(parsed, list):
        return [e for e in parsed if isinstance(e, dict)]
    if isinstance(parsed, dict):
        # Wrapper-Objekt mit Array-Wert
        for key in ('facts', 'results', 'entries', 'items'):
            v = parsed.get(key)
            if isinstance(v, list):
                return [e for e in v if isinstance(e, dict)]
        # Single-Fact-Objekt: hat 'content' und sieht aus wie ein Fakt
        if 'content' in parsed:
            return [parsed]
    return []


def _save_extracted_facts(facts: list) -> int:
    """
    Speichert die extrahierten Fakten via memory.save() ins LTM.

    Validiert defensiv: ungültige type-/who_said-Werte fallen auf
    Defaults zurück (memory.save handhabt das schon, hier nochmal Gürtel
    plus Hosenträger). Leere oder zu kurze Inhalte werden geskippt.

    Returns: Anzahl der tatsächlich gespeicherten Einträge.
    """
    saved = 0
    for f in facts:
        content = (f.get('content') or '').strip()
        if len(content) < 5:
            continue
        type_    = f.get('type',     'fact')
        who_said = f.get('who_said', 'user')
        memory.save(
            content  = content,
            type     = type_,
            who_said = who_said,
        )
        saved += 1
    return saved


# ── Öffentliche API ────────────────────────────────────────────────────

def consolidate_stm() -> dict:
    """
    Hauptfunktion: STM → LTM Konsolidierung.

    Ablauf:
      1. STM laden (Liste + Summary).
      2. Wenn Liste leer: nichts zu tun, früh raus.
      3. LLM-Extraktor aufrufen → strukturierte Fakten.
      4. Fakten ins LTM speichern (memory.save mit Embedding).
      5. STM komplett leeren (Liste + Summary).
      6. Tracking-Zeitpunkt aktualisieren.

    Returns: Statistik-Dict für Logging/UI:
        {
          'turns_seen':     int,   # wie viele STM-Einträge wir sahen
          'facts_extracted': int,   # wie viele das LLM extrahiert hat
          'facts_saved':     int,   # wie viele tatsächlich im LTM landeten
          'cleared':         bool,  # wurde STM danach geleert
        }
    """
    stm = memory.stm_load()
    stm_list = stm.get('list', [])

    stats = {
        'turns_seen':      len(stm_list),
        'facts_extracted': 0,
        'facts_saved':     0,
        'cleared':         False,
    }

    if not stm_list:
        return stats

    facts = _call_extractor(stm_list)
    stats['facts_extracted'] = len(facts)
    stats['facts_saved']     = _save_extracted_facts(facts)

    # STM in jedem Fall leeren - auch wenn der Extraktor 0 Fakten fand.
    # Begründung: wenn der Extraktor nichts wertvolles fand, ist der
    # Inhalt eh nicht erhaltenswert. Wenn er was übersehen hat, wird
    # der User das beim nächsten Mal erneut erwähnen (Wiederholung ist
    # in diesem System okay, sie kostet nur einen weiteren Save).
    memory.stm_clear()
    stats['cleared'] = True

    with _state_lock:
        global _last_consolidate_at
        _last_consolidate_at = datetime.now()

    return stats


def note_user_turn():
    """
    Wird bei jedem User-Turn aufgerufen (von ai.chat_stream). Aktualisiert
    den Inaktivitäts-Tracking-Zeitpunkt. Sehr leichtgewichtig - blockt
    nichts.
    """
    with _state_lock:
        global _last_user_turn_at
        _last_user_turn_at = datetime.now()


# ╔══════════════════════════════════════════════════════════════════════╗
# ║  Phase G: Konzept-Graph-Extraktion pro Turn                          ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Statt am Session-Ende flache Fakten ins LTM zu konsolidieren, läuft
# der Graph-Extraktor nach JEDEM Chat-Turn (async im Hintergrund-Thread,
# siehe ai._async_save_turn). Er extrahiert Konzepte (Knoten) und
# Beziehungen (Edges) und merged sie in den persistierten Graphen.
#
# Grundgedanke: Memory wird sofort assoziativ aufgebaut, nicht erst
# nach /sleep. Damit ist der Graph immer aktuell und Retrieval kann
# direkt darauf operieren.

_GRAPH_EXTRACTOR_PROMPT = """Du bist ein Konzept-Extraktor für Sashas persönliches Memory-System. Du liest einen Chat-Turn (User: Sasha, AI: die KI) und extrahierst die konkreten Konzepte aus SASHAS REALITÄT und ihre Beziehungen als Graph-Knoten und -Kanten.

ABSOLUTE REGELN:

1. NUR SASHA-SPEZIFISCH: ihre Sachen, Personen in ihrem Leben, Orte, Zustände, Projekte, Erfahrungen. NIE generische Welt-Konzepte definieren oder einbauen (was eine Wasserkanne ist, was Müdigkeit allgemein bedeutet, dass Couches in Wohnzimmern stehen) - das weiß das LLM schon.

2. KNOTEN sind kurze deutsche LABELS, KEINE Definitionen. Beispiele: "Sasha", "Pi", "müde", "ZENTRALE", "1 GB RAM", "Wohnzimmer", "Hut".

3. SUBJEKT bei User-Aussagen über sich: immer "Sasha". Wenn die KI über sich spricht: "KI".

4. EDGES haben kurze deutsche Relations-Labels: "besitzt", "ist", "arbeitet-an", "zustand", "wohnt-in", "geschah-am", "hat", "kann", "kann-nicht", "mag", "fühlt".

5. ZEIT: bei Aussagen wie "ich war heute müde" extrahiere das heutige Datum als Knoten im ISO-Format ("2026-05-15"). Edges: {Sasha→müde, rel=zustand}, {müde→2026-05-15, rel=geschah-am}. NIE "heute"/"gestern"/"morgen" als Knoten - immer absolutes Datum.

6. AI-LÜGEN UND HALLUZINATIONEN NICHT EXTRAHIEREN:

   a) "Ich speichere/notiere/merke das" → wenn KEIN echter Tool-Call
      im Turn war, ist es eine Lüge. Nicht als Fakt extrahieren.

   b) AI-AUSSAGEN ÜBER USER-FAKTEN sind NUR Fakten wenn der User sie
      in DIESEM Turn oder davor selbst genannt hat. Wenn die KI von
      sich aus behauptet "Du hast einen Hund namens Bello", "Du wohnst
      in Berlin", "Du hast neulich X gemacht" – aber der User hat das
      NICHT gesagt: das ist erfundene Vorgeschichte, NICHT extrahieren.
      Faustregel: jeder User-bezogene Fakt muss aus User-Text stammen,
      nicht aus AI-Text.

   c) AI-Aussagen über die KI SELBST ("ich kann nicht X", "ich habe
      kein Tool Y") sind dagegen ok zu extrahieren – das sind ihre
      eigenen Capability/Limit-Aussagen.

7. SMALLTALK weglassen: Begrüßungen, Höflichkeitsfloskeln, "ja"/"ok"/"nein"-Replies, Klärungsfragen. Wenn der Turn nichts substantielles bringt: {"nodes": [], "edges": []}.

8. KEINE redundanten Konzepte: wenn der User sagt "mein Pi", reicht der Knoten "Pi" (das "mein" wird durch die `besitzt`-Edge zu Sasha modelliert).

KNOTEN-TYPEN: "person", "object", "place", "project", "state", "concept", "property", "event". Im Zweifel: "concept".

OUTPUT: gültiges JSON mit zwei Arrays. Auch bei nur einem Knoten/Edge ein Array verwenden. Bei nichts extrahierbarem: leere Arrays.

{
  "nodes": [
    {"name": "Pi", "type": "object"},
    {"name": "1 GB RAM", "type": "property"}
  ],
  "edges": [
    {"from": "Sasha", "to": "Pi", "rel": "besitzt"},
    {"from": "Pi", "to": "1 GB RAM", "rel": "hat"}
  ]
}"""


def _call_graph_extractor(user_msg: str, ai_msg: str, today: str) -> tuple[list[dict], list[dict]]:
    """
    LLM-Call der einen Chat-Turn in (nodes, edges) übersetzt.

    Returns Tupel von (nodes, edges) Listen. Bei Fehlern: leere Listen.
    """
    body = (
        f"Heutiges Datum: {today}\n\n"
        f"Chat-Turn:\n"
        f"User (Sasha): {user_msg}\n"
        f"AI:           {ai_msg}\n\n"
        f"Extrahiere als JSON mit 'nodes' und 'edges' Arrays:"
    )
    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":    OLLAMA_MODEL,
                "messages": [
                    {"role": "system", "content": _GRAPH_EXTRACTOR_PROMPT},
                    {"role": "user",   "content": body},
                ],
                "stream":   False,
                "format":   "json",
            },
            timeout=90,
        )
        content = resp.get("message", {}).get("content", "").strip()
    except Exception:
        return ([], [])

    if not content:
        return ([], [])

    try:
        parsed = _json.loads(content)
    except Exception:
        return ([], [])

    if not isinstance(parsed, dict):
        return ([], [])

    nodes = parsed.get("nodes", [])
    edges = parsed.get("edges", [])
    if not isinstance(nodes, list): nodes = []
    if not isinstance(edges, list): edges = []

    # Defensive Filterung: nur Dicts mit minimal benötigten Feldern
    nodes = [n for n in nodes if isinstance(n, dict) and n.get("name")]
    edges = [e for e in edges if isinstance(e, dict)
             and e.get("from") and e.get("to") and e.get("rel")]
    return (nodes, edges)


def _is_substantive(user_msg: str) -> bool:
    """
    Pre-Filter: hat der Turn überhaupt genug Substanz für eine
    Extraktion? Vermeidet LLM-Calls auf "hi", "ok", purem Emoji-
    Geblubber, oder Single-Word-Replies. Verhindert auch dass das
    Modell aus 🎩💀🤖 wilde Konzepte wie "Kopfbedeckung, Toter,
    THOOK" erfindet.

    Heuristik: mindestens 8 alphanumerische Zeichen UND mindestens
    2 separate Wörter mit Buchstaben. Sonst skip.
    """
    if not user_msg:
        return False
    # Buchstaben/Zahlen zählen
    alpha_chars = sum(1 for c in user_msg if c.isalnum())
    if alpha_chars < 8:
        return False
    # Wörter mit mindestens einem Buchstaben
    word_count = sum(1 for w in user_msg.split() if any(c.isalpha() for c in w))
    if word_count < 2:
        return False
    return True


def extract_turn_into_graph(user_msg: str, ai_msg: str):
    """
    Hauptweg um einen Turn in den Graphen zu kippen. Wird async von
    ai._async_save_turn aufgerufen. Macht den LLM-Extraktor-Call und
    füttert das Ergebnis in graph.add_turn_extraction.

    Pre-Filter: Triviale Turns (zu kurz, kein echter Inhalt) werden
    übersprungen - kein LLM-Call. Spart Latenz und vermeidet
    Konfabulations-Müll.

    Blockiert nichts: Caller sollte das in einem Thread laufen lassen.
    """
    user_msg = (user_msg or '').strip()
    ai_msg   = (ai_msg   or '').strip()
    if not _is_substantive(user_msg):
        return

    today = date.today().isoformat()
    nodes, edges = _call_graph_extractor(user_msg, ai_msg, today)
    if not nodes and not edges:
        return
    graph.add_turn_extraction(nodes, edges)


def maybe_consolidate_due_to_inactivity() -> dict | None:
    """
    Lazy-Trigger: wird ebenfalls bei jedem User-Turn aufgerufen, prüft
    ob seit dem LETZTEN User-Turn mehr als INACTIVITY_THRESHOLD_SEC
    vergangen sind. Wenn ja → konsolidieren.

    Achtung Reihenfolge: erst maybe_consolidate_due_to_inactivity()
    aufrufen (vergleicht GEGEN den letzten Turn-Timestamp), DANN
    note_user_turn() (setzt den neuen Timestamp). Sonst sieht man die
    eigene "Inaktivität" nie.

    Returns: Stats-Dict wenn konsolidiert wurde, sonst None.
    """
    with _state_lock:
        prev = _last_user_turn_at
    if prev is None:
        return None  # Erster Turn der Session → keine "Inaktivität"
    gap = (datetime.now() - prev).total_seconds()
    if gap < INACTIVITY_THRESHOLD_SEC:
        return None
    return consolidate_stm()
