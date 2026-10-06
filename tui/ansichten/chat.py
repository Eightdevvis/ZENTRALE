# tui/ansichten/chat.py
#
# Der KI-Chat der TUI: Eingabe, Stream (SSE von /api/chat), Erlaubnis-Frage,
# Verlauf, Kosten im Titel, das Auge. Bis 06.10.2026 Closures in run_ui
# (tui/zentrale_tui.py); jetzt ein eigenes Modul, damit neue Chat-Funktionen
# hier wachsen können, ohne den Rest der TUI anzufassen
# (memory/system/tui_bauplan.md).
#
# Die Rümpfe sind die alten Closures; die erste Zeile jeder Methode sagt, was
# sie von außen braucht (self = dieser Chat, self.z = der Kontext).

import curses
import json
import threading
import time
import urllib.error
import urllib.request

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from .basis import BASE_URL, api_call
from .text import _md_umbruch, _wrap, md_zeilen


def echte_nachrichten(log):
    """Wie viele Eintraege davon kennt auch das Backend?

    Werkzeug- und Denk-Zeilen stehen NUR in der TUI. Zaehlt man sie mit,
    sieht der Poll gleich viele Eintraege wie das Backend und uebernimmt
    dessen Verlauf — womit genau die Zeilen verschwaenden, die gerade
    sichtbar gemacht werden sollten.
    """
    return sum(1 for rolle, _t in log if rolle in ("user", "ai"))


def ai_verlauf_holen():
    """Den Verlauf vom Backend holen. -> [(rolle, text)] oder None."""
    try:
        h = api_call("/api/chat/history")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(h, list):
        return None
    log = []
    for m in h:
        if not isinstance(m, dict):
            continue
        txt = (m.get("content") or "").strip()
        if txt:
            log.append(("user" if m.get("role") == "user" else "ai", txt))
    return log


def ai_wrap(role, text, w):
    """Text auf Breite w umbrechen; jede Zeile traegt ihre Rolle (fuer Farbe).

    Antworten der KI laufen durch md_zeilen: sie schreibt Markdown, und
    roh gezeichnet stand hier "**fett**" und "## Titel" als Zeichen. Die
    Rolle wird dabei um den Blockstil erweitert ("ai_kopf", "ai_code",
    "ai_liste") — welche Farbe das ergibt, entscheidet allein der
    Zeichner weiter unten.

    Sashas Eingaben bleiben roh: was er tippt, soll so dastehen, wie er
    es getippt hat.
    """
    if w < 6:
        w = 6
    # Werkzeuge und Denken bekommen ein eigenes Zeichen statt "du:"/"ki:".
    # Sie sind keine Aeusserungen, sondern das, was DAZWISCHEN passiert —
    # und genau das war bisher unsichtbar: Sasha sah "steht drin" und
    # konnte nicht nachsehen, ob und was wirklich geschrieben wurde.
    pre = {"user": "du:", "ai": "ki:", "werkzeug": "⚙",
           "werkzeug_fehler": "⚙", "denken": "…"}.get(role, "")
    if role.startswith("werkzeug") or role == "denken":
        eingerueckt = "  " + pre + " "
        aus = []
        for i, zeile in enumerate(_md_umbruch(text, w - len(eingerueckt),
                                              "")):
            aus.append((role, (eingerueckt if i == 0 else "    ") + zeile))
        return aus or [(role, eingerueckt)]

    if role == "ai":
        out = []
        for zeile, stil in md_zeilen(text, w - len(pre) if pre else w):
            out.append(("ai_" + stil if stil else "ai", zeile))
        if not out:
            out = [("ai", "")]
        if pre:                       # Praefix auf die erste Zeile
            art, ztext = out[0]
            out[0] = (art, (pre + ztext) if ztext.startswith(("•", " "))
                      else (pre + " " + ztext if ztext else pre))
        return out

    out = []
    first = True
    for para in text.split("\n"):
        cur = pre if (first and pre) else ""
        first = False
        for wd in para.split():
            while len(wd) > w:
                if cur:
                    out.append((role, cur)); cur = ""
                out.append((role, wd[:w])); wd = wd[w:]
            cand = (cur + " " + wd) if cur else wd
            if len(cand) > w:
                out.append((role, cur)); cur = wd
            else:
                cur = cand
        out.append((role, cur))
    return out


def fmt_euro(eur):
    """Einen Euro-Betrag so anzeigen, dass man ihn auch sieht.

    Zwei Fallen, die vorher beide zuschlugen: `f"{eur:.2f}"` macht aus
    0,0027 € eine glatte „0.00€", und die Anzeige verschwand ganz, wenn der
    Betrag 0 war. Ein Posten, der stumm bleibt, kann auch stumm wachsen —
    genau das soll die Zahl ja verhindern. Also: die Null wird gezeigt, und
    alles unter einem Cent bekommt ein sichtbares '<'.

    Defensiv wie fmt_uptime: der Wert kommt über HTTP/JSON.
    """
    try:
        eur = float(eur)
    except (TypeError, ValueError):
        return "—"
    if eur != eur or eur in (float("inf"), float("-inf")):   # NaN/inf
        return "—"
    if eur <= 0:
        return "0,00€"
    if eur < 0.01:
        return "<0,01€"
    return f"{eur:.2f}".replace(".", ",") + "€"


def werkzeug_zeile(w):
    """Ein Tool-Ereignis als Verlaufs-Zeile. -> (rolle, text)

    Argumente werden gekuerzt, nicht weggelassen: WELCHE Datei sie
    beschrieben hat, ist genau die Frage, die man hinterher stellt.
    """
    name = str(w.get("name") or "?")
    phase = w.get("phase")
    if phase == "start":
        args = w.get("args") or {}
        teile = []
        for schluessel, wert in args.items():
            text = " ".join(str(wert).split())
            if len(text) > 60:
                text = text[:59] + "…"
            teile.append("%s=%s" % (schluessel, text))
        return ("werkzeug", "%s(%s)" % (name, ", ".join(teile)))
    text = " ".join(str(w.get("text") or "").split())
    if len(text) > 200:
        text = text[:199] + "…"
    if phase == "fehler":
        return ("werkzeug_fehler", "%s ✗ %s" % (name, text))
    return ("werkzeug_ergebnis", "↳ " + text)


class Chat:
    """Der KI-Chat (Mitte, Leertaste auf der Startseite). Thin Client: die
    TUI rechnet keine KI, sie spricht nur HTTP mit /api/chat (SSE) und zeigt
    den Verlauf. Zustand in self.AI (auch z.AI), geschützt durch AI_LOCK,
    weil Stream- und Poll-Thread hineinschreiben."""

    def __init__(self, z):
        self.z = z
        # ── KI-Chat (füllt die MITTE-Box, Taste 'a') ───────────────────────
        # THIN-CLIENT: die TUI rechnet selbst keine KI. Wir sprechen NUR über HTTP
        # mit <BASE_URL>/api/chat; welcher Kern denkt, entscheidet das Backend
        # (ai_backends.chat_available(): Cloud oder Ollama). Daheim via
        # `zentrale-remote` zeigt BASE_URL auf den SSH-Tunnel → PC-Backend. Das
        # lokale tui-Backend (ZENTRALE_LOKALE_KI=aus) nutzt nur die Cloud; ist auch
        # die nicht da (offline, gedrosselt), antwortet /api/chat mit 503 — das
        # fangen wir ab und sagen es in der Statuszeile.
        # Der Stream (SSE) läuft in EINEM Hintergrund-Thread und füllt AI["answer"]
        # live; die Zeichenschleife rendert nur — nie IO im Render/Input-Thread.
        #   active   : Panel hat den Fokus
        #   input    : aktuelle Eingabezeile (Prompt)
        #   log      : Verlauf [(rolle, text)] rolle = "user"|"ai"|"sys"
        #   answer   : live wachsende KI-Antwort während des Streams (None=keiner)
        #   reflect  : letzter Denk-Schnipsel (dim, nur während Stream), ""=keiner
        #   streaming: läuft gerade ein Stream? (dann Eingabe gesperrt, schnellerer Tick)
        #   scroll   : Scroll-Offset vom Boden (0 = neueste unten sichtbar)
        #   perm     : offene Erlaubnis-Frage {frage, optionen} oder None (Tool-Gate)
        #   msg      : kurze Statuszeile (Fehler/Hinweis)
        #   loaded   : History schon einmal vom Backend geholt?
        #   backend  : "local" | "cloud" | None — wer gerade denkt (Kasten-Titel)
        #   model    : Modell-Name dazu, provider: bei cloud der Anbieter
        self.AI = z.AI = {"active": False, "input": "", "log": [], "answer": None,
                          "reflect": "", "denken": "", "streaming": False, "scroll": 0,
                          "perm": None, "msg": "", "loaded": False,
                          "backend": None, "model": "", "provider": "",
                          "kosten_heute": 0.0, "budget": {},
                          # Der Takt kann von sich aus sprechen (core/takt.py). Ohne diese
                          # zwei Felder spraeche sie in einen leeren Raum: der Verlauf wurde
                          # frueher EINMAL beim Oeffnen geholt.
                          "neu": False, "n": 0}
        self.AI_LOCK = z.AI_LOCK = threading.Lock()

    def start(self):
        """Hintergrund-Threads anwerfen (run_ui ruft das nach dem Aufbau)."""
        ai_poll = self.ai_poll
        threading.Thread(target=ai_poll, daemon=True, name="ai-poll").start()

    def ai_stream(self, message):
        """Öffnet den SSE-Stream /api/chat und füllt AI['answer'] Token für Token.
        Läuft im Hintergrund-Thread. Blockiert bei einer Erlaubnis-Frage still,
        bis der Input-Thread /api/permission_answer POSTet und der Server den
        Stream weiterlaufen lässt."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        url = BASE_URL + "/api/chat"
        data = json.dumps({"message": message}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream"})
        def denken_ablegen():
            """Gesammeltes Denken in den Verlauf schieben — in der richtigen
            Reihenfolge. Aufgerufen, sobald etwas ANDERES passiert (ein
            Werkzeug, Text, eine Rueckfrage): dann ist der Gedankengang zu
            Ende, und er steht vor dem, was daraus folgte. Haengt man ihn
            erst am Turn-Ende an, steht das Denken hinter den Taten."""
            gedacht = (AI.get("denken") or "").strip()
            if gedacht:
                AI["log"].append(("denken", gedacht))
                AI["denken"] = ""

        resp = None
        try:
            # 300 s, und die Zahl ist NICHT frei gewaehlt: der Timeout gilt
            # auch fuers LESEN am SSE-Strom, und waehrend die Erlaubnis-Frage
            # auf einen Klick wartet, fliesst nichts. Der Server gibt dem
            # Menschen dafuer 180 s (core/state.py::wait_permission). Mit 120 s
            # starb der Client, BEVOR der Server aufgab: am 18.08.2026 hat
            # Sasha 184 s zum Antworten gebraucht, die TUI zeigte danach
            # "keine verbindung zur ki", und die fertige Antwort des Modells —
            # die es laut Devtools gab — kam nie im Chat an.
            # Bleibt dieser Wert groesser als wait_permission, kann das nicht
            # wieder passieren. Waehrend echten Streamens setzt jeder Token den
            # Timeout ohnehin neu.
            resp = urllib.request.urlopen(req, timeout=300)
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                try:
                    evt = json.loads(line[5:].strip())
                except ValueError:
                    continue
                with AI_LOCK:
                    if "token" in evt:
                        denken_ablegen()
                        AI["answer"] = (AI["answer"] or "") + str(evt["token"])
                        AI["perm"] = None          # es fließt wieder Text
                    elif "reflect" in evt:
                        # Zweimal aufheben: gekuerzt fuer die Lauf-Anzeige,
                        # vollstaendig fuer den Verlauf. Wer hinterher wissen
                        # will, warum sie etwas getan hat, braucht das ganze
                        # Denken, nicht die letzten 400 Zeichen.
                        AI["reflect"] = (AI["reflect"] + str(evt["reflect"]))[-400:]
                        AI["denken"] = (AI["denken"] + str(evt["reflect"]))[-8000:]
                    elif "werkzeug" in evt:
                        denken_ablegen()
                        AI["log"].append(werkzeug_zeile(evt["werkzeug"]))
                    elif "permission" in evt:
                        denken_ablegen()
                        AI["perm"] = evt["permission"]
                    elif "fehler" in evt:
                        # Backend-Fehler, Ablehnung, Rundengrenze: in die
                        # Statuszeile, NICHT in den Verlauf — das hat nicht
                        # sie gesagt (core/werkzeug_schleife.py).
                        denken_ablegen()
                        AI["msg"] = "fehler: " + str(evt["fehler"])
                    elif "done" in evt:
                        break
                    # ascii/cinema: im Terminal ohne Bild/Sound → ignorieren
        except urllib.error.HTTPError as e:
            # 503 heißt nicht mehr automatisch "lokale ki aus" - es kann auch
            # heißen, dass gar kein Backend da ist (weder Ollama noch Cloud).
            # Den echten Grund schickt der Server im Body mit.
            grund = ""
            try:
                grund = (json.loads(e.read().decode("utf-8", "replace"))
                         .get("error") or "")
            except Exception:
                pass
            with AI_LOCK:
                AI["msg"] = ((grund or "kein ki-backend — tunnel? (/local on)")
                             if e.code == 503 else "fehler: HTTP %s" % e.code)
        except (urllib.error.URLError, OSError):
            with AI_LOCK:
                # Unterscheiden: gar nicht erst drangekommen vs. mittendrin
                # abgerissen. "keine verbindung" auf einen halb gelaufenen
                # Turn zu schreiben, schickt einen auf die falsche Faehrte.
                if (AI["answer"] or "").strip() or AI["perm"]:
                    AI["msg"] = "verbindung abgerissen — antwort unvollstaendig"
                else:
                    AI["msg"] = "keine verbindung zur ki (zentrale-remote?)"
        finally:
            if resp is not None:
                try: resp.close()
                except OSError: pass
            with AI_LOCK:
                denken_ablegen()
                ans = (AI["answer"] or "").strip()
                if ans:
                    AI["log"].append(("ai", ans))
                AI["answer"] = None
                AI["reflect"] = ""
                AI["perm"] = None
                AI["streaming"] = False

    def ai_submit(self):
        """Aktuellen Prompt abschicken (Stream im Hintergrund starten)."""
        AI, AI_LOCK, ai_stream = self.AI, self.AI_LOCK, self.ai_stream
        msg = AI["input"].strip()
        if not msg or AI["streaming"]:
            return
        with AI_LOCK:
            AI["log"].append(("user", msg))
            AI["input"] = ""
            AI["answer"] = ""
            AI["reflect"] = ""
            AI["perm"] = None
            AI["msg"] = ""
            AI["scroll"] = 0
            AI["streaming"] = True
        threading.Thread(target=ai_stream, args=(msg,), daemon=True).start()

    def ai_answer_perm(self, option):
        """Erlaubnis-Frage beantworten → entsperrt den wartenden Stream."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        try:
            api_call("/api/permission_answer", "POST", {"answer": option})
        except (urllib.error.URLError, OSError, ValueError):
            pass
        with AI_LOCK:
            AI["perm"] = None

    def ai_load_history(self):
        """Chat-Verlauf + Backend-Status vom Backend holen (der Verlauf lebt im
        Backend, state.py). Läuft im Hintergrund beim ersten Öffnen; scheitert still
        (dann leerer Verlauf)."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        # Welcher Kern antwortet gerade? Steht im Kasten-Titel, damit beim
        # Testen ohne Rätselraten sichtbar ist, ob lokal oder Cloud gedacht
        # wird - unterwegs ohne Ollama ist das der ganze Unterschied.
        try:
            st = api_call("/api/ai/status")
            if isinstance(st, dict):
                k = st.get("kosten") or {}
                with AI_LOCK:
                    AI["backend"] = st.get("backend")
                    AI["model"] = st.get("model") or ""
                    AI["provider"] = st.get("provider") or ""
                    AI["kosten_heute"] = k.get("heute") or 0.0
                    AI["budget"] = k.get("budget") or {}
        except (urllib.error.URLError, OSError, ValueError):
            pass
        log = ai_verlauf_holen() or []
        with AI_LOCK:
            # nur übernehmen, wenn zwischenzeitlich nichts Eigenes dazukam
            if not AI["log"]:
                AI["log"] = log
            AI["n"] = len(AI["log"])
            AI["loaded"] = True

    def ai_poll(self):
        """Regelmaessig nachsehen, ob die KI von sich aus etwas gesagt hat.

        Der Verlauf im Backend ist die Wahrheit — er enthaelt beide Seiten,
        auch was der Takt-Thread dort ablegt. Deshalb wird er im Ruhezustand
        einfach uebernommen statt Nachrichten einzeln zusammenzufuehren:
        beim Zusammenfuehren muesste man mitzaehlen, was die TUI waehrend
        eines Streams selbst schon angehaengt hat, und ein Zaehler, der
        einmal verrutscht, verdoppelt von da an jede Nachricht.

        Waehrend eines Streams wird nichts angefasst — dort waechst die
        Antwort Token fuer Token und wuerde vom Uebernehmen zerrissen.
        """
        AI, AI_LOCK = self.AI, self.AI_LOCK
        while True:
            time.sleep(20)
            try:
                with AI_LOCK:
                    if AI["streaming"] or not AI["loaded"]:
                        continue
                    alt_n = echte_nachrichten(AI["log"])
                log = ai_verlauf_holen()
                if log is None or len(log) <= alt_n:
                    continue
                with AI_LOCK:
                    if AI["streaming"]:
                        continue
                    AI["log"] = log
                    AI["n"] = len(log)
                    # Ein Zeichen im Titel nur, wenn er nicht ohnehin
                    # hinschaut und die KI das letzte Wort hatte.
                    if not AI["active"] and log and log[-1][0] == "ai":
                        AI["neu"] = True
            except Exception:
                pass          # ein Poll, der die TUI abschiesst, waere schlimmer

    def ai_titel(self):
        """Kasten-Titel mit dem Kern, der gerade denkt — und was er heute
        gekostet hat.

        »ki-chat« allein reicht nicht mehr: seit der Chat auch über die Cloud
        laufen kann, ist der Unterschied zwischen lokal und draußen genau das,
        was man beim Hinschauen wissen will. Und wer knapp bei Kasse ist, will
        die Tageskosten sehen, ohne danach zu suchen — eine Zahl, die man
        nebenbei mitbekommt, verhindert böse Überraschungen am Monatsende.

        Das ⚠ erscheint ab 80 % des Monatsbudgets."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        with AI_LOCK:
            b, mdl, prov = AI["backend"], AI["model"], AI["provider"]
            eur, budget = AI.get("kosten_heute") or 0.0, AI.get("budget") or {}
            # Sie kann von sich aus sprechen; steht der Kasten zu, sieht er
            # es sonst nie. Der Punkt steht VORNE — hinten haengt schon die
            # Kostenzeile und ein Zeichen dort geht unter.
            neu = "● " if AI.get("neu") else ""
        if b == "local":
            return neu + f"ki-chat · lokal ({mdl})".lower()
        if b != "cloud":
            return neu + "ki-chat"
        warn = " ⚠" if budget.get("status") in ("warn", "over") else ""
        return neu + f"ki-chat · cloud ({prov or mdl}) · {fmt_euro(eur)} heute{warn}".lower()

    def oeffnen(self):
        """Startseite → Chat (Leertaste): Fokus her, Verlauf beim ersten Mal
        im Hintergrund holen."""
        AI, ai_load_history = self.AI, self.ai_load_history
        AI["active"] = True; AI["scroll"] = 0; AI["msg"] = ""
        AI["neu"] = False              # gesehen
        if not AI["loaded"]:           # Verlauf einmal im Hintergrund nachladen
            threading.Thread(target=ai_load_history, daemon=True).start()

    def taste(self, ch):
        """Eine Taste, während der Chat den Fokus hat (früher ein Zweig der
        Hauptschleife in run_ui)."""
        AI, ai_answer_perm, ai_submit = self.AI, self.ai_answer_perm, self.ai_submit
        if AI["perm"]:                     # offene Erlaubnis-Frage → j/n/Zahl
            opts = AI["perm"].get("optionen") or ["ja", "nein"]
            if ch in (ord("j"), ord("J")):
                ai_answer_perm(next((o for o in opts if o.lower().startswith("j")), opts[0]))
            elif ch in (ord("n"), ord("N")):
                ai_answer_perm(next((o for o in opts if o.lower().startswith("n")), opts[-1]))
            elif ord("1") <= ch <= ord("9") and (ch - ord("1")) < len(opts):
                ai_answer_perm(opts[ch - ord("1")])
            elif ch == 27:                 # esc = ablehnen (letzte Option, meist nein)
                ai_answer_perm(opts[-1])
        elif ch == 27:                     # esc schließt das Panel (Stream läuft im BG weiter)
            AI["active"] = False
        elif ch in (10, 13, curses.KEY_ENTER):
            ai_submit()
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if not AI["streaming"]:
                AI["input"] = AI["input"][:-1]
        elif ch == curses.KEY_UP:
            AI["scroll"] += 1
        elif ch == curses.KEY_DOWN:
            AI["scroll"] = max(0, AI["scroll"] - 1)
        elif ch == curses.KEY_PPAGE:
            AI["scroll"] += 5
        elif ch == curses.KEY_NPAGE:
            AI["scroll"] = max(0, AI["scroll"] - 5)
        elif 32 <= ch <= 126 and not AI["streaming"] and len(AI["input"]) < 1000:
            AI["input"] += chr(ch)

    def draw_ai(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn der KI-Chat Fokus hat. Reiner Zeichner:
        liest AI[...] (unter Lock) und rendert Verlauf + laufende Antwort +
        Eingabezeile. Der Stream selbst läuft in ai_stream() im Hintergrund."""
        AI, AI_LOCK, C, PIX_MODUS = self.AI, self.AI_LOCK, self.z.C, self.z.PIX_MODUS
        addclip, pix_attr, safe_addstr = self.z.addclip, self.z.pix_attr, self.z.safe_addstr
        inx = bx + 2
        inw = max(6, bw - 4)
        body_top = by + 1

        with AI_LOCK:
            log = list(AI["log"])
            answer = AI["answer"]
            reflect = AI["reflect"]
            streaming = AI["streaming"]
            perm = dict(AI["perm"]) if AI["perm"] else None
            inp = AI["input"]
            msg = AI["msg"]
            scroll = AI["scroll"]

        # Fußzeilen zuerst: sie bestimmen, wie viel Platz der Verlauf noch hat.
        # Bei offener Erlaubnis-Frage brauchen Frage UND Knöpfe je nach Breite
        # mehrere Zeilen — früher wurden sie hart auf inw gekürzt, in einem
        # schmalen Fenster war die Frage damit unlesbar.
        foot = []
        if perm:
            opts = perm.get("optionen") or ["ja", "nein"]
            label = "  ".join("%d) %s" % (i + 1, o) for i, o in enumerate(opts))
            olines = _wrap("› " + label, inw) or ["›"]
            frage = (perm.get("frage") or "darf ich?").replace("\n", " ")
            qlines = _wrap("? " + frage, inw)
            room = max(1, (bh - 3) - len(olines))   # mind. 1 Zeile Verlauf bleibt
            if len(qlines) > room:                  # Knöpfe haben Vorrang
                qlines = qlines[:room]
                qlines[-1] = qlines[-1][:max(1, inw - 1)] + "…"
            foot = [(ln, C["warn"]) for ln in qlines + olines]
        else:
            # Info-Zeile: Denk-Strom > Fehler/Status > Scroll-Hinweis
            if streaming and reflect:
                foot.append((("denkt: " + reflect.replace("\n", " "))[-inw:],
                             C["faint"]))
            elif msg:
                foot.append((msg[:inw], C["warn"]))
            elif scroll > 0:
                foot.append(("↑ verlauf (↓ nach unten)", C["faint"]))
            else:
                foot.append(("", 0))               # Platz halten, Layout stabil
            # Unterste Zeile: Stream-läuft > Eingabe
            if streaming:
                foot.append(("› …", C["dim"]))
            else:
                shown = "› " + inp
                if len(shown) > inw - 1:
                    shown = "› …" + inp[-(inw - 5):]
                foot.append((shown + "_", C["bright"]))
        foot = foot[-max(1, bh - 3):]
        body_bot = by + bh - 2 - len(foot)
        avail = max(1, body_bot - body_top + 1)

        # Zeilen bauen: Verlauf + laufende Antwort (jede Zeile trägt ihre Rolle)
        lines = []
        for role, text in log:
            lines += ai_wrap(role, text, inw)
            lines.append(("gap", ""))
        if answer is not None:
            lines += ai_wrap("ai", answer + ("▌" if streaming else ""), inw)

        # Das Auge (Sasha, 04.10.2026): gross, in der Mitte, im Stil der
        # App-Symbole. Leerer Chat → mittig mit dem Hinweis darunter; läuft
        # ein Gespräch → oben, der Verlauf rückt darunter. Zu niedrig → weg.
        if C.get("pix_bg") is not None and PIX_MODUS != "off" and bw >= pixel.AUGE_W + 4:
            jetzt = time.monotonic()
            if AI.get("auge_t0") is None:
                AI["auge_t0"] = jetzt                  # gerade geöffnet: Lider gehen auf
            seit = jetzt - AI["auge_t0"]
            farben = "nacht" if sum(C["pix_bg"]) < 384 else "tag"
            auge = pixel.auge_zellen(round(min(1.0, seit / .45), 2), int(seit * 1000),
                                     streaming, farben,
                                     "half" if PIX_MODUS == "half" else "mix")
            ey = None
            if not lines and avail >= pixel.AUGE_H + 3:
                ey = body_top + max(0, (avail - pixel.AUGE_H - 2) // 2)
            elif lines and avail >= pixel.AUGE_H + 6:
                ey = body_top
                body_top += pixel.AUGE_H + 1
                avail = max(1, body_bot - body_top + 1)
            if ey is not None:
                ex = bx + (bw - pixel.AUGE_W) // 2
                for r, line in enumerate(auge):
                    for c, z in enumerate(line):
                        if z:
                            safe_addstr(ey + r, ex + c, z[0], pix_attr(z[1], z[2]))
                if not lines:
                    hinweis = "frag die lokale ki — tippen + enter"
                    addclip(ey + pixel.AUGE_H + 1, bx + max(2, (bw - len(hinweis)) // 2),
                            hinweis, inw, C["faint"])
                    lines = None                       # Hinweis steht schon

        if lines is None:
            pass
        elif not lines:
            addclip(body_top + avail // 2, inx,
                    "frag die lokale ki — tippen + enter", inw, C["faint"])
        else:
            total = len(lines)
            maxscroll = max(0, total - avail)     # scroll=0 → Boden (neueste)
            sc = min(scroll, maxscroll)
            start = max(0, total - avail - sc)
            y = body_top
            # Blockstile aus dem Markdown-Renderer auf Attribute abbilden.
            # Ueberschrift hebt sich ab, Code steht zurueck (er ist Beleg,
            # nicht Aussage), Listen lesen sich wie Fliesstext.
            #
            # Werkzeuge und Denken stehen ZURUECK: sie sollen nachlesbar
            # sein, ohne das Gespraech zu uebertoenen. Ein Werkzeug-FEHLER
            # tritt dagegen hervor — das ist der Fall, in dem sie hinterher
            # behauptet, es habe geklappt.
            stile = {
                "user":              C["acc"],
                "ai":                C["bright"],
                "ai_kopf":           C["acc"],
                "ai_code":           C["dim"],
                "ai_liste":          C["bright"],
                "werkzeug":          C["acc"],
                "werkzeug_ergebnis": C["faint"],
                "werkzeug_fehler":   C["warn"],
                "denken":            C["faint"],
            }
            for kind, seg in lines[start:start + avail]:
                addclip(y, inx, seg, inw, stile.get(kind, C["faint"]))
                y += 1

        # Fuß unten in den Kasten setzen (wächst nach oben, nicht in den Rahmen)
        fy = by + bh - 1 - len(foot)
        for txt, attr in foot:
            addclip(fy, inx, txt, inw, attr)
            fy += 1
