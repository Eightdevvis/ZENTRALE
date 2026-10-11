"""Technik-Vollbild (aus dem Technik-Rad)."""


def _technik(u):
    u.TECH["active"] = True; u.TECH["view"] = "system"


ZUSTAENDE = {"anzeige": _technik}
