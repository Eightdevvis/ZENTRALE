# core/skills.py
#
# Skills: Anleitungen für eine bestimmte ART Aufgabe („Woche planen",
# „eine neue Anleitung bauen"), die die KI nur bei Bedarf liest.
#
# 2026-10-07, Phase 4 des Claude-Web-Plans (memory/ki/claude_web_plan.md,
# Ebene „Skill" und Sashas Entscheidung 4). Sasha: „ki soll sogar welche
# vorschlagen totally, damit sie später wenn sie gut aufgestellt ist sich von
# alleine weiterentwickeln kann."
# Seit dem Abend desselben Tages im Format von Claude (core/skill_format.py):
# ein Skill = ein Ordner mit SKILL.md (+ scripts/, references/, assets/),
# damit echte Claude-Skills ohne Umbau hineinpassen.
#
# ── Das Prinzip: drei Stufen, wie bei Claude („Progressive Disclosure") ──
#   1. name + description   stehen im FESTEN, gecachten Teil des Cloud-
#                           Prompts (prompt_block) — bei jedem Zug dabei.
#   2. die Anleitung        holt das Modell mit load_skill(name); sie landet
#                           als Werkzeug-Ergebnis im Verlauf, der Cache-Anfang
#                           bleibt gleich.
#   3. weitere Dateien      load_skill(name, datei=…) liest references/ &
#                           Co.; scripts/ laufen nur über run_code(skill=…)
#                           in der Sandbox (Ordner dort nur lesend unter
#                           /skills/<name>).
#
# ── Abgrenzung ─────────────────────────────────────────────────────────
#   Hausregeln  gelten IMMER (Verhalten), stehen ganz im Kopf.
#   Skill       gilt nur für seine Art Aufgabe, wird bei Bedarf geladen.
#   Profil      wie eine Schiene grundsätzlich denkt (core/profil/).
#
# ── Was nur ZENTRALE weiß ──────────────────────────────────────────────
# steht in <name>/_zentrale.json, nie in der SKILL.md: status (aktiv |
# vorgeschlagen | aus), herkunft (sasha | ki | anthropic), erstellt, und
# optional braucht (was ZENTRALE dafür fehlt), vermerk, quelle. Eine Datei
# PRO SKILL statt einer gemeinsamen Statusdatei: der Sync ist „neueste Datei
# gewinnt" — schaltet Sasha am PC einen Skill und am Laptop einen anderen,
# überleben so beide Schalter (2026-10-07). Fehlt die Datei (Sasha hat einen
# Claude-Skill von Hand hineinkopiert), gilt der Skill als an.
#
# Sasha schaltet in der TUI an/aus (Gedächtnis-Ansicht, status_setzen).
# Gelöscht wird nie (der Sync ist additiv, ein gelöschter Ordner käme vom
# anderen Rechner zurück).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import shutil
import threading
from datetime import date, datetime

import datasync
import dateien
import gedaechtnis
import skill_format
import skill_umzug

STATUS = ("aktiv", "vorgeschlagen", "aus")
HERKUNFT = ("sasha", "ki", "anthropic")

MAX_BESCHREIBUNG = skill_format.BESCHREIBUNG_MAX   # 1024, wie bei Claude
# Die ganze Liste im festen Kopf (2026-10-07). Sie geht bei jedem Zug mit
# (gecacht: ~0,3 $ je Million Token gelesen, beim Ändern einmal voll
# geschrieben). 6.000 Zeichen ≈ 1.700 Token ≈ 0,05 Cent je Zug — und nicht
# größer als der übrige feste Kopf (gross.system < 5.000), damit die Liste
# Sashas Regeln nicht übertönt. Die Start-Skills brauchen ~4.500. Wird es
# mehr, werden alle Beschreibungen gleichmäßig gekürzt (nie unter
# MIN_BESCHREIBUNG), erst danach fallen Beschreibungen ganz weg.
LISTE_MAX = 6_000
MIN_BESCHREIBUNG = 160
MAX_INHALT = 20_000      # eine Anleitung, die propose/edit_skill schreiben
SEITE = 20_000           # so viel liefert load_skill je Aufruf (wie
                         # read_project_file); weiter mit `ab`
DATEIEN_LISTE_MAX = 40   # so viele Dateien nennt load_skill

# Die mitgelieferten Skills liegen im Repo und kommen beim Zugriff nach
# data/gedaechtnis/skills/ (erstbefuellen). Eigene direkt hier, die von
# Anthropic unter anthropic/ (Lizenz und Quelle: anthropic/README.md).
VORLAGEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "skill_vorlagen")
ANTHROPIC_DIR = os.path.join(VORLAGEN_DIR, "anthropic")
ANTHROPIC_STATUS = os.path.join(ANTHROPIC_DIR, "zentrale.json")

# Erstbefüllte Dateien bekommen DIESE Änderungszeit, nicht „jetzt".
# Der Sync ist rsync --update (neueste gewinnt): ein Rechner, der später zum
# ersten Mal startet, legt die Vorlagen frisch an — mit „jetzt" würden sie
# eine Fassung überschreiben, die Sasha auf dem anderen Rechner schon
# geändert (z. B. ausgeschaltet) hat. Mit einem festen, alten Stempel gewinnt
# jede echte Änderung. (2026-10-07)
_VORLAGEN_ZEIT = datetime(2026, 10, 7).timestamp()

_SPERRE = threading.Lock()


# ── Ordner, Umzug, Erstbefüllung ──────────────────────────────────────

def ordner() -> str:
    """Der Skill-Ordner. Bei jedem Zugriff: alte Dateien umziehen
    (skill_umzug) und fehlende Vorlagen nachliefern — beides tut nichts,
    wenn nichts zu tun ist."""
    pfad = gedaechtnis.bereich_ordner(gedaechtnis.SKILLS)
    with _SPERRE:
        os.makedirs(pfad, exist_ok=True)
        skill_umzug.umziehen(pfad)
        erstbefuellen(pfad)
    return pfad


def _vorlagen() -> list:
    """[(name, quellordner, zentrale-Vorgabe)] aller mitgelieferten Skills."""
    raus = []
    if os.path.isdir(VORLAGEN_DIR):
        for name in sorted(os.listdir(VORLAGEN_DIR)):
            quelle = os.path.join(VORLAGEN_DIR, name)
            if skill_format.gueltiger_name(name) and name != "anthropic" \
                    and os.path.isfile(os.path.join(quelle, skill_format.SKILL_MD)):
                raus.append((name, quelle, None))
    try:
        with open(ANTHROPIC_STATUS, encoding="utf-8") as f:
            liste = json.load(f)
    except (OSError, ValueError):
        liste = {}
    # Nur, was in zentrale.json steht (dort ist die Lizenz geprüft) — ein
    # Ordner, der ohne Eintrag dazukommt, wird nicht ausgeliefert.
    for name, vorgabe in sorted((liste.get("skills") or {}).items()):
        quelle = os.path.join(ANTHROPIC_DIR, name)
        if skill_format.gueltiger_name(name) and os.path.isdir(quelle):
            raus.append((name, quelle, {
                "status": vorgabe.get("status", "aus"), "herkunft": "anthropic",
                "erstellt": liste.get("stand", "-"),
                "quelle": liste.get("quelle", ""),
                **({"braucht": vorgabe["braucht"]} if vorgabe.get("braucht") else {}),
            }))
    return raus


def erstbefuellen(ziel: str) -> list:
    """Mitgelieferte Skills nach `ziel` kopieren — nur, wessen Ordner dort
    fehlt; nie wird etwas überschrieben. → Namen der angelegten.

    Bis 07.10. abends lief das nur, wenn der ganze Ordner fehlte. Seit die
    Anthropic-Skills dazukamen, je Skill: sonst bekäme ein Rechner, der
    schon Skills hat, die neuen nie. (Löschen kann Sasha ohnehin nicht —
    der Sync brächte den Ordner zurück; er schaltet ab.)"""
    os.makedirs(ziel, exist_ok=True)
    angelegt = []
    for name, quelle, zentrale in _vorlagen():
        if os.path.exists(os.path.join(ziel, name)):
            continue
        tmp = os.path.join(ziel, f".{name}.vorlage.{os.getpid()}")
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(quelle, tmp, symlinks=False)
        if zentrale is not None:
            dateien.json_schreiben(os.path.join(tmp, skill_format.ZENTRALE_JSON),
                                   zentrale)
        _alt_datieren(tmp)
        try:
            os.rename(tmp, os.path.join(ziel, name))
        except OSError:
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        angelegt.append(name)
    return angelegt


def _alt_datieren(wurzel: str) -> None:
    for ort, ordnernamen, dateinamen in os.walk(wurzel):
        for n in dateinamen:
            os.utime(os.path.join(ort, n), (_VORLAGEN_ZEIT, _VORLAGEN_ZEIT))
    for ort, _, _ in sorted(os.walk(wurzel), reverse=True):
        os.utime(ort, (_VORLAGEN_ZEIT, _VORLAGEN_ZEIT))


# ── Lesen ─────────────────────────────────────────────────────────────

def _skill_ordner(name: str) -> str | None:
    """Ordner eines Skills, wenn es ihn gibt (nur gültige Namen — kein
    Pfad-Ausbruch über den Namen)."""
    if not skill_format.gueltiger_name(name):
        return None
    pfad = os.path.join(ordner(), name)
    if os.path.isfile(os.path.join(pfad, skill_format.SKILL_MD)):
        return pfad
    return None


def _zentrale(pfad: str) -> dict:
    try:
        with open(os.path.join(pfad, skill_format.ZENTRALE_JSON),
                  encoding="utf-8") as f:
            daten = json.load(f)
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError):
        return {}


def _skill_md(pfad: str) -> str:
    with open(os.path.join(pfad, skill_format.SKILL_MD), encoding="utf-8",
              errors="replace") as f:
        return f.read()


def _eintrag(name: str, pfad: str) -> dict:
    _, felder, _ = skill_format.zerlegen(_skill_md(pfad))
    z = _zentrale(pfad)
    beschreibung = skill_format.text_feld(felder, "description")
    # Ohne _zentrale.json: von Hand hineinkopiert → an (Sasha wollte ihn).
    status = str(z.get("status") or "aktiv").strip().lower()
    if status not in STATUS or not beschreibung:
        # Ohne Beschreibung rutschte er leer in den Prompt — dann lieber aus.
        status = "aus"
    return {
        "name":         name,
        "beschreibung": beschreibung,
        "status":       status,
        "herkunft":     str(z.get("herkunft") or "-").strip().lower(),
        "erstellt":     str(z.get("erstellt") or "-").strip(),
        "braucht":      str(z.get("braucht") or "").strip(),
        "vermerk":      str(z.get("vermerk") or "").strip(),
    }


def alle() -> list:
    """Alle Skills, nach Name sortiert: [{name, beschreibung, status,
    herkunft, erstellt, braucht, vermerk}]."""
    wurzel = ordner()
    raus = []
    for name in sorted(os.listdir(wurzel)):
        pfad = os.path.join(wurzel, name)
        if skill_format.gueltiger_name(name) and \
                os.path.isfile(os.path.join(pfad, skill_format.SKILL_MD)):
            raus.append(_eintrag(name, pfad))
    return raus


def aktive() -> list:
    return [s for s in alle() if s["status"] == "aktiv"]


def _kuerzen(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def prompt_block() -> str:
    """Die Skill-Liste für den FESTEN Teil des Cloud-Prompts.

    Byte-stabil, solange sich kein Skill ändert: nach Name sortiert, nur
    aktive, nur Name und Beschreibung (einzeilig). Kein Datum, kein Zähler —
    sonst bräche der Prompt-Cache bei jedem Zug. Höchstens LISTE_MAX
    Zeichen; was darüber ginge, wird gleichmäßig gekürzt."""
    liste = aktive()
    if not liste:
        return ""
    kopf = ("## Skills\n"
            "Anleitungen für bestimmte Arten von Aufgaben. Den Inhalt holst "
            "du mit load_skill(name) — hier steht nur, wann einer passt.\n")
    deckel = MAX_BESCHREIBUNG
    while True:
        zeilen = [f"- {s['name']} — {_kuerzen(s['beschreibung'], deckel)}"
                  for s in liste]
        text = kopf + "\n".join(zeilen)
        if len(text) <= LISTE_MAX or deckel <= MIN_BESCHREIBUNG:
            break
        deckel = max(MIN_BESCHREIBUNG, deckel - 32)
    # Auch mit kurzen Beschreibungen zu lang: die hinteren nur mit Namen —
    # vorhanden bleiben alle, laden kann sie das Modell weiterhin.
    n = len(zeilen)
    while len(text) > LISTE_MAX and n > 0:
        n -= 1
        text = (kopf + "".join(z + "\n" for z in zeilen[:n])
                + "- ohne Beschreibung (zu viele): "
                + ", ".join(s["name"] for s in liste[n:]))
    return text


def _ab(ab) -> int:
    try:
        return max(0, int(ab or 0))
    except (TypeError, ValueError):
        return 0


def _seite(text: str, ab: int, weiter: str) -> str:
    stueck = text[ab:ab + SEITE]
    if ab + SEITE < len(text):
        stueck += (f"\n[… noch {len(text) - ab - SEITE} Zeichen — weiter mit "
                   f"{weiter}, ab={ab + SEITE}]")
    return stueck


# Nicht in der Datei-Liste fürs Modell (lesen ginge trotzdem): Lizenz und
# ZENTRALEs eigene Angaben sind kein Arbeitsstoff.
_NICHT_NENNEN = (skill_format.ZENTRALE_JSON, "LICENSE.txt", "LICENSE")

# ZENTRALEs Zusatz zu einem fremden Skill (2026-10-07): was davon hier geht.
# Die SKILL.md bleibt unverändert (Claude-tauglich); load_skill weist
# deshalb VOR der Anleitung auf diese Datei hin.
ZENTRALE_HINWEIS = "references/zentrale.md"


def _dateiliste(pfad: str) -> list:
    """Dateien des Skills außer SKILL.md und ZENTRALE-Eigenem, sortiert."""
    raus = []
    for ort, ordnernamen, dateinamen in os.walk(pfad):
        ordnernamen[:] = sorted(d for d in ordnernamen if not d.startswith("."))
        for n in sorted(dateinamen):
            rel = os.path.relpath(os.path.join(ort, n), pfad)
            if n.startswith(".") or n.endswith(".bak") or n in _NICHT_NENNEN \
                    or rel == skill_format.SKILL_MD:
                continue
            raus.append(rel)
    return sorted(raus)


def _schluessel(name) -> str:
    """Ordnername zu dem, was das Modell schickt („Wochenplan" → wochenplan).
    Ein schon gültiger Name bleibt, wie er ist (Claude erlaubt 64 Zeichen,
    slug kappt bei 60)."""
    name = str(name or "").strip()
    if skill_format.gueltiger_name(name):
        return name
    return gedaechtnis.slug(name).strip("-")


def _aktiv_oder_fehler(name: str) -> tuple:
    """(schluessel, ordner) eines aktiven Skills — oder (None, Fehlertext)."""
    schluessel = _schluessel(name)
    pfad = _skill_ordner(schluessel) if schluessel else None
    if not pfad:
        da = ", ".join(s["name"] for s in aktive()) or "keine"
        return None, f"[Keinen Skill {name!r}. Aktiv sind: {da}]"
    status = _eintrag(schluessel, pfad)["status"]
    if status != "aktiv":
        return None, (f"[Skill {schluessel!r} ist nicht aktiv ({status}) — "
                      f"Sasha hat ihn nicht freigegeben oder abgeschaltet. "
                      f"Arbeite ohne ihn.]")
    return schluessel, pfad


def laden(name: str, datei: str = "", ab=0) -> str:
    """Die Anleitung eines aktiven Skills fürs Modell — oder mit `datei`
    eine Datei aus seinem Ordner. Lange Texte seitenweise (`ab`)."""
    schluessel, pfad = _aktiv_oder_fehler(name)
    if not schluessel:
        return pfad
    if (datei or "").strip():
        return datei_lesen(schluessel, pfad, datei.strip(), _ab(ab))
    _, _, anleitung = skill_format.zerlegen(_skill_md(pfad))
    ab = _ab(ab)
    text = f"Skill {schluessel}:\n\n" if ab == 0 else ""
    if ab == 0 and os.path.isfile(os.path.join(pfad, ZENTRALE_HINWEIS)):
        text += (f"[Zuerst lesen: load_skill(name={schluessel!r}, datei="
                 f"{ZENTRALE_HINWEIS!r}) — was von dieser Anleitung in ZENTRALE "
                 f"geht und was nicht.]\n\n")
    text += _seite(anleitung, ab, f"load_skill(name={schluessel!r})")
    if ab == 0:
        text += _dateien_hinweis(schluessel, pfad)
    return text


def _dateien_hinweis(schluessel: str, pfad: str) -> str:
    liste = _dateiliste(pfad)
    if not liste:
        return ""
    mehr = len(liste) - DATEIEN_LISTE_MAX
    zeilen = ", ".join(liste[:DATEIEN_LISTE_MAX])
    if mehr > 0:
        zeilen += f" … (+{mehr} weitere)"
    hinweis = (f"\n\n[Dateien im Skill: {zeilen}. Lesen: load_skill("
               f"name={schluessel!r}, datei=…).")
    if any(d.startswith("scripts/") for d in liste):
        hinweis += (f" Skripte laufen nur über run_code mit skill={schluessel!r} "
                    f"— der Ordner liegt dort nur lesend unter /skills/{schluessel}.")
    return hinweis + "]"


def datei_lesen(schluessel: str, pfad: str, datei: str, ab: int = 0) -> str:
    """Eine Datei aus dem Skill-Ordner als Text. Kein Weg hinaus: der echte
    Pfad (Verweise aufgelöst) muss im echten Skill-Ordner liegen."""
    wurzel = os.path.realpath(pfad)
    ziel = os.path.realpath(os.path.join(wurzel, datei.lstrip("/")))
    if os.path.commonpath([wurzel, ziel]) != wurzel or ziel == wurzel:
        return f"[{datei!r} liegt nicht im Skill {schluessel!r}.]"
    if os.path.isdir(ziel):
        drin = [d for d in _dateiliste(pfad)
                if d.startswith(os.path.relpath(ziel, wurzel) + os.sep)]
        return (f"[{datei!r} ist ein Ordner. Darin: "
                f"{', '.join(drin[:DATEIEN_LISTE_MAX]) or 'nichts'}]")
    if not os.path.isfile(ziel):
        da = ", ".join(_dateiliste(pfad)[:DATEIEN_LISTE_MAX]) or "keine"
        return f"[Keine Datei {datei!r} im Skill {schluessel!r}. Es gibt: {da}]"
    with open(ziel, "rb") as f:
        roh = f.read(4_000_000)
    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError:
        return (f"[{datei!r} ist keine Textdatei ({os.path.getsize(ziel)} "
                f"Bytes) — für Ausgaben gedacht, nicht zum Lesen.]")
    rel = os.path.relpath(ziel, wurzel)
    kopf = f"Skill {schluessel}, {rel}:\n\n" if ab == 0 else ""
    return kopf + _seite(text, ab, f"load_skill(name={schluessel!r}, datei={rel!r})")


def skript_ordner(name: str) -> tuple:
    """Für run_code(skill=…): (ordner, None) eines aktiven Skills oder
    (None, Fehlertext). Der Ordner wird in der Sandbox nur lesend
    eingehängt (core/sandbox.py)."""
    schluessel, pfad = _aktiv_oder_fehler(name)
    if not schluessel:
        return None, pfad
    return os.path.realpath(pfad), None


# ── Schreiben (nur über die gegateten Werkzeuge) ──────────────────────

def _pruefen_inhalt(inhalt: str) -> str | None:
    if not (inhalt or "").strip():
        return "[Fehler: leerer Inhalt]"
    if len(inhalt) > MAX_INHALT:
        return (f"[Zu lang für einen Skill ({len(inhalt)} Zeichen, höchstens "
                f"{MAX_INHALT}). Eine Anleitung, kein Handbuch.]")
    return None


def _pruefen_beschreibung(beschreibung: str) -> str | None:
    if not beschreibung:
        return "[Fehler: keine Beschreibung — wann man ihn benutzt]"
    if len(beschreibung) > MAX_BESCHREIBUNG:
        return (f"[Beschreibung zu lang ({len(beschreibung)} Zeichen, "
                f"höchstens {MAX_BESCHREIBUNG}) — sag knapper, wann er passt.]")
    if "<" in beschreibung or ">" in beschreibung:
        # Claudes Prüfung (quick_validate.py) lehnt sie ab — der Skill soll
        # zu Claude passen.
        return "[Die Beschreibung darf kein < oder > enthalten.]"
    return None


def vorschlagen(name: str, beschreibung: str, inhalt: str) -> str:
    """Einen neuen Skill anlegen (herkunft ki, status aktiv).

    Wird NUR nach Sashas Ja aufgerufen (Gate im Werkzeug-Register). Ein
    bestehender Name wird nicht überschrieben — dafür gibt es edit_skill."""
    schluessel = _schluessel(name)
    if not schluessel:
        return "[Fehler: kein Name]"
    beschreibung = " ".join((beschreibung or "").split())
    fehler = _pruefen_beschreibung(beschreibung) or _pruefen_inhalt(inhalt)
    if fehler:
        return fehler
    _, _, inhalt = skill_format.zerlegen(inhalt)     # mitgeschickter Kopf weg
    wurzel = ordner()
    pfad = os.path.join(wurzel, schluessel)
    if os.path.exists(pfad):
        return (f"[Den Skill {schluessel!r} gibt es schon — zum Ändern "
                f"edit_skill, nicht propose_skill.]")
    dateien.atomar_schreiben(os.path.join(pfad, skill_format.SKILL_MD),
                             skill_format.rendern(schluessel, beschreibung, inhalt))
    dateien.json_schreiben(os.path.join(pfad, skill_format.ZENTRALE_JSON), {
        "status": "aktiv", "herkunft": "ki",
        "erstellt": date.today().isoformat()})
    datasync.notify_change(pfad)
    return (f"Skill {schluessel!r} angelegt (aktiv). Er steht ab dem nächsten "
            f"Gespräch in der Liste; jetzt schon mit load_skill lesbar.")


def aendern(name: str, inhalt: str) -> str:
    """Die Anleitung eines bestehenden Skills ersetzen; der YAML-Kopf bleibt
    Zeichen für Zeichen (auch fremde Felder eines Claude-Skills). Die alte
    Fassung liegt danach als SKILL.md.bak daneben (wie rewrite_note)."""
    schluessel = _schluessel(name)
    pfad = _skill_ordner(schluessel) if schluessel else None
    if not pfad:
        da = ", ".join(s["name"] for s in alle()) or "keine"
        return (f"[Keinen Skill {name!r} — edit_skill ändert nur bestehende. "
                f"Es gibt: {da}]")
    # Schickt das Modell einen Kopf mit, wird er weggeworfen: Name und
    # Beschreibung ändert nur Sasha, Status und Herkunft stehen ohnehin in
    # _zentrale.json. Eine Anleitung darf aber selbst mit `---` (Trennlinie)
    # beginnen — weg kommt nur ein Kopf mit name oder description.
    roh, felder, rest = skill_format.zerlegen(inhalt or "")
    if roh is not None and ("name" in felder or "description" in felder):
        inhalt = rest
    fehler = _pruefen_inhalt(inhalt)
    if fehler:
        return fehler
    datei = os.path.join(pfad, skill_format.SKILL_MD)
    alt = _skill_md(pfad)
    dateien.atomar_schreiben(datei + ".bak", alt)
    dateien.atomar_schreiben(datei, skill_format.mit_neuer_anleitung(alt, inhalt))
    datasync.notify_change(datei)
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


# ── Schalten (nur Sasha, über die TUI) ────────────────────────────────

def status_setzen(name: str, status: str) -> dict:
    """Einen Skill an- oder ausschalten (oder auf „vorgeschlagen" setzen).

    2026-10-07, Phase 3: Sasha soll dafür nicht in eine Datei müssen — die
    TUI schaltet über POST /api/skills/<name>/status. Nur _zentrale.json
    ändert sich, die SKILL.md bleibt. Kein Werkzeug der KI ruft das: was
    Sasha abschaltet, bleibt aus.
    → der Skill wie in alle(). Wirft KeyError (unbekannt), ValueError
    (unbekannter Status)."""
    status = (status or "").strip().lower()
    if status not in STATUS:
        raise ValueError(f"unbekannter Status {status!r} (erlaubt: {', '.join(STATUS)})")
    # Nur der genaue Ordnername: eine Route soll keinen Skill über eine
    # Schreibvariante („Wochen Plan") treffen, den Sasha so nie sah.
    pfad = _skill_ordner(name)
    if not pfad:
        raise KeyError(name)
    z = _zentrale(pfad)
    if str(z.get("status") or "").strip().lower() != status:
        z["status"] = status
        datei = os.path.join(pfad, skill_format.ZENTRALE_JSON)
        dateien.json_schreiben(datei, z)
        datasync.notify_change(datei)
    return _eintrag(name, pfad)
