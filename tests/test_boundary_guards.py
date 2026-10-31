"""Boundary guards E5, E7, E8 (memory/hub/kern_auszug_inventur.md section E,
built 2026-10-31 with lists step 3). Read-only tests, seconds to run; they
stop new copies, new data files in the surface and route clashes before more
apps leave the core.

E5  no copies in tui/: a comment or docstring that says it mirrors core
    ("wie core/…", "copy of core/…", "same rule as core/…") or a constant
    with the same name AND value as a core constant is a second truth.
    Today's known copies are a legacy list that may only SHRINK.
E7  no data files written from tui/: open(…, "w"/"a"/"x"), json.dump,
    os.replace/rename, shutil.move/copy, write_text/write_bytes only at the
    places on an allowlist — the log, device settings under ~/.config or
    ~/.local/state/zentrale, temp/cache files. Domain state belongs to the core.
E8  route ownership: every path belongs to the hub or to exactly one app (per
    `routen` in its app.toml); an app must not shadow a hub route, two apps
    must not claim the same path, and forwarding happens only in the one
    hook (ui/routen/hub_apps.py).
"""
import ast
import io
import os
import re
import tokenize

try:
    import tomllib
except ImportError:                      # Python < 3.11
    tomllib = None

import apps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TUI = os.path.join(ROOT, "tui")
CORE = os.path.join(ROOT, "core")
INVENTORY = "memory/hub/kern_auszug_inventur.md"


def _py(folder):
    for d, _dirs, files in os.walk(folder):
        if "__pycache__" in d:
            continue
        for f in sorted(files):
            if f.endswith(".py"):
                yield os.path.join(d, f)


def _rel(path):
    return os.path.relpath(path, ROOT)


# ── E5: no copies in tui/ ─────────────────────────────────────────────

COPY_MARK = re.compile(
    r"(\bwie\b|\bas in\b|\bsame \w+ as\b|\bdieselben? \w+ wie\b|\bcopy of\b|\bkopie\b"
    r"|\bmirrors?\b|\bgespiegelt\b|\bspiegel\w*\b)[^\n]{0,20}?\b(core/[\w./]+)", re.I)


def _module_constants(path):
    """NAME → literal value of the module-level UPPER_CASE constants."""
    out = {}
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            name = n.targets[0].id
            if name.lstrip("_").isupper():
                try:
                    out[name] = ast.literal_eval(n.value)
                except (ValueError, SyntaxError, TypeError):
                    pass
    return out


def copies_in_tui():
    """{(file, what)}: what = "says core/<ref>" or "constant <NAME>"."""
    core = {}
    for p in _py(CORE):
        for name, value in _module_constants(p).items():
            core.setdefault(name, []).append(value)
    found = set()
    for p in _py(TUI):
        with open(p, encoding="utf-8") as f:
            src = f.read()
        texts = [t.string for t in tokenize.generate_tokens(io.StringIO(src).readline)
                 if t.type in (tokenize.COMMENT, tokenize.STRING)]
        for text in texts:
            for m in COPY_MARK.finditer(text):
                found.add((_rel(p), "says " + m.group(2).rstrip(".,;:)")))
        for name, value in _module_constants(p).items():
            if any(value == v and type(value) is type(v) for v in core.get(name, ())):
                found.add((_rel(p), "constant " + name))
    return found


# Known copies on 2026-10-31 (row of the inventory, section A, where there is
# one). May only SHRINK: pull a value from its route, then strike it here.
COPIES_LEGACY = {
    ("tui/ansichten/kalender_advanced.py", "says core/kalender_deadline.dauer_lesen"): "A2",
    ("tui/ansichten/kalender_deadline.py", "says core/kalender_deadline.py"): "A5",
    ("tui/ansichten/kalender_deadline.py", "constant TYP"): "A5",
    ("tui/ansichten/kalender_deadline.py", "constant WT"): "A5",
    ("tui/ansichten/kalender_motive.py", "says core/kalender_rhythmus.EBENE"): "A7",
    ("tui/ansichten/kalender_motive.py", "constant EBENE"): "A7",
    ("tui/ansichten/projekte.py", "says core/projekte.MAX_WISSEN_BYTES"): "A18",
    ("tui/ansichten/schematix_draht.py", "says core/schematix_run.fits"): "A20",
    ("tui/ansichten/schematix.py", "constant LAYERS"): "A20 (Schematix)",
    ("tui/ansichten/notizen.py", "says core/notes"): "A14 (n_float_pos)",
    ("tui/ansichten/desk_kacheln.py", "says core/kacheln.GROESSE_GRENZE"): "-",
    ("tui/ansichten/chat_ablage.py", "says core/anhang.DATEI_MAX_BYTES"): "-",
    ("tui/ansichten/chat_ablage.py", "says core/ablage.BILD_MAX_BYTES"): "-",
    ("tui/ansichten/bewertung.py", "says core/rueckmeldungen.KOMMENTAR_MAX"): "-",
    ("tui/ansichten/bewertung.py", "constant KOMMENTAR_MAX"): "-",
    ("tui/ansichten/gespraechsliste.py", "says core/gespraeche.py"): "-",
    ("tui/ansichten/gespraechsliste.py", "constant ERINNERUNGEN"): "-",
    ("tui/ansichten/chat_gespraeche.py", "constant ERINNERUNGEN"): "-",
    ("tui/ansichten/chat.py", "constant VERMERK_ABGEBROCHEN"): "-",
    ("tui/ansichten/desk_neu.py", "says core/adressen.wert_text"): "-",
    ("tui/ansichten/desk_neu.py", "constant SCHEMA"): "-",
    ("tui/ansichten/sprung.py", "says core/adressen.py"): "-",
    ("tui/ansichten/sprung.py", "constant SCHEMA"): "-",
    ("tui/ansichten/kalender_gruppen.py", "constant KEINE"): "-",
    ("tui/ansichten/kalender_gruppen.py", "constant CUSTOM"): "-",
    ("tui/ansichten/kalender_werkzeuge.py", "constant UNVERBINDLICH"): "-",
    ("tui/ansichten/kalender_ansichten.py", "constant UNVERBINDLICH"): "-",
    ("tui/ansichten/kalender_ansichten.py", "constant WT"): "-",
    ("tui/ansichten/kalender_ansichten.py", "constant MONATE"): "-",
    ("tui/ansichten/kalender_beispiel.py", "constant MONATE"): "-",
    ("tui/ansichten/translate.py", "constant DEFAULT_LANGUAGE"): "-",
    ("tui/ansichten/zugang_klient.py", "constant VORGABE_PFAD"): "-",
    ("tui/bausteine/canvas_bild.py", "constant MODI"): "-",
}


def test_e5_no_new_copies_in_tui():
    new = sorted(copies_in_tui() - set(COPIES_LEGACY))
    assert not new, (
        "New copy of a core value/rule in tui/: %s. The surface takes the value "
        "from its route (answer, error sentence, schema) instead of writing it "
        "down a second time (%s, guard E5)." % (new, INVENTORY))


def test_e5_legacy_only_shrinks():
    gone = sorted(set(COPIES_LEGACY) - copies_in_tui())
    assert not gone, "Well done — %s is no copy any more: strike it in COPIES_LEGACY." % gone


def test_e5_catches_a_copy(monkeypatch):
    """The scanner itself: a marker comment and a same-name constant count."""
    assert COPY_MARK.search("X = 3   # wie core/foo.X")
    assert COPY_MARK.search('"""Same rule as core/bar.fits."""')
    assert not COPY_MARK.search("# holt core/foo über HTTP")


# ── E7: no data files written from tui/ ──────────────────────────────

WRITE_CALLS = {"json.dump", "os.replace", "os.rename", "shutil.move", "shutil.copy",
               "shutil.copyfile", "shutil.copy2"}
WRITE_METHODS = {"write_text", "write_bytes"}


def _call_name(node):
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.value.id + "." + f.attr
    if isinstance(f, ast.Attribute):
        return "." + f.attr
    return ""


def _mode(node):
    """The mode of an open()/fdopen() call: literal text, None (read), or "?"."""
    mode = node.args[1] if len(node.args) > 1 else next(
        (k.value for k in node.keywords if k.arg == "mode"), None)
    if mode is None:
        return None
    if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
        return mode.value
    return "?"


def writes_in_tui():
    """{(file, function, call)} of every place in tui/ that writes a file."""
    found = set()
    for p in _py(TUI):
        with open(p, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        owner = {}
        for fn in funcs:                         # innermost function wins (walk is outer first)
            for n in ast.walk(fn):
                owner[id(n)] = fn.name
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            name = _call_name(n)
            what = None
            if name in ("open", "os.fdopen", "io.open"):
                mode = _mode(n)
                if mode is not None and (mode == "?" or set(mode) & set("wax+")):
                    what = name
            elif name in WRITE_CALLS or name.lstrip(".") in WRITE_METHODS and name.startswith("."):
                what = name
            if what:
                found.add((_rel(p), owner.get(id(n), "<module>"), what))
    return found


# Allowed writers: (file, function) → why it is not domain state.
WRITES_ALLOWED = {
    ("tui/boot_loader.py", "_start_sync"): "log: /tmp boot log of the sync",
    ("tui/zentrale_tui.py", "schalter_schreiben"): "device setting under ~/.config (theme lock)",
    ("tui/zentrale_tui.py", "lebenslauf"): "log: ~/.local/state/zentrale/tui.log",
    ("tui/zentrale_tui.py", "main"): "log: crash log / frame error log",
    ("tui/ansichten/desk.py", "_bild_holen"): "temp: picture copy for the viewer",
    ("tui/ansichten/projekte.py", "anweisungen_bearbeiten"): "temp: file for the external editor",
    ("tui/ansichten/gedaechtnis.py", "bearbeiten"): "temp: file for the external editor",
    ("tui/ansichten/chat_bedienung.py", "kopieren"): "cache: ~/.cache/zentrale/kopie.txt (clipboard)",
    ("tui/ansichten/tasten_zaehler.py", "speichern"): "device state: ~/.local/state key counters",
    ("tui/ansichten/tasten_zaehler.py", "_kaputt"): "device state: a broken counter file set aside",
    ("tui/ansichten/app_start.py", "_starten"): "log: /tmp window log of an app",
    ("tui/ansichten/karte.py", "m_window"): "log: /tmp map window log",
}


def test_e7_tui_writes_only_on_the_allowlist():
    found = writes_in_tui()
    unknown = sorted(w for w in found if w[:2] not in WRITES_ALLOWED)
    assert not unknown, (
        "tui/ writes a file here: %s. Domain state is the core's (a route); "
        "the surface writes only logs, device settings under ~/.config or "
        "~/.local/state/zentrale and temp files — then add it to "
        "WRITES_ALLOWED with the reason (guard E7, %s)." % (unknown, INVENTORY))


def test_e7_allowlist_has_no_dead_entries():
    used = {w[:2] for w in writes_in_tui()}
    dead = sorted(set(WRITES_ALLOWED) - used)
    assert not dead, "WRITES_ALLOWED names places that no longer write: %s — strike them" % dead


# ── E8: route ownership ──────────────────────────────────────────────

def _segments(rule):
    return [s for s in rule.split("/") if s]


def _covers(prefix, rule):
    """Does an app prefix (e.g. /api/map) catch this hub rule? A converter
    segment (<lid>) in the rule may be anything, so it can be caught."""
    p, r = _segments(prefix), _segments(rule)
    if len(r) < len(p):
        return False
    return all(a == b or (b.startswith("<") and b.endswith(">")) for a, b in zip(p, r))


def ownership_problems(hub_rules, manifests):
    """[text] of every clash: an app prefix that shadows a hub rule, or two
    apps (or one app twice) claiming the same or a nested path."""
    problems = []
    claims = [(r, str(m.get("name"))) for m in manifests for r in apps.routen(m)]
    for prefix, app in claims:
        for rule in hub_rules:
            if _covers(prefix, rule):
                problems.append("app %s's %s shadows the hub route %s" % (app, prefix, rule))
    for i, (p1, a1) in enumerate(claims):
        for p2, a2 in claims[i + 1:]:
            if _covers(p1, p2) or _covers(p2, p1):
                problems.append("%s (%s) and %s (%s) claim the same path" % (p1, a1, p2, a2))
    return problems


def _hub_rules():
    from ui.app import app
    return sorted({r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"})


def _known_manifests():
    """The manifests of apps this node knows (installed in the test's world)
    and of the app repos next to ZENTRALE (zentrale-karte, language-tutor, …)."""
    found = list(apps.installiert())
    if tomllib is not None:
        parent = os.path.dirname(os.path.realpath(ROOT))
        while os.path.basename(parent) in ("worktrees", ".claude") or \
                os.path.basename(os.path.dirname(parent)) == "worktrees":
            parent = os.path.dirname(parent)          # a worktree: up to the repo's folder
        if os.path.basename(parent) == "ZENTRALE":
            parent = os.path.dirname(parent)
        for name in sorted(os.listdir(parent)) if os.path.isdir(parent) else []:
            path = os.path.join(parent, name, "app.toml")
            if name != "ZENTRALE" and os.path.isfile(path):
                with open(path, "rb") as f:
                    m = tomllib.load(f)
                if not any(k.get("name") == m.get("name") for k in found):
                    found.append(m)
    return found


def test_e8_no_app_shadows_the_hub_and_no_path_has_two_apps():
    problems = ownership_problems(_hub_rules(), _known_manifests())
    assert not problems, (
        "Route ownership (guard E8, %s): %s. A path belongs to the hub or to "
        "exactly one app — when a module moves out, its hub routes go in the "
        "same commit." % (INVENTORY, problems))


def test_e8_checker_catches_clashes():
    hub = ["/api/lists", "/api/lists/<lid>/bild", "/api/calendar", "/hub/gesund"]
    karte = {"name": "karte", "start": "x", "adresse": "http://127.0.0.1:1", "routen": ["/api/map"]}
    shadow = dict(karte, name="schatten", routen=["/api/lists"])
    twin = dict(karte, name="zwilling", routen=["/api/map/base"])
    assert ownership_problems(hub, [karte]) == []
    assert any("shadows the hub route /api/lists/<lid>/bild" in p
               for p in ownership_problems(hub, [shadow]))
    assert any("claim the same path" in p for p in ownership_problems(hub, [karte, twin]))
    assert not _covers("/api/map", "/api/mapx")


def test_e8_forwarding_only_in_the_one_hook():
    """Only ui/routen/hub_apps.py asks who owns a path and forwards."""
    callers = set()
    for folder in ("core", "ui", "tui", "scripts"):
        for p in _py(os.path.join(ROOT, folder)):
            with open(p, encoding="utf-8") as f:
                src = f.read()
            if re.search(r"app_weiterleitung\.(besitzer|weiterleiten)\(", src):
                callers.add(_rel(p))
    assert callers == {"ui/routen/hub_apps.py"}, callers
