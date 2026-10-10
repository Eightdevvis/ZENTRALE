# core/quellen.py
#
# Die Quellen-Zeile (2026-10-10): welche Seiten die KI in einem Zug
# tatsächlich GELESEN hat — Python zieht sie aus den Werkzeug-Ergebnissen,
# wie die Erledigt-Zeile aus dem Werkzeug-Protokoll (core/ehrlichkeit.py).
#
# Anlass: Prüfstand 10.10., f08. Die KI fand die Zeiten richtig, nannte die
# Seite aber nur als „LSF, Seite Analysis I" — die Adresse fehlte. Sasha:
# „besser wenn die adresse bei sowas einfach gar nich von der ki
# runtergezwungen wird, weil wir können die ja einfach durch code rausziehen
# lassen". Also muss die KI keine URL mehr abschreiben (und kann keine
# falsch abschreiben); was sie gelesen hat, steht ohnehin im Protokoll.
#
# Was zählt:
#   browser_*  die Seite, auf der die KI STEHEN blieb. Eine Seite, von der
#              sie weiterklickte oder zurückging, war Durchgang (Startseite,
#              Fakultät, Suchmaske) — sonst stünde jeder Ast eines LSF-Baums
#              in der Zeile. Ausdrücklich mit browser_read gelesen zählt sie
#              immer. Ein neues browser_open schließt die Kette davor ab.
#   fetch_url  jede geladene Seite (Status ok)
#   fetch_document  nur per http(s)-Adresse, nicht aus einer Datei
# Nicht: web_search — Treffer sind Hinweise, nicht gelesen (core/web.py).
# Nicht: was fehlschlug (B-LADEN, „nicht erreichbar", abgelehnt).
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md): nur Text. Die Form
# der Ergebnisse kommt aus core/ki_browser.py (Seite/Adresse) und
# core/web.py (Inhalt von …/Titel); tests/test_quellen.py hält beides fest.

import re
from urllib.parse import urlsplit

MAX = 6                       # mehr Seiten nennt die Zeile nicht

_LAEDT = ("browser_open", "browser_click", "browser_type", "browser_back")
_KOPF = re.compile(r"^\[ergebnis: (\w+)\]")
_SEITE = re.compile(r"^Seite: „(.*)“\s*$", re.M)
_ADRESSE = re.compile(r"^Adresse: (\S+)", re.M)
_INHALT = re.compile(r"^Inhalt von (\S+?):\s*$", re.M)
_TITEL = re.compile(r"^Titel: „(.*)“\s*$", re.M)


def _ok(text: str, ist_fehler: bool) -> bool:
    if ist_fehler:
        return False
    m = _KOPF.match(str(text or ""))
    return (m.group(1) == "ok") if m else not str(text or "").lstrip().startswith("[")


def _http(url) -> bool:
    return str(url or "").strip().lower().startswith(("http://", "https://"))


def _host(url) -> str:
    try:
        return urlsplit(url).hostname or url
    except ValueError:
        return url


def _quelle(titel, url, werkzeug) -> dict | None:
    url = str(url or "").strip()
    if not _http(url):
        return None
    titel = " ".join(str(titel or "").split()) or _host(url)
    return {"titel": titel[:120], "url": url[:500], "werkzeug": werkzeug}


def _browser_seite(name: str, text: str) -> dict | None:
    adresse = _ADRESSE.search(text)
    if not adresse:
        return None
    titel = _SEITE.search(text)
    return _quelle(titel.group(1) if titel else "", adresse.group(1), name)


def _fetch_url(args: dict, text: str) -> dict | None:
    m = _INHALT.search(text)
    url = m.group(1) if m else str((args or {}).get("url") or "").strip()
    if url and not _http(url):
        url = "https://" + url
    titel = _TITEL.search(text)
    return _quelle(titel.group(1) if titel else "", url, "fetch_url")


def aus_schritten(schritte) -> list:
    """Werkzeug-Aufrufe eines Zugs [(name, args, ergebnistext, ist_fehler)]
    in Reihenfolge -> [{titel, url, werkzeug}], jede Adresse einmal."""
    raus, gesehen = [], set()
    offen = None                   # die Browser-Seite, auf der die KI gerade steht

    def merken(q):
        if not q:
            return
        schluessel = q["url"].split("#", 1)[0].rstrip("/")
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            raus.append(q)

    for name, args, text, ist_fehler in schritte or []:
        text = str(text or "")
        ok = _ok(text, ist_fehler)
        if name in _LAEDT:
            seite = _browser_seite(name, text) if ok else None
            if seite is None:      # nichts geladen (Fehler, tippen ohne Enter)
                continue
            if name == "browser_open":
                merken(offen)      # die Kette davor endete dort
            offen = seite
        elif name == "browser_read" and ok:
            seite = _browser_seite(name, text)
            if seite and offen and offen["url"] == seite["url"]:
                seite = dict(offen, werkzeug="browser_read")
            merken(seite)
        elif name == "browser_close":
            merken(offen)
            offen = None
        elif name == "fetch_url" and ok:
            merken(_fetch_url(args, text))
        elif name == "fetch_document" and ok and _http((args or {}).get("url")):
            merken(_quelle((args or {}).get("name"), args["url"], "fetch_document"))
    merken(offen)
    return raus[:MAX]


def zeile(liste) -> str:
    """„Quellen: „Analysis I“ – http://… · „Ferien“ – https://…" — Sasha
    liest das unter der Antwort. Leer, wenn nichts gelesen wurde."""
    teile = [f"„{q.get('titel')}“ – {q.get('url')}" for q in liste or []
             if isinstance(q, dict) and q.get("url")]
    return ("Quellen: " + " · ".join(teile)) if teile else ""
