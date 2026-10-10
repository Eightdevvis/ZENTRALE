"""Das Werkzeug-Register (core/werkzeug_register.py): ein Eintrag pro Werkzeug.

2026-10-07, Phase 0 des Claude-Web-Plans. Vorher lag ein Werkzeug an drei
Stellen (Schema, Ausführung, Erlaubnis), und nichts merkte, wenn eine fehlte:
das Modell sah ein Werkzeug, das der Kern nicht kannte ("[Unbekanntes Tool]",
eine bezahlte Runde für nichts) — oder ein schreibendes Werkzeug kam ohne
Eintrag in der Erlaubnis-Liste ungefragt durch.

Diese Tests halten fest:
  1. keine Waisen: jedes angebotene Werkzeug hat einen Ausführer, jeder
     Ausführer ein angebotenes Werkzeug;
  2. das Register ist die EINZIGE Werkzeug-Liste (keine zweite in
     erlaubnis.py, profil/ oder ki_werkzeuge.py);
  3. das Verhalten der Nachschlage-Funktionen, inklusive Fehlerfälle.
Dass die Listen an die Modelle byte-gleich geblieben sind, prüft
tests/test_werkzeug_schnappschuss.py.
"""
import ast
import os

import pytest

import ki_werkzeuge
import werkzeug_register as reg

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")


def _alle_namen() -> set:
    """Jeder Name, unter dem ein Werkzeug irgendwo heißt."""
    namen = set()
    for w in reg.WERKZEUGE:
        namen.add(w.name)
        if w.klein_name:
            namen.add(w.klein_name)
    return namen


# ── 1. Keine Waisen ────────────────────────────────────────────────────

def test_jedes_angebotene_werkzeug_hat_einen_ausfuehrer():
    for schiene in reg.SCHIENEN:
        for w in reg.auf_schiene(schiene):
            if w.in_der_schleife:
                assert w.ausfuehrer is None, w.name
            else:
                assert callable(w.ausfuehrer), f"{schiene}: {w.name} ohne Ausführer"


def test_jeder_eintrag_wird_auf_einer_schiene_angeboten():
    """Ein Eintrag ohne Schiene ist ein Werkzeug, das kein Modell je sieht —
    toter Code, der so tut, als gäbe es etwas."""
    angeboten = {w.name for s in reg.SCHIENEN for w in reg.auf_schiene(s)}
    assert {w.name for w in reg.WERKZEUGE} == angeboten


def test_jede_ausfuehrer_funktion_in_ki_werkzeuge_ist_angemeldet():
    """Umgekehrte Richtung: eine Werkzeug-Funktion in ki_werkzeuge, die im
    Register fehlt, liefe nie. Gezählt werden die Funktionen mit
    @ausfuehrer-Dekorator im Quelltext. Seit 2026-10-08 stehen die PDF- und
    Word-Werkzeuge in einer eigenen Datei (ki_pdf_word, von ki_werkzeuge
    importiert) — beide zählen."""
    knoten_alle = []
    # Seit 2026-10-09 auch der Browser (ki_browser) und der Nutzerordner
    # (ki_nutzer_ordner: find_files, search_files, import_skill).
    for datei in ("ki_werkzeuge.py", "ki_pdf_word.py", "ki_browser.py", "ki_nutzer_ordner.py"):
        with open(os.path.join(CORE, datei), encoding="utf-8") as f:
            knoten_alle += ast.parse(f.read()).body
    dekoriert = {}
    for knoten in knoten_alle:
        if isinstance(knoten, ast.FunctionDef):
            for d in knoten.decorator_list:
                if (isinstance(d, ast.Call) and getattr(d.func, "id", "") == "ausfuehrer"):
                    dekoriert[d.args[0].value] = knoten.name
    mit_ausfuehrer = {w.name: w.ausfuehrer.__name__ for w in reg.WERKZEUGE if w.ausfuehrer}
    assert dekoriert == mit_ausfuehrer


def test_namen_sind_eindeutig():
    namen = [w.name for w in reg.WERKZEUGE]
    assert len(namen) == len(set(namen))
    for schiene in reg.SCHIENEN:
        auf = [t["function"]["name"] for t in reg.schema(schiene)]
        assert len(auf) == len(set(auf)), schiene


# ── 2. Das Register ist die einzige Liste ──────────────────────────────

@pytest.mark.parametrize("datei", [
    "erlaubnis.py", "profil/__init__.py", "profil/klein.py", "profil/gross.py",
    "ki_werkzeuge.py",
])
def test_keine_zweite_werkzeugliste(datei):
    """Kein Werkzeug-Name als eigener String außerhalb des Registers — sonst
    wächst wieder eine zweite Liste heran, die ein neues Werkzeug vergisst.
    Einzige Ausnahme: der Name im @ausfuehrer-Dekorator, mit dem sich die
    Funktion anmeldet (der Test oben prüft, dass er stimmt)."""
    with open(os.path.join(CORE, datei), encoding="utf-8") as f:
        baum = ast.parse(f.read())
    erlaubt = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.FunctionDef):
            for d in knoten.decorator_list:
                if isinstance(d, ast.Call):
                    erlaubt.update(id(a) for a in d.args)
    namen = _alle_namen()
    treffer = [k.value for k in ast.walk(baum)
               if isinstance(k, ast.Constant) and k.value in namen
               and id(k) not in erlaubt]
    assert not treffer, f"{datei} nennt Werkzeuge selbst: {treffer}"


def test_die_schienen_geben_die_liste_aus_dem_register_weiter():
    import ai
    import cloud
    import erlaubnis
    import profil
    from profil import gross, klein
    assert klein.TOOLS == reg.schema("klein")
    assert gross.TOOLS == reg.schema("gross")
    assert ai.TOOLS is klein.TOOLS
    assert cloud.cloud_tools() is gross.TOOLS
    assert profil.ALIASE is reg.ALIASE
    assert erlaubnis.PERMISSION_REQUIRED_TOOLS == reg.immer_bestaetigen()


# ── 3. Verhalten ───────────────────────────────────────────────────────

def test_alias_und_kanonischer_name_fuehren_dasselbe_aus(monkeypatch):
    w = reg.eintrag("read_news")
    monkeypatch.setattr(w, "ausfuehrer", lambda args: f"news {args.get('tage')}")
    assert ki_werkzeuge._verteilen("lies_news", {"tage": 7}) == "news 7"
    assert ki_werkzeuge._verteilen("read_news", {"tage": 7}) == "news 7"


def test_unbekanntes_werkzeug_wird_gemeldet_nicht_geworfen():
    assert ki_werkzeuge._verteilen("gibt_es_nicht", {}) == "[Unbekanntes Tool: gibt_es_nicht]"
    # Werkzeuge, die die Schleife selbst erledigt, laufen hier nie durch.
    assert ki_werkzeuge._verteilen("antwort", {"text": "x"}) == "[Unbekanntes Tool: antwort]"
    assert reg.eintrag("gibt_es_nicht") is None


def test_ausfuehrer_fuer_unbekanntes_werkzeug_wirft():
    with pytest.raises(KeyError):
        reg.ausfuehrer("gibt_es_nicht")
    # Alias reicht nicht: angemeldet wird unter dem Namen des Kerns.
    with pytest.raises(KeyError):
        reg.ausfuehrer("lies_news")


def test_ausfuehrer_fuer_schleifen_werkzeug_wirft():
    with pytest.raises(ValueError):
        reg.ausfuehrer("antwort")


def test_schema_unbekannte_schiene_wirft():
    with pytest.raises(ValueError):
        reg.schema("mittel")


def test_schema_liefert_eigene_kopien():
    """Ein Weg, der im Schema herumschreibt, darf weder die andere Schiene
    noch das Register verändern — sonst bräche der Cache im nächsten Zug."""
    a = reg.schema("gross")
    a[0]["function"]["parameters"]["properties"].clear()
    a[0]["function"]["description"] = "kaputt"
    b = reg.schema("gross")
    assert b[0]["function"]["parameters"]["properties"]
    assert b[0]["function"]["description"] != "kaputt"


def test_klein_namen_und_terminale():
    assert reg.schema("klein")[-1]["function"]["name"] == "frage_knopf"
    assert reg.terminal("klein") == {"antwort", "lies_news"}
    # antwort seit 2026-10-10 auch auf gross (Selbstauskunft).
    assert reg.terminal("gross") == {"antwort", "read_news"}
    assert reg.kanonisch("hole_url") == "fetch_url"
    assert reg.kanonisch("fetch_url") == "fetch_url"


def test_jedes_gegatete_werkzeug_hat_eine_eigene_frage():
    """Sasha drückt einen Knopf, ohne den Aufruf zu sehen. Die allgemeine
    Frage („die Aktion X ausführen?") sagt ihm nicht, WAS passiert."""
    for w in reg.WERKZEUGE:
        if w.erlaubnis is not False:
            assert w.frage is not None, w.name


def test_regel_mit_argumenten_greift_nur_mit_argumenten():
    assert not reg.braucht_erlaubnis("write_note")
    assert not reg.braucht_erlaubnis("write_note", {})
    assert reg.braucht_erlaubnis("write_note", {"name": "hausregeln", "text": "x"})
    assert not reg.braucht_erlaubnis("write_note", {"name": "einkauf", "text": "x"})


def test_unbekanntes_werkzeug_braucht_keine_erlaubnis_und_bekommt_allgemeine_frage():
    assert not reg.braucht_erlaubnis("gibt_es_nicht", {"x": 1})
    assert reg.frage("gibt_es_nicht", {}) == 'Soll ich die Aktion "gibt_es_nicht" wirklich ausführen?'
