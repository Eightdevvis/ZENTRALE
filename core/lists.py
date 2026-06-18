# core/lists.py
# Dynamische Listen-Registry für das Listen-Werkzeug (Pendant zum
# Graph-Werkzeug in core/graphs.py).
#
# Wie die Graphen werden Listen ZUR LAUFZEIT angelegt (TUI-Mitte „Listen",
# Taste 'l') und in data/lists.json persistiert – kein Python-Edit nötig.
#
# Unterschied zu den Graphen: eine Liste hat keine Zeitreihe, die sich die
# Data-Collection (/api/log → data/<id>.json) teilt. Die Einträge sind klein,
# listen-spezifisch und abhakbar (Todo) – sie liegen deshalb INLINE in der
# Definition. Diese Datei verwaltet also Definitionen UND Einträge.

import os
import re
import json
import unicodedata
from datetime import datetime

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
# ZWEI Registries, bewusst getrennt (gemerged gelesen):
#   _REGISTRY  = Sashas private Listen — pflegt NUR Sasha (TUI).
#   _FEATURES  = der ZENTRALE-Feature-Tracker (Liste »zentrale«) — pflegt Claude.
# Beim Lesen werden beide zusammengeführt (TUI + PROJECTS-Box sehen alles),
# beim Schreiben landet jede Liste wieder in IHRER Datei — und es wird nur die
# Datei angefasst, die sich wirklich geändert hat. ACHTUNG: das ist KEIN sauberer
# Besitz-Schnitt — features.json schreiben beide (Claude den Inhalt, Sasha das
# Projekt-Flag/Abhaken in der TUI). Beide Dateien sind NICHT in git (siehe
# .gitignore / datei_zugriffe.md); der Abgleich Laptop↔PC läuft über den
# rsync-Sync (zentrale-push/-pull, newest-wins) + Push-on-write (datasync.py →
# _save_file unten stößt zentrale-push-data an). Details: CLAUDE.md / topologie.md.
_REGISTRY = os.path.join(_DATA_DIR, 'lists.json')
_FEATURES = os.path.join(_DATA_DIR, 'features.json')


def _load_file(path):
    """Eine Registry-Datei von Disk lesen (leere Liste, wenn nicht vorhanden)."""
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_file(path, lists):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(lists, f, indent=2, ensure_ascii=False)
    # Echte Änderung geschrieben → Peer-Push anstoßen (no-op ohne AUTOPUSH).
    try:
        from datasync import notify_change
        notify_change(path)
    except Exception:
        pass


def _load():
    """Beide Registries gemerged (privat zuerst, dann Feature-Tracker)."""
    return _load_file(_REGISTRY) + _load_file(_FEATURES)


def _save(lists):
    """
    Die gemergte Liste zurück auf die zwei Dateien aufteilen: was im
    Feature-Tracker steckt (id ist dort schon bekannt) → features.json, alles
    andere → lists.json. Geschrieben wird nur, was sich gegenüber Disk wirklich
    geändert hat — damit eine reine Feature-Pflege lists.json NICHT berührt.
    """
    feat_ids = {l.get('id') for l in _load_file(_FEATURES)}
    features = [l for l in lists if l.get('id') in feat_ids]
    personal = [l for l in lists if l.get('id') not in feat_ids]
    if features != _load_file(_FEATURES):
        _save_file(_FEATURES, features)
    if personal != _load_file(_REGISTRY):
        _save_file(_REGISTRY, personal)


def _slug(name):
    """
    Namen → dateisystem-sichere id-Basis. ASCII-fold (ä→a), nur a-z0-9 und _.
    (Listen liegen zwar alle in EINER Datei, aber die id taucht in URLs auf –
    also sauber halten, kein Path-/Query-Murks.)
    """
    s = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    s = re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')
    return s or 'liste'


def _find(lists, lid):
    """Die Liste mit der id (oder None)."""
    for l in lists:
        if l.get('id') == lid:
            return l
    return None


# ── Baum-Helfer ────────────────────────────────────────────────────────────
# Einträge sind seit dem Verschachteln-Feature MISCHTYPEN: jeder Eintrag kann
# selbst wieder ein 'items'-Array tragen (Unterpunkte ODER eine eingeordnete
# Unterliste ODER beides). Ein Eintrag ohne 'items' (oder mit leerem) ist ein
# Blatt. Die folgenden Helfer laufen den Baum rekursiv ab; ältere Dateien ohne
# 'items' funktionieren weiter (`.get('items')` ⇒ None ⇒ als leer behandelt).

def _walk(items):
    """Alle Eintrags-Dicts rekursiv (Tiefensuche, Eltern vor Kindern)."""
    for it in items or []:
        if not isinstance(it, dict):
            continue
        yield it
        kids = it.get('items')
        if isinstance(kids, list):
            yield from _walk(kids)


def _find_item(items, iid):
    """Den Eintrag mit iid irgendwo im Baum (oder None)."""
    for it in _walk(items):
        if it.get('id') == iid:
            return it
    return None


def _remove_item(items, iid):
    """
    Den Eintrag mit iid (samt Teilbaum) irgendwo im Baum entfernen.
    Liefert True, wenn etwas entfernt wurde — mutiert die übergebene Liste.
    """
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if it.get('id') == iid:
            items.pop(idx)
            return True
        kids = it.get('items')
        if isinstance(kids, list) and _remove_item(kids, iid):
            return True
    return False


def _detach_item(items, iid):
    """
    Wie _remove_item, liefert aber den ausgeklinkten Eintrag (samt Teilbaum)
    zurück statt nur True/False — None, wenn nichts gefunden. Mutiert die Liste.
    Basis fürs Verschieben: erst ausklinken, dann woanders einhängen.
    """
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        if it.get('id') == iid:
            return items.pop(idx)
        kids = it.get('items')
        if isinstance(kids, list):
            got = _detach_item(kids, iid)
            if got is not None:
                return got
    return None


def _bump_next_item(lst):
    """next_item hinter JEDE schon vergebene id der Liste schieben (Alt-Dateien
    ohne das Feld migrieren) — Voraussetzung, damit _reid kollisionsfrei ist."""
    seen = max((i.get('id') or 0 for i in _walk(lst.get('items'))), default=0)
    lst['next_item'] = max(lst.get('next_item') or 1, seen + 1)


def _reid(items, lst):
    """
    Allen Einträgen in `items` (rekursiv) frische, im Top-Level `lst`
    eindeutige ids aus dessen 'next_item'-Quelle vergeben. Wird beim Einordnen
    einer ganzen Liste gebraucht: die mitgebrachten ids stammen aus dem
    id-Raum der QUELL-Liste und würden sonst mit denen der ZIEL-Liste kollidieren.
    """
    for it in items or []:
        if not isinstance(it, dict):
            continue
        it['id'] = lst['next_item']
        lst['next_item'] = lst['next_item'] + 1
        kids = it.get('items')
        if isinstance(kids, list):
            _reid(kids, lst)


def list_lists():
    """Alle Listen-Definitionen inkl. ihrer Einträge."""
    return _load()


def create_list(name):
    """
    Neue Liste anlegen. Liefert die Definition zurück.
    Wirft ValueError bei leerem Namen.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('Name fehlt')

    lists = _load()
    # id aus dem Namen ableiten, kollisionsfrei machen (l_<slug>, _2, _3 …)
    base = 'l_' + _slug(name)
    existing = {l['id'] for l in lists}
    lid, n = base, 2
    while lid in existing:
        lid = base + '_' + str(n)
        n += 1

    lst = {
        'id': lid,
        'name': name,
        'created': datetime.now().isoformat(),
        'next_item': 1,   # monoton steigende id-Quelle, eindeutig über den Baum
        'items': [],      # [{id, text, done, items?:[…]}] — items? = Unterpunkte
        'project': False, # als Projekt in der PROJECTS-Box der Fronten zeigen?
    }
    lists.append(lst)
    _save(lists)
    return lst


def delete_list(lid):
    """Listen-Definition (mit allen Einträgen) entfernen."""
    lists = [l for l in _load() if l.get('id') != lid]
    _save(lists)


def add_item(lid, text, parent_iid=None):
    """
    Eintrag an eine Liste hängen. Liefert den Eintrag ({id, text, done}).
    Ohne parent_iid landet er auf der obersten Ebene; mit parent_iid wird er
    Unterpunkt des Eintrags mit dieser id (der dadurch zum Container wird).
    Wirft ValueError bei leerem Text, KeyError bei unbekannter Liste /
    unbekanntem Eltern-Eintrag.
    """
    text = (text or '').strip()
    if not text:
        raise ValueError('Text fehlt')
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    # next_item ist die id-Quelle (eindeutig über den GANZEN Baum); ältere
    # Dateien ohne das Feld migrieren wir aus dem höchsten Vorkommen.
    iid = lst.get('next_item') or (max((i.get('id', 0) for i in _walk(lst.get('items'))), default=0) + 1)
    item = {'id': iid, 'text': text, 'done': False}
    if parent_iid is None:
        lst.setdefault('items', []).append(item)
    else:
        parent = _find_item(lst.get('items'), parent_iid)
        if parent is None:
            raise KeyError(parent_iid)
        parent.setdefault('items', []).append(item)
    lst['next_item'] = iid + 1
    _save(lists)
    return item


def is_container(item):
    """Eintrag mit (nicht-leeren) Kindern? Solche „Ordner" sind NICHT direkt
    abhakbar — ihr Erledigt-Status leitet sich aus den Kindern ab (is_done)."""
    kids = item.get('items') if isinstance(item, dict) else None
    return isinstance(kids, list) and len(kids) > 0


def is_done(item):
    """Effektiver Erledigt-Status. Blatt: das eigene 'done'. Ordner: abgeleitet
    — erledigt genau dann, wenn ALLE direkten Kinder (rekursiv) erledigt sind.
    Ein Ordner hat also keinen eigenen abhakbaren Zustand."""
    if is_container(item):
        return all(is_done(c) for c in item['items'] if isinstance(c, dict))
    return bool(item.get('done'))


def toggle_item(lid, iid):
    """
    Erledigt-Status eines BLATT-Eintrags umschalten (egal wie tief verschachtelt).
    Ordner (Einträge mit Kindern) sind nicht direkt abhakbar — ihr Status leitet
    sich aus den Kindern ab; ein Toggle darauf wirft ValueError.
    Liefert den Eintrag zurück. Wirft KeyError bei unbekannter Liste /
    unbekanntem Eintrag.
    """
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    item = _find_item(lst.get('items'), iid)
    if item is None:
        raise KeyError(iid)
    if is_container(item):
        raise ValueError('Ordner nicht direkt abhakbar')
    item['done'] = not item.get('done', False)
    _save(lists)
    return item


def delete_item(lid, iid):
    """
    Einen Eintrag (samt seinem Teilbaum) aus einer Liste löschen — egal wie
    tief er steckt. Wirft KeyError bei unbekannter Liste / unbekanntem Eintrag.
    """
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    if not _remove_item(lst.setdefault('items', []), iid):
        raise KeyError(iid)
    _save(lists)


def nest_list(lid, dest_lid, parent_iid=None):
    """
    Eine ganze Top-Level-Liste IN eine andere einordnen: die Quell-Liste `lid`
    wird zu einem Eintrag der Ziel-Liste `dest_lid` (Name → text, ihre Einträge
    → Kinder) und verschwindet aus der obersten Ebene. Ohne parent_iid landet
    sie ganz oben in der Ziel-Liste, mit parent_iid als Unterpunkt des
    betreffenden Ziel-Eintrags. Liefert den neuen Eintrag.

    Wirft ValueError beim Versuch, eine Liste in sich selbst zu schieben,
    KeyError bei unbekannter Quell-/Ziel-Liste bzw. unbekanntem Eltern-Eintrag.
    """
    if lid == dest_lid:
        raise ValueError('Liste in sich selbst')
    lists = _load()
    src = _find(lists, lid)
    dest = _find(lists, dest_lid)
    if src is None:
        raise KeyError(lid)
    if dest is None:
        raise KeyError(dest_lid)

    # next_item hinter alle schon vergebenen Ziel-ids schieben, BEVOR der neue
    # Teilbaum drinhängt — sonst kollidieren die gleich neu vergebenen ids.
    _bump_next_item(dest)

    # Quell-Liste → Eintrag. id wird gleich von _reid sauber überschrieben.
    node = {'id': None, 'text': src.get('name') or '', 'done': False,
            'items': src.get('items') or []}
    if parent_iid is None:
        dest.setdefault('items', []).append(node)
    else:
        parent = _find_item(dest.get('items'), parent_iid)
        if parent is None:
            raise KeyError(parent_iid)
        parent.setdefault('items', []).append(node)

    # Frische, im Ziel eindeutige ids für den ganzen eingehängten Teilbaum.
    _reid([node], dest)

    # Quell-Liste aus dem Top-Level entfernen (dest-Objekt bleibt referenziert).
    lists = [l for l in lists if l.get('id') != lid]
    _save(lists)
    return node


def rename_list(lid, name):
    """
    Anzeigenamen einer Liste ändern (die id bleibt stabil — sie steckt in URLs
    und Verweisen). Liefert die Liste zurück. Wirft ValueError bei leerem Namen,
    KeyError bei unbekannter Liste.
    """
    name = (name or '').strip()
    if not name:
        raise ValueError('Name fehlt')
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    lst['name'] = name
    _save(lists)
    return lst


def set_project(lid, on):
    """
    Projekt-Flag einer Liste setzen/löschen. Nur Listen mit gesetztem Flag
    erscheinen als Projekt in der PROJECTS-Box der Fronten (Titel + Erfüllungs-
    leiste). Reine Anzeige-Markierung, ändert die Einträge nicht. Liefert die
    Liste. Wirft KeyError bei unbekannter Liste.
    """
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    lst['project'] = bool(on)
    _save(lists)
    return lst


def leaf_progress(lst):
    """
    (erledigte Blätter, alle Blätter) rekursiv über den Baum — Basis für die
    Projekt-Erfüllungsleiste. Ordner (Einträge mit Kindern) zählen NICHT selbst
    mit, nur ihre Blätter; ihr Status ist ohnehin abgeleitet (vgl. is_done).
    """
    done = total = 0
    for it in _walk(lst.get('items')):
        if is_container(it):
            continue
        total += 1
        if it.get('done'):
            done += 1
    return done, total


def node_progress(node):
    """Erfüllungsgrad EINES Knotens (Liste oder Eintrag): über seine Blätter.
    Ein Blatt selbst zählt als 1 Punkt (erledigt/offen) — so kann auch ein
    einzelner Eintrag als Projekt einen Fortschritt zeigen."""
    if is_container(node):
        return leaf_progress(node)
    return (1 if node.get('done') else 0, 1)


def set_item_project(lid, iid, on):
    """
    Projekt-Flag auf einem EINTRAG (egal wie tief) setzen/löschen — Pendant zu
    set_project für Listen, damit jeder Knoten als Projekt markierbar ist.
    Liefert den Eintrag. Wirft KeyError bei unbekannter Liste / unbekanntem
    Eintrag.
    """
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    it = _find_item(lst.get('items'), iid)
    if it is None:
        raise KeyError(iid)
    it['project'] = bool(on)
    _save(lists)
    return it


def _project_subnodes(items):
    """
    Rekursiv die als Projekt geflaggten Einträge unter `items` als verschachtelte
    Knoten sammeln. Ein geflaggter Eintrag wird zum Knoten (sein Fortschritt +
    seine eigenen geflaggten Unter-Projekte als `children`); ein NICHT geflaggter
    Container wird nur durchschritten — seine geflaggten Nachfahren klettern eine
    Ebene höher. So erscheinen genau die markierten Knoten in ihrer Verschachtelung.
    """
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        if it.get('project'):
            d, t = node_progress(it)
            out.append({"id": it.get("id"), "name": it.get("text"),
                        "done": d, "total": t,
                        "children": _project_subnodes(it.get('items'))})
        else:
            kids = it.get('items')
            if isinstance(kids, list) and kids:
                out.extend(_project_subnodes(kids))
    return out


def projects_tree():
    """
    Verschachtelte Projekt-Struktur für die PROJECTS-Box. Jede als Projekt
    geflaggte Top-Level-Liste ist ein Wurzel-Knoten; ihre (rekursiv) geflaggten
    Unter-Einträge hängen als `children` darunter. Knoten-Form:
    `{id, name, done, total, children:[…]}`.

    Anzeige-Konvention der Fronten: ein Knoten OHNE children wird normal
    (Titel + Leiste) gezeigt, einer MIT children als gerahmter Kasten (Titel im
    Rahmen, children drin — der gerahmte Knoten selbst trägt KEINE eigene Leiste).
    `done/total` = erledigte/alle Blätter rekursiv unter dem Knoten.
    """
    out = []
    for l in _load():
        if l.get('project'):
            d, t = node_progress(l)
            out.append({"id": l.get("id"), "name": l.get("name"),
                        "done": d, "total": t,
                        "children": _project_subnodes(l.get('items'))})
        else:
            # Liste selbst kein Projekt → ihre geflaggten Einträge klettern hoch
            # und werden eigene Wurzeln (sonst „verstecken" sich Projekte in einer
            # ungeflaggten Liste und tauchen nie in der Box auf).
            out.extend(_project_subnodes(l.get('items')))
    return out


def rename_item(lid, iid, text):
    """
    Text eines Eintrags ändern (egal wie tief verschachtelt). Liefert den
    Eintrag. Wirft ValueError bei leerem Text, KeyError bei unbekannter Liste /
    unbekanntem Eintrag.
    """
    text = (text or '').strip()
    if not text:
        raise ValueError('Text fehlt')
    lists = _load()
    lst = _find(lists, lid)
    if lst is None:
        raise KeyError(lid)
    it = _find_item(lst.get('items'), iid)
    if it is None:
        raise KeyError(iid)
    it['text'] = text
    _save(lists)
    return it


def move_item(src_lid, iid, dest_lid, parent_iid=None):
    """
    Einen einzelnen Eintrag (samt Teilbaum) aus einer Liste RAUS und in eine
    andere (oder dieselbe) Liste einhängen — Gegenstück zu nest_list, aber für
    einen Punkt statt einer ganzen Liste. Ohne parent_iid landet er auf der
    obersten Ebene der Ziel-Liste, mit parent_iid als Unterpunkt dort. Die ids
    des bewegten Teilbaums werden im Ziel frisch (kollisionsfrei) vergeben.
    Liefert den Eintrag.

    Wirft KeyError bei unbekannter Quell-/Ziel-Liste bzw. unbekanntem Eintrag/
    Eltern-Eintrag, ValueError beim Versuch, einen Eintrag unter sich selbst
    (in seinen eigenen Teilbaum) zu hängen.
    """
    lists = _load()
    src = _find(lists, src_lid)
    if src is None:
        raise KeyError(src_lid)
    dest = _find(lists, dest_lid)
    if dest is None:
        raise KeyError(dest_lid)

    # Vor dem Ausklinken validieren, damit bei Fehlern nichts verloren geht.
    moving = _find_item(src.get('items'), iid)
    if moving is None:
        raise KeyError(iid)
    if parent_iid is not None:
        # Zyklus (Eltern im eigenen Teilbaum) kann nur in DERSELBEN Liste
        # entstehen — ids sind nur listenintern eindeutig, über Listen hinweg
        # wäre der Vergleich bedeutungslos (und falsch-positiv bei id-Gleichheit).
        if src is dest and _find_item([moving], parent_iid) is not None:
            raise ValueError('Eintrag in sich selbst')
        if _find_item(dest.get('items'), parent_iid) is None:
            raise KeyError(parent_iid)

    # next_item der Ziel-Liste hochziehen, SOLANGE der bewegte Teilbaum noch
    # nicht drinhängt (bei gleicher Liste zählt _walk seine alten ids mit — die
    # werden gleich eh neu vergeben, das schadet nur als oberer Startwert nicht).
    node = _detach_item(src.setdefault('items', []), iid)
    _bump_next_item(dest)
    if parent_iid is None:
        dest.setdefault('items', []).append(node)
    else:
        parent = _find_item(dest.get('items'), parent_iid)
        parent.setdefault('items', []).append(node)
    _reid([node], dest)
    _save(lists)
    return node
