"""werkzeug_schleife.run_tool fragt das Register statt fester Namen
(Aufräumen aus Phase 0, erledigt in Phase 3 des Claude-Web-Plans, 2026-10-07).

Vorher stand in run_tool je ein Zweig für "antwort", "read_news" und
"ask_choice", obwohl das Register `terminal` und `in_der_schleife` kennt —
zwei Wahrheiten. Jetzt entscheidet das Register; diese Tests beweisen, dass
das Verhalten gleich blieb (Events, Rückgabe, Alias-Namen, Tutor), und
halten Register und Schleife deckungsgleich.
"""
import ast
import inspect

import pytest

import ki_antwort
import ki_werkzeuge  # noqa: F401  — meldet die Ausführer im Register an
import werkzeug_register
import werkzeug_schleife


def _fahren(name, args, tutor_mode=False, exec_=None):
    aufgerufen = []

    def active_exec(n, a):
        aufgerufen.append((n, a))
        return exec_(n, a) if exec_ else "ergebnis"
    gen = werkzeug_schleife.run_tool(name, args, tutor_mode=tutor_mode,
                                     active_exec=active_exec, user_query="frage", store=None)
    ereignisse = []
    try:
        while True:
            ereignisse.append(gen.send(None))
    except StopIteration as ende:
        return ereignisse, ende.value, aufgerufen


@pytest.fixture(autouse=True)
def bilder_attrappe(monkeypatch):
    def mit_bildern(text, user_query, store=None):
        yield "ANTWORT:" + text
    monkeypatch.setattr(ki_antwort, "mit_bildern", mit_bildern)


def test_antwort_ist_terminal_und_laeuft_ohne_ausfuehrer():
    ev, aus, auf = _fahren("antwort", {"text": "  Hallo  "})
    assert ev[0] == {"werkzeug": {"phase": "start", "name": "antwort",
                                  "args": {"text": "  Hallo  "}}}
    assert ev[1:] == ["ANTWORT:Hallo"]
    assert aus == ("stop",) and auf == []


@pytest.mark.parametrize("name", ["read_news", "lies_news"])
def test_news_ist_terminal_mit_kino_und_ohne_kopf(name):
    ev, aus, auf = _fahren(name, {"tage": 7},
                           exec_=lambda n, a: "Sendung (Stand 12:00):\n\nGuten Tag.")
    assert ev[1:] == [{"cinema": True}, "Guten Tag."]
    assert aus == ("stop",) and auf == [("read_news", {"tage": 7})]
    # Ohne Kopf bleibt der Text, wie er ist.
    ev, _, _ = _fahren(name, {}, exec_=lambda n, a: "Nur Text.")
    assert ev[-1] == "Nur Text."


@pytest.mark.parametrize("name", ["ask_choice", "frage_knopf"])
def test_knopf_dialog_gibt_die_wahl_zurueck(name, monkeypatch):
    def knopf(args):
        yield {"permission": {"frage": args.get("frage"), "optionen": ["a", "b"]}}
        return "b"
    monkeypatch.setattr(werkzeug_schleife, "_ask_buttons", knopf)
    ev, aus, auf = _fahren(name, {"frage": "Welche?", "optionen": ["a", "b"]})
    assert ev[1] == {"permission": {"frage": "Welche?", "optionen": ["a", "b"]}}
    assert aus == ("result", "Sasha hat gewählt: b.", False) and auf == []


def test_im_tutor_gibt_es_keine_sonderwege():
    for name in ("antwort", "read_news", "ask_choice"):
        ev, aus, auf = _fahren(name, {"x": 1}, tutor_mode=True)
        assert aus == ("result", "ergebnis", False), name
        assert auf == [(name, {"x": 1})]
        assert {"cinema": True} not in ev


def test_normales_werkzeug_bleibt_normal():
    ev, aus, auf = _fahren("read_note", {"name": "x"})
    assert aus == ("result", "ergebnis", False)
    assert [e["werkzeug"]["phase"] for e in ev] == ["start", "fertig"]


def test_register_und_schleife_sind_deckungsgleich():
    """Jedes Register-Werkzeug, das die Schleife selbst erledigt, hat dort
    einen Weg — und umgekehrt. Jedes andere terminale hat einen Ausführer."""
    selbst = {w.name for w in werkzeug_register.WERKZEUGE if w.in_der_schleife}
    assert selbst == set(werkzeug_schleife.SELBST)
    for w in werkzeug_register.WERKZEUGE:
        if w.terminal and not w.in_der_schleife:
            assert w.ausfuehrer is not None, w.name


def test_run_tool_nennt_keine_werkzeug_namen_mehr():
    """Die Namen stehen im Register, nicht als Zweige in run_tool."""
    baum = ast.parse(inspect.getsource(werkzeug_schleife.run_tool))
    texte = {k.value for k in ast.walk(baum)
             if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    namen = {w.name for w in werkzeug_register.WERKZEUGE} | set(werkzeug_register.ALIASE)
    assert not (texte & namen), texte & namen
