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
import cloud_folder

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
    # Course colours of the calendar (core/calendar_colours.py, 2026-10-29):
    # the same colour on every front and device.
    "data/calendar_colours.json",
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
    # Der Adapter (core/adapter.py, 2026-10-24): die Beschreibungen der
    # Anschlüsse — nie ein Geheimnis darin (Schema). Die Zugangsdaten
    # (geheim.enc) stehen bewusst NICHT hier, sondern unten in GEHEIM.
    "data/adapter/anschluesse/*.json",
    # Plugs of app instances from the plug dialog (core/plug_store.py, building
    # kit step 11): wires like "assistant model ← adapter", owned by the
    # instance and synced like the calendar source. No secret in them.
    "data/adapter/plugs/*.json",
    "tutor/data/tutor_config.json",
    "tutor/data/aktiver_stand",
    "tutor/data/staende/**",
    "tutor/data/es/**",
]

# Nur abgeglichen, nie gesichert: was die alte Datensicherung im Klartext
# nach GitHub trüge. Seit 2026-10-24 die Zugangsdaten des Adapters
# (core/adapter_geheim.py) — sie verlassen das Gerät nur mit dem
# Kontoschlüssel verschlüsselt, und nur über den Abgleich.
# tests/test_adapter_geheim.py: daten_sichern greift nie danach.
GEHEIM = ["data/adapter/geheim.enc"]

# Bis 2026-10-24 stand hier auch data/kalender/**: jeder Rechner glich seinen
# Kalender selbst mit Google ab. Seitdem fährt immer nur EIN Gerät die Brücke
# zu Google (core/adapter_bruecke.py), alle anderen bekommen die Termine über
# die Mitte — data/kalender/** gleicht ab, sobald es einen Kalender-Anschluss
# gibt (abgleich_apps schneidet es sonst heraus). ai_calendar.json ist der
# alte Speicher von vor dem .ics-Umzug: bleibt je Gerät.
# Begründung: memory/betrieb/abgleich.md „Kalender".
NICHT_ABGLEICHEN = ["data/ai_calendar.json"]
# Nur im Abgleich: das Kontextpaket fürs Handy (core/mobil_kontext.py) —
# abgeleitet, eine Sicherung braucht es nicht. Dazu der Mietvertrag der
# Brücke mit dem Stand von vdirsyncer (core/adapter_bruecke.py) — gilt nur
# zwischen den Geräten — und die Zugangsdaten (GEHEIM).
# Since 2026-10-29 also the cloud folder (core/cloud_folder.py): whatever the
# user drops into ~/Zentrale/Cloud. Sync only, never the old plain-text
# backup — it may hold anything.
NUR_ABGLEICH = ["data/mobil/kontext.json", "data/adapter/bruecke/**", cloud_folder.PATTERN] + GEHEIM
ABGLEICH = [m for m in SICHERN if m not in NICHT_ABGLEICHEN] + NUR_ABGLEICH
assert not set(GEHEIM) & set(SICHERN), "Zugangsdaten gehören nie in die Sicherung"

# Im Kalender-Ordner sind nur Termine und die Namen/Farben der Ebenen Daten.
# Die Sperrdatei (.zentrale.lock) und was vdirsyncer beim Schreiben kurz
# hinlegt, wandern nie.
_KALENDER = "data/kalender/"
_KALENDER_NAMEN = ("displayname", "color")
_CLOUD = cloud_folder.PREFIX + "/"


def passt(rel, muster=SICHERN):
    """Steht der relative Pfad auf der Liste? `x/**` = alles darunter,
    sonst ein Muster für genau eine Ordner-Ebene."""
    rel = rel.replace(os.sep, "/")
    name = rel.rsplit("/", 1)[-1]
    # Zwischendateien von dateien.atomar_schreiben (".name.pid.ns.tmp"), die
    # ein Absturz liegen ließ, sind nie Daten.
    if name.startswith(".") and name.endswith(".tmp"):
        return False
    if rel.startswith(_CLOUD) and cloud_folder.excluded(rel[len(_CLOUD):]):
        return False
    if rel.startswith(_KALENDER) and (name.startswith(".") or not (
            name.endswith(".ics") or name in _KALENDER_NAMEN)):
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
AUSSEN = {"data/ablage": ablage_ort.dokumente, cloud_folder.PREFIX: cloud_folder.root}
_PROJEKT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _aussen(root) -> dict:
    """Nur für den echten ZENTRALE-Ordner, und nur, wenn der neue Ort schon
    da ist: vor dem Umzug (scripts/ablage_umzug.py) sähe der Abgleich sonst
    eine LEERE Ablage — und hielte alles für gelöscht."""
    if os.path.realpath(root) != _PROJEKT:
        return {}
    return {k: ort for k, ort in ((k, f()) for k, f in AUSSEN.items()) if os.path.isdir(ort)}


def create_outside(root, prefix) -> bool:
    """Create the outside folder for `prefix` (e.g. the cloud folder) on this
    device, but only for the real ZENTRALE folder (a test or foreign root
    keeps its own data/<…>). -> True if it exists now."""
    if prefix not in AUSSEN or os.path.realpath(root) != _PROJEKT:
        return False
    os.makedirs(AUSSEN[prefix](), exist_ok=True)
    return True


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
    # Ein installierter Hub (deploy/install.sh, 2026-10-22) hat data/ als
    # Verweis auf ~/.local/share/zentrale/data — die Daten überleben so jede
    # neue Programm-Fassung. os.walk folgt Verweisen nicht; die obersten
    # Datenordner deshalb ausdrücklich dazunehmen.
    starts = [root]
    for oben in ("data", "tutor"):
        p = os.path.join(root, oben)
        if os.path.islink(p) and os.path.isdir(p):
            starts.append(p)
    for start in starts:
        for wurzel, dirs, files in os.walk(start):
            rel_w = os.path.relpath(wurzel, root)
            if rel_w.startswith((".git", ".claude", "venv")) or "__pycache__" in rel_w \
                    or rel_w.replace(os.sep, "/") in aussen:
                dirs[:] = []
                continue
            if (rel_w.replace(os.sep, "/") + "/").startswith(_CLOUD):
                dirs[:] = [d for d in dirs if not cloud_folder.skip_dir(d)]
                files = [f for f in files if not os.path.islink(os.path.join(wurzel, f))]
            for f in files:
                rel = os.path.normpath(os.path.join(rel_w, f)).replace(os.sep, "/")
                if passt(rel, muster):
                    raus.append(rel)
    for vorsatz, ort in aussen.items():
        for wurzel, dirs, files in os.walk(ort):
            if vorsatz == cloud_folder.PREFIX:
                # Do not even walk into .git, node_modules …; symlinks are
                # never data (a link would arrive elsewhere as a copy).
                dirs[:] = [d for d in dirs if not cloud_folder.skip_dir(d)]
                files = [f for f in files if not os.path.islink(os.path.join(wurzel, f))]
            for f in files:
                rel = vorsatz + "/" + os.path.relpath(os.path.join(wurzel, f), ort) \
                    .replace(os.sep, "/")
                if passt(rel, muster):
                    raus.append(rel)
    return sorted(raus)
