# core/adapter_bruecke.py
#
# Wer fährt gerade die Brücke zu einem fremden Dienst? (memory/hub/adapter.md
# „Die Brücke ist ein Mietvertrag", Sasha 24.10.2026: ein festes Gerät fällt
# aus, wenn es aus ist — der Wechsel muss nahtlos sein.)
#
# Ein Mietvertrag je Anschluss, data/adapter/bruecke/<id>.json:
#
#   {"inhaber": "<gerät>", "ablauf": ISO-UTC, "seit": ISO-UTC,
#    "zustand": {…Stand des letzten Google-Laufs, kalender_sync_zustand…}}
#
# Die Datei gleicht über die Mitte ab wie jede andere — mit EINER eigenen
# Regel (core/abgleich_zusammenfuehren.py, Art „mitte"): haben beide Seiten
# sie geändert, gilt die Mitte, ohne Feld-für-Feld. Weil die Mitte nur
# annimmt, was auf ihrem letzten Stand aufbaut (senden → 409 → neu holen),
# heißt das: von zwei Geräten, die gleichzeitig zugreifen, gewinnt das, das
# zuerst ankam; das andere sieht nach seinem Abgleich den fremden Inhaber
# und fährt NICHT. Gefahren wird nur nach einem gelungenen Abgleich, der den
# eigenen Namen als Inhaber zurückbrachte.
#
# Der Stand von vdirsyncer (was die Brücke zuletzt auf beiden Seiten sah)
# reist mit, data/adapter/bruecke/<id>.status.json — sonst sähe ein neues
# Brücken-Gerät jeden Termin als neu oder als Konflikt. Gemessen (vdirsyncer
# 0.21.0, 24.10.2026): ein auf ein anderes Gerät kopierter Stand mit neuen
# Datei-Zeiten und Inodes löst keine einzige Übertragung aus — vdirsyncer
# vergleicht dann den Inhalt. Nur die Einträge reisen; die Entdeckung der
# Sammlungen (<paar>.collections) hängt an den Pfaden des Geräts und wird
# auf der neuen Brücke neu gemacht.
#
# Fundament (Schicht 1): kein Abgleich, kein Kalender — reine Datei-Arbeit.

import base64
import datetime
import hashlib
import json
import os

import adapter
import dateien

MIETE_MIN = 15     # länger als ein vdirsyncer-Lauf höchstens dauert (TimeoutStartSec=600)


def _utc(jetzt=None):
    return jetzt or datetime.datetime.now(datetime.timezone.utc)


def _iso(t) -> str:
    return t.astimezone(datetime.timezone.utc).replace(microsecond=0).isoformat()


def _zeit(iso):
    try:
        t = datetime.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)


def pfad(aid, wurzel=None) -> str:
    return os.path.join(adapter.ordner(wurzel), "bruecke", aid + ".json")


def status_pfad(aid, wurzel=None) -> str:
    return os.path.join(adapter.ordner(wurzel), "bruecke", aid + ".status.json")


# ── Der Mietvertrag ────────────────────────────────────────────────────

def lesen(aid, wurzel=None):
    try:
        with open(pfad(aid, wurzel), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def abgelaufen(miete, jetzt=None) -> bool:
    ablauf = _zeit((miete or {}).get("ablauf"))
    return ablauf is None or ablauf <= _utc(jetzt)


def frei_fuer(miete, ich, jetzt=None) -> bool:
    """Darf `ich` die Brücke nehmen (oder verlängern)?"""
    return not miete or miete.get("inhaber") == ich or abgelaufen(miete, jetzt)


def haelt(miete, ich, jetzt=None) -> bool:
    return bool(miete) and miete.get("inhaber") == ich and not abgelaufen(miete, jetzt)


def beanspruchen(aid, ich, jetzt=None, wurzel=None, zustand=None) -> dict:
    """Den Vertrag hier auf `ich` schreiben (nehmen oder verlängern). Gültig
    wird er erst, wenn der nächste Abgleich ihn so zurückbringt."""
    jetzt = _utc(jetzt)
    alt = lesen(aid, wurzel) or {}
    neu = {"inhaber": ich,
           "ablauf": _iso(jetzt + datetime.timedelta(minutes=MIETE_MIN)),
           "seit": alt.get("seit") if alt.get("inhaber") == ich and alt.get("seit") else _iso(jetzt)}
    z = zustand if zustand is not None else (alt.get("zustand") if alt.get("inhaber") == ich else None)
    if z:
        neu["zustand"] = z
    dateien.json_schreiben(pfad(aid, wurzel), neu)
    return neu


def zustand_ablegen(aid, ich, zustand, wurzel=None) -> None:
    """Den Stand des letzten Laufs in den Vertrag (alle Geräte sehen ihn)."""
    m = lesen(aid, wurzel)
    if m and m.get("inhaber") == ich:
        m["zustand"] = zustand
        dateien.json_schreiben(pfad(aid, wurzel), m)


# ── Der Stand von vdirsyncer reist mit ─────────────────────────────────

def _gehoert(rel, paare) -> bool:
    """Die Stände der Einträge (<paar>.items, <paar>/<sammlung>.items). Nicht
    <paar>.collections: das ist nur ein Zwischenspeicher der Entdeckung, an
    die Konfiguration DIESES Geräts gebunden (Pfade) — den baut jede Brücke
    selbst (adapter_vdirsyncer.entdecken)."""
    rel = rel.replace(os.sep, "/")
    return any(rel == p + ".items" or (rel.startswith(p + "/") and rel.endswith(".items"))
               for p in paare)


def _sha(d) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode("utf-8")).hexdigest()


def _merk_pfad(aid) -> str:
    return os.path.join(adapter.lauf_ordner(aid), "status_stand.json")


def _merk(aid):
    try:
        with open(_merk_pfad(aid), encoding="utf-8") as f:
            return json.load(f).get("sha")
    except (OSError, ValueError):
        return None


def _merken(aid, sha):
    dateien.json_schreiben(_merk_pfad(aid), {"sha": sha})


def einpacken(aid, status_dir, paare, stand_datei, ich, wurzel=None) -> bool:
    """Den Stand der Paare (die data/kalender/ schreiben) und die Liste der
    Löschsperre (scripts/kalender_sync.py STAND) in den Abgleich legen.
    → True, wenn sich etwas geändert hat."""
    dateien_ = {}
    if status_dir and os.path.isdir(status_dir):
        for w, _d, fs in os.walk(status_dir):
            for f in fs:
                rel = os.path.relpath(os.path.join(w, f), status_dir).replace(os.sep, "/")
                if _gehoert(rel, paare) and not rel.endswith(("-journal", "-wal", "-shm")):
                    with open(os.path.join(w, f), "rb") as fh:
                        dateien_[rel] = base64.b64encode(fh.read()).decode("ascii")
    stand = None
    try:
        with open(stand_datei, encoding="utf-8") as f:
            stand = json.load(f)
    except (OSError, ValueError, TypeError):
        pass
    inhalt = {"paare": sorted(paare), "dateien": dateien_, "stand": stand}
    sha = _sha(inhalt)
    try:
        with open(status_pfad(aid, wurzel), encoding="utf-8") as f:
            if _sha({k: v for k, v in json.load(f).items() if k in inhalt}) == sha:
                _merken(aid, sha)
                return False
    except (OSError, ValueError):
        pass
    dateien.json_schreiben(status_pfad(aid, wurzel), dict(inhalt, von=ich))
    _merken(aid, sha)
    return True


def auspacken(aid, status_dir, stand_datei, wurzel=None) -> bool:
    """Den mitgereisten Stand hier hinlegen — nur, wenn er nicht von hier
    stammt (der eigene ist dann ohnehin der neueste). → True, wenn gelegt."""
    try:
        with open(status_pfad(aid, wurzel), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return False
    inhalt = {k: d.get(k) for k in ("paare", "dateien", "stand")}
    sha = _sha(inhalt)
    if sha == _merk(aid):
        return False
    paare = inhalt["paare"] or []
    os.makedirs(status_dir, exist_ok=True)
    for w, _d, fs in os.walk(status_dir):
        for f in fs:
            rel = os.path.relpath(os.path.join(w, f), status_dir)
            if _gehoert(rel, paare):
                os.remove(os.path.join(w, f))
    for rel, b64 in (inhalt["dateien"] or {}).items():
        if ".." in rel.split("/") or rel.startswith("/"):
            continue
        dateien.atomar_schreiben(os.path.join(status_dir, rel), base64.b64decode(b64), geheim=True)
    if inhalt["stand"] is not None and stand_datei:
        dateien.json_schreiben(stand_datei, inhalt["stand"])
    _merken(aid, sha)
    return True
