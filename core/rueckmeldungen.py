# core/rueckmeldungen.py
#
# Bewertungen der KI-Antworten (gut/schlecht, optional ein Kommentar).
#
# Sasha, 08.10.2026: „bewertungen für uns um unser eigenes system zu
# verbessern … so dass ich nen kommentar hinzufügen könnte wenn ich wollte."
# Wofür: Sasha und Claude gehen sie gemeinsam durch und verbessern damit
# Prompt, Skills und Werkzeuge. Sie gehen NIRGENDWOHIN raus — kein Anbieter
# sieht sie, keine KI liest sie von selbst (kein Werkzeug, nicht im Prompt).
#
# ── Ablage: eine Datei pro Rechner, nur anhängen ──────────────────────────
#   data/rueckmeldungen/<knoten>.jsonl
# Derselbe Grund wie bei den Gesprächen (core/gespraeche.py): der Sync ist
# rsync „neueste Datei gewinnt". Schrieben PC und Laptop in eine Datei,
# verlöre einer seine Bewertungen. Eine Zeile = ein Ereignis; eine Bewertung
# ändern = ein neues Ereignis für dieselbe Nachricht, das letzte gilt. So
# wird nie etwas überschrieben oder gelöscht.
#
# Je Ereignis steht dabei, WER geantwortet hat (Anbieter, Modell) und welche
# Werkzeuge und Skills die Antwort benutzt hat — genau das braucht man, um
# später zu sehen, wo es hakt (z. B. „schlecht" fast immer nach web_search).
#
# Umlenkbar per Einstellung rueckmeldungen_dir (Env
# ZENTRALE_RUECKMELDUNGEN_DIR; Tests, tests/conftest.py).
#
# Schicht 2 (memory/system/bauplan_kern.md): liest Gespräche, weiß nichts
# von Modellen.

import json
import os
import threading
import uuid

import ai_config
import datasync
import dateien
import gespraeche

WERTE = (1, -1)                 # gut, schlecht
KOMMENTAR_MAX = 2000            # Zeichen; ein Kommentar ist eine Notiz, kein Aufsatz
AUSSCHNITT = 160                # so viel von der Antwort zeigt die Liste

_lock = threading.Lock()


class Ungueltig(ValueError):
    """Wert oder Kommentar passt nicht — der Text ist für Menschen."""


class Unbekannt(KeyError):
    """Kein Gespräch oder keine Antwort mit dieser id."""


# ── Wo ──────────────────────────────────────────────────────────────────

def ordner() -> str:
    eigen = ai_config.setting("rueckmeldungen_dir")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                        "data", "rueckmeldungen"))


# ── Was die Antwort benutzt hat ─────────────────────────────────────────

def _arg(args, name):
    """'name=wochenplan, datei=x' → 'wochenplan' für name='name'."""
    for teil in str(args or "").split(","):
        k, _, v = teil.partition("=")
        if k.strip() == name and v.strip():
            return v.strip()
    return ""


def benutzt(nachricht) -> tuple:
    """(werkzeuge, skills) einer gespeicherten Antwort, je ohne Doppelte in
    der Reihenfolge des ersten Aufrufs. Skills: was load_skill geladen und
    run_code(skill=…) benutzt hat."""
    werkzeuge, skills = [], []
    for w in (nachricht or {}).get("werkzeuge") or []:
        if not isinstance(w, dict):
            continue
        name = str(w.get("name") or "").strip()
        if name and name not in werkzeuge:
            werkzeuge.append(name)
        skill = (_arg(w.get("args"), "name") if name == "load_skill"
                 else _arg(w.get("args"), "skill") if name == "run_code" else "")
        if skill and skill not in skills:
            skills.append(skill)
    return werkzeuge, skills


# ── Schreiben ───────────────────────────────────────────────────────────

def _antwort(gid, nachricht_id):
    """Die geltende Antwort (Rolle assistant) oder Unbekannt."""
    if not gespraeche.gibt_es(gid):
        raise Unbekannt(gid)
    n = next((n for n in gespraeche.nachrichten(gid, versteckte=True)
              if n.get("id") == nachricht_id), None)
    if n is None or n.get("rolle") != "assistant":
        raise Unbekannt(nachricht_id)
    return n


def bewerten(gid, nachricht_id, wert, kommentar="", knoten=None) -> dict:
    """Eine Antwort bewerten (oder die Bewertung ändern). -> das Ereignis.
    Wirft Ungueltig (Wert, Kommentar) bzw. Unbekannt (Gespräch, Antwort)."""
    try:
        wert = int(wert)
    except (TypeError, ValueError):
        raise Ungueltig("Bewertung muss +1 (gut) oder -1 (schlecht) sein.")
    if wert not in WERTE:
        raise Ungueltig("Bewertung muss +1 (gut) oder -1 (schlecht) sein.")
    kommentar = str(kommentar or "").strip()
    if len(kommentar) > KOMMENTAR_MAX:
        raise Ungueltig("Der Kommentar ist zu lang (höchstens %d Zeichen)." % KOMMENTAR_MAX)
    n = _antwort(gid, nachricht_id)
    werkzeuge, skills = benutzt(n)
    kn = dateien.sicherer_name(knoten or dateien.knoten())
    e = {"id": uuid.uuid4().hex, "ts": gespraeche.jetzt_ts(), "knoten": kn,
         "gespraech": gid, "nachricht": nachricht_id, "wert": wert}
    if kommentar:
        e["kommentar"] = kommentar
    for feld in ("anbieter", "modell"):
        if n.get(feld):
            e[feld] = n[feld]
    if werkzeuge:
        e["werkzeuge"] = werkzeuge
    if skills:
        e["skills"] = skills
    zeile = (json.dumps(e, ensure_ascii=False) + "\n").encode("utf-8")
    os.makedirs(ordner(), exist_ok=True)
    pfad = os.path.join(ordner(), kn + ".jsonl")
    # Wie core/gespraeche.py: eine Zeile, ein write() mit O_APPEND, fsync —
    # nach einem Absturz fehlt höchstens die letzte Zeile, die das Lesen
    # überspringt. Nie überschreiben, nie löschen.
    with _lock:
        fd = os.open(pfad, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, zeile)
            os.fsync(fd)
        finally:
            os.close(fd)
    datasync.notify_change()
    return e


# ── Lesen ───────────────────────────────────────────────────────────────

def ereignisse() -> list:
    """Alle Ereignisse aller Rechner, älteste zuerst."""
    raus = []
    try:
        namen = sorted(os.listdir(ordner()))
    except OSError:
        return []
    for name in namen:
        if not name.endswith(".jsonl") or name.startswith("."):
            continue
        try:
            with open(os.path.join(ordner(), name), encoding="utf-8") as f:
                for nr, zeile in enumerate(f):
                    try:
                        e = json.loads(zeile)
                    except ValueError:
                        continue            # halbe Zeile nach Absturz
                    if isinstance(e, dict) and e.get("ts") and e.get("nachricht") \
                            and e.get("wert") in WERTE:
                        raus.append((str(e["ts"]), str(e.get("knoten") or ""), nr, e))
        except OSError:
            continue
    raus.sort(key=lambda t: t[:3])
    return [t[3] for t in raus]


def aktuelle(gid=None) -> list:
    """Die geltende Bewertung je Antwort (das letzte Ereignis), neueste
    zuerst. gid: nur die eines Gesprächs."""
    letzte = {}
    for e in ereignisse():
        if gid and e.get("gespraech") != gid:
            continue
        letzte[(e.get("gespraech"), e["nachricht"])] = e
    return sorted(letzte.values(), key=lambda e: e["ts"], reverse=True)


def mit_kontext(liste) -> list:
    """Bewertungen für die Liste in Customize → Feedback: dazu Titel des
    Gesprächs und ein Ausschnitt der Antwort. Eine inzwischen verworfene
    Antwort (wiederholt/bearbeitet) bekommt verworfen=True statt Ausschnitt."""
    texte, titel = {}, {}
    raus = []
    for e in liste:
        e = dict(e)
        gid = e.get("gespraech")
        if gid not in texte:
            try:
                texte[gid] = {n["id"]: n for n in gespraeche.nachrichten(gid, versteckte=True)}
                titel[gid] = gespraeche.kopf(gid).get("titel") or ""
            except (gespraeche.Unbekannt, OSError, ValueError):
                texte[gid], titel[gid] = {}, ""
        n = texte[gid].get(e["nachricht"])
        e["gespraech_titel"] = titel[gid]
        if n is None:
            e["verworfen"] = True
            e["ausschnitt"] = ""
        else:
            t = " ".join(gespraeche.text_fuer_ki(n).split())
            e["ausschnitt"] = t if len(t) <= AUSSCHNITT else t[:AUSSCHNITT - 1] + "…"
        raus.append(e)
    return raus
