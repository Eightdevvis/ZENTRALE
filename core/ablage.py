# core/ablage.py
#
# Die Ablage: Dokumente, die die KI für Sasha erzeugt (Text, Listen, Pläne,
# Code, Tabellen), Dateien aus einem Sandbox-Lauf und Anhänge, die Sasha in
# den Chat gibt. Claude-Webs „Artefakte" in Terminal-Form.
#
# 2026-10-07, Claude-Web-Plan Phase 5. Ausführlich: memory/ki/ablage.md.
#
# ── Wie es auf der Platte liegt ────────────────────────────────────────
#   data/ablage/<id>/kopf.json               Titel, Art, erstellt, Gespräch,
#                                            Herkunft, archiviert
#   data/ablage/<id>/v<n>-<knoten><endung>    eine Fassung, nie überschrieben
#
# Neue Fassung = neue Datei. Der Rechnername steht im Namen, weil der Sync
# „neueste Datei gewinnt" kennt: legten PC und Laptop gleichzeitig eine
# zweite Fassung an, hießen beide sonst v2.md und eine wäre weg. So liegen
# beide da; gezählt wird nach (n, Zeit). Nichts wird gelöscht — der Sync ist
# additiv, ein gelöschtes Dokument käme vom anderen Rechner zurück —, nur
# archiviert (Flag im Kopf). Der Kopf ist klein; dass zwei Rechner ihn
# schreiben (archivieren), ist harmlos.
#
# data/ablage/ synct gewollt: Sasha will alles überall (Entscheidung 07.10.).
# Umlenkbar per Einstellung ablage_dir (Env ZENTRALE_ABLAGE_DIR; Tests).
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

import ai_config
import datasync
import dateien

# Was es gibt und welche Endung es bekommt. code: Endung nach Sprache.
# html: der Morgenblick (core/morgenblick.py, 2026-10-08) — eine fertige Seite,
# die GET /api/ablage/<id>/roh unter strenger CSP ausliefert. Die KI legt
# selbst keine html-Dokumente an (create_document kennt die Art nicht).
# pdf, docx: fertige Dateien (Skills pdf und word, 2026-10-08) — wie Bilder
# Bytes, keine neue Fassung (eine geänderte Datei ist ein neues Dokument,
# das Original bleibt daneben liegen).
ARTEN = ("markdown", "text", "code", "csv", "bild", "html", "pdf", "docx")
BINAER = ("bild", "pdf", "docx")
HERKUENFTE = ("ki", "sandbox", "anhang", "morgenblick")

_ENDUNG = {"markdown": ".md", "text": ".txt", "csv": ".csv", "html": ".html",
           "pdf": ".pdf", "docx": ".docx"}
DATEI_MIME = {"pdf": "application/pdf",
              "docx": "application/vnd.openxmlformats-officedocument."
                      "wordprocessingml.document"}
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
BILD_MAX_BYTES = 5 * 1024 * 1024
DATEI_MAX_BYTES = 30 * 1024 * 1024       # pdf, docx
TITEL_MAX = 120

_ID_MUSTER = re.compile(r"^[a-z0-9][a-z0-9\-]{0,80}$")
_FASSUNG_MUSTER = re.compile(r"^v(\d+)-([A-Za-z0-9@.\-_]+?)(\.[A-Za-z0-9]+)$")

_lock = threading.Lock()


class Fehler(ValueError):
    """Etwas, das so nicht in die Ablage darf — der Text ist für Menschen."""


class Unbekannt(KeyError):
    """Kein Dokument mit dieser id."""


# ── Wo ──────────────────────────────────────────────────────────────────

def ordner() -> str:
    eigen = ai_config.setting("ablage_dir")
    if eigen:
        return os.path.abspath(os.path.expanduser(str(eigen)))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                        "data", "ablage"))


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
    return n


def _pruefen_inhalt(art, inhalt):
    if art in ("pdf", "docx"):
        if not isinstance(inhalt, (bytes, bytearray)) or not inhalt:
            raise Fehler("Eine Datei braucht Bytes.")
        if len(inhalt) > DATEI_MAX_BYTES:
            raise Fehler(f"Datei zu groß (höchstens {DATEI_MAX_BYTES // 1024 // 1024} MB).")
        kopf = bytes(inhalt[:1024])
        if (art == "pdf" and b"%PDF-" not in kopf) or (art == "docx" and kopf[:4] != b"PK\x03\x04"):
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
    if len(inhalt) > TEXT_MAX_ZEICHEN:
        raise Fehler(f"Zu lang: {len(inhalt)} Zeichen, höchstens {TEXT_MAX_ZEICHEN}.")
    return inhalt


# ── Öffentlich ─────────────────────────────────────────────────────────

def anlegen(titel, inhalt, art="markdown", *, herkunft="ki", gespraech=None,
            sprache=None, endung=None, quelle=None) -> dict:
    """Ein neues Dokument mit Fassung 1. -> kopf (mit id).

    endung: nur für Bilder/Anhänge (sonst aus art/sprache). quelle: woher es
    kam (Dateiname eines Anhangs, Lauf + Datei aus der Sandbox) — nur zur
    Anzeige, nie ein Pfad, der später geöffnet wird."""
    if art not in ARTEN:
        raise Fehler(f"Unbekannte Art {art!r} (geht: {', '.join(ARTEN)}).")
    if herkunft not in HERKUENFTE:
        raise Fehler(f"Unbekannte Herkunft {herkunft!r}.")
    titel = " ".join(str(titel or "").split())[:TITEL_MAX] or "Ohne Titel"
    inhalt = _pruefen_inhalt(art, inhalt)
    if art == "bild":
        endung = (endung or "").lower()
        if endung not in BILD_ENDUNGEN:
            raise Fehler("Bilder gehen als png, jpg, webp oder gif.")
    elif art in ("pdf", "docx"):
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
         "gespraech": gespraech, "herkunft": herkunft, "archiviert": False}
    if sprache and art == "code":
        k["sprache"] = str(sprache)[:30]
    if quelle:
        k["quelle"] = str(quelle)[:200]
    dateien.json_schreiben(os.path.join(ordner(), doc_id, "kopf.json"), k)
    _fassung_schreiben(doc_id, inhalt, endung)
    return kopf(doc_id)


def neue_fassung(doc_id, inhalt) -> dict:
    """Neue Fassung (Text-Dokumente). Die alte bleibt liegen. -> kopf"""
    k = kopf(doc_id)
    if k.get("art") == "bild":
        raise Fehler("Ein Bild bekommt keine neue Fassung — lege ein neues an.")
    if k.get("art") in ("pdf", "docx"):
        raise Fehler("Eine PDF- oder Word-Datei bekommt keine neue Fassung — "
                     "eine geänderte Kopie ist ein neues Dokument.")
    inhalt = _pruefen_inhalt(k.get("art"), inhalt)
    _fassung_schreiben(doc_id, inhalt, k.get("endung") or endung_fuer(
        k.get("art"), k.get("sprache")))
    return kopf(doc_id)


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
    k = _kopf_lesen(doc_id)
    k["archiviert"] = bool(an)
    dateien.json_schreiben(os.path.join(_doc_ordner(doc_id), "kopf.json"), k)
    datasync.notify_change()
    return kopf(doc_id)


def liste(archivierte=False) -> list:
    """Alle Dokumente, neueste Änderung zuerst. archivierte=True: nur die
    archivierten."""
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
        if bool(k.get("archiviert")) != bool(archivierte):
            continue
        raus.append(k)
    raus.sort(key=lambda k: str(k.get("geaendert") or ""), reverse=True)
    return raus


def kurz(k: dict) -> dict:
    """Das, was die TUI und das Event brauchen."""
    return {"id": k["id"], "titel": k.get("titel"), "art": k.get("art"),
            "fassung": k.get("fassung", 1)}
