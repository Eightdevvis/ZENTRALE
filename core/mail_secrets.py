# core/mail_secrets.py
#
# Verschlüsselter Zugangsdaten-Speicher für die Mail-Konten.
#
# ── Warum verschlüsselt + warum so ────────────────────────────────────
# Mail-Passwörter sind das "HIGH value"-Asset aus Sashas Bedrohungsmodell
# (memory/betrieb/sicherheit.md). Zwei Anforderungen, die zusammen die Wahl bestimmen:
#   - SECURITY: nicht im Klartext auf der Platte.
#   - MULTI-DEVICE: ZENTRALE läuft auf mehreren Geräten, die Konten sollen
#     überall verfügbar sein.
# Lösung: ein FERNET-verschlüsselter Blob (data/mail_secrets.enc). Weil der
# Inhalt Ciphertext ist, darf die Datei gefahrlos über Syncthing/scp auf alle
# Geräte synchronisiert werden — sie entschlüsselt sich nur mit der Passphrase.
#
# ── Woher die Passphrase kommt (zwei Quellen, in dieser Reihenfolge) ──
#   1. Env-Var ZENTRALE_MAIL_KEY  — headless-tauglich (systemd EnvironmentFile,
#      chmod 600). Das ist der Weg für den PC-Backend, der OHNE Login-Session
#      läuft, wo ein OS-Keyring gesperrt wäre.
#   2. OS-Keyring (Secret Service via secretstorage) — bequemer Fallback NUR
#      für die interaktive Desktop-Session: die Passphrase liegt verschlüsselt
#      im Login-Keyring (kein Klartext auf Platte) und entsperrt sich beim
#      Desktop-Login automatisch. So muss man am eigenen Rechner nicht jedes Mal
#      `export ZENTRALE_MAIL_KEY=…` tippen, ohne die Zwei-Schichten-Idee
#      (LUKS + separate Passphrase) aufzugeben.
# Fehlt secretstorage/DBus (headless), greift einfach weiter nur die Env-Var.
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


# ── OS-Keyring (Secret Service) — optionaler Passphrase-Fallback ──────
# Attribute zum Wiederfinden des Eintrags im Login-Keyring.
_KEYRING_ATTRS = {"application": "zentrale", "service": "mail-passphrase"}


def _keyring_collection():
    """Default-Collection des Secret Service (entsperrt). None bei Fehlen/Fehler."""
    import secretstorage  # lazy: nur wenn wirklich gebraucht
    conn = secretstorage.dbus_init()
    coll = secretstorage.get_default_collection(conn)
    if coll.is_locked():
        coll.unlock()
    return coll


def _keyring_get():
    """Passphrase aus dem OS-Keyring (oder None, wenn nichts/kein Backend)."""
    try:
        coll = _keyring_collection()
        for item in coll.search_items(_KEYRING_ATTRS):
            return item.get_secret().decode("utf-8")
    except Exception:
        return None
    return None


def _keyring_set(passphrase):
    """Passphrase im OS-Keyring ablegen (ersetzt einen vorhandenen Eintrag)."""
    coll = _keyring_collection()
    for item in coll.search_items(_KEYRING_ATTRS):
        item.delete()
    coll.create_item("ZENTRALE Mail-Passphrase", _KEYRING_ATTRS,
                     passphrase.encode("utf-8"))


def _keyring_clear():
    """Entfernt den Keyring-Eintrag. Liefert Anzahl gelöschter Einträge."""
    try:
        coll = _keyring_collection()
        n = 0
        for item in coll.search_items(_KEYRING_ATTRS):
            item.delete()
            n += 1
        return n
    except Exception:
        return 0


def _passphrase():
    """Die Master-Passphrase: ERST Env (headless/systemd), DANN OS-Keyring
    (interaktive Desktop-Session). None, wenn weder noch verfügbar."""
    return os.environ.get(_ENV_KEY) or _keyring_get()


def available():
    """True, wenn Verschlüsselung + Passphrase grundsätzlich nutzbar sind."""
    if not _passphrase():
        return False
    try:
        import cryptography  # noqa: F401
    except Exception:
        return False
    return True


def load_accounts():
    """Liste der Konto-Dicts (entschlüsselt) oder [] wenn nicht verfügbar."""
    passphrase = _passphrase()
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

    SICHERHEIT: Liefert `load_accounts()` LEER, obwohl ein nicht-leerer Store
    existiert (transienter Entschlüssel-Fehler, falsche Passphrase, Race), wird
    ABGEBROCHEN — sonst würde der Store mit nur DIESEM einen Konto überschrieben
    und alle anderen (z.B. Posteo) gingen verloren. Genau dieser Fall ist beim
    Token-Rotieren im Hintergrund-Poll schon einmal passiert.
    """
    existing = load_accounts()
    if not existing and os.path.exists(_STORE) and os.path.getsize(_STORE) > 0:
        raise RuntimeError("Konten-Store vorhanden, aber nicht lesbar (Passphrase?) "
                           "— upsert abgebrochen, um Datenverlust zu vermeiden")
    accts = [a for a in existing if a.get("name") != acct["name"]]
    accts.append(acct)
    save_accounts(accts)
    return acct


def save_accounts(accounts):
    """Verschlüsselt die Konto-Liste und schreibt sie atomar. Vor dem Über-
    schreiben wird der bisherige Store nach `.enc.bak` gesichert — ein Backup-
    Stand zum Zurückholen, falls doch mal zu wenig geschrieben wird."""
    passphrase = _passphrase()
    if not passphrase:
        raise RuntimeError(f"{_ENV_KEY} nicht gesetzt und kein OS-Keyring-Eintrag "
                           "— keine Passphrase zum Verschlüsseln")
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
    if os.path.exists(_STORE):                 # ein Stand Backup behalten
        try:
            import shutil
            shutil.copy2(_STORE, _STORE + ".bak")
        except Exception:
            pass
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

    # Keyring-Verwaltung braucht KEINE Passphrase in der Env (sie legt sie ja
    # gerade erst ab / liest sie aus dem Keyring).
    if cmd in ("keyring-set", "keyring-clear", "keyring-test"):
        return _keyring_cli(cmd)

    if not _passphrase():
        print(f"FEHLER: keine Passphrase. Entweder:\n"
              f"  export {_ENV_KEY}='deine-master-passphrase'\n"
              f"oder einmalig im OS-Keyring ablegen:\n"
              f"  venv/bin/python -m core.mail_secrets keyring-set", file=sys.stderr)
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

    if cmd == "rename":
        if len(args) < 3:
            print("Nutzung: rename <alt> <neu>", file=sys.stderr)
            return 2
        old, new = args[1], args[2]
        accts = load_accounts()
        if any(a["name"] == new for a in accts):
            print(f"'{new}' existiert schon.", file=sys.stderr)
            return 2
        hit = [a for a in accts if a["name"] == old]
        if not hit:
            print(f"'{old}' nicht gefunden.", file=sys.stderr)
            return 2
        hit[0]["name"] = new
        save_accounts(accts)
        print(f"'{old}' → '{new}'. (Token/Einstellungen bleiben erhalten)")
        return 0

    if cmd == "add":
        print("Neues Mail-Konto anlegen.")
        name = input("Kurzname (z.B. posteo): ").strip()
        provider = input("Provider [posteo/proton/gmail/outlook]: ").strip() or "posteo"
        user = input("IMAP-User (volle Mailadresse): ").strip()
        secret = getpass.getpass("Passwort / Bridge-Passwort / App-Passwort: ")
        # Bracketed-Paste-Marker entfernen (Terminals schmuggeln sie beim Einfügen
        # in die versteckte Eingabe — sonst stimmt das Passwort nicht).
        for mark in ("\x1b[200~", "\x1b[201~", "[200~", "[201~"):
            secret = secret.replace(mark, "")
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

    print(f"Unbekannter Befehl: {cmd}. Bekannt: list | add | remove | rename | "
          f"keyring-set | keyring-test | keyring-clear", file=sys.stderr)
    return 2


def _keyring_cli(cmd):
    """OS-Keyring-Verwaltung (Secret Service). Die Passphrase tippt der NUTZER
    selbst per getpass — sie wird nie geloggt und nie im Klartext gespeichert."""
    import sys
    import getpass

    if cmd == "keyring-test":
        val = _keyring_get()
        if val:
            print("OS-Keyring: Passphrase gefunden ✓")
            return 0
        print("OS-Keyring: kein Eintrag (oder Keyring gesperrt / kein Backend).")
        return 1

    if cmd == "keyring-clear":
        n = _keyring_clear()
        print(f"{n} Keyring-Eintrag/Einträge entfernt.")
        return 0

    # keyring-set
    try:
        import secretstorage  # noqa: F401
    except Exception:
        print("secretstorage fehlt — installieren mit:\n"
              "  venv/bin/pip install secretstorage jeepney", file=sys.stderr)
        return 2

    # Wenn ZENTRALE_MAIL_KEY schon in der Umgebung steht, NIMM DIE — sie hat
    # bewiesen, dass sie funktioniert, und wir umgehen die getpass-Einfüge-Falle
    # (Terminals hängen beim Paste „bracketed paste"-Steuerzeichen an, die in der
    # versteckten Eingabe unsichtbar mit reinrutschen und die Passphrase kaputt
    # machen). Sonst doch abfragen — und solche Marker sicherheitshalber strippen.
    pw = os.environ.get(_ENV_KEY)
    if pw:
        print(f"Übernehme {_ENV_KEY} aus der Umgebung (kein Tippen/Einfügen nötig).")
    else:
        print("Tipp: Wenn das Einfügen scheitert, vorher 'export "
              f"{_ENV_KEY}=…' setzen und diesen Befehl erneut aufrufen.")
        pw = getpass.getpass("Master-Passphrase (wird im OS-Keyring abgelegt): ")
        # Bracketed-Paste-Marker entfernen, falls das Terminal sie reingeschmuggelt hat.
        pw = pw.replace("\x1b[200~", "").replace("\x1b[201~", "")
        pw = pw.replace("[200~", "").replace("[201~", "")
    if not pw:
        print("abgebrochen (leer).", file=sys.stderr)
        return 2
    try:
        _keyring_set(pw)
    except Exception as e:
        print(f"Keyring-Schreiben fehlgeschlagen: {type(e).__name__}: {e}",
              file=sys.stderr)
        return 2
    # Gegenprobe: entschlüsselt diese Passphrase den vorhandenen Store wirklich?
    # (Env kurz ausblenden, damit load_accounts WIRKLICH den Keyring nutzt.)
    if os.path.exists(_STORE):
        saved_env = os.environ.pop(_ENV_KEY, None)
        ok = bool(load_accounts())
        if saved_env is not None:
            os.environ[_ENV_KEY] = saved_env
        if not ok:
            print("⚠ Im Keyring abgelegt — aber sie entschlüsselt den vorhandenen "
                  "Store NICHT. Stimmt die Passphrase? (keyring-clear zum Zurücksetzen)")
            return 1
    print("Passphrase im OS-Keyring abgelegt. Künftig kein 'export "
          f"{_ENV_KEY}' mehr nötig,\nsolange deine Desktop-Session läuft "
          "(Login-Keyring entsperrt).")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
