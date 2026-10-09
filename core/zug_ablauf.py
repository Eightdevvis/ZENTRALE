# core/zug_ablauf.py
#
# Das Ablauf-Protokoll eines Chat-Zugs (2026-10-09): von Sashas Nachricht bis
# zur fertigen Antwort, in Reihenfolge, ohne Auslassungen. Sasha: wie bei
# „Used …" nicht nur sehen, WELCHES Werkzeug lief, sondern was es zurückgab
# und wie die Antwort darauf weiterging.
#
# Nur MITSCHREIBEN. Nichts hier ändert, was ans Modell geht — der
# Prompt-Cache bleibt, wie er ist. Die Schleife (werkzeug_schleife) und die
# Cloud-Wege melden, was passiert; die Chat-Route öffnet das Protokoll und
# speichert es mit der Antwort (Feld `ablauf`, core/gespraeche.py).
#
# Einträge: {art, zeit, t, …}
#   system    fester System-Prompt — NUR Fingerabdruck + Länge (er ist je
#             Zug derselbe, voll gespeichert wäre er 50 Mal dasselbe)
#   kontext   der wechselnde Kontext-Umschlag (Jetzt, offene Zusagen …), voll;
#             anhaenge: Titel der Anhänge der neuesten Nachricht
#   text      Text des Modells vor/zwischen Werkzeugen
#   werkzeug  name, args, ergebnis (wie an die Schleife zurück, mit
#             Kopfzeile [ergebnis: …]), status, dauer
#   frage     Erlaubnis-/Knopf-Frage, optionen, antwort
#   pruefung  Befunde des Ehrlichkeits-Prüfers, Hinweis an die KI, die erste
#             (verworfene) Antwort — danach folgt die zweite
#   fehler / gestoppt   wenn der Zug so endete
#   antwort   die fertige Antwort (wie gespeichert)
#   kosten    Tokens und € aller Runden des Zugs
#
# Scharf ist das Protokoll erst, wenn ein Weg der gross-Schiene `system()`
# gemeldet hat. Lokal (klein) bleibt es leer, abschliessen() gibt dann None —
# die lokale Schiene ist gemessen, wie sie ist, und bekommt nichts Neues.
#
# contextvars wie core/zug.py: zwei Züge können parallel laufen.
# Fundament (Schicht 1, memory/system/bauplan_kern.md): weiß nichts vom Fach.

import contextvars
import hashlib
import json
import time
from datetime import datetime, timezone

# Obergrenze je Eintrag (Sasha-Vorgabe 2026-10-09): gegen Riesen (ganze
# Webseiten, PDFs). Sonst wird NICHTS gekürzt.
EINTRAG_MAX = 50_000

ARTEN = ("system", "kontext", "text", "werkzeug", "frage", "pruefung",
         "fehler", "gestoppt", "antwort", "kosten")

_aktuell = contextvars.ContextVar("zentrale_zug_ablauf", default=None)


class _Protokoll:
    def __init__(self):
        self.t0 = time.monotonic()
        self.eintraege = []
        self.scharf = False
        self.verbrauch = {"runden": 0, "eingabe": 0, "ausgabe": 0,
                          "cache_lesen": 0, "cache_schreiben": 0, "euro": 0.0}
        self.geschaetzt = False


def beginnen():
    """Ein Protokoll für den laufenden Zug öffnen. -> Marke für beenden()."""
    return _aktuell.set(_Protokoll())


def beenden(marke) -> None:
    try:
        _aktuell.reset(marke)
    except (ValueError, RuntimeError):
        _aktuell.set(None)


def _p():
    return _aktuell.get()


def offen() -> bool:
    """Schreibt gerade ein Protokoll mit?"""
    return _aktuell.get() is not None


def _jetzt(p) -> dict:
    return {"zeit": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "t": round(time.monotonic() - p.t0, 3)}


def kappen(eintrag: dict, grenze: int = EINTRAG_MAX) -> dict:
    """Einen Eintrag unter `grenze` Zeichen bringen: das längste Textfeld
    wird hinten gekürzt, mit Vermerk; args, die allein zu groß sind, werden
    dafür zu JSON-Text. Kleine Einträge bleiben unverändert."""
    def laenge(e):
        return len(json.dumps(e, ensure_ascii=False, default=str))
    if laenge(eintrag) <= grenze:
        return eintrag
    e = dict(eintrag)
    weg_gesamt = 0
    for _ in range(8):                       # wenige Felder, wenige Durchgänge
        zu_viel = laenge(e) - grenze
        if zu_viel <= 0:
            break
        felder = [(k, v) for k, v in e.items()
                  if k not in ("art", "zeit", "t") and isinstance(v, (str, dict, list))]
        if not felder:
            break
        k, v = max(felder, key=lambda kv: len(json.dumps(kv[1], ensure_ascii=False,
                                                           default=str)))
        if not isinstance(v, str):
            v = json.dumps(v, ensure_ascii=False, default=str)
        vermerk_platz = 120
        behalten = max(0, len(v) - zu_viel - vermerk_platz)
        weg = len(v) - behalten
        weg_gesamt += weg
        e[k] = (v[:behalten] + f"\n[… {weg:,} Zeichen gekürzt — Obergrenze "
                f"{grenze:,} Zeichen je Eintrag …]").replace(",", ".")
    e["gekuerzt"] = weg_gesamt
    return e


def _dazu(art: str, **felder):
    p = _p()
    if p is None:
        return None
    e = {"art": art, **_jetzt(p)}
    e.update({k: v for k, v in felder.items() if v is not None})
    e = kappen(e)
    p.eintraege.append(e)
    return e


# ── Melden (von den Wegen und der Schleife) ─────────────────────────────

def fingerabdruck(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def system(text: str) -> None:
    """Der feste System-Prompt: nur Fingerabdruck und Länge. Macht das
    Protokoll scharf (nur die gross-Schiene ruft das)."""
    p = _p()
    if p is None:
        return
    p.scharf = True
    _dazu("system", fingerabdruck=fingerabdruck(text), laenge=len(text or ""))


def kontext(text: str, anhaenge=None) -> None:
    """Der wechselnde Umschlag dieses Zugs, vollständig."""
    _dazu("kontext", text=str(text or ""), anhaenge=list(anhaenge) if anhaenge else None)


def text(inhalt: str, verworfen: bool = False) -> None:
    if str(inhalt or "").strip():
        _dazu("text", text=str(inhalt), verworfen=True if verworfen else None)


def werkzeug_beginnt(name: str, args: dict):
    """-> der Eintrag (für werkzeug_fertig) oder None."""
    p = _p()
    if p is None:
        return None
    e = _dazu("werkzeug", name=str(name), args=dict(args or {}))
    e["_start"] = time.monotonic()
    return e


def status_aus(ergebnis: str, ist_fehler: bool = False) -> str:
    """Status aus der Kopfzeile „[ergebnis: …]" (werkzeug_befund.mit_kopf)."""
    t = str(ergebnis or "")
    if t.startswith("[ergebnis: ") and "]" in t:
        return t[len("[ergebnis: "):t.index("]")].strip()
    return "fehlgeschlagen" if ist_fehler else "ok"


def werkzeug_fertig(eintrag, ergebnis, ist_fehler: bool = False, *, status=None) -> None:
    if eintrag is None or _p() is None:
        return
    start = eintrag.pop("_start", None)
    if start is not None:
        eintrag["dauer"] = round(time.monotonic() - start, 3)
    eintrag["ergebnis"] = str(ergebnis if ergebnis is not None else "")
    eintrag["status"] = status or status_aus(eintrag["ergebnis"], ist_fehler)
    if ist_fehler:
        eintrag["fehler"] = True
    neu = kappen(eintrag)
    if neu is not eintrag:
        eintrag.clear()
        eintrag.update(neu)


def frage(frage_: str, optionen, antwort, *, art: str = "knopf") -> None:
    """art: knopf (ask_choice) | erlaubnis (Gate). antwort None = keine."""
    _dazu("frage", frage=str(frage_ or ""), optionen=[str(o) for o in optionen or []],
          antwort=None if antwort is None else str(antwort),
          keine_antwort=True if antwort is None else None, wie=art)


def pruefung(befunde, hinweis: str, erste_antwort: str) -> None:
    _dazu("pruefung", befunde=list(befunde or []), hinweis=str(hinweis or ""),
          erste_antwort=str(erste_antwort or ""))


def fehler(text_: str) -> None:
    _dazu("fehler", text=str(text_ or ""))


def gestoppt() -> None:
    _dazu("gestoppt")


def verbrauch(*, eingabe=0, ausgabe=0, cache_lesen=0, cache_schreiben=0,
              euro=0.0, geschaetzt=False) -> None:
    """Eine gebuchte Runde (cloud._log_usage & Co.) aufsummieren."""
    p = _p()
    if p is None:
        return
    v = p.verbrauch
    v["runden"] += 1
    v["eingabe"] += int(eingabe or 0)
    v["ausgabe"] += int(ausgabe or 0)
    v["cache_lesen"] += int(cache_lesen or 0)
    v["cache_schreiben"] += int(cache_schreiben or 0)
    v["euro"] = round(v["euro"] + float(euro or 0.0), 6)
    p.geschaetzt = p.geschaetzt or bool(geschaetzt)


# ── Abschließen (die Route) ─────────────────────────────────────────────

def abschliessen(antwort: str | None = None) -> list | None:
    """Antwort und Kosten anhängen. -> die Einträge, oder None (nicht scharf:
    lokal, klein, kein Protokoll offen)."""
    p = _p()
    if p is None or not p.scharf:
        return None
    if antwort is not None:
        _dazu("antwort", text=str(antwort))
    if p.verbrauch["runden"]:
        _dazu("kosten", **p.verbrauch, geschaetzt=True if p.geschaetzt else None)
    for e in p.eintraege:
        e.pop("_start", None)
    return list(p.eintraege)


# ── Als Text (Export /trace) ────────────────────────────────────────────

_WORT = {"system": "System-Prompt (fest)", "kontext": "Kontext dieses Zugs",
         "text": "Text der KI", "werkzeug": "Werkzeug", "frage": "Frage an Sasha",
         "pruefung": "Prüfung", "fehler": "Fehler", "gestoppt": "Gestoppt",
         "antwort": "Antwort", "kosten": "Kosten"}


def kopfzeile(e: dict) -> str:
    """Eine Zeile je Eintrag — dieselbe Idee wie die Kopfzeile in der TUI."""
    art = e.get("art")
    if art == "system":
        return f"System-Prompt (fest) · {e.get('laenge', 0)} Zeichen · {e.get('fingerabdruck')}"
    if art == "werkzeug":
        teile = [f"Werkzeug {e.get('name')}", str(e.get("status") or "kein Ergebnis")]
        if e.get("dauer") is not None:
            teile.append(f"{e['dauer']:.1f} s")
        return " · ".join(teile)
    if art == "frage":
        a = e.get("antwort")
        return f"Frage an Sasha → {a if a is not None else '(keine Antwort)'}"
    if art == "pruefung":
        return f"Prüfung: {len(e.get('befunde') or [])} Befund(e), zweite Runde"
    if art == "kosten":
        return (f"Kosten · {e.get('runden')} Runde(n) · ein {e.get('eingabe')} · "
                f"aus {e.get('ausgabe')} · Cache {e.get('cache_lesen')} · "
                f"{float(e.get('euro') or 0):.4f} €" + (" (geschätzt)" if e.get("geschaetzt") else ""))
    wort = _WORT.get(art, str(art))
    t = str(e.get("text") or "")
    if art == "text" and e.get("verworfen"):
        wort += " (verworfen)"
    return f"{wort} · {len(t)} Zeichen" if t else wort


def inhalt(e: dict) -> str:
    """Der ganze Inhalt eines Eintrags als Text (ohne Kopfzeile)."""
    art = e.get("art")
    if art == "werkzeug":
        args = e.get("args")
        args = args if isinstance(args, str) else json.dumps(args or {}, ensure_ascii=False,
                                                             indent=2, default=str)
        return f"Argumente:\n{args}\n\nErgebnis:\n{e.get('ergebnis', '(kein Ergebnis — Zug endete vorher)')}"
    if art == "frage":
        return (f"{e.get('frage')}\nKnöpfe: {' | '.join(e.get('optionen') or [])}\n"
                f"Antwort: {e.get('antwort') if e.get('antwort') is not None else '(keine)'}")
    if art == "pruefung":
        bef = "\n".join("- " + (b.get("satz") or b.get("kennung") or str(b))
                        for b in e.get("befunde") or [] if isinstance(b, dict))
        return (f"Befunde:\n{bef or '-'}\n\nHinweis an die KI:\n{e.get('hinweis')}\n\n"
                f"Erste (verworfene) Antwort:\n{e.get('erste_antwort')}")
    if art == "kontext":
        anh = e.get("anhaenge")
        return str(e.get("text") or "") + (("\n\nAnhänge: " + ", ".join(map(str, anh))) if anh else "")
    if art in ("system", "kosten", "gestoppt"):
        return ""
    return str(e.get("text") or "")


def als_text(eintraege: list, titel: str = "") -> str:
    """Das ganze Protokoll als lesbare Textdatei."""
    zeilen = [titel or "Ablauf eines Zugs", ""]
    for nr, e in enumerate(eintraege or [], 1):
        if not isinstance(e, dict):
            continue
        zeilen.append(f"── {nr}. [+{float(e.get('t') or 0):.2f} s] {kopfzeile(e)}")
        voll = inhalt(e)
        if voll:
            zeilen += [voll, ""]
        if e.get("gekuerzt"):
            zeilen.append(f"(gekürzt um {e['gekuerzt']} Zeichen)")
    return "\n".join(zeilen).rstrip() + "\n"
