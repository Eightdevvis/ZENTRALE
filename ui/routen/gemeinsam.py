# ui/routen/gemeinsam.py
#
# Was mehrere Bereiche brauchen: der Pfad zu data/ und die zwei
# 503-Antworten, wenn auf diesem Knoten keine KI bzw. kein Tutor-Backend da ist.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md):
# dünne Adapter von HTTP auf core/. Herausgelöst aus ui/app.py am
# 2026-10-06, Code unverändert.

import os
from flask import jsonify

import tutor_port    # type: ignore  – EINZIGER Griff am Sprach-Tutor (Addon).
                     # Nicht tutor_* direkt importieren: der Port haelt den Tutor
                     # rausziehbar und wendet die ZENTRALE-Drossel an.


# Absoluter Pfad zum data/-Verzeichnis (liegt im Projektroot, nicht in ui/).
# os.path.abspath + join macht den Pfad robust gegen "von wo starte ich das Skript".
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')


# ── Gate für KI-Endpoints ─────────────────────────────────────────────
#
# 503-Antwort, wenn auf diesem Knoten kein KI-Backend bereitsteht (weder
# lokal noch über die Cloud). Benutzt von /api/permission_answer (kein
# Chat-Backend) und /api/speak + /api/transcribe (keine lokale KI und kein
# Tutor-Backend) — Defense-in-Depth, damit eine versehentliche Anfrage NIE die
# PC-KI anspricht.
def _ki_nicht_verfuegbar():
    return jsonify({"error": "KI auf diesem Knoten deaktiviert"}), 503


# Tutor-spezifisch: NICHT hart, sondern kapazitaetsbasiert. Der Tutor
# laeuft, sobald das Backend seines Providers da ist (lokal ODER cloud) – auch
# auf dem Laptop. Fehlt es, sagen wir das ehrlich ("backend not here").
def _tutor_unavail():
    return jsonify({"error": "backend not here",
                    "detail": tutor_port.unavailable_reason()
                              or "Tutor-Backend nicht erreichbar."}), 503
