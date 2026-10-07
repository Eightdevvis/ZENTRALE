# ui/routen/gespraeche.py
#
# Gesprächs-Verwaltung: Liste, neu, öffnen, laden, umbenennen, archivieren.
# Der Chat-Strom selbst (/api/chat, /api/chat/wiederholen) steht in ki.py.
# Speicher und Regeln: core/gespraeche.py (Claude-Web-Plan Phase 2,
# 2026-10-07).
#
# Keine dieser Routen braucht ein KI-Backend: Gespräche lesen und ordnen
# geht auch offline.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

from flask import Blueprint, jsonify, request

import erlaubnis    # type: ignore  – „für dieses Gespräch" endet beim Wechsel
import gespraeche   # type: ignore
import projekte     # type: ignore  – Projektname an der Zeile (Phase 6)

bp = Blueprint('gespraeche', __name__)


def _unbekannt():
    return jsonify({"error": "Dieses Gespräch gibt es nicht."}), 404


def _fest(gid):
    """Das Erinnerungs-Gespräch bleibt, wie es ist: oben, mit seinem Namen."""
    if gid == gespraeche.ERINNERUNGEN:
        return jsonify({"error": "Das Gespräch „Erinnerungen“ bleibt, wie es ist."}), 400
    return None


@bp.route('/api/gespraeche', methods=['GET'])
def api_gespraeche_liste():
    """{aktiv, neu_projekt, gespraeche: [{id, titel, erstellt, letzte, anzahl,
    archiviert, ungelesen, projekt, projekt_name}]}, neueste Aktivität zuerst,
    Erinnerungen oben. ?archiv=1 → nur die archivierten; ?projekt=<id> →
    nur die Gespräche dieses Projekts (Phase 6). neu_projekt: {id, name} des
    Projekts, in dem das nächste neue Gespräch beginnt, oder null."""
    archiv = request.args.get('archiv') in ('1', 'true', 'ja')
    projekt = request.args.get('projekt') or None
    if projekt and not projekte.gibt_es(projekt):
        return jsonify({"error": "Dieses Projekt gibt es nicht."}), 404
    eintraege = gespraeche.liste(archivierte=archiv, projekt=projekt)
    namen = {}
    for e in eintraege:
        pid = e.get("projekt")
        if pid and pid not in namen:
            namen[pid] = projekte.name(pid)
        e["projekt_name"] = namen.get(pid) or None if pid else None
    neu = gespraeche.neu_projekt()
    return jsonify({"aktiv": gespraeche.aktiv(), "gespraeche": eintraege,
                    "neu_projekt": ({"id": neu, "name": projekte.name(neu)}
                                    if neu and projekte.gibt_es(neu) else None)})


@bp.route('/api/gespraeche', methods=['POST'])
def api_gespraeche_neu():
    """Neues Gespräch anlegen und öffnen. Body {titel?}. -> {id}"""
    body = request.get_json(silent=True) or {}
    titel = " ".join(str(body.get('titel') or '').split()) or None
    gid = gespraeche.neu(titel)
    gespraeche.aktiv_setzen(gid)
    erlaubnis.gespraech_beginnt(gid)
    return jsonify({"ok": True, "id": gid}), 201


@bp.route('/api/gespraeche/aktiv', methods=['POST'])
def api_gespraeche_aktiv():
    """Gespräch öffnen (auf diesem Rechner). Body {id}; id null → das
    nächste Senden beginnt ein neues."""
    body = request.get_json(silent=True) or {}
    gid = body.get('id')
    if gid is not None and not gespraeche.gibt_es(str(gid)):
        return _unbekannt()
    gespraeche.aktiv_setzen(str(gid) if gid is not None else None)
    # Gesprächswechsel hebt „für dieses Gespräch" auf (2026-10-07).
    erlaubnis.gespraech_beginnt(str(gid) if gid is not None else None)
    return jsonify({"ok": True, "aktiv": gid})


@bp.route('/api/gespraeche/<gid>', methods=['GET'])
def api_gespraeche_laden(gid):
    """Kopf und alle sichtbaren Nachrichten (mit Denken und Werkzeugen)."""
    if not gespraeche.gibt_es(gid):
        return _unbekannt()
    return jsonify(gespraeche.laden(gid))


@bp.route('/api/gespraeche/<gid>/titel', methods=['POST'])
def api_gespraeche_titel(gid):
    """Umbenennen. Body {titel}."""
    if not gespraeche.gibt_es(gid):
        return _unbekannt()
    fehler = _fest(gid)
    if fehler:
        return fehler
    titel = " ".join(str((request.get_json(silent=True) or {}).get('titel') or '').split())
    if not titel:
        return jsonify({"error": "Der Titel ist leer."}), 400
    gespraeche.umbenennen(gid, titel)
    return jsonify({"ok": True, "titel": gespraeche.kopf(gid).get("titel")})


@bp.route('/api/gespraeche/<gid>/archiv', methods=['POST'])
def api_gespraeche_archiv(gid):
    """Archivieren (Body {an: true}, Standard) oder zurückholen ({an: false}).
    Gelöscht wird nie — der Sync brächte es vom anderen Rechner zurück.
    War es das offene Gespräch, beginnt das nächste Senden ein neues."""
    if not gespraeche.gibt_es(gid):
        return _unbekannt()
    fehler = _fest(gid)
    if fehler:
        return fehler
    an = (request.get_json(silent=True) or {}).get('an', True)
    gespraeche.archivieren(gid, bool(an))
    if an and gespraeche.aktiv() == gid:
        gespraeche.aktiv_setzen(None)
    return jsonify({"ok": True, "archiviert": bool(an), "aktiv": gespraeche.aktiv()})
