# tui/ansichten/post.py
#
# Post/Mail in der TUI: ein reiner Zeichner gegen /api/mail. Kategorien →
# Mails → Lesen, Einsortieren, Löschen, Antworten. Bis 06.10.2026 Closures in
# run_ui (tui/zentrale_tui.py), siehe memory/system/tui_bauplan.md.

import curses
import json
import queue
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .basis import BEENDEN, api_call
from .tasten import Tasten
from .text import _wrap


# Sentinel für MAIL["cat"]: der Eingang-Tray (INBOX + \Seen) statt einer Kategorie.
MAIL_EINGANG = "__eingang__"


def _do_refresh_counts(force=False):
    """Live-Ordnerzählung im Backend anstoßen (Backend zählt im eigenen
    Thread, der POST kehrt schnell zurück). `force` umgeht die Backend-TTL —
    nötig, wenn sich die Zahlen gerade geändert haben (nach Umsortieren)."""
    try:
        q = "/api/mail/refresh-counts" + ("?force=1" if force else "")
        api_call(q, method="POST", timeout=8.0)
    except Exception:
        pass


def _reply_filed_msg(r, verb):
    """Rückmeldung nach Antwort/Entwurf aus dem Eingang: wurde die Mail
    auto-einsortiert oder blieb sie (unbekannter Absender) liegen?"""
    filed = (r or {}).get("filed") or {}
    if filed.get("filed"):
        return "✓ %s + einsortiert → %s" % (verb, filed.get("category") or "?")
    return "✓ %s — Absender unbekannt, bleibt im Eingang (s = einsortieren)" % verb


class Post:
    """Das Post-Panel (Mitte, Taste 'p'): Kategorien, Mails, Lesen,
    Einsortieren, Löschen, Antworten im Split-Editor. Jede IMAP-Op läuft über
    EINEN Worker-Thread (_mail_submit/_mail_worker), nie im Zeichnen oder in
    der Tastatur — das Panel liest nur self.MAIL (auch z.MAIL)."""

    def __init__(self, z):
        self.z = z
        # ── Post/Mail (füllt die MITTE-Box, Taste 'p') ─────────────────────
        # Wie Karte/Kalender ein reiner Zeichner. Rein LESEND über /api/mail
        # (Kategorien + Mails aus data/mail_state.json — KEIN Key nötig). Nur der
        # Live-Poll ('r' → POST /api/mail/poll) braucht die Passphrase (Env oder
        # OS-Keyring) und läuft im Backend-Thread; der Fortschritt erscheint links
        # im Log. Aktualisiert sich alle paar Sekunden selbst.
        #
        # ZWEI EBENEN (Drill-down): Beim Öffnen sieht man NUR die Kategorien (Ebene
        # "cats") — der Review-Stapel ist einfach die Kategorie 'sasha muss gucken'
        # wie jede andere, nichts wird einem ins Gesicht geklatscht. Enter öffnet
        # eine Kategorie (Ebene "mails") und zeigt die Mails darin; esc führt zurück.
        #   active : Panel hat den Fokus
        #   level  : "cats" (Kategorien wählen) | "mails" (Mails der gewählten Kat.)
        #   sel    : Auswahl-Index in der Kategorie-Liste
        #   cat    : Name der geöffneten Kategorie (in "mails"); Sentinel MAIL_EINGANG
        #            = der Eingang-Tray (INBOX + \Seen) statt einer Kategorie
        #   off    : Scroll-Offset in der Mail-Liste; _ts: letzter Abruf (Auto-Refresh)
        self.MAIL = z.MAIL = {"active": False, "level": "cats", "sel": 0, "cat": None,
                              "off": 0, "data": None, "msg": "", "_ts": 0.0, "busy": "",
                              "mails": None, "mails_live": False,   # mails: None=lädt, []=leer
                              "fcache": {},         # Kategorie → zuletzt geholte Mail-Liste (Reopen instant)
                              # Ebene 2: zwei Anzeige-Modi + Aktions-Submodi.
                              "mode2": "read",      # "read" (eine Mail, Vorschau+ausklappen) | "list" (Blöcke)
                              "msel": 0,            # ausgewählte Mail (in beiden Modi)
                              "expanded": False,    # im read-Modus: voller Text statt Vorschau
                              "bodyoff": 0,         # Scroll im Body (read, ausgeklappt)
                              "body": None,         # gecachter Body der aktuellen Mail (None=lädt)
                              "bodyfor": None,      # uid, zu der der Body gehört
                              "picking": False,     # Einsortier-Picker offen (Kategorie wählen)
                              "picksel": 0,         # Auswahl im Picker
                              "confirmdel": False,  # Lösch-Nachfrage offen
                              # Antwort-Editor (Split-Pane: links Original, rechts dein Text).
                              "replying": False,    # Editor offen → Mitte wird breit
                              "reply_text": "",     # dein getippter Antworttext
                              "reply_origoff": 0,   # Scroll im Original (links)
                              "reply_confirm": False}  # Verlassen-Leiste (senden/verwerfen/weiter)
        # ── Mail-I/O läuft im Hintergrund, NIE im Render/Input-Thread ─────────
        # Jede IMAP-Op (zählen, Ordner holen, Body, einsortieren, löschen) kann bei
        # Outlook Sekunden dauern. Früher lief das synchron im Zeichnen/Tasten-Loop
        # → die ganze TUI fror ein, esc klemmte, und man sah nicht, WAS gerade lud.
        # Jetzt arbeitet EIN Worker-Thread die Jobs ab; das Panel liest nur den
        # Zustand und zeigt `busy` an. `key` dedupt (kein Job-Stau beim schnellen
        # Blättern), `busy` verschwindet erst, wenn nichts mehr wartet.
        self.MAIL_Q = queue.Queue()
        self.MAIL_PENDING = set()
        self.MAIL_PLOCK = threading.Lock()

    def start(self):
        """Hintergrund-Threads anwerfen (run_ui ruft das nach dem Aufbau)."""
        _mail_worker = self._mail_worker
        threading.Thread(target=_mail_worker, daemon=True, name="mail-io").start()

    def _mail_submit(self, key, label, fn):
        """Einen Mail-Job in den Hintergrund geben. Läuft/wartet schon einer mit
        gleichem `key`, wird NICHT doppelt eingereiht (Dedup). Leeres `label` =
        stiller Job (z.B. der billige 3s-Auto-Refresh, kein IMAP → kein Flackern)."""
        MAIL, MAIL_PENDING, MAIL_PLOCK = self.MAIL, self.MAIL_PENDING, self.MAIL_PLOCK
        MAIL_Q = self.MAIL_Q
        with MAIL_PLOCK:
            if key in MAIL_PENDING:
                return
            MAIL_PENDING.add(key)
        if label:
            MAIL["busy"] = label
        MAIL_Q.put((key, label, fn))

    def _mail_worker(self):
        MAIL, MAIL_PENDING, MAIL_PLOCK = self.MAIL, self.MAIL_PENDING, self.MAIL_PLOCK
        MAIL_Q = self.MAIL_Q
        while True:
            key, label, fn = MAIL_Q.get()
            if label:
                MAIL["busy"] = label
            try:
                fn()
            except Exception:
                pass
            finally:
                with MAIL_PLOCK:
                    MAIL_PENDING.discard(key)
                if MAIL_Q.empty():
                    MAIL["busy"] = ""

    # ── Post/Mail-Panel: laden / pollen / zeichnen ─────────────────────
    def mail_load(self):
        """Kategorie-Übersicht read-only holen (inkl. Live-Zähl-Cache)."""
        MAIL = self.MAIL
        try:
            MAIL["data"] = api_call("/api/mail", timeout=8.0)
            MAIL["msg"] = ""
        except Exception:
            MAIL["data"] = {"failed": True}
            MAIL["msg"] = "mail: backend?"
        MAIL["_ts"] = time.time()

    def mail_refresh_counts(self):
        """Zählung im Hintergrund anstoßen — friert die TUI nicht ein."""
        _mail_submit = self._mail_submit
        _mail_submit(("counts",), "zähle ordner…", _do_refresh_counts)

    def _mail_fetch_folder(self, name, force=False):
        """Die Mails einer Kategorie holen (läuft im Worker). Schreibt das
        Ergebnis nur, wenn der Nutzer nicht inzwischen weitergeschaltet hat, und
        zeigt einen ECHTEN Fehler statt ihn als „(Ordner leer)" zu verschleiern.
        `force=1` umgeht den Backend-Cache (nach Umsortieren/Löschen). Meldet das
        Backend, dass es im Hintergrund frisch nachzieht (`refreshing`), holen wir
        das Ergebnis nach kurzer Wartezeit noch einmal, damit die frische Liste
        einschwenkt."""
        MAIL, _mail_fetch_folder = self.MAIL, self._mail_fetch_folder
        _mail_submit = self._mail_submit
        mails, live, err, refreshing = None, False, None, False
        try:
            if name == MAIL_EINGANG:            # Eingang-Tray = INBOX + \Seen
                q = "/api/mail/inbox"
            else:
                q = "/api/mail/folder?cat=" + urllib.parse.quote(name or "")
                if force:
                    q += "&force=1"
            r = api_call(q, timeout=30.0)
            if isinstance(r, dict) and r.get("error"):
                mails, err = [], str(r.get("error"))
            elif isinstance(r, dict):
                mails = r.get("mails") if isinstance(r.get("mails"), list) else []
                live = bool(r.get("live"))
                refreshing = bool(r.get("refreshing"))
            else:
                mails = []
        except urllib.error.HTTPError as e:
            mails = []
            try:
                j = json.loads(e.read().decode("utf-8"))
                err = str(j.get("error", "HTTP %d" % e.code))
            except Exception:
                err = "HTTP %d" % e.code
        except Exception as ex:
            mails, err = [], "%s (backend?)" % type(ex).__name__
        if MAIL["cat"] != name:            # Nutzer ist weiter → Ergebnis verwerfen
            return
        MAIL["mails"] = mails
        MAIL["mails_live"] = live
        MAIL["msg"] = ("ordner: " + err) if err else ""
        if not err and isinstance(mails, list):
            MAIL["fcache"][name] = mails   # Reopen zeigt das sofort
        if refreshing and not err:
            # Backend zieht gerade frisch nach → gleich nochmal (still) abholen.
            t = threading.Timer(2.0, lambda n=name: _mail_submit(
                ("folder-refresh", n), "", lambda: _mail_fetch_folder(n)))
            t.daemon = True
            t.start()

    def mail_open_category(self, name):
        """Eine Kategorie öffnen: Ansicht sofort umschalten. Liegt der Ordner noch
        im TUI-Cache, zeigen wir ihn SOFORT und frischen still im Hintergrund auf
        (kein „lädt ordner…"-Warten mehr beim Wieder-Aufmachen); sonst holt der
        Worker ihn (Backend serviert i.d.R. instant aus SEINEM Cache)."""
        MAIL, _mail_fetch_folder = self.MAIL, self._mail_fetch_folder
        _mail_submit = self._mail_submit
        MAIL["cat"] = name
        MAIL["level"] = "mails"
        MAIL["off"] = 0
        MAIL["mode2"] = "read"; MAIL["msel"] = 0
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0
        MAIL["body"] = None; MAIL["bodyfor"] = None
        MAIL["picking"] = False; MAIL["confirmdel"] = False
        cached = MAIL["fcache"].get(name)
        MAIL["mails"] = cached                 # sofort zeigen (None ⇒ „lädt…")
        MAIL["mails_live"] = cached is not None
        MAIL["msg"] = ""
        _mail_submit(("folder", name),
                     "" if cached is not None else "lädt ordner…",
                     lambda n=name: _mail_fetch_folder(n))

    def mail_cur(self):
        """Die aktuell ausgewählte Mail (oder None)."""
        MAIL = self.MAIL
        ms = MAIL["mails"] or []
        return ms[MAIL["msel"]] if 0 <= MAIL["msel"] < len(ms) else None

    def _do_body(self, uid, it):
        """Body EINER Mail holen (läuft im Worker). Nachbarn zum Vorwärmen
        mitschicken; ECHTEN Fehlergrund zeigen statt „backend?"."""
        MAIL = self.MAIL
        ms = MAIL["mails"] or []
        acct = it.get("account") or ""
        try:
            sel = ms.index(it)
        except ValueError:
            sel = MAIL["msel"]
        neigh = []
        for j in (sel + 1, sel - 1):
            if 0 <= j < len(ms):
                nb = ms[j]
                nu = nb.get("uid")
                # Cache ist konto-skaliert → nur gleichkontige Nachbarn vorwärmen.
                if nu is not None and (nb.get("account") or "") == acct:
                    neigh.append(str(nu))
        try:
            if MAIL["cat"] == MAIL_EINGANG:     # Eingang-Mail liegt in der INBOX
                q = ("/api/mail/inbox-body?uid=" + str(uid)
                     + "&account=" + urllib.parse.quote(it.get("account") or ""))
            else:
                q = ("/api/mail/body?cat=" + urllib.parse.quote(MAIL["cat"] or "")
                     + "&uid=" + str(uid)
                     + "&account=" + urllib.parse.quote(it.get("account") or ""))
                if neigh:
                    q += "&prefetch=" + urllib.parse.quote(",".join(neigh))
            r = api_call(q, timeout=30.0)
            body = r if isinstance(r, dict) else {"error": "?"}
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read().decode("utf-8"))
                body = {"error": j.get("error", "HTTP %d" % e.code)}
            except Exception:
                body = {"error": "HTTP %d" % e.code}
        except Exception as ex:
            body = {"error": "%s (Backend erreichbar?)" % type(ex).__name__}
        MAIL["body"] = body
        MAIL["bodyfor"] = uid

    def mail_request_body(self):
        """Body der aktuellen Mail im Hintergrund anfordern (dedupt je uid).
        Blockiert NICHT — der Worker füllt MAIL['body'], das Panel zeigt solange
        „lädt Text…". Schon geladen/gecacht → sofort da."""
        MAIL, _do_body, _mail_submit = self.MAIL, self._do_body, self._mail_submit
        mail_cur = self.mail_cur
        it = mail_cur()
        if not it:
            MAIL["body"] = None; MAIL["bodyfor"] = None
            return
        uid = it.get("uid")
        if MAIL["bodyfor"] == uid and isinstance(MAIL["body"], dict):
            return
        _mail_submit(("body", it.get("account"), uid), "lädt text…",
                     lambda u=uid, item=it: _do_body(u, item))

    def _do_assign(self, sender, category):
        MAIL, _mail_fetch_folder = self.MAIL, self._mail_fetch_folder
        try:
            r = api_call("/api/mail/assign", method="POST",
                         body={"sender": sender, "category": category},
                         timeout=60.0)
            moved = (r or {}).get("moved", 0) if isinstance(r, dict) else 0
            MAIL["msg"] = "absender → %s (%d verschoben)" % (category, moved)
        except Exception:
            MAIL["msg"] = "einsortieren: backend?"
        # force=1: Backend-Cache umgehen, damit die umsortierten Mails hier
        # wirklich rausfallen (sonst zeigte der Cache sie noch).
        _mail_fetch_folder(MAIL["cat"], force=True)
        MAIL["body"] = None; MAIL["bodyfor"] = None
        _do_refresh_counts(force=True)    # Zahlen haben sich geändert

    def mail_assign(self, category):
        """Den ABSENDER der aktuellen Mail einer Kategorie zuordnen UND alle
        seine vorhandenen Mails dorthin verschieben (im Hintergrund — das kann
        bei Outlook lange dauern, die TUI bleibt derweil bedienbar)."""
        MAIL, _do_assign, _mail_submit = self.MAIL, self._do_assign, self._mail_submit
        mail_cur = self.mail_cur
        it = mail_cur()
        MAIL["picking"] = False
        if not it:
            return
        sender = it.get("from") or ""
        MAIL["msg"] = "sortiere absender ein…"
        _mail_submit(("assign", sender, category), "sortiere absender ein…",
                     lambda s=sender, c=category: _do_assign(s, c))

    def _do_delete(self, cat, uid, acct):
        MAIL = self.MAIL
        try:
            r = api_call("/api/mail/delete", method="POST",
                         body={"cat": cat, "uid": uid, "account": acct},
                         timeout=30.0)
            if isinstance(r, dict) and r.get("ok"):
                MAIL["mails"] = [m for m in (MAIL["mails"] or [])
                                 if not (m.get("uid") == uid
                                         and m.get("account") == acct)]
                MAIL["fcache"][cat] = MAIL["mails"]   # Cache mitziehen (Reopen)
                MAIL["body"] = None; MAIL["bodyfor"] = None
                MAIL["msg"] = "gelöscht (Papierkorb)"
            else:
                MAIL["msg"] = "löschen abgelehnt"
        except Exception:
            MAIL["msg"] = "löschen: backend?"
        _do_refresh_counts(force=True)

    def mail_delete(self):
        """Die aktuelle Mail in den Papierkorb (umkehrbar) — im Hintergrund."""
        MAIL, _do_delete, _mail_submit = self.MAIL, self._do_delete, self._mail_submit
        mail_cur = self.mail_cur
        it = mail_cur()
        MAIL["confirmdel"] = False
        if not it:
            return
        MAIL["msg"] = "löscht…"
        _mail_submit(("delete", it.get("account"), it.get("uid")), "löscht…",
                     lambda c=MAIL["cat"], u=it.get("uid"),
                            a=it.get("account"): _do_delete(c, u, a))

    def _do_poll(self):
        MAIL = self.MAIL
        try:
            r = api_call("/api/mail/poll", method="POST", timeout=8.0)
            if isinstance(r, dict) and r.get("error"):
                MAIL["msg"] = "kein key — keyring-set nötig"
            elif isinstance(r, dict) and r.get("already"):
                MAIL["msg"] = "poll läuft schon…"
            else:
                MAIL["msg"] = "poll gestartet — siehe log links"
        except Exception:
            MAIL["msg"] = "poll: backend?"

    def mail_poll(self):
        """Live-Poll im Backend anstoßen (im Hintergrund). Der Fortschritt läuft
        über das Log links. Braucht Passphrase (Env/Keyring)."""
        _do_poll, _mail_submit = self._do_poll, self._mail_submit
        _mail_submit(("poll",), "poll…", _do_poll)

    def _do_reconcile(self):
        MAIL = self.MAIL
        try:
            r = api_call("/api/mail/reconcile", method="POST", timeout=8.0)
            if isinstance(r, dict) and r.get("error"):
                MAIL["msg"] = "kein key — keyring-set nötig"
            elif isinstance(r, dict) and r.get("already"):
                MAIL["msg"] = "abgleich läuft schon…"
            else:
                MAIL["msg"] = "abgleich gestartet — siehe log links"
        except Exception:
            MAIL["msg"] = "abgleich: backend?"
        MAIL["data"] = None       # Zähler nach dem Umräumen frisch ziehen

    def mail_reconcile(self):
        """Ordner an die Keymap angleichen (bereits einsortierte Mail nachziehen)
        — läuft im Backend-Hintergrund, blockiert die TUI nie. Braucht Key."""
        MAIL, _do_reconcile, _mail_submit = self.MAIL, self._do_reconcile, self._mail_submit
        _mail_submit(("reconcile",), "gleiche ab…", _do_reconcile)
        MAIL["msg"] = "starte abgleich…"

    def mail_open_eingang(self):
        """Den Eingang-Tray öffnen (INBOX + \\Seen). Neue/ungelesene Mail liegt
        hier, bis sie gelesen ist; `f` hakt sie ab (gelesen + einsortieren)."""
        mail_open_category = self.mail_open_category
        mail_open_category(MAIL_EINGANG)

    def _do_mark_read(self):
        MAIL, _eingang_drop, mail_cur = self.MAIL, self._eingang_drop, self.mail_cur
        it = mail_cur()
        if not it:
            return
        uid = it.get("uid")
        try:
            r = api_call("/api/mail/read", method="POST",
                         body={"uid": uid, "account": it.get("account")}, timeout=30.0)
            if isinstance(r, dict) and r.get("filed"):
                MAIL["msg"] = "abgehakt → %s" % (r.get("category") or "?")
            elif isinstance(r, dict) and r.get("seen"):
                MAIL["msg"] = "gelesen — Absender noch unbekannt (s = einsortieren)"
            else:
                MAIL["msg"] = "abhaken: backend?"
        except Exception:
            MAIL["msg"] = "abhaken: backend?"
        # Die Mail hat den Eingang verlassen (oder ist zumindest jetzt gelesen) →
        # Liste ohne sie neu aufbauen, damit sie sofort verschwindet.
        _eingang_drop(uid)

    def _eingang_drop(self, uid):
        """Eine abgehakte/beantwortete Mail sofort aus der Eingang-Ansicht nehmen
        (Liste + Cache + Body), Zahlen frisch ziehen. Beim nächsten Öffnen kommt
        der echte Serverstand (eine nur gelesene, unbekannte Mail taucht als ○
        wieder auf — wie beim Abhaken)."""
        MAIL = self.MAIL
        MAIL["mails"] = [m for m in (MAIL["mails"] or [])
                         if m.get("uid") != uid]
        MAIL["fcache"].pop(MAIL_EINGANG, None)
        MAIL["body"] = None; MAIL["bodyfor"] = None
        _do_refresh_counts(force=True)

    def mail_mark_read(self):
        """Aktuelle Eingang-Mail abhaken: als gelesen markieren + (bekannter
        Absender) einsortieren. Läuft im Worker → TUI blockiert nicht."""
        MAIL, _do_mark_read, _mail_submit = self.MAIL, self._do_mark_read, self._mail_submit
        mail_cur = self.mail_cur
        it = mail_cur()
        if not it:
            return
        MAIL["msg"] = "hake ab…"
        _mail_submit(("read", it.get("account"), it.get("uid")), "hake ab…",
                     _do_mark_read)

    def oeffnen(self):
        """Startseite → Post (Ebene Kategorien); die echten Ordnergrößen holt
        der Worker im Hintergrund."""
        MAIL, mail_refresh_counts = self.MAIL, self.mail_refresh_counts
        MAIL["active"] = True; MAIL["level"] = "cats"
        MAIL["sel"] = 0; MAIL["cat"] = None; MAIL["off"] = 0
        MAIL["mails"] = None; MAIL["data"] = None; MAIL["msg"] = ""
        mail_refresh_counts()          # echte Ordnergrößen im Hintergrund holen

    # ── Tasten: EINE Tabelle, aus der Verteilung und Leiste lesen ──────
    # (tui/ansichten/tasten.py, 2026-10-11). Ohne Text = verarbeitet, aber
    # nicht gezeigt (vim-Tasten, Großbuchstaben, q, t Thema, p Panel zu …).
    # Der Antwort-Editor ist eine Ansicht wie jede andere; im Eingang hakt f
    # ab und d löscht nicht — darum eigene Ansichten „…:eingang".
    _NEBEN = [                         # überall in Ebene 2, ungezeigt
        ("p/P", "schliessen"), ("q/Q", "beenden"), ("e/E", "eingang"),
        ("r/R", "poll"), ("t/T", "thema"), ("X", "abgleich"), ("Z", "zaehlen"),
    ]
    _ENDE = [("x", "abgleich", "reconcile"), ("z", "zaehlen", "recount"),
             ("esc", "zurueck", "back")]
    _LISTE = [
        ("↑↓", "m_waehlen", "select"), ("k/j", "m_waehlen"), ("n/N", "m_waehlen"),
        ("space", "m_waehlen"), ("enter", "m_lesen", "read"), ("→/l", "m_lesen"),
        ("←/h", "zurueck"), ("v/V/tab", "modus"),
    ]
    _LESEN = [("←→", "blaettern", "prev/next")]
    _ZU = [("v", "modus", "list"), ("V/tab", "modus")]
    _VORSCHAU = [("↓", "aufklappen", "expand"), ("j/space", "aufklappen")]
    _OFFEN = [("↑↓", "scrollen", "scroll / fold"), ("k/j/space", "scrollen"),
              ("pgup pgdn", "seite")]
    _MIT_D = [("a", "antworten", "reply"), ("A", "antworten"),
              ("s", "einsortieren", "sort in"), ("S", "einsortieren"),
              ("d", "loeschen", "delete"), ("D", "loeschen")]
    # Eingang: f hakt ab (gelesen + einsortieren); d sagt nur, dass es hier
    # nicht löscht.
    _MIT_F = [("f", "abhaken", "done"), ("F", "abhaken"),
              ("a", "antworten", "reply"), ("A", "antworten"),
              ("s", "einsortieren", "sort in"), ("S", "einsortieren"),
              ("d/D", "loeschen")]
    TASTEN = Tasten({
        "kategorien": [
            ("↑↓", "k_waehlen", "select"), ("k/j", "k_waehlen"),
            ("enter", "k_oeffnen", "open"), ("→/l", "k_oeffnen"),
            ("e", "eingang", "inbox"), ("E", "eingang"),
            ("r", "poll", "poll"), ("R", "poll"),
            ("x", "abgleich", "reconcile"), ("X", "abgleich"),
            ("z", "zaehlen", "recount"), ("Z", "zaehlen"),
            ("esc", "schliessen", "close"), ("p/P", "schliessen"),
            ("q/Q", "beenden"), ("t/T", "thema"),
        ],
        # noch keine Kategorien (lädt, Backend weg, leer)
        "kategorien:leer": [
            ("e", "eingang", "inbox"), ("E", "eingang"),
            ("r", "poll", "poll"), ("R", "poll"),
            ("x", "abgleich", "reconcile"), ("X", "abgleich"),
            ("z", "zaehlen", "recount"), ("Z", "zaehlen"),
            ("esc", "schliessen", "close"), ("p/P", "schliessen"),
            ("q/Q", "beenden"), ("t/T", "thema"),
        ],
        # Ordner lädt noch oder ist leer
        "ordner:leer": _ENDE + _NEBEN,
        "liste": _LISTE + _MIT_D + _ENDE + _NEBEN,
        "liste:eingang": _LISTE[:6] + _MIT_F + _LISTE[6:] + _ENDE + _NEBEN,
        # Lesen: eine Mail, Vorschau …
        "lesen": _LESEN + _VORSCHAU + _MIT_D + _ZU + _ENDE + _NEBEN,
        "lesen:eingang": _LESEN + _VORSCHAU + _MIT_F + _ZU + _ENDE + _NEBEN,
        # … oder ausgeklappt (↑ ganz oben klappt wieder ein)
        "lesen:offen": _LESEN + _OFFEN + _MIT_D + _ZU + _ENDE + _NEBEN,
        "lesen:offen:eingang": _LESEN + _OFFEN + _MIT_F + _ZU + _ENDE + _NEBEN,
        # Absender einsortieren: Zielkategorie wählen
        "einsortieren": [
            ("↑↓", "ziel_waehlen", "select"), ("k/j", "ziel_waehlen"),
            ("enter", "ziel_nehmen", "sort in"), ("esc", "ziel_abbrechen", "cancel"),
        ],
        "loeschen:frage": [
            ("j/y/enter", "loeschen_ja", "delete"), ("J/Y", "loeschen_ja"),
            ("any key", "loeschen_nein", "cancel"),
        ],
        # Antwort-Editor (links das Original, rechts der eigene Text)
        "antwort": [
            ("type", "a_tippen", "type"), ("enter", "a_zeile", "new line"),
            ("⌫", "a_weg", "delete"), ("↑↓", "a_original", "scroll original"),
            ("esc", "a_fertig", "done"),
        ],
        "antwort:frage": [
            ("j/y", "a_senden", "send"), ("J/Y", "a_senden"),
            ("e", "a_entwurf", "draft"), ("E", "a_entwurf"),
            ("n", "a_verwerfen", "discard"), ("N", "a_verwerfen"),
            ("w/esc", "a_weiter", "keep writing"), ("W", "a_weiter"),
        ],
    })

    def ansicht(self):
        """Welche Ansicht der Tabelle gerade offen ist."""
        MAIL = self.MAIL
        if MAIL["replying"]:
            return "antwort:frage" if MAIL["reply_confirm"] else "antwort"
        if MAIL["level"] != "mails":
            return "kategorien" if self._kategorien() else "kategorien:leer"
        if MAIL["picking"]:
            return "einsortieren"
        if MAIL["confirmdel"]:
            return "loeschen:frage"
        if not MAIL["mails"]:
            return "ordner:leer"
        ein = ":eingang" if MAIL["cat"] == MAIL_EINGANG else ""
        if MAIL["mode2"] == "list":
            return "liste" + ein
        return ("lesen:offen" if MAIL["expanded"] else "lesen") + ein

    def taste(self, ch):
        """Eine Taste, während das Post-Panel den Fokus hat (früher ein Zweig der
        Hauptschleife in run_ui) — auch im Antwort-Editor. Gibt BEENDEN
        zurück, wenn die TUI enden soll."""
        if self.MAIL["replying"] and ch is not None and 128 <= ch <= 255:
            self._utf8(ch)                 # Umlaute: getch liefert UTF-8-Bytes
            return None
        return self.TASTEN.verteilen(self, self.ansicht(), ch)

    def taste_antwort(self, ch):
        """Übergang für die Hauptschleife: der Antwort-Editor ist seit
        2026-10-11 eine Ansicht von taste()."""
        return self.taste(ch)

    def _kategorien(self):
        d = self.MAIL["data"] or {}
        return d.get("categories") if isinstance(d.get("categories"), list) else []

    def _gepuffert(self, vor, zurueck):
        """Schnell nachkommende gleiche Tasten zusammenfassen (damit z.B.
        schnelles Durchklicken nicht pro Taste den Body lädt): +1 je Code aus
        `vor`, −1 je Code aus `zurueck`; die erste fremde Taste geht zurück."""
        stdscr, n = self.z.stdscr, 0
        stdscr.nodelay(True)
        while True:
            nx = stdscr.getch()
            if nx in vor:
                n += 1
            elif nx in zurueck:
                n -= 1
            else:
                if nx != -1:
                    curses.ungetch(nx)
                break
        stdscr.timeout(250)
        return n

    # ── überall ──
    def aktion_beenden(self, _taste):
        return BEENDEN

    def aktion_schliessen(self, _taste):
        self.MAIL["active"] = False

    def aktion_eingang(self, _taste):
        self.mail_open_eingang()

    def aktion_poll(self, _taste):
        self.mail_poll(); self.MAIL["data"] = None

    def aktion_abgleich(self, _taste):
        self.mail_reconcile()

    def aktion_zaehlen(self, _taste):
        """z: Zahlen JETZT neu zählen."""
        self._mail_submit(("counts",), "zähle ordner…",
                          lambda: _do_refresh_counts(force=True))
        self.MAIL["msg"] = "zähle neu…"

    def aktion_thema(self, _taste):
        self.z.cycle_theme()

    # ── Ebene 1: Kategorien ──
    def aktion_k_waehlen(self, taste):
        MAIL = self.MAIL
        if taste in ("up", "k"):
            MAIL["sel"] = max(0, MAIL["sel"] - 1)
        else:
            MAIL["sel"] = MAIL["sel"] + 1   # Klemmung beim Zeichnen

    def aktion_k_oeffnen(self, _taste):
        cl = self._kategorien()
        if 0 <= self.MAIL["sel"] < len(cl):
            self.mail_open_category(cl[self.MAIL["sel"]].get("name"))

    # ── Ebene 2: Mails einer Kategorie ──
    def aktion_zurueck(self, _taste):
        """esc (und ← in der Liste) → zurück zu den Kategorien."""
        self.MAIL["level"] = "cats"; self.MAIL["msg"] = ""

    def aktion_modus(self, _taste):
        """v/Tab: lesen ↔ liste."""
        MAIL = self.MAIL
        MAIL["mode2"] = "list" if MAIL["mode2"] == "read" else "read"
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0; MAIL["msg"] = ""

    def aktion_m_waehlen(self, taste):
        """LISTE: rauf/runter wählt eine Mail (gepuffert zusammengefasst)."""
        MAIL = self.MAIL
        runter = (curses.KEY_DOWN, ord("j"), ord("n"), ord(" "))
        rauf = (curses.KEY_UP, ord("k"), ord("N"))
        delta = 1 if taste in ("down", "j", "n", "space") else -1
        delta += self._gepuffert(runter, rauf)
        MAIL["msel"] = max(0, MAIL["msel"] + delta)
        MAIL["bodyoff"] = 0; MAIL["msg"] = ""

    def aktion_m_lesen(self, _taste):
        """aus der Liste: gewählte Mail lesen."""
        MAIL = self.MAIL
        MAIL["mode2"] = "read"
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0

    def aktion_blaettern(self, taste):
        """←/→ = vorige/nächste Mail im Stapel (gepuffert zusammengefasst)."""
        MAIL = self.MAIL
        delta = 1 if taste == "right" else -1
        delta += self._gepuffert((curses.KEY_RIGHT,), (curses.KEY_LEFT,))
        MAIL["msel"] = max(0, MAIL["msel"] + delta)  # Obergrenze beim Zeichnen
        MAIL["expanded"] = False; MAIL["bodyoff"] = 0; MAIL["msg"] = ""

    def aktion_aufklappen(self, _taste):
        """↓ aus der Vorschau = ausklappen."""
        MAIL = self.MAIL
        MAIL["expanded"] = True; MAIL["bodyoff"] = 0; MAIL["msg"] = ""

    def aktion_scrollen(self, taste):
        """Ausgeklappt: ↓ runter (Leertaste 5 Zeilen), ↑ hoch; ganz oben
        nochmal ↑ → wieder einklappen."""
        MAIL = self.MAIL
        runter = (curses.KEY_DOWN, ord("j"))
        rauf = (curses.KEY_UP, ord("k"))
        if taste in ("down", "j", "space"):
            step = (5 if taste == "space" else 1) + self._gepuffert(runter, rauf)
            MAIL["bodyoff"] = max(0, MAIL["bodyoff"] + step)
        elif MAIL["bodyoff"] > 0:
            step = 1 + self._gepuffert(rauf, runter)
            MAIL["bodyoff"] = max(0, MAIL["bodyoff"] - step)
        else:
            MAIL["expanded"] = False
        MAIL["msg"] = ""

    def aktion_seite(self, taste):
        """Bild↓/Bild↑ → Body 5 Zeilen."""
        MAIL = self.MAIL
        if taste == "pgdn":
            MAIL["bodyoff"] = MAIL["bodyoff"] + 5
        else:
            MAIL["bodyoff"] = max(0, MAIL["bodyoff"] - 5)

    def aktion_einsortieren(self, _taste):
        """s: Absender einsortieren (Kategorie wählen)."""
        MAIL = self.MAIL
        MAIL["picking"] = True; MAIL["picksel"] = 0; MAIL["msg"] = ""

    def aktion_abhaken(self, _taste):
        """f (Eingang): gelesen + einsortieren."""
        if self.MAIL["cat"] == MAIL_EINGANG:
            self.mail_mark_read()

    def aktion_loeschen(self, _taste):
        """d: in den Papierkorb (mit Nachfrage); im Eingang nicht."""
        MAIL = self.MAIL
        if MAIL["cat"] == MAIL_EINGANG:
            MAIL["msg"] = "im eingang: f = abhaken (löschen erst nach einsortieren)"
        else:
            MAIL["confirmdel"] = True; MAIL["msg"] = ""

    def aktion_antworten(self, _taste):
        """a: antworten (Split-Editor) — auch aus dem Eingang direkt."""
        self.mail_reply_open()

    # ── Einsortieren: Zielkategorie ──
    def aktion_ziel_waehlen(self, taste):
        MAIL = self.MAIL
        if taste in ("up", "k"):
            MAIL["picksel"] = max(0, MAIL["picksel"] - 1)
        else:
            MAIL["picksel"] = MAIL["picksel"] + 1

    def aktion_ziel_nehmen(self, _taste):
        pcats = [str(c.get("name", "?")) for c in self._kategorien()]
        if 0 <= self.MAIL["picksel"] < len(pcats):
            self.mail_assign(pcats[self.MAIL["picksel"]])

    def aktion_ziel_abbrechen(self, _taste):
        self.MAIL["picking"] = False; self.MAIL["msg"] = ""

    # ── Lösch-Nachfrage ──
    def aktion_loeschen_ja(self, _taste):
        self.mail_delete()

    def aktion_loeschen_nein(self, _taste):
        self.MAIL["confirmdel"] = False; self.MAIL["msg"] = ""

    def draw_mail(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box, wenn das Post/Mail-Panel Fokus hat. Zwei Ebenen:
        Ebene 'cats' = nur die Kategorien (zum Auswählen); Ebene 'mails' = die
        Mails der geöffneten Kategorie. Rein lesend, Auto-Refresh alle ~3s."""
        C, MAIL, _mail_submit = self.z.C, self.MAIL, self._mail_submit
        addclip, mail_load = self.z.addclip, self.mail_load
        mail_request_body = self.mail_request_body
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if iw < 8:
            return
        if (not MAIL["data"]) or (time.time() - MAIL["_ts"] > 3):
            _mail_submit("load", "", mail_load)   # billig, still (kein IMAP)
        d = MAIL["data"]
        if not isinstance(d, dict) or d.get("failed"):
            addclip(by + 1, ix, MAIL["msg"] or "lade mail…", iw, C["faint"])
            return

        cats = d.get("categories") if isinstance(d.get("categories"), list) else []
        live_counts = d.get("live_counts") if isinstance(d.get("live_counts"), dict) else {}
        refreshing = bool(d.get("counts_refreshing"))
        can_poll = bool(d.get("can_poll"))
        polling = bool(d.get("polling"))
        body_top = by + 3
        avail = bottom - body_top

        # ── Ebene 2: Mails der geöffneten Kategorie (LIVE aus dem Ordner) ─
        if MAIL["level"] == "mails" and MAIL["cat"] is not None:
            cat = MAIL["cat"]
            is_eingang = (cat == MAIL_EINGANG)
            catlabel = "Eingang" if is_eingang else cat
            mails = MAIL["mails"]
            src = "live" if MAIL["mails_live"] else "lokal"
            cnt = "…" if mails is None else str(len(mails))
            modetag = "lesen" if MAIL["mode2"] == "read" else "liste"
            head = "Post · %s (%s)" % (catlabel[:max(4, iw - 22)], cnt)
            if mails is not None:
                head += "  [%s/%s]" % (modetag, src)
            if MAIL["busy"]:
                head += "  ⟳ " + MAIL["busy"]
            addclip(by + 1, ix, head, iw, C["bright"])
            if mails is None:
                addclip(body_top, ix, "lädt Ordner…", iw, C["faint"])
                return
            n = len(mails)
            MAIL["msel"] = max(0, min(MAIL["msel"], max(0, n - 1)))

            # Einsortier-Picker überlagert alles: Zielkategorie wählen.
            if MAIL["picking"]:
                pcats = [str(c.get("name", "?")) for c in cats]
                psel = max(0, min(MAIL["picksel"], max(0, len(pcats) - 1)))
                MAIL["picksel"] = psel
                addclip(body_top, ix, "Absender einsortieren in:", iw, C["acc"])
                pavail = bottom - body_top        # bis zur untersten Zeile
                poff = max(0, min(psel - pavail // 2, max(0, len(pcats) - pavail))) \
                    if len(pcats) > pavail else 0
                for r, name in enumerate(pcats[poff:poff + pavail]):
                    idx = poff + r
                    mark = "» " if idx == psel else "  "
                    attr = (C["bright"] | curses.A_REVERSE) if idx == psel else C["bright"]
                    addclip(body_top + 1 + r, ix, mark + name, iw, attr)
                return

            if n == 0:
                # Bei einem Ordner-Fehler den ECHTEN Grund zeigen, nicht „leer".
                addclip(body_top, ix, MAIL["msg"] or "(Ordner leer)", iw, C["faint"])
                return

            # ── Modus LISTE: Blöckchen (Absender + Titel), auswählbar ──
            if MAIL["mode2"] == "list":
                blockh = 3
                vis = max(1, avail // blockh)
                start = max(0, min(MAIL["msel"] - vis // 2, max(0, n - vis)))
                for r in range(vis):
                    idx = start + r
                    if idx >= n:
                        break
                    it = mails[idx]
                    y = body_top + r * blockh
                    seld = (idx == MAIL["msel"])
                    who = (it.get("from") or "?").strip()
                    subj = (it.get("subject") or "").strip() or "(kein Betreff)"
                    if is_eingang:                # Gelesen-Marker + Ziel-Vorschau
                        # → Ziel an die ADRESSZEILE, nicht an den Betreff: ein
                        # langer Betreff schnitt das Ziel sonst ab.
                        who = ("○ " if it.get("seen") else "● ") + who
                        who += ("   → " + it["category"]) if it.get("category") else "   → ?"
                    a1 = (C["bright"] | curses.A_REVERSE) if seld else C["bright"]
                    a2 = (C["dim"] | curses.A_REVERSE) if seld else C["dim"]
                    addclip(y, ix, ("» " if seld else "  ") + who, iw, a1)
                    addclip(y + 1, ix, "  " + subj, iw, a2)
                hint = "wirklich löschen?" if MAIL["confirmdel"] else MAIL["msg"]
                if hint:                       # Frage oder Rückmeldung (Tasten: Leiste)
                    addclip(bottom, ix, hint, iw, C["faint"])
                return

            # ── Modus LESEN: eine Mail, Vorschau / ausgeklappt ──
            it = mails[MAIL["msel"]]
            mail_request_body()
            who = (it.get("from") or "?").strip()
            subj = (it.get("subject") or "").strip() or "(kein Betreff)"
            if is_eingang:                        # Eingang: Status + Ziel im Kopf
                # → Ziel an die Von-/Adresszeile, nicht an den (evtl. langen,
                # abgeschnittenen) Betreff.
                who = ("○ gelesen · " if it.get("seen") else "● neu · ") + who
                if it.get("category"):
                    who += "   → " + it["category"]
            addclip(body_top, ix, "Von:     " + who, iw, C["bright"])
            addclip(body_top + 1, ix, "Betreff: " + subj, iw, C["acc"])
            addclip(body_top + 2, ix, "─" * iw, iw, C["faint"])
            txt_top = body_top + 3
            txt_h = bottom - txt_top
            # Body nur zeigen, wenn er zur AKTUELLEN Mail gehört — sonst „lädt…".
            b = MAIL["body"] if MAIL["bodyfor"] == it.get("uid") else None
            if b is None:
                addclip(txt_top, ix, "lädt Text…", iw, C["faint"])
            elif isinstance(b, dict) and b.get("error"):
                addclip(txt_top, ix, "(Text nicht ladbar: %s)" % b["error"], iw, C["faint"])
            else:
                lines = _wrap((b or {}).get("body", ""), iw)
                if MAIL["expanded"]:
                    boff = max(0, min(MAIL["bodyoff"], max(0, len(lines) - txt_h)))
                    MAIL["bodyoff"] = boff
                    for r, ln in enumerate(lines[boff:boff + txt_h]):
                        addclip(txt_top + r, ix, ln, iw, C["dim"])
                else:
                    prev_h = min(txt_h, 6)
                    for r, ln in enumerate(lines[:prev_h]):
                        addclip(txt_top + r, ix, ln, iw, C["dim"])
                    if len(lines) > prev_h:
                        addclip(txt_top + prev_h, ix, "  …",
                                iw, C["faint"])
            if MAIL["confirmdel"]:
                hint = "wirklich löschen?"
            else:                              # nur Position/Rückmeldung (Tasten: Leiste)
                hint = MAIL["msg"] or ("%d/%d" % (MAIL["msel"] + 1, n))
            addclip(bottom, ix, hint, iw, C["faint"])
            return

        # ── Ebene 1: nur die Kategorien (Auswahl) ─────────────────────
        head = "Postfach · %d Kategorien" % len(cats)
        if MAIL["busy"]:
            head += "  ⟳ " + MAIL["busy"]
        elif polling:
            head += "  ⟳ poll läuft"
        elif refreshing:
            head += "  ⟳ zähle…"
        elif not can_poll:
            head += "  (kein key)"
        addclip(by + 1, ix, head, iw, C["bright"])
        n = len(cats)
        sel = max(0, min(MAIL["sel"], max(0, n - 1)))
        MAIL["sel"] = sel
        off = max(0, min(sel - avail // 2, max(0, n - avail))) if n > avail else 0
        if not cats:
            addclip(body_top, ix, "noch keine Kategorien.", iw, C["faint"])
        namew = max(4, iw - 6)
        for r, c in enumerate(cats[off:off + avail]):
            idx = off + r
            name = str(c.get("name", "?"))
            # Live-Ordnerzahl bevorzugen (echte Größe); sonst lokaler Schnappschuss.
            cnt = live_counts.get(name, c.get("count", 0))
            mark = "» " if idx == sel else "  "
            line = "%s%-*s%4d" % (mark, namew - 2, name[:namew - 2], cnt)
            attr = (C["bright"] | curses.A_REVERSE) if idx == sel else C["bright"]
            addclip(body_top + r, ix, line, iw, attr)
        src = "live" if live_counts else "lokal"
        # Tasten stehen in der Leiste; unten nur Feedback bzw. die Datenquelle.
        hint = MAIL["msg"] or ("[%s]" % src)
        addclip(bottom, ix, hint, iw, C["faint"])

    def mail_reply_open(self):
        """Antwort-Editor öffnen: stellt sicher, dass der Original-Body geladen
        ist (linke Spalte), startet mit leerem Text."""
        MAIL, mail_cur, mail_request_body = self.MAIL, self.mail_cur, self.mail_request_body
        it = mail_cur()
        if not it:
            return
        mail_request_body()
        MAIL["replying"] = True
        MAIL["reply_text"] = ""
        MAIL["reply_origoff"] = 0
        MAIL["reply_confirm"] = False
        MAIL["msg"] = ""

    def _do_reply(self, payload, uid=None, is_eingang=False):
        MAIL, _eingang_drop = self.MAIL, self._eingang_drop
        try:
            r = api_call("/api/mail/reply", method="POST", body=payload,
                         timeout=60.0)
            if isinstance(r, dict) and r.get("ok"):
                if is_eingang:
                    MAIL["msg"] = _reply_filed_msg(r, "gesendet")
                    _eingang_drop(uid)
                else:
                    MAIL["msg"] = "✓ Antwort gesendet"
            else:
                MAIL["msg"] = "senden fehlgeschlagen: %s" % (
                    (r or {}).get("error", "?") if isinstance(r, dict) else "?")
        except Exception:
            MAIL["msg"] = "senden: backend?"

    def mail_reply_send(self):
        """Den getippten Text als Antwort senden (SMTP via Backend, im
        Hintergrund). Der Editor schließt sofort, das Senden läuft im Worker.
        Aus dem Eingang wird die Original-Mail danach auto-einsortiert."""
        MAIL, _do_reply, _mail_submit = self.MAIL, self._do_reply, self._mail_submit
        mail_cur = self.mail_cur
        it = mail_cur()
        if not it or not MAIL["reply_text"].strip():
            MAIL["reply_confirm"] = False
            MAIL["msg"] = "leer — nichts gesendet"
            MAIL["replying"] = False
            return
        payload = {"cat": MAIL["cat"], "uid": it.get("uid"),
                   "account": it.get("account"), "text": MAIL["reply_text"]}
        is_eingang = (MAIL["cat"] == MAIL_EINGANG)
        uid = it.get("uid")
        MAIL["replying"] = False
        MAIL["reply_confirm"] = False
        MAIL["msg"] = "sende antwort…"
        _mail_submit(("reply", uid), "sendet antwort…",
                     lambda p=payload: _do_reply(p, uid=uid, is_eingang=is_eingang))

    def _do_reply_draft(self, payload, uid=None, is_eingang=False):
        MAIL, _eingang_drop = self.MAIL, self._eingang_drop
        try:
            r = api_call("/api/mail/reply", method="POST", body=payload,
                         timeout=60.0)
            if isinstance(r, dict) and r.get("ok"):
                if is_eingang:
                    MAIL["msg"] = _reply_filed_msg(r, "entwurf")
                    _eingang_drop(uid)
                else:
                    MAIL["msg"] = "✎ als Entwurf gespeichert"
            else:
                MAIL["msg"] = "entwurf fehlgeschlagen: %s" % (
                    (r or {}).get("error", "?") if isinstance(r, dict) else "?")
        except Exception:
            MAIL["msg"] = "entwurf: backend?"

    def mail_reply_draft(self):
        """Den getippten Text als ECHTEN Entwurf in den Drafts-Ordner legen (IMAP
        APPEND via Backend) — nichts geht raus, in Outlook/Handy weiterschreibbar.
        Editor schließt sofort, das Speichern läuft im Worker. Aus dem Eingang
        wird die Original-Mail danach auto-einsortiert."""
        MAIL, _do_reply_draft = self.MAIL, self._do_reply_draft
        _mail_submit, mail_cur = self._mail_submit, self.mail_cur
        it = mail_cur()
        if not it or not MAIL["reply_text"].strip():
            MAIL["reply_confirm"] = False
            MAIL["msg"] = "leer — kein entwurf"
            MAIL["replying"] = False
            return
        payload = {"cat": MAIL["cat"], "uid": it.get("uid"),
                   "account": it.get("account"), "text": MAIL["reply_text"],
                   "draft": True}
        is_eingang = (MAIL["cat"] == MAIL_EINGANG)
        uid = it.get("uid")
        MAIL["replying"] = False
        MAIL["reply_confirm"] = False
        MAIL["msg"] = "speichere entwurf…"
        _mail_submit(("draft", uid), "speichere entwurf…",
                     lambda p=payload: _do_reply_draft(p, uid=uid, is_eingang=is_eingang))

    # ── Antwort-Editor (Ansichten „antwort" und „antwort:frage") ──
    def aktion_a_tippen(self, zeichen):
        self.MAIL["reply_text"] += zeichen

    def _utf8(self, ch):
        """UTF-8 best effort (Umlaute): Bytes sammeln, bis ein Zeichen fertig ist."""
        MAIL = self.MAIL
        buf = MAIL.get("_u8", b"") + bytes([ch & 0xFF])
        try:
            MAIL["reply_text"] += buf.decode("utf-8")
            MAIL["_u8"] = b""
        except UnicodeDecodeError:
            MAIL["_u8"] = buf if len(buf) < 4 else b""

    def aktion_a_zeile(self, _taste):
        self.MAIL["reply_text"] += "\n"

    def aktion_a_weg(self, _taste):
        self.MAIL["reply_text"] = self.MAIL["reply_text"][:-1]

    def aktion_a_original(self, taste):
        """↑↓ scrollt das Original (links)."""
        MAIL = self.MAIL
        if taste == "up":
            MAIL["reply_origoff"] = max(0, MAIL["reply_origoff"] - 1)
        else:
            MAIL["reply_origoff"] = MAIL["reply_origoff"] + 1

    def aktion_a_fertig(self, _taste):
        """esc → senden / Entwurf / verwerfen / weiter?"""
        self.MAIL["reply_confirm"] = True

    def aktion_a_senden(self, _taste):
        self.mail_reply_send()

    def aktion_a_entwurf(self, _taste):
        self.mail_reply_draft()

    def aktion_a_verwerfen(self, _taste):
        MAIL = self.MAIL
        MAIL["replying"] = False; MAIL["reply_confirm"] = False
        MAIL["msg"] = "verworfen"

    def aktion_a_weiter(self, _taste):
        self.MAIL["reply_confirm"] = False

    def draw_reply(self, by, bx, bh, bw):
        """Antwort-Editor: zwei Kästen nebeneinander — links die Original-Mail,
        rechts dein Antwort-Text (Editor mit Cursor)."""
        C, MAIL, addclip, draw_box = self.z.C, self.MAIL, self.z.addclip, self.z.draw_box
        mail_cur = self.mail_cur
        gap = 1
        half = (bw - gap) // 2
        lw, rw = half, bw - gap - half
        # Linker Kasten: Original
        draw_box(by, bx, bh, lw, "original")
        it = mail_cur() or {}
        b = MAIL["body"] if isinstance(MAIL["body"], dict) else {}
        lix, liw = bx + 2, lw - 4
        addclip(by + 1, lix, "Von:     " + (it.get("from") or "?"), liw, C["dim"])
        addclip(by + 2, lix, "Betreff: " + (it.get("subject") or ""), liw, C["dim"])
        addclip(by + 3, lix, "─" * liw, liw, C["faint"])
        olines = _wrap(b.get("body", "") if b else "", liw)
        oh = (by + bh - 2) - (by + 4)
        ooff = max(0, min(MAIL["reply_origoff"], max(0, len(olines) - oh)))
        MAIL["reply_origoff"] = ooff
        for r, ln in enumerate(olines[ooff:ooff + oh]):
            addclip(by + 4 + r, lix, ln, liw, C["faint"])

        # Rechter Kasten: dein Editor
        rbx = bx + lw + gap
        title = "antwort" + ("  · senden?" if MAIL["reply_confirm"] else "")
        draw_box(by, rbx, bh, rw, title)
        rix, riw = rbx + 2, rw - 4
        to = ""
        try:
            import email.utils as _eu
            to = _eu.parseaddr(it.get("from", ""))[1] or it.get("from", "")
        except Exception:
            to = it.get("from", "")
        addclip(by + 1, rix, "An: " + to, riw, C["dim"])
        addclip(by + 2, rix, "─" * riw, riw, C["faint"])
        ed_top = by + 3
        # bis zur untersten Zeile im Kasten (die Tasten stehen in der Leiste)
        ed_h = (by + bh - 1) - ed_top
        elines = _wrap(MAIL["reply_text"], riw) or [""]
        # Cursor ans Ende; nur das untere Fenster zeigen, wenn länger als Platz.
        estart = max(0, len(elines) - ed_h)
        for r, ln in enumerate(elines[estart:estart + ed_h]):
            cur = "_" if (estart + r == len(elines) - 1) else ""
            addclip(ed_top + r, rix, ln + cur, riw, C["bright"])
