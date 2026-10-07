# core/skills.py
#
# Skills: Anleitungen für eine bestimmte ART Aufgabe („Woche planen",
# „etwas recherchieren"), die die KI nur bei Bedarf liest.
#
# 2026-10-07, Phase 4 des Claude-Web-Plans (memory/ki/claude_web_plan.md,
# Ebene „Skill" und Sashas Entscheidung 4). Sasha: „ki soll sogar welche
# vorschlagen totally, damit sie später wenn sie gut aufgestellt ist sich von
# alleine weiterentwickeln kann."
#
# ── Das Prinzip: Liste im Kopf, Inhalt auf Abruf ──────────────────────
# Wie beim Gedächtnis („Titel im Kopf, Inhalt per read_note"): im festen,
# gecachten Teil des Cloud-Prompts steht nur EINE Zeile je aktivem Skill
# (prompt_block). Den Inhalt holt das Modell mit load_skill — er landet als
# Werkzeug-Ergebnis im Verlauf und verändert den Cache-Anfang nicht. Ein
# Skill kostet also fast nichts, solange er nicht dran ist.
#
# ── Abgrenzung ─────────────────────────────────────────────────────────
#   Hausregeln  gelten IMMER (Verhalten), stehen ganz im Kopf.
#   Skill       gilt nur für seine Art Aufgabe, wird bei Bedarf geladen.
#   Profil      wie eine Schiene grundsätzlich denkt (core/profil/).
#
# ── Die Datei ──────────────────────────────────────────────────────────
# data/gedaechtnis/skills/<name>.md, Kopf im Katalog-Schema des Gedächtnisses
# (gedaechtnis.kopf_lesen), darunter die Anleitung in Sätzen:
#
#   ## wochenplan
#   - beschreibung: <EINE Zeile: wann benutzen>
#   - erstellt:     2026-10-07
#   - herkunft:     sasha | ki
#   - status:       aktiv | vorgeschlagen | aus
#
#   <Anleitung>
#
# Sasha schaltet einen Skill ab, indem er `status: aus` setzt. Gelöscht wird
# nie (der Sync ist additiv, eine gelöschte Datei käme vom anderen Rechner
# zurück).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import os
import shutil
from datetime import date, datetime

import dateien
import gedaechtnis

STATUS = ("aktiv", "vorgeschlagen", "aus")
HERKUNFT = ("sasha", "ki")
FELDER = ("beschreibung", "erstellt", "herkunft", "status")

MAX_BESCHREIBUNG = 160   # eine Zeile im gecachten Kopf, bei jedem Zug dabei
MAX_INHALT = 6_000       # eine Anleitung, kein Handbuch

# Die ersten Skills liegen im Repo und kommen beim ersten Zugriff nach
# data/gedaechtnis/skills/ (erstbefuellen).
VORLAGEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "skill_vorlagen")

# Erstbefüllte Dateien bekommen DIESE Änderungszeit, nicht „jetzt".
# Der Sync ist rsync --update (neueste gewinnt): ein Rechner, der später zum
# ersten Mal startet, legt die Vorlagen frisch an — mit „jetzt" würden sie
# eine Fassung überschreiben, die Sasha auf dem anderen Rechner schon
# geändert (z. B. ausgeschaltet) hat. Mit einem festen, alten Stempel gewinnt
# jede echte Änderung. (2026-10-07)
_VORLAGEN_ZEIT = datetime(2026, 10, 7).timestamp()


# ── Ordner und Erstbefüllung ──────────────────────────────────────────

def ordner() -> str:
    """Der Skill-Ordner; beim allerersten Zugriff mit den Vorlagen befüllt."""
    pfad = gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)
    if not os.path.isdir(pfad):
        erstbefuellen(pfad)
    return pfad


def erstbefuellen(ziel: str) -> list:
    """Die Vorlagen nach `ziel` kopieren — nur Dateien, die dort fehlen.

    Läuft nur, wenn der Ordner noch nicht existiert (ordner()): hat Sasha
    die Skills einmal bekommen, kommt nichts ungefragt zurück. Selbst dann
    wird keine vorhandene Datei überschrieben. → Liste der angelegten Namen."""
    os.makedirs(ziel, exist_ok=True)
    angelegt = []
    if not os.path.isdir(VORLAGEN_DIR):
        return angelegt
    for datei in sorted(os.listdir(VORLAGEN_DIR)):
        if not datei.endswith(".md"):
            continue
        pfad = os.path.join(ziel, datei)
        if os.path.exists(pfad):
            continue
        shutil.copyfile(os.path.join(VORLAGEN_DIR, datei), pfad)
        os.utime(pfad, (_VORLAGEN_ZEIT, _VORLAGEN_ZEIT))
        angelegt.append(datei[:-3])
    return angelegt


def _pfad(name: str) -> str:
    return os.path.join(ordner(), f"{name}.md")


# ── Lesen ─────────────────────────────────────────────────────────────

def _zerlegen(text: str) -> tuple:
    """Dateitext → (kopf, inhalt). Ohne gültigen Kopf: ({}, text)."""
    kopf = gedaechtnis.kopf_lesen(text)
    if not kopf:
        return {}, text.strip()
    # Der Kopf endet an der ersten Leerzeile (so liest ihn kopf_lesen).
    teile = text.strip().split("\n\n", 1)
    return kopf, (teile[1].strip() if len(teile) > 1 else "")


def _rendern(name: str, kopf: dict, inhalt: str) -> str:
    breite = max(len(f) for f in FELDER) + 1
    zeilen = [f"## {name}"]
    for feld in FELDER:
        wert = " ".join(str(kopf.get(feld) or "-").split())
        zeilen.append(f"- {(feld + ':'):<{breite}} {wert}")
    return "\n".join(zeilen) + "\n\n" + inhalt.strip() + "\n"


def _lesen(name: str) -> tuple:
    try:
        with open(_pfad(name), encoding="utf-8") as f:
            return _zerlegen(f.read())
    except FileNotFoundError:
        return None, None


def alle() -> list:
    """Alle Skills, nach Name sortiert: [{name, beschreibung, status,
    herkunft, erstellt}]. Eine Datei ohne Kopf zählt als ausgeschaltet —
    sie würde sonst mit leerer Beschreibung in den Prompt rutschen."""
    raus = []
    for datei in sorted(os.listdir(ordner())):
        if not datei.endswith(".md"):
            continue
        name = datei[:-3]
        kopf, _ = _lesen(name)
        kopf = kopf or {}
        status = (kopf.get("status") or "").strip().lower()
        raus.append({
            "name":         name,
            "beschreibung": (kopf.get("beschreibung") or "").strip(),
            "status":       status if status in STATUS else "aus",
            "herkunft":     (kopf.get("herkunft") or "").strip().lower() or "-",
            "erstellt":     (kopf.get("erstellt") or "").strip() or "-",
        })
    return raus


def aktive() -> list:
    return [s for s in alle() if s["status"] == "aktiv" and s["beschreibung"]]


def prompt_block() -> str:
    """Die Skill-Liste für den FESTEN Teil des Cloud-Prompts.

    Byte-stabil, solange sich keine Skill-Datei ändert: nach Name sortiert,
    nur aktive, nur Name und Beschreibung (eine Zeile). Kein Datum, kein
    Zähler — sonst bräche der Prompt-Cache bei jedem Zug."""
    zeilen = [f"- {s['name']} — {s['beschreibung'][:MAX_BESCHREIBUNG]}"
              for s in aktive()]
    if not zeilen:
        return ""
    return ("## Skills\n"
            "Anleitungen für bestimmte Arten von Aufgaben. Den Inhalt holst "
            "du mit load_skill(name) — hier steht nur, wann einer passt.\n"
            + "\n".join(zeilen))


def laden(name: str) -> str:
    """Den Inhalt eines aktiven Skills fürs Modell."""
    schluessel = gedaechtnis.slug(name)
    kopf, inhalt = _lesen(schluessel) if schluessel else (None, None)
    if kopf is None and inhalt is None:
        da = ", ".join(s["name"] for s in aktive()) or "keine"
        return f"[Keinen Skill {name!r}. Aktiv sind: {da}]"
    status = (kopf or {}).get("status", "").strip().lower()
    if status != "aktiv":
        return (f"[Skill {schluessel!r} ist nicht aktiv "
                f"({status or 'ohne Kopf'}) — Sasha hat ihn nicht freigegeben "
                f"oder abgeschaltet. Arbeite ohne ihn.]")
    return f"Skill {schluessel}:\n\n{inhalt}"


# ── Schreiben (nur über die gegateten Werkzeuge) ──────────────────────

def _pruefen_inhalt(inhalt: str) -> str | None:
    if not (inhalt or "").strip():
        return "[Fehler: leerer Inhalt]"
    if len(inhalt) > MAX_INHALT:
        return (f"[Zu lang für einen Skill ({len(inhalt)} Zeichen, höchstens "
                f"{MAX_INHALT}). Eine Anleitung, kein Handbuch.]")
    return None


def vorschlagen(name: str, beschreibung: str, inhalt: str) -> str:
    """Einen neuen Skill anlegen (herkunft ki, status aktiv).

    Wird NUR nach Sashas Ja aufgerufen (Gate im Werkzeug-Register). Ein
    bestehender Name wird nicht überschrieben — dafür gibt es edit_skill."""
    schluessel = gedaechtnis.slug(name)
    if not schluessel:
        return "[Fehler: kein Name]"
    beschreibung = " ".join((beschreibung or "").split())
    if not beschreibung:
        return "[Fehler: keine Beschreibung — eine Zeile, wann man ihn benutzt]"
    if len(beschreibung) > MAX_BESCHREIBUNG:
        return (f"[Beschreibung zu lang ({len(beschreibung)} Zeichen, "
                f"höchstens {MAX_BESCHREIBUNG}) — sag in einer Zeile, wann er "
                f"passt.]")
    fehler = _pruefen_inhalt(inhalt)
    if fehler:
        return fehler
    pfad = _pfad(schluessel)
    if os.path.exists(pfad):
        return (f"[Den Skill {schluessel!r} gibt es schon — zum Ändern "
                f"edit_skill, nicht propose_skill.]")
    kopf = {"beschreibung": beschreibung, "erstellt": date.today().isoformat(),
            "herkunft": "ki", "status": "aktiv"}
    dateien.atomar_schreiben(pfad, _rendern(schluessel, kopf, inhalt))
    return (f"Skill {schluessel!r} angelegt (aktiv). Er steht ab dem nächsten "
            f"Gespräch in der Liste; jetzt schon mit load_skill lesbar.")


def aendern(name: str, inhalt: str) -> str:
    """Die Anleitung eines bestehenden Skills ersetzen; der Kopf bleibt.
    Die alte Fassung liegt danach als .bak daneben (wie rewrite_note)."""
    schluessel = gedaechtnis.slug(name)
    pfad = _pfad(schluessel) if schluessel else ""
    if not schluessel or not os.path.exists(pfad):
        da = ", ".join(s["name"] for s in alle()) or "keine"
        return (f"[Keinen Skill {name!r} — edit_skill ändert nur bestehende. "
                f"Es gibt: {da}]")
    # Schreibt das Modell den Kopf mit, wird er weggeworfen: Beschreibung,
    # Herkunft und Status ändert nur Sasha (bzw. propose_skill beim Anlegen).
    # Nur ein Kopf mit dem Namen DIESES Skills zählt — eine Anleitung darf
    # selbst mit „## Ablauf" und einer Aufzählung beginnen.
    kopf_neu, rest = _zerlegen(inhalt or "")
    if (gedaechtnis.slug(kopf_neu.get("titel", "")) == schluessel
            and any(f in kopf_neu for f in FELDER)):
        inhalt = rest
    fehler = _pruefen_inhalt(inhalt)
    if fehler:
        return fehler
    with open(pfad, encoding="utf-8") as f:
        alt = f.read()
    kopf, _ = _zerlegen(alt)
    dateien.atomar_schreiben(pfad + ".bak", alt)
    dateien.atomar_schreiben(pfad, _rendern(schluessel, kopf or {}, inhalt))
    return (f"Skill {schluessel!r} neu geschrieben (alte Fassung liegt als "
            f".bak daneben).")


# Für die Frage an Sasha: die ersten Zeilen eines Textes, einzeilig.
def anfang(text: str, zeilen: int = 3, max_zeichen: int = 240) -> str:
    teile = [z.strip() for z in str(text or "").splitlines() if z.strip()]
    kurz = " ⏎ ".join(z[:80] for z in teile[:zeilen])
    if len(kurz) > max_zeichen:
        kurz = kurz[:max_zeichen - 1] + "…"
    if len(teile) > zeilen:
        kurz += f" (+{len(teile) - zeilen} Zeilen)"
    return kurz

