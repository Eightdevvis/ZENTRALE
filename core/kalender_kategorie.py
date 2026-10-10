# core/kalender_kategorie.py
#
# Gruppen von Kalender-Einträgen (iCalendar CATEGORIES, RFC 5545 — wie
# Outlook). Sasha, 10.10.2026: „in der monatsansicht seh ich lieber uni uni
# uni statt jeden tag welche fächer genau". Eine Gruppe fasst Einträge in der
# Monatsansicht zu EINEM Block zusammen („Uni 08:30–16:00"), sonst nichts.
# Standard: keine Gruppe.
#
# Datenmodell an Termin, Spanne und Routine:
#   kategorie       Schlüssel aus KATEGORIEN oder "custom"; fehlt = keine
#   kategorie_name  nur bei "custom": der eigene Name
# .ics: CATEGORIES:<Anzeigename> (Katalog: „Uni", custom: der Name). Beim
# Lesen wird ein Name, der zum Katalog passt, wieder dessen Schlüssel.
#
# Dazu der Kurs-Schlüssel eines Titels (`titel_schluessel`, bis heute nur in
# der TUI): erstes Wort ohne „@ Ort", klein, Kurzformen aufgelöst. Die TUI
# darf ihn von hier beziehen (Tür im Bauplan nötig, wenn sie es tut).
#
# Reines Modul (nur kalender_fehler), damit Abbildung, Fassade und Kennungen
# es ohne Import-Kreis benutzen.

import re

from kalender_fehler import KalenderAbgelehnt

# FESTE Konstante (nicht aus Daten gebaut): das KI-Schema bleibt pro Prozess
# gleich. Erweitern = hier eine Zeile; Schlüssel nie umbenennen.
KATEGORIEN = {
    "uni":    "Uni",
    "arbeit": "Arbeit",
}
KEINE = "keine"
CUSTOM = "custom"


def katalog() -> list[dict]:
    """Für GET /api/calendar/kategorien und das KI-Schema."""
    return ([{"schluessel": k, "name": n} for k, n in KATEGORIEN.items()]
            + [{"schluessel": KEINE, "name": "keine Gruppe"},
               {"schluessel": CUSTOM, "name": "eigener Name (kategorie_name)"}])


def _katalog_schluessel(text) -> str | None:
    t = text.strip().casefold() if isinstance(text, str) else ""
    for k, n in KATEGORIEN.items():
        if t in (k, n.casefold()):
            return k
    return None


def pruefen(kategorie, name=None) -> tuple[str | None, str | None]:
    """Eine Angabe prüfen → (kategorie, kategorie_name) zum Speichern;
    (None, None) heißt: keine Gruppe (Feld entfernen).
      ""/"keine"        → keine Gruppe
      "uni", "arbeit"   → Katalog (Groß/Klein egal)
      "custom" + name   → eigener Name; passt er zum Katalog („Uni"), gilt
                          der Katalog-Schlüssel (sonst läse .ics ihn anders
                          zurück, als er geschrieben wurde)
    Sonst KATEGORIE-UNBEKANNT / KATEGORIE-NAME-FEHLT; ein Name ohne custom
    ist UNBEKANNTES-FELD."""
    k = kategorie.strip().lower() if isinstance(kategorie, str) else None
    if k is None:
        raise KalenderAbgelehnt("KATEGORIE-UNBEKANNT", f"Gruppe {kategorie!r} ist kein Text")
    n = name.strip() if isinstance(name, str) else ""
    if k in ("", KEINE):
        if n:
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "kategorie_name gibt es nur bei custom")
        return None, None
    if k == CUSTOM:
        if not n:
            raise KalenderAbgelehnt("KATEGORIE-NAME-FEHLT")
        katalog_k = _katalog_schluessel(n)
        return (katalog_k, None) if katalog_k else (CUSTOM, n)
    if k in KATEGORIEN:
        if n:
            raise KalenderAbgelehnt("UNBEKANNTES-FELD", "kategorie_name gibt es nur bei custom")
        return k, None
    raise KalenderAbgelehnt("KATEGORIE-UNBEKANNT",
                            f"Gruppe {kategorie!r} gibt es nicht; erlaubt: "
                            f"{', '.join(KATEGORIEN)}, {KEINE}, {CUSTOM} (+ kategorie_name)")


def setzen(obj: dict, kategorie, name=None) -> None:
    """Geprüft an ein Daten-Dict schreiben (None = unverändert)."""
    if kategorie is None and name is None:
        return
    if kategorie is None:                  # nur einen neuen Namen: custom gemeint
        kategorie = CUSTOM
    k, n = pruefen(kategorie, name)
    obj.pop("kategorie", None)
    obj.pop("kategorie_name", None)
    if k:
        obj["kategorie"] = k
    if n:
        obj["kategorie_name"] = n


def anzeige(e: dict) -> str | None:
    """Der Name der Gruppe eines Eintrags („Uni", eigener Name) oder None."""
    k = (e or {}).get("kategorie")
    if k == CUSTOM:
        return (e.get("kategorie_name") or "").strip() or None
    return KATEGORIEN.get(k) if isinstance(k, str) else None


def sauber(e: dict) -> bool:
    """Stehen die Felder so da, wie pruefen() sie schreibt? Nur dann bildet
    die .ics-Abbildung sie auf CATEGORIES ab (sonst Extras, verlustfrei)."""
    k, n = e.get("kategorie"), e.get("kategorie_name")
    if k is None:
        return n is None
    if k in KATEGORIEN:
        return n is None
    return (k == CUSTOM and isinstance(n, str) and n == n.strip() and bool(n)
            and _katalog_schluessel(n) is None)


def aus_namen(namen: list[str]) -> dict:
    """CATEGORIES-Werte (beim Lesen) → Felder. Der erste ist die Gruppe;
    weitere (von außen, z. B. Outlook) bleiben in `kategorien_weitere`."""
    namen = [x for x in namen if isinstance(x, str) and x]
    if not namen:
        return {}
    k = _katalog_schluessel(namen[0])
    felder = {"kategorie": k} if k else {"kategorie": CUSTOM, "kategorie_name": namen[0]}
    if len(namen) > 1:
        felder["kategorien_weitere"] = namen[1:]
    return felder


# ── Kurs-Schlüssel eines Titels ────────────────────────────────────────
# Aus tui/ansichten/kalender_ansichten.py (dort noch eine eigene Kopie, bis
# die TUI von hier bezieht). Kurzformen: wie Sasha Kurse abkürzt.
KURZFORMEN = {
    "exphy": "experimentalphysik",
}


def titel_schluessel(label) -> str:
    """Der Kurs hinter einem Titel: erstes Wort, ohne Ort, klein.
    'Analysis I @ HS 1' → 'analysis'; 'ExPhy Übung' → 'experimentalphysik'."""
    name = (label or "").split(" @ ")[0].strip().lower()
    wort = re.split(r"[\s\-–:/,.()]+", name)[0] if name else ""
    return KURZFORMEN.get(wort, wort)
