# core/billig.py
#
# Ein Einmal-Aufruf beim billigen Modell des aktiven Anbieters — für
# Fleißarbeit, nicht fürs Gespräch: Konzepte aus einem Zug ziehen
# (consolidation), einem Gespräch einen Titel geben (gespraech_titel).
#
# Bis 2026-10-07 stand dieser Aufruf nur im Graph-Extraktor. Der Titel
# brauchte genau dasselbe (beide Dialekte, billiges Modell, kein Effort,
# Kosten buchen) — also steht es jetzt EINMAL hier.
#
# Schicht 3 (KI-Kern): fragt ai_backends nach dem Anbieter.

import os

import ai_backends
import providers
import state


class KeinWeg(RuntimeError):
    """Kein Anbieter oder ein Dialekt, den der Kern nicht spricht."""


def einmal(system, nachricht, *, modell=None, max_tokens=500, vorfuellen=None,
           als_json=False, log="BILLIG", timeout=90):
    """Einen Auftrag schicken, den Text zurückbekommen. -> (text, modell)

    Wirft bei jedem Fehler (Netz, Anbieter, kein Weg) — der Aufrufer
    entscheidet, was dann gilt. Kein Streaming, KEIN effort/temperature:
    die kleinen Modelle (haiku) quittieren beides mit einer 400 (gemessen
    am Graph-Extraktor, 2026-08).

    vorfuellen: Anfang der Antwort (nur Anthropic; zwingt z. B. in JSON).
    Der vorgefüllte Text steht im Ergebnis mit drin.
    als_json: OpenAI-kompatibel response_format json_object."""
    name = ai_backends.cloud_provider() or ""
    prov = providers.get(name)
    mdl = modell or providers.cheap_model(name)
    art = prov.get("kind")

    if art == "anthropic":
        import anthropic  # type: ignore
        client = anthropic.Anthropic()
        msgs = [{"role": "user", "content": nachricht}]
        if vorfuellen:
            msgs.append({"role": "assistant", "content": vorfuellen})
        antwort = client.messages.create(model=mdl, max_tokens=max_tokens,
                                         system=system, messages=msgs)
        text = "".join(b.text for b in antwort.content
                       if getattr(b, "type", None) == "text")
        _buchen(mdl, antwort.usage, log)
        return (vorfuellen or "") + text, mdl

    if art == "openai_compat":
        from openai import OpenAI  # type: ignore
        client = OpenAI(base_url=prov.get("base_url"),
                        api_key=os.environ.get(prov.get("key_env") or "", ""))
        extra = {"response_format": {"type": "json_object"}} if als_json else {}
        resp = client.chat.completions.create(
            model=mdl,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": nachricht}],
            stream=False, timeout=timeout, **extra)
        _buchen(mdl, getattr(resp, "usage", None), log)
        return (resp.choices[0].message.content or "").strip(), mdl

    raise KeinWeg(f"kein Weg für Anbieter {name!r} ({art!r})")


def _buchen(model, verbrauch, log):
    """Den Aufruf mitrechnen. Diese Aufrufe feuern OHNE Sashas Zutun — was
    man nicht sieht, kann man nicht deckeln."""
    if verbrauch is None:
        return
    try:
        import usage
        rein = int(getattr(verbrauch, "input_tokens", 0)
                   or getattr(verbrauch, "prompt_tokens", 0) or 0)
        raus = int(getattr(verbrauch, "output_tokens", 0)
                   or getattr(verbrauch, "completion_tokens", 0) or 0)
        eur = usage.buchen(model, input_tokens=rein, output_tokens=raus)
        state.push_log(f"{log} ← {model} in={rein} out={raus} ≈{eur:.4f}€")
    except Exception as e:
        # Nicht still: eine verlorene Buchung macht den Budget-Deckel blind.
        print(f"[usage] Buchung fehlgeschlagen ({model}): {e}")
