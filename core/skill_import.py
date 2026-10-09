# core/skill_import.py
#
# Claude-Skills übernehmen: aus einer .zip oder einem Ordner, so wie Claude
# sie weitergibt, nach data/gedaechtnis/skills/<name>/.
#
# 2026-10-09, Gespräch 20261009-155510: Sasha legte „Chefkoch ai-v1.zip" in
# den ZENTRALE-Ordner und bat, den Skill zu importieren. Es gab keinen Weg —
# die KI hätte ihn höchstens Datei für Datei abschreiben können.
#
# Woher: nur aus Sashas Input/ (core/nutzer_ordner.py) — dorthin legt er,
# was die KI übernehmen soll.
#
# Erkannte Formen (nach dem Auspacken; ein einzelner Hüllordner wird
# übersprungen):
#   Plugin        .claude-plugin/plugin.json + skills/<name>/SKILL.md
#                 (mehrere Skills: alle in einem Rutsch, ganz oder gar nicht)
#   Skill-Ordner  <name>/SKILL.md, auch mehrere nebeneinander
#   Zip           SKILL.md direkt in der Wurzel
#
# Sicherheit: Sasha hat die Datei genannt und am Gate ja gesagt — trotzdem
# kommt nichts heraus, was aus dem Arbeitsordner zeigt (absolute Pfade, `..`,
# Verweise/Symlinks), und nichts über MAX_BYTES / MAX_DATEIEN. Versteckte
# Dateien und solche, die nach Schlüssel aussehen (context._is_secret),
# bleiben draußen: was im Skill liegt, kann load_skill an den Anbieter
# schicken. Ausgepackt wird in einen versteckten Ordner IM Skill-Ordner
# (dieselbe Platte → os.rename ist atomar; alle()/Sicherung übersehen
# Versteckte), geprüft, dann umbenannt. Ein Name, den es schon gibt, bricht
# ab — überschrieben wird nie (die KI soll Sasha fragen).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from datetime import date

import context
import datasync
import dateien
import nutzer_ordner
import skill_format
import skills

MAX_BYTES = 20 * 1024 * 1024      # entpackt, alle Dateien zusammen
MAX_DATEIEN = 500
PLUGIN_ORDNER = ".claude-plugin"
_AUSLASSEN = {"__MACOSX", "__pycache__"}


class Fehler(Exception):
    """Abbruch mit Code aus core/fehlercodes.py."""

    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code = code
        self.grund = grund


# ── Quelle ─────────────────────────────────────────────────────────────

def quelle(pfad) -> str:
    """Der echte Pfad zu dem, was Sasha nennt — NUR in seinem Input/
    (core/nutzer_ordner.py, seit 2026-10-09: der Assistent greift nicht mehr
    in den Projektbaum). „x.zip" und „Input/x.zip" meinen dasselbe; ein
    absoluter Pfad zählt nur, wenn er (Verweise aufgelöst) in Input/ liegt."""
    roh = str(pfad or "").strip()
    if not roh:
        raise Fehler("S-QUELLE-FEHLT", "kein Pfad angegeben")
    echt = nutzer_ordner.aufloesen(roh, erlaubt=(nutzer_ordner.INPUT,))
    if echt is None:
        raise Fehler("S-QUELLE-AUSSERHALB",
                     f"„{roh}“ liegt nicht in {nutzer_ordner.anzeige(nutzer_ordner.unterordner())}/")
    if not os.path.exists(echt):
        raise Fehler("S-QUELLE-FEHLT", f"„{roh}“ gibt es nicht in Input/ — mit find_files suchen")
    if os.path.basename(echt) == skill_format.SKILL_MD:
        echt = os.path.dirname(echt)              # die SKILL.md selbst genannt
    rel = os.path.relpath(echt, nutzer_ordner.wurzel())
    if any(t.startswith(".") for t in rel.split(os.sep)) or context._is_secret(rel):
        raise Fehler("S-QUELLE-GESPERRT", "versteckt oder nach Schlüssel aussehend")
    if os.path.isfile(echt) and not zipfile.is_zipfile(echt):
        raise Fehler("S-ZIP-KAPUTT", f"„{os.path.basename(echt)}“ ist keine Zip-Datei")
    return echt


# ── Auspacken ──────────────────────────────────────────────────────────

def _auslassen(teile) -> bool:
    """Versteckt (außer .claude-plugin), Mac-/Python-Ballast, Schlüssel."""
    for t in teile:
        if t in _AUSLASSEN or (t.startswith(".") and t != PLUGIN_ORDNER):
            return True
    return context._is_secret(teile[-1])


def _zip_auspacken(datei: str, ziel: str) -> int:
    """→ Zahl der ausgelassenen Dateien. Prüft ALLE Einträge, bevor eine
    Datei entsteht; die Größe zählt beim Auspacken mit (die Angabe im
    Verzeichnis der Zip kann lügen)."""
    try:
        zf = zipfile.ZipFile(datei)
    except (zipfile.BadZipFile, OSError) as e:
        raise Fehler("S-ZIP-KAPUTT", f"die Zip lässt sich nicht öffnen ({e})")
    with zf:
        eintraege = []
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            teile = [t for t in name.split("/") if t not in ("", ".")]
            if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or ".." in teile:
                raise Fehler("S-UNSICHER", f"Pfad zeigt nach draußen: {info.filename}")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise Fehler("S-UNSICHER", f"Verweis (Symlink) in der Zip: {info.filename}")
            if info.flag_bits & 0x1:
                raise Fehler("S-ZIP-KAPUTT", "die Zip ist verschlüsselt")
            if teile and not info.is_dir():
                eintraege.append((info, teile))
        if len(eintraege) > MAX_DATEIEN:
            raise Fehler("S-ZU-GROSS", f"{len(eintraege)} Dateien, höchstens {MAX_DATEIEN}")
        if sum(i.file_size for i, _ in eintraege) > MAX_BYTES:
            raise Fehler("S-ZU-GROSS", f"entpackt über {MAX_BYTES // 2**20} MB")
        ausgelassen, summe = 0, 0
        for info, teile in eintraege:
            if _auslassen(teile):
                ausgelassen += 1
                continue
            pfad = os.path.join(ziel, *teile)
            os.makedirs(os.path.dirname(pfad), exist_ok=True)
            try:
                with zf.open(info) as q, open(pfad, "wb") as z:
                    while True:
                        stueck = q.read(1 << 16)
                        if not stueck:
                            break
                        summe += len(stueck)
                        if summe > MAX_BYTES:
                            raise Fehler("S-ZU-GROSS", f"entpackt über {MAX_BYTES // 2**20} MB")
                        z.write(stueck)
            except (zipfile.BadZipFile, OSError, EOFError, RuntimeError) as e:
                raise Fehler("S-ZIP-KAPUTT", f"{info.filename} lässt sich nicht entpacken ({e})")
    return ausgelassen


def _ordner_kopieren(quelle_: str, ziel: str) -> int:
    """Wie _zip_auspacken, für einen Ordner: erst alles prüfen, dann kopieren."""
    liste, ausgelassen, summe = [], 0, 0
    for ort, ordner, namen in os.walk(quelle_):
        for n in ordner + namen:
            p = os.path.join(ort, n)
            if os.path.islink(p):
                raise Fehler("S-UNSICHER", f"Verweis (Symlink) im Ordner: "
                                           f"{os.path.relpath(p, quelle_)}")
        ordner[:] = [o for o in ordner if not _auslassen([o])]
        for n in namen:
            p = os.path.join(ort, n)
            teile = os.path.relpath(p, quelle_).split(os.sep)
            if _auslassen(teile):
                ausgelassen += 1
                continue
            if not os.path.isfile(p):
                raise Fehler("S-UNSICHER", f"keine normale Datei: {'/'.join(teile)}")
            summe += os.path.getsize(p)
            liste.append((p, teile))
    if len(liste) > MAX_DATEIEN:
        raise Fehler("S-ZU-GROSS", f"{len(liste)} Dateien, höchstens {MAX_DATEIEN}")
    if summe > MAX_BYTES:
        raise Fehler("S-ZU-GROSS", f"über {MAX_BYTES // 2**20} MB")
    for p, teile in liste:
        z = os.path.join(ziel, *teile)
        os.makedirs(os.path.dirname(z), exist_ok=True)
        shutil.copyfile(p, z)
    return ausgelassen


def _auspacken(echt: str, ziel: str) -> int:
    os.makedirs(ziel, exist_ok=True)
    if os.path.isdir(echt):
        return _ordner_kopieren(echt, ziel)
    return _zip_auspacken(echt, ziel)


# ── Erkennen und prüfen ────────────────────────────────────────────────

def _innen(basis: str, rel) -> str | None:
    if not isinstance(rel, str) or not rel.strip():
        return None
    p = os.path.realpath(os.path.join(basis, rel))
    return p if os.path.commonpath([basis, p]) == basis else None


def _finden(wurzel: str) -> tuple:
    """→ (Liste der Skill-Ordner, plugin.json als dict oder {})."""
    w = os.path.realpath(wurzel)
    while True:                       # Hüllordner („Chefkoch ai-v1/…") überspringen
        drin = os.listdir(w)
        if skill_format.SKILL_MD in drin or PLUGIN_ORDNER in drin or "skills" in drin:
            break
        if len(drin) == 1 and os.path.isdir(os.path.join(w, drin[0])):
            w = os.path.join(w, drin[0])
            continue
        break
    plugin = {}
    pj = os.path.join(w, PLUGIN_ORDNER, "plugin.json")
    if os.path.isfile(pj):
        try:
            with open(pj, encoding="utf-8") as f:
                plugin = json.load(f)
        except (OSError, ValueError) as e:
            raise Fehler("S-SKILL-UNGUELTIG", f"plugin.json ist kaputt ({e})")
        if not isinstance(plugin, dict):
            plugin = {}
    if os.path.isfile(os.path.join(w, skill_format.SKILL_MD)):
        return [w], plugin
    # Plugins dürfen in plugin.json eigene Skill-Pfade nennen (Claude Code).
    extra = plugin.get("skills")
    extra = extra if isinstance(extra, list) else [extra]
    behaelter = [os.path.join(w, "skills")] + [p for p in (_innen(w, e) for e in extra) if p]
    gefunden = []
    for b in behaelter:
        if os.path.isfile(os.path.join(b, skill_format.SKILL_MD)):
            gefunden.append(b)
        elif os.path.isdir(b):
            gefunden += [os.path.join(b, d) for d in sorted(os.listdir(b))
                         if os.path.isfile(os.path.join(b, d, skill_format.SKILL_MD))]
    if not gefunden:                  # nackte Skill-Ordner nebeneinander
        gefunden = [os.path.join(w, d) for d in sorted(os.listdir(w))
                    if os.path.isfile(os.path.join(w, d, skill_format.SKILL_MD))]
    if not gefunden:
        raise Fehler("S-KEIN-SKILL", "keine SKILL.md gefunden (weder in der Wurzel, "
                                     "noch in skills/<name>/, noch in <name>/)")
    return list(dict.fromkeys(gefunden)), plugin


def _pruefen(ordner_liste: list) -> list:
    """→ [(name, ordner, kopf-felder)]. Wie Claude: name und description im
    Kopf, Name nach Claudes Regeln, Beschreibung höchstens 1024 Zeichen."""
    raus, namen = [], set()
    for o in ordner_liste:
        try:
            with open(os.path.join(o, skill_format.SKILL_MD), encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise Fehler("S-SKILL-UNGUELTIG", f"SKILL.md nicht lesbar ({e})")
        _, felder, anleitung = skill_format.zerlegen(text)
        name = skill_format.text_feld(felder, "name")
        wo = os.path.basename(o)
        if not skill_format.gueltiger_name(name):
            raise Fehler("S-SKILL-UNGUELTIG",
                         f"SKILL.md in „{wo}“: Name {name or '(fehlt)'!r} ungültig "
                         f"(nur a–z, 0–9, Bindestrich, höchstens {skill_format.NAME_MAX})")
        fehler = skills._pruefen_beschreibung(skill_format.text_feld(felder, "description"))
        if fehler:
            raise Fehler("S-SKILL-UNGUELTIG", f"Skill „{name}“: {fehler.strip('[]')}")
        if not anleitung.strip():
            raise Fehler("S-SKILL-UNGUELTIG", f"Skill „{name}“: die Anleitung ist leer")
        if name in namen:
            raise Fehler("S-SKILL-UNGUELTIG", f"der Name „{name}“ kommt zweimal vor")
        namen.add(name)
        raus.append((name, o, felder))
    return raus


def _person(wert) -> str:
    if isinstance(wert, dict):
        return str(wert.get("name") or "").strip()
    return str(wert or "").strip()


def _quelle_text(echt: str, plugin: dict, felder: dict) -> str:
    """Woher der Skill kam: Dateiname, dazu Name/Version/Autor/Lizenz des
    Plugins, soweit angegeben (keine Mail-Adressen)."""
    teile = []
    if plugin:
        p = " ".join(x for x in (str(plugin.get("name") or "").strip(),
                                 str(plugin.get("version") or "").strip()) if x)
        if p:
            teile.append(f"Plugin {p}")
        if _person(plugin.get("author")):
            teile.append(f"Autor {_person(plugin.get('author'))}")
    lizenz = str(plugin.get("license") or "").strip() or skill_format.text_feld(felder, "license")
    if lizenz:
        teile.append(f"Lizenz {lizenz}")
    return os.path.basename(echt) + (f" ({', '.join(teile)})" if teile else "")


def inhalt_zaehlen(ordner: str) -> dict:
    """{referenzen, skripte, weitere} — ohne SKILL.md und ZENTRALEs Eigenes."""
    n = {"referenzen": 0, "skripte": 0, "weitere": 0}
    for ort, _, namen in os.walk(ordner):
        for name in namen:
            rel = os.path.relpath(os.path.join(ort, name), ordner).split(os.sep)
            if rel in ([skill_format.SKILL_MD], [skill_format.ZENTRALE_JSON]):
                continue
            art = {"references": "referenzen", "scripts": "skripte"}.get(rel[0], "weitere")
            n[art] += 1
    return n


# ── Vorschau (für die Frage an Sasha) und Übernehmen ───────────────────

def vorschau(pfad) -> tuple:
    """(dateiname, [skill-namen]) — für die Frage am Gate. Packt in einen
    Wegwerf-Ordner aus und prüft wie beim Übernehmen; geht das nicht, sind
    die Namen leer (der Fehler kommt dann beim Übernehmen mit Code)."""
    name = os.path.basename(str(pfad or "").rstrip("/")) or "?"
    try:
        echt = quelle(pfad)
    except Fehler:
        return name, []
    tmp = tempfile.mkdtemp(prefix="zentrale_skill_vorschau_")
    try:
        _auspacken(echt, tmp)
        return os.path.basename(echt), [n for n, _, _ in _pruefen(_finden(tmp)[0])]
    except (Fehler, OSError):
        return os.path.basename(echt), []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def uebernehmen(pfad) -> dict:
    """Die Skills aus `pfad` übernehmen: status aktiv (Sasha hat am Gate ja
    gesagt), herkunft sasha. Ganz oder gar nicht: bricht etwas ab oder steht
    danach nicht in der Skill-Liste, ist jeder neue Ordner wieder weg.
    → {namen, inhalt: {name: inhalt_zaehlen}, ausgelassen, quelle}.
    Wirft Fehler (mit Code)."""
    echt = quelle(pfad)
    wurzel = skills.ordner()
    arbeit = os.path.join(wurzel, f".import.{os.getpid()}.{uuid.uuid4().hex[:8]}")
    angelegt = []
    try:
        ausgelassen = _auspacken(echt, os.path.join(arbeit, "roh"))
        ordner_liste, plugin = _finden(os.path.join(arbeit, "roh"))
        gepruefte = _pruefen(ordner_liste)
        da = [n for n, _, _ in gepruefte if os.path.exists(os.path.join(wurzel, n))]
        if da:
            raise Fehler("S-SKILL-GIBT-ES", "schon vorhanden: " + ", ".join(da))
        heute = date.today().isoformat()
        try:
            for name, o, felder in gepruefte:
                dateien.json_schreiben(os.path.join(o, skill_format.ZENTRALE_JSON), {
                    "status": "aktiv", "herkunft": "sasha", "erstellt": heute,
                    "quelle": _quelle_text(echt, plugin, felder)})
                ziel = os.path.join(wurzel, name)
                if os.path.exists(ziel):
                    raise Fehler("S-SKILL-GIBT-ES", f"schon vorhanden: {name}")
                os.rename(o, ziel)
                angelegt.append(ziel)
            # Nachlesen: steht jeder aktiv in der Liste, die der Prompt zeigt?
            aktiv = {s["name"] for s in skills.aktive()}
            fehlt = [n for n, _, _ in gepruefte if n not in aktiv]
            if fehlt:
                raise Fehler("W-NICHT-GESPEICHERT", "nachgelesen nicht in der Skill-Liste: "
                                                   + ", ".join(fehlt))
        except BaseException:
            for z in angelegt:        # gab es vorher nicht — kein Sync hat sie gesehen
                shutil.rmtree(z, ignore_errors=True)
            raise
    except OSError as e:
        raise Fehler("S-ZIP-KAPUTT", f"Auspacken/Ablegen ging nicht ({e})")
    finally:
        shutil.rmtree(arbeit, ignore_errors=True)
    for z in angelegt:
        datasync.notify_change(z)
    namen = [n for n, _, _ in gepruefte]
    return {"namen": namen,
            "inhalt": {n: inhalt_zaehlen(os.path.join(wurzel, n)) for n in namen},
            "ausgelassen": ausgelassen,
            "quelle": _quelle_text(echt, plugin, gepruefte[0][2])}
