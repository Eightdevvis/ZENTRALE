"""
Morgen-Messenger (core/morgen.py + scripts/morgen_messenger.py).

Geprüft wird die Logik, nicht die Optik: Fälligkeit, Schlaf-Eintrag in den
Graphen, die Aufgaben-Warteschlange (übernehmen / erledigen / vertagen) und
der Zustandsautomat des Fensters — der lässt sich ohne curses durchspielen,
weil er nur Tasten frisst und Zustände setzt.
"""
import os
import sys
from datetime import datetime, date, timedelta

import pytest

import graphs
import lists
import morgen

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import morgen_messenger as MM  # noqa: E402


@pytest.fixture()
def data(tmp_path, monkeypatch):
    """Alles auf ein leeres tmp-data/ umbiegen: Graph-Registry, Messwerte,
    Listen und der Messenger-Zustand. Sonst schriebe der Test in die echten
    Daten — und ein Test, der Sashas Schlafgraph anfasst, wäre ein Bug."""
    monkeypatch.setattr(graphs, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(graphs, "_REGISTRY", str(tmp_path / "graphs.json"))
    monkeypatch.setattr(lists, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(lists, "_REGISTRY", str(tmp_path / "lists.json"))
    monkeypatch.setattr(lists, "_FEATURES", str(tmp_path / "features.json"))
    monkeypatch.setattr(lists, "_week_migrated", False)
    monkeypatch.setattr(morgen, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(morgen, "_STATE", str(tmp_path / "morgen_state.json"))
    return tmp_path


@pytest.fixture()
def welt(data):
    """Die Ausgangslage eines echten Morgens: ein »sleep«-Graph mit Reminder
    um 05:00 und eine »week«-Liste mit drei Aufgaben."""
    graphs.create_graph("sleep", gtype="period", remind=True, remind_at="05:00")
    wl = lists.create_list("week")
    for t in ("dritte", "zweite", "erste"):     # week fügt oben ein → erste oben
        lists.add_item(wl["id"], t)
    return wl


# ── Die »week«-Liste sortiert Neues nach oben ────────────────────────────

def test_week_list_prepends_new_items(data):
    wl = lists.create_list("week")
    lists.add_item(wl["id"], "alt")
    lists.add_item(wl["id"], "neu")
    texts = [i["text"] for i in lists.week_items()["items"]]
    assert texts == ["neu", "alt"]


def test_other_lists_still_append(data):
    other = lists.create_list("trading")
    lists.add_item(other["id"], "alt")
    lists.add_item(other["id"], "neu")
    items = next(l for l in lists.list_lists() if l["id"] == other["id"])["items"]
    assert [i["text"] for i in items] == ["alt", "neu"]


def test_week_sublevel_still_appends(data):
    """Nur die oberste Ebene dreht sich um — Unterpunkte eines Eintrags
    bleiben in Eingabe-Reihenfolge, sonst läse sich jede Checkliste rückwärts."""
    wl = lists.create_list("week")
    top = lists.add_item(wl["id"], "aufgabe")
    lists.add_item(wl["id"], "schritt 1", parent_iid=top["id"])
    lists.add_item(wl["id"], "schritt 2", parent_iid=top["id"])
    kids = next(l for l in lists.list_lists()
                if l["id"] == wl["id"])["items"][0]["items"]
    assert [k["text"] for k in kids] == ["schritt 1", "schritt 2"]


# ── Schlaf ───────────────────────────────────────────────────────────────

def test_sleep_open_until_logged(welt):
    assert morgen.sleep_open() is True
    morgen.log_sleep(23 * 60, 7 * 60)
    assert morgen.sleep_open() is False


def test_log_sleep_writes_period_entry(welt):
    morgen.log_sleep(23 * 60 + 30, 6 * 60 + 45)
    rows = graphs.read_values(morgen.sleep_graph()["id"])
    assert len(rows) == 1
    assert rows[0]["date"] == date.today().isoformat()
    assert rows[0]["value"] == 23 * 60 + 30      # eingeschlafen
    assert rows[0]["end"] == 6 * 60 + 45         # aufgewacht
    assert "logged_at" in rows[0]


def test_log_sleep_upserts(welt):
    """Zweimal eintragen darf keine zwei Einträge für denselben Tag geben —
    sonst zeigte der Graph die Nacht doppelt."""
    morgen.log_sleep(23 * 60, 7 * 60)
    morgen.log_sleep(0, 8 * 60)
    rows = graphs.read_values(morgen.sleep_graph()["id"])
    assert len(rows) == 1 and rows[0]["value"] == 0


def test_skip_sleep_holds_for_the_day(welt):
    morgen.skip_sleep()
    assert morgen.sleep_open() is False
    assert graphs.read_values(morgen.sleep_graph()["id"]) == []


def test_sleep_duration_crosses_midnight(welt):
    assert morgen.sleep_duration(23 * 60, 7 * 60) == 8 * 60


def test_earliest_time_from_graph(welt):
    assert morgen.earliest_time() == "05:00"


# ── Aufgaben ─────────────────────────────────────────────────────────────

def test_first_task_is_top_of_list(welt):
    assert morgen.next_task()["text"] == "erste"


def test_done_tasks_drop_out(welt):
    t = morgen.next_task()
    morgen.conclude(t["lid"], t["iid"])
    assert morgen.next_task()["text"] == "zweite"


def test_take_on_survives_and_is_reported(welt):
    t = morgen.next_task()
    morgen.take_on(t["key"])
    assert morgen.next_task()["taken"] is True


def test_conclude_clears_taken_state(welt):
    t = morgen.next_task()
    morgen.take_on(t["key"])
    morgen.conclude(t["lid"], t["iid"])
    assert morgen._load_state().get("taken", {}) == {}


def test_snooze_hides_until_the_time(welt):
    t = morgen.next_task()
    later = datetime.now() + timedelta(hours=3)
    morgen.snooze(t["key"], later)
    assert morgen.next_task()["text"] == "zweite"
    # Zum Zeitpunkt selbst ist sie wieder da (Reihenfolge bleibt: sie stand oben).
    assert morgen.next_task(now=later + timedelta(minutes=1))["text"] == "erste"


def test_skip_shows_next_without_changing_the_list(welt):
    first = morgen.next_task()
    second = morgen.next_task(skip={first["key"]})
    assert second["text"] == "zweite"
    assert [i["text"] for i in lists.week_items()["items"]] \
        == ["erste", "zweite", "dritte"]


# ── Fälligkeit ───────────────────────────────────────────────────────────

def test_not_due_before_the_wake_time(welt):
    assert morgen.is_due(now=datetime.combine(date.today(),
                                              datetime.min.time().replace(hour=4))) is False


def test_due_after_the_wake_time(welt):
    assert morgen.is_due(now=datetime.combine(date.today(),
                                              datetime.min.time().replace(hour=7))) is True


def test_closed_day_stays_closed(welt):
    morgen.close_day()
    assert morgen.is_due(now=datetime.combine(date.today(),
                                              datetime.min.time().replace(hour=7))) is False


def test_silent_when_nothing_to_say(data):
    """Kein Graph, keine Aufgabe → der Messenger hält den Mund, statt ein
    leeres Fenster aufzureißen."""
    graphs.create_graph("sleep", gtype="period", remind=True, remind_at="05:00")
    morgen.log_sleep(23 * 60, 7 * 60)
    assert morgen.is_due(now=datetime.combine(date.today(),
                                              datetime.min.time().replace(hour=9))) is False


# ── Datum/Zeit-Eingabe des Vertagens ─────────────────────────────────────

@pytest.mark.parametrize("datum, zeit, erwartet", [
    ("",           "14:30", (2026, 8, 2, 14, 30)),   # leer = heute
    ("5",          "9",     (2026, 8, 5, 9, 0)),     # nur der Tag
    ("05.09.",     "07:15", (2026, 9, 5, 7, 15)),
    ("2026-12-24", "18:00", (2026, 12, 24, 18, 0)),
    ("1.1.",       "08:00", (2027, 1, 1, 8, 0)),     # schon vorbei → nächstes Jahr
])
def test_parse_when(datum, zeit, erwartet):
    got = morgen.parse_when(datum, zeit, today=date(2026, 8, 2))
    assert got == datetime(*erwartet)


@pytest.mark.parametrize("datum, zeit", [
    ("", ""), ("", "25:00"), ("32.1.", "08:00"), ("quatsch", "08:00"),
])
def test_parse_when_rejects_nonsense(datum, zeit):
    assert morgen.parse_when(datum, zeit, today=date(2026, 8, 2)) is None


# ── Der Zustandsautomat des Fensters (ohne curses) ───────────────────────

class FakeScreen:
    """Nur so viel Bildschirm, wie der Automat anfasst: die Innenbreite."""
    class _S:
        @staticmethod
        def getmaxyx():
            return (24, 80)
    s = _S()
    C = {}


class TinyScreen(FakeScreen):
    """So klein, dass ein langer Aufgabentext nicht mehr ganz hineinpasst:
    12 Zeilen → 6 Zeilen Inhalt, 52 Spalten → 46 Zeichen Textbreite."""
    class _S:
        @staticmethod
        def getmaxyx():
            return (12, 52)
    s = _S()


def _keys(m, text):
    for c in text:
        m.key(ord(c))


ENTER = 10
ESC = 27


def test_flow_sleep_then_take_on_and_conclude(welt):
    m = MM.Messenger(FakeScreen())
    assert m.state == "schlaf_von"

    _keys(m, "23:15"); m.key(ENTER)
    assert m.state == "schlaf_bis"
    _keys(m, "07:30"); m.key(ENTER)

    rows = graphs.read_values(morgen.sleep_graph()["id"])
    assert rows[0]["value"] == 23 * 60 + 15 and rows[0]["end"] == 7 * 60 + 30

    # Danach steht die oberste Aufgabe zur Übernahme bereit.
    assert m.state == "aufgabe" and m.task["text"] == "erste"
    m.key(ENTER)
    assert m.state == "uebernommen"
    m.key(ENTER)
    assert m.state == "bestaetigen"
    m.key(ord("n"))                       # doch nicht → zurück, nichts passiert
    assert m.state == "uebernommen"
    assert morgen.next_task()["text"] == "erste"

    m.key(ENTER); m.key(ord("y"))
    assert lists.week_items()["items"][0]["done"] is True
    # Abgehakt → Schluss für heute. Keine nächste Aufgabe hinterher: der
    # Messenger bietet morgens EINE an, er arbeitet die Liste nicht durch.
    assert m.done is True
    assert morgen.is_closed() is True


def test_flow_skip_sleep(welt):
    m = MM.Messenger(FakeScreen())
    m.key(ord("s"))
    assert m.state == "aufgabe"
    assert morgen.sleep_open() is False
    assert graphs.read_values(morgen.sleep_graph()["id"]) == []


def test_flow_snooze_shows_next_task(welt):
    morgen.skip_sleep()
    m = MM.Messenger(FakeScreen())
    assert m.state == "aufgabe" and m.task["text"] == "erste"

    m.key(ord("l"))
    assert m.state == "vertagen_datum"
    m.key(ENTER)                          # leeres Datum = heute
    assert m.state == "vertagen_zeit"
    _keys(m, "23:59"); m.key(ENTER)

    assert m.task["text"] == "zweite"
    assert morgen.next_task()["text"] == "zweite"


def test_flow_snooze_rejects_a_time_already_gone(welt):
    """Vertagen auf einen vergangenen Zeitpunkt würde die Aufgabe sofort
    wieder anbieten — das ist nie gewollt, also abgelehnt."""
    morgen.skip_sleep()
    m = MM.Messenger(FakeScreen())
    m.key(ord("l")); m.key(ENTER)                 # leeres datum = heute
    vorbei = (datetime.now() - timedelta(hours=1)).strftime("%H:%M")
    _keys(m, vorbei); m.key(ENTER)
    assert m.state == "vertagen_zeit" and m.msg == "das ist schon vorbei"
    assert morgen._load_state().get("snooze", {}) == {}
    assert morgen.next_task()["text"] == "erste"


def test_flow_snooze_rejects_bad_time(welt):
    morgen.skip_sleep()
    m = MM.Messenger(FakeScreen())
    m.key(ord("l")); m.key(ENTER)
    m.key(ENTER)                          # leere Uhrzeit
    assert m.state == "vertagen_zeit" and m.msg
    assert morgen.next_task()["text"] == "erste"


def test_flow_next_task_skips_without_touching_the_list(welt):
    morgen.skip_sleep()
    m = MM.Messenger(FakeScreen())
    m.key(ord("n"))
    assert m.task["text"] == "zweite"
    assert lists.week_items()["items"][0]["done"] is False


def test_flow_esc_closes_the_day(welt):
    morgen.skip_sleep()
    m = MM.Messenger(FakeScreen())
    m.key(ESC)
    assert m.done is True
    assert morgen.is_closed() is True


def test_flow_reopens_on_taken_task(welt):
    """Fenster zu, Aufgabe war übernommen: beim nächsten Aufmachen steht sie
    direkt im Übernommen-Zustand, nicht wieder mit »übernehmen?«."""
    morgen.skip_sleep()
    t = morgen.next_task()
    morgen.take_on(t["key"])
    m = MM.Messenger(FakeScreen())
    assert m.state == "uebernommen" and m.task["text"] == "erste"


def test_long_task_is_shortened_but_the_question_survives(data):
    """Das Fenster ist knapp geschnitten. Passt ein langer Aufgabentext nicht,
    wird ER gekürzt — nie die Frage darunter, sonst stünde man vor einem
    Eingabefeld ohne zu wissen, was gefragt ist."""
    graphs.create_graph("sleep", gtype="period", remind=True, remind_at="05:00")
    wl = lists.create_list("week")
    lists.add_item(wl["id"], "wort " * 60)          # weit mehr als 6 Zeilen
    morgen.skip_sleep()

    m = MM.Messenger(TinyScreen())
    _, lines, keys = m.view()
    assert len(lines) <= 6                          # passt in den Inhaltsbereich
    assert lines[-1] == "übernehmen?"               # die Frage steht noch da
    assert lines[-3].endswith("…")                  # gekürzt statt abgeschnitten
    assert all(len(x) <= 46 for x in lines)


def test_short_task_is_not_shortened(data):
    graphs.create_graph("sleep", gtype="period", remind=True, remind_at="05:00")
    wl = lists.create_list("week")
    lists.add_item(wl["id"], "oma anrufen")
    morgen.skip_sleep()

    _, lines, _ = MM.Messenger(TinyScreen()).view()
    assert lines == ["oma anrufen", "", "übernehmen?"]


def test_longest_key_line_fits_the_window(welt):
    """52 Spalten sind so gewählt, dass die längste Tastenzeile hineinpasst
    (3 Zeichen Rand links, Rahmen rechts). Wächst eine Zeile, muss COLS in
    scripts/morgen_start.sh mitwachsen — dieser Test schlägt dann an."""
    morgen.skip_sleep()
    m = MM.Messenger(TinyScreen())
    laengste = 0
    for zustand in ("aufgabe", "uebernommen", "bestaetigen",
                    "vertagen_datum", "vertagen_zeit"):
        m.state = zustand
        laengste = max(laengste, len(m.view()[2]))
    assert laengste <= 52 - 4


def test_messenger_selftest_runs():
    assert MM.selftest() == 0
