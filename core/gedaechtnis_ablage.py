# core/gedaechtnis_ablage.py
#
# Wie das Gedächtnis auf der Platte liegt: nach THEMEN, im Format von Claudes
# eigenem Datei-Gedächtnis. Hier nur Pfade, Datei-Kopf und Index — was die KI
# damit tut (anhängen, Katalog, Tagebuch …), steht in core/gedaechtnis.py.
#
# ── Warum nach Thema (2026-10-11) ──────────────────────────────────────
# Sasha: „wir sortieren momentan nach datenformat, FALSCH. wir sollten nach
# thema sortieren." Bis dahin lag der Spagat in dossiers/, die Übungen in
# kataloge/, die Kurve in data/g_*.json — drei Ordner für EINE Sache. Jetzt:
#
#   <wurzel>/
#     INDEX.md                  eine Zeile je Datei, nach Thema (wie MEMORY.md)
#     themen/<thema>/<name>.md  Notiz, Dossier, Quelle … (art steht im Kopf)
#     themen/<thema>/<name>.katalog.md   viele gleichförmige Einträge
#     themen/<thema>/<name>.reihe.json   Messreihe (+ <name>.reihe.md als Kopf)
#     themen/tagebuch/<JJJJ-MM>.md
#     ki/hausregeln.md, ki/vorlagen/, ki/skills/   Gedächtnis ÜBER die KI
#     _archiv/                  was nicht mehr gilt — archiviert, nie gelöscht
#
# Der Kopf jeder Datei ist der von Claude (name, description, metadata), damit
# ein Export/Import in beide Richtungen ohne Umbau geht:
#
#   ---
#   name: spagat
#   description: Voller Spagat — wo es blockiert, Plan, Stand
#   metadata:
#     art: dossier
#     aktualisiert: 2026-10-11
#   ---
#
# Die Wurzel kommt immer als Argument herein (gedaechtnis._DIR): Tests und der
# Prüfstand lenken sie dort um, und eine zweite Stelle mit eigener Meinung
# über die Wurzel wäre ein Weg ins echte data/.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import re
from datetime import date, datetime

import dateien

THEMEN = "themen"
KI = "ki"
ARCHIV = "_archiv"
INDEX = "INDEX.md"
TAGEBUCH = "tagebuch"
ALLGEMEIN = "allgemein"

# Was eine Datei sein kann. Frei erweiterbar — die Art steuert nur, WIE
# angehängt wird (gedaechtnis.notieren), nicht wo die Datei liegt.
ARTEN = ("notiz", "dossier", "projekt", "quelle", "tagebuch", "ziel",
         "steckbrief", "regel", "katalog", "messreihe", "vorlage")

# Arten mit eigener Endung: die Form ist dann am Dateinamen ablesbar, und
# `training.md` (Dossier) und `training.katalog.md` können nebeneinander
# liegen, ohne sich zu überschreiben.
_ENDUNG = {"katalog": ".katalog.md", "messreihe": ".reihe.md"}
REIHE_JSON = ".reihe.json"


def slug(name: str) -> str:
    """Datei- oder Themenname aus einem Titel. Wirft alles außer a-z, 0-9 und
    Bindestrich weg — so kommt kein `../` und kein Pfad hindurch."""
    s = (name or "").strip().lower()
    s = (s.replace("ä", "ae").replace("ö", "oe")
          .replace("ü", "ue").replace("ß", "ss"))
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60]


def endung(art: str) -> str:
    return _ENDUNG.get(art, ".md")


# ── Der Kopf (Claudes Format) ─────────────────────────────────────────

def _wert(roh: str) -> str:
    roh = roh.strip()
    if len(roh) >= 2 and roh[0] == roh[-1] == '"':
        try:
            return str(json.loads(roh))
        except ValueError:
            return roh[1:-1]
    if len(roh) >= 2 and roh[0] == roh[-1] == "'":
        return roh[1:-1].replace("''", "'")
    return roh


def zerlegen(text: str) -> tuple:
    """Text → (kopf, rumpf). kopf: {name, description, metadata: {…}, …};
    fremde Felder (Claudes `type:` u. a.) bleiben drin. Ohne Kopf: ({}, text).
    Wirft nie."""
    text = (text or "").replace("\r\n", "\n").lstrip("﻿")
    if not text.startswith("---\n"):
        return {}, text
    ende = text.find("\n---", 3)
    if ende < 0:
        return {}, text
    roh, rumpf = text[4:ende], text[ende + 4:]
    rumpf = rumpf[1:] if rumpf.startswith("\n") else rumpf
    kopf, block = {}, None
    for zeile in roh.split("\n"):
        if not zeile.strip() or zeile.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\s*)([A-Za-z_][\w-]*)\s*:\s*(.*)$", zeile)
        if not m:
            continue
        einzug, schluessel, wert = m.groups()
        if einzug and block is not None:
            kopf[block][schluessel] = _wert(wert)
        elif not einzug:
            if wert.strip():
                kopf[schluessel], block = _wert(wert), None
            else:
                kopf[schluessel], block = {}, schluessel
    return kopf, rumpf.lstrip("\n")


def _yaml_wert(wert) -> str:
    """Einfach, solange es einfach geht; sonst in Anführungszeichen (JSON ist
    gültiges YAML) — ein Doppelpunkt in der Beschreibung bricht so nichts."""
    s = " ".join(str(wert).split())
    if not s or re.search(r"(: |\s#|^[-?:,\[\]{}#&*!|>'\"%@`])|:$", s):
        return json.dumps(s, ensure_ascii=False)
    return s


def kopf_rendern(kopf: dict) -> str:
    """kopf (wie zerlegen ihn liefert) → der Block zwischen den `---`."""
    zeilen = ["---"]
    for schluessel in ("name", "description"):
        if kopf.get(schluessel) not in (None, ""):
            zeilen.append(f"{schluessel}: {_yaml_wert(kopf[schluessel])}")
    for schluessel, wert in kopf.items():
        if schluessel in ("name", "description", "metadata"):
            continue
        if isinstance(wert, dict):
            zeilen.append(f"{schluessel}:")
            zeilen += [f"  {k}: {_yaml_wert(v)}" for k, v in wert.items()]
        else:
            zeilen.append(f"{schluessel}: {_yaml_wert(wert)}")
    meta = kopf.get("metadata")
    if isinstance(meta, dict) and meta:
        zeilen.append("metadata:")
        zeilen += [f"  {k}: {_yaml_wert(v)}" for k, v in meta.items()]
    zeilen.append("---")
    return "\n".join(zeilen) + "\n"


def neuer_kopf(name: str, beschreibung: str, art: str, **mehr) -> dict:
    meta = {"art": art, "aktualisiert": date.today().isoformat()}
    meta.update({k: v for k, v in mehr.items() if v not in (None, "")})
    return {"name": name, "description": " ".join((beschreibung or "").split()),
            "metadata": meta}


def text_bauen(kopf: dict, rumpf: str) -> str:
    rumpf = (rumpf or "").strip("\n")
    return kopf_rendern(kopf) + ("\n" + rumpf.rstrip() + "\n" if rumpf.strip() else "")


def art_von(kopf: dict) -> str:
    meta = kopf.get("metadata")
    art = meta.get("art") if isinstance(meta, dict) else None
    return art or kopf.get("type") or "notiz"


# ── Dateien finden ────────────────────────────────────────────────────

def themen_ordner(wurzel: str) -> str:
    return os.path.join(wurzel, THEMEN)


def thema_ordner(wurzel: str, thema: str) -> str:
    return os.path.join(wurzel, THEMEN, slug(thema) or ALLGEMEIN)


def pfad(wurzel: str, thema: str, name: str, art: str = "notiz") -> str:
    return os.path.join(thema_ordner(wurzel, thema), slug(name) + endung(art))


def _stamm(dateiname: str) -> tuple:
    """'ideen.katalog.md' → ('ideen', '.katalog.md')."""
    for e in sorted(set(_ENDUNG.values()), key=len, reverse=True):
        if dateiname.endswith(e):
            return dateiname[:-len(e)], e
    return dateiname[:-3], ".md"


def endung_von(pfad: str) -> str:
    """'…/ideen.katalog.md' → '.katalog.md', '…/spagat.md' → '.md'."""
    return _stamm(os.path.basename(pfad))[1]


def eintrag(wurzel: str, voll: str) -> dict:
    """Eine Datei als dict: pfad, rel, thema, name, endung, kopf, rumpf, art,
    beschreibung."""
    try:
        with open(voll, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = ""
    kopf, rumpf = zerlegen(text)
    name, end = _stamm(os.path.basename(voll))
    rel = os.path.relpath(voll, wurzel).replace(os.sep, "/")
    teile = rel.split("/")
    thema = teile[1] if teile[0] == THEMEN and len(teile) > 2 else teile[0]
    return {"pfad": voll, "rel": rel, "thema": thema, "name": name,
            "endung": end, "kopf": kopf, "rumpf": rumpf, "art": art_von(kopf),
            "beschreibung": " ".join(str(kopf.get("description") or "").split())}


def themen(wurzel: str) -> list:
    ordner = themen_ordner(wurzel)
    if not os.path.isdir(ordner):
        return []
    return sorted(t for t in os.listdir(ordner)
                  if not t.startswith((".", "_")) and os.path.isdir(os.path.join(ordner, t)))


def dateien_im_thema(wurzel: str, thema: str) -> list:
    """Die .md-Dateien eines Themas (ohne Unterordner wie dateien/)."""
    ordner = thema_ordner(wurzel, thema)
    if not os.path.isdir(ordner):
        return []
    return [os.path.join(ordner, f) for f in sorted(os.listdir(ordner))
            if f.endswith(".md") and not f.startswith(".")]


def alle(wurzel: str) -> list:
    """Alle Themen-Dateien als eintrag-dicts, nach Thema und Name sortiert."""
    return [eintrag(wurzel, p) for t in themen(wurzel) for p in dateien_im_thema(wurzel, t)]


def name_zerlegen(name: str) -> tuple:
    """'themen/sport/training.katalog.md' | 'sport/training' | 'training'
    → (thema oder '', stamm, endung oder '')."""
    roh = (name or "").strip().strip("/")
    if roh.startswith(THEMEN + "/"):
        roh = roh[len(THEMEN) + 1:]
    thema = ""
    if "/" in roh:
        thema, roh = roh.rsplit("/", 1)
        thema = slug(thema.split("/")[-1])
    end = ""
    if roh.endswith(".md"):
        roh, end = _stamm(roh)
    else:
        for e in _ENDUNG.values():
            if roh.endswith(e[:-3]):
                roh, end = roh[:-len(e) + 3], e
                break
    return thema, slug(roh), end


def finden(wurzel: str, name: str, thema: str = "", endungen=None) -> list:
    """Alle Dateien, die zu `name` passen — erst im genannten Thema, sonst in
    allen. Ohne Endung zählt die schlichte .md vor .katalog.md vor .reihe.md
    (die Reihenfolge von `endungen`)."""
    t, stamm, end = name_zerlegen(name)
    thema = slug(thema) or t
    if not stamm:
        return []
    folge = [end] if end else list(endungen or (".md", ".katalog.md", ".reihe.md"))
    orte = [thema] if thema else themen(wurzel)
    for e in folge:
        treffer = [os.path.join(thema_ordner(wurzel, o), stamm + e) for o in orte]
        treffer = [p for p in treffer if os.path.isfile(p)]
        if treffer:
            return treffer
    return []


# ── Schreiben und Archivieren ─────────────────────────────────────────

def schreiben(voll: str, text: str) -> None:
    os.makedirs(os.path.dirname(voll), exist_ok=True)
    dateien.atomar_schreiben(voll, text)


def kopf_auffrischen(kopf: dict) -> dict:
    """`aktualisiert` auf heute setzen (eine Kopie)."""
    kopf = dict(kopf)
    meta = dict(kopf.get("metadata") or {}) if isinstance(kopf.get("metadata"), dict) else {}
    meta["aktualisiert"] = date.today().isoformat()
    kopf["metadata"] = meta
    return kopf


def archivieren(wurzel: str, voll: str) -> str:
    """Datei nach _archiv/ (gleicher relativer Pfad) — nie löschen: der
    Abgleich ist additiv, und was falsch war, will Sasha vielleicht noch
    nachlesen. Liegt dort schon eine, bekommt die neue einen Zeitstempel.
    → der neue Pfad."""
    rel = os.path.relpath(voll, wurzel)
    ziel = os.path.join(wurzel, ARCHIV, rel)
    if os.path.exists(ziel):
        basis, end = os.path.splitext(ziel)
        ziel = f"{basis}.{datetime.now().strftime('%Y%m%d-%H%M%S')}{end}"
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    os.replace(voll, ziel)
    return ziel


# ── Messreihen ────────────────────────────────────────────────────────

def reihe_stamm(gid: str) -> str:
    """Graph-id → Dateistamm: 'g_sleep' → 'sleep' (umkehrbar, kein slug —
    die id ist schon dateisicher, core/graphs._slug)."""
    gid = str(gid or "")
    return gid[2:] if gid.startswith("g_") else gid


def reihe_finden(wurzel: str, gid: str) -> str | None:
    """Wo die Werte einer Messreihe unter einem Thema liegen, sonst None."""
    stamm = reihe_stamm(gid)
    if not stamm or "/" in stamm or stamm.startswith("."):
        return None
    for t in themen(wurzel):
        p = os.path.join(thema_ordner(wurzel, t), stamm + REIHE_JSON)
        if os.path.isfile(p):
            return p
    return None


# ── Der Index (wie Claudes MEMORY.md) ─────────────────────────────────

def index_text(wurzel: str) -> str:
    """Eine Zeile je Datei, nach Thema gruppiert. Byte-stabil, solange keine
    Datei dazukommt, wegfällt oder ihre Beschreibung/Art ändert — der Index
    steht im gecachten Prompt-Kopf, und `aktualisiert` steht deshalb NICHT
    drin (sonst bräche jedes Anhängen den Cache)."""
    bloecke = []
    for t in themen(wurzel):
        eintraege = [eintrag(wurzel, p) for p in dateien_im_thema(wurzel, t)]
        if not eintraege:
            continue
        if t == TAGEBUCH:
            monate = [e["name"] for e in eintraege]
            bloecke.append(f"## {TAGEBUCH}\n- {len(monate)} Monat(e): "
                           f"{monate[0]} … {monate[-1]} — read_note('tagebuch') ist heute, "
                           f"'tagebuch/JJJJ-MM' ein Monat")
            continue
        zeilen = [f"## {t}"]
        for e in eintraege:
            art = e["art"] if e["art"] not in ("notiz",) else ""
            haken = e["beschreibung"]
            zeile = f"- [{e['name']}]({e['rel']})"
            if art:
                zeile += f" ({art})"
            if haken:
                zeile += f" — {haken}"
            zeilen.append(zeile)
        bloecke.append("\n".join(zeilen))
    return "\n\n".join(bloecke)


def index_schreiben(wurzel: str) -> bool:
    """INDEX.md neu schreiben, wenn er sich geändert hat. → geändert?"""
    text = "# Gedächtnis — Index\n\n" + (index_text(wurzel) or "(noch leer)") + "\n"
    voll = os.path.join(wurzel, INDEX)
    try:
        with open(voll, encoding="utf-8") as f:
            if f.read() == text:
                return False
    except OSError:
        pass
    schreiben(voll, text)
    return True
