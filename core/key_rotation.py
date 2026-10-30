# core/key_rotation.py
#
# Change the account key — offered only when a device was lost or stolen
# (Sasha 2026-10-30, memory/hub/building_kit_plan.md 5.1 step 7, build step 8).
#
# The key SCHEMA stays (memory/hub/knoten_beitritt.md, HKDF infos …/v1): the
# konto_schluessel is a random Fernet key wrapped by the password and by the
# emergency key. Changing it means:
#
#   1. a new random konto_schluessel, wrapped with the password (current or
#      new) and with a NEW emergency key — the old one unwrapped the old key,
#      so it stops working; the person sees the new one once and confirms;
#   2. every file in the cloud re-encrypted with it: the table of contents
#      (inhalt.enc), each d/<name>.enc under its new hidden name, each inbox
#      file of a foreign node (knoten/<node>/<name>.enc, the phone), and the
#      account-key entries inside the vault data/adapter/geheim.enc;
#   3. all of it uploaded as blobs, then ONE call PUT /v1/konto/schluessel
#      that swaps head, wraps and emergency proof together (409 → read again);
#   4. this device keeps its session and stores the new key; every other
#      device (phone included) is logged out and gets the new key at its
#      next login.
#
# What it cannot undo: whoever has the old key and the old encrypted files
# can still read THOSE. It protects everything from now on.
#
# No terminal, no print: the CLI (zentrale_cli/befehle.py) asks and shows.

import hashlib
import json
import os

import abgleich
import abgleich_auswahl
import abgleich_mitte
import abgleich_schluessel as schluessel
import adapter_geheim
import cloud_api
import dateien
import konto
import konto_schluessel as ks

VAULT = abgleich_auswahl.GEHEIM[0]          # data/adapter/geheim.enc
INBOX = abgleich.EINGANG + "/"               # knoten/<node>/<hidden>.enc
TRIES = 3


class RotationError(konto.KontoFehler):
    """For humans (English)."""


class Draft:
    """A new key, computed but not sent — so the CLI can show the new
    emergency key and get the confirmation BEFORE anything changes."""

    def __init__(self, password: str, new_password: str = None, kdf=None):
        if new_password:
            konto.passwort_pruefen(new_password)
        self.password = password
        self.konto_schluessel = ks.neuer_konto_schluessel()
        self._notfall = os.urandom(32)
        self.notfall_text = ks.notfall_text(self._notfall)
        self.teile = ks.passwort_teile(new_password or password, self.konto_schluessel, kdf)
        self.teile.update(ks.notfall_teile(self._notfall, self.konto_schluessel))


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def reencrypt(old_key: bytes, new_key: bytes, read, names):
    """The Mitte under the new key. `read(name)` → bytes|None, `names` = all
    names of the current stand. → (write {name: bytes}, delete [name],
    vault: (old plain, new plain) | None, skipped: number of unreadable inbox files).
    Pure apart from `read`: no network of its own."""
    old, new = schluessel.Tresor(old_key), schluessel.Tresor(new_key)
    write, delete, vault, skipped = {}, [], None, 0
    raw = read(abgleich.INHALT)
    if raw is None:
        raise RotationError("The table of contents is missing in the cloud — nothing was changed.")
    inhalt = json.loads(old.auf(raw))
    for rel, e in inhalt.get("dateien", {}).items():
        g = read("d/" + e["name"] + ".enc")
        if g is None:
            raise RotationError(f"A file is missing in the cloud ({rel}) — nothing was changed.")
        plain = old.auf(g)
        if rel == VAULT:
            before = plain
            plain = adapter_geheim.rekey(plain, old_key, new_key)
            vault = (before, plain)
            e["sha"] = _sha(plain)
        delete.append("d/" + e["name"] + ".enc")
        e["name"] = new.name(rel)
        write["d/" + e["name"] + ".enc"] = new.zu(plain)
    for name in names:
        parts = name.split("/")
        if not name.startswith(INBOX) or len(parts) != 3 or not parts[2].endswith(".enc"):
            continue
        delete.append(name)
        try:
            klar = old.auf(read(name) or b"")
            rel = json.loads(klar)["pfad"]
            if not isinstance(rel, str):
                raise TypeError(rel)
        except (schluessel.SchluesselFehler, ValueError, KeyError, TypeError):
            skipped += 1            # unreadable for everyone already: dropped
            continue
        write[f"{INBOX}{parts[1]}/{new.name(rel)}.enc"] = new.zu(klar)
    known = {abgleich.INHALT, abgleich.LIESMICH} | set(delete)
    unknown = [n for n in names if n not in known and not n.startswith("d/")]
    if unknown:
        raise RotationError(f"The cloud holds {len(unknown)} file(s) this version does not know — "
                            "update ZENTRALE first. Nothing was changed.")
    stale = [n for n in names if n.startswith("d/") and n not in delete]
    delete.extend(stale)            # orphans under old names would be unreadable anyway
    write[abgleich.INHALT] = new.zu(json.dumps(inhalt, ensure_ascii=False).encode("utf-8"))
    return write, [n for n in delete if n not in write], vault, skipped


def _upload(mitte, write: dict) -> dict:
    """Blobs up (only what the server lacks). → verweise {name: sha256}."""
    by_sha, refs = {}, {}
    for name, b in write.items():
        if len(b) > abgleich_mitte.MAX_BLOB:
            raise RotationError(f"A file is too large for the cloud ({len(b) // 2**20} MiB).")
        by_sha[_sha(b)] = b
        refs[name] = _sha(b)
    mitte._hochladen(by_sha)
    return refs


def _follow_vault(wurzel, local, vault, old_key, new_key):
    """This device's vault follows the cloud. Identical to the cloud's old
    one → exactly the new cloud bytes (the next sync sees no conflict);
    changed since the last sync → re-keyed on its own."""
    if local is None:
        return
    if vault is not None and local == vault[0]:
        new = vault[1]
    else:
        try:
            new = adapter_geheim.rekey(local, old_key, new_key)
        except adapter_geheim.GeheimFehler:
            return
    dateien.atomar_schreiben(os.path.join(str(wurzel), VAULT), new.decode("utf-8"), geheim=True)


def rotate(draft: Draft, wurzel) -> dict:
    """Change the account key for the account logged in here (see the top).
    → {"files": n, "inbox_skipped": n}. Raises RotationError / KontoFehler;
    on any error before the last call nothing changed."""
    d = konto.lesen()
    if d is None:
        raise RotationError("Not logged in. Run 'zentrale login' first.")
    old_key = d["konto_schluessel"].encode("ascii")
    c = konto.client()
    salz, kdf = konto._vorab(c, d["name"])
    try:
        current = ks.anmelde_schluessel(ks.hauptschluessel(draft.password, salz, kdf))
    except ks.SchluesselFehler as e:
        raise RotationError(str(e)) from None
    local_vault = None
    if wurzel and os.path.exists(os.path.join(str(wurzel), VAULT)):
        with open(os.path.join(str(wurzel), VAULT), "rb") as f:
            local_vault = f.read()
    with abgleich._sperre(120.0):
        for _try in range(TRIES):
            mitte = abgleich_mitte.HttpMitte(c)
            stand, read, names = mitte.holen()
            if stand is None:
                write, delete, vault, skipped = {}, [], None, 0
            else:
                write, delete, vault, skipped = reencrypt(old_key, draft.konto_schluessel, read, names)
            refs = _upload(mitte, write) if write else {}
            body = dict(draft.teile, altes_anmelde_schluessel=current,
                        stand={"basis": stand, "verweise": refs, "loeschen": delete})
            try:
                c.put("/v1/konto/schluessel", body)
                break
            except cloud_api.CloudFehler as e:
                if e.status == 409:
                    continue                      # someone synced in between: read again
                if e.code == "falsche_anmeldung":
                    raise RotationError("Wrong password. Nothing was changed — the emergency key just "
                                        "shown is NOT valid; your old one still is.") from None
                raise RotationError(str(e)) from None
        else:
            raise RotationError("The data in the cloud kept changing — try again in a minute. "
                                "Nothing was changed.")
        # The cloud has the new key now; this device follows.
        konto._speichern(d.get("server") or c.basis, d["name"], d.get("token"), d.get("laeuft_ab"),
                         draft.konto_schluessel, d.get("knoten"))
        _follow_vault(wurzel, local_vault, vault, old_key, draft.konto_schluessel)
    return {"files": sum(1 for n in write if n.startswith("d/")), "inbox_skipped": skipped}
