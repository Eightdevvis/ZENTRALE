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

import ablage_ort

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
    # Seit 2026-10-11 nach Themen: themen/ (samt Messreihen *.reihe.json),
    # ki/ (Hausregeln, Vorlagen, Skills), INDEX.md, _archiv/ und der beim
    # Umzug beiseitegelegte alte Bestand — alles darunter. data/g_*.json
    # oben bleibt für Reihen, die noch nicht umgezogen sind.
    "data/gedaechtnis/**",
    "data/ai_transcripts/*.jsonl",
    "data/gespraeche/**",
    "data/ablage/**",
    "data/rueckmeldungen/*.jsonl",
    # Desk View (core/desk.py, 2026-10-09, Sasha: „immer mitsyncen"):
    # .canvas-Dateien, JSON — zusammengeführt nach id wie jede JSON-Datei.
    "data/desk/**",
    # Schaufenster (core/shop.py, 2026-10-10): was geholt ist, eine
    # JSON-LD-Datei pro Rechner (besitz-<rechner>.jsonld) — nie zusammengeführt.
    "data/shop/**",
    # Selbst gebaute Apps (core/werkstatt.py, 2026-10-10): app.toml + icon.png
    # je App — Sasha baut sie auf einem Rechner und will sie überall im Rad.
    "data/apps/**",
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
# Nur im Abgleich: das Kontextpaket fürs Handy (core/mobil_kontext.py) —
# abgeleitet, eine Sicherung braucht es nicht.
NUR_ABGLEICH = ["data/mobil/kontext.json"]
ABGLEICH = [m for m in SICHERN if m not in NICHT_ABGLEICHEN] + NUR_ABGLEICH


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


# ── Was außerhalb des ZENTRALE-Ordners liegt (2026-10-11) ──────────────
# Die Ablage zog nach ~/Zentrale/Ablage (core/ablage_ort.py). Im Abgleich
# und in der Sicherung heißt sie weiter „data/ablage/<id>/…" — dieselben
# Namen wie vorher, also kein Umzug in der Mitte und keine Doppelten; nur
# WO sie auf diesem Rechner liegt, sagt pfad(). Gilt nur für den echten
# ZENTRALE-Ordner: ein Test- oder Fremd-Ordner (--quelle) behält sein
# eigenes data/ablage. Die lesbaren Dateien obendrauf gleicht niemand ab —
# jeder Rechner baut sie selbst (core/ablage_sichtbar.py).
AUSSEN = {"data/ablage": ablage_ort.dokumente}
_PROJEKT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _aussen(root) -> dict:
    """Nur für den echten ZENTRALE-Ordner, und nur, wenn der neue Ort schon
    da ist: vor dem Umzug (scripts/ablage_umzug.py) sähe der Abgleich sonst
    eine LEERE Ablage — und hielte alles für gelöscht."""
    if os.path.realpath(root) != _PROJEKT:
        return {}
    return {k: ort for k, ort in ((k, f()) for k, f in AUSSEN.items()) if os.path.isdir(ort)}


def pfad(root, rel) -> str:
    """Wo eine Datei der Auswahl auf diesem Rechner liegt."""
    rel = rel.replace(os.sep, "/")
    for vorsatz, ort in _aussen(root).items():
        if rel.startswith(vorsatz + "/"):
            return os.path.join(ort, rel[len(vorsatz) + 1:])
    return os.path.join(root, rel)


def auswahl(root, muster=SICHERN):
    """Relative Pfade aller Dateien unter `root`, die auf der Liste stehen
    (dazu, was nach AUSSEN gezogen ist)."""
    raus = []
    aussen = _aussen(root)
    for wurzel, dirs, files in os.walk(root):
        rel_w = os.path.relpath(wurzel, root)
        if rel_w.startswith((".git", ".claude", "venv")) or "__pycache__" in rel_w \
                or rel_w.replace(os.sep, "/") in aussen:
            dirs[:] = []
            continue
        for f in files:
            rel = os.path.normpath(os.path.join(rel_w, f)).replace(os.sep, "/")
            if passt(rel, muster):
                raus.append(rel)
    for vorsatz, ort in aussen.items():
        for wurzel, dirs, files in os.walk(ort):
            for f in files:
                rel = vorsatz + "/" + os.path.relpath(os.path.join(wurzel, f), ort) \
                    .replace(os.sep, "/")
                if passt(rel, muster):
                    raus.append(rel)
    return sorted(raus)
