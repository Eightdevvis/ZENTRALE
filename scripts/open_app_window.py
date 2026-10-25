#!/usr/bin/env python3
# scripts/open_app_window.py
#
# Das Fenster einer App öffnen (`[ansicht.fenster] start` im app.toml) — der
# dünne Starter, den die TUI ruft, ohne den Code der App zu kennen. Seit
# 2026-10-22 für die Karte (Taste `w` in der Karten-Ansicht); vorher startete
# die TUI scripts/map_window.py aus ZENTRALE selbst.
#
#   open_app_window.py <name> [Fenster-Argumente …]     z. B. karte --cx 10 --cy 50 --zoom 3
#   open_app_window.py <name> --pruefen                 nur prüfen (Satz für Sasha, Code 2)
#   open_app_window.py <name> --ansicht terminal        eine andere Ansicht (`[ansicht.<x>]
#                                                       start`), seit 2026-10-25 für Apps aus
#                                                       dem Schaufenster; terminal läuft im
#                                                       Terminal des Aufrufers (die TUI tritt
#                                                       so lange beiseite)
#
# Wo die App liegt: Env ZENTRALE_APP_PFAD_<NAME>, sonst die Einstellung von
# ZENTRALE (core/apps.py, falls core/ da ist), sonst das Nachbar-Repo
# (core/apps.py BEKANNT, Standard ../<name>). Nur Standardbibliothek und aus
# core/ die geteilten Start-Handgriffe (core/app_prozess.py): das Fenster
# läuft im Vordergrund dieses Prozesses, bis es zugeht.

import os
import subprocess
import sys

try:
    import tomllib
except ImportError:          # Python < 3.11: dann gibt es kein Fenster
    tomllib = None

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))

import app_prozess  # noqa: E402  – stdlib-only


def app_ordner(name):
    kandidaten = [os.environ.get("ZENTRALE_APP_PFAD_" + name.upper())]
    try:
        import apps                                   # nur, wo das Backend wohnt
        kandidaten.append(apps.pfad(name))
    except Exception:
        pass
    kandidaten.append(os.path.join(ROOT, "..", "zentrale-" + name))
    for k in kandidaten:
        if k and os.path.isfile(os.path.join(k, "app.toml")):
            return os.path.abspath(k)
    return None


def fenster_befehl(name, ansicht="fenster"):
    """→ (ordner, befehl) oder (None, Satz für Sasha)."""
    ordner = app_ordner(name)
    if ordner is None:
        return None, "die app „%s\" ist auf diesem rechner nicht installiert" % name
    if tomllib is None:
        return None, "dieses python kann app.toml nicht lesen (zu alt)"
    try:
        with open(os.path.join(ordner, "app.toml"), "rb") as f:
            m = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return None, "app.toml von „%s\" nicht lesbar: %s" % (name, e)
    start = ((m.get("ansicht") or {}).get(ansicht) or {}).get("start")
    if not start:
        if ansicht == "fenster":
            return None, "„%s\" hat kein fenster (app.toml ohne ansicht.fenster)" % name
        return None, "„%s\" hat keine ansicht %s (app.toml ohne ansicht.%s)" % (name, ansicht, ansicht)
    return ordner, app_prozess.befehl(ordner, start, ROOT)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("aufruf: open_app_window.py <name> [--pruefen | fenster-argumente …]", file=sys.stderr)
        return 2
    name, rest = argv[0], argv[1:]
    ansicht = "fenster"
    if rest[:1] == ["--ansicht"] and len(rest) >= 2:
        ansicht, rest = rest[1], rest[2:]
    ordner, befehl = fenster_befehl(name, ansicht)
    if ordner is None:
        print(befehl, file=sys.stderr)        # landet im Log der TUI
        return 2
    if rest == ["--pruefen"]:
        return 0
    try:
        return subprocess.call(befehl + rest, cwd=ordner)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
