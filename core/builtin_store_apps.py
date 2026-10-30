# core/builtin_store_apps.py
#
# Built-in apps that the store lists, installs and removes like any app
# (building kit step 10, memory/hub/building_kit_plan.md section 4): `cloud`
# and `cloud_folder`. Their code stays inside the core package; the catalog
# marks them `built_in` (core/shop_katalog.jsonld, app_register.built_in).
#
# "Installed" is not a second record — it IS the existing setting of this
# node (one truth, nothing copied):
#
#   cloud         on ⇔ abgleich.cloud_an(): sync over the cloud, logged in.
#                 install = this node syncs over the account (needs a login);
#                 remove  = back to local: sync settings cleared, still
#                 logged in, nothing deleted in the cloud.
#   cloud_folder  on ⇔ the node's app choice syncs it (abgleich_apps; never
#                 chosen = everything = on). install/remove = that choice,
#                 through the one gate (core/generations.py, step 9b).
#
# Ownership (what the ACCOUNT owns) is core/account_ownership.py; removing
# an app here never touches it.
#
# Foundation (layer 1): settings only, no shop import.

import abgleich
import abgleich_apps
import ai_config
import generations
import konto

APPS = ("cloud", "cloud_folder")


class BuiltinError(ValueError):
    """`code` = HTTP status for the route; the text is an English sentence."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


def address(name) -> str:
    return "zentrale://shop/apps/" + name


def by_address(adr):
    """zentrale://shop/apps/<name> → name, if it is one of APPS; else None."""
    for n in APPS:
        if adr == address(n):
            return n
    return None


def installed(name) -> bool:
    if name == "cloud":
        return abgleich.cloud_an()
    if name == "cloud_folder":
        e = abgleich_apps.entscheidungen()
        return e is None or e.get("cloud_folder") is True     # None = never chose = everything
    raise BuiltinError("not a built-in app: %s" % name, 404)


def _sync_choice(on: bool):
    r = generations.choose_sync({"cloud_folder": on})
    if not r.ok:
        text = "; ".join(e.get("text", "") for e in r["errors"]) or "; ".join(r["problems"])
        raise BuiltinError("The sync choice was refused: " + text, 409)


def installed_names() -> list:
    return [n for n in APPS if installed(n)]


def install(name) -> dict:
    """Idempotent. → {"name", "installed": True, "new": bool}."""
    was = installed(name)
    if name == "cloud":
        if not konto.angemeldet():
            raise BuiltinError("The Cloud app needs an account: run 'zentrale setup' or "
                               "'zentrale login' first.", 409)
        ai_config.set_override("abgleich_mitte_art", "http", persist=True)
        ai_config.set_override("abgleich_weg", "mitte", persist=True)
    elif name == "cloud_folder":
        _sync_choice(True)
    return {"name": name, "installed": True, "new": not was}


def remove(name) -> dict:
    """Idempotent; deletes nothing (neither here nor in the cloud).
    → {"name", "installed": False, "was": bool}."""
    was = installed(name)
    if name == "cloud":
        # Empty value = the override goes (ai_config.set_override): defaults.
        ai_config.set_override("abgleich_mitte_art", "", persist=True)
        ai_config.set_override("abgleich_weg", "", persist=True)
    elif name == "cloud_folder":
        _sync_choice(False)
    return {"name": name, "installed": False, "was": was}
