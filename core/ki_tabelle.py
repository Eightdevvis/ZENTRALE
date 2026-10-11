# core/ki_tabelle.py
#
# Was die Tabellen-Werkzeuge der KI TUN (Skill excel): read_xlsx,
# create_xlsx, edit_xlsx — Excel (.xlsx) und CSV, alles über die Ablage.
# Einträge und Fragen: core/werkzeug_tabelle.py; das Handwerk:
# core/tabelle_datei.py (openpyxl im Kindprozess), core/tabelle_formel.py.
#
# 2026-10-11, Führerschein-Gespräch 20261011-081303: Sasha wollte Kosten und
# Stunden tracken; die KI hatte nur PDFs, legte bei jeder Änderung eine
# Kopie an und erklärte ihm danach SUMMEWENN zum Abtippen. Jetzt:
#   - Formeln stehen im Excel-Standard in der Datei (englisch, Komma);
#     deutsche Eingaben werden sicher übersetzt (tabelle_formel), und der
#     Satz sagt, was übersetzt wurde. Werte rechnet openpyxl nicht — der Satz
#     nennt Formeln als Formeln, nie ein ausgedachtes Ergebnis.
#   - Ändern ersetzt (eigene Tabelle: frei, das alte in den Papierkorb;
#     Sashas: nur nach seinem Ja) oder legt mit daneben=true eine neue an.
#     Eine CSV ist Text: sie bekommt eine neue Fassung (die alte bleibt).
#   - Jede neue Datei wird NACH dem Ablegen aus der Ablage gelesen — erst das
#     ist der Beleg; stimmt es nicht, ist alles wie vorher.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import math
import os
import re
import shutil

import ablage
import schreib_sicherung
import tabelle_datei
import tabelle_formel
import werkzeug_register
import zug
from werkzeug_befund import Befund, OK, erledigt, abgebrochen

ausfuehrer = werkzeug_register.ausfuehrer

# Fehler-Arten aus tabelle_datei → Codes (core/fehlercodes.py).
_CODE = {"kaputt": "T-DATEI-KAPUTT", "gesperrt": "T-GESPERRT", "bibliothek": "T-BIBLIOTHEK",
         "zeit": "T-ZEIT", "zu_gross": "T-ZU-GROSS", "blatt": "T-BLATT-UNBEKANNT",
         "bereich": "T-BEREICH", "zelle": "T-ZELLE", "verlust": "T-VERLUST"}
_BLATT_VERBOTEN = re.compile(r"[\[\]:*?/\\]")
# Zahlen, die als Text kamen: „60", „60,5", „-3.25". Drei Nachkommastellen
# bleiben Text („1.000" ist im Deutschen tausend, nicht eins).
_ZAHL = re.compile(r"^-?(0|[1-9]\d{0,14})([.,](\d{1,2}|\d{4,}))?$")


class _Abbruch(Exception):
    def __init__(self, code: str, grund: str):
        super().__init__(grund)
        self.code, self.grund = code, grund


# ── Werte prüfen ────────────────────────────────────────────────────────

def _wert(v, wo: str, formeln: list, uebersetzt: list, csv: bool = False):
    """Ein Zellwert, wie er in die Datei darf. Formeln (Text mit =) werden
    übersetzt und gesammelt."""
    if v is None or (isinstance(v, str) and v == ""):
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        if isinstance(v, float) and not math.isfinite(v):
            raise _Abbruch("T-WERT-UNGUELTIG", f"{wo}: {v} ist keine Zahl")
        return v
    if not isinstance(v, str):
        raise _Abbruch("T-WERT-UNGUELTIG", f"{wo}: nur Text, Zahl, wahr/falsch oder leer")
    if len(v) > tabelle_datei.MAX_ZELLE_ZEICHEN:
        raise _Abbruch("T-WERT-UNGUELTIG", f"{wo}: mehr als {tabelle_datei.MAX_ZELLE_ZEICHEN} "
                                           f"Zeichen passen nicht in eine Zelle")
    if v.startswith("="):
        if csv:
            raise _Abbruch("T-CSV-FORMEL", f"{wo}: eine CSV speichert keine Formeln — xlsx nehmen")
        try:
            en, was = tabelle_formel.uebersetzen(v)
        except tabelle_formel.FormelFehler as e:
            raise _Abbruch("T-FORMEL", f"{wo} {v[:60]}: {e}")
        formeln.append((wo, en))
        uebersetzt += [w for w in was if w not in uebersetzt]
        return en
    if _ZAHL.match(v.strip()):
        t = v.strip().replace(",", ".")
        return float(t) if "." in t else int(t)
    return v


def _zeilen(roh, wo: str, formeln, uebersetzt, csv=False) -> list:
    if not isinstance(roh, list):
        raise _Abbruch("T-WERT-UNGUELTIG", f"{wo}: zeilen ist eine Liste von Zeilen")
    raus = []
    for zi, reihe in enumerate(roh, start=1):
        if not isinstance(reihe, list):
            reihe = [reihe]
        raus.append([_wert(v, f"{wo}{tabelle_datei.adresse(zi, si) if wo.endswith('!') else ''}",
                           formeln, uebersetzt, csv)
                     for si, v in enumerate(reihe, start=1)])
    return raus


def _blattname(name, i: int, gesehen: set) -> str:
    n = " ".join(str(name or "").split()) or f"Tabelle{i}"
    if len(n) > 31 or _BLATT_VERBOTEN.search(n) or n.startswith("'"):
        raise _Abbruch("T-BLATTNAME", f"Blattname „{n[:40]}“: höchstens 31 Zeichen, ohne "
                                      f"[ ] : * ? / \\")
    if n.lower() in gesehen:
        raise _Abbruch("T-BLATTNAME", f"Blattname „{n}“ kommt doppelt vor")
    gesehen.add(n.lower())
    return n


def _zellen_zahl(blaetter) -> int:
    return sum(len(r) for b in blaetter for r in b["zeilen"])


# ── Quelle ──────────────────────────────────────────────────────────────

def _dokument(doc_id) -> dict:
    doc_id = str(doc_id or "").strip()
    if not doc_id or not ablage.gibt_es(doc_id):
        raise _Abbruch("A-DOK-UNBEKANNT", "kein Dokument mit dieser id in der Ablage")
    k = ablage.kopf(doc_id)
    if k.get("art") not in ("xlsx", "csv"):
        raise _Abbruch("T-FALSCHE-ART", f"„{k.get('titel')}“ ist keine Tabelle (Art "
                                        f"{k.get('art')}) — read_document/read_pdf/read_docx")
    return k


def _lesen(k: dict, blatt=None, bereich=None) -> dict:
    try:
        if k["art"] == "csv":
            zeilen, trenner = tabelle_datei.csv_lesen(ablage.lesen(k["id"])["inhalt"])
            r = tabelle_datei.csv_zellen(zeilen, bereich)
            r["trenner"] = trenner
            return r
        return tabelle_datei.lesen(ablage.roh(k["id"]), blatt, bereich)
    except tabelle_datei.Fehler as e:
        raise _Abbruch(_CODE.get(e.art, "T-DATEI-KAPUTT"), str(e))


# ── read_xlsx ───────────────────────────────────────────────────────────

@ausfuehrer("read_xlsx")
def _read_xlsx(args: dict):
    try:
        k = _dokument(args.get("id"))
        r = _lesen(k, args.get("blatt"), args.get("bereich"))
    except _Abbruch as e:
        return abgebrochen("Tabelle lesen", e.code, e.grund, "nichts gelesen")
    art = "CSV" + (f" (Trenner „{r['trenner']}“)" if r.get("trenner") else "") \
        if k["art"] == "csv" else "Excel"
    kopf = (f"„{k.get('titel')}“ (Ablage-id {k['id']}): {art}. {tabelle_datei.kopf_text(r)}\n"
            f"Blatt „{r['blatt']}“, Bereich {r['bereich']} — Text in \"…\", Formeln mit dem in "
            f"der Datei gespeicherten Wert hinter →:")
    text = tabelle_datei.als_text(r) or "(keine gefüllte Zelle in diesem Bereich)"
    weiter = f"\n[weiter mit bereich={r['weiter']}]" if r.get("weiter") else ""
    return Befund(f"{kopf}\n{text}{weiter}", OK)


# ── create_xlsx ─────────────────────────────────────────────────────────

def _blaetter(roh, csv: bool) -> tuple:
    """→ (blaetter, formeln [(wo, formel)], uebersetzt). Wirft _Abbruch."""
    if not isinstance(roh, list) or not roh:
        raise _Abbruch("T-BLAETTER-FEHLEN", "blaetter fehlt (mindestens eins mit zeilen)")
    if len(roh) > (1 if csv else tabelle_datei.MAX_BLAETTER):
        raise _Abbruch("T-ZU-VIEL", "eine CSV hat genau ein Blatt" if csv else
                       f"höchstens {tabelle_datei.MAX_BLAETTER} Blätter")
    formeln, uebersetzt, gesehen, raus = [], [], set(), []
    for i, b in enumerate(roh, start=1):
        b = b if isinstance(b, dict) else {"zeilen": b}
        name = _blattname(b.get("name"), i, gesehen)
        zeilen = _zeilen(b.get("zeilen") or [], f"{name}!", formeln, uebersetzt, csv)
        breiten = b.get("spaltenbreiten") if isinstance(b.get("spaltenbreiten"), list) else []
        breiten = [max(1.0, min(255.0, float(x))) if isinstance(x, (int, float)) else None
                   for x in breiten[:200]]
        raus.append({"name": name, "zeilen": zeilen, "spaltenbreiten": breiten})
    if _zellen_zahl(raus) > tabelle_datei.MAX_ZELLEN:
        raise _Abbruch("T-ZU-VIEL", f"höchstens {tabelle_datei.MAX_ZELLEN} Zellen je Aufruf")
    if not any(any(v is not None for v in r) for b in raus for r in b["zeilen"]):
        raise _Abbruch("T-BLAETTER-FEHLEN", "alle Zeilen sind leer")
    return raus, formeln, uebersetzt


def _soll(blaetter) -> dict:
    """{(blatt, adresse): wert} — was nachgelesen dastehen muss."""
    soll = {}
    for b in blaetter:
        for zi, reihe in enumerate(b["zeilen"], start=1):
            for si, v in enumerate(reihe, start=1):
                if v is not None:
                    soll[(b["name"], tabelle_datei.adresse(zi, si))] = v
    return soll


def _gleich(soll, ist) -> bool:
    zahl = isinstance(soll, (int, float)) and not isinstance(soll, bool)
    if zahl and isinstance(ist, str):          # CSV: „60,5"
        try:
            ist = float(ist.strip().replace(",", "."))
        except ValueError:
            return False
    if zahl and isinstance(ist, (int, float)) and not isinstance(ist, bool):
        return abs(float(soll) - float(ist)) < 1e-9
    if isinstance(soll, bool) or isinstance(ist, bool):
        return soll == ist
    return str(soll) == str(ist)


def _nachlesen(k: dict, soll: dict, blaetter_namen) -> str | None:
    """Beleg aus der Ablage — oder None, wenn etwas nicht so dasteht."""
    gelesen = 0
    for name in blaetter_namen:
        try:
            r = _lesen(k, None if k["art"] == "csv" else name)
        except _Abbruch:
            return None
        ist = {(name, a): (f if f else w) for a, w, f, _b in r["zellen"]}
        for (bl, adr), v in soll.items():
            if bl != name or (bl, adr) not in ist and r.get("weiter"):
                continue
            if (bl, adr) not in ist or not _gleich(v, ist[(bl, adr)]):
                return None
        gelesen += len(r["zellen"])
    return f"liegt in der Ablage (id {k['id']}); nachgelesen: {gelesen} gefüllte Zellen wie verlangt."


def _formel_satz(formeln, uebersetzt) -> str:
    if not formeln:
        return ""
    zeigen = "; ".join(f"{wo} {tabelle_formel.anzeigen(f)}" for wo, f in formeln[:6])
    mehr = f" (+{len(formeln) - 6} weitere)" if len(formeln) > 6 else ""
    ueber = f" Übersetzt in den Excel-Standard: {', '.join(uebersetzt)}." if uebersetzt else ""
    return (f" Formeln (Excel rechnet sie beim Öffnen; hier ist KEIN Wert berechnet): "
            f"{zeigen}{mehr}.{ueber}")


def _weg(k: dict) -> None:
    shutil.rmtree(os.path.join(ablage.ordner(), k["id"]), ignore_errors=True)


@ausfuehrer("create_xlsx")
def _create_xlsx(args: dict):
    titel = " ".join(str(args.get("titel") or "").split()) or "Tabelle"
    csv = str(args.get("format") or "xlsx").strip().lower() == "csv"
    was = f"{'CSV' if csv else 'Excel-Tabelle'} „{titel}“ anlegen"
    try:
        blaetter, formeln, uebersetzt = _blaetter(args.get("blaetter"), csv)
        if csv:
            blaetter[0]["name"] = "CSV"          # eine CSV hat kein benanntes Blatt
            inhalt, art = tabelle_datei.csv_schreiben(blaetter[0]["zeilen"]), "csv"
        else:
            inhalt, art = tabelle_datei.erzeugen(blaetter), "xlsx"
    except _Abbruch as e:
        return abgebrochen(was, e.code, e.grund, "nichts angelegt")
    except tabelle_datei.Fehler as e:
        return abgebrochen(was, _CODE.get(e.art, "T-DATEI-KAPUTT"), str(e), "nichts angelegt")
    try:
        k = ablage.anlegen(titel, inhalt, art, herkunft="ki", gespraech=zug.gespraech())
    except ablage.Fehler as e:
        return abgebrochen(was, "T-ABGELEHNT", str(e), "nichts angelegt")
    beleg = _nachlesen(k, _soll(blaetter), [b["name"] for b in blaetter])
    if beleg is None:
        _weg(k)
        return abgebrochen(was, "W-NICHT-GESPEICHERT", "nachgelesen stand es nicht so da; "
                           "wieder entfernt", "nichts angelegt")
    zug.melden({"ablage": ablage.kurz(k)})
    bl = ", ".join(f"{b['name']} ({len(b['zeilen'])} Zeilen)" for b in blaetter)
    satz = (f"{'CSV' if csv else 'Excel-Tabelle'} „{k['titel']}“ ANGELEGT (id {k['id']}): "
            f"{bl}.{_formel_satz(formeln, uebersetzt)} Nachgelesen: {beleg}")
    return erledigt(satz, beleg, zusatz="Sasha sieht sie im Chat und in seinem Ablage-Ordner; "
                                        "wiederhole den Inhalt nicht.")


# ── edit_xlsx ───────────────────────────────────────────────────────────

def daneben(args: dict) -> bool:
    v = args.get("daneben")
    return v is True or str(v).strip().lower() in ("true", "1", "ja")


def _aenderungen(args, csv: bool) -> tuple:
    """→ (aenderungen [{blatt, zelle, wert}], anhaengen [{blatt, zeilen}],
    formeln, uebersetzt)."""
    formeln, uebersetzt, aend, anh = [], [], [], []
    roh = args.get("aenderungen") if isinstance(args.get("aenderungen"), list) else []
    for a in roh:
        if not isinstance(a, dict):
            raise _Abbruch("T-WERT-UNGUELTIG", "jede Änderung ist {blatt?, zelle, wert}")
        try:
            z, s = tabelle_datei.zelle_zerlegen(a.get("zelle"))
        except tabelle_datei.Fehler as e:
            raise _Abbruch("T-ZELLE", str(e))
        zelle = tabelle_datei.adresse(z, s)
        blatt = str(a.get("blatt") or "").strip() or None
        wo = f"{blatt}!{zelle}" if blatt else zelle
        aend.append({"blatt": blatt, "zelle": zelle,
                     "wert": _wert(a.get("wert"), wo, formeln, uebersetzt, csv)})
    if args.get("anhaengen") not in (None, "", []):
        blatt = str(args.get("blatt") or "").strip() or None
        anh.append({"blatt": blatt, "zeilen": _zeilen(args.get("anhaengen"), "anhaengen",
                                                       formeln, uebersetzt, csv)})
    if not aend and not anh:
        raise _Abbruch("T-NICHTS-ZU-AENDERN", "weder aenderungen noch anhaengen angegeben")
    if len(aend) + sum(len(r) for a in anh for r in a["zeilen"]) > tabelle_datei.MAX_ZELLEN:
        raise _Abbruch("T-ZU-VIEL", f"höchstens {tabelle_datei.MAX_ZELLEN} Zellen je Aufruf")
    return aend, anh, formeln, uebersetzt


def _csv_aendern(k: dict, aend, anh) -> tuple:
    """→ (text, angehaengt [{blatt, von, bis}])."""
    zeilen, trenner = tabelle_datei.csv_lesen(ablage.lesen(k["id"])["inhalt"])
    for a in aend:
        z, s = tabelle_datei.zelle_zerlegen(a["zelle"])
        while len(zeilen) < z:
            zeilen.append([])
        while len(zeilen[z - 1]) < s:
            zeilen[z - 1].append("")
        zeilen[z - 1][s - 1] = "" if a["wert"] is None else a["wert"]
    angehaengt = []
    for a in anh:
        while zeilen and not any(str(v).strip() for v in zeilen[-1]):
            zeilen.pop()
        von = len(zeilen) + 1
        zeilen += [list(r) for r in a["zeilen"]]
        angehaengt.append({"blatt": "CSV", "von": von, "bis": len(zeilen)})
    return tabelle_datei.csv_schreiben(zeilen, trenner), angehaengt


def _soll_aenderung(aend, angehaengt, anh, namen: list) -> dict:
    soll = {}
    gross = {n.lower(): n for n in namen}
    for a in aend:
        if a["wert"] is not None:
            blatt = gross.get(str(a["blatt"] or "").lower(), namen[0])
            soll[(blatt, a["zelle"])] = a["wert"]
    for a, wo in zip(anh, angehaengt):
        for i, reihe in enumerate(a["zeilen"]):
            for si, v in enumerate(reihe, start=1):
                if v is not None:
                    soll[(wo["blatt"], tabelle_datei.adresse(wo["von"] + i, si))] = v
    return soll


def _was_satz(aend, angehaengt) -> str:
    teile = []
    for a in aend[:5]:
        wo = f"{a['blatt']}!{a['zelle']}" if a["blatt"] else a["zelle"]
        teile.append(f"{wo} = {tabelle_datei.wert_text(a['wert']) if a['wert'] is not None else '(leer)'}")
    if len(aend) > 5:
        teile.append(f"+{len(aend) - 5} weitere Zellen")
    for wo in angehaengt:
        n = wo["bis"] - wo["von"] + 1
        teile.append(f"{n} Zeile{'n' if n != 1 else ''} angehängt ({wo['blatt']}, Zeile "
                     f"{wo['von']}{'–' + str(wo['bis']) if n > 1 else ''})")
    return "; ".join(teile)


@ausfuehrer("edit_xlsx")
def _edit_xlsx(args: dict):
    was = "Tabelle ändern"
    try:
        k = _dokument(args.get("id"))
        was = f"„{k.get('titel')}“ ändern"
        csv = k["art"] == "csv"
        aend, anh, formeln, uebersetzt = _aenderungen(args, csv)
        if csv:
            neu_inhalt, angehaengt = _csv_aendern(k, aend, anh)
            namen = ["CSV"]
        else:
            neu_inhalt, bericht = tabelle_datei.aendern(ablage.roh(k["id"]), aend, anh)
            angehaengt, namen = bericht["angehaengt"], bericht["blaetter"]
    except _Abbruch as e:
        return abgebrochen(was, e.code, e.grund)
    except tabelle_datei.Fehler as e:
        return abgebrochen(was, _CODE.get(e.art, "T-DATEI-KAPUTT"), str(e))
    if csv:
        aend = [dict(a, blatt="CSV") for a in aend]
    soll = _soll_aenderung(aend, angehaengt, anh, namen)
    titel = " ".join(str(args.get("titel") or "").split())
    sicherung, alt_weg = None, False
    try:
        if daneben(args):
            k_neu = ablage.anlegen(titel or f"{k.get('titel')} (geändert)", neu_inhalt, k["art"],
                                   herkunft="ki", gespraech=zug.gespraech(),
                                   quelle=f"geändert aus {k.get('titel')}")
            wie = f"als NEUE Tabelle daneben (id {k_neu['id']}); das Original ist unverändert"
        elif csv:
            sicherung = schreib_sicherung.Sicherung(ordner=[os.path.join(ablage.ordner(), k["id"])])
            k_neu = ablage.neue_fassung(k["id"], neu_inhalt)
            wie = f"als Fassung {k_neu['fassung']} (die alte bleibt erhalten)"
        else:
            k_neu, _ = ablage.ersetzen(k["id"], neu_inhalt, titel=titel or None, art="xlsx",
                                       gespraech=zug.gespraech(),
                                       quelle=f"neue Fassung von {k.get('titel')}")
            alt_weg = True
            wie = (f"als neue Fassung (id {k_neu['id']}); die alte ({k['id']}) liegt im "
                   f"Papierkorb, zurück mit restore_document")
    except ablage.Fehler as e:
        if sicherung:
            sicherung.zurueck()
        return abgebrochen(was, "T-ABGELEHNT", str(e))
    beleg = _nachlesen(k_neu, soll, sorted({bl for bl, _ in soll}) or namen[:1])
    if beleg is None:
        if sicherung:
            sicherung.zurueck()
        else:
            _weg(k_neu)
            if alt_weg:
                ablage.papierkorb(k["id"], False)
        return abgebrochen(was, "W-NICHT-GESPEICHERT", "nachgelesen stand es nicht so da; "
                           "alles ist wie vorher")
    zug.melden({"ablage": ablage.kurz(k_neu)})
    satz = (f"„{k_neu.get('titel')}“ GEÄNDERT {wie}: {_was_satz(aend, angehaengt)}."
            f"{_formel_satz(formeln, uebersetzt)} Nachgelesen: {beleg}")
    return erledigt(satz, beleg)
