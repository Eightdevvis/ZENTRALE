# tui/ansichten/kalender_bedienung.py
#
# Die Tasten der Kalender-Ansichten (A, später B/C) — wie calcurse. Hält die
# EINE Auswahl (Tag, Termin, Kasten), führt die Dialoge aus
# kalender_werkzeuge.py, schickt ihre Aufrufe ans Backend und zeichnet
# Frage-Zeile und Ansehen-Fenster. Die Ansicht selbst zeichnet nur.
#
# Eigene Datei, weil kalender.py sonst über die Riesen-Grenze wüchse
# (memory/system/tui_bauplan.md); der alte Kalender fliegt in Etappe 2 raus.

import curses
import json
import urllib.error
from datetime import date, timedelta

from .basis import BEENDEN, api_call
from . import kalender_werkzeuge as kw

FENSTER_TAGE = 3            # so viele Tage zeigt A (kalender_ansichten.ansicht_a)
FOKUS = ("termine", "kalender", "todo")


def _monat(d: date, delta: int) -> date:
    m = d.month - 1 + delta
    j, m = d.year + m // 12, m % 12 + 1
    for t in (d.day, 30, 29, 28):
        try:
            return date(j, m, t)
        except ValueError:
            continue


class Bedienung:
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
        d["_for"] = schluessel
        K["sdata"] = d
        return d

    def _holen(self, view, ref):
        try:
            r = api_call("/api/calendar?view=%s&ref=%s" % (view, ref.isoformat()), timeout=2.0)
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
        """Tag wählen; das 3-Tage-Fenster rückt mit, wenn er herausfällt."""
        W, K = self.W, self.K
        W["tag"], W["idx"] = d, idx
        ref = date.fromisoformat(K["ref"])
        if d < ref:
            K["ref"] = d.isoformat()
        elif d > ref + timedelta(days=FENSTER_TAGE - 1):
            K["ref"] = (d - timedelta(days=FENSTER_TAGE - 1)).isoformat()

    def termine(self, d: date | None = None) -> list:
        return kw.eintraege(self.daten(), d or self.tag(), self.K["showhidden"])

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
        return {"fokus": W["fokus"], "tag": self.tag().isoformat(),
                "idx": W["idx"], "tidx": W["tidx"]}

    # ── Tasten ─────────────────────────────────────────────────────────
    def taste(self, ch):
        """→ BEENDEN, True (verbraucht) oder False (die Ansicht soll sie
        nehmen: v, Theme, …)."""
        W, K = self.W, self.K
        W["msg"] = "" if ch != -1 else W["msg"]
        if W["dialog"] is not None:
            self._dialog_taste(ch)
            return True
        if W["popup"] is not None:
            W["popup"] = None              # jede Taste schließt, wie calcurse
            return True
        if ch == 27:
            K["active"] = False
            return True
        if ch in (ord("q"), ord("Q")):
            return BEENDEN
        if ch == 9:
            W["fokus"] = FOKUS[(FOKUS.index(W["fokus"]) + 1) % len(FOKUS)]
            return True
        if ch == curses.KEY_BTAB:
            W["fokus"] = FOKUS[(FOKUS.index(W["fokus"]) - 1) % len(FOKUS)]
            return True
        if self._springen(ch):
            return True
        if W["fokus"] == "todo":
            return self._taste_todo(ch)
        if W["fokus"] == "kalender":
            return self._taste_kalender(ch)
        return self._taste_termine(ch)

    def _springen(self, ch) -> bool:
        """calcurse: t/T Tag, w/W Woche, m/M Monat, y/Y Jahr, g gehe zu,
        Strg-G heute — gilt in jedem Kasten."""
        d = self.tag()
        sprung = {ord("t"): d + timedelta(days=1), ord("T"): d - timedelta(days=1),
                  ord("w"): d + timedelta(days=7), ord("W"): d - timedelta(days=7),
                  ord("m"): _monat(d, 1), ord("M"): _monat(d, -1),
                  ord("y"): _monat(d, 12), ord("Y"): _monat(d, -12),
                  7: date.today()}.get(ch)
        if sprung:
            self.setze_tag(sprung)
            return True
        if ch == ord("g"):
            self._starte(kw.dialog_gehe_zu(date.today()))
            return True
        if ch in (ord("x"), ord("X")):
            self.K["showhidden"] = not self.K["showhidden"]
            self.W["msg"] = "erledigte: " + ("an" if self.K["showhidden"] else "aus")
            return True
        return False

    def _taste_termine(self, ch) -> bool:
        W, d = self.W, self.tag()
        ts = self.termine()
        if ch in (curses.KEY_UP, ord("k")):
            if W["idx"] > 0:
                W["idx"] -= 1
            else:                              # über den Tagesanfang: Tag davor
                vor = d - timedelta(days=1)
                self.setze_tag(vor, max(0, len(self.termine(vor)) - 1))
        elif ch in (curses.KEY_DOWN, ord("j")):
            if W["idx"] < len(ts) - 1:
                W["idx"] += 1
            else:
                self.setze_tag(d + timedelta(days=1))
        elif ch in (curses.KEY_LEFT, ord("h")):
            self.setze_tag(d - timedelta(days=1))
        elif ch in (curses.KEY_RIGHT, ord("l")):
            self.setze_tag(d + timedelta(days=1))
        elif ch in (ord("a"), ord("A"), 1):    # Strg-A wie calcurse
            self._starte(kw.dialog_anlegen(d))
        elif ch in (10, 13, curses.KEY_ENTER):
            roh = self.gewaehlt()
            if roh:
                W["popup"] = kw.details(roh, d)
        elif ch in (ord("e"), ord("E"), ord("d"), ord("D"), ord("r"), ord("c")):
            roh = self.gewaehlt()
            if not roh:
                W["msg"] = "kein termin gewählt"
            elif ch in (ord("e"), ord("E")):
                self._starte(kw.dialog_bearbeiten(roh, d, date.today()))
            elif ch in (ord("d"), ord("D")):
                self._starte(kw.dialog_loeschen(roh, d))
            elif ch == ord("r"):
                dl = kw.dialog_wiederholen(roh, d, date.today())
                if dl is None:
                    W["msg"] = "eine spanne wiederholt sich nicht — e ändert sie"
                else:
                    self._starte(dl)
            else:
                W["clip"] = kw.kopie(roh)
                W["msg"] = "kopiert: %s — p fügt am gewählten tag ein" % roh.get("label", "")
        elif ch in (ord("p"), 22):             # p / Strg-V
            if W["clip"]:
                self._ausfuehren(kw.plan_einfuegen(W["clip"], d))
            else:
                W["msg"] = "nichts kopiert (c)"
        elif ch == ord("!"):
            W["msg"] = "! hakt im TODO-Kasten ab (Tab)"
        else:
            return False
        return True

    def _taste_kalender(self, ch) -> bool:
        """calcurse-Kalenderkasten: Pfeile wählen den Tag, 0/$ Wochenanfang/-ende."""
        d = self.tag()
        sprung = {curses.KEY_LEFT: -1, ord("h"): -1, curses.KEY_RIGHT: 1, ord("l"): 1,
                  curses.KEY_UP: -7, ord("k"): -7, curses.KEY_DOWN: 7, ord("j"): 7,
                  ord("0"): -d.weekday(), ord("$"): 6 - d.weekday()}.get(ch)
        if sprung is not None:
            self.setze_tag(d + timedelta(days=sprung))
        elif ch in (10, 13, curses.KEY_ENTER):
            self.W["fokus"] = "termine"
        elif ch in (ord("a"), ord("A"), 1):
            self._starte(kw.dialog_anlegen(d))
        else:
            return False
        return True

    def _taste_todo(self, ch) -> bool:
        W = self.W
        lid, items = kw.todo_punkte(self.daten())
        it = items[W["tidx"]] if items and 0 <= W["tidx"] < len(items) else None
        if ch in (curses.KEY_UP, ord("k")):
            W["tidx"] = max(0, W["tidx"] - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            W["tidx"] = min(max(0, len(items) - 1), W["tidx"] + 1)
        elif lid is None and ch in (ord("a"), ord("e"), ord("d"), ord("!"), ord("+"), ord("-")):
            W["msg"] = "keine wochenliste gefunden"
        elif ch in (ord("a"), ord("A"), 20):   # Strg-T wie calcurse
            self._starte(kw.dialog_todo_neu(lid))
        elif it is None and ch in (ord("e"), ord("d"), ord("!"), ord("+"), ord("-")):
            W["msg"] = "keine aufgabe gewählt"
        elif ch in (ord("e"), ord("E")):
            self._starte(kw.dialog_todo_bearbeiten(lid, it))
        elif ch in (ord("d"), ord("D")):
            self._starte(kw.dialog_todo_loeschen(lid, it))
        elif ch == ord("!"):                   # calcurse: erledigt an/aus
            self._ausfuehren(kw._plan([("POST", "/api/lists/%s/items/%s/toggle" % (lid, it["id"]),
                                        {})]))
        elif ch in (ord("+"), ord("-")):       # Reihenfolge = Priorität
            delta = -1 if ch == ord("+") else 1
            self._ausfuehren(kw._plan([("POST", "/api/lists/%s/items/%s/reorder"
                                        % (lid, it["id"]), {"delta": delta})]))
            W["tidx"] = max(0, min(len(items) - 1, W["tidx"] + delta))
        elif ch in (10, 13, curses.KEY_ENTER):
            W["popup"] = ["Aufgabe", "", str(it.get("text", "")) if it else "",
                          "", "erledigt" if it and it.get("done") else "offen"]
        else:
            return False
        return True

    # ── Dialoge und Aufrufe ────────────────────────────────────────────
    def _starte(self, dialog):
        self.W["dialog"] = dialog
        self.W["nach_konflikt"] = None

    def _dialog_taste(self, ch):
        W = self.W
        dl = W["dialog"]
        r = dl.taste(ch)
        if r == "abbruch":
            W["dialog"] = None
            W["msg"] = "abgebrochen"
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
                              body=plan["konflikt"]) or {}).get("konflikte") or []
            except Exception:
                k = []
            if k:
                zeile = k[0].lstrip("⚠ ").strip()
                W["dialog"] = kw.Dialog("kollision", [kw.Schritt(
                    "ok", "⚠ %s%s · trotzdem speichern? (j/n)"
                    % (zeile, " (+%d)" % (len(k) - 1) if len(k) > 1 else ""),
                    art="wahl", wahl={"j": True, "n": False})], lambda a: kw._plan())
                W["nach_konflikt"] = plan
                return
        for methode, pfad, body in plan.get("aufrufe", []):
            try:
                api_call(pfad, method=methode, body=body)
            except urllib.error.HTTPError as e:
                try:
                    grund = json.loads(e.read().decode("utf-8")).get("error") or str(e)
                except Exception:
                    grund = str(e)
                W["msg"] = "⚠ " + grund
                self.neu_laden()
                return
            except Exception as e:
                W["msg"] = "⚠ backend? " + str(e)[:60]
                self.neu_laden()
                return
        if plan.get("aufrufe"):
            self.neu_laden()
        if plan.get("meldung"):
            W["msg"] = plan["meldung"]
        if plan.get("danach", {}).get("tag"):
            self.setze_tag(plan["danach"]["tag"])

    # ── Zeichnen: Frage-Zeile und Ansehen-Fenster ──────────────────────
    def zeile_unten(self):
        """(text, rolle) für die unterste Zeile: Frage, Meldung oder None."""
        W = self.W
        if W["dialog"] is not None:
            return W["dialog"].zeile(), "kal"
        if W["msg"]:
            return W["msg"], "faint"
        return None

    def zeichne_popup(self, by, bx, bh, bw):
        W, z, C = self.W, self.z, self.z.C
        if not W["popup"]:
            return
        zeilen = W["popup"]
        w = min(bw - 4, max(30, max(len(s) for s in zeilen) + 4))
        h = min(bh - 2, len(zeilen) + 3)
        y, x = by + (bh - h) // 2, bx + (bw - w) // 2
        for i in range(h):
            z.safe_addstr(y + i, x, " " * w, C["dim"])
        z.draw_box(y, x, h, w, " ansehen ", C.get("kal", C["acc"]))
        for i, s in enumerate(zeilen[:h - 3]):
            z.addclip(y + 1 + i, x + 2, s, w - 4, C["bright"] if i == 0 else C["dim"])
        z.addclip(y + h - 2, x + 2, "eine taste schließt", w - 4, C["faint"])
