# core/ki_pdf_word.py
#
# Was die PDF- und Word-Werkzeuge der KI TUN: Quelle finden (Ablage oder
# Datei), lesen, neue Datei bauen, in die Ablage legen, nachlesen und mit
# Beleg antworten. Einträge und Fragen: core/werkzeug_pdf_word.py; das
# Handwerk: core/pdf_datei.py, core/pdf_schreiben.py, core/word_datei.py.
#
# 2026-10-08, Skills pdf und word (memory/ki/pdf_word.md). Jede neue Datei
# wird NACH dem Ablegen aus der Ablage gelesen (nicht aus dem Speicher) —
# erst das ist der Beleg, dass dort eine brauchbare Datei liegt.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Meldet sich per
# @ausfuehrer an; ki_werkzeuge importiert dieses Modul.

import os

import ablage
import ablage_text
import context
import input_aufraeumen
import pdf_datei
import pdf_schreiben
import textbloecke
import word_datei
import werkzeug_register
import zug
import shutil

from werkzeug_befund import Befund, OK, FEHLGESCHLAGEN, erledigt, abgebrochen
from werkzeug_pdf_word import quelle_name

ausfuehrer = werkzeug_register.ausfuehrer

SEITE_ZEICHEN = 20_000        # so viel Text je Aufruf (wie load_skill)
MAX_TEILE = 30


class _Fehlt(Exception):
    """Quelle nicht zu haben. code: core/fehlercodes.py (seit 2026-10-09)."""

    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code, self.grund = code, grund


# ── Quelle: Ablage-id oder Datei ────────────────────────────────────────

def _quelle(quelle, art: str) -> tuple:
    """→ (bytes, name, ablage_id|None). art: "pdf" | "docx"."""
    q = str(quelle or "").strip()
    wort = "PDF" if art == "pdf" else "Word-Datei"
    if not q:
        raise _Fehlt("P-QUELLE-FEHLT", "keine Quelle angegeben — Ablage-id oder Dateipfad")
    if ablage.gibt_es(q):
        k = ablage.kopf(q)
        if k.get("art") != art:
            if k.get("herkunft") == "anhang" and str(k.get("quelle") or "").lower() \
                    .endswith("." + art):
                raise _Fehlt("P-ORIGINAL-FEHLT", "dieser Anhang wurde früher nur als Text "
                             "abgelegt — das Original fehlt. Sasha muss die Datei neu "
                             "anhängen; den Text gibt read_document(id)")
            raise _Fehlt("P-FALSCHE-ART", f"„{k.get('titel')}“ ist keine {wort} "
                         f"(Art {k.get('art')})")
        return ablage.roh(q), k.get("titel") or q, q
    pfad = context.pfad_aufloesen(q)
    # Dieselbe Sperre wie read_file und fetch_document (context.erlaubt):
    # eine dritte Antwort auf „was darf sie sehen" wäre ein Umweg.
    grund = context.erlaubt(pfad)
    if grund == context.AUSSERHALB:
        # gross seit 2026-10-09: nur Input/ und Output/ (core/context.py).
        raise _Fehlt("P-QUELLE-AUSSERHALB", f"{q} liegt nicht in Input/ oder Output/ "
                     "des Nutzerordners")
    if grund:
        raise _Fehlt("P-QUELLE-GESPERRT", f"{q} — {grund}. Sasha kann die Datei anhängen")
    if not os.path.isfile(pfad):
        raise _Fehlt("P-QUELLE-FEHLT", f"weder eine Ablage-id noch eine Datei: {q}")
    if os.path.getsize(pfad) > pdf_datei.MAX_BYTES:
        raise _Fehlt("P-ZU-GROSS", "die Datei ist zu groß (höchstens 30 MB)")
    with open(pfad, "rb") as f:
        return f.read(), os.path.basename(pfad), None


def _fertig(ergebnis, quelle, doc_id):
    """Eine Datei (keine Ablage-id) ganz gelesen: liegt sie direkt in Input/,
    hängt die Aufräum-Zeile an (core/input_aufraeumen.py, 2026-10-09)."""
    if doc_id:
        return ergebnis
    return input_aufraeumen.nach_verarbeitung(ergebnis, context.pfad_aufloesen(quelle))


def _herkunft(name: str, doc_id) -> str:
    return f"„{name}“ (Ablage-id {doc_id})" if doc_id else f"„{name}“ (Datei)"


def _ablegen(titel: str, daten: bytes, art: str, quelle: str | None = None) -> dict:
    # Gemeldet (zug.melden) wird erst nach dem Beleg, in _belegt.
    return ablage.anlegen(titel, daten, art, herkunft="ki", gespraech=zug.gespraech(),
                          quelle=quelle)


def _belegt(k: dict, was: str, satz: str, beleg: str | None, zusatz: str = "") -> Befund:
    """ERLEDIGT mit dem nachgelesenen Beleg — oder die eben angelegte Datei
    wieder weg (es gab sie vorher nicht) und ABGEBROCHEN (2026-10-09)."""
    if beleg is None:
        shutil.rmtree(os.path.join(ablage.ordner(), k["id"]), ignore_errors=True)
        return abgebrochen(was, "W-NICHT-GESPEICHERT", "nachgelesen liegt sie nicht "
                           "lesbar in der Ablage; sie ist wieder entfernt", "nichts abgelegt")
    zug.melden({"ablage": ablage.kurz(k)})
    return erledigt(f"{satz} Nachgelesen: {beleg}", beleg, zusatz=zusatz)


def _anfang(text: str, n: int = 60) -> str:
    for z in str(text or "").splitlines():
        z = " ".join(z.strip().lstrip("#|-").split())
        if z:
            return z[:n]
    return ""


# ── PDF ─────────────────────────────────────────────────────────────────

def _pdf_kopf(r: dict, name: str, doc_id) -> str:
    teile = [f"{_herkunft(name, doc_id)}: PDF, {r.get('seiten_gesamt')} Seiten"]
    if r.get("felder"):
        teile.append(f"Formular mit {r['felder']} Feldern")
    if r.get("gesperrt_offen"):
        teile.append("war verschlüsselt, ließ sich ohne Passwort öffnen")
    return ", ".join(teile) + "."


def _seiten_zeigen(seiten: list, tabellen: bool) -> tuple:
    """→ (text, gezeigte_nummern, leere_nummern). Hört an einer Seitengrenze
    auf, wenn SEITE_ZEICHEN erreicht sind (mindestens eine Seite)."""
    raus, gezeigt, leer, laenge = [], [], [], 0
    for s in seiten:
        if tabellen and s.get("tabellen"):
            inhalt = "\n\n".join(pdf_datei.als_markdown(t) for t in s["tabellen"])
            inhalt += "\n(Tabellen geraten aus der Lage des Texts — Zahlen gegen den Text prüfen.)"
        else:
            inhalt = "\n".join(z.rstrip() for z in (s.get("text") or "").splitlines()).strip()
            if tabellen and inhalt:
                inhalt = "(keine Tabelle erkannt — Text mit Spalten wie gesetzt:)\n" + inhalt
        if not inhalt.strip():
            leer.append(s["nr"])
            inhalt = "(kein Text auf dieser Seite — Bild oder Scan?)"
        stueck = f"--- Seite {s['nr']} ---\n{inhalt}"
        if gezeigt and laenge + len(stueck) > SEITE_ZEICHEN:
            break
        raus.append(stueck[:SEITE_ZEICHEN])
        gezeigt.append(s["nr"])
        laenge += len(stueck)
    return "\n\n".join(raus), gezeigt, leer


@ausfuehrer("read_pdf")
def _read_pdf(args: dict) -> str:
    try:
        daten, name, doc_id = _quelle(args.get("quelle"), "pdf")
    except _Fehlt as e:
        return abgebrochen("PDF lesen", e.code, e.grund, "nichts gelesen")
    was = str(args.get("was") or "text").strip().lower()
    if was not in ("text", "tabellen", "formular"):
        was = "text"
    try:
        r = pdf_datei.lesen(daten, args.get("seiten"), was)
    except pdf_datei.Fehler as e:
        return abgebrochen(f"PDF {_herkunft(name, doc_id)} lesen", "P-DATEI-KAPUTT", str(e),
                           "nichts gelesen")
    kopf = _pdf_kopf(r, name, doc_id)
    if was == "formular":
        felder = r.get("formular") or []
        if not felder:
            return _fertig(Befund(kopf + "\nDas PDF hat keine ausfüllbaren Formularfelder.",
                                  OK), args.get("quelle"), doc_id)
        zeilen = []
        for f in felder:
            z = f"- {f['name']} ({f['art']}): {f['wert'] or '(leer)'}"
            if f.get("optionen"):
                z += " — möglich: " + ", ".join(o for o in f["optionen"] if o)
            zeilen.append(z)
        return _fertig(Befund(kopf + f"\n{len(felder)} Formularfelder:\n" + "\n".join(zeilen),
                              OK), args.get("quelle"), doc_id)
    text, gezeigt, leer = _seiten_zeigen(r["seiten"], was == "tabellen")
    angefragt = [s["nr"] for s in r["seiten"]]
    # Stückweise lesen ist kein Teil-Ergebnis (2026-10-09): der Aufruf hat
    # genau das getan, was er sagt — Seiten a–b gelesen, Rest per seiten=.
    hinweise = []
    if len(gezeigt) < len(angefragt):
        rest = angefragt[len(gezeigt):]
        hinweise.append(f"Seiten {pdf_datei.seiten_text(gezeigt)} von "
                        f"{r.get('seiten_gesamt')} gelesen, weiter mit "
                        f"seiten={pdf_datei.seiten_text(rest).replace(' ', '')}.")
    if leer:
        if len(leer) == len(gezeigt):
            return abgebrochen(f"PDF {_herkunft(name, doc_id)} lesen", "P-KEIN-TEXT",
                               f"kein Text auf den Seiten {pdf_datei.seiten_text(leer)} — "
                               f"vermutlich gescannt (nur Bilder); Texterkennung gibt es "
                               f"nicht", "nichts gelesen")
        hinweise.append(f"Ohne Text (Bild/Scan?): Seiten {pdf_datei.seiten_text(leer)}.")
    ergebnis = Befund("\n".join([kopf, text] + hinweise), OK)
    # Fertig ist eine Datei erst, wenn ALLE ihre Seiten gelesen sind.
    if len(gezeigt) == r.get("seiten_gesamt"):
        return _fertig(ergebnis, args.get("quelle"), doc_id)
    return ergebnis


@ausfuehrer("create_pdf")
def _create_pdf(args: dict) -> str:
    titel = " ".join(str(args.get("titel") or "").split()) or "Dokument"
    was = f"PDF „{titel}“ anlegen"
    try:
        roh, info = pdf_schreiben.erzeugen(titel, str(args.get("inhalt") or ""))
    except ValueError as e:
        return abgebrochen(was, "P-DATEI-KAPUTT", str(e), "nichts angelegt")
    # Zeichen, die die Schrift nicht kann, stünden als „?" da — das wäre
    # „anders als verlangt". Also gar nicht erst ablegen (2026-10-09).
    if info["ersetzt"]:
        return abgebrochen(was, "P-ZEICHEN", f"{info['ersetzt']} Zeichen kann die "
                           f"PDF-Schrift nicht darstellen (z. B. "
                           f"{' '.join(info['beispiele'])})", "nichts angelegt")
    try:
        k = _ablegen(titel, roh, "pdf")
    except ablage.Fehler as e:
        return abgebrochen(was, "P-ABGELEHNT", str(e), "nichts angelegt")
    return _belegt(k, was, f'PDF „{k["titel"]}“ ANGELEGT (id {k["id"]}, {info["seiten"]} '
                   f'Seiten).', _pdf_beleg(k["id"], info["seiten"]),
                   zusatz="Sasha sieht es im Chat; wiederhole den Inhalt nicht.")


def _pdf_beleg(doc_id, seiten_soll: int):
    try:
        r = pdf_datei.lesen(ablage.roh(doc_id), "1")
    except (pdf_datei.Fehler, ablage.Unbekannt, OSError):
        return None
    if r.get("seiten_gesamt") != seiten_soll:
        return None
    erste = _anfang(r["seiten"][0]["text"] if r["seiten"] else "")
    return (f"liegt in der Ablage (id {doc_id}), {r['seiten_gesamt']} Seiten; "
            f"Seite 1 beginnt mit „{erste}…“." if erste else
            f"liegt in der Ablage (id {doc_id}), {r['seiten_gesamt']} Seiten.")


@ausfuehrer("combine_pdf")
def _combine_pdf(args: dict) -> str:
    teile_args = args.get("teile") if isinstance(args.get("teile"), list) else []
    titel = " ".join(str(args.get("titel") or "").split()) or "Zusammengefügt"
    was = f"PDF „{titel}“ zusammenfügen"
    if not teile_args:
        return abgebrochen(was, "P-TEILE-FEHLEN", "keine Teile angegeben", "nichts angelegt")
    if len(teile_args) > MAX_TEILE:
        return abgebrochen(was, "P-ZU-VIELE-TEILE", f"höchstens {MAX_TEILE} Teile",
                           "nichts angelegt")
    teile, namen = [], []
    for t in teile_args:
        t = t if isinstance(t, dict) else {"quelle": t}
        try:
            daten, name, doc_id = _quelle(t.get("quelle"), "pdf")
        except _Fehlt as e:
            return abgebrochen(was, e.code, e.grund, "nichts angelegt")
        seiten = str(t.get("seiten") or "").strip() or None
        teile.append((daten, seiten))
        namen.append(name + (f" (Seiten {seiten})" if seiten else ""))
    try:
        roh, anzahl = pdf_datei.zusammenfuegen(teile, titel)
    except pdf_datei.Fehler as e:
        return abgebrochen(was, "P-DATEI-KAPUTT", str(e), "nichts angelegt")
    try:
        k = _ablegen(titel, roh, "pdf", quelle="aus: " + "; ".join(namen))
    except ablage.Fehler as e:
        return abgebrochen(was, "P-ABGELEHNT", str(e), "nichts angelegt")
    return _belegt(k, was, f'PDF „{k["titel"]}“ ANGELEGT (id {k["id"]}, {anzahl} Seiten) '
                   f'aus: {"; ".join(namen)}. Die Originale sind unverändert.',
                   _pdf_beleg(k["id"], anzahl))


# ── Word ────────────────────────────────────────────────────────────────

@ausfuehrer("read_docx")
def _read_docx(args: dict) -> str:
    try:
        daten, name, doc_id = _quelle(args.get("quelle"), "docx")
        r = word_datei.lesen(daten)
    except _Fehlt as e:
        return abgebrochen("Word-Datei lesen", e.code, e.grund, "nichts gelesen")
    except word_datei.Fehler as e:
        return abgebrochen("Word-Datei lesen", "P-DATEI-KAPUTT", str(e), "nichts gelesen")
    try:
        ab = max(0, int(args.get("ab") or 0))
    except (TypeError, ValueError):
        ab = 0
    text = r["text"]
    kopf = (f"{_herkunft(name, doc_id)}: Word, {r['absaetze']} Absätze, "
            f"{len(r['ueberschriften'])} Überschriften, {r['tabellen']} Tabellen.")
    if r["hinweise"]:
        kopf += " Hinweis: " + "; ".join(r["hinweise"]) + "."
    if not text.strip():
        return _fertig(Befund(kopf + "\nKein Text darin.", OK), args.get("quelle"), doc_id)
    stueck = text[ab:ab + SEITE_ZEICHEN]
    if ab + SEITE_ZEICHEN < len(text):
        return Befund(f"{kopf}\n{stueck}\n[Zeichen {ab}–{ab + len(stueck)} von "
                      f"{len(text)} gelesen, weiter mit ab={ab + len(stueck)}]", OK)
    return _fertig(Befund(f"{kopf}\n{stueck}", OK), args.get("quelle"), doc_id)


def _docx_beleg(doc_id, muss=(), darf_nicht=()):
    """Liest die abgelegte Datei; alle `muss` stehen drin, kein `darf_nicht`."""
    try:
        r = word_datei.lesen(ablage.roh(doc_id))
    except (word_datei.Fehler, ablage.Unbekannt, OSError):
        return None
    flach = " ".join(r["text"].replace("|", " ").split())
    for t in muss:
        if t and " ".join(t.split()) not in flach:
            return None
    for t in darf_nicht:
        if t and " ".join(t.split()) in flach:
            return None
    return (f"liegt in der Ablage (id {doc_id}): {r['absaetze']} Absätze, "
            f"{len(r['ueberschriften'])} Überschriften, {r['tabellen']} Tabellen; "
            f"beginnt mit „{_anfang(r['text'])}…“.")


def _erster_text(markdown: str) -> str:
    """Der erste Absatz/Titel als Klartext — die Probe für den Beleg."""
    for b in textbloecke.bloecke(markdown):
        if b.art in (textbloecke.UEBERSCHRIFT, textbloecke.ABSATZ):
            return textbloecke.klartext(b.text)[:60]
    return ""


@ausfuehrer("create_docx")
def _create_docx(args: dict) -> str:
    titel = " ".join(str(args.get("titel") or "").split()) or "Dokument"
    inhalt = str(args.get("inhalt") or "")
    was = f"Word-Datei „{titel}“ anlegen"
    try:
        roh = word_datei.erzeugen(titel, inhalt)
    except word_datei.Fehler as e:
        return abgebrochen(was, "P-DATEI-KAPUTT", str(e), "nichts angelegt")
    try:
        k = _ablegen(titel, roh, "docx")
    except ablage.Fehler as e:
        return abgebrochen(was, "P-ABGELEHNT", str(e), "nichts angelegt")
    return _belegt(k, was, f'Word-Datei „{k["titel"]}“ ANGELEGT (id {k["id"]}).',
                   _docx_beleg(k["id"], [_erster_text(inhalt)]),
                   zusatz="Sasha sieht sie im Chat; wiederhole den Inhalt nicht.")


@ausfuehrer("edit_docx")
def _edit_docx(args: dict) -> str:
    try:
        daten, name, doc_id = _quelle(args.get("quelle"), "docx")
    except _Fehlt as e:
        return abgebrochen("Geänderte Word-Kopie", e.code, e.grund, "nichts angelegt")
    roh_paare = args.get("ersetzen") if isinstance(args.get("ersetzen"), list) else []
    paare = [(str(p.get("alt") or ""), str(p.get("neu") or "")) for p in roh_paare
             if isinstance(p, dict)]
    anhaengen = str(args.get("anhaengen") or "")
    titel = " ".join(str(args.get("titel") or "").split()) or f"{os.path.splitext(name)[0]} (geändert)"
    was = f"Geänderte Kopie „{titel}“ von {_herkunft(name, doc_id)}"
    if not paare and not anhaengen.strip():
        return abgebrochen(was, "P-NICHTS-ZU-AENDERN", "weder ersetzen noch anhängen "
                           "angegeben", "keine Kopie angelegt")
    try:
        neu, bericht = word_datei.aendern(daten, paare, anhaengen, titel=titel)
    except word_datei.Fehler as e:
        return abgebrochen(was, "P-DATEI-KAPUTT", str(e), "keine Kopie angelegt")
    # Ganz oder gar nicht (2026-10-09): kommt ein Text nicht vor, oder ließe
    # sich ein Treffer nicht ersetzen, gibt es KEINE Kopie — eine Kopie, in
    # der die Hälfte fehlt, ist „anders als verlangt".
    fehlt = [alt for alt, n, _ in bericht["ersetzt"] if n == 0]
    if fehlt:
        return abgebrochen(was, "P-ERSETZEN-FEHLT", "kommt nicht vor: "
                           + "; ".join(f"„{a[:50]}“" for a in fehlt), "keine Kopie angelegt")
    geteilt = [(alt, aus) for alt, _n, aus in bericht["ersetzt"] if aus]
    if geteilt:
        return abgebrochen(was, "P-ERSETZEN-GETEILT", "; ".join(
            f"„{a[:50]}“ {aus}× über Tab/Zeilenumbruch" for a, aus in geteilt),
            "keine Kopie angelegt")
    zeilen = [f"„{alt[:50]}“: {n}× ersetzt" for alt, n, _ in bericht["ersetzt"]]
    try:
        k = _ablegen(titel, neu, "docx", quelle=f"geändert aus {quelle_name(args.get('quelle'))}")
    except ablage.Fehler as e:
        return abgebrochen(was, "P-ABGELEHNT", str(e), "keine Kopie angelegt")
    if bericht["angehaengt"]:
        zeilen.append(f"angehängt: {bericht['angehaengt']} Absätze/Tabellen")
    satz = (f'Geänderte Kopie „{k["titel"]}“ ANGELEGT (id {k["id"]}); das Original '
            f'{_herkunft(name, doc_id)} ist unverändert. ' + "; ".join(zeilen) + ".")
    # Beleg: jeder neue Text steht da; ein ersetzter alter nicht mehr, wenn er
    # nicht im neuen steckt und kein Treffer ausgelassen wurde.
    muss = [n for (a, n), (_, z, _) in zip(paare, bericht["ersetzt"]) if z and n.strip()]
    weg = [a for (a, n), (_, z, aus) in zip(paare, bericht["ersetzt"])
           if z and not aus and a not in n and a not in anhaengen]
    if anhaengen.strip():
        muss.append(_erster_text(anhaengen))
    return _belegt(k, was, satz, _docx_beleg(k["id"], muss, weg))
