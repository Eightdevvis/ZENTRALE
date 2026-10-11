"""Ersetzen, Papierkorb, zurückholen — die Ablage-Werkzeuge der KI
(2026-10-11, core/werkzeug_ablage.py + core/ki_ablage_adapter.py).

Anlass: Führerschein-Gespräch 20261011-081303 — jede Änderung eines PDFs
wurde eine weitere Kopie. Sashas Regel: „ihre eigenen dokumente soll sie
einfach so wegräumen können. meine sachen soll sie mit nachfrage wegräumen
können." Geprüft am Verhalten: Gate je nach Besitzer, Satz mit Beleg, Original
im Papierkorb, ganz oder gar nicht.
"""
import ablage
import erlaubnis
import ki_werkzeuge
import werkzeug_register
from werkzeug_befund import Befund


def _rufen(name, **args):
    r = ki_werkzeuge._verteilen(name, args)
    assert isinstance(r, Befund), r
    return r


def _ki(titel="Führerschein-Tracking", inhalt="# Kosten\n\nGrundbetrag 380", art="markdown"):
    return ablage.anlegen(titel, inhalt, art)["id"]


def _sasha(titel="Fahrschule-Preise.pdf"):
    return ablage.anlegen(titel, b"%PDF-1.4 x", "pdf", herkunft="anhang")["id"]


# ── Gate: KI-Dokumente frei, Sashas jedes Mal gefragt ──────────────────

def test_eigene_dokumente_ohne_frage_sashas_nur_mit_einmal_ja():
    ki, sasha = _ki(), _sasha()
    for name in ("replace_document", "trash_document"):
        assert not erlaubnis.braucht_erlaubnis(name, {"id": ki})
        assert erlaubnis.braucht_erlaubnis(name, {"id": sasha})
        assert erlaubnis.optionen(name, {"id": sasha}) == ["ja, nur dieses mal", "nein"]
        assert not werkzeug_register.immer_erlaubbar(name)
    assert erlaubnis.frage("trash_document", {"id": sasha}) == \
        "„Fahrschule-Preise.pdf“ hast du abgelegt — in den Papierkorb legen?"
    assert "hast du abgelegt" in erlaubnis.frage("replace_document", {"id": sasha})
    assert not erlaubnis.braucht_erlaubnis("restore_document", {"id": sasha})
    # Unbekannte id: keine Frage, das Werkzeug bricht ohnehin ab.
    assert not erlaubnis.braucht_erlaubnis("trash_document", {"id": "gibts-nicht-0000"})


def _fahren(name, args, antwort, monkeypatch):
    """Durch die echte Schleife mit Gate; Sasha klickt `antwort`."""
    import state
    import werkzeug_schleife
    monkeypatch.setattr(state, "wait_permission", lambda *a, **k: antwort)
    gen = werkzeug_schleife.run_tool(name, args, tutor_mode=False,
                                     active_exec=ki_werkzeuge._verteilen,
                                     user_query="x", store=None, schiene="gross")
    ev = []
    try:
        while True:
            ev.append(gen.send(None))
    except StopIteration as ende:
        return ev, ende.value


def test_ohne_ja_bleibt_sashas_dokument_unveraendert(monkeypatch):
    sasha = _sasha()
    vorher = ablage.kopf(sasha)
    ev, erg = _fahren("trash_document", {"id": sasha}, "nein", monkeypatch)
    frage = [e["permission"] for e in ev if "permission" in e]
    assert frage and frage[0]["optionen"] == ["ja, nur dieses mal", "nein"]
    assert ablage.kopf(sasha) == vorher
    ev, erg = _fahren("trash_document", {"id": sasha}, "ja, nur dieses mal", monkeypatch)
    assert ablage.im_papierkorb(ablage.kopf(sasha))
    # Eigenes Dokument: keine Frage.
    ki = _ki()
    ev, erg = _fahren("trash_document", {"id": ki}, "nein", monkeypatch)
    assert not [e for e in ev if "permission" in e] and ablage.im_papierkorb(ablage.kopf(ki))


def test_mit_ja_liegt_sashas_dokument_im_papierkorb():
    sasha = _sasha()
    r = _rufen("trash_document", id=sasha)
    assert r.status == "ok", r
    assert r.startswith(f"„Fahrschule-Preise.pdf“ IN DEN PAPIERKORB GELEGT (#{sasha})")
    assert ablage.im_papierkorb(ablage.kopf(sasha)) and ablage.liste() == []
    r = _rufen("restore_document", id=sasha)
    assert r.status == "ok" and "AUS DEM PAPIERKORB GEHOLT" in r
    assert [d["id"] for d in ablage.liste()] == [sasha]


# ── Ersetzen ───────────────────────────────────────────────────────────

def test_ersetzen_neue_fassung_alt_im_papierkorb_mit_beleg():
    alt = _ki()
    r = _rufen("replace_document", id=alt, inhalt="# Kosten\n\nGrundbetrag 380\nFahrstunde 60")
    assert r.status == "ok", r
    neu = [d["id"] for d in ablage.liste()]
    assert len(neu) == 1 and neu[0] != alt
    assert r.startswith(f"„Führerschein-Tracking“ ERSETZT (#{neu[0]}): alt {alt} liegt im "
                        f"Papierkorb")
    assert r.beleg
    assert ablage.lesen(neu[0])["inhalt"].endswith("Fahrstunde 60")
    assert ablage.kopf(alt)["ersetzt_durch"] == neu[0]


def test_ersetzen_baut_pdf_und_word_aus_markdown():
    for art, roh in (("pdf", None), ("docx", None)):
        import pdf_schreiben
        import word_datei
        daten = pdf_schreiben.erzeugen("T", "# Alt")[0] if art == "pdf" else \
            word_datei.erzeugen("T", "# Alt")
        alt = ablage.anlegen(f"Tracking {art}", daten, art)["id"]
        r = _rufen("replace_document", id=alt, inhalt="# Neu\n\n| a | b |\n|---|---|\n| 1 | 2 |")
        assert r.status == "ok", r
        neu = ablage.kopf(alt)["ersetzt_durch"]
        assert ablage.kopf(neu)["art"] == art


def test_ersetzen_bricht_kontrolliert_ab_und_laesst_alles_wie_es_war():
    alt = _ki()
    vorher = (ablage.kopf(alt), ablage.alle_ids())
    r = _rufen("replace_document", id=alt, inhalt="")
    assert r.status == "fehlgeschlagen" and r.code in ("A-PFLICHTFELD", "A-ABGELEHNT"), r
    r = _rufen("replace_document", id="gibts-nicht-0000", inhalt="x")
    assert r.code == "A-DOK-UNBEKANNT"
    bild = ablage.anlegen("Skizze", b"\x89PNG\r\n\x1a\n", "bild", endung=".png")["id"]
    assert _rufen("replace_document", id=bild, inhalt="x").code == "A-ERSETZEN-ART"
    pdf = ablage.anlegen("P", b"%PDF-1.4 x", "pdf")["id"]
    assert _rufen("replace_document", id=pdf, inhalt="Zeichen 汉 hier").code == "P-ZEICHEN"
    assert (ablage.kopf(alt), ablage.alle_ids()) == (vorher[0], vorher[1] + sorted([bild, pdf])) \
        or ablage.kopf(alt) == vorher[0]
    assert not ablage.im_papierkorb(ablage.kopf(alt))


def test_nachgelesen_falsch_nimmt_alles_zurueck(monkeypatch):
    import ki_ablage_adapter
    alt = _ki()
    monkeypatch.setattr(ki_ablage_adapter, "_lesbar", lambda neu, inhalt: False)
    r = _rufen("replace_document", id=alt, inhalt="neu")
    assert r.status == "fehlgeschlagen" and r.code == "W-NICHT-GESPEICHERT", r
    assert ablage.alle_ids() == [alt] and not ablage.im_papierkorb(ablage.kopf(alt))


def test_update_document_auf_pdf_zeigt_den_weg():
    pdf = _sasha()
    r = _rufen("update_document", id=pdf, inhalt="x")
    assert r.code == "A-DATEI-ERSETZEN" and "replace_document" in r
    assert ablage.kopf(pdf)["fassung"] == 1


def test_papierkorb_doppelt_und_zurueck_ohne_korb():
    ki = _ki()
    assert _rufen("restore_document", id=ki).code == "A-NICHT-IM-PAPIERKORB"
    assert _rufen("trash_document", id=ki).status == "ok"
    assert _rufen("trash_document", id=ki).code == "A-IM-PAPIERKORB"
    assert _rufen("replace_document", id=ki, inhalt="x").code == "A-IM-PAPIERKORB"
