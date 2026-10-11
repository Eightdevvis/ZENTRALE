# core/ablage.py
#
# Die Ablage: Dokumente, die die KI für Sasha erzeugt (Text, Listen, Pläne,
# Code, Tabellen), Dateien aus einem Sandbox-Lauf und Anhänge, die Sasha in
# den Chat gibt. Claude-Webs „Artefakte" in Terminal-Form.
#
# 2026-10-07, Claude-Web-Plan Phase 5. Ausführlich: memory/ki/ablage.md.
#
# ── Wie es auf der Platte liegt (seit 2026-10-11) ───────────────────────
#   ~/Zentrale/Ablage/<Titel><endung>         die neueste Fassung, lesbar für
#                                            Sasha (core/ablage_sichtbar.py)
#   ~/Zentrale/Ablage/.ablage/dokumente/<id>/kopf.json
#                                            Titel, Art, erstellt, Gespräch,
#                                            Herkunft, archiviert, …
#   ~/Zentrale/Ablage/.ablage/dokumente/<id>/v<n>-<knoten><endung>
#                                            eine Fassung, nie überschrieben
#
# Bis 2026-10-11 lag alles unter data/ablage/<id>/ im Code-Ordner — Sasha:
# „der user soll nich im code fischen gehen müssen". Die Fassungen und Köpfe
# sind dieselben geblieben (nur eine Ebene tiefer, versteckt); die lesbaren
# Dateien obendrauf hält ablage_sichtbar nach (Umzug: scripts/ablage_umzug.py).
#
# Neue Fassung = neue Datei. Der Rechnername steht im Namen, weil der Sync
# „neueste Datei gewinnt" kennt: legten PC und Laptop gleichzeitig eine
# zweite Fassung an, hießen beide sonst v2.md und eine wäre weg. So liegen
# beide da; gezählt wird nach (n, Zeit). Nichts wird gelöscht — der Sync ist
# additiv, ein gelöschtes Dokument käme vom anderen Rechner zurück —, nur
# archiviert (Flag im Kopf). Der Kopf ist klein; dass zwei Rechner ihn
# schreiben (archivieren), ist harmlos.
#
# Papierkorb (2026-10-11, Sasha: „sie muss alte sachen in der ablage
# rauslöschen und ersetzen können"): auch er ist nur ein Feld im Kopf
# („papierkorb": Zeitpunkt) — ausgeblendet aus der Liste, jederzeit zurück.
# Wem ein Dokument gehört, sagt „abgelegt_von" (sasha | ki): die KI räumt
# ihre eigenen ohne Frage weg, Sashas nur nach seinem Ja (das Gate dafür
# steht bei den Werkzeugen, core/werkzeug_ablage.py).
#
# data/ablage/ synct gewollt: Sasha will alles überall (Entscheidung 07.10.).
# Umlenkbar per Einstellung ablage_dir (Env ZENTRALE_ABLAGE_DIR; Tests) —
# sie nennt den sichtbaren Ordner (Standard ~/Zentrale/Ablage).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md): weiß nichts von der KI.
# Die Werkzeuge (create_document …) stehen in ki_werkzeuge, die Anhänge in
# core/anhang.py.

import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone

import ablage_ort
import datasync
import dateien

# Was es gibt und welche Endung es bekommt. code: Endung nach Sprache.
# html: der Morgenblick (core/morgenblick.py, 2026-10-08) — eine fertige Seite,
# die GET /api/ablage/<id>/roh unter strenger CSP ausliefert. Die KI legt
# selbst keine html-Dokumente an (create_document kennt die Art nicht).
# pdf, docx: fertige Dateien (Skills pdf und word, 2026-10-08) — wie Bilder
# Bytes, keine neue Fassung (eine geänderte Datei ist ein neues Dokument,
# das Original bleibt daneben liegen).
# xlsx (2026-10-11, Skill excel): eine Excel-Tabelle, Bytes wie pdf/docx.
ARTEN = ("markdown", "text", "code", "csv", "bild", "html", "pdf", "docx", "xlsx")
BINAER = ("bild", "pdf", "docx", "xlsx")
DATEIEN = ("pdf", "docx", "xlsx")          # fertige Dateien: keine neue Fassung
# einwurf (2026-10-11): was Sasha in den Einwurf-Ordner wirft (core/einwurf.py).
HERKUENFTE = ("ki", "sandbox", "anhang", "morgenblick", "ablauf", "einwurf")
VON = ("sasha", "ki")

_ENDUNG = {"markdown": ".md", "text": ".txt", "csv": ".csv", "html": ".html",
           "pdf": ".pdf", "docx": ".docx", "xlsx": ".xlsx"}
DATEI_MIME = {"pdf": "application/pdf",
              "docx": "application/vnd.openxmlformats-officedocument."
                      "wordprocessingml.document",
              "xlsx": "application/vnd.openxmlformats-officedocument."
                      "spreadsheetml.sheet"}
_CODE_ENDUNG = {
    "python": ".py", "py": ".py", "shell": ".sh", "bash": ".sh", "sh": ".sh",
    "javascript": ".js", "js": ".js", "typescript": ".ts", "ts": ".ts",
    "html": ".html", "css": ".css", "json": ".json", "sql": ".sql",
    "yaml": ".yaml", "yml": ".yaml", "toml": ".toml", "lua": ".lua",
    "c": ".c", "cpp": ".cpp", "rust": ".rs", "go": ".go", "java": ".java",
    "haskell": ".hs", "tidal": ".tidal", "markdown": ".md",
}
BILD_ENDUNGEN = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".gif": "image/gif"}

# Grenzen (2026-10-07). Ein Dokument ist etwas zum Lesen, kein Datengrab:
# 200.000 Zeichen sind ~60 Seiten. Bilder bis 5 MB — mehr nimmt Anthropic
# pro Bild nicht an.
TEXT_MAX_ZEICHEN = 200_000
# Ausnahme: ein Ablauf-Protokoll (/trace, core/zug_ablauf.py, 2026-10-09)
# soll ohne Auslassungen hinein — ein Zug mit vielen Werkzeugen hat bis zu
# 50.000 Zeichen je Schritt. Nur Herkunft „ablauf"; die KI schreibt so nichts.
ABLAUF_MAX_ZEICHEN = 2_000_000
BILD_MAX_BYTES = 5 * 1024 * 1024
DATEI_MAX_BYTES = 30 * 1024 * 1024       # pdf, docx, xlsx
TITEL_MAX = 120

_ID_MUSTER = re.compile(r"^[a-z0-9][a-z0-9\-]{0,80}$")
_FASSUNG_MUSTER = re.compile(r"^v(\d+)-([A-Za-z0-9@.\-_]+?)(\.[A-Za-z0-9]+)$")

_lock = threading.Lock()

VERSTECKT = ablage_ort.VERSTECKT

# Wer nach jedem Schreiben Bescheid bekommt: f(doc_id). Meldet sich selbst an
# (core/ablage_sichtbar.py hält die lesbare Datei nach) — die Ablage
# importiert niemanden über sich (kein Kreis, memory/system/bauplan_kern.md).
NACH_SCHREIBEN: list = []


class Fehler(ValueError):
    """Etwas, das so nicht in die Ablage darf — der Text ist für Menschen."""


class Unbekannt(KeyError):
    """Kein Dokument mit dieser id."""


# ── Wo ──────────────────────────────────────────────────────────────────

def wurzel() -> str:
    """Der Ordner, den Sasha sieht (Einstellung ablage_dir)."""
    return ablage_ort.wurzel()


def ordner() -> str:
    """Wo die Dokumente mit ihren Fassungen liegen (versteckt)."""
    return ablage_ort.dokumente()


def _gemeldet(doc_id) -> None:
    for f in list(NACH_SCHREIBEN):
        try:
            f(doc_id)
        except Exception as e:          # noqa: BLE001 — die Ablage selbst steht
            print(f"[ablage] Nachziehen von {doc_id} ging nicht: {e}")


def _gueltig(doc_id) -> bool:
    return isinstance(doc_id, str) and bool(_ID_MUSTER.match(doc_id))


def _doc_ordner(doc_id) -> str:
    if not _gueltig(doc_id):
        raise Unbekannt(doc_id)
    return os.path.join(ordner(), doc_id)


def gibt_es(doc_id) -> bool:
    return _gueltig(doc_id) and os.path.isfile(
        os.path.join(ordner(), doc_id, "kopf.json"))


def _jetzt() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(titel: str) -> str:
    s = titel.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:30].strip("-") or "dokument"


def endung_fuer(art: str, sprache: str | None = None) -> str:
    if art == "code":
        return _CODE_ENDUNG.get((sprache or "").strip().lower(), ".txt")
    return _ENDUNG.get(art, ".txt")


# ── Kopf und Fassungen ─────────────────────────────────────────────────

def _kopf_lesen(doc_id) -> dict:
    try:
        with open(os.path.join(_doc_ordner(doc_id), "kopf.json"), encoding="utf-8") as f:
            k = json.load(f)
    except (OSError, ValueError):
        raise Unbekannt(doc_id)
    return k if isinstance(k, dict) else {}


def _fassungen(doc_id) -> list:
    """[(n, knoten, endung, pfad, mtime)] nach (n, Zeit) — Position+1 ist
    die Fassungs-Nummer, die Sasha sieht."""
    od = _doc_ordner(doc_id)
    raus = []
    try:
        namen = os.listdir(od)
    except OSError:
        return []
    for name in namen:
        m = _FASSUNG_MUSTER.match(name)
        if not m:
            continue
        pfad = os.path.join(od, name)
        try:
            st = os.lstat(pfad)
        except OSError:
            continue
        if not os.path.isfile(pfad) or os.path.islink(pfad):
            continue
        raus.append((int(m.group(1)), m.group(2), m.group(3), pfad, st.st_mtime))
    raus.sort(key=lambda t: (t[0], t[4], t[1]))
    return raus


def kopf(doc_id) -> dict:
    """Kopf + fassung (Anzahl), geaendert (ISO), endung der neuesten."""
    k = dict(_kopf_lesen(doc_id))
    f = _fassungen(doc_id)
    k["id"] = doc_id
    k["fassung"] = len(f)
    if f:
        # Mikrosekunden: die Liste sortiert danach, zwei Dokumente aus
        # demselben Werkzeug-Zug liegen oft in derselben Sekunde.
        k["geaendert"] = datetime.fromtimestamp(f[-1][4], timezone.utc).isoformat(
            timespec="microseconds")
        k["endung"] = f[-1][2]
    else:
        k["geaendert"] = k.get("erstellt")
    return k


def _fassung_schreiben(doc_id, inhalt, endung) -> int:
    """Nächste Fassung anlegen — nie über eine bestehende."""
    od = _doc_ordner(doc_id)
    with _lock:
        n = max((t[0] for t in _fassungen(doc_id)), default=0) + 1
        knoten = dateien.knoten()
        pfad = os.path.join(od, f"v{n}-{knoten}{endung}")
        while os.path.exists(pfad):          # nie überschreiben
            n += 1
            pfad = os.path.join(od, f"v{n}-{knoten}{endung}")
        dateien.atomar_schreiben(pfad, inhalt)
    datasync.notify_change()
    _gemeldet(doc_id)
    return n


def _pruefen_inhalt(art, inhalt, grenze=TEXT_MAX_ZEICHEN):
    if art in DATEIEN:
        if not isinstance(inhalt, (bytes, bytearray)) or not inhalt:
            raise Fehler("Eine Datei braucht Bytes.")
        if len(inhalt) > DATEI_MAX_BYTES:
            raise Fehler(f"Datei zu groß (höchstens {DATEI_MAX_BYTES // 1024 // 1024} MB).")
        kopf = bytes(inhalt[:1024])
        if (art == "pdf" and b"%PDF-" not in kopf) or \
                (art in ("docx", "xlsx") and kopf[:4] != b"PK\x03\x04"):
            raise Fehler(f"Das ist keine {art.upper()}-Datei.")
        return bytes(inhalt)
    if art == "bild":
        if not isinstance(inhalt, (bytes, bytearray)) or not inhalt:
            raise Fehler("Ein Bild braucht Bytes.")
        if len(inhalt) > BILD_MAX_BYTES:
            raise Fehler(f"Bild zu groß (höchstens {BILD_MAX_BYTES // 1024 // 1024} MB).")
        return bytes(inhalt)
    if isinstance(inhalt, (bytes, bytearray)):
        try:
            inhalt = bytes(inhalt).decode("utf-8")
        except UnicodeDecodeError:
            raise Fehler("Das ist kein Text (kein UTF-8).")
    inhalt = str(inhalt or "")
    if not inhalt.strip():
        raise Fehler("Leerer Inhalt — nichts abgelegt.")
    if len(inhalt) > grenze:
        raise Fehler(f"Zu lang: {len(inhalt)} Zeichen, höchstens {grenze}.")
    return inhalt


# ── Öffentlich ─────────────────────────────────────────────────────────

def anlegen(titel, inhalt, art="markdown", *, herkunft="ki", gespraech=None,
            sprache=None, endung=None, quelle=None, von=None, ersetzt=None) -> dict:
    """Ein neues Dokument mit Fassung 1. -> kopf (mit id).

    endung: nur für Bilder/Anhänge (sonst aus art/sprache). quelle: woher es
    kam (Dateiname eines Anhangs, Lauf + Datei aus der Sandbox) — nur zur
    Anzeige, nie ein Pfad, der später geöffnet wird. von: wem es gehört
    (sasha | ki; Standard: ki nur bei Herkunft ki). ersetzt: id des
    Dokuments, dessen neue Fassung es ist (ersetzen())."""
    if art not in ARTEN:
        raise Fehler(f"Unbekannte Art {art!r} (geht: {', '.join(ARTEN)}).")
    if herkunft not in HERKUENFTE:
        raise Fehler(f"Unbekannte Herkunft {herkunft!r}.")
    von = von or ("ki" if herkunft == "ki" else "sasha")
    if von not in VON:
        raise Fehler(f"Unbekannt, wem es gehört: {von!r}.")
    titel = " ".join(str(titel or "").split())[:TITEL_MAX] or "Ohne Titel"
    inhalt = _pruefen_inhalt(art, inhalt, ABLAUF_MAX_ZEICHEN if herkunft == "ablauf"
                             else TEXT_MAX_ZEICHEN)
    if art == "bild":
        endung = (endung or "").lower()
        if endung not in BILD_ENDUNGEN:
            raise Fehler("Bilder gehen als png, jpg, webp oder gif.")
    elif art in DATEIEN:
        endung = _ENDUNG[art]
    else:
        endung = endung if (endung and re.fullmatch(r"\.[a-z0-9]{1,8}", endung)) \
            else endung_fuer(art, sprache)

    stempel = datetime.now().strftime("%Y%m%d")
    with _lock:
        while True:
            doc_id = f"{stempel}-{_slug(titel)}-{secrets.token_hex(2)}"
            if not os.path.exists(os.path.join(ordner(), doc_id)):
                break
        os.makedirs(os.path.join(ordner(), doc_id), exist_ok=True)
    k = {"id": doc_id, "titel": titel, "art": art, "erstellt": _jetzt(),
         "gespraech": gespraech, "herkunft": herkunft, "archiviert": False,
         "abgelegt_von": von}
    if ersetzt:
        k["ersetzt"] = str(ersetzt)
    if sprache and art == "code":
        k["sprache"] = str(sprache)[:30]
    if quelle:
        k["quelle"] = str(quelle)[:200]
    dateien.json_schreiben(os.path.join(ordner(), doc_id, "kopf.json"), k)
    _fassung_schreiben(doc_id, inhalt, endung)
    return kopf(doc_id)


def alle_ids() -> list:
    try:
        return sorted(n for n in os.listdir(ordner()) if gibt_es(n))
    except OSError:
        return []


def neue_fassung(doc_id, inhalt) -> dict:
    """Neue Fassung (Text-Dokumente). Die alte bleibt liegen. -> kopf"""
    k = kopf(doc_id)
    if k.get("art") == "bild":
        raise Fehler("Ein Bild bekommt keine neue Fassung — lege ein neues an.")
    if k.get("art") in DATEIEN:
        raise Fehler("Eine PDF-, Word- oder Excel-Datei bekommt keine neue Fassung — "
                     "eine geänderte ist ein neues Dokument (ersetzen: das alte kommt "
                     "in den Papierkorb).")
    inhalt = _pruefen_inhalt(k.get("art"), inhalt)
    _fassung_schreiben(doc_id, inhalt, k.get("endung") or endung_fuer(
        k.get("art"), k.get("sprache")))
    return kopf(doc_id)


def fassung_von_sasha(doc_id, inhalt) -> dict:
    """Sasha hat die lesbare Datei selbst geändert (core/ablage_sichtbar.py):
    das wird eine neue Fassung — auch bei PDF/Word/Excel, denn hier
    entscheidet er, nicht die KI. -> kopf"""
    k = kopf(doc_id)
    inhalt = _pruefen_inhalt(k.get("art"), inhalt)
    _fassung_schreiben(doc_id, inhalt, k.get("endung") or endung_fuer(
        k.get("art"), k.get("sprache")))
    return kopf(doc_id)


def _kopf_aendern(doc_id, **felder) -> dict:
    k = _kopf_lesen(doc_id)
    for name, wert in felder.items():
        if wert is None:
            k.pop(name, None)
        else:
            k[name] = wert
    dateien.json_schreiben(os.path.join(_doc_ordner(doc_id), "kopf.json"), k)
    datasync.notify_change()
    _gemeldet(doc_id)
    return kopf(doc_id)


def umbenennen(doc_id, titel) -> dict:
    """Neuer Titel (Sasha hat die Datei umbenannt). -> kopf"""
    titel = " ".join(str(titel or "").split())[:TITEL_MAX]
    if not titel:
        raise Fehler("Ein Titel braucht Text.")
    return _kopf_aendern(doc_id, titel=titel)


def pfad(doc_id, fassung=None) -> str:
    """Pfad einer Fassung (None = neueste). Wirft Unbekannt."""
    f = _fassungen(doc_id)
    if not f:
        raise Unbekannt(doc_id)
    if fassung is None:
        return f[-1][3]
    try:
        n = int(fassung)
    except (TypeError, ValueError):
        raise Unbekannt(f"{doc_id} Fassung {fassung}")
    if not 1 <= n <= len(f):
        raise Unbekannt(f"{doc_id} Fassung {fassung}")
    return f[n - 1][3]


def lesen(doc_id, fassung=None) -> dict:
    """{kopf, fassung, inhalt (Text) | None (Bild, PDF, Word), bytes, mime?}."""
    k = kopf(doc_id)
    p = pfad(doc_id, fassung)
    nr = int(fassung) if fassung is not None else k["fassung"]
    raus = {"kopf": k, "fassung": nr, "bytes": os.path.getsize(p)}
    if k.get("art") == "bild":
        raus["inhalt"] = None
        raus["mime"] = BILD_ENDUNGEN.get(os.path.splitext(p)[1].lower())
    elif k.get("art") in DATEI_MIME:
        raus["inhalt"] = None
        raus["mime"] = DATEI_MIME[k["art"]]
    else:
        with open(p, encoding="utf-8", errors="replace") as f:
            raus["inhalt"] = f.read()
    return raus


def bild_bytes(doc_id) -> tuple:
    """(mime, bytes) der neuesten Fassung eines Bildes. Wirft Unbekannt."""
    p = pfad(doc_id)
    mime = BILD_ENDUNGEN.get(os.path.splitext(p)[1].lower())
    if not mime:
        raise Unbekannt(doc_id)
    with open(p, "rb") as f:
        return mime, f.read()


def roh(doc_id, fassung=None) -> bytes:
    """Die Bytes einer Fassung, egal welcher Art (None = neueste). Wirft
    Unbekannt."""
    with open(pfad(doc_id, fassung), "rb") as f:
        return f.read()


def archivieren(doc_id, an=True) -> dict:
    """Archivieren (oder zurückholen). Gelöscht wird nie."""
    return _kopf_aendern(doc_id, archiviert=bool(an))


def von_sasha(k: dict) -> bool:
    """Gehört das Dokument Sasha? Im Zweifel ja (2026-10-11): ohne Feld
    „abgelegt_von" (alles vor dem 11.10.) gehört nur, was die KI selbst
    angelegt hat (Herkunft ki), der KI — Anhänge, Einwurf, Sandbox (nur auf
    Sashas Wunsch abgelegt), Morgenblick und Trace gehören Sasha."""
    von = k.get("abgelegt_von")
    if von in VON:
        return von == "sasha"
    return k.get("herkunft") != "ki"


def im_papierkorb(k: dict) -> bool:
    return bool(k.get("papierkorb"))


def papierkorb(doc_id, an=True, ersetzt_durch=None, grund=None) -> dict:
    """In den Papierkorb legen (oder zurückholen). Gelöscht wird nie: es ist
    ein Feld im Kopf, wie archiviert. grund: z. B. „von Sasha entfernt"
    (er hat die Datei im Ordner gelöscht). -> kopf"""
    if an:
        return _kopf_aendern(doc_id, papierkorb=_jetzt(),
                             ersetzt_durch=str(ersetzt_durch) if ersetzt_durch else None,
                             papierkorb_grund=grund)
    return _kopf_aendern(doc_id, papierkorb=None, ersetzt_durch=None, papierkorb_grund=None)


def ersetzen(alt_id, inhalt, *, titel=None, art=None, gespraech=None, quelle=None) -> tuple:
    """Die neue Fassung als NEUES Dokument anlegen und das alte in den
    Papierkorb legen — ganz oder gar nicht: scheitert das Anlegen, bleibt
    das alte unberührt; scheitert der Papierkorb, ist das neue wieder weg.
    Das neue gehört der KI (sie hat es gemacht); Titel und Art wie das alte,
    wenn nicht anders gesagt. -> (neu_kopf, alt_kopf). Wirft Unbekannt/Fehler."""
    alt = kopf(alt_id)
    if im_papierkorb(alt):
        raise Fehler("Das Dokument liegt schon im Papierkorb.")
    neu = anlegen(titel or alt.get("titel"), inhalt, art or alt.get("art"), herkunft="ki",
                  gespraech=gespraech, sprache=alt.get("sprache"), quelle=quelle,
                  von="ki", ersetzt=alt_id)
    try:
        alt = papierkorb(alt_id, True, ersetzt_durch=neu["id"])
    except Exception:
        import shutil
        shutil.rmtree(os.path.join(ordner(), neu["id"]), ignore_errors=True)
        raise
    return neu, alt


def liste(archivierte=False, papierkorb=False) -> list:
    """Alle Dokumente, neueste Änderung zuerst. archivierte=True: nur die
    archivierten; papierkorb=True: nur, was im Papierkorb liegt (sonst ist
    er ausgeblendet, 2026-10-11)."""
    try:
        namen = os.listdir(ordner())
    except OSError:
        return []
    raus = []
    for name in namen:
        if not gibt_es(name):
            continue
        try:
            k = kopf(name)
        except Unbekannt:
            continue
        if im_papierkorb(k) != bool(papierkorb):
            continue
        if not papierkorb and bool(k.get("archiviert")) != bool(archivierte):
            continue
        raus.append(k)
    raus.sort(key=lambda k: str(k.get("geaendert") or ""), reverse=True)
    return raus


def kurz(k: dict) -> dict:
    """Das, was die TUI und das Event brauchen."""
    return {"id": k["id"], "titel": k.get("titel"), "art": k.get("art"),
            "fassung": k.get("fassung", 1)}
