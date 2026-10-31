# core/consolidation.py
#
# What stays behind after a chat turn: the raw text in the transcript
# (core/transkript.py), read by search_chats (core/chat_suche.py).
#
# zug_vormerken (below) queues every turn; the worker writes them in a batch
# in the next pause of the conversation (CONSOLIDATION_IDLE_S without a new
# turn). Trivial turns ("hi", "ok", emoji) are skipped.
#
# History: the file is named after the concept graph (Phase G). Until
# 18.08.2026 the worker also ran an LLM extractor that turned every turn into
# graph triples; off since then, and the graph code was removed on
# 2026-10-31 (why: memory/ki/gedaechtnis_dateien.md, archive:
# memory/archive/associative_graph/). Only the transcript part is left.

import os
import threading
import time

import transkript            # raw material, append-only


def _is_substantive(user_msg: str) -> bool:
    """Is the turn worth keeping? Skips "hi", "ok", pure emoji and
    single-word replies.

    Heuristic: at least 8 alphanumeric characters AND at least 2 separate
    words with letters."""
    if not user_msg:
        return False
    alpha_chars = sum(1 for c in user_msg if c.isalnum())
    if alpha_chars < 8:
        return False
    word_count = sum(1 for w in user_msg.split() if any(c.isalpha() for c in w))
    if word_count < 2:
        return False
    return True


def record_turns(user_msg, ai_msg=None, store: str | None = None) -> list[str]:
    """Write one turn, or a batch [(user, ai), ...], to the transcript.

    store: truthy → the cloud transcript (`cloud-YYYY-MM.jsonl`), None → the
    local one. Local and cloud turns never mix. Returns the transcript ids."""
    if isinstance(user_msg, (list, tuple)):
        turns = [((u or '').strip(), (a or '').strip()) for u, a in user_msg]
        turns = [(u, a) for u, a in turns if _is_substantive(u)]
    else:
        user_msg = (user_msg or '').strip()
        ai_msg   = (ai_msg   or '').strip()
        turns = [(user_msg, ai_msg)] if _is_substantive(user_msg) else []
    if not turns:
        return []
    return transkript.schreiben(turns, store=store)


# ── Batched in the pause of the conversation ───────────────────────────
# One worker thread collects the turns and writes them only once
# CONSOLIDATION_IDLE_S passed without a new turn. Every turn pushes the
# deadline back. (The batching was built for the expensive graph extractor,
# which shared the one local model with the chat; it is kept so the
# transcript behaves exactly as before.)
CONSOLIDATION_IDLE_S = float(os.environ.get("CONSOLIDATION_IDLE_S", "45"))

_consol_pending = []                      # [(user_msg, ai_msg, store), ...]
_consol_cv      = threading.Condition()   # guards _consol_pending + _consol_last_ts
_consol_last_ts = 0.0                      # monotonic time of the last turn
_consol_started = False                    # worker started yet?


def _consolidation_worker():
    """Single worker: waits for turns, writes them after CONSOLIDATION_IDLE_S
    of quiet, never in parallel. Daemon thread for the whole app runtime."""
    while True:
        with _consol_cv:
            while not _consol_pending:
                _consol_cv.wait()
            while True:
                rest = CONSOLIDATION_IDLE_S - (time.monotonic() - _consol_last_ts)
                if rest <= 0:
                    break
                _consol_cv.wait(timeout=rest)
            # Grouped by store: local and cloud turns must never mix.
            buendel = _buendel_schnueren(_consol_pending)
            _consol_pending.clear()
        for store, turns in buendel.items():
            try:
                record_turns(turns, None, store=store)
            except Exception as e:
                try:
                    import state
                    state.push_log(f"[auto-save] FEHLER: {e}")
                except Exception:
                    pass


def zug_vormerken(user_msg: str, ai_msg: str, store: str | None = None):
    """Queue a turn for the transcript and return at once.

    store: None = local transcript; the cloud path passes its own marker
    (cloud.CLOUD_STORE) so cloud turns never land in the local file."""
    global _consol_last_ts, _consol_started
    if not user_msg or not user_msg.strip():
        return

    with _consol_cv:
        # Start the worker lazily (no side effect on import).
        if not _consol_started:
            _consol_started = True
            threading.Thread(target=_consolidation_worker, daemon=True,
                             name='ai-consolidation').start()
        _consol_pending.append((user_msg, ai_msg, store))
        _consol_last_ts = time.monotonic()   # reset the debounce deadline
        _consol_cv.notify()


def _buendel_schnueren(pending):
    """Group queued turns by store: {store: [(user, ai), ...]}.

    Its own function so the test checks the REAL grouping."""
    buendel = {}
    for u, a, s in pending:
        buendel.setdefault(s, []).append((u, a))
    return buendel
