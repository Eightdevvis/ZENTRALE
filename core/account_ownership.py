# core/account_ownership.py
#
# What the ACCOUNT owns (building kit step 10, memory/hub/building_kit_plan.md
# section 4; decided 22.10. in memory/hub/knoten_beitritt.md): ownership
# belongs to the account, installation to the node. Stored in the cloud as
# ONE opaque string (`GET/PUT /v1/besitz`): the same schema.org `ItemList` of
# `OwnershipInfo` as the shop's per-node files (core/shop.py) — only the
# reference `typeOfGood: {"@id": "zentrale://shop/<category>/<id>"}` and
# `ownedFrom`, never a copy of the item — encrypted with the account key
# (Fernet, like everything in the Mitte), so the server never sees what
# someone owns.
#
#   {"@context": "https://schema.org", "@type": "ItemList",
#    "format": "zentrale-ownership/1", "name": "Owned by the account",
#    "itemListElement": [{"@type": "ListItem", "position": 1, "item": {
#        "@type": "OwnershipInfo", "ownedFrom": "2026-10-30T12:00:00+01:00",
#        "typeOfGood": {"@id": "zentrale://shop/apps/cloud"}}}]}
#
# Marking is read → merge (union, earliest `ownedFrom` wins) → write, so two
# devices marking at once lose at most one mark until the next one (the
# server has no compare-and-swap on this route). A newer `format` major →
# read-only (core/formats.py): never written over. Removing an app from a
# node never removes ownership.
#
# Foundation (layer 1): konto + cloud_api + formats, no shop import — the
# addresses are plain strings here.

import datetime
import json

from cryptography.fernet import Fernet, InvalidToken

import cloud_api
import formats
import konto

FORMAT = "zentrale-ownership/1"
CONTEXT = "https://schema.org"


class OwnershipError(Exception):
    """English sentence for people (like konto.KontoFehler)."""


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def encode(owned: dict, key: bytes, keep=None) -> str:
    """{address: ownedFrom} → encrypted ItemList (fields of `keep` a newer
    minor added stay — 2.2 rule 2)."""
    items = [{"@type": "ListItem", "position": i + 1,
              "item": {"@type": "OwnershipInfo", "ownedFrom": am, "typeOfGood": {"@id": adr}}}
             for i, (adr, am) in enumerate(sorted(owned.items(), key=lambda x: (x[1], x[0])))]
    doc = {"@context": CONTEXT, "@type": "ItemList", "format": FORMAT,
           "name": "Owned by the account", "itemListElement": items}
    doc = formats.keep_unknown(keep, doc)
    return Fernet(key).encrypt(json.dumps(doc, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decode(blob, key: bytes):
    """Encrypted string → (doc, {address: ownedFrom}). Raises formats.NewerFormat
    for a newer major and OwnershipError when the key does not fit."""
    if not blob:
        return None, {}
    try:
        doc = json.loads(Fernet(key).decrypt(blob.encode("ascii")))
    except (InvalidToken, ValueError, UnicodeError):
        raise OwnershipError("The account's ownership list cannot be read with this key.") from None
    formats.check(doc, "account-ownership")
    owned = {}
    for el in (doc.get("itemListElement") if isinstance(doc, dict) else None) or []:
        it = el.get("item") if isinstance(el, dict) else None
        good = it.get("typeOfGood") if isinstance(it, dict) else None
        adr = good.get("@id") if isinstance(good, dict) else None
        am = it.get("ownedFrom") if isinstance(it, dict) else None
        if isinstance(adr, str) and isinstance(am, str):
            owned[adr] = min(am, owned.get(adr, am))
    return doc, owned


def _fetch():
    try:
        d = konto.client().get("/v1/besitz")
        return d.get("besitz") if isinstance(d, dict) else None
    except cloud_api.CloudFehler as e:
        raise OwnershipError(str(e)) from None


def owned() -> dict:
    """{address: ownedFrom} of the logged-in account. Not logged in → {}."""
    if not konto.angemeldet():
        return {}
    try:
        return decode(_fetch(), konto.konto_schluessel())[1]
    except formats.NewerFormat as e:
        raise OwnershipError(str(e)) from None


def mark(addresses) -> dict:
    """Mark items as owned by the account (idempotent: the first date stays).
    → the whole {address: ownedFrom}. Not logged in → OwnershipError."""
    if not konto.angemeldet():
        raise OwnershipError("Not logged in. Run 'zentrale login' first.")
    key = konto.konto_schluessel()
    blob = _fetch()
    try:
        doc, have = decode(blob, key)
    except formats.NewerFormat as e:
        raise OwnershipError(str(e)) from None
    except OwnershipError:
        # Encrypted with an older account key whose re-encryption failed
        # (core/key_rotation.py): unreadable for good — start afresh.
        doc, have = None, {}
    new = [a for a in addresses if a not in have]
    if not new:
        return have
    now = _now()
    have.update({a: now for a in new})
    try:
        konto.client().put("/v1/besitz", {"besitz": encode(have, key, keep=doc)})
    except cloud_api.CloudFehler as e:
        raise OwnershipError(str(e)) from None
    return have


def rekey(old_key: bytes, new_key: bytes) -> bool:
    """After an account key change (core/key_rotation.py): re-encrypt the list
    under the new key. → True when something was rewritten."""
    blob = _fetch()
    if not blob:
        return False
    doc, have = decode(blob, old_key)
    konto.client().put("/v1/besitz", {"besitz": encode(have, new_key, keep=doc)})
    return True
