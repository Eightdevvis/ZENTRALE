"""Der Kasten „Rhythmus": Tagesphasen einstellen — reine Logik, kein curses.

Sasha, 10.10.2026: „man muss ihn irgendwo einschreiben können … bau einfach
das gerüst dafür in dem ich es selbst dann einstellen kann, mach alles
möglich, dann is das ganze gleich für jeden anderen auch nutzbar … wenn ich
heute come down um 9:30 habe, dann 3 tage um 2 ins bett gehe, muss das
änderbar sein".

Taste R im Kalender (kalender_bedienung.TASTE_RHYTHMUS) öffnet die Liste
aller Phasen (GET /api/calendar/phasen). Darin:
  n  neue Phase          e / Enter  ändern (ab jetzt, PUT /api/calendar/phase)
  d  löschen             t  nur am gewählten Tag
  z  für einen Zeitraum („3 Tage um 2 ins Bett")
„nur am Tag" und „Zeitraum" gehen beide über POST /api/calendar/routine/
zeitraum (ein Tag = von gleich bis) — eine Abweichung je Tag im Kern
(kalender_kennung.routine_zeitraum_aendern), die Regel bleibt.

Wie kalender_werkzeuge: Formulare und Dialoge sammeln Antworten, `plan()`
macht daraus Aufrufe, die die Bedienung ausführt. Nach dem Speichern geht
der Kasten wieder auf (`zurueck`), Esc in einem Formular führt in die Liste.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import kalender_motive
from .kalender_werkzeuge import (WT_CODE, WT_KURZ, Dialog, Feld, Formular, Schritt,
                                 _l_datum, _l_titel, _l_wtage, _l_zahl, _l_zeit, _plan,
                                 datum_text, regel_text)

# ── Wiederholung einer Phase ───────────────────────────────────────────
# Die gängigen Rhythmen als Wahl, alles andere über „an Tagen" + Abstand.
# Eine Regel, die hier nicht abbildbar ist (monatlich, COUNT …), bleibt
# „wie bisher" und wird beim Speichern nicht angefasst.
TAEGLICH, WERKTAGS, WOCHENENDE, AN_TAGEN, WIE_BISHER = (
    "täglich", "werktags", "wochenende", "an tagen", "wie bisher")
_WERKTAGE = ["MO", "TU", "WE", "TH", "FR"]
_WOCHENENDE = ["SA", "SU"]


def regel_lesen(rrule) -> dict:
    """RRULE → {wied, alle, wtage, bis} für das Formular."""
    teile = dict(p.split("=", 1) for p in (rrule or "").split(";") if "=" in p)
    bis = ""
    until = teile.pop("UNTIL", "")
    if until:
        try:
            bis = datum_text(date(int(until[:4]), int(until[4:6]), int(until[6:8])))
        except ValueError:
            pass
    freq = teile.pop("FREQ", "")
    alle = teile.pop("INTERVAL", "1") or "1"
    tage = [c for c in teile.pop("BYDAY", "").split(",") if c]
    aus = {"wied": WIE_BISHER, "alle": alle, "wtage": "", "bis": bis}
    if teile or not freq:                  # COUNT, BYMONTHDAY …: nicht abbildbar
        return aus
    if freq == "DAILY" and not tage:
        aus["wied"] = TAEGLICH
    elif freq == "WEEKLY" and tage and all(t in WT_CODE for t in tage):
        if alle == "1" and tage == _WERKTAGE:
            aus["wied"] = WERKTAGS
        elif alle == "1" and tage == _WOCHENENDE:
            aus["wied"] = WOCHENENDE
        else:
            aus["wied"] = AN_TAGEN
            aus["wtage"] = " ".join(WT_KURZ[WT_CODE.index(t)].lower() for t in tage)
    return aus


def regel_bauen(wied, alle=1, wtage=None) -> str | None:
    """Formularwerte → RRULE ohne UNTIL (das Ende geht als `bis` mit);
    None = Regel nicht anfassen („wie bisher")."""
    n = ";INTERVAL=%d" % alle if alle and alle > 1 else ""
    if wied == TAEGLICH:
        return "FREQ=DAILY" + n
    if wied == WERKTAGS:
        return "FREQ=WEEKLY;BYDAY=" + ",".join(_WERKTAGE)
    if wied == WOCHENENDE:
        return "FREQ=WEEKLY;BYDAY=" + ",".join(_WOCHENENDE)
    if wied == AN_TAGEN and wtage:
        return "FREQ=WEEKLY%s;BYDAY=%s" % (n, ",".join(wtage))
    return None


# ── Anzeige ────────────────────────────────────────────────────────────
def _zeiten(p) -> str:
    t, e = p.get("time") or "", p.get("ende") or ""
    if not e:
        return t
    return "%s–%s%s" % (t, e, " (+1)" if e < t else "")


def _abweichend(p) -> int:
    a = p.get("abweichungen")
    return len(a) if isinstance(a, dict) else 0


def zeile(p: dict, motiv_namen: dict) -> str:
    """„coming down   21:30–23:00   Nachthimmel · täglich · ab 10.10.2026"."""
    teile = [motiv_namen.get(p.get("motiv"), p.get("motiv") or "?"),
             regel_text(p.get("rrule")) or "?"]
    try:
        teile.append("ab " + datum_text(date.fromisoformat(p["seit"])))
    except (KeyError, TypeError, ValueError):
        pass
    if _abweichend(p):
        n = _abweichend(p)
        teile.append("%d %s anders" % (n, "Tag" if n == 1 else "Tage"))
    return "%-16s %-19s %s" % ((p.get("label") or "?")[:16], _zeiten(p), " · ".join(teile))


class PhasenListe:
    """Die Liste im Kasten. `taste` → 'weiter' | 'fertig' (dann ist `plan()`
    der nächste Schritt: ein Formular als `weiter`) | 'abbruch'.
    `zurueck` setzt die Bedienung: () → eine frisch geladene Liste."""

    liste = True                    # zeichne_kasten erkennt den Kasten daran

    def __init__(self, phasen, motive, tag: date, heute: date, zurueck=None):
        self.phasen = sorted([p for p in phasen or [] if isinstance(p, dict)],
                             key=lambda p: (p.get("time") or "", p.get("label") or ""))
        self.motive = [m for m in motive or [] if isinstance(m, dict) and m.get("schluessel")]
        if not self.motive:          # Backend ohne Katalog: die Muster der TUI
            self.motive = [{"schluessel": k, "name": k.capitalize()}
                           for k in kalender_motive.MUSTER]
        self.motiv_namen = {m["schluessel"]: m.get("name") or m["schluessel"]
                            for m in self.motive}
        self.tag, self.heute = tag, heute
        self.zurueck = zurueck
        self.titel = "rhythmus"
        self.i = 0
        self.fehler = ""
        self._ergebnis = None

    @property
    def gewaehlt(self):
        return self.phasen[self.i] if self.phasen else None

    def hilfe(self) -> str:
        tag = "%s %s" % (WT_KURZ[self.tag.weekday()], self.tag.strftime("%d.%m."))
        if not self.phasen:
            return "n neue phase · esc schließen"
        return ("↑↓ wählen · n neu · e ändern · d löschen · t nur %s · z zeitraum · esc"
                % tag)

    def liste_zeilen(self) -> list:
        """[(zeichen, rolle, text, aktiv)] für den Kasten."""
        return [(kalender_motive.zeichen_a(p.get("motiv")), kalender_motive.rolle(p.get("motiv")),
                 zeile(p, self.motiv_namen), k == self.i)
                for k, p in enumerate(self.phasen)]

    def _weiter(self, dialog):
        """Ein Formular/Dialog öffnen; Esc darin führt hierher zurück."""
        dialog.bei_abbruch = self.zurueck
        self._ergebnis = _plan(weiter=dialog)
        return "fertig"

    def taste(self, ch: int) -> str:
        self.fehler = ""
        n = len(self.phasen)
        if ch == 27 or ch in (ord("q"),):
            return "abbruch"
        if ch in (259, ord("k")) and n:
            self.i = (self.i - 1) % n
        elif ch in (258, ord("j"), 9) and n:
            self.i = (self.i + 1) % n
        elif ch in (ord("n"), ord("a")):
            return self._weiter(formular_phase(None, self.motive, self.heute, self.zurueck))
        elif not n and ch in (ord("e"), 10, 13, ord("d"), ord("t"), ord("z")):
            self.fehler = "noch keine phase — n legt eine an"
        elif ch in (ord("e"), 10, 13, 343):
            return self._weiter(formular_phase(self.gewaehlt, self.motive, self.heute,
                                               self.zurueck))
        elif ch == ord("d"):
            return self._weiter(dialog_loeschen(self.gewaehlt, self.zurueck))
        elif ch == ord("t"):
            return self._weiter(formular_tag(self.gewaehlt, self.tag, self.zurueck))
        elif ch == ord("z"):
            return self._weiter(formular_zeitraum(self.gewaehlt, self.tag, self.heute,
                                                  self.zurueck))
        return "weiter"

    def plan(self) -> dict:
        return self._ergebnis or _plan()


# ── Formular: Phase anlegen / ab jetzt ändern ──────────────────────────
def _l_ende(s):
    if not s.strip():
        return True, None
    z = _l_zeit()(s)
    return z if not z[0] else (True, z[1])


def formular_phase(p: dict | None, motive: list, heute: date, zurueck=None) -> Formular:
    """Name, Motiv, von, bis (darf über Mitternacht), Wiederholung, gültig
    ab/bis. p=None: neu (POST /api/calendar/phase), sonst ab jetzt ändern
    (PUT, nur die Kennung zählt — Titel und Zeit dürfen sich ändern)."""
    p = p or {}
    namen = [m.get("name") or m["schluessel"] for m in motive]
    schl = {m.get("name") or m["schluessel"]: m["schluessel"] for m in motive}
    motiv0 = next((n for n, k in schl.items() if k == p.get("motiv")), namen[0] if namen else "")
    r = regel_lesen(p.get("rrule") or "FREQ=DAILY")
    optionen = (TAEGLICH, WERKTAGS, WOCHENENDE, AN_TAGEN)
    if r["wied"] == WIE_BISHER:
        optionen = (WIE_BISHER,) + optionen
    try:
        ab = datum_text(date.fromisoformat(p["seit"]))
    except (KeyError, TypeError, ValueError):
        ab = datum_text(heute)
    mit_abstand = lambda w: w.get("wied") in (TAEGLICH, AN_TAGEN)
    felder = [
        Feld("label", "Name", wert=p.get("label") or "", lesen=_l_titel,
             hilfe="z.B. coming down, Schlaf, Hunger"),
        Feld("motiv", "Motiv", art="wahl", wert=motiv0, optionen=namen,
             hilfe="das Muster im Hintergrund der Woche"),
        Feld("von", "Von", wert=p.get("time") or "", lesen=_l_zeit(leer_ok=False),
             hilfe="hh:mm"),
        Feld("bis", "Bis", wert=p.get("ende") or "", lesen=_l_ende,
             hilfe="hh:mm · vor Von = endet am Folgetag (23:00–07:00)"),
        Feld("wied", "Wiederholung", art="wahl", wert=r["wied"], optionen=optionen),
        Feld("alle", "Abstand", wert=r["alle"], lesen=_l_zahl(), zeigen=mit_abstand,
             hilfe="1 = jedes Mal, 2 = jeden zweiten Tag / jede zweite Woche"),
        Feld("wtage", "An Tagen", wert=r["wtage"], lesen=_l_wtage,
             zeigen=lambda w: w.get("wied") == AN_TAGEN, hilfe="z.B. mo mi fr, sa-so"),
        Feld("ab", "Gültig ab", wert=ab, lesen=_l_datum(heute), hilfe="TT.MM.JJJJ"),
        Feld("bis_tag", "Gültig bis", wert=r["bis"], lesen=_l_datum(heute),
             hilfe="leer = bis auf Weiteres"),
    ]

    def pruefen(w):
        if w.get("wied") == AN_TAGEN and not w.get("wtage"):
            return "wtage", "welche tage? z.B. mo mi fr"
        if w.get("bis_tag") and w.get("ab") and w["bis_tag"] < w["ab"]:
            return "bis_tag", "gültig bis liegt vor gültig ab"
        return None

    def plan(w):
        body = {"label": w["label"], "motiv": schl.get(w["motiv"], w["motiv"]),
                "time": w["von"], "ende": w.get("bis") or "",
                "von": w["ab"].isoformat(),
                "bis": w["bis_tag"].isoformat() if w.get("bis_tag") else ""}
        regel = regel_bauen(w["wied"], w.get("alle") or 1, w.get("wtage"))
        if regel:
            body["rrule"] = regel
        if p.get("kennung"):
            body["kennung"] = p["kennung"]
            return _plan([("PUT", "/api/calendar/phase", body)],
                         "rhythmus geändert: " + w["label"], zurueck=zurueck)
        body = {k: v for k, v in body.items() if v != ""}
        return _plan([("POST", "/api/calendar/phase", body)],
                     "neue phase: " + w["label"], zurueck=zurueck)
    return Formular("neue phase" if not p else "phase ändern · ab jetzt", felder, plan,
                    pruefen=pruefen)


# ── Ein Tag / ein Zeitraum anders ──────────────────────────────────────
def _an_dem_tag(p: dict, tag: date) -> tuple:
    """(von, bis) der Phase an `tag` — eine Abweichung geht vor."""
    for a in (p.get("abweichungen") or {}).values():
        if isinstance(a, dict) and a.get("tag") == tag.isoformat():
            return a.get("time") or p.get("time") or "", a.get("ende") or p.get("ende") or ""
    return p.get("time") or "", p.get("ende") or ""


def _zeit_felder(von, bis) -> list:
    anders = lambda w: w.get("regel") != "ja"
    return [
        Feld("regel", "Wie die Regel", art="wahl", wert="nein", optionen=("nein", "ja"),
             hilfe="ja = an diesen Tagen wieder wie sonst"),
        Feld("von", "Von", wert=von, lesen=_l_zeit(leer_ok=False), zeigen=anders,
             hilfe="hh:mm am Tag des Beginns — 02:00 heißt früh an DIESEM Tag"),
        Feld("bis", "Bis", wert=bis, lesen=_l_ende, zeigen=anders,
             hilfe="hh:mm · vor Von = endet am Folgetag"),
    ]


def _zeitraum_body(p, von: date, bis: date, w) -> dict:
    body = {"kennung": p.get("kennung"), "von": von.isoformat(), "bis": bis.isoformat()}
    if w.get("regel") == "ja":
        body.update({"time": "", "ende": ""})
    else:
        body["time"] = w["von"]
        if w.get("bis"):
            body["ende"] = w["bis"]
    return body


def formular_tag(p: dict, tag: date, zurueck=None) -> Formular:
    """t: „heute come down um 9:30" — nur dieser Tag (der Tag des Beginns)."""
    v0, b0 = _an_dem_tag(p, tag)

    def plan(w):
        return _plan([("POST", "/api/calendar/routine/zeitraum", _zeitraum_body(p, tag, tag, w))],
                     "nur %s: %s" % (datum_text(tag), p.get("label", "")), zurueck=zurueck)
    return Formular("„%s“ nur am %s %s" % (p.get("label", ""), WT_KURZ[tag.weekday()],
                                            datum_text(tag)), _zeit_felder(v0, b0), plan)


def formular_zeitraum(p: dict, tag: date, heute: date, zurueck=None) -> Formular:
    """z: „3 Tage um 2 ins Bett" — alle Vorkommen von … bis anders."""
    v0, b0 = _an_dem_tag(p, tag)
    felder = [Feld("erster", "Erster Tag", wert=datum_text(tag), lesen=_l_datum(heute)),
              Feld("letzter", "Letzter Tag", wert=datum_text(tag + timedelta(days=2)),
                   lesen=_l_datum(heute), hilfe="höchstens 366 Tage")] + _zeit_felder(v0, b0)

    def pruefen(w):
        if w["letzter"] < w["erster"]:
            return "letzter", "letzter tag vor dem ersten"
        return None

    def plan(w):
        return _plan([("POST", "/api/calendar/routine/zeitraum",
                       _zeitraum_body(p, w["erster"], w["letzter"], w))],
                     "%s: %s bis %s anders" % (p.get("label", ""), datum_text(w["erster"]),
                                               datum_text(w["letzter"])), zurueck=zurueck)
    return Formular("„%s“ für einen zeitraum" % p.get("label", ""), felder, plan,
                    pruefen=pruefen)


def dialog_loeschen(p: dict, zurueck=None) -> Dialog:
    return Dialog("phase löschen", [Schritt(
        "ok", "Phase „%s“ ganz löschen? (j/n)" % p.get("label", ""),
        art="wahl", wahl={"j": True, "n": False})],
        lambda a: _plan([("DELETE", "/api/calendar/phase", {"kennung": p.get("kennung")})]
                        if a["ok"] else [], ("gelöscht: " + p.get("label", "")) if a["ok"] else "",
                        zurueck=zurueck))

