#!/usr/bin/env python3
"""Sashas Daten ins private Daten-Repo sichern (git@github.com:Eightdevvis/data.git).

Sasha, 2026-10-06: „das neue git repo namens /data … wo wir backup und alles
was so an sensible daten in ne cloud will reinschmeißen können."

So funktioniert es:
  * POSITIVLISTE statt Sperrliste (SICHERN unten): gesichert wird nur, was
    dort ausdrücklich steht. Eine neue Datei mit Schlüsseln kann so nie aus
    Versehen mitrutschen — sie müsste erst hier eingetragen werden.
  * SCHLÜSSEL-SCANNER vor jedem Commit: findet er etwas, das nach einem
    Zugangsschlüssel aussieht, wird NICHTS committet und nichts gepusht.
    Auch ein privates Repo zählt als „draußen" (CLAUDE.md: ein Key auf
    GitHub gilt als kompromittiert).
  * EIN BRANCH PRO RECHNER (knoten/<hostname>): PC und Laptop schreiben nie
    in denselben Branch, also gibt es nie Konflikte und nie ein Überschreiben.
  * EIGENER KLON AUSSERHALB von data/ (~/.local/share/zentrale/daten-sicherung):
    der rsync-Sync zwischen den Rechnern fasst ihn nicht an.
  * Der Klon ist ein SPIEGEL: was in ZENTRALE gelöscht wird, verschwindet im
    nächsten Stand auch dort — die git-Historie hält jede frühere Fassung.

Aufruf (Sasha tippt Shell-Befehle selbst; hier nur in Worten):
  ohne Zusatz        sichern: kopieren, prüfen, committen, pushen
  --trocken          nur anzeigen, was gesichert würde — nichts schreiben
  --ohne-push        committen, aber nicht pushen
"""

import argparse
import datetime
import fnmatch
import os
import re
import shutil
import socket
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KLON = os.path.expanduser(os.environ.get(
    "ZENTRALE_SICHERUNG_KLON", "~/.local/share/zentrale/daten-sicherung"))
REMOTE = "git@github.com:Eightdevvis/data.git"

# Was gesichert wird — relativ zum ZENTRALE-Ordner. Bewusst NICHT dabei:
#   data/ai_config.json            Klartext-API-Schlüssel
#   data/mail_secrets.enc(.bak)    verschlüsselte Mail-Zugänge (Sasha entscheidet)
#   data/mail_state/_folders/_counts, data/news_*   Caches, neu erzeugbar
#   data/tts_model, data/ascii     Modell bzw. im Code-Repo versioniert
#   data/_beiseite                 Sasha geht es gerade durch
SICHERN = [
    "data/features.json",
    "data/lists.json",
    "data/notes.json",
    "data/graphs.json",
    "data/g_*.json",
    "data/melodies.json",
    "data/sleep_quality.json",
    "data/mail_rules.json",
    "data/ai_usage.json",
    "data/ai_calendar.json",
    "data/kalender_neben.json",
    "data/kalender/**",
    "data/gedaechtnis/**",
    "data/ai_transcripts/*.jsonl",
    "data/gespraeche/**",
    "data/ablage/**",
    "data/rueckmeldungen/*.jsonl",
    "tutor/data/tutor_config.json",
    "tutor/data/aktiver_stand",
    "tutor/data/staende/**",
    "tutor/data/es/**",
]

# Wonach der Scanner sucht. Lieber einmal zu viel abbrechen als einen
# Schlüssel auf einem fremden Server haben.
SCHLUESSEL_MUSTER = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),              # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                     # OpenAI-artig / DashScope
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),                 # Google
    re.compile(r"ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),           # Slack
    re.compile(r'"(?:[A-Z_]*API_KEY|password|passwort|passphrase|token|secret)"\s*:\s*"[^"]{6,}"',
               re.IGNORECASE),
    re.compile(r"refresh_token|client_secret", re.IGNORECASE),
]


def _git(args, cwd=None, check=True):
    # cwd erst beim Aufruf auflösen (nicht als Default-Wert): sonst wäre
    # KLON beim Laden festgenagelt und ließe sich nicht umlenken.
    return subprocess.run(["git"] + args, cwd=cwd or KLON, check=check,
                          capture_output=True, text=True)


def auswahl(root=ROOT, muster=SICHERN):
    """Relative Pfade aller Dateien, die gesichert werden."""
    raus = []
    for wurzel, dirs, files in os.walk(root):
        rel_w = os.path.relpath(wurzel, root)
        if rel_w.startswith((".git", ".claude", "venv")) or "__pycache__" in rel_w:
            dirs[:] = []
            continue
        for f in files:
            rel = os.path.normpath(os.path.join(rel_w, f))
            for m in muster:
                if m.endswith("/**"):
                    if rel.startswith(m[:-3] + "/"):
                        raus.append(rel)
                        break
                elif fnmatch.fnmatch(rel, m) and "/" not in rel[len(os.path.dirname(m)) + 1:]:
                    raus.append(rel)
                    break
    return sorted(raus)


def schluessel_funde(pfade, root):
    """[(pfad, muster)] für jede Datei, die nach einem Schlüssel aussieht."""
    funde = []
    for rel in pfade:
        try:
            text = open(os.path.join(root, rel), encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        for m in SCHLUESSEL_MUSTER:
            if m.search(text):
                funde.append((rel, m.pattern[:40]))
                break
    return funde


def spiegeln(pfade, quelle, ziel):
    """Ziel (ohne .git) exakt auf die Auswahl bringen: kopieren, was neu oder
    anders ist, entfernen, was nicht mehr ausgewählt ist."""
    soll = set(pfade)
    for wurzel, dirs, files in os.walk(ziel):
        dirs[:] = [d for d in dirs if d != ".git"]
        for f in files:
            rel = os.path.relpath(os.path.join(wurzel, f), ziel)
            if rel not in soll and rel != "LIESMICH.md":
                os.remove(os.path.join(wurzel, f))
    for rel in pfade:
        q, z = os.path.join(quelle, rel), os.path.join(ziel, rel)
        os.makedirs(os.path.dirname(z), exist_ok=True)
        shutil.copy2(q, z)


LIESMICH = """# ZENTRALE — Datensicherung

Automatisch geschrieben von `scripts/daten_sichern.py` im ZENTRALE-Repo.

- Ein Branch pro Rechner: `knoten/<hostname>`. Die Rechner schreiben nie in
  denselben Branch.
- Jeder Stand ist ein Spiegel der ausgewählten Dateien (Positivliste im
  Skript). Frühere Fassungen stehen in der git-Historie.
- Keine Klartext-Schlüssel: das Skript bricht ab, bevor so etwas committet
  würde.

Wiederherstellen: die gewünschte Fassung einer Datei aus der Historie holen
und an denselben relativen Pfad im ZENTRALE-Ordner legen.
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--trocken", action="store_true")
    ap.add_argument("--ohne-push", action="store_true")
    ap.add_argument("--quelle", default=ROOT,
                    help="ZENTRALE-Ordner, aus dem gesichert wird (Standard: dieser)")
    args = ap.parse_args(argv)
    quelle = os.path.abspath(args.quelle)

    host = socket.gethostname()
    branch = f"knoten/{host}"
    pfade = auswahl(quelle)
    groesse = sum(os.path.getsize(os.path.join(quelle, p)) for p in pfade)
    print(f"{len(pfade)} Dateien, {groesse / 1024:.0f} KB, Ziel {REMOTE} · {branch}")

    funde = schluessel_funde(pfade, quelle)
    if funde:
        print("ABBRUCH — diese Dateien sehen nach einem Schlüssel aus:")
        for rel, m in funde:
            print(f"  {rel}  ({m}…)")
        print("Nichts committet, nichts gepusht. Datei aus SICHERN nehmen oder prüfen.")
        return 2
    if args.trocken:
        for p in pfade:
            print("  " + p)
        return 0

    if not os.path.isdir(os.path.join(KLON, ".git")):
        os.makedirs(KLON, exist_ok=True)
        _git(["init", "-q"])
        _git(["remote", "add", "origin", REMOTE])
    if _git(["ls-remote", "--exit-code", "--heads", "origin", branch], check=False).returncode == 0:
        _git(["fetch", "-q", "origin", branch])
        _git(["checkout", "-q", "-B", branch, f"origin/{branch}"])
    else:
        _git(["checkout", "-q", "-B", branch], check=False)

    spiegeln(pfade, quelle, KLON)
    with open(os.path.join(KLON, "LIESMICH.md"), "w", encoding="utf-8") as f:
        f.write(LIESMICH)
    # Zweite Prüfung auf dem, was wirklich committet würde.
    alles = [os.path.relpath(os.path.join(w, f), KLON)
             for w, d, fs in os.walk(KLON) if ".git" not in w for f in fs]
    funde = schluessel_funde(alles, KLON)
    if funde:
        print("ABBRUCH im Klon — Schlüssel-Verdacht:", funde)
        return 2

    _git(["add", "-A"])
    if _git(["diff", "--cached", "--quiet"], check=False).returncode == 0:
        print("Nichts Neues seit der letzten Sicherung.")
    else:
        stand = datetime.datetime.now().isoformat(timespec="minutes")
        _git(["-c", "user.name=ZENTRALE", "-c", "user.email=zentrale@localhost",
              "commit", "-q", "-m", f"Sicherung {stand} ({host})"])
        print(f"Commit: Sicherung {stand}")
    if args.ohne_push:
        return 0
    r = _git(["push", "-q", "-u", "origin", branch], check=False)
    if r.returncode != 0:
        print("Push fehlgeschlagen:", r.stderr.strip()[:300])
        return 1
    print("Gepusht.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
