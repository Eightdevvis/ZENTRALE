# core/anhang.py
#
# Anhänge: Sasha gibt im Chat eine Datei mit (`/anhang <pfad>`), die KI
# bekommt sie mit der nächsten Nachricht. Text, Code, PDF und Word als Text,
# Bilder als Bild — Bilder nur auf der Cloud-Schiene (das lokale qwen sieht
# keine). PDF und Word liegen seit 2026-10-08 als ORIGINAL in der Ablage
# (Skills pdf und word); die KI bekommt ihren Text, mit read_pdf/edit_docx
# kommt sie ans Original.
#
# 2026-10-07, Claude-Web-Plan Phase 5. Ausführlich: memory/ki/ablage.md.
#
# ── Der Weg ────────────────────────────────────────────────────────────
# 1. Die TUI liest die Datei auf IHREM Rechner (der Laptop spricht über den
#    Tunnel mit dem PC-Backend — dort gibt es den Pfad gar nicht) und schickt
#    Pfad + Bytes an POST /api/anhang.
# 2. annehmen(): Sperrliste (context.anhang_gesperrt), Größe, Art erkennen,
#    PDF/Word einmal zu Text (core/ablage_text.py — prüft, ob es lesbar ist),
#    als Kopie in die Ablage mit Herkunft „anhang". Zurück kommt die id.
# 3. Die nächste Chat-Nachricht trägt die ids; im Gespräch steht nur der
#    VERWEIS ({id, titel, art}), nie der Inhalt und nie ein Bild als base64.
# 4. verlauf_einsetzen() setzt beim Bauen des Verlaufs für die KI den Inhalt
#    ein — für die Cloud als eigener Block (die Adapter in cloud.py und
#    cloud_openai.py formen daraus Text- und Bild-Blöcke), lokal als Text.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import base64
import os

import ablage
import ablage_text
import context

# Grenzen (2026-10-07).
DATEI_MAX_BYTES = 10 * 1024 * 1024     # was die TUI überhaupt schicken darf
# So viel Text eines Anhangs geht an die KI. Die Cloud bekommt ihn bei jedem
# Zug wieder (wie in Claude Web; bei Anthropic gecacht, also billig); lokal
# weniger, das 9B hat ein kleines Fenster.
TEXT_MAX_CLOUD = 30_000
TEXT_MAX_LOKAL = 8_000

_TEXT_ENDUNGEN = {".md": "markdown", ".markdown": "markdown", ".csv": "csv",
                  ".txt": "text", ".log": "text"}


class Abgelehnt(ValueError):
    """Geht nicht als Anhang — der Text ist für Sasha (Statuszeile)."""


def _art_fuer(name: str, daten: bytes) -> tuple:
    """(art, endung, text|None) — Bild, PDF/Word (Original + Text) oder
    Text/Code."""
    endung = os.path.splitext(name)[1].lower()
    if endung in ablage.BILD_ENDUNGEN or daten[:8] == b"\x89PNG\r\n\x1a\n" \
            or daten[:3] == b"\xff\xd8\xff" or (daten[:4] == b"RIFF" and daten[8:12] == b"WEBP"):
        echt = (".png" if daten[:8] == b"\x89PNG\r\n\x1a\n" else
                ".jpg" if daten[:3] == b"\xff\xd8\xff" else
                ".webp" if daten[:4] == b"RIFF" and daten[8:12] == b"WEBP" else
                ".gif" if daten[:6] in (b"GIF87a", b"GIF89a") else None)
        if echt is None:
            raise Abgelehnt("das ist kein Bild, das ich lesen kann (png, jpg, webp, gif)")
        return "bild", echt, None
    datei_art = ablage_text.art_von(daten)
    if datei_art:
        erg = ablage_text.aus_bytes(datei_art, daten)
        if erg["fehler"]:
            raise Abgelehnt(erg["fehler"])
        return datei_art, "." + datei_art, erg["text"]
    if daten[:4] == b"\xd0\xcf\x11\xe0":
        raise Abgelehnt("alte Word-Datei (.doc) oder mit Passwort — bitte als .docx "
                        "ohne Passwort speichern")
    if b"\x00" in daten[:8192]:
        raise Abgelehnt("diese Art Datei kann ich nicht lesen — nur Text, Code, PDF, "
                        "Word (.docx) und Bilder")
    try:
        text = daten.decode("utf-8")
    except UnicodeDecodeError:
        text = daten.decode("latin-1")       # alte Textdateien, nie Binäres (s. o.)
    if endung in _TEXT_ENDUNGEN:
        return _TEXT_ENDUNGEN[endung], endung, text
    return "code" if endung else "text", endung or ".txt", text


def annehmen(pfad: str, daten: bytes, *, gespraech=None, cloud=True) -> dict:
    """Eine Datei als Anhang annehmen. -> {id, titel, art, zeichen, gekappt,
    hinweis}. Wirft Abgelehnt (Klartext).

    pfad: wie die TUI ihn aufgelöst hat (nur zur Prüfung und als Titel; das
    Backend öffnet ihn nie — die Bytes kommen mit). cloud: denkt gerade die
    Cloud? Sonst bekommt ein Bild gleich den Hinweis."""
    grund = context.anhang_gesperrt(pfad)
    if grund:
        raise Abgelehnt(grund)
    if not daten:
        raise Abgelehnt("die Datei ist leer")
    if len(daten) > DATEI_MAX_BYTES:
        raise Abgelehnt(f"zu groß — höchstens {DATEI_MAX_BYTES // 1024 // 1024} MB")
    name = os.path.basename(str(pfad).rstrip("/")) or "anhang"
    art, endung, text = _art_fuer(name, daten)
    try:
        if art in ablage.BINAER:
            k = ablage.anlegen(name, daten, art, herkunft="anhang",
                               gespraech=gespraech, endung=endung, quelle=name)
        else:
            k = ablage.anlegen(name, text, art, herkunft="anhang", gespraech=gespraech,
                               endung=endung, quelle=name)
    except ablage.Fehler as e:
        raise Abgelehnt(str(e))
    raus = {"id": k["id"], "titel": k["titel"], "art": art, "zeichen": len(text or ""),
            "gekappt": bool(text and len(text) > TEXT_MAX_CLOUD), "hinweis": ""}
    if art == "bild" and not cloud:
        raus["hinweis"] = "Bilder nur mit Cloud — /cloud schaltet um"
    elif art in ("pdf", "docx") and not (text or "").strip():
        raus["hinweis"] = ("kein Text drin (gescannt?) — die KI kann es nicht lesen, "
                           "nur zusammenfügen")
    elif raus["gekappt"]:
        raus["hinweis"] = (f"lang — die KI sieht die ersten {TEXT_MAX_CLOUD:,} "
                           f"Zeichen").replace(",", ".")
    return raus


def verweise(ids) -> list:
    """Ablage-ids aus einer Chat-Nachricht → [{id, titel, art}] für das
    Gespräch (mit Fassung). Unbekannte → Abgelehnt."""
    raus = []
    for i in ids or []:
        i = str(i)
        if not ablage.gibt_es(i):
            raise Abgelehnt("ein Anhang ist nicht (mehr) da — bitte neu anhängen")
        k = ablage.kopf(i)
        # Die Fassung gehört zum Verweis: ändert die KI das Dokument später,
        # bleibt der Anhang, was Sasha angehängt hat (und der Cache stabil).
        raus.append({"id": i, "titel": k.get("titel"), "art": k.get("art"),
                     "fassung": k.get("fassung") or 1})
    return raus


def hat_bild(verweise_) -> bool:
    return any(v.get("art") == "bild" for v in verweise_ or [])


def _gekappt(text: str, grenze: int) -> str:
    if len(text) <= grenze:
        return text
    return (text[:grenze] + f"\n[… gekürzt: die ersten {grenze} von "
            f"{len(text)} Zeichen — der Rest steht in Sashas Ablage]")


def _aufgeloest(v: dict, cloud: bool) -> dict | None:
    """Ein Verweis → was an die KI geht. Deterministisch aus der Datei
    (gleicher Verweis = gleiche Bytes in jedem Zug, sonst bricht der Cache)."""
    titel = v.get("titel") or v.get("id")
    try:
        if v.get("art") == "bild":
            if not cloud:
                return {"art": "text", "titel": titel,
                        "text": "(ein Bild — sieht nur die Cloud-KI)"}
            mime, roh = ablage.bild_bytes(v["id"])
            return {"art": "bild", "titel": titel, "mime": mime,
                    "daten": base64.b64encode(roh).decode("ascii")}
        if v.get("art") in ("pdf", "docx"):
            erg = ablage_text.text(v["id"], v.get("fassung") or 1)
            text = erg["text"] or (f"(nicht lesbar: {erg['fehler']})" if erg["fehler"]
                                   else "(kein Text drin — vermutlich gescannt)")
            return {"art": "text", "titel": titel,
                    "text": ablage_text.kopfzeile(erg, v["id"]) + "\n" + _gekappt(
                        text, TEXT_MAX_CLOUD if cloud else TEXT_MAX_LOKAL)}
        inhalt = ablage.lesen(v["id"], v.get("fassung") or 1)["inhalt"] or ""
    except (ablage.Unbekannt, OSError):
        return {"art": "text", "titel": titel,
                "text": "(liegt auf diesem Rechner nicht vor)"}
    return {"art": "text", "titel": titel,
            "text": _gekappt(inhalt, TEXT_MAX_CLOUD if cloud else TEXT_MAX_LOKAL)}


def _dokumente_zeile(doks) -> str:
    teile = [f'"{d.get("titel")}" (id {d.get("id")})' for d in doks if d.get("id")]
    return "[In der Ablage: " + ", ".join(teile) + "]" if teile else ""


def verlauf_einsetzen(verlauf: list, cloud: bool) -> list:
    """Den Verlauf für die KI um Anhänge und Ablage-Hinweise ergänzen.

    Nachrichten mit 'anhaenge' (Verweise): Cloud → Schlüssel 'anhaenge' mit
    aufgelösten Einträgen ({art: text, titel, text} | {art: bild, titel, mime,
    daten}); die Adapter machen daraus Blöcke. Lokal → als Text an den Inhalt.
    Antworten mit 'dokumente': ein Satz, welche Dokumente dabei entstanden
    (mit id — sonst kann die KI sie später nicht mehr ändern)."""
    raus = []
    for m in verlauf or []:
        m = dict(m)
        verw = m.pop("anhaenge", None)
        doks = m.pop("dokumente", None)
        if doks:
            zeile = _dokumente_zeile(doks)
            if zeile:
                m["content"] = (m.get("content") or "").rstrip() + "\n\n" + zeile
        if verw:
            teile = [t for t in (_aufgeloest(v, cloud) for v in verw) if t]
            if cloud:
                m["anhaenge"] = teile
            else:
                extra = "\n\n".join(f"[Anhang: {t['titel']}]\n{t['text']}" for t in teile)
                m["content"] = ((m.get("content") or "").rstrip() + "\n\n" + extra).strip()
        raus.append(m)
    return raus
