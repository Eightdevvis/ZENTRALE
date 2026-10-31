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
# (dieselbe Reihenfolge wie Listen-Ansicht und Kachel; ein Ordner oben → sein
# oberstes offenes Blatt). Die Regel gehört den Listen: seit 2026-10-31
# (lists step 3) fragt der Kalender sie über lists.resolve (= POST
# /api/lists/aufloesen, Regel in listen_baum.resolve). Billig: je
# Kalender-Abruf EIN Aufruf für alle Quellen (liest nie schreibend).
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md).

import re

import adressen
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
# Since lists step 3 (2026-10-31) WHAT is on top is asked from the lists
# (lists.resolve = POST /api/lists/aufloesen, the rule in listen_baum) — the
# calendar no longer computes list logic in its own code. When the lists move
# out as an app (memory/hub/list_extraction_plan.md step 5), only _resolve
# turns into an HTTP call.
def _resolve(ids: list, n: int = 0) -> list | None:
    """Ask the lists once for all ids → [{zustand, titel, name, eintrag,
    offene, projekt}] — or None (lists unreadable: everything "fehlt")."""
    if not ids:
        return []
    try:
        return lists.resolve(ids, n)
    except Exception:
        return None


def _formed(quelle) -> dict | None:
    try:
        return form(quelle)
    except KalenderAbgelehnt:
        return None


def _answer(r: dict | None, rueckfall) -> dict:
    if r is None or r["zustand"] == FEHLT:
        return {"titel": rueckfall, "quelle_name": rueckfall, "zustand": FEHLT, "eintrag": None}
    return {"titel": r["titel"], "quelle_name": r["name"], "zustand": r["zustand"],
            "eintrag": r["eintrag"]}


def aufloesen(quelle, rueckfall: str | None = None) -> dict:
    """Eine Quelle jetzt auflösen →
      {"titel", "quelle_name", "zustand": "ok"|"leer"|"fehlt", "eintrag"}
    ok:    titel = oberster offener Punkt, eintrag = {"liste", "id"} (zum Abhaken)
    leer:  titel = "<Name> — alles erledigt"
    fehlt: Liste/Eintrag gelöscht (oder unlesbar) → titel = `rueckfall`."""
    q = _formed(quelle)
    found = _resolve([q["id"]]) if q else None
    return _answer(found[0] if found else None, rueckfall)


def pruefen(quelle) -> tuple[dict, str]:
    """Zum Setzen: Form UND Existenz → (quelle, name). QUELLE-UNBEKANNT, wenn
    es die Liste nicht gibt bzw. der Knoten kein Projekt ist."""
    q = form(quelle)
    found = _resolve([q["id"]])
    r = found[0] if found else None
    if r is None or r["zustand"] == FEHLT:
        raise KalenderAbgelehnt("QUELLE-UNBEKANNT", f"{q['art']} {q['id']!r} gibt es nicht")
    if q["art"] == PROJEKT and not r["projekt"]:
        raise KalenderAbgelehnt("QUELLE-UNBEKANNT", f"{q['id']!r} ist kein Projekt")
    return q, r["name"]


def vorschau(quelle, n: int = 4) -> dict:
    """Für GET /api/calendar/quelle (Ansehen in der TUI, 10.10.2026): Name,
    Zustand und die ersten `n` offenen Punkte als Text —
    {"name", "zustand", "punkte": [...]}. Schreibt nie."""
    n = max(1, min(int(n or 4), 20))
    q = _formed(quelle)
    found = _resolve([q["id"]], n) if q else None
    r = found[0] if found else None
    a = _answer(r, None)
    if a["zustand"] != OK:
        return {"name": a["quelle_name"], "zustand": a["zustand"], "punkte": []}
    return {"name": r["name"], "zustand": OK, "punkte": r["offene"] or [r["titel"]]}


# ── An Ausgaben hängen ─────────────────────────────────────────────────
def anreichern(eintraege) -> None:
    """Jedem Eintrag mit `quelle` titel_live, quelle_name, quelle_zustand und
    quelle_eintrag dazuschreiben (im Dict). Die Listen einmal fragen, jede
    Quelle einmal auflösen; `label` bleibt der gespeicherte Rückfall."""
    mit = [e for e in eintraege if isinstance(e, dict) and e.get("quelle")]
    if not mit:
        return
    keys = {}
    for e in mit:
        q = e["quelle"]
        key = (q.get("art"), q.get("id")) if isinstance(q, dict) else repr(q)
        if key not in keys:
            keys[key] = _formed(q)
    ids = sorted({q["id"] for q in keys.values() if q})
    found = _resolve(ids)
    by_id = dict(zip(ids, found)) if found is not None else {}
    for e in mit:
        q = e["quelle"]
        key = (q.get("art"), q.get("id")) if isinstance(q, dict) else repr(q)
        formed = keys[key]
        r = _answer(by_id.get(formed["id"]) if formed else None, None)
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
    try:
        listen = lists.read_lists() or []
    except Exception:
        listen = []
    wanted = []                                   # (art, id) in display order

    def projekte(items, lid):
        for it in items or []:
            if not isinstance(it, dict):
                continue
            if it.get("project") and isinstance(it.get("id"), int):
                wanted.append((PROJEKT, f"{lid}/{it['id']}"))
            projekte(it.get("items"), lid)

    ok_lists = [l for l in listen if isinstance(l, dict) and isinstance(l.get("id"), str)
                and _ID[LISTE].match(l["id"])]
    n_lists = len(ok_lists)
    wanted += [(LISTE, l["id"]) for l in ok_lists]
    for l in ok_lists:
        if l.get("project"):
            wanted.append((PROJEKT, l["id"]))
        projekte(l.get("items"), l["id"])
    found = _resolve([qid for _art, qid in wanted]) or [None] * len(wanted)
    rows = []
    for (art, qid), r in zip(wanted, found):
        a = _answer(r, None)
        rows.append({"art": art, "id": qid, "name": a["quelle_name"], "titel": a["titel"],
                     "zustand": a["zustand"]})
    return {"listen": rows[:n_lists], "projekte": rows[n_lists:]}
