# core/desk_bild.py
#
# Bilder auf dem Desk (2026-10-10). Sasha: „Images soll man auch
# draufbappen. Fürs Terminal eine Zwischenlösung: es wird eine Preview mit
# Titel als Kachel angezeigt, die Preview das Bild verpixelt …, und man kann
# es im Imageviewer direkt geöffnet kriegen."
#
# Ein Bild auf dem Desk ist in der .canvas-Datei ein file-Knoten (JSON
# Canvas 1.0), `file` relativ zum Desk-Ordner — so zeigt Obsidian das echte
# Bild. Die Datei selbst liegt in <desk_ordner>/bilder/.
#
# Warum KOPIEREN statt auf die Quelle zeigen (2026-10-10): der Desk-Ordner
# wird abgeglichen (data/desk/** auf der Positivliste), der Nutzerordner
# ~/Zentrale/Input nicht — und Input/ ist ein Durchgangsort, den Sasha
# leerräumt. Erst die Kopie macht das Bild zu einem Teil des Desks, der auf
# jedem Rechner da ist und in Obsidian aufgeht. Die Leitlinie „dasselbe
# Objekt, nicht kopiert" ist damit nicht verletzt: das Bild im Desk-Ordner
# IST danach das Objekt, auf das der Knoten zeigt; die Quelle in Input/ war
# nur die Anlieferung.
#
# Vorschau: core/bild_vorschau.py (Sashas ASCII-Filter). Öffnen im
# Bildbetrachter macht die TUI auf ihrem Rechner; hier steht nur, welcher
# Betrachter eingestellt ist (`bild_betrachter`, Standard „system").
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import hashlib
import os
import shutil

import ai_config
import bild_vorschau
import datasync
import desk
import nutzer_ordner

UNTERORDNER = "bilder"
GROESSE_GRENZE = 50 * 1024 * 1024
QUELLEN_GRENZE = 200
KACHEL_BREITE = 34                      # Standardbreite eines neuen Bildes (Zellen)


def bilder_ordner() -> str:
    return os.path.join(desk.ordner(), UNTERORDNER)


def pfad(datei) -> str:
    """Relativer Pfad aus dem Knoten → echter Pfad im Desk-Ordner. Was
    (auch über einen Verweis) hinausführt: DeskFehler."""
    d = desk.datei_pruefen(datei)
    wurzel = os.path.realpath(desk.ordner())
    echt = os.path.realpath(os.path.join(wurzel, d))
    if not echt.startswith(wurzel + os.sep):
        raise desk.DeskFehler("bild-datei liegt außerhalb des desks")
    return echt


def betrachter() -> str:
    return str(ai_config.setting("bild_betrachter", "system") or "system").strip() or "system"


# ── Quellen: was man auf den Desk legen kann ──────────────────────────

def quellen() -> list:
    """Bilder in ~/Zentrale/Input (auch eine Ebene tiefer), neueste zuerst:
    [{name, pfad}] — `name` relativ zu Input/, so wie man es tippen würde."""
    wurzel = nutzer_ordner.unterordner(nutzer_ordner.INPUT)
    raus = []
    for ort, ordner, namen in os.walk(wurzel):
        # Nur Input/ und eine Ebene darunter; versteckte Ordner (.Papierkorb
        # von input_dateien) nie.
        ordner[:] = [o for o in ordner if not o.startswith(".")] if ort == wurzel else []
        for n in namen:
            if n.startswith(".") or not desk.ist_bild(n):
                continue
            p = os.path.join(ort, n)
            try:
                mtime = os.path.getmtime(p)
            except OSError:
                continue
            raus.append({"name": os.path.relpath(p, wurzel), "pfad": p, "mtime": mtime})
    raus.sort(key=lambda q: -q["mtime"])
    return [{"name": q["name"], "pfad": q["pfad"]} for q in raus[:QUELLEN_GRENZE]]


def _quelle_finden(quelle) -> str:
    """Wie Sasha es nennt („foto.jpg", „Input/x.png", „~/Bilder/y.png") →
    echter Pfad. Ein Name ohne Ordner kommt aus Input/."""
    roh = str(quelle or "").strip()
    if not roh:
        raise desk.DeskFehler("welches bild?")
    roh = os.path.expanduser(roh)
    if not os.path.isabs(roh):
        p = nutzer_ordner.aufloesen(roh)
        if p is None:
            raise desk.DeskFehler("bild nicht gefunden: " + quelle, 404)
        roh = p
    if not os.path.isfile(roh):
        raise desk.DeskFehler("bild nicht gefunden: " + str(quelle), 404)
    return os.path.realpath(roh)


def _inhalt_gleich(a, b) -> bool:
    def summe(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for stueck in iter(lambda: f.read(1 << 16), b""):
                h.update(stueck)
        return h.digest()
    return os.path.getsize(a) == os.path.getsize(b) and summe(a) == summe(b)


def _zielname(quelle) -> str:
    """Freier Name in bilder/: derselbe Name, wenn er frei ist oder dort schon
    genau dieses Bild liegt; sonst „name-2.png" …"""
    basis, endung = os.path.splitext(os.path.basename(quelle))
    basis = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in basis).strip() or "bild"
    endung = endung.lower()
    for i in range(1, 1000):
        name = basis + ("" if i == 1 else "-%d" % i) + endung
        ziel = os.path.join(bilder_ordner(), name)
        if not os.path.exists(ziel) or _inhalt_gleich(quelle, ziel):
            return name
    raise desk.DeskFehler("zu viele bilder mit diesem namen")


def uebernehmen(quelle) -> dict:
    """Ein Bild in <desk_ordner>/bilder/ kopieren (atomar). Gibt zurück, was
    die TUI für ein neues Element braucht: {datei, titel, w, h}. Nur Bilder,
    die Pillow lesen kann — ein getippter Pfad holt so nie etwas anderes in
    den abgeglichenen Ordner."""
    q = _quelle_finden(quelle)
    if not desk.ist_bild(q):
        raise desk.DeskFehler("das ist keine bild-datei (png, jpg, gif, webp, bmp)")
    if os.path.getsize(q) > GROESSE_GRENZE:
        raise desk.DeskFehler("bild ist größer als 50 MB")
    try:
        bw, bh = bild_vorschau.groesse(q)
    except bild_vorschau.KeinBild as e:
        raise desk.DeskFehler(str(e), 422)
    except bild_vorschau.OhnePillow as e:
        raise desk.DeskFehler(str(e), 503)
    os.makedirs(bilder_ordner(), exist_ok=True)
    name = _zielname(q)
    ziel = os.path.join(bilder_ordner(), name)
    if not os.path.exists(ziel):
        zwischen = os.path.join(bilder_ordner(), ".%s.%d.tmp" % (name, os.getpid()))
        try:
            shutil.copyfile(q, zwischen)
            os.replace(zwischen, ziel)
        finally:
            if os.path.exists(zwischen):
                os.unlink(zwischen)
        datasync.notify_change(ziel)
    innen = KACHEL_BREITE - 2
    zeilen = max(4, min(16, bild_vorschau.zellen_fuer(bw, bh, innen)))
    return {"datei": UNTERORDNER + "/" + name,
            "titel": os.path.splitext(name)[0],
            "w": KACHEL_BREITE, "h": zeilen + 3}     # Rahmen oben/unten + Titelzeile


# ── Vorschau und Öffnen ───────────────────────────────────────────────

def vorschau(datei, spalten, zeilen, modus="mono", invert=False) -> dict:
    """{status, zeilen?, text?}. status: ok | weg (Datei fehlt) | kein_bild |
    ohne_pillow. Ein fehlendes Bild ist kein Fehler der Anfrage: die Kachel
    zeigt „weg" leise an (z. B. noch nicht vom anderen Rechner da)."""
    if modus not in desk.BILDMODI:
        raise desk.DeskFehler("modus: mono oder farbe")
    try:
        spalten, zeilen = int(spalten), int(zeilen)
    except (TypeError, ValueError):
        raise desk.DeskFehler("breite/höhe müssen zahlen sein")
    p = pfad(datei)
    try:
        return {"status": "ok",
                "zeilen": bild_vorschau.vorschau(p, spalten, zeilen, modus, invert)}
    except FileNotFoundError:
        return {"status": "weg", "text": "bild fehlt: " + datei}
    except bild_vorschau.KeinBild as e:
        return {"status": "kein_bild", "text": str(e)}
    except bild_vorschau.OhnePillow as e:
        return {"status": "ohne_pillow", "text": str(e)}


def oeffnen_info(datei) -> dict:
    """Was die TUI zum Öffnen braucht: echter Pfad (auf dem Rechner des
    Backends), ob es ihn gibt, und der eingestellte Betrachter."""
    p = pfad(datei)
    return {"pfad": p, "da": os.path.isfile(p), "betrachter": betrachter()}
