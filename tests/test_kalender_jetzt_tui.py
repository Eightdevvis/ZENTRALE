"""Jetzt-Linie in der Woche C und ▸ in der Tagesliste A (20.10.2026).

Sasha: „füge einen goldenen kleinen strich mit kleinem pfeil links dran
hinzu, der genau anzeigt, wo die zeit grade runterläuft, in der
wochenansicht".

Reine Funktionen (kalender_ansichten), Uhr gestellt (core/uhr.py) —
datumsunabhängig.
"""
from datetime import datetime

import uhr
from tui.ansichten import farben
from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_jetzt as kj

MI = "2026-10-21"                     # ein Mittwoch (Spalte 2)
R = kj.ROLLE


def daten(view="week", termine=(), ref=MI, heute=MI):
    return kb.api_daten(view, ref=ref, heute=heute, termine=list(termine), routinen=[])


def text(z):
    return "".join(t for t, _r in z)


def zellen(z):
    return [(ch, r) for t, r in z for ch in t]


def jetzt_zeilen(bild):
    return [k for k, z in enumerate(bild) if any(r.split("~")[0] == R for _t, r in z)]


def zeile_von(bild, uhrzeit):
    """Rasterzeile mit der Beschriftung „HH:MM" links."""
    return next(k for k, z in enumerate(bild) if text(z).startswith("│" + uhrzeit))


def woche(dt, termine=(), **kw):
    with uhr.gestellt(dt):
        return ka.ansicht_c(daten(termine=termine, **kw), 130, 36)


def spalte_x(bild, kopf):
    return text(bild[1]).index(kopf)


def test_linie_an_zeile_und_spalte_von_heute():
    bild = woche(datetime(2026, 10, 21, 12, 0))
    k = zeile_von(bild, "12:00")
    assert jetzt_zeilen(bild) == [k]
    z = zellen(bild[k])
    x = spalte_x(bild, "Mi 21.")
    assert z[x - 1] == (kj.PFEIL, R)                       # Pfeil im Spalt links
    gold = [i for i, (ch, r) in enumerate(z) if r == R and ch == kj.STRICH]
    assert gold[0] == x and len(gold) > 10                  # Strich über die Spalte
    assert max(gold) < spalte_x(bild, "Do 22.")             # nur Mittwoch
    assert "━" not in text(bild[k]) and "⚑" not in text(bild[k])   # ≠ Deadline


def test_nicht_in_anderer_woche_und_nicht_ausserhalb_des_fensters():
    assert jetzt_zeilen(woche(datetime(2026, 10, 28, 12, 0))) == []      # Woche weiter
    assert jetzt_zeilen(woche(datetime(2026, 10, 21, 3, 0))) == []       # vor dem Fenster
    assert kj.c_zeile(22 * 60, 8 * 60, 60, 14) is None                    # hinter dem Fenster
    assert kj.c_zeile(21 * 60 + 59, 8 * 60, 60, 14) == 13                 # letzte Zeile, nie dahinter


def test_linie_wandert_mit_der_uhr_und_rundet_auf_die_naechste_zeile():
    d = daten()
    with uhr.gestellt(datetime(2026, 10, 21, 10, 0)):
        a = ka.ansicht_c(d, 130, 36)
        uhr.vorstellen(hours=3)
        b = ka.ansicht_c(d, 130, 36)
    assert jetzt_zeilen(a) == [zeile_von(a, "10:00")]
    assert jetzt_zeilen(b) == [zeile_von(b, "13:00")]
    # Takt hier 30 min: 12:10 → 12:00, 12:20 → 12:30 (die Zeile darunter)
    assert kj.c_zeile(12 * 60 + 10, 7 * 60, 30, 34) == 10
    assert kj.c_zeile(12 * 60 + 20, 7 * 60, 30, 34) == 11
    assert kj.c_zeile(6 * 60, 7 * 60, 30, 34) is None


def test_blocktext_bleibt_unter_der_linie():
    t = {"day": MI, "time": "11:30", "ende": "12:45", "label": "Probe Block"}
    ohne = woche(datetime(2026, 10, 28, 12, 0), [dict(t, day="2026-10-28")], ref="2026-10-28",
                 heute="2026-10-28")
    mit = woche(datetime(2026, 10, 21, 12, 0), [t])
    k = zeile_von(mit, "12:00")
    assert jetzt_zeilen(mit) == [k]
    # die Zeit im Block steht unversehrt da, der Strich nur im Leerraum dahinter
    assert "11:30–12:45" in text(ohne[k]) and "11:30–12:45" in text(mit[k])
    blk = [(ch, r) for ch, r in zellen(mit[k]) if r.endswith(("_inv", "_inv_leise"))]
    assert any(ch == kj.STRICH for ch, _r in blk)
    assert "".join(ch for ch, _r in blk).startswith("11:30–12:45")


def test_deadline_bleibt_ueber_der_linie():
    dl = {"day": MI, "time": "12:00", "label": "HÜ", "typ": "deadline"}
    bild = woche(datetime(2026, 10, 21, 12, 0), [dl])
    z = bild[zeile_von(bild, "12:00")]
    assert "⚑" in text(z) and "HÜ" in text(z)


def test_a_pfeil_vor_laufendem_sonst_naechstem_termin():
    ts = [{"day": MI, "time": "09:00", "ende": "10:00", "label": "Frueh"},
          {"day": MI, "time": "11:30", "ende": "12:45", "label": "Laeuft"},
          {"day": MI, "time": "14:00", "ende": "15:00", "label": "Spaeter"}]
    d = daten("month", ts)

    def pfeil_vor(dt):
        with uhr.gestellt(dt):
            bild = ka.ansicht_a(d, 120, 40)
        k = next(k for k, z in enumerate(bild) if (kj.PFEIL, R) in zellen(z))
        return text(bild[k + 1]).strip("│ ")

    assert pfeil_vor(datetime(2026, 10, 21, 12, 0)).startswith("Laeuft")
    assert pfeil_vor(datetime(2026, 10, 21, 13, 0)).startswith("Spaeter")


def test_rolle_in_beiden_themes_gold_und_unterscheidbar():
    for th in ("night", "day"):
        assert "jetzt" in farben.KAL[th]
        gold = farben.KAL[th]["jetzt"][0]
        assert gold not in (farben.KAL[th]["heute"][0], farben.THEMES[th]["amber"][1])
