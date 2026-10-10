"""
„Frag nicht im Text, ruf das Werkzeug" (2026-10-10, core/ehrlichkeit.py
erlaubnis_befund) — für alle Modelle der gross-Schiene.

Anlass: Prüfstand 10.10., f09. Sasha fragt nach der Rückmeldefrist, die KI
antwortet „Soll ich im Netz nach … suchen?" und ruft nichts. Das Erlaubnis-
Gate fragt Sasha ohnehin per Knopf, wo es nötig ist. Vorher prüfte das nur
der qwen-Zusatzprüfer. Gefälschte Modelle, kein echter Aufruf.
"""
import pytest

import ai_config
import consolidation
import ehrlichkeit
import ehrlichkeit_erkennen as erkennen
import erlaubnis
import werkzeug_schleife

R = werkzeug_schleife.Runde
F09_FRAGE = "bis wann muss ich mich eigentlich fürs sommersemester zurückmelden? uni saarland"
F09_ANTWORT = ("Das ist eine konkrete Frist-Frage, die ich nicht raten sollte – muss ich "
               "nachsehen. Soll ich im Netz nach der aktuellen Rückmeldefrist der Uni des "
               "Saarlandes fürs Sommersemester suchen?")


def _befund(antwort, nutzer, protokoll=()):
    return ehrlichkeit.erlaubnis_befund(antwort, list(protokoll), nutzer)


# ── Erkennen ───────────────────────────────────────────────────────────

def test_f09_frage_statt_websuche():
    b = _befund(F09_ANTWORT, F09_FRAGE)
    assert b["art"] == "erlaubnis_frage" and b["werkzeug"] == "web_search"
    assert b["satz"].startswith("Soll ich im Netz")


@pytest.mark.parametrize("nutzer, antwort, aktion", [
    # qwen-Runde 3/4: Änderung verlangt, um Erlaubnis gebeten.
    ("der zahnarzt am dienstag ist jetzt erst um 16:30",
     "Ich ändere den Termin auf 16:30. Soll ich das jetzt durchführen?", "tun"),
    ("parkour am mittwoch ist ab jetzt um halb sieben",
     "Sag kurz Bescheid — dann mach ich's.", "tun"),
    ("lösch den friseur", "Den Friseur am Freitag gefunden. Soll ich ihn löschen?", "loeschen"),
    ("ja", "Soll ich die Pause eintragen?", "pause"),
    ("wann ist analysis I? schau mal im lsf", "Soll ich auf der LSF-Seite nachsehen?", "seite"),
    ("steht der zahnarzt noch drin?", "Soll ich im Kalender nachsehen?", "nachsehen"),
    ("merk dir, dass ich laktose nicht vertrage",
     "Möchtest du, dass ich das in deinen Notizen festhalte?", "notieren"),
])
def test_erlaubnis_fragen_werden_erkannt(nutzer, antwort, aktion):
    b = _befund(antwort, nutzer)
    assert b is not None, antwort
    assert b["werkzeug"] == ehrlichkeit.TATEN[aktion][1]


@pytest.mark.parametrize("nutzer, antwort", [
    # Echte Rückfragen: fehlende Angabe, Wahl zwischen Optionen.
    ("trag mir noch ne extra fahrstunde nächste woche ein", "An welchem Tag und um wie viel Uhr?"),
    ("trag chor montags ein", "Soll ich ihn um 14 Uhr eintragen?"),
    ("trag chor ein", "Soll ich ihn montags oder dienstags eintragen?"),
    ("lösch nyam und geige ist nur donnerstags",
     "Erledigt. Soll ich es nochmal versuchen, oder reicht dir eine grobe Hausnummer?"),
    ("trag die übung ein", "Welche Übungsgruppe soll ich eintragen?"),
    # Sasha will nichts ändern / plaudert / hat nur gefragt.
    ("wie war dein tag", "Gut. Soll ich dir was erzählen?"),
    ("zeig mir die übungen", "Übung 3 ist Fr 8:30. Soll ich sie eintragen?"),
    ("wann ist analysis? nur nachschauen, noch nix eintragen",
     "Mo 10–12. Soll ich es eintragen?"),
    # Keine Frage am Ende, oder die Frage steht nicht am Ende.
    ("lösch den friseur", "Soll ich ihn löschen? Ich warte."),
    ("such mal die ferien", "Die Ferien kenne ich nicht."),
])
def test_echte_rueckfragen_loesen_nicht_aus(nutzer, antwort):
    assert _befund(antwort, nutzer) is None, antwort


def test_lief_das_werkzeug_schon_bleibt_es_ruhig():
    S = ehrlichkeit.Schritt
    such = [S("web_search", {"query": "frist"}, "ok", "Treffer …")]
    assert _befund(F09_ANTWORT, F09_FRAGE, such) is None
    gelesen = [S("read_calendar", {}, "ok", "Kalender …")]
    # Lesen ist noch kein Löschen — die Frage bleibt eine Erlaubnis-Frage.
    assert _befund("Soll ich ihn löschen?", "lösch den friseur", gelesen)
    abgelehnt = [S("delete_calendar_entry", {"kennung": "#t1234"}, "abgelehnt", "…")]
    assert _befund("Soll ich ihn stattdessen löschen?", "lösch den friseur", abgelehnt) is None


def test_auftrag_bewusst_eng():
    assert erkennen.auftrag("lösch nyam und geige ist nur donnerstags")
    assert erkennen.auftrag("aber sie fällt wegen der ferien jetzt aus")
    assert erkennen.auftrag("kannst du mir den zahnarzt eintragen?")
    assert erkennen.auftrag("parkour ist ab jetzt um halb sieben")
    assert not erkennen.auftrag("wann ist analysis I? nur nachschauen, noch nix eintragen")
    assert not erkennen.auftrag("kannst du meinen kalender bearbeiten")
    assert not erkennen.auftrag("nein, lass es")
    assert not erkennen.auftrag("sure wieso denn nicht")
    assert erkennen.zustimmung("sure wieso denn nicht") and not erkennen.zustimmung("nein")


# ── Durch die Schleife ─────────────────────────────────────────────────

class _Skript:
    modell = "test"

    def __init__(self, runden):
        self.runden = list(runden)
        self.hinweise = []

    def runde(self):
        if False:
            yield
        return self.runden.pop(0)

    def assistent_anhaengen(self, r):
        pass

    def ergebnisse_anhaengen(self, e):
        pass

    def hinweis_anhaengen(self, r, text):
        self.hinweise.append(text)


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})


def _laufen(adapter, nutzer, modus="an"):
    aufrufe = []

    def exec_(name, args):
        aufrufe.append(name)
        return "Treffer = Hinweise, NICHT gelesen.\n1. Rückmeldung …"
    p = ehrlichkeit.Pruefer(modus, nutzer_text=nutzer)
    ev = list(werkzeug_schleife.laufen(adapter, tutor_mode=False, active_exec=exec_,
                                       user_query="x", schiene="gross", pruefer=p))
    return ev, aufrufe, p


def _schluss(ev):
    return next((e["ehrlichkeit"] for e in ev if isinstance(e, dict) and "ehrlichkeit" in e),
                None)


def test_text_frage_korrektur_dann_werkzeug():
    a = _Skript([R(F09_ANTWORT),
                 R("", [("c1", "web_search", {"query": "Rückmeldefrist Uni Saarland"})]),
                 R("Laut Suchtreffer 15.01.–15.02.2027, nicht nachgelesen.")])
    ev, aufrufe, p = _laufen(a, F09_FRAGE)
    assert aufrufe == ["web_search"]
    assert len(a.hinweise) == 1
    h = a.hinweise[0]
    assert "frag nicht im Text um Erlaubnis" in h and "web_search" in h and "per Knopf" in h
    assert "<pruefung_automatisch>" in h
    texte = "".join(e for e in ev if isinstance(e, str))
    assert "Soll ich" not in texte and "Suchtreffer" in texte
    schluss = _schluss(ev) or {}
    assert not schluss.get("warnungen") and p.korrekturen == 1


def test_bleibt_sie_beim_fragen_eine_runde_und_keine_warnung():
    a = _Skript([R(F09_ANTWORT), R(F09_ANTWORT), R(F09_ANTWORT)])
    ev, aufrufe, p = _laufen(a, F09_FRAGE)
    assert aufrufe == [] and len(a.hinweise) == 1 and p.korrekturen == 1
    assert "".join(e for e in ev if isinstance(e, str)) == F09_ANTWORT
    schluss = _schluss(ev) or {}
    assert not schluss.get("warnungen")
    assert [b["art"] for b in schluss.get("befunde") or []] == ["erlaubnis_frage"]


def test_echte_rueckfrage_kostet_keine_runde():
    a = _Skript([R("An welchem Tag und um wie viel Uhr?")])
    ev, aufrufe, p = _laufen(a, "trag mir noch ne extra fahrstunde nächste woche ein")
    assert a.hinweise == [] and p.korrekturen == 0


def test_messen_zaehlt_erlaubnis_fragen(tmp_path, capsys):
    """scripts/ehrlichkeit_messen.py: die Zahlen für die Doku (nur lesend)."""
    import importlib.util
    import json
    import os
    pfad = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "ehrlichkeit_messen.py")
    spec = importlib.util.spec_from_file_location("ehrlichkeit_messen", pfad)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    (tmp_path / "lauf").mkdir()
    (tmp_path / "lauf" / "ergebnis.json").write_text(json.dumps({"faelle": [{
        "id": "f09", "zuege": [
            {"sagt": F09_FRAGE, "antwort": F09_ANTWORT, "werkzeuge": []},
            {"sagt": "wie war dein tag", "antwort": "Gut. Soll ich dir was erzählen?",
             "werkzeuge": []}]}]}), encoding="utf-8")
    m.messen(m.zuege_pruefstand(str(tmp_path)), name="Probe")
    assert "Erlaubnis-Fragen 1 (Korrektur 1)" in capsys.readouterr().out


def test_melden_korrigiert_nicht():
    a = _Skript([R(F09_ANTWORT)])
    ev, aufrufe, p = _laufen(a, F09_FRAGE, modus="melden")
    assert a.hinweise == [] and aufrufe == []
    assert [b["art"] for b in (_schluss(ev) or {}).get("befunde") or []] == ["erlaubnis_frage"]
