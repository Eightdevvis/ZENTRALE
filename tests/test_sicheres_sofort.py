"""
„Sicheres sofort, Offenes fragen" (2026-10-10, core/ehrlichkeit.py
aufschub_befund, Prompt-Regel im Antwortverhalten der gross-Schiene).

Anlass: Prüfstand 10.10., f01. Sasha: „geige … fällt wegen der ferien jetzt
aus". Die KI: „Die Pause für die Geigenstunde trag ich erst ein, wenn ich
den Zeitraum sicher habe." — heute war sicher. Jetzt eine Korrekturrunde:
den sicheren Teil eintragen (add_calendar_pause nur mit von = heute), nur
nach dem Fehlenden fragen. Gefälschte Modelle, kein echter Aufruf.
"""
import pytest

import ai_config
import consolidation
import ehrlichkeit
import ehrlichkeit_erkennen as erkennen
import erlaubnis
import werkzeug_schleife

R = werkzeug_schleife.Runde
S = ehrlichkeit.Schritt
F01_SAGT = ("lösch nyam und geige ist nur donnerstags von 18:10-19 uhr. aber sie fällt "
            "wegen der ferien jetzt aus. weißt du bis wann die ferien hier gehen? bin in "
            "saarbrücken")
F01_AUFSCHUB = ("Erledigt: nyam gelöscht, Geige auf 18:10–19:00 gesetzt. Die Ferien konnte "
                "ich nicht nachlesen. Die Pause für die Geigenstunde trag ich erst ein, wenn "
                "ich den Zeitraum sicher habe.")
GESCHRIEBEN = [S("delete_calendar_entry", {"kennung": "#tc7fe"}, "ok", "GELÖSCHT"),
               S("edit_calendar_routine", {"kennung": "#r7a6f"}, "ok", "GEÄNDERT")]


# ── Erkennen ───────────────────────────────────────────────────────────

def test_f01_aufschub_trotz_anderer_kalender_aenderungen():
    b = ehrlichkeit.aufschub_befund(F01_AUFSCHUB, GESCHRIEBEN, F01_SAGT)
    assert b["art"] == "aufschub" and b["aktion"] == "pause"
    assert b["werkzeug"] == "add_calendar_pause"
    zeile = ehrlichkeit.hinweis([b])
    assert "Sasha hat das klar beauftragt" in zeile
    assert "add_calendar_pause nur mit von = heute" in zeile
    assert "frag nur nach dem, was wirklich fehlt" in zeile


def test_pause_eingetragen_dann_ruhe():
    pause = GESCHRIEBEN + [S("add_calendar_pause", {"von": "2026-10-08"}, "ok", "EINGETRAGEN")]
    assert ehrlichkeit.aufschub_befund(F01_AUFSCHUB, pause, F01_SAGT) is None


@pytest.mark.parametrize("satz", [
    "Die Pause trag ich erst ein, wenn ich das Ende sicher weiß.",
    "Den Termin lege ich erst an, sobald ich die Uhrzeit sicher habe.",
    "Das mach ich, sobald die Ferien feststehen.",
    "Mit der Pause warte ich noch ab.",
    "Die Vorlesung lass ich erst liegen, bis die Gruppe klar ist.",
])
def test_aufschub_formen(satz):
    assert erkennen.aufschuebe(satz), satz


@pytest.mark.parametrize("nutzer, antwort", [
    # Die Bedingung hängt an Sasha — eine echte Rückfrage.
    ("trag mir noch ne extra fahrstunde nächste woche ein",
     "Sobald du mir Tag und Uhrzeit sagst, trag ich sie ein."),
    ("trag mir noch ne extra fahrstunde nächste woche ein",
     "An welchem Tag und um wie viel Uhr?"),
    ("trag die übung ein", "Welche Übungsgruppe? Dann trag ich sie ein."),
    # Kein klarer Auftrag (Zustimmung zählt hier bewusst nicht).
    ("sure wieso denn nicht",
     "Vorlesung und Mathe-Ergänzungen lass ich auch erst liegen, bis die Gruppe klar ist."),
    ("wann ist analysis? nur nachschauen, noch nix eintragen",
     "Mo 10–12. Eintragen mach ich erst, wenn du es sagst."),
    # Frage, kein Aufschub.
    ("trag die pause ein", "Soll ich die Pause erst eintragen, wenn das Ende feststeht?"),
    # Zusage ohne Bedingung bleibt Sache der Zusagen.
    ("trag die pause ein", "Trag ich gleich ein."),
])
def test_echte_rueckfrage_loest_nicht_aus(nutzer, antwort):
    assert ehrlichkeit.aufschub_befund(antwort, [], nutzer) is None, antwort


def test_auftrag_aus_f01():
    assert erkennen.auftrag(F01_SAGT)
    assert erkennen.auftrag("geige fällt nächste woche aus")


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


def _laufen(runden, nutzer):
    aufrufe = []
    erg = {"delete_calendar_entry": "Kalendereintrag „nyam“ GELÖSCHT.",
           "edit_calendar_routine": "Routine „Geigenstunde“ GEÄNDERT (#r7a6f).",
           "add_calendar_pause": "Pause für „Geigenstunde“ am 08.10.2026 EINGETRAGEN."}

    def exec_(name, args):
        aufrufe.append((name, args))
        return erg.get(name, "ok")
    a = _Skript(runden)
    p = ehrlichkeit.Pruefer("an", nutzer_text=nutzer)
    ev = list(werkzeug_schleife.laufen(a, tutor_mode=False, active_exec=exec_,
                                       user_query="x", schiene="gross", pruefer=p))
    return ev, aufrufe, a, p


def test_aufschub_korrektur_dann_pause_ab_heute():
    ev, aufrufe, a, p = _laufen([
        R("", [("c1", "delete_calendar_entry", {"kennung": "#tc7fe"}),
               ("c2", "edit_calendar_routine", {"kennung": "#r7a6f", "time": "18:10"})]),
        R(F01_AUFSCHUB),
        R("", [("c3", "add_calendar_pause", {"label": "Geigenstunde", "von": "2026-10-08"})]),
        R("Geige fällt heute aus. Bis wann gehen die Ferien?"),
    ], F01_SAGT)
    assert [n for n, _a in aufrufe] == ["delete_calendar_entry", "edit_calendar_routine",
                                        "add_calendar_pause"]
    assert aufrufe[-1][1] == {"label": "Geigenstunde", "von": "2026-10-08"}
    assert len(a.hinweise) == 1 and "add_calendar_pause nur mit von = heute" in a.hinweise[0]
    texte = "".join(e for e in ev if isinstance(e, str))
    assert texte == "Geige fällt heute aus. Bis wann gehen die Ferien?"
    schluss = next(e["ehrlichkeit"] for e in ev if isinstance(e, dict) and "ehrlichkeit" in e)
    assert "✓ Pause eingetragen" in schluss["zeile"] and not schluss.get("warnungen")


def test_bleibt_sie_beim_aufschub_eine_runde_keine_warnung():
    nur = "Die Pause für die Geigenstunde trag ich erst ein, wenn ich den Zeitraum sicher habe."
    ev, aufrufe, a, p = _laufen([R(nur), R(nur)], F01_SAGT)
    assert len(a.hinweise) == 1 and p.korrekturen == 1
    schluss = next(e["ehrlichkeit"] for e in ev if isinstance(e, dict) and "ehrlichkeit" in e)
    assert not schluss.get("warnungen")


def test_echte_rueckfrage_im_lauf_kostet_keine_runde():
    ev, aufrufe, a, p = _laufen([R("Sobald du mir den Tag sagst, trag ich sie ein.")],
                                "trag mir noch ne extra fahrstunde nächste woche ein")
    assert a.hinweise == [] and aufrufe == []


def test_prompt_regel_gross_im_budget():
    from profil import gross, klein
    t = gross.system()
    assert "Aufträge setzt du sofort um, soweit sie sicher sind" in t
    assert len(t) < 5000
    assert "Aufträge setzt du sofort um" not in klein.system()      # klein bleibt
