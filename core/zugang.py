# core/zugang.py
#
# Der Zugangsschlüssel des Backends (memory/betrieb/zugang.md): wer nicht auf
# diesem Rechner sitzt, muss ihn mitschicken. Hier: Schlüssel anlegen, laden,
# ablegen, vergleichen, und die zwei abgeleiteten Werte für Browser (Keks und
# kurzlebiger Link). Die Prüfung jeder Anfrage macht ui/routen/zugang.py.
#
# Warum (2026-10-08): Flask lauscht auf 0.0.0.0:5000 ohne Anmeldung — jeder im
# WLAN konnte Chat, Kalender, Gedächtnis und Mail lesen und schreiben.
#
# Der Schlüssel liegt wie der Abgleich-Schlüssel in einer eigenen Datei (600)
# unter ~/.config/zentrale/, außerhalb von data/ und jedes Repos — damit geht
# er weder über den alten rsync-Weg noch über die Mitte noch in git. Ein
# Schlüssel für alle Rechner (in KeePass), weil der Pi das PC-Backend und
# später das Handy beliebige Backends ansprechen soll.

import hashlib
import hmac
import os
import secrets
import time

import ai_config
import dateien

VORGABE_PFAD = "~/.config/zentrale/zugang.schluessel"

# aus    = keine Prüfung (wie vor 2026-10-08)
# melden = durchlassen, aber jede Anfrage ohne Schlüssel ins Log schreiben
# an     = ohne Schlüssel kein Zugang (außer von diesem Rechner)
MODI = ("aus", "melden", "an")
# Vorgabe „melden" (2026-10-08): der Pi spricht das PC-Backend übers LAN an
# und hat den Schlüssel erst, wenn Sasha ihn dort ablegt. Mit „an" stünde die
# Wand morgen schwarz da. Sasha schaltet um, wenn das Log still ist.
VORGABE_MODUS = "melden"

LINK_GUELTIG_S = 10 * 60          # ein Browser-Link gilt 10 Minuten
KEKS_NAME = "zentrale_zugang"
KEKS_TAGE = 30


class SchluesselFehler(Exception):
    """Für Sasha lesbar: kein Schlüssel, kaputte Zeile, schon vorhanden."""


def pfad() -> str:
    return os.path.expanduser(ai_config.setting("zugang_schluessel") or VORGABE_PFAD)


def modus() -> str:
    """aus | melden | an. Ein Tippfehler zählt als „an": Sasha am Rechner
    selbst bleibt ohnehin frei, ein Vertipper darf die Tür nicht öffnen."""
    wert = str(ai_config.setting("zugang") or VORGABE_MODUS).strip().lower()
    return wert if wert in MODI else "an"


def pruefen(zeile: str) -> str:
    """Eine Schlüssel-Zeile → bereinigt, oder SchluesselFehler. Erlaubt ist,
    was erzeugen() liefert: URL-sichere Zeichen, mindestens 32 lang."""
    zeile = (zeile or "").strip()
    gueltig = len(zeile) >= 32 and all(c.isascii() and (c.isalnum() or c in "-_")
                                      for c in zeile)
    if not gueltig:
        raise SchluesselFehler(
            "Das ist kein gültiger Zugangsschlüssel (eine Zeile aus mindestens "
            "32 Buchstaben, Ziffern, - oder _ erwartet).")
    return zeile


def erzeugen() -> str:
    return secrets.token_urlsafe(32)          # 43 Zeichen, 256 Bit


# Kleiner Zwischenspeicher nach Änderungszeit: jede Anfrage fragt nach dem
# Schlüssel, die Datei ändert sich fast nie. Ein erneuerter Schlüssel gilt
# trotzdem sofort, ohne Neustart.
_cache = {"pfad": None, "mtime": None, "wert": None}


def laden() -> str | None:
    """Der Schlüssel dieses Rechners, oder None, wenn keiner (gültiger) da ist."""
    p = pfad()
    try:
        mtime = os.stat(p).st_mtime_ns
    except OSError:
        return None
    if _cache["pfad"] == p and _cache["mtime"] == mtime:
        return _cache["wert"]
    try:
        with open(p, encoding="ascii") as f:
            wert = pruefen(f.read())
    except (OSError, UnicodeDecodeError, SchluesselFehler):
        wert = None
    _cache.update(pfad=p, mtime=mtime, wert=wert)
    return wert


def vorhanden() -> bool:
    return laden() is not None


def ablegen(zeile: str) -> str:
    """Eine Zeile prüfen und nur für Sasha lesbar ablegen. → Pfad."""
    k = pruefen(zeile)
    dateien.atomar_schreiben(pfad(), k + "\n", geheim=True)
    return pfad()


def anlegen(erneuern: bool = False) -> str:
    """Neuen Schlüssel erzeugen und ablegen. Ohne erneuern=True wird ein
    vorhandener nicht überschrieben — sonst wären Pi und Handy still draußen."""
    if os.path.exists(pfad()) and not erneuern:
        raise SchluesselFehler(
            f"Es gibt schon einen Zugangsschlüssel ({pfad()}). Einen neuen gibt es "
            "nur mit „erneuern“ — danach brauchen alle anderen Geräte den neuen.")
    return ablegen(erzeugen())


def passt(angebot: str | None, schluessel: str | None = None) -> bool:
    """Zeitkonstanter Vergleich. Ohne Schlüssel auf dem Rechner passt nichts."""
    k = laden() if schluessel is None else schluessel
    if not k or not angebot:
        return False
    return hmac.compare_digest(angebot.strip().encode("utf-8"), k.encode("utf-8"))


def _mac(k: str, text: str) -> str:
    return hmac.new(k.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()


def keks_wert(schluessel: str | None = None) -> str | None:
    """Was im Browser-Keks steht: vom Schlüssel abgeleitet, nicht er selbst —
    ein ausgelesener Keks verrät den Schlüssel nicht. Erneuern macht alle
    Kekse ungültig."""
    k = laden() if schluessel is None else schluessel
    return _mac(k, "zentrale-zugang-keks") if k else None


def keks_passt(wert: str | None) -> bool:
    soll = keks_wert()
    return bool(soll and wert) and hmac.compare_digest(wert.encode("utf-8"),
                                                       soll.encode("utf-8"))


def link_marke(jetzt: float | None = None, schluessel: str | None = None) -> str | None:
    """Kurzlebige Marke für einen Browser-Link (`?zugang=<marke>`): Zeit plus
    Signatur. So steht nie der Schlüssel selbst in einer Adresszeile oder im
    Browser-Verlauf, und ein alter Link ist nach 10 Minuten wertlos."""
    k = laden() if schluessel is None else schluessel
    if not k:
        return None
    t = str(int(time.time() if jetzt is None else jetzt))
    return f"{t}.{_mac(k, 'zentrale-zugang-link:' + t)[:32]}"


def link_passt(marke: str | None, jetzt: float | None = None) -> bool:
    k = laden()
    if not k or not marke or "." not in marke:
        return False
    t, _, sig = marke.partition(".")
    if not t.isdigit():
        return False
    alter = (time.time() if jetzt is None else jetzt) - int(t)
    if not -60 <= alter <= LINK_GUELTIG_S:      # 1 min Uhrenversatz geduldet
        return False
    soll = _mac(k, "zentrale-zugang-link:" + t)[:32]
    return hmac.compare_digest(sig.encode("utf-8"), soll.encode("utf-8"))


def klient_kopf() -> dict:
    """Für Skripte auf einem Rechner mit Repo (ai_devtools …): der Kopf, den
    sie mitschicken. Leer, wenn hier kein Schlüssel liegt."""
    k = laden()
    return {"Authorization": f"Bearer {k}"} if k else {}
