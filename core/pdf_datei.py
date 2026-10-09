# core/pdf_datei.py
#
# PDFs lesen (Text je Seite, Tabellen so gut es geht, Formularfelder) und
# zusammenfügen bzw. Seiten herausnehmen. Neue PDFs schreibt
# core/pdf_schreiben.py.
#
# 2026-10-08, Skill pdf (memory/ki/pdf_word.md). Bibliothek: pypdf (BSD,
# reines Python — läuft auch auf dem Pi ohne Bauen). pdftotext (poppler) war
# vorher der Weg für Anhänge und fetch_document; der kennt aber weder
# Formularfelder noch Zusammenfügen, fehlt auf manchem Rechner, und zwei
# PDF-Wege liefen irgendwann auseinander. Seitdem geht JEDES PDF hier durch
# (gedaechtnis.pdf_text ruft text_alle()).
#
# ── Warum in einem eigenen Prozess ─────────────────────────────────────
# Ein PDF kommt oft von draußen (Downloads, Mail-Anhang). Ein kaputtes oder
# böswillig gebautes kann einen Leser lange rechnen oder viel Speicher
# fressen lassen — im Backend hielte das einen Thread fest, den niemand
# beenden kann. Deshalb läuft pypdf in einem Kindprozess dieser Datei
# (`python -I pdf_datei.py`) mit Zeit-, CPU- und Speichergrenze; wird er
# getötet, kommt eine Fehlermeldung zurück, das Backend läuft weiter. Der
# Kind-Teil (unten, „Im Kindprozess") importiert nur pypdf und die
# Standardbibliothek: mit -I sieht er die übrigen core-Module gar nicht.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import json
import os
import re
import resource
import subprocess
import sys
import tempfile

MAX_BYTES = 30 * 1024 * 1024        # größte Datei, die angenommen wird
ZEIT_S = 60                         # je Kindprozess
SPEICHER_BYTES = 1536 * 1024 * 1024
MAX_SEITEN_ZUSAMMEN = 2000          # Seiten im zusammengefügten PDF
MAX_FELDER = 400

# Fehlerarten aus dem Kindprozess → Text für die KI (und Sasha).
FEHLER_TEXT = {
    "kaputt": "Die Datei ist kein lesbares PDF (beschädigt oder etwas anderes).",
    "gesperrt": ("Das PDF ist mit einem Passwort geschützt — ohne Passwort "
                 "komme ich nicht hinein."),
    "leer": "Das PDF hat keine Seiten.",
    "bibliothek": ("Die PDF-Bibliothek (pypdf) fehlt auf diesem Rechner — "
                   "venv/bin/pip install -r requirements.txt"),
    "zeit": "Das PDF hat zu lange gebraucht (abgebrochen) — vermutlich kaputt oder riesig.",
    "seiten": "Diese Seiten gibt es nicht.",
}


class Fehler(ValueError):
    """Etwas ging mit dem PDF nicht — der Text ist für Menschen."""


# ── Seitenangaben ───────────────────────────────────────────────────────

def seiten_auswahl(angabe, anzahl: int) -> list:
    """„1-3, 7, 10-" → [1, 2, 3, 7, 10, …]. Seiten wie gedruckt: ab 1.
    Leer/None = alle. Unbekannte Seiten → Fehler mit Klartext."""
    if angabe is None or not str(angabe).strip() or str(angabe).strip().lower() in ("alle", "all"):
        return list(range(1, anzahl + 1))
    raus = []
    for teil in re.split(r"[,;\s]+", str(angabe).strip()):
        if not teil:
            continue
        m = re.fullmatch(r"(\d+)?\s*[-–]\s*(\d+)?|(\d+)", teil)
        if not m:
            raise Fehler(f"Seitenangabe {teil!r} verstehe ich nicht (so: 1-3,7).")
        if m.group(3):
            von = bis = int(m.group(3))
        else:
            von = int(m.group(1) or 1)
            bis = int(m.group(2) or anzahl)
        if von < 1 or bis > anzahl or von > bis:
            raise Fehler(f"Seite(n) {teil} gibt es nicht — das PDF hat {anzahl} Seiten.")
        raus.extend(range(von, bis + 1))
    if not raus:
        raise Fehler("Keine Seite angegeben.")
    return raus


def seiten_text(nummern: list) -> str:
    """[1,2,3,7] → „1-3, 7" (für Belege und Fragen)."""
    teile, i = [], 0
    while i < len(nummern):
        j = i
        while j + 1 < len(nummern) and nummern[j + 1] == nummern[j] + 1:
            j += 1
        teile.append(str(nummern[i]) if i == j else f"{nummern[i]}-{nummern[j]}")
        i = j + 1
    return ", ".join(teile)


# ── Kindprozess starten ─────────────────────────────────────────────────

def _grenzen():
    for art, wert in ((resource.RLIMIT_AS, SPEICHER_BYTES),
                      (resource.RLIMIT_CPU, int(ZEIT_S) + 5),
                      (resource.RLIMIT_FSIZE, 4 * MAX_BYTES)):
        try:
            resource.setrlimit(art, (wert, wert))
        except (ValueError, OSError):
            pass


def ist_pdf(daten: bytes) -> bool:
    # %PDF- darf laut Norm in den ersten 1024 Bytes stehen (Müll davor kommt vor).
    return bool(daten) and b"%PDF-" in daten[:1024]


def _im_kind(auftrag: dict, eingaben: list) -> tuple:
    """auftrag + PDF-Bytes → (antwort, ausgabe_bytes|None). Wirft Fehler."""
    for d in eingaben:
        if not d:
            raise Fehler("Die Datei ist leer.")
        if len(d) > MAX_BYTES:
            raise Fehler(f"Zu groß — höchstens {MAX_BYTES // 1024 // 1024} MB.")
        if not ist_pdf(d):
            raise Fehler(FEHLER_TEXT["kaputt"])
    with tempfile.TemporaryDirectory(prefix="zentrale-pdf-") as tmp:
        pfade = []
        for i, d in enumerate(eingaben):
            p = os.path.join(tmp, f"e{i}.pdf")
            with open(p, "wb") as f:
                f.write(d)
            pfade.append(p)
        auftrag = dict(auftrag, dateien=pfade, ziel=os.path.join(tmp, "aus.pdf"))
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-B", os.path.abspath(__file__)],
                input=json.dumps(auftrag), capture_output=True, text=True,
                timeout=ZEIT_S, preexec_fn=_grenzen, cwd=tmp,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        except subprocess.TimeoutExpired:
            raise Fehler(FEHLER_TEXT["zeit"])
        except (OSError, subprocess.SubprocessError):
            raise Fehler("Der PDF-Leser ließ sich nicht starten.")
        try:
            antwort = json.loads(proc.stdout or "{}")
        except ValueError:
            antwort = {}
        if not antwort:
            # Getötet (Speicher/CPU) oder abgestürzt: nie Rohes durchreichen.
            raise Fehler(FEHLER_TEXT["zeit"] if proc.returncode < 0
                         else FEHLER_TEXT["kaputt"])
        if antwort.get("fehler"):
            # „seiten" bringt einen eigenen Satz mit (aus seiten_auswahl, also
            # unser Text) — alles andere nur als Art, nie Rohes.
            raise Fehler(antwort.get("meldung") if antwort["fehler"] == "seiten"
                         and antwort.get("meldung")
                         else FEHLER_TEXT.get(antwort["fehler"], FEHLER_TEXT["kaputt"]))
        aus = None
        if os.path.isfile(auftrag["ziel"]):
            with open(auftrag["ziel"], "rb") as f:
                aus = f.read()
        return antwort, aus


# ── Öffentlich ──────────────────────────────────────────────────────────
# Je Aufruf EIN Kindprozess; er löst auch die Seitenangabe auf (er kennt
# die Seitenzahl) und liefert den Kopf (Seiten, Felder, Titel) immer mit.

def info(daten: bytes) -> dict:
    """{seiten_gesamt, gesperrt_offen (war mit leerem Passwort
    verschlüsselt), felder (Anzahl), titel}."""
    return _im_kind({"aufgabe": "info"}, [daten])[0]


def lesen(daten: bytes, seiten=None, was: str = "text") -> dict:
    """Text je Seite. was: text | tabellen (Spalten erhalten, Tabellen
    erkannt) | formular. -> {seiten_gesamt… siehe info, seiten: [{nr, text,
    tabellen?}], formular?: [{name, art, wert, optionen?}]}"""
    if was not in ("text", "tabellen", "formular"):
        raise Fehler("was: text, tabellen oder formular.")
    antwort = _im_kind({"aufgabe": was, "angabe": seiten}, [daten])[0]
    if was == "tabellen":
        for s in antwort.get("seiten") or []:
            s["tabellen"] = tabellen_aus_layout(s.get("text") or "")
    antwort.setdefault("seiten", [])
    return antwort


def text_alle(daten: bytes) -> tuple:
    """Der ganze Text mit Seitenmarken → (text, fehler); genau einer leer.
    Für Anhänge und fetch_document (gedaechtnis.pdf_text)."""
    try:
        r = lesen(daten)
    except Fehler as e:
        return "", str(e)
    teile = [f"--- Seite {s['nr']} ---\n{s['text'].strip()}" for s in r["seiten"]
             if (s.get("text") or "").strip()]
    if not teile:
        return "", ("Nichts Lesbares drin — vermutlich ein gescanntes PDF "
                    "(nur Bilder, kein Text).")
    return "\n\n".join(teile), ""


def zusammenfuegen(teile: list, titel: str = "") -> tuple:
    """[(pdf_bytes, seiten_angabe|None)] → (neues_pdf, seitenzahl). Die
    Teile in dieser Reihenfolge, jeder mit seinen Seiten (None = alle)."""
    if not teile:
        raise Fehler("Keine Teile angegeben.")
    antwort, aus = _im_kind({"aufgabe": "zusammen", "angaben": [a for _, a in teile],
                             "titel": str(titel or "")[:200]},
                            [d for d, _ in teile])
    if not aus:
        raise Fehler(FEHLER_TEXT["kaputt"])
    return aus, int(antwort.get("seiten") or 0)


# ── Tabellen aus spaltentreuem Text ────────────────────────────────────
# pypdf kann Text „wie gesetzt" ausgeben (layout): Spalten bleiben über
# Leerzeichen untereinander. Daraus Tabellen raten: Zeilen mit mindestens
# zwei Blöcken, die durch 2+ Leerzeichen getrennt sind, und davon mindestens
# zwei hintereinander. Spalten = wo Blöcke in mehreren Zeilen beginnen.
# Für Rechnungen und Stundenpläne reicht das; verbundene Zellen, gedrehte
# Tabellen und Tabellen als Bild erkennt es nicht — der Skill sagt das.

def _bloecke_der_zeile(zeile: str) -> list:
    return [(m.start(), m.group().strip()) for m in re.finditer(r"\S+(?: \S+)*", zeile)]


def tabellen_aus_layout(text: str) -> list:
    """Spaltentreuer Text → [[[zelle, …], …], …] (Tabellen aus Zeilen)."""
    tabellen, block = [], []

    def fertig():
        if len(block) >= 2:
            tabellen.append(_spalten(block))
        block.clear()

    leer = 0
    for zeile in str(text or "").splitlines():
        b = _bloecke_der_zeile(zeile)
        if len(b) >= 2:
            block.append(b)
            leer = 0
        elif not zeile.strip() and block and leer == 0:
            leer = 1                        # eine Leerzeile zwischen Reihen ist erlaubt
        else:
            fertig()
            leer = 0
    fertig()
    return tabellen


def _spalten(reihen: list) -> list:
    anfaenge = sorted({s for r in reihen for s, _ in r})
    spalten = []
    for s in anfaenge:
        if not spalten or s - spalten[-1][-1] > 2:
            spalten.append([s])
        else:
            spalten[-1].append(s)
    lage = [min(c) for c in spalten]
    raus = []
    for r in reihen:
        zellen = [""] * len(lage)
        for s, text in r:
            i = max(i for i, p in enumerate(lage) if p <= s + 2)
            zellen[i] = (zellen[i] + " " + text).strip()
        raus.append(zellen)
    # Spalten, die überall leer sind, weg
    voll = [i for i in range(len(lage)) if any(z[i] for z in raus)]
    return [[z[i] for i in voll] for z in raus]


def als_markdown(tabelle: list) -> str:
    if not tabelle:
        return ""
    def reihe(r):
        return "| " + " | ".join(z.replace("|", "\\|") for z in r) + " |"
    zeilen = [reihe(tabelle[0]), "|" + "---|" * len(tabelle[0])]
    zeilen += [reihe(r) for r in tabelle[1:]]
    return "\n".join(zeilen)


# ── Im Kindprozess ──────────────────────────────────────────────────────
# Nur Standardbibliothek + pypdf. Antwort als JSON auf stdout; Fehler als
# {"fehler": art} — nie eine Python-Meldung, die Pfade oder Inhalte zeigt.

def _kind_oeffnen(pfad):
    from pypdf import PdfReader
    try:
        r = PdfReader(pfad, strict=False)
    except Exception:
        return None, "kaputt", False
    offen = False
    if r.is_encrypted:
        try:
            ok = r.decrypt("")
        except Exception:
            ok = 0
        if not ok:
            return None, "gesperrt", False
        offen = True
    try:
        n = len(r.pages)
    except Exception:
        return None, "kaputt", False
    if n == 0:
        return None, "leer", False
    return r, "", offen


def _kind_wert(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_kind_wert(x) for x in v)
    v = str(v)
    return v[1:] if v.startswith("/") else v


def _kind_kopf(r, offen) -> dict:
    try:
        felder = len(r.get_fields() or {})
    except Exception:
        felder = 0
    try:
        titel = str((r.metadata or {}).get("/Title") or "")
    except Exception:
        titel = ""
    return {"seiten_gesamt": len(r.pages), "gesperrt_offen": offen,
            "felder": felder, "titel": titel[:200]}


def _kind_formular(r) -> list:
    try:
        felder = r.get_fields() or {}
    except Exception:
        felder = {}
    raus = []
    art_name = {"/Tx": "text", "/Btn": "knopf", "/Ch": "auswahl", "/Sig": "unterschrift"}
    for name, f in list(felder.items())[:MAX_FELDER]:
        eintrag = {"name": str(name), "art": art_name.get(str(f.get("/FT")), "feld"),
                   "wert": _kind_wert(f.get("/V"))}
        opt = f.get("/Opt") or f.get("/_States_")
        if opt:
            eintrag["optionen"] = [_kind_wert(o) for o in list(opt)[:30]]
        raus.append(eintrag)
    return raus


def _kind_text(r, nummern, layout: bool) -> list:
    raus = []
    for nr in nummern:
        try:
            if layout:
                t = r.pages[nr - 1].extract_text(extraction_mode="layout")
            else:
                t = r.pages[nr - 1].extract_text()
        except Exception:
            t = ""
        raus.append({"nr": nr, "text": t or ""})
    return raus


def _kind_zusammen(auftrag: dict) -> dict:
    from pypdf import PdfWriter
    w = PdfWriter()
    for pfad, angabe in zip(auftrag.get("dateien") or [], auftrag.get("angaben") or []):
        r, fehler, _ = _kind_oeffnen(pfad)
        if fehler:
            return {"fehler": fehler}
        nummern = seiten_auswahl(angabe, len(r.pages))
        if len(w.pages) + len(nummern) > MAX_SEITEN_ZUSAMMEN:
            return {"fehler": "seiten",
                    "meldung": f"Mehr als {MAX_SEITEN_ZUSAMMEN} Seiten — zu viel."}
        for nr in nummern:
            w.add_page(r.pages[nr - 1])
    if auftrag.get("titel"):
        w.add_metadata({"/Title": auftrag["titel"], "/Producer": "ZENTRALE"})
    with open(auftrag["ziel"], "wb") as f:
        w.write(f)
    return {"seiten": len(w.pages)}


def _kind_arbeiten(auftrag: dict) -> dict:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return {"fehler": "bibliothek"}
    aufgabe = auftrag.get("aufgabe")
    try:
        if aufgabe == "zusammen":
            return _kind_zusammen(auftrag)
        r, fehler, offen = _kind_oeffnen((auftrag.get("dateien") or [""])[0])
        if fehler:
            return {"fehler": fehler}
        kopf = _kind_kopf(r, offen)
        if aufgabe == "info":
            return kopf
        if aufgabe == "formular":
            return dict(kopf, formular=_kind_formular(r))
        if aufgabe in ("text", "tabellen"):
            nummern = seiten_auswahl(auftrag.get("angabe"), len(r.pages))
            return dict(kopf, seiten=_kind_text(r, nummern, aufgabe == "tabellen"))
    except Fehler as e:
        return {"fehler": "seiten", "meldung": str(e)}
    return {"fehler": "kaputt"}


def _kind():
    import logging
    logging.disable(logging.CRITICAL)      # pypdf-Warnungen nicht auf stderr
    try:
        auftrag = json.loads(sys.stdin.read() or "{}")
        antwort = _kind_arbeiten(auftrag)
    except MemoryError:
        antwort = {"fehler": "zeit"}
    except Exception:
        antwort = {"fehler": "kaputt"}
    sys.stdout.write(json.dumps(antwort, ensure_ascii=False))


if __name__ == "__main__":
    _kind()
