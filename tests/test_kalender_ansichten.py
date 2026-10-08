"""Kalender-Ansichten A/B/C (tui/ansichten/kalender_ansichten.py) — ohne Terminal.

Was zählt: keine Zeile wird breiter als erlaubt (sonst zerreißt es die TUI),
und Spannen sind als EIN zusammenhängendes Ding zu sehen — Sashas
Lieblingsfeature „von X bis Y, auch über mehrere Tage". Die Optik selbst
entscheidet Sasha; geprüft wird nur, was sie tragen muss.
"""
import pytest

from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb

BREITEN = (40, 70, 110, 136)
HOEHEN = (12, 30, 45)

# Ein eigener Satz Termine, der alle Fälle aus dem Auftrag abdeckt.
TERMINE = [
    {"day": "2026-10-05", "label": "Zahnarzt", "time": "14:00", "ende": "15:00"},
    {"day": "2026-10-05", "label": "Arbeit", "time": "13:30", "ende": "16:00"},  # Überschneidung
    {"day": "2026-10-06", "label": "Feiertag mit sehr langem Namen"},             # ganztägig
    {"day": "2026-10-07", "label": "Urlaub", "bis": "2026-10-09"},               # 3 Tage, ganztags
    {"day": "2026-10-09", "label": "Berlin", "bis": "2026-10-11",                # Zeit pro Tag
     "times": {"2026-10-09": "18:00", "2026-10-11": "14:00"}},
    {"day": "2026-10-17", "label": "Segeln", "bis": "2026-10-19"},               # über Wochengrenze
    {"day": "2026-09-29", "label": "Herbstfahrt", "bis": "2026-10-02"},          # über Monatswechsel
    {"day": "2026-10-13", "label": "Weg", "time": "09:00", "ende": "10:00",
     "deaktiviert": True},
]
ROUTINEN = [{"label": "Geige", "tage": (1, 3), "time": "10:00", "ende": "11:00"}]


def daten(view, ref="2026-10-07", heute="2026-10-05", termine=TERMINE, routinen=ROUTINEN):
    return kb.api_daten(view, ref=ref, heute=heute, termine=termine, routinen=routinen)


def text(zeile):
    return "".join(t for t, _r in zeile)


def zellen(zeile):
    """Zeile → [(zeichen, rolle)] je Spalte (alles hier ist schmal)."""
    return [(ch, r) for t, r in zeile for ch in t]


def finde(zeilen, wort):
    return [i for i, z in enumerate(zeilen) if wort in text(z)]


# ── Breite und Robustheit ──────────────────────────────────────────────
@pytest.mark.parametrize("ansicht", ka.ANSICHTEN)
@pytest.mark.parametrize("breite", BREITEN)
@pytest.mark.parametrize("hoehe", HOEHEN)
def test_nie_breiter_oder_hoeher_als_erlaubt(ansicht, breite, hoehe):
    zeilen = ka.zeichne(ansicht, daten(ka.DATENANSICHT[ansicht]), breite, hoehe)
    assert len(zeilen) <= hoehe
    for z in zeilen:
        assert ka.zeilen_breite(z) <= breite, text(z)
        for t, r in z:
            assert isinstance(t, str) and isinstance(r, str)
            assert r.removesuffix(ka.INV).isidentifier()       # Rollen sind Wörter


@pytest.mark.parametrize("ansicht", ka.ANSICHTEN)
@pytest.mark.parametrize("breite,hoehe", [(0, 0), (1, 1), (5, 3), (16, 4), (25, 6), (39, 8)])
def test_winzig_stuerzt_nicht_ab(ansicht, breite, hoehe):
    zeilen = ka.zeichne(ansicht, daten(ka.DATENANSICHT[ansicht]), breite, hoehe)
    assert all(ka.zeilen_breite(z) <= breite for z in zeilen)


@pytest.mark.parametrize("ansicht", ka.ANSICHTEN)
@pytest.mark.parametrize("muell", [None, "x", {}, {"days": "x"}, {"days": {"2026-10-05": "x"}},
                                   {"days": {"2026-10-05": [3, None, {"time": "kaputt"}]},
                                    "start": "nö", "today": 5},
                                   {"days": {"2026-10-05": [{"label": "x", "time": "25:99",
                                                             "spanning": True}]}}])
def test_kaputte_daten_zeichnen_trotzdem(ansicht, muell):
    zeilen = ka.zeichne(ansicht, muell, 70, 20)
    assert all(ka.zeilen_breite(z) <= 70 for z in zeilen)


def test_breite_zeichen_zaehlen_doppelt():
    t = [{"day": "2026-10-05", "label": "会議 mit 🎉 Team und viel mehr Text", "time": "09:00"}]
    for an in ka.ANSICHTEN:
        for z in ka.zeichne(an, daten(ka.DATENANSICHT[an], termine=t, routinen=[]), 70, 30):
            assert ka.zeilen_breite(z) <= 70


def test_kuerzen_endet_mit_auslassung():
    assert ka.kuerzen("Tag der Dt. Einheit", 14) == "Tag der Dt. E…"
    assert ka.kuerzen("kurz", 14) == "kurz"
    assert ka.kuerzen("abc", 0) == ""


# ── Taste v ────────────────────────────────────────────────────────────
def test_v_schaltet_zyklisch():
    assert ka.naechste_ansicht("A") == "B"
    assert ka.naechste_ansicht("B") == "C"
    assert ka.naechste_ansicht("C") == "A"       # der alte Kalender ist raus
    assert ka.naechste_ansicht(None) == "A"
    assert ka.naechste_ansicht("Q") == "A"


def test_jede_ansicht_sagt_welche_daten_sie_braucht():
    assert set(ka.DATENANSICHT) == set(ka.ANSICHTEN)
    assert set(ka.DATENANSICHT.values()) <= {"week", "month"}


# ── A: Tagesliste (wie calcurse, Sasha 07.10.2026) ─────────────────────
@pytest.mark.parametrize("breite", BREITEN)
def test_a_jeder_tag_der_spanne_in_spannenfarbe(breite):
    zeilen = ka.ansicht_a(daten("month"), breite, 120, tage=7)
    urlaub = finde(zeilen, "Urlaub")
    titel = [i for i in urlaub if text(zeilen[i]).strip().startswith(("Urlaub", "│    Urlaub"))
             or "    Urlaub" in text(zeilen[i])[:12]]
    assert len(titel) == 3                      # Mi, Do, Fr — jeder Tag trägt die Spanne
    for i in titel:
        assert ("U", ka.ROLLE["spanne"]) in zellen(zeilen[i])


def test_a_von_bis_wie_calcurse_auch_ueber_tage():
    zeilen = [text(z) for z in ka.ansicht_a(daten("month", ref="2026-10-05"), 110, 200, tage=8)]
    alles = "\n".join(zeilen)
    assert "- 14:00 -> 15:00" in alles          # einfacher Termin, zweizeilig
    assert "18:00 -> ..:.." in alles            # Spanne fängt abends an …
    assert "..:.. -> ..:.." in alles            # … läuft durch …
    assert "..:.. -> 14:00" in alles            # … und endet mittags


def test_a_kaesten_mit_titel_innen_und_statuszeile():
    zeilen = [text(z) for z in ka.ansicht_a(daten("month"), 110, 40)]
    assert "Termine" in zeilen[1] and "Kalender" in zeilen[1]
    assert zeilen[2].startswith("├") and "┤" in zeilen[2]
    assert zeilen[-1].startswith(" [ Mo 2026-10-05 |")
    assert any("[ 5]" in z for z in zeilen)        # heute im Mini-Monat


def test_a_schmal_nur_die_terminliste():
    zeilen = [text(z) for z in ka.ansicht_a(daten("month"), 70, 40)]
    assert any("Termine" in z for z in zeilen)
    assert not any("Kalender" in z for z in zeilen)    # Mini-Monat fällt weg


def test_a_ueberschneidung_steht_untereinander():
    zeilen = [text(z) for z in ka.ansicht_a(daten("month", ref="2026-10-05"), 110, 60)]
    za, ar = finde_text(zeilen, "Zahnarzt"), finde_text(zeilen, "Arbeit")
    assert za and ar and 0 < abs(ar[0] - za[0]) <= 3
    a, b = sorted((za[0], ar[0]))
    assert not any("──────" in z for z in zeilen[a:b]), "selber Tagesblock"


def test_a_drei_tage_gleich_hoch_ab_ref():
    zeilen = [text(z) for z in ka.ansicht_a(daten("month"), 110, 40)]
    koepfe = [i for i, z in enumerate(zeilen) if "Oktober 2026" in z and "│" in z[:2]
              and z.rstrip().endswith("│") and ", " in z]
    assert len(koepfe) == 3                              # ab ref 07.10.: Mi, Do, Fr
    assert "Mittwoch, 7. Oktober" in zeilen[koepfe[0]]
    assert koepfe[1] - koepfe[0] == koepfe[2] - koepfe[1], "gleich hoch verteilt"
    assert not any("noch" in z and "tage" in z for z in zeilen), "kein Überlauf-Hinweis"


def test_a_todo_zeigt_offene_punkte_der_wochenliste():
    d = daten("month")
    d["weekplan"] = {"lid": "l_week", "items": [
        {"id": 1, "text": "Steuer abgeben", "done": False},
        {"id": 2, "text": "Blumen gießen", "done": True}]}
    zeilen = [text(z) for z in ka.ansicht_a(d, 110, 40)]
    alles = "\n".join(zeilen)
    assert "TODO" in alles and "1. Steuer abgeben" in alles
    assert "X. Blumen gießen" in alles                    # erledigt: X statt Nummer, wie calcurse


def test_a_statusbalken_ist_eine_rote_flaeche():
    z = ka.ansicht_a(daten("month"), 110, 40)[-1]
    assert all(r == ka.ROLLE["a_akzent"] + ka.INV for _t, r in z)
    assert ka.zeilen_breite(z) == 110                     # über die ganze Breite


def finde_text(zeilen, wort):
    return [i for i, z in enumerate(zeilen) if wort in z]


def test_a_deaktiviertes_nur_mit_erledigte():
    d = daten("month")
    assert not finde(ka.ansicht_a(d, 110, 200, tage=31), "Weg")
    assert finde(ka.ansicht_a(d, 110, 200, erledigte=True, tage=31), "✗ Weg")


# ── B: Monatsraster ────────────────────────────────────────────────────
def _balken(zeilen, wort):
    """Alle Flächen-Läufe (Rolle *_inv) mit dem Wort: [(zeile, x, länge)]."""
    out = []
    for i, z in enumerate(zeilen):
        x = 0
        for t, r in z:
            if r.endswith(ka.INV) and wort in t:
                out.append((i, x, len(t)))
            x += len(t)
    return out


@pytest.mark.parametrize("breite", (70, 110, 136))
def test_b_spanne_ist_ein_balken_ueber_alle_zellen(breite):
    zeilen = ka.ansicht_b(daten("month"), breite, 40)
    cw = (breite - 2) // 7 - 1
    b = _balken(zeilen, "Urlaub")
    assert len(b) == 1                          # EIN Balken, nicht drei Termine
    _y, x, n = b[0]
    assert x == 2 + 2 * (cw + 1)                # beginnt in der Mittwochs-Zelle
    assert n == 3 * (cw + 1) - 1                # deckt Mi–Fr samt Trennern


def test_b_balken_zeigt_von_bis():
    zeilen = ka.ansicht_b(daten("month"), 110, 40)
    zeile = [text(zeilen[y]) for y, _x, _n in _balken(zeilen, "Berlin")]
    assert zeile and "Fr 18:00" in zeile[0] and "So 14:00" in zeile[0]


def test_b_spanne_ueber_die_woche_bricht_mit_pfeil_um():
    zeilen = ka.ansicht_b(daten("month"), 110, 40)
    teile = sorted(_balken(zeilen, "Segeln"))
    assert len(teile) == 2
    assert "▶" in text(zeilen[teile[0][0]])
    assert "◀" in text(zeilen[teile[1][0]])


def test_b_monatswechsel_spanne_aus_dem_vormonat():
    okt = ka.ansicht_b(daten("month"), 110, 40)
    b = _balken(okt, "Herbstfahrt")
    assert len(b) == 1 and "◀" in text(okt[b[0][0]])       # kommt aus dem September
    sep = ka.ansicht_b(daten("month", ref="2026-09-15"), 110, 40)
    assert "SEPTEMBER" in text(sep[0])
    b = _balken(sep, "Herbstfahrt")
    assert len(b) == 1 and "▶" in text(sep[b[0][0]])       # geht in den Oktober


def test_b_ganztags_als_band_und_gekuerzt():
    zeilen = ka.ansicht_b(daten("month"), 110, 40)
    b = _balken(zeilen, "Feiertag")
    assert len(b) == 1 and b[0][2] == (110 - 2) // 7 - 1   # volle Zellenbreite
    assert any("Feiertag mit…" in text(z) for z in zeilen)
    assert any("10:00 Geige" in text(z) for z in zeilen)   # Anfangszeit + Titel


def test_b_heute_hervorgehoben():
    zeilen = ka.ansicht_b(daten("month"), 110, 40)
    assert any(r == ka.ROLLE["heute"] + ka.INV and t.strip() == "5"
               for z in zeilen for t, r in z)


# ── C: Woche als Zeitachse ─────────────────────────────────────────────
def _spalte(breite, tag_index):
    innen = breite - 2
    g = 7 if innen >= 7 + 7 * 8 else (6 if innen >= 6 + 7 * 4 else 3)
    colw = (innen - g) // 7
    x0 = 1 + g + tag_index * colw
    return x0, x0 + colw - 1


def _zeitzeilen(zeilen):
    """Zeilen der Achse: zwischen Kopf (Tage/ganztags) und unterem Rahmen."""
    start = 3 if "ganzt" in text(zeilen[2]) else 2
    return list(range(start, len(zeilen) - 1))


@pytest.mark.parametrize("breite", (70, 110, 136))
def test_c_spanne_ist_durchgehende_flaeche(breite):
    zeilen = ka.ansicht_c(daten("week"), breite, 34)
    for tag in (2, 3, 4):                       # Urlaub Mi–Fr, ganztags
        a, b = _spalte(breite, tag)
        for y in _zeitzeilen(zeilen):
            z = zellen(zeilen[y])[a:b]
            assert any(r.removesuffix(ka.INV) in ka.SPANNEN_FARBEN and ch != "·"
                       for ch, r in z), (tag, y, text(zeilen[y]))


def test_c_spanne_mit_uhrzeit_beginnt_und_endet_richtig():
    zeilen = ka.ansicht_c(daten("week"), 110, 34)
    alles = "\n".join(text(z) for z in zeilen)
    # Fr ab 18 Uhr, So bis 14 Uhr — auch in schmalen Säulen bleibt die Marke.
    assert "18→ B" in alles and "→14 Berlin" in alles


def test_c_ueberschneidung_nebeneinander():
    zeilen = ka.ansicht_c(daten("week"), 110, 34)
    a, b = _spalte(110, 0)
    # Arbeit 13:30–16:00 und Zahnarzt 14:00–15:00 teilen sich die Montagsspalte.
    zs = [i for i, z in enumerate(zeilen) if "Zahna" in text(z)[a:b + 1]]
    ar = [i for i, z in enumerate(zeilen) if "Arbeit" in text(z)[a:b + 1]]
    assert zs and ar
    za_x = text(zeilen[zs[0]]).index("Zahna")
    ar_x = text(zeilen[ar[0]]).index("Arbeit")
    assert za_x != ar_x


def test_c_leere_woche():
    d = daten("week", ref="2026-11-18", heute="2026-11-18", termine=[], routinen=[])
    zeilen = [text(z) for z in ka.ansicht_c(d, 70, 20)]
    assert "WOCHE 47" in zeilen[0]
    assert any("08:00" in z and "····" in z for z in zeilen)


def test_c_monatswechsel_im_titel():
    d = daten("week", ref="2026-09-30")
    zeilen = [text(z) for z in ka.ansicht_c(d, 110, 30)]
    assert "28.09.–04.10." in zeilen[0]
    assert any("Herbstfahrt" in z for z in zeilen)


def test_beispiel_aus_dem_entwurf_zeichnet_alles():
    """Die Vorschau-Daten (Entwurf) enthalten alle Termine in jeder Ansicht."""
    for an in ka.ANSICHTEN:
        d = kb.api_daten(ka.DATENANSICHT[an], ref=kb.REF, heute=kb.HEUTE)
        alles = "\n".join(text(z) for z in ka.zeichne(an, d, 136, 40))
        assert "Messe" in alles and "Wochenende" in alles


# ── Auswahl in B und C (gleicher Termin wie in A, per Identität) ───────
def _gewaehlt_in(zeilen, rolle):
    return [text(z) for z in zeilen if any(r == rolle for _t, r in z)]


def test_b_markiert_gewaehlten_tag_und_termin():
    d = daten("month")
    sel = next(e for e in d["days"]["2026-10-05"] if e["label"] == "Zahnarzt")
    zeilen = ka.ansicht_b(d, 110, 40, auswahl={"tag": "2026-10-05", "roh": sel})
    akz = ka.ROLLE["a_akzent"] + ka.INV
    getroffen = [t for z in zeilen for t, r in z if r == akz]
    assert any("Zahnarzt" in t for t in getroffen)
    assert any(t.strip().startswith("5") for t in getroffen)        # Tageszahl


def test_c_markiert_gewaehlten_block():
    d = daten("week", ref="2026-10-05")
    sel = next(e for e in d["days"]["2026-10-05"] if e["label"] == "Zahnarzt")
    zeilen = ka.ansicht_c(d, 110, 40, auswahl={"tag": "2026-10-05", "roh": sel})
    akz = ka.ROLLE["a_akzent"]
    assert any(t.startswith("Zahn") for z in zeilen for t, r in z if r == akz + ka.INV)


def test_ohne_auswahl_bleibt_alles_wie_vorher():
    d = daten("month")
    assert ka.ansicht_b(d, 110, 40) == ka.ansicht_b(d, 110, 40, auswahl=None)


@pytest.mark.parametrize("nacht", [False, True])
def test_c_hat_bei_jeder_hoehe_uhrzeiten_und_punktlinien(nacht):
    """Sasha, 08.10.2026: eine Woche ohne Punktlinien. Bei manchen Höhen traf
    keine Zeile eine beschriftete Stunde (Anfang nicht auf dem Takt)."""
    termine = list(kb.TERMINE)
    if nacht:                                # zieht die Achse bis Mitternacht auf
        termine.append({"day": "2026-10-10", "label": "Nachts", "time": "01:00",
                        "ende": "02:00"})
    d = daten("week", ref="2026-10-05", termine=termine)
    for h in range(12, 70):
        zeilen = [text(z) for z in ka.ansicht_c(d, 130, h)]
        assert any("·····" in z for z in zeilen), "keine Punktlinie bei Höhe %d" % h
        assert any(z[1:3].isdigit() and z[3] == ":" for z in zeilen), "keine Uhrzeit bei %d" % h


def test_c_nachttermin_zieht_die_achse_nicht_auf_sondern_zeigt_pfeil():
    """Sasha, 08.10.2026: Fenster bleibt 8–22, ein Termin um 01:00 bekommt
    in seiner Tagesspalte ein ▲; wird er gewählt, rollt das Fenster hin."""
    termine = list(kb.TERMINE) + [{"day": "2026-10-10", "label": "Nachts",
                                   "time": "01:00", "ende": "02:00"}]
    d = daten("week", ref="2026-10-05", termine=termine)
    zeilen = [text(z) for z in ka.ansicht_c(d, 130, 36)]
    assert any("▲" in z for z in zeilen)
    assert not any(z[1:6] == "01:00" for z in zeilen), "Achse aufgezogen"
    sel = next(e for e in d["days"]["2026-10-10"] if e["label"] == "Nachts")
    zeilen = [text(z) for z in ka.ansicht_c(d, 130, 36, auswahl={"tag": "2026-10-10", "roh": sel})]
    assert any("Nachts" in z for z in zeilen), "gewählt: Fenster rollt hin"
