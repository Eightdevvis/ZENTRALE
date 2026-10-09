# core/werkzeug_browser.py
#
# Die Einträge der Browser-Werkzeuge (browser_open & Co.) und ihre Fragen an
# Sasha. werkzeug_register hängt EINTRAEGE hinten an seine Liste; ausgeführt
# wird in core/ki_browser.py, der Browser selbst ist core/browser_sitzung.py.
#
# 2026-10-09 (memory/ki/ki_system.md, „Browser"). Nur gross: das lokale qwen
# ist darauf nicht gemessen. Die Beschreibungen bleiben kurz (sie reisen in
# jedem Zug im gecachten Kopf mit); das WIE steht im Skill „browser".
#
# ── Wann Sasha gefragt wird ────────────────────────────────────────────
# Einmal je Host und Gespräch: das erste browser_open auf einen Host fragt
# „Soll ich im Browser <host> öffnen?". Danach sind Öffnen, Klicken und
# Tippen auf diesem Host frei. Ein Link auf einen anderen Host fragt neu.
# Ein Formular mit Passwortfeld abschicken fragt immer.
#
# Warum NICHT über „ja, für dieses Gespräch" des Erlaubnis-Gates: das gilt
# pro Werkzeug, nicht pro Host — nach einem Ja zu uni-saarland.de wäre jede
# andere Seite frei gewesen. Deshalb fragt die Regel hier (erlaubnis=f(args))
# nur, wenn der Host noch nicht erlaubt ist, und das Ja gilt „nur dieses mal"
# (nur_einmal): gemerkt wird es nicht im Gate, sondern als erlaubter Host in
# browser_sitzung — das tut der Ausführer, denn er läuft nur nach einem Ja.
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import browser_sitzung
import zug
from werkzeug_eintrag import Werkzeug


def _kurz(text, n: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


# ── Wann gefragt wird ───────────────────────────────────────────────────

def _host_der_adresse(args: dict) -> str:
    """Host aus browser_open(url), nur am Text erkannt (kein Netz). "" wenn
    die Adresse nicht taugt — dann fragt niemand, der Ausführer lehnt ab."""
    try:
        return browser_sitzung.adresse_pruefen(args.get("url"), dns=False)[1]
    except browser_sitzung.BrowserFehler:
        return ""


def _oeffnen_fragen(args: dict) -> bool:
    host = _host_der_adresse(args)
    return bool(host) and not browser_sitzung.host_erlaubt(zug.gespraech(), host)


def _element(args: dict):
    return browser_sitzung.element(zug.gespraech(), args.get("nr"))


def _neuer_host(e) -> str:
    """Host eines Links, für den noch keine Erlaubnis da ist, sonst ""."""
    if not e or e.get("art") != "Link":
        return ""
    href = str(e.get("href") or "")
    if not href.lower().startswith(("http://", "https://")):
        return ""
    host = e.get("host") or ""
    if not host or (not browser_sitzung.lokal_erlaubt() and browser_sitzung.ist_lokal(host, dns=False)):
        return ""
    return "" if browser_sitzung.host_erlaubt(zug.gespraech(), host) else host


def _klick_fragen(args: dict) -> bool:
    e = _element(args)
    if not e:
        return False
    if e.get("passwort_form") and e.get("art") == "Knopf":
        return True
    return bool(_neuer_host(e))


def _tippen_fragen(args: dict) -> bool:
    e = _element(args)
    return bool(e and e.get("passwort_form") and args.get("enter")
                and e.get("typ") != "password")


def _immer_einzeln(args: dict) -> bool:
    # Wenn hier gefragt wird, dann einzeln — gemerkt wird der Host, nicht
    # das Werkzeug (Kopf der Datei).
    return True


# ── Die Fragen ──────────────────────────────────────────────────────────

def _seitenhost() -> str:
    s = browser_sitzung.stand(zug.gespraech())
    return (s or {}).get("host") or "dieser Seite"


def _frage_oeffnen(args: dict) -> str:
    host = _host_der_adresse(args)
    if not host:
        return "Soll ich eine Seite im Browser öffnen?"
    return (f"Soll ich im Browser {host} öffnen? Auf {host} lese und klicke ich "
            f"dann in diesem Gespräch ohne weitere Frage.")


def _frage_klick(args: dict) -> str:
    e = _element(args) or {}
    text = _kurz(e.get("text"), 50)
    if e.get("passwort_form") and e.get("art") == "Knopf":
        return (f"Soll ich das Anmeldeformular auf {_seitenhost()} absenden"
                + (f" („{text}“)" if text else "") + "?")
    host = _neuer_host(e)
    if host:
        return (f"Der Link „{text or '…'}“ führt zu {host}. Soll ich im Browser "
                f"{host} öffnen?")
    return "Soll ich im Browser weiterklicken?"


def _frage_tippen(args: dict) -> str:
    return f"Soll ich das Anmeldeformular auf {_seitenhost()} absenden?"


# ── Die Einträge ────────────────────────────────────────────────────────

_NR = {"type": "integer", "description": "Nummer aus der Liste der Seite."}

EINTRAEGE = [
    Werkzeug(
        name="browser_open",
        erlaubnis=_oeffnen_fragen,
        nur_einmal=_immer_einzeln,
        immer_erlaubbar=False,
        frage=_frage_oeffnen,
        alltag="seiten im browser öffnen",
        gross=("Öffnet eine Seite in einem echten Browser (ohne Fenster): Text plus "
               "nummerierte Liste zum Klicken. Statt fetch_url, wenn die Seite nur "
               "Menü oder Baum zeigt, sich erst durch Klicken aufbaut oder eine "
               "Sitzung braucht (z. B. Vorlesungsverzeichnis LSF). Anleitung: Skill browser."),
        parameter={"type": "object",
                   "properties": {"url": {"type": "string", "description": "Adresse (http/https)."}},
                   "required": ["url"]},
    ),
    Werkzeug(
        name="browser_click",
        erlaubnis=_klick_fragen,
        nur_einmal=_immer_einzeln,
        immer_erlaubbar=False,
        frage=_frage_klick,
        alltag="im browser klicken",
        gross="Klickt Element nr der Liste; Ergebnis wie browser_open.",
        parameter={"type": "object", "properties": {"nr": _NR}, "required": ["nr"]},
    ),
    Werkzeug(
        name="browser_type",
        erlaubnis=_tippen_fragen,
        nur_einmal=_immer_einzeln,
        immer_erlaubbar=False,
        frage=_frage_tippen,
        alltag="im browser formulare ausfüllen",
        gross="Tippt text in Feld nr (bei einer Auswahl: den Eintrag); enter=true schickt ab.",
        parameter={"type": "object",
                   "properties": {"nr": _NR,
                                  "text": {"type": "string"},
                                  "enter": {"type": "boolean",
                                            "description": "Danach Enter drücken."}},
                   "required": ["nr", "text"]},
    ),
    Werkzeug(
        name="browser_find",
        gross="Sucht Elemente der offenen Seite nach Text, mit Nummern.",
        parameter={"type": "object",
                   "properties": {"text": {"type": "string"}},
                   "required": ["text"]},
    ),
    Werkzeug(
        name="browser_read",
        gross="Weiterer Text der offenen Seite ab Zeichen ab.",
        parameter={"type": "object",
                   "properties": {"ab": {"type": "integer"}},
                   "required": []},
    ),
    Werkzeug(
        name="browser_back",
        gross="Eine Seite zurück.",
        parameter={"type": "object", "properties": {}},
    ),
    Werkzeug(
        name="browser_close",
        gross="Schließt den Browser dieses Gesprächs.",
        parameter={"type": "object", "properties": {}},
    ),
    Werkzeug(
        name="browser_screenshot",
        schreibt=True,
        beweis="liest das Bild aus der Ablage nach: liegt es da, wie groß",
        gross=("Legt ein Bild der offenen Seite in Sashas Ablage — für ihn, du siehst es "
               "nicht. Nur wenn er es sehen will oder Text nicht reicht."),
        parameter={"type": "object",
                   "properties": {"titel": {"type": "string"}},
                   "required": []},
    ),
]
