# core/cloud_nutzung.py
#
# Wie nah ist die Cloud an den Gratis-Grenzen von Cloudflare? Fragt
# GET /v1/nutzung (nur Betreiber-Konten, sonst 403 nur_betreiber; Server:
# server/src/nutzung.ts) und merkt sich die Antwort 1 h in einer Datei pro
# Rechner (~/.local/state/zentrale/nutzung.json, umlenkbar per Einstellung
# `nutzung_dir` / ZENTRALE_NUTZUNG_DIR). Nicht data/: das synct, und jeder
# Rechner kann die Zahl selbst holen.
#
# `warnung()` ist für den Start von `zentrale` und für `zentrale status`: nie
# eine Ausnahme, höchstens ZEIT_START Sekunden Netz, und auch ein Fehlschlag
# wird 1 h gemerkt — offline wartet der Start also höchstens einmal pro Stunde
# kurz. Kein Terminal, kein print; die Texte macht die Oberfläche.

import json
import os
import time

import ai_config
import cloud_api
import dateien
import konto

GUELTIG_S = 3600               # Antwort (auch Fehlschlag) gilt 1 h
KEIN_BETREIBER_S = 24 * 3600   # 403: einen Tag lang nicht mehr fragen
ZEIT_START = 1.5               # Sekunden Netz beim Start, nicht mehr


class NurBetreiber(Exception):
    """Dieses Konto darf die Nutzung nicht sehen (403 nur_betreiber)."""


def _pfad() -> str:
    eigen = ai_config.setting("nutzung_dir")
    if eigen:
        basis = os.path.abspath(os.path.expanduser(str(eigen)))
    else:
        basis = os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
                             "zentrale")
    return os.path.join(basis, "nutzung.json")


def _cache_lesen() -> dict:
    try:
        with open(_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _cache_schreiben(eintrag: dict):
    try:
        os.makedirs(os.path.dirname(_pfad()), exist_ok=True)
        dateien.json_schreiben(_pfad(), eintrag)
    except OSError:
        pass            # ohne Cache fragt der nächste Start eben wieder


def _wer(c: cloud_api.Client) -> str:
    """Cache-Schlüssel: Konto + Server. Ein anderes Konto erbt nichts."""
    return f"{(konto.lesen() or {}).get('mail', '')}@{c.basis}"


def holen(zeit: float = cloud_api.ZEIT) -> dict:
    """Den Bericht jetzt vom Server holen und merken. → {zeit, grenzen, warnungen, …}.
    NurBetreiber bei 403 nur_betreiber, sonst CloudFehler / KontoFehler."""
    c = konto.client()
    if not c.token:
        raise konto.KontoFehler("Not logged in. Run 'zentrale login' first.")
    c.zeit = zeit
    wer = _wer(c)
    try:
        d = c.get("/v1/nutzung")
    except cloud_api.CloudFehler as e:
        if e.code == "nur_betreiber" or e.status == 403:
            _cache_schreiben({"wer": wer, "am": time.time(), "art": "kein_betreiber"})
            raise NurBetreiber(str(e)) from None
        raise
    if not isinstance(d, dict) or not isinstance(d.get("grenzen"), list):
        raise cloud_api.CloudFehler("The cloud sent an unreadable usage report.", "antwort", 200)
    _cache_schreiben({"wer": wer, "am": time.time(), "art": "bericht", "bericht": d})
    return d


def warnung(jetzt: float = None):
    """Die höchste Warnung (≥ 50 %) für Betreiber-Konten, sonst None.
    → {"text", "level", "weitere"} — nie eine Ausnahme, schnell und offline-fest."""
    try:
        if not konto.angemeldet():
            return None
        jetzt = time.time() if jetzt is None else jetzt
        c = konto.client()
        wer = _wer(c)
        e = _cache_lesen()
        alter = jetzt - float(e.get("am") or 0)
        frisch = e.get("wer") == wer and 0 <= alter < (
            KEIN_BETREIBER_S if e.get("art") == "kein_betreiber" else GUELTIG_S)
        if frisch:
            bericht = e.get("bericht") if e.get("art") == "bericht" else None
        else:
            try:
                bericht = holen(ZEIT_START)
            except NurBetreiber:
                return None
            except Exception:   # noqa: BLE001 — offline, Zeitüberschreitung, kaputt: nie den Start stören
                _cache_schreiben({"wer": wer, "am": jetzt, "art": "fehler"})
                return None
        w = (bericht or {}).get("warnungen") or []
        if not w or not isinstance(w[0], dict):
            return None
        return {"text": str(w[0].get("text") or ""), "level": str(w[0].get("level") or ""),
                "weitere": len(w) - 1}
    except Exception:   # noqa: BLE001 — eine Warnzeile darf nie etwas kaputt machen
        return None
