"""Termine im Abgleich (core/abgleich_ics.py): je VEVENT über die Basis,
nie zwei Fassungen als Text in einer .ics-Datei."""
import abgleich_zusammenfuehren as regeln

KOPF = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//t//DE\r\n"
FUSS = "END:VCALENDAR\r\n"


def _ev(uid, titel, lm="20261024T100000Z", rid=None):
    r = f"RECURRENCE-ID:{rid}\r\n" if rid else ""
    return (f"BEGIN:VEVENT\r\nUID:{uid}\r\n{r}LAST-MODIFIED:{lm}\r\n"
            f"SUMMARY:{titel}\r\nBEGIN:VALARM\r\nACTION:DISPLAY\r\nEND:VALARM\r\nEND:VEVENT\r\n")


def _cal(*evs):
    return (KOPF + "".join(evs) + FUSS).encode("utf-8")


REL = "data/kalender/termine/a.ics"


def test_art_ics_nur_im_kalender_ordner():
    assert regeln.art(REL) == "ics"
    assert regeln.art("data/ablage/x/a.ics", b"x") == "text"


def test_abweichungen_derselben_uid_beide_bleiben():
    """Eine Spanne mit eigener Zeit je Tag: Hauptteil + RECURRENCE-ID in einer
    Datei. Hier ändert der eine den Hauptteil, dort der andere einen Tag."""
    b = _cal(_ev("s", "Kurs"), _ev("s", "Kurs Mo", rid="20261102"))
    l = _cal(_ev("s", "Kurs neu", "20261024T110000Z"), _ev("s", "Kurs Mo", rid="20261102"))
    m = _cal(_ev("s", "Kurs"), _ev("s", "Kurs Mo 18 Uhr", "20261024T110000Z", rid="20261102"))
    r = regeln.zusammenfuehren(REL, b, l, m)
    text = r.inhalt.decode()
    assert "SUMMARY:Kurs neu" in text and "SUMMARY:Kurs Mo 18 Uhr" in text
    assert r.konflikte == [] and "⟪" not in text and text.count("BEGIN:VEVENT") == 2


def test_beide_aendern_dasselbe_spaeteres_gewinnt_mit_hinweis():
    b = _cal(_ev("u", "A"))
    l = _cal(_ev("u", "hier", "20261024T130000Z"))
    m = _cal(_ev("u", "mitte", "20261024T120000Z"))
    r = regeln.zusammenfuehren(REL, b, l, m)
    assert "SUMMARY:hier" in r.inhalt.decode() and r.konflikte
    l2 = _cal(_ev("u", "hier", "20261024T110000Z"))
    assert "SUMMARY:mitte" in regeln.zusammenfuehren(REL, b, l2, m).inhalt.decode()


def test_geloeschte_abweichung_gegen_unveraendert():
    b = _cal(_ev("s", "Kurs"), _ev("s", "Mo", rid="20261102"))
    l = _cal(_ev("s", "Kurs"))
    m = _cal(_ev("s", "Kurs"), _ev("s", "Mo", rid="20261102"))
    r = regeln.zusammenfuehren(REL, b, l, b.replace(b"PRODID:-//t//t//DE", b"PRODID:-//x//x//DE"))
    assert r.inhalt.decode().count("BEGIN:VEVENT") == 1
    assert regeln.zusammenfuehren(REL, b, l, m).inhalt == l


def test_kaputtes_ics_als_ganzes_die_mitte_bleibt():
    b = _cal(_ev("u", "A"))
    r = regeln.zusammenfuehren(REL, b, b"kein kalender", _cal(_ev("u", "B")))
    assert r.inhalt == _cal(_ev("u", "B")) and r.konflikte
