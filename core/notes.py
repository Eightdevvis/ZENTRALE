# core/notes.py
# Notiz-Registry für das TUI-Notiz-Werkzeug.
#
# Eine Notiz ist eine geordnete Folge von Blöcken, die sich auf der Seite
# automatisch untereinander stapeln (kein 2D-Canvas). Es gibt drei Blocktypen:
#   text  – mehrzeiliger Fließtext
#   list  – Checklisten-Einträge (gleiche Item-Shape wie core/lists.py)
#   float – verstreute Begriffe ("Ideen-Wolke"): Terme tauchen mit Abstand
#           zueinander in der Box auf; Position wird beim Zeichnen deterministisch
#           gestreut (nicht gespeichert), damit die Daten stabil/diffbar bleiben.
#
# Muster 1:1 wie core/graphs.py: eine Registry-Datei data/notes.json, _load/_save
# mit datasync.notify_change (Peer-Push), dateisystem-sichere ids via _slug.
# Die reinen Layout-Helfer (block_height/stack_layout/float_positions) sind
# curses-frei und ohne Terminal testbar; die TUI zeichnet damit.

import os
import re
import json
import unicodedata
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
_REGISTRY = os.path.join(_DATA_DIR, 'notes.json')

VALID_TYPES = ('text', 'list', 'float')


def _load():
    """Registry von Disk lesen (leere Liste wenn noch nichts angelegt)."""
    if not os.path.exists(_REGISTRY):
        return []
    with open(_REGISTRY, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save(notes):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_REGISTRY, 'w', encoding='utf-8') as f:
        json.dump(notes, f, indent=2, ensure_ascii=False)
    # Echte Änderung geschrieben → Peer-Push anstoßen (no-op ohne AUTOPUSH).
    try:
        from datasync import notify_change
        notify_change(_REGISTRY)
    except Exception:
        pass


def _slug(name):
    """Namen → dateisystem-sichere id-Basis (ä→a, nur a-z0-9 und _). Die id
    ist Teil der URL/Datei-Referenz – kein Path-Traversal, keine Sonderzeichen."""
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s or 'notiz'


def _now():
    return datetime.now().isoformat()


# ── Block-Sanitizing (tolerant gegen krude API-Bodies) ────────────────────────

def _clean_item(it, seed):
    """Ein Listen-Item auf {id,text,done} normalisieren (flach). seed[0] liefert
    fortlaufende ids für Items ohne eigene."""
    if not isinstance(it, dict):
        return None
    iid = it.get('id')
    if not isinstance(iid, int):
        iid = seed[0]
        seed[0] += 1
    return {'id': iid, 'text': str(it.get('text', '')), 'done': bool(it.get('done'))}


def _clean_block(b, seed):
    """Beliebiges Block-Dict auf eine gültige, minimale Form bringen. seed[0] ist
    der laufende Block-id-Zähler (Liste mit einem Element als Ref-Übergabe)."""
    if not isinstance(b, dict):
        return None
    t = b.get('type')
    if t not in VALID_TYPES:
        return None
    bid = b.get('id')
    if not isinstance(bid, int):
        bid = seed[0]
        seed[0] += 1
    block = {'id': bid, 'type': t}
    if t == 'text':
        block['text'] = str(b.get('text', ''))
    elif t == 'list':
        iseed = [1]
        items = [_clean_item(it, iseed) for it in (b.get('items') or [])]
        block['items'] = [it for it in items if it is not None]
        block['next_item'] = max((it['id'] for it in block['items']), default=0) + 1
    elif t == 'float':
        terms = []
        tid = 1
        for tm in (b.get('terms') or []):
            if isinstance(tm, dict):
                txt = str(tm.get('text', ''))
                ttid = tm.get('id') if isinstance(tm.get('id'), int) else tid
            else:
                txt, ttid = str(tm), tid
            if txt.strip():
                terms.append({'id': ttid, 'text': txt})
                tid = max(tid, ttid) + 1
        block['terms'] = terms
        block['next_term'] = max((tm['id'] for tm in terms), default=0) + 1
    return block


def _clean_blocks(blocks):
    seed = [1]
    out = [_clean_block(b, seed) for b in (blocks or [])]
    return [b for b in out if b is not None]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def list_notes():
    """Übersicht aller Notizen (ohne Block-Inhalte), neueste zuerst."""
    out = []
    for n in _load():
        out.append({
            'id': n.get('id'),
            'title': n.get('title', ''),
            'created': n.get('created', ''),
            'modified': n.get('modified', n.get('created', '')),
            'nblocks': len(n.get('blocks') or []),
        })
    out.sort(key=lambda n: n.get('modified') or '', reverse=True)
    return out


def get_note(nid):
    """Vollständige Notiz oder None."""
    return next((n for n in _load() if n.get('id') == nid), None)


def create_note(title=''):
    """Neue (leere) Notiz anlegen. Liefert die Definition. Titel darf leer sein."""
    title = (title or '').strip()
    notes = _load()
    base = 'n_' + _slug(title)
    existing = {n.get('id') for n in notes}
    nid, k = base, 2
    while nid in existing:
        nid = base + '_' + str(k)
        k += 1
    now = _now()
    note = {
        'id': nid,
        'title': title,
        'created': now,
        'modified': now,
        'next_block': 1,      # id-Quelle für Blöcke (wie next_item bei Listen)
        'blocks': [],
    }
    notes.append(note)
    _save(notes)
    return note


def save_note(nid, title=None, blocks=None):
    """Notiz-Inhalt ersetzen (Titel und/oder Blöcke) und 'modified' stempeln.
    Nur übergebene Felder werden angefasst. Wirft KeyError bei unbekannter id."""
    notes = _load()
    note = next((n for n in notes if n.get('id') == nid), None)
    if note is None:
        raise KeyError(nid)
    if title is not None:
        note['title'] = str(title).strip()
    if blocks is not None:
        note['blocks'] = _clean_blocks(blocks)
        note['next_block'] = max((b['id'] for b in note['blocks']), default=0) + 1
    note['modified'] = _now()
    _save(notes)
    return note


def delete_note(nid):
    """Notiz entfernen."""
    notes = [n for n in _load() if n.get('id') != nid]
    _save(notes)


# ── Reine Layout-Helfer (curses-frei, testbar) ────────────────────────────────

def wrap_text(text, width):
    """Fließtext auf `width` Spalten umbrechen. Erhält vorhandene \\n als harte
    Zeilenumbrüche; zu lange Wörter werden hart getrennt. Liefert immer >=1 Zeile."""
    width = max(1, int(width))
    out = []
    for raw in str(text).split('\n'):
        if not raw:
            out.append('')
            continue
        line = ''
        for word in raw.split(' '):
            while len(word) > width:            # überlanges Wort hart splitten
                if line:
                    out.append(line); line = ''
                out.append(word[:width]); word = word[width:]
            cand = word if not line else line + ' ' + word
            if len(cand) <= width:
                line = cand
            else:
                out.append(line); line = word
        out.append(line)
    return out or ['']


def _term_widths(terms):
    """Display-Breiten der Float-Terme (String ODER {text}) — wie breit jeder
    Term beim Zeichnen wirklich wird, damit das Packen nichts überlappt."""
    out = []
    for t in terms:
        txt = t.get('text', '') if isinstance(t, dict) else t
        out.append(len(str(txt)))
    return out


def _float_positions(widths, width):
    """(positions, rows) für Float-Terme gegebener Breiten in einem `width`
    breiten Feld. Greedy zeilenweise gepackt: jeder Term belegt SEINE echte
    Breite; passt er nicht mehr in die laufende Zeile, bricht er in die nächste
    um (die Box wächst also nach unten, statt Terme übereinander zu stapeln).
    Ein kleiner deterministischer Versatz (kein random → stabil/diffbar) gibt
    den 'verstreuten' Eindruck, eine Leerzeile zwischen den Zeilen die Luft."""
    w = max(1, int(width))
    gap = 3                                     # Luft zwischen zwei Termen
    pos, x, row = [], 0, 0
    for i, tw in enumerate(widths):
        tw = min(max(1, int(tw)), w)            # überbreiter Term → auf Feldbreite
        jit = (i * 7) % 3                       # 0..2 horizontaler Versatz
        if x > 0 and x + jit + tw > w:          # passt nicht mehr → neue Zeile
            row += 1
            x = 0
        px = x + (jit if x + jit + tw <= w else 0)
        px = min(px, max(0, w - tw))            # nie über den rechten Rand
        pos.append((px, row * 2))               # row*2 → Leerzeile dazwischen
        x = px + tw + gap
    return pos, (row + 1 if widths else 0)


def _float_rows_height(rows):
    """Inhaltszeilen einer Floatbox mit `rows` gepackten Term-Zeilen (eine
    Leerzeile dazwischen; Mindesthöhe für die leere bzw. '+'-Box)."""
    return max(3, rows * 2 - 1) if rows else 3


def float_positions(terms, width):
    """Verstreute (x,y)-Positionen für Float-Terme im `width` breiten Feld, plus
    die Zeilenzahl. terms: Liste von Strings ODER {text}. Deterministisch, nie
    überlappend, wächst nach unten. (Die TUI spiegelt diese Logik zum Zeichnen.)"""
    return _float_positions(_term_widths(terms), width)


def _content_rows(block, inner):
    """Zeilen NUR des Inhalts (ohne Rahmen) bei `inner` Innenbreite."""
    t = block.get('type')
    if t == 'text':
        return max(1, len(wrap_text(block.get('text', ''), inner)))
    if t == 'list':
        return max(1, len(block.get('items') or []))
    if t == 'float':
        _, rows = _float_positions(_term_widths(block.get('terms') or []), inner)
        return _float_rows_height(rows)
    return 1


def block_height(block, width):
    """Gesamthöhe eines Block-Kastens (inkl. oben/unten Rahmen) bei `width`
    Außenbreite. Wächst dynamisch mit dem Inhalt."""
    inner = max(1, int(width) - 2)
    return _content_rows(block, inner) + 2


def stack_layout(blocks, width, gap=1):
    """Blöcke von oben nach unten stapeln. Liefert [(block, y, h), …] mit
    kumuliertem y (0-basiert) und `gap` Leerzeilen zwischen den Kästen."""
    out, y = [], 0
    for b in blocks:
        h = block_height(b, width)
        out.append((b, y, h))
        y += h + gap
    return out
