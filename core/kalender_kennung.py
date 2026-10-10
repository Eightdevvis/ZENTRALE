# core/kalender_kennung.py
#
# Termine und Routinen über eine FESTE Kennung lesen und ändern.
#
# Anlass (08.10.2026): die KI sollte „die Geigenstunde" verschieben und traf
# beide gleichnamigen Serien — alle Werkzeuge suchten per Titel. Eine Kennung
# überlebt Umbenennen, neue Uhrzeit und neuen Ort; zwei gleiche Routinen sind
# damit einzeln zu treffen. Wunschliste von ASSISTANT (memory/ki/
# claude_web_plan.md §7), abgestimmt am 09.10.2026.
#
# Regeln:
#   * Kennung = im .ics-Speicher die UID, im alten JSON-Speicher das Feld
#     `uid` (hier beim ersten Zugriff vergeben und gespeichert).
#   * Keine stillen Korrekturen: alles Unpassende wird mit KalenderAbgelehnt
#     abgelehnt — fester `code` (Tabelle CODES) + lesbarer Grund.
#   * Jede Funktion = EIN Schreibvorgang unter dem Kalender-Lock. Geprüft
#     wird vorher; wird abgelehnt, ist nachweislich nichts geschrieben.
#   * Felder: None = unverändert, "" = löschen.

import copy
import uuid
from datetime import date

import kalender
import kalender_kategorie
import kalender_regel
import kalender_rhythmus
from kalender_ics import ohne_interna

# Codes, Fehlerklasse und Zeitprüfung stehen in kalender_fehler.py (unterstes
# Modul, damit kalender.py sie ohne Import-Kreis benutzen kann); hier
# weitergereicht, damit Aufrufer kalender_kennung.CODES/KalenderAbgelehnt sehen.
from kalender_fehler import CODES, KalenderAbgelehnt  # noqa: F401,E402
from kalender_fehler import reihenfolge as _zeiten  # noqa: E402
from kalender_fehler import uhrzeit as _hhmm  # noqa: E402


def _datum(feld, wert) -> date:
    try:
        return date.fromisoformat(wert)
    except (TypeError, ValueError):
        raise KalenderAbgelehnt("DATUM-UNGUELTIG", f"{feld} {wert!r} ist kein Datum (JJJJ-MM-TT)")


def _setze(obj, feld, wert, pruefe=None):
    """None = unverändert, "" = löschen, sonst (geprüft) setzen."""
    if wert is None:
        return
    if wert == "":
        obj.pop(feld, None)
        return
    obj[feld] = pruefe(feld, wert) if pruefe else (wert.strip() if isinstance(wert, str) else wert)


# ── Finden ─────────────────────────────────────────────────────────────
def _alle_objekte(data):
    """(art, layer, ort-im-dict, objekt) für alles Gespeicherte.
    ort = ("entries", tag) oder ("routines", index)."""
    for lname, lobj in (data.get("layers") or {}).items():
        for tag, liste in (lobj.get("entries") or {}).items():
            for e in liste if isinstance(liste, list) else []:
                if isinstance(e, dict):
                    yield ("spanne" if e.get("bis") else "einmal"), lname, ("entries", tag), e
        for i, r in enumerate(lobj.get("routines") or []):
            if isinstance(r, dict):
                yield "routine", lname, ("routines", i), r


def _sicherstellen(data) -> bool:
    """JSON-Speicher: fehlende Kennungen vergeben. -> geändert? (.ics hat
    seine UID schon; dort ändert das nichts.)"""
    geaendert = False
    for _art, _l, _ort, obj in _alle_objekte(data):
        if kalender.kennung(obj) is None and kalender._speicher().art != "ics":
            obj["uid"] = uuid.uuid4().hex
            geaendert = True
    return geaendert


def _finden(data, k, arten=None):
    for art, lname, ort, obj in _alle_objekte(data):
        if kalender.kennung(obj) == k:
            if arten and art not in arten:
                raise KalenderAbgelehnt("FALSCHE-ART",
                                        f"{k} ist ein(e) {art}, erwartet: {' oder '.join(arten)}")
            return art, lname, ort, obj
    raise KalenderAbgelehnt("KENNUNG-UNBEKANNT", f"keine Termin/Routine mit Kennung {k!r}")


def _aussen(art, lname, ort, obj, pausen) -> dict:
    d = ohne_interna(obj)
    d.pop("uid", None)
    d.update({"kennung": kalender.kennung(obj), "art": art, "layer": lname})
    # Gruppe immer nennen (seit 10.10.2026, Wunsch ASSISTANT: belegen
    # „… EINGETRAGEN [uni]"); gespeichert ist „keine" als fehlendes Feld.
    d.setdefault("kategorie", kalender_kategorie.KEINE)
    if art == "einmal":
        d["tag"] = ort[1]
    elif art == "spanne":
        d["von"] = ort[1]
    else:
        import kalender_ics
        eigene = [ohne_interna(p) for p in pausen if kalender_ics.pause_gehoert(p, obj)]
        if eigene:
            d["pausen"] = eigene
    return d


def kennung(eintrag: dict) -> str | None:
    """Die Kennung eines Eintrags — gespeichert oder aus entries_in_range."""
    if isinstance(eintrag, dict) and eintrag.get("kennung"):
        return eintrag["kennung"]
    return kalender.kennung(eintrag)


def alle_eintraege() -> list[dict]:
    """Alle Termine, Spannen und Routinen wie gespeichert, ohne Interna,
    jeweils mit kennung/art/layer (+ tag bzw. von, Routinen mit ihren Pausen)."""
    with kalender._lock:
        data = kalender._load_raw()
        if _sicherstellen(data):
            kalender._save_raw(data)
            data = kalender._load_raw()
    pausen = data.get("pausen") or []
    return [_aussen(a, l, o, obj, pausen) for a, l, o, obj in _alle_objekte(data)]


def eintrag(k: str) -> dict:
    """Ein Eintrag per Kennung (wie in alle_eintraege)."""
    data = kalender._load_raw()
    a, l, o, obj = _finden(data, k)
    return _aussen(a, l, o, obj, data.get("pausen") or [])


# ── Schreiben (alles nach demselben Muster) ────────────────────────────
def _schreiben(k, arbeit, arten=None):
    """Laden, finden, `arbeit(data, art, lname, ort, obj)` ändert das Dict
    (wirft vor jeder Änderung, wenn etwas nicht passt), dann EIN Speichern.
    -> der Eintrag danach (bzw. None, wenn er gelöscht wurde)."""
    with kalender._lock:
        data = kalender._load_raw()
        _sicherstellen(data)
        a, l, o, obj = _finden(data, k, arten)
        weg = arbeit(data, a, l, o, obj)
        kalender._save_raw(data)
        if weg:
            return None
        data = kalender._load_raw()
        a, l, o, obj = _finden(data, k)
        return _aussen(a, l, o, obj, data.get("pausen") or [])


def _aus_liste_nehmen(data, lname, ort, obj):
    lobj = data["layers"][lname]
    if ort[0] == "entries":
        liste = lobj["entries"][ort[1]]
        liste.remove(obj)
        if not liste:
            del lobj["entries"][ort[1]]
    else:
        lobj["routines"].remove(obj)


def eintrag_aendern(k: str, *, label=None, tag=None, time=None, ende=None, ort=None,
                    von=None, bis=None, times=None, enden=None,
                    kategorie=None, kategorie_name=None) -> dict:
    """Einen Einmal-Termin ODER eine Spanne ändern.
    Einmal: label, tag (verschieben), time, ende, ort.
    Spanne: label, ort, von/bis (erster/letzter Tag; die Tageszeiten wandern
    beim Verschieben von `von` mit), times/enden = {tag: "HH:MM"|"" } für
    einzelne Tage ("" = an dem Tag ohne Uhrzeit bzw. ohne Ende).
    kategorie/kategorie_name: Gruppe (kalender_kategorie.pruefen)."""
    def arbeit(data, art, lname, o, obj):
        neu = copy.deepcopy(obj)
        if label is not None:
            if not label.strip():
                raise KalenderAbgelehnt("TITEL-LEER")
            neu["label"] = label.strip()
        _setze(neu, "ort", ort)
        kalender_kategorie.setzen(neu, kategorie, kategorie_name)
        if art == "einmal":
            for name, wert in (("von", von), ("bis", bis), ("times", times), ("enden", enden)):
                if wert is not None:
                    raise KalenderAbgelehnt("UNBEKANNTES-FELD",
                                            f"{name} gibt es nur bei mehrtägigen Terminen")
            _setze(neu, "time", time, _hhmm)
            _setze(neu, "ende", ende, _hhmm)
            _zeiten(neu.get("time"), neu.get("ende"),
                    ueber_mitternacht=kalender_rhythmus.ist_phase(neu, lname))
            neuer_tag = _datum("tag", tag).isoformat() if tag else o[1]
        else:
            for name, wert in (("tag", tag), ("time", time), ("ende", ende)):
                if wert is not None:
                    raise KalenderAbgelehnt("UNBEKANNTES-FELD",
                                            f"{name} gibt es bei Spannen nur je Tag (times/enden)")
            alt_von = _datum("von", o[1])
            neu_von = _datum("von", von) if von else alt_von
            schub = neu_von - alt_von
            alt_bis = _datum("bis", obj["bis"])
            neu_bis = _datum("bis", bis) if bis else alt_bis + schub
            if neu_bis < neu_von:
                raise KalenderAbgelehnt("SPANNE-VERDREHT",
                                        f"letzter Tag {neu_bis} liegt vor dem ersten {neu_von}")
            for feld in ("times", "enden"):
                alt = neu.get(feld) if isinstance(neu.get(feld), dict) else {}
                verschoben = {}
                for t, w in alt.items():
                    try:
                        verschoben[(date.fromisoformat(t) + schub).isoformat()] = w
                    except ValueError:
                        continue
                neu[feld] = verschoben
            for feld, aenderung in (("times", times), ("enden", enden)):
                for t, w in (aenderung or {}).items():
                    d = _datum(feld, t)
                    if not neu_von <= d <= neu_bis:
                        raise KalenderAbgelehnt("TAG-AUSSERHALB",
                                                f"{t} liegt nicht in {neu_von}…{neu_bis}")
                    if w:
                        neu[feld][d.isoformat()] = _hhmm(feld, w)
                    else:
                        neu[feld].pop(d.isoformat(), None)
            for feld in ("times", "enden"):
                neu[feld] = {t: w for t, w in neu[feld].items()
                             if neu_von <= date.fromisoformat(t) <= neu_bis}
                if not neu[feld]:
                    neu.pop(feld)
            for t, e in (neu.get("enden") or {}).items():
                _zeiten((neu.get("times") or {}).get(t), e)
            neu["bis"] = neu_bis.isoformat()
            neuer_tag = neu_von.isoformat()
        # alles geprüft → erst jetzt am Dict ändern
        obj.clear()
        obj.update(neu)
        if neuer_tag != o[1]:
            lobj = data["layers"][lname]
            liste = lobj["entries"][o[1]]
            liste.remove(obj)
            if not liste:
                del lobj["entries"][o[1]]
            lobj["entries"].setdefault(neuer_tag, []).append(obj)
        return False
    return _schreiben(k, arbeit, ("einmal", "spanne"))


def eintrag_loeschen(k: str) -> None:
    """Einen Einmal-Termin oder eine Spanne löschen (genau diesen)."""
    def arbeit(data, art, lname, o, obj):
        _aus_liste_nehmen(data, lname, o, obj)
        return True
    _schreiben(k, arbeit, ("einmal", "spanne"))


def routine_aendern(k: str, *, time=None, ende=None, ort=None, label=None,
                    rrule=None, seit=None, bis=None, motiv=None,
                    kategorie=None, kategorie_name=None, nur_phase=False) -> dict:
    """ALLE Vorkommen einer Routine. rrule als Text (wird geprüft); wer die
    Regel ändert, behält Aus-Tage und Abweichungen (sie gelten weiter für
    die Tage, die es noch gibt). Pausen hängen an der Kennung — Umbenennen
    nimmt sie mit. `bis`: letzter Tag (UNTIL der Regel), "" = bis auf
    Weiteres. `motiv` nur bei Phasen (Ebene rhythmus; dort darf das Ende vor
    dem Beginn liegen = am Folgetag). `nur_phase`: ablehnen, wenn es keine
    Phase ist (phase_aendern)."""
    def arbeit(data, art, lname, o, obj):
        phase = kalender_rhythmus.ist_phase(obj, lname)
        if (nur_phase or motiv is not None) and not phase:
            raise KalenderAbgelehnt("KEINE-PHASE", f"{k} liegt in der Ebene {lname!r}")
        neu = copy.deepcopy(obj)
        if motiv is not None:
            neu["motiv"] = kalender_rhythmus.motiv_pruefen(motiv)
        kalender_kategorie.setzen(neu, kategorie, kategorie_name)
        if label is not None:
            if not label.strip():
                raise KalenderAbgelehnt("TITEL-LEER")
            neu["label"] = label.strip()
        _setze(neu, "time", time, _hhmm)
        _setze(neu, "ende", ende, _hhmm)
        _setze(neu, "ort", ort)
        if seit is not None:
            _setze(neu, "seit", seit, lambda f, w: _datum(f, w).isoformat())
        if rrule is not None:
            if not rrule.strip() or not kalender_regel.regel_gueltig(rrule.strip()):
                raise KalenderAbgelehnt("RRULE-UNGUELTIG", f"Regel {rrule!r} ist ungültig")
            neu["rrule"] = rrule.strip()
        if bis is not None:
            if bis:
                b = _datum("bis", bis)
                if neu.get("seit") and b < _datum("seit", neu["seit"]):
                    raise KalenderAbgelehnt("SPANNE-VERDREHT",
                                            f"bis {b} liegt vor seit {neu['seit']}")
                neu["rrule"] = kalender_regel.mit_ende(neu["rrule"], b.isoformat())
            else:
                neu["rrule"] = kalender_regel.mit_ende(neu["rrule"], None)
            if not kalender_regel.regel_gueltig(neu["rrule"]):
                raise KalenderAbgelehnt("RRULE-UNGUELTIG", f"Regel {neu['rrule']!r} ist ungültig")
        if phase and not neu.get("time"):
            raise KalenderAbgelehnt("PHASE-OHNE-ZEIT")
        _zeiten(neu.get("time"), neu.get("ende"), ueber_mitternacht=phase)
        # Pausen, die noch per Titel an dieser Routine hingen, fest anbinden,
        # bevor der Titel sich ändert.
        if neu.get("label") != obj.get("label"):
            for p in data.get("pausen") or []:
                if isinstance(p, dict) and not p.get("routine_uid") \
                        and p.get("label") == obj.get("label"):
                    p["routine_uid"] = k
                    p["label"] = neu["label"]
        obj.clear()
        obj.update(neu)
        return False
    return _schreiben(k, arbeit, ("routine",))


def routine_loeschen(k: str) -> None:
    """Eine Routine mit allen Vorkommen löschen (genau diese)."""
    def arbeit(data, art, lname, o, obj):
        _aus_liste_nehmen(data, lname, o, obj)
        data["pausen"] = [p for p in data.get("pausen") or []
                          if not (isinstance(p, dict) and p.get("routine_uid") == k)]
        return True
    _schreiben(k, arbeit, ("routine",))


def _vorkommen(r, tag: date) -> bool:
    try:
        if kalender_regel.vorkommen(r, tag, tag):
            return True
    except Exception:
        return False
    abw = r.get("abweichungen") if isinstance(r.get("abweichungen"), dict) else {}
    return any(isinstance(a, dict) and a.get("tag") == tag.isoformat() for a in abw.values())


def routine_absagen(k: str, tag: str, an: bool = False) -> dict:
    """Ein Vorkommen ausschalten (an=False) bzw. wieder einschalten."""
    d = _datum("tag", tag)

    def arbeit(data, art, lname, o, obj):
        if not _vorkommen(obj, d):
            raise KalenderAbgelehnt("KEIN-VORKOMMEN", f"{obj.get('label')} ist nicht am {d}")
        aus = [t for t in (obj.get("aus") or []) if t != d.isoformat()]
        if not an:
            aus.append(d.isoformat())
        if aus:
            obj["aus"] = aus
        else:
            obj.pop("aus", None)
        return False
    return _schreiben(k, arbeit, ("routine",))


def routine_tag_aendern(k: str, tag: str, **felder) -> dict:
    """NUR dieses Vorkommen ändern (Abweichung, wie am Handy „nur dieser
    Termin"): tag (verschieben), time, ende, label, ort."""
    d = _datum("tag", tag)
    erlaubt = {"tag", "time", "ende", "label", "ort"}
    falsch = set(felder) - erlaubt
    if falsch:
        raise KalenderAbgelehnt("UNBEKANNTES-FELD", "unbekannt: " + ", ".join(sorted(falsch)))

    def arbeit(data, art, lname, o, obj):
        if not _vorkommen(obj, d):
            raise KalenderAbgelehnt("KEIN-VORKOMMEN", f"{obj.get('label')} ist nicht am {d}")
        abw = obj.get("abweichungen") if isinstance(obj.get("abweichungen"), dict) else {}
        rid = next((r for r, a in abw.items() if isinstance(a, dict)
                    and a.get("tag") == d.isoformat()), d.isoformat())
        neu_abw = dict(abw)
        _abweichung_setzen(neu_abw, obj, rid, felder, kalender_rhythmus.ist_phase(obj, lname))
        _abweichungen_ablegen(obj, neu_abw)
        return False
    return _schreiben(k, arbeit, ("routine",))


def _abweichung_setzen(abw: dict, obj: dict, rid: str, felder: dict, phase: bool) -> None:
    """Die Abweichung `rid` (ursprünglicher Tag) in `abw` neu setzen —
    geprüft, bevor etwas geändert wird. Bleibt nur {"tag": rid} übrig (alles
    wieder wie die Regel), fällt sie weg."""
    a = dict(abw.get(rid) or {"tag": rid})
    if felder.get("tag"):
        a["tag"] = _datum("tag", felder["tag"]).isoformat()
    _setze(a, "time", felder.get("time"), _hhmm)
    _setze(a, "ende", felder.get("ende"), _hhmm)
    _setze(a, "ort", felder.get("ort"))
    if felder.get("label") is not None:
        if not felder["label"].strip():
            raise KalenderAbgelehnt("TITEL-LEER")
        a["label"] = felder["label"].strip()
    _zeiten(a.get("time") or obj.get("time"), a.get("ende"), ueber_mitternacht=phase)
    if a.get("ende") and "time" not in a and obj.get("time"):
        a["time"] = obj["time"]          # das .ics-Format braucht Beginn zum Ende
    if a == {"tag": rid}:
        abw.pop(rid, None)
    else:
        abw[rid] = a


def _abweichungen_ablegen(obj: dict, abw: dict) -> None:
    if abw:
        obj["abweichungen"] = abw
    else:
        obj.pop("abweichungen", None)


ZEITRAUM_HOECHSTENS = 366     # Tage; länger ist eine neue Regel, kein Zeitraum


def routine_zeitraum_aendern(k: str, von: str, bis: str, **felder) -> dict:
    """ALLE Vorkommen in [von, bis] ändern (je eine Abweichung, wie „nur
    dieser Termin" für jeden Tag) — Sasha: „3 Tage um 2 ins Bett". Felder:
    time, ende, label, ort; "" = an diesen Tagen wieder wie die Regel.
    Ein Schreibvorgang; abgelehnt = nichts geschrieben. Für Phasen darf das
    Ende vor dem Beginn liegen (am Folgetag)."""
    v, b = _datum("von", von), _datum("bis", bis)
    if b < v:
        raise KalenderAbgelehnt("SPANNE-VERDREHT", f"bis {b} liegt vor von {v}")
    if (b - v).days + 1 > ZEITRAUM_HOECHSTENS:
        raise KalenderAbgelehnt("ZEITRAUM-ZU-LANG",
                                f"{(b - v).days + 1} Tage; höchstens {ZEITRAUM_HOECHSTENS}")
    falsch = set(felder) - {"time", "ende", "label", "ort"}
    if falsch:
        raise KalenderAbgelehnt("UNBEKANNTES-FELD", "unbekannt: " + ", ".join(sorted(falsch)))
    felder = {f: w for f, w in felder.items() if w is not None}
    if not felder:
        raise KalenderAbgelehnt("UNBEKANNTES-FELD", "nichts zu ändern (time, ende, label, ort)")

    def arbeit(data, art, lname, o, obj):
        try:
            tage = [x.date().isoformat() for x in kalender_regel.vorkommen(obj, v, b)]
        except Exception:
            raise KalenderAbgelehnt("RRULE-UNGUELTIG", f"Regel {obj.get('rrule')!r} ist ungültig")
        if not tage:
            raise KalenderAbgelehnt("KEIN-VORKOMMEN", f"{obj.get('label')} ist nicht in {v}…{b}")
        abw = dict(obj.get("abweichungen") if isinstance(obj.get("abweichungen"), dict) else {})
        phase = kalender_rhythmus.ist_phase(obj, lname)
        for rid in tage:
            _abweichung_setzen(abw, obj, rid, felder, phase)
        _abweichungen_ablegen(obj, abw)
        return False
    return _schreiben(k, arbeit, ("routine",))


def routine_pause(k: str, von: str, bis: str, grund: str | None = None) -> dict:
    """Eine Pause (Ferien …) fest an DIESE Routine hängen."""
    v, b = _datum("von", von), _datum("bis", bis)
    if b < v:
        raise KalenderAbgelehnt("SPANNE-VERDREHT", f"bis {b} liegt vor von {v}")

    def arbeit(data, art, lname, o, obj):
        p = {"label": obj.get("label"), "von": v.isoformat(), "bis": b.isoformat(),
             "routine_uid": k}
        if grund:
            p["grund"] = grund
        data.setdefault("pausen", []).append(p)
        return False
    return _schreiben(k, arbeit, ("routine",))


# ── Ebene wechseln (committed ↔ uncommitted) ───────────────────────────
VERBINDLICH = "termine"
UNVERBINDLICH = "uncommitted"


def ebene_wechseln(k: str, ziel: str | None = None) -> dict:
    """Einen Eintrag (Termin, Spanne oder Routine) samt Kennung, Abweichungen
    und Pausen in eine andere Ebene legen. Ohne `ziel`: umschalten zwischen
    „termine" (committed) und „uncommitted". Ein Schreibvorgang; im .ics-
    Speicher wandert die Datei in den anderen Ordner (gleiche UID)."""
    if ziel is not None and ziel not in (VERBINDLICH, UNVERBINDLICH):
        raise KalenderAbgelehnt("EBENE-UNBEKANNT", f"Ebene {ziel!r} gibt es nicht")

    def arbeit(data, art, lname, o, obj):
        if kalender_rhythmus.ist_phase(obj, lname):
            raise KalenderAbgelehnt("IST-PHASE", f"{k} ist eine Phase des Tagesrhythmus")
        nach = ziel or (VERBINDLICH if lname == UNVERBINDLICH else UNVERBINDLICH)
        if nach == lname:
            return False
        layers = data.setdefault("layers", {})
        if nach not in layers:
            layers[nach] = copy.deepcopy(kalender._DEFAULT_LAYERS[nach])
        _aus_liste_nehmen(data, lname, o, obj)
        if o[0] == "entries":
            layers[nach].setdefault("entries", {}).setdefault(o[1], []).append(obj)
        else:
            layers[nach].setdefault("routines", []).append(obj)
        return False
    return _schreiben(k, arbeit)


# ── Neu anlegen (mit Kennung zurück) ───────────────────────────────────
def _anlegen(lname: str, tag: str | None, obj: dict) -> dict:
    """`obj` als Routine (tag None) bzw. Einmal-Eintrag an `tag` in Ebene
    `lname` speichern (Ebene aus den Vorgaben anlegen, wenn sie fehlt) und
    den Eintrag wie `eintrag()` zurückgeben. Ein Schreibvorgang."""
    with kalender._lock:
        data = kalender._load_raw()
        _sicherstellen(data)
        layers = data.setdefault("layers", {})
        if lname not in layers:
            if lname not in kalender._DEFAULT_LAYERS:
                raise KalenderAbgelehnt("EBENE-UNBEKANNT", f"Ebene {lname!r} gibt es nicht")
            layers[lname] = copy.deepcopy(kalender._DEFAULT_LAYERS[lname])
        if kalender._speicher().art != "ics":
            obj["uid"] = uuid.uuid4().hex
        if tag is None:
            layers[lname].setdefault("routines", []).append(obj)
        else:
            layers[lname].setdefault("entries", {}).setdefault(tag, []).append(obj)
        kalender._save_raw(data)
        k = kalender.kennung(obj)       # .ics: die UID setzt erst das Speichern
    if not k:
        raise KalenderAbgelehnt("KENNUNG-UNBEKANNT",
                                "gespeichert, aber ohne Kennung (nicht als .ics abbildbar)")
    return eintrag(k)


# ── Tagesrhythmus: Phasen (10.10.2026) ─────────────────────────────────
# Eine Phase = Routine in der Ebene `rhythmus` mit `motiv` (Katalog:
# kalender_rhythmus.MOTIVE). Nie ein Termin (kalender_konflikte), variabel:
# pro Tag (routine_tag_aendern), pro Zeitraum (routine_zeitraum_aendern),
# ab jetzt (phase_aendern).
def phase_anlegen(label: str, time: str, *, motiv: str, ende=None,
                  rrule: str = "FREQ=DAILY", von=None, bis=None, ort=None,
                  kategorie=None, kategorie_name=None) -> dict:
    """Neue Phase. `time` Pflicht (Beginn), `ende` optional und darf vor dem
    Beginn liegen (= am Folgetag, Schlaf 23:00–07:00). `von` = erster Tag
    (Standard heute), `bis` = letzter Tag oder None („bis auf Weiteres").
    -> der Eintrag wie eintrag() (kennung, art, layer, motiv, kategorie …)."""
    if not isinstance(label, str) or not label.strip():
        raise KalenderAbgelehnt("TITEL-LEER")
    if not time:
        raise KalenderAbgelehnt("PHASE-OHNE-ZEIT")
    obj = {"label": label.strip(), "time": _hhmm("time", time),
           "motiv": kalender_rhythmus.motiv_pruefen(motiv)}
    if ende:
        obj["ende"] = _hhmm("ende", ende)
    _zeiten(obj["time"], obj.get("ende"), ueber_mitternacht=True)
    v = _datum("von", von) if von else date.today()
    regel = (rrule or "").strip()
    if bis:
        b = _datum("bis", bis)
        if b < v:
            raise KalenderAbgelehnt("SPANNE-VERDREHT", f"bis {b} liegt vor von {v}")
        regel = kalender_regel.mit_ende(regel, b.isoformat())
    if not regel or not kalender_regel.regel_gueltig(regel):
        raise KalenderAbgelehnt("RRULE-UNGUELTIG", f"Regel {rrule!r} ist ungültig")
    obj["rrule"] = regel
    obj["seit"] = v.isoformat()
    if ort:
        obj["ort"] = ort.strip()
    kalender_kategorie.setzen(obj, kategorie, kategorie_name)
    return _anlegen(kalender_rhythmus.EBENE, None, obj)


def phase_aendern(k: str, **felder) -> dict:
    """Eine Phase ab jetzt/für immer ändern: time, ende, label, ort, motiv,
    rrule, von (= seit), bis ("" = bis auf Weiteres), kategorie,
    kategorie_name. Keine Phase → KEINE-PHASE."""
    if "von" in felder:
        felder["seit"] = felder.pop("von")
    return routine_aendern(k, nur_phase=True, **felder)


def phase_loeschen(k: str) -> None:
    """Eine Phase löschen (genau diese). Keine Phase → KEINE-PHASE."""
    def arbeit(data, art, lname, o, obj):
        if not kalender_rhythmus.ist_phase(obj, lname):
            raise KalenderAbgelehnt("KEINE-PHASE", f"{k} liegt in der Ebene {lname!r}")
        _aus_liste_nehmen(data, lname, o, obj)
        data["pausen"] = [p for p in data.get("pausen") or []
                          if not (isinstance(p, dict) and p.get("routine_uid") == k)]
        return True
    _schreiben(k, arbeit, ("routine",))


def phasen() -> list[dict]:
    """Alle Phasen wie gespeichert (wie alle_eintraege, nur Ebene rhythmus)."""
    return [e for e in alle_eintraege() if e["layer"] == kalender_rhythmus.EBENE]


# ── Gruppen (CATEGORIES) ───────────────────────────────────────────────
def kategorie_setzen(k: str, kategorie: str, kategorie_name=None) -> dict:
    """Gruppe eines Eintrags (Termin, Spanne, Routine, Phase) setzen;
    "keine" entfernt sie. Codes: KATEGORIE-UNBEKANNT, KATEGORIE-NAME-FEHLT."""
    if kategorie is None:
        raise KalenderAbgelehnt("KATEGORIE-UNBEKANNT", 'keine Gruppe angegeben ("keine" entfernt)')
    kalender_kategorie.pruefen(kategorie, kategorie_name)     # vor dem Laden prüfen

    def arbeit(data, art, lname, o, obj):
        kalender_kategorie.setzen(obj, kategorie, kategorie_name)
        return False
    return _schreiben(k, arbeit)


# Ebenen, in denen kein Kurs steht: Hintergrund und Auto-Spiegel.
_OHNE_KURS = (kalender_rhythmus.EBENE, "erlebt")


def kategorie_fuer_kurs(schluessel: str, kategorie: str, kategorie_name=None, *,
                        probe: bool = False) -> dict:
    """Allen Einträgen eines Kurses dieselbe Gruppe geben — in EINEM
    Schreibvorgang. Kurs = kalender_kategorie.titel_schluessel (erstes Wort
    ohne „@ Ort", Kurzformen); `schluessel` darf auch ein ganzer Titel sein
    („Experimentalphysik", „exphy", „ExPhy Übung"). Phasen und `erlebt`
    zählen nicht. `probe=True`: nur zeigen, was getroffen würde.
    -> {schluessel, kategorie, kategorie_name, geaendert, probe, eintraege}"""
    kurs = kalender_kategorie.titel_schluessel(schluessel)
    if not kurs:
        raise KalenderAbgelehnt("TITEL-LEER", "kein Kurs angegeben")
    kat, name = kalender_kategorie.pruefen(kategorie, kategorie_name)
    with kalender._lock:
        data = kalender._load_raw()
        _sicherstellen(data)
        treffer = [obj for _a, l, _o, obj in _alle_objekte(data)
                   if l not in _OHNE_KURS
                   and kalender_kategorie.titel_schluessel(obj.get("label")) == kurs]
        if not treffer:
            raise KalenderAbgelehnt("KEIN-TREFFER", f"kein Eintrag zum Kurs {kurs!r}")
        geaendert = 0
        for obj in treffer:
            vorher = (obj.get("kategorie"), obj.get("kategorie_name"))
            kalender_kategorie.setzen(obj, kategorie, kategorie_name)
            geaendert += vorher != (obj.get("kategorie"), obj.get("kategorie_name"))
        ziel = {kalender.kennung(obj) for obj in treffer}
        if not probe:                    # probe: geändertes Dict nur zeigen
            kalender._save_raw(data)
            data = kalender._load_raw()
    pausen = data.get("pausen") or []
    return {"schluessel": kurs, "kategorie": kat or kalender_kategorie.KEINE,
            "kategorie_name": name, "geaendert": geaendert, "probe": probe,
            "eintraege": [_aussen(a, l, o, obj, pausen) for a, l, o, obj in _alle_objekte(data)
                          if kalender.kennung(obj) in ziel]}
