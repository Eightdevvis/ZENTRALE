# core/ki_kalender_adapter.py
#
# Der Adapter des eigenen Kalenders für den Werkzeug-Erzeuger
# (core/werkzeug_erzeuger/; Schemas: core/werkzeug_kalender.py). Er
# übersetzt jede Aktion auf den Kalender-Kern (core/kalender_kennung.py) und
# meldet, was nachgelesen dastehen muss. Nachlesen, Zurücknehmen und die
# feste Satzform macht der Erzeuger — hier steht nur, was der KALENDER weiß.
#
# 2026-10-10. Die Fach-Regeln sind dieselben wie in den handgeschriebenen
# Werkzeugen (core/ki_kalender_aendern.py) und kommen von dort (Ziel finden
# per Kennung oder eindeutigem Namen, Uhrzeit/Datum prüfen, Zeitraum einer
# Serie, Hinweise) — damit beide Wege gleich entscheiden, solange die
# Einstellung `werkzeuge_erzeugt` umschaltbar ist. Ist der erzeugte Weg
# gemessen, fällt der handgeschriebene für gross weg; klein behält ihn.
#
# Sauber im Sinn des Erzeugers: jeder Eintrag über die feste Kennung des
# Kerns, nachlesen per Kennung, Ablehnung mit Code (K-…), nie still.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

from datetime import date

import kalender
import kalender_kategorie
import kalender_kennung
import kalender_quelle
import kalender_regel
import kalender_rhythmus
import ki_kalender as kk
import stil
import ki_kalender_aendern as ka
import werkzeug_fragen
from kalender_kennung import KalenderAbgelehnt
from werkzeug_erzeuger import Ablehnung, Ergebnis


def _text(args: dict, feld: str) -> str:
    return str(args.get(feld) or "").strip()


def _gruppe(args: dict) -> tuple:
    """(kategorie, kategorie_name) wie gespeichert — „keine" als "keine"."""
    k, n = kalender_kategorie.pruefen(args.get("kategorie") or kalender_kategorie.KEINE,
                                      args.get("kategorie_name"))
    return k or kalender_kategorie.KEINE, n


def _gruppe_verlangt(k: str, n) -> dict:
    v = {"kategorie": k}
    if n:
        v["kategorie_name"] = n
    return v


def _quelle(args: dict) -> tuple:
    """(quelle, name) aus quelle_art/quelle_id — geprüft, ob es sie gibt; (None,
    None) ohne. Nur eins von beiden → QUELLE-UNGUELTIG."""
    art, qid = _text(args, "quelle_art"), _text(args, "quelle_id")
    if not art and not qid:
        return None, None
    if not (art and qid):
        raise Ablehnung("K-QUELLE-UNGUELTIG", "quelle_art und quelle_id gehören zusammen")
    return kalender_quelle.pruefen({"art": art, "id": qid})


def _titel(args: dict, name) -> str:
    label = _text(args, "label") or (name or "")
    if not label:
        raise Ablehnung("K-TITEL-LEER", "label fehlt")
    return label


def quelle_satz(x: dict) -> str:
    """' (aus Liste: todo, jetzt: „Steuern planen“)' — aus dem Nachgelesenen."""
    if not x.get("quelle"):
        return ""
    wort = "Projekt" if x["quelle"].get("art") == kalender_quelle.PROJEKT else "Liste"
    name = x.get("quelle_name") or x.get("label")
    zustand = x.get("quelle_zustand")
    if zustand == "fehlt":
        return f" ({wort} {name} gibt es nicht mehr)"
    if zustand == "leer":
        return f" (aus {wort}: {name}, jetzt: alles erledigt)"
    return f" (aus {wort}: {name}, jetzt: „{x.get('titel_live')}“)"


def _ist_phase(s) -> bool:
    return kalender_rhythmus.ist_phase(s.roh, s.layer)


def _vorher(s) -> dict:
    return {"art": s.art, "roh": dict(s.roh), "tag": s.day, "layer": s.layer}


# ── Sätze ───────────────────────────────────────────────────────────────

def phase_satz(e: dict) -> str:
    nacht = kalender_rhythmus.ueber_mitternacht(e.get("time"), e.get("ende"))
    motiv = f" ({e['motiv']})" if e.get("motiv") else ""
    return (f"Phase „{e.get('label')}“{motiv} {kk.regel_text(e.get('rrule'), False)} "
            f"{kk.zeit(e.get('time'), e.get('ende'), nacht)}{kk.zeitraum_von(e)}")


def satz(e: dict) -> str:
    if e.get("art") == "routine":
        return phase_satz(e) if e.get("layer") == kalender_rhythmus.EBENE else ka.routine_satz(e)
    return ka.termin_satz(e)


class KalenderAdapter:
    """Grundaktionen des Kalenders (Schnittstelle: werkzeug_erzeuger/__init__.py)."""

    def ausfuehren(self, name: str, args: dict) -> Ergebnis:
        try:
            return _AKTIONEN[name](args)
        except ka._Abbruch as e:
            raise Ablehnung(e.code, e.grund)
        except KalenderAbgelehnt as e:
            raise Ablehnung(e.code, e.grund)

    def nachlesen(self, kennung: str):
        try:
            return kalender_kennung.eintrag(kennung)
        except KalenderAbgelehnt:
            return None

    def loeschen(self, kennung: str) -> None:
        try:
            kalender_kennung.eintrag_loeschen(kennung)
        except KalenderAbgelehnt as e:
            if e.code != "FALSCHE-ART":
                raise
            kalender_kennung.routine_loeschen(kennung)

    def wiederherstellen(self, kennung: str, vorher: dict) -> None:
        _wiederherstellen(kennung, vorher)

    def beschreiben(self, e: dict) -> str:
        return satz(e)

    def kurz(self, kennung: str) -> str:
        return kk.kurz_von(kennung)

    def ziel(self, kennung: str) -> str:
        """Was eine Kennung meint — Sasha sieht den Eintrag, nicht '#r3f9c'."""
        s, fehler = kk.finden(kennung)
        if fehler:
            return f"#{kennung.lstrip('#')} (gibt es so nicht — dann passiert nichts)"
        if s.art == "routine":
            return (f'"{s.label}" ({kk.regel_text(s.rrule, False)} '
                    f'{kk.zeit(s.time, s.ende)}{kk.zeitraum_von(s.roh)})')
        return f'"{s.label}" am {kk.datum(s.day)} {kk.zeit(s.time, s.ende)}'

    def frage(self, name: str, args: dict):
        return _frage(name, args)

    def was(self, name: str, args: dict) -> str:
        return _was(name, args)


# ── Ja/Nein-Fragen: die bisherigen, ergänzt um die neuen Felder ─────────
# Die handgeschriebenen Fragen (core/werkzeug_fragen.py) prüfen schon
# Konflikte und lösen Kennungen auf; für die neuen Werkzeuge baut der
# Erzeuger die Frage aus den Feldern (None hier).

_FRAGEN = {
    "add_calendar_entry": werkzeug_fragen._frage_termin,
    "add_calendar_routine": werkzeug_fragen._frage_routine,
    "edit_calendar_routine": werkzeug_fragen._frage_routine_aendern,
    "add_calendar_pause": werkzeug_fragen._frage_pause,
    "delete_calendar_entry": werkzeug_fragen._frage_termin_loeschen,
    "edit_calendar_entry": werkzeug_fragen._frage_termin_aendern,
}


def _frage(name: str, args: dict):
    f = _FRAGEN.get(name)
    if f is None:
        return None
    text = f(args)
    extra = []
    gruppe = kalender_kategorie.anzeige({"kategorie": _text(args, "kategorie").lower(),
                                         "kategorie_name": _text(args, "kategorie_name")})
    if gruppe:
        extra.append(f"Gruppe {gruppe}")
    if _text(args, "nur_von") or _text(args, "nur_bis"):
        extra.append(f"nur vom {_text(args, 'nur_von') or '?'} bis {_text(args, 'nur_bis') or '?'}")
    if extra and text.endswith("?"):
        text = text[:-1] + " (" + ", ".join(extra) + ")?"
    return text


def _wer(args: dict) -> str:
    return _text(args, "label") or "#" + (_text(args, "kennung") or "?").lstrip("#")


def _was(name: str, args: dict) -> str:
    if name == "add_calendar_entry":
        return ka._versuch_termin(_text(args, "label"), _text(args, "day"),
                                  _text(args, "time"), _text(args, "ende"), _text(args, "ort"))
    if name == "add_calendar_routine":
        return f"Routine „{_text(args, 'label')}“ {kk.regel_text(_text(args, 'rrule'))}".strip()
    if name == "edit_calendar_routine":
        return ka._was_routine(args)
    if name == "add_calendar_pause":
        return f"Pause für „{_wer(args)}“"
    if name == "delete_calendar_entry":
        return f"Kalendereintrag „{_wer(args)}“ löschen"
    if name == "edit_calendar_entry":
        return f"Kalendereintrag „{_wer(args)}“ ändern"
    if name == "set_calendar_phase":
        return f"Phase „{_text(args, 'label')}“"
    tun = {"edit_calendar_phase": "Phase {} ändern", "delete_calendar_phase": "Phase {} löschen",
           "set_calendar_group": "Gruppe für {} setzen",
           "set_calendar_layer": "Ebene von {} wechseln",
           "set_calendar_style": "Aussehen von {} ändern",
           "set_calendar_source": "Quelle für {} setzen",
           "clear_calendar_source": "Quelle von {} lösen"}.get(name, name + " {}")
    return tun.format(f"„{_wer(args)}“")


# ── Termine ────────────────────────────────────────────────────────────

def termin_eintragen(args: dict) -> Ergebnis:
    layer = _text(args, "layer") or "termine"
    q, name = _quelle(args)
    label, ort = _titel(args, name), _text(args, "ort")
    tag = ka._tag("day", args.get("day"))
    t, e = ka._uhr("time", args.get("time")), ka._uhr("ende", args.get("ende"))
    ka._reihenfolge(t, e)
    k_gruppe, n_gruppe = _gruppe(args)
    vorher = ka._kennungen()
    extras = {k: v for k, v in (("ende", e), ("ort", ort)) if v}
    extras.update(_gruppe_verlangt(k_gruppe, n_gruppe))
    if q:
        extras["quelle"] = q
    if not kalender.add_entry(layer=layer, day=tag, label=label, time=t or None, **extras):
        raise Ablehnung("K-EBENE-UNBEKANNT", f"Ebene {layer!r} gibt es nicht")
    k = ka._neue_kennung(vorher, routine=False)
    if k is None:
        raise Ablehnung("W-NICHT-GESPEICHERT", "nachgelesen steht der Eintrag nicht im Kalender")

    def nachsatz(x):
        n = kk.termine_am(x.get("tag") or tag)
        return f"{quelle_satz(x)}. Der Tag hat {n} {'Eintrag' if n == 1 else 'Einträge'}"
    return Ergebnis(kennung=k, verlangt={"label": label, "tag": tag, "time": t, "ende": e,
                                         "ort": ort, "quelle": q,
                                         **_gruppe_verlangt(k_gruppe, n_gruppe)},
                    nachsatz=nachsatz, zusatz=ka._hinweise)


def termin_aendern(args: dict) -> Ergebnis:
    s = ka._ziel(args, "termin")
    neu_tag = ka._tag("neuer_tag", args.get("neuer_tag"), pflicht=False)
    felder = {k: _text(args, k) for k in ("time", "ende", "ort", "neuer_titel", "bis")}
    felder = {k: v for k, v in felder.items() if v}
    if not felder and not neu_tag:
        raise Ablehnung("K-NICHTS-ZU-AENDERN", "gib an, was neu ist")
    if s.bis:
        if "time" in felder or "ende" in felder:
            raise Ablehnung("K-SPANNE-UHRZEIT", "Uhrzeiten einzelner Tage eines mehrtägigen "
                            "Termins ändert dieses Werkzeug nicht — das geht in der Kalender-Ansicht")
        bis = ka._tag("bis", felder["bis"]) if "bis" in felder else None
        kalender_kennung.eintrag_aendern(s.uid, label=felder.get("neuer_titel"),
                                         ort=felder.get("ort"), von=neu_tag or None, bis=bis)
        return Ergebnis(kennung=s.uid, vorher=_vorher(s),
                        zusatz=lambda x: kk.beleg_warnungen(x.get("label") or ""))
    if "bis" in felder:
        raise Ablehnung("K-UNBEKANNTES-FELD", "'bis' gibt es nur bei mehrtägigen Terminen")
    t = ka._uhr("time", felder["time"]) if "time" in felder else (s.time or "")
    e = ka._uhr("ende", felder["ende"]) if "ende" in felder else (s.ende or "")
    ka._reihenfolge(t, e)
    kalender_kennung.eintrag_aendern(
        s.uid, label=felder.get("neuer_titel"), tag=neu_tag or None,
        time=t if "time" in felder else None, ende=e if "ende" in felder else None,
        ort=felder.get("ort"))
    verlangt = {"time": t, "ende": e, "tag": neu_tag or s.day}
    if "ort" in felder:
        verlangt["ort"] = felder["ort"]
    if "neuer_titel" in felder:
        verlangt["label"] = felder["neuer_titel"]
    return Ergebnis(kennung=s.uid, verlangt=verlangt, vorher=_vorher(s), zusatz=ka._hinweise)


def termin_loeschen(args: dict) -> Ergebnis:
    s = ka._ziel(args, "termin")
    vorher = kalender_kennung.eintrag(s.uid)
    kalender_kennung.eintrag_loeschen(s.uid)
    ganz = " (mehrtägig — ganz gelöscht)" if s.bis else ""
    return Ergebnis(kennung=s.uid, vorher=vorher, nachsatz=lambda x: (
        f"{ganz}. Nachgelesen: weg; am {kk.datum(s.day)} stehen jetzt "
        f"{kk.termine_am(s.day)} Einträge"))


# ── Routinen ───────────────────────────────────────────────────────────

def routine_eintragen(args: dict) -> Ergebnis:
    q, name = _quelle(args)
    layer, label = ka._layer(args), _titel(args, name)
    rrule, ort = _text(args, "rrule"), _text(args, "ort")
    t, e = ka._uhr("time", args.get("time")), ka._uhr("ende", args.get("ende"))
    ka._reihenfolge(t, e)
    if not kalender_regel.regel_gueltig(rrule):
        raise Ablehnung("K-RRULE-UNGUELTIG", f"Regel {rrule!r} ist ungültig")
    ka._ohne_regel_ende(rrule)
    von, bis = ka._zeitraum(args, pflicht=True)
    regel = kk.regel_mit_ende(rrule, bis)
    k_gruppe, n_gruppe = _gruppe(args)
    vorher = ka._kennungen()
    extras = {k: v for k, v in (("ende", e), ("ort", ort), ("seit", von)) if v}
    extras.update(_gruppe_verlangt(k_gruppe, n_gruppe))
    if q:
        extras["quelle"] = q
    if not kalender.add_routine(layer=layer, label=label, rrule_str=regel, time=t or None,
                                **extras):
        raise Ablehnung("K-EBENE-UNBEKANNT", f"Ebene {layer!r} gibt es nicht")
    k = ka._neue_kennung(vorher, routine=True)
    if k is None:
        raise Ablehnung("W-NICHT-GESPEICHERT", "nachgelesen steht die Routine nicht im Kalender")
    return Ergebnis(
        kennung=k, verlangt={"label": label, "rrule": regel, "time": t, "ende": e, "ort": ort,
                             "seit": von, "quelle": q, **_gruppe_verlangt(k_gruppe, n_gruppe)},
        nachsatz=lambda x: f"{quelle_satz(x)}, {kk.naechstes(kk.stueck_von(k))}",
        zusatz=lambda x: _doppelt_hinweis(x, label))


def _doppelt_hinweis(x: dict, label: str) -> str:
    zusatz = ka._hinweise(x)
    gleich = [y for y in kk.stuecke() if y.art == "routine"
              and y.label.casefold() == label.casefold()]
    if len(gleich) > 1:
        # Der Geigenstunden-Fall vom 18.08.2026 (wie ki_kalender_aendern).
        zusatz += (f" ACHTUNG: es gibt jetzt {len(gleich)} Routinen namens '{label}': "
                   + "; ".join(kk.beschreiben(y) for y in gleich)
                   + ". Sollte das eine ÄNDERUNG sein? Dann frag Sasha, und lösch "
                     "die alte mit edit_calendar_routine.")
    return zusatz


def routine_aendern(args: dict) -> Ergebnis:
    s = ka._ziel(args, "routine")
    nur_am = ka._tag("nur_am", args.get("nur_am"), pflicht=False)
    nur = _nur_spanne(args, nur_am)
    if args.get("aktion") == "loeschen":
        if nur:
            raise Ablehnung("K-UNBEKANNTES-FELD", "absagen geht je Tag (nur_am) — für mehrere "
                            "Tage add_calendar_pause")
        return _routine_absagen(s, nur_am) if nur_am else _routine_loeschen(s)
    neu = {k: _text(args, k) for k in ("time", "ende", "ort", "rrule", "neuer_titel", "von", "bis")}
    neu = {k: v for k, v in neu.items() if v}
    if not neu:
        raise Ablehnung("K-NICHTS-ZU-AENDERN", "gib an, was neu ist")
    t = ka._uhr("time", neu["time"]) if "time" in neu else (s.time or "")
    e = ka._uhr("ende", neu["ende"]) if "ende" in neu else (s.ende or "")
    ka._reihenfolge(t, e, ueber_mitternacht=_ist_phase(s))
    if nur_am or nur:
        for feld in ("von", "bis", "rrule"):
            if feld in neu:
                raise Ablehnung("K-UNBEKANNTES-FELD", f"{feld} gilt für die ganze Serie — "
                                "ohne nur_am/nur_von/nur_bis")
        return _tage_aendern(s, nur or (nur_am, nur_am), neu, t, e)
    return _serie_aendern(s, neu, t, e)


def _nur_spanne(args: dict, nur_am: str):
    """(nur_von, nur_bis) oder None; beide oder keins, nicht mit nur_am."""
    von = ka._tag("nur_von", args.get("nur_von"), pflicht=False)
    bis = ka._tag("nur_bis", args.get("nur_bis"), pflicht=False)
    if not von and not bis:
        return None
    if nur_am:
        raise Ablehnung("K-UNBEKANNTES-FELD", "entweder nur_am oder nur_von/nur_bis")
    if not (von and bis):
        raise Ablehnung("K-PFLICHTFELD", "nur_von und nur_bis gehören zusammen")
    return von, bis


def _serie_aendern(s, neu: dict, t: str, e: str) -> Ergebnis:
    regel, seit = ka._neue_regel(s, neu)
    if regel is not None and not kalender_regel.regel_gueltig(regel):
        raise Ablehnung("K-RRULE-UNGUELTIG", f"Regel {regel!r} ist ungültig")
    kalender_kennung.routine_aendern(
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
    return Ergebnis(kennung=s.uid, verlangt=verlangt, vorher=_vorher(s),
                    nachsatz=lambda x: f", {kk.naechstes(kk.stueck_von(s.uid))}",
                    zusatz=lambda x: _serie_hinweise(x, s.uid))


def _serie_hinweise(x: dict, uid: str) -> str:
    jetzt = kk.stueck_von(uid)
    zusatz = ka._OHNE_ENDE if x.get("time") and not x.get("ende") \
        and x.get("layer") != kalender_rhythmus.EBENE else ""
    andere = [(y, f) for y in kk.stuecke() if y.art == "routine" and y.layer == jetzt.layer
              and y.label.casefold() == jetzt.label.casefold()
              and y.uid != jetzt.uid and (f := ka._was_fehlt(y, jetzt))]
    if andere:
        zusatz += (" Die gleichnamige " + "; ".join(f"{ka._kurz(y)} hat {', '.join(f)}"
                                                    for y, f in andere)
                   + " — löschst du sie, ist das weg. Erst übernehmen oder Sasha fragen.")
    if x.get("layer") != kalender_rhythmus.EBENE:
        zusatz += " " + kk.beleg_warnungen(x.get("label") or "")
    return zusatz.strip()


_TAG_FELDER = (("time", "time"), ("ende", "ende"), ("ort", "ort"), ("neuer_titel", "label"))


def _tage_aendern(s, spanne: tuple, neu: dict, t: str, e: str) -> Ergebnis:
    """Nur einzelne Tage (Abweichungen): ein Tag (nur_am) oder eine Spanne
    (nur_von/nur_bis, Kern: routine_zeitraum_aendern)."""
    von, bis = spanne
    felder = {}
    for feld, name in _TAG_FELDER:
        if feld in neu:
            felder[name] = {"time": t, "ende": e}.get(feld, neu[feld])
    if von == bis:
        kalender_kennung.routine_tag_aendern(s.uid, von, **felder)
    else:
        kalender_kennung.routine_zeitraum_aendern(s.uid, von, bis, **felder)

    def pruefe(x):
        tage = [a for a in (x.get("abweichungen") or {}).values()
                if isinstance(a, dict) and von <= str(a.get("tag")) <= bis]
        if not tage:
            return [f"keine Abweichung zwischen {von} und {bis}"]
        return [f"{a.get('tag')}: {f} verlangt {w!r}, steht {(a.get(f) or x.get(f))!r}"
                for a in tage for f, w in felder.items() if (a.get(f) or x.get(f) or "") != w]

    art = "Phase" if _ist_phase(s) else "Routine"
    wann = f"NUR am {kk.datum(von)}" if von == bis else \
        f"NUR vom {kk.datum(von, False)} bis {kk.datum(bis)}"
    return Ergebnis(
        kennung=s.uid, pruefe=pruefe, vorher={**_vorher(s), "tage": (von, bis)},
        subjekt=lambda x: f"{art} „{x.get('label')}“ {wann}",
        nachsatz=lambda x: f": jetzt {_tag_jetzt(x, von)}; die übrigen Tage der Serie bleiben")


def _tag_jetzt(x: dict, tag: str) -> str:
    abw = next((a for a in (x.get("abweichungen") or {}).values()
                if isinstance(a, dict) and a.get("tag") == tag), {})
    zeit_ = abw.get("time") or x.get("time")
    ende_ = abw.get("ende") or (None if "time" in abw else x.get("ende"))
    nacht = x.get("layer") == kalender_rhythmus.EBENE and \
        kalender_rhythmus.ueber_mitternacht(zeit_, ende_)
    ort = abw.get("ort") or x.get("ort")
    return (f"{kk.zeit(zeit_, ende_, nacht)} {abw.get('label') or x.get('label')}"
            + (f" @ {ort}" if ort else ""))


def _routine_absagen(s, tag: str) -> Ergebnis:
    kalender_kennung.routine_absagen(s.uid, tag, an=False)
    return Ergebnis(
        kennung=s.uid, vorher=_vorher(s), verb="ABGESAGT",
        pruefe=lambda x: [] if tag in (x.get("aus") or []) else [f"der {tag} ist nicht abgesagt"],
        subjekt=lambda x: f"Routine „{x.get('label')}“ NUR am {kk.datum(tag)}",
        nachsatz=lambda x: f"; die Serie bleibt ({kk.naechstes(kk.stueck_von(s.uid))})")


def _routine_loeschen(s) -> Ergebnis:
    vorher = kalender_kennung.eintrag(s.uid)
    kalender_kennung.routine_loeschen(s.uid)

    def nachsatz(_x):
        rest = [x for x in kk.stuecke() if x.art == "routine"
                and x.label.casefold() == s.label.casefold()]
        return (". Nachgelesen: " + (f"es gibt noch {len(rest)} Routine(n) mit dem Titel: "
                                     + "; ".join(kk.beschreiben(x) for x in rest) if rest
                                     else f"keine Routine '{s.label}' mehr"))

    def zusatz(_x):
        rest = [x for x in kk.stuecke() if x.art == "routine"
                and x.label.casefold() == s.label.casefold()]
        verlust = [f"{ka._kurz(x)}: {', '.join(f)}" for x in rest if (f := ka._was_fehlt(s, x))]
        if not verlust:
            return ""
        return (f"ACHTUNG, mit der gelöschten ging verloren — {'; '.join(verlust)}. "
                f"Soll die verbliebene das übernehmen? Sag es Sasha (oder "
                f"edit_calendar_routine an der verbliebenen).")
    return Ergebnis(kennung=s.uid, art="loeschen", vorher=vorher, nachsatz=nachsatz, zusatz=zusatz)


def pause_eintragen(args: dict) -> Ergebnis:
    label = _text(args, "label")
    s = ka._routine_fuer_pause(args, label)
    von = ka._tag("von", args.get("von"))
    offen = not _text(args, "bis")
    bis = von if offen else ka._tag("bis", args.get("bis"))
    if bis < von:
        raise Ablehnung("K-SPANNE-VERDREHT", f"bis {bis} liegt vor von {von}")
    kalender_kennung.routine_pause(s.uid, von, bis, _text(args, "grund") or None)
    grund = f" ({_text(args, 'grund')})" if _text(args, "grund") else ""

    def betroffen(x):
        faellt = ka._ausfaelle(x.get("label") or "", von, bis)
        return ", ".join(faellt) if faellt else "kein Termin im Zeitraum"
    if offen:
        return Ergebnis(
            kennung=s.uid, verb="EINGETRAGEN",
            subjekt=lambda x: f"Pause für Routine „{x.get('label')}“ NUR am {kk.datum(von)}{grund}",
            nachsatz=lambda x: (f": betroffen {betroffen(x)}. Ende noch offen — danach steht "
                                f"'{x.get('label')}' weiter im Kalender."),
            zusatz=lambda x: ("Sag Sasha, dass nur dieser Tag eingetragen ist, und frag, bis "
                              "wann. Kommt das Ende: add_calendar_pause noch einmal mit von und "
                              "bis. " + kk.beleg_warnungen(x.get("label") or "")))
    return Ergebnis(
        kennung=s.uid, verb="EINGETRAGEN",
        subjekt=lambda x: (f"Pause für Routine „{x.get('label')}“ {kk.datum(von, False)}–"
                           f"{kk.datum(bis)}{grund}"),
        nachsatz=lambda x: f": betroffen {betroffen(x)}",
        zusatz=lambda x: kk.beleg_warnungen(x.get("label") or ""))


# ── Phasen des Tagesrhythmus ───────────────────────────────────────────

def _phase(args: dict):
    s, fehler = kk.finden(_text(args, "kennung"))
    if fehler:
        raise Ablehnung("K-KENNUNG-UNBEKANNT", fehler)
    if not (s.art == "routine" and _ist_phase(s)):
        raise Ablehnung("K-KEINE-PHASE", f"#{s.kennung} ist keine Phase des Tagesrhythmus — "
                        "dafür edit_calendar_routine / edit_calendar_entry")
    return s


def phase_anlegen(args: dict) -> Ergebnis:
    t, e = ka._uhr("time", args.get("time")), ka._uhr("ende", args.get("ende"))
    ka._reihenfolge(t, e, ueber_mitternacht=True)
    rrule = _text(args, "rrule") or "FREQ=DAILY"
    ka._ohne_regel_ende(rrule)
    von = ka._tag("von", args.get("von"), pflicht=False)
    bis = ka._tag("bis", args.get("bis"), pflicht=False)
    x = kalender_kennung.phase_anlegen(_text(args, "label"), t, motiv=args["motiv"],
                                       ende=e or None, rrule=rrule, von=von or None,
                                       bis=bis or None)
    k = x["kennung"]
    return Ergebnis(kennung=k, verlangt={"label": _text(args, "label"), "time": t, "ende": e,
                                         "motiv": args["motiv"],
                                         "seit": von or date.today().isoformat()},
                    nachsatz=lambda _x: f", {kk.naechstes(kk.stueck_von(k))}")


def phase_aendern(args: dict) -> Ergebnis:
    s = _phase(args)
    nur_am = ka._tag("nur_am", args.get("nur_am"), pflicht=False)
    nur = _nur_spanne(args, nur_am)
    neu = {k: _text(args, k) for k in ("time", "ende", "neuer_titel", "motiv", "rrule", "von", "bis")}
    neu = {k: v for k, v in neu.items() if v}
    if not neu:
        raise Ablehnung("K-NICHTS-ZU-AENDERN", "gib an, was neu ist")
    t = ka._uhr("time", neu["time"]) if "time" in neu else (s.time or "")
    e = ka._uhr("ende", neu["ende"]) if "ende" in neu else (s.ende or "")
    ka._reihenfolge(t, e, ueber_mitternacht=True)
    if nur_am or nur:
        for feld in ("motiv", "rrule", "von", "bis"):
            if feld in neu:
                raise Ablehnung("K-UNBEKANNTES-FELD", f"{feld} gilt für die ganze Phase — "
                                "ohne nur_am/nur_von/nur_bis")
        return _tage_aendern(s, nur or (nur_am, nur_am), neu, t, e)
    felder = {}
    if "time" in neu:
        felder["time"] = t
    if "ende" in neu:
        felder["ende"] = e
    if "neuer_titel" in neu:
        felder["label"] = neu["neuer_titel"]
    if "motiv" in neu:
        felder["motiv"] = neu["motiv"]
    if "rrule" in neu:
        ka._ohne_regel_ende(neu["rrule"])
        felder["rrule"] = neu["rrule"]
    if "von" in neu:
        felder["von"] = ka._tag("von", neu["von"])
    if "bis" in neu:
        felder["bis"] = "" if neu["bis"].lower() == "offen" else ka._tag("bis", neu["bis"])
    kalender_kennung.phase_aendern(s.uid, **felder)
    verlangt = {f: w for f, w in felder.items() if f in ("time", "ende", "label", "motiv")}
    if "von" in felder:
        verlangt["seit"] = felder["von"]
    return Ergebnis(kennung=s.uid, verlangt=verlangt, vorher=_vorher(s),
                    nachsatz=lambda _x: f", {kk.naechstes(kk.stueck_von(s.uid))}")


def phase_loeschen(args: dict) -> Ergebnis:
    s = _phase(args)
    vorher = kalender_kennung.eintrag(s.uid)
    kalender_kennung.phase_loeschen(s.uid)
    return Ergebnis(kennung=s.uid, vorher=vorher, nachsatz=". Nachgelesen: weg")


# ── Gruppe und Ebene ───────────────────────────────────────────────────

def _irgendein(args: dict):
    s, fehler = kk.finden(_text(args, "kennung"))
    if fehler:
        raise Ablehnung("K-KENNUNG-UNBEKANNT", fehler)
    return s


def gruppe_setzen(args: dict) -> Ergebnis:
    s = _irgendein(args)
    k_gruppe, n_gruppe = _gruppe(args)
    kalender_kennung.kategorie_setzen(s.uid, args["kategorie"], args.get("kategorie_name"))
    return Ergebnis(kennung=s.uid, verlangt=_gruppe_verlangt(k_gruppe, n_gruppe),
                    vorher=_vorher(s),
                    nachsatz=lambda x: f": Gruppe jetzt {kalender_kategorie.anzeige(x) or 'keine'}")


def ebene_setzen(args: dict) -> Ergebnis:
    s = _irgendein(args)
    kalender_kennung.ebene_wechseln(s.uid, args["ebene"])
    wie = "vielleicht" if args["ebene"] == kalender_kennung.UNVERBINDLICH else "fest"
    return Ergebnis(kennung=s.uid, verlangt={"layer": args["ebene"]}, vorher=_vorher(s),
                    nachsatz=f": jetzt {wie} ({args['ebene']})")


# Flache Felder des Werkzeugs → CSS-Eigenschaften des Kerns (stil.KASTEN).
_STIL_FELDER = {"rahmen": "border-style", "rahmenfarbe": "border-color",
                "hintergrund": "background-color", "schrift": "color",
                "muster": stil.MUSTER_EIGENSCHAFT}


def stil_setzen(args: dict) -> Ergebnis:
    """Nur die genannten Felder ändern (der Kern ERSETZT den ganzen Stil,
    deshalb wird der alte Stil hier mit den neuen Werten zusammengeführt)."""
    s = _irgendein(args)
    alt = dict((_vorher(s)["roh"].get("stil")) or {})
    if _text(args, "entfernen") == "ja":
        neu = {}
    else:
        neu = dict(alt)
        for feld, css in _STIL_FELDER.items():
            wert = _text(args, feld)
            if wert:
                neu[css] = wert
        if neu == alt:
            raise Ablehnung("STIL-UNGUELTIG", "kein Feld fürs Aussehen genannt")
    kalender_kennung.stil_setzen(s.uid, neu)        # Ablehnung → K-… im Adapter
    soll = kalender_kennung.eintrag(s.uid).get("stil") or {}
    return Ergebnis(kennung=s.uid, vorher=_vorher(s),
                    pruefe=lambda x: [] if (x.get("stil") or {}) == soll and
                    all(soll.get(k) == v for k, v in neu.items()) and (neu or not soll)
                    else [f"Aussehen steht {x.get('stil')!r}, verlangt {neu!r}"],
                    nachsatz=lambda x: ": " + (stil.als_css(x.get("stil")) or "Standard-Aussehen"))


# ── Titel aus Liste/Projekt ────────────────────────────────────────────

def quellen_lesen(args: dict) -> Ergebnis:
    a = kalender_quelle.auswahl()
    zeilen = []
    for wort, schl in (("Listen", "listen"), ("Projekte", "projekte")):
        zeilen.append(f"{wort}:")
        zeilen += [f"  quelle_art={x['art']} quelle_id={x['id']}: {x['name']} — oben: "
                   f"{x['titel']}" + ("" if x["zustand"] == "ok" else f" ({x['zustand']})")
                   for x in a.get(schl) or []] or ["  (keine)"]
    return Ergebnis(text="\n".join(zeilen))


def quelle_setzen(args: dict) -> Ergebnis:
    s = _irgendein(args)
    q, name = _quelle(args)
    label = _text(args, "label") or None
    kalender_kennung.quelle_setzen(s.uid, q["art"], q["id"], label=label)
    return Ergebnis(kennung=s.uid, verlangt={"quelle": q, "label": label or name},
                    vorher=_vorher(s), nachsatz=lambda x: quelle_satz(x))


def quelle_loesen(args: dict) -> Ergebnis:
    s = _irgendein(args)
    kalender_kennung.quelle_loesen(s.uid, titel_uebernehmen=bool(args.get("titel_uebernehmen")))
    return Ergebnis(kennung=s.uid, vorher=_vorher(s),
                    pruefe=lambda x: ["die Quelle steht noch da"] if x.get("quelle") else [],
                    nachsatz=": ohne Quelle")


# ── Zurücknehmen (ganz oder gar nicht) ─────────────────────────────────

def _wiederherstellen(k: str, vorher: dict) -> None:
    """Den alten Stand per Kennung zurückschreiben (vorher aus _vorher)."""
    alt, lname = vorher["roh"], vorher["layer"]
    jetzt = kalender_kennung.eintrag(k)
    if jetzt.get("layer") != lname:
        kalender_kennung.ebene_wechseln(k, lname)
    if (jetzt.get("kategorie"), jetzt.get("kategorie_name")) != \
            (alt.get("kategorie", kalender_kategorie.KEINE), alt.get("kategorie_name")):
        kalender_kennung.kategorie_setzen(k, alt.get("kategorie") or kalender_kategorie.KEINE,
                                          alt.get("kategorie_name"))
    if (jetzt.get("stil") or {}) != (alt.get("stil") or {}):
        kalender_kennung.stil_setzen(k, alt.get("stil") or {})
    if (jetzt.get("quelle") or None) != (alt.get("quelle") or None):
        if alt.get("quelle"):
            kalender_kennung.quelle_setzen(k, alt["quelle"]["art"], alt["quelle"]["id"],
                                           label=alt.get("label"))
        else:
            kalender_kennung.quelle_loesen(k)
    if vorher.get("tage"):
        _tage_zurueck(k, vorher)
        return
    if vorher["art"] == "routine":
        kalender_kennung.routine_aendern(
            k, time=alt.get("time") or "", ende=alt.get("ende") or "",
            ort=alt.get("ort") or "", label=alt.get("label"), rrule=alt.get("rrule"),
            seit=alt.get("seit") or "",
            **({"motiv": alt["motiv"]} if alt.get("motiv") else {}))
    elif not alt.get("bis"):
        kalender_kennung.eintrag_aendern(
            k, label=alt.get("label"), tag=vorher["tag"], time=alt.get("time") or "",
            ende=alt.get("ende") or "", ort=alt.get("ort") or "")


def _tage_zurueck(k: str, vorher: dict) -> None:
    """Abweichungen in der Spanne auf den alten Stand: erst auf die Regel
    zurück, dann die alten Abweichungen dieser Tage wieder setzen."""
    von, bis = vorher["tage"]
    kalender_kennung.routine_zeitraum_aendern(k, von, bis, time="", ende="", ort="")
    for a in (vorher["roh"].get("abweichungen") or {}).values():
        if isinstance(a, dict) and von <= str(a.get("tag")) <= bis:
            felder = {f: a[f] for f in ("time", "ende", "ort", "label") if a.get(f)}
            if felder:
                kalender_kennung.routine_tag_aendern(k, a["tag"], **felder)


_AKTIONEN = {
    "add_calendar_entry": termin_eintragen,
    "edit_calendar_entry": termin_aendern,
    "delete_calendar_entry": termin_loeschen,
    "add_calendar_routine": routine_eintragen,
    "edit_calendar_routine": routine_aendern,
    "add_calendar_pause": pause_eintragen,
    "set_calendar_phase": phase_anlegen,
    "edit_calendar_phase": phase_aendern,
    "delete_calendar_phase": phase_loeschen,
    "set_calendar_group": gruppe_setzen,
    "set_calendar_style": stil_setzen,
    "set_calendar_layer": ebene_setzen,
    "read_calendar_sources": quellen_lesen,
    "set_calendar_source": quelle_setzen,
    "clear_calendar_source": quelle_loesen,
}
