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
# ihre eigene Aussage. ui/routen/ki.py reicht das Event als SSE 'fehler' an die TUI
# (Statuszeile) und speichert es nicht.

from dataclasses import dataclass, field

import ai_backends
import erlaubnis
import ki_antwort
import kidebug
import werkzeug_befund
import werkzeug_register
import zug_ablauf
from werkzeug_befund import Befund


@dataclass
class Runde:
    """Was ein Modell-Aufruf zurückbrachte."""
    text: str
    calls: list = field(default_factory=list)   # [(call_id, name, args_dict)]
    roh: object = None                          # Adapter-privat (z.B. Anthropic-Message)


class Gestoppt(Exception):
    """Sasha hat gestoppt (Abbruch-Signal, state.chat_zug_stoppen). Ein
    Adapter wirft das, sobald er es mitten im Strom merkt, NACHDEM er den
    Strom geschlossen und das bis dahin Verbrauchte gebucht hat. `text` ist,
    was das Modell in dieser Runde bis dahin geschrieben hatte."""

    def __init__(self, text: str = ""):
        super().__init__("gestoppt")
        self.text = text or ""


def gestoppt(abbruch) -> bool:
    """Ist das Abbruch-Signal gesetzt? abbruch: threading.Event oder None
    (None = dieser Zug ist nicht stoppbar, z. B. Tutor, Takt)."""
    return abbruch is not None and abbruch.is_set()


GESTOPPT = {"gestoppt": True}


class Abbruch(Exception):
    """Ein Adapter bricht den Zug mit einer Meldung an Sasha ab (z.B. die
    Cloud hat die Anfrage abgelehnt). Der Text geht wörtlich ins fehler-Event."""


def fehler(text: str) -> dict:
    return {"fehler": text}


def laufen(adapter, *, tutor_mode: bool, active_exec, user_query, store=None,
           fehler_name: str = "Cloud", abbruch=None, schiene: str = "klein",
           pruefer=None):
    """
    Der ganze Zug. Generator — yieldet dieselben Events wie bisher
    chat_stream (Text-Tokens, reflect, werkzeug, permission, ascii, cinema)
    plus {"fehler": …}.

    tutor_mode: fremdes Tool-Set → kein Gate, keine terminalen Kern-Tools,
    Antwort roh statt mit Bild-Markern.
    fehler_name: wer gescheitert ist, für die Meldung ("Cloud", "Ollama").
    abbruch: threading.Event (Stoppen, 2026-10-07) — geprüft vor jeder Runde
    und vor jedem Werkzeug; mitten im Strom prüft es der Adapter selbst.
    Gestoppt → {"gestoppt": True}, keine weitere Runde, nichts gemerkt.
    schiene: klein/gross (2026-10-08) — die Ausführer erfahren sie über
    werkzeug_befund.schiene() (Kennungen im Kalender nur auf gross).
    pruefer: ehrlichkeit.Pruefer oder None (2026-10-09) — sieht jedes
    Werkzeug-Ergebnis, prüft die fertige Antwort (eine Korrekturrunde, bevor
    Sasha sie sieht, über adapter.hinweis_anhaengen) und liefert am Ende das
    Ereignis {"ehrlichkeit": …} (Erledigt-Zeile, Befunde, offene Zusagen).
    """
    # Ablauf-Protokoll (core/zug_ablauf.py, 2026-10-09): nur mitschreiben,
    # was ohnehin passiert — Text zwischen Werkzeugen, Aufrufe mit Ergebnis,
    # Prüfung, Ende. Ohne offenes Protokoll (lokal, Takt) tut es nichts.
    grenze = ai_backends.runden_grenze(adapter.modell)
    for nr in range(grenze):
        if gestoppt(abbruch):
            zug_ablauf.gestoppt()
            yield dict(GESTOPPT)
            return
        try:
            runde = yield from adapter.runde()
        except Gestoppt as g:
            # Was sie bis dahin geschrieben hatte, roh raus: es soll mit dem
            # Vermerk im Verlauf stehen, aber nicht als fertige Antwort
            # gemerkt werden (kein ki_antwort.mit_bildern).
            if g.text.strip():
                yield g.text
            zug_ablauf.gestoppt()
            yield dict(GESTOPPT)
            return
        except Abbruch as e:
            zug_ablauf.fehler(str(e))
            yield fehler(str(e))
            return
        except Exception as e:
            zug_ablauf.fehler(f"{fehler_name}-Fehler: {e}")
            yield fehler(f"{fehler_name}-Fehler: {e}")
            return

        if not runde.calls:
            if pruefer is not None and hasattr(adapter, "hinweis_anhaengen"):
                korrektur = pruefer.nach_antwort(runde.text,
                                                 letzte_runde=(nr >= grenze - 1))
                if korrektur:
                    # Die Antwort geht NICHT raus (der Adapter puffert den
                    # Text einer Runde); die KI bekommt den Befund und
                    # schreibt sie neu — oder ruft jetzt das Werkzeug.
                    zug_ablauf.pruefung(pruefer.befunde, korrektur, runde.text)
                    adapter.hinweis_anhaengen(runde, korrektur)
                    continue
            yield from antwort(runde.text, tutor_mode=tutor_mode,
                               user_query=user_query, store=store)
            schluss = pruefer.abschluss(runde.text) if pruefer is not None else None
            if schluss:
                yield schluss
            return

        adapter.assistent_anhaengen(runde)
        zug_ablauf.text(runde.text)          # Vorgeplänkel, das der Chat nicht zeigt
        ergebnisse = []
        for call_id, name, args in runde.calls:
            if gestoppt(abbruch):
                zug_ablauf.gestoppt()
                yield dict(GESTOPPT)
                return
            spur = zug_ablauf.werkzeug_beginnt(_kanonisch(name), args)
            ausgang = yield from run_tool(
                name, args, tutor_mode=tutor_mode, active_exec=active_exec,
                user_query=user_query, store=store, schiene=schiene)
            if ausgang[0] == "stop":
                zug_ablauf.werkzeug_fertig(
                    spur, "(beendet den Zug — was es lieferte, ist die Antwort)",
                    status="ok")
                return
            _, text, ist_fehler = ausgang
            zug_ablauf.werkzeug_fertig(spur, text, ist_fehler)
            if pruefer is not None:
                pruefer.werkzeug(name, args, text, ist_fehler)
            ergebnisse.append((call_id, text, ist_fehler))
        adapter.ergebnisse_anhaengen(ergebnisse)

    schluss = pruefer.abschluss(None) if pruefer is not None else None
    if schluss:
        # Gerade dann zählt die Erledigt-Zeile: was bis zur Grenze geschrieben
        # wurde, steht sonst nirgends.
        yield schluss
    meldung = (f"Maximale Tool-Tiefe erreicht ({grenze} Runden) — "
               f"sie hat nicht zu Ende geantwortet.")
    zug_ablauf.fehler(meldung)
    yield fehler(meldung)


def _kanonisch(name: str) -> str:
    """Der Name, wie run_tool ihn ausführt (für das Ablauf-Protokoll)."""
    import profil
    try:
        return profil.kanonisch(name)
    except Exception:
        return name


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
             user_query, store=None, schiene: str = "klein"):
    """
    Behandelt EINEN Tool-Call: terminale Tools, Knopf-Dialog, Erlaubnis-Gate,
    Ausführung. Generator — yieldet die Events, mit `yield from` aufrufen.

    Rückgabe:
      ("stop",)                  Turn ist zu Ende (terminales Tool hat die
                                 Antwort schon geyieldet)
      ("result", text, is_error) Ergebnis, das als Tool-Ergebnis zurück soll

    Seit 2026-10-08 beginnt jedes Ergebnis an das Modell mit der Kopfzeile
    „[ergebnis: ok|fehlgeschlagen|keine_antwort|abgelehnt]"
    (core/werkzeug_befund.py) — außer im Tutor (fremdes Tool-Set).
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

    # Werkzeuge, die die Schleife SELBST erledigt (antwort, ask_choice), und
    # terminale mit Ausführer (read_news): welche das sind, sagt das Register
    # (in_der_schleife, terminal) — seit 2026-10-07, vorher stand hier jeder
    # Name einzeln. Fremde Tool-Sets (Tutor) kennen das Register nicht.
    w = None if tutor_mode else werkzeug_register.eintrag(name)
    if w is not None and w.in_der_schleife:
        return (yield from SELBST[w.name](args, user_query=user_query, store=store))
    if w is not None and w.terminal:
        return (yield from _terminal_ausgeben(name, args, active_exec))

    # Erlaubnis-Gate: Python-seitig, NICHT modellgetrieben. Fremde Tool-Sets
    # (Tutor) gaten wir nicht.
    if not tutor_mode and erlaubnis.braucht_erlaubnis(name, args):
        erlaubt = yield from _ask_permission(name, args)
        if not erlaubt:
            # Der zweite Satz galt bis 10/2026 nur lokal. Der Fall ist aber
            # überall derselbe: sie notiert "Zahnarzt eingetragen" und ruft im
            # selben Zug das Eintragen, das Sasha dann ablehnt.
            return ("result", werkzeug_befund.mit_kopf(Befund(
                    f"Sasha hat die Aktion '{name}' abgelehnt - NICHT "
                    f"ausführen, nichts eintragen. Kurz bestätigen dass du "
                    f"es lässt. Und falls du in derselben Runde schon "
                    f"irgendwo notiert hast, dass es passiert sei: schreib "
                    f"die Richtigstellung hinterher, sonst steht eine "
                    f"Unwahrheit im Gedächtnis.", werkzeug_befund.ABGELEHNT)), False)

    # Ein krachendes Tool darf den Turn nicht abreißen: die Runde ist bezahlt.
    # Das Modell soll den Fehler SEHEN und reagieren können, statt zu
    # behaupten, es hätte funktioniert.
    marke = werkzeug_befund.schiene_setzen(schiene)
    try:
        ergebnis = active_exec(name, args)
    except Exception as e:
        kidebug.emit("ai.tool", name=name, args=args, fehler=str(e))
        yield {"werkzeug": {"phase": "fehler", "name": name, "text": str(e)}}
        text = f"Tool '{name}' ist fehlgeschlagen: {e}"
        if not tutor_mode:
            text = werkzeug_befund.mit_kopf(werkzeug_befund.abgebrochen(
                f"Werkzeug {name}", "W-AUSNAHME", str(e),
                "ob es etwas geändert hat, ist nicht belegt — nachlesen"))
        return ("result", text, True)
    finally:
        werkzeug_befund.schiene_zuruecksetzen(marke)
    kidebug.emit("ai.tool", name=name, args=args, ergebnis=str(ergebnis))
    status = werkzeug_befund.status_von(ergebnis)
    yield {"werkzeug": {"phase": "fertig", "name": name,
                        "text": str(ergebnis), "status": status}}
    if tutor_mode:
        return ("result", ergebnis, False)
    return ("result", werkzeug_befund.mit_kopf(ergebnis), False)


# ── Was die Schleife selbst erledigt ───────────────────────────────────

def _antwort_werkzeug(args: dict, *, user_query, store=None):
    """antwort (nur klein) ist TERMINAL: der Text IST die finale Antwort."""
    text = str(args.get("text", "")).strip()
    yield from ki_antwort.mit_bildern(text, user_query, store=store)
    return ("stop",)


def _knopf_werkzeug(args: dict, *, user_query, store=None):
    """ask_choice: die KI baut selbst einen Knopf-Dialog.

    Keine Antwort (Zeit um, gestoppt, oder eine Antwort, die keiner der
    Knöpfe ist) heißt für die KI: nichts ändern, was davon abhängt, im Text
    nachfragen (2026-10-08). Vorher stand dort „Sasha hat gewählt: None." —
    das liest sich wie eine Wahl. Das Ergebnis geht jetzt auch als
    werkzeug-Event raus, damit es im Verlauf steht (vorher fehlte es dort,
    und wer nachlas, sah bei ask_choice kein Ergebnis)."""
    wahl, opts = yield from _ask_buttons(args)
    if wahl is None or str(wahl) not in opts:
        frage = str(args.get("frage", "")).strip()
        befund = Befund(
            f"Sasha hat NICHT geantwortet (Frage: „{frage[:160]}“). Er hat "
            f"nichts gewählt — ändere nichts, was von der Antwort abhängt, "
            f"und frag im Text nach.", werkzeug_befund.KEINE_ANTWORT)
    else:
        befund = Befund(f"Sasha hat gewählt: {wahl}.", werkzeug_befund.OK)
    yield {"werkzeug": {"phase": "fertig", "name": "ask_choice",
                        "text": str(befund), "status": befund.status}}
    return ("result", werkzeug_befund.mit_kopf(befund), False)


# Ein Eintrag je Register-Werkzeug mit in_der_schleife=True. Der Test
# (tests/test_werkzeug_register.py) hält beide Seiten deckungsgleich.
SELBST = {"antwort": _antwort_werkzeug, "ask_choice": _knopf_werkzeug}


def _terminal_ausgeben(name: str, args: dict, active_exec):
    """Ein terminales Werkzeug mit Ausführer (heute nur read_news): sein
    Ergebnis ist schon moderiert und wird direkt als Antwort gestreamt, statt
    es nacherzählen zu lassen. KEIN Auto-Save: Welt-News gehören nicht ins
    Gedächtnis."""
    yield {"cinema": True}
    show = active_exec(name, args)
    # Meta-Kopf ("Sendung (Stand …):") wegschneiden - der gesprochene
    # Broadcast soll mit dem Moderationstext beginnen, nicht mit Meta.
    if show.startswith("Sendung (Stand") and "\n\n" in show:
        show = show.split("\n\n", 1)[1]
    yield show
    return ("stop",)


def _ask_buttons(args: dict):
    """frage_knopf: Knopf-Dialog auslösen, blockieren. -> (Wahl oder None,
    angebotene Knöpfe). Generator (yieldet das permission-Event) — mit
    `yield from` aufrufen."""
    import state
    frage = str(args.get("frage", "")).strip() or "Wie soll ich weitermachen?"
    opts  = [str(o).strip() for o in (args.get("optionen") or []) if str(o).strip()]
    if len(opts) < 2:
        opts = ["ja", "nein"]
    opts = opts[:4]                       # Leiste fasst max 4 Knöpfe sauber
    state.push_log(f"AI →  FRAGE {opts}: {frage[:140]}")
    # Bei Zeit-Ende kommt None zurück (nicht mehr „(keine Antwort)" als
    # Text, 2026-10-08): ein Sentinel, das wie ein Knopf-Label aussieht,
    # konnte als Wahl durchrutschen.
    state.request_permission(options=opts, timeout_default=None)
    yield {"permission": {"frage": frage, "optionen": opts}}
    wahl = state.wait_permission()        # BLOCKIERT bis Klick/Timeout
    state.push_log(f"AI ←  WAHL: {wahl if wahl is not None else '(keine Antwort)'}")
    zug_ablauf.frage(frage, opts, wahl, art="knopf")
    return wahl, opts


def _ask_permission(name: str, args: dict):
    """Erlaubnis-Gate: JA/NEIN-Dialog vor einem schreibenden Tool.
    Generator — mit `yield from` aufrufen. True = ausführen."""
    import state
    # Geltungsbereiche (2026-10-07, core/erlaubnis.py): schon „immer" oder
    # „für dieses Gespräch" erlaubt → nicht fragen, aber im Log sichtbar.
    schon = erlaubnis.vorab(name, args)
    if schon:
        state.push_log(f"AI ✓  ERLAUBT ({schon}): {werkzeug_register.kanonisch(name)}")
        if zug_ablauf.offen():
            zug_ablauf.frage(erlaubnis.frage(name, args), [], f"schon erlaubt ({schon})",
                             art="erlaubnis")
        return True
    frage = erlaubnis.frage(name, args)
    opts = erlaubnis.optionen(name, args)
    state.push_log(f"AI →  ERLAUBNIS? {frage[:160]}")
    state.request_permission(options=opts)
    # optionen + geltung: neu seit 2026-10-07. Ein Client, der nur „frage"
    # kennt, darf weiter "ja"/"nein" schicken (/api/permission_answer nimmt
    # die alten Wörter an); geltung sagt maschinenlesbar, was jeder Knopf heißt.
    yield {"permission": {"frage": frage, "optionen": opts, "erlaubnis": True,
                          "geltung": erlaubnis.geltungen(name, args) + [erlaubnis.NEIN]}}
    antwort_ = state.wait_permission()    # BLOCKIERT bis Klick/Timeout
    geltung = erlaubnis.deuten(antwort_)
    state.push_log(f"AI ←  ERLAUBNIS: {antwort_}")
    zug_ablauf.frage(frage, opts, antwort_, art="erlaubnis")
    if geltung == erlaubnis.NEIN:
        return False
    erlaubnis.merken(name, geltung, args)
    return True
