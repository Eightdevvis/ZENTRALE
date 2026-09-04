"""Spielstände: mehrere Lernstände nebeneinander, einer ist aktiv.

Bis hierher hatte der Tutor GENAU EINEN Lernstand — `tutor/data/<lang>/`. Wer
noch einmal von vorn anfangen wollte (oder jemand anderem das Spiel zeigen),
musste die Dateien löschen; der alte Fortschritt war weg.

Ein Spielstand ist alles, was gelernt wurde, ueber ALLE Sprachen hinweg:

    tutor/data/staende/<id>/stand.json     Name, angelegt, zuletzt gespielt
    tutor/data/staende/<id>/<lang>/…       vocab, fsrs, game, persona_mem, …

Global und nicht pro Sprache, weil ein Spielstand »ein Durchgang« ist: wer
neu anfaengt, faengt bei allen Sprachen neu an. Die SPRACHE waehlt man
weiterhin getrennt (/lang, Alt+L im Zimmer) — sie ist eine Eigenschaft des
Spielens, nicht des Spielstands.

Welcher Stand aktiv ist, steht in `tutor/data/aktiver_stand` — eine Zeile,
bewusst NICHT in tutor_config.json: die haelt Sprache/Provider/Modell, also
Einstellungen. Welchen Spielstand man spielt, ist keine Einstellung.
"""

import datetime
import json
import os
import re
import time

def _jetzt():
    """Zeitstempel mit Millisekunden.

    Mikrosekunden, nicht Sekunden: wer zwei Staende schnell hintereinander
    waehlt, bekaeme sonst denselben Stempel, und »zuletzt gespielt« waere
    Zufall statt Reihenfolge. Mit Millisekunden ist das im vollen Testlauf
    trotzdem noch kollidiert — zwei Datei-Schreibvorgaenge passen in eine
    Millisekunde. Im Betrieb waere daraus ein seltener, schwer erklaerbarer
    Sprung in der Liste geworden.
    """
    return datetime.datetime.now().isoformat(timespec="microseconds")


WURZEL_NAME = "staende"
META = "stand.json"
ZEIGER = "aktiver_stand"
STANDARD_NAME = "Erster Anlauf"


def _wurzel(daten_root):
    return os.path.join(daten_root, WURZEL_NAME)


def _slug(name):
    """Aus einem Namen eine haltbare Ordner-Id machen.

    Nur Kleinbuchstaben, Ziffern und Bindestriche — der Name selbst darf alles
    sein und steht in stand.json. So bleibt der Ordner auf jedem Dateisystem
    heil, auch wenn jemand seinen Stand »Lucía & ich 💃« nennt.
    """
    roh = re.sub(r"[^a-z0-9]+", "-", (name or "").lower().strip()).strip("-")
    return roh[:40] or "stand"


def _lies_meta(pfad):
    try:
        with open(os.path.join(pfad, META), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _schreib_meta(pfad, meta):
    os.makedirs(pfad, exist_ok=True)
    tmp = os.path.join(pfad, META + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.replace(tmp, os.path.join(pfad, META))


def liste(daten_root):
    """Alle Spielstaende, zuletzt gespielter zuerst.

    Pro Stand eine kurze Zusammenfassung je Sprache (Woerter, Muenzen), damit
    die Auswahl nicht nur Namen zeigt, sondern woran man sie wiedererkennt.
    """
    wurzel = _wurzel(daten_root)
    raus = []
    try:
        eintraege = sorted(os.listdir(wurzel))
    except OSError:
        return raus
    for sid in eintraege:
        pfad = os.path.join(wurzel, sid)
        if not os.path.isdir(pfad):
            continue
        meta = _lies_meta(pfad)
        raus.append({
            "id": sid,
            "name": meta.get("name") or sid,
            "erstellt": meta.get("erstellt") or "",
            "zuletzt": meta.get("zuletzt") or "",
            "sprachen": _sprachen(pfad),
        })
    # Nach »zuletzt gespielt«, absteigend. Die id als zweites Kriterium, damit
    # die Reihenfolge bei gleichem Stempel nicht von listdir abhaengt.
    raus.sort(key=lambda s: (s["zuletzt"] or s["erstellt"], s["id"]), reverse=True)
    return raus


def _sprachen(stand_pfad):
    """Was in diesem Stand schon gelernt wurde, je Sprache."""
    raus = {}
    try:
        kinder = sorted(os.listdir(stand_pfad))
    except OSError:
        return raus
    for lang in kinder:
        d = os.path.join(stand_pfad, lang)
        if not os.path.isdir(d):
            continue
        eintrag = {"woerter": 0, "muenzen": 0}
        try:
            with open(os.path.join(d, "vocab.json"), encoding="utf-8") as f:
                v = json.load(f)
            eintrag["woerter"] = len(v) if isinstance(v, list) else 0
        except (OSError, ValueError):
            pass
        try:
            with open(os.path.join(d, "game.json"), encoding="utf-8") as f:
                g = json.load(f)
            eintrag["muenzen"] = int(g.get("coins") or 0)
        except (OSError, ValueError, TypeError):
            pass
        raus[lang] = eintrag
    return raus


def anlegen(daten_root, name=None):
    """Neuen Spielstand anlegen und zurueckgeben (macht ihn NICHT aktiv)."""
    wurzel = _wurzel(daten_root)
    os.makedirs(wurzel, exist_ok=True)
    name = (name or "").strip() or time.strftime("Neu %d.%m.%Y")
    basis = _slug(name)
    sid, n = basis, 2
    while os.path.exists(os.path.join(wurzel, sid)):
        sid = "%s-%d" % (basis, n)
        n += 1
    jetzt = _jetzt()
    _schreib_meta(os.path.join(wurzel, sid),
                  {"name": name, "erstellt": jetzt, "zuletzt": jetzt})
    return sid


# Ordner unter tutor/data/, die KEINE Sprache sind und beim Umzug in einen
# Spielstand liegen bleiben muessen.
_KEINE_SPRACHE = {WURZEL_NAME, "vocab_images", "persona_music"}


def migrieren(daten_root):
    """Alten Einzel-Lernstand in einen Spielstand umziehen. Einmalig, je Knoten.

    Vor den Spielstaenden lagen die Sprachordner direkt unter tutor/data/.
    Statt sie wegzuwerfen (und jemanden seinen Fortschritt zu kosten) wandern
    sie beim ersten Start in einen Stand — der Knoten migriert sich selbst,
    ohne dass jemand ein Skript aufrufen muss.

    Idempotent: gibt es die Staende-Wurzel schon, passiert gar nichts.
    """
    wurzel = _wurzel(daten_root)
    if os.path.exists(wurzel):
        return None
    try:
        kinder = sorted(os.listdir(daten_root))
    except OSError:
        return None
    sprachen = [k for k in kinder
                if k not in _KEINE_SPRACHE and not k.startswith(".")
                and os.path.isdir(os.path.join(daten_root, k))
                and os.path.exists(os.path.join(daten_root, k, "vocab.json"))]
    if not sprachen:
        return None
    sid = anlegen(daten_root, STANDARD_NAME)
    ziel = os.path.join(wurzel, sid)
    for lang in sprachen:
        os.replace(os.path.join(daten_root, lang), os.path.join(ziel, lang))
    return sid


def aktiv(daten_root):
    """Id des aktiven Spielstands. Legt beim allerersten Mal einen an.

    Nie None: jeder Aufruf, der einen Datenpfad braucht, muss einen bekommen —
    sonst muesste jede Schreibstelle im Tutor den Sonderfall »noch kein Stand«
    kennen.
    """
    zeiger = os.path.join(daten_root, ZEIGER)
    try:
        with open(zeiger, encoding="utf-8") as f:
            sid = f.read().strip()
        if sid and os.path.isdir(os.path.join(_wurzel(daten_root), sid)):
            return sid
    except OSError:
        pass
    migrieren(daten_root)
    vorhandene = liste(daten_root)
    sid = vorhandene[0]["id"] if vorhandene else anlegen(daten_root, STANDARD_NAME)
    waehlen(daten_root, sid)
    return sid


def waehlen(daten_root, sid):
    """Diesen Stand aktiv machen. Unbekannte Id -> False, nichts geaendert."""
    pfad = os.path.join(_wurzel(daten_root), sid)
    if not os.path.isdir(pfad):
        return False
    os.makedirs(daten_root, exist_ok=True)
    zeiger = os.path.join(daten_root, ZEIGER)
    tmp = zeiger + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(sid + "\n")
    os.replace(tmp, zeiger)
    meta = _lies_meta(pfad)
    meta["zuletzt"] = _jetzt()
    meta.setdefault("name", sid)
    meta.setdefault("erstellt", meta["zuletzt"])
    _schreib_meta(pfad, meta)
    return True


def loeschen(daten_root, sid):
    """Einen Spielstand samt allem Gelernten entfernen. True = weg.

    Auch der AKTIVE darf weg — man raeumt ja meistens den auf, in dem man
    gerade steht. Der Zeiger wird dann geloescht; der naechste aktiv()-Aufruf
    nimmt den zuletzt gespielten der uebrigen oder legt einen neuen an. So
    bleibt der Tutor auch dann bedienbar, wenn jemand ALLE Staende loescht.
    """
    import shutil
    pfad_ = os.path.join(_wurzel(daten_root), sid)
    if not os.path.isdir(pfad_):
        return False
    shutil.rmtree(pfad_)
    zeiger = os.path.join(daten_root, ZEIGER)
    try:
        with open(zeiger, encoding="utf-8") as f:
            war_aktiv = f.read().strip() == sid
    except OSError:
        war_aktiv = False
    if war_aktiv:
        try:
            os.remove(zeiger)
        except OSError:
            pass
    return True


def pfad(daten_root, lang):
    """Datenordner fuer diese Sprache IM AKTIVEN STAND (wird angelegt).

    Das ist der eine Griff, ueber den memory/srs/tools ihre Dateien finden —
    frueher zeigten die drei direkt auf tutor/data/<lang>/.
    """
    d = os.path.join(_wurzel(daten_root), aktiv(daten_root), lang)
    os.makedirs(d, exist_ok=True)
    return d
