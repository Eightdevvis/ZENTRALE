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


def create_graph(name, gtype='number', unit=''):
    """
    Neuen Graphen anlegen. Liefert die Definition zurück.
    Wirft ValueError bei leerem Namen oder unbekanntem Typ.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('Name fehlt')
    if gtype not in VALID_TYPES:
        raise ValueError('Typ muss number oder scale sein')

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
    }
    graphs.append(graph)
    _save(graphs)
    return graph


def delete_graph(gid):
    """Definition entfernen und die zugehörige Messwerte-Datei mit löschen."""
    graphs = [g for g in _load() if g.get('id') != gid]
    _save(graphs)
    values = os.path.join(_DATA_DIR, gid + '.json')
    if os.path.exists(values):
        os.remove(values)
