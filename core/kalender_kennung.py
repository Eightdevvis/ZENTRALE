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
import kalender_regel
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
                    von=None, bis=None, times=None, enden=None) -> dict:
    """Einen Einmal-Termin ODER eine Spanne ändern.
    Einmal: label, tag (verschieben), time, ende, ort.
    Spanne: label, ort, von/bis (erster/letzter Tag; die Tageszeiten wandern
    beim Verschieben von `von` mit), times/enden = {tag: "HH:MM"|"" } für
    einzelne Tage ("" = an dem Tag ohne Uhrzeit bzw. ohne Ende)."""
    def arbeit(data, art, lname, o, obj):
        neu = copy.deepcopy(obj)
        if label is not None:
            if not label.strip():
                raise KalenderAbgelehnt("TITEL-LEER")
            neu["label"] = label.strip()
        _setze(neu, "ort", ort)
        if art == "einmal":
            for name, wert in (("von", von), ("bis", bis), ("times", times), ("enden", enden)):
                if wert is not None:
                    raise KalenderAbgelehnt("UNBEKANNTES-FELD",
                                            f"{name} gibt es nur bei mehrtägigen Terminen")
            _setze(neu, "time", time, _hhmm)
            _setze(neu, "ende", ende, _hhmm)
            _zeiten(neu.get("time"), neu.get("ende"))
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
                    rrule=None, seit=None) -> dict:
    """ALLE Vorkommen einer Routine. rrule als Text (wird geprüft); wer die
    Regel ändert, behält Aus-Tage und Abweichungen (sie gelten weiter für
    die Tage, die es noch gibt). Pausen hängen an der Kennung — Umbenennen
    nimmt sie mit."""
    def arbeit(data, art, lname, o, obj):
        neu = copy.deepcopy(obj)
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
        _zeiten(neu.get("time"), neu.get("ende"))
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
        a = dict(abw.get(rid) or {"tag": d.isoformat()})
        if felder.get("tag"):
            a["tag"] = _datum("tag", felder["tag"]).isoformat()
        _setze(a, "time", felder.get("time"), _hhmm)
        _setze(a, "ende", felder.get("ende"), _hhmm)
        _setze(a, "ort", felder.get("ort"))
        if felder.get("label") is not None:
            if not felder["label"].strip():
                raise KalenderAbgelehnt("TITEL-LEER")
            a["label"] = felder["label"].strip()
        _zeiten(a.get("time") or obj.get("time"), a.get("ende"))
        if a.get("ende") and "time" not in a and obj.get("time"):
            a["time"] = obj["time"]          # das .ics-Format braucht Beginn zum Ende
        neu_abw = dict(abw)
        neu_abw[rid] = a
        obj["abweichungen"] = neu_abw
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
