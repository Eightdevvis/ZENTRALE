# core/consolidation.py
#
# Konzept-Graph-Extraktion pro Chat-Turn (Phase G).
#
# Nach jedem User+AI-Turn ruft ai._async_save_turn diese Datei (im
# Daemon-Thread) auf. Ein LLM-Extraktor zieht aus dem Turn strukturierte
# Konzepte (Knoten) und Beziehungen (Edges) und merged sie in den
# persistierten Graphen (graph.add_turn_extraction). Memory wird so
# sofort assoziativ aufgebaut, ohne separate /sleep-Konsolidierung.
#
# Die alte STM→LTM-Pipeline (Phase D/E, ai_stm.json/ai_ltm.json,
# /sleep-Command, INACTIVITY_THRESHOLD) ist mit dem Wechsel auf den
# Graph komplett rausgeflogen - sie schrieb in Strukturen die niemand
# mehr las und kostete pro Turn unnötige LLM- und Embedding-Calls.

import os
import re
import json as _json
from datetime import date

import net      # HTTP-Wrapper mit Logging
import graph    # Konzept-Graph (Phase G)
import state    # Logging in den UI-Terminal-Stream
import kalender              # Auto-Capture in den erlebt-Layer

# ── Konfiguration ──────────────────────────────────────────────────────
OLLAMA_URL        = os.environ.get("OLLAMA_URL",        "http://localhost:11434")
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL",      "qwen2.5:14b")
# Modell warmhalten - dieser Extraktor läuft async nach jedem Turn,
# wenn das Modell zwischendurch unloadet wird kostet jeder Lauf den
# Reload. Default 30m, per Env überschreibbar.
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
# KRITISCH: identisch zu ai.py.OLLAMA_NUM_CTX. Ollama haelt pro
# (Modell, Kontextgroesse) eine eigene Instanz. Riefe dieser Extraktor
# qwen ohne num_ctx (= Ollama-Default ~4096), waehrend der Chat
# num_ctx=8192 nutzt, wuerde Ollama qwen bei JEDEM Turn neu laden
# (Chat@8192 → Konsolidierung@default → naechster Chat@8192 = 2 Reloads
# pro Frage, ~17 s je Reload). Gleicher Wert = eine Instanz, kein Reload.
OLLAMA_NUM_CTX    = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


# ── Sanitization für extrahierte Edges ────────────────────────────────
# Der Extraktor halluziniert munter neue Edge-Verben ("wohlbehalten",
# "kennet", "aktuelles-Datum", "definiert") und vertauscht Subjekte
# ("KI → arbeitet-an → Sasha" wenn die KI über Sasha geredet hat).
# Wir filtern post-hoc, weil reine Prompt-Disziplin nicht reicht - das
# Modell ignoriert die Whitelist-Liste im Prompt und erfindet trotzdem.
#
# Whitelist absichtlich klein gehalten. Im Zweifel: lieber einen Edge
# fallen lassen als Müll in den Graphen schreiben - die wichtigen
# Beziehungen bauen sich über mehrere Turns auf, ein verlorener Edge
# heilt sich beim nächsten Mal.
_ALLOWED_EDGE_VERBS = {
    # aus dem Extraktor-Prompt (Regel 4)
    "besitzt", "ist", "arbeitet-an", "zustand", "wohnt-in",
    "geschah-am", "hat", "kann", "kann-nicht", "mag", "fühlt",
    # internes (Time-Anker, Beziehungen, Aktionen)
    "erwähnt-am", "kennt", "kommuniziert-mit", "macht", "war-am",
}

# YYYY-MM-DD Datums-Knoten. Datum als SUBJEKT eines Edges ist fast
# immer Extraktor-Müll - korrekte Richtung ist <konzept> ─[erwähnt-am
# /geschah-am]─► <datum>. Subjekt-Datum produziert "2026-05-31 hat
# zustand Sasha" - sowas verdaut das LLM beim Lesen unmöglich richtig.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Relations die richtungs-anfällig sind: KI/Sasha sind hier oft am
# falschen Ende, wenn die KI in der Antwort über Sasha geredet hat
# und der Extraktor das Subjekt verwechselt. "ist" und
# "kommuniziert-mit" sind ausgenommen (Sasha ist KingHEZ etc.).
_SUBJECT_SWAP_RISK = {
    "arbeitet-an", "hat", "mag", "fühlt", "zustand",
    "kann", "kann-nicht", "besitzt", "wohnt-in", "macht",
}


def _sanitize_extracted(nodes: list, edges: list) -> tuple[list, dict]:
    """
    Filtert Extraktor-Output gegen die typischen Pathologien:
      1. Edge-Verb außerhalb der Whitelist → raus
      2. Subjekt = Datums-Knoten → raus (Edge-Richtung verkehrt)
      3. KI ↔ Sasha bei Subjekt-anfälligen Relations → raus
         (klassischer Subjekt-Tausch)

    Nodes werden NICHT gefiltert - die sind harmlos und können später
    durch reale Edges sinnvoll werden.

    Returns: (saubere_edges, drop_stats).
    """
    clean = []
    drops = {"verb": 0, "date_subject": 0, "subject_swap": 0}
    for e in edges:
        rel = e.get("rel", "")
        frm = e.get("from", "")
        to  = e.get("to", "")

        if rel not in _ALLOWED_EDGE_VERBS:
            drops["verb"] += 1
            continue
        if _DATE_RE.match(frm):
            drops["date_subject"] += 1
            continue
        if rel in _SUBJECT_SWAP_RISK and {frm, to} == {"KI", "Sasha"}:
            drops["subject_swap"] += 1
            continue

        clean.append(e)

    return clean, drops


# ── Extraktor-Prompt ──────────────────────────────────────────────────
_GRAPH_EXTRACTOR_PROMPT = """Du bist ein Konzept-Extraktor für Sashas persönliches Memory-System. Du liest einen Chat-Turn (User: Sasha, AI: die KI) und extrahierst die konkreten Konzepte aus SASHAS REALITÄT und ihre Beziehungen als Graph-Knoten und -Kanten.

ABSOLUTE REGELN:

1. NUR SASHA-SPEZIFISCH: ihre Sachen, Personen in ihrem Leben, Orte, Zustände, Projekte, Erfahrungen. NIE generische Welt-Konzepte definieren oder einbauen (was eine Wasserkanne ist, was Müdigkeit allgemein bedeutet, dass Couches in Wohnzimmern stehen) - das weiß das LLM schon.

2. KNOTEN sind kurze deutsche LABELS, KEINE Definitionen. Beispiele: "Sasha", "Pi", "müde", "ZENTRALE", "1 GB RAM", "Wohnzimmer", "Hut".

3. SUBJEKT bei User-Aussagen über sich: immer "Sasha". Wenn die KI über sich spricht: "KI". NIEMALS umdrehen: "KI arbeitet-an Sasha" oder "KI hat Sasha" sind IMMER Müll - Sasha ist nie Objekt einer Eigenschaft der KI.

4. EDGES haben kurze deutsche Relations-Labels - NUR aus dieser geschlossenen Liste, keine neuen Verben erfinden: "besitzt", "ist", "arbeitet-an", "zustand", "wohnt-in", "geschah-am", "hat", "kann", "kann-nicht", "mag", "fühlt", "erwähnt-am", "kennt", "kommuniziert-mit", "macht", "war-am". Wenn keins davon passt: Edge weglassen, lieber gar nichts als ein erfundenes Verb wie "wohlbehalten", "definiert", "aktuelles-Datum", "kennet".

5. ZEIT: bei Aussagen wie "ich war heute müde" extrahiere das heutige Datum als Knoten im ISO-Format ("2026-05-15"). Edges: {Sasha→müde, rel=zustand}, {müde→2026-05-15, rel=geschah-am}. NIE "heute"/"gestern"/"morgen" als Knoten - immer absolutes Datum. Datums-Knoten sind NIE Subjekt eines Edges - immer am Pfeil-Ziel-Ende (X ─[erwähnt-am]─► 2026-05-15, niemals 2026-05-15 ─[X]─► Y).

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

   d) WICHTIGSTER STOLPERSTEIN: Wenn die KI in ihrer Antwort Themen
      benennt über die sie GERADE REDET ("ich erkläre dir API-Endpunkte",
      "Dateipfade sind...", "Bibliotheken funktionieren so..."), ist
      das KEIN Sasha-Fakt. Sasha mag nicht plötzlich "API-Endpunkte"
      oder "Dateipfade" nur weil die KI darüber dozierte. Solche
      Edges wie {Sasha → mag → API-Endpunkte} sind IMMER Müll. Wenn
      Sasha selbst gesagt hat "ich mag X", dann ja - sonst nein.

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
                "stream":     False,
                "format":     "json",
                "keep_alive": OLLAMA_KEEP_ALIVE,
                # Gleiche Kontextgroesse wie der Chat-Pfad – sonst laedt
                # Ollama qwen pro Turn neu (siehe OLLAMA_NUM_CTX oben).
                "options":    {"num_ctx": OLLAMA_NUM_CTX},
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

    # Sanitization gegen die bekannten Pathologien (Verb-Hallu, Subjekt-
    # Tausch, Datum-als-Subjekt). Drop-Counts ins Terminal damit man
    # sieht ob der Extraktor halbwegs sauber arbeitet oder ob die
    # Whitelist nachjustiert werden muss.
    edges, drops = _sanitize_extracted(nodes, edges)
    if any(drops.values()):
        try:
            state.push_log(
                f"GRAPH-SANITY verworfen: {drops['verb']} Verb, "
                f"{drops['date_subject']} Datum-Subjekt, "
                f"{drops['subject_swap']} KI↔Sasha-Tausch"
            )
        except Exception:
            pass

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
    alpha_chars = sum(1 for c in user_msg if c.isalnum())
    if alpha_chars < 8:
        return False
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

    # Auto-Capture in den Kalender: jedes Konzept das im Graph einen
    # geschah-am-Edge zu einem ISO-Datum kriegt, spiegeln wir in den
    # erlebt-Layer. Das gibt dem Kalender ein "war da was?"-Skelett
    # ohne dass die KI dafür explizit Tool-Calls machen muss.
    for e in edges:
        if e.get("rel") != "geschah-am":
            continue
        target = e.get("to", "")
        if not _DATE_RE.match(target):
            continue
        concept = e.get("from", "")
        if not concept or concept in ("Sasha", "KI"):
            continue  # Subjekt-Anker selbst nicht als Erlebnis spiegeln
        try:
            kalender.auto_capture(concept, target)
        except Exception:
            pass
