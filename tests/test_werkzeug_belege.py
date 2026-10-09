"""Belege statt „OK" — und ein Status, den die KI nicht erraten muss.

2026-10-08, nach Sashas Kalender-Testlauf (Gespräch 20261008-132404): die KI
meldete „donnerstags 18:10–19:00" als erledigt, das Werkzeug hatte aber nur
„OK, Routine eingetragen" gesagt und kein Ende gespeichert. Seitdem:

  - jedes schreibende Werkzeug liest nach dem Schreiben nach und gibt den
    echten Stand als Beleg zurück (Register-Felder `schreibt`/`beweis`);
  - jedes Ergebnis an die KI beginnt mit „[ergebnis: …]";
  - ask_choice ohne Antwort heißt „keine_antwort", nie „gewählt: None";
  - die Websuche sagt, dass Treffer nicht gelesen sind, und fetch_url sagt,
    wenn eine Seite kaum Inhalt hatte.
"""
import io
import urllib.request

import pytest

import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import werkzeug_befund
import werkzeug_register
import werkzeug_schleife
from werkzeug_befund import Befund

# Werkzeuge, die bestätigt werden, aber nichts von Sashas Daten verändern.
# Der Browser (2026-10-09) fragt vor einem neuen Host und vor Anmeldeformularen,
# liest aber nur — nichts von Sasha ändert sich.
NICHT_SCHREIBEND = {"web_search", "fetch_url", "run_code",
                    "browser_open", "browser_click", "browser_type"}


def test_jedes_schreibende_werkzeug_sagt_wie_es_belegt():
    for w in werkzeug_register.WERKZEUGE:
        if w.schreibt:
            assert w.beweis and len(w.beweis) > 10, w.name
        else:
            assert w.beweis is None, w.name


def test_was_bestaetigt_wird_und_schreibt_ist_als_schreibend_markiert():
    """Wer ein neues gegatetes Werkzeug anlegt, muss sich entscheiden: schreibt
    es (dann mit Beleg) oder nicht (dann in die Liste oben)."""
    for w in werkzeug_register.WERKZEUGE:
        if w.erlaubnis is not False and w.name not in NICHT_SCHREIBEND:
            assert w.schreibt, w.name


# ── Jedes schreibende Werkzeug, einmal echt ausgeführt ─────────────────

@pytest.fixture
def umgebung(tmp_path, monkeypatch):
    """Alles, was die Schreiber berühren, in Wegwerf-Ordnern (Gedächtnis,
    Ablage, Kalender biegt conftest schon um)."""
    import graphs
    import sandbox
    # Beide: _REGISTRY wird beim Import aus _DATA_DIR gebaut und zeigt sonst
    # weiter auf data/graphs.json.
    monkeypatch.setattr(graphs, "_DATA_DIR", str(tmp_path / "graphs"))
    monkeypatch.setattr(graphs, "_REGISTRY", str(tmp_path / "graphs" / "graphs.json"))

    class Antwort(io.BytesIO):
        headers = {"Content-Type": "text/html"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    html = b"<html><body><p>" + b"Ein Satz mit Inhalt. " * 40 + b"</p></body></html>"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: Antwort(html))
    monkeypatch.setattr(sandbox, "datei_lesen", lambda lauf, datei, n: b"zeile eins\n")
    # Sashas Nutzerordner (Input/, Output/; import_skill liest dort, 2026-10-09).
    monkeypatch.setenv("ZENTRALE_NUTZER_ORDNER", str(tmp_path / "nutzer"))
    return tmp_path


# Je schreibendem Werkzeug ein Aufruf, der gelingen muss. Reihenfolge zählt
# (ändern setzt Anlegen voraus). Fehlt hier ein Werkzeug, wird der Test rot.
AUFRUFE = [
    ("add_calendar_entry", {"layer": "termine", "day": "2026-10-20",
                            "label": "Arzt", "time": "10:00", "ende": "11:00"}),
    ("edit_calendar_entry", {"day": "2026-10-20", "label": "Arzt", "ort": "Praxis"}),
    ("delete_calendar_entry", {"day": "2026-10-20", "label": "Arzt"}),
    ("add_calendar_routine", {"label": "Geige", "rrule": "FREQ=WEEKLY;BYDAY=TH",
                              "time": "18:10", "ende": "19:10"}),
    ("edit_calendar_routine", {"label": "Geige", "aktion": "aendern", "ort": "Schule"}),
    ("add_calendar_pause", {"label": "Geige", "von": "2026-10-05", "bis": "2026-10-16"}),
    ("write_note", {"name": "tagebuch", "text": "Heute Geige geübt."}),
    ("write_note", {"name": "wegzeiten", "text": "Zur Geigenschule 20 min."}),
    ("rewrite_note", {"name": "wegzeiten", "content": "Zur Geigenschule 25 min."}),
    ("fetch_document", {"url": "https://example.org/a", "name": "handbuch"}),
    ("create_series", {"name": "Spagat", "typ": "number", "einheit": "cm"}),
    ("log_series", {"series": "Spagat", "value": 12, "day": "2026-10-08"}),
    ("propose_skill", {"name": "probelauf-belege", "beschreibung": "Wenn Sasha die Woche plant.",
                       "inhalt": "1. Termine lesen.\n2. Lücken nennen."}),
    ("edit_skill", {"name": "probelauf-belege", "inhalt": "1. Erst Termine lesen.\n2. Dann fragen."}),
    ("create_document", {"titel": "Plan", "inhalt": "eins\nzwei"}),
    ("save_from_sandbox", {"lauf": "x", "datei": "notiz.txt", "titel": "Notiz"}),
    ("create_pdf", {"titel": "Plan", "inhalt": "# Woche\n\nMontag Geige."}),
    ("create_docx", {"titel": "Brief", "inhalt": "# Brief\n\nLiebe Frau Meier,"}),
]


def test_jedes_schreibende_werkzeug_belegt_echt(umgebung):
    # browser_screenshot braucht eine offene Seite: belegt in tests/test_browser.py
    # (test_bild_landet_in_der_ablage_mit_beleg, ohne Chromium).
    abgedeckt = {n for n, _ in AUFRUFE} | {"update_document", "combine_pdf", "edit_docx",
                                           "browser_screenshot", "import_skill",
                                           "unzip", "remove_input"}
    schreibend = {w.name for w in werkzeug_register.WERKZEUGE if w.schreibt}
    assert schreibend <= abgedeckt, schreibend - abgedeckt
    ids = {}
    for name, args in AUFRUFE:
        r = ki_werkzeuge._verteilen(name, args)
        assert isinstance(r, Befund), (name, r)
        assert r.status == werkzeug_befund.OK, (name, r)
        assert r.beleg, (name, r)
        if name in ("create_document", "create_pdf", "create_docx"):
            ids[name] = r.split("(id ", 1)[1].split(",", 1)[0].split(")", 1)[0]
    doc_id = ids["create_document"]
    # Die zwei, die eine vorhandene Datei brauchen (Skills pdf/word, 08.10.)
    r = ki_werkzeuge._verteilen("combine_pdf", {"titel": "Doppelt", "teile": [
        {"quelle": ids["create_pdf"]}, {"quelle": ids["create_pdf"]}]})
    assert isinstance(r, Befund) and r.status == "ok" and "2 Seiten" in r.beleg, r
    r = ki_werkzeuge._verteilen("edit_docx", {"quelle": ids["create_docx"], "ersetzen": [
        {"alt": "Frau Meier", "neu": "Herr Kurz"}]})
    assert isinstance(r, Befund) and r.status == "ok" and r.beleg, r
    r = ki_werkzeuge._verteilen("update_document", {"id": doc_id, "inhalt": "drei"})
    assert isinstance(r, Befund) and r.status == "ok" and "Fassung 2" in r.beleg
    # import_skill braucht eine Datei (2026-10-09): ein Skill-Ordner in Input/.
    import nutzer_ordner
    from pathlib import Path
    skill = Path(nutzer_ordner.unterordner()) / "beleg-import"
    skill.mkdir()
    (skill / "SKILL.md").write_text("---\nname: beleg-import\ndescription: Wenn x.\n---\n\n1. A.\n",
                                    encoding="utf-8")
    r = ki_werkzeuge._verteilen("import_skill", {"pfad": "beleg-import"})
    assert isinstance(r, Befund) and r.status == "ok" and "beleg-import" in r.beleg, r
    # unzip und remove_input (2026-10-09): eine Zip in Input/, ausgepackt, weggeräumt.
    import zipfile
    with zipfile.ZipFile(Path(nutzer_ordner.unterordner()) / "beleg.zip", "w") as z:
        z.writestr("a.txt", "eins")
    r = ki_werkzeuge._verteilen("unzip", {"datei": "beleg.zip"})
    assert isinstance(r, Befund) and r.status == "ok" and "1 Datei" in r.beleg, r
    r = ki_werkzeuge._verteilen("remove_input", {"datei": "beleg.zip"})
    assert isinstance(r, Befund) and r.status == "ok" and "Papierkorb" in r.beleg, r


def test_notiz_die_nicht_dasteht_ist_kein_erfolg(monkeypatch):
    import gedaechtnis
    monkeypatch.setattr(gedaechtnis, "tagebuch_notieren", lambda text: "Ins Tagebuch geschrieben.")
    monkeypatch.setattr(gedaechtnis, "tagebuch_lesen", lambda: "")
    r = ki_werkzeuge._verteilen("write_note", {"name": "tagebuch", "text": "Geige"})
    assert r.status == werkzeug_befund.FEHLGESCHLAGEN
    assert "ABGEBROCHEN" in r and r.code == "W-NICHT-GESPEICHERT"


# ── Die Kopfzeile ──────────────────────────────────────────────────────

def _fahren(name, args, exec_, **kw):
    gen = werkzeug_schleife.run_tool(name, args, tutor_mode=False, active_exec=exec_,
                                     user_query="x", store=None, **kw)
    ev = []
    try:
        while True:
            ev.append(gen.send(None))
    except StopIteration as ende:
        return ev, ende.value


@pytest.mark.parametrize("ergebnis, status", [
    ("Liste: a, b", "ok"),
    ("[Fehler: kaputt]", "fehlgeschlagen"),
    (Befund("nein", "abgelehnt"), "abgelehnt"),
    ("", "fehlgeschlagen"),
    (None, "fehlgeschlagen"),
])
def test_jedes_ergebnis_beginnt_mit_dem_status(ergebnis, status):
    ev, aus = _fahren("read_file", {"path": "x"}, lambda n, a: ergebnis)
    assert aus[0] == "result"
    assert aus[1].startswith(f"[ergebnis: {status}]\n")
    assert "None" not in aus[1]
    assert ev[-1]["werkzeug"]["status"] == status


def test_krachendes_werkzeug_ist_fehlgeschlagen():
    def kracht(n, a):
        raise OSError("weg")
    _, aus = _fahren("read_file", {"path": "x"}, kracht)
    assert aus[0] == "result" and aus[2] is True
    assert aus[1].startswith("[ergebnis: fehlgeschlagen]\nWerkzeug read_file ABGEBROCHEN")
    assert "Fehler W-AUSNAHME: weg" in aus[1]


def test_abgelehnt_hat_seinen_status(monkeypatch):
    import erlaubnis

    def nein(name, args):
        return False
        yield  # Generator
    monkeypatch.setattr(werkzeug_schleife, "_ask_permission", nein)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda n, a: True)
    _, aus = _fahren("add_calendar_entry", {"label": "x"}, lambda n, a: "nie")
    assert aus[1].startswith("[ergebnis: abgelehnt]\n")


def test_die_schiene_erreicht_den_ausfuehrer_und_nur_ihn():
    gesehen = []
    _fahren("read_file", {}, lambda n, a: gesehen.append(werkzeug_befund.schiene()) or "x",
            schiene="gross")
    assert gesehen == ["gross"]
    assert werkzeug_befund.schiene() == "klein"


# ── ask_choice ohne Antwort ────────────────────────────────────────────

@pytest.mark.parametrize("wahl", [None, "(keine Antwort)", "vielleicht"])
def test_keine_wahl_heisst_keine_antwort(wahl, monkeypatch):
    """Am 08.10. las sich „Sasha hat gewählt: None." wie eine Wahl."""
    import state
    monkeypatch.setattr(state, "request_permission", lambda **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda: wahl)
    ev, aus = _fahren("ask_choice", {"frage": "Pause eintragen?"}, lambda n, a: "nie")
    assert aus[1].startswith("[ergebnis: keine_antwort]\n")
    assert "None" not in aus[1]
    assert "NICHT geantwortet" in aus[1] and "frag" in aus[1]
    # und es steht als Ergebnis im Verlauf
    assert ev[-1]["werkzeug"] == {"phase": "fertig", "name": "ask_choice",
                                  "text": aus[1].split("\n", 1)[1],
                                  "status": "keine_antwort"}


def test_eine_echte_wahl_kommt_an(monkeypatch):
    import state
    monkeypatch.setattr(state, "request_permission", lambda **k: None)
    monkeypatch.setattr(state, "wait_permission", lambda: "ja")
    _, aus = _fahren("ask_choice", {"frage": "Pause eintragen?"}, lambda n, a: "nie")
    assert aus[1] == "[ergebnis: ok]\nSasha hat gewählt: ja."


def test_zeit_um_liefert_bei_ask_choice_none():
    import state
    state.request_permission(options=["ja", "nein"], timeout_default=None)
    assert state.wait_permission(0.01) is None


def test_tui_loescht_nicht_die_naechste_frage(monkeypatch):
    """Die Ursache, warum eine Frage verschwinden konnte: die Antwort auf die
    ERSTE Frage löschte nach dem POST AI['perm'] — auch wenn dort schon die
    ZWEITE stand (der Server macht sofort weiter)."""
    from tui.ansichten import chat as chat_mod
    import threading

    zweite = {"frage": "Und das?", "optionen": ["ja", "nein"]}

    class C:
        AI = {"perm": {"frage": "Erst?", "optionen": ["ja", "nein"]}}
        AI_LOCK = threading.Lock()

    def post(pfad, methode, body):
        C.AI["perm"] = zweite          # kommt an, während der POST läuft
    monkeypatch.setattr(chat_mod, "api_call", post)
    chat_mod.Chat.ai_answer_perm(C, "ja")
    assert C.AI["perm"] is zweite


# ── Websuche und Seiten ehrlich beschriftet ────────────────────────────

def test_suchtreffer_sind_als_ungelesen_beschriftet(monkeypatch):
    import web
    monkeypatch.setattr(web, "_searxng_search", lambda q, n: [
        {"title": "Ferien Saarland", "url": "https://x.de", "snippet": "Kalender 2026"}])
    text = web.suche("Herbstferien Saarland")
    assert text.startswith("Treffer = Hinweise, NICHT gelesen.")
    assert "nicht nachgelesen" in text


def test_duenne_seite_wird_gemeldet(monkeypatch):
    import web
    monkeypatch.setattr(web.net, "get", lambda *a, **k:
                        b"<html><a>Start</a> <a>Lehre</a> <a>Anmelden</a></html>")
    r = web.hole("https://lsf.example/baum")
    # Seit 2026-10-09 kein „teilweise": gelesen ist, was da ist; die
    # Warnung sagt, wie wenig.
    assert werkzeug_befund.status_von(r) == "ok"
    assert "kaum lesbaren Inhalt" in r and "Anmelde-Wort" in r


def test_volle_seite_bleibt_wie_sie_war(monkeypatch):
    import web
    monkeypatch.setattr(web.net, "get", lambda *a, **k:
                        b"<p>" + b"Die Vorlesung ist am Montag. " * 30 + b"</p>")
    r = web.hole("https://example.org")
    assert werkzeug_befund.status_von(r) == "ok"
    assert r.startswith("Inhalt von https://example.org:")


# ── Die Regel im Prompt ────────────────────────────────────────────────

def test_gross_hat_die_belegpflicht_klein_nicht():
    from profil import gross, klein
    assert "Belegt oder gesagt" in gross.system()
    assert "weiß ich nicht" in gross.system()
    assert "Belegt oder gesagt" not in klein.system()
