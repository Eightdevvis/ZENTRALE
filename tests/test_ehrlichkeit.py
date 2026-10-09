"""
Die Live-Prüfer (core/ehrlichkeit.py, memory/ki/ehrlichkeit_live.md):
Tat gegen Wort, Kennungen, offene Zusagen — mit gefälschtem Modell, ohne
einen echten Aufruf. Alle Beispielsätze sind erfunden.
"""
import json

import pytest

import ai_backends
import ai_config
import cloud
import consolidation
import ehrlichkeit
import ehrlichkeit_erkennen as erkennen
import gespraeche
import graph
import kern
import ki_prompt
import werkzeug_register
import werkzeug_schleife
import zug
import zusagen
from test_cloud_loop import FakeBlock, FakeClient  # noqa: F401


# ── Erkennung ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("satz", [
    "Hab ich eingetragen: Zahnarzt am Dienstag um 10:30.",
    "Ich habe die Routine Chor angelegt.",
    "Der Termin ist jetzt gelöscht.",
    "Verschoben: Zahnarzt jetzt um 16:30.",
    "Erledigt — Parkour läuft jetzt 18:30–19:30.",
    "Steht jetzt drin.",
    "Habe die Pause eingetragen.",
])
def test_erledigt_saetze_werden_erkannt(satz):
    assert len(erkennen.taten(satz)) == 1


@pytest.mark.parametrize("satz", [
    "Soll ich das eintragen?",
    "Hab ich den Termin eingetragen?",
    "Ich habe nichts eingetragen.",
    "Das hab ich noch nicht gelöscht.",
    "Wenn du willst, hab ich das gleich angelegt.",
    "Der Zahnarzt ist am Dienstag eingetragen.",       # Zustand ohne „jetzt": gelesen
    "Das wäre dann eingetragen.",
    "Ich kann das eintragen.",
])
def test_keine_behauptung_kein_treffer(satz):
    assert erkennen.taten(satz) == []


@pytest.mark.parametrize("satz", [
    "Trag ich gleich ein.",
    "Mach ich, sobald du mir die Uhrzeit sagst.",
    "Schick mir die Zeiten, dann leg ich die Routine an.",
    "Ich werde den Termin morgen verschieben.",
    "Ich kümmere mich drum.",
    "Lass mich kurz nachsehen.",
])
def test_zusagen_werden_erkannt(satz):
    assert len(erkennen.versprechen(satz)) == 1


@pytest.mark.parametrize("satz", [
    "Soll ich das eintragen?",
    "Wenn du willst, trag ich das ein.",
    "Ich kann das gern eintragen.",
    "Das trag ich nicht ein.",
    "Hab ich eingetragen.",
    "Das sehe ich auch so.",
    "Zwei Wege: ich schau gleich im Netz, oder du schickst mir den Plan.",
    "Möchtest du, dass ich das notiere?",
])
def test_fragen_und_angebote_sind_keine_zusagen(satz):
    assert erkennen.versprechen(satz) == []


def test_bereich_aus_dem_satz():
    assert "kalender" in erkennen.taten("Hab den Termin verschoben.")[0].bereiche
    assert "notiz" in erkennen.taten("Hab ich in den Hausregeln notiert.")[0].bereiche


def test_kennungen_und_abkuerzung():
    assert erkennen.kennungen("Geige #r3f9c und #t47d2, nicht #rot oder abc#r1234") == ["r3f9c", "t47d2"]
    assert erkennen.unbekannte_kennungen("#r3f9 und #rdead", {"r3f9c"}) == ["rdead"]


def test_jedes_schreibende_werkzeug_hat_bereich_und_worte():
    for w in werkzeug_register.WERKZEUGE:
        if w.schreibt and w.gross:
            assert w.name in ehrlichkeit.BEREICH, w.name
            assert w.name in ehrlichkeit.WORTE, w.name


# ── Prüfen gegen das Protokoll ──────────────────────────────────────────

def _schritt(name, status="ok", text="", args=None):
    return ehrlichkeit.Schritt(name, args or {}, status, text)


def test_tat_braucht_schreibendes_werkzeug_des_bereichs():
    antwort = "Hab den Termin eingetragen."
    assert ehrlichkeit.befunde(antwort, [])[0]["art"] == "tat"
    assert ehrlichkeit.befunde(antwort, [_schritt("read_calendar")])  # Lesen reicht nicht
    assert ehrlichkeit.befunde(antwort, [_schritt("write_note")])     # falscher Bereich
    assert ehrlichkeit.befunde(antwort, [_schritt("add_calendar_entry", "fehlgeschlagen")])
    assert not ehrlichkeit.befunde(antwort, [_schritt("add_calendar_entry")])


def test_tat_von_frueher_darf_sich_auf_frueheres_stuetzen():
    antwort = "Den Termin hab ich vorhin schon eingetragen."
    assert ehrlichkeit.befunde(antwort, [])
    assert not ehrlichkeit.befunde(antwort, [], frueher=[_schritt("add_calendar_entry")])
    assert not ehrlichkeit.befunde(antwort, [_schritt("read_calendar")])


def test_erfundene_kennung():
    prot = [_schritt("read_calendar", text="#t47d2 10:30 Zahnarzt")]
    assert not ehrlichkeit.befunde("Zahnarzt #t47d2.", prot)
    b = ehrlichkeit.befunde("Zahnarzt #t9999.", prot)
    assert b == [{"art": "kennung", "kennung": "#t9999"}]
    assert not ehrlichkeit.befunde("Zahnarzt #t9999.", prot, bekannt_text="du sagtest #t9999")


def test_erledigt_zeile_nur_aus_dem_protokoll():
    liste = ehrlichkeit.erledigt_liste([
        _schritt("read_calendar"),
        _schritt("add_calendar_entry", args={"label": "Zahnarzt"}),
        _schritt("edit_calendar_routine", "fehlgeschlagen", args={"label": "Parkour"}),
        _schritt("delete_calendar_entry", "abgelehnt", args={"label": "Drive"})])
    zeile = ehrlichkeit.erledigt_zeile(liste)
    assert zeile == ("✓ Termin eingetragen: Zahnarzt · ✗ Routine ändern ging nicht: Parkour"
                     " · – Löschen: von dir abgelehnt: Drive")


# ── Die Schleife: Korrekturrunde ────────────────────────────────────────

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
        self.hinweise.append((r.text, text))


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    import erlaubnis
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    # Kein Knopf wartet auf Sasha (sonst blockiert der Zug bis zur Zeitgrenze).
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})


def _laufen(adapter, exec_, modus="an"):
    p = ehrlichkeit.Pruefer(modus)
    return list(werkzeug_schleife.laufen(adapter, tutor_mode=False, active_exec=exec_,
                                         user_query="x", schiene="gross", pruefer=p))


def test_falsche_erledigt_behauptung_loest_eine_korrekturrunde_aus():
    a = _Skript([werkzeug_schleife.Runde("Hab den Termin eingetragen."),
                 werkzeug_schleife.Runde("Eingetragen hab ich noch nichts — wann genau?")])
    ev = _laufen(a, lambda n, x: "ok")
    texte = [e for e in ev if isinstance(e, str)]
    assert texte == ["Eingetragen hab ich noch nichts — wann genau?"]   # die erste sah Sasha nie
    assert len(a.hinweise) == 1 and "Hab den Termin eingetragen." in a.hinweise[0][1]
    assert "<pruefung_automatisch>" in a.hinweise[0][1]
    schluss = ev[-1]["ehrlichkeit"]
    assert schluss["korrigiert"] is True and "befunde" not in schluss


def test_auch_die_korrigierte_antwort_wird_geprueft():
    # Bis 2026-10-09 gab es nur EINE Korrekturrunde; die zweite Antwort ging
    # ungeprüft raus. Jetzt wird jede neu geprüft (mehr: test_ehrlichkeit_runden).
    a = _Skript([werkzeug_schleife.Runde("Hab den Termin eingetragen."),
                 werkzeug_schleife.Runde("Hab den Termin wirklich eingetragen."),
                 werkzeug_schleife.Runde("Eingetragen ist noch nichts.")])
    ev = _laufen(a, lambda n, x: "ok")
    assert [e for e in ev if isinstance(e, str)] == ["Eingetragen ist noch nichts."]
    assert len(a.hinweise) == 2


def test_belegte_behauptung_geht_direkt_raus_mit_erledigt_zeile():
    a = _Skript([werkzeug_schleife.Runde("", [("c1", "add_calendar_entry", {"label": "Zahnarzt"})]),
                 werkzeug_schleife.Runde("Hab den Termin eingetragen.")])
    ev = _laufen(a, lambda n, x: "Steht jetzt: #t47d2 Zahnarzt")
    assert a.hinweise == []
    assert ev[-1]["ehrlichkeit"]["zeile"] == "✓ Termin eingetragen: Zahnarzt"


def test_melden_korrigiert_nicht():
    a = _Skript([werkzeug_schleife.Runde("Hab den Termin eingetragen.")])
    ev = _laufen(a, lambda n, x: "ok", modus="melden")
    assert a.hinweise == [] and ev[-1]["ehrlichkeit"]["befunde"]


def test_keine_korrektur_in_der_letzten_runde(monkeypatch):
    monkeypatch.setattr(ai_backends, "runden_grenze", lambda m: 1)
    a = _Skript([werkzeug_schleife.Runde("Hab den Termin eingetragen.")])
    ev = _laufen(a, lambda n, x: "ok")
    assert a.hinweise == [] and "Hab den Termin eingetragen." in ev


def test_rundengrenze_liefert_trotzdem_die_erledigt_zeile(monkeypatch):
    monkeypatch.setattr(ai_backends, "runden_grenze", lambda m: 1)
    a = _Skript([werkzeug_schleife.Runde("", [("c1", "add_calendar_entry", {"label": "Geige"})])])
    ev = _laufen(a, lambda n, x: "ok")
    assert ev[-2] == {"ehrlichkeit": {"erledigt": [{"werkzeug": "add_calendar_entry",
                                                    "wen": "Geige", "status": "ok"}],
                                      "zeile": "✓ Termin eingetragen: Geige"}}
    assert "fehler" in ev[-1]


def test_klein_und_tutor_ohne_pruefer(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "an"})
    assert ehrlichkeit.pruefer_fuer([], schiene="klein", tutor_mode=False) is None
    assert ehrlichkeit.pruefer_fuer([], schiene="gross", tutor_mode=True) is None
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "aus"})
    assert ehrlichkeit.pruefer_fuer([], schiene="gross", tutor_mode=False) is None
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "quatsch"})
    assert ehrlichkeit.modus() == ehrlichkeit.STANDARD


# ── „Nicht da" (2026-10-09, Gespräch 20261009-155510) ──────────────────

@pytest.mark.parametrize("satz", [
    "Ich seh in der Liste keine \"chefkoch\"-Datei oder ZIP – da ist jede Menge Code, "
    "aber kein Chefkoch-Skill-Zip.",
    "Die Datei gibt es nicht.",
    "In Input/ liegt keine Zip.",
    "Eine Datei namens rezepte.md finde ich nicht.",
    "Im Ordner ist keine PDF vorhanden.",
])
def test_nicht_da_wird_erkannt(satz):
    assert erkennen.nicht_da(satz), satz


@pytest.mark.parametrize("satz", [
    "Liegt das wirklich schon im richtigen Ordner?",
    "Falls die Datei nicht da ist, sag Bescheid.",
    "Den Termin gibt es nicht.",
    "Ich habe die Datei gelesen.",
    "Die Zip liegt in Input/.",
])
def test_kein_nicht_da(satz):
    assert not erkennen.nicht_da(satz), satz


_GEKUERZT = ("Verfügbare Dateien:\n  … [4700 weitere unter ~/codicus nicht gelistet — "
             "read_file erreicht sie trotzdem]")
_CHEFKOCH = ("Ich seh in der Liste keine \"chefkoch\"-Datei oder ZIP – da ist jede Menge "
             "ZENTRALE-Code, aber kein Chefkoch-Skill-Zip.")


def test_chefkoch_fall_gekuerzte_liste_nicht_da_korrekturrunde():
    """Genau der Fall vom 09.10.: Liste gekappt → „nicht da" → EINE
    Korrekturrunde; danach sucht die KI und findet die Zip."""
    import zug_ablauf
    a = _Skript([werkzeug_schleife.Runde("", [("c1", "list_files", {})]),
                 werkzeug_schleife.Runde(_CHEFKOCH),
                 werkzeug_schleife.Runde("", [("c2", "find_files", {"muster": "*chefkoch*"})]),
                 werkzeug_schleife.Runde("Gefunden: Input/Chefkoch ai-v1.zip.")])
    ergebnisse = {"list_files": _GEKUERZT,
                  "find_files": "Suche vollständig: 1 Treffer — durchsucht: Input/, Output/ "
                                "(3 Dateien).\n  Input/Chefkoch ai-v1.zip  (12 KB)"}
    m = zug_ablauf.beginnen()
    try:
        zug_ablauf.system("fest")
        ev = _laufen(a, lambda n, x: ergebnisse[n])
        ablauf = zug_ablauf.abschliessen("x")
    finally:
        zug_ablauf.beenden(m)
    assert [e for e in ev if isinstance(e, str)] == ["Gefunden: Input/Chefkoch ai-v1.zip."]
    assert len(a.hinweise) == 1
    hinweis = a.hinweise[0][1]
    assert "‚nicht da'" in hinweis and "find_files/search_files" in hinweis
    # Im Ablauf-Protokoll (/trace) steht der Befund im Eintrag „pruefung".
    pruefung = [e for e in ablauf if e["art"] == "pruefung"]
    assert pruefung and pruefung[0]["befunde"][0]["art"] == "nicht_da"
    assert "Chefkoch-Skill-Zip" in zug_ablauf.inhalt(pruefung[0])


def test_nicht_da_nach_vollstaendiger_leerer_suche_geht_durch():
    a = _Skript([werkzeug_schleife.Runde("", [("c1", "find_files", {"muster": "*chefkoch*"})]),
                 werkzeug_schleife.Runde("In Input/ liegt keine Chefkoch-Zip.")])
    leer = "[ergebnis: ok]\nSuche vollständig: 0 Treffer — durchsucht: Input/, Output/ (3 Dateien)."
    ev = _laufen(a, lambda n, x: leer)
    assert a.hinweise == []
    assert "In Input/ liegt keine Chefkoch-Zip." in ev


def test_nicht_da_nach_unvollstaendiger_suche_wird_korrigiert():
    a = _Skript([werkzeug_schleife.Runde("", [("c1", "search_files", {"text": "Rezept"})]),
                 werkzeug_schleife.Runde("Eine Datei mit Rezept gibt es nicht."),
                 werkzeug_schleife.Runde("Das weiß ich nicht sicher.")])
    halb = ("Suche NICHT vollständig: 2 Dateien über 2 MB oder unlesbar, nicht durchsucht — "
            "durchsucht: Input/, Output/ (9 Dateien). 0 Treffer im Rest.")
    ev = _laufen(a, lambda n, x: halb)
    assert len(a.hinweise) == 1
    assert [e for e in ev if isinstance(e, str)] == ["Das weiß ich nicht sicher."]


def test_read_file_nicht_gefunden_belegt():
    assert ehrlichkeit.suche_belegt([_schritt("read_file", text="[Datei nicht gefunden: x.md]")])
    assert not ehrlichkeit.suche_belegt([_schritt("list_files", text=_GEKUERZT)])


# ── Der echte Anthropic-Adapter: die Korrektur als user-Nachricht ───────

def test_anthropic_adapter_haengt_hinweis_als_user_nachricht_an(monkeypatch):
    monkeypatch.setattr(cloud.graph, "context_for_query", lambda *a, **k: "")
    monkeypatch.setattr(graph, "einmal_seeden", lambda *a, **k: None)
    monkeypatch.setattr(ki_prompt, "_imprint_prompt", lambda: "")
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    c = FakeClient([
        {"text": ["Hab den Termin eingetragen."],
         "content": [FakeBlock("text", text="Hab den Termin eingetragen.")]},
        {"text": ["Noch nichts eingetragen — welche Uhrzeit?"],
         "content": [FakeBlock("text", text="Noch nichts eingetragen — welche Uhrzeit?")]}])
    monkeypatch.setattr(cloud, "_get_client", lambda: c)
    ev = list(cloud.chat_stream([{"role": "user", "content": "trag zahnarzt ein"}]))
    assert "Noch nichts eingetragen — welche Uhrzeit?" in ev
    zweite = c.calls[1]["messages"]
    assert zweite[-2]["role"] == "assistant"
    assert zweite[-1]["role"] == "user"
    assert "<pruefung_automatisch>" in zweite[-1]["content"][0]["text"]


# ── Zusagen über mehrere Züge, über die Route ──────────────────────────

@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "an"})
    return app.test_client()


def _events(r):
    return [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
            if z.startswith("data:")]


def _zug(client, monkeypatch, nachricht, runden, gesehen):
    """Ein Zug über /api/chat mit einem Skript-Modell; `gesehen` sammelt den
    Kontext-Umschlag, wie cloud._volatile_text ihn für diesen Zug baut."""
    def gen(history, **k):
        gesehen.append(cloud._volatile_text("", False, False))
        p = ehrlichkeit.pruefer_fuer(history, schiene="gross", tutor_mode=False)
        yield from werkzeug_schleife.laufen(
            _Skript(runden), tutor_mode=False, user_query=nachricht, schiene="gross",
            active_exec=lambda n, a: "[ergebnis: ok]\nSteht jetzt: #t1234 Zahnarzt",
            pruefer=p)

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    monkeypatch.setattr(ki_prompt, "_alarm_prompt", lambda: "")
    return _events(client.post("/api/chat", json={"message": nachricht}))


def test_zusage_in_zug1_hinweis_in_zug2_erledigt_nach_werkzeug(client, monkeypatch):
    gesehen = []
    ev = _zug(client, monkeypatch, "zahnarzt dienstag",
              [werkzeug_schleife.Runde("Sag mir die Uhrzeit, dann trag ich ihn ein.")], gesehen)
    gid = gespraeche.aktiv()
    assert [z["satz"] for z in zusagen.offen(gid)] == ["Sag mir die Uhrzeit, dann trag ich ihn ein."]
    p = next(e["ehrlichkeit"] for e in ev if "ehrlichkeit" in e)
    assert p["offen"] == ["Sag mir die Uhrzeit, dann trag ich ihn ein."]
    antwort = gespraeche.nachrichten(gid)[-1]
    assert antwort["offen"] == p["offen"] and "offen" not in antwort["text"]

    # Zug 2: der Hinweis steht im Umschlag (nicht im festen Kopf).
    _zug(client, monkeypatch, "10:30",
         [werkzeug_schleife.Runde("", [("c1", "add_calendar_entry", {"label": "Zahnarzt"})]),
          werkzeug_schleife.Runde("Eingetragen: Zahnarzt #t1234.")], gesehen)
    assert "Noch offen von dir zugesagt" in gesehen[1] and "(Zug 1)" in gesehen[1]
    assert "<kontext_automatisch>" in gesehen[1]
    assert zusagen.offen(gid) == []
    antwort = gespraeche.nachrichten(gid)[-1]
    assert antwort["erledigt"]["zeile"] == "✓ Termin eingetragen: Zahnarzt"
    h = client.get("/api/chat/history").get_json()
    assert h[-1]["erledigt"]["zeile"] == "✓ Termin eingetragen: Zahnarzt"
    assert "offen" not in h[-1]

    # Zug 3: nichts mehr offen → kein Hinweis.
    _zug(client, monkeypatch, "danke", [werkzeug_schleife.Runde("Gern.")], gesehen)
    assert "Noch offen" not in gesehen[2]


def test_ablehnung_und_verfall(client, monkeypatch):
    gesehen = []
    _zug(client, monkeypatch, "a", [werkzeug_schleife.Runde("Trag ich gleich ein.")], gesehen)
    gid = gespraeche.aktiv()
    _zug(client, monkeypatch, "nein, lass es", [werkzeug_schleife.Runde("Okay.")], gesehen)
    assert zusagen.offen(gid) == []

    monkeypatch.setattr(ehrlichkeit, "verfall_zuege", lambda: 2)
    _zug(client, monkeypatch, "b", [werkzeug_schleife.Runde("Leg ich nachher an.")], gesehen)
    _zug(client, monkeypatch, "c", [werkzeug_schleife.Runde("Hm.")], gesehen)
    assert len(zusagen.offen(gid)) == 1
    _zug(client, monkeypatch, "d", [werkzeug_schleife.Runde("Hm.")], gesehen)
    assert zusagen.offen(gid) == []


def test_zusagen_eine_datei_pro_rechner(monkeypatch):
    gid = gespraeche.neu("t")
    zusagen.hinzufuegen(gid, erkennen.versprechen("Trag ich gleich ein."), 1)
    monkeypatch.setattr(gespraeche, "knoten", lambda: "anderer")
    (z,) = zusagen.offen(gid)
    zusagen.erledigen(gid, z["id"], "werkzeug", 2)      # der andere Rechner hakt ab
    import os
    namen = sorted(n for n in os.listdir(gespraeche._ordner(gid)) if n.startswith("zusagen-"))
    assert len(namen) == 2
    assert zusagen.offen(gid) == []


def test_tui_zeigt_erledigt_und_offen_dezent():
    from tui.ansichten.chat_gespraeche import verlauf_aus
    from tui.ansichten import verlauf
    h = [{"role": "user", "content": "x"},
         {"role": "assistant", "content": "a", "offen": ["Trag ich gleich ein."]},
         {"role": "user", "content": "y"},
         {"role": "assistant", "content": "b", "erledigt": {"zeile": "✓ Termin eingetragen: Z"},
          "offen": ["Leg ich an."]}]
    log = verlauf_aus(h)
    assert ("erledigt", "✓ Termin eingetragen: Z") in log
    assert [t for r, t in log if r == "offen"] == ["offen: Leg ich an."]   # nur die neueste
    zeilen = verlauf.verlauf_zeilen(log, 40)
    stile = {s for z in zeilen for _t, s, _z in z if _t.startswith(("✓", "offen"))}
    assert stile == {"leise"}
