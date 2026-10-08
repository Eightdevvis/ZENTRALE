# tui/ansichten/chat_zeichnen.py
#
# Das Bild des Chats nach dem Vorbild von Claude Web (2026-10-07): ein Mixin
# für Chat (chat.py), damit chat.py bei Zustand, Strom und Tasten bleibt.
# Aufteilung: chat_layout.py (Skizze dort). Verlauf: verlauf.py. Leiste
# links: seitenleiste.py. Rechts: rechts.py. Denk-Animation: denkadern.py.
#
# Jedes Bild legt die anklickbaren Flächen neu an (self.klicks, Maus:
# maus.py) — gezeichnet und geklickt wird also immer dasselbe.

import curses
import time

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel

from . import chat_layout, denkadern, eingabe, fussleiste
from . import verlauf as V
from .text import _wrap


class ChatZeichnen:

    # ── Klickflächen ───────────────────────────────────────────────────
    def klickbar(self, y, x, w, aktion):
        """Eine Fläche (eine Zeile, x … x+w) löst beim Klick `aktion()` aus."""
        if w > 0:
            self.klicks.append((y, x, x + w, aktion))

    def rad_flaeche(self, y, x, h, w, was):
        """Hier scrollt das Mausrad `was` ("verlauf", "dokument", "seite")."""
        self.raeder.append((y, x, y + h, x + w, was))

    def fokus_setzen(self, wohin):
        self.AI["fokus"] = wohin
        if wohin == "seite":
            self.seite.fokus()

    # ── Das Bild ───────────────────────────────────────────────────────
    def aufteilung(self, bx, bw):
        AI = self.AI
        art = self.rechts.art()
        a = chat_layout.aufteilen(bx, bw, self.seite.offen(bw), art, AI.get("gross"))
        AI["seite_voll"] = bool(a.seite and a.mitte is None and a.rechts is None)
        self._letzte = a                     # für Tab und F6 (chat_bedienung.py)
        return a

    def draw_ai(self, by, bx, bh, bw):
        """Inhalt des Chat-Kastens: Seitenleiste | Verlauf + Eingabe | rechts.
        Reiner Zeichner (liest AI unter Lock); der Strom läuft in ai_stream."""
        self.klicks, self.raeder = [], []
        a = self.aufteilung(bx, bw)
        top, h = by + 1, max(1, bh - 2)
        self._fokus_pruefen(a)
        if a.seite:
            self.seite.zeichnen(top, a.seite.x, h, a.seite.w)
            self._trenner(top, a.seite.x + a.seite.w, h)
            self.rad_flaeche(top, a.seite.x, h, a.seite.w, "seite")
        elif a.leiste:
            self.seite.zeichnen_leiste(top, a.leiste.x, h)
            self._trenner(top, a.leiste.x + a.leiste.w, h)
        # Rechts der Leiste: der Inhalt (Überlagerungen nehmen ihn ganz)
        reste = [b for b in (a.mitte, a.rechts) if b]
        if not reste:
            return
        cx = reste[0].x
        cw = reste[-1].x + reste[-1].w - cx
        ueber = self._ueberlagerung()
        if ueber is not None:
            ueber.zeichnen(by, cx - 1, bh, cw + 2)
            return
        if a.mitte:
            self._mitte(top, a.mitte, h)
        if a.rechts:
            if a.mitte:
                self._trenner(top, a.rechts.x - 1, h)
            self.rechts.zeichnen(top, a.rechts.x, h, a.rechts.w)
        if self.AI.get("bewertung"):          # kleines Fenster obenauf (bewertung.py)
            m = a.mitte or reste[0]
            self.bewertung.zeichnen(top, m.x, h, m.w)

    def _ueberlagerung(self):
        """Was den Inhalt ganz überdeckt (Einstellungen, Gedächtnis, Projekte,
        Ablage-Liste) — oder None."""
        AI = self.AI
        if AI.get("einstellungen"):
            return self.einstellungen
        if AI.get("gedaechtnis"):
            return self.gedaechtnis
        if AI.get("projekte"):
            return self.projekte
        if AI.get("ablage") and not AI["ablage"].get("direkt"):
            return self.ablageliste
        return None

    def _fokus_pruefen(self, a):
        """Der Fokus darf nicht auf etwas liegen, das nicht zu sehen ist."""
        AI = self.AI
        f = AI.get("fokus") or "eingabe"
        if f == "seite" and not a.seite:
            f = "eingabe"
        if f == "rechts" and not a.rechts:
            f = "eingabe"
        if f in ("eingabe", "verlauf") and not a.mitte:
            f = "rechts" if a.rechts else ("seite" if a.seite else "eingabe")
        AI["fokus"] = f

    def _trenner(self, top, x, h):
        for y in range(top, top + h):
            self.z.safe_addstr(y, x, "│", self.z.C["faint"])

    # ── Mitte: Kopf, Verlauf, Eingabe ──────────────────────────────────
    def _mitte(self, top, bereich, h):
        AI, AI_LOCK, C = self.AI, self.AI_LOCK, self.z.C
        addclip = self.z.addclip
        with AI_LOCK:
            log = list(AI["log"])
            answer = AI["answer"]
            reflect = AI["reflect"]
            streaming = AI["streaming"]
            perm = dict(AI["perm"]) if AI["perm"] else None
            inp = AI["input"]
            cur = min(AI["cur"], len(inp))
            msg = AI["msg"]
            wahl = AI["wahl"]
            wahl = dict(wahl, optionen=list(wahl["optionen"])) if wahl else None
            zu_viel = AI.get("zu_viel", 0)
            anhaenge = list(AI.get("anhaenge") or [])
        sp = chat_layout.spalte(bereich)
        # Kopf: Titel ▾ links, Outputs rechts
        titel = " ".join(str(AI.get("titel") or "").split()) or "new chat"
        if AI.get("projekt"):
            titel = "%s · %s" % (AI["projekt"], titel)
        n_docs = sum(1 for r, _t in log if r == "ablage")
        rechts_txt = " ▤ %d " % n_docs if n_docs else " ▤ "
        tw = max(4, bereich.w - 4 - len(rechts_txt))
        if len(titel) + 2 > tw:
            titel = titel[:max(1, tw - 3)] + "…"
        addclip(top, bereich.x + 2, titel + " ▾", tw, C["dim"])
        self.klickbar(top, bereich.x + 2, len(titel) + 2, self.menue_gespraech)
        rx = bereich.x + bereich.w - len(rechts_txt) - 1
        addclip(top, rx, rechts_txt, len(rechts_txt),
                (C["acc"] | curses.A_REVERSE) if self.rechts.art() == "outputs" else C["dim"])
        self.klickbar(top, rx, len(rechts_txt), self.rechts.outputs_umschalten)

        # Unten: Fuß (Frage/Auswahl/Info), Eingabekasten, Leiste darunter
        fuss = self._fuss(perm, wahl, msg, reflect, streaming, inp, zu_viel, sp.w)
        kasten = self._kasten_zeilen(inp, cur, anhaenge, sp.w, h, streaming)
        unten = top + h                      # erste Zeile NACH dem Bereich
        leiste_y = unten - 1
        kasten_y = leiste_y - 1 - len(kasten)     # Rahmen oben: kasten_y - 1
        fuss = fuss[-max(0, kasten_y - 1 - (top + 3)):] if fuss else fuss
        fuss_y = kasten_y - 1 - len(fuss)
        self._kasten(kasten_y, sp, kasten, streaming)
        self._leiste_unten(leiste_y, sp)
        for i, (text, attr) in enumerate(fuss):
            addclip(fuss_y + i, sp.x, text, sp.w, attr)
        if wahl and not perm and getattr(self, "_wahl_zeilen", None):
            oben, n = self._wahl_zeilen          # jede Option anklickbar
            for k in range(n):
                self.klickbar(fuss_y + 1 + k, sp.x, sp.w,
                              lambda i=oben + k: self.wahl_nehmen(i))

        # Verlauf zwischen Kopf und Fuß
        v_oben, v_unten = top + 2, fuss_y - 1
        platz = max(1, v_unten - v_oben + 1)
        self.rad_flaeche(v_oben, bereich.x, platz, bereich.w, "verlauf")
        self._verlauf(v_oben, platz, sp, log, answer, streaming, bereich)

    def _fuss(self, perm, wahl, msg, reflect, streaming, inp, zu_viel, w):
        """Zeilen über dem Eingabekasten: Erlaubnis-Frage, Auswahl oder eine
        Info-Zeile (Grenze > Denk-Strom > Hinweis > was gerade geht)."""
        C = self.z.C
        if perm:
            opts = perm.get("optionen") or ["ja", "nein"]
            label = "  ".join("%d) %s" % (i + 1, o) for i, o in enumerate(opts))
            frage = (perm.get("frage") or "darf ich?").replace("\n", " ")
            return [(ln, C["warn"]) for ln in _wrap("? " + frage, w) + (_wrap("› " + label, w) or ["›"])]
        if wahl:
            return self._fuss_wahl(wahl, w, 30)
        grenze = eingabe.grenz_meldung(len(inp), zu_viel)
        zaehler = eingabe.zaehler(len(inp))
        if grenze:
            return [(ln, C["warn"] | curses.A_BOLD) for ln in _wrap(grenze, w)]
        if streaming and reflect:
            zeile = (("thinking: " + reflect.replace("\n", " "))[-w:], C["faint"])
        elif msg:
            zeile = (msg[:w], C["warn"])
        elif streaming:
            zeile = ("answering … ctrl+c stops · esc closes (keeps running)"[:w], C["faint"])
        else:
            zeile = ("", 0)
        if zaehler:
            platz = max(0, w - len(zaehler) - 2)
            zeile = (zeile[0][:platz].ljust(platz) + "  " + zaehler, zeile[1] or C["faint"])
        return [zeile]

    def _kasten_zeilen(self, inp, cur, anhaenge, w, h, streaming):
        """Der Inhalt des Eingabekastens: [(text, art)] mit art "chip",
        "platzhalter", "text" (+ Cursor-Lage in self._cursor)."""
        innen = max(4, w - 4)
        zeilen = []
        if anhaenge:
            chips = "  ".join("[▤ %s]" % str(a.get("titel") or "datei") for a in anhaenge)
            zeilen.append((chips[:innen], "chip"))
        hoehe = max(1, min(eingabe.HOEHE, h - 8))
        self._cursor = None
        if not inp:
            zeilen.append(("Reply", "platzhalter"))
            self._cursor = (len(zeilen) - 1, 0, "R")
            return zeilen
        tz, cy, cx, oben = eingabe.anzeige(inp, cur, innen, hoehe)
        for i, t in enumerate(tz):
            zeilen.append((t, "text"))
        self._cursor = (len(zeilen) - len(tz) + cy, cx,
                        tz[cy][cx] if cx < len(tz[cy]) else " ")
        return zeilen

    def _kasten(self, y0, sp, zeilen, streaming):
        """Der Eingabekasten: Rahmen (Fokus = Akzentfarbe), Zeilen, Cursor."""
        C, addclip, safe = self.z.C, self.z.addclip, self.z.safe_addstr
        AI = self.AI
        fokus = AI.get("fokus") == "eingabe"
        rahmen = C["acc"] if fokus else C["faint"]
        w = sp.w
        addclip(y0 - 1, sp.x, "┌" + "─" * (w - 2) + "┐", w, rahmen)
        for i, (text, art) in enumerate(zeilen):
            y = y0 + i
            addclip(y, sp.x, "│", 1, rahmen)
            addclip(y, sp.x + w - 1, "│", 1, rahmen)
            attr = {"chip": C["acc"], "platzhalter": C["faint"]}.get(
                art, C["dim"] if streaming else C["bright"])
            addclip(y, sp.x + 2, text, w - 4, attr)
            self.klickbar(y, sp.x, w, lambda: self.fokus_setzen("eingabe"))
        addclip(y0 + len(zeilen), sp.x, "└" + "─" * (w - 2) + "┘", w, rahmen)
        if fokus and self._cursor is not None:
            cy, cx, ch = self._cursor
            if cx < w - 4:
                safe(y0 + cy, sp.x + 2 + cx, ch, C["bright"] | curses.A_REVERSE)
        self.klickbar(y0 - 1, sp.x, w, lambda: self.fokus_setzen("eingabe"))

    def _leiste_unten(self, y, sp):
        """Unter dem Kasten: „+ attach" links, Modell · Effort rechts — beides
        anklickbar (öffnet die vorhandene Auswahl)."""
        AI, C, addclip = self.AI, self.z.C, self.z.addclip
        addclip(y, sp.x + 1, "+", 1, C["acc"])
        addclip(y, sp.x + 3, "attach", 6, C["faint"])
        self.klickbar(y, sp.x, 9, self.anhang_vorbereiten)
        modell = AI.get("model") or "—"
        if AI.get("backend") == "local":
            modell = "lokal · " + modell
        effort = AI.get("effort") or ""
        rechts = modell + (" · " + effort if effort and AI.get("backend") == "cloud" else "")
        rechts = rechts[:max(1, sp.w - 12)]
        rx = sp.x + sp.w - len(rechts) - 1
        addclip(y, rx, rechts, len(rechts), C["dim"])
        self.klickbar(y, rx, len(modell), lambda: self.befehl("modell", ""))
        if effort and AI.get("backend") == "cloud":
            self.klickbar(y, rx + len(modell) + 3, len(effort), lambda: self.befehl("effort", ""))

    # ── Verlauf ────────────────────────────────────────────────────────
    def _verlauf(self, y0, platz, sp, log, answer, streaming, bereich):
        AI, C, z = self.AI, self.z.C, self.z
        if not log and answer is None and self._auge(y0, platz, bereich):
            return
        jetzt = time.monotonic()
        adern, ausklang, dauer = self._adern_lage(streaming, answer, jetzt)
        n_adern = denkadern.hoehe_fuer(platz) if adern else 0
        zeilen = V.verlauf_zeilen(
            log, sp.w, offen=AI.get("offen") or frozenset(),
            denken_alle=AI.get("denken_offen"), letzte_ai=V.letzte_antwort(log),
            antwort=answer, adern=n_adern, streaming=streaming,
            adern_bei=self._adern_bei(log, streaming), bewertet=self.bewertung.marken(log))
        self._ziele = V.ziele(zeilen)
        if not zeilen:
            hinweis = "frag die ki — tippen + enter · /help"
            z.addclip(y0 + platz // 2, sp.x, hinweis, sp.w, C["faint"])
            return
        total = len(zeilen)
        maxscroll = max(0, total - platz)
        vw = AI.get("vwahl") if AI.get("fokus") == "verlauf" else None
        if vw is not None and AI.pop("vwahl_folgen", False):
            pos = next((i for i, zl in enumerate(zeilen) if any(s[2] == vw for s in zl)), None)
            if pos is not None:
                start = total - platz - AI["scroll"]
                if pos < start:
                    AI["scroll"] = total - platz - pos
                elif pos >= start + platz:
                    AI["scroll"] = max(0, total - pos - 1)
        AI["scroll"] = min(AI["scroll"], maxscroll)
        start = max(0, total - platz - AI["scroll"])
        stile = self._stile()
        adern_y = None
        for r, zeile in enumerate(zeilen[start:start + platz]):
            y, x = y0 + r, sp.x
            for text, stil, ziel in zeile:
                if stil == "adern":
                    adern_y = y if adern_y is None else adern_y
                    continue
                attr = stile.get(stil, C["dim"])
                if ziel is not None and ziel == vw:
                    attr = C["bright"] | curses.A_REVERSE
                z.addclip(y, x, text, max(0, sp.x + sp.w - x), attr)
                if ziel is not None:
                    self.klickbar(y, x, len(text), lambda zz=ziel: self.ziel_ausloesen(zz))
                x += len(text)
        if n_adern and adern_y is not None:
            # erste sichtbare Adern-Zeile; oben abgeschnittene fehlen dann
            vor = max(0, (start - next(i for i, zl in enumerate(zeilen)
                                        if zl and zl[0][1] == "adern")))
            self._adern_malen(adern_y, sp, n_adern, vor, jetzt, dauer, ausklang)

    def _stile(self):
        C = self.z.C
        user = C["bright"]
        if C.get("pix_bg") is not None:
            bg = C["pix_bg"]
            hell = sum(bg) >= 384
            fl = pixel.mix(bg, (0, 0, 0) if hell else (255, 255, 255), .1)
            user = self.z.pix_attr((0, 0, 0) if hell else (255, 255, 255), fl)
        else:
            user = C["bright"] | curses.A_REVERSE
        return {"user": user, "ai": C["bright"], "ai_kopf": C["acc"] | curses.A_BOLD,
                "ai_code": C["dim"], "ai_liste": C["bright"], "schritt": C["faint"],
                "schritt_fehler": C["warn"], "denken": C["faint"], "dok": C["acc"],
                "anhang": C["acc"], "aktion": C["faint"], "leise": C["faint"],
                "aktion_an": C["acc"] | curses.A_BOLD,
                "hinweis": C["dim"]}

    def _adern_lage(self, streaming, answer, jetzt):
        """Läuft die Denk-Animation? -> (an, ausklang 0..1, dauer s).
        Sie läuft, solange auf Text gewartet wird; danach zieht sie sich
        AUSKLANG_S lang zurück."""
        AI = self.AI
        t0 = AI.get("denk_t0")
        if t0 is None:
            return False, 0.0, 0.0
        wartet = streaming and not (answer or "").strip()
        if wartet:
            AI["denk_ende"] = None
            return True, 0.0, jetzt - t0
        if AI.get("denk_ende") is None:
            AI["denk_ende"] = jetzt
        seit = jetzt - AI["denk_ende"]
        if seit >= denkadern.AUSKLANG_S:
            AI["denk_t0"] = None
            return False, 0.0, 0.0
        return True, seit / denkadern.AUSKLANG_S, AI["denk_ende"] - t0

    def _adern_bei(self, log, streaming):
        """Nach dem Strom: die Adern ziehen sich dort zurück, wo die Antwort
        dieses Zugs beginnt (vor ihr, hinter den Schritten)."""
        if streaming:
            return None
        n = self.AI.get("denk_log_n") or 0
        letzte = V.letzte_antwort(log)
        return letzte if letzte is not None and letzte >= n else None

    def adern_laufen(self):
        """Leben die Denk-Adern gerade (Warten oder Rückzug)?"""
        return self.AI.get("denk_t0") is not None

    def nur_adern(self):
        """Für die Hauptschleife: bewegen sich nur die Adern (kein Text, der
        gerade einläuft)? Dann reicht ihr eigener Takt (100 ms); im Rückzug
        nach dem Strom ebenso."""
        AI = self.AI
        return self.adern_laufen() and not (AI.get("answer") or "").strip()

    def _adern_malen(self, y, sp, n, vor, jetzt, dauer, ausklang):
        C, z = self.z.C, self.z
        if C.get("pix_bg") is None or z.PIX_MODUS == "off":
            if vor == 0:
                z.addclip(y + n // 2, sp.x + sp.w // 2 - 1, "···"[:3], 3, C["acc"])
            return
        thema = "nacht" if sum(C["pix_bg"]) < 384 else "tag"
        zellen = denkadern.adern_zellen(jetzt, dauer, sp.w, n, thema, ausklang)
        for r, zeile in enumerate(zellen[vor:]):
            for c, f in enumerate(zeile):
                if f:
                    z.safe_addstr(y + r, sp.x + c, f[0], z.pix_attr(f[1], f[2]))

    def _auge(self, y0, platz, bereich):
        """Leerer Chat: das Auge (Sasha, 04.10.2026) mittig, darunter der
        Hinweis. -> True, wenn gezeichnet."""
        AI, C, z = self.AI, self.z.C, self.z
        if C.get("pix_bg") is None or z.PIX_MODUS == "off" or bereich.w < pixel.AUGE_W + 4 \
                or platz < pixel.AUGE_H + 3:
            return False
        jetzt = time.monotonic()
        if AI.get("auge_t0") is None:
            AI["auge_t0"] = jetzt
        seit = jetzt - AI["auge_t0"]
        farben = "nacht" if sum(C["pix_bg"]) < 384 else "tag"
        auge = pixel.auge_zellen(round(min(1.0, seit / .45), 2), int(seit * 1000),
                                 AI["streaming"], farben, "half" if z.PIX_MODUS == "half" else "mix")
        ey = y0 + max(0, (platz - pixel.AUGE_H - 2) // 2)
        ex = bereich.x + (bereich.w - pixel.AUGE_W) // 2
        for r, line in enumerate(auge):
            for c, f in enumerate(line):
                if f:
                    z.safe_addstr(ey + r, ex + c, f[0], z.pix_attr(f[1], f[2]))
        hinweis = "frag die ki — tippen + enter · /help"
        z.addclip(ey + pixel.AUGE_H + 1, bereich.x + max(2, (bereich.w - len(hinweis)) // 2),
                  hinweis, bereich.w - 4, C["faint"])
        return True

    # ── Auswahl im Fuß ─────────────────────────────────────────────────
    def _fuss_wahl(self, wahl, inw, bh):
        """Die offene Auswahl als Fußzeilen: Titel, ein Fenster der Optionen
        um die gewählte herum, Hinweis. Jede Option ist anklickbar."""
        C = self.z.C
        opts, idx = wahl["optionen"], wahl["idx"]
        platz = max(1, min(len(opts), bh - 6, 9)) if opts else 0
        oben = max(0, min(idx - platz // 2, len(opts) - platz))
        titel = wahl["titel"]
        if "filter" in wahl:
            titel += " · %d von %d" % (len(opts), len(wahl["alle"]))
            if wahl["filter"]:
                titel += " · filter: " + wahl["filter"]
        zeilen = [(titel[:inw], C["acc"])]
        if not opts:
            zeilen.append(("  nichts passt", C["dim"]))
        for i in range(oben, oben + platz):
            zeichen = "›" if i == idx else " "
            nr = "%d) " % (i + 1) if i < 9 and "filter" not in wahl else "   "
            zeilen.append(("%s %s%s" % (zeichen, nr, opts[i][0]),
                           C["bright"] if i == idx else C["dim"]))
        zeilen.append((fussleiste.text(self._tasten_wahl(wahl))[:inw], C["faint"]))
        self._wahl_zeilen = (oben, platz)
        return zeilen
