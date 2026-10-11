"""
Wächter: die Testsuite bleibt schnell, weil ihre Grundfixtures billig bleiben.

Anlass (10.10.2026): Die volle Suite brauchte 16+ Minuten, etwa die Hälfte
davon ging auf die Fixture-Architektur. Acht autouse-Fixtures in conftest.py
holten sich bei JEDEM Test per `tmp_path_factory.mktemp()` einen Ordner (9
Aufrufe pro Test). pytest liest bei jedem mktemp den ganzen Basetemp-Ordner
(make_numbered_dir sucht die nächste freie Nummer) — am Ende 30–37 Tsd.
Einträge, die Kosten wuchsen quadratisch. Regeln und Messwerte:
memory/betrieb/tests.md.

Geprüft wird statisch (AST), damit die Regel nicht erst auffällt, wenn die
Suite wieder langsam geworden ist.
"""
import ast
import functools
import os

TESTS = os.path.dirname(os.path.abspath(__file__))


def _ist_fixture(dekorator):
    """(ist_fixture, scope, autouse) für einen Dekorator-Knoten."""
    knoten = dekorator.func if isinstance(dekorator, ast.Call) else dekorator
    name = getattr(knoten, "attr", None) or getattr(knoten, "id", None)
    if name != "fixture":
        return False, None, False
    scope, autouse = "function", False
    if isinstance(dekorator, ast.Call):
        for kw in dekorator.keywords:
            if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                scope = kw.value.value
            if kw.arg == "autouse" and isinstance(kw.value, ast.Constant):
                autouse = bool(kw.value.value)
    return True, scope, autouse


@functools.lru_cache(maxsize=None)
def _fixtures(pfad):
    baum = ast.parse(open(pfad, encoding="utf-8").read(), pfad)
    gefunden = []
    for f in ast.walk(baum):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in f.decorator_list:
                ist, scope, autouse = _ist_fixture(d)
                if ist:
                    gefunden.append((f, scope, autouse))
    return tuple(gefunden)


def _testdateien():
    for name in sorted(os.listdir(TESTS)):
        if name.endswith(".py"):
            yield os.path.join(TESTS, name)


def _ruft_mktemp(funktion):
    return any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "mktemp" for n in ast.walk(funktion))


def test_keine_funktions_fixture_ruft_mktemp():
    """tmp_path_factory.mktemp nur im Sitzungs-/Modul-Scope — nie pro Test."""
    verstoesse = []
    for pfad in _testdateien():
        if "mktemp" not in open(pfad, encoding="utf-8").read():
            continue                # billiger Vorfilter: nur verdächtige parsen
        for f, scope, _autouse in _fixtures(pfad):
            if scope == "function" and _ruft_mktemp(f):
                verstoesse.append("%s::%s" % (os.path.basename(pfad), f.name))
    assert not verstoesse, (
        "Funktions-Fixtures mit mktemp (pro Test ein Basetemp-Scan, wächst "
        "quadratisch; siehe memory/betrieb/tests.md): %s" % verstoesse)


def test_conftest_autouse_holt_sich_keinen_eigenen_tmp_ordner():
    """Autouse-Fixtures in conftest.py laufen bei JEDEM Test der Suite: sie
    nehmen den einen Ordner `_test_ordner` (+ `_frisch()`), nicht tmp_path /
    tmp_path_factory. (Autouse in einer Testdatei darf tmp_path nehmen — das
    ist derselbe eine Ordner, den der Test ohnehin hat.)"""
    verstoesse = []
    for f, scope, autouse in _fixtures(os.path.join(TESTS, "conftest.py")):
        if autouse and scope == "function":
            argumente = {a.arg for a in f.args.args}
            if argumente & {"tmp_path", "tmpdir", "tmp_path_factory", "tmpdir_factory"}:
                verstoesse.append(f.name)
    assert not verstoesse, (
        "conftest-Autouse mit eigenem tmp-Ordner (nimm `_test_ordner` und "
        "`_frisch()`): %s" % verstoesse)


def test_der_test_ordner_ist_pro_test_frisch(_test_ordner):
    """Die eine Umlenkung pro Test: frisch, und die Unterordner sind leer."""
    assert _test_ordner.is_dir()
    unter = sorted(p.name for p in _test_ordner.iterdir())
    assert "kalender_default" in unter and "listen_graphen" in unter
    assert all(not any((_test_ordner / u).iterdir()) for u in unter)


def test_umlenkungen_liegen_im_test_ordner(_test_ordner):
    import gespraeche
    import kalender
    import lists
    for pfad in (kalender.CAL_PATH, gespraeche._DIR, lists._REGISTRY,
                 os.environ["ZENTRALE_ABLAGE_DIR"],
                 os.environ["ZENTRALE_DESK_ORDNER"],
                 os.environ["ZENTRALE_SHOP_ORDNER"]):
        assert str(pfad).startswith(str(_test_ordner)), pfad
