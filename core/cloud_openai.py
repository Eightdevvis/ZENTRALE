# core/cloud_openai.py
#
# Zweites Cloud-Backend des KERNS: alles mit OpenAI-kompatiblem /v1-Endpoint
# (Qwen/DashScope, DeepSeek, Mistral, OpenAI, Groq …). Drop-in für
# ai.chat_stream(), gleiche Signatur, gleiches Event-Protokoll.
#
# ── Warum es das gibt ───────────────────────────────────────────────────
# Der Ziel-Pfad des Kerns ist Anthropic (core/cloud.py). Aber die ganze
# Verkabelung drumherum — Backend-Routing, getrennter Cloud-Graph,
# Event-Protokoll, Erlaubnis-Gate, Tool-Loop, SSE bis in den Browser — ist
# providerunabhängig und lässt sich mit dem Qwen-Key testen, der schon da ist.
# Ein zweiter Provider ist ausserdem der ehrlichere Test der Struktur als ein
# zweiter Mock: erst wenn ein FREMDES Modell durch dieselbe Naht passt, ist
# die Naht wirklich eine.
#
# ── Was hier NICHT geht (bewusst) ───────────────────────────────────────
# * Prompt-Cache mit cache_control — das ist Anthropic-spezifisch. DashScope
#   hat einen impliziten Kontext-Cache, den man nicht steuert. Die
#   Block-Reihenfolge (statisch zuerst) bleibt trotzdem dieselbe: sie hilft
#   jedem impliziten Cache und haelt beide Pfade vergleichbar.
# * thinking/effort — gibt es in diesem Dialekt nicht. Liefert das Modell
#   `reasoning_content` (manche qwen-Varianten tun das), spiegeln wir es als
#   reflect-Event, sonst bleibt das HUD eben still.
# * is_error auf Tool-Ergebnissen — der Dialekt kennt nur role=tool mit Text.
#   Der Fehler geht als Text zurueck, das Modell sieht ihn trotzdem.
#
# ── Isolations-Invariante ───────────────────────────────────────────────
# Wie core/cloud.py: eigener Graph (cloud.CLOUD_GRAPH), damit Sashas
# Konzept-Graph nicht an die API geht. Es ist DERSELBE Cloud-Graph fuer beide
# Provider — die Grenze verlaeuft zwischen "im Haus" und "draussen", nicht
# zwischen zwei Anbietern.
#
# ── Konfiguration ───────────────────────────────────────────────────────
#   ZENTRALE_CLOUD_OPENAI_MODEL       Default: default_model des Providers
#   ZENTRALE_CLOUD_OPENAI_MAX_TOKENS  Default 2000
#   ZENTRALE_CLOUD_OPENAI_TEMP        Default 0.4 (hier ERLAUBT, anders als
#                                     bei Anthropic ab Opus 4.7)

import json as _json
import os

import ai
import cloud      # geteilt: Graph-Pfad, System-Bloecke, run_tool, Gate
import graph
import providers

_MAX_TOKENS = int(os.environ.get("ZENTRALE_CLOUD_OPENAI_MAX_TOKENS", "2000"))
_TEMP       = float(os.environ.get("ZENTRALE_CLOUD_OPENAI_TEMP", "0.4"))
_MAX_ROUNDS = 8

_clients = {}   # base_url → Client (lazy, gecacht)


def _provider(name: str | None = None) -> dict:
    """Provider-Eintrag — Default: der konfigurierte Cloud-Provider."""
    return providers.get(name or providers.configured() or "")


def _get_client(prov: dict):
    """Lazy-Init eines OpenAI-Clients fuer base_url/key des Providers."""
    url = prov.get("base_url") or "default"
    if url not in _clients:
        from openai import OpenAI  # type: ignore – nur im Cloud-Pfad importiert
        key = os.environ.get(prov.get("key_env") or "", "")
        _clients[url] = OpenAI(base_url=prov.get("base_url"),
                               api_key=key or "missing-key")
    return _clients[url]


def is_available(name: str | None = None) -> bool:
    """SDK installiert + Key fuer diesen Provider gesetzt?"""
    prov = _provider(name)
    if prov.get("kind") != "openai_compat":
        return False
    if not os.environ.get(prov.get("key_env") or ""):
        return False
    try:
        import openai  # noqa: F401
        return True
    except Exception:
        return False


def _system_text(system, mem_ctx, via_mic, tutor_mode) -> str:
    """Der statische Kopf — dieselbe Funktion wie im Anthropic-Pfad, damit die
    beiden Dialekte nicht auseinanderlaufen.

    mem_ctx/via_mic werden hier NICHT mehr eingefaltet: das Wechselnde haengt
    seit dem Cache-Umbau hinten an der neuesten User-Nachricht. Explizites
    cache_control gibt es in diesem Dialekt zwar nicht, aber die impliziten
    Praefix-Caches der Anbieter arbeiten nach derselben Logik — was sich
    aendert, gehoert ans Ende, nicht an den Anfang. Die Parameter bleiben in
    der Signatur, damit die Aufrufstelle in beiden Modulen gleich aussieht."""
    return cloud._static_system(system, tutor_mode)


def _log_usage(verbrauch, model: str):
    """Verbrauch + geschätzte Kosten ins Terminal, plus Buchung.

    Dieser Dialekt kennt keine getrennten Cache-Zähler; manche Anbieter
    liefern `prompt_tokens_details.cached_tokens`, viele gar nichts. Wir
    rechnen deshalb konservativ: was nicht ausgewiesen als gecacht gilt, gilt
    als voll bezahlt. Lieber zu hoch schätzen als sich arm rechnen."""
    if verbrauch is None:
        return
    try:
        import state
        import usage
        rein = int(getattr(verbrauch, "prompt_tokens", 0) or 0)
        raus = int(getattr(verbrauch, "completion_tokens", 0) or 0)
        det  = getattr(verbrauch, "prompt_tokens_details", None)
        gecacht = int(getattr(det, "cached_tokens", 0) or 0) if det else 0
        eur = usage.buchen(model, input_tokens=max(rein - gecacht, 0),
                           output_tokens=raus, cache_read=gecacht)
        state.push_log(
            f"CLOUD ← {model} in={rein} cache_read={gecacht} out={raus} "
            f"≈{eur:.4f}€ (heute {usage.heute_euro():.2f}€)")
    except Exception:
        pass


def _prepare_messages(messages: list, system_text: str,
                      volatile: str = "") -> list:
    """Verlauf in OpenAI-Form. `volatile` (Graph, Jetzt, Alarme, Mic) haengt
    hinten an der letzten User-Nachricht statt vorne im System-Prompt — siehe
    cloud._volatile_text."""
    out = [{"role": "system", "content": system_text}]
    for m in (messages or []):
        if m.get("role") in ("user", "assistant") and m.get("content"):
            out.append({"role": m["role"], "content": m["content"]})
    if not any(m["role"] == "user" for m in out):
        out.append({"role": "user", "content": "(kein Text)"})
    if volatile and out[-1]["role"] == "user":
        out[-1] = {"role": "user",
                   "content": f"{out[-1]['content']}\n\n{volatile}"}
    return out


def chat_stream(messages: list, model: str = None, system: str = None,
                tools: list = None, tool_executor=None, via_mic: bool = False,
                *, provider: str = None):
    """
    Drop-in fuer ai.chat_stream() gegen einen OpenAI-kompatiblen Provider.

    Gleiche Signatur und gleiches Event-Protokoll wie core/cloud.py; die
    Bedeutung eines Tool-Calls (terminal? bestaetigungspflichtig?) kommt aus
    cloud.run_tool, damit beide Dialekte nicht auseinanderlaufen.
    """
    prov = _provider(provider)
    if prov.get("kind") != "openai_compat":
        yield f"[Cloud-Fehler: Provider '{provider or providers.configured()}' " \
              f"ist kein OpenAI-kompatibler Endpoint]"
        return

    tutor_mode   = tools is not None
    # Tool-Set von der Schiene, nicht aus ai.TOOLS: dort haengt das
    # Set fuer KLEINE Modelle (siehe core/profil/).
    active_tools = tools if tools is not None else cloud.cloud_tools()
    active_exec  = tool_executor if tool_executor is not None else ai._execute_tool
    store        = None if tutor_mode else cloud.CLOUD_GRAPH

    user_query = ai._last_user_query(messages)

    if tutor_mode:
        mem_ctx = ""
    else:
        cloud.prepare_store()      # Embedder anmelden (derselbe Cloud-Graph)
        ai._ensure_seed_once(store=store)
        mem_ctx = graph.context_for_query(user_query, store=store)

    msgs   = _prepare_messages(
        messages,
        _system_text(system, mem_ctx, via_mic, tutor_mode),
        cloud._volatile_text(mem_ctx, via_mic, tutor_mode))
    client = _get_client(prov)
    # Modell aus derselben Quelle wie beim Anthropic-Pfad: pro Anbieter
    # gespeichert. Sonst gäbe es zwei Wahrheiten darüber, was gerade läuft.
    if model:
        mdl = model
    else:
        import ai_backends
        mdl = ai_backends.chat_model(provider or providers.configured()) \
            or prov.get("default_model")

    for _ in range(_MAX_ROUNDS):
        round_text = []
        tool_calls = {}       # index → {id, name, args}
        verbrauch = None
        try:
            stream = client.chat.completions.create(
                model=mdl,
                messages=msgs,
                tools=active_tools or None,   # ai.TOOLS ist schon OpenAI-Schema
                stream=True,
                temperature=_TEMP,
                max_tokens=_MAX_TOKENS,
                # Verbrauch am Stream-Ende mitschicken lassen — sonst wüssten
                # wir bei jedem Nicht-Anthropic-Anbieter nicht, was der Turn
                # gekostet hat. Anbieter, die das Feld nicht kennen, ignorieren
                # es; deshalb steht es in stream_options und nicht als Pflicht.
                stream_options={"include_usage": True},
            )
            for chunk in stream:
                # Der Usage-Chunk kommt am Ende und hat KEINE choices - er
                # darf nicht als leerer Delta durchrutschen.
                if getattr(chunk, "usage", None):
                    verbrauch = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Manche qwen-Varianten liefern den Denk-Strom getrennt.
                # Wenn ja: ins HUD spiegeln, wie Ollamas thinking-Feld.
                denk = getattr(delta, "reasoning_content", None)
                if denk:
                    yield {"reflect": denk}

                if getattr(delta, "content", None):
                    # NICHT sofort yielden: Text aus einer Runde, die mit
                    # einem Tool-Call endet, ist Geschwaetz ("Ich schau kurz
                    # nach…") und wuerde vorgelesen. Gleiche Entscheidung wie
                    # im lokalen Pfad und in core/cloud.py.
                    round_text.append(delta.content)

                for tc in (getattr(delta, "tool_calls", None) or []):
                    slot = tool_calls.setdefault(
                        tc.index, {"id": None, "name": "", "args": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["args"] += tc.function.arguments
        except Exception as e:
            yield f"[Cloud-Fehler: {e}]"
            return

        _log_usage(verbrauch, mdl)

        if not tool_calls:
            answer = "".join(round_text)
            if tutor_mode:
                if answer:
                    yield answer
            else:
                yield from ai._answer_with_images(answer, user_query, store=store)
            return

        # Assistant-Turn (mit tool_calls) als Kontext anhaengen.
        msgs.append({
            "role":    "assistant",
            "content": "".join(round_text) or None,
            "tool_calls": [{
                "id":   s["id"],
                "type": "function",
                "function": {"name": s["name"], "arguments": s["args"] or "{}"},
            } for s in tool_calls.values()],
        })

        beendet = False
        for s in tool_calls.values():
            try:
                args = _json.loads(s["args"] or "{}")
            except Exception:
                args = {}
            ausgang = yield from cloud.run_tool(
                s["name"], args, tutor_mode=tutor_mode, active_exec=active_exec,
                user_query=user_query, store=store)
            if ausgang[0] == "stop":
                beendet = True
                break
            # Dieser Dialekt kennt keine Fehler-Markierung — der Fehlertext
            # geht als normales Ergebnis zurueck, das Modell sieht ihn trotzdem.
            msgs.append({"role": "tool", "tool_call_id": s["id"],
                         "content": str(ausgang[1])})
        if beendet:
            return

    yield "\n[Maximale Tool-Tiefe erreicht]"
