# ui/routen/gespraeche.py
#
# Gesprächs-Verwaltung: Liste, neu, öffnen, laden, umbenennen, archivieren —
# und seit 2026-10-08 die Bewertungen der Antworten (core/rueckmeldungen.py).
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
import rueckmeldungen  # type: ignore  – Bewertungen der Antworten (2026-10-08)

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
    d = gespraeche.laden(gid)
    # Das Ablauf-Protokoll ist groß (bis 50.000 Zeichen je Schritt) — hier
    # nur die Zahl, der Inhalt kommt über …/ablauf/<nachricht> (2026-10-09).
    for n in d["nachrichten"]:
        a = n.pop("ablauf", None)
        if a:
            n["ablauf_n"] = len(a)
    return jsonify(d)


# ── Ablauf-Protokoll (2026-10-09, core/zug_ablauf.py) ──────────────────

def _ablauf_finden(gid, nachricht):
    """-> (nachricht-id, einträge) oder eine Fehler-Antwort. nachricht
    „letzte": die letzte Antwort mit Protokoll (für /trace)."""
    if not gespraeche.gibt_es(gid):
        return None, _unbekannt()
    if nachricht == "letzte":
        for n in reversed(gespraeche.nachrichten(gid)):
            if n.get("ablauf"):
                return n["id"], gespraeche.ablauf(gid, n["id"])
        return None, (jsonify({"error": "In diesem Gespräch gibt es noch keinen "
                                        "Ablauf zum Nachlesen."}), 404)
    try:
        eintraege = gespraeche.ablauf(gid, nachricht)
    except gespraeche.Unbekannt:
        return None, (jsonify({"error": "Diese Nachricht gibt es in dem Gespräch nicht."}), 404)
    if eintraege is None:
        return None, (jsonify({"error": "Zu dieser Antwort ist kein Ablauf gespeichert "
                                        "(ältere Antwort oder lokale KI)."}), 404)
    return nachricht, eintraege


@bp.route('/api/gespraeche/<gid>/ablauf/<nachricht>', methods=['GET'])
def api_gespraeche_ablauf(gid, nachricht):
    """Das Ablauf-Protokoll einer Antwort: {gespraech, nachricht, ablauf:
    [{art, zeit, t, …}]}. nachricht „letzte" = die letzte mit Protokoll."""
    nid, eintraege = _ablauf_finden(gid, nachricht)
    if nid is None:
        return eintraege
    return jsonify({"gespraech": gid, "nachricht": nid, "ablauf": eintraege})


@bp.route('/api/gespraeche/<gid>/ablauf/<nachricht>/ablage', methods=['POST'])
def api_gespraeche_ablauf_ablage(gid, nachricht):
    """Das Protokoll als Textdatei in die Ablage (/trace im Chat).
    -> {ok, dokument: {id, titel, art, fassung}}"""
    import ablage       # type: ignore
    import zug_ablauf   # type: ignore
    nid, eintraege = _ablauf_finden(gid, nachricht)
    if nid is None:
        return eintraege
    titel = "Ablauf: " + (gespraeche.kopf(gid).get("titel") or gid)
    text = zug_ablauf.als_text(eintraege, titel=f"{titel} (Antwort {nid})")
    try:
        k = ablage.anlegen(titel, text, "text", herkunft="ablauf", gespraech=gid)
    except ablage.Fehler as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "dokument": ablage.kurz(k)}), 201


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


# ── Bewertungen (2026-10-08) ────────────────────────────────────────────
# Hier und nicht in einem eigenen Bereich: eine Bewertung gehört zu einer
# Antwort eines Gesprächs, und ein eigenes Modul hieße ui/routen/__init__.py
# anfassen, woran parallel gebaut wird.

@bp.route('/api/rueckmeldung', methods=['POST'])
def api_rueckmeldung():
    """Eine Antwort bewerten oder die Bewertung ändern. Body {gespraech,
    nachricht, wert: 1|-1, kommentar?}. -> {ok, rueckmeldung}. 400 bei
    falschem Wert/zu langem Kommentar, 404 ohne Gespräch/Antwort."""
    body = request.get_json(silent=True) or {}
    try:
        e = rueckmeldungen.bewerten(str(body.get('gespraech') or ''),
                                    str(body.get('nachricht') or ''),
                                    body.get('wert'), body.get('kommentar') or '')
    except rueckmeldungen.Ungueltig as fehler:
        return jsonify({"error": str(fehler)}), 400
    except rueckmeldungen.Unbekannt:
        return jsonify({"error": "Diese Antwort gibt es nicht (mehr)."}), 404
    return jsonify({"ok": True, "rueckmeldung": e})


@bp.route('/api/rueckmeldungen', methods=['GET'])
def api_rueckmeldungen():
    """{rueckmeldungen: [...]}: die geltende Bewertung je Antwort, neueste
    zuerst, mit gespraech_titel und ausschnitt (bzw. verworfen).
    ?gespraech=<id>: nur die eines Gesprächs."""
    gid = request.args.get('gespraech') or None
    return jsonify({"rueckmeldungen": rueckmeldungen.mit_kontext(rueckmeldungen.aktuelle(gid))})
