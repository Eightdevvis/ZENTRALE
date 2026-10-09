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
import pdf_datei
import pdf_schreiben
import textbloecke
import word_datei
import werkzeug_register
import zug
from werkzeug_befund import Befund, OK, TEILWEISE, FEHLGESCHLAGEN
from werkzeug_pdf_word import quelle_name

ausfuehrer = werkzeug_register.ausfuehrer

SEITE_ZEICHEN = 20_000        # so viel Text je Aufruf (wie load_skill)
MAX_TEILE = 30


class _Fehlt(Exception):
    """Quelle nicht zu haben — der Text geht so an die KI."""


# ── Quelle: Ablage-id oder Datei ────────────────────────────────────────

def _quelle(quelle, art: str) -> tuple:
    """→ (bytes, name, ablage_id|None). art: "pdf" | "docx"."""
    q = str(quelle or "").strip()
    wort = "PDF" if art == "pdf" else "Word-Datei"
    if not q:
        raise _Fehlt("[Fehler: keine Quelle angegeben — Ablage-id oder Dateipfad.]")
    if ablage.gibt_es(q):
        k = ablage.kopf(q)
        if k.get("art") != art:
            if k.get("herkunft") == "anhang" and str(k.get("quelle") or "").lower() \
                    .endswith("." + art):
                raise _Fehlt(f"[Fehler: dieser Anhang wurde früher nur als Text abgelegt — "
                             f"das Original fehlt. Sasha muss die Datei neu anhängen; "
                             f"den Text gibt read_document(id).]")
            raise _Fehlt(f"[Fehler: „{k.get('titel')}“ ist keine {wort} "
                         f"(Art {k.get('art')}).]")
        return ablage.roh(q), k.get("titel") or q, q
    pfad = os.path.expanduser(q)
    if not os.path.isabs(pfad):
        for wurzel in context._WURZELN:
            if os.path.exists(os.path.join(wurzel, pfad)):
                pfad = os.path.join(wurzel, pfad)
                break
    pfad = os.path.abspath(pfad)
    # Dieselbe Sperre wie read_file und fetch_document (context.erlaubt):
    # eine dritte Antwort auf „was darf sie sehen" wäre ein Umweg.
    grund = context.erlaubt(pfad)
    if grund:
        raise _Fehlt(f"[Nicht erlaubt: {q} — {grund}. Sasha kann die Datei anhängen.]")
    if not os.path.isfile(pfad):
        raise _Fehlt(f"[Fehler: weder eine Ablage-id noch eine Datei: {q}]")
    if os.path.getsize(pfad) > pdf_datei.MAX_BYTES:
        raise _Fehlt("[Fehler: die Datei ist zu groß (höchstens 30 MB).]")
    with open(pfad, "rb") as f:
        return f.read(), os.path.basename(pfad), None


def _herkunft(name: str, doc_id) -> str:
    return f"„{name}“ (Ablage-id {doc_id})" if doc_id else f"„{name}“ (Datei)"


def _ablegen(titel: str, daten: bytes, art: str, quelle: str | None = None) -> dict:
    k = ablage.anlegen(titel, daten, art, herkunft="ki", gespraech=zug.gespraech(),
                       quelle=quelle)
    zug.melden({"ablage": ablage.kurz(k)})
    return k


def _belegt(text: str, status: str, beleg: str | None, fehlt: str) -> Befund:
    if beleg is None:
        return Befund(f"{text}\nNachgelesen: {fehlt} — melde keinen Erfolg.",
                      FEHLGESCHLAGEN)
    return Befund(f"{text}\nNachgelesen: {beleg}", status, beleg=beleg)


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
        return str(e)
    was = str(args.get("was") or "text").strip().lower()
    if was not in ("text", "tabellen", "formular"):
        was = "text"
    try:
        r = pdf_datei.lesen(daten, args.get("seiten"), was)
    except pdf_datei.Fehler as e:
        return f"[Fehler: {e}]"
    kopf = _pdf_kopf(r, name, doc_id)
    if was == "formular":
        felder = r.get("formular") or []
        if not felder:
            return Befund(kopf + "\nDas PDF hat keine ausfüllbaren Formularfelder.", OK)
        zeilen = []
        for f in felder:
            z = f"- {f['name']} ({f['art']}): {f['wert'] or '(leer)'}"
            if f.get("optionen"):
                z += " — möglich: " + ", ".join(o for o in f["optionen"] if o)
            zeilen.append(z)
        return Befund(kopf + f"\n{len(felder)} Formularfelder:\n" + "\n".join(zeilen), OK)
    text, gezeigt, leer = _seiten_zeigen(r["seiten"], was == "tabellen")
    angefragt = [s["nr"] for s in r["seiten"]]
    hinweise, status = [], OK
    if len(gezeigt) < len(angefragt):
        rest = angefragt[len(gezeigt):]
        hinweise.append(f"Gezeigt: Seiten {pdf_datei.seiten_text(gezeigt)}. Weiter mit "
                        f"seiten='{pdf_datei.seiten_text(rest).replace(' ', '')}'.")
        status = TEILWEISE
    if leer:
        if len(leer) == len(gezeigt):
            return Befund(kopf + "\nKein Text auf den Seiten "
                          f"{pdf_datei.seiten_text(leer)} — vermutlich gescannt (nur "
                          "Bilder). Texterkennung habe ich nicht; sag Sasha das so.",
                          FEHLGESCHLAGEN)
        hinweise.append(f"Ohne Text (Bild/Scan?): Seiten {pdf_datei.seiten_text(leer)}.")
        status = TEILWEISE
    return Befund("\n".join([kopf, text] + hinweise), status)


@ausfuehrer("create_pdf")
def _create_pdf(args: dict) -> str:
    titel = " ".join(str(args.get("titel") or "").split()) or "Dokument"
    try:
        roh, info = pdf_schreiben.erzeugen(titel, str(args.get("inhalt") or ""))
        k = _ablegen(titel, roh, "pdf")
    except (ValueError, ablage.Fehler) as e:
        return f"[Nicht erstellt: {e}]"
    text = (f'PDF „{k["titel"]}“ erstellt und abgelegt (id {k["id"]}, '
            f'{info["seiten"]} Seiten). Sasha sieht es im Chat; wiederhole den Inhalt nicht.')
    status = OK
    if info["ersetzt"]:
        text += (f"\nAchtung: {info['ersetzt']} Zeichen kann die PDF-Schrift nicht "
                 f"darstellen (z. B. {' '.join(info['beispiele'])}) — sie stehen als „?“ "
                 f"da. Sag Sasha das.")
        status = TEILWEISE
    return _belegt(text, status, _pdf_beleg(k["id"], info["seiten"]),
                   "das PDF liegt NICHT lesbar in der Ablage")


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
    if not teile_args:
        return "[Fehler: keine Teile angegeben.]"
    if len(teile_args) > MAX_TEILE:
        return f"[Fehler: höchstens {MAX_TEILE} Teile.]"
    teile, namen = [], []
    for t in teile_args:
        t = t if isinstance(t, dict) else {"quelle": t}
        try:
            daten, name, doc_id = _quelle(t.get("quelle"), "pdf")
        except _Fehlt as e:
            return str(e)
        seiten = str(t.get("seiten") or "").strip() or None
        teile.append((daten, seiten))
        namen.append(name + (f" (Seiten {seiten})" if seiten else ""))
    titel = " ".join(str(args.get("titel") or "").split()) or "Zusammengefügt"
    try:
        roh, anzahl = pdf_datei.zusammenfuegen(teile, titel)
        k = _ablegen(titel, roh, "pdf", quelle="aus: " + "; ".join(namen))
    except (pdf_datei.Fehler, ablage.Fehler) as e:
        return f"[Nicht erstellt: {e}]"
    text = (f'Neues PDF „{k["titel"]}“ abgelegt (id {k["id"]}) aus: {"; ".join(namen)}. '
            f'Die Originale sind unverändert.')
    return _belegt(text, OK, _pdf_beleg(k["id"], anzahl),
                   "das neue PDF liegt NICHT lesbar in der Ablage")


# ── Word ────────────────────────────────────────────────────────────────

@ausfuehrer("read_docx")
def _read_docx(args: dict) -> str:
    try:
        daten, name, doc_id = _quelle(args.get("quelle"), "docx")
        r = word_datei.lesen(daten)
    except _Fehlt as e:
        return str(e)
    except word_datei.Fehler as e:
        return f"[Fehler: {e}]"
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
        return Befund(kopf + "\nKein Text darin.", OK)
    stueck = text[ab:ab + SEITE_ZEICHEN]
    if ab + SEITE_ZEICHEN < len(text):
        return Befund(f"{kopf}\n{stueck}\n[… Zeichen {ab}–{ab + len(stueck)} von "
                      f"{len(text)}; weiter mit ab={ab + len(stueck)}]", TEILWEISE)
    return Befund(f"{kopf}\n{stueck}", OK)


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
    try:
        roh = word_datei.erzeugen(titel, inhalt)
        k = _ablegen(titel, roh, "docx")
    except (word_datei.Fehler, ablage.Fehler) as e:
        return f"[Nicht erstellt: {e}]"
    text = (f'Word-Datei „{k["titel"]}“ erstellt und abgelegt (id {k["id"]}). Sasha '
            f'sieht sie im Chat; wiederhole den Inhalt nicht.')
    return _belegt(text, OK, _docx_beleg(k["id"], [_erster_text(inhalt)]),
                   "die Word-Datei liegt NICHT lesbar in der Ablage")


@ausfuehrer("edit_docx")
def _edit_docx(args: dict) -> str:
    try:
        daten, name, doc_id = _quelle(args.get("quelle"), "docx")
    except _Fehlt as e:
        return str(e)
    roh_paare = args.get("ersetzen") if isinstance(args.get("ersetzen"), list) else []
    paare = [(str(p.get("alt") or ""), str(p.get("neu") or "")) for p in roh_paare
             if isinstance(p, dict)]
    anhaengen = str(args.get("anhaengen") or "")
    titel = " ".join(str(args.get("titel") or "").split()) or f"{os.path.splitext(name)[0]} (geändert)"
    try:
        neu, bericht = word_datei.aendern(daten, paare, anhaengen, titel=titel)
    except word_datei.Fehler as e:
        return f"[Nicht geändert: {e}]"
    zeilen, fehlend, status = [], [], OK
    for alt, n, ausgelassen in bericht["ersetzt"]:
        z = f"„{alt[:50]}“: {n}× ersetzt"
        if ausgelassen:
            z += f", {ausgelassen}× NICHT (geht über einen Tab/Zeilenumbruch)"
            status = TEILWEISE
        if n == 0:
            fehlend.append(alt)
            z += " — kommt nicht vor (genau so geschrieben?)"
            status = TEILWEISE
        zeilen.append(z)
    if not bericht["angehaengt"] and not any(n for _, n, _ in bericht["ersetzt"]):
        return Befund(f"[Nichts geändert — keine Kopie angelegt.]\n" + "\n".join(zeilen),
                      FEHLGESCHLAGEN)
    try:
        k = _ablegen(titel, neu, "docx", quelle=f"geändert aus {quelle_name(args.get('quelle'))}")
    except ablage.Fehler as e:
        return f"[Nicht abgelegt: {e}]"
    if bericht["angehaengt"]:
        zeilen.append(f"angehängt: {bericht['angehaengt']} Absätze/Tabellen")
    text = (f'Geänderte Kopie „{k["titel"]}“ abgelegt (id {k["id"]}); das Original '
            f'{_herkunft(name, doc_id)} ist unverändert.\n' + "\n".join(zeilen))
    # Beleg: jeder neue Text steht da; ein ersetzter alter nicht mehr, wenn er
    # nicht im neuen steckt und kein Treffer ausgelassen wurde.
    muss = [n for (a, n), (_, z, _) in zip(paare, bericht["ersetzt"]) if z and n.strip()]
    weg = [a for (a, n), (_, z, aus) in zip(paare, bericht["ersetzt"])
           if z and not aus and a not in n and a not in anhaengen]
    if anhaengen.strip():
        muss.append(_erster_text(anhaengen))
    return _belegt(text, status, _docx_beleg(k["id"], muss, weg),
                   "die Kopie liegt NICHT wie verlangt in der Ablage")
