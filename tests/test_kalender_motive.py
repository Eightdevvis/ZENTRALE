"""
Tagesphasen als Hintergrund der Woche (tui/ansichten/kalender_motive.py).

Sasha, 10.10.2026: „fürs coming down ein paar sterne, wolken usw eingemalt
wie ein nachthimmel, ab 10 uhr ein par z z z … eine leichte hintergrund
ebene". Geprüft: Phasen sind keine Termine (nicht wählbar, keine Zeile in A/B,
kein Block in C), das Muster ist schmal und still (deterministisch), liegt
UNTER den Terminen, setzt sich über Mitternacht am Folgetag fort und zieht
das feste Fenster 08–22 nicht auf.
"""
from datetime import date

from tui.ansichten import farben, kalender_ansichten as ka, kalender_motive as km
from tui.ansichten import kalender_werkzeuge as kw

MO = date(2026, 10, 5)


def _phase(label, t, e, motiv):
    p = {"label": label, "time": t, "ende": e, "layer": "rhythmus", "motiv": motiv,
         "recurring": True, "rrule": "FREQ=DAILY", "kennung": "p-" + motiv,
         "kategorie": "keine"}
    if e and e < t:
        p["ueber_nacht"] = True
    return p


def _daten(extra=None):
    tage = {}
    for i in range(-1, 7):
        d = date.fromordinal(MO.toordinal() + i).isoformat()
        tage[d] = [_phase("coming down", "21:30", "23:00", "nachthimmel"),
                   _phase("Schlaf", "23:00", "07:00", "schlaf"),
                   _phase("Hunger", "10:00", "10:30", "essen")]
    tage[MO.isoformat()].append({"label": "Analysis I", "time": "10:00", "ende": "12:00",
                                 "layer": "termine", "kategorie": "keine"})
    for iso, e in (extra or {}).items():
        tage.setdefault(iso, []).append(e)
    return {"today": "2026-10-06", "ref": "2026-10-06", "start": MO.isoformat(),
            "end": "2026-10-11", "days": tage}


def _text(zeilen):
    return ["".join(t for t, _r in z) for z in zeilen]


def test_alle_zeichen_sind_einspaltig_und_haben_farbe():
    for motiv, m in list(km.MUSTER.items()) + [("rueckfall", km.RUECKFALL)]:
        for ch in m["zeichen"]:
            assert ka.text_breite(ch) == 1, (motiv, ch)
        assert 0 < m["dichte"] < 0.5, motiv
        for thema in ("night", "day"):
            assert motiv in farben.MOTIV_FARBEN[thema], (motiv, thema)
    for ch in km.A_ZEICHEN.values():
        assert ka.text_breite(ch) == 1


def test_phasen_sind_keine_termine():
    d = _daten()
    ts = kw.eintraege(d, MO, False)
    assert [t["label"] for t in ts] == ["Analysis I"]          # nur der Termin
    assert [t["label"] for t in kw.eintraege(d, MO, False, monat=True)] == ["Analysis I"]
    tab = {}
    ka.farben_vergeben(d, tab)
    assert not {"schlaf", "coming", "hunger"} & set(tab)     # Phasen nehmen keine Farbe


def test_ueber_mitternacht_am_folgetag():
    d = _daten()
    ph = km.tag_phasen(d, MO)
    # Montag 0–7 kommt vom Sonntag (Schlaf ab 23:00), 23–24 vom Montag selbst
    assert (0, 7 * 60, "schlaf") in [(s, e, m) for s, e, m, _ in ph]
    assert (23 * 60, 24 * 60, "schlaf") in [(s, e, m) for s, e, m, _ in ph]
    assert (21 * 60 + 30, 23 * 60, "nachthimmel") in [(s, e, m) for s, e, m, _ in ph]


def test_muster_steht_still():
    a = [km.zelle("2026-10-05", 21 * 60 + 30, c, "nachthimmel") for c in range(40)]
    b = [km.zelle("2026-10-05", 21 * 60 + 30, c, "nachthimmel") for c in range(40)]
    assert a == b and any(a) and a.count(None) > 20       # still und dünn


def test_c_malt_hintergrund_unter_den_terminen():
    zeilen = ka.ansicht_c(_daten(), 140, 40)
    txt = "\n".join(_text(zeilen))
    rollen = {r for z in zeilen for _t, r in z}
    assert any(r.startswith("k_m_nachthimmel") for r in rollen)
    assert any(ch in txt for ch in km.MUSTER["nachthimmel"]["zeichen"])
    # Analysis 10–12 liegt deckend über „Hunger" 10:00–10:30: in seiner
    # Fläche steht kein Musterzeichen
    zeile = next(z for z in _text(zeilen) if "Analysis I" in z)
    start = zeile.index("10–12 Analysis I")
    assert not any(ch in zeile[start:start + 18] for ch in "∘◦∪")


def test_phasen_ziehen_das_fenster_nicht_auf():
    """Schlaf 23–07 liegt fast ganz außerhalb von 08–22: kein ▲/▼ dafür."""
    zeilen = _text(ka.ansicht_c(_daten(), 140, 40))
    assert not any("▲" in z or "▼" in z for z in zeilen)
    assert any(z.strip("│ ").startswith("08:00") or "08:00" in z[:10] for z in zeilen)


def test_punktlinie_laesst_platz():
    lw = ka.Leinwand(20, 1)
    lw.setze(0, 3, "✦", "k_m_nachthimmel")
    ka._punktlinie_um_muster(lw, 0, 0, 20)
    assert "".join(c for c, _r in lw.z[0]) == "···✦" + "·" * 16


def test_a_hinweis_im_tageskopf(monkeypatch):
    d = _daten()
    teile = km.a_hinweis(d, MO)
    assert [t for t, _r in teile] == ["∘ 10:00", "☾ 21:30", "ᶻ 23:00"]
    txt = "\n".join(_text(ka.ansicht_a(d, 120, 30)))
    assert "☾ 21:30" in txt and "coming down" not in txt
    monkeypatch.setattr(km, "A_HINWEIS", False)
    assert "☾ 21:30" not in "\n".join(_text(ka.ansicht_a(d, 120, 30)))
