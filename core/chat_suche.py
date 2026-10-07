# core/chat_suche.py
#
# Suche quer durch alle Gespräche — das Werkzeug search_chats (und
# read_chat zum Nachlesen eines Treffers).
#
# 2026-10-07, Phase 3 des Claude-Web-Plans (memory/ki/claude_web_plan.md).
# Sasha: „mein kopf kann sich thematisch viel besser orientieren als
# datiert. solang der assistant eh einfach crossgespräche suchen kann wie
# claude web." Viele Gespräche (Phase 2) gehen nur, wenn die KI aus jedem
# Gespräch heraus findet, was in einem anderen gesagt wurde.
#
# ── Was durchsucht wird ────────────────────────────────────────────────
#   1. Alle Gespräche (core/gespraeche.py), auch archivierte und
#      „Erinnerungen". Nur der sichtbare Text von Sasha und der KI — kein
#      Denken, keine Werkzeug-Listen, keine versteckten Erinnerungs-Aufträge
#      (das sind Regieanweisungen von ZENTRALE, nicht Gesagtes).
#   2. Das alte Transkript (core/transkript.py, data/ai_transcripts/) — der
#      Verlauf von vor den Gesprächen. Es enthält Testmüll aus der Zeit vor
#      dem Riegel in tests/conftest.py; den kann hier niemand sicher
#      erkennen, also bleibt er drin. Was es auch als Gespräch gibt (die
#      Konsolidierung schreibt jeden Zug weiter ins Transkript), fällt raus.
#
# ── Das laufende Gespräch ──────────────────────────────────────────────
# Was die KI ohnehin im Verlauf hat (die letzten gespraeche.FENSTER
# Nachrichten des offenen Gesprächs), wird nicht noch einmal geliefert —
# das wären doppelt bezahlte Zeichen. Ältere Nachrichten desselben
# Gesprächs schon: die sieht sie nicht mehr. „Offen" heißt hier
# gespraeche.aktiv(): die Chat-Route setzt es vor jedem Zug.
#
# ── Wie gesucht wird (bewusst einfach) ─────────────────────────────────
# Wörter normalisiert (klein, ä→ae, ß→ss, Akzente weg), Füllwörter raus,
# ALLE übrigen Wörter müssen in der Einheit vorkommen — als Teilwort, weil
# Deutsch zusammensetzt („geige" findet „Geigenstunde"). Eine Einheit ist
# ein Gespräch bzw. ein Tag des alten Transkripts: thematisch, nicht pro
# Satz — „geige ferien" darf über zwei Nachrichten verteilt stehen.
# Rang = Trefferdichte × Aktualität (Halbwertszeit HALBWERT_TAGE). Kein
# Index, keine Vektoren: es sind ein paar hundert Nachrichten, und ein
# Wortfund ist nachprüfbar, ein Ähnlichkeitswert nicht.
#
# Dienst (Schicht 2, memory/system/bauplan_kern.md). Weiß nichts von
# Modellen; die Werkzeug-Einträge stehen im Register.

import math
import re
import unicodedata
from datetime import datetime, timezone

import gespraeche
import transkript

MAX_TREFFER = 8          # Ausgabe geht als Werkzeug-Ergebnis in den Verlauf
AUSSCHNITT = 220         # Zeichen um die Fundstelle
HALBWERT_TAGE = 60       # nach so vielen Tagen zählt ein Fund halb so viel
LESEN_STANDARD = 20      # read_chat: so viele Nachrichten …
LESEN_MAX = 40           # … höchstens
LESEN_NACHRICHT = 1500   # read_chat: eine Nachricht höchstens so lang
TRANSKRIPT = "transkript:"   # id-Vorsatz eines Transkript-Tages

# Woran ein Erinnerungs-Auftrag im alten Transkript zu erkennen ist. Dort
# fehlt das versteckt-Flag der Gespräche; der Auftrag stand als „user"-Text
# da (core/takt.py baut ihn, Kennzeichnung aus gespraeche.AUFTRAG_VORSATZ).
_AUFTRAG_ANFAENGE = ("erinnere sasha", gespraeche.AUFTRAG_VORSATZ.strip()[:20].lower())

# Füllwörter: „das mit dem umzug" soll wie „umzug" suchen. Nur Wörter, die
# als Teilwort fast überall vorkämen und nie ein Thema sind.
_FUELLWOERTER = frozenset("""
der die das den dem des ein eine einen einem einer und oder mit von vom zu
zum zur im in am an auf aus bei fuer ueber unter als wie was wer wo ist sind
war hat habe hatte ich du er sie es wir ihr mein dein sein mal noch schon
auch nur so da dann denn doch ja nein nicht letztens neulich damals
""".split())


# ── Normalisieren ──────────────────────────────────────────────────────

def normalisieren(text) -> str:
    """Klein, Umlaute und ß ausgeschrieben, Akzente weg, nur Buchstaben und
    Ziffern (Rest wird Leerzeichen). „Straße"/„STRASSE"/„strasse" → gleich."""
    s = str(text or "").lower()
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def suchwoerter(anfrage) -> list:
    """Die Wörter, die vorkommen müssen. Füllwörter und Einzelzeichen fallen
    weg — bleibt nichts übrig, zählen doch alle (sonst fände „das" nichts)."""
    alle = normalisieren(anfrage).split()
    woerter = [w for w in alle if len(w) > 1 and w not in _FUELLWOERTER]
    return list(dict.fromkeys(woerter or [w for w in alle if w]))


# ── Einheiten sammeln ──────────────────────────────────────────────────
# Eine Einheit: {"id", "titel", "nachrichten": [{"rolle", "text", "ts"}]},
# ts als datetime (aware). Gespräche und Transkript-Tage sehen gleich aus.

def _zeit(ts):
    """ISO-Zeitstempel → aware datetime. Ohne Zone (Transkript): Ortszeit."""
    try:
        d = datetime.fromisoformat(str(ts))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.astimezone()


def _ist_auftrag(text) -> bool:
    return str(text or "").strip().lower().startswith(_AUFTRAG_ANFAENGE)


def _gespraech_einheit(eintrag, aktiv=None):
    gid = eintrag["id"]
    try:
        ns = gespraeche.nachrichten(gid, versteckte=True)
    except gespraeche.Unbekannt:
        return None
    if gid == aktiv:
        # Was im Verlauf an die KI steckt, nicht doppelt liefern.
        ns = ns[:-gespraeche.FENSTER] if len(ns) > gespraeche.FENSTER else []
    nachrichten = [{"rolle": n["rolle"], "text": gespraeche.text_fuer_ki(n),
                    "ts": _zeit(n.get("ts"))}
                   for n in ns if not n.get("versteckt") and (n.get("text") or "").strip()]
    return {"id": gid, "titel": eintrag.get("titel") or "neues gespräch",
            "archiviert": bool(eintrag.get("archiviert")), "nachrichten": nachrichten}


def _gespraechs_liste():
    return gespraeche.liste() + gespraeche.liste(archivierte=True)


def _schluessel(text) -> str:
    """Vergleichs-Schlüssel, um einen Zug im Transkript wiederzuerkennen."""
    return normalisieren(text)[:300]


def _transkript_tage(bekannt=frozenset()):
    """Das alte Transkript, nach Tag gruppiert: {tag: [nachricht…]}.
    `bekannt`: Schlüssel von KI-Antworten, die es als Gespräch gibt — die
    Züge fallen hier raus."""
    tage = {}
    for _store, z in transkript.alle():
        ts = _zeit(z.get("zeit"))
        if ts is None:
            continue
        user, ai = str(z.get("user") or ""), str(z.get("ai") or "")
        if ai.strip() and _schluessel(ai) in bekannt:
            continue
        tag = ts.date().isoformat()
        liste = tage.setdefault(tag, [])
        if user.strip() and not _ist_auftrag(user):
            liste.append({"rolle": "user", "text": user, "ts": ts})
        if ai.strip():
            liste.append({"rolle": "assistant", "text": ai, "ts": ts})
    for liste in tage.values():
        liste.sort(key=lambda n: n["ts"])
    return {t: ns for t, ns in tage.items() if ns}


def _tag_titel(tag) -> str:
    try:
        return "Früherer Chat vom " + datetime.fromisoformat(tag).strftime("%d.%m.%Y")
    except ValueError:
        return "Früherer Chat"


def einheiten(aktiv=None, projekt=None) -> list:
    """Alles Durchsuchbare: Gespräche (ohne das laufende Fenster) und die
    Tage des alten Transkripts. projekt (id, Phase 6): nur die Gespräche
    dieses Projekts — das alte Transkript kennt keine Projekte und fällt
    dann weg."""
    raus, bekannt = [], set()
    for eintrag in _gespraechs_liste():
        if projekt and eintrag.get("projekt") != projekt:
            continue
        e = _gespraech_einheit(eintrag, aktiv)
        if e is None:
            continue
        # Auch das laufende Fenster zählt als „gibt es schon", sonst käme es
        # über das Transkript doch doppelt.
        for n in gespraeche.nachrichten(eintrag["id"]):
            if n["rolle"] == "assistant" and (n.get("text") or "").strip():
                bekannt.add(_schluessel(n["text"]))
        if e["nachrichten"]:
            raus.append(e)
    if projekt:
        return raus
    for tag, ns in sorted(_transkript_tage(frozenset(bekannt)).items()):
        raus.append({"id": TRANSKRIPT + tag, "titel": _tag_titel(tag),
                     "archiviert": False, "nachrichten": ns})
    return raus


# ── Bewerten ───────────────────────────────────────────────────────────

def _bewerten(einheit, woerter, jetzt):
    """→ (rang, beste_nachricht, stellen) oder None, wenn ein Wort fehlt."""
    texte = [normalisieren(n["text"]) for n in einheit["nachrichten"]]
    gesamt = " ".join(texte)
    if not all(w in gesamt for w in woerter):
        return None
    stellen = sum(gesamt.count(w) for w in woerter)
    laenge = len(gesamt.split()) or 1
    dichte = stellen / math.sqrt(laenge + 20)
    # Beste Nachricht: die meisten verschiedenen Wörter, dann die meisten
    # Stellen, dann die jüngste.
    best_i, best = None, None
    for i, t in enumerate(texte):
        wert = (sum(1 for w in woerter if w in t), sum(t.count(w) for w in woerter), i)
        if wert[0] and (best is None or wert > best):
            best_i, best = i, wert
    nachricht = einheit["nachrichten"][best_i]
    ts = nachricht["ts"] or jetzt
    alter_tage = max(0.0, (jetzt - ts).total_seconds() / 86400)
    frische = 0.5 ** (alter_tage / HALBWERT_TAGE)
    return dichte * (0.4 + 0.6 * frische), nachricht, stellen


def ausschnitt(text, woerter, breite=AUSSCHNITT) -> str:
    """Ein Stück Text um die erste Fundstelle, einzeilig, mit … an den
    Schnittkanten. Gesucht wird im normalisierten Text; weil Umlaute dort
    länger sind, wird die Stelle über die Wortnummer zurückgerechnet."""
    flach = " ".join(str(text or "").split())
    roh_woerter = flach.split(" ")
    pos_wort = None
    for i, rw in enumerate(roh_woerter):
        n = normalisieren(rw)
        if any(w in n for w in woerter):
            pos_wort = i
            break
    if pos_wort is None or len(flach) <= breite:
        return flach[:breite] + ("…" if len(flach) > breite else "")
    start_zeichen = len(" ".join(roh_woerter[:pos_wort]))
    anfang = max(0, start_zeichen - breite // 3)
    # an einer Wortgrenze beginnen
    if anfang:
        leer = flach.rfind(" ", 0, anfang)
        anfang = leer + 1 if leer >= 0 else anfang
    stueck = flach[anfang:anfang + breite]
    return ("…" if anfang else "") + stueck + ("…" if anfang + breite < len(flach) else "")


# ── Die Werkzeuge ──────────────────────────────────────────────────────

def _datum(ts) -> str:
    return ts.astimezone().strftime("%d.%m.%Y") if ts else "?"


def _wer(rolle) -> str:
    return "Sasha" if rolle == "user" else "KI"


def suchen(anfrage, aktiv=None, jetzt=None, max_treffer=MAX_TREFFER, projekt=None) -> list:
    """Treffer, bester zuerst: [{id, titel, datum, stellen, rolle,
    ausschnitt, archiviert}]. Leere Anfrage → []."""
    woerter = suchwoerter(anfrage)
    if not woerter:
        return []
    jetzt = jetzt or datetime.now(timezone.utc)
    bewertet = []
    for e in einheiten(aktiv, projekt):
        b = _bewerten(e, woerter, jetzt)
        if b:
            bewertet.append((b[0], e, b[1], b[2]))
    bewertet.sort(key=lambda t: t[0], reverse=True)
    return [{"id": e["id"], "titel": e["titel"], "datum": _datum(n["ts"]),
             "stellen": stellen, "rolle": n["rolle"],
             "ausschnitt": ausschnitt(n["text"], woerter),
             "archiviert": e["archiviert"]}
            for _rang, e, n, stellen in bewertet[:max_treffer]]


def suchen_text(anfrage, aktiv=None, jetzt=None, projekt=None) -> str:
    """Das Ergebnis von search_chats, kompakt fürs Modell."""
    if not suchwoerter(anfrage):
        return "[Fehler: kein Suchbegriff]"
    treffer = suchen(anfrage, aktiv=aktiv, jetzt=jetzt, projekt=projekt)
    if not treffer:
        wo = "in den Gesprächen dieses Projekts" if projekt else "in früheren Gesprächen"
        return (f"Nichts gefunden zu \"{anfrage}\" {wo}. "
                f"Alle Wörter müssen vorkommen — mit weniger oder anderen "
                f"Wörtern versuchen.")
    zeilen = [f"{len(treffer)} Treffer zu \"{anfrage}\" (bester zuerst):"]
    for i, t in enumerate(treffer, 1):
        teile = [f"{i}. {t['titel']} [{t['id']}]", t["datum"],
                 f"{t['stellen']} Stelle{'' if t['stellen'] == 1 else 'n'}"] +(["archiviert"] if t["archiviert"] else [])
        zeilen.append(" · ".join(teile))
        zeilen.append(f"   {_wer(t['rolle'])}: {t['ausschnitt']}")
    zeilen.append("Mehr davon: read_chat(id, query).")
    return "\n".join(zeilen)


def _einheit(eid):
    """Eine Einheit nach id — Gespräch (ganz, auch das laufende) oder
    Transkript-Tag. → Einheit oder None."""
    eid = str(eid or "").strip()
    if eid.startswith(TRANSKRIPT):
        tag = eid[len(TRANSKRIPT):]
        ns = _transkript_tage().get(tag)
        return {"id": eid, "titel": _tag_titel(tag), "nachrichten": ns} if ns else None
    if not gespraeche.gibt_es(eid):
        return None
    return _gespraech_einheit({"id": eid, "titel": gespraeche.kopf(eid).get("titel")})


def lesen_text(eid, anfrage="", anzahl=LESEN_STANDARD) -> str:
    """Das Ergebnis von read_chat: ein Gespräch nachlesen — die letzten
    `anzahl` Nachrichten, oder mit `anfrage` die um die beste Fundstelle."""
    e = _einheit(eid)
    if e is None:
        return (f"[Kein Gespräch mit der id {eid!r}. Die id steht in den "
                f"Treffern von search_chats in eckigen Klammern.]")
    try:
        anzahl = int(anzahl)
    except (TypeError, ValueError):
        anzahl = LESEN_STANDARD
    anzahl = max(1, min(LESEN_MAX, anzahl))
    ns = e["nachrichten"]
    if not ns:
        return f"{e['titel']} [{e['id']}]: keine Nachrichten."
    woerter = suchwoerter(anfrage)
    ende = len(ns)
    if woerter:
        stellen = [i for i, n in enumerate(ns)
                   if any(w in normalisieren(n["text"]) for w in woerter)]
        if stellen:
            # Die Fundstelle mit den meisten Wörtern in die Mitte des Fensters.
            mitte = max(stellen, key=lambda i: sum(
                1 for w in woerter if w in normalisieren(ns[i]["text"])))
            ende = min(len(ns), mitte + anzahl // 2 + 1)
    anfang = max(0, ende - anzahl)
    zeilen = [f"{e['titel']} [{e['id']}], Nachricht {anfang + 1}–{ende} "
              f"von {len(ns)}:"]
    for n in ns[anfang:ende]:
        text = n["text"].strip()
        if len(text) > LESEN_NACHRICHT:
            text = text[:LESEN_NACHRICHT - 1] + "…"
        zeilen.append(f"[{_datum(n['ts'])}] {_wer(n['rolle'])}: {text}")
    return "\n".join(zeilen)
