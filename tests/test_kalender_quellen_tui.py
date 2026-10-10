"""
Kalender-TUI: Termine mit Titel aus einer Liste/einem Projekt (quelle).

Sasha, 10.10.2026: „im container steht das dann als ‚titel' wie ein normaler
termin titel und unten drunter weniger stark sichtbar dezent ‚titel der
liste' … man wählt ja eigentlich einfach nur ne liste für nen termin slot
aus, ansonsten soll sich das ganze ganz normal als termin bearbeiten lassen".
Geprüft: Anzeige in A/B/C (tui/ansichten/kalender_ansichten.py), der Kasten
„welche Liste?" und die Pläne (kalender_quellen.py, kalender_werkzeuge.py).
Reine Logik — ohne Terminal und ohne Backend.
"""
from datetime import date

from tui.ansichten import kalender_ansichten as ka
from tui.ansichten import kalender_beispiel as kb
from tui.ansichten import kalender_quellen as kq
from tui.ansichten import kalender_werkzeuge as kw

TAG = date(2026, 10, 7)
Q = {"art": "liste", "id": "l_todo"}

QUELL_TERMIN = {"day": "2026-10-07", "label": "todo", "time": "10:00", "ende": "12:00",
                "quelle": Q, "titel_live": "Steuern planen", "quelle_name": "todo",
                "quelle_zustand": "ok", "quelle_eintrag": {"liste": "l_todo", "id": 3},
                "kennung": "k-todo"}
LEER_TERMIN = {"day": "2026-10-08", "label": "haus", "time": "16:00", "ende": "17:00",
               "quelle": {"art": "projekt", "id": "l_haus/7"},
               "titel_live": "haus — alles erledigt", "quelle_name": "haus",
               "quelle_zustand": "leer", "quelle_eintrag": None, "kennung": "k-haus"}
AUSWAHL = {"listen": [{"art": "liste", "id": "l_todo", "name": "todo",
                       "titel": "Steuern planen", "zustand": "ok"},
                      {"art": "liste", "id": "l_ein", "name": "einkauf",
                       "titel": "Milch", "zustand": "ok"}],
           "projekte": [{"art": "projekt", "id": "l_haus/7", "name": "Bad renovieren",
                         "titel": "Fliesen kaufen", "zustand": "ok"}]}


def text(zeile):
    return "".join(t for t, _r in zeile)


def daten(view="week", termine=None):
    return kb.api_daten(view, ref="2026-10-07", heute="2026-10-05",
                        termine=termine if termine is not None else [QUELL_TERMIN, LEER_TERMIN],
                        routinen=[])


def roh_von(d, iso="2026-10-07"):
    return next(e for e in d["days"][iso] if e.get("quelle"))


# ── Anzeige ────────────────────────────────────────────────────────────
def test_a_titel_live_darunter_dezent_die_liste():
    zeilen = ka.ansicht_a(daten("month"), 120, 40)
    i = next(i for i, z in enumerate(zeilen) if "Steuern planen" in text(z))
    assert "todo" in text(zeilen[i + 1])
    assert any(r == ka.ROLLE["leer"] for t, r in zeilen[i + 1] if "todo" in t)
    # „leer": der Titel sagt es schon, keine zweite Zeile mit dem Namen
    j = next(i for i, z in enumerate(zeilen) if "alles erledigt" in text(z))
    assert "haus" not in text(zeilen[j + 1])


def test_a_gewaehlt_unterzeile_leise_auf_der_akzentflaeche():
    d = daten("month")
    aw = {"fokus": "termine", "tag": "2026-10-07", "idx": 0, "roh": roh_von(d)}
    zeilen = ka.ansicht_a(d, 120, 40, auswahl=aw)
    i = next(i for i, z in enumerate(zeilen) if "Steuern planen" in text(z))
    assert any(r == "k_akzent" + ka.INV + ka.LEISE for t, r in zeilen[i + 1] if "todo" in t)


def test_b_zeigt_nur_den_live_titel():
    zeilen = ka.ansicht_b(daten("month"), 140, 40)
    alles = "\n".join(text(z) for z in zeilen)
    assert "Steuern" in alles


def test_c_zeilen_titel_liste_zeit():
    zeilen = ka.ansicht_c(daten("week"), 140, 40)
    i = next(i for i, z in enumerate(zeilen) if "Steuern planen" in text(z))
    x = text(zeilen[i]).index("Steuern")
    assert text(zeilen[i + 1])[x:x + 4] == "todo"
    assert text(zeilen[i + 2])[x:x + 5] == "10–12"
    # Liste und Zeit: leise Schrift auf der Fläche
    assert any(r.endswith(ka.INV + ka.LEISE) for t, r in zeilen[i + 1] if "todo" in t)


def test_c_einheitlich_titel_zuerst_zeit_darunter():
    """Sasha: „wieso divergieren manche termine, bei manchen steht die uhrzeit
    davor bei manchen nicht?" — Zeile 1 ist immer nur der Titel."""
    t = {"label": "Zahnarzt", "start": 600, "ende": 720, "spanne": False, "quelle": None}
    assert ka._c_zeilen(t, 600, 720, 40, 3) == ["Zahnarzt", "10–12"]
    assert ka._c_zeilen(t, 600, 720, 40, 1) == ["Zahnarzt"]
    t2 = dict(t, start=615, ende=705)
    assert ka._c_zeilen(t2, 615, 705, 40, 2) == ["Zahnarzt", "10:15–11:45"]
    sp = dict(t, spanne=True, start=18 * 60, ende=None)
    assert ka._c_zeilen(sp, 18 * 60, 24 * 60, 40, 2) == ["Zahnarzt", "18→"]


def test_c_uncommitted_quellen_termin_ist_glas_mit_allen_zeilen():
    t = dict(QUELL_TERMIN, layer="uncommitted")
    zeilen = ka.ansicht_c(daten("week", [t]), 140, 40)
    i = next(i for i, z in enumerate(zeilen) if "Steuern planen" in text(z))
    assert all(ka.GLAS in r for tt, r in zeilen[i] if "Steuern" in tt)
    assert any(ka.GLAS in r for tt, r in zeilen[i + 1] if "todo" in tt)


def test_farbe_fest_nach_der_quelle_nicht_nach_dem_titel():
    a = ka.ansicht_c(daten("week"), 140, 40)
    anders = dict(QUELL_TERMIN, titel_live="Bad putzen")
    b = ka.ansicht_c(daten("week", [anders, LEER_TERMIN]), 140, 40)

    def rolle(zeilen, wort):
        z = next(z for z in zeilen if wort in text(z))
        return next(r for t, r in z if wort in t)
    assert rolle(a, "Steuern") == rolle(b, "Bad putzen")
    n = ka.farben_vergeben(daten("week", [QUELL_TERMIN, dict(QUELL_TERMIN, day="2026-10-09")]),
                           tab := {})
    assert n and "quelle:l_todo" in tab and "steuern" not in tab


# ── Kasten „welche Liste?" ─────────────────────────────────────────────
def test_wahl_filtert_beim_tippen_und_nimmt_mit_enter():
    gewaehlt = []
    w = kq.QuellenWahl(AUSWAHL, lambda q: gewaehlt.append(q) or kw._plan())
    assert len(w.liste_zeilen()) == 3
    zeichen = [z for z, _r, _t, _a in w.liste_zeilen()]
    assert zeichen == ["≡", "≡", "◆"]
    for ch in "flie":                       # filtert auch nach dem obersten Punkt
        w.taste(ord(ch))
    assert [t for _z, _r, t, _a in w.liste_zeilen()][0].startswith("Bad renovieren")
    assert w.taste(10) == "fertig"
    assert gewaehlt == [{"art": "projekt", "id": "l_haus/7", "name": "Bad renovieren"}]


def test_wahl_jk_sind_text_pfeile_waehlen():
    w = kq.QuellenWahl(AUSWAHL, lambda q: kw._plan())
    w.taste(258)
    assert w.i == 1
    w.taste(ord("j"))
    assert w.suche == "j" and not w.liste_zeilen()
    assert w.taste(10) == "weiter" and w.fehler
    w.taste(127)
    assert w.suche == "" and len(w.liste_zeilen()) == 3
    assert w.taste(27) == "abbruch"


def test_neu_fuer_liste_ist_das_normale_formular_mit_quelle():
    q = {"art": "liste", "id": "l_todo", "name": "todo"}
    f = kw.formular_neu(TAG, TAG, quelle=q)
    normal = kw.formular_neu(TAG, TAG)
    assert [x.name for x in f.felder] == [x.name for x in normal.felder]
    assert f.felder[0].text == "todo" and "todo" in f.titel
    f.felder[0].text = ""                      # leer = Name der Liste
    f.feld.text = ""
    for x in f.felder:
        if x.name == "von":
            x.text = "10"
        if x.name == "bis":
            x.text = "12"
    assert f.taste(10) == "fertig"
    p = f.plan()
    (meth, pfad, body), = p["aufrufe"]
    assert (meth, pfad) == ("POST", "/api/calendar/entry")
    assert body["quelle"] == Q and body["label"] == "todo" and body["time"] == "10:00"


def test_neu_fuer_liste_als_routine_und_spanne():
    q = {"art": "liste", "id": "l_todo", "name": "todo"}
    w = {"titel": "todo", "datum": TAG, "ganz": "nein", "von": "08:00", "bis": None,
         "wied": "wöchentlich", "alle": 1, "wtage": [], "wbis": None}
    (_m, pfad, body), = kw._neu_plan(w, TAG, quelle=q)[0]
    assert pfad == "/api/calendar/routine" and body["quelle"] == Q
    w = {"titel": "todo", "datum": TAG, "ganz": "ja", "tage": 3, "wied": "keine"}
    (_m, pfad, body), = kw._neu_plan(w, TAG, quelle=q)[0]
    assert pfad == "/api/calendar/spanne" and body["quelle"] == Q


# ── Bearbeiten: Feld „Liste" ───────────────────────────────────────────
def _speichern(f, liste):
    feld = next(x for x in f.felder if x.name == "liste")
    feld.wahl = feld.optionen.index(liste)
    assert f.taste(10) == "fertig"
    return f.plan()


def test_bearbeiten_liste_loesen_fragt_titel_uebernehmen():
    roh = dict(QUELL_TERMIN, layer="termine")
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert next(x for x in f.felder if x.name == "liste").optionen == ("todo", "keine")
    p = _speichern(f, "keine")
    assert p["aufrufe"][0][0] == "PUT"
    frage = p["zurueck"]()
    assert "Steuern planen" in frage.zeile() and "(j/n)" in frage.zeile()
    frage.taste(ord("j"))
    (meth, pfad, body), = frage.plan()["aufrufe"]
    assert (meth, pfad) == ("DELETE", "/api/calendar/quelle")
    assert body == {"kennung": "k-todo", "titel_uebernehmen": True}


def test_bearbeiten_liste_bleibt_ohne_folge():
    f = kw.formular_bearbeiten(dict(QUELL_TERMIN, layer="termine"), TAG, TAG)
    assert _speichern(f, "todo")["zurueck"] is None


def test_bearbeiten_liste_waehlen_oeffnet_den_kasten_und_setzt_per_kennung():
    roh = {"day": "2026-10-07", "label": "Kino", "time": "19:00", "layer": "termine",
           "kennung": "k-kino"}
    f = kw.formular_bearbeiten(roh, TAG, TAG, quelle_wahl=lambda r: kq.QuellenWahl(
        AUSWAHL, lambda q: kq.plan_setzen(r, q)))
    p = _speichern(f, kw.LISTE_WAEHLEN)
    w = p["zurueck"]()
    assert w.taste(10) == "fertig"
    (meth, pfad, body), = w.plan()["aufrufe"]
    assert (meth, pfad) == ("POST", "/api/calendar/quelle")
    assert body == {"kennung": "k-kino", "art": "liste", "id": "l_todo"}


def test_ohne_quelle_und_ohne_wahl_kein_feld():
    roh = {"day": "2026-10-07", "label": "Kino", "time": "19:00", "kennung": "k"}
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert "liste" not in [x.name for x in f.felder]


def test_kopie_nimmt_die_liste_mit():
    assert kw.kopie(dict(QUELL_TERMIN, layer="termine"))["quelle"] == Q


# ── Abhaken und Ansehen ────────────────────────────────────────────────
def test_abhaken_plan_und_meldung():
    (meth, pfad, _b), = kq.plan_abhaken(QUELL_TERMIN)["aufrufe"]
    assert (meth, pfad) == ("POST", "/api/lists/l_todo/items/3/toggle")
    assert kq.plan_abhaken(LEER_TERMIN) is None
    neu = dict(QUELL_TERMIN, titel_live="Bad putzen")
    assert kq.meldung_abgehakt("Steuern planen", neu) == \
        "erledigt: Steuern planen — jetzt: Bad putzen"
    assert "leer" in kq.meldung_abgehakt("X", LEER_TERMIN)
    assert kq.finde(daten(), "k-haus")["quelle_name"] == "haus"


def test_ansehen_zeigt_liste_und_die_naechsten():
    v = {"name": "todo", "zustand": "ok", "punkte": ["Steuern planen", "Bad putzen", "Fenster"]}
    zeilen = kw.details(QUELL_TERMIN, TAG, v)
    assert zeilen[0] == "Steuern planen"
    alles = "\n".join(zeilen)
    assert "Liste    todo" in alles and "Jetzt    Steuern planen" in alles
    assert "Danach   Bad putzen" in alles and "Fenster" in alles
    assert "gibt es nicht mehr" in "\n".join(kw.details(
        dict(QUELL_TERMIN, quelle_zustand="fehlt"), TAG, {"zustand": "fehlt"}))


def test_fusszeile_passt_sich_der_breite_an():
    for an in ka.ANSICHTEN:
        voll = ka.tasten_hinweis(an)
        for b in (150, 120, 100):
            s = ka.tasten_hinweis(an, b)
            assert ka.text_breite(s) <= b or s == ka.tasten_hinweis(an, 1)
        assert ka.tasten_hinweis(an, 10_000) == voll
    for an in ("A", "C"):
        for b in (150, 110, 80):
            s = ka.tasten_hinweis(an, b)
            assert "A für liste" in s and "! abhaken" in s
