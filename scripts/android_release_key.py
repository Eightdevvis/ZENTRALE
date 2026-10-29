"""The Android release signing key of the phone app, kept in the ZENTRALE vault.

The key belongs to the account (the publisher), not to a device
(memory/hub/standort_und_app.md): it lives as ONE vault entry in
core/adapter_geheim.py, encrypted with the account key and synced through the
Mitte like every other account secret. Gradle stays file-based — it reads
key.properties from $ZENTRALE_ANDROID_KEY_PROPERTIES or
~/.config/zentrale/android/key.properties — so this module only moves the two
files between that folder and the vault:

    backup   local files → vault   (refuses to replace a DIFFERENT vault key
                                    unless force_replace; the old one is kept
                                    under PREVIOUS_ENTRY, never dropped)
    restore  vault → local files   (refuses to overwrite a different local key)
    status   local present? vault present? same certificate SHA-256?
    ensure   what publish/bump run first: restore if only the vault has it,
             back up if only this computer has it, stop if both differ.

Never prints or logs the password or key bytes; the certificate fingerprint is
public. Docs: memory/betrieb/phone_app_release.md.
"""

import base64
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if os.path.join(ROOT, "core") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "core"))

import adapter_geheim  # noqa: E402
import dateien  # noqa: E402
import konto  # noqa: E402
from i18n import _  # noqa: E402 — UI text: core/locale/<lang>/LC_MESSAGES/zentrale.po

PROPERTIES_ENV = "ZENTRALE_ANDROID_KEY_PROPERTIES"      # same variable Gradle reads
DEFAULT_PROPERTIES = "~/.config/zentrale/android/key.properties"
VAULT_ENTRY = "android/release_key"
PREVIOUS_ENTRY = "android/release_key.previous"
FORMAT = "zentrale-android-key/1"


class ReleaseKeyError(Exception):
    """A sentence for the human (translated)."""


# ── local files ────────────────────────────────────────────────────────

def properties_path() -> str:
    return os.path.expanduser(os.environ.get(PROPERTIES_ENV) or DEFAULT_PROPERTIES)


def parse_properties(text: str) -> dict:
    """The simple key=value subset of Java properties that key.properties uses."""
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#!" or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _store_file(properties_text: str) -> str:
    store = parse_properties(properties_text).get("storeFile") or "zentrale-release.jks"
    if os.path.isabs(store) or os.path.normpath(store).startswith(".."):
        raise ReleaseKeyError(_("storeFile in key.properties must be a file name next to key.properties, not '{path}'.")
                              .format(path=store))
    return store


def read_local(props_path: str = None):
    """{"key_properties": str, "keystore": bytes, "store_file": str} or None if
    neither file exists. Only one of them → ReleaseKeyError (never guess)."""
    props_path = props_path or properties_path()
    if not os.path.exists(props_path):
        default_store = os.path.join(os.path.dirname(props_path), "zentrale-release.jks")
        if os.path.exists(default_store):
            raise ReleaseKeyError(_("{path} exists but key.properties is missing — the local key is incomplete.")
                                  .format(path=default_store))
        return None
    with open(props_path, encoding="utf-8") as f:
        text = f.read()
    store = _store_file(text)
    store_path = os.path.join(os.path.dirname(props_path), store)
    try:
        with open(store_path, "rb") as f:
            keystore = f.read()
    except FileNotFoundError:
        raise ReleaseKeyError(_("{path} exists but its keystore {store} is missing — the local key is incomplete.")
                              .format(path=props_path, store=store_path)) from None
    return {"key_properties": text, "keystore": keystore, "store_file": store}


def write_local(key: dict, props_path: str = None) -> None:
    """Both files, 600; a folder created here gets 700."""
    props_path = props_path or properties_path()
    folder = os.path.dirname(props_path)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700)
        os.chmod(folder, 0o700)
    dateien.atomar_schreiben(os.path.join(folder, key["store_file"]), key["keystore"], geheim=True)
    dateien.atomar_schreiben(props_path, key["key_properties"], geheim=True)


# ── the vault ──────────────────────────────────────────────────────────

def _encode(key: dict) -> str:
    return json.dumps({"format": FORMAT, "store_file": key["store_file"],
                       "key_properties": key["key_properties"],
                       "keystore_b64": base64.b64encode(key["keystore"]).decode("ascii")},
                      sort_keys=True)


def _decode(text: str) -> dict:
    try:
        d = json.loads(text)
        if d.get("format") != FORMAT:
            raise ValueError
        return {"key_properties": d["key_properties"], "store_file": d["store_file"],
                "keystore": base64.b64decode(d["keystore_b64"], validate=True)}
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ReleaseKeyError(_("The release key in the vault is damaged.")) from None


def read_vault(wurzel=None):
    """The key from the vault, None if there is none. An entry this computer
    cannot decrypt (other account, not logged in) → ReleaseKeyError."""
    if VAULT_ENTRY not in adapter_geheim.namen(wurzel):
        return None
    text = adapter_geheim.lesen(VAULT_ENTRY, wurzel)
    if text is None:
        raise ReleaseKeyError(_("The vault has a release key, but this computer cannot decrypt it. "
                                "Log in with the account that stored it ('zentrale login')."))
    key = _decode(text)
    _store_file(key["key_properties"])
    if key["store_file"] != _store_file(key["key_properties"]):
        raise ReleaseKeyError(_("The release key in the vault is damaged."))
    return key


def _require_account():
    if not konto.angemeldet():
        raise ReleaseKeyError(_("Not logged in on this computer. The release key is stored encrypted with the account — "
                                "run 'zentrale login' first."))


# ── comparing ──────────────────────────────────────────────────────────

def same(a: dict, b: dict) -> bool:
    return (a["keystore"] == b["keystore"] and a["key_properties"] == b["key_properties"]
            and a["store_file"] == b["store_file"])


def certificate_sha256(key: dict):
    """'AB:CD:…' of the signing certificate, or None if it cannot be read."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import pkcs12
    password = parse_properties(key["key_properties"]).get("storePassword") or ""
    try:
        _k, cert, _more = pkcs12.load_key_and_certificates(key["keystore"], password.encode("utf-8"))
    except (ValueError, TypeError):
        return None
    if cert is None:
        return None
    return cert.fingerprint(hashes.SHA256()).hex(":").upper()


# ── operations ─────────────────────────────────────────────────────────

def backup(force_replace: bool = False, props_path: str = None, wurzel=None) -> str:
    """→ "stored" | "unchanged" | "replaced"."""
    _require_account()
    local = read_local(props_path)
    if local is None:
        raise ReleaseKeyError(_("No release key on this computer ({path}).").format(path=props_path or properties_path()))
    vault = read_vault(wurzel)        # an entry this computer cannot decrypt is never replaced
    if vault is not None and same(local, vault):
        return "unchanged"
    replaced = vault is not None
    if replaced and not force_replace:
        raise ReleaseKeyError(_("The vault already holds a DIFFERENT release key (certificate {vault}; this computer: {local}). "
                                "Nothing was changed. Only if you are sure, run 'key backup --force-replace' "
                                "(the old one is kept as {previous}).")
                              .format(vault=certificate_sha256(vault), local=certificate_sha256(local),
                                      previous=PREVIOUS_ENTRY))
    if replaced:
        adapter_geheim.setzen(PREVIOUS_ENTRY, _encode(vault), wurzel)
    adapter_geheim.setzen(VAULT_ENTRY, _encode(local), wurzel)
    back = read_vault(wurzel)
    if back is None or not same(local, back):
        raise ReleaseKeyError(_("Storing the release key in the vault failed — it does not read back the same."))
    return "replaced" if replaced else "stored"


def restore(props_path: str = None, wurzel=None) -> str:
    """→ "restored" | "unchanged"."""
    _require_account()
    vault = read_vault(wurzel)
    if vault is None:
        raise ReleaseKeyError(_("The vault has no release key."))
    props_path = props_path or properties_path()
    local = read_local(props_path)
    if local is not None:
        if same(local, vault):
            return "unchanged"
        raise ReleaseKeyError(_("{path} holds a DIFFERENT release key than the vault (here {local}, vault {vault}). "
                                "Nothing was overwritten.")
                              .format(path=props_path, local=certificate_sha256(local), vault=certificate_sha256(vault)))
    store_path = os.path.join(os.path.dirname(props_path), vault["store_file"])
    if os.path.exists(store_path):
        raise ReleaseKeyError(_("{path} exists already — nothing was overwritten.").format(path=store_path))
    write_local(vault, props_path)
    if not same(read_local(props_path), vault):
        raise ReleaseKeyError(_("Restoring the release key failed — the files do not read back the same."))
    return "restored"


def status(props_path: str = None, wurzel=None) -> dict:
    """{"local": bool, "local_sha256", "vault": bool|"unreadable", "vault_sha256",
    "same": bool|None, "logged_in": bool, "error": str|None}. Never raises."""
    out = {"logged_in": konto.angemeldet(), "local": False, "local_sha256": None,
           "vault": False, "vault_sha256": None, "same": None, "error": None}
    local = vault = None
    try:
        local = read_local(props_path)
    except ReleaseKeyError as e:
        out["error"] = str(e)
    if local:
        out["local"], out["local_sha256"] = True, certificate_sha256(local)
    try:
        vault = read_vault(wurzel)
    except ReleaseKeyError as e:
        out["vault"] = "unreadable"
        out["error"] = out["error"] or str(e)
    if vault:
        out["vault"], out["vault_sha256"] = True, certificate_sha256(vault)
    if local and vault:
        out["same"] = same(local, vault)
    return out


def ensure(props_path: str = None, wurzel=None) -> str:
    """Run before bump/publish. → "ok" | "restored" | "backed_up" |
    "no_account" | "missing". Both present but different → ReleaseKeyError."""
    if not konto.angemeldet():
        return "no_account"
    local = read_local(props_path)
    vault = read_vault(wurzel)
    if local is None and vault is None:
        return "missing"
    if local is None:
        restore(props_path, wurzel)
        return "restored"
    if vault is None:
        backup(False, props_path, wurzel)
        return "backed_up"
    if same(local, vault):
        return "ok"
    raise ReleaseKeyError(_("This computer and the vault hold DIFFERENT release keys (here {local}, vault {vault}). "
                            "Stopped — decide by hand which one is right ('key status'), then 'key backup --force-replace' "
                            "or move the local files away and 'key restore'.")
                          .format(local=certificate_sha256(local), vault=certificate_sha256(vault)))
