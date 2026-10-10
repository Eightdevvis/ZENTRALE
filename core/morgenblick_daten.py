# core/morgenblick_daten.py
#
# Was der Morgenblick weiß: heute + morgen aus dem Kalender, Mail, das
# Gespräch „Erinnerungen", ungelesene Gespräche, Listen, Projekte, die
# Ablage — und die Form des Tages (HEAVY / NORMAL / OPEN), deterministisch
# gerechnet. Ausführlich: memory/werkzeuge/morgenblick.md.
#
# 2026-10-08. Jede Quelle ist EIN Sammler in SAMMLER (Name → Funktion). Eine
# neue Quelle (Sasha: Chat-Dienste wie Slack/Teams später) ist ein Eintrag
# mit @sammler("name") — sonst ändert sich nichts. Ein Sammler, der wirft,
# kostet nur seine Quelle: sammeln() schreibt dann {"fehler": …} hinein.
#
# NUR LESEN, KEIN NETZ: Mail kommt aus dem lokalen Triage-Stand
# (mail.recent liest data/mail_state.json), nie per IMAP. Nichts hier legt
# etwas an — auch das Erinnerungs-Gespräch nicht, wenn es fehlt.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md): weiß nichts von der KI.

from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import ablage
import gespraeche
import kalender
import kalender_rhythmus
import lists
import mail
import projekte

SAMMLER = []                      # [(name, funktion(heute, jetzt) -> dict)]

# Wie weit „kürzlich" zurückreicht. Ungelesenes aus zwei Tagen: es gibt im
# Triage-Stand kein „wartet auf Antwort" (2026-10-08 geprüft) — das ist der
# Rückfall dafür, in der Doku als offen notiert.
MAIL_TAGE = 2
KUERZLICH = timedelta(hours=24)
TEXT_MAX = 200                    # Zeichen je gesammeltem Text (Betreff, Titel …)
JE_LISTE = 8                      # Einträge je Quelle, die an die KI gehen

# Form des Tages (Vorlage „morning", 2026-10-08): HEAVY ab 5 h Terminen
# oder einer Häufung von drei, die ohne Luft aufeinander folgen; OPEN bei
# höchstens einem kurzen Termin.
HEAVY_MINUTEN = 5 * 60
HAEUFUNG = 3
HAEUFUNG_LUFT = 30                # Minuten zwischen Ende und nächstem Start
OPEN_KURZ = 60                    # ein Termin bis hierhin ist „kurz"
OHNE_ENDE = 60                    # angenommene Dauer, wenn kein Ende da ist


def sammler(name):
    """Eine Quelle anmelden. Die Reihenfolge ist die des Anmeldens."""
    def anmelden(f):
        SAMMLER.append((name, f))
        return f
    return anmelden


def _kurz(text, n=TEXT_MAX) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


def _minuten(hhmm):
    try:
        h, m = str(hhmm).split(":")
        h, m = int(h), int(m)
    except (ValueError, AttributeError):
        return None
    return h * 60 + m if 0 <= h <= 24 and 0 <= m < 60 else None


# ── Termine und die Form des Tages ─────────────────────────────────────

def termin(e: dict) -> dict | None:
    """Ein Kalender-Eintrag in der Form, die der Morgenblick braucht —
    oder None, wenn er nicht stattfindet (Ausfall, abgeschaltet)."""
    if e.get("ausfall") or e.get("deaktiviert"):
        return None
    t = {"titel": _kurz(e.get("label"), 120)}
    start = _minuten(e.get("time"))
    if start is None:
        t["ganztags"] = True
        return t
    ende = _minuten(e.get("ende"))
    t["start"] = start
    t["ende"] = ende if ende is not None and ende > start else None
    if e.get("ort"):
        t["ort"] = _kurz(e.get("ort"), 80)
    if e.get("recurring"):
        t["regelmaessig"] = True
    return t


def dauer(t: dict) -> int:
    if t.get("start") is None:
        return 0
    return (t["ende"] - t["start"]) if t.get("ende") else OHNE_ENDE


def _belegt(termine):
    """Minuten, die Termine belegen — Überschneidungen nur einmal gezählt."""
    spannen = sorted((t["start"], t["start"] + dauer(t)) for t in termine
                     if t.get("start") is not None)
    summe, bis = 0, -1
    for a, b in spannen:
        if b <= bis:
            continue
        summe += b - max(a, bis)
        bis = b
    return summe


def _haeufung(termine) -> int:
    """Längste Kette von Terminen, zwischen denen höchstens HAEUFUNG_LUFT
    Minuten liegen."""
    zeitig = sorted((t for t in termine if t.get("start") is not None),
                    key=lambda t: t["start"])
    beste, kette, ende = 0, 0, None
    for t in zeitig:
        s, e = t["start"], t["start"] + dauer(t)
        if ende is not None and s - ende <= HAEUFUNG_LUFT:
            kette, ende = kette + 1, max(ende, e)
        else:
            kette, ende = 1, e
        beste = max(beste, kette)
    return beste


def tagesform(termine) -> str:
    """HEAVY / NORMAL / OPEN aus den Terminen eines Tages. Ganztägige
    Einträge (Geburtstag, Ferien) machen den Tag nicht voller."""
    zeitig = [t for t in termine if t.get("start") is not None]
    if _belegt(zeitig) >= HEAVY_MINUTEN or _haeufung(zeitig) >= HAEUFUNG:
        return "HEAVY"
    if len(zeitig) == 0 or (len(zeitig) == 1 and dauer(zeitig[0]) <= OPEN_KURZ):
        return "OPEN"
    return "NORMAL"


# ── Drei Akte ──────────────────────────────────────────────────────────
# Vormittag bis 12, Nachmittag bis 17, Abend danach. Feste Grenzen statt
# „in drei gleiche Teile": so steht 14 Uhr jeden Morgen an derselben Stelle.
AKT_GRENZEN = (12 * 60, 17 * 60)
TAG_ANFANG = 7 * 60
TAG_ENDE = 22 * 60


def fenster(termine) -> tuple:
    """(anfang, ende) des gezeichneten Tages in Minuten: 7–22 Uhr, weiter,
    wenn ein Termin früher beginnt oder später endet (volle Stunden)."""
    zeitig = [t for t in termine if t.get("start") is not None]
    anfang = min([TAG_ANFANG] + [t["start"] - 30 for t in zeitig])
    ende = max([TAG_ENDE] + [t["start"] + dauer(t) + 30 for t in zeitig])
    anfang = max(0, min(anfang // 60 * 60, AKT_GRENZEN[0] - 60))
    ende = min(24 * 60, max(-(-ende // 60) * 60, AKT_GRENZEN[1] + 60))
    return anfang, ende


def akte(termine) -> list:
    """Die drei Akte: [{von, bis, termine: [Index]}]. Ein Termin gehört zum
    Akt, in dem er beginnt. von/bis: erster Start bis letztes Ende im Akt,
    ohne Termine das Fenster des Akts."""
    anfang, ende = fenster(termine)
    grenzen = [(anfang, AKT_GRENZEN[0]), AKT_GRENZEN, (AKT_GRENZEN[1], ende)]
    raus = []
    for nr, (a, b) in enumerate(grenzen):
        unten = -1 if nr == 0 else a           # vor dem Fenster: erster Akt
        oben = 24 * 60 + 1 if nr == 2 else b   # danach: letzter Akt
        idx = [i for i, t in enumerate(termine)
               if t.get("start") is not None and unten <= t["start"] < oben]
        if idx:
            von = min(termine[i]["start"] for i in idx)
            bis = max(termine[i]["start"] + dauer(termine[i]) for i in idx)
        else:
            von, bis = a, b
        raus.append({"von": von, "bis": bis, "fenster": (a, b), "termine": idx})
    return raus


def uhr(minuten) -> str:
    """540 → '9:00', 1440 → '24:00'."""
    return f"{minuten // 60}:{minuten % 60:02d}"


def ueberschneidungen(termine) -> list:
    """[(i, j)] Indizes von Terminen, die sich echt überschneiden (halboffen:
    18:00–18:00 berührt sich nur)."""
    raus = []
    for i, a in enumerate(termine):
        if a.get("start") is None or not a.get("ende"):
            continue
        for j in range(i + 1, len(termine)):
            b = termine[j]
            if b.get("start") is None or not b.get("ende"):
                continue
            if a["start"] < b["ende"] and b["start"] < a["ende"]:
                raus.append((i, j))
    return raus


# ── Die Sammler ────────────────────────────────────────────────────────

@sammler("kalender")
def _kalender(heute, jetzt):
    tage = kalender.entries_in_range(heute, heute + timedelta(days=1))
    def tag(d):
        # Der Tagesrhythmus (Ebene rhythmus) ist kein Termin des Tages.
        ts = [termin(e) for e in tage.get(d.isoformat(), [])
              if e.get("layer") != kalender_rhythmus.EBENE]
        ts = [t for t in ts if t]
        ts.sort(key=lambda t: (t.get("start") is not None, t.get("start") or 0))
        return ts
    h, m = tag(heute), tag(heute + timedelta(days=1))
    return {"heute": h, "morgen": m, "form": tagesform(h),
            "ueberschneidungen": ueberschneidungen(h)}


def _mail_zeit(it):
    """Zeit einer Mail aus dem Triage-Stand (ISO oder RFC-Datum) als aware
    datetime, oder None."""
    for feld in ("date", "seen_at"):
        roh = it.get(feld)
        if not roh:
            continue
        try:
            dt = datetime.fromisoformat(str(roh))
        except ValueError:
            try:
                dt = parsedate_to_datetime(str(roh))
            except (TypeError, ValueError, IndexError):
                continue
        if dt.tzinfo is None:
            dt = dt.astimezone()          # lokale Zeit annehmen
        return dt
    return None


def _mail_kurz(it):
    return {"von": _kurz(it.get("from"), 80), "betreff": _kurz(it.get("subject"), 140),
            "kategorie": _kurz(it.get("category"), 40)}


@sammler("mail")
def _mail(heute, jetzt):
    items = mail.recent(200)
    grenze = jetzt - timedelta(days=MAIL_TAGE)
    ungelesen, je_kat, einsortiert = [], {}, []
    for it in items:
        zeit = _mail_zeit(it)
        if not it.get("seen") and zeit and zeit >= grenze:
            ungelesen.append(it)
            k = str(it.get("category") or "?")
            je_kat[k] = je_kat.get(k, 0) + 1
        try:
            gesehen = datetime.fromisoformat(str(it.get("seen_at"))).astimezone()
        except (TypeError, ValueError):
            gesehen = None
        if it.get("applied") and gesehen and gesehen >= jetzt - KUERZLICH:
            einsortiert.append(it)
    unbekannt = mail.review_stack(20)
    return {"ungelesen_2_tage": [_mail_kurz(i) for i in ungelesen[:JE_LISTE]],
            "ungelesen_anzahl": len(ungelesen),
            "ungelesen_je_kategorie": je_kat,
            "unbekannte_absender": [_mail_kurz(i) for i in unbekannt[:JE_LISTE]],
            "unbekannte_absender_anzahl": len(unbekannt),
            "einsortiert_24h": len(einsortiert),
            # Ehrlich sagen, was es nicht gibt — sonst erfindet die KI es.
            "wartet_auf_antwort": "unbekannt — wird nicht erfasst"}


def _seit(ts, jetzt):
    try:
        dt = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= jetzt - KUERZLICH


@sammler("erinnerungen")
def _erinnerungen(heute, jetzt):
    if not gespraeche.gibt_es(gespraeche.ERINNERUNGEN):
        return {"letzte_24h": []}
    ns = [n for n in gespraeche.nachrichten(gespraeche.ERINNERUNGEN)
          if n.get("rolle") == "assistant" and _seit(n.get("ts"), jetzt)]
    return {"letzte_24h": [_kurz(n.get("text"), 240) for n in ns[-JE_LISTE:]]}


@sammler("gespraeche")
def _gespraeche(heute, jetzt):
    alle = [g for g in gespraeche.liste() if g["id"] != gespraeche.ERINNERUNGEN]
    return {"ungelesene_antwort": [_kurz(g["titel"], 80) for g in alle
                                   if g.get("ungelesen")][:JE_LISTE],
            "aktiv_24h": [_kurz(g["titel"], 80) for g in alle
                          if _seit(g.get("letzte"), jetzt)][:JE_LISTE]}


@sammler("listen")
def _listen(heute, jetzt):
    # Listen-Einträge haben kein Fälligkeitsdatum (2026-10-08 geprüft) —
    # deshalb nur der Wochenvorrat (Kalender-Seitenleiste) und der Fokus.
    woche = lists.week_items()
    offen = [_kurz(i.get("text"), 100) for i in woche.get("items") or []
             if not i.get("done")]
    fokus = lists.get_focus()
    return {"woche_offen": offen[:JE_LISTE], "woche_offen_anzahl": len(offen),
            "fokus": _kurz(fokus.get("name"), 80) if fokus else None}


@sammler("projekte")
def _projekte(heute, jetzt):
    namen = {p["id"]: p["name"] for p in projekte.liste()}
    aktiv = sorted({namen[g["projekt"]] for g in gespraeche.liste()
                    if g.get("projekt") in namen and _seit(g.get("letzte"), jetzt)})
    return {"offen": [_kurz(n, 60) for n in list(namen.values())[:JE_LISTE]],
            "aktiv_24h": [_kurz(n, 60) for n in aktiv[:JE_LISTE]]}


@sammler("ablage")
def _ablage(heute, jetzt):
    neu = [k for k in ablage.liste() if _seit(k.get("erstellt"), jetzt)
           and k.get("herkunft") != "morgenblick"]
    return {"neu_24h": [_kurz(k.get("titel"), 80) for k in neu[:JE_LISTE]]}


def sammeln(heute: date | None = None, jetzt: datetime | None = None) -> dict:
    """Alle Quellen. -> {"datum": iso, "<quelle>": {...} | {"fehler": text}}"""
    jetzt = jetzt or datetime.now().astimezone()
    if jetzt.tzinfo is None:
        jetzt = jetzt.astimezone()
    heute = heute or jetzt.date()
    raus = {"datum": heute.isoformat()}
    for name, f in SAMMLER:
        try:
            raus[name] = f(heute, jetzt)
        except Exception as e:            # eine kaputte Quelle kostet nur sich
            raus[name] = {"fehler": f"{type(e).__name__}: {_kurz(e, 120)}"}
    return raus
