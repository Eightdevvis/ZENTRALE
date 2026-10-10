# core/calendar.py
#
# Kalender-System mit Layer-Struktur – zeitliche Klammer um den
# assoziativen Graph (siehe memory/ki/ki_system.md).
#
# Idee: der Konzept-Graph ist assoziativ und gut darin "wer mag was,
# wer kennt wen, was hängt mit was zusammen" abzubilden. Was er
# strukturell NICHT gut kann ist "welcher Tag war wann", "was kommt
# noch", "regelmäßige Termine". Dafür gibt es jetzt diese Schicht:
# eine eigene Datei `data/ai_calendar.json` mit benannten Layern,
# die unabhängig sichtbar/unsichtbar geschaltet werden können.
#
# Layer-Modell (initial drei, weitere via add_layer erweiterbar):
#
#   termine    – manuelle Einmal-Events (Arzt, Frist, Geburtstag)
#   routinen   – Wiederholungs-Regeln (Geige jeden Di, Miete am 1.)
#   erlebt     – auto-captured aus dem Graph-Extraktor (Spiegelung
#                aller geschah-am-Edges → eine "war da was?"-Übersicht)
#
# Geplant: ernaehrung, schlaf, training – jeder Tracker bekommt einen
# eigenen Layer mit eigenem Tool, Daten kollidieren nicht.
#
# Cross-Reference zum Graph:
#
#   Graph: Geige ─[geschah-am]─► 2026-05-26
#   Kalender (routinen): Geige | RRULE=FREQ=WEEKLY;BYDAY=TU | 18:00
#
#   "wie war Geige letztes Mal?" → Kalender liefert "letzter Di = 26.5.",
#   Graph-Aktivierung um den 26.5. liefert verknüpfte Konzepte
#   (Stimmung, was danach kam). Verbindung läuft über das ISO-Datum
#   als gemeinsamer Schlüssel - keine harte Referenz, beide Systeme
#   bleiben unabhängig wartbar.

import os
import copy
import hashlib
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import state  # Logging in den UI-Terminal-Stream
import kalender_kategorie
import kalender_regel
import kalender_rhythmus
import kalender_speicher
from kalender_ics import FELD as _ICS_FELD, ohne_interna

# ── Pfad & Locking ─────────────────────────────────────────────────────
# CAL_PATH ist der Ort der ALTEN JSON. Alle anderen Kalender-Pfade (vdir,
# Nebendaten, Verlauf, Snapshots) leiten sich aus seinem Ordner ab
# (kalender_speicher.pfade) — so biegt ein Test, der CAL_PATH umlenkt, beide
# Speicher zugleich in sein Wegwerf-Verzeichnis.
CAL_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_calendar.json"
ICS_DIR: Path | None = None       # None = data/kalender/ neben CAL_PATH
_lock    = threading.Lock()
_ERZWUNGEN = None                 # mit_speicher(): fester Speicher für Skripte/Tests

# ── Default-Layer beim ersten Boot ────────────────────────────────────
# Farben sind als Hinweis für späteres UI gedacht (Konzept-Browser,
# Wochen-Widget). Backend selbst rendert keine Farbe.
_DEFAULT_LAYERS = {
    "termine": {
        "label":           "Termine",
        "color":           "#ff5500",
        "default_visible": True,
        "entries":         {},   # {date_iso: [{label, time?, ...}, ...]}
        "routines":        [],   # in dieser Layer-Klasse ungenutzt
    },
    "routinen": {
        "label":           "Routinen",
        "color":           "#5577ff",
        "default_visible": True,
        "entries":         {},   # Einmal-Ausnahmen sind hier auch erlaubt
        "routines":        [],   # [{label, rrule, time?, ...}]
    },
    # Unverbindliches (Sasha, 10.10.2026: „den layer uncommitted … mehr
    # transparent … sachen verschieben committed <-> uncommitted"). Liegt in
    # den Ansichten immer blass ÜBER den Terminen, nie getrennt; Kollisionen
    # sind dort nur Hinweis, die KI liest es als „vielleicht".
    "uncommitted": {
        "label":           "Uncommitted",
        "color":           "#888888",
        "default_visible": True,
        "entries":         {},
        "routines":        [],
    },
    # Tagesrhythmus (Sasha, 10.10.2026: „eine leichte hintergrund ebene"):
    # Phasen wie Schlaf, Essen, coming down — Routinen mit `motiv`, nie ein
    # Termin (kalender_rhythmus.py). Nicht im Google-Abgleich.
    kalender_rhythmus.EBENE: {
        "label":           "Rhythmus",
        "color":           "#556677",
        "default_visible": True,
        "entries":         {},
        "routines":        [],
    },
    "erlebt": {
        "label":           "Erlebt (auto)",
        "color":           "#888888",
        "default_visible": False,  # default ausgeblendet, sonst noisy
        "entries":         {},
        "routines":        [],
    },
}

_WEEKDAYS_SHORT_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_MONTHS_FULL_DE    = ["Januar", "Februar", "März", "April", "Mai", "Juni",
                      "Juli", "August", "September", "Oktober", "November",
                      "Dezember"]


# ── Persistenz ─────────────────────────────────────────────────────────
# Seit 2026-10-06 austauschbar: die alte JSON (core/kalender_json.py) oder
# der .ics-Ordner (core/kalender_ics.py), gewählt über die Einstellung
# `kalender_speicher` (memory/werkzeuge/kalender_ics_bauplan.md). Alles
# darüber — Kollisionen, Alarme, Imprint — arbeitet unverändert auf dem
# Daten-Dict und weiß nicht, woher es kommt.
def _speicher():
    return _ERZWUNGEN or kalender_speicher.speicher_fuer(CAL_PATH, ICS_DIR)


@contextmanager
def mit_speicher(speicher):
    """Für Skripte und Tests (Migration, Vergleich json↔ics): alle
    Kalender-Funktionen laufen in diesem Block gegen `speicher`. Nicht für
    den laufenden Betrieb — der Schalter ist prozessweit."""
    global _ERZWUNGEN
    vorher, _ERZWUNGEN = _ERZWUNGEN, speicher
    try:
        yield speicher
    finally:
        _ERZWUNGEN = vorher


def _default_layers() -> dict:
    # TIEF kopieren. `dict(v)` kopierte nur die Layer-Hülle — `entries`
    # und `routines` blieben DIESELBEN Objekte wie in _DEFAULT_LAYERS.
    # Ein Eintrag, der vor der ersten gespeicherten Datei geschrieben
    # wurde, landete damit in der Vorlage und tauchte danach in jedem
    # "frischen" Kalender dieses Prozesses wieder auf.
    # Ebenen, die ein Speicher nicht mehr führt (`erlebt` in .ics), fehlen.
    weg = _speicher().ohne_layer
    return {k: copy.deepcopy(v) for k, v in _DEFAULT_LAYERS.items() if k not in weg}


def _load_raw() -> dict:
    data = _speicher().laden()
    if data is None:
        return {"version": 1, "layers": _default_layers()}
    return data


def _save_raw(data: dict) -> None:
    # Wirft KalenderGesperrt (Massenlösch-Sperre, Rückfall-Sperre): dann ist
    # nichts geschrieben, und der Aufrufer soll es merken — kein except hier.
    _speicher().speichern(data)
    # Echte Änderung geschrieben → Peer-Push anstoßen (no-op ohne AUTOPUSH).
    try:
        from datasync import notify_change
        notify_change(str(CAL_PATH))
    except Exception:
        pass
    # Alarm-Kanal frisch halten: nach JEDER Mutation das komplette Alarm-Set
    # neu rechnen und in den State legen (Dashboard-Ecke + KI-Prompt ziehen es
    # von dort). Zentral hier, weil ALLE Schreibpfade durch _save_raw laufen.
    # In try/except gekapselt: ein Alarm-Rechenfehler darf NIE einen Kalender-
    # Schreibvorgang kippen. Kein Deadlock-Risiko - die open_alarms-Kette nimmt
    # _lock nicht (nur die Setter tun das, in denen _save_raw gerade schon läuft).
    try:
        state.set_alarms(open_alarms())
    except Exception as e:
        state.push_log(f"[calendar] Alarm-Recompute fehlgeschlagen: {e}")


def ensure_init() -> None:
    """
    Stellt sicher dass die Kalender-Datei existiert und alle Default-
    Layer da sind. Idempotent - kann beim Boot mehrfach gerufen werden.
    Migrations-sicher: fehlende Default-Layer werden ergänzt, vorhandene
    benutzerdefinierte Layer bleiben unberührt.
    """
    with _lock:
        data = _speicher().laden()
        if data is None:
            _save_raw({"version": 1, "layers": _default_layers()})
            return
        layers = data.setdefault("layers", {})
        changed = False
        for name, default in _default_layers().items():
            if name not in layers:
                layers[name] = default
                changed = True
        if changed:
            _save_raw(data)


# ── Schreib-API ────────────────────────────────────────────────────────
def _mit_kategorie(extras: dict) -> dict:
    """`kategorie`/`kategorie_name` in den Zusatzfeldern geprüft übernehmen
    (kalender_kategorie.pruefen; wirft KalenderAbgelehnt, dann ist nichts
    geschrieben — die Prüfung läuft vor dem Laden). "keine" = kein Feld."""
    if "kategorie" not in extras and "kategorie_name" not in extras:
        return extras
    rest = {k: v for k, v in extras.items() if k not in ("kategorie", "kategorie_name")}
    kalender_kategorie.setzen(rest, extras.get("kategorie"), extras.get("kategorie_name"))
    return rest


def add_entry(layer: str, day: str, label: str,
              time: str | None = None, **extras) -> bool:
    """
    Trägt einen Einmal-Eintrag in einen Layer ein.

      layer  – Layer-Name, muss existieren (sonst False)
      day    – YYYY-MM-DD
      label  – kurzer Titel
      time   – HH:MM (optional, sonst ganztags)
      extras – beliebige Zusatzfelder (tags, location, ...)
    """
    with _lock:
        data = _load_raw()
        if layer not in data.get("layers", {}):
            state.push_log(f"[calendar] unbekannter Layer: {layer}")
            return False
        entries = data["layers"][layer].setdefault("entries", {})
        entry: dict = {"label": label}
        if time:
            entry["time"] = time
        entry.update(_mit_kategorie(extras))
        entries.setdefault(day, []).append(entry)
        _save_raw(data)
        return True


def add_span(layer: str, von: str, bis: str, label: str, **extras) -> bool:
    """
    Trägt einen MEHRTÄGIGEN (ganztägigen) Termin ein: einen Einmal-Eintrag mit
    `bis`-Datum, gespeichert unter dem Start-Tag `von`. `entries_in_range`
    expandiert ihn dann über die ganze Spanne [von, bis] (inklusive).

      von/bis – YYYY-MM-DD; bis muss >= von sein.
      label   – Titel.
      extras  – Zusatzfelder (ort, …). Uhrzeiten werden NICHT pauschal gesetzt
                (ganztägig); pro Tag optional über `set_span_time`.
    Defensiv: ungültige/verdrehte Daten oder unbekannter Layer → False.
    """
    try:
        d0 = date.fromisoformat(von)
        d1 = date.fromisoformat(bis)
    except (TypeError, ValueError):
        state.push_log(f"[calendar] ungültige Spannen-Daten {von!r}/{bis!r}")
        return False
    if d1 < d0:
        state.push_log(f"[calendar] Spanne verdreht: bis {bis} < von {von}")
        return False
    with _lock:
        data = _load_raw()
        if layer not in data.get("layers", {}):
            state.push_log(f"[calendar] unbekannter Layer: {layer}")
            return False
        entries = data["layers"][layer].setdefault("entries", {})
        entry: dict = {"label": label, "bis": bis}
        entry.update(_mit_kategorie(extras))
        entries.setdefault(von, []).append(entry)
        _save_raw(data)
        return True


def set_span_time(layer: str, von: str, label: str, day: str,
                  time: str | None) -> bool:
    """
    Für EINEN Tag einer mehrtägigen Spanne eine Uhrzeit setzen bzw. löschen
    (leeres `time` = wieder ganztägig an dem Tag). Die Spanne wird über ihren
    Start-Tag `von` + `label` (case-insensitiv, exakt) gefunden; die Uhrzeit
    landet in `times[day]` an der Spanne. Liefert True bei Treffer.
    """
    needle = (label or "").strip().lower()
    time = (time or "").strip() or None
    with _lock:
        data = _load_raw()
        lobj = data.get("layers", {}).get(layer)
        if not lobj:
            return False
        for e in (lobj.get("entries", {}).get(von) or []):
            if not isinstance(e, dict) or not e.get("bis"):
                continue
            if (e.get("label", "").strip().lower()) != needle:
                continue
            times = e.setdefault("times", {})
            if time:
                times[day] = time
            else:
                times.pop(day, None)
            if not times:
                e.pop("times", None)      # leere Map wieder entfernen (sauber)
            _save_raw(data)
            return True
    return False


def naechster_termin(jetzt: datetime | None = None) -> dict | None:
    """Der naechste Termin ab jetzt (heute oder morgen). None = keiner.

    -> {"label", "time", "layer", "minuten", "morgen"}

    Zwei Verwendungen, absichtlich dieselbe Funktion: das Werkzeug
    `read_time` beantwortet damit "wie lange hab ich noch", und der Takt
    entscheidet damit, wann er anstoesst. Zwei getrennte Rechnungen fuer
    dieselbe Frage wuerden irgendwann auseinanderlaufen, und dann sagt der
    Ping etwas anderes als die Antwort im Chat.

    Nur sichtbare Layer — dieselbe Regel wie beim Imprint: die KI soll
    nichts wissen, was Sasha nicht nachlesen kann.
    """
    jetzt = jetzt or datetime.now()
    heute = jetzt.date()
    try:
        data = _load_raw()
    except Exception:
        return None
    # Der Tagesrhythmus ist kein Termin: kein Countdown, kein Takt-Anstoß.
    sichtbar = [n for n, lyr in data.get("layers", {}).items()
                if lyr.get("default_visible", True) and n != kalender_rhythmus.EBENE]
    tage = entries_in_range(heute, heute + timedelta(days=1), layers=sichtbar)
    for iso in sorted(tage):
        ist_morgen = iso != heute.isoformat()
        for e in tage[iso]:
            m = _to_minutes(e.get("time") or "")
            if m is None:
                continue          # ganztags: kein Countdown moeglich
            weg = m - (jetzt.hour * 60 + jetzt.minute) + (1440 if ist_morgen else 0)
            if weg < 0:
                continue          # heute schon vorbei
            return {"label": e.get("label", ""), "time": e.get("time", ""),
                    "layer": e.get("layer", ""), "minuten": weg,
                    "morgen": ist_morgen}
    return None


def routine_finden(label: str, layer: str | None = None) -> list:
    """Alle Routinen, deren Label passt. -> [(layer, index, routine), ...]

    Match wie bei delete_entry: case-insensitiv, exakt ODER Teilstring.
    """
    needle = (label or "").strip().lower()
    if not needle:
        return []
    aus = []
    data = _load_raw()
    layers = data.get("layers", {})
    for lname in ([layer] if layer else list(layers.keys())):
        lyr = layers.get(lname) or {}
        for i, r in enumerate(lyr.get("routines") or []):
            if needle in (r.get("label") or "").lower():
                aus.append((lname, i, ohne_interna(r)))
    return aus


def routine_aendern(label: str, layer: str | None = None,
                    neues_label: str | None = None, **felder) -> int:
    """Felder einer bestehenden Routine aendern. -> Anzahl geaenderter.

    Gab es bis 18.08.2026 nicht, und das war eine echte Luecke: Sasha sagte
    "Geige ist jetzt um 18 statt 17:45", die KI konnte nur ANLEGEN — also
    stand die Stunde zweimal im Kalender, und sie musste einraeumen, dass
    sie die alte nicht wegbekommt.

    `label` ist der SUCHBEGRIFF; ein neuer Titel geht ueber `neues_label`.
    Die beiden zu trennen ist noetig, nicht huebsch: `label` als Feld in
    **felder waere derselbe Parametername zweimal und haette beim
    Umbenennen eine Ausnahme geworfen.

    `felder` mit Wert None werden ignoriert (nicht geloescht), damit man
    die Uhrzeit aendern kann, ohne Ort und Ende zu verlieren. Ein leerer
    String LOESCHT das Feld — das ist der Weg, einen Ort wieder loszuwerden.
    """
    if neues_label:
        felder["label"] = neues_label
    if felder.get("rrule") and not kalender_regel.regel_gueltig(felder["rrule"]):
        state.push_log(f"[calendar] ungueltige rrule {felder['rrule']!r}")
        return 0
    treffer = routine_finden(label, layer)
    if not treffer:
        return 0
    # Keine stille Korrektur (09.10.2026): Uhrzeiten prüfen, Ende nach Beginn.
    from kalender_fehler import reihenfolge as _zeiten, uhrzeit as _hhmm
    for k in ("time", "ende"):
        if felder.get(k):
            felder[k] = _hhmm(k, felder[k])
    for _l, _i, r in treffer:
        t = felder["time"] if felder.get("time") is not None else r.get("time")
        e = felder["ende"] if felder.get("ende") is not None else r.get("ende")
        _zeiten(t or None, e or None, ueber_mitternacht=(_l == kalender_rhythmus.EBENE))
    geaendert = 0
    with _lock:
        data = _load_raw()
        for lname, i, _ in treffer:
            r = data["layers"][lname]["routines"][i]
            for k, v in felder.items():
                if v is None:
                    continue
                if v == "":
                    if k not in ("label", "rrule"):   # ohne die beiden
                        r.pop(k, None)                # ist es keine Routine mehr
                else:
                    r[k] = v
            geaendert += 1
        _save_raw(data)
    return geaendert


def routine_loeschen(label: str, layer: str | None = None) -> int:
    """Eine Wiederholungs-Regel entfernen. -> Anzahl entfernter.

    Getrennt von delete_entry, weil die Semantik eine andere ist: ein
    Einmal-Termin verschwindet an EINEM Tag, eine Routine fuer immer.
    """
    treffer = routine_finden(label, layer)
    if not treffer:
        return 0
    with _lock:
        data = _load_raw()
        # von hinten, damit die Indizes waehrend des Loeschens halten
        for lname, i, _ in sorted(treffer, key=lambda t: -t[1]):
            del data["layers"][lname]["routines"][i]
        _save_raw(data)
    return len(treffer)


def delete_entry(day: str, label: str, layer: str | None = None) -> int:
    """
    Löscht Einmal-Einträge an einem Tag, deren Label passt.

      day    – YYYY-MM-DD des Termins
      label  – Titel; Match case-insensitiv, exakt ODER als Teilstring
               (damit „Fake-Termin" auch „Fake-Termin: Test" trifft)
      layer  – optional auf einen Layer beschränken; None = alle Layer

    Wirkt nur auf `entries` (Einmal-Termine), NICHT auf Routinen/Pausen –
    die liegen in anderen Speicher-Slots und haben eigene Semantik.

    Gibt die Anzahl entfernter Einträge zurück (0 = nichts gefunden, damit
    der Aufrufer dem User ehrlich „nichts gelöscht" melden kann statt einen
    Erfolg zu behaupten).
    """
    needle = (label or "").strip().lower()
    if not needle:
        return 0
    removed = 0
    with _lock:
        data   = _load_raw()
        layers = data.get("layers", {})
        # Entweder nur der genannte Layer oder alle durchsuchen.
        names  = [layer] if layer else list(layers.keys())
        for lname in names:
            lobj = layers.get(lname)
            if not lobj:
                continue
            entries  = lobj.get("entries", {})
            day_list = entries.get(day)
            if not day_list:
                continue
            keep = []
            for e in day_list:
                lab = (e.get("label", "")).strip().lower()
                if needle == lab or needle in lab:
                    removed += 1          # Treffer → fällt raus
                else:
                    keep.append(e)        # behalten
            # Tages-Liste aktualisieren bzw. leeren Tag-Key ganz entfernen.
            if keep:
                entries[day] = keep
            else:
                entries.pop(day, None)
        if removed:
            _save_raw(data)
    return removed


def _routine_hits_day(r: dict, d: date) -> bool:
    """True, wenn die Routine `r` an genau dem Tag `d` ein Vorkommen hat.

    Nötig, um bei MEHREREN gleichnamigen Routinen (z.B. zwei 'Parkour' an
    verschiedenen Wochentagen) die RICHTIGE zu treffen — Label allein reicht
    nicht (sonst landet ein Aus-/Lösch-Befehl auf der erstbesten Namensgleichen,
    die an dem Tag gar nicht stattfindet → es passiert sichtbar nichts).
    Expandiert die rrule für den einen Tag (gleiche Logik wie entries_in_range).
    Defensiv: ungültige/fehlende rrule → False."""
    if not r.get("rrule"):
        return False
    try:
        return bool(kalender_regel.vorkommen(r, d, d))
    except Exception:
        return False


def set_routine_skip(layer: str, label: str, day: str, off: bool = True,
                     time: str | None = None) -> bool:
    """
    Einen EINZELNEN Routine-Termin an `day` deaktivieren (off=True) bzw. wieder
    aktivieren (off=False) - reversibel, pro Vorkommen. Speichert die Liste der
    deaktivierten ISO-Daten im Feld `aus` an der Routine selbst.

      layer  – Layer der Routine (z.B. 'routinen')
      label  – Routinen-Titel; Match case-insensitiv, exakt ODER Teilstring.
      day    – YYYY-MM-DD des konkreten Vorkommens
      off    – True = deaktivieren, False = wieder aktivieren
      time   – optional HH:MM des Vorkommens, grenzt bei gleichem Label+Tag
               die richtige Routine zusätzlich ein.

    Trifft NUR Routinen, die an `day` tatsächlich vorkommen (`_routine_hits_day`)
    — sonst landet das Aus-Datum auf einer gleichnamigen Routine an einem anderen
    Wochentag und bewirkt sichtbar nichts. Anders als delete bleibt die Routine
    voll erhalten; nur das eine Datum wird stillgelegt. Gibt True bei tatsächlicher
    Änderung zurück (False = nichts passendes gefunden / schon im Zielzustand).
    """
    needle = (label or "").strip().lower()
    if not needle:
        return False
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        return False
    want_time = (time or "").strip() or None
    changed = False
    with _lock:
        data = _load_raw()
        lobj = data.get("layers", {}).get(layer)
        if not lobj:
            return False
        cands = [r for r in lobj.get("routines", [])
                 if (needle == (r.get("label", "").strip().lower())
                     or needle in (r.get("label", "").strip().lower()))
                 and _routine_hits_day(r, d)]
        # Bei gleichem Tag + gleichem Label per Uhrzeit weiter eingrenzen.
        if want_time and any((c.get("time") or "") == want_time for c in cands):
            cands = [c for c in cands if (c.get("time") or "") == want_time]
        for r in cands:
            aus = r.setdefault("aus", [])
            if off and day not in aus:
                aus.append(day); changed = True
            elif not off and day in aus:
                aus.remove(day); changed = True
            if not aus:                 # leere Liste wieder entfernen (sauber)
                r.pop("aus", None)
        if changed:
            _save_raw(data)
    return changed


def delete_routine(layer: str, label: str, day: str | None = None,
                   time: str | None = None) -> int:
    """
    Eine GANZE Wiederholungs-Regel aus einem Layer entfernen (Gegenstück zu
    add_routine) - alle Vorkommen weg.

      layer  – Layer der Routine.
      label  – Titel; Match case-insensitiv, exakt ODER Teilstring.
      day    – optional YYYY-MM-DD: trifft dann NUR die Routine, die an diesem
               Tag vorkommt (damit gleichnamige Serien an anderen Wochentagen
               NICHT mitgelöscht werden). Ohne `day`: alle Label-Treffer.
      time   – optional, grenzt bei gleichem Label+Tag weiter ein.

    Gibt die Anzahl entfernter Routinen zurück (0 = nichts gefunden).
    """
    needle = (label or "").strip().lower()
    if not needle:
        return 0
    d = None
    if day:
        try:
            d = date.fromisoformat(day)
        except (TypeError, ValueError):
            d = None
    want_time = (time or "").strip() or None
    removed = 0
    with _lock:
        data = _load_raw()
        lobj = data.get("layers", {}).get(layer)
        if not lobj:
            return 0
        routines = lobj.get("routines", [])

        def label_match(r):
            lab = (r.get("label", "")).strip().lower()
            return needle == lab or needle in lab

        cands = [r for r in routines
                 if label_match(r) and (d is None or _routine_hits_day(r, d))]
        if d is not None and want_time and any((c.get("time") or "") == want_time for c in cands):
            cands = [c for c in cands if (c.get("time") or "") == want_time]
        cand_ids = {id(c) for c in cands}
        keep = [r for r in routines if id(r) not in cand_ids]
        removed = len(routines) - len(keep)
        if removed:
            lobj["routines"] = keep
            _save_raw(data)
    return removed


def add_routine(layer: str, label: str, rrule_str: str,
                time: str | None = None, **extras) -> bool:
    """
    Trägt eine Wiederholungs-Regel ein (iCal RRULE-Syntax).

    Beispiele:
      FREQ=WEEKLY;BYDAY=TU                  – jeden Dienstag
      FREQ=WEEKLY;BYDAY=MO,WE,FR            – Mo/Mi/Fr
      FREQ=MONTHLY;BYMONTHDAY=1             – jeder 1. im Monat
      FREQ=MONTHLY;BYDAY=2TU                – zweiter Dienstag im Monat
      FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25  – jedes Jahr 25.12.

    Validierung läuft via dateutil; ungültige Regeln werden abgewiesen
    und geloggt, damit nichts kaputtes persistiert wird.
    """
    if not kalender_regel.regel_gueltig(rrule_str):
        state.push_log(f"[calendar] ungültige rrule {rrule_str!r}")
        return False

    with _lock:
        data = _load_raw()
        if layer not in data.get("layers", {}):
            state.push_log(f"[calendar] unbekannter Layer: {layer}")
            return False
        routine: dict = {"label": label, "rrule": rrule_str}
        if time:
            routine["time"] = time
        routine.update(_mit_kategorie(extras))
        data["layers"][layer].setdefault("routines", []).append(routine)
        _save_raw(data)
        return True


def add_layer(name: str, label: str, color: str = "#999999",
              default_visible: bool = True) -> bool:
    """
    Legt einen neuen Layer an (z.B. 'ernaehrung', 'training'). Idempotent:
    wenn er schon existiert, wird er nicht überschrieben.
    """
    with _lock:
        data = _load_raw()
        layers = data.setdefault("layers", {})
        if name in layers:
            return False
        layers[name] = {
            "label":           label,
            "color":           color,
            "default_visible": default_visible,
            "entries":         {},
            "routines":        [],
        }
        _save_raw(data)
        return True


def add_pause(label: str, von: str, bis: str, grund: str | None = None) -> bool:
    """
    Trägt eine Pause/einen Ausfall für eine Routine ein: in [von, bis] findet
    die Routine mit diesem `label` NICHT statt (Ferien, Feiertag, Lehrerin im
    Urlaub). Beim Lesen wird das betroffene Routinen-Vorkommen als „fällt aus"
    markiert statt normal angezeigt - so wird der User erinnert, dass z.B. keine
    Geige ist, statt umsonst hinzufahren (Richtung 2 zum Reise-Konflikt: hier
    sagt die ANDERE Seite ab).

    Pausen liegen top-level unter `pausen` (nicht in einem Layer), weil sie ein
    Routinen-Label Layer-übergreifend betreffen. von/bis als YYYY-MM-DD inkl.
    """
    try:
        date.fromisoformat(von)
        date.fromisoformat(bis)
    except ValueError:
        state.push_log(f"[calendar] ungültige Pause-Daten {von!r}/{bis!r}")
        return False
    with _lock:
        data = _load_raw()
        pause: dict = {"label": label, "von": von, "bis": bis}
        if grund:
            pause["grund"] = grund
        data.setdefault("pausen", []).append(pause)
        _save_raw(data)
        return True


# ── Auto-Capture aus dem Graph: ERSATZLOS GESTRICHEN (17.08.2026) ──────
# `auto_capture` spiegelte geschah-am-Kanten des Graphen ungefragt in den
# unsichtbaren `erlebt`-Layer — ein Schreibweg am Erlaubnis-Gate vorbei, den
# nur die KI lesen konnte. Den Kalender füllen nur Sasha und bestätigte
# Tool-Calls; lesend hilft `imprint_for_prompt()`. Ganze Begründung:
# memory/werkzeuge/kalender_system.md ("Auto-Capture vom Graph").


# ── Lese-API ───────────────────────────────────────────────────────────
def _aussen(e: dict) -> dict:
    """Ein Eintrag ohne die internen Felder des .ics-Speichers (`_ics`: UID,
    Position). Die gehören nie in eine Antwort an Fronten oder KI."""
    return {k: v for k, v in e.items() if not k.startswith("_ics")}


def kennung(e: dict) -> str | None:
    """Die feste Kennung eines gespeicherten Eintrags/einer Routine: im
    .ics-Speicher die UID (überlebt Umbenennen, Zeit, Ort), im alten
    JSON-Speicher das Feld `uid` (vergibt core/kalender_kennung.py beim
    ersten Zugriff). None, solange es (noch) keine gibt."""
    if not isinstance(e, dict):
        return None
    intern = e.get(_ICS_FELD)
    if isinstance(intern, dict) and intern.get("uid"):
        return str(intern["uid"])
    return str(e["uid"]) if e.get("uid") else None


# Felder einer Routine, die jedes Vorkommen mitbekommt (zusätzlich zu Zeit,
# Ende, Ort …): Motiv der Phase, Gruppe.
_MITGEGEBEN = ("motiv", "kategorie", "kategorie_name", "kategorien_weitere")


def _ueber_nacht_markieren(e: dict) -> None:
    """Phase über Mitternacht (Schlaf 23:00–07:00): `ueber_nacht: True` —
    das Vorkommen steht am Tag des Beginns und endet am Folgetag."""
    if kalender_rhythmus.ist_phase(e) and kalender_rhythmus.ueber_mitternacht(
            e.get("time"), e.get("ende")):
        e["ueber_nacht"] = True


def entries_in_range(start: date, end: date,
                     layers: list[str] | None = None) -> dict:
    """
    Liefert alle Einträge im Zeitraum [start, end] (inklusive), nach
    Datum gruppiert. Wenn `layers` angegeben: nur diese Layer.

    Routinen werden via rrule expandiert - jedes Vorkommen in dem
    Range wird als eigener Eintrag zurückgegeben.

    Return-Form:
      {
        "2026-05-26": [
          {"layer": "routinen", "label": "Geige", "time": "18:00"},
          ...
        ],
        ...
      }
    sortiert nach Datum, innerhalb Tag nach Zeit.
    """
    data = _load_raw()
    target = layers if layers else list(data.get("layers", {}).keys())
    pausen = data.get("pausen", [])  # Ausfälle (Ferien etc.) für Routinen
    out: dict[str, list[dict]] = {}

    for layer_name in target:
        layer = data["layers"].get(layer_name)
        if not layer:
            continue

        # 1. Einmal-Einträge (inkl. mehrtägiger Spannen mit `bis`)
        for day_iso, day_entries in layer.get("entries", {}).items():
            try:
                d0 = date.fromisoformat(day_iso)
            except ValueError:
                continue
            for e in day_entries:
                bis_s = e.get("bis") if isinstance(e, dict) else None
                if bis_s:
                    # Mehrtägiger Termin: über [von, bis] ∩ [start, end] verteilen.
                    # Jeder Tag bekommt eine eigene Kopie mit Spann-Markern; die
                    # optionale Pro-Tag-Uhrzeit kommt aus `times`. `bis`/`times`
                    # selbst wandern NICHT als Rohfelder in die Kopie.
                    try:
                        d1 = date.fromisoformat(bis_s)
                    except (TypeError, ValueError):
                        d1 = d0
                    if d1 < d0:
                        d1 = d0
                    times = e.get("times") if isinstance(e.get("times"), dict) else {}
                    # `enden`: Ende pro Tag — gibt es nur bei Spannen, die von
                    # außen kommen (.ics: "Fr 18:00 bis So 14:00", Messe mit
                    # eigener Zeit je Tag). Die alte JSON kennt das Feld nicht.
                    enden = e.get("enden") if isinstance(e.get("enden"), dict) else {}
                    cur = max(d0, start)
                    last = min(d1, end)
                    while cur <= last:
                        ci = cur.isoformat()
                        kopie = {k: v for k, v in _aussen(e).items()
                                 if k not in ("bis", "times", "enden")}
                        if kennung(e):
                            kopie["kennung"] = kennung(e)
                        kopie.update({
                            "layer": layer_name, "spanning": True,
                            "von": day_iso, "bis": bis_s,
                            "span_first": (cur == d0), "span_last": (cur == d1),
                        })
                        t = times.get(ci)
                        if t:
                            kopie["time"] = t          # Uhrzeit nur für diesen Tag
                        else:
                            kopie.pop("time", None)     # sonst ganztägig
                        if enden.get(ci):
                            kopie["ende"] = enden[ci]
                        out.setdefault(ci, []).append(kopie)
                        cur += timedelta(days=1)
                elif start <= d0 <= end:
                    eintrag = {"layer": layer_name, **_aussen(e)}
                    if kennung(e):
                        eintrag["kennung"] = kennung(e)
                    _ueber_nacht_markieren(eintrag)
                    out.setdefault(day_iso, []).append(eintrag)

        # 2. Routinen expandieren
        for r in layer.get("routines", []):
            try:
                abweichungen = r.get("abweichungen") if isinstance(r.get("abweichungen"), dict) else {}
                for occ in kalender_regel.vorkommen(r, start, end):
                    day_iso = occ.date().isoformat()
                    # recurring=True markiert diesen Eintrag als Routine (aus einer
                    # rrule expandiert), im Gegensatz zu Einmal-Einträgen. Der
                    # Reise-Konflikt-Check (_conflict_lines) nutzt das: regelmäßige
                    # Termine fallen auf Reisen sowieso aus → kein Alarm.
                    entry: dict = {"layer": layer_name, "label": r["label"],
                                   "recurring": True, "rrule": r["rrule"]}
                    if kennung(r):
                        entry["kennung"] = kennung(r)
                    if r.get("time"):
                        entry["time"] = r["time"]
                    # Ende + Ort mitschleppen, sonst sieht weder die Kollisions-
                    # Prüfung (find_collisions, braucht ende) noch der Knapp-Check
                    # (day_warnings/travel_minutes, braucht ort) die Routine.
                    if r.get("ende"):
                        entry["ende"] = r["ende"]
                    if r.get("ort"):
                        entry["ort"] = r["ort"]
                    # Phase (motiv) und Gruppe (kategorie) mitgeben — die
                    # Ansichten fassen danach zusammen, die KI liest sie.
                    for feld in _MITGEGEBEN:
                        if r.get(feld):
                            entry[feld] = copy.deepcopy(r[feld])
                    # absage_noetig: diese Routine muss bei Abwesenheit aktiv
                    # abgesagt werden (z.B. Geige bei der Lehrerin), fällt NICHT
                    # einfach weg wie Parkour. Steuert den Absage-Alarm.
                    if r.get("absage_noetig"):
                        entry["absage_noetig"] = True
                    # Fällt diese Routine an dem Tag aus (Ferien/Feiertag)?
                    grund = _pause_grund(r["label"], occ.date(), pausen, kennung(r))
                    if grund:
                        entry["ausfall"] = grund
                    # Vom User EINZELN deaktiviert? `aus` = Liste von ISO-Daten an
                    # der Routine. Das Vorkommen wird trotzdem ausgegeben (sichtbar +
                    # wieder-aktivierbar), aber als `deaktiviert` markiert: es löst
                    # keine Kollisions-/Absage-Alarme aus (siehe Guards in
                    # open_alarms/_absage_alarms/conflicts_for_proposed).
                    if day_iso in (r.get("aus") or []):
                        entry["deaktiviert"] = True
                    # Ein einzelnes Vorkommen, das außerhalb verschoben wurde
                    # (am Handy: "nur dieser Termin"; .ics RECURRENCE-ID).
                    ab = abweichungen.get(day_iso)
                    if isinstance(ab, dict):
                        if ab.get("entfaellt"):
                            entry["deaktiviert"] = True
                        else:
                            day_iso = ab.get("tag") or day_iso
                            try:
                                if not (start <= date.fromisoformat(day_iso) <= end):
                                    continue
                            except (TypeError, ValueError):
                                continue
                            for k in ("time", "ende", "label", "ort"):
                                if ab.get(k):
                                    entry[k] = ab[k]
                    _ueber_nacht_markieren(entry)
                    out.setdefault(day_iso, []).append(entry)
            except Exception as e:
                state.push_log(
                    f"[calendar] rrule expand fail layer={layer_name} "
                    f"label={r.get('label')!r}: {e}"
                )

    for day_iso in out:
        out[day_iso].sort(key=lambda e: e.get("time", "00:00"))

    return dict(sorted(out.items()))


def week_view(reference: date | None = None,
              only_default_visible: bool = True) -> dict:
    """
    Liefert die laufende Kalenderwoche (Mo-So) um `reference`. Die Anzeige
    beginnt IMMER am Montag. Die Sidebar-Liste (lists.week_items) ist davon
    unabhängig — sie ist ein flacher, wochenunabhängiger Vorrat und wird von der
    Front separat rechts neben dem Gitter gezeigt.

    only_default_visible=True (Default) zeigt nur Layer mit
    default_visible=True - sonst würde der `erlebt`-Auto-Layer den
    Jetzt-Block bei jeder Antwort fluten. Wenn der User explizit
    nach Erlebtem fragt, ruft die KI das read_calendar-Tool.
    """
    if reference is None:
        reference = date.today()
    monday = reference - timedelta(days=reference.weekday())
    sunday = monday + timedelta(days=6)
    layers = None
    if only_default_visible:
        data = _load_raw()
        layers = [
            name for name, lyr in data.get("layers", {}).items()
            if lyr.get("default_visible", True)
        ]
    return {
        "start": monday.isoformat(),
        "end":   sunday.isoformat(),
        "days":  entries_in_range(monday, sunday, layers=layers),
    }


def month_view(reference: date | None = None,
               only_default_visible: bool = True) -> dict:
    """
    Liefert den Monat um `reference` als GITTER-Daten für eine Monatsansicht:
    alle Tage vom Montag VOR dem Monatsersten bis zum Sonntag NACH dem
    Monatsletzten - also volle Mo-So-Wochenzeilen, damit eine Front ein
    lückenloses Raster zeichnen kann. Welche Tage zum Monat selbst gehören
    (und welche nur Rand-Füllung aus Vor-/Folgemonat sind), erkennt die Front
    über `first`/`last`.

    only_default_visible wie week_view: nur sichtbare Layer, sonst flutet der
    erlebt-Auto-Layer das Gitter. Datums-Arithmetik macht Python, nicht die
    Front - dieselbe Linie wie resolve_range/week_view.
    """
    if reference is None:
        reference = date.today()
    first = reference.replace(day=1)
    last = _month_last_day(first)
    grid_start = first - timedelta(days=first.weekday())      # Mo vor dem 1.
    grid_end = last + timedelta(days=6 - last.weekday())      # So nach dem Letzten
    layers = None
    if only_default_visible:
        data = _load_raw()
        layers = [
            name for name, lyr in data.get("layers", {}).items()
            if lyr.get("default_visible", True)
        ]
    return {
        "month": first.strftime("%Y-%m"),
        "label": f"{_MONTHS_FULL_DE[first.month - 1]} {first.year}",
        "first": first.isoformat(),
        "last":  last.isoformat(),
        "start": grid_start.isoformat(),
        "end":   grid_end.isoformat(),
        "days":  entries_in_range(grid_start, grid_end, layers=layers),
    }


# ── Range-Auflösung ────────────────────────────────────────────────────
# Datums-Arithmetik für relative Zeiträume steht in core/kalender_zeitraum.py
# (reine Rechnung, keine Daten). Hier nur durchgereicht, weil ai.py und die
# Prompt-Profile sie als kalender.RANGE_BUCKETS / kalender.resolve_range
# kennen.
from kalender_zeitraum import RANGE_BUCKETS, resolve_range, _month_last_day  # noqa: E402,F401


# ── Konflikte, Alarme, Abdruck: in core/kalender_konflikte.py ─────────
# (ausgezogen 09.10.2026, Riesen-Grenze). Hier weitergereicht, damit alle
# Aufrufer kalender.<name> behalten; der Import steht am Ende, weil das
# Modul seinerseits kalender braucht.
from kalender_konflikte import (  # noqa: E402,F401
    DEFAULT_PUFFER_MIN, IMPRINT_TAGE, _absage_alarms, _away_blocks,
    _conflict_lines, _fmt_entry, _fmt_min, _interval, _load_config,
    _pause_grund, _to_minutes, conflicts_for_proposed, day_warnings,
    find_collisions, imprint_for_prompt, open_alarms, render_range_for_tool,
    travel_minutes, _WEEKDAYS_FULL_DE)
import kalender_konflikte as _konflikte  # noqa: E402
_konflikte.anschliessen(_load_raw, entries_in_range)
