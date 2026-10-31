# ui/routen/listen.py
#
# Listen und Projekte: To-Do-/Sammel-Listen, Einträge, Verschachtelung, Projekt-Fokus.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

from flask import Blueprint, jsonify, request

import lists        # type: ignore  – dynamische Listen-Registry (Todo/Sammel-Listen)
import state         # type: ignore  – in core/, aber durch sys.path.insert auffindbar

bp = Blueprint('listen', __name__)


# ── Listen (dynamisch, vom Dashboard angelegt) ─────────────────────────
#
# Pendant zu den Lifestyle-Graphen, aber für abhakbare Todo-/Sammel-Listen.
# Anders als die Graphen liegen Definition UND Einträge inline in
# data/lists.json (core/lists.py) – keine Zeitreihe, kein /api/log-Sharing.

@bp.route('/api/lists')
def api_lists():
    """Alle Listen-Definitionen inkl. ihrer Einträge. With ?view=1 (lists
    step 3, A8) every list and item also carries `view` {done, total,
    complete, order?, finished?} — counts and display order from the core,
    so no surface computes them."""
    if request.args.get('view') in ('1', 'true'):
        # &box=W: the boxes for the root of the list view (Sasha 2026-10-31)
        try:
            box = _int_arg('box', low=1, high=400)
        except ValueError as e:
            return jsonify({"error": "box: a width 1–400 (%s)" % e}), 400
        return jsonify(lists.lists_with_view(box))
    return jsonify(lists.list_lists())


# ── Lists step 3 (2026-10-31): read-only answers for surfaces and the
# calendar, so they do not compute list logic in their own process
# (memory/hub/list_extraction_plan.md). Shapes: openapi.yaml.

def _int_arg(name, default=None, low=None, high=None):
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    value = int(raw)                       # ValueError → 400 by the caller
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(name)
    return value


@bp.route('/api/lists/targets')
def api_lists_targets():
    """?kind=list|item&lid=…[&iid=…] → [{lid, iid, text, tiefe}]: where the
    list or item can be filed into (`>`), without its own subtree."""
    a = request.args
    try:
        iid = _int_arg('iid')
        return jsonify(lists.filing_targets(a.get('kind'), a.get('lid'), iid))
    except ValueError as e:
        return jsonify({"error": "kind=list|item, lid, iid as number (%s)" % e}), 400


@bp.route('/api/lists/<lid>/bild')
def api_lists_picture(lid):
    """The picture of ONE level of a list (A9) — the same one the tile shows:
    ?w=&h=[&pfad=4,7][&auswahl=-1..][&erledigte=1][&oben=][&kopf_frei=] →
    {zeilen, bernstein, kaesten, leer, oben, oben_max, versteckt, pfad, namen}."""
    a = request.args
    try:
        w = _int_arg('w', low=1, high=400)
        h = _int_arg('h', low=1, high=400)
        if w is None or h is None:
            raise ValueError("w and h")
        path = [int(p) for p in (a.get('pfad') or '').split(',') if p.strip()]
        selection = _int_arg('auswahl', low=-1)
        top = _int_arg('oben', low=0)
        head_free = _int_arg('kopf_frei', 0, low=0, high=400)
    except ValueError as e:
        return jsonify({"error": "w, h (1–400) and numbers for pfad/auswahl/oben/kopf_frei (%s)" % e}), 400
    try:
        return jsonify(lists.level_picture(
            lid, w, h, path, selection, a.get('erledigte') in ('1', 'true'), top, head_free))
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404


@bp.route('/api/lists/aufloesen', methods=['POST'])
def api_lists_resolve():
    """Body {quellen: ["<list>" | "<list>/<item>" | {id}], offene?: n} →
    {ergebnisse: [{zustand, titel, name, eintrag, offene, projekt}]} in the
    same order: what is on top of each list or project now (the calendar's
    live titles, core/kalender_quelle.py)."""
    body = request.get_json(silent=True) or {}
    sources = body.get('quellen')
    if not isinstance(sources, list) or len(sources) > 500:
        return jsonify({"error": "quellen: a list (at most 500)"}), 400
    ids = [q.get('id') if isinstance(q, dict) else q for q in sources]
    ids = [str(i) if isinstance(i, (str, int)) and not isinstance(i, bool) else "" for i in ids]
    return jsonify({"ergebnisse": lists.resolve(ids, body.get('offene') or 0)})


@bp.route('/api/projects')
def api_projects():
    """
    Als Projekt markierte KNOTEN (Listen UND Einträge) als VERSCHACHTELTER Baum:
    geflaggte Top-Level-Liste = Wurzel, ihre geflaggten Unter-Einträge hängen
    rekursiv als `children` darunter (`{id,name,done,total,children:[…]}`).
    Quelle für die PROJECTS-Box in ALLEN Fronten — die Fortschrittslogik bleibt
    an einer Stelle (core/lists), die Fronten rendern nur. Ein Knoten ohne
    children → normal (Titel+Leiste), mit children → gerahmter Kasten.
    NICHT KI-gegatet (gibt es überall).
    """
    return jsonify(lists.projects_tree())


@bp.route('/api/projects/focused')
def api_projects_focused():
    """
    Der aktuell fokussierte Projekt-Teilbaum (voller Knoten inkl. children /
    Fortschritt) — oder null. QUELLE DER FOCUS-BOX in allen Fronten: die zeigt
    NUR noch dieses eine Projekt (oder nichts). Die volle Projekt-Übersicht gibt
    es ausschließlich über /api/projects (die neue Projektansicht der TUI).
    NICHT KI-gegatet (gibt es überall).
    """
    return jsonify(lists.focused_subtree())


@bp.route('/api/projects/focus', methods=['GET', 'POST'])
def api_projects_focus():
    """
    Projekt-FOKUS: genau EIN Projekt allein am Rand rendern.
    GET  → das aktuell fokussierte Projekt `{lid,iid,name}` oder null.
    POST → Fokus setzen (Toggle) bzw. löschen. Quelle für die »Projektansicht«
    der TUI (Taste 'f'); ist ein Fokus gesetzt, zeigen die Fronten in der
    PROJECTS-Box NUR dieses Projekt. Höchstens einer gleichzeitig.
    Body (JSON): {"lid": "...", "iid": 3|null}  → diesen Knoten togglen
                 {"clear": true}                 → Fokus ganz aus
    """
    if request.method == 'GET':
        return jsonify(lists.get_focus())
    body = request.get_json(silent=True) or {}
    if body.get('clear'):
        lists.clear_focus()
        state.push_log("FOKUS-: (aus)")
        return jsonify(None)
    lid = body.get('lid')
    if not lid:
        return jsonify({"error": "lid fehlt"}), 400
    iid = body.get('iid')
    try:
        foc = lists.set_focus(lid, iid if iid is not None else None)
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"FOKUS{'+' if foc else '-'}: {lid}" + (f"/{iid}" if iid is not None else ""))
    return jsonify(foc)


@bp.route('/api/lists', methods=['POST'])
def api_lists_create():
    """
    Neue Liste anlegen.
    Body (JSON): {"name": "Einkaufen"}
    """
    body = request.get_json(silent=True) or {}
    try:
        l = lists.create_list(body.get('name'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    state.push_log(f"LISTE+: {l['id']}")
    return jsonify(l)


@bp.route('/api/lists/<lid>', methods=['DELETE'])
def api_lists_delete(lid):
    """Listen-Definition mit allen Einträgen löschen."""
    lists.delete_list(lid)
    state.push_log(f"LISTE-: {lid}")
    return jsonify({"ok": True})


@bp.route('/api/lists/<lid>/rename', methods=['POST'])
def api_lists_rename(lid):
    """
    Anzeigenamen einer Liste ändern (id bleibt stabil).
    Body (JSON): {"name": "Neuer Name"}
    """
    body = request.get_json(silent=True) or {}
    try:
        lst = lists.rename_list(lid, body.get('name'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    return jsonify(lst)


@bp.route('/api/lists/<lid>/project', methods=['POST'])
def api_lists_set_project(lid):
    """
    Projekt-Flag einer Liste setzen/löschen — bestimmt, ob sie in der
    PROJECTS-Box der Fronten erscheint.
    Body (JSON): {"project": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        lst = lists.set_project(lid, bool(body.get('project')))
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    state.push_log(f"PROJEKT{'+' if lst.get('project') else '-'}: {lid}")
    return jsonify(lst)


@bp.route('/api/lists/<lid>/items/<int:iid>/project', methods=['POST'])
def api_lists_set_item_project(lid, iid):
    """
    Projekt-Flag auf einem Eintrag setzen/löschen (Pendant zu /project für
    Listen — jeder Knoten ist als Projekt markierbar).
    Body (JSON): {"project": true|false}
    """
    body = request.get_json(silent=True) or {}
    try:
        it = lists.set_item_project(lid, iid, bool(body.get('project')))
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"PROJEKT{'+' if it.get('project') else '-'}: {lid}/{iid}")
    return jsonify(it)


@bp.route('/api/lists/<lid>/items', methods=['POST'])
def api_lists_add_item(lid):
    """
    Eintrag an eine Liste hängen.
    Body (JSON): {"text": "Milch"} — optional {"parent": <iid>} macht ihn zum
    Unterpunkt des Eintrags <iid> (Liste wird so zum verschachtelten Mischtyp).
    """
    body = request.get_json(silent=True) or {}
    try:
        item = lists.add_item(lid, body.get('text'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    return jsonify(item)


@bp.route('/api/lists/<lid>/nest', methods=['POST'])
def api_lists_nest(lid):
    """
    Eine ganze Liste IN eine andere einordnen — sie wird dort zum Eintrag und
    verschwindet aus der obersten Ebene.
    Body (JSON): {"into": <ziel-lid>} — optional {"parent": <iid>} hängt sie
    unter einen bestimmten Ziel-Eintrag statt ganz oben.
    """
    body = request.get_json(silent=True) or {}
    try:
        node = lists.nest_list(lid, body.get('into'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"LISTE~: {lid} → {body.get('into')}")
    return jsonify(node)


@bp.route('/api/lists/<lid>/items/<int:iid>/toggle', methods=['POST'])
def api_lists_toggle_item(lid, iid):
    """Erledigt-Status eines Blatt-Eintrags umschalten. Ordner sind nicht
    direkt abhakbar (Status abgeleitet) → 400."""
    try:
        item = lists.toggle_item(lid, iid)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannt"}), 404
    return jsonify(item)


@bp.route('/api/lists/<lid>/items/<int:iid>/rename', methods=['POST'])
def api_lists_rename_item(lid, iid):
    """
    Text eines Eintrags ändern (egal wie tief).
    Body (JSON): {"text": "Neuer Text"}
    """
    body = request.get_json(silent=True) or {}
    try:
        item = lists.rename_item(lid, iid, body.get('text'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannt"}), 404
    return jsonify(item)


@bp.route('/api/lists/<lid>/items/<int:iid>/move', methods=['POST'])
def api_lists_move_item(lid, iid):
    """
    Einen Eintrag (samt Teilbaum) RAUS in eine andere (oder dieselbe) Liste
    verschieben.
    Body (JSON): {"into": <ziel-lid>} — optional {"parent": <iid>} hängt ihn
    unter einen bestimmten Ziel-Eintrag statt ganz oben.
    """
    body = request.get_json(silent=True) or {}
    try:
        node = lists.move_item(lid, iid, body.get('into'), body.get('parent'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    state.push_log(f"LISTE↦: {lid}/{iid} → {body.get('into')}")
    return jsonify(node)


@bp.route('/api/lists/<lid>/items/<int:iid>/reorder', methods=['POST'])
def api_lists_reorder_item(lid, iid):
    """
    Einen Eintrag INNERHALB seiner Geschwister-Ebene verschieben (Reihenfolge).
    Body (JSON): {"delta": -1|+1} — rauf/runter, geklemmt am Rand.
    """
    body = request.get_json(silent=True) or {}
    try:
        moved = lists.reorder_item(lid, iid, body.get('delta', 0))
    except KeyError:
        return jsonify({"error": "unbekannte liste/eintrag"}), 404
    return jsonify({"moved": bool(moved)})


@bp.route('/api/lists/<lid>/items/<int:iid>', methods=['DELETE'])
def api_lists_delete_item(lid, iid):
    """Einen Eintrag aus einer Liste löschen."""
    try:
        lists.delete_item(lid, iid)
    except KeyError:
        return jsonify({"error": "unbekannte liste"}), 404
    return jsonify({"ok": True})
