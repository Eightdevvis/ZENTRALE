# core/melodies.py
# Melodie-Registry für das Klavier-Werkzeug (Canvas-Exhibit „Klavier").
#
# Eine Melodie ist eine flache Liste von Noten-Ereignissen, so wie sie auf der
# Computertastatur gespielt wurden:
#   n – MIDI-Notennummer (21–108, also A0 bis C8; 60 = C4/mittleres C)
#   t – Startzeit in Millisekunden ab Aufnahmebeginn
#   d – Klingdauer in Millisekunden (wie lange die Taste gehalten wurde)
#
# Bewusst KEIN Takt/Tempo/Notenwert: aufgezeichnet wird, was gespielt wurde
# (freies Timing in ms). Das Notensystem im Browser leitet die Tonhöhe daraus
# ab und zeigt die Dauer nur grob (voller/hohler Notenkopf) — Quantisierung
# wäre eine eigene Baustelle und würde das Gespielte verfälschen.
#
# Muster 1:1 wie core/notes.py / core/graphs.py: eine Registry-Datei
# data/melodies.json, _load/_save mit datasync.notify_change (Peer-Push),
# dateisystem-sichere ids via _slug.

import os
import re
import json
import unicodedata
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
_REGISTRY = os.path.join(_DATA_DIR, 'melodies.json')

MIN_NOTE, MAX_NOTE = 21, 108     # A0 … C8 (Klaviatur-Umfang)
MAX_NOTES = 5000                 # Deckel pro Melodie (ein Tastatur-Spiel ist kurz)


def _load():
    """Registry von Disk lesen (leere Liste wenn noch nichts aufgenommen)."""
    if not os.path.exists(_REGISTRY):
        return []
    with open(_REGISTRY, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(melodies):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(melodies, f, indent=2, ensure_ascii=False)
    # Echte Änderung geschrieben → Peer-Push anstoßen (no-op ohne AUTOPUSH).
    try:
        from datasync import notify_change
        notify_change(_REGISTRY)
    except Exception:
        pass


def _slug(name):
    """Namen → dateisystem-sichere id-Basis (ä→a, nur a-z0-9 und _). Die id
    steht in der URL – kein Path-Traversal, keine Sonderzeichen."""
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s or 'melodie'


def _clean_notes(raw):
    """
    Beliebigen API-Body auf eine gültige Notenliste normalisieren: nur Dicts mit
    brauchbarer Tonhöhe, Zeiten auf ganze Millisekunden ≥ 0 geklemmt, nach
    Startzeit sortiert, auf MAX_NOTES gedeckelt. Wirft ValueError, wenn am Ende
    keine einzige Note übrig bleibt (eine leere Melodie ist keine).
    """
    out = []
    for e in (raw or []):
        if not isinstance(e, dict):
            continue
        try:
            n = int(e.get('n'))
            t = int(e.get('t', 0))
            d = int(e.get('d', 0))
        except (TypeError, ValueError):
            continue
        if not (MIN_NOTE <= n <= MAX_NOTE):
            continue
        out.append({'n': n, 't': max(0, t), 'd': max(1, d)})
    if not out:
        raise ValueError('melodie ist leer')
    out.sort(key=lambda e: (e['t'], e['n']))
    return out[:MAX_NOTES]


def duration_ms(notes):
    """Gesamtlänge einer Melodie: bis zum Verklingen der letzten Note."""
    return max([e['t'] + e['d'] for e in notes], default=0)


def list_melodies():
    """Alle Melodien inkl. ihrer Noten (sie sind klein — kein Nachladen nötig)."""
    return _load()


def get_melody(mid):
    """Eine Melodie oder None."""
    return next((m for m in _load() if m.get('id') == mid), None)


def create_melody(name, notes):
    """
    Aufgezeichnete Melodie ablegen. Liefert den Datensatz zurück.
    Wirft ValueError bei leerem Namen oder leerer Notenliste.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('name fehlt')
    notes = _clean_notes(notes)

    melodies = _load()
    base = 'm_' + _slug(name)
    existing = {m.get('id') for m in melodies}
    mid, n = base, 2
    while mid in existing:
        mid = base + '_' + str(n)
        n += 1

    mel = {
        'id': mid,
        'name': name,
        'created': datetime.now().isoformat(),
        'dur': duration_ms(notes),
        'notes': notes,
    }
    melodies.append(mel)
    _save(melodies)
    return mel


def rename_melody(mid, name):
    """Melodie umbenennen (die id bleibt, damit Referenzen halten).
    Wirft KeyError bei unbekannter id, ValueError bei leerem Namen."""
    name = (name or '').strip()
    if not name:
        raise ValueError('name fehlt')
    melodies = _load()
    m = next((x for x in melodies if x.get('id') == mid), None)
    if m is None:
        raise KeyError(mid)
    m['name'] = name
    _save(melodies)
    return m


def delete_melody(mid):
    """Melodie löschen (still, wenn es sie gar nicht gibt)."""
    melodies = _load()
    rest = [m for m in melodies if m.get('id') != mid]
    if len(rest) != len(melodies):
        _save(rest)
    return True
