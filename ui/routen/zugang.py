# ui/routen/zugang.py
#
# Die Tür vor allen Routen: wer nicht auf diesem Rechner sitzt, braucht den
# Zugangsschlüssel (core/zugang.py, memory/betrieb/zugang.md). Läuft vor JEDER
# Anfrage (before_app_request), deshalb steht dieser Bereich in
# ui/routen/__init__.py an erster Stelle.
#
#   von diesem Rechner (127.0.0.1/::1 UND Host localhost)  → frei
#   Authorization: Bearer <schlüssel>                       → frei
#   Keks aus einem Browser-Link                             → frei
#   ?zugang=<marke> (Link, 10 min gültig)                   → Keks setzen, weiterleiten
#   sonst: Modus „melden" lässt durch und schreibt ins Log, „an" sagt 401
#   with the next step for the refused client (_NEXT_STEP). Default „an"
#   since 2026-10-31.
#
# Teil der Routen-Schicht (Schicht 5, memory/system/bauplan_kern.md). 2026-10-08.

import threading
import time
from collections import deque

from flask import Blueprint, Response, jsonify, redirect, request

import ai_config     # type: ignore  – in core/, aber durch sys.path.insert auffindbar
import state         # type: ignore
import zugang        # type: ignore

bp = Blueprint('zugang', __name__)

_LOKAL_ADRESSEN = ("127.0.0.1", "::1", "::ffff:127.0.0.1")
_LOKAL_NAMEN = ("localhost", "127.0.0.1", "[::1]")

# Frei ohne Schlüssel: das Code-Paket der Aussenposten. Es enthält nur Code
# aus dem Repo (TUI, Zimmer, Bridge), keine Daten — und genau mit diesem
# Paket bekommt der Pi die Fassung, die den Schlüssel mitschickt. Wäre es
# gesperrt, käme ein Pi ohne Schlüssel nie mehr an ein Update (2026-10-08).
_FREI = ("/api/aussenposten/manifest", "/api/aussenposten/paket")

# Wer zuletzt ohne Schlüssel kam: für den Status und damit das Log nicht
# jede Sekunde dieselbe Zeile bekommt (die TUI am Pi pollt sekündlich).
_gemeldet = deque(maxlen=50)
_zuletzt_geloggt = {}
_LOG_ABSTAND_S = 600
_lock = threading.Lock()


def lokal() -> bool:
    """Von diesem Rechner, an localhost gerichtet. Der Host-Kopf zählt mit:
    sonst käme eine fremde Webseite im eigenen Browser über einen umgebogenen
    Namen (DNS-Rebinding) als „lokal" durch. Ein SSH-Tunnel (Laptop →
    localhost am PC) zählt als lokal — wer SSH hat, hat ohnehin alles."""
    host = (request.host or "").lower()
    host = host[:host.find("]") + 1] if host.startswith("[") else host.split(":")[0]
    return request.remote_addr in _LOKAL_ADRESSEN and host in _LOKAL_NAMEN


def _bearer() -> str | None:
    kopf = request.headers.get("Authorization", "")
    art, _, wert = kopf.partition(" ")
    return wert.strip() if art.lower() == "bearer" and wert.strip() else None


def _melden(grund: str, durchgelassen: bool):
    """Ins Log (gedrosselt je Absender+Pfad) und in die Status-Liste."""
    adr = request.remote_addr or "?"
    eintrag = {"am": time.strftime("%Y-%m-%d %H:%M:%S"), "von": adr,
               "pfad": request.path, "grund": grund, "durchgelassen": durchgelassen}
    jetzt = time.monotonic()
    with _lock:
        _gemeldet.append(eintrag)
        schluessel = (adr, request.path)
        if jetzt - _zuletzt_geloggt.get(schluessel, -1e9) < _LOG_ABSTAND_S:
            return
        _zuletzt_geloggt[schluessel] = jetzt
    was = "durchgelassen (Modus melden)" if durchgelassen else "abgewiesen"
    state.push_log(f"ZUGANG: {request.method} {request.path} von {adr} {grund} — {was}")


# What a refused client is told to do next (2026-10-31). The default is now
# "an", so this message is what a forgotten node sees first: it has to say
# where the key goes, not just "no".
_NEXT_STEP = {
    "missing": "Put the access key (KeePass entry “ZENTRALE Zugang”) on the "
               "device that is asking, as a one-line file at "
               "~/.config/zentrale/zugang.schluessel (or point "
               "ZENTRALE_ZUGANG_SCHLUESSEL at it); the programs send it by "
               "themselves. For a browser: create a link on this machine with "
               "scripts/zugang.py link <address>.",
    "wrong": "The key the device sent does not match the one on this machine. "
             "Copy the current line from KeePass (“ZENTRALE Zugang”) into "
             "~/.config/zentrale/zugang.schluessel on the asking device.",
    "no_key_here": "This machine has no access key yet, so nobody gets in "
                   "from another device. On this machine: scripts/zugang.py "
                   "anlegen, then put the same line on the other devices.",
}


def _abweisen(art: str = "missing"):
    from i18n import _      # type: ignore  – core/i18n.py
    text = (_("No access: this ZENTRALE answers other devices only with its "
              "access key.") + " " + _(_NEXT_STEP[art]))
    if "text/html" in request.headers.get("Accept", ""):
        from html import escape
        r = Response('<!doctype html><meta charset="utf-8"><title>No access</title>'
                     f'<p style="font:16px system-ui;margin:20vh auto;max-width:520px">{escape(text)}</p>',
                     status=401, mimetype="text/html")
        r.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    else:
        r = jsonify({"error": text, "reason": art})
        r.status_code = 401
    r.headers["WWW-Authenticate"] = 'Bearer realm="zentrale"'
    r.headers["Cache-Control"] = "no-store"
    return r


def _link_einloesen():
    """?zugang=<marke> auf einer GET-Seite: Keks setzen und auf dieselbe
    Adresse ohne Marke weiterleiten — damit sie nicht im Verlauf stehen bleibt."""
    rest = [(k, v) for k, v in request.args.items(multi=True) if k != "zugang"]
    from urllib.parse import urlencode
    ziel = request.path + ("?" + urlencode(rest) if rest else "")
    r = redirect(ziel, code=303)
    r.set_cookie(zugang.KEKS_NAME, zugang.keks_wert(), max_age=zugang.KEKS_TAGE * 86400,
                 httponly=True, samesite="Lax", path="/")
    r.headers["Cache-Control"] = "no-store"
    return r


@bp.before_app_request
def pruefen():
    m = zugang.modus()
    if m == "aus" or lokal() or request.path in _FREI:
        return None
    if request.method == "GET" and zugang.link_passt(request.args.get("zugang")):
        return _link_einloesen()
    angebot = _bearer()
    if angebot is not None:
        if zugang.passt(angebot):
            return None
        grund, art = "mit falschem Schlüssel", "wrong"
    elif zugang.keks_passt(request.cookies.get(zugang.KEKS_NAME)):
        return None
    elif zugang.vorhanden():
        grund, art = "ohne Schlüssel", "missing"
    else:
        grund, art = "ohne Schlüssel (auf diesem Rechner ist auch keiner angelegt)", "no_key_here"
    if not zugang.vorhanden():
        art = "no_key_here"
    if m == "melden":
        _melden(grund, durchgelassen=True)
        return None
    _melden(grund, durchgelassen=False)
    return _abweisen(art)


@bp.route('/api/zugang', methods=['GET'])
def api_zugang():
    """Stand der Tür: Modus, ob ein Schlüssel da ist, wer zuletzt ohne kam.
    Nur von diesem Rechner — auch mit Schlüssel nicht von draußen."""
    if not lokal():
        return jsonify({"error": "Nur auf dem Rechner selbst."}), 403
    with _lock:
        zuletzt = list(_gemeldet)
    return jsonify({"modus": zugang.modus(), "schluessel_da": zugang.vorhanden(),
                    "ohne_schluessel": zuletzt})


@bp.route('/api/zugang', methods=['POST'])
def api_zugang_setzen():
    """Body {modus: aus|melden|an} — live und dauerhaft. Nur von diesem
    Rechner: ein abgegriffener Schlüssel darf die Tür nicht abschalten."""
    if not lokal():
        return jsonify({"error": "Nur auf dem Rechner selbst."}), 403
    neu = str((request.get_json(silent=True) or {}).get("modus", "")).strip().lower()
    if neu not in zugang.MODI:
        return jsonify({"error": "Modus ist aus, melden oder an."}), 400
    ai_config.set_override("zugang", neu, persist=True)
    state.push_log(f"ZUGANG: Modus jetzt „{neu}“")
    return jsonify({"modus": zugang.modus(), "schluessel_da": zugang.vorhanden()})
