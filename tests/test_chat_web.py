"""Der Chat nach dem Vorbild von Claude Web (2026-10-07): Aufteilung des
Kastens, Verlauf mit Schritten/Denken/Aktionen, Pixel-Symbole — reine
Funktionen ohne Bildschirm."""
from tui import pixel
from tui.ansichten import chat_layout as L
from tui.ansichten import symbole, verlauf as V


# ── Aufteilung ────────────────────────────────────────────────────────

def _breiten(a):
    return {k: (getattr(a, k).w if getattr(a, k) else 0) for k in a._fields}


def test_schmal_seite_zu_nur_symbole_dokument_ersetzt_verlauf():
    a = L.aufteilen(0, 80)
    assert a.seite is None and a.leiste and a.mitte and a.rechts is None
    assert a.leiste.w + 1 + a.mitte.w == 78
    d = L.aufteilen(0, 80, rechts="dokument")
    assert d.mitte is None and d.rechts.w == 78 - L.LEISTE - 1
    o = L.aufteilen(0, 80, rechts="outputs")
    assert o.mitte is None and o.rechts


def test_offene_seite_daneben_und_zu_schmal_ueber_alles():
    a = L.aufteilen(0, 80, seite_offen=True)
    assert a.seite == L.Bereich(1, L.SEITE) and a.mitte.w == 78 - L.SEITE - 1
    a = L.aufteilen(0, 60, seite_offen=True)
    assert a.seite == L.Bereich(1, 58) and a.mitte is None


def test_breit_alles_nebeneinander_ohne_luecke():
    for rechts in ("dokument", "outputs"):
        a = L.aufteilen(0, 136, seite_offen=True, rechts=rechts)
        assert a.seite and a.mitte and a.rechts, rechts
        assert a.mitte.w >= L.MITTE_MIN
        # Seite | Mitte | rechts mit je einer Trennspalte, genau bis zum Rahmen
        assert a.seite.x == 1 and a.mitte.x == a.seite.x + a.seite.w + 1
        assert a.rechts.x == a.mitte.x + a.mitte.w + 1
        assert a.rechts.x + a.rechts.w == 135


def test_gross_nimmt_mitte_und_rechts():
    a = L.aufteilen(0, 160, seite_offen=True, rechts="dokument", gross=True)
    assert a.mitte is None and a.rechts.x == a.seite.x + a.seite.w + 1


def test_textspalte_mittig_und_begrenzt():
    s = L.spalte(L.Bereich(10, 200))
    assert s.w == L.TEXT_MAX and s.x == 10 + (200 - L.TEXT_MAX) // 2
    assert L.spalte(L.Bereich(1, 40)) == L.Bereich(3, 36)
    assert L.spalte(None) is None


def test_seite_von_selbst_offen_erst_wenn_breit():
    assert not L.seite_auto(80) and not L.seite_auto(120) and L.seite_auto(136)


# ── Verlauf ───────────────────────────────────────────────────────────

LOG = [("user", "wie flicke ich?"), ("anhang", "anhang: foto.png"),
       ("denken", "Er fragt nach unterwegs."),
       ("werkzeug", "read_note(name=fahrrad)"), ("werkzeug_ergebnis", "↳ flickzeug, kleber"),
       ("werkzeug", "web_search(query=x)"), ("werkzeug_fehler", "web_search ✗ kein netz"),
       ("ablage", "d1\tPackliste"), ("ai", "Mit **Flickzeug**."),
       ("user", "danke"), ("ai", "Gern.")]


def _text(zeilen):
    return ["".join(t for t, _s, _z in z) for z in zeilen]


def test_schritte_fassen_start_und_ergebnis_zusammen():
    s = V.schritte(LOG)
    assert set(s) == {3, 5}
    assert s[3]["name"] == "read_note" and s[3]["args"] == "name=fahrrad"
    assert s[3]["ergebnis"] == "flickzeug, kleber" and not s[3]["fehler"]
    assert s[5]["fehler"] and s[5]["ergebnis"] == "kein netz"
    # gespeicherter Fehler ohne Start davor ist ein eigener Schritt
    assert V.schritte([("werkzeug_fehler", "web() ✗")])[0]["fehler"]


def test_verlauf_wie_claude():
    z = V.verlauf_zeilen(LOG, 60, letzte_ai=V.letzte_antwort(LOG))
    t = _text(z)
    # Nutzer rechts auf eigener Fläche, ohne „du:"
    nutzer = next(x for x in z if any(s == "user" for _t, s, _z in x))
    assert nutzer[0][0].strip() == "" and "du:" not in "".join(t)
    assert any(x.strip() == "[▤ foto.png]" for x in t)
    assert "▸ thought · 24 chars" in t
    assert "Used memory ›" in t and "Used web search ✗ ›" in t
    assert "▤ Packliste ›" in t
    assert "Mit Flickzeug." in t and "ki:" not in "".join(t)
    # copy unter jeder Antwort, retry nur unter der letzten
    assert t.count("copy") == 1 and t.count("copy · retry") == 1
    assert V.ziele(z) == [("denken", 2), ("schritt", 3), ("schritt", 5), ("dok", 7),
                          ("kopieren", 8), ("kopieren", 10), ("wiederholen", 10)]


def test_aufklappen_zeigt_argumente_und_ergebnis():
    t = _text(V.verlauf_zeilen(LOG, 60, offen={("schritt", 3), ("denken", 2)}))
    assert "Used memory ⌄" in t and "    name=fahrrad" in t and "  → flickzeug, kleber" in t
    assert "▾ thought · 24 chars" in t and "  Er fragt nach unterwegs." in t
    assert "▾ thought · 24 chars" in _text(V.verlauf_zeilen(LOG, 60, denken_alle=True))


def test_ohne_gespeichertes_ergebnis_sagt_es_das():
    t = _text(V.verlauf_zeilen([("werkzeug", "read_time()"), ("ai", "12 Uhr")], 50,
                               offen={("schritt", 0)}))
    assert "    (ergebnis nicht gespeichert)" in t


def test_laufende_antwort_und_platz_fuer_die_adern():
    z = V.verlauf_zeilen([("user", "hallo")], 40, adern=5, streaming=True)
    assert [s for x in z for _t, s, _z in x].count("adern") == 5
    z = V.verlauf_zeilen([("user", "hallo")], 40, antwort="Hal", streaming=True)
    assert _text(z)[-1] == "Hal▌"
    # während einer Antwort kein retry
    z = V.verlauf_zeilen([("user", "a"), ("ai", "b")], 40, letzte_ai=1, streaming=True)
    assert "retry" not in "".join(_text(z))


def test_benutzt_in_dieser_sitzung():
    assert V.benutzt(LOG) == [("memory", 1, "fahrrad"), ("web search", 1, "x")]
    assert V.benutzt([]) == []


def test_zeilen_passen_in_die_breite():
    lang = [("user", "wort " * 80), ("ai", "satz " * 80), ("hinweis", "x" * 130)]
    for b in (12, 30, 77):
        for x in _text(V.verlauf_zeilen(lang, b, letzte_ai=1)):
            assert len(x) <= b, (b, x)


# ── Symbole ───────────────────────────────────────────────────────────

def test_pixel_symbole_sind_zwei_zeilen_hoch_aus_sextanten():
    """Sasha 08.10.2026: 3×1 Felder waren nicht zu erkennen — Pixel-Symbole
    sind seitdem 4 Felder breit und 2 Zeilen hoch (pixelstil.md)."""
    erlaubt = {pixel.sextant(b) for b in range(64)}
    for name, bild in symbole.BILDER.items():
        assert len(bild) == 6 and all(len(r) == 8 for r in bild), name
        z = symbole.symbol_zellen(name, "nacht")
        assert len(z) == symbole.HOEHE == 2, name
        for zeile in z:
            assert len(zeile) == symbole.BREITE and all(f[0] in erlaubt for f in zeile), name
        assert any(f[0] != " " for f in z[1]), "untere Zeile leer: " + name
        assert symbole.symbol_zellen(name, "tag") != z
        assert symbole.symbol_zellen(name, "nacht", True) != z     # gewählt leuchtet
    leer = symbole.symbol_zellen("gibtsnicht")
    assert len(leer) == 2 and all(f[0] == " " for zeile in leer for f in zeile)


def test_pixel_symbole_sind_verschieden():
    bilder = [tuple(b) for b in symbole.BILDER.values()]
    assert len(set(bilder)) == len(bilder)


def test_zeichen_sind_einspaltig_und_keine_emoji():
    """Die Zeichen-Art: je ein Zeichen, das das Terminal einspaltig zeichnet
    (keine Voll-/Doppelbreite, keine Emoji-Darstellung)."""
    import unicodedata
    for name in list(symbole.BILDER) + ["gibtsnicht"]:
        z = symbole.zeichen(name)
        assert len(z) == 1, name
        assert unicodedata.east_asian_width(z) not in ("W", "F"), (name, z)
        assert ord(z) < 0x1F000, (name, z)             # kein Emoji-Block
    assert set(symbole.ZEICHEN) == set(symbole.BILDER)
    assert len(symbole.DOKU) == 1 and unicodedata.east_asian_width(symbole.DOKU) != "W"


def test_symbol_art_und_groesse():
    assert symbole.art(None) == symbole.art("quatsch") == "pixel2"
    assert symbole.art(" Zeichen ") == "zeichen"
    assert symbole.groesse("pixel2") == (4, 2) and symbole.groesse("zeichen") == (1, 1)


def test_zugeklappte_spalte_so_breit_wie_die_symbole():
    a = L.aufteilen(0, 80, leiste_w=L.LEISTE_ZEICHEN)
    assert a.leiste.w == L.LEISTE_ZEICHEN and a.leiste.w + 1 + a.mitte.w == 78
    assert L.LEISTE >= symbole.BREITE + 2