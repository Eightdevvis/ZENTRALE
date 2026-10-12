# ui/routen/browser.py
#
# Die Browser-Front (Monolith) unter /zentrale — zurück aus dem Archiv seit
# 2026-10-12 (memory/system/dashboard.md). Die TUI bleibt die Haupt-Front;
# der Browser ist eine zweite Ansicht auf dieselben /api/-Routen.
#
#   /zentrale            → ui/templates/monolith.html
#   /zentrale/static/…   → ui/static/ (engine.js, viz.js, ascii.js, fonts/)
#   /                    → Weiterleitung auf /zentrale
#   /api/photos[/<name>] → Fotos für den Bild→ASCII-Filter
#
# Alles, was nur der Browser braucht, steht hier — die Daten-Routen
# (/api/state, /api/chat, …) gehören ihren Bereichen, der Browser ruft sie
# nur auf. Die Tür (zugang.py) gilt wie für jede andere Route.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md).

import os

from flask import Blueprint, jsonify, make_response, redirect, render_template, send_from_directory, url_for

import ai_backends   # type: ignore  – in core/, aber durch sys.path.insert auffindbar

from ui.routen.gemeinsam import _DATA_DIR

bp = Blueprint('browser', __name__,
               template_folder='../templates',
               static_folder='../static',
               static_url_path='/zentrale/static')


@bp.route('/')
def wurzel():
    """Die nackte Adresse führt zur Browser-Front."""
    return redirect(url_for('browser.zentrale'))


@bp.route('/zentrale')
def zentrale():
    """Das Dashboard. ki_aus blendet die KI-Blöcke aus, wenn dieser Knoten
    keine lokale KI hat. no-store: der Browser soll immer die aktuelle
    Fassung laden, nie eine gecachte."""
    r = make_response(render_template('monolith.html',
                                      ki_aus=ai_backends.lokale_ki_aus()))
    r.headers['Cache-Control'] = 'no-store'
    return r


# ── Fotos (Quelle für den ASCII-Bild-Filter) ──────────────────────────
#
# Same-origin vom Backend, nicht direkt aus dem Netz: nur dann darf der
# Canvas per getImageData() die Pixel lesen. Ordner per Env überschreibbar.
# Fehlt er, kommt eine leere Liste und der Filter nimmt sein Test-Bild.

_PHOTO_DIR = os.environ.get("ZENTRALE_PHOTO_DIR", os.path.join(_DATA_DIR, "photos"))
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")


@bp.route('/api/photos')
def api_photos():
    """Liste der Bild-Dateinamen (sortiert); leer, wenn kein Ordner da ist."""
    if not os.path.isdir(_PHOTO_DIR):
        return jsonify([])
    return jsonify([f for f in sorted(os.listdir(_PHOTO_DIR))
                    if f.lower().endswith(_PHOTO_EXTS)])


@bp.route('/api/photos/<path:name>')
def api_photo_file(name):
    """Eine Bild-Datei. send_from_directory verhindert ../-Ausbrüche."""
    return send_from_directory(_PHOTO_DIR, name)
