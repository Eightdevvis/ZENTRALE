# tui/ansichten/kalender_bedienung.py
#
# Die Tasten der Kalender-Ansichten A/B/C — wie calcurse. Hält die EINE
# Auswahl (Tag, Termin, Kasten), führt die Dialoge aus kalender_werkzeuge.py,
# schickt ihre Aufrufe ans Backend und zeichnet Kästen und Ansehen-Fenster.
# Die Ansicht selbst zeichnet nur. Die Tasten stehen in Tastentabellen
# (TASTEN_A/B/C unten, tasten.py); kalender.py verteilt aus ihnen.
#
# Eigene Datei, weil kalender.py sonst über die Riesen-Grenze wüchse
# (memory/system/tui_bauplan.md); der alte Kalender fliegt in Etappe 2 raus.

import curses
import json
import textwrap
import time
import urllib.error
import urllib.parse
from datetime import date, timedelta

from .basis import BEENDEN, api_call
from . import kalender_advanced, kalender_gruppen, kalender_motive, kalender_phasen
from . import kalender_quellen as kq
from . import kalender_kasten, kalender_stil
from . import kalender_werkzeuge as kw
from .tasten import Tasten

FENSTER_TAGE = 3            # so viele Tage zeigt A (kalender_ansichten.ansicht_a)
FOKUS = ("termine", "kalender", "todo")


# ── Tastentabellen der Ansichten (tasten.py, 2026-10-11) ───────────────
# EINE Belegung für Verteilen und Leiste. Andere Belegung → nur hier.
# R = Rhythmus (10.10.2026): groß, damit es r (wiederholen) nicht
# überschreibt; in A, B und C gleich. Neuer Termin für eine Liste/ein
# Projekt: seit 11.10.2026 keine eigene Taste mehr (vorher Shift+A, d75f21a;
# Sasha: „den kannst dann rausnehmen") — a → Formular → Advanced → Typ liste,
# A ist wieder ein zweites a. Abhaken des angezeigten Punkts: „!" wie im
# TODO-Kasten (dort calcurses „erledigt").
_SPRUENGE = [("t/w/m/y", "springen", "day/week/month/year (caps: back)"),
             ("T/W/M/Y", "springen"), ("ctrl+g", "springen")]


def _rest(esc="close", kasten=False, spruenge=True):
    """Was jede Ansicht hat: springen, gehe zu, erledigte, Rhythmus, (Tab),
    v, Esc, q. Ohne Text = geht, steht aber nicht in der Leiste."""
    t = list(_SPRUENGE) if spruenge else [(k, a) for k, a, *_x in _SPRUENGE]
    t += [("g", "gehe_zu", "go to"), ("x", "erledigte", "show done"), ("X", "erledigte"),
          ("R", "rhythmus", "rhythm")]
    if kasten:
        t += [("tab", "kasten", "box"), ("shift+tab", "kasten")]
    return t + [("v", "ansicht", "view"), ("V", "ansicht"), ("esc", "schliessen", esc),
                ("q/Q", "beenden")]


def _termine(leer, **rest):
    """Die Termine eines Tages (A „termine", C). leer = am Tag steht keiner:
    e/d/r/c/u/! sagen dann nur „kein termin gewählt", Enter tut nichts."""
    def zeigen(text):
        return None if leer else text
    t = [("↑↓", "eintrag", "entry"), ("k/j", "eintrag"), ("←→", "tag", "day"),
         ("h/l", "tag"), ("a", "neu", "new"), ("A/ctrl+a", "neu"),
         ("e", "aendern", zeigen("edit")), ("E", "aendern"),
         ("d", "loeschen", zeigen("delete")), ("D", "loeschen"),
         ("r", "wiederholen", zeigen("repeat")), ("!", "abhaken", zeigen("tick off"))]
    if not leer:
        t.append(("enter", "ansehen", "view"))
    t += [("u", "ebene", zeigen("(un)commit")), ("U", "ebene"),
          ("c", "kopieren", zeigen("copy")), ("p", "einfuegen", "paste"),
          ("ctrl+v", "einfuegen")]
    return t + _rest(**rest)


def _kalender(**rest):
    """A, Kasten „kalender" (calcurse): Pfeile wählen den Tag."""
    return [("←→", "kal_tag", "day"), ("↑↓", "kal_tag", "week"), ("h/j/k/l", "kal_tag"),
            ("0/$", "kal_tag", "week start/end"), ("a", "neu", "new"),
            ("A/ctrl+a", "neu"), ("enter", "zu_terminen", "to entries")] + _rest(**rest)


def _todo(art, **rest):
    """A, Kasten „todo" (die Wochenliste). art: „voll", „leer" (Liste ohne
    Aufgaben) oder „ohne" (keine Wochenliste: alles sagt nur das)."""
    if art == "ohne":
        t = [("a/A/ctrl+t/e/E/d/D/!/+/-", "keine_liste")]
    else:
        t = [("a", "todo_neu", "new"), ("A/ctrl+t", "todo_neu")]
        if art == "leer":
            t += [("e/E/d/D/!/+/-", "keine_aufgabe")]
        else:
            t = [("↑↓", "todo_waehlen", "select"), ("k/j", "todo_waehlen")] + t + [
                ("e", "todo_aendern", "edit"), ("E", "todo_aendern"),
                ("d", "todo_loeschen", "delete"), ("D", "todo_loeschen"),
                ("!", "todo_haken", "done"), ("+/-", "todo_schieben", "up/down"),
                ("enter", "todo_ansehen", "view")]
    return t + _rest(spruenge=False, **rest)


def _a_tabelle():
    tab = {}
    for zusatz, esc in (("", "close"), ("_vom_monat", "back to month")):
        tab["termine" + zusatz] = _termine(False, esc=esc, kasten=True)
        tab["termine_leer" + zusatz] = _termine(True, esc=esc, kasten=True)
        tab["kalender" + zusatz] = _kalender(esc=esc, kasten=True)
        for art, name in (("voll", "todo"), ("leer", "todo_leer"), ("ohne", "todo_ohne")):
            tab[name + zusatz] = _todo(art, esc=esc, kasten=True)
    return tab


def _monat(d: date, delta: int) -> date:
    m = d.month - 1 + delta
    j, m = d.year + m // 12, m % 12 + 1
    for t in (d.day, 30, 29, 28):
        try:
            return date(j, m, t)
        except ValueError:
            continue


def rueckfrage_zeilen(text: str, breite: int) -> list[str]:
    """Text einer Rückfrage in Zeilen von höchstens `breite` Zeichen —
    an Wortgrenzen, überlange Wörter werden geteilt, nichts fällt weg."""
    breite = max(1, breite)
    aus = []
    for absatz in (text or "").split("\n"):
        aus += textwrap.wrap(absatz, breite, drop_whitespace=True,
                             break_long_words=True, break_on_hyphens=False) or [""]
    return aus or [""]


class Bedienung:
    TASTEN_A = Tasten(_a_tabelle())
    TASTEN_B = Tasten({"monat": [
        ("←→", "monat_tag", "day"), ("↑↓", "monat_tag", "week"), ("h/j/k/l", "monat_tag"),
        ("enter", "tag_oeffnen", "edit day"),
        # bearbeiten geht in der Tagesliste — hier nur eine Meldung
        ("a/A/ctrl+a/e/E/d/D/r/c/p/ctrl+v/u/U/tab/shift+tab", "nur_ansehen"),
    ] + _rest()})
    TASTEN_C = Tasten({"woche": _termine(False), "woche_leer": _termine(True)})

    def __init__(self, kal):
        self.kal, self.z, self.K = kal, kal.z, kal.K
        self.W = self.K.setdefault("w", {
            "fokus": "termine", "tag": None, "idx": 0, "tidx": 0,
            "dialog": None, "popup": None, "clip": None, "msg": ""})

    # ── Daten ──────────────────────────────────────────────────────────
    def daten(self) -> dict:
        """Die Daten der Ansicht; für A auch über den Monatsrand hinaus,
        damit das 3-Tage-Fenster nie halb leer ist."""
        K = self.K
        ref = date.fromisoformat(K["ref"])
        schluessel = (K["stil"], K["ref"])
        d = K.get("sdata")
        if d and d.get("_for") == schluessel:
            # Ein Fehlschlag bleibt nicht kleben: nach ein paar Sekunden neu
            # versuchen (07.10.2026: nach dem Speichern blieb „kalender:
            # backend?" stehen, bis man blätterte).
            if not d.get("failed") or time.monotonic() - d.get("_um", 0) < 3:
                return d
        d = self._holen("month", ref)
        if not d.get("failed") and K["stil"] == "A":
            rand = ref + timedelta(days=FENSTER_TAGE - 1)
            try:
                if rand > date.fromisoformat(d.get("end", "")):
                    d2 = self._holen("month", rand)
                    if not d2.get("failed"):
                        d["days"] = {**d2.get("days", {}), **d.get("days", {})}
                        d["cycle"] = {**(d2.get("cycle") or {}), **(d.get("cycle") or {})}
                        d["end"] = d2.get("end", d["end"])
            except ValueError:
                pass
        if not d.get("failed") and K["stil"] == "C":
            self._vortag_phasen(d, ref)
        if not d.get("failed"):
            self._katalog_laden()
        d["_for"] = schluessel
        d["_um"] = time.monotonic()
        K["sdata"] = d
        return d

    def _vortag_phasen(self, d, ref):
        """C: eine Phase über Mitternacht (Schlaf 23–07) steht nur am Tag
        ihres Beginns. Fehlt der Sonntag vor der Woche in den Daten, seine
        Phasen nachholen — sonst begänne der Montag ohne den Rest der Nacht."""
        vortag = ref - timedelta(days=ref.weekday() + 1)
        tage = d.setdefault("days", {})
        if not isinstance(tage, dict) or vortag.isoformat() in tage:
            return
        d2 = self._holen("month", vortag)
        if d2.get("failed"):
            return
        nacht = [e for e in (d2.get("days") or {}).get(vortag.isoformat()) or []
                 if kalender_motive.ist_phase(e)]
        if nacht:
            tage[vortag.isoformat()] = nacht

    def _katalog_laden(self):
        """Die Namen der Gruppen einmal je Sitzung vom Backend (Rückfall:
        kalender_gruppen.NAMEN)."""
        if getattr(self, "_katalog", False):
            return
        self._katalog = True
        try:
            r = api_call("/api/calendar/kategorien", timeout=4.0)
            kalender_gruppen.namen_setzen((r or {}).get("kategorien"))
        except Exception:
            pass

    def _holen(self, view, ref):
        try:
            r = api_call("/api/calendar?view=%s&ref=%s" % (view, ref.isoformat()), timeout=8.0)
            return r if isinstance(r, dict) else {"failed": True}
        except Exception:
            return {"failed": True}

    def neu_laden(self):
        self.K["sdata"] = None
        self.K["data"] = None

    # ── Auswahl ────────────────────────────────────────────────────────
    def tag(self) -> date:
        W, K = self.W, self.K
        if W["tag"] is None:
            W["tag"] = date.fromisoformat(K["ref"])
        return W["tag"]

    def setze_tag(self, d: date, idx: int = 0):
        """Tag wählen; die Ansicht rückt mit, wenn er herausfällt: A das
        3-Tage-Fenster, B der Monat, C die Woche."""
        W, K = self.W, self.K
        W["tag"], W["idx"] = d, idx
        ref = date.fromisoformat(K["ref"])
        stil = K.get("stil") or "A"
        if stil == "B":
            if (d.year, d.month) != (ref.year, ref.month):
                K["ref"] = d.isoformat()
        elif stil == "C":
            if d - timedelta(days=d.weekday()) != ref - timedelta(days=ref.weekday()):
                K["ref"] = d.isoformat()
        elif d < ref:
            K["ref"] = d.isoformat()
        elif d > ref + timedelta(days=FENSTER_TAGE - 1):
            K["ref"] = (d - timedelta(days=FENSTER_TAGE - 1)).isoformat()

    def termine(self, d: date | None = None) -> list:
        """Die Liste, aus der gewählt wird — in B mit Gruppen als einer Zeile."""
        return kw.eintraege(self.daten(), d or self.tag(), self.K["showhidden"],
                            monat=self.K.get("stil") == "B")

    def gewaehlt(self) -> dict | None:
        ts = self.termine()
        if not ts:
            return None
        self.W["idx"] = max(0, min(self.W["idx"], len(ts) - 1))
        return ts[self.W["idx"]]["roh"]

    def auswahl(self) -> dict:
        """Was die Ansicht hervorheben soll."""
        W = self.W
        lid, items = kw.todo_punkte(self.daten())
        W["tidx"] = max(0, min(W["tidx"], len(items) - 1)) if items else 0
        if self.termine():
            self.gewaehlt()
        fokus = W["fokus"] if self.K.get("stil") in (None, "A") else "termine"
        monat = self.K.get("stil") == "B"          # im Monat wird kein Termin gewählt
        return {"fokus": fokus, "tag": self.tag().isoformat(),
                "idx": W["idx"], "tidx": W["tidx"],
                "roh": self.gewaehlt() if fokus == "termine" and not monat else None}

    # ── Tasten: die Tabellen der drei Ansichten (tasten.py, 2026-10-11) ──
    # Der Kalender (kalender.py) setzt sie mit den Tabellen der Kästen zu
    # EINER zusammen; aus ihr verteilt er die Tasten, und die Leiste ganz
    # unten zeigt sie. Ansichten: a:termine / a:kalender / a:todo (die drei
    # Kästen von A, je mit „_leer" bzw. „_ohne", wenn dort nichts zu wählen
    # ist, und „_vom_monat", wenn der Tag aus dem Monat geliehen ist — dann
    # führt Esc zurück), b:monat, c:woche (+ „_leer").
    def ansicht(self) -> str:
        K, W = self.K, self.W
        stil = K.get("stil") or "A"
        if stil == "B":
            return "b:monat"
        if stil == "C":
            return "c:woche" if self.gewaehlt() else "c:woche_leer"
        if W["fokus"] == "todo":
            lid, items = kw.todo_punkte(self.daten())
            name = "todo_ohne" if lid is None else ("todo" if items else "todo_leer")
        elif W["fokus"] == "kalender":
            name = "kalender"
        else:
            name = "termine" if self.gewaehlt() else "termine_leer"
        return "a:" + name + ("_vom_monat" if K.get("sprung") else "")

    # ── Bewegen und Springen (in jeder Ansicht) ────────────────────────
    def aktion_springen(self, taste):
        """calcurse: t/T Tag, w/W Woche, m/M Monat, y/Y Jahr, Strg-G heute."""
        d = self.tag()
        self.setze_tag({"t": d + timedelta(days=1), "T": d - timedelta(days=1),
                        "w": d + timedelta(days=7), "W": d - timedelta(days=7),
                        "m": _monat(d, 1), "M": _monat(d, -1),
                        "y": _monat(d, 12), "Y": _monat(d, -12),
                        "ctrl+g": date.today()}[taste])

    def aktion_gehe_zu(self, _t):
        self._starte(kw.dialog_gehe_zu(date.today()))

    def aktion_erledigte(self, _t):
        self.K["showhidden"] = not self.K["showhidden"]
        self.W["msg"] = "erledigte: " + ("an" if self.K["showhidden"] else "aus")

    def aktion_rhythmus(self, _t):
        """R: der Kasten mit allen Phasen (kalender_phasen.PhasenListe)."""
        kasten = self._rhythmus_kasten()
        if kasten is not None:
            self._starte(kasten)

    def aktion_ansicht(self, _t):            # v: A → B → C
        self.kal.k_stil_weiter()

    def aktion_kasten(self, taste):          # A: Tab wechselt den Kasten
        W = self.W
        W["fokus"] = FOKUS[(FOKUS.index(W["fokus"]) + (-1 if taste == "shift+tab" else 1))
                           % len(FOKUS)]

    def aktion_schliessen(self, _t):
        if self.K.get("sprung"):             # Tag aus dem Monat geöffnet → zurück in den Monat
            self.kal.sprung_zurueck()
        else:
            self.K["active"] = False

    def aktion_beenden(self, _t):
        return BEENDEN

    # ── Termine (A, Kasten „termine", und C) ───────────────────────────
    def aktion_eintrag(self, taste):
        """↑↓ über den Tagesrand hinaus: der Tag davor/danach."""
        W, d = self.W, self.tag()
        if taste in ("up", "k"):
            if W["idx"] > 0:
                W["idx"] -= 1
            else:
                vor = d - timedelta(days=1)
                self.setze_tag(vor, max(0, len(self.termine(vor)) - 1))
        elif W["idx"] < len(self.termine()) - 1:
            W["idx"] += 1
        else:
            self.setze_tag(d + timedelta(days=1))

    def aktion_tag(self, taste):
        self.setze_tag(self.tag() + timedelta(days=-1 if taste in ("left", "h") else 1))

    def aktion_neu(self, _t):                # a, A, Strg-A wie calcurse
        self._starte(kw.formular_neu(self.tag(), date.today(), quellen=self._quellen_holen))

    def _termin(self):
        """Der gewählte Termin, sonst None und eine Meldung."""
        roh = self.gewaehlt()
        if not roh:
            self.W["msg"] = "kein termin gewählt"
        return roh

    def aktion_ansehen(self, _t):
        roh = self.gewaehlt()
        if roh:
            self.W["popup"] = kw.details(roh, self.tag(), self._quelle_vorschau(roh))

    def aktion_aendern(self, _t):
        roh = self._termin()
        if roh:
            self._starte(kw.formular_bearbeiten(roh, self.tag(), date.today(),
                                                quellen=self._quellen_holen))

    def aktion_loeschen(self, _t):
        roh = self._termin()
        if roh:
            self._starte(kw.dialog_loeschen(roh, self.tag()))

    def aktion_wiederholen(self, _t):
        roh = self._termin()
        if not roh:
            return
        dl = kw.formular_wiederholen(roh, self.tag(), date.today(), self._quellen_holen)
        if dl is None:
            self.W["msg"] = "eine spanne wiederholt sich nicht"
        else:
            self._starte(dl)

    def aktion_kopieren(self, _t):
        roh = self._termin()
        if roh:
            self.W["clip"] = kw.kopie(roh)
            self.W["msg"] = "kopiert: %s" % roh.get("label", "")

    def aktion_einfuegen(self, _t):          # p / Strg-V
        if self.W["clip"]:
            self._ausfuehren(kw.plan_einfuegen(self.W["clip"], self.tag()))
        else:
            self.W["msg"] = "nichts kopiert"

    def aktion_ebene(self, _t):              # committed ↔ uncommitted
        roh = self._termin()
        plan = kw.plan_ebene(roh) if roh else None
        if plan is not None:
            self._ausfuehren(plan, pruefen=False)
        elif roh:
            self.W["msg"] = "kein termin gewählt"

    def aktion_abhaken(self, _t):
        roh = self.gewaehlt()
        if roh and kq.quelle_von(roh):
            self._quelle_abhaken(roh)
        else:
            self.W["msg"] = "abhaken geht bei Listen-Terminen (advanced → typ liste)"

    # ── Monat (B): nur ansehen ─────────────────────────────────────────
    # Sasha, 10.10.2026: „besser wenn man auf einem datum im monat enter
    # macht, dass man auf die tagansicht kommt und dort richtig bearbeiten
    # kann, und in monat dann keine".
    def aktion_monat_tag(self, taste):
        """←→ Tag, ↑↓ Woche — wie calcurses Kalenderkasten."""
        schritt = {"left": -1, "h": -1, "right": 1, "l": 1,
                   "up": -7, "k": -7, "down": 7, "j": 7}[taste]
        self.setze_tag(self.tag() + timedelta(days=schritt))

    def aktion_tag_oeffnen(self, _t):
        self.kal.sprung_zum_tag(self.tag())

    def aktion_nur_ansehen(self, _t):
        self.W["msg"] = "im monat nur ansehen — bearbeiten in der tagesliste"

    # ── Kalenderkasten (A) ─────────────────────────────────────────────
    def aktion_kal_tag(self, taste):
        """Pfeile wählen den Tag, 0/$ Wochenanfang/-ende."""
        d = self.tag()
        schritt = {"left": -1, "h": -1, "right": 1, "l": 1, "up": -7, "k": -7,
                   "down": 7, "j": 7, "0": -d.weekday(), "$": 6 - d.weekday()}[taste]
        self.setze_tag(d + timedelta(days=schritt))

    def aktion_zu_terminen(self, _t):
        self.W["fokus"] = "termine"

    # ── TODO-Kasten (A) ────────────────────────────────────────────────
    def _aufgabe(self):
        """(liste, gewählte Aufgabe)."""
        W = self.W
        lid, items = kw.todo_punkte(self.daten())
        it = items[W["tidx"]] if items and 0 <= W["tidx"] < len(items) else None
        return lid, it, items

    def aktion_todo_waehlen(self, taste):
        W = self.W
        _lid, _it, items = self._aufgabe()
        if taste in ("up", "k"):
            W["tidx"] = max(0, W["tidx"] - 1)
        else:
            W["tidx"] = min(max(0, len(items) - 1), W["tidx"] + 1)

    def aktion_todo_neu(self, _t):           # a, A, Strg-T wie calcurse
        self._starte(kw.dialog_todo_neu(self._aufgabe()[0]))

    def aktion_todo_aendern(self, _t):
        lid, it, _items = self._aufgabe()
        self._starte(kw.dialog_todo_bearbeiten(lid, it))

    def aktion_todo_loeschen(self, _t):
        lid, it, _items = self._aufgabe()
        self._starte(kw.dialog_todo_loeschen(lid, it))

    def aktion_todo_haken(self, _t):         # calcurse: erledigt an/aus
        lid, it, _items = self._aufgabe()
        self._ausfuehren(kw._plan([("POST", "/api/lists/%s/items/%s/toggle" % (lid, it["id"]),
                                    {})]))

    def aktion_todo_schieben(self, taste):   # Reihenfolge = Priorität
        lid, it, items = self._aufgabe()
        delta = -1 if taste == "+" else 1
        self._ausfuehren(kw._plan([("POST", "/api/lists/%s/items/%s/reorder"
                                    % (lid, it["id"]), {"delta": delta})]))
        self.W["tidx"] = max(0, min(len(items) - 1, self.W["tidx"] + delta))

    def aktion_todo_ansehen(self, _t):
        _lid, it, _items = self._aufgabe()
        self.W["popup"] = ["Aufgabe", "", str(it.get("text", "")),
                           "", "erledigt" if it.get("done") else "offen"]

    def aktion_keine_aufgabe(self, _t):
        self.W["msg"] = "keine aufgabe gewählt"

    def aktion_keine_liste(self, _t):
        self.W["msg"] = "keine wochenliste gefunden"

    # ── Termine mit Titel aus Liste/Projekt (kalender_quellen.py) ─────
    def _quellen_holen(self):
        """Für Advanced → Typ liste: GET /api/calendar/quellen (None = Fehler;
        das Fenster sagt es selbst)."""
        try:
            return api_call("/api/calendar/quellen", timeout=8.0) or {}
        except Exception:
            return None

    def _quelle_vorschau(self, roh):
        q = kq.quelle_von(roh)
        if q is None:
            return None
        try:
            return api_call("/api/calendar/quelle?art=%s&id=%s&n=4"
                            % (q["art"], urllib.parse.quote(q["id"], safe="")), timeout=4.0)
        except Exception:
            return None

    def _quelle_abhaken(self, roh):
        """!: den angezeigten Punkt abhaken; der nächste rückt nach."""
        plan = kq.plan_abhaken(roh)
        if plan is None:
            self.W["msg"] = "„%s“: nichts offen zum abhaken" % (roh.get("quelle_name")
                                                               or roh.get("label") or "")
            return
        vorher = roh.get("titel_live") or "?"
        self.W["msg"] = ""
        self._ausfuehren(plan, pruefen=False)
        if self.W["msg"].startswith("⚠"):
            return
        self.W["msg"] = kq.meldung_abgehakt(vorher, kq.finde(self.daten(), roh.get("kennung")))

    # ── Rhythmus (Tagesphasen) ─────────────────────────────────────────
    def _rhythmus_kasten(self):
        try:
            phasen = (api_call("/api/calendar/phasen", timeout=8.0) or {}).get("phasen")
        except Exception as e:
            self.W["msg"] = "⚠ rhythmus: backend? " + str(e)[:50]
            return None
        try:
            motive = (api_call("/api/calendar/motive", timeout=4.0) or {}).get("motive")
        except Exception:
            motive = None
        return kalender_phasen.PhasenListe(phasen or [], motive, self.tag(), date.today(),
                                           zurueck=self._rhythmus_kasten)

    # ── Dialoge und Aufrufe ────────────────────────────────────────────
    def _starte(self, dialog):
        self.W["dialog"] = dialog
        self.W["nach_konflikt"] = None

    def kette(self) -> list:
        """Die offenen Kästen von außen nach innen: Dialog/Formular →
        advanced → „welche Liste?" bzw. Stylebox (mit ihrem Farbwähler).
        Der innerste bekommt die Tasten; seine Tabelle zeigt die Leiste."""
        raus, o = [], self.W["dialog"]
        while o is not None:
            raus.append(o)
            unter = getattr(o, "box", None) if isinstance(o, kw.Formular) else None
            if isinstance(o, kalender_advanced.Advanced) and o.unter is not None:
                unter = o.unter
                if not isinstance(unter, kq.QuellenWahl):            # die Stylebox
                    raus.append(unter)
                    unter = None
            o = unter
        return raus

    def dialog_taste(self, ch):
        """Eine Taste an den offenen Kasten (er verteilt sie aus seiner
        Tabelle) und was sein Ergebnis heißt: abbrechen, ausführen …"""
        W = self.W
        dl = W["dialog"]
        r = dl.taste(ch)
        if r == "abbruch":
            W["dialog"] = None
            zurueck = getattr(dl, "bei_abbruch", None)
            if zurueck is not None:            # aus dem Rhythmus-Kasten: dorthin
                self._starte(zurueck())
                return
            W["msg"] = "" if getattr(dl, "liste", False) else "abgebrochen"
            return
        if r != "fertig":
            return
        W["dialog"] = None
        if W.get("nach_konflikt") is not None:     # Antwort auf „trotzdem?"
            plan, W["nach_konflikt"] = W["nach_konflikt"], None
            if dl.antworten.get("ok"):
                self._ausfuehren(plan, pruefen=False)
            else:
                W["msg"] = "nicht gespeichert"
            return
        self._ausfuehren(dl.plan())

    def _ausfuehren(self, plan, pruefen=True):
        W = self.W
        if pruefen and plan.get("konflikt"):
            try:
                k = (api_call("/api/calendar/konflikte", method="POST",
                              body=plan["konflikt"], timeout=8.0) or {}).get("konflikte") or []
            except Exception:
                k = []
            if k:
                zeile = k[0].lstrip("⚠ ").strip()
                W["dialog"] = kw.Dialog("kollision", [kw.Schritt(
                    "ok", "⚠ %s%s · trotzdem speichern?"
                    % (zeile, " (+%d)" % (len(k) - 1) if len(k) > 1 else ""),
                    art="wahl", wahl={"j": True, "n": False})], lambda a: kw._plan())
                W["nach_konflikt"] = plan
                return
        if plan.get("weiter") is not None:     # „nur dieser Tag?" → der Kasten
            self._starte(plan["weiter"])
            return
        if plan.get("vorab"):                  # erst fragen (Probe), dann entscheiden
            ok, antwort = self._rufen(*plan["vorab"]["aufruf"])
            if ok:
                folge = plan["vorab"]["dann"](antwort)
                if isinstance(folge, dict):
                    self._ausfuehren(folge, pruefen=False)
                else:
                    self._starte(folge)
            return
        for methode, pfad, body in plan.get("aufrufe", []):
            ok, _antwort = self._rufen(methode, pfad, body)
            if not ok:
                self.neu_laden()
                if plan.get("zurueck"):        # Rhythmus-Kasten: Fehler dort zeigen
                    msg = W["msg"]
                    kasten = plan["zurueck"]()
                    if kasten is not None:
                        kasten.fehler = msg
                        self._starte(kasten)
                return
        if plan.get("aufrufe"):
            self.neu_laden()
        if plan.get("meldung"):
            W["msg"] = plan["meldung"]
        if plan.get("danach", {}).get("tag"):
            self.setze_tag(plan["danach"]["tag"])
        if plan.get("zurueck"):
            kasten = plan["zurueck"]()
            if kasten is not None:
                self._starte(kasten)

    def _rufen(self, methode, pfad, body):
        """Ein Aufruf; ein Fehler landet lesbar in der Meldung. → (ok, antwort)"""
        try:
            return True, api_call(pfad, method=methode, body=body, timeout=15.0)
        except urllib.error.HTTPError as e:
            try:
                grund = json.loads(e.read().decode("utf-8")).get("error") or str(e)
            except Exception:
                grund = str(e)
            self.W["msg"] = "⚠ " + grund
        except Exception as e:
            self.W["msg"] = "⚠ backend? " + str(e)[:60]
        return False, None

    # ── Zeichnen: Kasten (Formular/Rückfrage) und Ansehen-Fenster ─────
    def zeile_unten(self):
        """(text, rolle) für die unterste Zeile: nur noch Meldungen — Fragen
        stehen im Kasten (Sasha, 07.10.2026: „ich will das modal")."""
        W = self.W
        if W["msg"] and (W["dialog"] is None or getattr(W["dialog"], "liste", False)):
            return W["msg"], "faint"
        return None

    def _kasten(self, by, bx, bh, bw, w, h, titel):
        z, C = self.z, self.z.C
        w, h = min(bw - 2, w), min(bh - 2, h)
        y, x = by + max(1, (bh - h) // 2), bx + (bw - w) // 2
        for i in range(h):
            z.safe_addstr(y + i, x, " " * w, C["dim"])
        z.draw_box(y, x, h, w, " %s " % titel, C.get("kal", C["acc"]) | curses.A_BOLD)
        return y, x, w, h

    def zeichne_kasten(self, by, bx, bh, bw):
        dl = self.W["dialog"]
        if dl is None:
            return
        z, C = self.z, self.z.C
        kal = C.get("kal", C["acc"])
        if isinstance(dl, kw.Formular):
            felder = dl.felder                   # alle, feste Plätze (18.10.2026)
            self._zeichne_felder(dl.zeilen(), [f.art for f in felder],
                                 [f.adv for f in felder], dl.titel, dl.fehler,
                                 by, bx, bh, bw, gilt=dl.gilt())
            if dl.box is not None:               # Fenster „advanced" über dem Formular
                self._zeichne_advanced(dl.box, by, bx, bh, bw)
            return
        if getattr(dl, "liste", False):
            self._zeichne_liste(dl, by, bx, bh, bw)
            return
        # Rückfrage: lange Fragen (Kollisions-Warnung ~120 Zeichen) brechen
        # um, der Kasten wächst in der Höhe statt abzuschneiden (16.10.2026).
        frage = dl.zeile()
        w = max(44, min(bw - 4, len(frage) + 6))
        zeilen = rueckfrage_zeilen(frage, w - 4)
        y, x, w, h = self._kasten(by, bx, bh, bw, w, len(zeilen) + 4, dl.titel)
        for i, zeile in enumerate(zeilen[:max(1, h - 4)]):
            z.addclip(y + 2 + i, x + 2, zeile, w - 4, C["bright"])

    def _zeichne_felder(self, zeilen, arten, stile, titel, fehler, by, bx, bh, bw,
                        gilt=None):
        """Ein Kasten mit Feldzeilen (Formular und Fenster „advanced"):
        Beschriftung, Wert (aktiv in Akzentfläche), unten Hilfe/Fehler. Die
        Tasten stehen in der Leiste ganz unten (Tastentabelle, 11.10.2026).
        `stile[i]`: dict mit „stil" → Rahmenzeichen farbig. `gilt[i]` falsch:
        die Zeile gilt gerade nicht → ganz gedämpft (sie steht trotzdem da,
        damit nichts den Platz wechselt — 18.10.2026)."""
        z, C = self.z, self.z.C
        kal = C.get("kal", C["acc"])
        bl = max(len(b) for b, *_ in zeilen) + 2
        # breit genug für die längste Zeile (Stil-Vorschau), höchstens der Platz
        w = min(bw - 4, max(56, bl + 40, bl + 6 + max(len(wt) for _b, wt, *_r in zeilen)))
        h = len(zeilen) + 5
        y, x, w, h = self._kasten(by, bx, bh, bw, w, h, titel)
        for i, (besch, wert, aktiv, hilfe) in enumerate(zeilen):
            yy = y + 2 + i
            if gilt is not None and i < len(gilt) and not gilt[i]:
                z.addclip(yy, x + 2, besch, bl, C["faint"])
                z.addclip(yy, x + 2 + bl, wert, w - bl - 4, C["faint"])
                continue
            z.addclip(yy, x + 2, besch, bl, kal if aktiv else C["faint"])
            feld_w = w - bl - 4
            art = arten[i] if i < len(arten) else "text"
            txt = wert + ("_" if aktiv and art == "text" else "")
            attr = C.get("k_akzent_inv", C["bright"] | curses.A_REVERSE) if aktiv else C["dim"]
            z.addclip(yy, x + 2 + bl, txt.ljust(feld_w)[:feld_w], feld_w, attr)
            st = (stile[i] or {}).get("stil") if i < len(stile) else None
            if st:                               # Rahmenzeichen in Rahmen- und Flächenfarbe
                self._stil_vorschau(yy, x + 2 + bl, st, wert)
        unten = y + h - 2
        if fehler:
            z.addclip(unten, x + 2, "⚠ " + fehler, w - 4, C["warn"])
        else:
            hilfe = next((hf for _b, _w, a, hf in zeilen if a and hf), "")
            if hilfe:
                z.addclip(unten, x + 2, hilfe, w - 4, C["faint"])

    def _zeichne_advanced(self, adv, by, bx, bh, bw):
        """Das Fenster „advanced" (kalender_advanced.Advanced) und darüber,
        falls offen, die Stylebox oder „welche Liste?"."""
        zeilen = adv.zeilen()
        stile = [{"stil": adv.stil} if b == "Stylebox" else None for b, *_r in zeilen]
        self._zeichne_felder(zeilen, ["wahl"] * len(zeilen), stile, adv.titel, adv.fehler,
                             by, bx, bh, bw, gilt=adv.gilt())
        u = adv.unter
        if u is None:
            return
        if getattr(u, "liste", False):
            self._zeichne_liste(u, by, bx, bh, bw)
        else:                                    # Stylebox
            hb, wb = u.groesse(bh - 2, bw - 4)           # aus dem Inhalt (vorher fest 22)
            yb, xb, hb, wb = u.mittig(bh, bw, hb, wb)
            u.zeichne(self.z, by + yb, bx + xb, hb, wb)

    def _stil_vorschau(self, y, x, st, wert=""):
        """Die drei Rahmenzeichen in der Zeile farbig (wie der Kasten im
        Kalender aussehen wird) — dort, wo sie im Text stehen."""
        vr = kalender_stil.vorschau_rahmen(st)
        if vr is None:
            return
        zeichen, rolle = vr
        ab = wert.find(zeichen)
        if ab < 0:
            return
        attr = self.kal._stil_attr(rolle) if hasattr(self.kal, "_stil_attr") else self.z.C["dim"]
        self.z.addclip(y, x + ab, zeichen, 3, attr)

    def _zeichne_liste(self, dl, by, bx, bh, bw):
        """Ein Listen-Kasten (Rhythmus, „welche Liste?"): eine Zeile je
        Eintrag, Zeichen in Motivfarbe, der gewählte in Akzentfläche; unten
        Fehler und der Stand (hilfe(): Suche, gewählter Tag)."""
        z, C = self.z, self.z.C
        zeilen = dl.liste_zeilen()
        platz = max(1, min(len(zeilen) or 1, bh - 9))
        breit = max([len(t) for _z, _r, t, _a in zeilen] + [len(dl.hilfe())])
        y, x, w, h = self._kasten(by, bx, bh, bw, max(60, breit + 8), platz + 6, dl.titel)
        erst = max(0, dl.i - platz + 1)
        aktiv = C.get("k_akzent_inv", C["bright"] | curses.A_REVERSE)
        if not zeilen:
            z.addclip(y + 2, x + 2, getattr(dl, "leer_text", "noch keine phase"),
                      w - 4, C["faint"])
        for k, (zeichen, rolle, text, an) in enumerate(zeilen[erst:erst + platz]):
            yy = y + 2 + k
            z.addclip(yy, x + 2, zeichen, 2, aktiv if an else C.get(rolle, C["faint"]))
            z.addclip(yy, x + 4, " " + text.ljust(w - 7)[:w - 7], w - 6,
                      aktiv if an else C["dim"])
        if dl.fehler:
            z.addclip(y + h - 3, x + 2, "⚠ " + dl.fehler, w - 4, C["warn"])
        z.addclip(y + h - 2, x + 2, dl.hilfe(), w - 4, C["faint"])

    def zeichne_popup(self, by, bx, bh, bw):
        W, z, C = self.W, self.z, self.z.C
        if not W["popup"]:
            return
        zeilen = W["popup"]
        w = max(30, max(len(s) for s in zeilen) + 4)
        y, x, w, h = self._kasten(by, bx, bh, bw, w, len(zeilen) + 2, "ansehen")
        for i, s in enumerate(zeilen[:h - 2]):
            z.addclip(y + 1 + i, x + 2, s, w - 4, C["bright"] if i == 0 else C["dim"])
