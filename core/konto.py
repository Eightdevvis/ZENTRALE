# core/konto.py
#
# Das Konto bei der ZENTRALE-Cloud (memory/hub/knoten_beitritt.md, „Bauplan v1"):
# anlegen, anmelden, abmelden, Notfall, Passwort ändern — und was danach auf
# dem Gerät liegt: Sitzung + konto_schluessel in ~/.config/zentrale/konto.json
# (Rechte 600). Abmelden löscht beides.
#
# Anonym (23.10.2026): ein Konto ist ein Benutzername, nie eine Mail. Für alle
# dieselbe Art Name — keine „anonyme Option" (erzeugte Nummern), denn schon die
# Wahl wäre Metadaten. Regeln wie server/src/name.ts, gemeinsame Fälle in
# tests/daten/konto_namen.json.
#
# Kein Terminal, keine Fragen, kein print: jede Oberfläche (CLI, TUI, Handy,
# Browser …) ruft diese Funktionen und zeigt die Fehler (KontoFehler,
# englischer Satz) selbst. Das Rechnen steht in konto_schluessel, der Draht
# in cloud_api.

import json
import os
import re
import unicodedata

import ai_config
import cloud_api
import dateien
import konto_schluessel as ks

VORGABE_DATEI = "~/.config/zentrale/konto.json"


class KontoFehler(Exception):
    """Für den Menschen lesbar (englisch)."""


def datei() -> str:
    return os.path.expanduser(ai_config.setting("konto_datei") or VORGABE_DATEI)


# ── Der Name ───────────────────────────────────────────────────────────

_BENUTZERNAME = re.compile(r"[a-z][a-z0-9._-]{2,31}")
RESERVIERT = frozenset({
    "abuse", "admin", "administrator", "anonym", "anonymous", "api", "betreiber", "cloudflare",
    "contact", "help", "hilfe", "hostmaster", "info", "kontakt", "mod", "moderator", "no-reply",
    "noreply", "null", "official", "offiziell", "operator", "owner", "postmaster", "root",
    "security", "sicherheit", "staff", "superuser", "support", "sysadmin", "system", "team",
    "undefined", "webmaster", "zentrale",
})
RESERVIERT_ANFANG = ("admin", "zentrale")
KEINE_MAIL = ("No email needed — ZENTRALE accounts are anonymous. Use a username instead "
              "(3–32 characters: a–z, 0–9, '.', '_', '-', starting with a letter).")


class NameVergeben(KontoFehler):
    """Beim Anlegen: den Namen hat schon jemand (409 name_vergeben)."""


def name_lesen(name: str) -> str:
    """Getrimmt, NFC, klein — oder KontoFehler mit einem Satz für Menschen."""
    name = name or ""
    if "@" in name:
        raise KontoFehler(KEINE_MAIL)
    name = unicodedata.normalize("NFC", name.strip()).lower()
    if not _BENUTZERNAME.fullmatch(name):
        raise KontoFehler("A username has 3–32 characters (a–z, 0–9, '.', '_', '-') "
                          "and starts with a letter.")
    return name


def reserviert(name: str) -> bool:
    return name in RESERVIERT or name.startswith(RESERVIERT_ANFANG)


def neuer_name(name: str) -> str:
    """Wie name_lesen, aber für ein neues Konto: reservierte Namen gehen nicht."""
    name = name_lesen(name)
    if reserviert(name):
        raise KontoFehler("This username is reserved. Please choose another one.")
    return name


# ── Was auf dem Gerät liegt ────────────────────────────────────────────

def lesen():
    """→ dict {server, name, token, laeuft_ab, konto_schluessel, knoten} oder None."""
    try:
        with open(datei(), encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        raise KontoFehler(f"The account file {datei()} is damaged. "
                          "Log out and log in again.") from None
    # Ohne "name" (Format 1 hatte noch "mail"): wie abgemeldet.
    return d if isinstance(d, dict) and d.get("konto_schluessel") and d.get("name") else None


def angemeldet() -> bool:
    try:
        return lesen() is not None
    except KontoFehler:
        return False


def _speichern(server, name, token, laeuft_ab, konto_schluessel: bytes, knoten):
    dateien.json_schreiben(datei(), {
        "format": 2, "server": server, "name": name, "token": token,
        "laeuft_ab": laeuft_ab, "knoten": knoten,
        "konto_schluessel": konto_schluessel.decode("ascii")}, geheim=True)


def konto_schluessel() -> bytes:
    """Der Schlüssel, mit dem alle Daten in der Cloud verschlüsselt sind."""
    d = lesen()
    if d is None:
        raise KontoFehler("Not logged in. Run 'zentrale login' first.")
    return d["konto_schluessel"].encode("ascii")


def client(basis: str = None) -> cloud_api.Client:
    """Ein Client mit der Sitzung dieses Geräts (oder ohne, wenn abgemeldet).
    Die Adresse: ausdrücklich > Einstellung/Env > die beim Anmelden benutzte."""
    d = None
    try:
        d = lesen()
    except KontoFehler:
        pass
    if basis is None and d and d.get("server") and not ai_config.setting("cloud"):
        basis = d["server"]
    return cloud_api.Client(basis, token=(d or {}).get("token"))


def _cloud(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except cloud_api.CloudFehler as e:
        raise KontoFehler(str(e)) from None


# ── Konto anlegen ──────────────────────────────────────────────────────

MIN_PASSWORT = 10


def passwort_pruefen(passwort: str):
    if len(passwort or "") < MIN_PASSWORT:
        raise KontoFehler(f"The password must be at least {MIN_PASSWORT} characters long.")


class Entwurf:
    """Ein Konto, fertig gerechnet, aber noch nicht beim Server. So kann die
    Oberfläche den Notfallschlüssel zeigen und sich bestätigen lassen, dass
    er aufgeschrieben ist, BEVOR das Konto entsteht."""

    def __init__(self, passwort: str, kdf=None):
        passwort_pruefen(passwort)
        self.konto_schluessel = ks.neuer_konto_schluessel()
        self._notfall = os.urandom(32)
        self.notfall_text = ks.notfall_text(self._notfall)
        self.teile = ks.passwort_teile(passwort, self.konto_schluessel, kdf)
        self.teile.update(ks.notfall_teile(self._notfall, self.konto_schluessel))


def anlegen(entwurf: Entwurf, name: str, code: str, passwort: str, knoten: str = None,
            basis: str = None):
    """Konto beim Server anlegen (verbraucht den Einladungscode) und gleich
    anmelden. Name vergeben → NameVergeben; der Code bleibt dann frei, der
    Entwurf gilt weiter (mit einem anderen Namen noch einmal)."""
    name = neuer_name(name)
    code = "".join((code or "").split()).upper()     # ZB-XXXX-…, Groß/klein und Leerzeichen egal
    if not code:
        raise KontoFehler("An invite code is required.")
    c = cloud_api.Client(basis)
    try:
        c.post("/v1/konto", dict(entwurf.teile, name=name, code=code))
    except cloud_api.CloudFehler as e:
        if e.code == "name_vergeben":
            raise NameVergeben("This username is already taken. Please choose another one.") from None
        raise KontoFehler(str(e)) from None
    return anmelden(name, passwort, knoten, basis=c.basis)


# ── Anmelden / Abmelden ────────────────────────────────────────────────

def _vorab(c, name):
    d = _cloud(c.post, "/v1/vorab", {"name": name})
    try:
        return ks.b64u_lesen(d["salz"]), ks.kdf_lesen(d.get("kdf"))
    except (KeyError, TypeError, ValueError):
        raise KontoFehler("The cloud sent unreadable login values.") from None


def _sitzung(c, name, passwort, knoten):
    salz, kdf = _vorab(c, name)
    haupt = ks.hauptschluessel(passwort, salz, kdf)
    try:
        d = c.post("/v1/sitzung", {"name": name, "anmelde_schluessel": ks.anmelde_schluessel(haupt),
                                   "knoten": knoten})
    except cloud_api.CloudFehler as e:
        if e.status in (401, 403):
            raise KontoFehler("Wrong username or password.") from None
        raise KontoFehler(str(e)) from None
    k = ks.auspacken(ks.verpack_schluessel(haupt), d.get("verpackt_passwort"),
                     "The account key could not be unlocked with this password.")
    return d, k


def anmelden(name: str, passwort: str, knoten: str = None, basis: str = None) -> dict:
    """Anmelden und Sitzung + konto_schluessel ablegen. → gespeicherte Daten."""
    name = name_lesen(name)
    knoten = knoten or dateien.knoten()
    c = cloud_api.Client(basis)
    try:
        d, k = _sitzung(c, name, passwort, knoten)
    except ks.SchluesselFehler as e:
        raise KontoFehler(str(e)) from None
    _speichern(c.basis, name, d.get("token"), d.get("laeuft_ab"), k, knoten)
    return lesen()


def abmelden() -> bool:
    """Sitzung beim Server beenden (wenn erreichbar) und alles vom Gerät
    löschen. → True, wenn jemand angemeldet war."""
    try:
        d = lesen()
    except KontoFehler:
        d = {}
    if d and d.get("token"):
        try:
            cloud_api.Client(d.get("server"), token=d["token"], zeit=10).delete("/v1/sitzung")
        except cloud_api.CloudFehler:
            pass   # offline abmelden geht trotzdem; die Sitzung läuft dort ab
    try:
        os.remove(datei())
        return True
    except FileNotFoundError:
        return bool(d)


# ── Notfall und Passwort ───────────────────────────────────────────────

def wiederherstellen(name: str, notfall_text: str, neues_passwort: str,
                     knoten: str = None, basis: str = None) -> dict:
    """Mit dem Notfallschlüssel ein neues Passwort setzen und anmelden."""
    name = name_lesen(name)
    passwort_pruefen(neues_passwort)
    try:
        notfall = ks.notfall_lesen(notfall_text)
    except ks.SchluesselFehler as e:
        raise KontoFehler(str(e)) from None
    c = cloud_api.Client(basis)
    try:
        d = c.post("/v1/notfall", {"name": name, "notfall_beweis": ks.notfall_beweis(notfall)})
    except cloud_api.CloudFehler as e:
        if e.status in (401, 403, 404):
            raise KontoFehler("This emergency key does not match this account.") from None
        raise KontoFehler(str(e)) from None
    try:
        k = ks.auspacken(ks.notfall_schluessel(notfall), d.get("verpackt_notfall"),
                         "This emergency key does not match this account.")
    except ks.SchluesselFehler as e:
        raise KontoFehler(str(e)) from None
    neu = cloud_api.Client(c.basis, token=d.get("token"))
    _cloud(neu.put, "/v1/konto/passwort", ks.passwort_teile(neues_passwort, k))
    return anmelden(name, neues_passwort, knoten, basis=c.basis)


def passwort_aendern(altes: str, neues: str) -> dict:
    """Nur verpackt_passwort ändert sich; der konto_schluessel (und damit
    alle Daten) bleibt. Der Server prüft das alte Passwort über
    `altes_anmelde_schluessel` (aus altem Salz + alten KDF-Werten) und
    beendet alle anderen Sitzungen; diese hier bleibt."""
    passwort_pruefen(neues)
    d = lesen()
    if d is None:
        raise KontoFehler("Not logged in. Run 'zentrale login' first.")
    c = cloud_api.Client(d.get("server"), token=d.get("token"))
    try:
        salz, kdf = _vorab(c, d["name"])
        alt = ks.anmelde_schluessel(ks.hauptschluessel(altes, salz, kdf))
        teile = ks.passwort_teile(neues, d["konto_schluessel"].encode("ascii"))
    except ks.SchluesselFehler as e:
        raise KontoFehler(str(e)) from None
    try:
        c.put("/v1/konto/passwort", dict(teile, altes_anmelde_schluessel=alt))
    except cloud_api.CloudFehler as e:
        if e.code == "nicht_angemeldet":
            raise KontoFehler("Your session has expired. Run 'zentrale login' first.") from None
        if e.status in (401, 403):
            raise KontoFehler("Wrong current password.") from None
        raise KontoFehler(str(e)) from None
    return lesen()
