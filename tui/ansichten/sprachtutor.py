# tui/ansichten/sprachtutor.py
#
# Der Sprach-Tutor in der TUI: Status, Session-Stream (/api/tutor/*),
# Slash-Befehle in derselben Zeile, das Persona-Zimmer als natives Fenster.
# Bis 06.10.2026 Closures in run_ui (tui/zentrale_tui.py), siehe
# memory/system/tui_bauplan.md. Heißt nicht tutor.py, damit es nicht mit dem
# Tutor-Projekt (tutor/) verwechselt wird — das hier ist nur der Zeichner.

import curses
import json
import os
import subprocess
import threading
import urllib.error
import urllib.request

from .basis import BASE_URL, PROJEKT, api_call, venv_python
from .chat import ai_wrap
from .text import _wrap


class Sprachtutor:
    """Das Text-Panel des Sprach-Tutors (Mitte). Mit Display öffnet 'u'
    stattdessen das Persona-Zimmer als eigenes Fenster (tutor_window); das
    Panel ist der Weg ohne Bildschirm (ssh, headless). Zustand in self.TUTOR
    (auch z.TUTOR), geschützt durch TUTOR_LOCK (Stream-Threads schreiben)."""

    def __init__(self, z):
        self.z = z
        # ── Sprach-Tutor (füllt die MITTE-Box, Taste 'u') ──────────────────
        # Angekabelt an das Backend über <BASE_URL>/api/tutor/*. Anders als der Chat
        # läuft der Tutor meist über die CLOUD (Default zh→qwen): die Session ist
        # ZUSTANDSBEHAFTET (start/stop), der Stream liefert nur token/done (keine
        # Erlaubnis-Fragen). Das Backend entscheidet per tutor.session.available()
        # anhand des AUFGELÖSTEN Providers, ob es überhaupt geht (ollama vs cloud);
        # ist es weg (cloud gedrosselt / offline), zeigt das Panel einen toten Smiley
        # statt einen /start ins Leere zu schicken. Slash-Befehle (/lang /provider
        # /model /models /tutorstop /cloud) tippt man in DIESELBE Zeile (Browser-
        # Konsolen-Prinzip) — beginnt die Eingabe mit '/', ist es ein Befehl, sonst
        # eine Antwort an den Tutor. Alle IO im Hintergrund-Thread, nie im Render/Input.
        #   session : läuft serverseitig eine Tutor-Session? (start setzt sie)
        #   avail   : Backend erreichbar? None=noch nicht geprüft, False=toter Smiley
        #   reason  : WARUM nicht — Klartext aus core/tutor_port.py ("Cloud ist per
        #             Kill-Switch gedrosselt", "Provider-Backend nicht erreichbar",
        #             "Tutor nicht installiert (…)"). Vorher riet die TUI hier selbst
        #             ("cloud gedrosselt? /cloud on") — mit Fragezeichen, weil sie den
        #             Grund gar nicht hatte. Der Kern weiß ihn, also fragen wir ihn.
        #   provider/model/lang/lang_name : aufgelöste Wahl (Kopfzeile)
        #   privacy : Datenschutz-Warnung (Provider trainiert auf Daten) oder None
        self.TUTOR = z.TUTOR = {"active": False, "input": "", "log": [], "answer": None,
                                "streaming": False, "scroll": 0, "session": False, "avail": None,
                                "provider": "", "model": "", "lang": "", "lang_name": "",
                                "persona_name": "", "country": "", "reason": "",
                                "privacy": None, "msg": "", "loaded": False, "proc": None}
        self.TUTOR_LOCK = threading.Lock()

    def tutor_refresh(self):
        """Status + Config vom Backend holen (Hintergrund): avail/session/privacy
        aus /api/tutor/status, provider/model/lang aus /api/tutor/config. Scheitert
        still → avail=False (toter Smiley)."""
        TUTOR, TUTOR_LOCK = self.TUTOR, self.TUTOR_LOCK
        try:
            st = api_call("/api/tutor/status")
        except (urllib.error.URLError, OSError, ValueError):
            st = None
        try:
            cf = api_call("/api/tutor/config")
        except (urllib.error.URLError, OSError, ValueError):
            cf = None
        with TUTOR_LOCK:
            if isinstance(st, dict):
                TUTOR["avail"]   = bool(st.get("available"))
                TUTOR["session"] = bool(st.get("active"))
                TUTOR["privacy"] = st.get("privacy_warning")
                TUTOR["reason"]  = st.get("reason") or ""
            else:
                TUTOR["avail"]  = False
                TUTOR["reason"] = "keine verbindung zum backend (zentrale-remote?)"
            if isinstance(cf, dict):
                TUTOR["provider"]     = cf.get("provider") or ""
                TUTOR["model"]        = cf.get("model") or ""
                TUTOR["lang"]         = cf.get("lang") or ""
                TUTOR["lang_name"]    = cf.get("lang_name") or ""
                TUTOR["persona_name"] = cf.get("persona_name") or ""
                TUTOR["country"]      = cf.get("country") or ""
                # Config warnt schon VOR Session-Start, falls der Provider trainiert
                if cf.get("trains_on_data") and not TUTOR["privacy"]:
                    TUTOR["privacy"] = "provider '%s' trainiert auf deine eingaben" % (
                        TUTOR["provider"],)
            TUTOR["loaded"] = True

    def tutor_open(self):
        """Panel-Öffnen-Ablauf im Hintergrund: Status holen, und wenn das Backend
        da ist und noch keine Session läuft, den Tutor SOFORT loslegen lassen
        (kein Enter, keine 'Stunde starten' — die Persona quatscht von selbst an).
        Läuft eine Session schon (esc/wieder auf), knüpft sie einfach weiter an."""
        TUTOR, TUTOR_LOCK, tutor_begin = self.TUTOR, self.TUTOR_LOCK, self.tutor_begin
        tutor_refresh = self.tutor_refresh
        tutor_refresh()
        with TUTOR_LOCK:
            avail     = TUTOR["avail"]
            session   = TUTOR["session"]
            streaming = TUTOR["streaming"]
        if avail and not session and not streaming:
            tutor_begin()

    def tutor_sse(self, url, payload):
        """Gemeinsamer SSE-Leser für /api/tutor/start + /respond. Füllt
        TUTOR['answer'] Token für Token, hängt die fertige Antwort ans log.
        503 → aufgelöstes Backend weg → avail=False (toter Smiley)."""
        TUTOR, TUTOR_LOCK = self.TUTOR, self.TUTOR_LOCK
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Accept": "text/event-stream"})
        resp = None
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            for raw in resp:
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                try:
                    evt = json.loads(line[5:].strip())
                except ValueError:
                    continue
                with TUTOR_LOCK:
                    if "token" in evt:
                        TUTOR["answer"] = (TUTOR["answer"] or "") + str(evt["token"])
                    elif "done" in evt:
                        break
        except urllib.error.HTTPError as e:
            # Der 503-Body trägt den Klartext-Grund aus core/tutor_port.py
            # (_tutor_unavail in ui/app.py) — lesen statt raten.
            detail = ""
            try:
                detail = (json.loads(e.read().decode("utf-8", "replace"))
                          .get("detail") or "")
            except (ValueError, OSError, AttributeError):
                pass
            with TUTOR_LOCK:
                if e.code == 503:
                    TUTOR["avail"] = False
                    TUTOR["session"] = False
                    TUTOR["reason"] = detail
                    TUTOR["msg"] = detail.lower() or "tutor-backend nicht erreichbar"
                else:
                    TUTOR["msg"] = "fehler: HTTP %s%s" % (
                        e.code, (" — " + detail.lower()) if detail else "")
        except (urllib.error.URLError, OSError):
            with TUTOR_LOCK:
                TUTOR["msg"] = "keine verbindung (zentrale-remote?)"
        finally:
            if resp is not None:
                try: resp.close()
                except OSError: pass
            with TUTOR_LOCK:
                ans = (TUTOR["answer"] or "").strip()
                if ans:
                    TUTOR["log"].append(("ai", ans))
                TUTOR["answer"] = None
                TUTOR["streaming"] = False

    def tutor_begin(self):
        """Session starten (KI begrüßt, user_text=None). Nur wenn erreichbar."""
        TUTOR, TUTOR_LOCK, tutor_sse = self.TUTOR, self.TUTOR_LOCK, self.tutor_sse
        with TUTOR_LOCK:
            if TUTOR["streaming"]:
                return
            if TUTOR["avail"] is False:
                TUTOR["msg"] = (TUTOR["reason"] or "tutor-backend nicht erreichbar").lower()
                return
            TUTOR["answer"]    = ""
            TUTOR["msg"]       = ""
            TUTOR["scroll"]    = 0
            TUTOR["session"]   = True
            TUTOR["streaming"] = True
        threading.Thread(target=tutor_sse,
                         args=(BASE_URL + "/api/tutor/start", {}), daemon=True).start()

    def tutor_say(self, text):
        """Antwort an den Tutor schicken (respond-Stream). Session muss laufen."""
        TUTOR, TUTOR_LOCK, tutor_sse = self.TUTOR, self.TUTOR_LOCK, self.tutor_sse
        with TUTOR_LOCK:
            if TUTOR["streaming"] or not text:
                return
            TUTOR["log"].append(("user", text))
            TUTOR["input"]     = ""
            TUTOR["answer"]    = ""
            TUTOR["msg"]       = ""
            TUTOR["scroll"]    = 0
            TUTOR["streaming"] = True
        threading.Thread(target=tutor_sse,
                         args=(BASE_URL + "/api/tutor/respond", {"text": text}),
                         daemon=True).start()

    def tutor_window(self):
        """Das Persona-ZIMMER im NATIVEN Fenster aufklappen (pygame,
        tutor/room.py) — wie die Karte per 'w'. Der Tutor ist keine
        Chat-Box, sondern eine Person: hier wohnt sie, läuft rum, sitzt auf der
        Couch. Detached gestartet (eigener Prozess), die TUI läuft weiter; das
        Fenster spricht dieselbe /api/tutor/*-Session. BASE_URL wird mitgereicht,
        damit es auch vom Laptop (zentrale-remote) ans PC-Backend findet.

        Gestartet wird NICHT room.py direkt, sondern der On-demand-Launcher
        scripts/open_tutor_room.py: der fährt die lokalen Audio-Dienste (Whisper
        :5050, TTS :5051) beim Öffnen hoch und beim Schließen wieder runter —
        weil 0RAMMachine die Modelle nicht ab Boot tragen darf. Was schon läuft
        (systemd am PC) bleibt unangetastet."""
        TUTOR, TUTOR_LOCK = self.TUTOR, self.TUTOR_LOCK
        root = PROJEKT
        py = venv_python(root)
        script = os.path.join(root, "scripts", "open_tutor_room.py")
        if not os.environ.get("DISPLAY"):
            with TUTOR_LOCK: TUTOR["msg"] = "kein DISPLAY (X11?)"
            return
        if not os.path.exists(script):
            with TUTOR_LOCK: TUTOR["msg"] = "open_tutor_room.py fehlt"
            return
        # Nur EIN Fenster: läuft das vorige noch (poll() is None), kein neues.
        proc = TUTOR.get("proc")
        if proc is not None and proc.poll() is None:
            with TUTOR_LOCK: TUTOR["msg"] = "zimmer läuft schon"
            return
        try:
            room_log = os.environ.get("ZENTRALE_ROOM_WINDOW_LOG") or "/tmp/zentrale-tutor-room.log"
            errf = open(room_log, "a", encoding="utf-8")
            TUTOR["proc"] = subprocess.Popen(
                [py, script, "--url", BASE_URL],
                stdout=subprocess.DEVNULL, stderr=errf, start_new_session=True)
            errf.close()
            with TUTOR_LOCK: TUTOR["msg"] = "zimmer offen (eigenes fenster)"
        except Exception as exc:
            with TUTOR_LOCK: TUTOR["msg"] = "zimmer-start: %s" % exc

    def tutor_cmd(self, buf):
        """Slash-Befehl aus der Tutor-Zeile (Browser-Konsolen-Prinzip). Kennt
        /tutor(start) /tutorstop /room /lang /provider /model /models /cloud.
        Live-Umschalten geht über /api/tutor/config (persist=False = nur laufende
        Instanz, wie im Browser). Alles kurz synchron (ein paar ms) + Refresh."""
        TUTOR, TUTOR_LOCK, store = self.TUTOR, self.TUTOR_LOCK, self.z.store
        tutor_begin, tutor_refresh = self.tutor_begin, self.tutor_refresh
        tutor_window = self.tutor_window
        parts = buf[1:].strip().split()
        with TUTOR_LOCK:
            TUTOR["input"] = ""
        if not parts:
            return
        name = parts[0].lower()
        arg  = " ".join(parts[1:]).strip()
        if name in ("tutor", "start"):
            tutor_begin(); return
        if name in ("room", "fenster", "zimmer"):    # Persona-Zimmer nativ öffnen
            threading.Thread(target=tutor_window, daemon=True).start(); return
        if name in ("tutorstop", "stop"):
            try: api_call("/api/tutor/stop", "POST", {})
            except (urllib.error.URLError, OSError, ValueError): pass
            with TUTOR_LOCK:
                TUTOR["session"] = False
                TUTOR["msg"]     = "tutor beendet"
            return
        if name == "cloud":                          # Tutor braucht meist Cloud
            want = None
            if arg.lower() in ("on", "an"):  want = True
            if arg.lower() in ("off", "aus"): want = False
            try:
                if want is None:
                    cur  = api_call("/api/ai/backends")
                    want = not (cur or {}).get("cloud_enabled", True)
                st = api_call("/api/ai/backends", "POST", {"cloud_enabled": bool(want)})
                store._poll_backends()
                with TUTOR_LOCK:
                    TUTOR["msg"] = "cloud " + ("AN" if (st or {}).get("cloud_enabled") else "GEDROSSELT")
            except (urllib.error.URLError, OSError, ValueError):
                with TUTOR_LOCK: TUTOR["msg"] = "cloud-schalter fehlgeschlagen"
            threading.Thread(target=tutor_refresh, daemon=True).start()
            return
        if name == "lang":
            # Sprache = Spielstand (seit 2026-09-17): wechseln heißt im Zimmer
            # (Esc → Hauptmenü) einen anderen Stand laden — sonst bluten Stände.
            with TUTOR_LOCK: TUTOR["msg"] = "sprache gehört zum spielstand — im zimmer: Esc → Hauptmenü"
            return
        if name in ("provider", "model"):
            if not arg:
                with TUTOR_LOCK: TUTOR["msg"] = "nutze /%s <wert>" % name
                return
            try:
                api_call("/api/tutor/config", "POST", {name: arg})
                with TUTOR_LOCK: TUTOR["msg"] = "%s → %s" % (name, arg)
            except (urllib.error.URLError, OSError, ValueError):
                with TUTOR_LOCK: TUTOR["msg"] = "%s-wechsel fehlgeschlagen" % name
            threading.Thread(target=tutor_refresh, daemon=True).start()
            return
        if name in ("models", "model?"):
            try:
                cf = api_call("/api/tutor/config")
            except (urllib.error.URLError, OSError, ValueError):
                cf = None
            with TUTOR_LOCK:
                if isinstance(cf, dict):
                    provs = ", ".join(p.get("name") for p in cf.get("providers", [])
                                      if p.get("enabled"))
                    TUTOR["msg"] = "jetzt: %s · %s · %s — wählbar: %s" % (
                        cf.get("provider"), cf.get("model"), cf.get("lang"),
                        provs or "—")
                else:
                    TUTOR["msg"] = "modelle nicht lesbar"
            return
        with TUTOR_LOCK:
            TUTOR["msg"] = "unbekannt: /%s" % name

    def oeffnen(self):
        """Taste 'u' auf der Startseite: mit Display das Persona-Zimmer als
        eigenes Fenster, ohne (headless/ssh) das Text-Panel. (Kommt die TUI
        selbst aus dem Zimmer, entscheidet run_ui vorher: zurück ins Zimmer.)"""
        if os.environ.get("DISPLAY"):
            # kein Umweg mehr über Panel + /room: das Zimmer geht auf, die
            # Persona quatscht dort von selbst los (Session startet im Fenster).
            threading.Thread(target=self.tutor_window, daemon=True).start()
        else:
            # kein grafisches Display (headless/ssh) → Text-Panel als Fallback
            self.oeffnen_panel()

    def oeffnen_panel(self):
        """Das Text-Panel öffnen (ohne Display, oder per /tutor): Status holen
        und, falls das Backend da ist und keine Session läuft, die Persona
        sofort loslegen lassen (tutor_open im Hintergrund)."""
        TUTOR, tutor_open = self.TUTOR, self.tutor_open
        TUTOR["active"] = True; TUTOR["scroll"] = 0; TUTOR["msg"] = ""
        threading.Thread(target=tutor_open, daemon=True).start()

    def taste(self, ch):
        """Eine Taste, während das Tutor-Panel den Fokus hat (früher ein Zweig
        der Hauptschleife in run_ui)."""
        TUTOR, TUTOR_LOCK, tutor_begin = self.TUTOR, self.TUTOR_LOCK, self.tutor_begin
        tutor_cmd, tutor_say = self.tutor_cmd, self.tutor_say
        if ch == 27:                       # esc schließt Panel (Session bleibt aktiv)
            TUTOR["active"] = False
        elif ch in (10, 13, curses.KEY_ENTER):
            buf = TUTOR["input"].strip()
            if buf.startswith("/"):        # /befehl (reden vs. steuern in EINER zeile)
                tutor_cmd(buf)
            elif not TUTOR["session"]:     # Fallback: falls Auto-Start (tutor_open)
                with TUTOR_LOCK: TUTOR["input"] = ""   # noch nicht lief (Backend kam später)
                tutor_begin()
            elif buf:                      # session läuft + text → antworten
                tutor_say(buf)
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if not TUTOR["streaming"]:
                TUTOR["input"] = TUTOR["input"][:-1]
        elif ch == curses.KEY_UP:
            TUTOR["scroll"] += 1
        elif ch == curses.KEY_DOWN:
            TUTOR["scroll"] = max(0, TUTOR["scroll"] - 1)
        elif ch == curses.KEY_PPAGE:
            TUTOR["scroll"] += 5
        elif ch == curses.KEY_NPAGE:
            TUTOR["scroll"] = max(0, TUTOR["scroll"] - 5)
        elif 32 <= ch <= 126 and not TUTOR["streaming"] and len(TUTOR["input"]) < 1000:
            TUTOR["input"] += chr(ch)

    def draw_tutor(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn der Sprach-Tutor Fokus hat. Reiner Zeichner:
        Kopfzeile (aufgelöste Wahl + Privacy-Ampel), Verlauf/laufende Antwort,
        Info- + Eingabezeile. Ist das Backend weg (avail=False) → toter Smiley."""
        C, TUTOR, TUTOR_LOCK = self.z.C, self.TUTOR, self.TUTOR_LOCK
        addclip = self.z.addclip
        inx = bx + 2
        inw = max(6, bw - 4)
        input_y  = by + bh - 2
        info_y   = by + bh - 3
        head_y   = by + 1
        body_top = by + 2
        body_bot = by + bh - 4
        rows = max(1, body_bot - body_top + 1)

        with TUTOR_LOCK:
            log       = list(TUTOR["log"])
            answer    = TUTOR["answer"]
            streaming = TUTOR["streaming"]
            inp       = TUTOR["input"]
            msg       = TUTOR["msg"]
            scroll    = TUTOR["scroll"]
            session   = TUTOR["session"]
            av        = TUTOR["avail"]
            reason    = TUTOR["reason"]
            prov      = TUTOR["provider"]
            model     = TUTOR["model"]
            lang      = TUTOR["lang"]
            persona   = TUTOR["persona_name"]
            privacy   = TUTOR["privacy"]

        # Kopfzeile: Persona-Name (Ling Ling) links + aufgelöste Wahl, Ampel rechts
        head = persona or "tutor"
        sel = " · ".join(x for x in (model or prov, lang) if x)
        if sel:
            head += " · " + sel
        pflag = "⚠ trainiert" if privacy else ("· ok" if (prov or lang) else "")
        addclip(head_y, inx, head, max(1, inw - len(pflag) - 1), C["dim"])
        if pflag:
            addclip(head_y, inx + max(0, inw - len(pflag)), pflag, len(pflag),
                    C["warn"] if privacy else C["faint"])

        if av is False:                          # Backend weg → toter Smiley + GRUND
            # Der Grund kommt fertig aus core/tutor_port.py durch /api/tutor/status.
            # Vorher stand hier fest "cloud gedrosselt? · /cloud on" — eine Vermutung,
            # die bei fehlendem tutor/ oder totem Ollama schlicht falsch war.
            why = (reason or "tutor-backend nicht erreichbar").lower()
            face = ["x_x"] + _wrap(why, max(8, inw - 2))
            face = face[:max(1, rows)]
            cy = body_top + max(0, rows // 2 - len(face) // 2)
            for i, ln in enumerate(face):
                addclip(cy + i, inx + max(0, (inw - len(ln)) // 2), ln, inw,
                        C["warn"] if i == 0 else C["faint"])
        else:
            lines = []
            for role, text in log:
                lines += ai_wrap(role, text, inw)
                lines.append(("gap", ""))
            if answer is not None:
                lines += ai_wrap("ai", answer + ("▌" if streaming else ""), inw)
            if not lines:
                hint = ((persona or "die persona") + " meldet sich gleich…" if not session else
                        "tippen + enter · /room = eigenes fenster · /lang /provider /model /tutorstop")
                addclip(body_top + rows // 2, inx, hint[:inw], inw, C["faint"])
            else:
                total = len(lines)
                maxscroll = max(0, total - rows)
                sc = min(scroll, maxscroll)
                start = max(0, total - rows - sc)
                y = body_top
                for kind, seg in lines[start:start + rows]:
                    attr = C["acc"] if kind == "user" else (
                        C["bright"] if kind == "ai" else C["faint"])
                    addclip(y, inx, seg, inw, attr)
                    y += 1

        # Info-Zeile: Status/Fehler > Privacy-Warnung > Scroll-Hinweis
        if msg:
            addclip(info_y, inx, msg[:inw], inw, C["warn"])
        elif privacy:
            addclip(info_y, inx, ("⚠ " + str(privacy))[:inw], inw, C["warn"])
        elif scroll > 0:
            addclip(info_y, inx, "↑ verlauf (↓ nach unten)", inw, C["faint"])

        # Eingabezeile: Stream läuft > Backend weg > normale Eingabe
        if streaming:
            addclip(input_y, inx, "› …", inw, C["dim"])
        elif av is False:
            addclip(input_y, inx, "› /cloud on  gibt die cloud frei", inw, C["faint"])
        else:
            shown = "› " + inp
            if len(shown) > inw - 1:
                shown = "› …" + inp[-(inw - 5):]
            addclip(input_y, inx, shown + "_", inw, C["bright"])
