# core/werkzeug_suche.py
#
# Die Werkzeug-Suche (2026-10-14): Anthropic nachgemacht — die KI sieht auf
# gross nur einen festen Kern von Werkzeugen (werkzeug_gruppen.IMMER), den
# Rest findet sie über search_tools. Doku und Messungen:
# memory/ki/werkzeug_suche.md.
#
# Warum: die gross-Liste hat 71 Werkzeuge mit ~45.000 Zeichen Schema. Die
# gehen in JEDEM Zug mit (gecacht, aber gelesen), und je mehr Werkzeuge,
# desto öfter greift ein Modell daneben (OpenAI: „unter 20 zu Beginn eines
# Zugs"; das qwen-Profil hat deshalb seit Runde 9 eine Vorauswahl).
#
# Was hier steht:
#   - der Index: beim Import aus dem Register gebaut (Name, Beschreibung,
#     Parameter, alltag/worte, Schlagworte der Gruppe), die aktiven Skills
#     kommen bei jeder Suche frisch dazu (Sasha schaltet sie zur Laufzeit);
#   - suchen(): BM25 in reinem Python, ein Treffer bringt seine ganze
#     Gruppe (werkzeug_gruppen.GRUPPEN), Standard 5 Treffer;
#   - das Ergebnis als Treffer (ein str mit den gefundenen Namen dran): der
#     Text geht an OpenAI und ins Protokoll, die Namen nimmt der
#     Anthropic-Adapter für tool_reference-Blöcke;
#   - die Freischaltung im Zug (Freischaltung) und über Züge hinweg (aus
#     dem Verlauf, anhang.verlauf_einsetzen);
#   - an(): die Einstellung werkzeug_suche (Standard aus).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md). Liest das Register,
# das Register liest hier nichts.

import hashlib
import json
import math
import re

import werkzeug_gruppen
import werkzeug_register

SCHALTER = werkzeug_gruppen.SCHALTER
NAME = "search_tools"
STANDARD_TREFFER = 5
# Höchstens so viele Werkzeuge schaltet EINE Suche frei (Treffer samt
# Gruppen). Die größte Gruppe (browser) hat 8.
MAX_WERKZEUGE = 16
ANTEIL = 1 / 3
# Werkzeuge, die nie ein Suchtreffer sind: die Schleife erledigt sie, und
# sie sind ohnehin immer da.
_NICHT_IM_INDEX = {"antwort", NAME}


def an() -> bool:
    """Ist die Werkzeug-Suche eingeschaltet? (Einstellung werkzeug_suche,
    an|aus, Standard aus — bis der Prüfstand gelaufen ist.)"""
    return werkzeug_gruppen.suche_an()


# ── Zerlegen ───────────────────────────────────────────────────────────

_FALTEN = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_STOPP = set("""der die das den dem des ein eine einen einem einer und oder
nicht nur mit von zu im in am an auf aus für fuer bei ist sind wird werden
als wie was wer wo es er sie ich du mir mich dir dich sein seine hat haben
kann soll auch noch schon dann wenn ob so zum zur vom über ueber nach vor
the a an of to for and or is are with from on by this that be""".split())


def worte(text: str) -> list:
    """Text → Suchwörter: klein, Umlaute gefaltet, ohne Füllwörter;
    read_calendar → read, calendar."""
    text = str(text or "").casefold().translate(_FALTEN).replace("_", " ")
    return [w for w in re.findall(r"[a-z0-9]+", text)
            if len(w) > 1 and w not in _STOPP]


# ── Der Index ──────────────────────────────────────────────────────────

class Dokument:
    """Ein Eintrag im Index: ein Werkzeug oder ein Skill."""

    def __init__(self, art: str, name: str, felder: list):
        self.art, self.name = art, name
        self.tf = {}
        for text, gewicht in felder:
            for w in worte(text):
                self.tf[w] = self.tf.get(w, 0) + gewicht
        self.laenge = sum(self.tf.values()) or 1


def _parameter_text(schema: dict) -> str:
    teile = []
    for feld, s in ((schema or {}).get("properties") or {}).items():
        teile.append(feld)
        if isinstance(s, dict):
            teile.append(str(s.get("description") or ""))
    return " ".join(teile)


def _werkzeug_dokument(w) -> Dokument:
    gruppe = w.gruppe or ""
    return Dokument("werkzeug", w.name, [
        (w.name, 3),
        (w.alltag or "", 2),
        (" ".join(w.worte or ()), 2),
        (werkzeug_gruppen.schlagworte(gruppe) if gruppe else "", 2),
        (w.beschreibung("gross") or "", 1),
        (_parameter_text(w.parameter_auf("gross")), 1),
    ])


def angeboten() -> list:
    """Die Register-Einträge, die die Suche finden kann (gross, ohne die,
    die die Schleife selbst erledigt), in Register-Reihenfolge."""
    return [w for w in werkzeug_register.auf_schiene("gross")
            if w.name not in _NICHT_IM_INDEX]


def _bauen() -> list:
    return [_werkzeug_dokument(w) for w in angeboten()]


INDEX = _bauen()


def neu_bauen() -> None:
    """Nach einem Umschalten im Register (Tests, erzeugte Werkzeuge)."""
    global INDEX
    INDEX = _bauen()


def _skill_dokumente() -> list:
    try:
        import skills
        liste = skills.aktive()
    except Exception:
        return []
    return [Dokument("skill", s["name"], [(s["name"], 3), (s["beschreibung"], 1)])
            for s in liste]


# ── BM25 ───────────────────────────────────────────────────────────────
# Ein Suchwort trifft ein Wort im Dokument genau oder als Wortanfang (ab 4
# Zeichen, in beide Richtungen): „Routine" trifft „routinen", „xlsx" trifft
# „xlsx". Deutsch hat zu viele Endungen für genaue Treffer allein.
_K1, _B = 1.2, 0.75


def _passt(such: str, wort: str) -> bool:
    if such == wort:
        return True
    if len(such) >= 4 and wort.startswith(such):
        return True
    return len(wort) >= 4 and such.startswith(wort)


def bewerten(anfrage: str, dokumente: list) -> list:
    """[(punkte, dokument)] absteigend, nur mit Punkten > 0. Gleichstand:
    Reihenfolge im Index (deterministisch)."""
    such = list(dict.fromkeys(worte(anfrage)))
    if not such or not dokumente:
        return []
    n = len(dokumente)
    schnitt = sum(d.laenge for d in dokumente) / n
    punkte = [0.0] * n
    for s in such:
        tf = [sum(c for w, c in d.tf.items() if _passt(s, w)) for d in dokumente]
        df = sum(1 for t in tf if t)
        if not df:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i, (t, d) in enumerate(zip(tf, dokumente)):
            if t:
                punkte[i] += idf * t * (_K1 + 1) / (
                    t + _K1 * (1 - _B + _B * d.laenge / schnitt))
    raus = [(p, i, d) for i, (p, d) in enumerate(zip(punkte, dokumente)) if p > 0]
    raus.sort(key=lambda x: (-x[0], x[1]))
    return [(p, d) for p, _i, d in raus]


# ── Das Ergebnis ───────────────────────────────────────────────────────

class Treffer(str):
    """Das Ergebnis von search_tools: der Text fürs Modell (OpenAI) und das
    Protokoll, dazu die gefundenen Werkzeuge (werkzeuge, Register-Namen in
    Treffer-Reihenfolge), Skills (skills) und die Anfrage. Ein str, damit
    alles, was Werkzeug-Ergebnisse liest (Prüfer, Ablauf), nichts Neues
    lernen muss."""

    def __new__(cls, text: str, werkzeuge=(), skills=(), anfrage: str = ""):
        t = super().__new__(cls, text)
        t.werkzeuge = tuple(werkzeuge)
        t.skills = tuple(skills)
        t.anfrage = anfrage
        return t


def gruppe_von(name: str) -> list:
    """Die Namen der Gruppe eines Werkzeugs (es selbst, wenn es immer
    geladen ist oder allein steht), in Register-Reihenfolge."""
    w = werkzeug_register.eintrag(name)
    if w is None or w.laden == "immer" or not w.gruppe:
        return [name]
    return [x.name for x in angeboten() if x.gruppe == w.gruppe]


def suchen(anfrage: str, n: int = STANDARD_TREFFER) -> Treffer:
    """Die besten n Treffer (Werkzeuge und Skills); jedes gefundene
    Werkzeug bringt seine Gruppe mit. Höchstens MAX_WERKZEUGE Namen."""
    import werkzeug_befund
    anfrage = " ".join(str(anfrage or "").split())
    beste = bewerten(anfrage, INDEX + _skill_dokumente())[:max(1, int(n or 1))]
    # Schwache Mitläufer weg: was nicht ein Drittel der Punkte des besten
    # Treffers hat, traf meist nur ein Allerweltswort.
    beste = [(p, d) for p, d in beste if p >= ANTEIL * beste[0][0]] if beste else []
    namen, skills = [], []
    for _p, d in beste:
        if d.art == "skill":
            skills.append(d.name)
            continue
        for x in gruppe_von(d.name):
            if x not in namen and len(namen) < MAX_WERKZEUGE:
                namen.append(x)
    if skills and "load_skill" not in namen and any(
            w.name == "load_skill" for w in angeboten()):
        namen.append("load_skill")       # wer einen Skill findet, will ihn laden
    if not namen and not skills:
        return Treffer(werkzeug_befund.Befund(
            f"Kein Werkzeug und kein Skill passt zu „{anfrage}“. Versuch andere "
            f"Stichworte (die Sache, nicht den Inhalt) — oder es gibt dafür keins."),
            anfrage=anfrage)
    zeilen = []
    if namen:
        zeilen.append("Gefunden, ab jetzt aufrufbar: " + ", ".join(namen))
        for x in namen:
            w = werkzeug_register.eintrag(x)
            zeilen.append(f"- {x} — {_erster_satz(w.beschreibung('gross') if w else '')}")
    if skills:
        zeilen.append(skill_zeile(skills))
    return Treffer(werkzeug_befund.Befund("\n".join(zeilen)), namen, skills, anfrage)


def skill_zeile(skills) -> str:
    return ("Passende Skills (Anleitung mit load_skill holen): "
            + ", ".join(skills))


def _erster_satz(text: str) -> str:
    text = " ".join(str(text or "").split())
    m = re.search(r"[.!?](\s|$)", text)
    satz = text[:m.end()].strip() if m else text
    return satz if len(satz) <= 160 else satz[:159].rstrip() + "…"


# ── Freischaltung im Zug ───────────────────────────────────────────────

class Freischaltung:
    """Was in diesem Zug (und davor im Gespräch) freigeschaltet ist, in der
    Reihenfolge des Freischaltens — die Liste wächst nur."""

    def __init__(self, namen=()):
        self.namen = list(dict.fromkeys(namen))

    def dazu(self, namen) -> list:
        """Neue Namen anhängen. -> die wirklich neuen."""
        neu = [n for n in namen if n not in self.namen]
        self.namen += neu
        return neu


def zurueckgestellt() -> set:
    """Namen der Werkzeuge, die bei eingeschalteter Suche erst nach
    search_tools geladen werden (gross, laden = bedarf)."""
    return {w.name for w in werkzeug_register.auf_schiene("gross")
            if w.laden == "bedarf" and w.name not in _NICHT_IM_INDEX}


def immer() -> list:
    return [w.name for w in werkzeug_register.auf_schiene("gross") if w.laden == "immer"]


def vorab(schiene, verlauf) -> set:
    """Was das Gespräch vorab bekommt (Schnittstelle für einen späteren
    Klassifikator): das Profil darf es selbst sagen (ModellSchiene.vorab),
    sonst die Schlagworte aus werkzeug_gruppen."""
    f = getattr(schiene, "vorab", None)
    if callable(f):
        return set(f(verlauf or [], INDEX))
    return werkzeug_gruppen.vorab(verlauf or [], INDEX)


# ── Über Züge hinweg ───────────────────────────────────────────────────
# Der Verlauf trägt frühere Züge nur als Text. Damit eine Freischaltung den
# Zug überlebt, merkt sich die Antwort im Gespräch (Werkzeug-Spur, Feld
# `freigeschaltet` = {anfrage, namen}); anhang.verlauf_einsetzen gibt das
# als `suche` an die Nachricht, und die Adapter setzen daraus wieder ein:
# Anthropic das Paar Suchaufruf + Ergebnis (tool_use + tool_result mit
# tool_reference), BYTE-gleich in jedem Zug (feste id aus dem Inhalt) —
# sonst bräche der Prompt-Cache ab dieser Stelle; OpenAI hängt die Schemas
# an die Liste.

def _bekannt(suche: list) -> list:
    """Nur Namen, die es noch gibt — ein weggefallenes Werkzeug darf nicht
    referenziert werden (die API lehnte das ab). Suchen ohne Namen fallen
    weg. Deterministisch: gleicher Verlauf, gleiches Register → gleich."""
    bekannt = {w.name for w in angeboten()}
    raus = []
    for s in suche or ():
        namen = [n for n in s.get("namen") or () if n in bekannt]
        if namen:
            raus.append({"anfrage": str(s.get("anfrage") or ""), "namen": namen})
    return raus


def aus_spur(spur) -> list:
    """Werkzeug-Spur einer Antwort → [{anfrage, namen}], nur bekannte Namen."""
    return _bekannt(werkzeug_gruppen.suche_aus_spur(spur))


def aus_verlauf(verlauf) -> list:
    """Alle im Gespräch freigeschalteten Namen, in Reihenfolge."""
    namen = []
    for m in verlauf or ():
        for s in _bekannt(m.get("suche")):
            namen += [n for n in s["namen"] if n not in namen]
    return namen


def _id(m: dict, i: int, s: dict) -> str:
    roh = json.dumps([str(m.get("content") or ""), i, s.get("anfrage"), s.get("namen")],
                     ensure_ascii=False, sort_keys=True)
    return "toolu_zsuche_" + hashlib.sha1(roh.encode("utf-8")).hexdigest()[:20]


def paare_anthropic(m: dict) -> list:
    """Die eingesetzten Paare vor einer Antwort mit `suche`: je Suche eine
    assistant-Nachricht mit dem Aufruf und eine user-Nachricht mit dem
    Ergebnis. Deterministisch aus der gespeicherten Nachricht."""
    raus = []
    for i, s in enumerate(_bekannt(m.get("suche"))):
        cid = _id(m, i, s)
        raus.append({"role": "assistant", "content": [{
            "type": "tool_use", "id": cid, "name": NAME,
            "input": {"query": s.get("anfrage") or ""}}]})
        raus.append({"role": "user", "content": [{
            "type": "tool_result", "tool_use_id": cid,
            "content": referenzen(s.get("namen") or ())}]})
    return raus


def referenzen(namen) -> list:
    """tool_reference-Blöcke (Anthropic). Ein Ergebnis darf NUR daraus
    bestehen — Text daneben lehnt die API ab (Probelauf 14.10.2026:
    „Tool definitions … cannot be mixed with other content")."""
    return [{"type": "tool_reference", "tool_name": n} for n in namen]


# ── Für Werkzeuge von außen: der Index als MCP tools/list ──────────────

def mcp_liste() -> dict:
    """Der Index im Format einer MCP-Antwort auf tools/list — was die Suche
    kennt, mit laden/gruppe/Schlagworten unter _meta (scripts/
    werkzeug_index.py)."""
    tools = []
    for w in angeboten():
        tools.append({
            "name": w.name,
            "description": w.beschreibung("gross") or "",
            "inputSchema": w.parameter_auf("gross"),
            "_meta": {"zentrale/laden": w.laden,
                      "zentrale/gruppe": w.gruppe,
                      "zentrale/schlagworte": (werkzeug_gruppen.schlagworte(w.gruppe)
                                               if w.gruppe else "")},
        })
    return {"tools": tools}
