# core/abgleich.py
#
# Ein Abgleich über die Mitte, von vorn bis hinten (memory/betrieb/abgleich.md):
# holen → entschlüsseln → mit der Basis zusammenführen → verschlüsselt in die
# Mitte senden → auf dem Rechner schreiben → neue Basis merken.
#
# Sasha, 2026-10-08: „der sync zum pc war immer iwie etwas cursed … besser
# wenn jetzt gegen eine cloud, einen server einfach geprüft wird." Statt
# rsync direkt zwischen den Rechnern gleicht jeder nur noch mit der Mitte ab.
#
# Hier liegt nur der Ablauf. Die Regeln: abgleich_zusammenfuehren. Die Mitte:
# abgleich_mitte. Der Schlüssel: abgleich_schluessel. Was mitdarf:
# abgleich_auswahl.
#
# Örtlicher Zustand unter `abgleich_dir` (Vorgabe ~/.local/share/zentrale/
# abgleich) — bewusst außerhalb von data/, sonst trüge der alte rsync-Weg
# die Basis des einen Rechners auf den anderen:
#   basis/            worauf sich dieser Rechner zuletzt mit der Mitte geeinigt hat
#   basis.json        … und auf welchen Stand der Mitte
#   mitte/            der git-Klon (nur verschlüsselt)
#   vorhaben/         was ein laufender Abgleich gerade tut (absturzsicher)
#   konflikte/<zeit>/ eigene Fassungen, die einem Widerspruch weichen mussten
#   beiseite/<zeit>/  Dateien, die in der Mitte gelöscht wurden
#   zustand.json      letzter Abgleich, Fehler, Hinweise — für TUI und Route

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import shutil
import time

import abgleich_auswahl as auswahl
import abgleich_mitte
import abgleich_schluessel as schluessel
import abgleich_zusammenfuehren as regeln
import ai_config
import dateien

VORGABE_DIR = "~/.local/share/zentrale/abgleich"
VORGABE_MITTE = "git@github.com:Eightdevvis/data.git"
INHALT = "inhalt.enc"
LIESMICH = "LIESMICH.md"
WEGE = ("rsync", "mitte")
MAX_HINWEISE = 50

LIESMICH_TEXT = """# ZENTRALE — die Mitte

Automatisch geschrieben vom Abgleich (scripts/abgleich.py im ZENTRALE-Repo).
Alles hier ist verschlüsselt; ohne den Schlüssel aus KeePass („ZENTRALE
Abgleich") ist es nicht lesbar. Nicht von Hand ändern.
"""


class Besetzt(Exception):
    """Ein anderer Abgleich läuft gerade."""


class Bericht:
    def __init__(self):
        self.art = ""            # "" | "erstbefuellung" | "erstabgleich"
        self.geholt = []         # auf dem Rechner geändert
        self.gesendet = []       # in der Mitte geändert
        self.beiseite = []       # auf dem Rechner beiseitegelegt
        self.hinweise = []
        self.trocken = False

    def als_dict(self):
        return dict(self.__dict__)


# ── Einstellungen und Orte ─────────────────────────────────────────────

def ordner() -> str:
    return os.path.expanduser(ai_config.setting("abgleich_dir") or VORGABE_DIR)


def weg() -> str:
    w = (ai_config.setting("abgleich_weg") or "rsync").strip().lower()
    return w if w in WEGE else "rsync"


def mitte_oeffnen():
    return abgleich_mitte.oeffnen(
        (ai_config.setting("abgleich_mitte_art") or "git").strip().lower(),
        ai_config.setting("abgleich_mitte") or VORGABE_MITTE,
        os.path.join(ordner(), "mitte"))


def _sha(b):
    return hashlib.sha256(b).hexdigest() if b is not None else None


def _lesen(pfad):
    try:
        with open(pfad, "rb") as f:
            return f.read()
    except (FileNotFoundError, IsADirectoryError):
        return None


def _kurz(rel):
    return rel[5:] if rel.startswith("data/") else rel


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


@contextlib.contextmanager
def _sperre(warten: float):
    os.makedirs(ordner(), exist_ok=True)
    with open(os.path.join(ordner(), "sperre"), "w") as f:
        bis = time.monotonic() + warten
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= bis:
                    raise Besetzt("Ein anderer Abgleich läuft gerade.") from None
                time.sleep(0.3)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ── Basis ──────────────────────────────────────────────────────────────

def _basis_lesen():
    """→ (stand oder None, {rel: bytes}). Ohne basis.json: noch nie abgeglichen."""
    kopf = _lesen(os.path.join(ordner(), "basis.json"))
    if kopf is None:
        return None, {}
    kopf = json.loads(kopf)
    wurzel = os.path.join(ordner(), "basis")
    return kopf.get("stand"), {rel: _lesen(os.path.join(wurzel, rel))
                               for rel in kopf.get("dateien", [])
                               if os.path.exists(os.path.join(wurzel, rel))}


def _basis_schreiben(stand, basis):
    wurzel = os.path.join(ordner(), "basis")
    _, alt = _basis_lesen()
    for rel, inhalt in basis.items():
        if alt.get(rel) != inhalt:
            dateien.atomar_schreiben(os.path.join(wurzel, rel), inhalt)
    for rel in set(alt) - set(basis):
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(wurzel, rel))
    # Der Kopf zuletzt: erst wenn er steht, gilt die neue Basis als ganz.
    dateien.json_schreiben(os.path.join(ordner(), "basis.json"),
                           {"stand": stand, "dateien": sorted(basis)})


# ── Mitte lesen ────────────────────────────────────────────────────────

def _leeres_inhalt():
    return {"format": 1, "dateien": {}, "geloescht": {}}


def _mitte_lesen(tresor, stand, lesen, basis):
    """→ (inhalt, {rel: klartext}) für alle Dateien auf unserer Liste."""
    if stand is None:
        return _leeres_inhalt(), {}
    roh = lesen(INHALT)
    if roh is None:
        raise abgleich_mitte.MitteFehler("In der Mitte fehlt das Inhaltsverzeichnis.")
    inhalt = json.loads(tresor.auf(roh))
    raus = {}
    for rel, e in inhalt.get("dateien", {}).items():
        if not auswahl.passt(rel, auswahl.ABGLEICH):
            continue   # nicht auf unserer Liste: bleibt in der Mitte unberührt
        if _sha(basis.get(rel)) == e["sha"]:
            raus[rel] = basis[rel]       # unverändert seit der Basis — nicht entschlüsseln
            continue
        g = lesen("d/" + e["name"] + ".enc")
        if g is None:
            raise abgleich_mitte.MitteFehler(f"In der Mitte fehlt {_kurz(rel)}.")
        raus[rel] = tresor.auf(g)
    return inhalt, raus


# ── Planen ─────────────────────────────────────────────────────────────

def _planen(basis, lokal, mitte, grabsteine, art, rechner, bericht):
    """→ (ergebnis {rel: bytes|None}, aufheben {rel: bytes}).
    aufheben = eigene Fassungen, die weichen mussten."""
    erg, aufheben = {}, {}
    for rel in sorted(set(basis) | set(lokal) | set(mitte)):
        b, l, m = basis.get(rel), lokal.get(rel), mitte.get(rel)
        stein = grabsteine.get(rel)
        tot = l is not None and stein is not None and stein.get("sha") == _sha(l)
        if art == "erstabgleich":
            # Noch keine Basis: die Mitte gilt. Zusammenführen hieße, einen
            # alten rsync-Stand mit allem Gelöschten zurückzubringen.
            if m is not None:
                erg[rel] = m
                if l is not None and l != m:
                    aufheben[rel] = l
                    bericht.hinweise.append(
                        f"{_kurz(rel)}: auf diesem Rechner anders als in der Mitte — "
                        "die Mitte gilt, die Fassung von hier ist aufgehoben")
            elif l is not None and stein is not None:
                erg[rel] = None
                bericht.hinweise.append(f"{_kurz(rel)}: wurde anderswo gelöscht — hier beiseitegelegt")
            else:
                erg[rel] = l
            continue
        if b is None and m is None and tot:
            erg[rel] = None   # unverändert zurückgekehrt, war gelöscht — bleibt gelöscht
            continue
        r = regeln.zusammenfuehren(rel, b, l, m, rechner)
        erg[rel] = r.inhalt
        if r.konflikte:
            text_regel = regeln.art(rel, b, l, m) == "text"
            if not text_regel and l is not None and r.inhalt != l:
                aufheben[rel] = l
            for k in r.konflikte[:5]:
                bericht.hinweise.append(f"{_kurz(rel)}: {k}")
    return erg, aufheben


# ── Vorhaben (absturzsicher) ───────────────────────────────────────────

def _vorhaben_dir():
    return os.path.join(ordner(), "vorhaben")


def _vorhaben_schreiben(kennung, erg, lokal, basis, aufheben):
    """Alles ablegen, was zum Fertigmachen nötig ist — BEVOR gesendet wird."""
    v = _vorhaben_dir()
    shutil.rmtree(v, ignore_errors=True)
    eintraege = {}
    for rel, r in erg.items():
        l = lokal.get(rel)
        if r == l and r == basis.get(rel):
            continue
        eintraege[rel] = {"neu": r is not None, "alt": l is not None,
                          "aufheben": rel in aufheben}
        if r is not None:
            dateien.atomar_schreiben(os.path.join(v, "neu", rel), r)
        if l is not None and l != r:
            dateien.atomar_schreiben(os.path.join(v, "alt", rel), l)
        if rel in aufheben:
            dateien.atomar_schreiben(os.path.join(v, "auf", rel), aufheben[rel])
    dateien.json_schreiben(os.path.join(v, "vorhaben.json"),
                           {"kennung": kennung, "zeit": _jetzt(), "eintraege": eintraege})


def _vorhaben_abschliessen(wurzel, bericht=None):
    """Das abgelegte Vorhaben auf dem Rechner zu Ende bringen und die neue
    Basis merken. Derselbe Weg im normalen Lauf und nach einem Absturz."""
    v = _vorhaben_dir()
    kopf = json.loads(_lesen(os.path.join(v, "vorhaben.json")))
    tag = kopf["zeit"].replace(":", "-").replace("T", "_")
    _, basis = _basis_lesen()
    basis = dict(basis)
    for rel, e in kopf["eintraege"].items():
        neu = _lesen(os.path.join(v, "neu", rel)) if e["neu"] else None
        alt = _lesen(os.path.join(v, "alt", rel)) if e["alt"] else None
        if e["alt"] and alt is None:
            alt = neu                     # alt == neu: nur die Basis ändert sich
        pfad = os.path.join(wurzel, rel)
        jetzt = _lesen(pfad)
        if jetzt == neu:
            pass                          # schon da (oder nach Absturz schon geschrieben)
        elif jetzt != alt:
            # Die App hat während des Abgleichs geschrieben. Nicht
            # überschreiben; als Basis gilt, was gelesen wurde — der nächste
            # Lauf führt die neue Fassung sauber mit der Mitte zusammen.
            if alt is None:
                basis.pop(rel, None)
            else:
                basis[rel] = alt
            continue
        else:
            if e["aufheben"]:
                dateien.atomar_schreiben(os.path.join(ordner(), "konflikte", tag, rel),
                                         _lesen(os.path.join(v, "auf", rel)))
            if neu is None:
                ziel = os.path.join(ordner(), "beiseite", tag, rel)
                os.makedirs(os.path.dirname(ziel), exist_ok=True)
                shutil.move(pfad, ziel)
                if bericht is not None:
                    bericht.beiseite.append(rel)
            else:
                dateien.atomar_schreiben(pfad, neu)
                if bericht is not None:
                    bericht.geholt.append(rel)
        if neu is None:
            basis.pop(rel, None)
        else:
            basis[rel] = neu
    _basis_schreiben(kopf["kennung"], basis)
    shutil.rmtree(v, ignore_errors=True)


def _vorhaben_nachholen(wurzel, mitte):
    """Ein Vorhaben von einem abgestürzten Lauf: ist sein Stand in der Mitte
    angekommen, zu Ende bringen — sonst verwerfen (die Mitte hat nichts)."""
    if not os.path.exists(os.path.join(_vorhaben_dir(), "vorhaben.json")):
        return
    kopf = json.loads(_lesen(os.path.join(_vorhaben_dir(), "vorhaben.json")))
    if mitte.enthaelt(kopf["kennung"]):
        _vorhaben_abschliessen(wurzel)
    else:
        shutil.rmtree(_vorhaben_dir(), ignore_errors=True)


# ── Der Abgleich ───────────────────────────────────────────────────────

def _neues_inhalt(tresor, inhalt, erg, mitte, rechner):
    """→ (neues inhalt, schreiben {name: bytes}, loeschen [name])."""
    neu = {"format": 1, "dateien": dict(inhalt.get("dateien", {})),
           "geloescht": dict(inhalt.get("geloescht", {}))}
    schreiben, loeschen = {}, []
    for rel, r in erg.items():
        if r == mitte.get(rel):
            continue
        name = tresor.name(rel)
        if r is None:
            neu["dateien"].pop(rel, None)
            neu["geloescht"][rel] = {"sha": _sha(mitte.get(rel)), "von": rechner, "am": _jetzt()}
            loeschen.append("d/" + name + ".enc")
        else:
            neu["dateien"][rel] = {"name": name, "sha": _sha(r)}
            neu["geloescht"].pop(rel, None)
            schreiben["d/" + name + ".enc"] = tresor.zu(r)
    schreiben[INHALT] = tresor.zu(json.dumps(neu, ensure_ascii=False).encode("utf-8"))
    return neu, schreiben, loeschen


def abgleichen(wurzel, trocken=False, warten=120.0) -> Bericht:
    """Einmal mit der Mitte abgleichen. `wurzel` = der ZENTRALE-Ordner, dessen
    data/ gemeint ist (bewusst ohne Vorgabe: kein Aufruf trifft aus Versehen
    die echten Daten). Fehler → SchluesselFehler / MitteFehler / Besetzt,
    und sie stehen danach auch im Zustand."""
    bericht = Bericht()
    bericht.trocken = trocken
    try:
        with _sperre(warten):
            tresor = schluessel.Tresor(schluessel.laden())
            mitte = mitte_oeffnen()
            rechner = dateien.knoten()
            if not trocken:
                _vorhaben_nachholen(wurzel, mitte)
            for _versuch in range(4):
                stand, lesen, namen = mitte.holen()
                basis_stand, basis = _basis_lesen()
                inhalt, m = _mitte_lesen(tresor, stand, lesen, basis)
                lokal = {rel: _lesen(os.path.join(wurzel, rel))
                         for rel in auswahl.auswahl(wurzel, auswahl.ABGLEICH)}
                bericht.art = ("erstbefuellung" if stand is None else
                               "erstabgleich" if basis_stand is None else "")
                if bericht.art == "erstbefuellung":
                    basis = {}
                bericht.hinweise, bericht.geholt, bericht.beiseite = [], [], []
                erg, aufheben = _planen(basis, lokal, m, inhalt.get("geloescht", {}),
                                        bericht.art, rechner, bericht)
                bericht.gesendet = sorted(r for r in erg if erg[r] != m.get(r))
                if trocken:
                    bericht.geholt = sorted(r for r in erg if erg[r] != lokal.get(r))
                    return bericht
                kennung = stand
                if bericht.gesendet or LIESMICH not in namen:
                    _, schreiben, loeschen = _neues_inhalt(tresor, inhalt, erg, m, rechner)
                    schreiben[LIESMICH] = LIESMICH_TEXT.encode("utf-8")
                    kennung = mitte.vorbereiten(schreiben, loeschen,
                                                f"Abgleich {_jetzt()} von {rechner}")
                _vorhaben_schreiben(kennung, erg, lokal, basis, aufheben)
                if kennung != stand and not mitte.senden(kennung):
                    shutil.rmtree(_vorhaben_dir(), ignore_errors=True)
                    continue              # jemand war schneller: neu holen
                _vorhaben_abschliessen(wurzel, bericht)
                _zustand_erfolg(bericht, kennung)
                return bericht
            raise abgleich_mitte.MitteFehler(
                "Die Mitte hat sich viermal hintereinander geändert — später nochmal.")
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler) as e:
        if not trocken:
            _zustand_fehler(str(e))
        raise


# ── Zustand ────────────────────────────────────────────────────────────

def _zustand_pfad():
    return os.path.join(ordner(), "zustand.json")


def _zustand_lesen():
    roh = _lesen(_zustand_pfad())
    try:
        return json.loads(roh) if roh else {}
    except ValueError:
        return {}


def _zustand_erfolg(bericht, kennung):
    z = _zustand_lesen()
    jetzt = _jetzt()
    z.update(letzter_versuch=jetzt, letzter_erfolg=jetzt, fehler=None, mitte_stand=kennung,
             geholt=len(bericht.geholt) + len(bericht.beiseite),
             gesendet=len(bericht.gesendet))
    neu = [{"am": jetzt, "text": h} for h in bericht.hinweise]
    z["hinweise"] = (z.get("hinweise", []) + neu)[-MAX_HINWEISE:]
    dateien.json_schreiben(_zustand_pfad(), z)


def _zustand_fehler(text):
    z = _zustand_lesen()
    z.update(letzter_versuch=_jetzt(), fehler=text)
    with contextlib.suppress(OSError):
        dateien.json_schreiben(_zustand_pfad(), z)


def zustand() -> dict:
    """Für Route, TUI und `status`: Weg, Schlüssel da?, letzter Abgleich,
    Fehler, Hinweise (neueste zuletzt)."""
    z = _zustand_lesen()
    return {"weg": weg(), "rechner": dateien.knoten(),
            "schluessel_da": schluessel.vorhanden(),
            "letzter_versuch": z.get("letzter_versuch"),
            "letzter_erfolg": z.get("letzter_erfolg"),
            "fehler": z.get("fehler"),
            "geholt": z.get("geholt", 0), "gesendet": z.get("gesendet", 0),
            "hinweise": z.get("hinweise", []),
            "konflikte_ordner": os.path.join(ordner(), "konflikte")}


def umstellen(neuer_weg: str) -> str:
    """Den Weg wechseln (bewusster Schritt). Nach `mitte` nur, wenn Schlüssel
    da ist und schon einmal erfolgreich abgeglichen wurde."""
    if neuer_weg not in WEGE:
        raise ValueError(f"Weg „{neuer_weg}“ gibt es nicht — nur rsync oder mitte.")
    if neuer_weg == "mitte":
        if not schluessel.vorhanden():
            raise schluessel.SchluesselFehler(
                "Erst einen Schlüssel anlegen oder eingeben, dann umstellen.")
        if not _zustand_lesen().get("letzter_erfolg"):
            raise abgleich_mitte.MitteFehler(
                "Erst einmal von Hand abgleichen (jetzt), dann umstellen.")
    ai_config.set_override("abgleich_weg", neuer_weg, persist=True)
    return neuer_weg
