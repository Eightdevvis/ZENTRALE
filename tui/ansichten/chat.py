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

from . import chat_befehle, eingabe, fussleiste, maus
from . import verlauf as V
from .ablage import Ablageliste
from .chat_ablage import AblageSteuerung, ablage_anzeige, anhang_eintrag
from .chat_erlaubnis import ErlaubnisSteuerung
from .chat_bedienung import ChatBedienung
from .chat_zeichnen import ChatZeichnen
from .einstellungen import Einstellungen
from .rechts import Rechts
from .seitenleiste import Seitenleiste
from .chat_gespraeche import GespraechsSteuerung, ai_verlauf_holen, verlauf_aus  # noqa: F401
from .gespraechsliste import Gespraechsliste
from .gedaechtnis import Gedaechtnis
from .projekte import Projekte
from .basis import BASE_URL, api_call
from .text import _md_umbruch, md_zeilen

# Alt+Enter als eigener Tastencode: curses liefert ESC + Enter als zwei
# Tasten; Chat.taste setzt sie zu diesem einen zusammen. -1 ist „keine
# Taste", -2 gibt es bei curses nicht.
TASTE_ALT_ENTER = -2

# Strg+C kommt als Zeichen 3 an, seit die TUI curses im raw-Modus fährt
# (run_ui, 2026-10-07) — vorher löste es SIGINT aus und beendete die TUI.
TASTE_STRG_C = 3

# Strg-Tasten des Chats nach dem Vorbild von Claude Web (2026-10-07): curses
# im raw-Modus liefert Strg+Buchstabe als 1 … 26.
STRG = {"n": 14, "o": 15, "p": 16, "t": 20, "u": 21}

# Ein Stoß: was beim Einfügen auf einmal im Tastaturpuffer liegt. Mehr als
# das wird nicht in einem Rutsch gelesen (der Rest kommt im nächsten Takt).
STOSS_MAX = 200_000
# Ein Stoß ab so vielen Zeichen, der mit Enter endet, ist ein Einfügen —
# das Enter wird dann eine neue Zeile statt abzuschicken.
STOSS_EINFUEGEN = 10

# Vermerk hinter einer gestoppten Antwort — derselbe wie im Backend
# (ui/routen/ki.py), damit der Verlauf nach dem nächsten Poll gleich aussieht.
VERMERK_ABGEBROCHEN = "(abgebrochen)"


def echte_nachrichten(log):
    """Wie viele Eintraege davon kennt auch das Backend?

    Werkzeug- und Denk-Zeilen stehen NUR in der TUI. Zaehlt man sie mit,
    sieht der Poll gleich viele Eintraege wie das Backend und uebernimmt
    dessen Verlauf — womit genau die Zeilen verschwaenden, die gerade
    sichtbar gemacht werden sollten.
    """
    return sum(1 for rolle, _t in log if rolle in ("user", "ai"))


def zahl(n):
    """1234 → '1 234' (Tausender mit Leerzeichen, wie Sasha es liest)."""
    return "{:,}".format(int(n)).replace(",", " ")


def denken_wrap(text, offen, w):
    """Denken als Verlaufs-Zeilen: eingeklappt EINE Zeile
    „▸ gedacht (1 234 Zeichen)", aufgeklappt Kopf + Text (Strg+D, /denken)."""
    kopf = "%s gedacht (%s Zeichen)" % ("▾" if offen else "▸", zahl(len(text)))
    if not offen:
        return [("denken", "  " + kopf[:max(1, w - 2)])]
    return [("denken", "  " + kopf[:max(1, w - 2)])] + ai_wrap("denken", text, w)


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
           "werkzeug_fehler": "⚙", "denken": "…",
           "ablage": "▤", "anhang": "▤"}.get(role, "")
    if role == "hinweis":
        # Antworten der TUI selbst (/hilfe): Zeilen wie geschrieben, nur
        # hart umbrochen — Einrückung und Spalten bleiben stehen.
        aus = []
        for zeile in text.split("\n"):
            aus += [(role, zeile[i:i + w]) for i in range(0, len(zeile), w)] or [(role, "")]
        return aus
    if role.startswith("werkzeug") or role in ("denken", "ablage", "anhang"):
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


def auswahl(name, stand):
    """Die Auswahl-Liste für /modell, /anbieter, /effort ohne Argument.
    -> {"titel", "optionen": [(text, daten_zum_setzen)], "idx"}; idx steht
    auf dem, was gerade gilt. Nur Anbieter mit Schlüssel."""
    anbieter = [a for a in stand.get("anbieter_liste") or []
                if a.get("schluessel") and a.get("spricht")]
    aktiv = stand.get("anbieter_aktiv")
    optionen, idx = [], 0
    if name == "modell":
        titel = "modell wählen"
        for a in anbieter:
            for m in a.get("modelle") or []:
                if a["name"] == aktiv and m == stand.get("modell"):
                    idx = len(optionen)
                optionen.append(("%s · %s" % (a["name"], m),
                                 {"anbieter": a["name"], "modell": m}))
        # Seit 2026-10-07 alle Modelle der Anbieter (Qwen hat Hunderte):
        # tippen filtert (wahl_filtern), Ziffern gehören dann zum Filter.
        return {"titel": titel, "optionen": optionen, "idx": idx,
                "alle": list(optionen), "filter": ""}
    if name == "anbieter":
        titel = "anbieter wählen"
        for n in ["auto"] + [a["name"] for a in anbieter]:
            if n == stand.get("anbieter"):
                idx = len(optionen)
            optionen.append((n, {"anbieter": n}))
    else:                                   # effort
        titel = "denk-tiefe wählen" + ("" if stand.get("effort_wirkt")
                                       else " (wirkt nur bei claude)")
        for st in stand.get("effort_stufen") or []:
            if st == stand.get("effort"):
                idx = len(optionen)
            optionen.append((st, {"effort": st}))
    return {"titel": titel, "optionen": optionen, "idx": idx}


def wahl_filtern(wahl, text):
    """Die Auswahl auf Optionen eingrenzen, die alle Wörter von `text`
    enthalten (Groß/klein egal). Die gewählte bleibt gewählt, wenn sie
    noch drin ist."""
    alt = wahl["optionen"][wahl["idx"]] if wahl["optionen"] else None
    woerter = text.lower().split()
    wahl["filter"] = text
    wahl["optionen"] = [o for o in wahl["alle"]
                        if all(w in o[0].lower() for w in woerter)]
    wahl["idx"] = wahl["optionen"].index(alt) if alt in wahl["optionen"] else 0
    return wahl


def budget_text(stand):
    """/budget ohne Zahl: was gilt und was schon weg ist."""
    lage = stand.get("budget_lage") or {}
    weg = fmt_euro(lage.get("ausgegeben") or 0)
    if not stand.get("budget"):
        return "kein budget gesetzt · %s diesen monat · /budget 20 setzt eins" % weg
    return "budget %s im monat · %s verbraucht" % (fmt_euro(stand["budget"]), weg)


def stand_text(daten, stand):
    """Statuszeile nach dem Setzen: was jetzt gilt."""
    if "weg" in daten:
        return {"local": "nur lokal", "cloud": "nur cloud",
                "auto": "lokal, wenn da — sonst cloud"}.get(stand.get("weg"), "weg gesetzt")
    if "budget" in daten:
        return budget_text(stand)
    if "tui_symbole" in daten:
        return "symbole: %s" % ("zeichen" if stand.get("tui_symbole") == "zeichen"
                                else "pixel, zwei zeilen hoch")
    if "effort" in daten:
        return "denk-tiefe: %s%s" % (stand.get("effort"), "" if stand.get("effort_wirkt")
                                     else " (wirkt nur bei claude)")
    if "modell" in daten:
        return "modell: %s · %s" % (stand.get("anbieter_aktiv") or "—", stand.get("modell") or "—")
    if stand.get("anbieter") == "auto":
        return "anbieter: auto (jetzt %s)" % (stand.get("anbieter_aktiv") or "keiner")
    return "anbieter: %s" % (stand.get("anbieter") or "—")


class Chat(ChatZeichnen, ChatBedienung, GespraechsSteuerung, AblageSteuerung, ErlaubnisSteuerung):
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
                          "neu": False, "n": 0,
                          # Eingabe mit Cursor (ansichten/eingabe.py), halbe
                          # UTF-8-Zeichen, offene Auswahl (/modell …), Nummer
                          # des laufenden Zugs (fürs Stoppen) — 2026-10-07.
                          "cur": 0, "u8": b"", "wahl": None, "strom": None,
                          "gestoppt": False,
                          # Gespräche (Phase 2, 2026-10-07): welches offen ist
                          # (gid None = das nächste Senden beginnt ein neues),
                          # sein Titel, die offene Liste (gespraechsliste.py),
                          # Denken auf/zu, bearbeitete Nachricht (/bearbeiten),
                          # Nachrichten-Zahl beim letzten Laden (für den Poll).
                          "gid": None, "titel": "", "liste": None,
                          "denken_offen": False, "ersetzt": None, "n_server": 0,
                          "gespraeche": [],
                          # Ablage (Phase 5, 2026-10-07): offene Liste/Lesen
                          # (ablage.py), Anhänge für die nächste Nachricht.
                          "ablage": None, "anhaenge": [],
                          # Nachbesserung 2026-10-07: Antwort fertig geworden,
                          # während das Fenster zu war (●); Zeichen, die an der
                          # Eingabe-Grenze nicht mehr hineinpassten.
                          "fertig_ungesehen": False, "zu_viel": 0}
        # Claude-Web-Ansicht (2026-10-07, chat_zeichnen.py): wer den Fokus hat
        # (eingabe | verlauf | seite | rechts), was im Verlauf aufgeklappt und
        # angewählt ist, wann das Warten auf die Antwort begann (Denk-Adern),
        # Denk-Tiefe für die Leiste unter der Eingabe, Maus an/aus.
        self.AI.update(fokus="eingabe", offen=set(), vwahl=None, denk_t0=None,
                       denk_ende=None, denk_log_n=0, effort="", maus=maus.gewuenscht())
        self.klicks, self.raeder, self._ziele = [], [], []
        self.AI_LOCK = threading.Lock()
        self.liste = Gespraechsliste(self)
        self.gedaechtnis = Gedaechtnis(self)       # /gedaechtnis, /skills (Phase 3)
        self.ablageliste = Ablageliste(self)
        self.projekte = Projekte(self)             # /projekt, /projekte (Phase 6)
        self.seite = Seitenleiste(self)            # links (seitenleiste.py)
        self.rechts = Rechts(self)                 # Dokument / Outputs (rechts.py)
        self.einstellungen = Einstellungen(self)   # Customize (einstellungen.py)

    def start(self):
        """Hintergrund-Threads anwerfen (run_ui ruft das nach dem Aufbau)."""
        ai_poll = self.ai_poll
        threading.Thread(target=ai_poll, daemon=True, name="ai-poll").start()

    def ai_stream(self, message, ersetzt=None, wiederholen=False, anhaenge=None):
        """Öffnet den SSE-Stream /api/chat und füllt AI['answer'] Token für Token.
        Läuft im Hintergrund-Thread. Blockiert bei einer Erlaubnis-Frage still,
        bis der Input-Thread /api/permission_answer POSTet und der Server den
        Stream weiterlaufen lässt.

        ersetzt: Nachricht-id (/bearbeiten). wiederholen: statt einer neuen
        Frage /api/chat/wiederholen (dieselbe SSE-Form)."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        body = {"message": message}
        if AI.get("gid"):
            body["gespraech"] = AI["gid"]
        if ersetzt:
            body["ersetzt"] = ersetzt
        if anhaenge:
            body["anhaenge"] = [a["id"] for a in anhaenge]
        url = BASE_URL + ("/api/chat/wiederholen" if wiederholen else "/api/chat")
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
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
                    if "strom" in evt:
                        AI["strom"] = evt["strom"]   # damit Esc genau ihn stoppt
                    elif "titel" in evt:
                        AI["titel"] = str(evt["titel"])
                    elif "gespraech" in evt:
                        # Ein eben angelegtes Gespräch: ab jetzt geht alles dorthin.
                        AI["gid"] = evt["gespraech"]
                    elif "gestoppt" in evt:
                        denken_ablegen()
                        AI["gestoppt"] = True
                        AI["msg"] = "gestoppt"
                    elif "token" in evt:
                        denken_ablegen()
                        AI["answer"] = (AI["answer"] or "") + str(evt["token"])
                        AI["perm"] = None          # es fließt wieder Text
                    elif "reflect" in evt:
                        # Zweimal aufheben: gekuerzt fuer die Lauf-Anzeige,
                        # vollstaendig fuer den Verlauf. Wer hinterher wissen
                        # will, warum sie etwas getan hat, braucht das ganze
                        # Denken, nicht die letzten 400 Zeichen.
                        AI["reflect"] = (AI["reflect"] + str(evt["reflect"]))[-400:]
                        AI["denken"] = (AI["denken"] + str(evt["reflect"]))[-20000:]
                    elif "werkzeug" in evt:
                        denken_ablegen()
                        AI["log"].append(werkzeug_zeile(evt["werkzeug"]))
                    elif "ablage" in evt:          # ein Dokument liegt in der Ablage
                        self.ablage_event(evt["ablage"])
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
                             if e.code == 503 else grund or "fehler: HTTP %s" % e.code)
                # Abgelehnt (z. B. Bild ohne Cloud): Anhänge warten weiter.
                AI["anhaenge"] = list(anhaenge or []) + list(AI.get("anhaenge") or [])
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
                if ans and AI["gestoppt"]:
                    ans += "\n\n" + VERMERK_ABGEBROCHEN
                if ans:
                    AI["log"].append(("ai", ans))
                AI["answer"] = None
                AI["strom"] = None
                if AI["msg"] == "stoppe …":   # war schon fertig, als Strg+C kam
                    AI["msg"] = ""
                # Fenster war zu (Esc lässt die Antwort weiterlaufen, Sasha
                # 07.10.2026): ● auf der Startseite, bis der Chat wieder offen
                # ist. Eigenes Feld, weil der Poll „neu" alle 20 s aus der
                # Gesprächsliste neu rechnet und es sonst wieder löschte.
                if ans and not AI["active"]:
                    AI["fertig_ungesehen"] = True
                AI["reflect"] = ""
                AI["perm"] = None
                AI["streaming"] = False

    def ai_submit(self):
        """Eingabe abschicken: ein Slash-Befehl wird hier ausgeführt
        (chat_befehle.py), alles andere geht als Frage an die KI."""
        AI = self.AI
        was = chat_befehle.lesen(AI["input"])
        if was.art == "leer":
            return
        if was.art == "unbekannt":
            # Eingabe bleibt stehen: meist ein Tippfehler, den man korrigiert.
            AI["msg"] = "unbekannter befehl /%s — /help zeigt alle" % was.name
            return
        if was.art == "befehl":
            AI["input"], AI["cur"] = "", 0
            self.befehl(was.name, was.arg)
            return
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — ctrl+c stoppt sie"
            return
        if AI.get("ersetzt"):              # /bearbeiten: ab dort ersetzen
            self.senden(was.text, ersetzt=AI["ersetzt"])
        else:
            self.senden(was.text)

    def senden(self, msg, ersetzt=None, wiederholen=False):
        """Eine Frage an die KI schicken (Stream im Hintergrund starten).
        ersetzt (/bearbeiten): ab der letzten eigenen Nachricht neu.
        wiederholen: die Frage steht schon im Verlauf, nur die Antwort neu."""
        AI, AI_LOCK, ai_stream = self.AI, self.AI_LOCK, self.ai_stream
        with AI_LOCK:
            if ersetzt:
                letzte = max((i for i, (r, _t) in enumerate(AI["log"]) if r == "user"),
                             default=len(AI["log"]))
                del AI["log"][letzte:]
            # Wiederholen schickt die gespeicherten Anhänge selbst mit.
            anhaenge = [] if wiederholen else self.anhaenge_nehmen()
            if not wiederholen:
                AI["log"].append(("user", msg))
                AI["log"] += [anhang_eintrag(a) for a in anhaenge]
            # Denk-Adern: ab jetzt wird gewartet; die Antwort beginnt hinter
            # allem, was bis hier im Verlauf steht (chat_zeichnen._adern_lage).
            AI["denk_t0"], AI["denk_ende"] = time.monotonic(), None
            AI["denk_log_n"] = len(AI["log"])
            AI["ersetzt"] = None
            AI["input"] = ""
            AI["cur"] = 0
            AI["zu_viel"] = 0
            AI["gestoppt"] = False
            AI["strom"] = None
            AI["answer"] = ""
            AI["reflect"] = ""
            AI["perm"] = None
            AI["msg"] = ""
            AI["scroll"] = 0
            AI["streaming"] = True
        threading.Thread(target=ai_stream, args=(msg, ersetzt, wiederholen, anhaenge),
                         daemon=True).start()

    def ai_answer_perm(self, option):
        """Erlaubnis-Frage beantworten → entsperrt den wartenden Stream."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        try:
            api_call("/api/permission_answer", "POST", {"answer": option})
        except (urllib.error.URLError, OSError, ValueError):
            pass
        with AI_LOCK:
            AI["perm"] = None

    def status_holen(self):
        """Backend-Status für den Kasten-Titel holen (/api/ai/status).
        Auch nach jedem Slash-Befehl, damit der Titel sofort stimmt."""
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
                    AI["effort"] = st.get("effort") or ""
                    AI["kosten_heute"] = k.get("heute") or 0.0
                    AI["budget"] = k.get("budget") or {}
                    if st.get("tui_symbole"):        # Symbole der Seitenleiste (symbole.py)
                        AI["symbole"] = st["tui_symbole"]
        except (urllib.error.URLError, OSError, ValueError):
            pass

    # ── Steuerung: stoppen, neu, Einstellungen (Phase 1, 2026-10-07) ──────

    def stoppen(self):
        """Laufende Antwort stoppen (Strg+C). Das Backend bricht bis in die
        Werkzeug-Schleife ab und schickt dann 'gestoppt'; der Strom endet
        von selbst. Im Hintergrund, damit die Taste nie hängt."""
        AI = self.AI
        with self.AI_LOCK:
            strom = AI.get("strom")
            AI["msg"] = "stoppe …"

        def los():
            try:
                api_call("/api/chat/stop", "POST",
                         {"strom": strom} if strom else {})
            except (urllib.error.URLError, OSError, ValueError):
                with self.AI_LOCK:
                    AI["msg"] = "stoppen ging nicht — keine verbindung"
        threading.Thread(target=los, daemon=True).start()

    def befehl(self, name, arg):
        """Einen Slash-Befehl ausführen (chat_befehle.BEFEHLE)."""
        AI = self.AI
        if name == "hilfe":
            with self.AI_LOCK:
                AI["log"].append(("hinweis", chat_befehle.hilfe_text()))
                AI["scroll"] = 0
            return
        # Gespräche (Phase 2, 2026-10-07) — die Methoden stehen in
        # chat_gespraeche.py.
        einfach = {"neu": self.neues_gespraech, "liste": lambda: self.seite.aufklappen(),
                   "einstellungen": lambda: self.einstellungen.oeffnen(),
                   "maus": self.maus_umschalten,
                   "archiv": self.archivieren_aktuell, "wiederholen": self.wiederholen,
                   "bearbeiten": self.bearbeiten, "denken": self.denken_umschalten}
        if name in einfach:
            einfach[name]()
            return
        if name == "titel":
            self.befehl_titel(arg)
            return
        if name in ("gedaechtnis", "skills"):      # gedaechtnis.py (Phase 3)
            self.gedaechtnis.oeffnen("skills" if name == "skills" else None)
            return
        if name == "ablage":                # Phase 5: Liste; anhang: chat_ablage.py
            self.ablageliste.oeffnen()
            return
        if name == "anhang":
            self.anhang_dazu(arg)
            return
        if name == "erlaubnis":             # chat_erlaubnis.py (2026-10-07)
            self.befehl_erlaubnis(arg)
            return
        if name in ("projekt", "projekte"):        # projekte.py (Phase 6)
            self.projekte.befehl(name, arg)
            return
        if name in ("lokal", "cloud", "auto"):
            self.setzen({"weg": name})
            return
        if arg:
            feld = {"modell": "modell", "anbieter": "anbieter",
                    "effort": "effort", "budget": "budget"}[name]
            self.setzen({feld: arg})
            return
        # Ohne Argument: zeigen bzw. zur Auswahl stellen.
        stand = self.einstellungen_holen()
        if stand is None:
            return
        if name == "budget":
            AI["msg"] = budget_text(stand)
            return
        wahl = auswahl(name, stand)
        if not wahl["optionen"]:
            AI["msg"] = "kein anbieter mit schlüssel — nichts zu wählen"
            return
        AI["wahl"] = wahl

    def einstellungen_holen(self):
        """GET /api/ai/einstellungen, oder None (Hinweis steht dann da)."""
        try:
            stand = api_call("/api/ai/einstellungen")
        except (urllib.error.URLError, OSError, ValueError):
            self.AI["msg"] = "keine verbindung zum backend"
            return None
        return stand if isinstance(stand, dict) else None

    def setzen(self, daten):
        """POST /api/ai/einstellungen; Ergebnis oder Klartext-Fehler in die
        Statuszeile, danach den Titel auffrischen."""
        AI = self.AI
        try:
            stand = api_call("/api/ai/einstellungen", "POST", daten)
        except urllib.error.HTTPError as e:
            grund = ""
            try:
                grund = json.loads(e.read().decode("utf-8", "replace")).get("error") or ""
            except Exception:
                pass
            AI["msg"] = grund or "fehler: HTTP %s" % e.code
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung zum backend"
            return
        stand = stand if isinstance(stand, dict) else {}
        if stand.get("tui_symbole"):                 # sofort neu zeichnen, nicht erst beim Poll
            AI["symbole"] = stand["tui_symbole"]
        AI["msg"] = stand_text(daten, stand)
        threading.Thread(target=self.status_holen, daemon=True).start()

    def _taste_wahl(self, ch):
        """Offene Auswahl (/modell, /anbieter, /effort): ↑↓ wählen, Enter
        oder Ziffer nimmt, Esc bricht ab. Bei /modell (Schlüssel „filter")
        filtert Tippen, ⌫ nimmt zurück, Ziffern gehören zum Filter."""
        AI = self.AI
        wahl = AI["wahl"]
        n = len(wahl["optionen"])
        if ch == 27:
            AI["wahl"] = None
        elif "filter" in wahl and ch in (curses.KEY_BACKSPACE, 127, 8):
            wahl_filtern(wahl, wahl["filter"][:-1])
        elif "filter" in wahl and isinstance(ch, int) and 32 <= ch < 127:
            wahl_filtern(wahl, wahl["filter"] + chr(ch))
        elif n == 0:
            pass
        elif ch == curses.KEY_UP:
            wahl["idx"] = (wahl["idx"] - 1) % n
        elif ch == curses.KEY_DOWN:
            wahl["idx"] = (wahl["idx"] + 1) % n
        elif ch in (10, 13, curses.KEY_ENTER) or (
                isinstance(ch, int) and ord("1") <= ch <= ord("9")
                and ch - ord("1") < n):
            idx = wahl["idx"] if ch in (10, 13, curses.KEY_ENTER) else ch - ord("1")
            AI["wahl"] = None
            # Eine Auswahl kann ihre eigene Aktion mitbringen (/projekt, Phase 6).
            (wahl.get("aktion") or self.setzen)(wahl["optionen"][idx][1])

    def _esc_lesen(self):
        """Nach einem ESC kurz (50 ms) schauen, was folgt — derselbe Weg
        wie Alt+Pfeil in der Karte (karte.m_alt_arrow). -> "esc",
        "alt_enter" oder None."""
        stdscr = self.z.stdscr
        folge = []
        try:
            stdscr.timeout(50)
            erst = stdscr.getch()
            if erst != -1:
                folge.append(erst)
                stdscr.nodelay(True)
                for _ in range(7):
                    nx = stdscr.getch()
                    if nx == -1:
                        break
                    folge.append(nx)
        finally:
            stdscr.timeout(250)
        return eingabe.esc_folge(folge)

    def tasten(self):
        """Was die Tasten gerade tun — für die Fußleiste (fussleiste.py) und
        tests/test_fussleiste.py, das jede davon im Chat drückt. Seit
        2026-10-07 je Zustand genau das, was wirkt (Sasha: „die leiste zeigt
        NUR das an was auch tatsächlich … genommen werden kann")."""
        AI = self.AI
        stopp = [("ctrl+c", "stop")] if AI.get("streaming") else []
        if AI.get("perm"):
            opts = AI["perm"].get("optionen") or ["ja", "nein"]
            return ([(str(i + 1), o) for i, o in enumerate(opts[:9])]
                    + [("esc", "decline")] + stopp)
        if AI.get("wahl"):
            return self._tasten_wahl(AI["wahl"])
        ueber = self._ueberlagerung()
        if ueber is not None:                  # Überlagerung offen: sie weiß es
            return stopp + ueber.tasten()
        fokus = AI.get("fokus") or "eingabe"
        weiter = [("f6", "next pane")]
        if fokus == "seite":
            return stopp + self.seite.tasten() + weiter
        if fokus == "rechts" and self.rechts.art():
            return stopp + self.rechts.tasten() + weiter
        if fokus == "verlauf":
            return stopp + self._tasten_verlauf() + weiter
        if AI.get("ersetzt"):
            return stopp + [("enter", "send edit"), ("alt+enter", "new line"),
                            ("esc", "cancel edit")]
        mehrzeilig = eingabe.mehrzeilig(AI["input"])
        liste = list(stopp)
        if not AI["streaming"] and AI["input"].strip():
            liste = [("enter", "send")]
        # Wichtigstes zuerst: auf 80 Spalten fällt hinten etwas weg.
        liste += [("esc", "close (keeps running)" if AI["streaming"] else "close"),
                  ("alt+enter", "new line"),
                  ("↑↓", "line") if mehrzeilig else ("↑↓", "scroll")]
        if mehrzeilig or AI["streaming"]:
            liste.append(("pgup pgdn", "scroll"))
        if not AI["input"]:
            liste.append(("tab", "hide chats" if self._seite_sichtbar() else "chats"))
        liste += [("/help", "commands"), ("ctrl+d", "thinking"), ("f6", "next pane"),
                  ("ctrl+o", "outputs"), ("ctrl+p", "model"), ("ctrl+t", "effort"),
                  ("ctrl+u", "attach"), ("ctrl+n", "new chat")]
        return liste

    def fusszeile(self):
        """Die Tastenzeile als Text (ohne führendes Leerzeichen)."""
        return fussleiste.text(self.tasten())

    def ungelesen(self):
        """● auf der Startseite: Neues in einem anderen Gespräch, oder eine
        Antwort, die fertig wurde, während das Fenster zu war."""
        return bool(self.AI.get("neu") or self.AI.get("fertig_ungesehen"))

    def ai_titel(self, breite=None):
        """Kasten-Titel: der Titel des offenen Gesprächs (seit 2026-10-07),
        der Kern, der gerade denkt — und was er heute gekostet hat.
        breite: so viele Zeichen höchstens (der Gesprächstitel wird gekürzt).

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
            gtitel = " ".join(str(AI.get("titel") or "").split())
            # Kasten-Titel „Projekt · Gespräch" (Phase 6, 2026-10-07).
            ptitel = " ".join(str(AI.get("projekt") or "").split())
        if ptitel:
            gtitel = ptitel + (" · " + gtitel if gtitel else "")
        if b == "local":
            rest = f" · lokal ({mdl})".lower()
        elif b != "cloud":
            rest = ""
        else:
            warn = " ⚠" if budget.get("status") in ("warn", "over") else ""
            rest = f" · cloud ({prov or mdl}) · {fmt_euro(eur)} heute{warn}".lower()
        kopf = neu + "ki-chat"
        if gtitel:
            # Der Gesprächstitel gibt nach, nicht Kosten oder Kern.
            platz = (breite - len(kopf) - len(rest) - 3) if breite else 40
            if platz >= 4:
                kopf += " · " + (gtitel if len(gtitel) <= platz else gtitel[:platz - 1] + "…")
        return (kopf + rest)[:breite] if breite else kopf + rest

    def oeffnen(self):
        """Startseite → Chat (Leertaste): Fokus her, das offene Gespräch im
        Hintergrund (neu) laden — es kann seit dem letzten Mal gewachsen sein
        (anderer Rechner). Liegt etwas Ungelesenes in einem ANDEREN
        Gespräch (meist „Erinnerungen"), sagt es die Statuszeile."""
        AI, ai_load_history = self.AI, self.ai_load_history
        AI["active"] = True; AI["scroll"] = 0; AI["msg"] = ""
        AI["fertig_ungesehen"] = False
        AI["fokus"] = "eingabe"
        if any(e.get("ungelesen") and e.get("id") != AI.get("gid")
               for e in AI.get("gespraeche") or []):
            AI["msg"] = "neues in einem anderen gespräch — tab zeigt die gespräche"
        if not AI["streaming"]:
            threading.Thread(target=ai_load_history, daemon=True).start()

    def taste(self, ch):
        """Eine Taste, während der Chat den Fokus hat. Belegung und die
        ↑↓-Regel: ansichten/eingabe.py (Kopf)."""
        AI, ai_answer_perm = self.AI, self.ai_answer_perm
        if ch == TASTE_STRG_C:
            # Stoppen (Sasha, 07.10.2026: „bei claude ist ctrl c intuitiv").
            # Im Chat beendet Strg+C NIE die TUI — auch nicht, wenn die
            # Antwort gerade fertig wurde und die Taste zu spät kam.
            if AI["streaming"]:
                self.stoppen()
            else:
                AI["msg"] = "es läuft keine antwort — esc schließt den chat"
            return
        if ch == 27:
            # Allein stehendes Esc oder Alt+Enter? Andere Alt-Tasten: nichts.
            art = self._esc_lesen()
            if art is None:
                return
            ch = TASTE_ALT_ENTER if art == "alt_enter" else 27
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
            return
        if ch == curses.KEY_MOUSE:         # Klick, Rad (maus.py)
            self.maus_ereignis()
            return
        if AI["wahl"]:
            self._taste_wahl(ch)
            return
        # Überlagerungen über dem Inhalt (Einstellungen, Gedächtnis, Projekte,
        # Ablage-Liste) nehmen alle Tasten.
        ueber = self._ueberlagerung()
        if ueber is not None:
            ueber.taste(ch)
            return
        if ch == curses.KEY_F6:            # Fokus weiter: Leiste → Verlauf → Eingabe → rechts
            self.fokus_weiter()
            return
        fokus = AI.get("fokus") or "eingabe"
        if fokus == "seite":               # Seitenleiste (seitenleiste.py)
            self.seite.taste(ch)
            return
        if fokus == "rechts" and self.rechts.art():
            self.rechts.taste(ch)
            return
        if fokus == "verlauf":
            self._taste_verlauf(ch)
            return
        if self._taste_strg(ch):
            return
        if ch == 27:
            # Esc schließt das Fenster — auch während einer Antwort, die dann
            # im Hintergrund weiterläuft (● auf der Startseite, wenn sie fertig
            # ist). Stoppen ist Strg+C. Sasha, 07.10.2026: „man soll dem
            # fenster escapen können ohne dass die antwort gestoppt wird".
            # Nur /bearbeiten bricht Esc zuerst ab (eine Stufe zurück).
            if AI.get("ersetzt"):
                AI["ersetzt"], AI["input"], AI["cur"] = None, "", 0
                AI["msg"] = "bearbeiten abgebrochen"
            else:
                AI["active"] = False
            return
        if ch == 9 and not AI["input"]:    # Tab bei leerer Eingabe: Gespräche auf/zu
            self.seite_umschalten()
            return
        if ch == 4:                        # Strg+D: Denken auf-/zuklappen
            self.denken_umschalten()
            return
        if ch in (10, 13, curses.KEY_ENTER):
            # Leere Eingabe + ein Dokument im Verlauf: Enter liest es.
            if not AI["input"].strip() and not AI["streaming"] \
                    and self.dokument_oeffnen_letztes():
                if self.rechts.dokument_offen():
                    AI["fokus"] = "rechts"
                return
            # \ am Zeilenende + Enter = neue Zeile, wie in der Shell.
            vorher = AI["input"], AI["cur"]
            art, text, pos = eingabe.enter_deuten(vorher[0], min(vorher[1], len(vorher[0])))
            AI["input"], AI["cur"] = text, pos
            if art == "senden":
                self.ai_submit()
                if AI["input"] == text:        # nicht abgeschickt (läuft noch,
                    AI["input"], AI["cur"] = vorher   # Tippfehler): \\ bleibt
            return
        if ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            AI["scroll"] = max(0, AI["scroll"] + (5 if ch == curses.KEY_PPAGE else -5))
            return
        if ch in (curses.KEY_UP, curses.KEY_DOWN) and not eingabe.mehrzeilig(AI["input"]):
            AI["scroll"] = max(0, AI["scroll"] + (1 if ch == curses.KEY_UP else -1))
            return
        self._taste_eingabe(ch)

    # Tasten, die den Cursor bewegen oder an ihm löschen → Funktion in eingabe.
    _BEARBEITEN = {
        curses.KEY_LEFT: eingabe.links, curses.KEY_RIGHT: eingabe.rechts,
        curses.KEY_HOME: eingabe.zeilenanfang, curses.KEY_FIND: eingabe.zeilenanfang,
        1: eingabe.zeilenanfang,                     # Strg+A
        curses.KEY_END: eingabe.zeilenende, curses.KEY_SELECT: eingabe.zeilenende,
        5: eingabe.zeilenende,                       # Strg+E
        curses.KEY_UP: eingabe.hoch, curses.KEY_DOWN: eingabe.runter,
        curses.KEY_BACKSPACE: eingabe.zurueck, 127: eingabe.zurueck, 8: eingabe.zurueck,
        curses.KEY_DC: eingabe.entfernen,
    }

    def denken_umschalten(self):
        """Strg+D, /denken: alles Denken im Verlauf auf- oder zuklappen."""
        AI = self.AI
        AI["denken_offen"] = not AI["denken_offen"]
        AI["msg"] = "denken aufgeklappt" if AI["denken_offen"] else "denken zugeklappt"

    def _taste_eingabe(self, ch):
        """Tippen und Bearbeiten im Eingabefeld (auch während eine Antwort
        läuft — nur Abschicken wartet)."""
        AI = self.AI
        text, pos = AI["input"], min(AI["cur"], len(AI["input"]))
        if ch in self._BEARBEITEN:
            text, pos = self._BEARBEITEN[ch](text, pos)
            AI["input"], AI["cur"] = text, pos
            if len(text) < eingabe.GRENZE:
                AI["zu_viel"] = 0          # wieder Platz: die Meldung ist erledigt
            return
        if ch == TASTE_ALT_ENTER:
            self._einfuegen("\n")
        elif ch == 9 or 32 <= ch <= 255:
            self._stoss(ch)

    def _stoss(self, ch):
        """Ein Zeichen — und alles, was gleich dahinter im Puffer liegt.

        Ein Einfügen (Strg+Shift+V) kommt als Tausende einzelner Bytes. Jedes
        einzeln hieße: ein ganzes Bild pro Byte, und ein Zeilenumbruch darin
        schickte die halbe Nachricht ab. Darum wird der Puffer hier in einem
        Rutsch geleert (2026-10-07); ein Enter MITTEN im Stoß ist eine neue
        Zeile. Endet ein langer Stoß mit Enter, war es auch eingefügt; ein
        kurzer (getippt, während gerade gezeichnet wurde) schickt ab."""
        AI, stdscr = self.AI, self.z.stdscr
        codes = [ch]
        try:
            stdscr.nodelay(True)
            while len(codes) < STOSS_MAX:
                nx = stdscr.getch()
                if nx == -1:
                    break
                codes.append(nx)
        finally:
            stdscr.timeout(250)
        teile, rest = [], []
        for i, c in enumerate(codes):
            if c in (10, 13):
                if i == len(codes) - 1 and len(codes) < STOSS_EINFUEGEN:
                    rest = [c]                 # getipptes Enter: abschicken
                    break
                teile.append("\n")
            elif c == 9:
                teile.append(" ")
            elif 32 <= c <= 126:
                teile.append(chr(c))
            elif 128 <= c <= 255:              # ein Byte eines Umlauts (UTF-8)
                AI["u8"], zeichen = eingabe.utf8_byte(AI.get("u8", b""), c)
                if zeichen is not None and eingabe.druckbar(zeichen):
                    teile.append(zeichen)
            else:                              # Pfeil, Esc, Steuerzeichen: Stoß endet
                rest = codes[i:]
                break
        if teile:
            self._einfuegen("".join(teile))
        # Der Rest ist schon aus dem Puffer genommen — ein ESC darin kann
        # nicht mehr selbst nach seiner Folgetaste schauen (_esc_lesen).
        i = 0
        while i < len(rest):
            if rest[i] == 27 and i + 1 < len(rest):
                if rest[i + 1] in eingabe.ENTER_CODES:
                    self.taste(TASTE_ALT_ENTER)
                    i += 2
                    continue
                break                          # andere Alt-Taste: nichts tun
            self.taste(rest[i])
            i += 1

    def _einfuegen(self, s):
        """s an der Cursorstelle einfügen; was über die Grenze ginge, wird
        gezählt (AI["zu_viel"]) und unten genannt — nie still verworfen."""
        AI = self.AI
        text, pos = AI["input"], min(AI["cur"], len(AI["input"]))
        neu, pos = eingabe.einfuegen(text, pos, s)
        AI["zu_viel"] = AI.get("zu_viel", 0) + len(s) - (len(neu) - len(text))
        AI["input"], AI["cur"] = neu, pos

    def _tasten_wahl(self, wahl):
        """Tasten der offenen Auswahl — Fußleiste und Hinweis darüber."""
        n = len(wahl.get("optionen") or [])
        liste = [("↑↓", "select")] if n > 1 else []
        if "filter" in wahl:                       # /model: tippen filtert
            liste.append(("type", "filter"))
        if n:
            liste.append(("enter", "take"))
        return liste + [("esc", "cancel")]
