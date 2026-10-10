# tui/ansichten/spur.py
#
# „trace ›" unter einer Antwort (2026-10-09): der ganze Zug von Sashas
# Nachricht bis zur fertigen Antwort, in Reihenfolge — Kontext, Text
# zwischen den Werkzeugen, jedes Werkzeug mit Argumenten und vollem
# Ergebnis, Fragen an Sasha, die Prüfung, Antwort, Kosten. Sasha: wie bei
# „Used …" nicht nur sehen, welches Werkzeug lief, sondern was es zurückgab
# und wie die Antwort darauf weiterging.
#
# Gespeichert wird das Protokoll im Backend (core/zug_ablauf.py, Feld
# `ablauf` der Antwort); /api/chat/history sagt nur, DASS es eins gibt
# (ablauf_n). Den Inhalt holt die TUI erst beim Aufklappen
# (GET /api/gespraeche/<id>/ablauf/<nachricht>, chat_gespraeche.py).
#
# Reine Funktionen ohne curses (tests/test_zug_ablauf_tui.py). Jeder Eintrag
# erst als Kopfzeile, ein Klick (Ziel ("spur", (i, k))) zeigt ihn ganz —
# wie „… mehr" bei den Werkzeug-Schritten (verlauf.py).

import json
from functools import lru_cache

from .text import _md_umbruch

LAEDT = "laedt"     # Platzhalter in AI["ablaeufe"], solange geholt wird


def spuren(log, nachrichten):
    """{log-index: nachricht-id} der Antworten mit Ablauf-Protokoll. Die
    k-te „ai"-Zeile ist die k-te Antwort mit Text (wie bewertung.py)."""
    ids = [(m.get("id"), bool(m.get("ablauf_n"))) for m in nachrichten or []
           if isinstance(m, dict) and m.get("role") != "user"
           and (m.get("content") or "").strip()]
    raus, k = {}, 0
    for i, (rolle, _t) in enumerate(log):
        if rolle != "ai":
            continue
        if k < len(ids) and ids[k][1] and ids[k][0]:
            raus[i] = ids[k][0]
        k += 1
    return raus


def _zahl(n):
    try:
        return "{:,}".format(int(n)).replace(",", " ")
    except (TypeError, ValueError):
        return "?"


def _einzeilig(text, n=60):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def kopf(e):
    """Eine Zeile je Eintrag (ohne Nummer und Pfeil)."""
    art = e.get("art")
    if art == "system":
        return "system prompt (fixed) · %s chars" % _zahl(e.get("laenge"))
    if art == "kontext":
        anh = e.get("anhaenge") or []
        return "context · %s chars%s" % (_zahl(len(str(e.get("text") or ""))),
                                         " · %d attached" % len(anh) if anh else "")
    if art == "text":
        return ("discarded: " if e.get("verworfen") else "said: ") + _einzeilig(e.get("text"))
    if art == "werkzeug":
        teile = ["tool %s" % e.get("name"), str(e.get("status") or "no result")]
        if e.get("dauer") is not None:
            teile.append("%.1f s" % float(e["dauer"]))
        return " · ".join(teile)
    if art == "frage":
        a = e.get("antwort")
        return "asked: %s → %s" % (_einzeilig(e.get("frage"), 40),
                                   a if a is not None else "no answer")
    if art == "pruefung":
        runde = " (round %s)" % e["runde"] if e.get("runde") else ""
        return "check: %d finding(s) → written again%s" % (len(e.get("befunde") or []), runde)
    if art == "warnung":
        return "warning: " + str(e.get("text") or "")
    if art == "quellen":
        return "sources: %d page(s) read" % len(e.get("liste") or [])
    if art == "fehler":
        return "error: " + _einzeilig(e.get("text"))
    if art == "gestoppt":
        return "stopped"
    if art == "antwort":
        return "answer · %s chars" % _zahl(len(str(e.get("text") or "")))
    if art == "kosten":
        return "cost · %s round(s) · in %s · out %s · cache %s · %.4f €%s" % (
            e.get("runden"), _zahl(e.get("eingabe")), _zahl(e.get("ausgabe")),
            _zahl(e.get("cache_lesen")), float(e.get("euro") or 0),
            " (estimated)" if e.get("geschaetzt") else "")
    return str(art)


def inhalt(e):
    """Der ganze Eintrag als Text — leer, wenn die Kopfzeile alles sagt."""
    art = e.get("art")
    if art == "werkzeug":
        args = e.get("args")
        if not isinstance(args, str):
            args = json.dumps(args or {}, ensure_ascii=False, indent=2, default=str)
        erg = e.get("ergebnis")
        return "arguments:\n%s\n\nresult:\n%s" % (
            args, erg if erg is not None else "(no result — the turn ended first)")
    if art == "frage":
        a = e.get("antwort")
        return "%s\nbuttons: %s\nanswer: %s" % (e.get("frage") or "",
                                                " | ".join(e.get("optionen") or []) or "-",
                                                a if a is not None else "(none)")
    if art == "pruefung":
        bef = "\n".join("- " + str(b.get("satz") or b.get("kennung") or b)
                        for b in e.get("befunde") or [] if isinstance(b, dict))
        return "findings:\n%s\n\nnote to the ai:\n%s\n\nfirst answer (not shown):\n%s" % (
            bef or "-", e.get("hinweis") or "", e.get("erste_antwort") or "")
    if art == "kontext":
        anh = e.get("anhaenge") or []
        return str(e.get("text") or "") + ("\n\nattached: " + ", ".join(map(str, anh))
                                           if anh else "")
    if art == "system":
        return "fingerprint %s — the fixed part is the same every turn and is not " \
               "stored per turn" % e.get("fingerabdruck")
    if art == "quellen":
        return "\n".join("„%s“ – %s (%s)" % (q.get("titel"), q.get("url"), q.get("werkzeug"))
                         for q in e.get("liste") or [] if isinstance(q, dict))
    if art in ("text", "fehler", "antwort"):
        return str(e.get("text") or "")
    return ""


@lru_cache(maxsize=64)
def _umbrochen(text, breite):
    """Zeilenweise umbrechen, Leerzeilen bleiben (anders als _md_umbruch
    allein, das jeden Weißraum zusammenzieht)."""
    raus = []
    for zeile in str(text).split("\n"):
        raus += _md_umbruch(zeile, max(4, breite), "") if zeile.strip() else [""]
    return tuple(raus)


def zeilen(eintraege, i, offen, breite):
    """Die Zeilen des aufgeklappten trace unter der Antwort log[i].
    eintraege: Liste, LAEDT oder ein Fehlertext (str)."""
    breite = max(8, int(breite))
    if eintraege == LAEDT or eintraege is None:
        return [[("  … loading", "denken", None)]]
    if isinstance(eintraege, str):
        return [[("  " + eintraege[:breite - 2], "hinweis", None)]]
    raus = []
    for k, e in enumerate(eintraege):
        if not isinstance(e, dict):
            continue
        z = ("spur", (i, k))
        voll = inhalt(e)
        auf = z in offen and bool(voll)
        t = e.get("t")
        zeit = ("+%.1fs " % float(t)) if isinstance(t, (int, float)) else ""
        pfeil = ("▾" if auf else "▸") if voll else " "
        vorne = "  %s %d %s" % (pfeil, k + 1, zeit)
        stil = ("schritt_fehler" if (e.get("art") in ("fehler", "warnung") or e.get("fehler"))
                else "schritt")
        # Zu lange Kopfzeilen (Kosten bei 80 Spalten) umbrechen statt kappen.
        teile = _umbrochen(kopf(e), max(4, breite - len(vorne))) or ("",)
        for n, teil in enumerate(teile):
            text = (vorne if n == 0 else " " * len(vorne)) + teil
            raus.append([(text[:breite], stil, z if voll else None)])
        if auf:
            for u in _umbrochen(voll, breite - 6):
                raus.append([("      " + u, "denken", None)])
            if e.get("gekuerzt"):
                raus.append([("      (shortened by %s chars)" % _zahl(e["gekuerzt"]),
                              "leise", None)])
    return raus or [[("  (empty)", "denken", None)]]
