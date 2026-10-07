# ui/routen/projekte.py
#
# Projekte (Claude-Web-Plan Phase 6, 2026-10-07): Rahmen für ein Thema mit
# eigenen Anweisungen und Wissensdateien; Gespräche gehören optional dazu.
# Speicher und Regeln: core/projekte.py, Doku memory/ki/projekte.md.
#
#   GET  /api/projekte                      Liste (?archiv=1: die archivierten)
#   POST /api/projekte                      anlegen {name, anweisungen?}
#   GET  /api/projekte/<id>                 alles zu einem Projekt + seine Gespräche
#   PUT  /api/projekte/<id>/anweisungen     {text, stand?} — 409 bei altem Stand
#   POST /api/projekte/<id>/wissen          {name, text} oder {pfad, name?, text?}
#   POST /api/projekte/<id>/archiv          {an: true|false}
#   POST /api/projekte/zuordnen             {gespraech: id|null, projekt: id|null}
#
# Geschrieben wird hier nur, was Sasha in der TUI tut. Die KI liest Projekte
# nur (read_project_file); anlegen oder ändern kann sie sie nicht.
#
# Keine dieser Routen braucht ein KI-Backend.
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import gespraeche   # type: ignore
import projekte     # type: ignore

bp = Blueprint('projekte', __name__)


def _fehler(text, code):
    return jsonify({"error": text}), code


def _unbekannt():
    return _fehler("Dieses Projekt gibt es nicht.", 404)


@bp.route('/api/projekte', methods=['GET'])
def api_projekte_liste():
    """{projekte: [{id, name, erstellt, archiviert, wissen}]} nach Name."""
    archiv = request.args.get('archiv') in ('1', 'true', 'ja')
    return jsonify({"projekte": projekte.liste(archivierte=archiv)})


@bp.route('/api/projekte', methods=['POST'])
def api_projekte_neu():
    """Body {name, anweisungen?}. → das Projekt (201). 400: leer, reserviert
    oder gibt es schon."""
    body = request.get_json(silent=True) or {}
    try:
        p = projekte.anlegen(str(body.get('name') or ''),
                             str(body.get('anweisungen') or ''))
    except projekte.Ungueltig as e:
        return _fehler(str(e), 400)
    return jsonify(p), 201


@bp.route('/api/projekte/<pid>', methods=['GET'])
def api_projekte_laden(pid):
    """{id, name, erstellt, archiviert, anweisungen, stand, wissen,
    gespraeche: [wie /api/gespraeche, auch archivierte]}."""
    if not projekte.gibt_es(pid):
        return _unbekannt()
    p = projekte.laden(pid)
    p["gespraeche"] = (gespraeche.liste(projekt=pid)
                       + gespraeche.liste(archivierte=True, projekt=pid))
    return jsonify(p)


@bp.route('/api/projekte/<pid>/anweisungen', methods=['PUT'])
def api_projekte_anweisungen(pid):
    """Body {text, stand?}. `stand` aus dem GET: weicht die Datei inzwischen
    ab (anderer Rechner), 409 statt Überschreiben. → {anweisungen, stand}"""
    if not projekte.gibt_es(pid):
        return _unbekannt()
    body = request.get_json(silent=True) or {}
    text = body.get('text')
    if not isinstance(text, str):
        return _fehler("Es fehlt der Text.", 400)
    stand = body.get('stand')
    if stand and stand != projekte.stand(projekte.anweisungen_lesen(pid)):
        return _fehler("Die Anweisungen wurden inzwischen geändert — neu laden "
                       "und noch einmal.", 409)
    try:
        neu = projekte.anweisungen_schreiben(pid, text)
    except projekte.Ungueltig as e:
        return _fehler(str(e), 400)
    return jsonify({"anweisungen": projekte.anweisungen_lesen(pid), "stand": neu})


@bp.route('/api/projekte/<pid>/wissen', methods=['POST'])
def api_projekte_wissen(pid):
    """Wissen hinzufügen. Body {name, text} (Text direkt) oder {pfad, name?,
    text?}: eine Datei — gesperrt sind Zugangsdaten und gesperrte Ordner
    (dieselbe Liste wie für die KI). Ohne text liest das Backend die Datei;
    gibt es sie auf diesem Rechner nicht: 404 mit {fehlt: true} — die TUI
    auf einem anderen Rechner schickt dann den Text mit. → {name, groesse}"""
    if not projekte.gibt_es(pid):
        return _unbekannt()
    body = request.get_json(silent=True) or {}
    pfad = str(body.get('pfad') or '').strip()
    text = body.get('text')
    if text is not None and not isinstance(text, str):
        return _fehler("Der Text muss Text sein.", 400)
    try:
        if pfad:
            w = projekte.wissen_aus_datei(pid, pfad, str(body.get('name') or ''), text)
        else:
            w = projekte.wissen_hinzufuegen(pid, str(body.get('name') or ''), text or '')
    except projekte.Ungueltig as e:
        return _fehler(str(e), 400)
    except FileNotFoundError:
        return jsonify({"error": "Die Datei gibt es auf diesem Rechner nicht.",
                        "fehlt": True}), 404
    except OSError:
        return _fehler("Die Datei ließ sich nicht lesen.", 400)
    return jsonify(w), 201


@bp.route('/api/projekte/<pid>/archiv', methods=['POST'])
def api_projekte_archiv(pid):
    """Archivieren (Body {an: true}, Standard) oder zurückholen. Gelöscht
    wird nie; die Gespräche bleiben dem Projekt zugeordnet."""
    if not projekte.gibt_es(pid):
        return _unbekannt()
    an = (request.get_json(silent=True) or {}).get('an', True)
    return jsonify(projekte.archivieren(pid, bool(an)))


@bp.route('/api/projekte/zuordnen', methods=['POST'])
def api_projekte_zuordnen():
    """Ein Gespräch einem Projekt zuordnen oder lösen. Body {gespraech,
    projekt}: projekt null → kein Projekt. gespraech null → das nächste neue
    Gespräch dieses Rechners (nach /neu, bevor etwas geschickt wurde).
    → {gespraech, projekt, name}"""
    body = request.get_json(silent=True) or {}
    pid = body.get('projekt') or None
    if pid is not None:
        pid = str(pid)
        if not projekte.gibt_es(pid):
            return _unbekannt()
    gid = body.get('gespraech') or None
    if gid is None:
        if gespraeche.aktiv() is not None:
            return _fehler("Es ist gerade ein Gespräch offen — dessen id fehlt.", 400)
        gespraeche.aktiv_setzen(None, projekt=pid)
    else:
        gid = str(gid)
        if not gespraeche.gibt_es(gid):
            return _fehler("Dieses Gespräch gibt es nicht.", 404)
        try:
            gespraeche.projekt_setzen(gid, pid)
        except ValueError as e:
            return _fehler(str(e), 400)
    return jsonify({"gespraech": gid, "projekt": pid,
                    "name": projekte.name(pid) if pid else None})
