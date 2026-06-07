# core/web.py
#
# Internet-Pipe für die ZENTRALE-KI: Web-Suche + Webseite holen.
#
# ── Zweck ─────────────────────────────────────────────────────────────
# ZENTRALE war bisher vollständig offline. Dieses Modul ist das EINZIGE,
# das bewusst nach draußen telefoniert (außer dem lokalen Ollama). Es gibt
# der KI zwei Werkzeuge:
#   suche(query) – sucht im Internet, liefert Trefferliste (Titel/URL/Snippet)
#   hole(url)    – lädt eine konkrete Seite und gibt deren Textinhalt zurück
#
# ── Such-Quelle (heute: DuckDuckGo keyless) ───────────────────────────
# Die eigentliche Suche steckt bewusst in EINER Funktion (`_ddg_search`).
# Heute scrapen wir den HTML-Endpoint von DuckDuckGo - kein API-Key, kein
# Account, kein Cloud-Vertrag (passt zur Offline/Kontroll-Linie). Wenn wir
# später auf SearXNG (self-hosted) oder die Brave-API umstellen wollen,
# tauschen wir NUR `_ddg_search` aus - `suche()`/`hole()` und ai.py bleiben
# unangetastet. "Scraping" heißt: wir schicken dieselbe Anfrage wie ein
# Browser und schnippeln die Treffer aus dem zurückgelieferten HTML. Das ist
# fragil (ändert DDG sein Seiten-Layout, müssen die Regexe nachgezogen werden).
#
# ── Transparenz / Tripwire ────────────────────────────────────────────
# Aller HTTP-Verkehr läuft durch net.py. Da DuckDuckGo und beliebige URLs
# echte Internet-Ziele sind (kein localhost/LAN), leuchtet jeder Call
# AUTOMATISCH im orangen Internet-Panel des Dashboards auf - man sieht live,
# was rein- und rausgeht. Kein versteckter Traffic, kein Sonder-Logging nötig.

import re
import html as _html
from urllib.parse import urlencode, urlparse, parse_qs, unquote

import net  # transparenter HTTP-Wrapper (loggt jeden Call ins Dashboard)


# DuckDuckGo HTML-Endpoint. Liefert eine simple Trefferseite ohne JavaScript,
# gut parsebar. (Der "lite"-Endpoint ginge auch, html/ ist stabiler bestückt.)
_DDG_URL = "https://html.duckduckgo.com/html/"

# Browser-User-Agent: ohne diesen Header gibt DDG dem urllib-Default oft eine
# leere/abweisende Antwort. Wir geben uns als normaler Firefox aus.
_UA = ("Mozilla/5.0 (X11; Linux x86_64; rv:121.0) "
       "Gecko/20100101 Firefox/121.0")

# Default-Timeouts/-Limits. Internet ist langsamer als localhost -> großzügiger
# Timeout. max_chars kappt den Seitentext, damit hole() nicht das knappe
# Kontextfenster (num_ctx=8192) sprengt.
_TIMEOUT_S       = 15
_DEFAULT_RESULTS = 5
_DEFAULT_MAXCHARS = 4000


# ── HTML-Parsing-Regexe (DDG-Trefferseite) ────────────────────────────
# Jeder Treffer ist ein <a class="result__a" href="...">Titel</a>, der
# Snippet ein <a class="result__snippet">...</a>. Die hrefs sind DDG-
# Redirect-Links (//duckduckgo.com/l/?uddg=<ziel-url>&...) - die echte
# Ziel-URL steckt im uddg-Parameter (URL-codiert).
_RESULT_RE = re.compile(
    r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)
_SNIPPET_RE = re.compile(
    r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
    re.DOTALL | re.IGNORECASE,
)

# Für hole(): <script>/<style>-Blöcke komplett raus (inkl. Inhalt), bevor
# wir Tags strippen - sonst landet JS-Code im Text.
_SCRIPT_STYLE_RE = re.compile(
    r'<(script|style)[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)
_TAG_RE = re.compile(r'<[^>]+>')


def _strip_html(s: str) -> str:
    """
    Macht aus HTML-Schnipsel reinen Text: Tags weg, HTML-Entities (&amp; ->
    &) auflösen, Whitespace zu einzelnen Spaces zusammenfalten.
    """
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _decode_ddg_href(href: str) -> str:
    """
    Holt aus einem DDG-Redirect-Link die echte Ziel-URL. DDG verpackt sie als
    //duckduckgo.com/l/?uddg=<url-codiert>&rut=... - wir ziehen den uddg-
    Parameter raus und decodieren ihn. Schon-direkte Links geben wir durch
    (nur protokolllose //host-Links auf https heben).
    """
    if "uddg=" in href:
        params = parse_qs(urlparse(href).query)
        if params.get("uddg"):
            return unquote(params["uddg"][0])
    if href.startswith("//"):
        return "https:" + href
    return href


def _ddg_search(query: str, max_results: int):
    """
    DIE austauschbare Such-Implementierung. Fragt DuckDuckGo, parst die
    Trefferseite, gibt eine Liste {title, url, snippet} zurück. Wirft bei
    Netz-/Parse-Fehlern (suche() fängt das ab).

    -> Wer die Such-Quelle wechseln will (SearXNG/Brave), ersetzt NUR diese
       Funktion; der Rückgabe-Typ (Liste von Dicts) bleibt gleich.
    """
    url  = _DDG_URL + "?" + urlencode({"q": query})
    body = net.get(url, timeout=_TIMEOUT_S, headers={"User-Agent": _UA})
    page = body.decode("utf-8", errors="replace")

    titles   = _RESULT_RE.findall(page)     # [(href, titel_html), ...]
    snippets = _SNIPPET_RE.findall(page)    # [snippet_html, ...]

    # WICHTIG: DDG mischt bezahlte Anzeigen unter die Treffer - dieselbe
    # CSS-Klasse, aber der href zeigt auf einen Ad-Tracker
    # (duckduckgo.com/y.js?ad_provider=...) statt auf den echten /l/?uddg=-
    # Redirect. Die filtern wir raus, sonst kriegt die KI Werbung als "Fakt".
    results = []
    for i, (href, title_html) in enumerate(titles):
        if "y.js" in href or "ad_provider" in href or "ad_domain" in href:
            continue                      # Anzeige -> überspringen
        snippet_html = snippets[i] if i < len(snippets) else ""
        results.append({
            "url":     _decode_ddg_href(href),
            "title":   _strip_html(title_html),
            "snippet": _strip_html(snippet_html),
        })
        if len(results) >= max_results:   # genug echte Treffer
            break
    return results


def suche(query: str, max_results: int = _DEFAULT_RESULTS) -> str:
    """
    Web-Suche für das KI-Tool `web_suche`. Gibt ein menschen-/modell-lesbares
    Trefferlisting als String zurück (wird als tool-Result an die KI geschickt).
    Fehler werden NICHT geworfen, sondern als [Fehler: ...]-String geliefert,
    damit die KI im selben Zug sinnvoll reagieren kann statt die Tool-Loop
    abzubrechen.
    """
    query = (query or "").strip()
    if not query:
        return "[Fehler: leere Suchanfrage]"
    try:
        results = _ddg_search(query, max_results)
    except Exception as e:
        return f"[Fehler bei der Web-Suche: {e}]"
    if not results:
        return f"Keine Treffer für '{query}'."

    lines = [f"Web-Suche '{query}' - {len(results)} Treffer:"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
    return "\n".join(lines)


def hole(url: str, max_chars: int = _DEFAULT_MAXCHARS) -> str:
    """
    Lädt eine Webseite und gibt ihren Textinhalt zurück (für das KI-Tool
    `hole_url`). HTML wird zu reinem Text reduziert und auf max_chars gekürzt,
    damit das Kontextfenster nicht überläuft. Fehler kommen als String zurück.
    """
    url = (url or "").strip()
    if not url:
        return "[Fehler: keine URL angegeben]"
    # Schema ergänzen, falls die KI/der User nur 'example.com' liefert.
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        body = net.get(url, timeout=_TIMEOUT_S, headers={"User-Agent": _UA})
    except Exception as e:
        return f"[Fehler beim Laden von {url}: {e}]"

    page = body.decode("utf-8", errors="replace")
    page = _SCRIPT_STYLE_RE.sub(" ", page)   # JS/CSS samt Inhalt raus
    text = _strip_html(page)

    if not text:
        return f"[Seite {url} geladen, aber kein lesbarer Text gefunden]"
    if len(text) > max_chars:
        text = text[:max_chars] + " […abgeschnitten]"
    return f"Inhalt von {url}:\n{text}"
