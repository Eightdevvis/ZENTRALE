# core/ollama.py
#
# Die Anbindung an Ollama — die lokale Modell-Laufzeit. Adresse, Modell,
# Kontextfenster, Sampling, Denk-Schalter, Erreichbarkeit und Warmup stehen
# hier EINMAL.
#
# Bis 2026-10-06 standen sie in core/ai.py, und core/consolidation.py hatte
# dieselben Werte kopiert — mit dem Kommentar „KRITISCH: identisch zu ai.py".
# Eine Wahrheit an zwei Stellen, von Hand gleich gehalten. Und ai_backends
# importierte den ganzen KI-Kern, nur um Ollama anzupingen.
#
# Schicht 2 (Dienste, memory/system/bauplan_kern.md): weiß nichts vom Chat,
# nur wie man Ollama erreicht. Aufbau des KI-Kerns: memory/ki/kern_aufbau.md.
#
# ── Konfiguration ────────────────────────────────────────────────────
#   OLLAMA_URL        – default: http://localhost:11434
#   OLLAMA_MODEL      – default: qwen3.5:9b
#   OLLAMA_KEEP_ALIVE – default: 30m
#   OLLAMA_NUM_CTX    – default: 8192
#   OLLAMA_TEMP / OLLAMA_TOP_P / OLLAMA_TOP_K – Sampling

import os

import net
import state

OLLAMA_URL   = os.environ.get("OLLAMA_URL",   "http://localhost:11434")
# Default-Modell seit 2026-06-06: qwen3.5:9b. Reasoning-Bench (scripts/
# bench_reasoning.py) zeigte es gleichstark zu qwen3:14b (10/11 ohne Thinking),
# aber schneller (68 vs 47 tok/s) und kleiner (8.8 statt 11 GB VRAM -> laesst
# Luft fuer Browser/Desktop, behebt die VRAM-Contention-Crashes). Tool-Calling
# 100%. Per Env OLLAMA_MODEL umstellbar (Fallback z.B. qwen3:14b / qwen2.5:14b).
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3.5:9b")

# qwen3/qwen3.5 "denken" per Default vor JEDER Antwort (lange Reasoning-Traces
# -> 30-80 s Latenz pro Turn; gemessen 55 s fuer ein blankes "Hallo"). Fuer den
# Voice-/Chat-Use-Case toedlich, also schalten wir Thinking explizit AUS. Das
# `think`-Feld ist nur fuer Thinking-faehige Modelle (qwen3*) gueltig; bei
# aelteren (qwen2.5) wuerfe Ollama 400, deshalb nur dann setzen.
SUPPORTS_THINK = OLLAMA_MODEL.startswith("qwen3")


def think_opts() -> dict:
    """{'think': False} fuer Thinking-Modelle, sonst {} - zum Spreaden in die
    /api/chat-Payloads (siehe SUPPORTS_THINK)."""
    return {"think": False} if SUPPORTS_THINK else {}


# Ollama unloadet ein Modell nach Default 5 Min Idle - dann zahlt der
# nächste Turn den Cold-Load (qwen3.5:9b sind ~8,8 GB, das sind ein paar
# Sekunden Reload je nach SSD/RAM). Wir halten das Hauptmodell länger
# warm, damit Chat-Antworten auch nach einer Kaffeepause direkt losgehen.
# Per Env `OLLAMA_KEEP_ALIVE` überschreibbar (z.B. "-1" = ewig, "10m",
# "0" = sofort unloaden für RAM-knappe Setups).
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")

# Kontextfenster-Groesse in Token. KRITISCH: ohne explizites num_ctx nimmt
# Ollama seinen winzigen Default (2048-4096) - voellig unabhaengig davon,
# dass qwen2.5 eigentlich 32768 koennte. Folge: sobald System-Prompt +
# Graph-Kontext + Chat-History (deque maxlen=50 in state.py) diese Grenze
# sprengen, schiebt Ollama das Fenster und schneidet VORNE ab - genau dort,
# wo der System-Prompt mit der "nur lateinische Schrift"-Regel sitzt. Faellt
# die Regel raus, kommt qwens bilinguale zh/en-Ader durch -> Chinesisch
# blutet mitten im Gespraech ein. 8192 haelt die 50er-History + Prompt
# bequem im Fenster und passt noch in 12 GB VRAM neben dem ~9 GB Modell
# (KV-Cache waechst linear mit num_ctx; groesser ginge, riskiert aber
# Auslagerung ins RAM = langsam). Per Env feinjustierbar.
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "8192"))


# Qwen-empfohlene Sampling-Parameter (Non-Thinking-Modus). Vorher setzte der
# Chat-Pfad NUR num_ctx -> Ollama nahm seine Defaults (temp 0.8, top_p 0.9,
# top_k 40, repeat_penalty 1.1), die fuer Qwen NICHT passen. Qwen empfiehlt
# offiziell temp 0.7 / top_p 0.8 / top_k 20 / min_p 0 / repeat_penalty 1.05
# (qwen.readthedocs.io function_call + Qwen3-Modelcards) und warnt explizit vor
# greedy/temp=0 (-> Wiederholungen/Degradation). Im Kalender-Bench hob das die
# Korrektheit von qwen3.5:9b messbar (70 -> 76 %, mit Antwort-Suffix -> 82 %,
# auf 14B-Niveau bei 9B-Speed). Wird in den Chat-Calls in `options` gespreadt.
QWEN_SAMPLING = {
    "temperature":    float(os.environ.get("OLLAMA_TEMP",    "0.7")),
    "top_p":          float(os.environ.get("OLLAMA_TOP_P",   "0.8")),
    "top_k":          int(os.environ.get("OLLAMA_TOP_K",     "20")),
    "min_p":          0.0,
    "repeat_penalty": 1.05,
}


def is_available() -> bool:
    """
    Health-Check: ist Ollama erreichbar?
    Nutzt urllib direkt (ohne net.py Logging) da dieser Check
    alle 30s im Hintergrund läuft und das Terminal nicht zumüllen soll.
    """
    import urllib.request
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2)
        return True
    except Exception:
        return False


def warmup():
    """
    Zieht das Chat-Modell (OLLAMA_MODEL, Default qwen3.5:9b) und bge-m3 (Embedding-Modell) in
    Ollamas RAM-Cache. Wird als Daemon-Thread beim App-Start gefeuert,
    damit der allererste User-Turn nicht den Cold-Load der ~9 GB qwen-
    Weights bezahlen muss.

    Strategie:
      - Health-Check mit Retry-Loop: beim Boot kann es eine Race geben
        zwischen unserem warmup-Thread und dem ollama.service. Statt
        beim ersten "nicht erreichbar" gleich aufzugeben, geben wir
        Ollama eine knappe halbe Minute, in der wir alle paar Sekunden
        retryen. Schlägt's nach _WARMUP_RETRIES Versuchen weiter fehl
        → leise abbrechen, kein Crash. Beim ersten echten User-Turn
        wird das Modell dann eh on-demand geladen (nur halt mit Latenz).
      - Mini-Chat mit num_predict=1: erzwingt das Laden ohne lange zu
        generieren. keep_alive ist schon im Payload, das Modell bleibt
        also direkt warm.
      - Mini-Embed mit "warmup" als Input: zieht bge-m3 in den RAM.
      - Beide in Try-Except gewrappt - der Hauptthread kümmert sich
        nicht ob's geklappt hat.

    Logs landen sichtbar im Dashboard-Terminal, damit man die Startphase
    transparent verfolgen kann.
    """
    import state
    import time as _time

    # Retry-Loop für die Boot-Race: kalter Systemstart bringt unseren
    # warmup-Thread oft Sekunden vor dem ollama.service-Ready ans Netz.
    # 5 Versuche × 3 s = ~15 s Toleranz, danach geben wir auf.
    _WARMUP_RETRIES        = 5
    _WARMUP_RETRY_DELAY_S  = 3

    for attempt in range(1, _WARMUP_RETRIES + 1):
        if is_available():
            if attempt > 1:
                state.push_log(f"WARMUP ✓  Ollama nach {attempt} Versuchen erreichbar")
            break
        if attempt == _WARMUP_RETRIES:
            state.push_log(
                f"WARMUP ✗  Ollama nach {_WARMUP_RETRIES} Versuchen "
                f"({_WARMUP_RETRIES * _WARMUP_RETRY_DELAY_S}s) nicht erreichbar, überspringe"
            )
            return
        state.push_log(
            f"WARMUP …  Ollama noch nicht da (Versuch {attempt}/{_WARMUP_RETRIES}), "
            f"retry in {_WARMUP_RETRY_DELAY_S}s"
        )
        _time.sleep(_WARMUP_RETRY_DELAY_S)

    state.push_log(f"WARMUP →  Lade {OLLAMA_MODEL} und Embed-Modell in den RAM")

    # 1. Chat-Modell warmladen
    try:
        net.post(
            f"{OLLAMA_URL}/api/chat",
            {
                "model":      OLLAMA_MODEL,
                **think_opts(),   # Thinking aus - sonst "denkt" der Warmup minutenlang
                "messages":   [{"role": "user", "content": "ping"}],
                "stream":     False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                # num_predict=1: das Modell muss laden, aber nicht
                # nennenswert generieren. Spart ein paar Sekunden ggü.
                # einer vollen Antwort.
                # num_ctx identisch zum Chat-Pfad: sonst laedt der Warmup
                # qwen@default und die erste echte Frage (num_ctx=8192)
                # muss trotzdem neu laden – Warmup waere wirkungslos.
                "options":    {"num_predict": 1, "num_ctx": OLLAMA_NUM_CTX},
            },
            timeout=120,
        )
        state.push_log(f"WARMUP ←  {OLLAMA_MODEL} im RAM")
    except Exception as e:
        state.push_log(f"WARMUP ✗  Chat-Modell-Warmup fehlgeschlagen: {e}")

    # 2. Embed-Modell warmladen
    try:
        import embeddings as _emb
        vec = _emb.embed_query("warmup")
        if vec:
            state.push_log(f"WARMUP ←  {_emb.EMBED_MODEL} im RAM ({len(vec)}-dim)")
        else:
            state.push_log("WARMUP ✗  Embed-Modell antwortete leer")
    except Exception as e:
        state.push_log(f"WARMUP ✗  Embed-Modell-Warmup fehlgeschlagen: {e}")
