# tui/ansichten/einstellungen.py
#
# „Customize" des Chats wie die Einstellungen von Claude Web (Vorlage
# skill.png, 2026-10-07): links die Abschnitte, rechts das Einzelne.
#   Skills       Liste + ein Skill im Einzelnen: an/aus, Beschreibung,
#                Herkunft, „braucht"
#   Memory       Hausregeln, Steckbrief, Ziele, Bereiche (dieselben Zeilen
#                wie die Gedächtnis-Ansicht, gedaechtnis.inhalt_zeilen;
#                Ändern im Editor über deren bearbeiten())
#   Usage        Kosten heute / Monat / Budget, davon geschätzt, je Modell
#   Capabilities was die KI kann (Werkzeuge aus dem Register, gruppiert);
#                umschalten nur, wo es einen Schalter gibt: Cloud, lokal
#   Permissions  was ohne Frage erlaubt ist, mit Zurücknehmen
#   Model        Anbieter, Modell, Denk-Tiefe, Weg — öffnet die vorhandene
#                Auswahl (/model, /provider, /effort)
# Eine Überlagerung über dem Inhalt rechts der Seitenleiste, wie Gedächtnis
# und Projekte. Zustand AI["einstellungen"] (None = zu).
#
# Tasten: ↑↓ Abschnitt, → oder Enter hinein, im Abschnitt ↑↓ wählen,
# Enter/Leertaste schalten, ← oder Esc zurück, Esc in der Leiste schließt.

import curses
import urllib.error
import urllib.parse

from . import fussleiste
from . import verlauf as V
from .basis import api_call
from . import chat as chatmod      # erst beim Aufruf gelesen: chat importiert uns
from .gedaechtnis import KERNAKTEN, inhalt_zeilen, naechster_status
from .text import md_zeilen

ABSCHNITTE = [("skills", "Skills"), ("memory", "Memory"), ("usage", "Usage"),
              ("capabilities", "Capabilities"), ("permissions", "Permissions"),
              ("model", "Model")]
AKTEN = ["hausregeln", "steckbrief", "ziele", "bereiche"]
NAV = 18                                  # Breite der Leiste links
VON = {"sasha": "you", "ki": "the ki", "anthropic": "Anthropic"}   # „Created by"

# Werkzeug-Wort (verlauf.NAMEN) → Gruppe für „Capabilities".
GRUPPEN = [("calendar", "Calendar"), ("clock", "Calendar"), ("memory", "Memory"),
           ("past chats", "Memory"), ("skill", "Skills"), ("web search", "Web"),
           ("web page", "Web"), ("news", "Web"), ("mail", "Mail"), ("files", "Files"),
           ("document", "Files"), ("code", "Code"), ("series", "Series"),
           ("choice", "Chat"), ("answer", "Chat")]
FRAGT = {"nie": "", "immer": "asks first", "manchmal": "asks if it changes something"}


# ── Reine Helfer ─────────────────────────────────────────────────────────

def gruppiert(werkzeuge):
    """Werkzeuge nach Gruppe. -> [(gruppe, [werkzeug, …])] in fester Reihenfolge."""
    zu = dict(GRUPPEN)
    reihe = []
    for _w, g in GRUPPEN:
        if g not in reihe:
            reihe.append(g)
    nach = {}
    for w in werkzeuge or []:
        g = zu.get(V.wort(w.get("name") or ""), "Other")
        nach.setdefault(g, []).append(w)
    return [(g, nach[g]) for g in reihe + ["Other"] if g in nach]


def balken(anteil, breite=20):
    """Ein kantiger Balken ▰▰▰▱▱ für 0..1 (darüber: voll)."""
    try:
        a = max(0.0, min(1.0, float(anteil)))
    except (TypeError, ValueError):
        a = 0.0
    voll = int(round(a * breite))
    return "▰" * voll + "▱" * (breite - voll)


def skill_zeilen(s, breite):
    """Ein Skill im Einzelnen. -> [(text, art)]"""
    an = s.get("status") == "aktiv"
    schalter = "[● on ]" if an else ("[ off ○]" if s.get("status") == "aus" else "[ proposed ◌]")
    zeilen = [(s.get("name") or "?", "kopf"), (schalter, "schalter"),
              ("by %s%s" % (VON.get(s.get("herkunft"), s.get("herkunft") or "?"),
                            " · created %s" % s["erstellt"] if s.get("erstellt") else ""), "leise"),
              ("", ""), ("Description", "kopf")]
    zeilen += [(t, "") for t, _st in md_zeilen(s.get("beschreibung") or "—", breite)]
    for titel, feld in (("Needs", "braucht"), ("Note", "vermerk")):
        if s.get(feld):
            zeilen += [("", ""), (titel, "kopf")]
            zeilen += [(t, "") for t, _st in md_zeilen(s[feld], breite)]
    return zeilen


def liste_hinweis(lage, breite):
    """Customize → Skills, ganz oben (2026-10-08): ist die Skill-Liste für
    die KI zu lang, sagt es das — statt still alle Beschreibungen zu kürzen.
    lage = skill_liste aus /api/gedaechtnis. -> [(text, art)]"""
    lage = lage if isinstance(lage, dict) else {}
    if not lage.get("zu_lang"):
        return []

    def zahl(n):
        return "{:,}".format(int(n or 0)).replace(",", " ")
    text = ("Liste zu lang: %s von %s Zeichen — schalte Skills aus, die du nicht brauchst"
            % (zahl(lage.get("laenge")), zahl(lage.get("grenze"))))
    zeilen = [(t, "warn") for t, _s in md_zeilen(text, breite)]
    kurz = list(lage.get("nur_name") or []) + list(lage.get("gekuerzt") or [])
    if kurz:
        zeilen += [(t, "leise") for t, _s in
                   md_zeilen("die ki sieht davon gerade nur kurz: " + ", ".join(kurz), breite)]
    return zeilen + [("", "")]


def kosten_zeilen(k, breite):
    """Usage als Zeilen."""
    b = (k or {}).get("budget") or {}
    zeilen = [("today        %s  (%d calls)" % (chatmod.fmt_euro(k.get("heute")), k.get("calls_heute") or 0), ""),
              ("this month   %s" % chatmod.fmt_euro(k.get("monat")), "")]
    if k.get("geschaetzt_monat"):
        zeilen.append(("  of which estimated  %s" % chatmod.fmt_euro(k["geschaetzt_monat"]), "leise"))
    zeilen.append(("", ""))
    if b.get("limit"):
        zeilen.append(("budget       %s / month" % chatmod.fmt_euro(b["limit"]), ""))
        zeilen.append(("%s %d %%" % (balken(b.get("anteil"), min(30, max(5, breite - 8))),
                                      int(100 * float(b.get("anteil") or 0))),
                       "warn" if b.get("status") in ("warn", "over") else "acc"))
    else:
        zeilen.append(("no monthly budget — /budget 20 sets one", "leise"))
    if k.get("modelle"):
        zeilen += [("", ""), ("By model", "kopf")]
        for m, eur in k["modelle"].items():
            zeilen.append(("%s  %s" % (chatmod.fmt_euro(eur).rjust(8), m), ""))
    return zeilen


# ── Die Überlagerung ─────────────────────────────────────────────────────

class Einstellungen:
    """Zustand AI["einstellungen"]: {abschnitt, fokus "nav"|"detail", daten,
    wahl, scroll, akte}."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        self.AI.setdefault("einstellungen", None)

    def oeffnen(self, abschnitt=None):
        AI = self.AI
        idx = next((i for i, (s, _t) in enumerate(ABSCHNITTE) if s == abschnitt), 0)
        AI["einstellungen"] = {"abschnitt": idx, "fokus": "detail" if abschnitt else "nav",
                               "daten": {}, "wahl": 0, "scroll": 0, "akte": 0}
        AI["msg"] = ""
        self.laden()

    def schliessen(self):
        self.AI["einstellungen"] = None

    def abschnitt(self):
        return ABSCHNITTE[self.AI["einstellungen"]["abschnitt"]][0]

    # ── Daten ──────────────────────────────────────────────────────────
    def _holen(self, pfad):
        try:
            d = api_call(pfad)
        except (urllib.error.URLError, OSError, ValueError):
            self.AI["msg"] = "keine verbindung zum backend"
            return None
        return d if isinstance(d, (dict, list)) else None

    def laden(self):
        E = self.AI["einstellungen"]
        ab = self.abschnitt()
        if ab in ("skills", "memory"):
            E["daten"]["gedaechtnis"] = self._holen("/api/gedaechtnis") or {}
        elif ab == "usage":
            E["daten"]["kosten"] = self._holen("/api/ai/kosten") or {}
        elif ab == "capabilities":
            E["daten"]["werkzeuge"] = (self._holen("/api/ai/werkzeuge") or {}).get("werkzeuge") or []
            E["daten"]["wege"] = self._holen("/api/ai/backends") or {}
        elif ab == "permissions":
            E["daten"]["erlaubnis"] = self._holen("/api/erlaubnis") or {}
        elif ab == "model":
            E["daten"]["stand"] = self._holen("/api/ai/einstellungen") or {}

    def _skills(self):
        return (self.AI["einstellungen"]["daten"].get("gedaechtnis") or {}).get("skills") or []

    def _erlaubt(self):
        e = self.AI["einstellungen"]["daten"].get("erlaubnis") or {}
        return ([("always", x) for x in e.get("immer") or []]
                + [("this chat", x) for x in e.get("gespraech") or []])

    def _modell_reihen(self):
        st = self.AI["einstellungen"]["daten"].get("stand") or {}
        weg = {"local": "local only", "cloud": "cloud only", "auto": "local if there, else cloud"}
        return [("provider", "%s%s" % (st.get("anbieter") or "—",
                                        " (now %s)" % st["anbieter_aktiv"]
                                        if st.get("anbieter") == "auto" and st.get("anbieter_aktiv")
                                        else ""), "anbieter"),
                ("model", st.get("modell") or "—", "modell"),
                ("effort", "%s%s" % (st.get("effort") or "—",
                                     "" if st.get("effort_wirkt") else " (claude only)"), "effort"),
                ("way", weg.get(st.get("weg"), st.get("weg") or "—"), "weg"),
                ("budget", chatmod.fmt_euro(st["budget"]) + " / month" if st.get("budget") else "none",
                 "budget")]

    def _waehlbar(self):
        """Wie viele Zeilen im Abschnitt wählbar sind."""
        ab = self.abschnitt()
        if ab == "skills":
            return len(self._skills())
        if ab == "memory":
            return len(AKTEN)
        if ab == "capabilities":
            return 2
        if ab == "permissions":
            return len(self._erlaubt())
        if ab == "model":
            return len(self._modell_reihen())
        return 0

    # ── Tasten ─────────────────────────────────────────────────────────
    def tasten(self):
        E = self.AI["einstellungen"]
        if E["fokus"] == "nav":
            return [("↑↓", "section"), ("enter", "open"), ("→", "open"), ("esc", "close")]
        ab, n = self.abschnitt(), self._waehlbar()
        mitte = [("↑↓", "select")] if n > 1 else []
        if ab == "skills" and n:
            mitte.append(("enter", "on/off"))
        elif ab == "memory":
            mitte = [("tab", "next file"), ("↑↓", "scroll")] + (
                [("e", "edit in editor")] if AKTEN[E["akte"]] in KERNAKTEN else [])
        elif ab == "capabilities":
            mitte += [("enter", "on/off"), ("pgup pgdn", "scroll")]
        elif ab == "permissions" and n:
            mitte.append(("enter", "revoke"))
        elif ab == "model":
            mitte.append(("enter", "change"))
        elif ab == "usage":
            mitte = [("r", "reload")]
        return mitte + [("←", "sections"), ("esc", "back")]

    def taste(self, ch):
        E = self.AI["einstellungen"]
        if E["fokus"] == "nav":
            if ch == 27:
                self.schliessen()
            elif ch in (curses.KEY_UP, curses.KEY_DOWN):
                E["abschnitt"] = (E["abschnitt"] + (1 if ch == curses.KEY_DOWN else -1)) % len(ABSCHNITTE)
                E["wahl"] = E["scroll"] = 0
                self.laden()
            elif ch in (10, 13, curses.KEY_ENTER, curses.KEY_RIGHT):
                E["fokus"] = "detail"
            return
        if ch in (27, curses.KEY_LEFT):
            E["fokus"] = "nav"
            return
        ab, n = self.abschnitt(), self._waehlbar()
        if ab == "memory":
            self._taste_memory(ch)
            return
        if ch in (curses.KEY_UP, curses.KEY_DOWN) and n:
            E["wahl"] = (E["wahl"] + (1 if ch == curses.KEY_DOWN else -1)) % n
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            E["scroll"] = max(0, E["scroll"] + (-8 if ch == curses.KEY_PPAGE else 8))
        elif ch == ord("r"):
            self.laden()
        elif ch in (10, 13, curses.KEY_ENTER, ord(" ")) and n:
            self.ausloesen(E["wahl"])

    def _taste_memory(self, ch):
        E = self.AI["einstellungen"]
        if ch == 9:
            E["akte"], E["scroll"] = (E["akte"] + 1) % len(AKTEN), 0
        elif ch in (curses.KEY_UP, curses.KEY_DOWN):
            E["scroll"] = max(0, E["scroll"] + (1 if ch == curses.KEY_DOWN else -1))
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            E["scroll"] = max(0, E["scroll"] + (-8 if ch == curses.KEY_PPAGE else 8))
        elif ch in (ord("e"), 10, 13, curses.KEY_ENTER) and AKTEN[E["akte"]] in KERNAKTEN:
            self.akte_bearbeiten(AKTEN[E["akte"]])

    def ausloesen(self, i):
        """Enter/Klick auf Zeile i des Abschnitts."""
        E, AI = self.AI["einstellungen"], self.AI
        E["wahl"] = i
        ab = self.abschnitt()
        if ab == "skills":
            self.skill_umschalten(i)
        elif ab == "capabilities":
            schluessel = ("cloud_enabled", "local_enabled")[i]
            an = not (E["daten"].get("wege") or {}).get(schluessel, True)
            try:
                E["daten"]["wege"] = api_call("/api/ai/backends", "POST", {schluessel: an})
            except (urllib.error.URLError, OSError, ValueError):
                AI["msg"] = "keine verbindung — nicht umgeschaltet"
                return
            AI["msg"] = "%s: %s" % (("cloud", "local")[i], "on" if an else "off")
        elif ab == "permissions":
            art, x = self._erlaubt()[i]
            try:
                api_call("/api/erlaubnis/zuruecknehmen", "POST", {"werkzeug": x.get("name")})
            except (urllib.error.URLError, OSError, ValueError):
                AI["msg"] = "keine verbindung — nicht zurückgenommen"
                return
            AI["msg"] = "zurückgenommen — die ki fragt wieder"
            self.laden()
            E["wahl"] = max(0, min(E["wahl"], self._waehlbar() - 1))
        elif ab == "model":
            self._modell(self._modell_reihen()[i][2])

    def _modell(self, was):
        AI = self.AI
        stand = self.AI["einstellungen"]["daten"].get("stand") or {}
        if was == "budget":
            AI["msg"] = "budget: /budget 20 im chat setzt es, /budget off nimmt es weg"
            return
        if was == "weg":
            folge = {"auto": "cloud", "cloud": "local", "local": "auto"}
            self.chat.setzen({"weg": folge.get(stand.get("weg"), "auto")})
            self.laden()
            return
        wahl = chatmod.auswahl(was, stand)
        if not wahl["optionen"]:
            AI["msg"] = "kein anbieter mit schlüssel — nichts zu wählen"
            return

        def nehmen(daten):
            self.chat.setzen(daten)
            if self.AI.get("einstellungen"):
                self.laden()
        wahl["aktion"] = nehmen
        AI["wahl"] = wahl

    def skill_umschalten(self, i):
        AI = self.AI
        skills = self._skills()
        if not 0 <= i < len(skills):
            return
        s = skills[i]
        neu = naechster_status(s.get("status"))
        try:
            d = api_call("/api/skills/%s/status" % urllib.parse.quote(s["name"], safe=""),
                         "POST", {"status": neu})
        except urllib.error.HTTPError as e:
            AI["msg"] = "nicht umgeschaltet (%s)" % e.code
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht umgeschaltet"
            return
        if isinstance(d, dict) and isinstance(d.get("skill"), dict):
            s.update(d["skill"])
            if isinstance(d.get("skill_liste"), dict):     # Hinweis „zu lang" frisch
                self._gedaechtnis()["skill_liste"] = d["skill_liste"]
        else:
            s["status"] = neu
        AI["msg"] = "skill „%s“ is now %s" % (s["name"], "on" if neu == "aktiv" else "off")

    def akte_bearbeiten(self, akte):
        """Kernakte im Editor — über die Gedächtnis-Ansicht (dieselbe
        Zwischendatei-und-stand-Logik), danach neu laden."""
        AI, ged = self.AI, self.chat.gedaechtnis
        alt = AI.get("gedaechtnis")
        AI["gedaechtnis"] = {"abschnitt": 0, "daten": self._gedaechtnis(), "scroll": 0, "wahl": 0}
        try:
            ged.bearbeiten(akte)
        finally:
            AI["gedaechtnis"] = alt
        self.laden()

    def _gedaechtnis(self):
        return self.AI["einstellungen"]["daten"].get("gedaechtnis") or {}

    # ── Zeichnen ───────────────────────────────────────────────────────
    def zeichnen(self, by, bx, bh, bw):
        chat, E = self.chat, self.AI["einstellungen"]
        C, addclip = chat.z.C, chat.z.addclip
        top, x0, h, w = by + 1, bx + 1, max(1, bh - 2), max(4, bw - 2)
        fuss = [fussleiste.text(self.chat.tasten())]   # dasselbe wie die Leiste unten
        if self.AI.get("msg"):
            fuss = [self.AI["msg"]] + fuss
        fuss_zeilen = [f[i:i + w - 2] for f in fuss for i in range(0, max(1, len(f)), max(1, w - 2))]
        unten = top + h - len(fuss_zeilen)
        for i, f in enumerate(fuss_zeilen):
            addclip(unten + i, x0 + 1, f, w - 2,
                    C["warn"] if (self.AI.get("msg") and i == 0) else C["faint"])
        schmal = w < NAV + 30
        if schmal:                       # nur der gewählte Abschnitt mit Pfeilen
            titel = "‹ %s ›  %d/%d" % (ABSCHNITTE[E["abschnitt"]][1], E["abschnitt"] + 1,
                                       len(ABSCHNITTE))
            addclip(top, x0 + 1, titel, w - 2,
                    (C["bright"] | curses.A_REVERSE) if E["fokus"] == "nav" else C["acc"])
            dx, dw, dtop = x0 + 1, w - 2, top + 2
        else:
            addclip(top, x0 + 1, "Settings", NAV - 2, C["faint"])
            for i, (_s, text) in enumerate(ABSCHNITTE):
                y = top + 1 + i
                gew = i == E["abschnitt"]
                attr = ((C["bright"] | curses.A_REVERSE) if (gew and E["fokus"] == "nav")
                        else (C["bright"] | curses.A_BOLD) if gew else C["dim"])
                addclip(y, x0 + 1, (" " + text).ljust(NAV - 3), NAV - 3, attr)
                chat.klickbar(y, x0, NAV - 1, lambda i=i: self.abschnitt_klick(i))
            for y in range(top, unten - 1):
                chat.z.safe_addstr(y, x0 + NAV - 1, "│", C["faint"])
            dx, dw, dtop = x0 + NAV + 1, w - NAV - 2, top
        self._detail(dtop, dx, max(1, unten - 1 - dtop), dw)

    def abschnitt_klick(self, i):
        E = self.AI["einstellungen"]
        if E["abschnitt"] != i:
            E["abschnitt"], E["wahl"], E["scroll"] = i, 0, 0
            self.laden()
        E["fokus"] = "detail"

    def _detail(self, top, x, h, w):
        chat, E = self.chat, self.AI["einstellungen"]
        C, addclip = chat.z.C, chat.z.addclip
        ab = self.abschnitt()
        fokus = E["fokus"] == "detail"
        stile = {"": C["bright"], "kopf": C["acc"] | curses.A_BOLD, "leise": C["faint"],
                 "liste": C["bright"], "code": C["dim"], "warn": C["warn"], "acc": C["acc"],
                 "schalter": C["acc"] | curses.A_BOLD, "aus": C["faint"], "gewaehlt": C["bright"]}
        zeilen, klicks = self._inhalt(ab, w)
        # Auswahl (/model …) unten im Abschnitt
        wahl = self.AI.get("wahl")
        wz = chat._fuss_wahl(wahl, w, h) if wahl else []
        platz = max(1, h - len(wz))
        ziel = next((r for r, k in enumerate(klicks) if k == E["wahl"]), 0)
        if fokus and ab != "memory":
            if ziel < E["scroll"]:
                E["scroll"] = ziel
            elif ziel >= E["scroll"] + platz:
                E["scroll"] = ziel - platz + 1
        E["scroll"] = max(0, min(E["scroll"], max(0, len(zeilen) - platz)))
        for r in range(min(platz, len(zeilen) - E["scroll"])):
            text, art = zeilen[E["scroll"] + r]
            k = klicks[E["scroll"] + r]
            attr = stile.get(art, C["dim"])
            if k is not None and k == E["wahl"] and fokus:
                attr = C["bright"] | curses.A_REVERSE
            addclip(top + r, x, text, w, attr)
            if k is not None:
                chat.klickbar(top + r, x, w, lambda k=k: self._klick(k))
        for i, (text, attr) in enumerate(wz):
            addclip(top + platz + i, x, text, w, attr)

    def _klick(self, k):
        E = self.AI["einstellungen"]
        E["fokus"] = "detail"
        if self.abschnitt() == "memory":
            E["akte"], E["scroll"] = (E["akte"] + 1) % len(AKTEN), 0
            return
        self.ausloesen(k)

    def _inhalt(self, ab, w):
        """Zeilen des Abschnitts + je Zeile, welche wählbare Nummer sie trägt
        (oder None). -> ([(text, art)], [nummer|None])"""
        E = self.AI["einstellungen"]
        zeilen, klicks = [], []

        def dazu(text, art="", k=None):
            zeilen.append((text, art))
            klicks.append(k)

        if ab == "skills":
            skills = self._skills()
            for text, art in liste_hinweis(self._gedaechtnis().get("skill_liste"), w):
                dazu(text, art)
            if not skills:
                dazu("no skills yet", "leise")
            for i, s in enumerate(skills):
                an = s.get("status") == "aktiv"
                punkt = "●" if an else ("◌" if s.get("status") == "vorgeschlagen" else "○")
                dazu("%s %s" % (punkt, s.get("name") or "?"), "" if an else "aus", i)
            if skills:
                s = skills[max(0, min(E["wahl"], len(skills) - 1))]
                dazu("")
                dazu("─" * min(w, 40), "leise")
                for text, art in skill_zeilen(s, w):
                    dazu(text, art, E["wahl"] if art == "schalter" else None)
        elif ab == "memory":
            reiter = "  ".join(("[%s]" if i == E["akte"] else " %s ") % a for i, a in enumerate(AKTEN))
            dazu(reiter[:w], "acc", -1)          # Klick: nächste Akte
            dazu("")
            inhalt, _z = inhalt_zeilen(self._gedaechtnis(), AKTEN[E["akte"]], w)
            for text, art in inhalt:
                dazu(text, art)
        elif ab == "usage":
            for text, art in kosten_zeilen(E["daten"].get("kosten") or {}, w):
                dazu(text, art)
        elif ab == "capabilities":
            wege = E["daten"].get("wege") or {}
            dazu("Ways", "kopf")
            for i, (wort, sch) in enumerate((("cloud", "cloud_enabled"), ("local", "local_enabled"))):
                an = wege.get(sch, True)
                dazu("%s %s" % ("[● on ]" if an else "[ off ○]", wort), "schalter" if an else "aus", i)
            for gruppe, liste in gruppiert(E["daten"].get("werkzeuge")):
                dazu("")
                dazu(gruppe, "kopf")
                for wz in liste:
                    fr = FRAGT.get(wz.get("fragt"), "")
                    titel = wz.get("alltag") or wz.get("name")
                    dazu("  %s%s" % (titel, " · " + fr if fr else ""), "")
                    for t, _s in md_zeilen(wz.get("beschreibung") or "", max(6, w - 4))[:2]:
                        dazu("    " + t, "leise")
        elif ab == "permissions":
            erl = self._erlaubt()
            if not erl:
                dazu("nothing is allowed without asking — the ki asks before it changes something",
                     "leise")
            for i, (art, x) in enumerate(erl):
                dazu("%-10s %s" % (art, x.get("was") or x.get("name")), "", i)
            if erl:
                dazu("")
                dazu("enter takes it back — the ki asks again", "leise")
        elif ab == "model":
            for i, (name, wert, _was) in enumerate(self._modell_reihen()):
                dazu("%-9s %s" % (name, wert), "", i)
        return zeilen, klicks
