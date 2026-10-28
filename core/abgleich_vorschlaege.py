# core/abgleich_vorschlaege.py
#
# Was ein fremder Knoten (das Handy) VORSCHLAGEN darf — Dateien, die nicht
# ihm allein gehören, die ein Rechner aber aus seinem Eingang übernimmt,
# solange nichts dagegen spricht (memory/betrieb/abgleich.md, „Format für
# fremde Knoten“). Die eigenen Dateien eines Knotens (seine .jsonl …) stehen
# in abgleich.eigene_datei; hier nur die Vorschläge:
#
#   data/gespraeche/<id>/kopf.json      Kopf eines NEUEN Gesprächs — gilt
#                                       nur, solange die Mitte keinen hat
#   data/kalender/<ebene>/<uid>.ics     ein NEUER Termin (seit 2026-10-28) —
#                                       nur, solange es Pfad und UID nirgends
#                                       gibt (kalender_vorschlag_annehmen)
#
# Warum Termine nur als neue Datei: ein Rechner führt die Mitte zusammen, das
# Handy nicht. Änderte das Handy einen vorhandenen Termin, gäbe es zwei
# Schreiber derselben Datei ohne gemeinsame Basis. Ein neuer Termin hat
# keinen Vorgänger — da gibt es nichts zu widersprechen. Der nächste Schritt
# (Ändern, Löschen, einzelne Vorkommen aus) weitet NUR
# kalender_vorschlag_annehmen: dann wird ein Vorschlag zu einer vorhandenen
# UID je VEVENT zusammengeführt (abgleich_ics), statt abgelehnt.
#
# Reine Funktionen: Pfade und Bytes rein, Entscheidung raus.

import re

import abgleich_ics
import dateien

_EBENE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")   # wie kalender_ics.ordner_fuer


def ist_kopf(rel: str) -> bool:
    """Der Kopf eines Gesprächs (data/gespraeche/<id>/kopf.json)."""
    teile = rel.split("/")
    return (len(teile) == 4 and rel.startswith("data/gespraeche/")
            and teile[2][:1] not in ("_", ".") and teile[3] == "kopf.json")


def ist_kalender(rel: str) -> bool:
    """Ein Termin im Kalender-Ordner (data/kalender/<ebene>/<name>.ics)."""
    teile = rel.split("/")
    return (len(teile) == 4 and teile[0] == "data" and teile[1] == "kalender"
            and bool(_EBENE.match(teile[2])) and teile[3].endswith(".ics")
            and not teile[3].startswith("."))


def ist_vorschlag(rel: str) -> bool:
    return ist_kopf(rel) or ist_kalender(rel)


def _uids(roh: bytes) -> set:
    """Die UIDs einer .ics (leer, wenn sie sich nicht lesen lässt)."""
    try:
        return {uid for uid, _rid in abgleich_ics.zerlegen(roh).termine}
    except (ValueError, UnicodeDecodeError):
        return set()


def kalender_vorschlag_annehmen(rel: str, inhalt: bytes, mitte: dict, geloescht: dict):
    """Darf der Termin-Vorschlag `rel` aus einem Eingang in die Mitte?

    mitte     = {rel: bytes} — was das Inhaltsverzeichnis gerade nennt
    geloescht = die Grabsteine aus inhalt.enc

    → (True, None) annehmen; (False, None) still übergehen (schon da oder
    gelöscht — der Vorschlag hat sich erledigt); (False, "Grund") ablehnen
    mit Hinweis. Heute gilt: NUR neue Termine (Pfad und UID gibt es noch
    nicht). Hier — und nur hier — wird es später für Änderungen geweitet."""
    if rel in mitte or rel in geloescht:
        return False, None
    ebene = rel.split("/")[2]
    if not any(r.startswith(f"data/kalender/{ebene}/") for r in mitte):
        return False, f"die Ebene „{ebene}“ gibt es nicht"
    try:
        teile = abgleich_ics.zerlegen(inhalt)
    except (ValueError, UnicodeDecodeError):
        return False, "kein lesbarer Termin"
    uids = {uid for uid, _rid in teile.termine}
    if len(uids) != 1:
        return False, "eine Datei hält genau einen Termin (eine UID)"
    uid = uids.pop()
    if rel.rsplit("/", 1)[1] != dateien.sicherer_name(uid) + ".ics":
        return False, "der Dateiname passt nicht zur UID"
    for anderer, roh in mitte.items():
        if ist_kalender(anderer) and uid in _uids(roh):
            return False, "diesen Termin gibt es schon (Ändern kommt erst später)"
    return True, None
