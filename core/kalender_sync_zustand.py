# core/kalender_sync_zustand.py
#
# Wie steht der Google-Abgleich des Kalenders? (seit 16.10.2026)
#
# Anlass: vom 10. bis 13.10. lief der Sync-Timer gar nicht, ab 14.10. 16:33
# brach jeder Lauf ab (Google-Zugang abgelaufen) — beides war in ZENTRALE
# unsichtbar. Sasha: „dass es expired is hätte in zentrale angezeigt werden
# müssen".
#
# scripts/kalender_sync.py schreibt nach JEDEM Lauf eine kleine JSON-Datei
# (ein Rechner, eine Datei — jeder Rechner synct selbst mit Google):
#
#   {"letzter_versuch": ISO, "letzter_erfolg": ISO|null, "ok": bool,
#    "art": "ok"|"zugang"|"netz"|"loeschsperre"|"sicherung"|"einrichtung"|"sonstig",
#    "fehler": kurzer Klartext|null, "seit": ISO|null (erster Fehlschlag
#    nach dem letzten Erfolg), "exit": int}
#
# Hier wird sie gelesen und bewertet (bewerten): Backend-Route
# GET /api/calendar/sync, das Feld „sync" in /api/calendar und ein Alarm im
# Alarm-Kanal (alarme → kalender.alarme → state.set_alarms). Doku:
# memory/werkzeuge/kalender_sync_zustand.md.
#
# Keine Datei = auf diesem Rechner läuft kein Sync → nichts anzeigen.

import hashlib
import json
import os
from datetime import datetime, timedelta
import uhr  # die eine Uhr (core/uhr.py)

# Ab wann gilt der Stand als alt (Timer läuft alle 3 min)? Sasha entscheidet.
ALT_MIN = 10
# Kein Netz ist auf dem Laptop oft gewollt — erst warnen, wenn so lange
# (Minuten) kein Abgleich mehr gelang.
NETZ_GEDULD_MIN = 60

# art → (kurz für Köpfe/Statuszeilen, Klartext für Datei und Alarm)
ARTEN = {
    "zugang": ("Zugang abgelaufen", "Google-Zugang abgelaufen — neu anmelden"),
    "netz": ("kein Netz", "kein Netz — Google nicht erreichbar"),
    "loeschsperre": ("Löschsperre", "Löschsperre: lokal fehlen Termine — nicht gesynct"),
    "sicherung": ("Sicherung fehlgeschlagen",
                  "Sicherungskopie von Google fehlgeschlagen — nicht gesynct"),
    "einrichtung": ("nicht eingerichtet", "Sync nicht eingerichtet"),
    "sonstig": ("Fehler", "Abgleich fehlgeschlagen"),
}

# Woran man die Fälle in der Ausgabe von vdirsyncer erkennt (klein geschrieben).
_ZUGANG = ("invalid_grant", "token has been expired or revoked",
           "invalid_client", "unauthorized_client")
_NETZ = ("name or service not known", "temporary failure in name resolution",
         "failed to establish a new connection", "network is unreachable",
         "connection refused", "connectionerror", "max retries exceeded",
         "timed out", "nodename nor servname")


def pfad() -> str:
    """Umlenkbar (Tests: tests/conftest.py und der venv-Riegel)."""
    return os.path.expanduser(os.environ.get("ZENTRALE_KALENDER_SYNC_ZUSTAND")
                              or "~/.local/share/zentrale/kalender_sync.json")


def erkennen(code: int, ausgabe: str = "", stufe: str = "") -> tuple:
    """(art, fehler-Klartext) aus Exit-Code, Ausgabe und Stufe des Laufs.
    `stufe`: "sicherung" (Nur-Lese-Kopie), "loeschsperre", "einrichtung"
    oder "" (der eigentliche Abgleich)."""
    if code == 0:
        return "ok", None
    roh = (ausgabe or "").lower()
    if any(m in roh for m in _ZUGANG):
        return "zugang", ARTEN["zugang"][1]
    if any(m in roh for m in _NETZ):
        return "netz", ARTEN["netz"][1]
    if stufe in ("loeschsperre", "sicherung", "einrichtung"):
        return stufe, ARTEN[stufe][1]
    letzte = _letzte_fehlerzeile(ausgabe)
    text = ARTEN["sonstig"][1] + " (Exit %d)" % code
    return "sonstig", text + (": " + letzte if letzte else "")


def _letzte_fehlerzeile(ausgabe: str) -> str:
    for zeile in reversed((ausgabe or "").splitlines()):
        z = zeile.strip()
        if "error" in z.lower() or "fehler" in z.lower():
            return z[:100]
    return ""


def lesen() -> dict | None:
    try:
        with open(pfad(), encoding="utf-8") as f:
            z = json.load(f)
        return z if isinstance(z, dict) else None
    except (OSError, ValueError):
        return None


def schreiben(code: int, art: str, fehler: str | None, jetzt: datetime | None = None) -> dict:
    """Den Stand nach einem Lauf festhalten (atomar). `letzter_erfolg` und
    `seit` kommen aus dem alten Stand mit."""
    jetzt = (jetzt or uhr.jetzt()).replace(microsecond=0)
    alt = lesen() or {}
    ok = art == "ok"
    z = {"letzter_versuch": jetzt.isoformat(),
         "letzter_erfolg": jetzt.isoformat() if ok else alt.get("letzter_erfolg"),
         "ok": ok, "art": art, "fehler": None if ok else fehler,
         "seit": None if ok else (alt.get("seit") if not alt.get("ok", True) and alt.get("seit")
                                  else jetzt.isoformat()),
         "exit": int(code)}
    p = pfad()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(z, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)
    return z


def uebernehmen(z: dict | None) -> None:
    """Auf einem Gerät, das gerade NICHT die Brücke ist (memory/hub/adapter.md):
    den Stand der Brücke hierher legen (er reist im Mietvertrag mit). Kein
    Stand → die eigene Datei weg (sonst warnte ein alter eigener Stand
    „läuft nicht", obwohl ein anderes Gerät längst fährt)."""
    p = pfad()
    if not z:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(z, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def _zeit(iso) -> datetime | None:
    try:
        return datetime.fromisoformat(iso) if iso else None
    except (TypeError, ValueError):
        return None


def _wann(d: datetime) -> str:
    return d.strftime("%d.%m. %H:%M")


def _google_aus() -> bool:
    try:
        import adapter      # Schicht 1 wie dieses Modul; spät, nur wenn gefragt
        return adapter.kalender_ohne_bruecke()
    except Exception:       # noqa: BLE001 — ohne lesbaren Adapter gilt der Stand
        return False


def bewerten(z: dict | None = None, jetzt: datetime | None = None) -> dict:
    """Der Stand plus Urteil: {bekannt, problem, alt, hinweis, kurz, …Felder}.
    `hinweis` ist die fertige Warnzeile („⚠ google-sync: Zugang abgelaufen —
    seit 14.10. 16:33"), `kurz` die leise Zeile ohne Problem („google ✓ 16:31")."""
    if z is None:
        # Kalender nur über die Mitte (kalender-mitte, ohne Google-Anschluss):
        # Google fährt bewusst niemand — ein alter Stand ist kein „läuft nicht".
        z = None if _google_aus() else lesen()
    if not z:
        return {"bekannt": False, "problem": False, "alt": False,
                "hinweis": None, "kurz": None}
    jetzt = jetzt or uhr.jetzt()
    grenze = timedelta(minutes=ALT_MIN)
    versuch, erfolg = _zeit(z.get("letzter_versuch")), _zeit(z.get("letzter_erfolg"))
    alt = (versuch is None or jetzt - versuch > grenze
           or erfolg is None or jetzt - erfolg > grenze)
    aus = dict(z, bekannt=True, alt=alt, problem=False, hinweis=None, kurz=None)
    if versuch is None or jetzt - versuch > grenze:
        aus["problem"] = True
        aus["hinweis"] = "⚠ google-sync läuft nicht — letzter Versuch %s" % (
            _wann(versuch) if versuch else "unbekannt")
        aus["kurz_art"] = "läuft nicht"
    elif not z.get("ok"):
        art = z.get("art") if z.get("art") in ARTEN else "sonstig"
        geduld = timedelta(minutes=NETZ_GEDULD_MIN)
        if art != "netz" or erfolg is None or jetzt - erfolg > geduld:
            seit = _zeit(z.get("seit")) or versuch
            aus["problem"] = True
            aus["kurz_art"] = ARTEN[art][0]
            aus["hinweis"] = "⚠ google-sync: %s — seit %s" % (ARTEN[art][0], _wann(seit))
    if not aus["problem"] and erfolg:
        aus["kurz"] = "google ✓ %s" % erfolg.strftime("%H:%M")
        if z.get("bruecke"):
            aus["kurz"] += " · " + str(z["bruecke"])
    return aus


def alarme(jetzt: datetime | None = None) -> list:
    """Für den Alarm-Kanal (state.set_alarms): ein Alarm, solange der Sync
    ein Problem hat; sonst []. Form wie kalender.open_alarms."""
    b = bewerten(jetzt=jetzt)
    if not b["problem"]:
        return []
    fehler = b.get("fehler") if b.get("kurz_art") != "läuft nicht" else None
    text = b["hinweis"].lstrip("⚠").strip()
    if fehler:
        text += " (" + fehler + ")"
    aid = hashlib.md5(("Google-Sync|%s|%s" % (b.get("kurz_art"), b.get("seit")))
                      .encode("utf-8")).hexdigest()[:8]
    return [{"id": aid, "kind": "Google-Sync", "text": text}]
