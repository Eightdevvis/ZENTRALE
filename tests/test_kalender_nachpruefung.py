"""Kalender: nur übernehmen, was Sasha gesagt hat (2026-10-22).

Anlass: Gespräch 20261022-111358-dd6127, qwen-plus im Budget-Rückfall. Sasha
gab vier Sprechstunden mit Wochentag und Uhrzeit, ohne Zeitraum. qwen machte
drei Fehler, jeder hier als Regressionstest — dazu Gegenproben ohne Fehlalarm:
  1. „Sprechstunde Jonas Schömer (Mo)" an einer Serie BYDAY=WE
     → Adapter bricht ab (K-TITEL-WOCHENTAG), nichts gespeichert;
  2. von=2026-10-26, bis=2026-12-20 erfunden → Befund „grundlos" (eine Runde,
     danach Warnung);
  3. „alle mit 'uncommitted'", ohne dass ein layer gesetzt war → Befund
     „behauptung".
Keine Kosten: kein Modell, nur der Prüfer und der Kalender-Speicher.
"""
import re
from datetime import date, datetime, timedelta

import pytest

import ehrlichkeit
import ehrlichkeit_kalender as ek
import fehlercodes
import kalender
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer an
import profil
import titel_wochentag
import uhr
import werkzeug_befund
import werkzeug_register

# Der Tag des Gesprächs: Donnerstag, 22.10.2026 (Regel 8: nie das echte heute).
TAG = datetime(2026, 10, 22, 13, 14)

SASHA = ("hier leg mal die folgenden termine für die woche regelmäßig uncommitted an "
         "Zusätzlich bieten die Hausaufgaben-Übungsleiter eine wöchentliche Sprechstunde im "
         "Lernraum der Studierenden (E12) in E2 6 an. Die Termine für die Sprechstunden sind:\n"
         "Montag 13:00-14:30 Uhr Jannik Zenker\n"
         "Dienstag 16:15 - 17:45 Uhr Sebastian Mathieu\n"
         "Mittwoch 16:15 - 17:15 Uhr: Jonas Schömer\n"
         "Freitag 14:00-15:00: Jonas Schömer")

QWEN = ("Vier Sprechstunden sind jetzt als unverbindliche Routinen eingetragen — alle mit "
        "'uncommitted' (kein festes Commitment, nur als Option):\n\n"
        "• Mo 13:00–14:30: Jannik Zenker (E2 6, Lernraum)\n"
        "• Di 16:15–17:45: Sebastian Mathieu (E2 6, Lernraum)\n"
        "• Mi 16:15–17:15: Jonas Schömer (E2 6, Lernraum)\n"
        "• Fr 14:00–15:00: Jonas Schömer (E2 6, Lernraum)")

_SERIEN = (("Sprechstunde Jannik Zenker", "MO", "13:00", "14:30", "mo"),
           ("Sprechstunde Sebastian Mathieu", "TU", "16:15", "17:45", "di"),
           ("Sprechstunde Jonas Schömer", "WE", "16:15", "17:15", "mi"),
           ("Sprechstunde Jonas Schömer", "FR", "14:00", "15:00", "fr"))


def _aufrufe(von="2026-10-26", bis="2026-12-20", layer=None):
    """Die vier add_calendar_routine-Schritte wie im Gespräch (ok)."""
    raus = []
    for label, tag, t, e, kurz in _SERIEN:
        args = {"label": label, "rrule": f"FREQ=WEEKLY;BYDAY={tag}", "time": t, "ende": e,
                "von": von, "bis": bis, "kategorie": "uni", "typ": "normal",
                "ort": "E2 6, Lernraum der Studierenden (E12)"}
        if layer:
            args["layer"] = layer
        ebene = " als vielleicht (uncommitted)" if layer == "uncommitted" else ""
        text = (f"[ergebnis: ok]\nRoutine „{label}“ wöchentlich {kurz} {t}–{e} @ E2 6 vom "
                f"{von[8:]}.{von[5:7]}.{von[:4]} bis {bis[8:]}.{bis[5:7]}.{bis[:4]} "
                f"EINGETRAGEN (#r{len(raus)}a1){ebene}.")
        raus.append(ehrlichkeit.Schritt("add_calendar_routine", args, "ok", text))
    return raus


def _lesen():
    return ehrlichkeit.Schritt("read_calendar", {"zeitraum": "diese_woche", "suche": "Sprechstunde"},
                               "ok", "[ergebnis: ok]\nKalender 22.10.2026 bis 25.10.2026: "
                                     "Keine Einträge mit 'Sprechstunde' in diesem Zeitraum.")


def _arten(befunde, art):
    return [b for b in befunde if b["art"] == art]


# ── Fehler 1: Wochentag im Titel ────────────────────────────────────────

def test_titel_wochentag_erkennt_nur_sicheres():
    assert titel_wochentag.im_titel("Sprechstunde Jonas Schömer (Mo)") == {0}
    assert titel_wochentag.im_titel("Kurs [Mo, Mi]") == {0, 2}
    assert titel_wochentag.im_titel("Training mittwochs") == {2}
    assert titel_wochentag.im_titel("Sprechstunde – Fr") == {4}
    for titel in ("To Do", "So geht's los", "Fr. Meier anrufen", "Montagsrunde",
                  "Sprechstunde Jonas Schömer", "Lernraum (E2 6)", "Mittagessen"):
        assert titel_wochentag.im_titel(titel) == set(), titel
    assert titel_wochentag.aus_regel("FREQ=WEEKLY;BYDAY=WE") == {2}
    assert titel_wochentag.aus_regel("FREQ=DAILY") == set(range(7))
    assert titel_wochentag.aus_regel("FREQ=MONTHLY;BYMONTHDAY=1") is None


@pytest.fixture
def gross():
    werkzeug_register.erzeugte_einsetzen(True)
    marke = werkzeug_befund.schiene_setzen("gross")
    yield
    werkzeug_befund.schiene_zuruecksetzen(marke)


def _tun(name, **args):
    return ki_werkzeuge._verteilen(name, args)


def _naechster(wochentag: int) -> date:
    heute = date.today()
    return heute + timedelta(days=(wochentag - heute.weekday()) % 7 + 7)


@pytest.mark.kalender_beide
def test_mittwochs_serie_mit_mo_im_titel_bricht_ab(gross):
    """Fehler 1: „(Mo)" an BYDAY=WE — nichts gespeichert, Code mit „Was tun"."""
    vorher = kalender._load_raw()
    von = date.today().isoformat()
    bis = (date.today() + timedelta(days=60)).isoformat()
    r = _tun("add_calendar_routine", label="Sprechstunde Jonas Schömer (Mo)",
             rrule="FREQ=WEEKLY;BYDAY=WE", time="16:15", ende="17:15", von=von, bis=bis,
             kategorie="uni")
    assert r.status == "fehlgeschlagen" and "K-TITEL-WOCHENTAG" in r, r
    assert "nennt mo, findet mi statt" in r and "ohne Wochentag" in r
    assert kalender._load_raw() == vorher
    assert fehlercodes.bekannt("K-TITEL-WOCHENTAG")


@pytest.mark.kalender_beide
def test_titel_ohne_oder_mit_passendem_wochentag_geht_durch(gross):
    """Gegenprobe: ohne Wochentag, oder „(Fr)" an einer Freitags-Serie (wie
    Sashas eigene „Chemie (Mo)") — kein Abbruch."""
    von = date.today().isoformat()
    bis = (date.today() + timedelta(days=60)).isoformat()
    for label, regel in (("Sprechstunde Jonas Schömer", "FREQ=WEEKLY;BYDAY=WE"),
                         ("Sprechstunde Jonas Schömer (Fr)", "FREQ=WEEKLY;BYDAY=FR"),
                         ("Montagsrunde", "FREQ=WEEKLY;BYDAY=TH")):
        r = _tun("add_calendar_routine", label=label, rrule=regel, time="16:15",
                 ende="17:15", von=von, bis=bis, kategorie="keine")
        assert r.status == "ok", (label, r)


@pytest.mark.kalender_beide
def test_einmal_termin_und_umbenennen_pruefen_den_wochentag(gross):
    mi = _naechster(2)
    r = _tun("add_calendar_entry", day=mi.isoformat(), label="Sprechstunde (Mo)",
             time="16:15", ende="17:15", kategorie="keine")
    assert "K-TITEL-WOCHENTAG" in r, r
    r = _tun("add_calendar_entry", day=mi.isoformat(), label="Sprechstunde (Mi)",
             time="16:15", ende="17:15", kategorie="keine")
    assert r.status == "ok", r
    k = re.findall(r"#(t[0-9a-f]+)", r)[0]
    r = _tun("edit_calendar_entry", kennung=k, neuer_titel="Sprechstunde (Fr)")
    assert "K-TITEL-WOCHENTAG" in r, r


# ── Fehler 2: Zeitraum ohne Grundlage ───────────────────────────────────

def test_erfundener_zeitraum_wird_gefunden():
    """Fehler 2: von 26.10. liegt noch in „ab jetzt" (der nächste Termin), bis
    20.12.2026 hat Sasha nie genannt."""
    with uhr.gestellt(TAG):
        b = _arten(ek.befunde(QWEN, [_lesen(), *_aufrufe()], nutzer_text=SASHA), "grundlos")
    assert [x["feld"] for x in b] == ["bis"] and len(b[0]["wen"]) == 4
    assert "20.12.2026" in b[0]["satz"] and "angenommen" in b[0]["zeile"]
    assert b[0]["warnung"].startswith("⚠ Angenommen")


def test_von_weit_weg_ohne_grundlage_auch():
    with uhr.gestellt(TAG):
        b = ek.befunde("Eingetragen.", _aufrufe(von="2026-11-16")[:1], nutzer_text=SASHA)
    assert {x["feld"] for x in _arten(b, "grundlos")} == {"von", "bis"}


@pytest.mark.parametrize("sasha", [
    "die sprechstunde mittwochs 16:15-17:15 vom 26.10. bis 20.12. eintragen",
    "mittwochs 16:15-17:15 sprechstunde, ab nächster woche bis zum 20. dezember",
    "mittwochs 16:15-17:15 sprechstunde, ab nächster Woche bis Semesterende",
    "mittwochs 16:15 bis 17:15 sprechstunde, die nächsten zwei monate",
])
def test_genannter_oder_ungefaehrer_zeitraum_kein_befund(sasha):
    """Gegenprobe: von/bis, die Sasha wirklich nennt — als Datum oder ungefähr
    („ab nächster Woche", „bis Semesterende") — sind kein Befund."""
    schritt = [s for s in _aufrufe() if "Schömer" in s.args["label"]][0]
    with uhr.gestellt(TAG):
        b = ek.befunde("Eingetragen: Sprechstunde mittwochs 16:15–17:15.", [schritt],
                       nutzer_text=sasha)
    assert not b, b


def test_zeitraum_aus_dem_gespraech_oder_einer_suche_ist_belegt():
    schritt = _aufrufe()[0]
    with uhr.gestellt(TAG):
        assert not _arten(ek.befunde("Eingetragen.", [schritt], nutzer_text="ja mach",
                                     grundlage="Soll ich sie montags 13:00-14:30 bis 20.12.2026 eintragen?"),
                          "grundlos")
        netz = ehrlichkeit.Schritt("fetch_url", {"url": "x"}, "ok",
                                   "Vorlesungszeit: 12.10.2026 – 20.12.2026")
        assert not _arten(ek.befunde("Eingetragen.", [netz, schritt],
                                     nutzer_text="trag die sprechstunde montags 13-14:30 ein"), "grundlos")


def test_ende_ohne_grundlage_aber_nicht_bei_dauer():
    def termin(ende):
        return ehrlichkeit.Schritt("add_calendar_entry", {"day": "2026-10-28", "label": "Kino",
                                                          "time": "19:00", "ende": ende}, "ok",
                                   "[ergebnis: ok]\nKalendereintrag „Kino“ EINGETRAGEN (#t1).")
    with uhr.gestellt(TAG):
        assert _arten(ek.befunde("Eingetragen.", [termin("21:00")],
                                 nutzer_text="kino am mittwoch um 19 uhr"), "grundlos")
        for sasha in ("kino am mittwoch 19-21 uhr", "kino mittwoch um 7, so zwei stunden",
                      "kino mittwoch 19:00 bis 21:00", "kino mittwoch um sieben bis neun"):
            ende = "21:00"
            assert not _arten(ek.befunde("Eingetragen.", [termin(ende)], nutzer_text=sasha),
                              "grundlos"), sasha


# ── Fehler 3: Behauptung gegen die echten Aufrufe ───────────────────────

def test_uncommitted_behauptet_ohne_layer():
    """Fehler 3: „alle mit 'uncommitted'", kein Aufruf hatte layer."""
    with uhr.gestellt(TAG):
        b = _arten(ek.befunde(QWEN, [_lesen(), *_aufrufe()], nutzer_text=SASHA), "behauptung")
    assert b and "uncommitted" in b[0]["was"]
    assert "set_calendar_layer" in b[0]["zeile"]


def test_uncommitted_wirklich_gesetzt_kein_befund():
    with uhr.gestellt(TAG):
        b = ek.befunde(QWEN, [_lesen(), *_aufrufe(layer="uncommitted")], nutzer_text=SASHA)
    assert not _arten(b, "behauptung"), b


def test_frage_oder_verneinung_ist_keine_behauptung():
    with uhr.gestellt(TAG):
        for antwort in ("Eingetragen. Soll ich sie als vielleicht (uncommitted) markieren?",
                        "Eingetragen, aber nicht als uncommitted — das Feld fehlte mir.",
                        "Vier Sprechstunden eingetragen, Mi 16:15–17:15."):
            assert not _arten(ek.befunde(antwort, _aufrufe(), nutzer_text=SASHA),
                              "behauptung"), antwort


def test_deadline_anzahl_und_zeit_gegen_die_aufrufe():
    with uhr.gestellt(TAG):
        zwei = _aufrufe()[:2]
        assert _arten(ek.befunde("Alle vier Sprechstunden sind eingetragen.", zwei,
                                 nutzer_text=SASHA), "behauptung")
        assert _arten(ek.befunde("Beide als Deadline eingetragen.", zwei,
                                 nutzer_text=SASHA), "behauptung")
        assert _arten(ek.befunde("Eingetragen: Mo 13:00–15:00.", zwei, nutzer_text=SASHA),
                      "behauptung")
        assert not _arten(ek.befunde("Zwei Sprechstunden eingetragen: Mo 13:00–14:30.", zwei,
                                     nutzer_text=SASHA), "behauptung")


def test_ohne_kalender_schreiben_nichts():
    assert ek.befunde(QWEN, [_lesen()], nutzer_text=SASHA) == []


# ── im Prüfer: Runden und Warnungen ─────────────────────────────────────

def test_pruefer_korrigiert_und_warnt():
    """Das ganze Gespräch durch den Prüfer der Schiene: Runde 1 nennt beide
    Befunde; ist die Behauptung weg, aber das Ende nicht genannt, gibt es
    keine zweite Runde für „grundlos", nur die Warnung."""
    with uhr.gestellt(TAG):
        p = ehrlichkeit.Pruefer(ehrlichkeit.AN, nutzer_text=SASHA, bekannt_text=SASHA)
        for s in [_lesen(), *_aufrufe()]:
            p.werkzeug(s.name, s.args, s.text)
        hinweis = p.nach_antwort(QWEN, letzte_runde=False)
        assert hinweis and "angenommen" in hinweis and "uncommitted" in hinweis
        neu = "Vier Sprechstunden sind fest eingetragen: Mo 13:00–14:30, Mi 16:15–17:15."
        assert p.nach_antwort(neu, letzte_runde=False) is None
        warn = p.abschluss(neu)["ehrlichkeit"]["warnungen"]
    assert any("Angenommen" in w and "20.12.2026" in w for w in warn)
    assert not any("uncommitted" in w for w in warn)


def test_pruefer_ohne_warnung_wenn_die_antwort_das_ende_nennt():
    with uhr.gestellt(TAG):
        p = ehrlichkeit.Pruefer(ehrlichkeit.AN, nutzer_text=SASHA, bekannt_text=SASHA)
        for s in _aufrufe():
            p.werkzeug(s.name, s.args, s.text)
        antwort = ("Vier Sprechstunden eingetragen, vorläufig bis 20.12.2026 — das Ende habe "
                   "ich angenommen. Bis wann gehen sie wirklich?")
        p.nach_antwort(antwort, letzte_runde=False)
        schluss = p.abschluss(antwort)["ehrlichkeit"]
    assert not schluss.get("warnungen")


# ── Werkzeug-Texte, auch für qwen ───────────────────────────────────────

def test_werkzeug_texte_sagen_nur_was_sasha_gesagt_hat(monkeypatch):
    """Gross und qwen (nach dem Zuschnitt) sehen die neue Regel im Text und
    die Titel-Regel im Feld."""
    import json
    from profil import gross as g
    monkeypatch.setenv("ZENTRALE_MODELL_PROFILE", json.dumps({"qwen-*": "qwen"}))
    werkzeug_register.erzeugte_einsetzen(True)
    qwen = profil.fuer_backend("cloud", modell="qwen-plus")
    for tools in (g.TOOLS, qwen.TOOLS):
        fn = {t["function"]["name"]: t["function"] for t in tools}
        for name in ("add_calendar_entry", "add_calendar_routine"):
            assert "erfinden" in fn[name]["description"], name
            label = fn[name]["parameters"]["properties"]["label"]["description"]
            assert "ohne Wochentag" in label, name
        bis = fn["add_calendar_routine"]["parameters"]["properties"]["bis"]["description"]
        assert "nie raten" in bis
    assert "kein Wochentag im Titel" in qwen.system("")
