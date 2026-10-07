# tui/ansichten/verlauf.py
#
# Der Verlauf des Chats wie bei Claude Web (2026-10-07): Antworten ohne
# Blasen und ohne „ki:", Sashas Nachrichten abgesetzt (rechts, auf eigener
# Fläche), Werkzeug-Schritte als eingeklappte graue Zeilen „Used memory ›",
# Denken eingeklappt, unter jeder Antwort „copy · retry".
#
# Reine Funktionen ohne curses (tests/test_chat_web.py): aus dem Verlauf
# (Liste von (rolle, text), wie Chat.AI["log"] ihn führt) werden Zeilen aus
# Stücken (text, stil, ziel). `ziel` ist None oder ein Tupel (art, index) —
# alles mit Ziel kann man anklicken oder mit ↑↓ anwählen und mit Enter
# auslösen: ("schritt", i) auf/zu, ("denken", i) auf/zu, ("kopieren", i),
# ("wiederholen", i), ("dok", i) öffnen. i ist der Index im Verlauf.
#
# 👍/👎 gibt es bewusst nicht: das Backend kann damit nichts anfangen (kein
# Ort, an dem eine Bewertung landet oder etwas bewirkt) — ein Knopf, der
# nichts tut, wäre gelogen (Sasha zur Fußleiste: „zeigt NUR das an was auch
# tatsächlich … genommen werden kann").

from .chat_ablage import TRENNER
from .text import _md_umbruch, md_zeilen

# Werkzeug → Wort, wie Claude „Used Claude Docs" schreibt (englisch wie die
# Bedienung). Was hier fehlt, heißt wie das Werkzeug.
NAMEN = {
    "web_search": "web search", "fetch_url": "web page", "read_note": "memory",
    "write_note": "memory", "rewrite_note": "memory", "search_memory": "memory",
    "search_chats": "past chats", "read_calendar": "calendar",
    "add_calendar_entry": "calendar", "add_calendar_routine": "calendar",
    "edit_calendar_routine": "calendar", "add_calendar_pause": "calendar",
    "delete_calendar_entry": "calendar", "read_time": "clock", "read_file": "files",
    "list_files": "files", "read_news": "news", "read_mail": "mail",
    "fetch_document": "document", "create_series": "series", "log_series": "series",
    "run_code": "code", "load_skill": "skill", "propose_skill": "skill",
    "edit_skill": "skill", "ask_choice": "choice", "antwort": "answer",
}


def werkzeug_name(text):
    """'read_note(name=x)' / 'read_note ✗ fehler' → 'read_note'."""
    t = str(text or "")
    for zeichen in ("(", " "):
        if zeichen in t:
            t = t.split(zeichen, 1)[0]
    return t.strip() or "?"


def werkzeug_args(text):
    """Die Argumente aus 'name(a=1, b=2)' (Text in der Klammer) oder ''."""
    t = str(text or "")
    if "(" in t and ")" in t:
        return t[t.index("(") + 1:t.rindex(")")].strip()
    return ""


def wort(name):
    return NAMEN.get(name, name.replace("_", " "))


def schritte(log):
    """Werkzeug-Einträge zu Schritten zusammenfassen. -> {start_index:
    {"name", "args", "ergebnis", "fehler", "teile": [indizes]}}. Ein
    Ergebnis/Fehler direkt hinter seinem Start gehört zu ihm."""
    raus, offen = {}, None
    for i, (rolle, text) in enumerate(log):
        if rolle == "werkzeug":
            offen = i
            raus[i] = {"name": werkzeug_name(text), "args": werkzeug_args(text),
                       "ergebnis": "", "fehler": False, "teile": [i]}
        elif rolle in ("werkzeug_ergebnis", "werkzeug_fehler") and offen is not None \
                and raus[offen]["teile"][-1] == i - 1:
            s = raus[offen]
            s["teile"].append(i)
            if rolle == "werkzeug_fehler":
                s["fehler"] = True
                s["ergebnis"] = str(text).split("✗", 1)[-1].strip()
            else:
                s["ergebnis"] = str(text)[2:] if str(text).startswith("↳ ") else str(text)
        elif rolle == "werkzeug_fehler":        # aus dem gespeicherten Verlauf: allein
            offen = None
            raus[i] = {"name": werkzeug_name(text), "args": werkzeug_args(text),
                       "ergebnis": "", "fehler": True, "teile": [i]}
        else:
            offen = None
    return raus


def benutzt(log):
    """„Used in this session": welche Werkzeuge (als Wort) wie oft, mit dem
    zuletzt genannten Argument. -> [(wort, anzahl, detail)] in Reihenfolge
    des ersten Auftretens."""
    reihe, zahl, detail = [], {}, {}
    for s in schritte(log).values():
        w = wort(s["name"])
        if w not in zahl:
            reihe.append(w)
            zahl[w] = 0
        zahl[w] += 1
        if s["args"]:
            erstes = s["args"].split(",")[0]
            detail[w] = erstes.split("=", 1)[-1].strip()
    return [(w, zahl[w], detail.get(w, "")) for w in reihe]


def zahl(n):
    return "{:,}".format(int(n)).replace(",", " ")


def _umbruch(text, breite):
    return _md_umbruch(text, max(4, breite), "") or [""]


def _nutzer(text, breite):
    """Sashas Nachricht: rechts auf eigener Fläche (Stil "user"), höchstens
    85 % der Breite — wie die graue Blase bei Claude, nur kantig."""
    innen = max(4, int(breite * 0.85) - 2)
    zeilen = []
    for absatz in str(text).split("\n"):
        zeilen += _umbruch(absatz, innen) if absatz.strip() else [""]
    bw = min(innen, max(len(z) for z in zeilen)) + 2
    vorne = " " * max(0, breite - bw)
    return [[(vorne, "", None), (" " + z.ljust(bw - 2) + " ", "user", None)] for z in zeilen]


def verlauf_zeilen(log, breite, offen=frozenset(), denken_alle=False, letzte_ai=None,
                   antwort=None, adern=0, streaming=False):
    """Der Verlauf als Zeilen aus Stücken (text, stil, ziel).

    offen: Ziele, die aufgeklappt sind ({("schritt", i), ("denken", i)});
    denken_alle: Strg+D — alles Denken offen; letzte_ai: Index der letzten
    Antwort (nur sie bekommt „retry"); antwort: die laufende Antwort (Text)
    oder None; adern: so viele leere Zeilen für die Denk-Animation."""
    breite = max(8, int(breite))
    zeilen = []
    gruppen = schritte(log)
    teil_von = {j for s in gruppen.values() for j in s["teile"][1:]}
    vorher = None
    for i, (rolle, text) in enumerate(log):
        if i in teil_von:
            continue
        # Luft zwischen zwei Äußerungen; Schritte und Denken kleben an der Antwort
        if zeilen and (rolle in ("user", "hinweis") or
                       (rolle == "ai" and vorher not in ("werkzeug", "denken", "ablage",
                                                         "werkzeug_fehler"))):
            zeilen.append([])
        if rolle == "user":
            zeilen += _nutzer(text, breite)
        elif rolle == "anhang":
            name = str(text).split(":", 1)[-1].strip()
            chip = "[▤ %s]" % name[:max(1, breite - 4)]
            zeilen.append([(" " * max(0, breite - len(chip)), "", None), (chip, "anhang", None)])
        elif rolle == "denken":
            z = ("denken", i)
            auf = denken_alle or z in offen
            kopf = "%s thought · %s chars" % ("▾" if auf else "▸", zahl(len(text)))
            zeilen.append([(kopf, "schritt", z)])
            if auf:
                for u in _umbruch(text, breite - 2):
                    zeilen.append([("  " + u, "denken", None)])
        elif i in gruppen:
            s, z = gruppen[i], ("schritt", i)
            auf = z in offen
            kopf = "Used %s%s %s" % (wort(s["name"]), " ✗" if s["fehler"] else "",
                                     "⌄" if auf else "›")
            zeilen.append([(kopf, "schritt_fehler" if s["fehler"] else "schritt", z)])
            if auf:
                zeilen.append([("  %s" % s["name"], "denken", None)])
                if s["args"]:
                    for u in _umbruch(s["args"], breite - 4)[:4]:
                        zeilen.append([("    " + u, "denken", None)])
                if s["ergebnis"]:
                    erg = _umbruch(s["ergebnis"], breite - 4)
                    for k, u in enumerate(erg[:3]):
                        zeilen.append([(("  → " if k == 0 else "    ") + u, "denken", None)])
                    if len(erg) > 3:
                        zeilen.append([("    …", "denken", None)])
                elif not s["fehler"]:
                    zeilen.append([("    (ergebnis nicht gespeichert)", "denken", None)])
        elif rolle == "ablage":
            doc_id, _, titel = str(text).partition(TRENNER)
            zeilen.append([("▤ " + titel[:max(1, breite - 4)] + " ›", "dok", ("dok", i))])
        elif rolle == "ai":
            for z_text, stil in md_zeilen(text, breite):
                zeilen.append([(z_text, "ai_" + stil if stil else "ai", None)])
            aktionen = [("copy", "aktion", ("kopieren", i))]
            if i == letzte_ai and not streaming:
                aktionen += [(" · ", "leise", None), ("retry", "aktion", ("wiederholen", i))]
            zeilen.append(aktionen)
        elif rolle == "hinweis":
            for z_text in str(text).split("\n"):
                for k in range(0, max(1, len(z_text)), breite):
                    zeilen.append([(z_text[k:k + breite], "hinweis", None)])
        else:                                    # sys & Co.: leise, wie es kommt
            for u in _umbruch(text, breite):
                zeilen.append([(u, "leise", None)])
        vorher = rolle
    if adern:
        if zeilen:
            zeilen.append([])
        zeilen += [[("", "adern", None)] for _ in range(adern)]
    if antwort is not None and antwort.strip():
        if zeilen and not adern:
            zeilen.append([])
        for z_text, stil in md_zeilen(antwort + ("▌" if streaming else ""), breite):
            zeilen.append([(z_text, "ai_" + stil if stil else "ai", None)])
    return zeilen


def ziele(zeilen):
    """Alle anwählbaren Ziele in Reihenfolge (für ↑↓ im Verlauf)."""
    raus = []
    for zeile in zeilen:
        for _t, _s, z in zeile:
            if z is not None and z not in raus:
                raus.append(z)
    return raus


def letzte_antwort(log):
    """Index der letzten Antwort im Verlauf, oder None."""
    return max((i for i, (r, _t) in enumerate(log) if r == "ai"), default=None)
