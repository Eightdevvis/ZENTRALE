# core/auftrag_abrechnung.py
#
# Auftrags-Abrechnung: die KI rechnet jeden Teil von Sashas Auftrag im Feld
# `auftrag` des Werkzeugs antwort ab (core/selbstauskunft.py) — erledigt,
# offen oder abgelehnt. Python prüft, was es prüfen kann:
#
#   erledigt   braucht in DIESEM Zug ein Werkzeug mit [ergebnis: ok] — das
#              genannte (`werkzeug`), sonst irgendeins → sonst Befund „tat"
#   offen      mit `sicherer_teil` → EINE Korrekturrunde „trag den sicheren
#              Teil jetzt ein, frag nur nach dem Rest" (Befund „sicherer_teil")
#   offen / abgelehnt ohne sicheren Teil → kein Befund, aber Sasha sieht es
#              unter der Antwort („offen: Geige fällt aus — Ende der Ferien
#              unklar")
#   fehlt      obwohl Sashas Nachricht mehrere Aufträge trägt → EINE
#              Korrekturrunde „rechne den Auftrag in `auftrag` ab"
#
# Warum (2026-10-10, Prüfstand f01k mit Haiku): Sasha „lösch nyam und geige
# ist nur donnerstags von 18:10-19 uhr. aber sie fällt wegen der ferien jetzt
# aus" — die KI löschte, änderte, und ließ die Pause einfach WEG („brauchst
# du die Info akut, um die Pause einzutragen?"). Kein Satz war falsch, also
# schlug kein Prüfer an. Was fehlt, kann keine Satz-Prüfung finden; eine
# Abrechnung, die jeden Teil nennen muss, macht das Weglassen sichtbar.
#
# „Mehrere Aufträge" ohne Wortliste (Sasha 10.10.: Wortlisten skalieren
# nicht und kennen nur Deutsch): in diesem Zug lief mindestens ein
# schreibendes Werkzeug (gleich welcher Ausgang — Sasha wollte also etwas
# geändert haben), UND Sashas Nachricht hat mindestens zwei Teile, die keine
# Frage sind (Sätze, getrennt an . ! ; … und Zeilen; nicht in Uhrzeiten und
# Daten) — einer davon kann liegen geblieben sein. Gemessen mit
# scripts/ehrlichkeit_messen.py (memory/ki/ehrlichkeit_live.md). Die erste
# Fassung zählte zusätzlich „zwei verschiedene Ziele geschrieben" als
# mehrere Aufträge — das traf Verschieben per Löschen+Anlegen und Züge, in
# denen die KI ungefragt mehr tat (6 % Falschtreffer), und fiel weg.
# Bewusst NICHT der Klassifikator (core/klassifikator.py): er kennt keine
# Satzart „Auftrag" und wird nur bei Widersprüchen gefragt, nie je Zug
# pauschal (kostet). Übersehen kostet hier wenig: die KI rechnet ohnehin ab,
# wenn sie über antwort antwortet; der Prüfer fängt nur das Schweigen.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md): kennt das Werkzeug-
# Register. Die Schritte des Protokolls (ehrlichkeit.Schritt) kommen als
# Argument — kein Import von ehrlichkeit (das ruft hierher).

import re

import werkzeug_register

ERLEDIGT, OFFEN, ABGELEHNT = "erledigt", "offen", "abgelehnt"

# Sätze in Sashas Nachricht: an . ! ? ; und Zeilen getrennt — nicht in
# Uhrzeiten und Daten („18.10", „12.10.").
_TEIL = re.compile(r"[^\n]+?(?:(?<!\d)[.!?;…]+(?!\d)|$)", re.M)


def _teile(nachricht: str) -> list:
    """Sashas Nachricht → [(teil, ist_frage)] mit mindestens zwei Wörtern."""
    raus = []
    for m in _TEIL.finditer(str(nachricht or "")):
        t = m.group(0).strip()
        if len(t.split()) >= 2:
            raus.append((t, t.rstrip().endswith("?")))
    return raus


def noetig(nutzer_text: str, protokoll: list) -> bool:
    """Trägt Sashas Nachricht mehrere Aufträge, sodass eine Abrechnung
    Pflicht ist? Sprachfrei, siehe Kopf."""
    if not str(nutzer_text or "").strip():
        return False
    if not any(s.schreibt for s in protokoll):
        return False
    return sum(1 for _t, frage in _teile(nutzer_text) if not frage) >= 2


def _werkzeug(punkt: dict) -> str | None:
    """Das genannte Werkzeug, kanonisch — None, wenn keins oder unbekannt."""
    name = werkzeug_register.kanonisch(str(punkt.get("werkzeug") or "").strip())
    return name if name and werkzeug_register.eintrag(name) else None


def belegt(punkt: dict, protokoll: list) -> bool:
    """Ist ein „erledigt" durch dieses Zugs Protokoll gedeckt? Mit genanntem
    Werkzeug: genau das, mit ok. Ohne (oder unbekannt): irgendeins mit ok —
    die vorsichtige Seite, ohne Werkzeug weiß Python nicht, welches passt."""
    name = _werkzeug(punkt)
    return any(s.status == "ok" and (name is None or s.name == name) for s in protokoll)


def _sicher_lief(punkt: dict, protokoll: list) -> bool:
    """Lief das genannte Werkzeug schon (ok oder von Sasha abgelehnt)? Dann
    ist der sichere Teil getan oder entschieden — keine Runde dafür."""
    name = _werkzeug(punkt)
    return bool(name) and any(s.name == name and s.status in ("ok", "abgelehnt")
                              for s in protokoll)


def befunde(auftrag, protokoll: list, nutzer_text: str = "") -> list:
    """auftrag: das gelesene Feld (selbstauskunft.auftrag_lesen) oder None.
    -> Befunde [{art, satz, …, quelle: "auftrag"}]."""
    raus = []
    for p in auftrag or ():
        if p.get("stand") == ERLEDIGT and not belegt(p, protokoll):
            b = {"art": "tat", "satz": p["was"], "quelle": "auftrag", "auftrag": True}
            name = _werkzeug(p)
            if name:
                b["werkzeug"] = name
            raus.append(b)
        elif p.get("stand") == OFFEN and p.get("sicherer_teil") \
                and not _sicher_lief(p, protokoll):
            raus.append({"art": "sicherer_teil", "satz": p["was"],
                         "sicherer_teil": p["sicherer_teil"], "quelle": "auftrag"})
    if not auftrag and noetig(nutzer_text, protokoll):
        raus.append({"art": "auftrag_fehlt", "satz": "", "quelle": "auftrag"})
    return raus


def zeile(auftrag) -> str:
    """Was Sasha unter der Antwort sieht: die offenen und nicht gemachten
    Teile. „offen: Geige fällt aus — Ende der Ferien unklar". Erledigtes
    steht schon in der Erledigt-Zeile (aus dem Protokoll)."""
    teile = []
    for p in auftrag or ():
        wort = {OFFEN: "offen", ABGELEHNT: "nicht gemacht"}.get(p.get("stand"))
        if not wort:
            continue
        grund = f" — {p['grund']}" if p.get("grund") else ""
        teile.append(f"{wort}: {p['was']}{grund}")
    return " · ".join(teile)
