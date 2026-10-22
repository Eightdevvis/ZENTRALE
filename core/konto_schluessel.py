# core/konto_schluessel.py
#
# Das Schlüssel-Schema des Kontos (memory/hub/knoten_beitritt.md, „Bauplan v1
# — Schlüssel"). Zero-Knowledge nach dem Bitwarden-Modell: der Server sieht
# nie Passwort, Schlüssel oder Klartext. Hier steht NUR Rechnen — kein Netz,
# keine Datei, kein Terminal —, damit jede andere Oberfläche (Handy in Dart,
# Browser mit WebCrypto + argon2-wasm, Brille …) dasselbe aus der Doku
# nachbauen kann. Prüfstein dafür: tests/daten/konto_testvektoren.json.
#
#   passwort ─Argon2id(salz, t, m, p)→ hauptschluessel (32 B)
#   hauptschluessel ─HKDF info="zentrale/anmelden/v1"→ anmelde_schluessel (an den Server)
#   hauptschluessel ─HKDF info="zentrale/verpacken/v1"→ verpack_schluessel (Fernet)
#   konto_schluessel  = Fernet.generate_key()   ← verschlüsselt alle Daten
#   verpackt_passwort = Fernet(verpack_schluessel).encrypt(konto_schluessel)
#   notfall (32 B)    ─HKDF info="zentrale/notfall/v1"→ Fernet-Schlüssel → verpackt_notfall
#   notfall (32 B)    ─HKDF info="zentrale/notfall-beweis/v1"→ notfall_beweis (an den Server)
#
# Festlegungen, die die Doku offen ließ (2026-10-22, gleich im Bauplan):
#   - HKDF-SHA256 ohne Salz (RFC 5869: Salz = 32 Null-Bytes), Länge 32.
#   - Bytes an den Server (salz, anmelde_schluessel, notfall_beweis):
#     base64url OHNE Auffüllung. Fernet-Schlüssel: base64url MIT Auffüllung
#     (das Fernet-Format selbst).
#   - Passwort als UTF-8 nach Unicode-NFC.
#   - kdf = {"name": "argon2id", "t": 3, "m": 65536, "p": 4}, m in KiB.

import base64
import os
import unicodedata

KDF_VORGABE = {"name": "argon2id", "t": 3, "m": 65536, "p": 4}
INFO_ANMELDEN = b"zentrale/anmelden/v1"
INFO_VERPACKEN = b"zentrale/verpacken/v1"
INFO_NOTFALL = b"zentrale/notfall/v1"
INFO_NOTFALL_BEWEIS = b"zentrale/notfall-beweis/v1"
SALZ_BYTES = 16


class SchluesselFehler(Exception):
    """Falsches Passwort, falscher Notfallschlüssel, kaputte Werte."""


def b64u(roh: bytes) -> str:
    """base64url ohne Auffüllung (für alles, was an den Server geht)."""
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode("ascii")


def b64u_lesen(text: str) -> bytes:
    text = (text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def kdf_lesen(kdf) -> dict:
    """Die KDF-Werte vom Server → {name, t, m, p}. Nimmt auch die Langnamen
    (iterations/memory/parallelism), falls der Server sie so schreibt."""
    kdf = dict(kdf or {})
    name = str(kdf.get("name") or kdf.get("art") or "argon2id").lower()
    if name != "argon2id":
        raise SchluesselFehler(f"Unsupported key derivation '{name}' (expected argon2id).")
    try:
        t = int(kdf.get("t", kdf.get("iterations", KDF_VORGABE["t"])))
        m = int(kdf.get("m", kdf.get("memory", KDF_VORGABE["m"])))
        p = int(kdf.get("p", kdf.get("parallelism", kdf.get("lanes", KDF_VORGABE["p"]))))
    except (TypeError, ValueError):
        raise SchluesselFehler("The server sent unreadable key derivation values.") from None
    if t < 1 or p < 1 or m < 8 * p:
        raise SchluesselFehler("The server sent invalid key derivation values.")
    return {"name": "argon2id", "t": t, "m": m, "p": p}


def hauptschluessel(passwort: str, salz: bytes, kdf=None) -> bytes:
    from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
    k = kdf_lesen(kdf or KDF_VORGABE)
    roh = unicodedata.normalize("NFC", passwort).encode("utf-8")
    return Argon2id(salt=salz, length=32, iterations=k["t"], lanes=k["p"],
                    memory_cost=k["m"]).derive(roh)


def hkdf(eingabe: bytes, info: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=info).derive(eingabe)


def fernet_schluessel(roh32: bytes) -> bytes:
    return base64.urlsafe_b64encode(roh32)


def anmelde_schluessel(haupt: bytes) -> str:
    return b64u(hkdf(haupt, INFO_ANMELDEN))


def verpack_schluessel(haupt: bytes) -> bytes:
    return fernet_schluessel(hkdf(haupt, INFO_VERPACKEN))


def notfall_schluessel(notfall: bytes) -> bytes:
    return fernet_schluessel(hkdf(notfall, INFO_NOTFALL))


def notfall_beweis(notfall: bytes) -> str:
    return b64u(hkdf(notfall, INFO_NOTFALL_BEWEIS))


def verpacken(fernet_key: bytes, konto_schluessel: bytes) -> str:
    from cryptography.fernet import Fernet
    return Fernet(fernet_key).encrypt(konto_schluessel).decode("ascii")


def auspacken(fernet_key: bytes, verpackt: str, fehler: str) -> bytes:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        k = Fernet(fernet_key).decrypt((verpackt or "").encode("ascii"))
    except (InvalidToken, ValueError, UnicodeEncodeError):
        raise SchluesselFehler(fehler) from None
    try:
        Fernet(k)
    except ValueError:
        raise SchluesselFehler("The account key from the server is damaged.") from None
    return k


# ── Notfallschlüssel als Text ───────────────────────────────────────────

def notfall_text(notfall: bytes) -> str:
    """32 Bytes → Base32 (RFC 4648, ohne '='), in Vierergruppen mit '-'."""
    b32 = base64.b32encode(notfall).decode("ascii").rstrip("=")
    return "-".join(b32[i:i + 4] for i in range(0, len(b32), 4))


def notfall_lesen(text: str) -> bytes:
    """Getippt mit Leerzeichen, Bindestrichen, klein — alles egal."""
    rein = "".join(c for c in (text or "").upper() if c.isalnum())
    # Häufige Verwechsler: Base32 kennt weder 0, 1 noch 8.
    rein = rein.replace("0", "O").replace("1", "I").replace("8", "B")
    try:
        roh = base64.b32decode(rein + "=" * (-len(rein) % 8))
    except (ValueError, base64.binascii.Error):
        roh = b""
    if len(roh) != 32:
        raise SchluesselFehler(
            "That is not a valid emergency key (52 letters and digits in groups of 4).")
    return roh


# ── Fertige Bündel für Konto anlegen / Passwort setzen ─────────────────

def neues_salz() -> bytes:
    return os.urandom(SALZ_BYTES)


def neuer_konto_schluessel() -> bytes:
    from cryptography.fernet import Fernet
    return Fernet.generate_key()


def passwort_teile(passwort: str, konto_schluessel: bytes, kdf=None, salz=None) -> dict:
    """→ {salz, kdf, anmelde_schluessel, verpackt_passwort} für den Server."""
    kdf = kdf_lesen(kdf or KDF_VORGABE)
    salz = salz if salz is not None else neues_salz()
    haupt = hauptschluessel(passwort, salz, kdf)
    return {"salz": b64u(salz), "kdf": kdf,
            "anmelde_schluessel": anmelde_schluessel(haupt),
            "verpackt_passwort": verpacken(verpack_schluessel(haupt), konto_schluessel)}


def notfall_teile(notfall: bytes, konto_schluessel: bytes) -> dict:
    """→ {verpackt_notfall, notfall_beweis} für den Server."""
    return {"verpackt_notfall": verpacken(notfall_schluessel(notfall), konto_schluessel),
            "notfall_beweis": notfall_beweis(notfall)}
