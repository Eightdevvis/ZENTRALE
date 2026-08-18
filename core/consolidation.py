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
from datetime import date, timedelta

import net      # HTTP-Wrapper mit Logging
import graph    # Konzept-Graph (Phase G)
import state    # Logging in den UI-Terminal-Stream
import kidebug               # Devtools-Bus (scripts/ai_devtools.py)
import transkript            # Rohmaterial unter dem Graphen (append-only)

# ── Konfiguration ──────────────────────────────────────────────────────
OLLAMA_URL        = os.environ.get("OLLAMA_URL",        "http://localhost:11434")
OLLAMA_MODEL      = os.environ.get("OLLAMA_MODEL",      "qwen3.5:9b")
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
# qwen3/qwen3.5 denken per Default vor jeder Antwort -> dieser JSON-Extraktor
# wuerde pro Turn minutenlang "nachdenken" statt nur Fakten zu liefern.
# Thinking aus. Nur fuer qwen3* gueltig (qwen2.5 -> Ollama 400), daher kond.
SUPPORTS_THINK    = OLLAMA_MODEL.startswith("qwen3")

# Die Tripel-Extraktion in den Konzept-Graphen. DEFAULT AUS seit 18.08.2026.
#
# Sie kostete pro Turn einen eigenen LLM-Call (gemessen 0,0028 EUR) — bei
# 30 Kontakten am Tag rund 2,70 EUR im Monat, bei einem 20-EUR-Budget also
# ein Achtel, ausgegeben fuer ein Ergebnis, das die Antworten messbar
# schlechter machte: "Sasha wohnt-in Universitaet des Saarlandes",
# "Fahrradfahren [project]", derselbe Fakt doppelt in zwei Formen.
#
# Das ROHMATERIAL wird weiter geschrieben (transkript.schreiben, gleich
# unten) — es ist die Grundlage des Datei-Gedaechtnisses und jeder
# spaeteren Auswertung. Verloren geht also nichts; es wird nur nicht mehr
# jeder Satz in Tripel zerhackt.
#
# ZENTRALE_GRAPH_EXTRAKTION=1 schaltet sie zurueck, wenn der Graph eines
# Tages ein Schema hat (Graphiti o.ae.).
GRAPH_EXTRAKTION  = os.environ.get("ZENTRALE_GRAPH_EXTRAKTION", "0") == "1"



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
# Tag, Woche, Monat ODER Jahr: seit der Zeit-Regel darf der Extraktor gröber
# datieren ("2026-W34", "2026-08"), und eine Woche als SUBJEKT ist genauso
# Müll wie ein Tag als Subjekt.
_DATE_RE = re.compile(r"^\d{4}(-(W\d{2}|\d{2}(-\d{2})?))?$")

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

5. ZEIT - die häufigste Fehlerquelle. Trenne strikt, WANN etwas passiert ist, von WANN darüber geredet wird. Das heutige Datum steht oben im Body; rechne relative Angaben dagegen um und schreib sie absolut ("2026-05-15"). NIE "heute"/"gestern"/"morgen" als Knoten. Datums-Knoten sind NIE Subjekt eines Edges - immer am Pfeil-Ziel-Ende (X ─[erwähnt-am]─► 2026-05-15, niemals 2026-05-15 ─[X]─► Y).

   a) `geschah-am` NUR mit einem Datum, das im Turn wirklich dasteht oder
      eindeutig ableitbar ist: "heute", "gestern", "am Dienstag", "am 12.8.".
      Beispiel "ich war heute müde": {Sasha→müde, rel=zustand},
      {müde→2026-05-15, rel=geschah-am}.

   b) UNGEFÄHRE VERGANGENHEIT WIRD GRÖBER, NICHT FALSCH — aber nur so grob
      wie nötig. Nimm IMMER die feinste Stufe, die noch WAHR ist:

        Tag     "2026-08-17"  wenn der Tag dasteht oder eindeutig folgt
        Woche   "2026-W34"    "vor ein paar Tagen", "letztens", "diese
                              Woche", "Anfang der Woche", "am Wochenende"
        Monat   "2026-08"     "vor ein paar Wochen", "Anfang August",
                              "letzten Monat"
        Jahr    "2026"        wenn nicht mal der Monat klar ist

      Die heutige Kalenderwoche steht oben im Body; "vor ein paar Tagen"
      ist je nach Wochentag diese oder die vorige. Beispiel:
      {Schüttelfrost→2026-W33, rel=geschah-am}.

      NIEMALS ein Tages-Datum auf Verdacht — das ist der schlimmste Fehler
      überhaupt, denn das heutige wäre der Tag des Erzählens, nicht der des
      Geschehens. Passt nicht mal ein Jahr: gar keine Zeitkante.

   c) GEGENWART IST DAGEGEN EINFACH. "ich hab grad Fieber", "mir ist heute
      schlecht", "ich bin gerade in Berlin" beschreiben JETZT → heutiges
      Datum, ganz normal als Tages-Knoten. Sei hier nicht übervorsichtig:
      Regel (b) gilt für UNBESTIMMTE Vergangenheit, nicht für Aussagen im
      Präsens. Was der Turn klar sagt, wird klar datiert.

   d) NICHT-EREIGNISSE bekommen NIEMALS ein geschah-am: Fragen ("kann ich
      heute wieder Sport machen?"), Vorhaben und Pläne ("ich will nachher
      laufen"), Hypothetisches ("wenn ich morgen fit bin"), Verneintes
      ("ich war nicht joggen"). Nach etwas zu FRAGEN heißt nicht, es getan
      zu haben. Im Zweifel: keine Zeitkante.

   e) Ein datierter Zustand gilt GENAU an diesem Tag und sagt NICHTS über
      andere Tage. "Fieber geschah-am 2026-08-09" heißt nicht, dass das
      Fieber davor oder danach bestand.

   f) `erwähnt-am` ist das Gegenstück und datiert das REDEN: wenn du weißt,
      dass etwas Thema war, aber nicht wann es passierte, nimm erwähnt-am
      aufs heutige Datum - nie geschah-am.

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


def _wochen_anker(today: str) -> str:
    """Kalenderwoche + Wochentag zum heutigen Datum, als Klammerzusatz.

    Ohne das müsste der Extraktor die ISO-Woche selbst ausrechnen, um "vor
    ein paar Tagen" auf einen Wochen-Knoten zu legen — und Datums-Arithmetik
    ist genau das, was Modelle zuverlässig verhauen. Python rechnet, das
    Modell liest ab. Dieselbe Linie wie beim Wochentag im Kalender-Renderer.
    """
    try:
        d = date.fromisoformat(today)
    except (TypeError, ValueError):
        return ""
    import graph
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
            "Samstag", "Sonntag"]
    vorwoche = graph.woche_von(d - timedelta(days=7))
    return (f" ({tage[d.weekday()]}, Kalenderwoche {graph.woche_von(d)}"
            f", vorige Woche {vorwoche})")


def _extractor_body(user_msg, ai_msg=None, today: str = "") -> str:
    """Der User-Prompt-Body für den Extraktor (identisch für lokal + cloud).

    Nimmt EINEN Turn (user_msg, ai_msg) oder eine LISTE von Turns
    [(user, ai), …]. Mehrere Turns in einem Call sind billiger und obendrein
    besser: der Extraktor sieht den Zusammenhang über die Turns hinweg statt
    jeden für sich, und die Anweisungen im System-Prompt werden einmal statt
    fünfmal bezahlt.
    """
    if isinstance(user_msg, (list, tuple)):
        turns = list(user_msg)
        if today == "" and isinstance(ai_msg, str):
            today = ai_msg            # alte Positions-Reihenfolge tolerieren
    else:
        turns = [(user_msg, ai_msg)]

    teile = [f"Heutiges Datum: {today}{_wochen_anker(today)}", ""]
    if len(turns) == 1:
        u, a = turns[0]
        teile += [f"Chat-Turn:", f"User (Sasha): {u}", f"AI:           {a}", ""]
    else:
        teile.append(f"{len(turns)} Chat-Turns, chronologisch:")
        for i, (u, a) in enumerate(turns, 1):
            teile += [f"", f"[Turn {i}]",
                      f"User (Sasha): {u}", f"AI:           {a}"]
        teile.append("")
    teile.append("Extrahiere als JSON mit 'nodes' und 'edges' Arrays:")
    return "\n".join(teile)


def _finalize_extraction(content: str) -> tuple[list[dict], list[dict]]:
    """Parst die JSON-Antwort eines Extraktors (lokal ODER cloud) und
    sanitized sie gegen die bekannten Pathologien. Bei Müll: leere Listen."""
    content = (content or "").strip()
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


def _local_da() -> bool:
    """Ist Ollama gerade erreichbar? Entscheidet, ob der Cloud-Extraktor
    überhaupt in Frage kommt."""
    try:
        import ai
        return bool(ai.is_available())
    except Exception:
        return False


def _call_graph_extractor_cloud(user_msg: str, ai_msg: str,
                                today: str) -> tuple[list[dict], list[dict]]:
    """
    CLOUD-Extraktor (OpenAI-kompatibel): dasselbe wie unten, nur über einen
    Anbieter statt über Ollama.

    Wozu: unterwegs läuft kein Ollama. Ohne Extraktor bekäme der Cloud-Graph
    nie Fakten — die Cloud-KI könnte reden, würde sich aber nichts merken,
    und das Memory bliebe ein Feature, das nur daheim existiert.

    NUR für den Cloud-Graphen. Den lokalen Graphen hier zu füttern hieße,
    Sashas Gespräche an einen Anbieter zu schicken; die Entscheidung trifft
    extract_turn_into_graph, nicht diese Funktion.

    Fleißarbeit, kein Denken: Konzepte und Kanten aus einem Turn ziehen. Ein
    kleines/billiges Modell reicht (providers.cheap_model, übersteuerbar per
    ZENTRALE_CONSOL_CLOUD_MODEL).

    Beide Dialekte. Der Anthropic-Zweig ist nicht optional: sobald Claude der
    konfigurierte Anbieter ist — und genau darauf läuft der Kern hinaus —
    stieg diese Funktion vorher mit ([], []) aus. Der Cloud-Graph hätte
    einfach nichts mehr bekommen, still, und das Gedächtnis wäre genau beim
    Umschalten auf das Modell gestorben, um das es geht.
    """
    import os as _os
    import providers

    body = _extractor_body(user_msg, ai_msg, today)
    name = providers.configured() or ""
    prov = providers.get(name)
    mdl  = _os.environ.get("ZENTRALE_CONSOL_CLOUD_MODEL") \
        or providers.cheap_model(name)
    art  = prov.get("kind")

    try:
        if art == "anthropic":
            import anthropic  # type: ignore
            client = anthropic.Anthropic()
            # Kein Streaming. KEIN output_config/effort: die kleinen Modelle
            # (haiku) kennen den Parameter nicht und quittieren ihn mit einer
            # 400 — live gemessen, und der Fehler war doppelt gemein, weil er
            # nur den Hintergrund-Extraktor traf. Das Gespraech lief weiter,
            # nur gemerkt hat sich die KI nichts.
            antwort = client.messages.create(
                model=mdl,
                max_tokens=2000,
                system=_GRAPH_EXTRACTOR_PROMPT,
                messages=[{"role": "user", "content": body},
                          # Vorgefüllter Assistant-Turn: zwingt das Modell in
                          # JSON, ohne dass ein Vorwort ("Hier sind die
                          # Konzepte:") den Parser zerlegt.
                          {"role": "assistant", "content": "{"}],
            )
            text = "".join(b.text for b in antwort.content
                           if getattr(b, "type", None) == "text")
            content = "{" + text
            _buchen(mdl, antwort.usage)

        elif art == "openai_compat":
            from openai import OpenAI  # type: ignore
            client = OpenAI(base_url=prov.get("base_url"),
                            api_key=_os.environ.get(prov.get("key_env") or "", ""))
            resp = client.chat.completions.create(
                model=mdl,
                messages=[{"role": "system", "content": _GRAPH_EXTRACTOR_PROMPT},
                          {"role": "user",   "content": body}],
                response_format={"type": "json_object"},
                stream=False,
                timeout=90,
            )
            content = (resp.choices[0].message.content or "").strip()
            _buchen(mdl, getattr(resp, "usage", None))

        else:
            return ([], [])
    except Exception as e:
        state.push_log(f"[konsolidierung-cloud] FEHLER: {e}")
        return ([], [])

    return _finalize_extraction(content)


def _buchen(model: str, verbrauch) -> None:
    """Den Extraktor-Call mitrechnen.

    Er lief bisher an der Buchhaltung vorbei — und ist der einzige Posten, der
    OHNE Sashas Zutun feuert. Was man nicht sieht, kann man nicht deckeln.
    """
    if verbrauch is None:
        return
    try:
        import usage
        rein = int(getattr(verbrauch, "input_tokens", 0)
                   or getattr(verbrauch, "prompt_tokens", 0) or 0)
        raus = int(getattr(verbrauch, "output_tokens", 0)
                   or getattr(verbrauch, "completion_tokens", 0) or 0)
        eur = usage.buchen(model, input_tokens=rein, output_tokens=raus)
        state.push_log(f"GRAPH ← {model} in={rein} out={raus} ≈{eur:.4f}€")
    except Exception:
        pass


def _call_graph_extractor(user_msg: str, ai_msg: str, today: str) -> tuple[list[dict], list[dict]]:
    """
    LOKALER Extraktor (Ollama): übersetzt einen Chat-Turn in (nodes, edges).
    Returns Tupel von (nodes, edges) Listen. Bei Fehlern: leere Listen.
    """
    body = _extractor_body(user_msg, ai_msg, today)
    try:
        resp = net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":    OLLAMA_MODEL,
                **({"think": False} if SUPPORTS_THINK else {}),
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

    return _finalize_extraction(content)


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


def extract_turn_into_graph(user_msg: str, ai_msg: str,
                            store: str | None = None):
    """
    Hauptweg um einen Turn in den Graphen zu kippen. Wird async von
    ai._async_save_turn aufgerufen. Macht den LLM-Extraktor-Call und
    füttert das Ergebnis in graph.add_turn_extraction.

    Pre-Filter: Triviale Turns (zu kurz, kein echter Inhalt) werden
    übersprungen - kein LLM-Call. Spart Latenz und vermeidet
    Konfabulations-Müll.

    Blockiert nichts: Caller sollte das in einem Thread laufen lassen.

    Args:
        store:           None → Core-Graph (data/ai_graph.json). Der Persona-
                         Pfad ist TOT: der Tutor nutzt seit dem Notiz-Umbau
                         (2026-07-10) tutor/memory.py (Notiz-Modell), NICHT den
                         Graphen — heute wird diese Funktion nur mit store=None
                         (Core-Graph) aufgerufen. Die Grenze Tutor ↔ Core-KI
                         liegt darin, dass die Stores sich NIE anfassen.

    ── Wer verdichtet ────────────────────────────────────────────────
    Bevorzugt IMMER lokal (Ollama): daheim ist das gratis und für
    Fleißarbeit gut genug.

    Für den CLOUD-Graphen gibt es einen Rückfall auf den Cloud-Extraktor,
    wenn Ollama nicht da ist — unterwegs würde sich die Cloud-KI sonst nie
    etwas merken. Der Turn ist in dem Fall ohnehin schon durch die Cloud
    gelaufen; ihn zum Verdichten noch einmal hinzuschicken gibt nichts preis,
    was der Anbieter nicht schon gesehen hat.

    Für den LOKALEN Graphen gibt es diesen Rückfall NICHT. Ohne Ollama wird
    dort nicht verdichtet, Punkt — Sashas privater Graph verlässt das Haus
    nicht, auch nicht als Extraktions-Auftrag.
    """
    # Ein Turn oder ein Buendel — der Worker sammelt in der Gespraechspause
    # ohnehin schon mehrere an. Sie in EINEM Call zu verdichten ist billiger
    # (die Extraktor-Anweisungen gehen einmal statt fuenfmal raus) und
    # obendrein besser: der Extraktor sieht den Zusammenhang ueber die Turns
    # hinweg, statt jeden fuer sich zu lesen.
    if isinstance(user_msg, (list, tuple)):
        turns = [((u or '').strip(), (a or '').strip()) for u, a in user_msg]
        turns = [(u, a) for u, a in turns if _is_substantive(u)]
        if not turns:
            return
        argument = turns
    else:
        user_msg = (user_msg or '').strip()
        ai_msg   = (ai_msg   or '').strip()
        if not _is_substantive(user_msg):
            return
        argument = user_msg
        turns = [(user_msg, ai_msg)]

    # Rohmaterial wegschreiben, BEVOR der Extraktor destilliert. Was er
    # wegwirft, waere sonst weg — der Graph merkt sich, DASS eine Beziehung
    # besteht, nicht WAS gesagt wurde. Append-only, wird nie durchsucht.
    quellen = transkript.schreiben(turns, store=store)

    # Ab hier beginnt die Tripel-Extraktion. Ist sie aus, endet der Weg
    # hier — das Rohmaterial steht, und das ist der Teil, der zaehlt.
    if not GRAPH_EXTRAKTION:
        return

    today = date.today().isoformat()
    if isinstance(argument, list):
        nodes, edges = _call_graph_extractor(argument, None, today)
    else:
        nodes, edges = _call_graph_extractor(argument, ai_msg, today)
    if not nodes and not edges and store and not _local_da():
        state.push_log("[konsolidierung] lokal nicht da → Cloud-Extraktor")
        if isinstance(argument, list):
            nodes, edges = _call_graph_extractor_cloud(argument, None, today)
        else:
            nodes, edges = _call_graph_extractor_cloud(argument, ai_msg, today)
    if not nodes and not edges:
        return
    graph.add_turn_extraction(nodes, edges, store=store, quellen=quellen)
    kidebug.emit("ai.graph",
                 knoten=[n.get("name") for n in nodes],
                 kanten=[f"{e.get('from')} -[{e.get('rel')}]-> {e.get('to')}"
                         for e in edges],
                 quellen=quellen,
                 store="cloud" if store else "lokal")

    # Hier stand der Kalender-Spiegel (jede geschah-am-Kante als erlebt-
    # Eintrag). Ersatzlos gestrichen am 17.08.2026 — Begründung steht bei
    # der gelöschten `kalender.auto_capture`. Kurzfassung: ein Schreibweg
    # am Erlaubnis-Gate vorbei, in eine Ebene, die nur die KI lesen konnte.
    # Die Konsolidierung schreibt ab jetzt ausschließlich in den Graphen.
