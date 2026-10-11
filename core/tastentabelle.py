# core/tastentabelle.py
#
# Die Tastentabelle — wie eine App sagt, welche Tasten sie in welcher Ansicht
# nimmt (Sasha, 2026-10-11: „keine shortcuts per hand in die leiste, sondern
# ein client, der das programm abhört und wissen will, welche tastenkombis
# genommen werden — dynamisch pro ansicht, und nur die, die dort von belang
# sind").
#
# Form (JSON, und genauso im app.toml unter [tasten]):
#
#     {"<ansicht>": [{"taste": "↑↓", "aktion": "waehlen", "text": "select"},
#                    {"taste": "k",  "aktion": "waehlen"}, …], …}
#
#   taste   Beschriftung, wie die Leiste sie zeigt; daraus liest jede
#           Oberfläche die echten Tasten (namen() unten). „a/s" = zwei Tasten,
#           „↑↓" = zwei, „pgup pgdn" = zwei. Besondere Wörter: „type" = jedes
#           druckbare Zeichen (Freitext), „any key" = jede übrige Taste.
#   aktion  Name der Handlung in der App (Kleinbuchstaben, _ erlaubt). Die
#           Oberfläche ruft sie auf; was sie tut, weiß nur die App.
#   text    kurz, englisch (Leisten-Sprache seit 2026-10-07). Fehlt er, wird
#           die Taste verarbeitet, aber nicht angezeigt (Zweitbelegung wie
#           k für ↑).
#
# Die Tabelle ist zugleich die Tastenverteilung des Programms: was hier
# steht, geht, und was angezeigt wird, steht hier. Eine Oberfläche zeigt
# NUR die Einträge der Ansicht, die gerade offen ist. Wer keine Tabelle
# liefert, wird abgehört (tui/ansichten/horcher.py).
#
# Tastennamen sind neutral (keine curses-Codes): ein druckbares Zeichen ist
# es selbst, sonst enter esc tab shift+tab space backspace del home end pgup
# pgdn up down left right, alt+<pfeil|enter|zeichen>, ctrl+<a–z>, f1–f12.
# Die TUI bildet sie in tui/ansichten/tasten.py auf curses ab.
#
# Nur Standardbibliothek (die TUI liest das Modul über basis.kern_pfad()).
# Doku: memory/system/tui_bauplan.md „Tastentabelle", hub_bauplan.md.

import re

FREITEXT = "type"
JEDE = "any key"
BESONDERE = (FREITEXT, JEDE)

_PFEILE = {"↑": "up", "↓": "down", "←": "left", "→": "right"}
_WOERTER = {
    "enter": "enter", "esc": "esc", "tab": "tab", "shift+tab": "shift+tab",
    "space": "space", "⌫": "backspace", "backspace": "backspace", "del": "del",
    "home": "home", "end": "end", "pgup": "pgup", "pgdn": "pgdn",
    "alt+enter": "alt+enter",
}
_AKTION = re.compile(r"^[a-z][a-z0-9_]*$")


def _wort(t):
    """Ein Stück einer Beschriftung → [tastenname, …]; None = unlesbar."""
    if t in _WOERTER:
        return [_WOERTER[t]]
    if t and all(c in _PFEILE for c in t):
        return [_PFEILE[c] for c in t]
    if t.startswith("alt+") and t[4:]:
        rest = t[4:]
        if all(c in _PFEILE for c in rest):
            return ["alt+" + _PFEILE[c] for c in rest]
        if len(rest) == 1 and rest.isprintable() and rest != " ":
            return ["alt+" + rest]
    if t.startswith("ctrl+") and len(t) == 6 and t[5].isalpha() and t[5].isascii():
        return ["ctrl+" + t[5].lower()]
    if re.fullmatch(r"f([1-9]|1[0-2])", t):
        return [t]
    if len(t) == 1 and t.isprintable() and t != " ":
        return [t]
    return None


def namen(taste):
    """Beschriftung → Liste neutraler Tastennamen. [] für „type"/„any key".
    Wirft ValueError, wenn niemand die Beschriftung lesen kann."""
    if taste in BESONDERE:
        return []
    raus = []
    for wort in str(taste).split():
        # „a/s" = zwei Tasten; „/" allein ist die Taste Schrägstrich, „+/-" zwei.
        teile = [wort] if wort == "/" else [s for s in wort.split("/") if s] or [wort]
        for t in teile:
            n = _wort(t)
            if n is None:
                raise ValueError("unbekannte taste %r in %r" % (t, taste))
            raus += n
    if not raus:
        raise ValueError("leere taste %r" % (taste,))
    return raus


def pruefen(tabelle):
    """Fehler der Tabelle als Liste deutscher Sätze ([] = in Ordnung). Eine
    Taste darf in einer Ansicht nur EINE Aktion haben."""
    fehler = []
    if not isinstance(tabelle, dict):
        return ["tastentabelle ist kein objekt"]
    for ansicht, eintraege in tabelle.items():
        if not isinstance(ansicht, str) or not ansicht:
            fehler.append("ansicht ohne namen"); continue
        if not isinstance(eintraege, list):
            fehler.append("%s: keine liste" % ansicht); continue
        belegt = {}
        for e in eintraege:
            if not isinstance(e, dict) or not isinstance(e.get("taste"), str):
                fehler.append("%s: eintrag ohne taste" % ansicht); continue
            if not _AKTION.match(str(e.get("aktion", ""))):
                fehler.append("%s: %r hat keine gültige aktion" % (ansicht, e["taste"]))
            if "text" in e and e["text"] is not None and not isinstance(e["text"], str):
                fehler.append("%s: %r: text ist kein text" % (ansicht, e["taste"]))
            unbekannt = set(e) - {"taste", "aktion", "text"}
            if unbekannt:
                fehler.append("%s: %r: unbekannte felder %s"
                              % (ansicht, e["taste"], sorted(unbekannt)))
            try:
                tasten = namen(e["taste"]) or [e["taste"]]
            except ValueError as err:
                fehler.append("%s: %s" % (ansicht, err)); continue
            for t in tasten:
                if t in belegt and belegt[t] != e.get("aktion"):
                    fehler.append("%s: %s doppelt (%s und %s)"
                                  % (ansicht, t, belegt[t], e.get("aktion")))
                belegt.setdefault(t, e.get("aktion"))
    return fehler


def eintraege(tabelle, ansicht):
    """Was eine Leiste in `ansicht` zeigt: [(taste, text)] in Tabellen-
    Reihenfolge, nur Einträge mit Text."""
    return [(e["taste"], e["text"]) for e in (tabelle.get(ansicht) or [])
            if e.get("text")]


def katalog(manifeste):
    """`GET /api/tasten`: [{app, tasten}] aller Apps, deren app.toml eine
    gültige Tastentabelle trägt (Reihenfolge wie die Manifeste). Apps ohne
    Tabelle fehlen — die hört eine Oberfläche selbst ab."""
    raus = []
    for m in manifeste:
        t = aus_manifest(m)
        if t is not None:
            raus.append({"app": m.get("_slug") or m.get("name"), "tasten": t})
    return raus


def aus_manifest(m):
    """[tasten] eines app.toml → Tastentabelle, oder None (keine oder kaputt;
    kaputt mit Zeile im Log — dann wird abgehört)."""
    t = (m or {}).get("tasten")
    if t is None:
        return None
    fehler = pruefen(t)
    if fehler:
        print("[tasten] %s: %s" % ((m or {}).get("name", "?"), "; ".join(fehler)), flush=True)
        return None
    return t
