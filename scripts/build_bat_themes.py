#!/usr/bin/env python3
"""
build_bat_themes.py — erzeugt die zwei bat-Themes aus DERSELBEN Palette wie nvim.

  bat/themes/zentrale-cyber.tmTheme   (night)
  bat/themes/zentrale-paper.tmTheme   (day)

Warum generiert und nicht von Hand gepflegt? Die Paletten in
`nvim/lua/zentrale_theme/palettes.lua` sind schon zweimal nachjustiert worden
(Papier von Creme auf Sepia, Akzente neu gegen die Fläche gerechnet). Zwei
handgepflegte XML-Dateien daneben wären beim dritten Mal still auseinander-
gelaufen. Also: eine Quelle, ein Generator — und `tests/test_bat_theme.py`
schlägt Alarm, sobald die eingecheckten Dateien nicht mehr dazu passen.

BEWUSSTER UNTERSCHIED ZU NVIM — die Fläche:
nvim setzt sich vom Terminal ab (Sepia #ece0c0 gegen Terminal-Creme #f3ecd9),
damit man sieht, dass man IM Editor ist. bat ist kein Editor, sondern
Terminal-Ausgabe: es soll nahtlos in den umgebenden Text fließen, ohne
sichtbaren Kasten um den Code. Deshalb erbt bat Fläche und Grundtext vom
TERMINAL (`scripts/zentrale-term-theme`), und nur die Syntaxfarben kommen aus
der nvim-Palette. Die sind gegen die (dunklere) nvim-Fläche gerechnet; auf dem
helleren Terminal-Papier wird ihr Kontrast dadurch besser, nie schlechter.

Aufruf: python3 scripts/build_bat_themes.py [--check]
  --check schreibt nichts, sondern meldet nur, ob die Dateien aktuell sind
          (Exit 1 bei Drift) — das nutzt der Test.
"""
import argparse
import os
import re
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PALETTES_LUA = os.path.join(ROOT, "nvim", "lua", "zentrale_theme", "palettes.lua")
TERM_APPLIER = os.path.join(ROOT, "scripts", "zentrale-term-theme")
OUT_DIR = os.path.join(ROOT, "bat", "themes")

# Fläche + Grundtext kommen vom Terminal, nicht aus der nvim-Palette (s.o.).
# Gelesen wird beides aus scripts/zentrale-term-theme, damit auch DAS eine
# Quelle bleibt — steht dort ein neues Papier, zieht bat mit.
TERM_KEYS = ("BG", "FG", "SEL_BG", "CURSOR")


def read_lua_palettes(path=PALETTES_LUA):
    """Die zwei Paletten aus palettes.lua ziehen → {"cyber": {...}, "paper": {...}}.

    Kein Lua-Interpreter: die Datei ist eine flache Tabelle aus
    `schluessel = "#rrggbb",`-Zeilen. Wir schneiden sie an den beiden
    `M.<name> = {`-Köpfen auf und lesen die Paare per Regex. Bricht das je
    (weil jemand die Struktur umbaut), fliegt hier ein KeyError/ValueError —
    besser als still ein halbes Theme zu bauen.
    """
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    out = {}
    for name in ("cyber", "paper"):
        m = re.search(r"^M\.%s\s*=\s*\{(.*?)^\}" % name, src, re.S | re.M)
        if not m:
            raise ValueError("Palette M.%s in %s nicht gefunden" % (name, path))
        body = m.group(1)
        pal = dict(re.findall(r"(\w+)\s*=\s*\"(#[0-9a-fA-F]{6})\"", body))
        if not pal:
            raise ValueError("Palette M.%s enthält keine Farben" % name)
        out[name] = pal
    return out


def read_term_colors(path=TERM_APPLIER):
    """Fläche/Text/Auswahl/Cursor je Modus aus dem Terminal-Applier lesen.

    Der Applier setzt sie in einem `if [ "$resolved" = "night" ]`-Zweig; wir
    lesen beide Zweige getrennt aus, damit bat exakt dieselbe Fläche bekommt,
    die das xfce4-terminal bekommt.
    """
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r'if \[ "\$resolved" = "night" \]; then(.*?)^else(.*?)^fi',
                  src, re.S | re.M)
    if not m:
        raise ValueError("Farbzweige in %s nicht gefunden" % path)
    out = {}
    for mode, block in (("night", m.group(1)), ("day", m.group(2))):
        vals = dict(re.findall(r'(\w+)="(#[0-9a-fA-F]{6})"', block))
        missing = [k for k in TERM_KEYS if k not in vals]
        if missing:
            raise ValueError("%s: %s fehlen im %s-Zweig"
                             % (path, ", ".join(missing), mode))
        out[mode] = vals
    return out


def _d(pairs):
    """Kleines plist-<dict> aus (key, value)-Paaren; None-Werte fallen raus."""
    body = "".join("\n\t\t\t\t<key>%s</key>\n\t\t\t\t<string>%s</string>"
                   % (escape(k), escape(v)) for k, v in pairs if v)
    return "\t\t\t<dict>%s\n\t\t\t</dict>" % body


def _rule(name, scope, fg=None, style=None, bg=None):
    """Eine Scope-Regel (der <dict> mit name/scope/settings)."""
    settings = _d([("foreground", fg), ("background", bg), ("fontStyle", style)])
    return (
        "\t\t<dict>\n"
        "\t\t\t<key>name</key>\n\t\t\t<string>%s</string>\n"
        "\t\t\t<key>scope</key>\n\t\t\t<string>%s</string>\n"
        "\t\t\t<key>settings</key>\n%s\n"
        "\t\t</dict>" % (escape(name), escape(scope), settings)
    )


def build(theme_name, pal, term):
    """Ein vollständiges .tmTheme als String.

    Die Scope→Rolle-Zuordnung spiegelt bewusst `nvim/lua/zentrale_theme/
    highlights.lua`: dieselbe Rolle bekommt dieselbe Farbe, damit eine Datei in
    bat und in nvim gleich aussieht. Sublime-Scopes sind feiner als nvims
    Gruppen, deshalb stehen hier mehrere Scopes pro Rolle.
    """
    it = "italic"
    rules = [
        # ── Grundeinstellungen (kein scope) ──────────────────────────────
        "\t\t<dict>\n\t\t\t<key>settings</key>\n%s\n\t\t</dict>" % _d([
            ("background",      term["BG"]),
            ("foreground",      term["FG"]),
            ("caret",           term["CURSOR"]),
            ("selection",       term["SEL_BG"]),
            ("lineHighlight",   pal["bg_dim"]),
            # Zeilennummern-Spalte: bat malt sie mit gutterForeground.
            ("gutter",          term["BG"]),
            ("gutterForeground", pal["line_nr"]),
            ("invisibles",      pal["fg_faint"]),
        ]),

        _rule("Kommentar", "comment, punctuation.definition.comment",
              pal["fg_faint"], it),
        _rule("Zeichenkette", "string, string.quoted, punctuation.definition.string",
              pal["string"]),
        _rule("Escape in Zeichenkette", "constant.character.escape, "
              "constant.other.placeholder, string.regexp", pal["special"]),
        _rule("Zahl", "constant.numeric", pal["number"]),
        _rule("Konstante", "constant.language, constant.other, "
              "support.constant, variable.other.constant", pal["constant"]),
        _rule("Schluesselwort", "keyword, keyword.control, keyword.other, "
              "storage.modifier", pal["keyword"]),
        _rule("Operator", "keyword.operator, punctuation.separator, "
              "punctuation.terminator, punctuation.accessor, meta.brace",
              pal["fg_dim"]),
        _rule("Storage/Typ-Schluesselwort", "storage, storage.type",
              pal["type"]),
        _rule("Typ", "entity.name.type, entity.name.class, entity.name.struct, "
              "entity.name.enum, support.type, support.class, "
              "entity.other.inherited-class", pal["type"]),
        _rule("Funktion", "entity.name.function, support.function, "
              "meta.function-call, variable.function", pal["accent"]),
        _rule("Eigenschaft/Feld", "variable.other.member, variable.other.property, "
              "support.variable, meta.object-literal.key, "
              "entity.name.label", pal["property"]),
        _rule("Variable/Parameter", "variable, variable.parameter, "
              "variable.other", pal["fg"]),
        _rule("Tag", "entity.name.tag, punctuation.definition.tag",
              pal["keyword"]),
        _rule("Attribut", "entity.other.attribute-name", pal["property"]),
        _rule("Namensraum/Modul", "entity.name.namespace, entity.name.module, "
              "support.module", pal["type"]),
        _rule("Ungueltig", "invalid, invalid.illegal", pal["error"]),
        _rule("Veraltet", "invalid.deprecated", pal["warn"], it),

        # ── Markdown & Co. ───────────────────────────────────────────────
        _rule("Ueberschrift", "markup.heading, entity.name.section",
              pal["title"], "bold"),
        _rule("Fett", "markup.bold", pal["fg"], "bold"),
        _rule("Kursiv", "markup.italic", pal["fg"], it),
        _rule("Link", "markup.underline.link, string.other.link",
              pal["accent"], "underline"),
        _rule("Zitat", "markup.quote", pal["fg_faint"], it),
        _rule("Code im Text", "markup.raw, markup.inline.raw", pal["string"]),
        _rule("Liste", "markup.list punctuation.definition.list_item",
              pal["special"]),

        # ── diff: bat faerbt `git diff` mit genau diesen Scopes ──────────
        _rule("diff: hinzugefuegt", "markup.inserted, markup.inserted.diff",
              pal["ok"]),
        _rule("diff: entfernt", "markup.deleted, markup.deleted.diff",
              pal["error"]),
        _rule("diff: geaendert", "markup.changed, markup.changed.diff",
              pal["warn"]),
        _rule("diff: Kopfzeile", "meta.diff.header, meta.diff.range",
              pal["accent"], "bold"),
    ]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "\t<key>name</key>\n\t<string>%s</string>\n"
        "\t<key>settings</key>\n\t<array>\n%s\n\t</array>\n"
        "</dict>\n"
        "</plist>\n" % (escape(theme_name), "\n".join(rules))
    )


# Modus → (Theme-Name, Palette-Schlüssel). night/day wie überall im Projekt.
THEMES = {"night": ("zentrale-cyber", "cyber"), "day": ("zentrale-paper", "paper")}


def render_all():
    """→ {dateiname: inhalt} für beide Themes."""
    pals = read_lua_palettes()
    term = read_term_colors()
    return {"%s.tmTheme" % name: build(name, pals[key], term[mode])
            for mode, (name, key) in THEMES.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="nur pruefen, ob die eingecheckten Dateien aktuell sind")
    args = ap.parse_args(argv)

    files = render_all()
    if args.check:
        drift = []
        for fname, want in files.items():
            path = os.path.join(OUT_DIR, fname)
            try:
                with open(path, encoding="utf-8") as fh:
                    have = fh.read()
            except OSError:
                drift.append("%s fehlt" % fname)
                continue
            if have != want:
                drift.append("%s weicht von der Palette ab" % fname)
        if drift:
            print("bat-Themes nicht aktuell: %s" % "; ".join(drift), file=sys.stderr)
            print("  → python3 scripts/build_bat_themes.py", file=sys.stderr)
            return 1
        print("bat-Themes aktuell (%d Dateien)" % len(files))
        return 0

    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, content in files.items():
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print("geschrieben: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
