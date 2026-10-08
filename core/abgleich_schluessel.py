# core/abgleich_schluessel.py
#
# Der eine Schlüssel für die Mitte (memory/betrieb/abgleich.md): anlegen,
# laden, ablegen, Dateien ver- und entschlüsseln, Pfade verstecken.
#
# Warum Fernet und nicht git-crypt/age (2026-10-08): `cryptography` ist schon
# im venv (mail_secrets nutzt es), kein neues Systempaket auf jedem Rechner,
# und der Klartext erreicht den git-Klon nie — ein git-Filter, der auf einem
# Rechner fehlt, schiebt dagegen still Klartext hoch.
#
# Der Schlüssel liegt in einer eigenen Datei (600) außerhalb von data/ und
# außerhalb jedes Repos. Wo, sagt die Einstellung `abgleich_schluessel`.

import base64
import hashlib
import hmac
import os

import ai_config
import dateien

VORGABE_PFAD = "~/.config/zentrale/abgleich.schluessel"


class SchluesselFehler(Exception):
    """Für Sasha lesbar: kein Schlüssel, falscher Schlüssel, kaputte Zeile."""


def pfad() -> str:
    return os.path.expanduser(ai_config.setting("abgleich_schluessel") or VORGABE_PFAD)


def pruefen(zeile: str) -> bytes:
    """Eine Schlüssel-Zeile → Bytes für Fernet, oder SchluesselFehler."""
    zeile = (zeile or "").strip()
    try:
        roh = base64.urlsafe_b64decode(zeile.encode("ascii"))
    except Exception:
        roh = b""
    if len(roh) != 32:
        raise SchluesselFehler(
            "Das ist kein gültiger Abgleich-Schlüssel (eine Zeile aus 44 Zeichen erwartet).")
    return zeile.encode("ascii")


def vorhanden() -> bool:
    return os.path.exists(pfad())


def laden() -> bytes:
    """Den Schlüssel dieses Rechners. Fehlt er → SchluesselFehler mit dem Weg."""
    try:
        with open(pfad(), encoding="ascii") as f:
            return pruefen(f.read())
    except FileNotFoundError:
        raise SchluesselFehler(
            "Auf diesem Rechner liegt kein Abgleich-Schlüssel. Ohne ihn sind die "
            "Daten in der Mitte nicht lesbar. Neu anlegen (nur beim allerersten "
            "Mal) oder den aus KeePass eingeben.") from None
    except UnicodeDecodeError:
        raise SchluesselFehler("Die Schlüssel-Datei ist beschädigt.") from None


def ablegen(zeile: str) -> str:
    """Eine Schlüssel-Zeile prüfen und nur für Sasha lesbar ablegen. → Pfad."""
    k = pruefen(zeile)
    dateien.atomar_schreiben(pfad(), k.decode("ascii") + "\n", geheim=True)
    return pfad()


def anlegen() -> str:
    """Neuen Schlüssel erzeugen und ablegen. Weigert sich, einen vorhandenen
    zu überschreiben — der alte wäre sonst weg, und mit ihm die Mitte."""
    if vorhanden():
        raise SchluesselFehler(
            f"Es gibt schon einen Schlüssel ({pfad()}). Ein neuer würde die Mitte "
            "unlesbar machen — deshalb lege ich keinen an.")
    from cryptography.fernet import Fernet
    return ablegen(Fernet.generate_key().decode("ascii"))


class Tresor:
    """Ver- und Entschlüsseln mit einem Schlüssel."""

    def __init__(self, schluessel: bytes):
        from cryptography.fernet import Fernet
        self._fernet = Fernet(schluessel)
        # Ein eigener Unterschlüssel für die versteckten Namen: derselbe Pfad
        # ergibt immer denselben Namen (sonst wäre jeder Abgleich ein Umzug
        # aller Dateien), verrät aber ohne Schlüssel nichts.
        self._namen = hashlib.sha256(b"zentrale-abgleich-namen\0" + schluessel).digest()

    def zu(self, klartext: bytes) -> bytes:
        return self._fernet.encrypt(klartext)

    def auf(self, geheim: bytes) -> bytes:
        from cryptography.fernet import InvalidToken
        try:
            return self._fernet.decrypt(geheim)
        except InvalidToken:
            raise SchluesselFehler(
                "Der Schlüssel passt nicht zur Mitte — die Daten dort sind mit einem "
                "anderen verschlüsselt. Den richtigen aus KeePass eingeben.") from None

    def name(self, rel: str) -> str:
        """Versteckter Dateiname in der Mitte für einen relativen Pfad."""
        return hmac.new(self._namen, rel.encode("utf-8"), hashlib.sha256).hexdigest()[:32]
