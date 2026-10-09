# core/kalender_bearbeiten.py
#
# Bearbeiten im Kalender, so wie calcurse und der Handy-Kalender es können:
# Wiederholung mit Typ/Intervall/Ende, eine Routine gezielt ändern, „nur
# dieser Tag" (Abweichung), Spannen mit Uhrzeit pro Tag.
#
# Warum ein eigenes Modul: core/kalender.py steht an der Riesen-Grenze
# (1.500 Zeilen, memory/system/bauplan_kern.md). Hier liegen nur die neuen
# Schreibwege; sie laufen über dieselben Speicher-Funktionen und dasselbe
# Lock wie kalender.py, damit es EINEN Kalender gibt — egal welche Ansicht
# (A/B/C) oder ob die KI schreibt.
#
# Datenmodell (unverändert, siehe kalender_ics_abbildung.py):
#   Routine:  {label, rrule, time?, ende?, ort?, seit?, aus?, abweichungen?}
#             abweichungen = {iso_ursprung: {tag, time?, ende?, label?, ort?}}
#   Spanne:   {label, bis, ort?, times?:{iso: HH:MM}, enden?:{iso: HH:MM}}

from datetime import date, datetime, timedelta

import kalender
import kalender_regel
from kalender_fehler import KalenderAbgelehnt


def _nicht_vor(beginn, ende):
    """Seit 09.10.2026 keine stille Korrektur mehr: ein Ende, das nicht nach
    dem Beginn liegt, wird abgelehnt statt still verworfen."""
    if ende and not beginn:
        raise KalenderAbgelehnt("ENDE-OHNE-BEGINN", f"Ende {ende} ohne Beginn-Uhrzeit")
    if beginn and ende and ende <= beginn:
        raise KalenderAbgelehnt("ENDE-VOR-BEGINN", f"Ende {ende} liegt nicht nach Beginn {beginn}")

FREQS = {"t": "DAILY", "w": "WEEKLY", "m": "MONTHLY", "j": "YEARLY",
         "DAILY": "DAILY", "WEEKLY": "WEEKLY", "MONTHLY": "MONTHLY", "YEARLY": "YEARLY"}
WOCHENTAGE = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")


def _iso(s) -> date | None:
    try:
        return date.fromisoformat(s) if isinstance(s, str) else None
    except ValueError:
        return None


def _hhmm(s) -> str | None:
    """'9:5' → '09:05'; Murks → None."""
    if not isinstance(s, str) or ":" not in s:
        return None
    try:
        h, m = s.strip().split(":", 1)
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return "%02d:%02d" % (h, m)


# ── Wiederholungsregel ─────────────────────────────────────────────────
def regel_bauen(freq: str, seit: date, intervall: int = 1,
                bis: date | None = None, wochentage=None) -> str | None:
    """Die RRULE aus den calcurse-Fragen (Typ, „alle wie viele", Ende).

    Monatlich/jährlich hängen am gewählten Tag (BYMONTHDAY/BYMONTH), so wie
    calcurse und der Handy-Kalender es auch tun. Wöchentlich ohne Tage =
    der Wochentag des gewählten Tags. -> None bei Murks."""
    f = FREQS.get((freq or "").strip().upper()) or FREQS.get((freq or "").strip().lower())
    if not f or not isinstance(seit, date):
        return None
    try:
        intervall = max(1, int(intervall or 1))
    except (TypeError, ValueError):
        return None
    teile = ["FREQ=" + f]
    if intervall > 1:
        teile.append("INTERVAL=%d" % intervall)
    if f == "WEEKLY":
        tage = [t.strip().upper() for t in (wochentage or []) if t and t.strip()]
        tage = [t for t in tage if t in WOCHENTAGE] or [WOCHENTAGE[seit.weekday()]]
        teile.append("BYDAY=" + ",".join(sorted(set(tage), key=WOCHENTAGE.index)))
    elif f == "MONTHLY":
        teile.append("BYMONTHDAY=%d" % seit.day)
    elif f == "YEARLY":
        teile.append("BYMONTH=%d;BYMONTHDAY=%d" % (seit.month, seit.day))
    if bis is not None:
        if bis < seit:
            return None
        teile.append("UNTIL=" + bis.strftime("%Y%m%dT235959"))
    regel = ";".join(teile)
    return regel if kalender_regel.regel_gueltig(regel) else None


def routine_neu(layer: str, label: str, seit: str, freq: str, intervall: int = 1,
                bis: str | None = None, wochentage=None, time: str | None = None,
                ende: str | None = None, ort: str | None = None) -> bool:
    """Neue Routine ab `seit` (dem gewählten Tag), wie calcurse „r"."""
    d = _iso(seit)
    regel = regel_bauen(freq, d, intervall, _iso(bis) if bis else None, wochentage)
    if not regel or not (label or "").strip():
        return False
    extras = {"seit": d.isoformat()}
    if ende and _hhmm(ende):
        extras["ende"] = _hhmm(ende)
    if ort:
        extras["ort"] = ort.strip()
    return kalender.add_routine(layer or "termine", label.strip(), regel,
                                time=_hhmm(time) if time else None, **extras)


# ── Eine bestimmte Routine finden ──────────────────────────────────────
def _routine_ziel(lobj: dict, label: str, day: date | None, time: str | None):
    """DIE Routine hinter einem angezeigten Vorkommen: gleiches Label
    (exakt), kommt an `day` vor, bei mehreren gleichnamigen per Uhrzeit.
    Ein Teilstring-Treffer wie bei delete_routine wäre hier gefährlich —
    „Geige" würde „Geigenstunde" mit ändern."""
    needle = (label or "").strip().lower()
    cands = [r for r in lobj.get("routines", [])
             if (r.get("label") or "").strip().lower() == needle]
    if day is not None:
        cands = [r for r in cands if _vorkommen_an(r, day)]
    if time and len(cands) > 1:
        genau = [r for r in cands if (r.get("time") or "") == time]
        cands = genau or cands
    return cands[0] if len(cands) == 1 else None


def _vorkommen_an(r: dict, day: date) -> bool:
    if not r.get("rrule"):
        return False
    try:
        if kalender_regel.vorkommen(r, day, day):
            return True
    except Exception:
        return False
    # Ein schon verschobenes Vorkommen gehört trotzdem zu dieser Routine.
    abw = r.get("abweichungen") if isinstance(r.get("abweichungen"), dict) else {}
    return any(isinstance(a, dict) and a.get("tag") == day.isoformat()
               for a in abw.values())


def _ursprung(r: dict, day: date) -> str:
    """Der Ursprungstag eines Vorkommens (Schlüssel der Abweichungen)."""
    abw = r.get("abweichungen") if isinstance(r.get("abweichungen"), dict) else {}
    for rid, a in abw.items():
        if isinstance(a, dict) and a.get("tag") == day.isoformat():
            return rid
    return day.isoformat()


def routine_bearbeiten(layer: str, label: str, day: str, time: str | None,
                       neu: dict) -> bool:
    """ALLE Vorkommen einer Routine ändern (calcurse „e" bzw. Handy „alle").
    `neu`: label, time, ende, ort (leerer String löscht das Feld) und/oder
    wiederholung = {freq, intervall, bis, wochentage}. Wer die Wiederholung
    ändert, verliert wie bei calcurse die Abweichungen und Aus-Tage."""
    d = _iso(day)
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine")
        if not lobj:
            return False
        r = _routine_ziel(lobj, label, d, _hhmm(time) if time else None)
        if r is None:
            return False
        if (neu.get("label") or "").strip():
            r["label"] = neu["label"].strip()
        for feld in ("time", "ende"):
            if feld in neu:
                v = neu[feld]
                if v in ("", None):
                    if v == "":
                        r.pop(feld, None)
                elif _hhmm(v):
                    r[feld] = _hhmm(v)
                else:
                    return False
        if "ort" in neu:
            if neu["ort"]:
                r["ort"] = neu["ort"].strip()
            else:
                r.pop("ort", None)
        w = neu.get("wiederholung")
        if isinstance(w, dict):
            seit = _iso(r.get("seit")) or d or date.today()
            regel = regel_bauen(w.get("freq"), seit, w.get("intervall", 1),
                                _iso(w.get("bis")) if w.get("bis") else None,
                                w.get("wochentage"))
            if not regel:
                return False
            r["rrule"] = regel
            r["seit"] = seit.isoformat()
            r.pop("aus", None)
            r.pop("abweichungen", None)
        _nicht_vor(r.get("time"), r.get("ende"))
        kalender._save_raw(data)
        return True


def routine_abweichung(layer: str, label: str, day: str, time: str | None,
                       neu: dict) -> bool:
    """NUR dieses Vorkommen ändern (Handy-Kalender: „nur dieser Termin").
    `neu`: tag (verschieben), time, ende, label, ort."""
    d = _iso(day)
    if d is None:
        return False
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine")
        if not lobj:
            return False
        r = _routine_ziel(lobj, label, d, _hhmm(time) if time else None)
        if r is None:
            return False
        rid = _ursprung(r, d)
        abw = r.setdefault("abweichungen", {})
        alt = abw.get(rid) if isinstance(abw.get(rid), dict) else {}
        a = {"tag": alt.get("tag") or d.isoformat()}
        for feld in ("time", "ende", "label", "ort"):
            if alt.get(feld):
                a[feld] = alt[feld]
        if neu.get("tag") and _iso(neu["tag"]):
            a["tag"] = neu["tag"]
        if "time" in neu:
            t = _hhmm(neu["time"]) if neu["time"] else None
            if neu["time"] and not t:
                return False
            if t:
                a["time"] = t
            else:
                a.pop("time", None)
                a.pop("ende", None)
        if "ende" in neu:
            e = _hhmm(neu["ende"]) if neu["ende"] else None
            if e:
                a["ende"] = e
            else:
                a.pop("ende", None)
        for feld in ("label", "ort"):
            if (neu.get(feld) or "").strip():
                a[feld] = neu[feld].strip()
        if "time" not in a and r.get("time") and "ende" in a:
            a["time"] = r["time"]
        _nicht_vor(a.get("time"), a.get("ende"))
        abw[rid] = a
        kalender._save_raw(data)
        return True


# ── Spannen ────────────────────────────────────────────────────────────
def _spanne_ziel(lobj: dict, von: str, label: str):
    needle = (label or "").strip().lower()
    for e in (lobj.get("entries", {}).get(von) or []):
        if isinstance(e, dict) and e.get("bis") and \
                (e.get("label") or "").strip().lower() == needle:
            return e
    return None


def spanne_neu(layer: str, von: str, bis: str, label: str,
               start_zeit: str | None = None, end_zeit: str | None = None,
               tageszeit: tuple | None = None, ort: str | None = None) -> bool:
    """Mehrtägig anlegen.

    - start_zeit/end_zeit: durchgehend, z.B. Fr 18:00 → So 14:00 (calcurse:
      Startzeit + Dauer über Mitternacht).
    - tageszeit=(von, bis): jeden Tag dieselbe Zeit, z.B. Messe 10–18
      (calcurse: Termin + „r" täglich bis …). Einzelne Tage lassen sich
      danach mit spanne_tag anpassen."""
    d0, d1 = _iso(von), _iso(bis)
    if d0 is None or d1 is None or d1 < d0 or not (label or "").strip():
        return False
    # Erst ALLES prüfen, dann schreiben — sonst stünde bei einer Ablehnung
    # die Spanne schon da, nur ohne ihre Zeiten.
    if tageszeit:
        _nicht_vor(_hhmm(tageszeit[0]), _hhmm(tageszeit[1]) if tageszeit[1] else None)
    extras = {"ort": ort.strip()} if ort else {}
    if not kalender.add_span(layer or "termine", von, bis, label.strip(), **extras):
        return False
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine") or {}
        e = _spanne_ziel(lobj, von, label)
        if e is None:
            return True
        times, enden = {}, {}
        if tageszeit:
            a, b = _hhmm(tageszeit[0]), _hhmm(tageszeit[1]) if tageszeit[1] else None
            cur = d0
            while cur <= d1 and a:
                times[cur.isoformat()] = a
                if b:
                    enden[cur.isoformat()] = b
                cur += timedelta(days=1)
        else:
            if start_zeit and _hhmm(start_zeit):
                times[von] = _hhmm(start_zeit)
            if end_zeit and _hhmm(end_zeit):
                # Eine einzelne Uhrzeit am LETZTEN Tag einer Spanne ist ihr
                # Ende („→ 14:00") — so liest es das Modell seit jeher.
                times[bis] = _hhmm(end_zeit)
        if times:
            e["times"] = times
        if enden:
            e["enden"] = enden
        if times or enden:
            kalender._save_raw(data)
        return True


def spanne_tag(layer: str, von: str, label: str, day: str,
               time: str | None, ende: str | None) -> bool:
    """Uhrzeit EINES Tages einer Spanne setzen (leer = an dem Tag ganztägig)."""
    if _iso(day) is None:
        return False
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine") or {}
        e = _spanne_ziel(lobj, von, label)
        if e is None or not (_iso(von) <= _iso(day) <= _iso(e["bis"])):
            return False
        times = e.setdefault("times", {})
        enden = e.setdefault("enden", {})
        t = _hhmm(time) if time else None
        en = _hhmm(ende) if ende else None
        if t:
            times[day] = t
        else:
            times.pop(day, None)
        _nicht_vor(t, en)
        if en:
            enden[day] = en
        else:
            enden.pop(day, None)
        if not times:
            e.pop("times", None)
        if not enden:
            e.pop("enden", None)
        kalender._save_raw(data)
        return True


def spanne_aendern(layer: str, von: str, label: str, neu_label: str | None = None,
                   verschieben: int = 0, neu_bis: str | None = None,
                   ort: str | None = None) -> bool:
    """Alle Tage einer Spanne: Titel, Ort, verschieben (Tage, samt aller
    Tageszeiten) oder neues Ende."""
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine")
        if not lobj:
            return False
        e = _spanne_ziel(lobj, von, label)
        if e is None:
            return False
        if (neu_label or "").strip():
            e["label"] = neu_label.strip()
        if ort is not None:
            if ort.strip():
                e["ort"] = ort.strip()
            else:
                e.pop("ort", None)
        if neu_bis:
            b = _iso(neu_bis)
            if b is None or b < _iso(von):
                return False
            e["bis"] = b.isoformat()
            for feld in ("times", "enden"):
                if isinstance(e.get(feld), dict):
                    e[feld] = {k: v for k, v in e[feld].items() if _iso(k) and _iso(k) <= b}
                    if not e[feld]:
                        e.pop(feld)
        if verschieben:
            schub = timedelta(days=int(verschieben))
            neu_von = (_iso(von) + schub).isoformat()
            e["bis"] = (_iso(e["bis"]) + schub).isoformat()
            for feld in ("times", "enden"):
                if isinstance(e.get(feld), dict):
                    e[feld] = {(_iso(k) + schub).isoformat(): v
                               for k, v in e[feld].items() if _iso(k)}
            liste = lobj["entries"][von]
            liste.remove(e)
            if not liste:
                del lobj["entries"][von]
            lobj["entries"].setdefault(neu_von, []).append(e)
        kalender._save_raw(data)
        return True


# ── Einmal-Termine GENAU treffen ───────────────────────────────────────
# delete_entry (kalender.py) trifft den Titel auch als Teilstring — für die
# KI gewollt („Fake-Termin" trifft „Fake-Termin: Test"), für eine Taste in
# der Ansicht zu grob: „d" auf „Kino" würde „Kino mit Lea" am selben Tag
# mitnehmen. Hier zählt nur der exakte Titel, bei Gleichnamigen die Uhrzeit.
def _eintrag_ziel(lobj: dict, day: str, label: str, time: str | None):
    needle = (label or "").strip().lower()
    liste = lobj.get("entries", {}).get(day) or []
    cands = [e for e in liste if isinstance(e, dict)
             and (e.get("label") or "").strip().lower() == needle]
    if time is not None and len(cands) > 1:
        genau = [e for e in cands if (e.get("time") or "") == (time or "")]
        cands = genau or cands
    return (liste, cands[0]) if cands else (liste, None)


def eintrag_loeschen(layer: str, day: str, label: str, time: str | None = None) -> bool:
    """Genau EINEN Einmal-Termin (oder eine Spanne an ihrem Start-Tag) löschen."""
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine")
        if not lobj:
            return False
        liste, e = _eintrag_ziel(lobj, day, label, _hhmm(time) if time else None)
        if e is None:
            return False
        liste.remove(e)
        if not liste:
            del lobj["entries"][day]
        kalender._save_raw(data)
        return True


def eintrag_aendern(layer: str, day: str, label: str, time: str | None,
                    neu: dict) -> bool:
    """Einen Einmal-Termin ändern; alle anderen Felder bleiben. `neu`: day,
    label, time, ende, ort (leerer String löscht time/ende/ort)."""
    with kalender._lock:
        data = kalender._load_raw()
        lobj = data.get("layers", {}).get(layer or "termine")
        if not lobj:
            return False
        liste, e = _eintrag_ziel(lobj, day, label, _hhmm(time) if time else None)
        if e is None or e.get("bis"):
            return False
        if (neu.get("label") or "").strip():
            e["label"] = neu["label"].strip()
        for feld in ("time", "ende"):
            if feld in neu:
                if neu[feld]:
                    if not _hhmm(neu[feld]):
                        return False
                    e[feld] = _hhmm(neu[feld])
                else:
                    e.pop(feld, None)
        if not e.get("time") and "time" in neu and not neu["time"]:
            e.pop("ende", None)            # ganztägig gemacht: Ende fällt mit weg
        _nicht_vor(e.get("time"), e.get("ende"))
        if "ort" in neu:
            if (neu["ort"] or "").strip():
                e["ort"] = neu["ort"].strip()
            else:
                e.pop("ort", None)
        neu_tag = neu.get("day")
        if neu_tag and neu_tag != day:
            if _iso(neu_tag) is None:
                return False
            liste.remove(e)
            if not liste:
                del lobj["entries"][day]
            lobj["entries"].setdefault(neu_tag, []).append(e)
        kalender._save_raw(data)
        return True
