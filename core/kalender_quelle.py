# core/kalender_quelle.py
#
# Ein Termin, dessen Titel aus einer Liste oder einem Projekt kommt.
#
# Sasha, 10.10.2026: „ich hab im kalender den variablen container der todo
# liste drin stehen, und im kalender wird als termintitel einfach das höchste
# item angezeigt. wenn ich die liste umsortiere dann ändert sich der
# containertitel mit … diese zeit ist für genau diesen schritt von diesem
# projekt." Ein Zeitfenster wählt also nur eine Liste (bzw. ein Projekt); der
# Titel wird bei jedem Lesen LIVE aufgelöst — der Kalender wird beim
# Umsortieren oder Abhaken nie geschrieben (Leitlinie „dasselbe Objekt,
# nicht kopiert": der Termin verweist aufs Original).
#
# Datenmodell (an Einmal-Termin, Spanne, Routine; nie an Phasen):
#   quelle = {"art": "liste",   "id": "<liste>"}
#          | {"art": "projekt", "id": "<liste>" | "<liste>/<eintrag>"}
#   label  = Rückfall-Titel (Name der Liste/des Projekts) — das zeigen Google
#            und das Handy, und das gilt, wenn die Quelle gelöscht ist.
# „Projekt" = ein als Projekt markierter Knoten der Listen (lists.projects_tree,
# PROJECTS-Box, /api/projects): eine ganze Liste oder ein Eintrag darin. Die
# Projekte der KI (core/projekte.py) haben keine Schritte und zählen nicht.
#
# .ics (core/kalender_ics_abbildung.py): X-ZENTRALE-QUELLE:<art>:<id> und
# URL:zentrale://fokus/<liste>[/<eintrag>] (die Adresse des Objekts,
# core/adressen.py, wie die Listen-Kachel sie nennt).
#
# Auflösung: oberstes OFFENES Blatt in Anzeige-Reihenfolge der Listen
# (listen_baum.ordnen — dieselbe Reihenfolge wie Listen-Ansicht und Kachel;
# ein Ordner oben → sein oberstes offenes Blatt). Billig: die Listen werden
# je Kalender-Abruf höchstens EINMAL gelesen (lists.read_lists, schreibt
# garantiert nicht), jede Quelle einmal aufgelöst.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import re

import adressen
import listen_baum
import lists
from kalender_fehler import KalenderAbgelehnt

LISTE, PROJEKT = "liste", "projekt"
ARTEN = (LISTE, PROJEKT)
APP = "fokus"                    # Adresse einer Liste: zentrale://fokus/<liste>

OK, LEER, FEHLT = "ok", "leer", "fehlt"

_LID = r"[A-Za-z0-9_\-]{1,80}"
_ID = {LISTE: re.compile(rf"^{_LID}$"),
       PROJEKT: re.compile(rf"^{_LID}(/[0-9]{{1,9}})?$")}


# ── Form (rein) ────────────────────────────────────────────────────────
def form(quelle) -> dict:
    """Die FORM einer Angabe prüfen (ohne nachzusehen, ob es sie gibt) →
    {"art", "id"}. Codes: QUELLE-ART-UNBEKANNT, QUELLE-UNGUELTIG."""
    if not isinstance(quelle, dict):
        raise KalenderAbgelehnt("QUELLE-UNGUELTIG", f"quelle {quelle!r} ist kein {{art, id}}")
    art = quelle.get("art")
    art = art.strip().lower() if isinstance(art, str) else art
    if art not in ARTEN:
        raise KalenderAbgelehnt("QUELLE-ART-UNBEKANNT",
                                f"art {quelle.get('art')!r}; erlaubt: {', '.join(ARTEN)}")
    qid = quelle.get("id")
    qid = str(qid).strip() if isinstance(qid, (str, int)) and not isinstance(qid, bool) else ""
    if not _ID[art].match(qid):
        raise KalenderAbgelehnt("QUELLE-UNGUELTIG", f"id {quelle.get('id')!r} passt nicht zu {art}")
    falsch = set(quelle) - {"art", "id"}
    if falsch:
        raise KalenderAbgelehnt("UNBEKANNTES-FELD", "quelle: " + ", ".join(sorted(falsch)))
    return {"art": art, "id": qid}


def sauber(q) -> bool:
    """Steht die Quelle genau so da, wie form() sie schreibt? Nur dann bildet
    die .ics-Abbildung sie auf eigene Properties ab (sonst Extras)."""
    try:
        return form(q) == q
    except KalenderAbgelehnt:
        return False


def als_text(q: dict) -> str:
    """{"art": "liste", "id": "l_todo"} → "liste:l_todo" (X-ZENTRALE-QUELLE)."""
    return f"{q['art']}:{q['id']}"


def aus_text(text) -> dict | None:
    art, _, qid = str(text or "").partition(":")
    try:
        return form({"art": art, "id": qid})
    except KalenderAbgelehnt:
        return None


def adresse(q: dict) -> str:
    """Die Adresse des Objekts: zentrale://fokus/<liste>[/<eintrag>]."""
    return adressen.bauen(APP, q["id"].split("/"))


def aus_adresse(text) -> dict | None:
    """Rückweg aus URL, falls ein Server X-ZENTRALE-QUELLE verliert. Ein
    Abschnitt = Liste, zwei = Projekt-Eintrag (eine ganze Liste als Projekt
    kommt so als „liste" zurück — gleiche Auflösung)."""
    try:
        a = adressen.lesen(str(text))
    except adressen.AdresseFehler:
        return None
    if a.app != APP or a.abfrage or len(a.pfad) not in (1, 2):
        return None
    try:
        return form({"art": LISTE if len(a.pfad) == 1 else PROJEKT, "id": "/".join(a.pfad)})
    except KalenderAbgelehnt:
        return None


# ── Nachsehen ──────────────────────────────────────────────────────────
def _knoten(q: dict, listen: list):
    """(knoten, name, lid) — die Liste bzw. der Projekt-Eintrag — oder None."""
    lid, _, iid = q["id"].partition("/")
    lst = next((l for l in listen if isinstance(l, dict) and l.get("id") == lid), None)
    if lst is None:
        return None
    if not iid:
        return lst, lst.get("name") or lid, lid
    it = listen_baum.finden(lst.get("items"), int(iid))
    if it is None:
        return None
    return it, it.get("text") or iid, lid


def oberstes(items):
    """Das oberste offene BLATT in Anzeige-Reihenfolge (oder None)."""
    reihe = listen_baum.ordnen(items)
    if not reihe:
        return None
    it = reihe[0]
    kids = it.get("items") if isinstance(it.get("items"), list) else []
    return oberstes(kids) if kids else it


def _listen_lesen() -> list | None:
    try:
        return lists.read_lists()
    except Exception:
        return None


def aufloesen(quelle, rueckfall: str | None = None, listen: list | None = None) -> dict:
    """Eine Quelle jetzt auflösen →
      {"titel", "quelle_name", "zustand": "ok"|"leer"|"fehlt", "eintrag"}
    ok:    titel = oberster offener Punkt, eintrag = {"liste", "id"} (zum Abhaken)
    leer:  titel = "<Name> — alles erledigt"
    fehlt: Liste/Eintrag gelöscht (oder unlesbar) → titel = `rueckfall`."""
    if listen is None:
        listen = _listen_lesen()
    try:
        q = form(quelle)
    except KalenderAbgelehnt:
        q = None
    treffer = _knoten(q, listen) if q and listen is not None else None
    if treffer is None:
        return {"titel": rueckfall, "quelle_name": rueckfall, "zustand": FEHLT, "eintrag": None}
    knoten, name, lid = treffer
    blatt = oberstes(knoten.get("items"))
    if blatt is None:
        if q["art"] == PROJEKT and "/" in q["id"] and not listen_baum.erledigt(knoten):
            # ein Projekt-Eintrag ohne Unterpunkte IST selbst der Schritt
            return {"titel": name, "quelle_name": name, "zustand": OK,
                    "eintrag": {"liste": lid, "id": knoten.get("id")}}
        return {"titel": f"{name} — alles erledigt", "quelle_name": name,
                "zustand": LEER, "eintrag": None}
    return {"titel": blatt.get("text") or "?", "quelle_name": name, "zustand": OK,
            "eintrag": {"liste": lid, "id": blatt.get("id")}}


def pruefen(quelle) -> tuple[dict, str]:
    """Zum Setzen: Form UND Existenz → (quelle, name). QUELLE-UNBEKANNT, wenn
    es die Liste nicht gibt bzw. der Knoten kein Projekt ist."""
    q = form(quelle)
    listen = _listen_lesen() or []
    treffer = _knoten(q, listen)
    if treffer is None:
        raise KalenderAbgelehnt("QUELLE-UNBEKANNT", f"{q['art']} {q['id']!r} gibt es nicht")
    knoten, name, _lid = treffer
    if q["art"] == PROJEKT and not knoten.get("project"):
        raise KalenderAbgelehnt("QUELLE-UNBEKANNT", f"{q['id']!r} ist kein Projekt")
    return q, name


# ── An Ausgaben hängen ─────────────────────────────────────────────────
def anreichern(eintraege) -> None:
    """Jedem Eintrag mit `quelle` titel_live, quelle_name, quelle_zustand und
    quelle_eintrag dazuschreiben (im Dict). Listen einmal lesen, jede Quelle
    einmal auflösen; `label` bleibt der gespeicherte Rückfall."""
    mit = [e for e in eintraege if isinstance(e, dict) and e.get("quelle")]
    if not mit:
        return
    listen = _listen_lesen()
    gemerkt = {}
    for e in mit:
        q = e["quelle"]
        schl = (q.get("art"), q.get("id")) if isinstance(q, dict) else repr(q)
        if schl not in gemerkt:
            gemerkt[schl] = aufloesen(q, None, listen)
        r = gemerkt[schl]
        e["titel_live"] = r["titel"] or e.get("label")
        e["quelle_name"] = r["quelle_name"] or e.get("label")
        e["quelle_zustand"] = r["zustand"]
        e["quelle_eintrag"] = r["eintrag"]


def anzeige_titel(e: dict) -> str:
    """Titel für Lesetexte (KI, Imprint): „Steuern planen (aus Liste: todo)";
    ohne Quelle das label."""
    label = e.get("label") or "?"
    if not e.get("quelle") or "titel_live" not in e:
        return label
    art = (e["quelle"].get("art") if isinstance(e["quelle"], dict) else None) or LISTE
    wort = "Projekt" if art == PROJEKT else "Liste"
    if e.get("quelle_zustand") == FEHLT:
        return f"{label} ({wort} gibt es nicht mehr)"
    return f"{e['titel_live']} (aus {wort}: {e.get('quelle_name') or label})"


def auswahl() -> dict:
    """Für GET /api/calendar/quellen: alle Listen und Projekte mit dem, was
    jetzt oben steht. {"listen": [...], "projekte": [...]}, je
    {art, id, name, titel, zustand}."""
    listen = _listen_lesen() or []

    def zeile(art, qid):
        r = aufloesen({"art": art, "id": qid}, None, listen)
        return {"art": art, "id": qid, "name": r["quelle_name"], "titel": r["titel"],
                "zustand": r["zustand"]}

    raus_l = [zeile(LISTE, l["id"]) for l in listen
              if isinstance(l, dict) and isinstance(l.get("id"), str) and _ID[LISTE].match(l["id"])]
    raus_p = []

    def projekte(items, lid):
        for it in items or []:
            if not isinstance(it, dict):
                continue
            if it.get("project") and isinstance(it.get("id"), int):
                raus_p.append(zeile(PROJEKT, f"{lid}/{it['id']}"))
            projekte(it.get("items"), lid)

    for l in listen:
        if not (isinstance(l, dict) and isinstance(l.get("id"), str)
                and _ID[LISTE].match(l["id"])):
            continue
        if l.get("project"):
            raus_p.append(zeile(PROJEKT, l["id"]))
        projekte(l.get("items"), l["id"])
    return {"listen": raus_l, "projekte": raus_p}
