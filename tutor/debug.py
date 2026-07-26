# tutor/debug.py
#
# Devtools-Ereignisbus für den Tutor. Sammelt ZEITGESTEMPELTE Debug-Events und
# streamt sie an ein Devtools-Terminal (scripts/tutor_devtools.py über SSE:
# GET /api/tutor/debug/stream). Was geloggt wird:
#   • vocab   — jede Statusänderung einer Vokabel (neu / wacklig / fest, correct_use)
#   • ai.req  — was die KI KRIEGT: voller System-Prompt + Messages + Tools + Modell
#   • ai.out  — was die KI AUSGIBT: die ROH-Antwort (inkl. dem, was das Zimmer sonst
#               versteckt — (Regie-Klammern), geleakte Tool-Zeilen …)
#   • ai.tool — jeder Tool-Call der KI: Name, Args, Ergebnis
# Der Snapshot beim Verbinden (User-Vokabel + Assessment-Routing) kommt aus
# tools.debug_snapshot(); der SSE-Endpunkt schickt ihn zuerst.
#
# Billig + robust: Ring-Puffer (Historie, auch ohne Zuhörer) + Subscriber-Queues.
# emit() schluckt jeden Fehler — Debug darf die echte Logik NIE stören.

import time
import threading
import queue
from collections import deque

_LOCK = threading.Lock()
_BUF = deque(maxlen=3000)     # jüngste Events (Historie beim Öffnen)
_SUBS = []                    # aktive Devtools-Verbindungen (queue.Queue)


def _ts() -> str:
    t = time.time()
    return time.strftime('%H:%M:%S', time.localtime(t)) + ('.%03d' % int((t % 1) * 1000))


def emit(kind: str, **fields):
    """Ein Event ablegen + an alle Zuhörer schicken. Darf nie werfen."""
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
                pass
        return ev
    except Exception:
        return None


def history() -> list:
    with _LOCK:
        return list(_BUF)


def subscribe():
    q = queue.Queue(maxsize=8000)
    with _LOCK:
        _SUBS.append(q)
    return q


def unsubscribe(q):
    with _LOCK:
        try:
            _SUBS.remove(q)
        except ValueError:
            pass
