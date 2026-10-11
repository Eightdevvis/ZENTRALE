"""Startseite (das Rad): Galaxie und altes Dashboard."""


def _dashboard(u):
    u.DASH["an"] = True


ZUSTAENDE = {
    "galaxie": lambda u: None,
    "dashboard": _dashboard,
}
