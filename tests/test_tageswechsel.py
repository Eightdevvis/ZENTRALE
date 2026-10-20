"""
Tageswechsel: „heute" friert nicht ein (Anlass 20.10.2026).

Sasha: „zentrale steht immer noch auf 19.10. böse falle, vorallem wenn
zentrale künftig auf nem server bald im dauerzustand weiterlaufen soll."
Die TUI lief über Mitternacht; der Kalender blieb auf dem Öffnungstag
(Anker K["ref"]/W["tag"] und die gepufferte /api/calendar-Antwort mit
ihrem `today`, Schlüssel ohne Datum).

Geprüft mit gestellter Uhr (core/uhr.py) von 23:59 auf 00:01:
  - Kalender der TUI: Heute-Markierung, Anker rückt mit, ein bewusst
    gewählter anderer Tag bleibt stehen, Hot-Reload-Übergabe,
  - API: /api/calendar ohne ref liefert das neue `today`,
  - Alarme: der Konflikt von gestern fällt sofort raus (main.py-Hörer),
  - Graph-Reminder: weggeklickt gilt für den Tag, nicht die Sitzung,
  - Wächter: kein neues date.today()/datetime.now() auf Modulebene, in
    __init__, als Default einer Signatur oder in einer gecachten Funktion.

Gefahrzone dazu: memory/system/gefahrzonen.md („Eingefrorener Tag").
"""
import ast
import os
import types
from datetime import date, datetime
from pathlib import Path

import pytest

import uhr

ROOT = Path(__file__).resolve().parent.parent
ABEND = datetime(2026, 10, 19, 23, 59)
GESTERN, HEUTE = date(2026, 10, 19), date(2026, 10, 20)


@pytest.fixture
def abends():
    """Uhr auf 19.10.2026 23:59 — vorstellen(minutes=2) ist nach Mitternacht."""
    with uhr.gestellt(ABEND):
        yield


# ── die Uhr selbst ─────────────────────────────────────────────────────

def test_uhr_meldet_den_wechsel_genau_einmal(abends):
    w = uhr.Tageswechsel()
    gehoert = []
    w.anmelden(lambda alt, neu: gehoert.append((alt, neu)))
    w.anmelden(lambda alt, neu: 1 / 0)          # ein kaputter Hörer stört nicht
    assert w.pruefen() is None and uhr.heute() == GESTERN
    uhr.vorstellen(minutes=2)
    assert w.pruefen() == HEUTE
    assert w.pruefen() is None
    assert gehoert == [(GESTERN, HEUTE)]


def test_uhr_nach_tagen_ruhezustand_ein_wechsel(abends):
    """Laptop zugeklappt über mehrere Tage: EIN Wechsel, alt = zuletzt gesehen."""
    w = uhr.Tageswechsel()
    gehoert = []
    w.anmelden(lambda alt, neu: gehoert.append((alt, neu)))
    uhr.vorstellen(days=3)
    w.pruefen()
    assert gehoert == [(GESTERN, date(2026, 10, 22))]


# ── TUI-Kalender ───────────────────────────────────────────────────────

@pytest.fixture
def kal(abends, tmp_path, monkeypatch):
    """Der TUI-Kalender gegen ein falsches Backend, das `today` von der Uhr
    nimmt wie das echte (ui/routen/kalender.py)."""
    monkeypatch.setenv("ZENTRALE_KALENDER_FARBEN", str(tmp_path / "f.json"))
    from tui.ansichten import kalender_bedienung
    from tui.ansichten.kalender import Kalender
    anfragen = []

    def api(pfad, **_k):
        anfragen.append(pfad)
        if not pfad.startswith("/api/calendar?"):
            return {}
        return {"today": uhr.heute().isoformat(), "ref": pfad.rsplit("=", 1)[1],
                "start": "2026-09-28", "end": "2026-11-08", "days": {}}

    monkeypatch.setattr(kalender_bedienung, "api_call", api)
    k = Kalender(types.SimpleNamespace())
    k.oeffnen()
    k.anfragen = anfragen
    return k


def _heute_markiert(k):
    from tui.ansichten import kalender_ansichten as ka
    return ka._rahmen(k.bedienung.daten())[0]


def test_kalender_heute_rueckt_ueber_mitternacht(kal):
    b = kal.bedienung
    assert b.tag() == GESTERN and _heute_markiert(kal) == GESTERN
    uhr.vorstellen(minutes=2)
    kal.tageswechsel(GESTERN, HEUTE)
    assert b.tag() == HEUTE
    assert kal.K["ref"] == HEUTE.isoformat()           # A: Fenster beginnt heute
    assert _heute_markiert(kal) == HEUTE


def test_kalender_puffer_klebt_auch_ohne_ereignis_nicht(kal):
    """Selbst wenn niemand das Ereignis zustellt: der Puffer hat den Tag im
    Schlüssel, die Heute-Markierung stimmt nach Mitternacht."""
    assert _heute_markiert(kal) == GESTERN
    uhr.vorstellen(minutes=2)
    assert _heute_markiert(kal) == HEUTE


def test_kalender_bewusst_gewaehlter_tag_bleibt(kal):
    b = kal.bedienung
    gewaehlt = date(2026, 10, 25)
    b.setze_tag(gewaehlt)
    uhr.vorstellen(minutes=2)
    kal.tageswechsel(GESTERN, HEUTE)
    assert b.tag() == gewaehlt
    assert _heute_markiert(kal) == HEUTE               # Markierung trotzdem neu


def test_kalender_gemerkte_ansichten_auf_heute_ruecken_mit(kal):
    """B (Monat) stand auf heute, A wird gerade gezeigt: nach Mitternacht
    kommt B beim Zurückwechseln auf dem neuen Heute an."""
    kal.k_stil_weiter()                                # A → B, beide auf 19.10.
    kal.k_stil_weiter()                                # B → C
    kal.k_stil_weiter()                                # C → A
    uhr.vorstellen(minutes=2)
    kal.tageswechsel(GESTERN, HEUTE)
    kal.k_stil_weiter()                                # → B aus dem Gemerkten
    assert kal.K["stil"] == "B" and kal.bedienung.tag() == HEUTE


def test_kalender_hot_reload_ueber_mitternacht(kal, monkeypatch):
    """Vor Mitternacht gemerkt, danach neu geladen: heute bleibt heute."""
    stand = kal.stand_fuer_neustart()
    assert stand["heute"] is True
    uhr.vorstellen(minutes=2)
    from tui.ansichten.kalender import Kalender
    neu = Kalender(types.SimpleNamespace())
    neu.oeffnen()
    neu.stand_nach_neustart(stand)
    assert neu.bedienung.tag() == HEUTE


def test_tui_hauptschleife_verkabelt_den_wechsel(kal):
    from tui import zentrale_tui as zt
    erinnerung = types.SimpleNamespace(tageswechsel=lambda a, n: None)
    graphen = types.SimpleNamespace(tageswechsel=lambda a, n: None)
    w = zt.tageswechsel_verkabeln(kal, graphen, erinnerung)
    uhr.vorstellen(minutes=2)
    assert w.pruefen() == HEUTE
    assert kal.bedienung.tag() == HEUTE


def test_graph_reminder_weggeklickt_gilt_fuer_den_tag():
    from tui.ansichten.erinnerung import Erinnerung
    e = Erinnerung(types.SimpleNamespace(), graphen=None)
    store = types.SimpleNamespace(reminders_snapshot=lambda: [{"id": "g1"}])
    e.pruefen(store)
    e.taste(ord("x"))                                  # weggeklickt
    e.pruefen(store)
    assert not e.nag_active
    e.tageswechsel(GESTERN, HEUTE)
    e.pruefen(store)
    assert e.nag_active


# ── Backend ────────────────────────────────────────────────────────────

def test_api_calendar_today_ueber_mitternacht(abends):
    from ui.app import app
    app.config.update(TESTING=True)
    c = app.test_client()
    assert c.get("/api/calendar").get_json()["today"] == GESTERN.isoformat()
    uhr.vorstellen(minutes=2)
    d = c.get("/api/calendar").get_json()
    assert d["today"] == HEUTE.isoformat() and d["ref"] == HEUTE.isoformat()


@pytest.mark.kalender_beide
def test_alarme_vom_vortag_fallen_um_mitternacht(abends, tmp_path, monkeypatch):
    import kalender
    import main
    import state
    from events import DAY_CHANGED
    monkeypatch.setattr(kalender, "CAL_PATH", tmp_path / "cal.json")
    for titel in ("Probe", "Konzert"):
        kalender.add_entry("termine", GESTERN.isoformat(), titel,
                           time="20:00", ende="22:00")
    state.set_alarms(kalender.alarme())
    vortag = lambda: [a for a in state.get_alarms() if a.get("tag") == GESTERN.isoformat()]
    assert vortag(), "Kollision am 19.10. sollte um 23:59 noch alarmieren"

    queue = []
    w = uhr.Tageswechsel()
    main.tageswechsel_verkabeln(w, queue)
    uhr.vorstellen(minutes=2)
    w.pruefen()
    assert not vortag()
    assert queue == [DAY_CHANGED]


# ── Wächter ────────────────────────────────────────────────────────────
#
# Gemeldet wird ein Zeitaufruf (date.today, datetime.now/today/utcnow,
# uhr.heute/jetzt), der einen Tag FESTHÄLT:
#   - auf Modulebene oder im Klassenkörper (läuft einmal beim Import),
#   - in __init__ (Zustand für die ganze Lebenszeit des Objekts),
#   - als Default einer Signatur (def f(tag=date.today()) — beim def!),
#   - in einer Funktion mit @lru_cache/@cache (Ergebnis klebt).
# Aufrufe im Rumpf einer gewöhnlichen Funktion sind in Ordnung: sie fragen
# jedes Mal neu. Wer einen Tag trotzdem hält, braucht hier eine Begründung.

ZEIT_AUFRUFE = {("date", "today"), ("datetime", "now"), ("datetime", "today"),
                ("datetime", "utcnow"), ("uhr", "heute"), ("uhr", "jetzt")}

AUSNAHMEN = {
    # Vorbelegung des Ankers; oeffnen() setzt heute, tageswechsel() rückt nach.
    ("tui/ansichten/kalender.py", "Kalender.__init__"):
        "Anker rückt per tageswechsel() nach",
}


def _zeit_aufruf(n):
    if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
        return False
    basis = n.func.value
    name = basis.attr if isinstance(basis, ast.Attribute) else getattr(basis, "id", None)
    return (name, n.func.attr) in ZEIT_AUFRUFE


def _treffer(knoten):
    return [n for n in ast.walk(knoten) if _zeit_aufruf(n)]


def _funde(pfad: Path, rel: str):
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    raus = []

    def melde(n, wo, wie):
        raus.append((rel, wo, n.lineno, wie))

    def funktion(f, wo):
        for d in f.args.defaults + [d for d in f.args.kw_defaults if d is not None]:
            for n in _treffer(d):
                melde(n, wo, "Default der Signatur")
        if any("cache" in ast.unparse(d) for d in f.decorator_list):
            for n in _treffer(f):
                melde(n, wo, "gecachte Funktion")
        elif f.name == "__init__":
            for n in _treffer(f):
                melde(n, wo, "__init__")

    def koerper(body, praefix):
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funktion(st, praefix + st.name)
            elif isinstance(st, ast.ClassDef):
                koerper(st.body, praefix + st.name + ".")
            else:
                # Modul-/Klassenebene. Funktionen in if/try-Blöcken darunter
                # einzeln prüfen, ihren Rumpf aber nicht als Modulebene werten.
                innen = {id(n) for f in ast.walk(st)
                         if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                         for n in ast.walk(f) if n is not f}
                for f in ast.walk(st):
                    if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        funktion(f, praefix + f.name)
                for n in _treffer(st):
                    if id(n) not in innen:
                        melde(n, praefix + "<modul>", "Modulebene")

    koerper(baum.body, "")
    return raus


def _alle_funde():
    raus = []
    for bereich in ("core", "ui", "tui"):
        for p in sorted((ROOT / bereich).rglob("*.py")):
            rel = p.relative_to(ROOT).as_posix()
            raus += _funde(p, rel)
    return raus


def test_waechter_kein_eingefrorener_tag():
    neu = [f for f in _alle_funde() if (f[0], f[1]) not in AUSNAHMEN]
    assert not neu, (
        "„heute\" wird hier einmal festgehalten und nie erneuert — im "
        "Dauerbetrieb steht es nach Mitternacht falsch:\n  "
        + "\n  ".join(f"{d}:{z} {wo} ({wie})" for d, wo, z, wie in neu)
        + "\nZur Gebrauchszeit uhr.heute() fragen; wer sich einen Tag merkt, "
          "meldet sich beim Tageswechsel an (memory/system/gefahrzonen.md). "
          "Begründete Ausnahme: AUSNAHMEN in diesem Test.")


def test_waechter_ausnahmen_gibt_es_noch():
    """Eine Ausnahme ohne Fundstelle ist veraltet und kommt raus."""
    da = {(f[0], f[1]) for f in _alle_funde()}
    assert not set(AUSNAHMEN) - da, sorted(set(AUSNAHMEN) - da)


def test_waechter_erkennt_die_verstecke(tmp_path):
    """Selbsttest: jede Form wird gemeldet, ein Aufruf im Rumpf nicht."""
    p = tmp_path / "probe.py"
    p.write_text(
        "from datetime import date, datetime\n"
        "from functools import lru_cache\n"
        "HEUTE = date.today()\n"
        "def f(tag=date.today()):\n    return tag\n"
        "@lru_cache(maxsize=1)\ndef g():\n    return datetime.now().date()\n"
        "class K:\n"
        "    STAND = uhr.heute()\n"
        "    def __init__(self):\n        self.tag = date.today()\n"
        "    def gut(self):\n        return date.today()\n"
        "try:\n    import x\nexcept ImportError:\n"
        "    def h():\n        return date.today()\n", encoding="utf-8")
    wie = sorted(f[3] for f in _funde(p, "probe.py"))
    assert wie == sorted(["Modulebene", "Default der Signatur", "gecachte Funktion",
                          "Modulebene", "__init__"]), wie
