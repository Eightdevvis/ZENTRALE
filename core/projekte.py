# core/projekte.py
#
# Projekte: ein Rahmen für ein Thema — wie die Projekte in Claude Web.
# Ein Projekt hat Anweisungen (wie Sasha in diesem Thema arbeiten will) und
# Wissensdateien (Texte, die die KI darin nachlesen kann). Ein Gespräch
# gehört optional zu einem Projekt (gespraeche: kopf.json → "projekt").
#
# 2026-10-07, Phase 6 des Claude-Web-Plans (memory/ki/claude_web_plan.md,
# Ebene „Projekt"). Ausführlich: memory/ki/projekte.md.
#
# ── Die Ordner ─────────────────────────────────────────────────────────
#   data/gedaechtnis/projekte/<id>/projekt.json    {name, erstellt, archiviert}
#   data/gedaechtnis/projekte/<id>/anweisungen.md  Sashas Anweisungen
#   data/gedaechtnis/projekte/<id>/wissen/<datei>  Wissen als Text
#
# Unter der Gedächtnis-Wurzel, damit dieselbe Test-Umlenkung
# (ZENTRALE_GEDAECHTNIS_DIR) und derselbe Sync greifen. Bewusst NICHT in
# gedaechtnis.BEREICHE (wie skills/): write_note erreichte sonst die
# Anweisungen ungefragt, und kopf_block schriebe die Projekt-Ordner als
# Titel in den Kopf jedes Gesprächs.
#
# ── Was in den Prompt geht ─────────────────────────────────────────────
# prompt_block(id): Name, Anweisungen (gekappt) und die LISTE der Wissens-
# dateien (Name + Größe) — im festen, gecachten Teil (cloud._static_system),
# nur bei einem Gespräch, das zu einem Projekt gehört. Der Block ändert sich
# nur, wenn Sasha am Projekt etwas ändert; der Cache gilt also pro Projekt.
# Den Inhalt einer Wissensdatei holt das Modell mit read_project_file —
# Werkzeug-Ergebnis, wandert mit dem Verlauf, bricht den Cache nicht.
#
# Nie löschen (der Sync ist additiv, ein Gelöschtes käme zurück): Projekte
# werden archiviert, alte Fassungen liegen als .bak daneben.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import hashlib
import json
import os
from datetime import datetime, timezone

import context
import datasync
import dateien
import gedaechtnis

# Grenzen. Die Anweisungen stehen bei JEDEM Zug im Kopf — gekappt; die Datei
# selbst darf länger sein (die KI liest den Rest per read_project_file).
MAX_PROMPT_ANWEISUNGEN = 4_000
MAX_ANWEISUNGEN = 20_000          # wie eine Kernakte
MAX_WISSEN = 200_000              # Zeichen je Wissensdatei
MAX_WISSEN_BYTES = 2_000_000      # Datei von der Platte, vor dem Lesen
MAX_LESEN = 20_000                # Zeichen je read_project_file-Aufruf
MAX_LISTE_PROMPT = 40             # Wissensdateien, die im Kopf genannt werden

# Dateiendungen, die als Text übernommen werden. Was nicht Text ist (PDF,
# Bilder), nimmt das Projekt nicht an — Text lesen kann jedes Modell.
TEXT_ENDUNGEN = (".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".toml",
                 ".py", ".js", ".ts", ".html", ".css", ".sh", ".ini", ".cfg",
                 ".tex", ".rst", ".org", ".xml", ".log", "")

# Wörter, die in /projekt selbst etwas bedeuten — kein Projekt darf so heißen.
RESERVIERT = ("neu", "aus", "kein", "keins", "keines", "zuordnen")

ANWEISUNGEN = "anweisungen"


class Unbekannt(KeyError):
    """Kein Projekt (oder keine Wissensdatei) mit diesem Namen."""


class Ungueltig(ValueError):
    """Eingabe passt nicht (leer, zu lang, gesperrt, keine Textdatei …)."""


# ── Ordner und Kopf ────────────────────────────────────────────────────

def ordner() -> str:
    return gedaechtnis.bereich_ordner(gedaechtnis.PROJEKTE)


def _ordner(pid) -> str:
    return os.path.join(ordner(), pid)


def _gueltig(pid) -> bool:
    # Eine id ist immer ein slug — damit kann keine id aus dem Ordner führen.
    return isinstance(pid, str) and bool(pid) and gedaechtnis.slug(pid) == pid


def gibt_es(pid) -> bool:
    return _gueltig(pid) and os.path.isfile(os.path.join(_ordner(pid), "projekt.json"))


def _pruefen(pid):
    if not gibt_es(pid):
        raise Unbekannt(pid)


def _kopf_lesen(pid) -> dict:
    try:
        with open(os.path.join(_ordner(pid), "projekt.json"), encoding="utf-8") as f:
            k = json.load(f)
        return k if isinstance(k, dict) else {}
    except (OSError, ValueError):
        return {}


def _kopf_schreiben(pid, kopf):
    pfad = os.path.join(_ordner(pid), "projekt.json")
    dateien.json_schreiben(pfad, kopf)
    datasync.notify_change(pfad)


def stand(text: str) -> str:
    """Fingerabdruck einer Fassung (wie gedaechtnis.kernakte_stand): die TUI
    schickt ihn beim Speichern mit, damit eine Änderung vom anderen Rechner
    nicht still überschrieben wird."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


# ── Anlegen, Liste, Laden, Archivieren ─────────────────────────────────

def anlegen(name: str, anweisungen: str = "") -> dict:
    """Ein neues Projekt. → wie laden(). Wirft Ungueltig (leer, reserviert,
    gibt es schon)."""
    name = " ".join(str(name or "").split())[:80]
    pid = gedaechtnis.slug(name)
    if not pid:
        raise Ungueltig("Das Projekt braucht einen Namen.")
    if pid in RESERVIERT:
        raise Ungueltig(f"„{name}“ geht nicht als Projektname — such dir einen anderen.")
    if os.path.exists(_ordner(pid)):
        raise Ungueltig(f"Ein Projekt „{name}“ gibt es schon.")
    os.makedirs(os.path.join(_ordner(pid), "wissen"), exist_ok=True)
    _kopf_schreiben(pid, {"name": name, "archiviert": False,
                          "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    if (anweisungen or "").strip():
        anweisungen_schreiben(pid, anweisungen)
    return laden(pid)


def name(pid) -> str:
    """Der Name, den Sasha sieht (sonst die id)."""
    return (_kopf_lesen(pid).get("name") or pid) if gibt_es(pid) else ""


def liste(archivierte: bool = False) -> list:
    """Alle Projekte, nach Name: [{id, name, erstellt, archiviert, wissen}].
    archivierte=False: nur die offenen; True: nur die archivierten."""
    try:
        namen = sorted(os.listdir(ordner()))
    except OSError:
        return []
    raus = []
    for pid in namen:
        if not gibt_es(pid):
            continue
        k = _kopf_lesen(pid)
        if bool(k.get("archiviert")) != bool(archivierte):
            continue
        raus.append({"id": pid, "name": k.get("name") or pid,
                     "erstellt": k.get("erstellt"),
                     "archiviert": bool(k.get("archiviert")),
                     "wissen": len(wissen_liste(pid))})
    raus.sort(key=lambda p: p["name"].lower())
    return raus


def finden(eingabe):
    """Projekt-id zu dem, was Sasha oder die KI tippt: id, Name oder Slug
    des Namens (Groß/klein egal). → id oder None."""
    roh = " ".join(str(eingabe or "").split())
    if not roh:
        return None
    if gibt_es(roh):
        return roh
    schluessel = gedaechtnis.slug(roh)
    if gibt_es(schluessel):
        return schluessel
    for p in liste() + liste(archivierte=True):
        if p["name"].lower() == roh.lower():
            return p["id"]
    return None


def laden(pid) -> dict:
    """Alles zu einem Projekt: {id, name, erstellt, archiviert, anweisungen,
    stand, wissen: [{name, groesse}]}. Wirft Unbekannt."""
    _pruefen(pid)
    k = _kopf_lesen(pid)
    text = anweisungen_lesen(pid)
    return {"id": pid, "name": k.get("name") or pid, "erstellt": k.get("erstellt"),
            "archiviert": bool(k.get("archiviert")), "anweisungen": text,
            "stand": stand(text), "wissen": wissen_liste(pid)}


def archivieren(pid, an: bool = True) -> dict:
    """Archivieren (an=True) oder zurückholen. Gelöscht wird nie. Gespräche
    des Projekts bleiben ihm zugeordnet."""
    _pruefen(pid)
    k = _kopf_lesen(pid)
    k["archiviert"] = bool(an)
    _kopf_schreiben(pid, k)
    return laden(pid)


# ── Anweisungen ───────────────────────────────────────────────────────

def _anweisungen_pfad(pid) -> str:
    return os.path.join(_ordner(pid), ANWEISUNGEN + ".md")


def anweisungen_lesen(pid) -> str:
    _pruefen(pid)
    try:
        with open(_anweisungen_pfad(pid), encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def anweisungen_schreiben(pid, text: str) -> str:
    """Die Anweisungen ganz ersetzen (Sasha von Hand). Atomar, die alte
    Fassung als .bak. → der neue Stand. Wirft Unbekannt, Ungueltig."""
    _pruefen(pid)
    text = str(text or "").replace("\r\n", "\n")
    if len(text) > MAX_ANWEISUNGEN:
        raise Ungueltig(f"Zu lang ({len(text)} Zeichen, höchstens {MAX_ANWEISUNGEN}).")
    pfad = _anweisungen_pfad(pid)
    alt = anweisungen_lesen(pid)
    if alt:
        dateien.atomar_schreiben(pfad + ".bak", alt)
    neu = text.rstrip() + "\n" if text.strip() else ""
    dateien.atomar_schreiben(pfad, neu)
    datasync.notify_change(pfad)
    return stand(neu)


# ── Wissen ────────────────────────────────────────────────────────────

def _wissen_ordner(pid) -> str:
    return os.path.join(_ordner(pid), "wissen")


def wissen_liste(pid) -> list:
    """[{name, groesse}] nach Name; .bak und Zwischendateien fehlen."""
    try:
        namen = sorted(os.listdir(_wissen_ordner(pid)))
    except OSError:
        return []
    raus = []
    for n in namen:
        pfad = os.path.join(_wissen_ordner(pid), n)
        if n.startswith(".") or n.endswith(".bak") or not os.path.isfile(pfad):
            continue
        raus.append({"name": n, "groesse": os.path.getsize(pfad)})
    return raus


def _dateiname(name: str) -> str:
    """Sicherer Dateiname: slug des Stamms + eine Text-Endung (sonst .md).
    Ein Name wie „../../ai_config.json" wird zu „ai-config.json" im
    Wissens-Ordner — aus dem Ordner führt keiner heraus."""
    basis = os.path.basename(str(name or "").strip())
    stamm, endung = os.path.splitext(basis)
    endung = endung.lower()
    if endung not in TEXT_ENDUNGEN:      # „bericht.v2" → „bericht-v2.md"
        stamm, endung = basis, ".md"
    elif not endung:
        endung = ".md"
    schluessel = gedaechtnis.slug(stamm)
    return (schluessel + endung) if schluessel else ""


def wissen_hinzufuegen(pid, name: str, text: str) -> dict:
    """Eine Wissensdatei aus Text. Gibt es den Namen schon, wird ersetzt —
    die alte Fassung bleibt als .bak. → {name, groesse}."""
    _pruefen(pid)
    datei = _dateiname(name)
    if not datei:
        raise Ungueltig("Die Datei braucht einen Namen.")
    text = str(text or "").replace("\r\n", "\n")
    if not text.strip():
        raise Ungueltig("Die Datei ist leer.")
    if len(text) > MAX_WISSEN:
        raise Ungueltig(f"Zu lang ({len(text)} Zeichen, höchstens {MAX_WISSEN}).")
    pfad = os.path.join(_wissen_ordner(pid), datei)
    if os.path.exists(pfad):
        with open(pfad, encoding="utf-8", errors="replace") as f:
            dateien.atomar_schreiben(pfad + ".bak", f.read())
    dateien.atomar_schreiben(pfad, text)
    datasync.notify_change(pfad)
    return {"name": datei, "groesse": os.path.getsize(pfad)}


def wissen_aus_datei(pid, pfad: str, name: str = "", text: str | None = None) -> dict:
    """Eine Datei als Wissen übernehmen. Erst die Sperrliste (Zugangsdaten,
    gesperrte Ordner wie learning/, ZENTRALEs data/ — dieselbe wie für
    Anhänge, context.anhang_gesperrt), dann lesen.

    text: schon gelesener Inhalt (die TUI auf einem anderen Rechner als das
    Backend liest die Datei selbst) — die Sperrliste gilt trotzdem, sie
    prüft den Pfad. Wirft Unbekannt, Ungueltig, FileNotFoundError."""
    _pruefen(pid)
    pfad = os.path.expanduser(str(pfad or "").strip())
    if not pfad:
        raise Ungueltig("Es fehlt der Pfad.")
    # Dieselbe Regel wie für Anhänge (Phase 5): eine Sperrliste, nicht zwei.
    grund = context.anhang_gesperrt(pfad)
    if grund:
        raise Ungueltig(f"Diese Datei nehme ich nicht: {grund}.")
    endung = os.path.splitext(pfad)[1].lower()
    if endung not in TEXT_ENDUNGEN:
        raise Ungueltig("Nur Textdateien (z. B. .md, .txt, .csv) — "
                        f"{endung or 'diese Art'} geht nicht.")
    if text is None:
        if not os.path.isfile(pfad):
            raise FileNotFoundError(pfad)
        if os.path.getsize(pfad) > MAX_WISSEN_BYTES:
            raise Ungueltig("Die Datei ist zu groß.")
        with open(pfad, "rb") as f:
            roh = f.read()
        if b"\x00" in roh[:8192]:
            raise Ungueltig("Das ist keine Textdatei.")
        try:
            text = roh.decode("utf-8")
        except UnicodeDecodeError:
            raise Ungueltig("Das ist keine Textdatei (kein UTF-8).") from None
    return wissen_hinzufuegen(pid, name or os.path.basename(pfad), text)


def wissen_lesen(pid, name: str, ab: int = 0) -> str:
    """Eine Wissensdatei fürs Modell (read_project_file), höchstens MAX_LESEN
    Zeichen ab Stelle `ab`. Gefunden wird NUR über die Liste des Projekts —
    ein Pfad im Namen führt nirgendwo hin. „anweisungen" liefert die
    ungekürzten Anweisungen, wenn es keine Wissensdatei so gibt."""
    _pruefen(pid)
    roh = os.path.basename(str(name or "").strip())
    dateien_liste = [w["name"] for w in wissen_liste(pid)]
    treffer = next((d for d in dateien_liste if d == roh), None)
    if treffer is None:
        stamm = gedaechtnis.slug(os.path.splitext(roh)[0])
        treffer = next((d for d in dateien_liste
                        if gedaechtnis.slug(os.path.splitext(d)[0]) == stamm and stamm), None)
    if treffer is None:
        if gedaechtnis.slug(roh) == ANWEISUNGEN:
            text = anweisungen_lesen(pid)
            treffer = "anweisungen"
        else:
            da = ", ".join(dateien_liste) or "keine"
            return f"[Keine Wissensdatei {name!r} in diesem Projekt. Es gibt: {da}]"
    else:
        with open(os.path.join(_wissen_ordner(pid), treffer), encoding="utf-8",
                  errors="replace") as f:
            text = f.read()
    try:
        ab = max(0, int(ab or 0))
    except (TypeError, ValueError):
        ab = 0
    stueck = text[ab:ab + MAX_LESEN]
    kopf = f"{treffer} ({len(text)} Zeichen)"
    if ab or ab + MAX_LESEN < len(text):
        kopf += f", Zeichen {ab}–{ab + len(stueck)}"
    rest = ""
    if ab + MAX_LESEN < len(text):
        rest = f"\n\n[… weiter mit read_project_file(name, ab={ab + MAX_LESEN})]"
    return f"{kopf}:\n\n{stueck}{rest}"


# ── Prompt ────────────────────────────────────────────────────────────

def _groesse(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{round(n / 1024)} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def prompt_block(pid) -> str:
    """Der Projekt-Block für den FESTEN Teil des Cloud-Prompts.

    Byte-stabil, solange sich am Projekt nichts ändert: kein Datum, keine
    Uhrzeit, Dateien nach Name sortiert. Unbekanntes Projekt → ""."""
    if not gibt_es(pid):
        return ""
    k = _kopf_lesen(pid)
    titel = k.get("name") or pid
    anw = anweisungen_lesen(pid).strip()
    teile = [f"## Projekt: {titel}",
             "Dieses Gespräch gehört zu Sashas Projekt. Seine Anweisungen dafür "
             "gelten hier zusätzlich; die Hausregeln gehen vor."]
    if anw:
        if len(anw) > MAX_PROMPT_ANWEISUNGEN:
            anw = (anw[:MAX_PROMPT_ANWEISUNGEN].rstrip() + "\n[… gekürzt — "
                   "ganz: read_project_file(\"anweisungen\")]")
        teile.append("### Anweisungen\n" + anw)
    wissen = wissen_liste(pid)
    if wissen:
        zeilen = [f"- {w['name']} ({_groesse(w['groesse'])})"
                  for w in wissen[:MAX_LISTE_PROMPT]]
        if len(wissen) > MAX_LISTE_PROMPT:
            zeilen.append(f"- … und {len(wissen) - MAX_LISTE_PROMPT} weitere")
        teile.append("### Wissen\nDateien des Projekts — Inhalt mit "
                     "read_project_file(name), wenn es darum geht:\n"
                     + "\n".join(zeilen))
    return "\n\n".join(teile)
