# ═══════════════════════════════════════════════════════════════════════
# Die Werkzeug-Schleife — EINE für alle drei Wege
# ═══════════════════════════════════════════════════════════════════════
#
# Ein Chat-Zug ist immer dasselbe: Modell fragen → will es Werkzeuge? →
# ausführen (Gate davor) → Ergebnisse zurück → nächste Runde, bis es
# antwortet oder die Grenze erreicht ist. Bis 10/2026 stand diese Schleife
# dreimal da (ai.py lokal, cloud.py Anthropic, cloud_openai.py), und die
# lokale Kopie war schon auseinandergelaufen: keine werkzeug-Events, ein
# krachendes Tool riss den Zug ab, eigener Ablehnungstext.
#
# Jetzt gehört hier alles, was ein Werkzeug-Aufruf BEDEUTET (Runden, Gate,
# terminale Tools, Antwort, Fehler). Ein Weg ist nur noch ein Adapter, der
# drei Dinge kann:
#
#   runde()                    Generator: EIN Modell-Aufruf, reflect-Events
#                              durchreichen, `return Runde(text, calls, roh)`
#   assistent_anhaengen(r)     den Zug des Modells in SEINEM Format anhängen
#   ergebnisse_anhaengen(liste) [(call_id, text, is_error)] in seinem Format
#
# dazu das Attribut `modell`: danach richtet sich die Rundengrenze
# (ai_backends.runden_grenze — pro Modell, Standard 8).
#
# Wie der Prompt gebaut wird, bleibt ganz beim Weg: Schiene, Cache und
# Graph-Store sind gewollt verschieden.
#
# ── Fehler ──────────────────────────────────────────────────────────────
# Fehler und die Rundengrenze gehen als eigenes Event {"fehler": text}
# raus, NICHT als Antworttext. Vorher stand "[Cloud-Fehler: …]" danach im
# Verlauf, als hätte die KI das gesagt — und die nächste Runde las es als
# ihre eigene Aussage. app.py reicht das Event als SSE 'fehler' an die TUI
# (Statuszeile) und speichert es nicht.

from dataclasses import dataclass, field

import ai_backends
import erlaubnis
import ki_antwort
import kidebug


@dataclass
class Runde:
    """Was ein Modell-Aufruf zurückbrachte."""
    text: str
    calls: list = field(default_factory=list)   # [(call_id, name, args_dict)]
    roh: object = None                          # Adapter-privat (z.B. Anthropic-Message)


class Abbruch(Exception):
    """Ein Adapter bricht den Zug mit einer Meldung an Sasha ab (z.B. die
    Cloud hat die Anfrage abgelehnt). Der Text geht wörtlich ins fehler-Event."""


def fehler(text: str) -> dict:
    return {"fehler": text}


def laufen(adapter, *, tutor_mode: bool, active_exec, user_query, store=None,
           fehler_name: str = "Cloud"):
    """
    Der ganze Zug. Generator — yieldet dieselben Events wie bisher
    chat_stream (Text-Tokens, reflect, werkzeug, permission, ascii, cinema)
    plus {"fehler": …}.

    tutor_mode: fremdes Tool-Set → kein Gate, keine terminalen Kern-Tools,
    Antwort roh statt mit Bild-Markern.
    fehler_name: wer gescheitert ist, für die Meldung ("Cloud", "Ollama").
    """
    grenze = ai_backends.runden_grenze(adapter.modell)
    for _ in range(grenze):
        try:
            runde = yield from adapter.runde()
        except Abbruch as e:
            yield fehler(str(e))
            return
        except Exception as e:
            yield fehler(f"{fehler_name}-Fehler: {e}")
            return

        if not runde.calls:
            yield from antwort(runde.text, tutor_mode=tutor_mode,
                               user_query=user_query, store=store)
            return

        adapter.assistent_anhaengen(runde)
        ergebnisse = []
        for call_id, name, args in runde.calls:
            ausgang = yield from run_tool(
                name, args, tutor_mode=tutor_mode, active_exec=active_exec,
                user_query=user_query, store=store)
            if ausgang[0] == "stop":
                return
            _, text, ist_fehler = ausgang
            ergebnisse.append((call_id, text, ist_fehler))
        adapter.ergebnisse_anhaengen(ergebnisse)

    yield fehler(f"Maximale Tool-Tiefe erreicht ({grenze} Runden) — "
                 f"sie hat nicht zu Ende geantwortet.")


def antwort(text: str, *, tutor_mode: bool, user_query, store=None):
    """Die finale Antwort ausgeben. Regulärer Chat: Bild-Marker rausziehen,
    Bilder feuern, Auto-Save (ki_antwort.mit_bildern). Tutor: roh."""
    if tutor_mode:
        if text:
            yield text
        return
    yield from ki_antwort.mit_bildern(text, user_query, store=store)


# ── Ein Tool-Call ──────────────────────────────────────────────────────

def run_tool(name: str, args: dict, *, tutor_mode: bool, active_exec,
             user_query, store=None):
    """
    Behandelt EINEN Tool-Call: terminale Tools, Knopf-Dialog, Erlaubnis-Gate,
    Ausführung. Generator — yieldet die Events, mit `yield from` aufrufen.

    Rückgabe:
      ("stop",)                  Turn ist zu Ende (terminales Tool hat die
                                 Antwort schon geyieldet)
      ("result", text, is_error) Ergebnis, das als Tool-Ergebnis zurück soll
    """
    import profil
    # Auf das Vokabular des Kerns bringen — welche Schiene ihr Tool wie nennt,
    # ist ihre Sache (siehe core/profil/). Der ausfuehrende Name bleibt der
    # kanonische, auch fuer den Gate-Text.
    name = profil.kanonisch(name)

    # ── Sichtbar machen, was sie tut ──────────────────────────────────
    # Sasha, 20.08.2026: "machen wir im normalen chat einfach die tool calls
    # usw details was sie macht wie tool call, thinking, usw einfach alle
    # transparent und sichtbar, so wie man es bei dir claude sieht! das wird
    # schon helfen. weil keine ahnung was sie hier fabriziert hat."
    #
    # Der Anlass war ein Turn, in dem sie zweimal schrieb und beide Male nur
    # "steht drin" sagte — von aussen sah das aus wie eine Luege beim ersten
    # Mal. Wer sieht, WELCHES Werkzeug mit WELCHEN Argumenten lief, muss das
    # nicht mehr raten. Seit der gemeinsamen Schleife auch lokal.
    yield {"werkzeug": {"phase": "start", "name": name, "args": args}}

    # antwort-Tool ist TERMINAL: der Text IST die finale Antwort.
    if not tutor_mode and name == "antwort":
        text = str(args.get("text", "")).strip()
        yield from ki_antwort.mit_bildern(text, user_query, store=store)
        return ("stop",)

    # read_news ist TERMINAL: das Briefing ist schon moderiert und wird
    # direkt gestreamt, statt es nacherzählen zu lassen. KEIN Auto-Save:
    # Welt-News gehören nicht ins Gedächtnis.
    if not tutor_mode and name == "read_news":
        yield {"cinema": True}
        show = active_exec(name, args)
        # Meta-Kopf ("Sendung (Stand …):") wegschneiden - der gesprochene
        # Broadcast soll mit dem Moderationstext beginnen, nicht mit Meta.
        if show.startswith("Sendung (Stand") and "\n\n" in show:
            show = show.split("\n\n", 1)[1]
        yield show
        return ("stop",)

    # ask_choice: die KI baut selbst einen Knopf-Dialog.
    if not tutor_mode and name == "ask_choice":
        wahl = yield from _ask_buttons(args)
        return ("result", f"Sasha hat gewählt: {wahl}.", False)

    # Erlaubnis-Gate: Python-seitig, NICHT modellgetrieben. Fremde Tool-Sets
    # (Tutor) gaten wir nicht.
    if not tutor_mode and erlaubnis.braucht_erlaubnis(name, args):
        erlaubt = yield from _ask_permission(name, args)
        if not erlaubt:
            # Der zweite Satz galt bis 10/2026 nur lokal. Der Fall ist aber
            # überall derselbe: sie notiert "Zahnarzt eingetragen" und ruft im
            # selben Zug das Eintragen, das Sasha dann ablehnt.
            return ("result",
                    f"Sasha hat die Aktion '{name}' abgelehnt - NICHT "
                    f"ausführen, nichts eintragen. Kurz bestätigen dass du "
                    f"es lässt. Und falls du in derselben Runde schon "
                    f"irgendwo notiert hast, dass es passiert sei: schreib "
                    f"die Richtigstellung hinterher, sonst steht eine "
                    f"Unwahrheit im Gedächtnis.", False)

    # Ein krachendes Tool darf den Turn nicht abreißen: die Runde ist bezahlt.
    # Das Modell soll den Fehler SEHEN und reagieren können, statt zu
    # behaupten, es hätte funktioniert.
    try:
        ergebnis = active_exec(name, args)
        kidebug.emit("ai.tool", name=name, args=args, ergebnis=str(ergebnis))
        yield {"werkzeug": {"phase": "fertig", "name": name,
                            "text": str(ergebnis)}}
        return ("result", ergebnis, False)
    except Exception as e:
        kidebug.emit("ai.tool", name=name, args=args, fehler=str(e))
        yield {"werkzeug": {"phase": "fehler", "name": name, "text": str(e)}}
        return ("result", f"Tool '{name}' ist fehlgeschlagen: {e}", True)


def _ask_buttons(args: dict):
    """frage_knopf: Knopf-Dialog auslösen, blockieren, Wahl zurückgeben.
    Generator (yieldet das permission-Event) — mit `yield from` aufrufen."""
    import state
    frage = str(args.get("frage", "")).strip() or "Wie soll ich weitermachen?"
    opts  = [str(o).strip() for o in (args.get("optionen") or []) if str(o).strip()]
    if len(opts) < 2:
        opts = ["ja", "nein"]
    opts = opts[:4]                       # Leiste fasst max 4 Knöpfe sauber
    state.push_log(f"AI →  FRAGE {opts}: {frage[:140]}")
    state.request_permission(options=opts, timeout_default="(keine Antwort)")
    yield {"permission": {"frage": frage, "optionen": opts}}
    wahl = state.wait_permission()        # BLOCKIERT bis Klick/Timeout
    state.push_log(f"AI ←  WAHL: {wahl}")
    return wahl


def _ask_permission(name: str, args: dict):
    """Erlaubnis-Gate: JA/NEIN-Dialog vor einem schreibenden Tool.
    Generator — mit `yield from` aufrufen. True = ausführen."""
    import state
    frage = erlaubnis.frage(name, args)
    state.push_log(f"AI →  ERLAUBNIS? {frage[:160]}")
    state.request_permission()
    yield {"permission": {"frage": frage}}
    antwort_ = state.wait_permission()    # BLOCKIERT bis Klick/Timeout
    state.push_log(f"AI ←  ERLAUBNIS: {antwort_}")
    return antwort_ == "ja"
