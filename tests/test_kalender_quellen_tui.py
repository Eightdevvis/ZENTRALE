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


# ── Typ liste im Fenster „advanced" (11.10.2026) ──────────────────────
# Sasha: „dann wird der listentermin zu nem termintypen und nicht zu so nem
# extra shortcut". Kein eigener Weg mehr (Taste A), sondern a → Formular →
# Advanced → Typ liste.
def _feld(f, name):
    return next(x for x in f.felder if x.name == name)


def _liste_waehlen(f, suche=""):
    """Im Formular: Advanced öffnen, Typ liste, Liste wählen, übernehmen."""
    f.i = [x.name for x in f.felder].index("advanced")
    assert f.taste(10) == "weiter" and f.box is not None
    f.taste(261)                               # Typ: normal → liste
    f.taste(258)                               # Zeile „Liste"
    f.taste(10)                                # „welche Liste?"
    for ch in suche:
        f.taste(ord(ch))
    f.taste(10)                                # nimmt
    assert f.box.unter is None
    assert f.taste(19) == "weiter" and f.box is None     # Strg-S: übernehmen


def test_neu_typ_liste_ist_das_normale_formular_mit_quelle():
    f = kw.formular_neu(TAG, TAG, quellen=lambda: AUSWAHL)
    assert "liste" not in [x.name for x in f.felder]     # kein eigenes Feld mehr
    _liste_waehlen(f)
    assert f.felder[0].text == "todo"                    # Titel vorbelegt
    assert "Rückfall" in dict((b, h) for b, _w, _a, h in f.zeilen())["Titel"]
    zeile = kw.kalender_advanced.zusammenfassung(next(x for x in f.felder if x.art == "advanced").adv)
    assert zeile == "typ liste: todo · stil keine"
    f.felder[0].text = ""                                # leer = Name der Liste
    _feld(f, "von").text, _feld(f, "bis").text = "10", "12"
    assert f.taste(19) == "fertig"
    (meth, pfad, body), = f.plan()["aufrufe"]
    assert (meth, pfad) == ("POST", "/api/calendar/entry")
    assert body["quelle"] == Q and body["label"] == "todo" and body["time"] == "10:00"


def test_neu_typ_normal_ohne_quelle_und_titel_pflicht():
    f = kw.formular_neu(TAG, TAG, quellen=lambda: AUSWAHL)
    _feld(f, "von").text = "10"
    assert f.taste(19) == "weiter" and f.fehler == "titel fehlt"
    f.felder[0].text = "Kino"
    assert f.taste(19) == "fertig"
    (_m, _p, body), = f.plan()["aufrufe"]
    assert "quelle" not in body and "stil" not in body


def test_neu_typ_liste_als_routine_und_spanne():
    q = {"art": "liste", "id": "l_todo", "name": "todo"}
    w = {"titel": "todo", "datum": TAG, "ganz": "nein", "von": "08:00", "bis": None,
         "wied": "wöchentlich", "alle": 1, "wtage": [], "wbis": None}
    (_m, pfad, body), = kw._neu_plan(w, TAG, quelle=q)[0]
    assert pfad == "/api/calendar/routine" and body["quelle"] == Q
    w = {"titel": "todo", "datum": TAG, "ganz": "ja", "tage": 3, "wied": "keine"}
    (_m, pfad, body), = kw._neu_plan(w, TAG, quelle=q)[0]
    assert pfad == "/api/calendar/spanne" and body["quelle"] == Q


def test_advanced_liste_ohne_wahl_laesst_nicht_zu():
    f = kw.formular_neu(TAG, TAG, quellen=lambda: AUSWAHL)
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    f.taste(32)                                # Leertaste: Typ liste
    assert f.taste(10) == "weiter" and f.box is not None   # Enter auf Typ: übernehmen?
    assert "liste wählen" in f.box.fehler and f.box.reihe == "liste"
    f.taste(27)                                # Esc: verworfen
    assert f.box is None and _feld(f, "advanced").adv["typ"] == "normal"


def test_advanced_esc_verwirft_auch_die_gewaehlte_liste():
    f = kw.formular_neu(TAG, TAG, quellen=lambda: AUSWAHL)
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    f.taste(261)
    f.taste(258)
    f.taste(10)
    f.taste(27)                                # Esc in „welche Liste?" → zurück ins Fenster
    assert f.box is not None and f.box.unter is None and f.box.quelle is None
    f.taste(10)
    f.taste(258)                               # zweite Liste
    f.taste(10)
    assert f.box.quelle["name"] == "einkauf"
    f.taste(27)                                # Esc im Fenster: alles weg
    assert f.box is None and kw.kalender_advanced.quelle(_feld(f, "advanced").adv) is None
    assert f.felder[0].text == ""


def test_advanced_ohne_backend_sagt_es():
    f = kw.formular_neu(TAG, TAG, quellen=lambda: None)
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    f.taste(261)
    f.taste(258)
    f.taste(10)
    assert f.box.unter is None and "backend" in f.box.fehler


# ── Bearbeiten: Typ liste ↔ normal ─────────────────────────────────────
def _typ_normal(f):
    f.i = [x.name for x in f.felder].index("advanced")
    f.taste(10)
    assert f.box.typ == "liste"
    f.taste(260)                               # ← : liste → normal
    f.taste(10)                                # Enter auf Typ: übernehmen
    assert f.box is None


def test_bearbeiten_typ_normal_fragt_titel_uebernehmen():
    roh = dict(QUELL_TERMIN, layer="termine")
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    assert kw.kalender_advanced.zusammenfassung(next(x for x in f.felder if x.art == "advanced").adv).startswith("typ liste: todo")
    _typ_normal(f)
    assert f.taste(19) == "fertig"
    p = f.plan()
    assert p["aufrufe"][0][0] == "PUT"
    assert all(pf != "/api/calendar/quelle" for _m, pf, _b in p["aufrufe"])
    frage = p["zurueck"]()
    assert "Steuern planen" in frage.zeile() and frage.ansicht() == "ny"   # y/n: die Leiste
    frage.taste(ord("j"))
    (meth, pfad, body), = frage.plan()["aufrufe"]
    assert (meth, pfad) == ("DELETE", "/api/calendar/quelle")
    assert body == {"kennung": "k-todo", "titel_uebernehmen": True}


def test_bearbeiten_liste_bleibt_ohne_folge():
    f = kw.formular_bearbeiten(dict(QUELL_TERMIN, layer="termine"), TAG, TAG)
    assert f.taste(19) == "fertig"
    p = f.plan()
    assert p["zurueck"] is None
    assert all(pf != "/api/calendar/quelle" for _m, pf, _b in p["aufrufe"])


def test_bearbeiten_typ_liste_setzt_per_kennung_beim_speichern():
    roh = {"day": "2026-10-07", "label": "Kino", "time": "19:00", "layer": "termine",
           "kennung": "k-kino"}
    f = kw.formular_bearbeiten(roh, TAG, TAG, quellen=lambda: AUSWAHL)
    _liste_waehlen(f)
    assert f.felder[0].text == "Kino"          # eigener Titel bleibt (nur Rückfall)
    assert f.taste(19) == "fertig"
    p = f.plan()
    assert p["aufrufe"][0][0] == "PUT" and p["zurueck"] is None
    assert ("POST", "/api/calendar/quelle", {"kennung": "k-kino", "art": "liste",
                                             "id": "l_todo"}) in p["aufrufe"]


def test_bearbeiten_andere_liste_und_serie_und_spanne():
    roh = dict(QUELL_TERMIN, recurring=True, rrule="FREQ=WEEKLY;BYDAY=WE", layer="termine")
    frage = kw.formular_bearbeiten(roh, TAG, TAG, quellen=lambda: AUSWAHL)
    frage.taste(ord("a"))
    alle = frage.plan()["weiter"]
    alle.i = [x.name for x in alle.felder].index("advanced")
    alle.taste(10)
    alle.taste(258)                            # Zeile „Liste"
    alle.taste(10)
    for ch in "bad":
        alle.taste(ord(ch))
    alle.taste(10)
    alle.taste(19)
    assert alle.felder[0].text == "Bad renovieren"   # Titel war der Name der alten Liste
    assert alle.taste(19) == "fertig"
    assert ("POST", "/api/calendar/quelle", {"kennung": "k-todo", "art": "projekt",
                                             "id": "l_haus/7"}) in alle.plan()["aufrufe"]
    frage = kw.formular_bearbeiten(roh, TAG, TAG)
    frage.taste(ord("t"))
    assert "advanced" not in [x.name for x in frage.plan()["weiter"].felder]
    sp = dict(QUELL_TERMIN, spanning=True, von="2026-10-06", bis="2026-10-08", layer="termine")
    frage = kw.formular_bearbeiten(sp, TAG, TAG)
    frage.taste(ord("a"))
    ganze = frage.plan()["weiter"]
    _typ_normal(ganze)
    assert ganze.taste(19) == "fertig" and ganze.plan()["zurueck"] is not None
    frage = kw.formular_bearbeiten(sp, TAG, TAG)
    frage.taste(ord("t"))
    assert "advanced" not in [x.name for x in frage.plan()["weiter"].felder]


def test_einmal_wird_routine_quelle_aus_dem_fenster():
    roh = dict(QUELL_TERMIN, layer="termine")
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    _feld(f, "wied").wahl = kw.WIEDERHOLUNG.index("wöchentlich")
    assert f.taste(19) == "fertig"
    (_m, pfad, body), _weg = f.plan()["aufrufe"]
    assert pfad == "/api/calendar/routine" and body["quelle"] == Q
    f = kw.formular_bearbeiten(roh, TAG, TAG)
    _typ_normal(f)
    _feld(f, "wied").wahl = kw.WIEDERHOLUNG.index("wöchentlich")
    assert f.taste(19) == "fertig"
    (_m, pfad, body), _weg = f.plan()["aufrufe"]
    assert "quelle" not in body


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


def test_tasten_stehen_in_der_leiste_nicht_im_kasten():
    """Seit 11.10.2026 keine Fußzeile mehr im Kasten (vorher
    kalender_ansichten.tasten_hinweis in drei Breitenstufen): die Leiste ganz
    unten zeigt die Tastentabelle des Kalenders und kürzt selbst. ! abhaken
    steht in A und C; eine eigene Taste für Listen-Termine gibt es nicht
    (A ist ein zweites a und wird nicht angezeigt)."""
    from tui.ansichten.kalender import Kalender
    assert not hasattr(ka, "tasten_hinweis")
    for ansicht in ("a:termine", "c:woche"):
        e = dict(Kalender.TASTEN.eintraege(ansicht))
        assert e["!"] == "tick off" and "A" not in e
        assert Kalender.TASTEN.nimmt(ansicht, "A") == "neu"
