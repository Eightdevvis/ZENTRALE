# core/abgleich_auswahl.py
#
# Welche Dateien den Rechner verlassen dürfen — eine Positivliste, die
# Datensicherung (scripts/daten_sichern.py) und Abgleich über die Mitte
# (core/abgleich.py) teilen. Bis 2026-10-08 stand sie im Sicherungs-Skript;
# zwei Listen wären auseinandergelaufen.
#
# Positivliste statt Sperrliste: eine neue Datei mit Schlüsseln kann nie aus
# Versehen mitrutschen — sie müsste erst hier eingetragen werden.

import fnmatch
import os

# Relativ zum ZENTRALE-Ordner. Bewusst NICHT dabei:
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

# Der Kalender gleicht sich auf jedem Rechner selbst mit Google ab
# (vdirsyncer, seit 2026-10-07). Ein zweiter Weg über die Mitte brächte
# Doppelte und Geister. kalender_neben.json (Reisezeiten, Puffer, Ebenen)
# kennt Google nicht — die bleibt drin. Begründung: memory/betrieb/abgleich.md.
NICHT_ABGLEICHEN = ["data/ai_calendar.json", "data/kalender/**"]
ABGLEICH = [m for m in SICHERN if m not in NICHT_ABGLEICHEN]


def passt(rel, muster=SICHERN):
    """Steht der relative Pfad auf der Liste? `x/**` = alles darunter,
    sonst ein Muster für genau eine Ordner-Ebene."""
    rel = rel.replace(os.sep, "/")
    name = rel.rsplit("/", 1)[-1]
    # Zwischendateien von dateien.atomar_schreiben (".name.pid.ns.tmp"), die
    # ein Absturz liegen ließ, sind nie Daten.
    if name.startswith(".") and name.endswith(".tmp"):
        return False
    for m in muster:
        if m.endswith("/**"):
            if rel.startswith(m[:-3] + "/"):
                return True
        elif fnmatch.fnmatch(rel, m) and "/" not in rel[len(os.path.dirname(m)) + 1:]:
            return True
    return False


def auswahl(root, muster=SICHERN):
    """Relative Pfade aller Dateien unter `root`, die auf der Liste stehen."""
    raus = []
    for wurzel, dirs, files in os.walk(root):
        rel_w = os.path.relpath(wurzel, root)
        if rel_w.startswith((".git", ".claude", "venv")) or "__pycache__" in rel_w:
            dirs[:] = []
            continue
        for f in files:
            rel = os.path.normpath(os.path.join(rel_w, f)).replace(os.sep, "/")
            if passt(rel, muster):
                raus.append(rel)
    return sorted(raus)
