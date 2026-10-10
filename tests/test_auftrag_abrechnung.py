"""
Auftrags-Abrechnung und „nicht gefunden nach Stichwortsuche" (2026-10-10,
memory/ki/ehrlichkeit_live.md). Anlass: Prüfstand f01k mit Haiku — Sasha
„lösch nyam und geige ist nur donnerstags … aber sie fällt wegen der ferien
jetzt aus", die KI löschte und änderte, die Pause fiel still weg; f10 —
„Ich hab die uni-Einträge nicht gefunden" nach read_calendar(suche="uni").

Gefälschte Modelle, kein echter Aufruf.
"""
import json

import pytest

import ai_backends
import ai_config
import auftrag_abrechnung as ab
import cloud
import consolidation
import ehrlichkeit
import erlaubnis
import gespraeche
import kern
import ki_prompt
import selbstauskunft
import werkzeug_schleife
import zug_ablauf
from test_selbstauskunft import _Skript

R = werkzeug_schleife.Runde

F01K = ("lösch nyam und geige ist nur donnerstags von 18:10-19 uhr. aber sie fällt wegen "
        "der ferien jetzt aus. weißt du bis wann die ferien hier gehen? bin in saarbrücken")
HAIKU = ("✓ Erledigt: nyam gelöscht, die zweite Geigenstunde entfernt, die erste auf "
         "18:10–19:00 angepasst.\n\nZu den Herbstferien: ich komme gerade nicht an die "
         "Seite. Brauchst du die Info akut, um die Pause einzutragen?")
LEER = "Kalender 09.10.2026 bis 06.01.2027 (gefiltert nach 'uni'):\nKeine Einträge mit 'uni' in diesem Zeitraum."


@pytest.fixture(autouse=True)
def ruhig(monkeypatch):
    monkeypatch.setattr(consolidation, "zug_vormerken", lambda *a, **k: None)
    monkeypatch.setattr(erlaubnis, "braucht_erlaubnis", lambda *a, **k: False)
    monkeypatch.setattr(ai_config, "_overrides", {})


def _abgabe(text, auftrag=None, id="a1", **mehr):
    args = {"text": text, "erledigt": [], "fragt_erlaubnis": False, "schiebt_auf": False,
            **mehr}
    if auftrag is not None:
        args["auftrag"] = auftrag
    return R("", [(id, "antwort", args)])


def _laufen(adapter, nutzer, exec_=lambda n, a: "ok"):
    p = ehrlichkeit.Pruefer("an", nutzer_text=nutzer)
    gerufen = []

    def ausfuehren(n, a):
        gerufen.append(n)
        return exec_(n, a)
    ev = list(werkzeug_schleife.laufen(adapter, tutor_mode=False, active_exec=ausfuehren,
                                       user_query=nutzer, schiene="gross", pruefer=p))
    return ev, p, gerufen


def _schluss(ev):
    return next((e["ehrlichkeit"] for e in ev if isinstance(e, dict) and "ehrlichkeit" in e),
                None)


def _schritt(name, args=None, status="ok", text="ok"):
    return ehrlichkeit.Schritt(name, args or {}, status, text)


# ── Der Fall f01k ───────────────────────────────────────────────────────

def test_f01k_pause_weggelassen_korrektur_bis_add_calendar_pause():
    erledigt = [{"was": "nyam löschen", "stand": "erledigt", "werkzeug": "delete_calendar_entry"},
                {"was": "Geige nur Do 18:10–19:00", "stand": "erledigt",
                 "werkzeug": "edit_calendar_routine"}]
    a = _Skript([
        R("", [("c1", "delete_calendar_entry", {"kennung": "#t8d2e"}),
               ("c2", "edit_calendar_routine", {"kennung": "#ra82b", "aktion": "aendern"})]),
        # 1. Haikus Antwort: frei, ohne Abrechnung — die Pause fehlt still.
        R(HAIKU),
        # 2. Abgerechnet, die Pause offen mit sicherem Teil.
        _abgabe("Pause trag ich ein, wenn das Ferienende klar ist.", erledigt + [
            {"was": "Geige fällt aus", "stand": "offen", "grund": "Ende der Ferien unklar",
             "sicherer_teil": "Pause ab heute"}], id="a2"),
        # 3. Jetzt eingetragen.
        R("", [("c3", "add_calendar_pause", {"kennung": "#ra82b", "von": "2026-10-08"})]),
        _abgabe("nyam ist weg, Geige Do 18:10–19:00, heute fällt sie aus. Bis wann gehen "
                "die Ferien?", erledigt + [
                    {"was": "Geige fällt aus", "stand": "erledigt",
                     "werkzeug": "add_calendar_pause"},
                    {"was": "Pause bis Ferienende", "stand": "offen",
                     "grund": "Ende der Ferien unklar"}], id="a3"),
    ])
    ev, p, gerufen = _laufen(a, F01K)
    assert "add_calendar_pause" in gerufen
    assert len(a.hinweise) == 2
    assert "in `auftrag` ab" in a.hinweise[0]
    assert "Trag den sicheren Teil jetzt ein (Pause ab heute)" in a.hinweise[1]
    s = _schluss(ev)
    assert s["korrekturen"] == 2 and "warnungen" not in s
    assert s["auftrag"]["zeile"] == "offen: Pause bis Ferienende — Ende der Ferien unklar"
    assert [x["stand"] for x in s["auftrag"]["punkte"]] == ["erledigt"] * 3 + ["offen"]
    assert "✓ Pause eingetragen" in s["zeile"]


def test_fehlende_abrechnung_nur_eine_runde_dann_ohne_warnung():
    a = _Skript([R("", [("c1", "delete_calendar_entry", {"kennung": "#t1"}),
                        ("c2", "edit_calendar_routine", {"kennung": "#r2"})]),
                 R(HAIKU), R(HAIKU)])
    ev, p, _ = _laufen(a, F01K)
    assert len(a.hinweise) == 1
    s = _schluss(ev)
    assert "warnungen" not in s and "auftrag" not in s
    assert any(b["art"] == "auftrag_fehlt" for b in s["befunde"])


def test_offen_ohne_sicheren_teil_kein_befund_aber_sichtbar():
    a = _Skript([_abgabe("Geht klar, sobald du mir das Ende sagst. Bis wann?", [
        {"was": "Geige fällt aus", "stand": "offen", "grund": "Ende der Ferien unklar"}])])
    ev, p, _ = _laufen(a, "geige fällt wegen der ferien aus")
    assert a.hinweise == []
    s = _schluss(ev)
    assert "befunde" not in s
    assert s["auftrag"]["zeile"] == "offen: Geige fällt aus — Ende der Ferien unklar"


def test_abgelehnt_steht_als_nicht_gemacht_da():
    punkte = selbstauskunft.auftrag_lesen([
        {"was": "Konto löschen", "stand": "abgelehnt", "grund": "kann ich nicht"},
        {"was": "Zahnarzt", "stand": "erledigt"}])
    assert ab.zeile(punkte) == "nicht gemacht: Konto löschen — kann ich nicht"
    assert ab.befunde(punkte, [_schritt("add_calendar_entry")]) == []


def test_erledigt_ohne_werkzeug_ist_eine_tat_mit_warnung():
    punkte = [{"was": "Pause eintragen", "stand": "erledigt", "werkzeug": "add_calendar_pause"}]
    b = ab.befunde(punkte, [_schritt("read_calendar")])
    assert b == [{"art": "tat", "satz": "Pause eintragen", "quelle": "auftrag",
                  "auftrag": True, "werkzeug": "add_calendar_pause"}]
    w = ehrlichkeit.warnungen(b)
    assert w and "„Pause eintragen“ als erledigt gemeldet" in w[0] and "Kalender" in w[0]
    assert "add_calendar_pause nicht mit [ergebnis: ok]" in ehrlichkeit.hinweis(b)
    # Abgelehnt am Knopf ist nicht erledigt.
    assert ab.befunde(punkte, [_schritt("add_calendar_pause", status="abgelehnt")])
    assert ab.befunde(punkte, [_schritt("add_calendar_pause")]) == []
    # Ohne (bekanntes) Werkzeug reicht irgendein ok — ohne gar keins nicht.
    ohne = [{"was": "Ferien nachsehen", "stand": "erledigt", "werkzeug": "zaubern"}]
    assert ab.befunde(ohne, [_schritt("web_search")]) == []
    assert ab.befunde(ohne, [])[0]["art"] == "tat"


def test_sicherer_teil_schon_getan_keine_runde():
    punkte = [{"was": "Geige fällt aus", "stand": "offen", "werkzeug": "add_calendar_pause",
               "sicherer_teil": "Pause ab heute"}]
    assert ab.befunde(punkte, [_schritt("add_calendar_pause")]) == []
    assert ab.befunde(punkte, [])[0]["art"] == "sicherer_teil"


# ── Wann ist eine Abrechnung Pflicht? ───────────────────────────────────

@pytest.mark.parametrize("nutzer,protokoll,noetig", [
    # zwei Aussage-Teile und geschrieben → Pflicht, gleich welche Sprache
    ("delete nyam. set violin to 6pm!", [_schritt("delete_calendar_entry", {"kennung": "#t1"}),
                                         _schritt("edit_calendar_routine", {"kennung": "#r2"})],
     True),
    # ein Teil, aber per Löschen+Anlegen verschoben → kein Mehrfach-Auftrag
    ("der zahnarzt am dienstag ist jetzt erst um 16:30, die haben grad angerufen",
     [_schritt("delete_calendar_entry", {"kennung": "#t1"}),
      _schritt("add_calendar_entry", {"label": "Zahnarzt"})], False),
    # zwei Teile, aber nichts geschrieben (reden, fragen) → nicht Pflicht
    ("bin in saarbrücken. die ferien gehen bald los.", [_schritt("web_search")], False),
    # ein Schreiben, aber zwei Aussage-Teile in der Nachricht
    ("Zahnarzt morgen um 10 Uhr. Und Geige fällt aus.", [_schritt("add_calendar_entry",
                                                              {"label": "Zahnarzt"})], True),
    # ein Schreiben, ein Auftrag plus eine Frage → nicht Pflicht
    ("trag zahnarzt morgen um 10 ein. passt das?", [_schritt("add_calendar_entry",
                                                             {"label": "Zahnarzt"})], False),
    # nur gelesen
    ("wann ist parkour? und wann geige?", [_schritt("read_calendar")], False),
    # Uhrzeiten und Daten trennen keine Sätze
    ("parkour am 12.10. um 18.30", [_schritt("add_calendar_entry", {"label": "P"})], False),
    ("", [_schritt("delete_calendar_entry", {"kennung": "#t1"}),
          _schritt("edit_calendar_routine", {"kennung": "#r2"})], False),
])
def test_noetig(nutzer, protokoll, noetig):
    assert ab.noetig(nutzer, protokoll) is noetig


def test_reine_frage_braucht_keine_abrechnung():
    a = _Skript([R("", [("c1", "read_calendar", {"suche": "parkour"})]),
                 R("Parkour ist Mittwoch 18:00–19:00 und Freitag 20:00–21:00.")])
    ev, p, _ = _laufen(a, "wann ist parkour diese woche?",
                       exec_=lambda n, a: "Mittwoch 18:00–19:00 Parkour")
    assert a.hinweise == [] and p.befunde == []


def test_leere_abrechnung_trotz_zwei_aenderungen_ist_fehlend():
    b = ab.befunde([], [_schritt("delete_calendar_entry", {"kennung": "#t1"}),
                        _schritt("write_note", {"titel": "x"})], "lösch das. notier das.")
    assert [x["art"] for x in b] == ["auftrag_fehlt"]


# ── Form: tolerant lesen ────────────────────────────────────────────────

def test_auftrag_lesen_tolerant():
    assert selbstauskunft.auftrag_lesen(None) is None
    assert selbstauskunft.auftrag_lesen([]) == []
    assert selbstauskunft.auftrag_lesen("Pause eintragen") == [
        {"was": "Pause eintragen", "stand": "offen"}]
    p = selbstauskunft.auftrag_lesen([{"was": " X ", "stand": "Erledigt", "werkzeug": "w"},
                                      {"stand": "offen"}, {"was": "Y", "stand": "done"}, 7])
    assert p == [{"was": "X", "stand": "erledigt", "werkzeug": "w"},
                 {"was": "Y", "stand": "offen"}]
    a = selbstauskunft.lesen({"text": "t", "auftrag": [{"was": "Z", "stand": "offen"}],
                              "nicht_gefunden": ["uni"]})
    assert a.als_dict()["auftrag"] == [{"was": "Z", "stand": "offen"}]
    assert a.nicht_gefunden == ["uni"]
    assert "auftrag" not in selbstauskunft.lesen({"text": "t"}).als_dict()


def test_schema_auftrag_ist_pflicht_und_hat_die_staende():
    import werkzeug_register
    p = werkzeug_register.eintrag("antwort").gross_parameter
    assert "auftrag" in p["required"]
    item = p["properties"]["auftrag"]["items"]
    assert item["properties"]["stand"]["enum"] == list(selbstauskunft.STAENDE)
    assert "nicht_gefunden" in p["properties"] and "nicht_gefunden" not in p["required"]


# ── „Nicht gefunden" nach nur einer Stichwortsuche — für alle Modelle ───

def test_nicht_gefunden_nach_stichwortsuche_wird_korrigiert():
    a = _Skript([
        R("", [("c1", "read_calendar", {"suche": "uni"})]),
        R("Ich hab die uni-Einträge nicht gefunden — möglicherweise unter anderen Namen."),
        R("", [("c2", "read_calendar", {"zeitraum": "naechste_30_tage"})]),
        R("Analysis I, Chemie und Theoretische Physik stehen drin. Bis wann geht das "
          "Semester?"),
    ])

    def exec_(n, a):
        return LEER if a.get("suche") else "Montag, 12.10.2026: 10:00-12:00 Analysis I"
    ev, p, _ = _laufen(a, "die uni-sachen sollen nur im semester stehen", exec_)
    assert len(a.hinweise) == 1
    assert ehrlichkeit.STICHWORT in a.hinweise[0]
    assert "warnungen" not in (_schluss(ev) or {})


def test_nicht_gefunden_ueber_das_feld_sprachfrei():
    prot = [_schritt("read_calendar", {"suche": "uni"}, text=LEER)]
    a = selbstauskunft.lesen({"text": "Couldn't find them.", "nicht_gefunden": ["uni courses"]})
    b = ehrlichkeit.stichwort_befund("Couldn't find them.", prot, a)
    assert b == {"art": "stichwort", "satz": "uni courses", "quelle": "auskunft"}
    w = ehrlichkeit.warnungen([b])
    assert w and "Stichwortsuche" in w[0]
    # Ohne Suchwort gelesen: dann darf sie „nichts da" sagen.
    prot2 = prot + [_schritt("read_calendar", {"zeitraum": "naechste_30_tage"}, text="Montag …")]
    assert ehrlichkeit.stichwort_befund("Nichts gefunden.", prot2) is None
    # Frage und Bedingung zählen nicht.
    assert ehrlichkeit.stichwort_befund("Falls nichts da ist, sag Bescheid.", prot) is None
    assert ehrlichkeit.stichwort_befund("Hast du nichts gefunden?", prot) is None


# ── Gespeichert, Route, Trace, TUI ──────────────────────────────────────

@pytest.fixture
def client(monkeypatch):
    from ui.app import app
    app.config.update(TESTING=True)
    monkeypatch.setattr(ai_backends, "chat_available", lambda: ai_backends.CLOUD)
    monkeypatch.setattr(ai_backends, "cloud_provider", lambda: "test")
    monkeypatch.setattr(ai_backends, "modell_wechsel", lambda: None)
    monkeypatch.setattr(ai_config, "_overrides", {"ehrlichkeit_pruefer": "an"})
    return app.test_client()


def test_route_speichert_auftrag_und_tui_zeigt_offen(client, monkeypatch):
    punkte = [{"was": "Geige fällt aus", "stand": "offen", "grund": "Ende der Ferien unklar"}]

    def gen(history, **k):
        zug_ablauf.system("fest")      # macht das Ablauf-Protokoll scharf, wie cloud.py
        p = ehrlichkeit.pruefer_fuer(history, schiene="gross", tutor_mode=False)
        yield from werkzeug_schleife.laufen(
            _Skript([_abgabe("Bis wann gehen die Ferien?", punkte)]), tutor_mode=False,
            user_query="x", schiene="gross", active_exec=lambda n, a: "ok", pruefer=p)

    class Modul:
        chat_stream = staticmethod(gen)
    monkeypatch.setattr(kern, "cloud_modul", lambda: Modul)
    monkeypatch.setattr(cloud, "_profil", lambda: __import__("profil").gross)
    monkeypatch.setattr(ki_prompt, "_alarm_prompt", lambda: "")
    r = client.post("/api/chat", json={"message": "geige fällt wegen der ferien aus"})
    ev = [json.loads(z[5:]) for z in r.get_data(as_text=True).splitlines()
          if z.startswith("data:")]
    zeile = "offen: Geige fällt aus — Ende der Ferien unklar"
    assert next(e["ehrlichkeit"] for e in ev if "ehrlichkeit" in e)["auftrag"]["zeile"] == zeile
    antwort = gespraeche.nachrichten(gespraeche.aktiv())[-1]
    assert antwort["auftrag"] == {"zeile": zeile, "punkte": punkte}
    assert zeile not in antwort["text"]
    assert any(e.get("art") == "auftrag" for e in antwort.get("ablauf") or [])
    h = client.get("/api/chat/history").get_json()[-1]
    assert h["auftrag"]["zeile"] == zeile

    from tui.ansichten.chat_gespraeche import verlauf_aus
    from tui.ansichten import verlauf
    log = verlauf_aus([h])
    i_ai = max(i for i, (rolle, _t) in enumerate(log) if rolle == "ai")
    assert ("auftrag", zeile) in log[i_ai:]
    stile = {s for z in verlauf.verlauf_zeilen(log, 60) for t, s, _z in z if "offen:" in t}
    assert stile == {"leise"}


def test_trace_zeilen():
    e = {"art": "auftrag", "punkte": [
        {"was": "nyam", "stand": "erledigt", "werkzeug": "delete_calendar_entry"},
        {"was": "Pause", "stand": "offen", "grund": "Ende unklar", "sicherer_teil": "ab heute"}]}
    assert zug_ablauf.kopfzeile(e) == "Auftrag · 1 erledigt, 1 offen"
    assert "- offen: Pause · Grund: Ende unklar · sicher: ab heute" in zug_ablauf.inhalt(e)
    from tui.ansichten import spur
    assert spur.kopf(e) == "task: 1 done, 1 open"
    assert "sicherer_teil: ab heute" in spur.inhalt(e)


def test_tui_live_zeigt_auftrag_unter_der_antwort(monkeypatch):
    from types import SimpleNamespace
    from test_chat_strom import _laufen as strom_laufen, _Schirm
    from tui.ansichten import chat, chat_gespraeche, chat_strom
    ch = chat.Chat(SimpleNamespace(stdscr=_Schirm(), C={}))
    ch.AI.update(active=True, gid="a", titel="t", loaded=True, log=[("user", "alt")])
    ch.verlauf_laden = lambda gid=None: None
    monkeypatch.setattr(chat_gespraeche, "api_call", lambda *a, **k: {})
    monkeypatch.setattr(chat_strom, "api_call", lambda *a, **k: {})
    zeile = "offen: Geige fällt aus — Ende der Ferien unklar"
    strom_laufen(ch, monkeypatch, [
        {"strom": "z1"}, {"gespraech": "a", "nachricht": "n1"},
        {"token": "Bis wann gehen die Ferien?"},
        {"ehrlichkeit": {"erledigt": [], "zeile": "", "auftrag": {"zeile": zeile,
                                                                  "punkte": []}}},
        {"done": True}])
    log = ch.AI["log"]
    i = log.index(("ai", "Bis wann gehen die Ferien?"))
    assert ("auftrag", zeile) in log[i:]
