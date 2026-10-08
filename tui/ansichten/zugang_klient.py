# tui/ansichten/zugang_klient.py
#
# Die TUI schickt den Zugangsschlüssel mit (memory/betrieb/zugang.md). Nötig,
# wo sie ein Backend auf einem ANDEREN Rechner anspricht — heute der Pi an
# der Wand gegen das PC-Backend. Auf dem Rechner selbst ist der Kopf unnötig,
# aber harmlos.
#
# stdlib-only (läuft auf dem Pi unter dem System-Python). Statt jede
# urlopen-Stelle (Polling, Chat-Strom, Tutor-Strom, api_call) einzeln
# anzufassen, hängt sich ein Handler in urllib und ergänzt den Kopf für jede
# Anfrage an BASE_URL — und NUR dorthin: ein fremder Server bekommt den
# Schlüssel nie. 2026-10-08.
#
# Den Pfad liest die TUI direkt aus der Umgebung statt über ai_config:
# core/ gibt es auf dem Pi nicht. Name und Vorgabe sind dieselben wie in
# core/zugang.py (tests/test_zugang.py prüft, dass sie gleich bleiben).

import os
import urllib.request

ENV = "ZENTRALE_ZUGANG_SCHLUESSEL"
VORGABE_PFAD = "~/.config/zentrale/zugang.schluessel"


def pfad() -> str:
    return os.path.expanduser(os.environ.get(ENV) or VORGABE_PFAD)


def schluessel():
    """Die Zeile aus der Schlüssel-Datei, oder None. Jedes Mal frisch gelesen
    (ein paar Mikrosekunden): ein erneuerter Schlüssel gilt ohne Neustart."""
    try:
        with open(pfad(), encoding="ascii") as f:
            k = f.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return k or None


class _Kopf(urllib.request.BaseHandler):
    handler_order = 100          # vor dem eigentlichen HTTP-Handler

    def __init__(self, basis: str):
        self.basis = basis.rstrip("/") + "/"

    def http_request(self, req):
        if (req.full_url + "/").startswith(self.basis) and not req.has_header("Authorization"):
            k = schluessel()
            if k:
                req.add_unredirected_header("Authorization", f"Bearer {k}")
        return req

    https_request = http_request


def einrichten(basis_url: str) -> None:
    """Ab jetzt schickt jedes urllib.urlopen an basis_url den Schlüssel mit."""
    urllib.request.install_opener(urllib.request.build_opener(_Kopf(basis_url)))
