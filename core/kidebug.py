# core/kidebug.py
#
# Devtools-Ereignisbus für die KERN-KI. Sammelt zeitgestempelte Debug-Events
# und streamt sie an ein Terminal (scripts/ai_devtools.py über SSE:
# GET /api/ai/debug/stream).
#
# ── Warum es das braucht ────────────────────────────────────────────────
# Im Dashboard-Log steht, WAS gekostet hat (`CLOUD ← claude-sonnet-5 in=250
# cache_read=5464 …`) und DASS ein Tool lief. Was tatsächlich rausgeht — der
# vollständige System-Prompt, der Graph-Kontext, das Tool-Schema, die
# Reihenfolge der Blöcke, wo die Cache-Breakpoints sitzen — sieht man nirgends.
# Seit es zwei Prompt-Schienen gibt (core/profil/), ist genau das die Frage,
# die man ständig hat: was schickt `gross` da eigentlich?
#
# ── Verhältnis zu tutor/debug.py ────────────────────────────────────────
# Gleiche Bauart, bewusst eine eigene Datei. Der Tutor ist ein Addon und muss
# am Stück rausziehbar bleiben (core/tutor_port.py ist die einzige Naht) — der
# Kern darf nicht aus tutor/ importieren. Dieselbe Entscheidung wie bei
# providers.py vs. tutor_providers.py: lieber zwei kleine Busse als einer, an
# dem beide zerren.
#
# ── Events ──────────────────────────────────────────────────────────────
#   ai.req   Was die KI KRIEGT: Modell, Schiene, kompletter System-Prompt,
#            alle Messages, Tool-Namen, Cache-Breakpoints.
#   ai.out   Was sie AUSGIBT: Roh-Text, stop_reason, Token-Verbrauch.
#   ai.tool  Jeder Tool-Call: Name, Argumente, Ergebnis.
#   ai.graph Was der Extraktor in den Graphen geschrieben hat.
#
# ── Robustheit ──────────────────────────────────────────────────────────
# Ring-Puffer (Historie, auch ohne Zuhörer) + Subscriber-Queues. `emit()`
# schluckt JEDEN Fehler: ein Debug-Kanal, der das Gespräch abreißen lässt, ist
# schlimmer als gar keiner.
#
# ── Was hier rausgeht ───────────────────────────────────────────────────
# ALLES. Der volle Prompt enthält den Graph-Kontext, also Sashas Zustände und
# Erlebnisse. Der Stream ist so privat wie der Graph selbst und gehört nicht
# über eine offene Schnittstelle — er läuft über dieselbe lokale API wie der
# Rest (siehe memory/betrieb/sicherheit.md).

import hashlib
import json
import os
import queue
import threading
import time
from collections import deque

# Aus. Der Bus kostet fast nichts, aber „fast nichts" mal jedem Turn ist auch
# etwas — und der volle Prompt im Speicher zu halten ist nur sinnvoll, wenn
# jemand zuschaut. ZENTRALE_AI_DEBUG=1 schaltet ihn scharf; das Devtools-
# Terminal schaltet ihn beim Verbinden von selbst ein.
_AN = os.environ.get("ZENTRALE_AI_DEBUG", "0") != "0"

_LOCK = threading.Lock()
_BUF  = deque(maxlen=500)     # jüngste Events (Historie beim Öffnen)
_TOOLS_FP = None              # Fingerabdruck des zuletzt AUSGESCHRIEBENEN
                              # Werkzeug-Satzes (siehe request())
_SUBS = []                    # aktive Devtools-Verbindungen (queue.Queue)


def an() -> bool:
    return _AN


def einschalten(wert: bool = True) -> bool:
    """Bus scharf schalten. Das Devtools-Terminal ruft das beim Verbinden."""
    global _AN
    _AN = bool(wert)
    return _AN


def _ts() -> str:
    t = time.time()
    return (time.strftime('%H:%M:%S', time.localtime(t))
            + ('.%03d' % int((t % 1) * 1000)))


def emit(kind: str, **fields):
    """Ein Event ablegen + an alle Zuhörer schicken. Darf NIE werfen."""
    if not _AN:
        return None
    try:
        ev = {'ts': _ts(), 'kind': kind}
        ev.update(fields)
        with _LOCK:
            _BUF.append(ev)
            subs = list(_SUBS)
        for q in subs:
            try:
                q.put_nowait(ev)
            except Exception:
                pass          # langsamer Zuhörer verliert Events, nicht der Chat
        return ev
    except Exception:
        return None


def history() -> list:
    with _LOCK:
        return list(_BUF)


def subscribe():
    # Der Merker wird zurueckgesetzt: ein frisch verbundenes Devtools hat die
    # Schemata noch nie gesehen, auch wenn sie vor Stunden schon mal durch den
    # Puffer liefen. Sonst haette ausgerechnet die erste Sitzung nichts.
    global _TOOLS_FP
    q = queue.Queue(maxsize=2000)
    with _LOCK:
        _TOOLS_FP = None
        _SUBS.append(q)
    return q


def unsubscribe(q) -> None:
    with _LOCK:
        if q in _SUBS:
            _SUBS.remove(q)


# ── Formatierung: aus einem Request ein lesbares Event machen ───────────

def _text_von_block(b) -> str:
    """Ein Content-Block als Text — egal ob dict (Anthropic) oder String."""
    if isinstance(b, str):
        return b
    if isinstance(b, dict):
        if b.get("type") == "text":
            return b.get("text", "")
        if b.get("type") == "tool_result":
            return f"[tool_result {b.get('tool_use_id','')}] {b.get('content','')}"
        if b.get("type") == "tool_use":
            return f"[tool_use {b.get('name','')}] {b.get('input','')}"
        return str(b)
    # SDK-Objekte (assistant-Turns kommen als solche zurück)
    typ = getattr(b, "type", None)
    if typ == "text":
        return getattr(b, "text", "")
    if typ == "thinking":
        return "[denken] " + (getattr(b, "thinking", "") or "")
    if typ == "tool_use":
        return f"[tool_use {getattr(b,'name','')}] {getattr(b,'input','')}"
    return str(b)


def request(*, modell: str, schiene: str, system, messages, tools) -> None:
    """Einen ausgehenden Request als ai.req-Event ablegen.

    Nimmt beide Dialekte an: `system` als Block-Liste (Anthropic) oder String
    (OpenAI-kompatibel), `messages` mit Block-Listen oder Strings.
    """
    if not _AN:
        return
    try:
        if isinstance(system, str):
            bloecke = [{"text": system, "cache": False}]
        else:
            bloecke = [{"text": b.get("text", ""),
                        "cache": bool(b.get("cache_control"))}
                       for b in (system or [])]

        msgs = []
        for m in (messages or []):
            c = m.get("content")
            teile = c if isinstance(c, list) else [c]
            msgs.append({
                "rolle": m.get("role", "?"),
                "bloecke": [{"text": _text_von_block(b),
                             "cache": bool(isinstance(b, dict)
                                           and b.get("cache_control"))}
                            for b in teile],
            })

        # Werkzeuge: bis 18.08.2026 gingen hier nur die NAMEN raus. Damit log
        # die Devtools ihren eigenen Anspruch — die Beschreibungen sind das,
        # woraus die KI ableitet, wann sie was nimmt, und sie sind ein
        # betraechtlicher Teil des gecachten Prefix. Wer wissen will, warum
        # sie zum falschen Werkzeug greift, muss genau das lesen koennen.
        #
        # Ausgeschrieben werden sie aber nur, wenn sich der Satz seit dem
        # letzten Request geaendert hat. Er ist statisch; ihn 500-mal in einen
        # Puffer von 500 Events zu legen hiesse, alles andere daraus zu
        # verdraengen. `tools_voll=None` heisst darum "unveraendert", nicht
        # "nicht verfuegbar".
        global _TOOLS_FP
        namen, voll = [], []
        for t in (tools or []):
            fn = t.get("function", t) if isinstance(t, dict) else {}
            namen.append(fn.get("name", "?"))
            voll.append({"name":        fn.get("name", "?"),
                         "beschreibung": fn.get("description", ""),
                         "parameter":   fn.get("parameters") or {}})
        fp = hashlib.sha1(
            json.dumps(voll, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:12]
        neuer_satz = fp != _TOOLS_FP
        _TOOLS_FP = fp

        emit("ai.req", modell=modell, schiene=schiene,
             system=bloecke, messages=msgs, tools=namen,
             tools_fp=fp, tools_voll=(voll if neuer_satz else None))
    except Exception:
        pass
