# core/desk.py
#
# Desk View: eine unendliche Fläche pro Desk („Elektronik", „Geige" …), auf
# der Notizen liegen und mit Schnüren verbunden sind. Hier wohnt nur die
# Datei: lesen, prüfen, schreiben. Was man auf der Fläche tut, macht die TUI
# (tui/ansichten/desk.py mit dem Baustein tui/bausteine/canvas.py) und
# schickt den ganzen Desk per PUT zurück. Doku: memory/system/desk_view.md.
#
# ── Format: JSON Canvas 1.0 (https://jsoncanvas.org/spec/1.0/) ─────────
# Eine Datei pro Desk, `<desk_ordner>/<name>.canvas`, so wie Obsidian sie
# schreibt: {"nodes": [...], "edges": [...]}. 2026-10-09: ein offenes,
# kleines Format statt eines eigenen — Sasha kann einen Desk in Obsidian
# öffnen, und der Abgleich führt `nodes`/`edges` Eintrag für Eintrag nach
# `id` zusammen wie jede JSON-Datei (abgleich_zusammenfuehren).
#
# Die TUI rechnet in Zellen, die Datei in Pixeln. Feste Umrechnung
# (2026-10-09): 1 Spalte = 10 px, 1 Zeile = 20 px — eine Terminalzelle ist
# etwa doppelt so hoch wie breit, so sieht der Desk in Obsidian aus wie im
# Terminal. Die Datei ist die Wahrheit: eine Lage wird nur neu geschrieben,
# wenn sie sich IN ZELLEN geändert hat — sonst würde jedes Speichern die
# Pixel-Lagen aus Obsidian auf das 10er-Raster ziehen.
#
# Arten (2026-10-09): ein Text-Knoten (type "text", Markdown) ist ein
# Zettel, Art „notiz", erste Zeile = Titel. Ein Text-Knoten mit
# `zentrale_kachel` ist eine Kachel (Art „kachel", Verweis auf ein Objekt
# einer anderen App) — Text und Zusatzfeld bleiben unangetastet, nur die
# Lage ändert sich. Ein file-Knoten, dessen Datei ein Bild ist, ist ein
# Bild (Art „bild", 2026-10-10): `file` relativ zum Desk-Ordner, damit
# Obsidian das echte Bild zeigt (core/desk_bild.py legt es nach bilder/).
# Eigene Zusatzfelder nur mit Vorsilbe: `zentrale_titel` (sonst gilt der
# Dateiname) und `zentrale_bildmodus` (mono/farbe der Vorschau im Terminal).
# Alles andere (file, link, group …) kommt als Art „fremd" an: bleibt, wie es ist, lässt sich verschieben und verbinden,
# nicht bearbeiten.
# Felder, die die TUI nicht kennt (color …), bleiben unverändert stehen.
#
# ── Ort ───────────────────────────────────────────────────────────────
# Einstellung `desk_ordner` (Env ZENTRALE_DESK_ORDNER; Tests), Standard
# data/desk/ in ZENTRALE. 2026-10-09, Sasha: der Desk-Ordner soll IMMER mit
# abgeglichen werden. Der Abgleich arbeitet relativ zur ZENTRALE-Wurzel
# (Positivliste core/abgleich_auswahl.py: data/desk/**); ein Ordner im
# Nutzerordner ~/Zentrale hätte einen zweiten Wurzel-Begriff im Abgleich
# gebraucht. Wer `desk_ordner` woanders hin stellt, gleicht ihn NICHT ab.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import hashlib
import json
import os
import re

import ai_config
import datasync
import dateien

PX_SPALTE = 10
PX_ZEILE = 20
ENDUNG = ".canvas"
TEXT_GRENZE = 20000
KOORD_GRENZE = 1_000_000
_NAME = re.compile(r"^[\w äöüÄÖÜß.,()+\-]{1,60}$")
_KENNUNG = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
# Zusatzfeld einer Kachel im text-Knoten: {v, app, art, ref} (hub_bauplan.md
# „Kacheln", entschieden 2026-10-09). App-Namen: fokus (Listen), graph,
# kalender. Dieses Modul legt keine Kacheln an und ändert sie nie.
KACHEL = "zentrale_kachel"
# Bild-Knoten (2026-10-10). Endungen, die Pillow liest UND Obsidian zeigt.
BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
TITEL = "zentrale_titel"
BILDMODUS = "zentrale_bildmodus"
BILDMODI = ("mono", "farbe")
SEITEN = ("top", "right", "bottom", "left")


class DeskFehler(ValueError):
    """Eingabe oder Datei taugt nicht. `code` sagt der Route den HTTP-Status."""

    def __init__(self, text, code=400):
        super().__init__(text)
        self.code = code


class DeskKonflikt(DeskFehler):
    """Die Datei wurde seit dem Laden woanders geändert (anderer Rechner,
    Obsidian). Nichts geschrieben; `stand` ist der jetzige."""

    def __init__(self, stand):
        super().__init__("desk wurde inzwischen woanders geändert", 409)
        self.stand = stand


def ordner() -> str:
    eigen = ai_config.setting("desk_ordner")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "desk"))


def name_pruefen(name) -> str:
    """Desk-Name → derselbe, getrimmt; sonst DeskFehler. Kein Schrägstrich,
    kein Punkt vorn: der Name ist zugleich der Dateiname."""
    n = str(name or "").strip()
    if not n or n.startswith(".") or not _NAME.match(n):
        raise DeskFehler("name ungültig (buchstaben, ziffern, leerzeichen, - _ . bis 60 zeichen)")
    return n


def _pfad(name) -> str:
    return os.path.join(ordner(), name_pruefen(name) + ENDUNG)


def _stand(roh: bytes) -> str:
    return hashlib.sha256(roh).hexdigest()[:16] if roh else ""


def _datei_lesen(pfad):
    """-> (daten, stand). Fehlt sie: DeskFehler 404. Kaputt: 422 — eine
    kaputte Datei wird nie überschrieben (vielleicht hat Sasha sie gerade
    in der Hand)."""
    try:
        with open(pfad, "rb") as f:
            roh = f.read()
    except FileNotFoundError:
        raise DeskFehler("desk gibt es nicht", 404)
    try:
        daten = json.loads(roh.decode("utf-8")) if roh.strip() else {}
    except (ValueError, UnicodeDecodeError):
        raise DeskFehler("desk-datei ist kein gültiges JSON — bitte von hand ansehen", 422)
    if not isinstance(daten, dict):
        raise DeskFehler("desk-datei hat nicht die form von JSON Canvas", 422)
    for k in ("nodes", "edges"):
        if not isinstance(daten.get(k, []), list):
            raise DeskFehler("desk-datei: %s ist keine liste" % k, 422)
    return daten, _stand(roh)


# ── Umrechnung Datei ↔ Zellen ─────────────────────────────────────────

def _zahl(x, vorgabe=0):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x != x:
        return vorgabe
    return x


def _zellen(knoten) -> dict:
    """Lage eines Knotens in Zellen (Breite/Höhe mindestens 3 — kleiner kann
    die TUI keinen Rahmen mit Inhalt zeichnen)."""
    return {"x": round(_zahl(knoten.get("x")) / PX_SPALTE),
            "y": round(_zahl(knoten.get("y")) / PX_ZEILE),
            "w": max(3, round(_zahl(knoten.get("width"), 250) / PX_SPALTE)),
            "h": max(3, round(_zahl(knoten.get("height"), 60) / PX_ZEILE))}


def _element(knoten) -> dict | None:
    kid = knoten.get("id")
    if not isinstance(kid, str) or not kid:
        return None
    el = {"id": kid, **_zellen(knoten)}
    kachel = knoten.get(KACHEL)
    if isinstance(kachel, dict):
        # Kachel einer anderen App (hub_bauplan.md „Kacheln"): ein Verweis,
        # hier nur durchgereicht. `text` ist Rückfall für Obsidian, nie
        # bearbeitet; die TUI zeigt ihn, bis eine Kachel-Art ihn ersetzt.
        el["art"] = "kachel"
        el["kachel"] = dict(kachel)
        el["typ"] = "kachel · %s/%s" % (kachel.get("app", "?"), kachel.get("art", "?"))
        el["titel"] = str(knoten.get("text") or "")
    elif knoten.get("type") == "text":
        el["art"] = "notiz"
        el["text"] = str(knoten.get("text") or "")
    elif knoten.get("type") == "file" and ist_bild(knoten.get("file")):
        el["art"] = "bild"
        el["datei"] = knoten["file"]
        el["titel"] = str(knoten.get(TITEL) or "")
        el["modus"] = knoten.get(BILDMODUS) if knoten.get(BILDMODUS) in BILDMODI else "mono"
    else:
        typ = str(knoten.get("type") or "?")
        el["art"] = "fremd"
        el["typ"] = typ
        el["titel"] = str(knoten.get("label") or knoten.get("file")
                          or knoten.get("url") or typ)
    return el


def ist_bild(datei) -> bool:
    return isinstance(datei, str) and datei.lower().endswith(BILD_ENDUNGEN)


def datei_pruefen(datei) -> str:
    """Pfad eines Bildes, relativ zum Desk-Ordner, ohne Weg hinaus."""
    d = str(datei or "").replace("\\", "/").strip()
    teile = d.split("/")
    if not d or d.startswith("/") or any(t in ("", ".", "..") for t in teile) \
            or not ist_bild(d) or len(d) > 300:
        raise DeskFehler("bild-datei ungültig")
    return d


def _bild_felder(k, el):
    """Titel und Modus eines Bildes aus der TUI in den Knoten (nur, was
    sie mitschickt; leerer Titel = wieder der Dateiname)."""
    if "titel" in el:
        titel = el["titel"]
        if not isinstance(titel, str) or len(titel) > 200:
            raise DeskFehler("titel zu lang oder kein text")
        titel = " ".join(titel.split())
        if titel:
            k[TITEL] = titel
        else:
            k.pop(TITEL, None)
    if "modus" in el:
        if el["modus"] not in BILDMODI:
            raise DeskFehler("modus: mono oder farbe")
        if el["modus"] == "mono":
            k.pop(BILDMODUS, None)
        else:
            k[BILDMODUS] = el["modus"]


def _verbindung(kante, ids) -> dict | None:
    v = {"id": kante.get("id"), "von": kante.get("fromNode"), "nach": kante.get("toNode")}
    if not all(isinstance(v[k], str) and v[k] for k in v):
        return None
    if v["von"] not in ids or v["nach"] not in ids:
        return None                      # Schnur zu einem Knoten, den es nicht mehr gibt
    if isinstance(kante.get("label"), str) and kante["label"]:
        v["label"] = kante["label"]
    return v


def _als_desk(name, daten, stand) -> dict:
    elemente = [e for e in (_element(k) for k in daten.get("nodes", [])
                            if isinstance(k, dict)) if e]
    ids = {e["id"] for e in elemente}
    verbindungen = [v for v in (_verbindung(k, ids) for k in daten.get("edges", [])
                                if isinstance(k, dict)) if v]
    return {"name": name, "elemente": elemente, "verbindungen": verbindungen, "stand": stand}


# ── Öffentlich ────────────────────────────────────────────────────────

def liste() -> list:
    """Alle Desks, zuletzt geändert zuerst: [{name, elemente, geaendert}]."""
    o = ordner()
    raus = []
    try:
        namen = os.listdir(o)
    except FileNotFoundError:
        return []
    for f in namen:
        if not f.endswith(ENDUNG) or f.startswith("."):
            continue
        name = f[:-len(ENDUNG)]
        try:
            name_pruefen(name)
            daten, _ = _datei_lesen(os.path.join(o, f))
            n = len(daten.get("nodes", []))
        except DeskFehler:
            n = None                     # kaputt: trotzdem zeigen, Öffnen sagt warum
        raus.append({"name": name, "elemente": n,
                     "geaendert": os.path.getmtime(os.path.join(o, f))})
    raus.sort(key=lambda d: -d["geaendert"])
    return raus


def laden(name) -> dict:
    """Ein Desk in Zellen: {name, elemente, verbindungen, stand}."""
    name = name_pruefen(name)
    daten, stand = _datei_lesen(_pfad(name))
    return _als_desk(name, daten, stand)


def anlegen(name) -> dict:
    """Leeren Desk anlegen. Gibt es ihn schon: DeskFehler 409."""
    pfad = _pfad(name)
    if os.path.exists(pfad):
        raise DeskFehler("desk gibt es schon", 409)
    dateien.json_schreiben(pfad, {"nodes": [], "edges": []})
    datasync.notify_change(pfad)
    return laden(name)


def _ganz(x, unten=-KOORD_GRENZE, oben=KOORD_GRENZE):
    if isinstance(x, bool) or not isinstance(x, int):
        raise DeskFehler("lage muss eine ganze zahl sein")
    if not unten <= x <= oben:
        raise DeskFehler("lage außerhalb des desks")
    return x


def _knoten_aus(el, alt) -> dict:
    """Ein Element der TUI → Knoten der Datei, auf dem alten aufgebaut."""
    if not isinstance(el, dict) or not isinstance(el.get("id"), str) \
            or not _KENNUNG.match(el["id"]):
        raise DeskFehler("element ohne gültige id")
    lage = {"x": _ganz(el.get("x")), "y": _ganz(el.get("y")),
            "w": _ganz(el.get("w"), 3, 2000), "h": _ganz(el.get("h"), 3, 2000)}
    if alt is None:
        if el.get("art") == "bild":
            k = {"id": el["id"], "type": "file", "file": datei_pruefen(el.get("datei"))}
        elif el.get("art") == "notiz":
            k = {"id": el["id"], "type": "text", "text": ""}
        else:
            raise DeskFehler("neu anlegen geht nur mit notizen und bildern")
        alte_lage = None
    else:
        k = dict(alt)
        alte_lage = _zellen(alt)
    if lage != alte_lage:
        k.update(x=lage["x"] * PX_SPALTE, y=lage["y"] * PX_ZEILE,
                 width=lage["w"] * PX_SPALTE, height=lage["h"] * PX_ZEILE)
    if k.get("type") == "text" and KACHEL not in k:
        text = el.get("text", k.get("text", ""))
        if not isinstance(text, str) or len(text) > TEXT_GRENZE:
            raise DeskFehler("notiz-text zu lang oder kein text")
        k["text"] = text
    if k.get("type") == "file" and ist_bild(k.get("file")):
        _bild_felder(k, el)
    return k


def _kante_aus(v, alt, ids) -> dict | None:
    if not isinstance(v, dict) or not isinstance(v.get("id"), str) \
            or not _KENNUNG.match(v["id"]):
        raise DeskFehler("verbindung ohne gültige id")
    von, nach = v.get("von"), v.get("nach")
    if von not in ids or nach not in ids or von == nach:
        return None                      # Ende weg (gelöscht): Schnur fällt mit
    k = dict(alt) if alt else {"id": v["id"]}
    k["fromNode"], k["toNode"] = von, nach
    for feld, datei_feld in (("von_seite", "fromSide"), ("nach_seite", "toSide")):
        if v.get(feld) in SEITEN:
            k[datei_feld] = v[feld]
    if isinstance(v.get("label"), str):
        if v["label"]:
            k["label"] = v["label"][:200]
        else:
            k.pop("label", None)
    return k


def speichern(name, elemente, verbindungen=None, stand=None) -> dict:
    """Den ganzen Desk aus der TUI schreiben (atomar). Elemente, die fehlen,
    sind gelöscht — mit ihren Schnüren. `stand` (vom Laden) schützt vor dem
    Überschreiben einer Änderung von woanders: passt er nicht, DeskKonflikt.
    verbindungen=None lässt die Schnüre der Datei, wie sie sind."""
    name = name_pruefen(name)
    pfad = _pfad(name)
    daten, jetzt = _datei_lesen(pfad)
    if stand is not None and stand != jetzt:
        raise DeskKonflikt(jetzt)
    if not isinstance(elemente, list):
        raise DeskFehler("elemente fehlen")
    alte_knoten = {k.get("id"): k for k in daten.get("nodes", []) if isinstance(k, dict)}
    knoten, ids = [], set()
    for el in elemente:
        k = _knoten_aus(el, alte_knoten.get(el.get("id") if isinstance(el, dict) else None))
        if k["id"] in ids:
            raise DeskFehler("id doppelt: " + k["id"])
        ids.add(k["id"])
        knoten.append(k)
    alte_kanten = {k.get("id"): k for k in daten.get("edges", []) if isinstance(k, dict)}
    if verbindungen is None:
        kanten = [k for k in alte_kanten.values()
                  if k.get("fromNode") in ids and k.get("toNode") in ids]
    else:
        if not isinstance(verbindungen, list):
            raise DeskFehler("verbindungen müssen eine liste sein")
        kanten, kids = [], set()
        for v in verbindungen:
            k = _kante_aus(v, alte_kanten.get(v.get("id") if isinstance(v, dict) else None), ids)
            if k and k["id"] not in kids:
                kids.add(k["id"])
                kanten.append(k)
    daten = dict(daten, nodes=knoten, edges=kanten)
    dateien.json_schreiben(pfad, daten)
    datasync.notify_change(pfad)
    return laden(name)
