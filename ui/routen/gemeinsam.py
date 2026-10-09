# ui/routen/gemeinsam.py
#
# Was mehrere Bereiche brauchen: der Pfad zu data/ und die 503-Antwort,
# wenn auf diesem Knoten keine KI da ist. (Die Tutor-Antwort ist seit
# 2026-10-09 weg: der Tutor ist eine eigene App mit eigenem Server.)
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import os
from flask import jsonify


# Absoluter Pfad zum data/-Verzeichnis (liegt im Projektroot, nicht in ui/).
# os.path.abspath + join macht den Pfad robust gegen "von wo starte ich das Skript".
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')


# ── Gate für KI-Endpoints ─────────────────────────────────────────────
#
# 503-Antwort, wenn auf diesem Knoten kein KI-Backend bereitsteht (weder
# lokal noch über die Cloud). Benutzt von /api/permission_answer (kein
# Chat-Backend) und /api/speak + /api/transcribe (keine lokale KI) —
# Defense-in-Depth, damit eine versehentliche Anfrage NIE die
# PC-KI anspricht.
def _ki_nicht_verfuegbar():
    return jsonify({"error": "KI auf diesem Knoten deaktiviert"}), 503
