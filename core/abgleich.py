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
# abgleich_auswahl; was dieses Gerät davon will (je App): abgleich_apps.
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
import base64
import json
import os
import re
import shutil
import time

import abgleich_apps
import abgleich_auswahl as auswahl
import abgleich_mitte
import abgleich_schluessel as schluessel
import abgleich_vorschlaege as vorschlag
import abgleich_zusammenfuehren as regeln
import adapter
import adapter_geheim
import ai_config
import dateien
import konto

VORGABE_DIR = "~/.local/share/zentrale/abgleich"
VORGABE_MITTE = "git@github.com:Eightdevvis/data.git"
INHALT = "inhalt.enc"
LIESMICH = "LIESMICH.md"
EINGANG = "knoten"        # knoten/<name>/<versteckter name>.enc — Eingang fremder Knoten
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


def mitte_art() -> str:
    return (ai_config.setting("abgleich_mitte_art") or "git").strip().lower()


def mitte_oeffnen():
    if mitte_art() == "http":
        # Die Cloud: Adresse und Sitzung kommen vom Konto (core/konto.py).
        c = konto.client()
        return abgleich_mitte.oeffnen("http", c.basis, "", token=c.token)
    return abgleich_mitte.oeffnen(
        mitte_art(),
        ai_config.setting("abgleich_mitte") or VORGABE_MITTE,
        os.path.join(ordner(), "mitte"))


def schluessel_laden() -> bytes:
    """Der Schlüssel der Mitte. Über die Cloud (`http`) ist es der
    konto_schluessel aus konto.json, sonst abgleich.schluessel (KeePass)."""
    if mitte_art() == "http":
        try:
            return konto.konto_schluessel()
        except konto.KontoFehler as e:
            raise schluessel.SchluesselFehler(str(e)) from None
    return schluessel.laden()


def schluessel_da() -> bool:
    return konto.angemeldet() if mitte_art() == "http" else schluessel.vorhanden()


def cloud_an() -> bool:
    """Die App `cloud` (core/eingebaute_apps.py) ist an: dieses Gerät gleicht
    über die ZENTRALE-Cloud ab und ist angemeldet. Sonst ist es rein lokal."""
    return mitte_art() == "http" and konto.angemeldet()


def cloud_pfade():
    """Welche Pfade in der Cloud liegen — nur aus dem verschlüsselten
    Inhaltsverzeichnis (inhalt.enc), ohne eine Datei zu laden. Für die Frage
    „hat diese App schon Daten?". Immer die Cloud (Konto + konto_schluessel),
    egal, über welchen Weg dieses Gerät gerade abgleicht. None, wenn es nicht
    geht (abgemeldet, offline) — das ist nie ein Fehler."""
    try:
        if not konto.angemeldet():
            return None
        tresor = schluessel.Tresor(konto.konto_schluessel())
        c = konto.client()
        stand, lesen, _namen = abgleich_mitte.oeffnen("http", c.basis, "", token=c.token).holen()
        if stand is None:
            return set()
        roh = lesen(INHALT)
        return set(json.loads(tresor.auf(roh)).get("dateien", {})) if roh else set()
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler, konto.KontoFehler,
            OSError, ValueError):
        return None


def mitte_pfade():
    """Welche Pfade das Inhaltsverzeichnis der Mitte nennt, auf dem Weg, über
    den dieses Gerät abgleicht (git oder Cloud) — ohne eine Datei zu laden.
    None, wenn es nicht geht (kein Schlüssel, offline)."""
    try:
        tresor = schluessel.Tresor(schluessel_laden())
        stand, lesen, _namen = mitte_oeffnen().holen()
        if stand is None:
            return set()
        roh = lesen(INHALT)
        return set(json.loads(tresor.auf(roh)).get("dateien", {})) if roh else set()
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler, konto.KontoFehler,
            OSError, ValueError):
        return None


def mitte_hat_kalender(ordner="data/kalender"):
    """Liegt im Inhaltsverzeichnis der Mitte mindestens eine Datei unter
    `ordner`/** (Vorgabe: die Termine)? True / False (Mitte erreichbar, nichts
    da) / None (offline, kein Schlüssel — unbekannt; der Aufrufer bricht dann
    ab). Für die Quelle der Kalender-App (adapter.vor_abgleich,
    adapter_ablauf.kalender_quelle_setzen): die Mitte ist die Wahrheit — hat
    sie schon Termine, legt ein Gerät, das zum ersten Mal dazukommt, seine
    beiseite; ist sie leer, füllt es sie."""
    pfade = mitte_pfade()
    if pfade is None:
        return None
    vorn = ordner.rstrip("/") + "/"
    return any(p.startswith(vorn) for p in pfade)


def basis_kennt(ordner="data/kalender") -> bool:
    """Kennt die Basis dieses Geräts (basis.json: worauf es sich zuletzt mit
    der Mitte geeinigt hat) mindestens eine Datei unter `ordner`/**? Nein =
    dieses Gerät hat sich über den Ordner noch nie mit der Mitte geeinigt
    („erstes Mal“, adapter.vor_abgleich)."""
    try:
        kopf = json.loads(_lesen(os.path.join(_abgleich_dir(), "basis.json")) or b"{}")
    except ValueError:
        return False
    vorn = ordner.rstrip("/") + "/"
    return any(isinstance(r, str) and r.startswith(vorn) for r in kopf.get("dateien") or [])


_abgleich_dir = ordner          # basis_kennt nimmt den Namen `ordner` als Argument


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


def _mitte_lesen(tresor, stand, lesen, basis, muster=auswahl.ABGLEICH):
    """→ (inhalt, {rel: klartext}) für alle Dateien auf unserer Liste
    (`muster` = was dieses Gerät abgleicht, abgleich_apps)."""
    if stand is None:
        return _leeres_inhalt(), {}
    roh = lesen(INHALT)
    if roh is None:
        raise abgleich_mitte.MitteFehler("In der Mitte fehlt das Inhaltsverzeichnis.")
    inhalt = json.loads(tresor.auf(roh))
    raus = {}
    for rel, e in inhalt.get("dateien", {}).items():
        if not auswahl.passt(rel, muster):
            continue   # nicht auf unserer Liste: bleibt in der Mitte unberührt
        if _sha(basis.get(rel)) == e["sha"]:
            raus[rel] = basis[rel]       # unverändert seit der Basis — nicht entschlüsseln
            continue
        g = lesen("d/" + e["name"] + ".enc")
        if g is None:
            raise abgleich_mitte.MitteFehler(f"In der Mitte fehlt {_kurz(rel)}.")
        raus[rel] = tresor.auf(g)
    return inhalt, raus


# ── Eingang fremder Knoten (Handy, 2026-10-08) ─────────────────────────
# Das Handy (eigene App, Dart) liest die Mitte, schreibt aber NIE ins
# Inhaltsverzeichnis — sonst stritten es und die Rechner um eine Datei.
# Es legt nur eigene Dateien in seinen Eingang knoten/<name>/, jede als
# verschlüsselter Umschlag {format, pfad, inhalt}. Format für fremde Knoten:
# memory/betrieb/abgleich_fremde_knoten.md.

_KNOTEN_NAME = re.compile(r"^[A-Za-z0-9@.\-]+$")


def eigene_datei(rel: str, knoten: str) -> bool:
    """Gehört die Datei allein diesem Knoten? Dann schreibt sie nur er —
    konfliktfrei durch Bauart (gespraeche/<id>/<knoten>.jsonl,
    gespraeche/_knoten/<knoten>.json, rueckmeldungen/<knoten>.jsonl)."""
    teile = rel.split("/")
    name = teile[-1]
    if rel.startswith("data/gespraeche/") and len(teile) == 4:
        return name == knoten + ".jsonl" or (teile[2] == "_knoten" and name == knoten + ".json")
    return rel == f"data/rueckmeldungen/{knoten}.jsonl"


def _eingang_lesen(tresor, namen, lesen, rechner, bericht, muster=auswahl.ABGLEICH, gesehen=None):
    """→ (fremd {rel: bytes}, vorschlaege {rel: bytes | Vorschlag}). Was nicht
    passt (falscher Pfad, kaputt, fremde Datei), wird übergangen — mit Hinweis.
    Ein Termin-Vorschlag kommt als abgleich_vorschlaege.Vorschlag (mit Basis,
    Löschen, Prüfwert des Umschlags für die Quittung). `gesehen` (Menge)
    bekommt jedes lesbare (knoten, pfad) — damit verfallen alte Quittungen."""
    fremd, vorschlaege = {}, {}
    for name in namen:
        teile = name.split("/")
        if len(teile) != 3 or teile[0] != EINGANG or not teile[2].endswith(".enc"):
            continue
        knoten = teile[1]
        if not _KNOTEN_NAME.match(knoten) or knoten == rechner:
            continue
        try:
            klar = tresor.auf(lesen(name) or b"")
            u = json.loads(klar)
            rel = u["pfad"]
            loeschen = u.get("loeschen") is True
            inhalt = (None if loeschen and u.get("inhalt") is None
                      else base64.b64decode(u["inhalt"], validate=True))
            basis_roh = u.get("basis")
            basis_roh = base64.b64decode(basis_roh, validate=True) if basis_roh else None
            if not isinstance(rel, str):
                raise TypeError(rel)
        except schluessel.SchluesselFehler:
            raise
        except (ValueError, KeyError, TypeError):
            bericht.hinweise.append(f"Eingang {knoten}: eine Datei ist unlesbar — übergangen")
            continue
        if not auswahl.passt(rel, auswahl.ABGLEICH) or teile[2] != tresor.name(rel) + ".enc":
            bericht.hinweise.append(f"Eingang {knoten}: {rel!r} gehört nicht dorthin — übergangen")
        elif not auswahl.passt(rel, muster):
            continue          # App auf diesem Gerät abgewählt
        elif loeschen and not vorschlag.ist_kalender(rel):
            bericht.hinweise.append(f"Eingang {knoten}: {_kurz(rel)} löschen darf er nicht — übergangen")
        elif eigene_datei(rel, knoten):
            fremd[rel] = inhalt
        elif vorschlag.ist_kalender(rel):
            if gesehen is not None:
                gesehen.add((knoten, rel))
            vorschlaege[rel] = vorschlag.Vorschlag(
                rel, inhalt, loeschen, u.get("basis_sha"), basis_roh, knoten,
                hashlib.sha256(klar).hexdigest())
        elif vorschlag.ist_vorschlag(rel):
            vorschlaege[rel] = inhalt
        else:
            bericht.hinweise.append(f"Eingang {knoten}: {_kurz(rel)} darf er nicht schreiben — übergangen")
    return fremd, vorschlaege


def _vorschlaege_pruefen(vorschlaege, m, geloescht, bericht, basis=None, eingang=None,
                         trocken=False):
    """Welche Vorschläge gelten (abgleich_vorschlaege)? Ein Gesprächskopf,
    solange die Mitte keinen hat; ein Termin nach kalender_vorschlag_annehmen
    (neu, geändert, Ebene gewechselt, gelöscht — nie gegen einen Widerspruch).
    → ({rel: bytes | None=löschen}, quittungen).

    Quittungen (`eingang` in inhalt.enc, {knoten: {pfad: {umschlag, ergebnis,
    grund, am}}}): jeder entschiedene Termin-Vorschlag bekommt eine; daran
    sieht das Handy, dass er erledigt ist, und räumt seinen Eingang. Ein
    Umschlag mit Quittung wird nicht noch einmal geprüft. Abgelehnt → die
    Fassung vom Handy liegt zusätzlich unter konflikte/eingang-<knoten>/."""
    raus = {}
    quittungen = {k: dict(v) for k, v in (eingang or {}).items() if isinstance(v, dict)}
    for rel, v in vorschlaege.items():
        if not isinstance(v, vorschlag.Vorschlag):
            if rel not in m:
                raus[rel] = v               # Kopf eines neuen Gesprächs
            continue
        alt = quittungen.get(v.knoten, {}).get(rel)
        if isinstance(alt, dict) and alt.get("umschlag") == v.umschlag:
            continue                        # schon entschieden
        e = vorschlag.kalender_vorschlag_annehmen(v, m, geloescht, basis)
        if e.ja and any(r in raus for r in e.schreiben):
            e = vorschlag.Entscheid(vorschlag.ABGELEHNT, "ein anderer Vorschlag trifft dieselbe Datei")
        if e.ja:
            raus.update(e.schreiben)
        elif e.ergebnis == vorschlag.ABGELEHNT:
            bericht.hinweise.append(f"Eingang {v.knoten}: Termin {_kurz(rel)} abgelehnt — "
                                    f"{e.grund}; die Mitte bleibt, wie sie ist")
            if v.inhalt is not None and not trocken:
                dateien.atomar_schreiben(os.path.join(
                    ordner(), "konflikte", f"eingang-{v.knoten}", v.umschlag[:12], rel), v.inhalt)
        q = {"umschlag": v.umschlag, "ergebnis": e.ergebnis, "am": _jetzt()}
        if e.grund:
            q["grund"] = e.grund
        quittungen.setdefault(v.knoten, {})[rel] = q
    return raus, quittungen


def _quittungen_aufraeumen(quittungen, gesehen, muster):
    """Eine Quittung gilt, solange der Umschlag im Eingang liegt. Räumt der
    Knoten ihn weg, fällt sie. Pfade, die dieses Gerät nicht abgleicht,
    bleiben unberührt (ein anderes Gerät hat sie entschieden)."""
    raus = {}
    for k, eintraege in quittungen.items():
        behalten = {rel: q for rel, q in eintraege.items()
                    if (k, rel) in gesehen or not auswahl.passt(rel, muster)}
        if behalten:
            raus[k] = behalten
    return raus


# ── Apps neu dabei (2026-10-29) ────────────────────────────────────────
# Grundsatz „die Cloud wird nie überschrieben“: wird eine App auf diesem
# Gerät (wieder) angewählt, gilt für ihre Dateien die Mitte — wie beim
# Erstabgleich. Eine abweichende Fassung von hier wird aufgehoben
# (konflikte/<zeit>/), Sasha wählt. Sonst liefe sie über eine alte Basis
# zusammen, und eine .ics mit späterem LAST-MODIFIED ersetzte die der Mitte.

def _dabei_pfad():
    return os.path.join(ordner(), "apps_dabei.json")


def _dabei_lesen():
    """Die Muster des letzten erfolgreichen Abgleichs; None = noch nie gemerkt."""
    roh = _lesen(_dabei_pfad())
    try:
        w = json.loads(roh) if roh else None
    except ValueError:
        return None
    return set(w["muster"]) if isinstance(w, dict) and isinstance(w.get("muster"), list) else None


def _neu_dabei(muster) -> list:
    """Muster, die dieses Gerät jetzt abgleicht, beim letzten Mal aber nicht.
    Ohne Merkzettel: keine (ein Gerät von vor dieser Regel). Pflicht-Apps
    (der Adapter, z. B. Zugangsdaten erst ab der Anmeldung) zählen nie."""
    vorher = _dabei_lesen()
    if vorher is None:
        return []
    pflicht = {x for a in abgleich_apps.tabelle().values() if a["pflicht"] for x in a["muster"]}
    return [x for x in muster if x not in vorher and x not in pflicht]


# ── Planen ─────────────────────────────────────────────────────────────

def _planen(basis, lokal, mitte, grabsteine, art, rechner, bericht, fremd=None, neu_dabei=()):
    """→ (ergebnis {rel: bytes|None}, aufheben {rel: bytes}).
    aufheben = eigene Fassungen, die weichen mussten. fremd = Dateien aus dem
    Eingang eines anderen Knotens: die gelten, wie sie sind — nie überschrieben.
    neu_dabei = Muster einer (wieder) angewählten App: für sie gilt die Mitte
    wie beim Erstabgleich."""
    erg, aufheben = {}, {}
    fremd = fremd or {}
    for rel in sorted(set(basis) | set(lokal) | set(mitte)):
        b, l, m = basis.get(rel), lokal.get(rel), mitte.get(rel)
        if rel in fremd:
            erg[rel] = fremd[rel]
            continue
        stein = grabsteine.get(rel)
        tot = l is not None and stein is not None and stein.get("sha") == _sha(l)
        neu = art != "erstabgleich" and bool(neu_dabei) and auswahl.passt(rel, neu_dabei)
        if art == "erstabgleich" or neu:
            # Noch keine Basis: die Mitte gilt. Zusammenführen hieße, einen
            # alten rsync-Stand mit allem Gelöschten zurückzubringen. Ebenso
            # für eine wieder angewählte App (ihre Basis ist alt).
            if m is not None:
                erg[rel] = m
                if l is not None and l != m:
                    aufheben[rel] = l
                    bericht.hinweise.append(
                        f"{_kurz(rel)}: auf diesem Rechner anders als in der Mitte"
                        + (" (App neu dabei)" if neu else "") +
                        " — die Mitte gilt, die Fassung von hier ist aufgehoben")
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


def _vorhaben_kennung(mitte):
    """HttpMitte vergibt die echte Kennung erst beim Senden; im Vorhaben
    steht bis dahin die vorläufige. Danach die echte eintragen, damit die
    Basis sich den Stand des Servers merkt. (GitMitte: nichts zu tun.)"""
    echt = getattr(mitte, "echte_kennung", None)
    pfad = os.path.join(_vorhaben_dir(), "vorhaben.json")
    if echt is None or not os.path.exists(pfad):
        return
    kopf = json.loads(_lesen(pfad))
    if echt(kopf["kennung"]) != kopf["kennung"]:
        kopf["kennung"] = echt(kopf["kennung"])
        dateien.json_schreiben(pfad, kopf)


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
        pfad = auswahl.pfad(wurzel, rel)
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
        _vorhaben_kennung(mitte)
        _vorhaben_abschliessen(wurzel)
    else:
        shutil.rmtree(_vorhaben_dir(), ignore_errors=True)


# ── Der Abgleich ───────────────────────────────────────────────────────

def _neues_inhalt(tresor, inhalt, erg, mitte, rechner, fremd=(), eingang=None):
    """→ (neues inhalt, schreiben {name: bytes}, loeschen [name]).
    `mitte` = was im Inhaltsverzeichnis steht; Dateien fremder Knoten
    (`fremd`) bleiben in deren Eingang und kommen nie hinein. `eingang` = die
    Quittungen für fremde Knoten (None = unverändert übernehmen)."""
    neu = {"format": 1, "dateien": dict(inhalt.get("dateien", {})),
           "geloescht": dict(inhalt.get("geloescht", {}))}
    eingang = inhalt.get("eingang") if eingang is None else eingang
    if eingang:
        neu["eingang"] = eingang
    schreiben, loeschen = {}, []
    for rel, r in erg.items():
        if r == mitte.get(rel) or rel in fremd:
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
            tresor = schluessel.Tresor(schluessel_laden())
            mitte = mitte_oeffnen()
            rechner = dateien.knoten()
            muster = abgleich_apps.muster()
            if not trocken:
                _vorhaben_nachholen(wurzel, mitte)
                _adapter_vorher(wurzel, muster)
            for _versuch in range(4):
                stand, lesen, namen = mitte.holen()
                basis_stand, basis = _basis_lesen()
                # Abgewählte Apps: weder holen noch senden — auch nicht
                # über die Basis (sonst sähe eine abgewählte App aus wie
                # „überall gelöscht").
                basis = {rel: b for rel, b in basis.items() if auswahl.passt(rel, muster)}
                gesehen = set()
                try:
                    inhalt, m = _mitte_lesen(tresor, stand, lesen, basis, muster)
                    bericht.hinweise, bericht.geholt, bericht.beiseite = [], [], []
                    fremd, vorschlaege = _eingang_lesen(tresor, namen, lesen, rechner,
                                                        bericht, muster, gesehen)
                except abgleich_mitte.MitteBewegt:
                    continue                  # mitten im Lesen weitergelaufen: neu holen
                sicht = dict(m)                 # was die Mitte insgesamt sagt
                sicht.update(fremd)
                eingang_alt = inhalt.get("eingang") or {}
                angenommen, eingang = _vorschlaege_pruefen(
                    vorschlaege, m, inhalt.get("geloescht", {}), bericht, basis,
                    eingang_alt, trocken)
                sicht.update(angenommen)
                eingang = _quittungen_aufraeumen(eingang, gesehen, muster)
                lokal = {rel: _lesen(auswahl.pfad(wurzel, rel))
                         for rel in auswahl.auswahl(wurzel, muster)}
                bericht.art = ("erstbefuellung" if stand is None else
                               "erstabgleich" if basis_stand is None else "")
                if bericht.art == "erstbefuellung":
                    basis = {}
                erg, aufheben = _planen(basis, lokal, sicht, inhalt.get("geloescht", {}),
                                        bericht.art, rechner, bericht, fremd,
                                        _neu_dabei(muster) if bericht.art == "" else ())
                bericht.gesendet = sorted(r for r in erg
                                          if erg[r] != m.get(r) and r not in fremd)
                if trocken:
                    bericht.geholt = sorted(r for r in erg if erg[r] != lokal.get(r))
                    return bericht
                kennung = stand
                if bericht.gesendet or LIESMICH not in namen or eingang != eingang_alt:
                    _, schreiben, loeschen = _neues_inhalt(tresor, inhalt, erg, m, rechner, fremd,
                                                           eingang)
                    schreiben[LIESMICH] = LIESMICH_TEXT.encode("utf-8")
                    kennung = mitte.vorbereiten(schreiben, loeschen,
                                                f"Abgleich {_jetzt()} von {rechner}")
                _vorhaben_schreiben(kennung, erg, lokal, basis, aufheben)
                if kennung != stand and not mitte.senden(kennung):
                    shutil.rmtree(_vorhaben_dir(), ignore_errors=True)
                    continue              # jemand war schneller: neu holen
                _vorhaben_kennung(mitte)
                kennung = getattr(mitte, "echte_kennung", lambda k: k)(kennung)
                _vorhaben_abschliessen(wurzel, bericht)
                dateien.json_schreiben(_dabei_pfad(), {"muster": sorted(muster)})
                _zustand_erfolg(bericht, kennung)
                _adapter_nachher(wurzel, muster)
                return bericht
            raise abgleich_mitte.MitteFehler(
                "Die Mitte hat sich viermal hintereinander geändert — später nochmal.")
    except (schluessel.SchluesselFehler, abgleich_mitte.MitteFehler) as e:
        if not trocken:
            _zustand_fehler(str(e))
        raise


# ── Der Adapter (memory/hub/adapter.md) ────────────────────────────────

def _adapter_vorher(wurzel, muster):
    """Zugangsdaten auf den Schlüssel bringen, der jetzt gilt (angemeldet →
    Konto), und einen Kalender, der zum ersten Mal über die Cloud kommt,
    sauber übernehmen (adapter.vor_abgleich). Ein Fehler beim Beiseitelegen
    bricht den Abgleich ab — lieber kein Abgleich als Geister."""
    try:
        adapter_geheim.umschluesseln(wurzel=wurzel)
    except Exception as e:      # noqa: BLE001 — Zugangsdaten sind Beiwerk des Abgleichs
        print(f"[abgleich] Zugangsdaten nicht umgeschlüsselt: {e}")
    adapter.vor_abgleich(wurzel, ordner(), muster, mitte_hat_kalender=mitte_hat_kalender,
                         basis_kennt=basis_kennt)


def _adapter_nachher(wurzel, muster):
    """Merken, dass der Kalender mitläuft; frisch angekommene KI-Schlüssel
    gleich in die Umgebung (ein neues Gerät hat so ohne Neustart eine KI)."""
    try:
        adapter.nach_abgleich(ordner(), muster)
        adapter_geheim.schluessel_einspielen(wurzel)
    except Exception as e:      # noqa: BLE001
        print(f"[abgleich] Adapter nach dem Abgleich: {e}")


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
            "schluessel_da": schluessel_da(),
            "mitte_art": mitte_art(), "cloud": cloud_an(),
            "apps": abgleich_apps.entscheidungen(),
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
        if not schluessel_da():
            raise schluessel.SchluesselFehler(
                "Erst einen Schlüssel anlegen oder eingeben, dann umstellen.")
        if not _zustand_lesen().get("letzter_erfolg"):
            raise abgleich_mitte.MitteFehler(
                "Erst einmal von Hand abgleichen (jetzt), dann umstellen.")
    ai_config.set_override("abgleich_weg", neuer_weg, persist=True)
    return neuer_weg
