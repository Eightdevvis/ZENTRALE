"""Spielstände: mehrere Lernstände nebeneinander, einer ist aktiv.

Bis hierher hatte der Tutor GENAU EINEN Lernstand — `tutor/data/<lang>/`. Wer
noch einmal von vorn anfangen wollte (oder jemand anderem das Spiel zeigen),
musste die Dateien löschen; der alte Fortschritt war weg.

Ein Spielstand ist GENAU EINE Sprache mit ihrem Lernstand (seit 2026-09-17):

    tutor/data/staende/<id>/stand.json     Name, Sprache, Level, angelegt, zuletzt
    tutor/data/staende/<id>/<lang>/…       vocab, fsrs, game, persona_mem, …

Bis dahin spannte ein Stand alle Sprachen, und die Sprache kam aus einer
zweiten Quelle (tutor_config.json). Zwei Quellen fuer »welche Sprache gerade«
hiessen: Prompt in der einen, Daten in der anderen, Hintergrund-Threads
schreiben nach einem Wechsel in den falschen Stand. Sasha: »sobald
Spielstaende ineinander bluten koennen, ist unser ganzes Game im Arsch« —
also physisch unmoeglich machen:

  - Die aktive Sprache leitet sich NUR aus dem aktiven Stand ab
    (aktive_sprache()). Sprache wechseln = anderen Stand laden.
  - pfad(root, lang) weigert sich (StandSprache), wenn lang nicht die Sprache
    des aktiven Stands ist: kein fremdsprachiger Write in einen Stand.
  - Wechsel (waehlen/anlegen/loeschen) und jede Lese-Aender-Schreib-Folge in
    tools/memory/srs laufen unter DERSELBEN Sperre (stand_lock): kein Wechsel
    zwischen Lesen und Schreiben.
  - Lange Operationen (memory.remember: LLM-Aufruf zwischen Laden und
    Speichern) fassen vorher ein token() und pruefen es vor dem Schreiben
    (pruefen(): StandGewechselt → Write verworfen, geloggt).

Welcher Stand aktiv ist, steht in `tutor/data/aktiver_stand` — eine Zeile,
bewusst NICHT in tutor_config.json: die haelt Provider/Modell/Muttersprache,
also Einstellungen. Welchen Spielstand man spielt, ist keine Einstellung.
"""

import datetime
import json
import os
import re
import shutil
import threading
import time

# EINE Sperre fuer alles, was Stand-Pfade liest und schreibt (tools, memory,
# srs nehmen dieselbe). RLock, weil tools-Funktionen einander aufrufen.
stand_lock = threading.RLock()

# Level beim Anlegen: 0 = von vorn, 1 = Grundlagen (wichtigste Kernwoerter
# gelten als bekannt), 2 = kann mich verstaendigen (alle Kernwoerter bekannt).
LEVELS = (0, 1, 2)
LEVEL_NAMEN = {0: "von vorn", 1: "Grundlagen", 2: "kann mich verständigen"}

# Ohne einen einzigen Stand (frische Installation) legt aktiv() einen an —
# in dieser Sprache. Nur dafuer; ansonsten kommt die Sprache aus dem Stand.
STANDARD_LANG = os.environ.get("TUTOR_STANDARD_LANG", "es")


class StandSprache(Exception):
    """Zugriff mit einer Sprache, die nicht die des aktiven Stands ist."""


class StandGewechselt(Exception):
    """Zwischen Lesen und Schreiben wurde der Stand gewechselt — Write verworfen."""

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
        lang = meta.get("lang") or ""
        stand = _sprach_stand(os.path.join(pfad, lang)) if lang else {"woerter": 0, "muenzen": 0}
        raus.append({
            "id": sid,
            "name": meta.get("name") or sid,
            "lang": lang,
            "level": int(meta.get("level") or 0),
            "erstellt": meta.get("erstellt") or "",
            "zuletzt": meta.get("zuletzt") or "",
            "woerter": stand["woerter"],
            "muenzen": stand["muenzen"],
            # Kompatibilitaet fuer Fronten, die noch je Sprache lesen:
            "sprachen": {lang: stand} if lang else {},
        })
    # Nach »zuletzt gespielt«, absteigend. Die id als zweites Kriterium, damit
    # die Reihenfolge bei gleichem Stempel nicht von listdir abhaengt.
    raus.sort(key=lambda s: (s["zuletzt"] or s["erstellt"], s["id"]), reverse=True)
    return raus


def _sprach_stand(d):
    """Was in diesem Sprachordner schon gelernt wurde (Woerter, Muenzen)."""
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
    return eintrag


def _sprachordner_mit_daten(stand_pfad):
    """Sprach-Unterordner, in denen wirklich etwas liegt (vocab.json)."""
    raus = []
    try:
        kinder = sorted(os.listdir(stand_pfad))
    except OSError:
        return raus
    for k in kinder:
        d = os.path.join(stand_pfad, k)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "vocab.json")):
            raus.append(k)
    return raus


def anlegen(daten_root, name=None, lang=None, level=0):
    """Neuen Spielstand anlegen und zurueckgeben (macht ihn NICHT aktiv).

    lang ist Pflicht: ein Stand ohne Sprache waere wieder die alte Zweideutigkeit.
    """
    lang = (lang or "").strip().lower()
    if not re.fullmatch(r"[a-z]{2,8}", lang):
        raise ValueError("Spielstand braucht eine Sprache (z.B. 'es')")
    level = int(level or 0)
    if level not in LEVELS:
        raise ValueError("Level muss 0, 1 oder 2 sein")
    with stand_lock:
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
                      {"name": name, "lang": lang, "level": level,
                       "erstellt": jetzt, "zuletzt": jetzt})
        os.makedirs(os.path.join(wurzel, sid, lang), exist_ok=True)
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
    # Ein Stand je Sprache (seit 2026-09-17 kennt ein Stand genau eine).
    erster = None
    for lang in sprachen:
        sid = anlegen(daten_root, STANDARD_NAME, lang=lang)
        ziel = os.path.join(wurzel, sid, lang)
        shutil.rmtree(ziel, ignore_errors=True)
        os.replace(os.path.join(daten_root, lang), ziel)
        erster = erster or sid
    return erster


def migrieren_sprachen(daten_root):
    """Staende ohne Sprache (Modell vor 2026-09-17: ein Stand, viele Sprach-
    Ordner) in Ein-Sprach-Staende aufteilen. Einmalig, idempotent.

    Der erste Sprachordner mit Daten bleibt unter der alten Id (bekommt lang),
    jeder weitere wird ein eigener Stand »<name> (<lang>)«. Leere Sprachordner
    (nur von pfad()s makedirs angelegt) verschwinden. Ein Stand ganz ohne Daten
    bekommt STANDARD_LANG.
    """
    wurzel = _wurzel(daten_root)
    try:
        eintraege = sorted(os.listdir(wurzel))
    except OSError:
        return []
    umgezogen = []
    with stand_lock:
        for sid in eintraege:
            pfad_ = os.path.join(wurzel, sid)
            if not os.path.isdir(pfad_):
                continue
            meta = _lies_meta(pfad_)
            if meta.get("lang"):
                continue
            mit_daten = _sprachordner_mit_daten(pfad_)
            # leere Sprachordner weg
            for k in os.listdir(pfad_):
                d = os.path.join(pfad_, k)
                if os.path.isdir(d) and k not in mit_daten:
                    shutil.rmtree(d, ignore_errors=True)
            haupt = mit_daten[0] if mit_daten else STANDARD_LANG
            for lang in mit_daten[1:]:
                neu = anlegen(daten_root, "%s (%s)" % (meta.get("name") or sid, lang), lang=lang)
                ziel = os.path.join(wurzel, neu, lang)
                shutil.rmtree(ziel, ignore_errors=True)
                os.replace(os.path.join(pfad_, lang), ziel)
                umgezogen.append(neu)
            meta["lang"] = haupt
            meta.setdefault("level", 0)
            meta.setdefault("name", sid)
            os.makedirs(os.path.join(pfad_, haupt), exist_ok=True)
            _schreib_meta(pfad_, meta)
            umgezogen.append(sid)
    return umgezogen


def aktiv(daten_root):
    """Id des aktiven Spielstands. Legt beim allerersten Mal einen an.

    Nie None: jeder Aufruf, der einen Datenpfad braucht, muss einen bekommen —
    sonst muesste jede Schreibstelle im Tutor den Sonderfall »noch kein Stand«
    kennen.
    """
    with stand_lock:
        zeiger = os.path.join(daten_root, ZEIGER)
        try:
            with open(zeiger, encoding="utf-8") as f:
                sid = f.read().strip()
            if sid and os.path.isdir(os.path.join(_wurzel(daten_root), sid)):
                if not _lies_meta(os.path.join(_wurzel(daten_root), sid)).get("lang"):
                    migrieren_sprachen(daten_root)
                return sid
        except OSError:
            pass
        migrieren(daten_root)
        migrieren_sprachen(daten_root)
        vorhandene = liste(daten_root)
        sid = vorhandene[0]["id"] if vorhandene else anlegen(daten_root, STANDARD_NAME, lang=STANDARD_LANG)
        waehlen(daten_root, sid)
        return sid


def aktiv_info(daten_root):
    """Meta des aktiven Stands (id, name, lang, level, ...). Nie None."""
    with stand_lock:
        sid = aktiv(daten_root)
        meta = _lies_meta(os.path.join(_wurzel(daten_root), sid))
        meta["id"] = sid
        meta.setdefault("level", 0)
        if not meta.get("lang"):
            migrieren_sprachen(daten_root)
            meta = _lies_meta(os.path.join(_wurzel(daten_root), sid)); meta["id"] = sid
        return meta


def aktive_sprache(daten_root):
    """DIE Quelle fuer »welche Sprache gerade«: die des aktiven Stands."""
    return aktiv_info(daten_root).get("lang") or STANDARD_LANG


def token(daten_root):
    """(id, lang) des aktiven Stands — vor einer langen Operation fassen."""
    info = aktiv_info(daten_root)
    return (info["id"], info.get("lang"))


def pruefen(daten_root, tok):
    """Ist der Stand noch derselbe wie beim token()? Sonst StandGewechselt."""
    jetzt = token(daten_root)
    if tuple(tok) != tuple(jetzt):
        raise StandGewechselt("Stand %s/%s → %s/%s" % (tok[0], tok[1], jetzt[0], jetzt[1]))
    return True


def waehlen(daten_root, sid):
    """Diesen Stand aktiv machen. Unbekannte Id -> False, nichts geaendert."""
    with stand_lock:
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
    with stand_lock:
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


def pfad(daten_root, lang=None):
    """Datenordner der Sprache IM AKTIVEN STAND (wird angelegt).

    Das ist der eine Griff, ueber den memory/srs/tools ihre Dateien finden.
    lang darf fehlen (dann die Stand-Sprache) — ist es angegeben und NICHT die
    Sprache des aktiven Stands, gibt es keinen Pfad, sondern StandSprache: ein
    fremdsprachiger Write in einen Stand ist damit unmoeglich, nicht nur
    unerwuenscht.
    """
    with stand_lock:
        info = aktiv_info(daten_root)
        eigene = info.get("lang") or STANDARD_LANG
        if lang and lang != eigene:
            raise StandSprache("Stand '%s' ist %s, nicht %s" % (info["id"], eigene, lang))
        d = os.path.join(_wurzel(daten_root), info["id"], eigene)
        os.makedirs(d, exist_ok=True)
        return d
