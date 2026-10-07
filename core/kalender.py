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
import kalender_regel
import kalender_speicher
from kalender_ics import ohne_interna

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
    "erlebt": {
        "label":           "Erlebt (auto)",
        "color":           "#888888",
        "default_visible": False,  # default ausgeblendet, sonst noisy
        "entries":         {},
        "routines":        [],
    },
}

_WEEKDAYS_SHORT_DE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_WEEKDAYS_FULL_DE  = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                      "Freitag", "Samstag", "Sonntag"]
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
        entry.update(extras)
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
        entry.update(extras)
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
    sichtbar = [n for n, lyr in data.get("layers", {}).items()
                if lyr.get("default_visible", True)]
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
        routine.update(extras)
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
                    out.setdefault(day_iso, []).append({
                        "layer": layer_name,
                        **_aussen(e),
                    })

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
                    if r.get("time"):
                        entry["time"] = r["time"]
                    # Ende + Ort mitschleppen, sonst sieht weder die Kollisions-
                    # Prüfung (find_collisions, braucht ende) noch der Knapp-Check
                    # (day_warnings/travel_minutes, braucht ort) die Routine.
                    if r.get("ende"):
                        entry["ende"] = r["ende"]
                    if r.get("ort"):
                        entry["ort"] = r["ort"]
                    # absage_noetig: diese Routine muss bei Abwesenheit aktiv
                    # abgesagt werden (z.B. Geige bei der Lehrerin), fällt NICHT
                    # einfach weg wie Parkour. Steuert den Absage-Alarm.
                    if r.get("absage_noetig"):
                        entry["absage_noetig"] = True
                    # Fällt diese Routine an dem Tag aus (Ferien/Feiertag)?
                    grund = _pause_grund(r["label"], occ.date(), pausen)
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


def _to_minutes(hhmm: str) -> int | None:
    """'17:45' → 1065 (Minuten seit Mitternacht). None bei Murks."""
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


# Default-Puffer (Minuten), der bei der Reisezeit-Prüfung auf JEDE Fahrt
# draufkommt - Reserve, falls was schiefläuft. Pro Kalender-Datei über das
# Feld "puffer_min" überschreibbar (Entscheidung 2026-06-06).
DEFAULT_PUFFER_MIN = 15


def _interval(e: dict) -> tuple[int, int] | None:
    """
    (start_min, end_min) eines Eintrags in Minuten-seit-Mitternacht, oder
    None wenn er KEIN echtes Zeit-Intervall ist (time/ende fehlt oder
    ende <= start). Ganztags-Einträge (nur 'label') fallen so bewusst raus.
    """
    s  = _to_minutes(e.get("time", ""))
    en = _to_minutes(e.get("ende", ""))
    if s is None or en is None or en <= s:
        return None
    return s, en


def _fmt_min(m: int) -> str:
    """1065 → '17:45' (für Warnzeilen-Zeitangaben)."""
    return f"{m // 60:02d}:{m % 60:02d}"


def _fmt_entry(e: dict) -> str:
    """'Geigenstunde (17:45-18:30)' für eine ⚠-Zeile."""
    return f"{e.get('label', '?')} ({e.get('time', '?')}-{e.get('ende', '?')})"


def find_collisions(entries: list[dict]) -> list[tuple[dict, dict, str]]:
    """
    Findet überlappende Termin-Paare an EINEM Tag und klassifiziert die Art.

    Kollisions-Modell (entschieden 2026-06-06): ein Eintrag zählt nur dann
    mit, wenn er SOWOHL 'time' ALS AUCH 'ende' hat - erst dann ist er ein
    echtes Zeit-Intervall. Einträge ohne Ende gelten als ganztags/unbestimmt
    und lösen bewusst keine Kollision aus (sonst würde jeder zeitlose Eintrag
    mit allem "kollidieren").

    Reine Intervall-Mathematik → gehört in Python, nicht ins Modell (selbes
    Prinzip wie resolve_range fürs Datum, suche fürs Filtern). Das Modell
    bekommt nur die fertige ⚠-Zeile serviert.

    Rückgabe: Liste von (a, b, kind), a startet nicht nach b. kind ist:
      'voll' – einer steckt komplett im anderen (oder identisch) →
               entweder/oder, splitten bringt nichts.
      'teil' – sie überschneiden sich nur teilweise, jeder hat Exklusiv-Zeit
               → man könnte den ersten früher verlassen.

    Overlap (halboffen): a_start < b_end und b_start < a_end. Termine, die
    sich nur an der Grenze berühren (18:00↔18:00), kollidieren NICHT.
    """
    timed = []
    for e in entries:
        iv = _interval(e)
        if iv:
            timed.append((iv[0], iv[1], e))
    timed.sort(key=lambda t: (t[0], t[1]))

    out: list[tuple[dict, dict, str]] = []
    for i in range(len(timed)):
        a_s, a_e, a = timed[i]
        for j in range(i + 1, len(timed)):
            b_s, b_e, b = timed[j]
            if not (a_s < b_e and b_s < a_e):
                continue  # kein Overlap
            # Umschließt einer den anderen vollständig? Dann 'voll', sonst nur
            # teilweise. (Beide Richtungen prüfen, falls gleicher Startzeit-
            # punkt aber unterschiedliche Länge.)
            a_contains_b = a_s <= b_s and a_e >= b_e
            b_contains_a = b_s <= a_s and b_e >= a_e
            kind = "voll" if (a_contains_b or b_contains_a) else "teil"
            out.append((a, b, kind))
    return out


def _load_config() -> tuple[dict, int]:
    """
    (reisezeiten-Matrix, puffer_min) aus der Kalender-Datei. Beide Felder sind
    optional - fehlen sie, gilt leere Matrix bzw. DEFAULT_PUFFER_MIN. Die Matrix
    ist {von: {nach: minuten}} und darf unvollständig/asymmetrisch sein
    (travel_minutes schaut in beide Richtungen).
    """
    try:
        data = _load_raw()
    except Exception:
        return {}, DEFAULT_PUFFER_MIN
    matrix = data.get("reisezeiten") or {}
    try:
        puffer = int(data.get("puffer_min", DEFAULT_PUFFER_MIN))
    except (TypeError, ValueError):
        puffer = DEFAULT_PUFFER_MIN
    return matrix, puffer


def travel_minutes(von: str | None, nach: str | None,
                   matrix: dict | None = None) -> int | None:
    """
    Grobe Reisezeit zwischen zwei Orten in Minuten - die EINE Nahtstelle für
    Ortsdistanz. Heute liest sie eine handgepflegte, symmetrische Matrix aus
    der Kalender-Datei ('reisezeiten'). Später kann hier ein eigener Router
    (Dijkstra o.ä.) oder ein Transit-Grep andocken, OHNE dass der Kalender-
    Layer drumherum sich ändert - bewusst NIE eine Google-Maps-Anbindung.

    Rückgabe:
      0    – gleicher Ort (kein Weg nötig)
      int  – bekannte grobe Fahrzeit
      None – Orte fehlen oder Paar nicht in der Matrix → KEINE Aussage
             (lieber schweigen als eine Distanz erfinden)
    """
    if not von or not nach:
        return None
    if von == nach:
        return 0
    if matrix is None:
        matrix, _ = _load_config()
    if von in matrix and nach in matrix[von]:
        return matrix[von][nach]
    if nach in matrix and von in matrix[nach]:
        return matrix[nach][von]
    return None


def day_warnings(entries: list[dict],
                 matrix: dict | None = None,
                 puffer_min: int | None = None) -> list[str]:
    """
    Baut die ⚠-Warnzeilen für einen Tag - genau die drei Fälle, die wir
    festgelegt haben (2026-06-06):

      • voll überlappt   → entweder/oder
      • teils überlappt  → ersten früher verlassen + Rest beim nächsten?
                           (bewusste Nachfrage - Ausnahme von "keine Rückfragen")
      • kein Overlap, aber Lücke < Fahrzeit+Puffer → wird örtlich knapp

    Reisezeit kommt aus travel_minutes (handgepflegte Matrix, offline). Fehlt
    sie (Ort unbekannt / Paar nicht gepflegt / gleicher Ort), gibt es KEINE
    Knapp-Warnung - der Layer rät nie über Distanzen.
    """
    if matrix is None or puffer_min is None:
        m, p = _load_config()
        matrix     = m if matrix     is None else matrix
        puffer_min = p if puffer_min is None else puffer_min

    warns: list[str] = []

    # 1) Überlappungen (voll / teil)
    for a, b, kind in find_collisions(entries):
        if kind == "voll":
            warns.append(
                f"⚠ Kollision: {_fmt_entry(a)} und {_fmt_entry(b)} "
                "überlappen sich komplett - entweder/oder."
            )
        else:
            # Teil von b, der nach a-Ende noch übrig wäre (lohnt das Hinrennen?)
            rest = _interval(b)[1] - _interval(a)[1]
            warns.append(
                f"⚠ Teil-Überlappung: {_fmt_entry(a)} und {_fmt_entry(b)} "
                f"überschneiden sich teilweise ({b.get('label', '?')} läuft "
                f"{rest} min länger)."
            )

    # 2) Knappe Übergänge zwischen direkt aufeinanderfolgenden Terminen.
    #    Nur benachbarte Paare prüfen - eine Lücke gibt es immer nur zum
    #    unmittelbar nächsten Termin.
    timed = []
    for e in entries:
        iv = _interval(e)
        if iv:
            timed.append((iv[0], iv[1], e))
    timed.sort(key=lambda t: (t[0], t[1]))
    for i in range(len(timed) - 1):
        _a_s, a_e, a = timed[i]
        b_s, _b_e, b = timed[i + 1]
        if b_s < a_e:
            continue  # überlappt → schon unter (1) behandelt
        tt = travel_minutes(a.get("ort"), b.get("ort"), matrix=matrix)
        if not tt:  # None (unbekannt) oder 0 (gleicher Ort) → kein Hinweis
            continue
        gap  = b_s - a_e
        need = tt + puffer_min
        if gap < need:
            warns.append(
                f"⚠ Knapp: zwischen {a.get('label', '?')} (Ende {_fmt_min(a_e)}) "
                f"und {b.get('label', '?')} ({_fmt_min(b_s)}) nur {gap} min - "
                f"du brauchst ~{need} min (Fahrt {tt} + {puffer_min} Puffer)."
            )
    return warns


def _pause_grund(label: str, day: date, pausen: list[dict]) -> str | None:
    """
    Grund, falls die Routine `label` an `day` pausiert (Ferien etc.), sonst None.

    Die EINE Nahtstelle für Ausfälle - heute aus der manuell gepflegten
    `pausen`-Liste. Wenn die KI später Internet hat, kann hier zusätzlich eine
    automatische Ferien-/Feiertags-Abfrage andocken, ohne dass der Rest sich
    ändert (bewusst nie über Google).
    """
    for p in pausen:
        if p.get("label") != label:
            continue
        try:
            von = date.fromisoformat(p["von"])
            bis = date.fromisoformat(p["bis"])
        except (ValueError, KeyError):
            continue
        if von <= day <= bis:
            return p.get("grund", "Pause")
    return None


def _away_blocks(start: date, end: date, data: dict | None = None) -> list[dict]:
    """
    Findet Mehrtages-Abwesenheits-Blöcke, die den Bereich [start, end]
    überschneiden. Ein Block ist ein Einmal-Eintrag mit `bis`-Feld (Enddatum)
    UND `ort` - z.B. eine Reise:

        "2026-06-08": [{"label": "Ungarn-Reise", "bis": "2026-06-12", "ort": "Ungarn"}]

    Damit weiß der Kalender über mehrere Tage, WO du bist - die Voraussetzung,
    um lokale Termine in der Spanne (Geige daheim, während du in Ungarn bist)
    als unmöglich zu erkennen. Ohne `bis` ist ein Eintrag ein Punkt und löst
    keine Abwesenheit aus.

    Rückgabe: Liste von {von, bis, ort, label} (von/bis als date).
    """
    if data is None:
        data = _load_raw()
    blocks: list[dict] = []
    for layer in data.get("layers", {}).values():
        for day_iso, day_entries in layer.get("entries", {}).items():
            for e in day_entries:
                bis = e.get("bis")
                if not bis:
                    continue
                try:
                    von_d = date.fromisoformat(day_iso)
                    bis_d = date.fromisoformat(bis)
                except ValueError:
                    continue
                if bis_d < von_d:
                    continue
                # Überschneidet der Block den abgefragten Bereich?
                if bis_d >= start and von_d <= end:
                    blocks.append({"von": von_d, "bis": bis_d,
                                   "ort": e.get("ort"), "label": e.get("label", "?")})
    return blocks


def _conflict_lines(day: date, entries: list[dict],
                    away_blocks: list[dict]) -> list[str]:
    """
    Prüft für EINEN Tag, ob ein konkreter Termin in eine Abwesenheits-Spanne
    fällt, in der du an einem ANDEREN Ort bist - der „du bist in Ungarn, hast
    aber Dienstag Geige"-Fall. Liefert fertige ⚠-KONFLIKT-Zeilen.

    NUR Einmal-Termine (unregelmäßig) lösen Alarm aus. Regelmäßige Routinen
    (recurring=True: Geige, Fahrschule, Parkour) fallen auf einer Reise sowieso
    aus - das ist normal, kein Alarm. Der Unterschied (Sasha 2026-06-07): bei
    Routinen verpasst man Erwartbares, bei Einzelterminen etwas Besonderes, das
    man evtl. aktiv absagen/verschieben muss.

    Modell-Verhalten (Persona): bei so einem KONFLIKT vergewissert sich die KI
    einmal beim User (stimmt die Reise? stimmt der Termin?) und schlägt dann
    laut Alarm (Text + Bild-Marker [[bild: alarm]]) - statt blind oder stumm.
    Python liefert nur das Signal, die KI führt die Verifikation.

    Kein Konflikt, wenn der Termin am selben Ort wie das Reiseziel liegt
    (du hast vor Ort was geplant). Ort unbekannt → trotzdem flaggen: du bist
    verreist, lokale Termine sind dann höchst wahrscheinlich nicht machbar.
    """
    lines: list[str] = []
    for blk in away_blocks:
        if not (blk["von"] <= day <= blk["bis"]):
            continue
        for e in entries:
            if not e.get("time"):
                continue  # nur konkrete (zeitlich verortete) Termine
            if e.get("label") == blk["label"]:
                continue  # der Reise-Eintrag nicht gegen sich selbst
            if e.get("recurring"):
                continue  # Routine → fällt auf der Reise sowieso aus, kein Alarm
            appt_ort = e.get("ort")
            if blk["ort"] and appt_ort and appt_ort == blk["ort"]:
                continue  # gleicher Ort wie Reiseziel → kein Konflikt
            wd = _WEEKDAYS_FULL_DE[day.weekday()]
            ort_str = f" @ {appt_ort}" if appt_ort else ""
            # NUR Fakten - was die KI damit tun soll (rückversichern, Alarm),
            # steht in der read_calendar-Tool-Beschreibung, NICHT hier. Sonst
            # liest das Modell die Regie-Anweisung wörtlich vor.
            #
            # ANMERKUNG (2026-06-07): Versuch, diese Zeile parallel zur ABSAGEN-
            # Zeile auf „Termin X musst du verschieben oder absagen" umzubauen,
            # wurde GEMESSEN ZURÜCKGEROLLT - das „verschieben oder absagen" steht
            # in T1 mit im Kontext und ließ das 9B beim expliziten „lösch den"
            # zögern (T1-Löschquote 100 %→80 %), ohne die T2-Zuordnung zu heben
            # (bench_calendar_delete.py, N=20). Daher bewusst die nüchterne
            # „überschneidet sich"-Form behalten.
            lines.append(
                f"⚠ KONFLIKT: Reise {blk['label']} "
                f"({blk['von'].strftime('%d.%m.')}-{blk['bis'].strftime('%d.%m.')}, "
                f"{blk['ort'] or 'unterwegs'}) überschneidet sich mit Einzeltermin "
                f"'{e['label']}'{ort_str} am {wd} {day.strftime('%d.%m.')}."
            )
    return lines


def _absage_alarms(away_blocks: list[dict]) -> list[str]:
    """
    Findet Routinen, die in eine Reise-Spanne fallen UND aktiv abgesagt werden
    müssen (`absage_noetig`, z.B. Geige bei der Lehrerin). Liefert pro Reise und
    Routine GENAU EINE Alarm-Zeile - egal über wie viele Wochen die Reise geht
    (Sasha sagt einmal „bin von-bis weg", nicht jede Woche neu).

    Abgegrenzt von _conflict_lines (Einmal-Termine, die man verpasst): hier geht
    es um regelmäßige Termine mit Absage-PFLICHT - ein To-do, kein Verpassen.
    Normale Routinen ohne `absage_noetig` (Parkour, Fahrschule) erscheinen hier
    nicht; die fallen auf Reisen einfach weg.
    """
    lines: list[str] = []
    for blk in away_blocks:
        seen: set[str] = set()
        # entries_in_range liest selbst aus der Kalender-Datei und expandiert
        # die Routinen über die Reise-Spanne - so finden wir jedes Vorkommen.
        for day_iso, ents in entries_in_range(blk["von"], blk["bis"]).items():
            for e in ents:
                if not (e.get("recurring") and e.get("absage_noetig")):
                    continue
                if e.get("ausfall"):
                    continue  # fällt eh aus (Ferien) → nichts abzusagen
                if e.get("deaktiviert"):
                    continue  # vom User einzeln deaktiviert → kein Alarm
                if e["label"] in seen:
                    continue
                appt_ort = e.get("ort")
                if blk["ort"] and appt_ort and appt_ort == blk["ort"]:
                    continue  # findet am Reiseziel statt → kein Absagen nötig
                seen.add(e["label"])
                # Formulierung (Umbau 2026-06-07, gemessen): die alte Zeile
                # „Routine 'X' liegt in Reise Y - Pflicht-Absage" las das 9B als
                # Kollisions-Narrativ und klebte sie an einen anderen (oft schon
                # gelöschten) Termin → Alarm-Zuordnung nur 30 % (bench_calendar_
                # delete.py). Jetzt: AKTION + Subjekt nach vorn, der eigene
                # Wochentag des Vorkommens (unterscheidet die Routine vom
                # Einmal-Termin an einem anderen Tag), die Reise als GRUND nach
                # hinten. Immer noch reine Fakten an Sasha, keine Regie-Anweisung
                # ans Modell (die steht in der Tool-/Persona-Beschreibung).
                # Formulierung gemessen prod-treu (N=20, temp 0.7): diese Zeile vs.
                # die alte „Routine 'X' liegt in Reise Y - Pflicht-Absage" → T2-Alarm-
                # Zuordnung 100 % vs 80 %, Episode 85 % vs 60 % (memory/ki/bench_history.md P5).
                # Der Umbau trägt also echt, nicht nur ein temp-1-Artefakt.
                d  = date.fromisoformat(day_iso)
                wd = _WEEKDAYS_FULL_DE[d.weekday()]
                wo = f" (bei {appt_ort})" if appt_ort else ""
                lines.append(
                    f"⚠ {e['label']} absagen: dein wöchentlicher Termin am {wd} "
                    f"({d.strftime('%d.%m.')}) fällt in die Reise {blk['label']} "
                    f"({blk['von'].strftime('%d.%m.')}-"
                    f"{blk['bis'].strftime('%d.%m.')}) - du musst aktiv "
                    f"absagen{wo}, er entfällt nicht von selbst."
                )
    return lines


def render_range_for_tool(start: date, end: date,
                          layers: list[str] | None = None,
                          suche: str | None = None) -> str:
    """
    Formatiert die Einträge in [start, end] als Tool-Antwort für die KI.

    Kernpunkt gegen die Wochentag-Halluzination: jeder Tag kommt MIT
    ausgeschriebenem Wochentag ("Dienstag, 09.06.2026: …"). Vorher gab das
    Tool nackte ISO-Daten zurück und das Modell rechnete den Wochentag selbst
    aus - und verrechnete sich regelmäßig ("Montag" statt "Dienstag"). Steht
    der Wochentag fertig da, muss das Modell nur noch abschreiben.

    `suche`: optionaler Label-Substring-Filter (case-insensitive). Bei Fragen
    nach EINER Aktivität ("wann hab ich Fahrschule?") gibt das Tool damit nur
    die passenden Zeilen zurück, statt der ganzen Monatswand. Grund: schwache
    Modelle (qwen3-Familie) scheitern daran, eine lange Liste selbst nach
    einem Begriff zu durchsuchen - sie sagen dann "keine gefunden" obwohl der
    Eintrag dasteht, kotzen die Rohliste aus oder übersehen Treffer (z.B. den
    Donnerstag). Filtern ist deterministische Arbeit → macht Python, nicht das
    Modell. Selbes Prinzip wie resolve_range fürs Datums-Rechnen.

    Leerer Zeitraum → klare Ansage, damit die KI "nichts geplant" von
    "weiß ich nicht" unterscheiden kann.
    """
    days = entries_in_range(start, end, layers=layers)
    # Label-Filter in Python anwenden, BEVOR gerendert wird.
    if suche:
        needle = suche.casefold()
        days = {
            day_iso: matches
            for day_iso, entries in days.items()
            if (matches := [e for e in entries
                            if needle in e.get("label", "").casefold()])
        }
    span = (f"Kalender {start.strftime('%d.%m.%Y')} bis "
            f"{end.strftime('%d.%m.%Y')}")
    head = f"{span} (gefiltert nach {suche!r}):" if suche else f"{span}:"
    if not days:
        leer = (f"Keine Einträge mit {suche!r} in diesem Zeitraum."
                if suche else "Keine Einträge in diesem Zeitraum.")
        return head + "\n" + leer
    # Reine Arbeitsdaten: NUR die Terminliste. Die ⚠-Warnungen (Reise-KONFLIKT,
    # ABSAGEN, Tages-Kollision) sind hier BEWUSST RAUS - sie kaperten beim
    # kleinen Modell die Aufmerksamkeit (Löschen scheiterte, Add wurde blind).
    # Sie laufen jetzt über den Alarm-Kanal (open_alarms → state → Dashboard-Ecke
    # + ai._alarm_prompt), randständig statt zwischen die Termine gemischt. Die
    # KI darf den Kalender dadurch wieder frei lesen, ohne abgelenkt zu werden.
    lines = [head]
    for day_iso, entries in days.items():
        d = date.fromisoformat(day_iso)
        wd = _WEEKDAYS_FULL_DE[d.weekday()]
        lines.append(f"{wd}, {d.strftime('%d.%m.%Y')}:")
        for e in entries:
            # Fällt die Routine aus (Ferien/Feiertag)? Dann als Erinnerung
            # zeigen statt als normalen Termin - der User soll wissen, dass
            # NICHTS ist, nicht umsonst hinfahren.
            if e.get("ausfall"):
                lines.append(f"  ℹ {e['label']} fällt aus ({e['ausfall']}) "
                             f"- kein Termin an diesem Tag")
                continue
            if e.get("deaktiviert"):
                lines.append(f"  ℹ {e['label']} ist an diesem Tag deaktiviert "
                             f"- findet nicht statt")
                continue
            # Zeit MIT Ende anzeigen, wenn vorhanden ('17:45-18:30'),
            # sonst nur Startzeit - das Modell sieht so die Dauer direkt.
            if e.get("time") and e.get("ende"):
                t = f"{e['time']}-{e['ende']} "
            elif e.get("time"):
                t = f"{e['time']} "
            else:
                t = ""
            ort = f" @ {e['ort']}" if e.get("ort") else ""
            # Mehrtages-Block: Spanne sichtbar machen ('… (bis 12.06.)').
            bis = ""
            if e.get("bis"):
                try:
                    bis = f" (bis {date.fromisoformat(e['bis']).strftime('%d.%m.')})"
                except ValueError:
                    pass
            lines.append(f"  [{e['layer']}] {t}{e['label']}{bis}{ort}")
        # (Keine ⚠-Warnzeilen mehr hier - die laufen über den Alarm-Kanal,
        #  siehe open_alarms. Der Read bleibt saubere Terminliste.)
    return "\n".join(lines)


# ── Imprint: was ansteht, ohne Tool-Runde ──────────────────────────────

IMPRINT_TAGE = int(os.environ.get("ZENTRALE_IMPRINT_TAGE", "1"))


def imprint_for_prompt(tage: int | None = None) -> str:
    """Der nahe Horizont, fest im Prompt: heute und morgen.

    Das ersetzt den gelöschten Kalender-Spiegel — und zwar in der richtigen
    Richtung. Der Spiegel wollte der KI den Tag präsent machen, indem er in
    den Kalender SCHRIEB; hier liest sie ihn einfach mit. Nichts wird
    verändert, also braucht es auch keine Erlaubnis.

    Warum überhaupt mitgeliefert, wo es doch `read_calendar` gibt: „was
    steht heute an" ist die häufigste Frage überhaupt, und jede Tool-Runde
    kostet einen kompletten zweiten Call mit vollem Präfix. Zwei Tage sind
    ein paar Zeilen — billiger als die Runde, die sie erspart.

    ── Achtung, das widerspricht einer alten Entscheidung ──
    2026-06 wurde der Kalender BEWUSST aus dem Prompt genommen (siehe die
    Notiz über `RANGE_BUCKETS`): Kleben skaliert nicht, und das damalige
    14B-Modell antwortete faul aus dem geklebten Block, statt für andere
    Zeiträume das Tool zu rufen. Beides gilt hier NICHT:
      * Geklebt wird nur der nahe Horizont, nicht „irgendein Zeitraum" —
        die Skalierungs-Sorge trifft genau das nicht.
      * Gegen die Faulheit steht der Schlusssatz des Blocks, der die Grenze
        ausdrücklich benennt. Bleibt er wirkungslos, gehört der Imprint
        wieder raus — das ist der Prüfstein.

    Sichtbarkeits-Regel: nur Layer, die auch Sasha sieht
    (`default_visible`). Die KI soll nichts wissen, was er nicht nachlesen
    kann — genau diese Asymmetrie hat der `erlebt`-Layer erzeugt.

    Warum am Ende eine Verhaltensregel steht (18.08.2026): weil der Block
    im gecachten Kopf sitzt und der Jetzt-Block die Uhr jede Runde neu
    setzt, rechnete sie bei JEDEM Turn nach, wie lange es noch hin ist —
    "in 16 Minuten", "noch 3 Minuten", obwohl Sasha den Termin laengst
    gesehen hatte. Der Alarm-Block (`ai._alarm_prompt`) hat gegen genau das
    seit jeher einen Satz ("EINMAL aktiv zur Sprache bringen, nicht in jede
    Antwort quetschen"); der Imprint hatte keinen. Das war die ganze
    Asymmetrie. Ein Assistent, der dreimal mahnt, wird abgeschaltet — das
    ist die eigentliche Gefahr proaktiver Schichten.

    Vorlaufzeiten (zwei Tage vor der Abreise ans Packen denken) gehören
    NICHT hierher, sondern in die Schemen-Mechanik: die kennt die Vorhaben
    und kann entscheiden, was wie früh sichtbar werden muss. `tage` ist der
    Hebel, an dem sie das später dreht.
    """
    tage = IMPRINT_TAGE if tage is None else tage
    if tage < 0:
        return ""
    heute = date.today()
    try:
        data = _load_raw()
    except Exception:
        return ""
    layers = [name for name, lyr in data.get("layers", {}).items()
              if lyr.get("default_visible", True)]
    liste = render_range_for_tool(heute, heute + timedelta(days=tage),
                                  layers=layers)
    grenze = ("Das ist NUR der nahe Horizont. Für jeden anderen Zeitraum "
              "(nächste Woche, ein bestimmtes Datum, 'wann war X') "
              "read_calendar rufen — aus diesem Block lässt sich das "
              "nicht beantworten.\n\n"
              "Und: das hier ist stehender Hintergrund, keine Meldung. Sasha "
              "sieht denselben Kalender vor sich. Einen Termin sagst du "
              "EINMAL an; hat er ihn zur Kenntnis genommen, ist das Thema "
              "durch — auch wenn die Uhrzeit näher rückt. Kein zweiter "
              "Hinweis, kein Countdown. Nur wenn er selbst etwas sagt, das "
              "damit kollidiert, sagst du es nochmal.")
    return f"## Was ansteht\n{liste}\n\n{grenze}"


def conflicts_for_proposed(layer: str, day: str, label: str,
                           time: str | None = None, ende: str | None = None) -> list[str]:
    """
    Prüft einen NOCH NICHT geschriebenen Einmal-Termin HYPOTHETISCH auf Konflikte
    mit dem schon belegten Tag - ohne ihn zu speichern. Gedacht für die Erlaubnis-
    Frage (ai._permission_question): Sasha soll im JA/NEIN-Dialog schon sehen, ob
    der geplante Termin in eine Reise fällt (⚠ KONFLIKT) oder mit einem
    bestehenden Termin kollidiert (⚠ Kollision/Teil-Überlappung/Knapp) - BEVOR
    sie bestätigt, nicht erst hinterher als Tool-Ergebnis.

    Trick gegen die „Konflikt entsteht erst durchs Schreiben"-Henne-Ei-Falle: wir
    holen die echten Einträge des Tages (alle Layer), hängen den geplanten Termin
    als Phantom-Eintrag dran und lassen die GLEICHEN Konflikt-Funktionen laufen
    wie der Render-Pfad (day_warnings + _conflict_lines) - eine Logik, kein
    Doppel-Code. _absage_alarms (Geige-Pflichtabsage) bleibt bewusst außen vor:
    das ist ein Reise-To-do, kein Konflikt DIESES Termins, und wäre im Add-Dialog
    nur Rauschen.

    Hinweis: _conflict_lines flaggt nur Termine MIT Uhrzeit; ein ganztägiger
    Eintrag (kein `time`) löst also keine Reise-KONFLIKT-Zeile aus - dasselbe
    Verhalten wie im normalen read_calendar-Pfad, bewusst konsistent gehalten.

    Gibt [] bei ungültigem Datum ODER wenn der geplante Termin konfliktfrei ist.
    """
    try:
        d = date.fromisoformat((day or "").strip())
    except ValueError:
        return []
    existing = [e for e in entries_in_range(d, d).get(d.isoformat(), [])
                if not e.get("deaktiviert")]   # deaktivierte zählen nicht mit
    phantom: dict = {"layer": (layer or "termine"),
                     "label": (label or "(neuer Termin)")}
    t = (time or "").strip()
    if t:
        phantom["time"] = t
        if (ende or "").strip():          # erst mit Ende ein Intervall (find_collisions)
            phantom["ende"] = ende.strip()
    entries = sorted(existing + [phantom], key=lambda e: e.get("time", "00:00"))
    away = _away_blocks(d, d)
    return day_warnings(entries) + _conflict_lines(d, entries, away)


def open_alarms(horizon_days: int = 30) -> list[dict]:
    """
    Berechnet das KOMPLETTE Set offener Kalender-Alarme von heute über den
    Horizont (Default 30 Tage) und liefert strukturierte Dicts. Das ist die
    EINE Quelle des Alarm-Kanals: kalender → state.set_alarms → (Dashboard-Ecke
    im KI-Canvas + ai._alarm_prompt "offene Erinnerungen"). Bewusst NICHT mehr
    inline in render_range_for_tool - dort kaperten die ⚠-Zeilen die
    Aufmerksamkeit des kleinen Modells (Löschen scheiterte, Add wurde blind).

    Sammelt aus den GLEICHEN Rechenfunktionen wie früher der Render-Pfad, damit
    die Konflikt-Logik an EINER Stelle bleibt (DRY):
      - _absage_alarms(away_blocks) → Pflicht-Absagen (Routine in Reise)
      - _conflict_lines(d, entries, away) → Einzeltermin in Reise
      - day_warnings(entries) → Tages-Kollision / Teil-Überlappung / Knapp

    Form je Alarm: {"id": <stabiler 8-Hex-Hash>, "kind": str, "text": str}.
    'text' ist die fertige Zeile OHNE führendes "⚠ " - jede Senke setzt ihr
    eigenes Symbol (Dreieck im Canvas, "- " im Prompt). 'id' ist stabil über
    Recomputes (md5 über kind+text), damit das Frontend nicht bei jedem Poll
    neu aufflackert. Reihenfolge: Reise-Absagen zuerst (vergisst man am
    leichtesten), dann tagesweise Konflikte + Kollisionen.
    """
    today = date.today()
    end   = today + timedelta(days=max(0, horizon_days))
    away_blocks = _away_blocks(today, end)

    raw: list[tuple[str, str]] = []   # (kind, roh-Zeile) in Anzeige-Reihenfolge
    for line in _absage_alarms(away_blocks):
        raw.append(("ABSAGEN", line))
    for day_iso, entries in entries_in_range(today, end).items():
        d = date.fromisoformat(day_iso)
        entries = [e for e in entries if not e.get("deaktiviert")]  # deaktivierte: kein Alarm
        for line in _conflict_lines(d, entries, away_blocks):
            raw.append(("KONFLIKT", line))
        for line in day_warnings(entries):
            # kind aus dem Zeilenkopf ableiten (Kollision/Teil-Überlappung/Knapp)
            kind = line.split(":", 1)[0].replace("⚠", "").strip() or "Warnung"
            raw.append((kind, line))

    alarms: list[dict] = []
    for kind, line in raw:
        text = line.lstrip("⚠").strip()
        aid  = hashlib.md5(f"{kind}|{text}".encode("utf-8")).hexdigest()[:8]
        alarms.append({"id": aid, "kind": kind, "text": text})
    return alarms
