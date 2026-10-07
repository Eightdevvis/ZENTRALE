# core/gespraeche.py
#
# Gespräche, die einen Neustart überleben — und zwei Rechner.
#
# Bis 2026-10-07 war der Verlauf EIN Gespräch im RAM (state._chat_history,
# 50 Einträge), weg nach jedem Neustart. Claude-Web-Plan Phase 2
# (memory/ki/claude_web_plan.md, Abschnitt 4 „Gespräche auf zwei Rechnern"):
# viele Gespräche wie im Web, auf allen Rechnern gleich.
#
# ── Warum ein Ordner und eine Datei PRO RECHNER ────────────────────────
# Der Sync zwischen PC und Laptop ist rsync, additiv, „neueste Datei
# gewinnt" (memory/system/topologie.md). Schreiben beide Rechner in DIESELBE
# Datei, gewinnt eine Fassung und die Nachrichten der anderen sind weg. Also:
#
#   data/gespraeche/<id>/kopf.json        Titel, erstellt, archiviert, projekt
#   data/gespraeche/<id>/<knoten>.jsonl   nur dieser Rechner schreibt, nur anhängen
#   data/gespraeche/_knoten/<knoten>.json welches Gespräch hier offen ist, was gelesen
#
# Eine Rechner-Datei wird nur von ihrem Rechner geschrieben; auf dem anderen
# liegt höchstens eine ältere Kopie — „neueste gewinnt" ist dort immer
# richtig. kopf.json schreiben beide, aber der Kopf ist klein und eine
# verlorene Umbenennung harmlos.
#
# ── Ereignisse statt Zustand ───────────────────────────────────────────
# Eine Zeile der jsonl ist ein EREIGNIS: {id, ts, knoten, art, …}.
#   art "nachricht": rolle user/assistant, text, optional denken, werkzeuge,
#                    anbieter, modell, abgebrochen, versteckt
#   art "verwerfen": ab (Nachricht-id) — diese und alle späteren Nachrichten
#                    zählen nicht mehr (Wiederholen, Bearbeiten)
# Lesen = alle Rechner-Dateien zusammenlegen, nach ts sortieren, anwenden.
# Weil nie etwas überschrieben wird, kann auch nichts verloren gehen; ein
# „verwerfen" vom Laptop wirkt auf Nachrichten vom PC genauso.
#
# Nie löschen: ein gelöschter Ordner käme vom anderen Rechner zurück.
# Gespräche werden archiviert (Flag im Kopf).
#
# Schicht 2 (memory/system/bauplan_kern.md): weiß nichts von Modellen.
# Den Titel per Modell macht core/gespraech_titel.py (Schicht 3).

import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import datasync
import dateien

# Test-Umlenkung wie ZENTRALE_TRANSKRIPT_DIR (tests/conftest.py).
_DIR = os.environ.get("ZENTRALE_GESPRAECHE_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "gespraeche"))

# Das feste Gespräch für alles, was ZENTRALE von sich aus sagt (Kalender-
# Erinnerungen). Sasha, 07.10.: Erinnerungen bekommt der Assistent alle; sie
# landen nicht mitten in einem Thema, sondern hier, immer oben in der Liste.
ERINNERUNGEN = "erinnerungen"
ERINNERUNGEN_TITEL = "Erinnerungen"

# So viele Nachrichten gehen an die KI — dieselbe Zahl wie das alte
# deque(maxlen=50). Die Länge EINER Nachricht kappt cloud.kappen.
FENSTER = 50

# Denken wird mitgespeichert (Sashas Entscheidung 6), aber nicht endlos:
# ein langer Werkzeug-Zug denkt leicht 100.000 Zeichen.
DENKEN_GRENZE = 20000

# Vermerk hinter einer gestoppten Antwort — für die KI und die Anzeige.
VERMERK_ABGEBROCHEN = "(abgebrochen)"

# Wie ein Erinnerungs-Auftrag im Verlauf an die KI geht. Er ist eine
# Regieanweisung, kein Satz von Sasha — ohne Kennzeichnung läse das Modell
# ihn später als seine Worte (test_takt.py erklärt, warum das schadet).
AUFTRAG_VORSATZ = "[Automatischer Auftrag von ZENTRALE, nicht von Sasha geschrieben] "

_lock = threading.RLock()   # RLock: gelesen_setzen holt jetzt_ts unter dem Lock
_letzte_ts = [""]


class Unbekannt(KeyError):
    """Kein Gespräch (oder keine Nachricht) mit dieser id."""


# ── Pfade und Namen ─────────────────────────────────────────────────────

def knoten() -> str:
    """Name dieses Rechners (wie scripts/daten_sichern.py)."""
    return dateien.knoten()


def _ordner(gid=None):
    return os.path.join(_DIR, gid) if gid else _DIR


def _gueltig(gid) -> bool:
    return (isinstance(gid, str) and gid and not gid.startswith(("_", "."))
            and "/" not in gid and "\\" not in gid and gid == gid.strip())


def gibt_es(gid) -> bool:
    return _gueltig(gid) and os.path.isfile(os.path.join(_ordner(gid), "kopf.json"))


def _pruefen(gid):
    if not gibt_es(gid):
        raise Unbekannt(gid)


def jetzt_ts() -> str:
    """UTC-ISO mit Mikrosekunden, in diesem Prozess streng steigend — zwei
    Ereignisse in derselben Mikrosekunde behalten so ihre Reihenfolge."""
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    with _lock:
        if ts <= _letzte_ts[0]:
            alt = datetime.fromisoformat(_letzte_ts[0])
            ts = (alt + timedelta(microseconds=1)).isoformat(timespec="microseconds")
        _letzte_ts[0] = ts
    return ts


def _neue_id() -> str:
    # Sortiert nach Erstellzeit und ist trotzdem auf zwei Rechnern eindeutig.
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


# ── Kopf ────────────────────────────────────────────────────────────────

def _kopf_lesen(gid) -> dict:
    try:
        with open(os.path.join(_ordner(gid), "kopf.json"), encoding="utf-8") as f:
            k = json.load(f)
        return k if isinstance(k, dict) else {}
    except (OSError, ValueError):
        return {}


def _kopf_schreiben(gid, kopf):
    dateien.json_schreiben(os.path.join(_ordner(gid), "kopf.json"), kopf)
    datasync.notify_change()


def kopf(gid) -> dict:
    _pruefen(gid)
    return _kopf_lesen(gid)


def neu(titel=None, gid=None) -> str:
    """Ein Gespräch anlegen. -> id. titel None: kommt später (gespraech_titel)."""
    gid = gid or _neue_id()
    if not _gueltig(gid):
        raise ValueError(f"ungültige Gesprächs-id: {gid!r}")
    _kopf_schreiben(gid, {"titel": titel, "titel_von": "sasha" if titel else None,
                          "erstellt": jetzt_ts(), "archiviert": False,
                          "projekt": None})
    return gid


def erinnerungen() -> str:
    """Das feste Erinnerungs-Gespräch, bei Bedarf angelegt. -> id"""
    if not gibt_es(ERINNERUNGEN):
        neu(ERINNERUNGEN_TITEL, gid=ERINNERUNGEN)
    return ERINNERUNGEN


def umbenennen(gid, titel, von="sasha"):
    """Titel setzen. von: "sasha" (Hand), "modell" oder "woerter" (automatisch).
    Ein automatischer Titel überschreibt nie einen von Hand gesetzten."""
    _pruefen(gid)
    titel = " ".join(str(titel or "").split())[:120]
    if not titel:
        raise ValueError("leerer Titel")
    with _lock:
        k = _kopf_lesen(gid)
        if von != "sasha" and k.get("titel_von") == "sasha":
            return False
        k["titel"], k["titel_von"] = titel, von
        _kopf_schreiben(gid, k)
    return True


def archivieren(gid, an=True):
    """Archivieren (an=True) oder zurückholen. Gelöscht wird nie."""
    _pruefen(gid)
    with _lock:
        k = _kopf_lesen(gid)
        k["archiviert"] = bool(an)
        _kopf_schreiben(gid, k)


# ── Ereignisse schreiben ───────────────────────────────────────────────

def _anhaengen_roh(gid, ereignis, kn=None):
    kn = dateien.sicherer_name(kn or knoten())
    ereignis = dict(ereignis, id=ereignis.get("id") or uuid.uuid4().hex,
                    ts=jetzt_ts(), knoten=kn)
    zeile = json.dumps(ereignis, ensure_ascii=False) + "\n"
    pfad = os.path.join(_ordner(gid), kn + ".jsonl")
    # Eine Zeile, ein write() mit O_APPEND, dann fsync: auch zwei Threads
    # desselben Rechners zerschneiden sich keine Zeile, und nach einem
    # Stromausfall fehlt höchstens die letzte (die das Lesen überspringt).
    with _lock:
        fd = os.open(pfad, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, zeile.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
    datasync.notify_change()
    return ereignis


def anhaengen(gid, rolle, text, *, denken=None, werkzeuge=None, anbieter=None,
              modell=None, abgebrochen=False, versteckt=False, knoten=None,
              anhaenge=None, dokumente=None) -> dict:
    """Eine Nachricht anhängen. -> das Ereignis (mit id und ts).

    anhaenge (Frage) / dokumente (Antwort): VERWEISE in die Ablage
    ([{id, titel, art, …}], core/anhang.py, Phase 5) — nie der Inhalt, nie
    ein Bild; das setzt anhang.verlauf_einsetzen erst beim Senden ein."""
    _pruefen(gid)
    if rolle not in ("user", "assistant"):
        raise ValueError(f"unbekannte Rolle: {rolle!r}")
    e = {"art": "nachricht", "rolle": rolle, "text": str(text)}
    if denken:
        denken = str(denken)
        if len(denken) > DENKEN_GRENZE:
            # Das Ende behalten: dort steht, wozu das Denken geführt hat.
            denken = "…" + denken[-(DENKEN_GRENZE - 1):]
        e["denken"] = denken
    if werkzeuge:
        e["werkzeuge"] = list(werkzeuge)
    if anbieter:
        e["anbieter"] = anbieter
    if modell:
        e["modell"] = modell
    if abgebrochen:
        e["abgebrochen"] = True
    if versteckt:
        e["versteckt"] = True
    if anhaenge:
        e["anhaenge"] = [dict(a) for a in anhaenge]
    if dokumente:
        e["dokumente"] = [dict(d) for d in dokumente]
    return _anhaengen_roh(gid, e, knoten)


def verwerfen_ab(gid, nachricht_id, knoten=None) -> dict:
    """Diese Nachricht und alle späteren zählen nicht mehr (Wiederholen,
    Bearbeiten). Die Zeilen bleiben stehen — nur ein Ereignis kommt dazu."""
    if not any(n["id"] == nachricht_id for n in nachrichten(gid, versteckte=True)):
        raise Unbekannt(nachricht_id)
    return _anhaengen_roh(gid, {"art": "verwerfen", "ab": nachricht_id}, knoten)


# ── Lesen ───────────────────────────────────────────────────────────────

_cache = {}     # gid -> (stempel, nachrichten)


def _rechner_dateien(gid):
    try:
        namen = os.listdir(_ordner(gid))
    except OSError:
        return []
    return sorted(os.path.join(_ordner(gid), n) for n in namen if n.endswith(".jsonl")
                  and not n.startswith("."))


def _ereignisse(pfade):
    raus = []
    for pfad in pfade:
        try:
            with open(pfad, encoding="utf-8") as f:
                for nr, zeile in enumerate(f):
                    try:
                        e = json.loads(zeile)
                    except ValueError:
                        continue        # halbe Zeile nach Absturz: überspringen
                    if isinstance(e, dict) and e.get("ts") and e.get("id"):
                        raus.append((e["ts"], str(e.get("knoten") or ""), nr, e))
        except OSError:
            continue
    raus.sort(key=lambda t: t[:3])
    return [t[3] for t in raus]


def _anwenden(ereignisse):
    liste = []
    for e in ereignisse:
        if e.get("art") == "nachricht":
            liste.append(e)
        elif e.get("art") == "verwerfen":
            for i, n in enumerate(liste):
                if n["id"] == e.get("ab"):
                    del liste[i:]
                    break
    return liste


def nachrichten(gid, versteckte=False) -> list:
    """Die geltenden Nachrichten, älteste zuerst. versteckte=False lässt die
    Erinnerungs-Aufträge weg (die sieht nur die KI)."""
    _pruefen(gid)
    pfade = _rechner_dateien(gid)
    stempel = []
    for p in pfade:
        try:
            st = os.stat(p)
            stempel.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    stempel = tuple(stempel)
    with _lock:
        treffer = _cache.get(gid)
    if treffer and treffer[0] == stempel:
        liste = treffer[1]
    else:
        liste = _anwenden(_ereignisse(pfade))
        with _lock:
            _cache[gid] = (stempel, liste)
    if versteckte:
        return [dict(n) for n in liste]
    return [dict(n) for n in liste if not n.get("versteckt")]


def laden(gid) -> dict:
    """Kopf + sichtbare Nachrichten (mit Denken). Wirft Unbekannt."""
    return {"id": gid, "kopf": kopf(gid), "nachrichten": nachrichten(gid)}


def text_fuer_ki(n) -> str:
    """Der Text einer Nachricht, wie ihn die KI sieht (und die alte Anzeige)."""
    text = n.get("text") or ""
    if n.get("abgebrochen"):
        text = text.rstrip() + "\n\n" + VERMERK_ABGEBROCHEN
    if n.get("versteckt") and n.get("rolle") == "user":
        text = AUFTRAG_VORSATZ + text
    return text


def verlauf_fuer_ki(gid, fenster=FENSTER) -> list:
    """[{role, content}] der letzten `fenster` Nachrichten — dieselbe Form
    wie früher state.get_chat_history(). Verweise auf Anhänge und Dokumente
    gehen als 'anhaenge'/'dokumente' mit (aufgelöst von anhang.verlauf_einsetzen)."""
    if not gid or not gibt_es(gid):
        return []
    raus = []
    for n in nachrichten(gid, versteckte=True)[-fenster:]:
        m = {"role": n["rolle"], "content": text_fuer_ki(n)}
        for feld in ("anhaenge", "dokumente"):
            if n.get(feld):
                m[feld] = [dict(x) for x in n[feld]]
        raus.append(m)
    return raus


def letzte_nutzer_nachricht(gid):
    """Die letzte sichtbare Nachricht von Sasha, oder None."""
    for n in reversed(nachrichten(gid)):
        if n["rolle"] == "user":
            return n
    return None


# ── Pro Rechner: welches Gespräch ist offen, was ist gelesen ───────────

def _knoten_pfad():
    return os.path.join(_DIR, "_knoten", dateien.sicherer_name(knoten()) + ".json")


def _knoten_lesen() -> dict:
    try:
        with open(_knoten_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _knoten_schreiben(d):
    # Kein notify_change: die Datei gilt nur für diesen Rechner.
    dateien.json_schreiben(_knoten_pfad(), d)


def aktiv():
    """Das Gespräch, das auf DIESEM Rechner offen ist, oder None (= das
    nächste Senden legt ein neues an)."""
    gid = _knoten_lesen().get("aktiv")
    return gid if gid and gibt_es(gid) else None


def aktiv_setzen(gid):
    """Gespräch öffnen (None: ein neues beginnt beim nächsten Senden).
    Eigene Datei pro Rechner, damit sich PC und Laptop nicht gegenseitig
    umschalten."""
    if gid is not None:
        _pruefen(gid)
    with _lock:
        d = _knoten_lesen()
        d["aktiv"] = gid
        _knoten_schreiben(d)


def gelesen_setzen(gid):
    """Alles bis jetzt in diesem Gespräch gilt hier als gelesen."""
    _pruefen(gid)
    with _lock:
        d = _knoten_lesen()
        d.setdefault("gelesen", {})[gid] = jetzt_ts()
        _knoten_schreiben(d)


# ── Liste ───────────────────────────────────────────────────────────────

def liste(archivierte=False) -> list:
    """Alle Gespräche, neueste Aktivität zuerst; „Erinnerungen" immer oben.

    archivierte=False: nur die nicht archivierten; True: nur die archivierten.
    Gespräche ohne eine einzige Nachricht fehlen (außer Erinnerungen)."""
    try:
        namen = os.listdir(_DIR)
    except OSError:
        return []
    gelesen = _knoten_lesen().get("gelesen") or {}
    raus = []
    for gid in namen:
        if not gibt_es(gid):
            continue
        k = _kopf_lesen(gid)
        if bool(k.get("archiviert")) != bool(archivierte):
            continue
        ns = nachrichten(gid)
        if not ns and gid != ERINNERUNGEN:
            continue
        letzte = ns[-1]["ts"] if ns else (k.get("erstellt") or "")
        letzte_ki = next((n["ts"] for n in reversed(ns) if n["rolle"] == "assistant"), "")
        raus.append({
            "id": gid,
            "titel": k.get("titel") or "neues gespräch",
            "erstellt": k.get("erstellt"),
            "letzte": letzte,
            "anzahl": len(ns),
            "archiviert": bool(k.get("archiviert")),
            "ungelesen": bool(letzte_ki and letzte_ki > (gelesen.get(gid) or "")),
        })
    raus.sort(key=lambda g: g["letzte"] or "", reverse=True)
    raus.sort(key=lambda g: g["id"] != ERINNERUNGEN)       # stabil: Erinnerungen oben
    return raus
