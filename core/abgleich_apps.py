# core/abgleich_apps.py
#
# Was dieses Gerät abgleicht — je App (memory/hub/cloud_app.md, seit
# 2026-10-23; vorher zwölf feste Bereiche, core/abgleich_bereiche.py).
#
# Zentrale speichert nichts Eigenes; Daten haben nur Apps. Jede App sagt in
# `[daten]` (app.toml, bzw. core/eingebaute_apps.py für die eingebauten),
# welche Dateien sie hat. Die Positivliste core/abgleich_auswahl.py bleibt der
# Schutz: ein Muster wird nur abgeglichen, wenn es GENAU so auch dort steht
# (deny by default), und jedes Muster gehört nur einer App (die erste gewinnt:
# eingebaute, dann Ersatz, dann Manifeste nach Namen).
#
# Die Wahl gilt je App und je Gerät: Einstellung `abgleich_apps` in
# data/ai_config.json (wird nie abgeglichen), {app: true|false}.
#   nicht gesetzt  = alles (wie bisher; Sashas git-Weg bleibt, wie er war)
#   {}             = noch nichts entschieden — jede App mit Daten fragt einmal
#   fehlt eine App = noch nicht gefragt → wird weder geholt noch gesendet
# Die alte Einstellung `abgleich_bereiche` wird beim Lesen übernommen
# (aus_bereichen); geschrieben wird nur die neue.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md). Die Cloud kennt dieses
# Modul nicht: wer wissen will, was in der Mitte liegt, gibt es herein
# (abgleich.cloud_pfade).

import glob
import json
import os

import abgleich_auswahl as auswahl
import ai_config
import apps
import eingebaute_apps

EINSTELLUNG = "abgleich_apps"
ALT = "abgleich_bereiche"

# Die alten Bereichs-ids (bis 2026-10-23) → App. Zwei Bereiche wurden eine App
# (memory + conversations → assistent).
ALT_BEREICHE = {"lists": "fokus", "notes": "notizen", "calendar": "kalender",
                "graphs": "graph", "memory": "assistent", "conversations": "assistent",
                "documents": "ablage", "desk": "desk", "apps": "werkstatt", "mail": "mail",
                "music": "klavier", "tutor": "tutor"}


# ── Welche Apps Daten haben können ─────────────────────────────────────

def _manifeste() -> dict:
    raus = {}
    for m in apps.installiert():
        name = str(m.get("_slug") or m.get("name") or "")
        if name:
            raus.setdefault(name, m)
    return raus


def tabelle() -> dict:
    """name → {titel, muster}: alle Apps, deren Daten abgeglichen werden
    DÜRFEN (`abgleichen = true`), nur mit Mustern von der Positivliste. Apps
    ohne ein einziges erlaubtes Muster fehlen."""
    manifeste = _manifeste()
    roh = []                     # (name, titel, daten)
    for quelle in (eingebaute_apps.EINGEBAUT, eingebaute_apps.ERSATZ):
        for n, e in quelle.items():
            if "daten" not in e:
                continue
            m = manifeste.pop(n, None)
            d = apps.daten(m) if m else None     # zieht sie aus, gilt ihr Manifest
            titel = str((m or {}).get("titel") or e["titel"])
            roh.append((n, titel, d if d is not None else e["daten"]))
    for n, m in sorted(manifeste.items()):
        d = apps.daten(m)
        if d is not None:
            roh.append((n, str(m.get("titel") or n), d))
    vergeben, raus = set(), {}
    for n, titel, d in roh:
        if not d.get("abgleichen"):
            continue
        muster = [x for x in d["muster"] if x in auswahl.ABGLEICH and x not in vergeben]
        vergeben.update(muster)
        if muster:
            raus[n] = {"titel": titel, "muster": muster}
    return raus


# ── Die Wahl je Gerät ──────────────────────────────────────────────────

def _lesen(w) -> dict:
    if isinstance(w, str):
        try:
            w = json.loads(w)
        except ValueError:
            w = [t.strip() for t in w.split(",") if t.strip()]
    if isinstance(w, dict):
        return {str(k): v is True for k, v in w.items()}
    if isinstance(w, (list, tuple)):
        return {str(k): True for k in w}
    return {}


def aus_bereichen(ids) -> dict:
    """Die alte Wahl (`abgleich_bereiche`) als Wahl je App. Ganz gewählt →
    ja, gar nicht → nein; nur zum Teil (memory ohne conversations) → keine
    Entscheidung: die App fragt einmal, statt still mehr oder weniger als
    vorher abzugleichen."""
    if isinstance(ids, str):
        ids = [t.strip() for t in ids.split(",") if t.strip()]
    ids = set(ids or [])
    raus = {}
    for app in dict.fromkeys(ALT_BEREICHE.values()):
        teile = [b for b, a in ALT_BEREICHE.items() if a == app]
        an = [b for b in teile if b in ids]
        if len(an) == len(teile):
            raus[app] = True
        elif not an:
            raus[app] = False
    return raus


def entscheidungen():
    """→ {app: bool} dieses Geräts, oder None = nie gewählt (alles)."""
    w = ai_config.setting(EINSTELLUNG)
    if w is not None:
        return _lesen(w)
    alt = ai_config.setting(ALT)
    if alt is None:
        return None
    return aus_bereichen(alt)


def setzen(neu: dict):
    """Entscheidungen ablegen (zu den bisherigen dazu). Ein {} macht aus „nie
    gewählt" ein „noch nichts entschieden"."""
    alles = dict(entscheidungen() or {})
    alles.update({str(k): v is True for k, v in neu.items()})
    # {} ist eine echte Wahl, kein „löschen" — set_override löscht nur None und "".
    ai_config.set_override(EINSTELLUNG, alles, persist=True)


def muster() -> list:
    """Die Muster der Positivliste, die dieses Gerät abgleicht."""
    e = entscheidungen()
    if e is None:
        return list(auswahl.ABGLEICH)
    return [x for n, a in tabelle().items() if e.get(n) for x in a["muster"]]


def app_von(rel: str):
    """Zu welcher App gehört ein Pfad? → name oder None."""
    for n, a in tabelle().items():
        if auswahl.passt(rel, a["muster"]):
            return n
    return None


# ── Wer hat Daten ──────────────────────────────────────────────────────

def _lokal_da(wurzel, m) -> bool:
    """Gibt es auf diesem Gerät eine Datei zu diesem Muster? Ohne den ganzen
    Ordner zu durchlaufen (läuft beim Start von `zentrale`)."""
    if m.endswith("/**"):
        vorsatz = m[:-3]
        ort = os.path.dirname(auswahl.pfad(wurzel, vorsatz + "/_"))
        for w, _dirs, files in os.walk(ort):
            for f in files:
                rel = vorsatz + "/" + os.path.relpath(os.path.join(w, f), ort).replace(os.sep, "/")
                if auswahl.passt(rel, [m]):
                    return True
        return False
    return any(os.path.isfile(p) for p in glob.glob(glob.escape(wurzel) + "/" + m))


def hat_daten(wurzel, muster_liste, cloud=None) -> bool:
    if cloud and any(auswahl.passt(rel, muster_liste) for rel in cloud):
        return True
    return any(_lokal_da(wurzel, m) for m in muster_liste)


def mit_daten(wurzel, cloud=None) -> list:
    """Apps, die hier (oder laut `cloud` = Pfade aus dem Inhaltsverzeichnis
    der Mitte) schon Daten haben — in der Reihenfolge der Tabelle."""
    return [n for n, a in tabelle().items() if hat_daten(wurzel, a["muster"], cloud)]


def offen(wurzel, cloud_holen=None) -> list:
    """Apps mit Daten, über die dieses Gerät noch nicht entschieden hat. Leer,
    solange nie gewählt wurde (dann gilt ohnehin alles). `cloud_holen()` →
    Pfade der Mitte; gefragt wird nur, wenn es überhaupt Unentschiedene gibt."""
    e = entscheidungen()
    if e is None:
        return []
    kandidaten = {n: a for n, a in tabelle().items() if n not in e}
    if not kandidaten:
        return []
    cloud = cloud_holen() if cloud_holen else None
    return [n for n, a in kandidaten.items() if hat_daten(wurzel, a["muster"], cloud)]
