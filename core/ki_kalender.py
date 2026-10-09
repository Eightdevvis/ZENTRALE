# core/ki_kalender.py
#
# Der Kalender, wie die KI ihn liest: kurze Kennungen je Eintrag, alle Felder
# (Zeit von–bis, Ort, Wiederholung, Pausen, Ebene), die Warnungen frisch
# gerechnet — und der Beleg, der nach jedem Schreiben nachliest, was WIRKLICH
# dasteht. Die Schreib-Werkzeuge selbst: core/ki_kalender_aendern.py.
#
# 2026-10-08, nach Sashas Kalender-Testlauf (Gespräch 20261008-132404, Analyse
# im Claude-Web-Plan §7). Die Fallen waren Werkzeug-Fallen, keine Modell-
# Launen: Ändern per Name traf ALLE Treffer („2 Routine(n) geändert" — welche?),
# das Ergebnis sagte „OK" statt was dasteht, und die Warnungen konnte die KI
# nur raten („5 Warnsymbole unten links"). Nach Anthropic („Writing effective
# tools for agents"): kurze lesbare Kennungen statt Namen oder UUIDs,
# Ergebnisse mit hohem Signal, Fehlermeldungen, die zum richtigen Gebrauch
# lenken.
#
# ── Warum die Kennung aus dem INHALT abgeleitet ist ─────────────────────
# (Entscheidung 2026-10-08) `#r3f9c` = Art (t Termin, r Routine) + 4 Zeichen
# einer Prüfsumme über Ebene, Tag, Titel, Uhrzeit (Routine: Regel statt Tag).
# Erwogen und verworfen:
#   - fortlaufende Nummern je Gespräch (#3): bräuchten Zustand, der einen
#     Neustart des Backends nicht überlebt, und #3 aus dem ersten Lesen
#     meinte nach einem Löschen etwas anderes — ein stiller Fehlgriff.
#   - die UID des .ics-Speichers: gibt es im JSON-Speicher nicht, und die
#     Fassade gibt sie absichtlich nicht heraus.
# Die Inhalts-Kennung braucht keinen Zustand, ist auf beiden Rechnern gleich
# und wirkt als Sicherung: wurde der Eintrag inzwischen geändert, passt die
# alte Kennung nicht mehr, und das Werkzeug sagt „lies neu" statt den
# falschen Eintrag zu treffen. Der Preis: nach einer Änderung von Uhrzeit oder
# Titel hat der Eintrag eine neue Kennung — sie steht im Beleg.
#
# Die Kennungen zeigt nur die gross-Schiene (werkzeug_befund.schiene). Das
# lokale qwen ist auf die bisherige Ausgabe gemessen und bekommt sie weiter.
#
# Der Kalender-Kern (core/kalender*.py) gehört der Kalender-Sitzung und wird
# hier nur benutzt. Was er für diese Seite noch können müsste, steht in
# memory/ki/claude_web_plan.md §7 („braucht vom Kalender-Kern").
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

import kalender
import werkzeug_befund

_WOTAG_LANG = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
               "Samstag", "Sonntag")
_WOTAG = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_BYDAY = {"MO": "mo", "TU": "di", "WE": "mi", "TH": "do", "FR": "fr",
          "SA": "sa", "SU": "so"}


@dataclass
class Stueck:
    """Ein Eintrag, wie er gespeichert ist (nicht ein Vorkommen)."""
    art: str                  # "termin" oder "routine"
    layer: str
    label: str
    roh: dict = field(repr=False)
    day: str | None = None    # Termin: Tag (bei Spannen der Start-Tag)
    kennung: str = ""

    @property
    def time(self):
        return self.roh.get("time") or None

    @property
    def ende(self):
        return self.roh.get("ende") or None

    @property
    def ort(self):
        return self.roh.get("ort") or None

    @property
    def rrule(self):
        return self.roh.get("rrule") or None

    @property
    def bis(self):
        return self.roh.get("bis") or None

    @property
    def uid(self):
        """Die feste Kennung des Kalender-Kerns (core/kalender_kennung.py)."""
        return kalender.kennung(self.roh)

    def schluessel(self) -> str:
        if self.art == "routine":
            return f"r|{self.layer}|{self.label}|{self.rrule}|{self.time or ''}"
        return f"t|{self.layer}|{self.day}|{self.label}|{self.time or ''}|{self.bis or ''}"


def mit_kennungen() -> bool:
    """Kennungen zeigen? Nur auf der gross-Schiene (Kopf dieser Datei)."""
    return werkzeug_befund.schiene() == "gross"


# ── Lesen, was gespeichert ist ─────────────────────────────────────────

def roh() -> dict:
    """Die gespeicherten Kalenderdaten, NUR LESEN.

    Die Fassade hat keine öffentliche Funktion „alle Einträge, wie
    gespeichert" (entries_in_range liefert Vorkommen, keine Serien). Bis es
    sie gibt, liest diese eine Stelle über kalender._load_raw — so wie
    kalender_bearbeiten es auch tut. Bedarf ist gemeldet (Kopf der Datei)."""
    return kalender._load_raw()


def stuecke(daten: dict | None = None) -> list:
    """Alle Termine und Routinen mit ihrer Kennung, in Speicher-Reihenfolge."""
    if daten is None:
        daten = roh()
        if _ohne_uid(daten):
            # Der JSON-Speicher vergibt feste Kennungen erst beim ersten
            # Zugriff über den Kern (kalender_kennung.alle_eintraege).
            import kalender_kennung
            kalender_kennung.alle_eintraege()
            daten = roh()
    liste = []
    for lname, lyr in (daten.get("layers") or {}).items():
        for tag, eintraege in (lyr.get("entries") or {}).items():
            for e in eintraege or []:
                if isinstance(e, dict):
                    liste.append(Stueck("termin", lname, e.get("label") or "", e, day=tag))
        for r in lyr.get("routines") or []:
            if isinstance(r, dict) and r.get("rrule"):
                liste.append(Stueck("routine", lname, r.get("label") or "", r))
    _kennungen_vergeben(liste)
    return liste


def _ohne_uid(daten: dict) -> bool:
    for lyr in (daten.get("layers") or {}).values():
        for eintraege in (lyr.get("entries") or {}).values():
            for e in eintraege or []:
                if isinstance(e, dict) and not kalender.kennung(e):
                    return True
        for r in lyr.get("routines") or []:
            if isinstance(r, dict) and not kalender.kennung(r):
                return True
    return False


def _hash(uid) -> str:
    return hashlib.sha1(str(uid).encode("utf-8")).hexdigest()


def kurz_von(uid, art: str | None = None) -> str:
    """Die kurze Kennung (#r3f9c) zu einer festen Kennung des Kerns — wie
    read_calendar sie zeigt (bei Kollision länger, also nachschlagen)."""
    for s in stuecke():
        if s.uid == uid:
            return s.kennung
    return (art or "t")[0] + _hash(uid)[:4]


def stueck_von(uid):
    """Das Stück mit dieser festen Kennung (oder None)."""
    return next((s for s in stuecke() if s.uid == uid), None)


def _kennungen_vergeben(liste: list) -> None:
    """Seit 2026-10-09 aus der FESTEN Kennung des Kerns (UID): sie überlebt
    Umbenennen, neue Uhrzeit, neuen Ort — die kurze Kennung bleibt also
    dieselbe, auch nach einer Änderung. Vorher war sie aus dem Inhalt
    abgeleitet und änderte sich mit jeder Änderung. Ohne UID (Daten, die
    nicht über den Kern gelesen wurden) wie vorher aus dem Inhalt.
    Kollidieren zwei in 4 Zeichen, werden sie länger."""
    zaehler, hashes = {}, []
    for s in liste:
        if s.uid:
            hashes.append(_hash(s.uid))
            continue
        k = s.schluessel()
        n = zaehler.get(k, 0)
        zaehler[k] = n + 1
        hashes.append(hashlib.sha1(f"{k}|{n}".encode("utf-8")).hexdigest())
    laenge = [4] * len(liste)
    for _ in range(4):
        kurz = [s.art[0] + h[:n] for s, h, n in zip(liste, hashes, laenge)]
        zahl = Counter(kurz)
        doppelt = [i for i, k in enumerate(kurz) if zahl[k] > 1]
        if not doppelt:
            break
        for i in doppelt:
            laenge[i] += 2
    for s, k in zip(liste, kurz if liste else []):
        s.kennung = k


def finden(kennung: str, daten: dict | None = None):
    """-> (Stueck, None) oder (None, Fehlertext). Nimmt '#r3f9c' und 'r3f9c'."""
    k = str(kennung or "").strip().lower().lstrip("#").strip()
    if not k:
        return None, "[Fehler: keine Kennung angegeben.]"
    alle = stuecke(daten)
    treffer = [s for s in alle if s.kennung == k]
    if not treffer and len(k) >= 5:
        treffer = [s for s in alle if s.kennung.startswith(k)]
    if len(treffer) == 1:
        return treffer[0], None
    if not treffer:
        return None, (f"[Kennung #{k} gibt es nicht (mehr) — der Eintrag wurde "
                      f"inzwischen geändert oder gelöscht. Nichts geändert. Lies "
                      f"mit read_calendar neu und nimm die neue Kennung.]")
    return None, (f"[Kennung #{k} ist nicht eindeutig. Nichts geändert. "
                  f"Lies mit read_calendar neu.]")


def nach_name(label: str, art: str, day: str | None = None,
              layer: str | None = None, daten: dict | None = None) -> list:
    """Kandidaten zu einem Titel: genaue Treffer (ohne Groß/Klein) gehen vor,
    sonst Teilstring. Bei Terminen mit `day`: nur Termine an dem Tag, auch
    mehrtägige, die ihn überdecken."""
    nadel = (label or "").strip().casefold()
    if not nadel:
        return []
    kandidaten = []
    for s in stuecke(daten):
        if s.art != art or (layer and s.layer != layer):
            continue
        if art == "termin" and day and not _deckt_tag(s, day):
            continue
        kandidaten.append(s)
    genau = [s for s in kandidaten if s.label.strip().casefold() == nadel]
    return genau or [s for s in kandidaten if nadel in s.label.casefold()]


def _deckt_tag(s: Stueck, day: str) -> bool:
    if s.day == day:
        return True
    return bool(s.bis) and str(s.day) <= day <= str(s.bis)


def mehrdeutig(treffer: list, was: str) -> str:
    """Der Text, wenn ein Name mehrere Einträge trifft: nichts ändern, die
    Liste zeigen, Sasha fragen lassen."""
    zeilen = [f"[Nichts geändert: '{was}' trifft {len(treffer)} Einträge:"]
    zeilen += ["  " + beschreiben(s) for s in treffer[:12]]
    zeilen.append("Frag Sasha, welcher gemeint ist"
                  + (", und nimm dann dessen Kennung.]" if mit_kennungen() else ".]"))
    return "\n".join(zeilen)


# ── Formate ────────────────────────────────────────────────────────────

def datum(iso: str, mit_jahr: bool = True) -> str:
    try:
        d = date.fromisoformat(str(iso))
    except ValueError:
        return str(iso)
    return f"{_WOTAG[d.weekday()]} {d.strftime('%d.%m.%Y' if mit_jahr else '%d.%m.')}"


def zeit(time, ende) -> str:
    """'18:10–19:10'; ohne Ende ausdrücklich so, damit niemand eins erfindet."""
    if time and ende:
        return f"{time}–{ende}"
    if time:
        return f"{time} (ohne Ende)"
    return "ganztags"


def regel_text(rrule: str | None) -> str:
    """FREQ=WEEKLY;BYDAY=TH → 'wöchentlich do'. Unbekanntes bleibt roh."""
    if not rrule:
        return ""
    teile = dict(p.split("=", 1) for p in rrule.upper().split(";") if "=" in p)
    n = teile.get("INTERVAL", "1")
    freq = teile.get("FREQ")
    namen = {"DAILY": ("täglich", "Tage"), "WEEKLY": ("wöchentlich", "Wochen"),
             "MONTHLY": ("monatlich", "Monate"), "YEARLY": ("jährlich", "Jahre")}
    if freq not in namen:
        return rrule
    text = namen[freq][0] if n == "1" else f"alle {n} {namen[freq][1]}"
    tage = [_BYDAY.get(t[-2:], t) + ("" if len(t) == 2 else f" ({t[:-2]}.)")
            for t in teile.get("BYDAY", "").split(",") if t]
    if tage:
        text += " " + ",".join(tage)
    if teile.get("BYMONTHDAY"):
        text += f" am {teile['BYMONTHDAY']}."
    if teile.get("UNTIL"):
        u = teile["UNTIL"][:8]
        text += f" bis {u[6:8]}.{u[4:6]}.{u[0:4]}"
    return text


def _pausen(label: str, daten: dict) -> list:
    """Pausen, die (noch) wirken. Sie gelten nur bei GENAU gleichem Titel
    (kalender._pause_grund)."""
    heute = date.today().isoformat()
    return [p for p in daten.get("pausen") or []
            if p.get("label") == label and str(p.get("bis") or "") >= heute]


def beschreiben(s: Stueck, daten: dict | None = None) -> str:
    """Eine Zeile mit allen Feldern. Mit Kennung nur auf der gross-Schiene."""
    kenn = f"#{s.kennung} " if mit_kennungen() else ""
    ort = f" @ {s.ort}" if s.ort else ""
    if s.art == "termin":
        wann = datum(s.day)
        if s.bis:
            wann += f" bis {datum(s.bis)} (mehrtägig)"
        return f"{kenn}Termin {wann} {zeit(s.time, s.ende)} {s.label}{ort}, Ebene {s.layer}"
    daten = roh() if daten is None else daten
    teile = [f"{kenn}Routine {s.label}: {regel_text(s.rrule)} {zeit(s.time, s.ende)}{ort}",
             f"Ebene {s.layer}"]
    for p in _pausen(s.label, daten):
        grund = f" ({p['grund']})" if p.get("grund") else ""
        teile.append(f"Pause {datum(p.get('von'), False)}–{datum(p.get('bis'))}{grund}")
    aus = [d for d in s.roh.get("aus") or [] if d >= date.today().isoformat()]
    if aus:
        teile.append("einzeln abgesagt: " + ", ".join(datum(d, False) for d in aus[:6]))
    if s.roh.get("abweichungen"):
        teile.append(f"{len(s.roh['abweichungen'])} Termin(e) einzeln verschoben")
    return ", ".join(teile)


# ── Warnungen: dieselbe Liste, die Sasha als ⚠ sieht ───────────────────

def warnungen_zu(label: str | None = None) -> list:
    """Die Warnungen von heute bis +30 Tage, frisch gerechnet (dieselbe Quelle
    wie die ⚠ in Sashas Ansicht: kalender.open_alarms). Mit `label`: nur die,
    die den Titel nennen."""
    try:
        alle = kalender.open_alarms()
    except Exception as e:
        return [f"(Warnungen ließen sich nicht berechnen: {e})"]
    texte = [a["text"] if a["text"].startswith(a["kind"]) else f"{a['kind']}: {a['text']}"
             for a in alle]
    if label:
        nadel = label.casefold()
        texte = [t for t in texte if nadel in t.casefold()]
    # Eine Überschneidung zweier Serien steht für JEDEN Tag einmal da, ohne
    # Datum (kalender.day_warnings) — fünfmal dieselbe Zeile ist Rauschen.
    zahl = {}
    for t in texte:
        zahl[t] = zahl.get(t, 0) + 1
    return [t + (f" (an {n} Tagen)" if n > 1 else "") for t, n in zahl.items()]


def warnungen_lesen(args: dict) -> str:
    """Ausführer read_calendar_warnings."""
    suche = (args.get("suche") or "").strip() or None
    zeilen = warnungen_zu(suche)
    wo = f" mit '{suche}'" if suche else ""
    if not zeilen:
        return (f"Keine Kalender-Warnungen{wo} von heute bis in 30 Tagen "
                f"(frisch berechnet).")
    return (f"Kalender-Warnungen{wo}, heute bis in 30 Tagen, frisch berechnet "
            f"— dieselben, die Sasha als ⚠ sieht ({len(zeilen)}):\n"
            + "\n".join(f"- {z}" for z in zeilen))


# ── read_calendar ──────────────────────────────────────────────────────

def lesen(args: dict) -> str:
    """Ausführer read_calendar. Den Zeitraum rechnet Python (wie bisher);
    klein bekommt die gemessene Ausgabe der Fassade, gross dieselbe Liste
    mit Kennungen, allen Feldern und den Serien darunter."""
    spanne = _zeitraum(args)
    if isinstance(spanne, str):
        return spanne
    start, end = spanne
    layers = args.get("layers") or None
    suche = (args.get("suche") or "").strip() or None
    if not mit_kennungen():
        return kalender.render_range_for_tool(start, end, layers=layers, suche=suche)
    return _lesen_gross(start, end, layers, suche)


def _zeitraum(args: dict):
    """(start, end) oder ein Fehlertext. Unverändert aus ki_werkzeuge
    übernommen (2026-10-08): ohne Angabe nicht bestrafen, sondern sinnvoll
    vorgeben — mit suche ein Quartal, sonst die nahe Zukunft."""
    zeitraum = (args.get("zeitraum") or "").strip()
    suche = (args.get("suche") or "").strip()
    if zeitraum:
        rng = kalender.resolve_range(zeitraum)
        if rng is None:
            return (f"[Fehler: unbekannter zeitraum {zeitraum!r}. "
                    f"Erlaubt: {', '.join(kalender.RANGE_BUCKETS)} "
                    f"- oder start_date+end_date angeben.]")
        start, end = rng
    elif args.get("start_date") and args.get("end_date"):
        try:
            start = date.fromisoformat(args["start_date"])
            end = date.fromisoformat(args["end_date"])
        except ValueError as e:
            return (f"[Fehler: ungültiges start/end-Datum – {e}. "
                    f"Besser 'zeitraum' nutzen: {', '.join(kalender.RANGE_BUCKETS)}.]")
    else:
        start, end = kalender.resolve_range(
            "naechste_90_tage" if suche else "diese_und_naechste_woche")
    return (end, start) if start > end else (start, end)


def _lesen_gross(start, end, layers, suche) -> str:
    tage = kalender.entries_in_range(start, end, layers=layers)
    if suche:
        nadel = suche.casefold()
        tage = {t: treffer for t, es in tage.items()
                if (treffer := [e for e in es if nadel in (e.get("label") or "").casefold()])}
    spanne = f"Kalender {start.strftime('%d.%m.%Y')} bis {end.strftime('%d.%m.%Y')}"
    kopf = f"{spanne} (gefiltert nach {suche!r}):" if suche else f"{spanne}:"
    if not tage:
        return kopf + "\n" + (f"Keine Einträge mit {suche!r} in diesem Zeitraum."
                              if suche else "Keine Einträge in diesem Zeitraum.")
    daten = roh()
    alle = stuecke(daten)
    zuordnung = _Zuordnung(alle)
    zeilen, serien = [kopf], []
    for tag, eintraege in tage.items():
        zeilen.append(f"{_WOTAG_LANG[date.fromisoformat(tag).weekday()]}, "
                      f"{date.fromisoformat(tag).strftime('%d.%m.%Y')}:")
        for e in eintraege:
            s = zuordnung.stueck(e, tag)
            if s is not None and s.art == "routine" and s not in serien:
                serien.append(s)
            zeilen.append("  " + _vorkommen_zeile(e, s))
    if serien:
        zeilen.append("Serien darin:")
        zeilen += ["  " + beschreiben(s, daten) + f" ({s.rrule})" for s in serien]
    n = len(warnungen_zu())
    if n:
        zeilen.append(f"Warnungen (heute bis +30 Tage): {n} — Wortlaut mit "
                      f"read_calendar_warnings.")
    return "\n".join(zeilen)


def _vorkommen_zeile(e: dict, s) -> str:
    kenn = f"#{s.kennung} " if s is not None else "#? "
    if e.get("ausfall"):
        return f"{kenn}ℹ {e['label']} fällt aus ({e['ausfall']}) — kein Termin an diesem Tag"
    if e.get("deaktiviert"):
        return f"{kenn}ℹ {e['label']} ist an diesem Tag abgesagt — findet nicht statt"
    ort = f" @ {e['ort']}" if e.get("ort") else ""
    bis = ""
    if e.get("spanning"):
        bis = f" (mehrtägig {datum(e['von'], False)}–{datum(e['bis'], False)})"
    serie = " ↻" if e.get("recurring") else ""
    return f"{kenn}{zeit(e.get('time'), e.get('ende'))} {e['label']}{bis}{ort} [{e['layer']}]{serie}"


class _Zuordnung:
    """Welches gespeicherte Stück steckt hinter einem Vorkommen aus
    entries_in_range? Termine: Ebene + Tag + Titel + Uhrzeit (Doppel der
    Reihe nach). Routinen: Ebene + Regel, dann Titel/Uhrzeit, sonst die
    Routine, die an dem Tag eine Abweichung hat."""

    def __init__(self, alle):
        self.alle = alle
        self.benutzt = {}

    def stueck(self, e: dict, tag: str):
        # Seit 2026-10-09 tragen die Vorkommen die feste Kennung selbst.
        if e.get("kennung"):
            treffer = [s for s in self.alle if s.uid == e["kennung"]]
            if treffer:
                return treffer[0]
        if e.get("recurring"):
            return self._routine(e, tag)
        anker = e.get("von") if e.get("spanning") else tag
        kand = [s for s in self.alle if s.art == "termin" and s.layer == e.get("layer")
                and s.day == anker and s.label == e.get("label")
                and (e.get("spanning") or (s.time or None) == (e.get("time") or None))]
        if not kand:
            return None
        schl = (tag, kand[0].schluessel())
        n = self.benutzt.get(schl, 0)
        self.benutzt[schl] = n + 1
        return kand[min(n, len(kand) - 1)]

    def _routine(self, e: dict, tag: str):
        kand = [s for s in self.alle if s.art == "routine"
                and s.layer == e.get("layer") and s.rrule == e.get("rrule")]
        genau = [s for s in kand if s.label == e.get("label")
                 and (s.time or None) == (e.get("time") or None)]
        if genau:
            schl = (tag, genau[0].schluessel())
            n = self.benutzt.get(schl, 0)
            self.benutzt[schl] = n + 1
            return genau[min(n, len(genau) - 1)]
        verschoben = [s for s in kand if any(
            isinstance(a, dict) and a.get("tag") == tag
            for a in (s.roh.get("abweichungen") or {}).values())]
        if len(verschoben) == 1:
            return verschoben[0]
        gleich = [s for s in kand if s.label == e.get("label")]
        return gleich[0] if len(gleich) == 1 else None


# ── Belege: nachlesen, was jetzt dasteht ───────────────────────────────

def naechstes(s: Stueck, tage: int = 60) -> str:
    """'nächstes Mal Do 15.10.' — mit Pausen und Absagen gerechnet."""
    heute = date.today()
    try:
        vor = kalender.entries_in_range(heute, heute + timedelta(days=tage), layers=[s.layer])
    except Exception:
        return ""
    for tag, es in vor.items():
        for e in es:
            if (e.get("recurring") and e.get("rrule") == s.rrule and e.get("label") == s.label
                    and not e.get("ausfall") and not e.get("deaktiviert")):
                return f"nächstes Mal {datum(tag, False).rstrip('.')}"
    return f"in den nächsten {tage} Tagen kein Termin"


def beleg_warnungen(label: str) -> str:
    w = warnungen_zu(label)
    if not w:
        return f"Keine Kalender-Warnung nennt '{label}'."
    return "Warnungen dazu jetzt: " + " | ".join(w[:4]) + (" …" if len(w) > 4 else "")


def gleiche(s: Stueck, daten: dict | None = None) -> list:
    """Alle Stücke mit denselben Kerndaten (Doppel eingeschlossen)."""
    return [x for x in stuecke(daten) if x.schluessel() == s.schluessel()]
