# core/graphs.py
# Dynamische Graph-Registry für das Lifestyle-Graph-Werkzeug.
#
# Unterschied zu core/categories.py: Die Data-Collection-Kategorien dort
# sind HART verdrahtet (Code-Änderung nötig). Graphen hier werden ZUR
# LAUFZEIT vom Dashboard angelegt (Mittel-Exhibit „Graph") und in
# data/graphs.json persistiert – kein Python-Edit nötig.
#
# Die eigentlichen Messwerte teilen sich die Infrastruktur der
# Data-Collection: geschrieben über /api/log, gelesen über
# /api/data/<graph_id>, abgelegt in data/<graph_id>.json. Diese Datei hier
# verwaltet also nur die DEFINITIONEN (Name, Typ, Einheit), nicht die Werte.

import os
import re
import json
import unicodedata
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
_REGISTRY = os.path.join(_DATA_DIR, 'graphs.json')

# number = freie Messwerte (echte Kurve), scale = 1–5 Bewertung,
# time   = Uhrzeit pro Datum (value = Minuten seit Mitternacht, 0–1439),
# period = Zeitspanne pro Datum (value = Start-Minute, end = End-Minute;
#          End < Start heißt über Mitternacht, z.B. Schlaf 23:00–07:00).
# Die Werte teilen sich wie gehabt /api/log; time/period legen ihre Minuten
# als Zahl ab (period zusätzlich 'end'), brauchen also kein neues Storage.
VALID_TYPES = ('number', 'scale', 'time', 'period')


def _load():
    """Registry von Disk lesen (leere Liste wenn noch nichts angelegt)."""
    if not os.path.exists(_REGISTRY):
        return []
    with open(_REGISTRY, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(graphs):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(graphs, f, indent=2, ensure_ascii=False)
    # Echte Änderung geschrieben → Peer-Push anstoßen (no-op ohne AUTOPUSH).
    try:
        from datasync import notify_change
        notify_change(_REGISTRY)
    except Exception:
        pass


def _slug(name):
    """
    Namen → dateisystem-sichere id-Basis. ASCII-fold (ä→a), nur a-z0-9 und _.
    Wichtig, weil die id direkt als Dateiname data/<id>.json landet – kein
    Path-Traversal, keine Sonderzeichen.
    """
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s or 'graph'


def list_graphs():
    """Alle Graph-Definitionen."""
    return _load()


def _norm_hhmm(s):
    """'HH:MM' validieren/normalisieren. '' bleibt '' (kein Reminder). Wirft
    ValueError bei Unsinn. Genutzt für die Reminder-Uhrzeit (remind_at)."""
    s = (s or '').strip()
    if not s:
        return ''
    m = re.match(r'^(\d{1,2}):(\d{2})$', s)
    if not m:
        raise ValueError('uhrzeit muss HH:MM sein')
    h, mi = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        raise ValueError('uhrzeit ausserhalb 00:00–23:59')
    return '%02d:%02d' % (h, mi)


def create_graph(name, gtype='number', unit='', remind=False, remind_at=''):
    """
    Neuen Graphen anlegen. Liefert die Definition zurück.
    Wirft ValueError bei leerem Namen, unbekanntem Typ oder kaputter Uhrzeit.
    remind/remind_at: optionaler Tages-Reminder (siehe set_remind).
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('Name fehlt')
    if gtype not in VALID_TYPES:
        raise ValueError('Typ muss number oder scale sein')
    remind_at = _norm_hhmm(remind_at)
    remind = bool(remind)
    if remind and not remind_at:
        remind_at = '20:00'   # an, aber keine Uhrzeit → sinnvoller Default

    graphs = _load()
    # id aus dem Namen ableiten, kollisionsfrei machen (g_<slug>, _2, _3 …)
    base = 'g_' + _slug(name)
    existing = {g['id'] for g in graphs}
    gid, n = base, 2
    while gid in existing:
        gid = base + '_' + str(n)
        n += 1

    graph = {
        'id': gid,
        'name': name,
        'type': gtype,
        'unit': (unit or '').strip() if gtype == 'number' else '',
        'created': datetime.now().isoformat(),
        'predict': False,   # Lücken-Tage in der lifestyle-Box aus dem Schnitt schätzen?
        'remind': remind,   # täglich ans Eintragen erinnern, bis für den Tag geloggt?
        'remind_at': remind_at,   # ab welcher Uhrzeit erinnert wird ('' = aus)
    }
    graphs.append(graph)
    _save(graphs)
    return graph


def set_predict(gid, on):
    """
    Vorhersage-Flag eines Graphen setzen/löschen. Ist es gesetzt, schätzt die
    lifestyle-Box fehlende (nicht eingetragene) Tage aus dem Schnitt der letzten
    echten Werte und zeigt sie blass/schraffiert. Default aus — bewusst nur dort
    sinnvoll, wo ein stabiles Muster existiert (z.B. Schlaf). Liefert den Graphen.
    Wirft KeyError bei unbekanntem Graphen.
    """
    graphs = _load()
    g = next((x for x in graphs if x.get('id') == gid), None)
    if g is None:
        raise KeyError(gid)
    g['predict'] = bool(on)
    _save(graphs)
    return g


def set_remind(gid, on, at=None):
    """
    Tages-Reminder eines Graphen setzen/löschen. Ist er an, melden die Fronten
    (Dashboard + TUI) ab der Uhrzeit »bitte eintragen«, SOLANGE für den heutigen
    Tag noch kein Wert da ist — sobald geloggt, ist der Reminder erfüllt und
    verschwindet (siehe due_reminders). Default aus. Liefert den Graphen.
    `at` (HH:MM): None = Uhrzeit unverändert lassen, sonst neu setzen ('' = leer).
    Wirft KeyError bei unbekanntem Graphen, ValueError bei kaputter Uhrzeit.
    """
    graphs = _load()
    g = next((x for x in graphs if x.get('id') == gid), None)
    if g is None:
        raise KeyError(gid)
    g['remind'] = bool(on)
    if at is not None:
        g['remind_at'] = _norm_hhmm(at)
    if g['remind'] and not g.get('remind_at'):
        g['remind_at'] = '20:00'   # an, aber keine Uhrzeit → sinnvoller Default
    _save(graphs)
    return g


def _values_path(gid):
    """Pfad der Messwert-Datei eines Graphen (dieselbe, die /api/log schreibt)."""
    return os.path.join(_DATA_DIR, gid + '.json')


def read_values(gid):
    """Messwerte eines Graphen als Liste (leer, wenn nichts/kaputt).
    Lese-Pendant zu /api/data/<gid>, aber ohne laufendes Backend."""
    path = _values_path(gid)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            rows = json.load(f)
    except Exception:
        return []
    return rows if isinstance(rows, list) else []


def logged_on(gid, day):
    """True, wenn data/<gid>.json schon einen Eintrag mit date==day trägt."""
    return any(isinstance(e, dict) and e.get('date') == day for e in read_values(gid))


def log_value(gid, day, value, end=None):
    """
    Einen Messwert für `day` (ISO-Datum) schreiben — ohne Umweg übers Backend.

    Format und Datei sind IDENTISCH zu /api/log mit upsert=True (ein Eintrag
    pro Tag, `logged_at` als Zeitstempel); `end` gesetzt heißt Zeitspanne
    (value = Start-Minute, end = End-Minute). Bewusst eine zweite Schreibstelle
    neben `ui/app.py::api_log`: der Morgen-Messenger (scripts/morgen_*) läuft,
    BEVOR ZENTRALE wach ist — er kann sich auf keinen HTTP-Port verlassen.
    Wer beides ändert, muss beide Stellen anfassen.
    """
    rows = [e for e in read_values(gid)
            if not (isinstance(e, dict) and e.get('date') == day)]
    entry = {'date': day, 'value': value}
    if end is not None:
        entry['end'] = end
    entry['logged_at'] = datetime.now().isoformat()
    rows.append(entry)
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_values_path(gid), 'w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    return entry


def _logged_today(gid, today):
    """True, wenn data/<gid>.json schon einen Eintrag mit date==today trägt.
    Quelle ist dieselbe Messwert-Datei, die /api/log schreibt."""
    return logged_on(gid, today)


def due_reminders(now=None):
    """
    Graphen mit JETZT fälligem Tages-Reminder: remind=an, die Tages-Uhrzeit ist
    erreicht/überschritten UND für HEUTE wurde noch kein Wert eingetragen. Sobald
    für den Tag geloggt ist, fällt der Graph hier raus (Reminder erfüllt).
    Liefert [{id, name, remind_at}, …]. `now` = datetime (Default: jetzt).
    Geteilte Quelle für monolith/laptop (Modal) und TUI (Nag).
    """
    now = now or datetime.now()
    today = now.date().isoformat()
    cur = now.strftime('%H:%M')   # HH:MM, nullgepolstert → String-Vergleich ok
    due = []
    for g in _load():
        if not g.get('remind'):
            continue
        at = g.get('remind_at') or ''
        if at and cur < at:
            continue
        if _logged_today(g.get('id'), today):
            continue
        due.append({'id': g.get('id'), 'name': g.get('name'), 'remind_at': at})
    return due


def delete_graph(gid):
    """Definition entfernen und die zugehörige Messwerte-Datei mit löschen."""
    graphs = [g for g in _load() if g.get('id') != gid]
    _save(graphs)
    values = os.path.join(_DATA_DIR, gid + '.json')
    if os.path.exists(values):
        os.remove(values)
