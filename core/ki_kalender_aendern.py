# core/ki_kalender_aendern.py
#
# Die schreibenden Kalender-Werkzeuge der KI: eintragen, ändern, löschen,
# pausieren — jedes mit Beleg (nach dem Schreiben nachgelesen, was WIRKLICH
# dasteht) und Status (core/werkzeug_befund.py). Lesen, Kennungen, Formate:
# core/ki_kalender.py.
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
# Der Kalender-Kern trifft Einträge teils per Teilstring (routine_aendern,
# routine_loeschen, set_routine_skip). Hier wird VOR jedem solchen Aufruf
# nachgerechnet, ob er genau das gemeinte Stück träfe; sonst lieber nicht
# schreiben und es sagen. Was der Kern dafür noch können müsste: Claude-Web-
# Plan §7, „braucht vom Kalender-Kern".
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from datetime import date, timedelta

import kalender
import kalender_bearbeiten
import kalender_regel
import ki_kalender as kk
from werkzeug_befund import Befund, OK, TEILWEISE, FEHLGESCHLAGEN

_OHNE_ENDE = ("Kein Ende angegeben: gespeichert ist nur der Beginn. Die "
              "Kalender-Ansicht zeichnet dafür eine Stunde, Überschneidungen "
              "werden NICHT geprüft. Hat Sasha kein Ende genannt: frag nach, "
              "statt eins zu nennen.")


def _fehler(text: str) -> Befund:
    return Befund(text, FEHLGESCHLAGEN)


def _uhr(wert, ende: bool = False):
    """'9:05' → '09:05'; leer → ''; Murks → None."""
    s = str(wert or "").strip()
    if not s:
        return ""
    if s == "24:00" and ende:
        return s
    try:
        h, m = s.split(":", 1)
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def _tag(wert):
    try:
        return date.fromisoformat(str(wert or "").strip()).isoformat()
    except ValueError:
        return None


def _zeiten(args: dict):
    """(time, ende) geprüft, oder ein Fehler-Befund."""
    t, e = _uhr(args.get("time")), _uhr(args.get("ende"), ende=True)
    if t is None or e is None:
        return _fehler("[Fehler: Uhrzeiten als HH:MM (24h), z.B. '18:10'.]")
    if e and not t:
        return _fehler("[Fehler: ein Ende ohne Beginn geht nicht — gib 'time' mit an.]")
    if t and e and e <= t:
        return _fehler(f"[Fehler: Ende {e} liegt nicht nach Beginn {t}.]")
    return t, e


def _layer(args: dict, standard="termine") -> str:
    # Seit 07.10.2026 EIN Kalender (Sasha: „ich brauche einen einheitlichen"):
    # ein altes „routinen" wird nach „termine" umgeleitet.
    l = (args.get("layer") or "").strip()
    return standard if l in ("", "routinen") else l


# ── Eintragen ──────────────────────────────────────────────────────────

def termin_eintragen(args: dict) -> Befund:
    """add_calendar_entry. Konflikte sieht Sasha schon in der Ja/Nein-Frage
    (werkzeug_fragen._frage_termin); hier der Beleg."""
    layer = (args.get("layer") or "termine").strip() or "termine"
    tag, label = _tag(args.get("day")), (args.get("label") or "").strip()
    if not tag or not label:
        return _fehler("[Fehler: day (YYYY-MM-DD) und label sind nötig.]")
    zeiten = _zeiten(args)
    if isinstance(zeiten, Befund):
        return zeiten
    t, e = zeiten
    extras = {k: v for k, v in (("ende", e), ("ort", (args.get("ort") or "").strip())) if v}
    if not kalender.add_entry(layer=layer, day=tag, label=label, time=t or None, **extras):
        return _fehler(f"[Fehler: Ebene '{layer}' gibt es nicht oder die Eingabe "
                       f"ist ungültig — nichts eingetragen.]")
    treffer = [s for s in kk.stuecke() if s.art == "termin" and s.layer == layer
               and s.day == tag and s.label == label and (s.time or "") == t]
    if not treffer:
        return _fehler(f"[Eingetragen gemeldet, aber am {tag} steht '{label}' NICHT — "
                       f"sag das, statt einen Erfolg zu melden.]")
    s = treffer[-1]
    n = len(kalender.entries_in_range(date.fromisoformat(tag),
                                      date.fromisoformat(tag)).get(tag) or [])
    beleg = f"Steht jetzt: {kk.beschreiben(s)}. Der Tag hat {n} {'Eintrag' if n == 1 else 'Einträge'}."
    return _mit_hinweisen(beleg, s, t, e)


def _mit_hinweisen(beleg: str, s, t, e) -> Befund:
    teile = [beleg]
    if t and not e:
        teile.append(_OHNE_ENDE)
    teile.append(kk.beleg_warnungen(s.label))
    return Befund(" ".join(teile), OK, beleg=beleg)


def routine_eintragen(args: dict) -> Befund:
    """add_calendar_routine — mit Ende und Ort (gross), ohne still eine Dauer
    anzunehmen."""
    layer, label = _layer(args), (args.get("label") or "").strip()
    rrule = (args.get("rrule") or "").strip()
    if not label or not rrule:
        return _fehler("[Fehler: label und rrule sind nötig.]")
    zeiten = _zeiten(args)
    if isinstance(zeiten, Befund):
        return zeiten
    t, e = zeiten
    extras = {k: v for k, v in (("ende", e), ("ort", (args.get("ort") or "").strip())) if v}
    if not kalender.add_routine(layer=layer, label=label, rrule_str=rrule, time=t or None, **extras):
        return _fehler("[Fehler: Ebene existiert nicht oder die rrule ist ungültig "
                       "— nichts eingetragen.]")
    treffer = [s for s in kk.stuecke() if s.art == "routine" and s.layer == layer
               and s.label == label and s.rrule == rrule and (s.time or "") == t]
    if not treffer:
        return _fehler(f"[Eingetragen gemeldet, aber die Routine '{label}' steht NICHT "
                       f"im Kalender — melde keinen Erfolg.]")
    s = treffer[-1]
    beleg = f"Steht jetzt: {kk.beschreiben(s)}, {kk.naechstes(s)}."
    befund = _mit_hinweisen(beleg, s, t, e)
    gleich = [x for x in kk.stuecke() if x.art == "routine"
              and x.label.casefold() == label.casefold()]
    if len(gleich) > 1:
        # Der Geigenstunden-Fall vom 18.08.2026: eine ZWEITE Regel gleichen
        # Namens. Er soll hier auffallen, nicht Sasha drei Tage später.
        liste = "; ".join(kk.beschreiben(x) for x in gleich)
        return Befund(f"{befund} ACHTUNG: es gibt jetzt {len(gleich)} Routinen "
                      f"namens '{label}': {liste}. Sollte das eine ÄNDERUNG sein? "
                      f"Dann frag Sasha, und lösch die alte mit "
                      f"edit_calendar_routine.", OK, beleg=beleg)
    return befund


def pause_eintragen(args: dict) -> Befund:
    """add_calendar_pause. Eine Pause wirkt nur auf eine Routine mit GENAU
    diesem Titel (kalender._pause_grund) — am 08.10. landete „Geigenstunde"
    neben der Routine „Geigenstunde @ Geigenschule" und wirkte auf nichts."""
    label = (args.get("label") or "").strip()
    if (args.get("kennung") or "").strip():
        s, fehler = kk.finden(args["kennung"])
        if fehler:
            return _fehler(fehler)
        if s.art != "routine":
            return _fehler("[Fehler: Pausen gibt es nur für Routinen; das ist ein "
                           "Einzeltermin.]")
        label = s.label
    von, bis = _tag(args.get("von")), _tag(args.get("bis"))
    if not label or not von or not bis or bis < von:
        return _fehler("[Fehler: Routine (label oder kennung) und von/bis als "
                       "YYYY-MM-DD, bis nicht vor von.]")
    if not kalender.add_pause(label=label, von=von, bis=bis, grund=args.get("grund")):
        return _fehler("[Fehler: ungültige Datumsangabe — nichts eingetragen.]")
    routinen = [s for s in kk.stuecke() if s.art == "routine" and s.label == label]
    if not routinen:
        aehnlich = kk.nach_name(label, "routine")
        vorschlag = ("; in Frage kommt: " + "; ".join(kk.beschreiben(s) for s in aehnlich[:4])
                     if aehnlich else "")
        return Befund(f"Pause '{label}' {kk.datum(von, False)}–{kk.datum(bis)} gespeichert, "
                      f"wirkt aber auf KEINE Routine: keine heißt genau '{label}'"
                      f"{vorschlag}. Sag Sasha das, statt einen Erfolg zu melden.",
                      TEILWEISE, beleg="Pause ohne passende Routine gespeichert.")
    faellt = _ausfaelle(label, von, bis)
    beleg = (f"Pause steht: '{label}' fällt {kk.datum(von, False)}–{kk.datum(bis)} aus"
             + (f" ({args['grund']})" if args.get("grund") else "")
             + f"; betroffen: {', '.join(faellt) if faellt else 'kein Termin im Zeitraum'}.")
    return Befund(beleg + " " + kk.beleg_warnungen(label), OK, beleg=beleg)


def _ausfaelle(label: str, von: str, bis: str) -> list:
    try:
        tage = kalender.entries_in_range(date.fromisoformat(von), date.fromisoformat(bis))
    except Exception:
        return []
    return [kk.datum(t, False) for t, es in tage.items()
            if any(e.get("label") == label and e.get("ausfall") for e in es)]


# ── Ziel finden: Kennung, oder ein Name mit genau EINEM Treffer ─────────

def _ziel(args: dict, art: str):
    """-> (Stueck, None) oder (None, Befund)."""
    if (args.get("kennung") or "").strip():
        s, fehler = kk.finden(args["kennung"])
        if fehler:
            return None, _fehler(fehler)
        if s.art != art:
            andere = ("edit_calendar_entry / delete_calendar_entry" if s.art == "termin"
                      else "edit_calendar_routine")
            return None, _fehler(f"[Fehler: #{s.kennung} ist ein{'e Routine' if s.art == 'routine' else ' Einzeltermin'} "
                                 f"— dafür {andere}. Nichts geändert.]")
        return s, None
    label = (args.get("label") or "").strip()
    tag = _tag(args.get("day")) if art == "termin" else None
    if not label or (art == "termin" and not tag):
        noetig = "kennung, oder day + label" if art == "termin" else "kennung oder label"
        return None, _fehler(f"[Fehler: {noetig} ist nötig.]")
    layer = (args.get("layer") or "").strip() or None
    treffer = kk.nach_name(label, art, day=tag, layer=layer)
    if not treffer:
        wo = f" am {tag}" if tag else ""
        return None, _fehler(f"[Kein{'e Routine' if art == 'routine' else ' Termin'} "
                             f"'{label}'{wo} gefunden — nichts geändert.]")
    if len(treffer) > 1:
        return None, _fehler(kk.mehrdeutig(treffer, label))
    return treffer[0], None


def _vorkommen_tag(s, um: date | None = None):
    """Ein Tag, an dem die Routine vorkommt (für die Kern-Aufrufe, die eine
    Routine über einen Tag eingrenzen)."""
    um = um or date.today()
    try:
        occ = kalender_regel.vorkommen(s.roh, um - timedelta(days=400), um + timedelta(days=400))
    except Exception:
        return None
    return occ[0].date().isoformat() if occ else None


def _findet_statt(r: dict, d: date) -> bool:
    """Hat die Routine an d ein Vorkommen? (wie kalender._routine_hits_day)"""
    try:
        return bool(kalender_regel.vorkommen(r, d, d))
    except Exception:
        return False


def _termin_eindeutig(s) -> bool:
    """Träfe kalender_bearbeiten._eintrag_ziel (genauer Titel, bei mehreren
    die Uhrzeit) genau s — oder ein gleiches Doppel davon?"""
    kand = [x for x in kk.stuecke() if x.art == "termin" and x.layer == s.layer
            and x.day == s.day and x.label.strip().lower() == s.label.strip().lower()]
    if s.time and len(kand) > 1:
        kand = [x for x in kand if (x.time or "") == s.time] or kand
    return bool(kand) and kand[0].schluessel() == s.schluessel()


def _trifft_genau(s, tag: str | None) -> bool:
    """Träfe ein Kern-Aufruf mit Teilstring-Suche (+Tag, +Uhrzeit) genau s?
    Nachgerechnet wie set_routine_skip/delete_routine es tun."""
    nadel = s.label.strip().lower()
    kand = [x for x in kk.stuecke() if x.art == "routine" and x.layer == s.layer
            and nadel in x.label.strip().lower()]
    if tag is not None:
        d = date.fromisoformat(tag)
        kand = [x for x in kand if _findet_statt(x.roh, d)]
        if s.time and any((x.time or "") == s.time for x in kand):
            kand = [x for x in kand if (x.time or "") == s.time]
    return len(kand) == 1 and kand[0].schluessel() == s.schluessel()


_BEDARF = ("Der Kalender-Kern kann diese Routine gerade nicht einzeln treffen "
           "(es gibt gleichnamige). Nichts geändert — sag Sasha, dass das in der "
           "Kalender-Ansicht geht.")


_BEDARF_TERMIN = ("Der Kalender-Kern kann diesen Termin gerade nicht einzeln "
                  "treffen (am selben Tag gibt es einen gleichnamigen). Nichts "
                  "geändert — sag Sasha, dass das in der Kalender-Ansicht geht.")


# ── Routinen ändern / löschen ──────────────────────────────────────────

def routine_aendern(args: dict) -> Befund:
    """edit_calendar_routine: nur die genannten Felder, nur EINE Routine;
    mit nur_am nur das eine Vorkommen."""
    aktion = (args.get("aktion") or "").strip()
    if aktion not in ("aendern", "loeschen"):
        return _fehler("[Fehler: aktion muss 'aendern' oder 'loeschen' sein.]")
    s, fehler = _ziel(args, "routine")
    if fehler:
        return fehler
    nur_am = (args.get("nur_am") or "").strip()
    if nur_am and not _tag(nur_am):
        return _fehler("[Fehler: nur_am als YYYY-MM-DD.]")
    if aktion == "loeschen":
        return _routine_tag_absagen(s, _tag(nur_am)) if nur_am else _routine_loeschen(s)
    neu = {k: (args.get(k) or "").strip() for k in ("time", "ende", "ort", "rrule", "neuer_titel")}
    neu = {k: v for k, v in neu.items() if v}
    if not neu:
        return _fehler("[Fehler: nichts zu ändern — gib an, was neu ist.]")
    t = _uhr(neu.get("time", s.time))
    e = _uhr(neu.get("ende", s.ende), ende=True)
    if t is None or e is None:
        return _fehler("[Fehler: Uhrzeiten als HH:MM (24h).]")
    if t and e and e <= t:
        return _fehler(f"[Fehler: Ende {e} läge nicht nach Beginn {t} — nichts geändert. "
                       f"Gib Beginn und Ende zusammen an.]")
    if nur_am:
        return _vorkommen_aendern(s, _tag(nur_am), neu)
    return _serie_aendern(s, neu)


def _serie_aendern(s, neu: dict) -> Befund:
    if "rrule" in neu:
        if not kalender_regel.regel_gueltig(neu["rrule"]):
            return _fehler("[Fehler: die rrule ist ungültig — nichts geändert.]")
        # routine_aendern trifft per Teilstring: nur wenn das genau diese ist.
        if len(kalender.routine_finden(s.label, s.layer)) != 1:
            return _fehler(f"[{_BEDARF}]")
        felder = {k: neu[k] for k in ("ort", "rrule") if k in neu}
        for k in ("time", "ende"):
            if k in neu:
                felder[k] = _uhr(neu[k], k == "ende")
        n = kalender.routine_aendern(s.label, s.layer,
                                     neues_label=neu.get("neuer_titel"), **felder)
        ok = n == 1
    else:
        felder = {"label": neu.get("neuer_titel")} if neu.get("neuer_titel") else {}
        for k in ("time", "ende"):
            if k in neu:
                felder[k] = _uhr(neu[k], k == "ende")
        if "ort" in neu:
            felder["ort"] = neu["ort"]
        ok = kalender_bearbeiten.routine_bearbeiten(s.layer, s.label, None, s.time, felder)
        if not ok and len(kk.gleiche(s)) > 1:
            return _fehler(f"[Es gibt diese Routine {len(kk.gleiche(s))}-mal genau gleich "
                           f"({kk.beschreiben(s)}). {_BEDARF}]")
    if not ok:
        return _fehler(f"[Nicht geändert: der Kalender hat die Änderung an "
                       f"{kk.beschreiben(s)} abgelehnt.]")
    return _beleg_routine(s, neu)


def _beleg_routine(alt, neu: dict) -> Befund:
    label = neu.get("neuer_titel") or alt.label
    rrule = neu.get("rrule") or alt.rrule
    t = _uhr(neu.get("time", alt.time)) or None
    jetzt = [s for s in kk.stuecke() if s.art == "routine" and s.layer == alt.layer
             and s.label == label and s.rrule == rrule and (s.time or None) == t]
    if not jetzt:
        return _fehler(f"[Geändert gemeldet, aber die Routine '{label}' ist so NICHT "
                       f"zu finden — melde keinen Erfolg, lies nach.]")
    s = jetzt[0]
    abweichung = []
    if "ende" in neu and s.ende != _uhr(neu["ende"], True):
        abweichung.append(f"Ende verlangt {neu['ende']}, steht {s.ende or 'keins'}")
    if "ort" in neu and s.ort != neu["ort"]:
        abweichung.append(f"Ort verlangt {neu['ort']}, steht {s.ort or 'keiner'}")
    beleg = f"Steht jetzt: {kk.beschreiben(s)}, {kk.naechstes(s)}."
    hinweis = (" " + _OHNE_ENDE) if s.time and not s.ende else ""
    if abweichung:
        return Befund(f"{beleg} NICHT wie verlangt: {'; '.join(abweichung)}.{hinweis}",
                      TEILWEISE, beleg=beleg)
    return Befund(f"{beleg}{hinweis} {kk.beleg_warnungen(s.label)}", OK, beleg=beleg)


def _vorkommen_aendern(s, tag: str, neu: dict) -> Befund:
    if "rrule" in neu:
        return _fehler("[Fehler: die Wiederholung gilt für die ganze Serie — ohne nur_am.]")
    if not _findet_statt(s.roh, date.fromisoformat(tag)):
        return _fehler(f"[Fehler: {s.label} findet am {kk.datum(tag)} gar nicht statt.]")
    felder = {k: _uhr(neu[k], k == "ende") for k in ("time", "ende") if k in neu}
    if neu.get("ort"):
        felder["ort"] = neu["ort"]
    if neu.get("neuer_titel"):
        felder["label"] = neu["neuer_titel"]
    if not kalender_bearbeiten.routine_abweichung(s.layer, s.label, tag, s.time, felder):
        return _fehler(f"[Nicht geändert: {kk.beschreiben(s)} ließ sich für den "
                       f"{kk.datum(tag)} nicht einzeln ändern.]")
    tage = kalender.entries_in_range(date.fromisoformat(tag), date.fromisoformat(tag))
    label = felder.get("label") or s.label
    zeit_neu = felder.get("time") or s.time
    da = [e for e in tage.get(tag) or [] if e.get("recurring") and e.get("rrule") == s.rrule
          and e.get("label") == label and (e.get("time") or None) == (zeit_neu or None)]
    if not da:
        return _fehler(f"[Geändert gemeldet, aber am {tag} ist das Vorkommen NICHT zu "
                       f"sehen — melde keinen Erfolg.]")
    e = da[0]
    beleg = (f"Nur am {kk.datum(tag)} steht jetzt: {kk.zeit(e.get('time'), e.get('ende'))} "
             f"{e.get('label')}" + (f" @ {e['ort']}" if e.get("ort") else "")
             + "; die übrigen Termine der Serie bleiben.")
    return Befund(beleg, OK, beleg=beleg)


def _routine_tag_absagen(s, tag: str) -> Befund:
    if not _findet_statt(s.roh, date.fromisoformat(tag)):
        return _fehler(f"[Fehler: {s.label} findet am {kk.datum(tag)} gar nicht statt.]")
    if not _trifft_genau(s, tag):
        return _fehler(f"[{_BEDARF}]")
    kalender.set_routine_skip(s.layer, s.label, tag, off=True, time=s.time)
    tage = kalender.entries_in_range(date.fromisoformat(tag), date.fromisoformat(tag))
    weg = [e for e in tage.get(tag) or [] if e.get("rrule") == s.rrule
           and e.get("label") == s.label and e.get("deaktiviert")]
    if not weg:
        return _fehler(f"[Abgesagt gemeldet, aber am {tag} steht {s.label} weiter "
                       f"an — melde keinen Erfolg.]")
    beleg = (f"Abgesagt nur am {kk.datum(tag)}: {s.label} findet an dem Tag nicht "
             f"statt; die Serie bleibt ({kk.naechstes(s)}).")
    return Befund(beleg, OK, beleg=beleg)


def _routine_loeschen(s) -> Befund:
    vorher = len(kk.gleiche(s))
    if len(kalender.routine_finden(s.label, s.layer)) == 1:
        kalender.routine_loeschen(s.label, s.layer)
    else:
        tag = _vorkommen_tag(s)
        if tag is None or not _trifft_genau(s, tag):
            return _fehler(f"[{_BEDARF}]")
        kalender.delete_routine(s.layer, s.label, day=tag, time=s.time)
    nachher = len(kk.gleiche(s))
    if nachher >= vorher:
        return _fehler(f"[Gelöscht gemeldet, aber {kk.beschreiben(s)} steht noch da "
                       f"— melde keinen Erfolg.]")
    rest = [x for x in kk.stuecke() if x.art == "routine"
            and x.label.casefold() == s.label.casefold()]
    beleg = (f"Gelöscht: {kk.beschreiben(s)}. Nachgelesen: "
             + (f"es gibt noch {len(rest)} Routine(n) mit dem Titel: "
                + "; ".join(kk.beschreiben(x) for x in rest) if rest
                else f"keine Routine '{s.label}' mehr."))
    return Befund(beleg, OK, beleg=beleg)


# ── Einzeltermine ändern / löschen ─────────────────────────────────────

def termin_loeschen(args: dict) -> Befund:
    """delete_calendar_entry: GENAU ein Termin (Kennung, oder Tag + Name mit
    einem Treffer). Mehrtägige werden ganz gelöscht — das steht im Beleg."""
    s, fehler = _ziel(args, "termin")
    if fehler:
        return fehler
    vorher = len(kk.gleiche(s))
    if not _termin_eindeutig(s):
        return _fehler(f"[{_BEDARF_TERMIN}]")
    if not kalender_bearbeiten.eintrag_loeschen(s.layer, s.day, s.label, s.time):
        return _fehler(f"[Nicht gelöscht: {kk.beschreiben(s)} ließ sich nicht löschen.]")
    if len(kk.gleiche(s)) >= vorher:
        return _fehler(f"[Gelöscht gemeldet, aber {kk.beschreiben(s)} steht noch da "
                       f"— melde keinen Erfolg.]")
    n = len(kalender.entries_in_range(date.fromisoformat(s.day),
                                      date.fromisoformat(s.day)).get(s.day) or [])
    ganz = " (mehrtägig — ganz gelöscht)" if s.bis else ""
    beleg = (f"Gelöscht: {kk.beschreiben(s)}{ganz}. Nachgelesen: weg; am "
             f"{kk.datum(s.day)} stehen jetzt {n} Einträge.")
    return Befund(beleg, OK, beleg=beleg)


def termin_aendern(args: dict) -> Befund:
    """edit_calendar_entry: einen Einzeltermin ändern, nur genannte Felder."""
    s, fehler = _ziel(args, "termin")
    if fehler:
        return fehler
    neu_tag = (args.get("neuer_tag") or "").strip()
    if neu_tag and not _tag(neu_tag):
        return _fehler("[Fehler: neuer_tag als YYYY-MM-DD.]")
    felder = {k: (args.get(k) or "").strip() for k in ("time", "ende", "ort", "neuer_titel", "bis")}
    felder = {k: v for k, v in felder.items() if v}
    if not felder and not neu_tag:
        return _fehler("[Fehler: nichts zu ändern — gib an, was neu ist.]")
    if s.bis:
        return _spanne_aendern(s, felder, neu_tag)
    if "bis" in felder:
        return _fehler("[Fehler: 'bis' gibt es nur bei mehrtägigen Terminen.]")
    t = _uhr(felder.get("time", s.time))
    e = _uhr(felder.get("ende", s.ende), ende=True)
    if t is None or e is None:
        return _fehler("[Fehler: Uhrzeiten als HH:MM (24h).]")
    if e and not t:
        return _fehler("[Fehler: ein Ende ohne Beginn geht nicht.]")
    if t and e and e <= t:
        return _fehler(f"[Fehler: Ende {e} läge nicht nach Beginn {t} — nichts geändert.]")
    neu = {}
    if "time" in felder:
        neu["time"] = t
    if "ende" in felder:
        neu["ende"] = e
    if "ort" in felder:
        neu["ort"] = felder["ort"]
    if "neuer_titel" in felder:
        neu["label"] = felder["neuer_titel"]
    if neu_tag:
        neu["day"] = neu_tag
    if not _termin_eindeutig(s):
        return _fehler(f"[{_BEDARF_TERMIN}]")
    if not kalender_bearbeiten.eintrag_aendern(s.layer, s.day, s.label, s.time, neu):
        return _fehler(f"[Nicht geändert: der Kalender hat die Änderung an "
                       f"{kk.beschreiben(s)} abgelehnt.]")
    ziel = dict(day=neu_tag or s.day, label=neu.get("label") or s.label, time=t or None)
    jetzt = [x for x in kk.stuecke() if x.art == "termin" and x.layer == s.layer
             and x.day == ziel["day"] and x.label == ziel["label"] and (x.time or None) == ziel["time"]]
    if not jetzt:
        return _fehler("[Geändert gemeldet, aber der Termin ist so NICHT zu finden — "
                       "melde keinen Erfolg, lies nach.]")
    x = jetzt[0]
    beleg = f"Steht jetzt: {kk.beschreiben(x)}."
    if "ort" in felder and x.ort != felder["ort"]:
        return Befund(f"{beleg} NICHT wie verlangt: Ort steht {x.ort or 'keiner'}.",
                      TEILWEISE, beleg=beleg)
    return _mit_hinweisen(beleg, x, x.time, x.ende)


def _spanne_aendern(s, felder: dict, neu_tag: str) -> Befund:
    if "time" in felder or "ende" in felder:
        return _fehler("[Nicht geändert: Uhrzeiten einzelner Tage eines mehrtägigen "
                       "Termins kann ich nicht ändern — das geht in der Kalender-Ansicht.]")
    schub = (date.fromisoformat(neu_tag) - date.fromisoformat(s.day)).days if neu_tag else 0
    bis = felder.get("bis")
    if bis and not _tag(bis):
        return _fehler("[Fehler: bis als YYYY-MM-DD.]")
    if bis and schub:
        return _fehler("[Fehler: verschieben und neues Ende bitte nacheinander.]")
    if not kalender_bearbeiten.spanne_aendern(s.layer, s.day, s.label,
                                              neu_label=felder.get("neuer_titel"),
                                              verschieben=schub, neu_bis=bis,
                                              ort=felder.get("ort")):
        return _fehler(f"[Nicht geändert: der Kalender hat die Änderung an "
                       f"{kk.beschreiben(s)} abgelehnt.]")
    von = (date.fromisoformat(s.day) + timedelta(days=schub)).isoformat()
    label = felder.get("neuer_titel") or s.label
    jetzt = [x for x in kk.stuecke() if x.art == "termin" and x.layer == s.layer
             and x.day == von and x.label == label and x.bis]
    if not jetzt:
        return _fehler("[Geändert gemeldet, aber der Termin ist so NICHT zu finden — "
                       "melde keinen Erfolg, lies nach.]")
    beleg = f"Steht jetzt: {kk.beschreiben(jetzt[0])}."
    return Befund(f"{beleg} {kk.beleg_warnungen(label)}", OK, beleg=beleg)
