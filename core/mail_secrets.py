# core/mail_secrets.py
#
# Verschlüsselter Zugangsdaten-Speicher für die Mail-Konten.
#
# ── Warum verschlüsselt + warum so ────────────────────────────────────
# Mail-Passwörter sind das "HIGH value"-Asset aus Sashas Bedrohungsmodell
# (sicherheit.md). Zwei Anforderungen, die zusammen die Wahl bestimmen:
#   - SECURITY: nicht im Klartext auf der Platte.
#   - MULTI-DEVICE: ZENTRALE läuft auf mehreren Geräten, die Konten sollen
#     überall verfügbar sein.
# Lösung: ein FERNET-verschlüsselter Blob (data/mail_secrets.enc). Weil der
# Inhalt Ciphertext ist, darf die Datei gefahrlos über Syncthing/scp auf alle
# Geräte synchronisiert werden — sie entschlüsselt sich nur mit der Passphrase
# aus der Env-Var ZENTRALE_MAIL_KEY, die jedes Gerät einmal lokal hält (z.B.
# systemd EnvironmentFile, chmod 600). Kein OS-Keyring: der PC-Backend läuft
# als systemd OHNE Login-Session -> GNOME-Keyring wäre gesperrt.
#
# ── Graceful degradation ──────────────────────────────────────────────
# Fehlt die `cryptography`-Lib, die Passphrase oder die Datei, liefert
# load_accounts() einfach [] (mit einem Hinweis im Log). Das Mail-System
# bleibt dann schlicht aus — kein Crash, kein Boot-Blocker.

import os
import json
import base64
import hashlib

_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_STORE = os.path.join(_DIR, "data", "mail_secrets.enc")
_ENV_KEY = "ZENTRALE_MAIL_KEY"

# scrypt-Parameter (interaktiv, RAM-moderat). dklen=32 -> Fernet-Schlüssel.
_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)


def _log(msg):
    # state importiert erst spät, um Zirkelimporte beim Boot zu vermeiden.
    try:
        import state  # type: ignore
        state.push_log(msg)
    except Exception:
        print(msg, flush=True)


def _fernet_for(passphrase, salt):
    from cryptography.fernet import Fernet  # lazy: nur wenn wirklich gebraucht
    key = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **_SCRYPT)
    return Fernet(base64.urlsafe_b64encode(key))


def available():
    """True, wenn Verschlüsselung + Passphrase grundsätzlich nutzbar sind."""
    if not os.environ.get(_ENV_KEY):
        return False
    try:
        import cryptography  # noqa: F401
    except Exception:
        return False
    return True


def load_accounts():
    """Liste der Konto-Dicts (entschlüsselt) oder [] wenn nicht verfügbar."""
    passphrase = os.environ.get(_ENV_KEY)
    if not passphrase:
        return []
    if not os.path.exists(_STORE):
        return []
    try:
        with open(_STORE, "rb") as f:
            envelope = json.loads(f.read().decode("utf-8"))
        salt = base64.b64decode(envelope["salt"])
        token = envelope["ct"].encode("utf-8")
        plain = _fernet_for(passphrase, salt).decrypt(token)
        data = json.loads(plain.decode("utf-8"))
        return data.get("accounts", [])
    except ImportError:
        _log("MAIL: `cryptography` fehlt — Konten bleiben verschlüsselt unlesbar "
             "(venv/bin/pip install cryptography)")
        return []
    except Exception as e:
        # Falsche Passphrase, kaputtes File o.ä. -> NICHT crashen, nur warnen.
        _log(f"MAIL: Zugangsdaten nicht entschlüsselbar ({type(e).__name__}) — "
             "stimmt ZENTRALE_MAIL_KEY?")
        return []


def upsert(acct):
    """Fügt ein Konto ein oder ersetzt das gleichnamige (by `name`) und
    schreibt verschlüsselt. Praktisch für den OAuth-Login, der ein Konto
    inkl. frischem Refresh-Token zurückspeichern muss.
    """
    accts = [a for a in load_accounts() if a.get("name") != acct["name"]]
    accts.append(acct)
    save_accounts(accts)
    return acct


def save_accounts(accounts):
    """Verschlüsselt die Konto-Liste und schreibt sie atomar."""
    passphrase = os.environ.get(_ENV_KEY)
    if not passphrase:
        raise RuntimeError(f"{_ENV_KEY} ist nicht gesetzt — keine Passphrase zum Verschlüsseln")
    salt = os.urandom(16)
    token = _fernet_for(passphrase, salt).encrypt(
        json.dumps({"accounts": accounts}, ensure_ascii=False).encode("utf-8")
    )
    envelope = {
        "kdf": "scrypt",
        "salt": base64.b64encode(salt).decode("ascii"),
        "ct": token.decode("utf-8"),
    }
    os.makedirs(os.path.dirname(_STORE), exist_ok=True)
    tmp = _STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(envelope))
    os.replace(tmp, _STORE)


# ── kleines CLI, damit man Konten anlegt ohne Klartext-JSON von Hand ──
#   venv/bin/python -m core.mail_secrets add
#   venv/bin/python -m core.mail_secrets list
#   venv/bin/python -m core.mail_secrets remove <name>
# Erwartet ZENTRALE_MAIL_KEY in der Env.

def _cli():
    import sys
    import getpass

    args = sys.argv[1:]
    cmd = args[0] if args else "list"

    if not os.environ.get(_ENV_KEY):
        print(f"FEHLER: {_ENV_KEY} nicht gesetzt. Beispiel:\n"
              f"  export {_ENV_KEY}='deine-master-passphrase'", file=sys.stderr)
        return 2

    if cmd == "list":
        accts = load_accounts()
        if not accts:
            print("(keine Konten gespeichert oder Passphrase falsch)")
        for a in accts:
            star = "" if a.get("enabled", True) else "  [aus]"
            print(f"- {a['name']:<14} {a.get('provider','?'):<8} "
                  f"{a.get('user','?')}{star}")
        return 0

    if cmd == "remove":
        if len(args) < 2:
            print("Nutzung: remove <name>", file=sys.stderr)
            return 2
        accts = [a for a in load_accounts() if a["name"] != args[1]]
        save_accounts(accts)
        print(f"'{args[1]}' entfernt. Verbleibend: {len(accts)}")
        return 0

    if cmd == "add":
        print("Neues Mail-Konto anlegen.")
        name = input("Kurzname (z.B. proton): ").strip()
        provider = input("Provider [proton/gmail/outlook]: ").strip() or "proton"
        user = input("IMAP-User (volle Mailadresse): ").strip()
        secret = getpass.getpass("Passwort / Bridge-Passwort / App-Passwort: ")
        acct = {
            "name": name,
            "provider": provider,
            "user": user,
            "secret": secret,
            "auth": "password",
            "enabled": True,
        }
        accts = [a for a in load_accounts() if a["name"] != name]
        accts.append(acct)
        save_accounts(accts)
        print(f"'{name}' gespeichert ({len(accts)} Konten gesamt).")
        return 0

    print(f"Unbekannter Befehl: {cmd}. Bekannt: list | add | remove", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
