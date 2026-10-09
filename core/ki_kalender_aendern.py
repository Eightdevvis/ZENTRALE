# core/ki_kalender_aendern.py
#
# Die schreibenden Kalender-Werkzeuge der KI: eintragen, ändern, löschen,
# pausieren. Lesen, Kennungen, Formate: core/ki_kalender.py.
#
# 2026-10-08, nach Sashas Kalender-Testlauf. Drei Regeln, alle aus einem
# belegten Fehler:
#   1. Ein Name, der MEHRERE Einträge trifft, ändert NICHTS. Vorher änderte
#      edit_calendar_routine alle Treffer („2 Routine(n) geändert"), und die
#      KI wusste nicht, welche.
#   2. Ändern ändert nur die genannten Felder. Vorher reparierte die KI per
#      Löschen + Neuanlegen und verlor dabei Ende und Ort.
#   3. Nichts wird still angenommen. Fehlt das Ende, steht das im Ergebnis —
#      die 18:10–19:00, die sie Sasha meldete, waren nie gespeichert.
#
# 2026-10-09, Sasha: „das programm macht etwas richtig ODER bricht
# KONTROLLIERT KOMPLETT AB mit genauem fehlercode!" Seitdem:
#   - nur zwei Ausgänge: ERLEDIGT — der Satz kommt aus dem nachgelesenen
#     Stand („Kalendereintrag „Geige" am Do 08.10.2026 18:10–19:00 @ Schule
#     EINGETRAGEN (#t3f9c).") — oder ABGEBROCHEN mit Code (core/fehlercodes.py),
#     und dann ist nichts geändert;
#   - geändert, gelöscht, pausiert wird per KENNUNG über den Kalender-Kern
#     (core/kalender_kennung.py): er prüft vorher und schreibt ganz oder gar
#     nicht; seine Ablehnung (KalenderAbgelehnt) kommt als „K-<CODE>" durch;
#   - Neu-Anlegen kann der Kern per Kennung nicht; hier wird nachgelesen und
#     ein Eintrag, der nicht so dasteht wie verlangt, per Kennung wieder
#     gelöscht (W-NICHT-GESPEICHERT).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from datetime import date

import kalender
import kalender_kennung
import kalender_regel
import ki_kalender as kk
import werkzeug_befund
from kalender_kennung import KalenderAbgelehnt
from werkzeug_befund import abgebrochen, erledigt

_OHNE_ENDE = ("Kein Ende angegeben: gespeichert ist nur der Beginn. Die "
              "Kalender-Ansicht zeichnet dafür eine Stunde, Überschneidungen "
              "werden NICHT geprüft. Hat Sasha kein Ende genannt: frag nach, "
              "statt eins zu nennen.")


class _Abbruch(Exception):
    """Ein Abbruch mit Code — gefangen in _sicher."""

    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code, self.grund = code, grund


def _sicher(was: str, nichts: str, arbeit):
    """arbeit() → Befund; jede Ablehnung wird ABGEBROCHEN mit Code."""
    try:
        return arbeit()
    except _Abbruch as e:
        return abgebrochen(was, e.code, e.grund, nichts)
    except KalenderAbgelehnt as e:
        return abgebrochen(was, "K-" + e.code, e.grund, nichts)


def _uhr(feld: str, wert) -> str:
    """'9:05' → '09:05'; leer → ''; Murks → _Abbruch(K-ZEIT-UNGUELTIG)."""
    s = str(wert or "").strip()
    if not s:
        return ""
    try:
        h, m = s.split(":", 1)
        h, m = int(h), int(m)
    except ValueError:
        raise _Abbruch("K-ZEIT-UNGUELTIG", f"{feld} {s!r} ist keine Uhrzeit (HH:MM, 24 h)")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise _Abbruch("K-ZEIT-UNGUELTIG", f"{feld} {s!r} gibt es nicht")
    return f"{h:02d}:{m:02d}"


def _reihenfolge(t: str, e: str) -> None:
    if e and not t:
        raise _Abbruch("K-ENDE-OHNE-BEGINN", f"Ende {e} ohne Beginn — gib 'time' mit an")
    if t and e and e <= t:
        raise _Abbruch("K-ENDE-VOR-BEGINN", f"Ende {e} liegt nicht nach Beginn {t}")


def _tag(feld: str, wert, pflicht: bool = True) -> str:
    s = str(wert or "").strip()
    if not s and not pflicht:
        return ""
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        if not s:
            raise _Abbruch("K-PFLICHTFELD", f"{feld} fehlt (YYYY-MM-DD)")
        raise _Abbruch("K-DATUM-UNGUELTIG", f"{feld} {s!r} ist kein Datum (YYYY-MM-DD)")


def _layer(args: dict, standard="termine") -> str:
    # Seit 07.10.2026 EIN Kalender (Sasha: „ich brauche einen einheitlichen"):
    # ein altes „routinen" wird nach „termine" umgeleitet.
    l = (args.get("layer") or "").strip()
    return standard if l in ("", "routinen") else l


# ── Sätze aus dem echten Stand ─────────────────────────────────────────
# Name, Datum, Uhrzeit, Ort und Kennung kommen aus dem nachgelesenen
# Eintrag (kalender_kennung.eintrag), nie aus den Argumenten.

def _kenn(e: dict) -> str:
    if not kk.mit_kennungen():
        return ""
    return f" (#{kk.kurz_von(e.get('kennung'))})"


def _ort(e: dict) -> str:
    return f" @ {e['ort']}" if e.get("ort") else ""


def termin_satz(e: dict) -> str:
    if e.get("art") == "spanne":
        return (f"Kalendereintrag „{e.get('label')}“ {kk.datum(e.get('von'))} bis "
                f"{kk.datum(e.get('bis'))} (mehrtägig){_ort(e)}")
    return (f"Kalendereintrag „{e.get('label')}“ am {kk.datum(e.get('tag'))} "
            f"{kk.zeit(e.get('time'), e.get('ende'))}{_ort(e)}")


def routine_satz(e: dict) -> str:
    return (f"Routine „{e.get('label')}“ {kk.regel_text(e.get('rrule'), False)} "
            f"{kk.zeit(e.get('time'), e.get('ende'))}{_ort(e)}{kk.zeitraum_von(e)}")


def _versuch_termin(label, tag, t="", e="", ort="") -> str:
    """Wie termin_satz, aber aus dem Verlangten (für Abbrüche vor dem Schreiben)."""
    wann = f" am {kk.datum(tag)}" if tag else ""
    zeit = (f" {t}" + (f"–{e}" if e else "")) if t else ""
    return f"Kalendereintrag „{label}“{wann}{zeit}" + (f" @ {ort}" if ort else "")


def _hinweise(e: dict) -> str:
    teile = []
    if e.get("time") and not e.get("ende"):
        teile.append(_OHNE_ENDE)
    teile.append(kk.beleg_warnungen(e.get("label") or ""))
    return " ".join(teile)


def _zeitraum(args: dict, pflicht: bool, seit_alt: str = "", bis_alt: str = ""):
    """von/bis (YYYY-MM-DD) einer Serie → (von, bis), '' = nicht genannt.
    pflicht: beide müssen da sein (Anlegen auf gross, 2026-10-09). Geprüft
    wird gegen das, was nach der Änderung gilt (alte Werte, wo nichts Neues
    kommt)."""
    roh_von = str(args.get("von") or "").strip()
    roh_bis = str(args.get("bis") or "").strip()
    if pflicht and not (roh_von and roh_bis):
        fehlt = " und ".join(f for f, w in (("von", roh_von), ("bis", roh_bis)) if not w)
        raise _Abbruch("K-ZEITRAUM-FEHLT", f"{fehlt} fehlt — von wann bis wann läuft die Serie?")
    von = _tag("von", roh_von, pflicht=False)
    bis = _tag("bis", roh_bis, pflicht=False)
    a, b = von or seit_alt, bis or bis_alt
    if a and b and b < a:
        raise _Abbruch("K-SPANNE-VERDREHT", f"bis {b} liegt vor von {a}")
    return von, bis


def _ohne_regel_ende(rrule: str) -> None:
    if kk.regel_hat_ende(rrule):
        raise _Abbruch("K-RRULE-MIT-ENDE", f"Regel {rrule!r} enthält UNTIL oder COUNT — "
                       "das Ende der Serie gehört in 'bis'")


def _passt(e: dict, verlangt: dict) -> list:
    """Felder, die nachgelesen anders dastehen als verlangt."""
    return [f"{k} verlangt {v!r}, steht {e.get(k)!r}"
            for k, v in verlangt.items() if (e.get(k) or "") != (v or "")]


def _kennungen() -> set:
    return {x["kennung"] for x in kalender_kennung.alle_eintraege()}


def _neue_kennung(vorher: set, routine: bool) -> str | None:
    neu = [x for x in kalender_kennung.alle_eintraege()
           if x["kennung"] not in vorher and (x["art"] == "routine") == routine]
    return neu[-1]["kennung"] if neu else None


# ── Eintragen ──────────────────────────────────────────────────────────

def termin_eintragen(args: dict):
    """add_calendar_entry. Konflikte sieht Sasha schon in der Ja/Nein-Frage
    (werkzeug_fragen._frage_termin); hier der Satz aus dem echten Stand."""
    layer = (args.get("layer") or "termine").strip() or "termine"
    label = (args.get("label") or "").strip()
    ort = (args.get("ort") or "").strip()

    def arbeit():
        if not label:
            raise _Abbruch("K-TITEL-LEER", "label fehlt")
        tag = _tag("day", args.get("day"))
        t, e = _uhr("time", args.get("time")), _uhr("ende", args.get("ende"))
        _reihenfolge(t, e)
        vorher = _kennungen()
        extras = {k: v for k, v in (("ende", e), ("ort", ort)) if v}
        if not kalender.add_entry(layer=layer, day=tag, label=label, time=t or None, **extras):
            raise _Abbruch("K-EBENE-UNBEKANNT", f"Ebene {layer!r} gibt es nicht")
        k = _neue_kennung(vorher, routine=False)
        if k is None:
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen steht der Eintrag nicht im Kalender")
        x = kalender_kennung.eintrag(k)
        falsch = _passt(x, {"label": label, "tag": tag, "time": t, "ende": e, "ort": ort})
        if falsch:
            kalender_kennung.eintrag_loeschen(k)
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen stand er anders da ("
                           + "; ".join(falsch) + "); wieder gelöscht")
        n = len(kalender.entries_in_range(date.fromisoformat(tag),
                                          date.fromisoformat(tag)).get(tag) or [])
        satz = (f"{termin_satz(x)} EINGETRAGEN{_kenn(x)}. Der Tag hat {n} "
                f"{'Eintrag' if n == 1 else 'Einträge'}.")
        return erledigt(satz, satz, zusatz=_hinweise(x))
    return _sicher(_versuch_termin(label, str(args.get("day") or ""),
                                   str(args.get("time") or ""), str(args.get("ende") or ""), ort),
                   "nichts eingetragen", arbeit)


def routine_eintragen(args: dict):
    """add_calendar_routine — mit Ende und Ort (gross), ohne still eine Dauer
    anzunehmen. Auf gross mit Pflicht-Zeitraum von/bis (2026-10-09): eine
    Serie ohne Ende lief „für immer", auch rückwärts in die Wochen vor ihrem
    Anfang. klein bleibt beim gemessenen Vertrag (ohne von/bis)."""
    layer, label = _layer(args), (args.get("label") or "").strip()
    rrule = (args.get("rrule") or "").strip()
    ort = (args.get("ort") or "").strip()

    def arbeit():
        if not label:
            raise _Abbruch("K-TITEL-LEER", "label fehlt")
        if not rrule:
            raise _Abbruch("K-PFLICHTFELD", "rrule fehlt (z. B. FREQ=WEEKLY;BYDAY=MO)")
        t, e = _uhr("time", args.get("time")), _uhr("ende", args.get("ende"))
        _reihenfolge(t, e)
        if not kalender_regel.regel_gueltig(rrule):
            raise _Abbruch("K-RRULE-UNGUELTIG", f"Regel {rrule!r} ist ungültig")
        regel, von = rrule, ""
        if werkzeug_befund.schiene() == "gross":
            _ohne_regel_ende(rrule)
            von, bis = _zeitraum(args, pflicht=True)
            regel = kk.regel_mit_ende(rrule, bis)
        vorher = _kennungen()
        extras = {k: v for k, v in (("ende", e), ("ort", ort), ("seit", von)) if v}
        if not kalender.add_routine(layer=layer, label=label, rrule_str=regel,
                                    time=t or None, **extras):
            raise _Abbruch("K-EBENE-UNBEKANNT", f"Ebene {layer!r} gibt es nicht")
        k = _neue_kennung(vorher, routine=True)
        if k is None:
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen steht die Routine nicht im Kalender")
        x = kalender_kennung.eintrag(k)
        falsch = _passt(x, {"label": label, "rrule": regel, "time": t, "ende": e, "ort": ort,
                            "seit": von})
        if falsch:
            kalender_kennung.routine_loeschen(k)
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen stand sie anders da ("
                           + "; ".join(falsch) + "); wieder gelöscht")
        satz = f"{routine_satz(x)} EINGETRAGEN{_kenn(x)}, {kk.naechstes(kk.stueck_von(k))}."
        zusatz = _hinweise(x)
        gleich = [y for y in kk.stuecke() if y.art == "routine"
                  and y.label.casefold() == label.casefold()]
        if len(gleich) > 1:
            # Der Geigenstunden-Fall vom 18.08.2026: eine ZWEITE Regel gleichen
            # Namens. Er soll hier auffallen, nicht Sasha drei Tage später.
            zusatz += (f" ACHTUNG: es gibt jetzt {len(gleich)} Routinen namens '{label}': "
                       + "; ".join(kk.beschreiben(y) for y in gleich)
                       + ". Sollte das eine ÄNDERUNG sein? Dann frag Sasha, und lösch "
                         "die alte mit edit_calendar_routine.")
        return erledigt(satz, satz, zusatz=zusatz)
    return _sicher(f"Routine „{label}“ {kk.regel_text(rrule)}".strip(),
                   "nichts eingetragen", arbeit)


def pause_eintragen(args: dict):
    """add_calendar_pause, per Kennung fest an GENAU eine Routine
    (kalender_kennung.routine_pause). Am 08.10. landete „Geigenstunde" neben
    der Routine „Geigenstunde @ Geigenschule" und wirkte auf nichts — seit
    09.10. bricht das ab (K-PAUSE-KEINE-ROUTINE), statt still eine
    wirkungslose Pause zu speichern."""
    label = (args.get("label") or "").strip()

    def arbeit():
        s = _routine_fuer_pause(args, label)
        von = _tag("von", args.get("von"))
        # Ende offen (2026-10-08, Prüfstand f01): eingetragen wird, was
        # feststeht (der Tag `von`), und das Ergebnis sagt, dass das Ende
        # fehlt. Nur gross: klein bleibt beim gemessenen Vertrag.
        offen = (not str(args.get("bis") or "").strip()
                 and werkzeug_befund.schiene() == "gross")
        bis = von if offen else _tag("bis", args.get("bis"))
        if bis < von:
            raise _Abbruch("K-SPANNE-VERDREHT", f"bis {bis} liegt vor von {von}")
        x = kalender_kennung.routine_pause(s.uid, von, bis, args.get("grund") or None)
        name = x.get("label") or ""
        faellt = _ausfaelle(name, von, bis)
        betroffen = ", ".join(faellt) if faellt else "kein Termin im Zeitraum"
        grund = f" ({args['grund']})" if args.get("grund") else ""
        if offen:
            satz = (f"Pause für Routine „{name}“ NUR am {kk.datum(von)}{grund} "
                    f"EINGETRAGEN{_kenn(x)}: betroffen {betroffen}. Ende noch offen — "
                    f"danach steht '{name}' weiter im Kalender.")
            return erledigt(satz, satz, zusatz=(
                "Sag Sasha, dass nur dieser Tag eingetragen ist, und frag, bis wann. "
                "Kommt das Ende: add_calendar_pause noch einmal mit von und bis. "
                + kk.beleg_warnungen(name)))
        satz = (f"Pause für Routine „{name}“ {kk.datum(von, False)}–{kk.datum(bis)}{grund} "
                f"EINGETRAGEN{_kenn(x)}: betroffen {betroffen}.")
        return erledigt(satz, satz, zusatz=kk.beleg_warnungen(name))
    wer = label or "#" + str(args.get("kennung") or "?").lstrip("#")
    return _sicher(f"Pause für „{wer}“", "nichts eingetragen", arbeit)


def _routine_fuer_pause(args: dict, label: str):
    if (args.get("kennung") or "").strip():
        return _ziel(args, "routine")
    if not label:
        raise _Abbruch("K-PFLICHTFELD", "Routine fehlt (label oder kennung)")
    genau = [s for s in kk.stuecke() if s.art == "routine" and s.label == label]
    if len(genau) == 1:
        return genau[0]
    if len(genau) > 1:
        raise _Abbruch("K-MEHRDEUTIG", kk.mehrdeutig(genau, label))
    aehnlich = kk.nach_name(label, "routine")
    vorschlag = ("; in Frage kommt: " + "; ".join(kk.beschreiben(s) for s in aehnlich[:4])
                 if aehnlich else "")
    raise _Abbruch("K-PAUSE-KEINE-ROUTINE",
                   f"keine Routine heißt genau '{label}'{vorschlag}")


def _ausfaelle(label: str, von: str, bis: str) -> list:
    try:
        tage = kalender.entries_in_range(date.fromisoformat(von), date.fromisoformat(bis))
    except Exception:
        return []
    return [kk.datum(t, False) for t, es in tage.items()
            if any(e.get("label") == label and e.get("ausfall") for e in es)]


# ── Ziel finden: Kennung, oder ein Name mit genau EINEM Treffer ─────────

def _ziel(args: dict, art: str):
    """-> Stueck, sonst _Abbruch."""
    if (args.get("kennung") or "").strip():
        s, fehler = kk.finden(args["kennung"])
        if fehler:
            raise _Abbruch("K-KENNUNG-UNBEKANNT", fehler)
        if s.art != art:
            andere = ("edit_calendar_entry / delete_calendar_entry" if s.art == "termin"
                      else "edit_calendar_routine")
            raise _Abbruch("K-FALSCHE-ART", f"#{s.kennung} ist "
                           f"{'eine Routine' if s.art == 'routine' else 'ein Einzeltermin'} "
                           f"— dafür {andere}")
        return s
    label = (args.get("label") or "").strip()
    tag = _tag("day", args.get("day"), pflicht=False) if art == "termin" else ""
    # Termin nur per Name (gross, 2026-10-09, Prüfstand f01): „lösch nyam" —
    # es gab genau einen. Ohne Tag zählen die Termine, die noch nicht vorbei
    # sind; trifft der Name genau einen, ist er gemeint, sonst die Liste.
    ohne_tag = art == "termin" and not tag and werkzeug_befund.schiene() == "gross"
    if not label or (art == "termin" and not tag and not ohne_tag):
        noetig = "kennung, oder day + label" if art == "termin" else "kennung oder label"
        raise _Abbruch("K-PFLICHTFELD", f"{noetig} ist nötig")
    layer = (args.get("layer") or "").strip() or None
    treffer = kk.nach_name(label, art, day=tag or None, layer=layer)
    if ohne_tag:
        heute = date.today().isoformat()
        treffer = [x for x in treffer if str(x.bis or x.day) >= heute]
    if not treffer:
        wo = f" am {tag}" if tag else ""
        raise _Abbruch("K-NICHT-GEFUNDEN", f"kein{'e Routine' if art == 'routine' else ' Termin'} "
                       f"'{label}'{wo}")
    if len(treffer) > 1:
        raise _Abbruch("K-MEHRDEUTIG", kk.mehrdeutig(treffer, label))
    return treffer[0]


# ── Routinen ändern / löschen ──────────────────────────────────────────

def routine_aendern(args: dict):
    """edit_calendar_routine: nur die genannten Felder, nur EINE Routine;
    mit nur_am nur das eine Vorkommen."""
    def arbeit():
        aktion = (args.get("aktion") or "").strip()
        if aktion not in ("aendern", "loeschen"):
            raise _Abbruch("K-AKTION-UNGUELTIG", "aktion muss 'aendern' oder 'loeschen' sein")
        s = _ziel(args, "routine")
        nur_am = _tag("nur_am", args.get("nur_am"), pflicht=False)
        if aktion == "loeschen":
            return _routine_tag_absagen(s, nur_am) if nur_am else _routine_loeschen(s)
        # von/bis (Zeitraum der Serie) nur auf gross, wie beim Anlegen.
        felder = ("time", "ende", "ort", "rrule", "neuer_titel")
        if werkzeug_befund.schiene() == "gross":
            felder += ("von", "bis")
        neu = {k: str(args.get(k) or "").strip() for k in felder}
        neu = {k: v for k, v in neu.items() if v}
        if not neu:
            raise _Abbruch("K-NICHTS-ZU-AENDERN", "gib an, was neu ist")
        t = _uhr("time", neu["time"]) if "time" in neu else (s.time or "")
        e = _uhr("ende", neu["ende"]) if "ende" in neu else (s.ende or "")
        _reihenfolge(t, e)
        if nur_am:
            if "von" in neu or "bis" in neu:
                raise _Abbruch("K-UNBEKANNTES-FELD", "der Zeitraum gilt für die ganze Serie — "
                               "ohne nur_am")
            return _vorkommen_aendern(s, nur_am, neu, t, e)
        return _serie_aendern(s, neu, t, e)
    return _sicher(_was_routine(args), "nichts geändert", arbeit)


def _was_routine(args: dict) -> str:
    wer = (args.get("label") or "").strip() or ("#" + str(args.get("kennung") or "?").lstrip("#"))
    am = f" am {args['nur_am']}" if args.get("nur_am") else ""
    tun = "löschen" if args.get("aktion") == "loeschen" else "ändern"
    return f"Routine „{wer}“{am} {tun}"


def _neue_regel(s, neu: dict) -> tuple:
    """(rrule, seit) nach der Änderung; None = bleibt. Auf gross (nur dort
    gibt es von/bis) behält eine neue Wiederholung das bisherige Ende —
    „nur genannte Felder ändern" gilt auch für den Zeitraum."""
    if "von" not in neu and "bis" not in neu and not (
            "rrule" in neu and werkzeug_befund.schiene() == "gross"):
        return neu.get("rrule"), None
    if "rrule" in neu:
        _ohne_regel_ende(neu["rrule"])
    bis_alt = kk.regel_bis(s.rrule) or ""
    von, bis = _zeitraum(neu, pflicht=False, seit_alt=str(s.roh.get("seit") or ""),
                         bis_alt=bis_alt)
    basis = neu.get("rrule") or s.rrule
    ende = bis or bis_alt
    regel = kk.regel_mit_ende(basis, ende) if ende else basis
    return (regel if regel != s.rrule else None), (von or None)


def _serie_aendern(s, neu: dict, t: str, e: str):
    regel, seit = _neue_regel(s, neu)
    if regel is not None and not kalender_regel.regel_gueltig(regel):
        raise _Abbruch("K-RRULE-UNGUELTIG", f"Regel {regel!r} ist ungültig")
    x = kalender_kennung.routine_aendern(
        s.uid, time=t if "time" in neu else None, ende=e if "ende" in neu else None,
        ort=neu.get("ort"), label=neu.get("neuer_titel"), rrule=regel, seit=seit)
    verlangt = {"time": t, "ende": e}
    for feld, name in (("ort", "ort"), ("neuer_titel", "label")):
        if feld in neu:
            verlangt[name] = neu[feld]
    if regel is not None:
        verlangt["rrule"] = regel
    if seit is not None:
        verlangt["seit"] = seit
    falsch = _passt(x, verlangt)
    if falsch:
        # Der Kern hat geschrieben, aber nicht das Verlangte: zurück auf den
        # alten Stand, per Kennung (2026-10-09) — Zeitraum (seit) inklusive.
        alt = s.roh
        kalender_kennung.routine_aendern(
            s.uid, time=alt.get("time") or "", ende=alt.get("ende") or "",
            ort=alt.get("ort") or "", label=alt.get("label"), rrule=alt.get("rrule"),
            seit=alt.get("seit") or "")
        raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen stand sie anders da ("
                       + "; ".join(falsch) + "); der alte Stand ist wiederhergestellt")
    jetzt = kk.stueck_von(s.uid)
    satz = f"{routine_satz(x)} GEÄNDERT{_kenn(x)}, {kk.naechstes(jetzt)}."
    zusatz = _OHNE_ENDE if x.get("time") and not x.get("ende") else ""
    # Gleichnamige mit Feldern, die diese nicht hat (2026-10-09, f01): wird
    # die andere danach gelöscht, wären sie weg — das soll vorher dastehen.
    andere = [(y, f) for y in kk.stuecke() if y.art == "routine" and y.layer == jetzt.layer
              and y.label.casefold() == jetzt.label.casefold()
              and y.uid != jetzt.uid and (f := _was_fehlt(y, jetzt))]
    if andere:
        zusatz += (" Die gleichnamige " + "; ".join(f"{_kurz(y)} hat {', '.join(f)}"
                                                    for y, f in andere)
                   + " — löschst du sie, ist das weg. Erst übernehmen oder Sasha fragen.")
    zusatz += " " + kk.beleg_warnungen(x.get("label") or "")
    return erledigt(satz, satz, zusatz=zusatz.strip())


def _vorkommen_aendern(s, tag: str, neu: dict, t: str, e: str):
    if "rrule" in neu:
        raise _Abbruch("K-UNBEKANNTES-FELD", "die Wiederholung gilt für die ganze Serie — "
                       "ohne nur_am")
    felder = {}
    if "time" in neu:
        felder["time"] = t
    if "ende" in neu:
        felder["ende"] = e
    if neu.get("ort"):
        felder["ort"] = neu["ort"]
    if neu.get("neuer_titel"):
        felder["label"] = neu["neuer_titel"]
    x = kalender_kennung.routine_tag_aendern(s.uid, tag, **felder)
    abw = next((a for a in (x.get("abweichungen") or {}).values()
                if isinstance(a, dict) and a.get("tag") == tag), {})
    zeit_ = abw.get("time") or x.get("time")
    ende_ = abw.get("ende") or (None if "time" in abw else x.get("ende"))
    label = abw.get("label") or x.get("label")
    ort = abw.get("ort") or x.get("ort")
    satz = (f"Routine „{x.get('label')}“ NUR am {kk.datum(tag)} GEÄNDERT{_kenn(x)}: jetzt "
            f"{kk.zeit(zeit_, ende_)} {label}" + (f" @ {ort}" if ort else "")
            + "; die übrigen Termine der Serie bleiben.")
    return erledigt(satz, satz)


def _routine_tag_absagen(s, tag: str):
    x = kalender_kennung.routine_absagen(s.uid, tag, an=False)
    if tag not in (x.get("aus") or []):
        raise _Abbruch("W-NICHT-GESPEICHERT", f"nachgelesen ist der {tag} nicht abgesagt")
    satz = (f"Routine „{x.get('label')}“ NUR am {kk.datum(tag)} ABGESAGT{_kenn(x)}; die "
            f"Serie bleibt ({kk.naechstes(kk.stueck_von(s.uid))}).")
    return erledigt(satz, satz)


def _routine_loeschen(s):
    vorher = kalender_kennung.eintrag(s.uid)
    kalender_kennung.routine_loeschen(s.uid)
    if s.uid in _kennungen():
        raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen steht die Routine noch da")
    rest = [x for x in kk.stuecke() if x.art == "routine"
            and x.label.casefold() == s.label.casefold()]
    satz = (f"{routine_satz(vorher)} GELÖSCHT. Nachgelesen: "
            + (f"es gibt noch {len(rest)} Routine(n) mit dem Titel: "
               + "; ".join(kk.beschreiben(x) for x in rest) if rest
               else f"keine Routine '{s.label}' mehr."))
    verlust = [f"{_kurz(x)}: {', '.join(f)}" for x in rest if (f := _was_fehlt(s, x))]
    zusatz = ""
    if verlust:
        zusatz = (f"ACHTUNG, mit der gelöschten ging verloren — {'; '.join(verlust)}. "
                  f"Soll die verbliebene das übernehmen? Sag es Sasha (oder "
                  f"edit_calendar_routine an der verbliebenen).")
    return erledigt(satz, satz, zusatz=zusatz)


def _was_fehlt(weg, bleibt) -> list:
    """Was `weg` hatte und die gleichnamige `bleibt` nicht (2026-10-09,
    Prüfstand f01): zwei Geigen-Regeln, nur eine mit Ort. Die KI löschte die
    mit Ort und änderte die andere — der Ort war still weg, und kein Ergebnis
    hatte es gesagt. Uhrzeit und Wiederholung zählen nicht: die ändert man
    ja gerade."""
    raus = []
    if weg.ort and weg.ort != bleibt.ort:
        raus.append(f"Ort '{weg.ort}' (sie hat {repr(bleibt.ort) if bleibt.ort else 'keinen'})")
    if weg.ende and not bleibt.ende:
        raus.append(f"ein Ende (die gelöschte endete {weg.ende}, sie hat keins)")
    return raus


def _kurz(s) -> str:
    kenn = f"#{s.kennung} " if kk.mit_kennungen() else ""
    return f"{kenn}{s.label} {kk.regel_text(s.rrule)} {kk.zeit(s.time, s.ende)}".strip()


# ── Einzeltermine ändern / löschen ─────────────────────────────────────

def termin_loeschen(args: dict):
    """delete_calendar_entry: GENAU ein Termin (Kennung, oder Tag + Name mit
    einem Treffer). Mehrtägige werden ganz gelöscht — das steht im Satz."""
    def arbeit():
        s = _ziel(args, "termin")
        vorher = kalender_kennung.eintrag(s.uid)
        kalender_kennung.eintrag_loeschen(s.uid)
        if s.uid in _kennungen():
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen steht der Termin noch da")
        n = len(kalender.entries_in_range(date.fromisoformat(s.day),
                                          date.fromisoformat(s.day)).get(s.day) or [])
        ganz = " (mehrtägig — ganz gelöscht)" if s.bis else ""
        satz = (f"{termin_satz(vorher)} GELÖSCHT{ganz}. Nachgelesen: weg; am "
                f"{kk.datum(s.day)} stehen jetzt {n} Einträge.")
        return erledigt(satz, satz)
    wer = (args.get("label") or "").strip() or "#" + str(args.get("kennung") or "?").lstrip("#")
    return _sicher(f"Kalendereintrag „{wer}“ löschen", "nichts gelöscht", arbeit)


def termin_aendern(args: dict):
    """edit_calendar_entry: einen Einzeltermin ändern, nur genannte Felder."""
    def arbeit():
        s = _ziel(args, "termin")
        neu_tag = _tag("neuer_tag", args.get("neuer_tag"), pflicht=False)
        felder = {k: str(args.get(k) or "").strip()
                  for k in ("time", "ende", "ort", "neuer_titel", "bis")}
        felder = {k: v for k, v in felder.items() if v}
        if not felder and not neu_tag:
            raise _Abbruch("K-NICHTS-ZU-AENDERN", "gib an, was neu ist")
        if s.bis:
            return _spanne_aendern(s, felder, neu_tag)
        if "bis" in felder:
            raise _Abbruch("K-UNBEKANNTES-FELD", "'bis' gibt es nur bei mehrtägigen Terminen")
        t = _uhr("time", felder["time"]) if "time" in felder else (s.time or "")
        e = _uhr("ende", felder["ende"]) if "ende" in felder else (s.ende or "")
        _reihenfolge(t, e)
        x = kalender_kennung.eintrag_aendern(
            s.uid, label=felder.get("neuer_titel"), tag=neu_tag or None,
            time=t if "time" in felder else None, ende=e if "ende" in felder else None,
            ort=felder.get("ort"))
        verlangt = {"time": t, "ende": e, "tag": neu_tag or s.day}
        if "ort" in felder:
            verlangt["ort"] = felder["ort"]
        if "neuer_titel" in felder:
            verlangt["label"] = felder["neuer_titel"]
        falsch = _passt(x, verlangt)
        if falsch:
            alt = s.roh
            kalender_kennung.eintrag_aendern(
                s.uid, label=alt.get("label"), tag=s.day, time=alt.get("time") or "",
                ende=alt.get("ende") or "", ort=alt.get("ort") or "")
            raise _Abbruch("W-NICHT-GESPEICHERT", "nachgelesen stand er anders da ("
                           + "; ".join(falsch) + "); der alte Stand ist wiederhergestellt")
        satz = f"{termin_satz(x)} GEÄNDERT{_kenn(x)}."
        return erledigt(satz, satz, zusatz=_hinweise(x))
    wer = (args.get("label") or "").strip() or "#" + str(args.get("kennung") or "?").lstrip("#")
    return _sicher(f"Kalendereintrag „{wer}“ ändern", "nichts geändert", arbeit)


def _spanne_aendern(s, felder: dict, neu_tag: str):
    if "time" in felder or "ende" in felder:
        raise _Abbruch("K-SPANNE-UHRZEIT", "Uhrzeiten einzelner Tage eines mehrtägigen "
                       "Termins ändert dieses Werkzeug nicht — das geht in der Kalender-Ansicht")
    bis = _tag("bis", felder["bis"]) if "bis" in felder else None
    x = kalender_kennung.eintrag_aendern(
        s.uid, label=felder.get("neuer_titel"), ort=felder.get("ort"),
        von=neu_tag or None, bis=bis)
    satz = f"{termin_satz(x)} GEÄNDERT{_kenn(x)}."
    return erledigt(satz, satz, zusatz=kk.beleg_warnungen(x.get("label") or ""))
