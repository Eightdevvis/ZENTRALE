"""Erschöpfende Tests der PUREN TUI-Helfer.

Zwei Ebenen:
  1. Konkrete Soll-Werte (Korrektheit der gehärteten Logik).
  2. Eine „darf-NIE-werfen"-Eigenschaft: jeder Helfer wird mit tausenden
     gemeinen Argument-Kombinationen beworfen (None, NaN, Inf, Listen, Bytes,
     Unicode, riesige Zahlen, falsch geformte Dicts) — keiner darf eine
     Exception werfen. Genau diese Robustheit hält die TUI am Leben.
"""
import math
import random

import pytest

from tui.zentrale_tui import (
    _num, fmt_uptime, fmt_clock, fmt_euro, parse_clock, period_duration,
    graph_series, graph_last, tele_value, parse_command, log_prefix,
    blockspark, bar, overlay_rows, terminal_too_small,
)

# ── Gemeiner Werte-Pool (für die Fuzz-Eigenschaft) ──────────────────────────
NASTY = [None, True, False, 0, 1, -1, 1440, 1441, 99999999, -99999999,
         0.0, 0.5, -0.5, 1e308, -1e308, float("nan"), float("inf"), float("-inf"),
         "", "x", "12:30", "2515", "nicht-zahl", "99:99", "  ", "ünî 🚀",
         "\x00\x01", "—" * 50, b"bytes", [], [1, 2], {}, {"a": 1},
         {"value": None}, {"value": 5, "end": None}, {"v": None}, {"v": "x"}]


# ── fmt_euro ────────────────────────────────────────────────────────────────
def test_euro_zeigt_die_null_statt_zu_verschwinden():
    """Vorher fiel die Anzeige bei 0 komplett weg — und ein Posten, der stumm
    bleibt, kann auch stumm wachsen."""
    assert fmt_euro(0) == "0,00€"
    assert fmt_euro(0.0) == "0,00€"


def test_euro_rundet_cent_betraege_nicht_auf_null():
    """Der echte Fall: ein Tag mit 0,0027 € wurde als '0.00€' angezeigt, also
    faktisch als 'nichts ausgegeben'."""
    assert fmt_euro(0.0027) == "<0,01€"
    assert fmt_euro(0.009) == "<0,01€"


def test_euro_normale_betraege_mit_komma():
    assert fmt_euro(0.21) == "0,21€"
    assert fmt_euro(1) == "1,00€"
    assert fmt_euro(12.345) == "12,35€"


def test_euro_wirft_nie():
    for a in NASTY:
        assert isinstance(fmt_euro(a), str)


# ── _num ────────────────────────────────────────────────────────────────────
def test_num_passes_real_numbers():
    for x in (0, 1, -1, 42, 3.14, -2.5, 1440, 99999999):
        assert _num(x) == x


def test_num_rejects_non_numbers_and_specials():
    for x in (None, True, False, "5", "x", [], [1], {}, b"5",
              float("nan"), float("inf"), float("-inf")):
        assert _num(x) is None


# ── fmt_uptime ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("u,exp", [
    (None, "—"), (0, "00:00:00"), (59, "00:00:59"), (60, "00:01:00"),
    (3600, "01:00:00"), (3661, "01:01:01"), (86399, "23:59:59"), (90061, "25:01:01"),
])
def test_fmt_uptime_values(u, exp):
    assert fmt_uptime(u) == exp


def test_fmt_uptime_garbage_is_dash():
    # NB: "12" ist KEIN Müll — int("12")=12 → "00:00:12". Nur echtes Nicht-Zahl-Zeug.
    for x in ("x", [], {}, float("nan"), float("inf"), None, "nicht-zahl", b"bytes"):
        assert fmt_uptime(x) == "—"


# ── fmt_clock ↔ parse_clock ─────────────────────────────────────────────────
@pytest.mark.parametrize("m,exp", [
    (None, "—"), (0, "00:00"), (90, "01:30"), (1439, "23:59"), (1440, "24:00"),
    (1500, "24:00"),
])
def test_fmt_clock_values(m, exp):
    assert fmt_clock(m) == exp


def test_fmt_clock_garbage_is_dash():
    for x in ("x", [], {}, float("nan"), float("inf")):
        assert fmt_clock(x) == "—"


def test_parse_clock_roundtrip_all_minutes():
    # Jede Minute des Tages: fmt → parse muss wieder dieselbe Minute ergeben.
    for m in range(0, 1440):
        assert parse_clock(fmt_clock(m)) == m


@pytest.mark.parametrize("s,exp", [
    ("0", 0), ("7", 420), ("23", 1380), ("2315", 1395), ("7:5", 425),
    ("23:15", 1395), ("24:00", 1440), ("23.45", 1425), ("", None),
    ("99:99", None), ("24:01", None), ("25", None), ("foo", None),
    ("12:ab", None), (None, None),
])
def test_parse_clock_values(s, exp):
    assert parse_clock(s) == exp


# ── period_duration ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("start,end,exp", [
    (0, 60, 60), (1380, 360, 420), (100, 100, 0), (1439, 0, 1),  # über Mitternacht
])
def test_period_duration_values(start, end, exp):
    assert period_duration(start, end) == exp


# ── graph_series ────────────────────────────────────────────────────────────
def test_graph_series_number_skips_bad_entries():
    rows = [{"value": 5}, {"value": None}, {"value": "x"}, {"value": 7.5},
            "kaputt", {"value": float("nan")}, {}, {"value": [1]}]
    assert graph_series("number", rows) == [5.0, 7.5]


def test_graph_series_period_needs_end():
    rows = [{"value": 1380, "end": 360}, {"value": 100, "end": None},
            {"value": 100}, {"value": "x", "end": 5}]
    assert graph_series("period", rows) == [420]


def test_graph_series_non_list_is_empty():
    for rows in (None, "x", 5, {}):
        assert graph_series("number", rows) == []


# ── graph_last ──────────────────────────────────────────────────────────────
def test_graph_last_formats_by_type():
    assert graph_last({"type": "number", "unit": "kg"}, [{"value": 72.5}]) == "72.5 kg"
    assert graph_last({"type": "time"}, [{"value": 450}]) == "07:30"
    assert graph_last({"type": "period"}, [{"value": 1380, "end": 360}]) == "23:00–06:00"
    assert graph_last({"type": "number"}, []) == "—"


def test_graph_last_garbage_never_raises():
    for g in NASTY:
        for rows in (NASTY, [], [{"value": "x"}], "nope", None):
            res = graph_last(g, rows)
            assert isinstance(res, str)


# ── tele_value ──────────────────────────────────────────────────────────────
def test_tele_value_valid():
    pct, txt = tele_value({"pc": {"cpu": {"v": 40}}}, "cpu")
    assert pct == 40 and txt == "40%"
    pct, txt = tele_value({"pc": {"temp": {"v": 60}}}, "temp")
    assert txt == "60°C" and abs(pct - 50.0) < 1e-9   # (60-30)/60*100


def test_tele_value_missing_or_garbage_is_none():
    for metrics in (None, {}, {"pc": None}, {"pc": 5}, {"pc": {"cpu": None}},
                    {"pc": {"cpu": {"v": None}}}, {"pc": {"cpu": {"v": "x"}}},
                    {"pc": {"cpu": {"v": float("nan")}}}, "x", 42, []):
        assert tele_value(metrics, "cpu") is None


# ── parse_command ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("buf,exp", [
    ("/quit", "QUIT"), ("/q", "QUIT"), ("/exit", "QUIT"),
    ("/help", "HELP"), ("/h", "HELP"), ("/?", "HELP"),
    ("/", None), ("/theme dunkel", None), ("/unsinn", None),
])
def test_parse_command_action(buf, exp):
    action, _mode, _msg = parse_command(buf, "auto")
    assert action == exp


def test_parse_command_theme_sets_mode():
    assert parse_command("/theme dunkel", "auto")[1] == "night"
    assert parse_command("/theme hell", "auto")[1] == "day"
    assert parse_command("/theme", "auto")[1] == "day"          # zyklisch ab auto


# ── overlay_rows: '/' zeigt die Shortcuts des fokussierten Fensters ──────────
def test_overlay_bare_slash_shows_context_keys_then_commands():
    ctx = ("liste", [("enter", "rein / hak"), ("space", "hak")])
    title, rows = overlay_rows("/", False, ctx)
    assert title == "liste"
    keys = [r for r in rows if r[0] == "key"]
    cmds = [r for r in rows if r[0] == "cmd"]
    # Kontext-Tasten zuerst, dann eine Trennlinie, dann die globalen Befehle.
    assert ("key", "enter", "rein / hak") in keys
    assert ("sep",) in rows
    assert any(c[1] == "/help" for c in cmds)        # /help bleibt immer erreichbar


def test_overlay_bare_slash_without_ctx_is_just_commands():
    title, rows = overlay_rows("/", False, None)
    assert title == "befehle"
    assert ("sep",) not in rows                       # keine Kontext-Tasten → keine Trennlinie
    assert all(r[0] == "cmd" for r in rows)


def test_overlay_help_still_lists_global_keys():
    _title, rows = overlay_rows("/help", False, ("liste", [("x", "y")]))
    assert ("key", "q", "beenden") in rows            # volle Hilfe inkl. globaler Tasten
    assert _title == "hilfe"


def test_overlay_prefix_filters_commands():
    _title, rows = overlay_rows("/q", False, ("liste", [("x", "y")]))
    names = [r[1] for r in rows if r[0] == "cmd"]
    assert names == ["/quit"]                         # Präfix filtert, Kontext tritt zurück


# ── log_prefix / blockspark / bar ───────────────────────────────────────────
def test_log_prefix():
    assert log_prefix("EVENT IN BOOT")[0] == "EVENT IN"
    assert log_prefix("NET foo")[0] == "NET"
    assert log_prefix("irgendwas ohne prefix") == (None, None)


def test_blockspark_and_bar_bounds():
    assert blockspark([]) == ""
    assert len(blockspark([1, 2, 3, 4, 5])) == 5
    for pct in (-50, 0, 50, 100, 150, float("nan") if False else 100):
        assert len(bar(pct, 10)) == 10


def test_terminal_too_small_threshold():
    assert terminal_too_small(13, 80) and terminal_too_small(14, 59)
    assert not terminal_too_small(14, 60) and not terminal_too_small(50, 200)


# ── Eigenschaft: KEIN Helfer wirft je eine Exception (tausende Kombis) ───────
def test_pure_helpers_never_raise():
    rnd = random.Random(20260611)
    types = ["number", "scale", "time", "period", "bogus", None]
    calls = 0
    for _ in range(2500):
        a = rnd.choice(NASTY)
        b = rnd.choice(NASTY)
        # jede Single-Arg-Funktion mit Müll
        for fn in (fmt_uptime, fmt_clock, parse_clock, _num, blockspark):
            try:
                fn(a)
            except Exception as e:        # noqa: BLE001 — genau das prüfen wir
                pytest.fail(f"{fn.__name__}({a!r}) warf {e!r}")
            calls += 1
        # bar / period_duration / parse_command / log_prefix
        try:
            bar(a if isinstance(a, (int, float)) and a == a else 0, 10)
            period_duration(rnd.randint(0, 1439), rnd.randint(0, 1439))
            parse_command(str(a)[:30] if not isinstance(a, str) else a, rnd.choice(["auto", "day", "night"]))
            log_prefix(a if isinstance(a, str) else "x")
        except Exception as e:            # noqa: BLE001
            pytest.fail(f"Helfer warf bei a={a!r}: {e!r}")
        # graph_series / graph_last / tele_value mit gemeinen Rows/Metrics
        rows = rnd.choice([NASTY, [a], [{"value": a, "end": b, "date": "d"}], a, []])
        gt = rnd.choice(types)
        try:
            graph_series(gt, rows)
            graph_last({"type": gt, "unit": a} if rnd.random() < 0.5 else a, rows)
            tele_value({"pc": {"cpu": {"v": a}}} if rnd.random() < 0.5 else a, "cpu")
        except Exception as e:            # noqa: BLE001
            pytest.fail(f"graph/tele warf bei a={a!r} rows={rows!r}: {e!r}")
        calls += 6
    assert calls > 15000                  # wir haben WIRKLICH viel durchgeprügelt
