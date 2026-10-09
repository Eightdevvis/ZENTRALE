# core/browser_sitzung.py
#
# Ein echter Browser ohne Fenster (Chromium über Playwright), den die KI über
# Text steuert: Seite öffnen, nummerierte Liste der klickbaren Dinge, klicken,
# tippen, zurück. Kein Bildschirm, keine Koordinaten.
#
# 2026-10-09, Anlass: das Vorlesungsverzeichnis der Uni (LSF, QIS/HIS) ist
# ein Baum, der sich erst durch Klicken aufbaut, oft in Rahmen (frames).
# fetch_url bekam am 08.10. nur den Navigationsbaum; die KI schloss daraus
# „ohne Login komm ich nicht tiefer". Ein Browser sieht, was Sasha sieht.
#
# ── Aufbau ─────────────────────────────────────────────────────────────
# Playwright (sync) bindet sich an den Thread, der es gestartet hat. Die
# Werkzeuge laufen aber im Thread des jeweiligen Chat-Zugs. Deshalb EIN
# eigener Arbeiter-Thread, der alles mit Playwright erledigt; die Werkzeuge
# reichen Aufträge hinein und warten. Ein Browser-Prozess für alles
# (Auftrag: höchstens einer), darin je Gespräch ein eigener Kontext (eigene
# Cookies) mit einer Seite. 10 Minuten nichts getan → Sitzung zu; keine
# Sitzung mehr → Browser-Prozess beendet (der Pi hat wenig Speicher).
#
# Fehlt Playwright oder Chromium (z. B. auf dem Pi), gibt es keinen Absturz,
# sondern BrowserFehler("B-NICHT-EINGERICHTET").
#
# ── Was der Browser darf ───────────────────────────────────────────────
# - nur http/https; nichts im eigenen Rechner/Netz (localhost, 192.168.…),
#   außer Einstellung browser_lokal_erlaubt (für Tests mit eigenem Server);
# - Seiten (Dokumente, auch in Rahmen) nur von Hosts, die Sasha in diesem
#   Gespräch erlaubt hat. Ein Klick, der woanders hinführt, wird nicht
#   geladen (B-ANDERE-SEITE) — die KI muss browser_open aufrufen, und Sasha
#   wird gefragt. Bilder, Skripte, Stile dürfen von anderswo kommen, sonst
#   bricht jede Seite; aber nie aus dem eigenen Netz.
# - Weiterleitungen holt der Arbeiter selbst (ohne ihnen zu folgen) und
#   prüft das Ziel, bevor der Browser es lädt: Playwright ruft seinen
#   Abfang-Haken nur für die ERSTE Adresse einer Weiterleitung auf — so
#   käme eine erlaubte Seite per 302 an localhost vorbei.
# - keine Downloads, keine Service-Worker; JavaScript nur das der Seite.
#   Unser eigenes Skript (Liste der Elemente, Text) ist fest im Code, aus
#   dem Text der KI wird nie etwas ausgeführt.
#
# Dienste (Schicht 2, memory/system/bauplan_kern.md): weiß nichts von der
# KI; Fragen, Texte und Fehlercodes für die KI stehen in core/ki_browser.py.

import html as _html
import importlib.util
import ipaddress
import json as _json
import queue
import re
import socket
import threading
import time
from urllib.parse import urlsplit

import ai_config
import state


SCHRITT_MS = 20_000          # Zeitgrenze je Schritt (laden, klicken, tippen)
LEERLAUF_S = 600             # so lange darf eine Sitzung nichts tun
PRUEF_S = 15                 # so oft schaut der Arbeiter nach Leerlauf
MAX_SITZUNGEN = 3            # Gespräche mit offenem Browser gleichzeitig
MAX_ELEMENTE = 2_000         # mehr Elemente einer Seite merken wir uns nicht
MAX_TEXT = 400_000           # mehr Seitentext auch nicht
_RUHE_MS = 2_500             # nach dem Laden: kurz auf nachladende Skripte warten
_DNS_MERKEN_S = 60
_MAX_UMLEITUNGEN = 10
_SEITEN_ARTEN = ("text/", "image/", "application/xhtml+xml", "application/xml")
_SCHEMA = re.compile(r"^[a-z][a-z0-9+.\-]*:(?!\d)", re.IGNORECASE)
_ZWISCHENSEITE = ('<!doctype html><meta http-equiv="refresh" content="0;url={html}">'
                  '<script>location.replace({js})</script>')


class BrowserFehler(Exception):
    """Ein Schritt ging nicht. code: core/fehlercodes.py (B-…)."""

    def __init__(self, code: str, grund: str):
        super().__init__(f"{code}: {grund}")
        self.code = code
        self.grund = grund


# ── Ist der Browser eingerichtet? ─────────────────────────────────────

def verfuegbar() -> tuple:
    """(True, "") oder (False, Grund in Alltagswörtern). Prüft nur, ob das
    Paket da ist; ob Chromium startet, zeigt erst der erste Start."""
    if importlib.util.find_spec("playwright") is None:
        return False, "das Browser-Paket (Playwright) ist auf diesem Rechner nicht installiert"
    return True, ""


# ── Adressen ──────────────────────────────────────────────────────────

def lokal_erlaubt() -> bool:
    """Einstellung browser_lokal_erlaubt: auch Adressen im eigenen Rechner/
    Netz. Aus, außer für Tests mit eigenem Server (oder bewusst gesetzt)."""
    wert = ai_config.setting("browser_lokal_erlaubt")
    return str(wert).strip().lower() in ("1", "true", "ja", "an", "yes", "on")


_dns = {}
_dns_lock = threading.Lock()


def _ip_lokal(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if getattr(a, "ipv4_mapped", None):
        a = a.ipv4_mapped
    return (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
            or a.is_multicast or a.is_unspecified)


def ist_lokal(host: str, dns: bool = True) -> bool:
    """Liegt `host` im eigenen Rechner oder Netz? Mit dns=False nur am Namen
    erkennbar (für die Frage an Sasha: schnell und ohne Netz)."""
    host = (host or "").strip("[]").lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return True
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        return _ip_lokal(host)
    except ValueError:
        pass
    if not dns:
        return False
    jetzt = time.monotonic()
    with _dns_lock:
        merk = _dns.get(host)
        if merk and jetzt - merk[0] < _DNS_MERKEN_S:
            return merk[1]
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except OSError:
        ips = set()           # unbekannt: laden scheitert dann ohnehin
    lokal = any(_ip_lokal(ip) for ip in ips)
    with _dns_lock:
        _dns[host] = (jetzt, lokal)
    return lokal


def host_von(url) -> str:
    """Der Host einer Adresse (klein geschrieben), "" wenn keiner."""
    try:
        return (urlsplit(str(url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


def adresse_pruefen(url, dns: bool = True) -> tuple:
    """-> (url, host) oder BrowserFehler. Ohne Schema gilt https."""
    url = str(url or "").strip()
    if not url:
        raise BrowserFehler("B-ADRESSE", "keine Adresse angegeben")
    if "://" not in url:
        # „javascript:…", „data:…", „mailto:…" sind kein Rechnername ohne
        # Schema; „localhost:5000" (Ziffer nach dem Doppelpunkt) schon.
        if _SCHEMA.match(url):
            raise BrowserFehler("B-ADRESSE", "nur http und https")
        url = "https://" + url
    try:
        teile = urlsplit(url)
    except ValueError:
        raise BrowserFehler("B-ADRESSE", "die Adresse ist kaputt")
    if teile.scheme.lower() not in ("http", "https"):
        raise BrowserFehler("B-ADRESSE", f"nur http und https, nicht {teile.scheme}")
    host = (teile.hostname or "").lower()
    if not host:
        raise BrowserFehler("B-ADRESSE", "in der Adresse fehlt der Rechnername")
    if not lokal_erlaubt() and ist_lokal(host, dns=dns):
        raise BrowserFehler("B-ADRESSE-GESPERRT",
                            f"{host} liegt im eigenen Rechner oder Netz")
    return url, host


# ── Was Sasha in welchem Gespräch erlaubt hat ─────────────────────────
# Nur im Arbeitsspeicher, wie „für dieses Gespräch" im Erlaubnis-Gate: ein
# Neustart fragt wieder. Ohne Gespräch wird nichts gemerkt.

_lock = threading.Lock()
_erlaubt = {}       # gid -> {host}
_staende = {}       # gid -> Seite (dict) — die zuletzt gelesene Seite


def host_erlaubt(gid, host) -> bool:
    if not gid or not host:
        return False
    with _lock:
        return host.lower() in _erlaubt.get(gid, ())


def host_erlauben(gid, host) -> None:
    if not gid or not host:
        return
    with _lock:
        _erlaubt.setdefault(gid, set()).add(host.lower())


def erlaubte_hosts(gid) -> list:
    with _lock:
        return sorted(_erlaubt.get(gid, ()))


def stand(gid):
    """Die zuletzt gelesene Seite dieses Gesprächs (dict) oder None."""
    with _lock:
        s = _staende.get(gid)
        return dict(s) if s else None


def element(gid, nr):
    """Element Nummer `nr` der zuletzt gelesenen Seite, oder None."""
    try:
        nr = int(nr)
    except (TypeError, ValueError):
        return None
    with _lock:
        s = _staende.get(gid)
        if not s:
            return None
        for e in s["elemente"]:
            if e["nr"] == nr:
                return dict(e)
    return None


def _stand_setzen(gid, seite) -> None:
    with _lock:
        if seite is None:
            _staende.pop(gid, None)
        else:
            _staende[gid] = seite


def _vergessen_fuer_tests() -> None:
    with _lock:
        _erlaubt.clear()
        _staende.clear()


# ── Unser festes Skript in der Seite ──────────────────────────────────
# Nummeriert die sichtbaren, bedienbaren Elemente eines Rahmens (ab `start`)
# und merkt die Nummer als Attribut — darüber findet klicken() es wieder.

_ELEMENTE_JS = r"""
(start) => {
  const sel = 'a[href], button, input:not([type=hidden]), select, textarea, ' +
              '[role=button], [role=link], [role=treeitem], [onclick], summary';
  const sauber = s => (s || '').replace(/\s+/g, ' ').trim();
  const raus = [];
  let nr = start;
  document.querySelectorAll('[data-zentrale-nr]').forEach(
    el => el.removeAttribute('data-zentrale-nr'));
  for (const el of document.querySelectorAll(sel)) {
    if (raus.length >= 2000) break;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if ((r.width === 0 && r.height === 0) || st.visibility === 'hidden' ||
        st.display === 'none') continue;
    const tag = el.tagName.toLowerCase();
    const typ = (el.getAttribute('type') || '').toLowerCase();
    let text = '';
    if (tag === 'input' || tag === 'select' || tag === 'textarea') {
      const lab = el.labels && el.labels.length ? el.labels[0].innerText : '';
      text = sauber(lab || el.getAttribute('aria-label') || el.getAttribute('placeholder') ||
                    el.getAttribute('title') || el.name || el.id);
      if (tag === 'input' && ['submit', 'button', 'reset'].includes(typ))
        text = sauber(el.value || text);
    } else {
      text = sauber(el.innerText || el.getAttribute('aria-label') || el.getAttribute('title'));
      if (!text) {
        const img = el.querySelector('img[alt]');
        text = sauber(img ? img.getAttribute('alt') : '');
      }
    }
    let wert = '';
    let optionen = [];
    if (tag === 'select') {
      const o = el.options[el.selectedIndex];
      wert = o ? sauber(o.text) : '';
      optionen = Array.from(el.options).slice(0, 12).map(o => sauber(o.text));
    } else if (tag === 'input' && ['checkbox', 'radio'].includes(typ)) {
      wert = el.checked ? 'an' : 'aus';
    } else if (tag === 'input' || tag === 'textarea') {
      wert = typ === 'password' ? '' : sauber(el.value).slice(0, 80);
    }
    const form = el.form || el.closest('form');
    el.setAttribute('data-zentrale-nr', String(nr));
    raus.push({nr: nr, tag: tag, typ: typ, text: text.slice(0, 140),
               href: tag === 'a' ? el.href : '', wert: wert, optionen: optionen,
               passwort_form: !!(form && form.querySelector('input[type=password]'))});
    nr += 1;
  }
  return raus;
}
"""

_TEXT_JS = "() => document.body ? document.body.innerText : ''"


def _art(e: dict) -> str:
    tag, typ = e["tag"], e["typ"]
    if tag == "a" or (tag not in ("button", "input", "select", "textarea") and not typ):
        return "Link" if tag == "a" else "Knopf"
    if tag == "select":
        return "Auswahl"
    if tag == "textarea":
        return "Textfeld"
    if tag == "button" or typ in ("submit", "button", "reset", "image"):
        return "Knopf"
    if typ in ("checkbox", "radio"):
        return "Häkchen"
    return "Feld"


# ── Der Arbeiter-Thread ───────────────────────────────────────────────

class _Sitzung:
    def __init__(self, gid, kontext, seite):
        self.gid = gid
        self.kontext = kontext
        self.seite = seite
        self.zuletzt = time.monotonic()
        self.blockiert = ""          # Adresse eines Hosts ohne Erlaubnis
        self.umleitung = ""          # erlaubtes Ziel einer Weiterleitung, kommt gleich
        self.download = ""           # Adresse einer Datei statt einer Seite
        self.gesperrt = ""           # Adresse im eigenen Netz
        self.rahmen_fremd = 0        # Rahmen anderer Hosts, nicht geladen
        self.neue_seiten = []


class _Auftrag:
    def __init__(self, fn):
        self.fn = fn
        self.fertig = threading.Event()
        self.ergebnis = None
        self.fehler = None


class _Arbeiter(threading.Thread):
    def __init__(self):
        super().__init__(name="zentrale-browser", daemon=True)
        self.auftraege = queue.Queue()
        self.pw = None
        self.browser = None
        self.sitzungen = {}

    # Läuft im Arbeiter-Thread.
    def run(self):
        while True:
            try:
                a = self.auftraege.get(timeout=PRUEF_S)
            except queue.Empty:
                self._aufraeumen()
                continue
            if a is None:
                self._alles_zu()
                return
            try:
                a.ergebnis = a.fn(self)
            except BaseException as e:      # noqa: BLE001 — geht an den Aufrufer
                a.fehler = e
            a.fertig.set()
            self._aufraeumen()

    # ── Browser und Sitzungen ──
    def _browser(self):
        if self.browser is not None and self.browser.is_connected():
            return self.browser
        ok, grund = verfuegbar()
        if not ok:
            raise BrowserFehler("B-NICHT-EINGERICHTET", grund)
        from playwright.sync_api import sync_playwright
        if self.pw is None:
            self.pw = sync_playwright().start()
        letzter = None
        # Erst mit Chromiums eigener Abschottung; geht das auf diesem System
        # nicht (Ubuntu sperrt sie für fremde Programme oft), ohne — der
        # Browser bleibt ein eigener Prozess ohne Downloads und ohne Zugriff
        # aufs eigene Netz.
        for abgeschottet in (True, False):
            try:
                self.browser = self.pw.chromium.launch(
                    headless=True, chromium_sandbox=abgeschottet,
                    args=["--disable-dev-shm-usage"], timeout=SCHRITT_MS)
                if not abgeschottet:
                    state.push_log("BROWSER: Chromium läuft ohne eigene Abschottung "
                                   "(vom System nicht erlaubt)")
                return self.browser
            except Exception as e:          # noqa: BLE001
                letzter = e
        text = str(letzter or "")
        if "Executable doesn't exist" in text or "playwright install" in text:
            grund = "Chromium für den Browser ist nicht heruntergeladen"
        elif "missing dependencies" in text.lower():
            grund = "dem System fehlen Bibliotheken, die Chromium braucht"
        else:
            grund = "Chromium startet nicht: " + text.strip().splitlines()[0][:200] \
                if text.strip() else "Chromium startet nicht"
        raise BrowserFehler("B-NICHT-EINGERICHTET", grund)

    def sitzung(self, gid, neu: bool):
        s = self.sitzungen.get(gid)
        if s is not None:
            s.zuletzt = time.monotonic()
            return s
        if not neu:
            raise BrowserFehler("B-KEINE-SEITE", "in diesem Gespräch ist kein Browser offen")
        while len(self.sitzungen) >= MAX_SITZUNGEN:
            aelteste = min(self.sitzungen.values(), key=lambda x: x.zuletzt)
            self._zu(aelteste.gid)
        b = self._browser()
        kontext = b.new_context(
            accept_downloads=False, service_workers="block", locale="de-DE",
            java_script_enabled=True,
            user_agent=None)
        kontext.set_default_timeout(SCHRITT_MS)
        kontext.set_default_navigation_timeout(SCHRITT_MS)
        seite = kontext.new_page()
        s = _Sitzung(gid, kontext, seite)
        kontext.route("**/*", lambda route, anfrage: self._abfangen(s, route, anfrage))
        kontext.on("page", lambda p: s.neue_seiten.append(p))
        self.sitzungen[gid] = s
        return s

    def _zu(self, gid) -> bool:
        s = self.sitzungen.pop(gid, None)
        _stand_setzen(gid, None)
        if s is None:
            return False
        try:
            s.kontext.close()
        except Exception:                   # noqa: BLE001
            pass
        return True

    def _alles_zu(self):
        for gid in list(self.sitzungen):
            self._zu(gid)
        try:
            if self.browser is not None:
                self.browser.close()
        except Exception:                   # noqa: BLE001
            pass
        try:
            if self.pw is not None:
                self.pw.stop()
        except Exception:                   # noqa: BLE001
            pass
        self.browser = self.pw = None

    def _aufraeumen(self):
        jetzt = time.monotonic()
        for gid, s in list(self.sitzungen.items()):
            if jetzt - s.zuletzt > LEERLAUF_S:
                self._zu(gid)
        if not self.sitzungen and (self.browser is not None or self.pw is not None):
            self._alles_zu()

    # ── Jede Anfrage der Seite läuft hier durch ──
    def _abfangen(self, s, route, anfrage):
        url = anfrage.url
        teile = urlsplit(url)
        if teile.scheme not in ("http", "https"):
            return route.abort("blockedbyclient")
        host = (teile.hostname or "").lower()
        if not lokal_erlaubt() and ist_lokal(host):
            if anfrage.resource_type == "document":
                s.gesperrt = url
            return route.abort("blockedbyclient")
        if anfrage.resource_type != "document":
            return route.continue_()
        hauptrahmen = anfrage.frame.parent_frame is None
        if not host_erlaubt(s.gid, host):
            if hauptrahmen:
                s.blockiert = url
            else:
                s.rahmen_fremd += 1
            return route.abort("blockedbyclient")
        state.push_internet_log(f"NET →  BROWSER {url[:200]}")
        # Selbst holen, ohne Weiterleitungen zu folgen (Kopf der Datei).
        try:
            antwort = route.fetch(max_redirects=0, timeout=SCHRITT_MS)
        except Exception:                   # noqa: BLE001 — Netzfehler zeigt der Browser
            return route.abort("failed")
        ziel = antwort.headers.get("location")
        if 300 <= antwort.status < 400 and ziel:
            from urllib.parse import urljoin
            ziel_url = urljoin(url, ziel)
            ziel_host = host_von(ziel_url)
            if urlsplit(ziel_url).scheme not in ("http", "https") or \
                    (not lokal_erlaubt() and ist_lokal(ziel_host)):
                if hauptrahmen:
                    s.gesperrt = ziel_url
                return route.abort("blockedbyclient")
            if not host_erlaubt(s.gid, ziel_host):
                if hauptrahmen:
                    s.blockiert = ziel_url
                else:
                    s.rahmen_fremd += 1
                return route.abort("blockedbyclient")
            # Erlaubt: nicht die 3xx-Antwort durchreichen (der Browser folgte
            # ihr, ohne dass das Ziel hier noch einmal vorbeikommt), sondern
            # eine Zwischenseite, die das Ziel neu lädt — das läuft dann
            # wieder hier durch, samt seiner eigenen Weiterleitungen. Cookies
            # aus der Weiterleitung hat route.fetch schon im Kontext abgelegt.
            if hauptrahmen:
                s.umleitung = ziel_url
            return route.fulfill(status=200, content_type="text/html",
                                 body=_ZWISCHENSEITE.format(
                                     html=_html.escape(ziel_url, quote=True),
                                     js=_json.dumps(ziel_url)))
        # Keine Seite, sondern eine Datei (PDF, Zip, „herunterladen"): nicht
        # an den Browser geben — Downloads sind aus, und die KI soll
        # fetch_document nehmen, das legt PDFs lesbar in die Ablage.
        art = (antwort.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
        anhang = "attachment" in (antwort.headers.get("content-disposition") or "").lower()
        if anhang or (art and not art.startswith(_SEITEN_ARTEN)):
            if hauptrahmen:
                s.download = url
            return route.abort("blockedbyclient")
        return route.fulfill(response=antwort)

    # ── Schritte ──
    def _vorher(self, s):
        s.blockiert = s.gesperrt = s.umleitung = s.download = ""
        s.rahmen_fremd = 0
        s.neue_seiten = []

    def _nachher(self, s, fehler=None):
        """Nach einem Schritt: neue Seite (Pop-up) übernehmen, Sperren
        melden, auf nachladende Skripte warten, lesen."""
        if s.neue_seiten:
            neu = s.neue_seiten[-1]
            alt = s.seite
            s.seite = neu
            try:
                alt.close()
            except Exception:               # noqa: BLE001
                pass
        for _ in range(_MAX_UMLEITUNGEN):
            self._sperren_melden(s)
            if not s.umleitung:
                break
            ziel, s.umleitung = s.umleitung, ""
            try:
                s.seite.wait_for_url(lambda u, z=ziel: _gleich(u, z),
                                     wait_until="domcontentloaded", timeout=SCHRITT_MS)
            except Exception:               # noqa: BLE001
                self._sperren_melden(s)
                raise BrowserFehler("B-ZEIT", "die Weiterleitung kam nicht an")
            fehler = None                   # die Zwischenseite war kein Fehler
        else:
            raise BrowserFehler("B-LADEN", "zu viele Weiterleitungen hintereinander")
        if fehler is not None:
            raise fehler
        try:
            s.seite.wait_for_load_state("domcontentloaded", timeout=SCHRITT_MS)
        except Exception:                   # noqa: BLE001
            raise BrowserFehler("B-ZEIT", "die Seite ist nicht fertig geladen")
        try:
            s.seite.wait_for_load_state("networkidle", timeout=_RUHE_MS)
        except Exception:                   # noqa: BLE001 — Seiten mit Dauerverbindung
            pass
        return self.lesen(s)

    def _sperren_melden(self, s):
        if s.download:
            raise BrowserFehler("B-DOWNLOAD", f"{s.download[:200]} ist eine Datei, keine Seite "
                                              f"— Downloads sind aus")
        if s.gesperrt:
            raise BrowserFehler("B-ADRESSE-GESPERRT",
                                f"die Seite wollte {s.gesperrt[:200]} laden — das liegt im "
                                f"eigenen Rechner oder Netz; nicht geladen")
        if s.blockiert:
            raise BrowserFehler("B-ANDERE-SEITE", s.blockiert[:300])

    def lesen(self, s) -> dict:
        p = s.seite
        elemente, texte, nr = [], [], 1
        for i, rahmen in enumerate(p.frames):
            try:
                if rahmen.url in ("", "about:blank") and rahmen is not p.main_frame:
                    continue
                stueck = rahmen.evaluate(_TEXT_JS) or ""
                liste = rahmen.evaluate(_ELEMENTE_JS, nr) or []
            except Exception:               # noqa: BLE001 — Rahmen mitten im Wechsel
                continue
            if stueck.strip():
                kopf = "" if rahmen is p.main_frame else f"\n── Rahmen: {rahmen.name or rahmen.url[:80]} ──\n"
                texte.append(kopf + stueck.strip())
            for e in liste:
                e["rahmen"] = i
                e["art"] = _art(e)
                e["host"] = host_von(e.get("href"))
                elemente.append(e)
            nr += len(liste)
            if len(elemente) >= MAX_ELEMENTE:
                break
        try:
            titel = p.title()
        except Exception:                   # noqa: BLE001
            titel = ""
        seite = {"url": p.url, "host": host_von(p.url), "titel": titel,
                 "text": "\n".join(texte)[:MAX_TEXT], "elemente": elemente[:MAX_ELEMENTE],
                 "rahmen_fremd": s.rahmen_fremd}
        _stand_setzen(s.gid, seite)
        return seite

    def _locator(self, s, nr):
        e = element(s.gid, nr)
        if e is None:
            raise BrowserFehler("B-NR-UNBEKANNT", f"keine Nummer {nr} auf der zuletzt gelesenen Seite")
        rahmen = s.seite.frames
        if e["rahmen"] >= len(rahmen):
            raise BrowserFehler("B-NR-UNBEKANNT", "die Seite hat sich inzwischen verändert")
        loc = rahmen[e["rahmen"]].locator(f'[data-zentrale-nr="{int(nr)}"]')
        if loc.count() != 1:
            raise BrowserFehler("B-NR-UNBEKANNT", "die Seite hat sich inzwischen verändert")
        return e, loc

    def oeffnen(self, gid, url):
        s = self.sitzung(gid, neu=True)
        self._vorher(s)
        fehler = None
        try:
            s.seite.goto(url, wait_until="domcontentloaded", timeout=SCHRITT_MS)
        except Exception as e:              # noqa: BLE001
            fehler = _uebersetzen(e)
        return self._nachher(s, fehler)

    def klicken(self, gid, nr):
        s = self.sitzung(gid, neu=False)
        e, loc = self._locator(s, nr)
        self._vorher(s)
        fehler = None
        try:
            loc.click(timeout=SCHRITT_MS)
        except Exception as ex:             # noqa: BLE001
            fehler = _uebersetzen(ex)
        return self._nachher(s, fehler)

    def tippen(self, gid, nr, text, enter):
        s = self.sitzung(gid, neu=False)
        e, loc = self._locator(s, nr)
        if e["typ"] == "password":
            raise BrowserFehler("B-PASSWORT", "in Passwortfelder tippt die KI nicht")
        if e["art"] not in ("Feld", "Textfeld", "Auswahl"):
            raise BrowserFehler("B-KEIN-FELD", f"Nummer {nr} ist ein {e['art']}, kein Eingabefeld")
        self._vorher(s)
        try:
            if e["art"] == "Auswahl":
                try:
                    loc.select_option(label=text, timeout=SCHRITT_MS)
                except Exception:           # noqa: BLE001
                    loc.select_option(value=text, timeout=SCHRITT_MS)
                wert = loc.evaluate("el => el.options[el.selectedIndex] ? "
                                    "el.options[el.selectedIndex].text : ''")
            else:
                loc.fill(text, timeout=SCHRITT_MS)
                wert = loc.input_value(timeout=SCHRITT_MS)
        except BrowserFehler:
            raise
        except Exception as ex:             # noqa: BLE001
            raise _uebersetzen(ex, "B-KEIN-FELD")
        if not enter:
            return {"wert": wert, "seite": None}
        fehler = None
        try:
            loc.press("Enter", timeout=SCHRITT_MS)
        except Exception as ex:             # noqa: BLE001
            fehler = _uebersetzen(ex)
        return {"wert": wert, "seite": self._nachher(s, fehler)}

    def zurueck(self, gid):
        s = self.sitzung(gid, neu=False)
        self._vorher(s)
        try:
            antwort = s.seite.go_back(wait_until="domcontentloaded", timeout=SCHRITT_MS)
        except Exception as e:              # noqa: BLE001
            return self._nachher(s, _uebersetzen(e))
        if antwort is None and s.seite.url in ("", "about:blank"):
            raise BrowserFehler("B-KEIN-ZURUECK", "es gibt keine vorige Seite")
        return self._nachher(s)

    def bildschirmfoto(self, gid, max_bytes):
        s = self.sitzung(gid, neu=False)
        png = s.seite.screenshot(full_page=True, type="png", timeout=SCHRITT_MS)
        if len(png) > max_bytes:
            png = s.seite.screenshot(full_page=False, type="png", timeout=SCHRITT_MS)
        return png, s.seite.url


def _gleich(a: str, b: str) -> bool:
    """Dieselbe Adresse, bis auf #Sprungmarke und Schrägstrich am Ende."""
    def norm(u):
        return str(u or "").split("#", 1)[0].rstrip("/")
    return norm(a) == norm(b)


def _uebersetzen(e, code_sonst: str = "B-LADEN") -> BrowserFehler:
    """Eine Playwright-Ausnahme in einen Fehler mit Code."""
    if isinstance(e, BrowserFehler):
        return e
    text = str(e or "")
    erste = text.strip().splitlines()[0][:200] if text.strip() else type(e).__name__
    if "Download is starting" in text:
        return BrowserFehler("B-DOWNLOAD", "der Link lädt eine Datei herunter — Downloads sind aus")
    if type(e).__name__ == "TimeoutError" or "Timeout" in erste:
        return BrowserFehler("B-ZEIT", f"nach {SCHRITT_MS // 1000} s nicht fertig")
    return BrowserFehler(code_sonst, erste)


# ── Die Tür nach außen ────────────────────────────────────────────────

_arbeiter = None
_arbeiter_lock = threading.Lock()


def _auftrag(fn, warten_s: float = SCHRITT_MS / 1000 * 3):
    global _arbeiter
    with _arbeiter_lock:
        if _arbeiter is None or not _arbeiter.is_alive():
            _arbeiter = _Arbeiter()
            _arbeiter.start()
        a = _Auftrag(fn)
        _arbeiter.auftraege.put(a)
    if not a.fertig.wait(warten_s):
        raise BrowserFehler("B-ZEIT", "der Browser antwortet nicht")
    if a.fehler is not None:
        raise a.fehler
    return a.ergebnis


def oeffnen(gid, url) -> dict:
    """Seite laden. url muss vorher durch adresse_pruefen gegangen und der
    Host erlaubt sein. -> Seite {url, host, titel, text, elemente, rahmen_fremd}."""
    ok, grund = verfuegbar()
    if not ok:
        raise BrowserFehler("B-NICHT-EINGERICHTET", grund)
    return _auftrag(lambda w: w.oeffnen(gid, url))


def klicken(gid, nr) -> dict:
    return _auftrag(lambda w: w.klicken(gid, nr))


def tippen(gid, nr, text, enter=False) -> dict:
    """-> {wert: was jetzt im Feld steht, seite: Seite oder None (ohne Enter)}."""
    return _auftrag(lambda w: w.tippen(gid, nr, str(text), bool(enter)))


def zurueck(gid) -> dict:
    return _auftrag(lambda w: w.zurueck(gid))


def bildschirmfoto(gid, max_bytes: int) -> tuple:
    """-> (png-Bytes, url)."""
    return _auftrag(lambda w: w.bildschirmfoto(gid, max_bytes))


def schliessen(gid) -> bool:
    """Sitzung des Gesprächs schließen. -> war eine offen? Die erlaubten
    Hosts bleiben (Sasha hat für das Gespräch Ja gesagt)."""
    if _arbeiter is None or not _arbeiter.is_alive():
        _stand_setzen(gid, None)
        return False
    return _auftrag(lambda w: w._zu(gid))


def offen(gid) -> bool:
    return stand(gid) is not None


def beenden() -> None:
    """Alles zu und den Arbeiter stoppen (Tests, Herunterfahren)."""
    global _arbeiter
    with _arbeiter_lock:
        w, _arbeiter = _arbeiter, None
    if w is not None and w.is_alive():
        w.auftraege.put(None)
        w.join(timeout=30)
    with _lock:
        _staende.clear()
