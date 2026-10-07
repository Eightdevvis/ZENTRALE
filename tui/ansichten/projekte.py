# tui/ansichten/projekte.py
#
# Projekte im KI-Chat (Claude-Web-Plan Phase 6, 2026-10-07): ein Rahmen für
# ein Thema mit eigenen Anweisungen und Wissensdateien; ein Gespräch gehört
# optional zu einem Projekt. Backend: ui/routen/projekte.py, Speicher
# core/projekte.py, Doku memory/ki/projekte.md.
#
# Zwei Dinge wohnen hier:
#   - /projekt im Chat: ohne Argument eine Auswahl (Projekte, „kein
#     projekt", „neues projekt …"), mit Namen direkt zuordnen,
#     /projekt neu <name> legt an und ordnet zu, /projekt kein löst.
#   - /projekte: die Übersicht als Überlagerung im Chat-Kasten (wie die
#     Gesprächsliste und das Gedächtnis). Liste der Projekte → Enter zeigt
#     eins: Anweisungen, Wissen, Gespräche. Dort e = Anweisungen im Editor,
#     w = Wissen per Pfad, Enter = Gespräch öffnen, n = neues Gespräch darin.
#
# Warum eigene Überlagerung und kein Abschnitt der Gedächtnis-Ansicht: ein
# Projekt hat eine zweite Ebene (seine Gespräche, sein Wissen) und eigene
# Eingaben (Name, Pfad). Im Gedächtnis wäre das ein Sonderfall in jedem
# Zweig; hier ist es eine Klasse, im Chat-Code nur fünf Haken.
#
# Reine Helfer (projekt_name, finden, wahl, liste_zeilen, detail_zeilen,
# groesse_text) sind ohne curses und ohne HTTP testbar
# (tests/test_projekte_ansicht.py).

import curses
import json
import os
import subprocess
import tempfile
import urllib.error

from . import eingabe
from .basis import api_call
from .gedaechtnis import editor_befehl
from .gespraechsliste import alter_text
from .text import md_zeilen

# Was in /projekt <wort> nicht als Projektname gilt.
WORTE_KEIN = ("kein", "keins", "keines", "aus", "-")
WORT_NEU = "neu"
MAX_DATEI = 2_000_000       # wie core/projekte.MAX_WISSEN_BYTES
SPALTE = 64                 # Listen-Zeilen höchstens so breit (wie die Skills)


# ── Reine Helfer ─────────────────────────────────────────────────────────

def projekt_name(eintraege, gid, neu=None):
    """Der Projektname zum offenen Gespräch (aus der Gesprächsliste), ohne
    Gespräch der des nächsten neuen (neu_projekt). → Name oder ""."""
    if gid:
        e = next((e for e in eintraege or [] if e.get("id") == gid), None)
        return str((e or {}).get("projekt_name") or "")
    return str((neu or {}).get("name") or "") if isinstance(neu, dict) else ""


def finden(projekte, eingabe_text):
    """Projekt zu einem getippten Namen: id oder Name, Groß/klein egal.
    → Eintrag oder None."""
    roh = " ".join(str(eingabe_text or "").split()).lower()
    if not roh:
        return None
    return next((p for p in projekte or []
                 if roh in (str(p.get("id") or "").lower(), str(p.get("name") or "").lower())),
                None)


def wahl(projekte, aktuell=""):
    """Die Auswahl für /projekt ohne Argument (wie /modell in chat.py):
    {"titel", "optionen": [(text, daten)], "idx"}. daten: {"projekt": id},
    {"projekt": None} oder {"neu": True}. idx steht auf dem aktuellen."""
    optionen, idx = [], None
    for p in projekte or []:
        if p.get("name") == aktuell and aktuell:
            idx = len(optionen)
        optionen.append((p.get("name") or p.get("id"), {"projekt": p.get("id")}))
    if idx is None and not aktuell:
        idx = len(optionen)
    optionen.append(("kein projekt", {"projekt": None}))
    optionen.append(("neues projekt …", {"neu": True}))
    titel = "projekt für dieses gespräch" + (" (jetzt: %s)" % aktuell if aktuell else "")
    return {"titel": titel, "optionen": optionen, "idx": idx or 0}


def groesse_text(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%d KB" % round(n / 1024)
    return "%.1f MB" % (n / (1024 * 1024))


def liste_zeilen(projekte, idx, breite):
    """Die Projekt-Liste. → [(text, art)], art "gewaehlt" | "normal"."""
    breite = min(int(breite), SPALTE)
    raus = []
    for i, p in enumerate(projekte or []):
        zeiger = "›" if i == idx else " "
        n = int(p.get("wissen") or 0)
        rechts = "%d datei%s" % (n, "" if n == 1 else "en") if n else ""
        links = "%s %s" % (zeiger, p.get("name") or p.get("id") or "?")
        luecke = max(1, breite - len(links) - len(rechts))
        raus.append(((links + " " * luecke + rechts)[:breite],
                     "gewaehlt" if i == idx else "normal"))
    return raus


def detail_zeilen(p, wahl_idx, breite, jetzt=None):
    """Ein Projekt im Einzelnen: Anweisungen, Wissen, Gespräche.
    → ([(text, art)], zeile_der_wahl). art wie in gedaechtnis.inhalt_zeilen."""
    breite = max(6, int(breite))
    zeilen = [("anweisungen", "kopf")]
    text = (p.get("anweisungen") or "").strip()
    if text:
        zeilen += md_zeilen(text, breite)
    else:
        zeilen.append(("(noch keine) — e schreibt sie im editor", "leise"))
    zeilen += [("", ""), ("wissen", "kopf")]
    breite = min(breite, SPALTE)      # Größe/Alter bleiben beim Namen
    wissen = p.get("wissen") or []
    if wissen:
        for w in wissen:
            g = groesse_text(w.get("groesse"))
            links = "  " + str(w.get("name") or "?")
            zeilen.append(((links + " " * max(1, breite - len(links) - len(g)) + g)[:breite], ""))
    else:
        zeilen.append(("  (keins) — w fügt eine datei hinzu", "leise"))
    zeilen += [("", ""), ("gespräche", "kopf")]
    gespraeche = p.get("gespraeche") or []
    ziel = 0
    if not gespraeche:
        zeilen.append(("  (noch keine) — n beginnt eins in diesem projekt", "leise"))
    for i, g in enumerate(gespraeche):
        zeiger = "›" if i == wahl_idx else " "
        alter = alter_text(g.get("letzte"), jetzt)
        titel = str(g.get("titel") or "neues gespräch").replace("\n", " ")
        if g.get("archiviert"):
            titel += " (archiv)"
        platz = max(1, breite - 3 - len(alter) - 1)
        if len(titel) > platz:
            titel = titel[:max(1, platz - 1)] + "…"
        if i == wahl_idx:
            ziel = len(zeilen)
        zeilen.append((("%s %s" % (zeiger, titel.ljust(platz)) + " " + alter)[:breite],
                       "gewaehlt" if i == wahl_idx else ""))
    return zeilen, ziel


# ── Zuordnen (/projekt) und Übersicht (/projekte) ───────────────────────

class Projekte:
    """Zustand der Übersicht in chat.AI["projekte"] (None = zu):
    {liste, idx, archiv, detail, wahl, eingabe}. eingabe: offenes
    Eingabefeld {art: "name"|"pfad", text, cur, u8} oder None.
    Der Projektname des offenen Gesprächs steht in chat.AI["projekt"]."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        self.AI.setdefault("projekte", None)
        self.AI.setdefault("projekt", "")

    # ── HTTP ───────────────────────────────────────────────────────────
    def _rufen(self, pfad, methode="GET", body=None, fehlschlag="ging nicht"):
        """api_call mit Klartext in der Statuszeile. → Antwort oder None."""
        try:
            return api_call(pfad, methode, body)
        except urllib.error.HTTPError as e:
            self.AI["msg"] = _fehlertext(e, fehlschlag)
        except (urllib.error.URLError, OSError, ValueError):
            self.AI["msg"] = "keine verbindung — " + fehlschlag
        return None

    def projekte_holen(self, archiv=False):
        d = self._rufen("/api/projekte" + ("?archiv=1" if archiv else ""),
                        fehlschlag="projekte nicht geladen")
        return [p for p in (d or {}).get("projekte") or [] if isinstance(p, dict)] \
            if isinstance(d, dict) else None

    # ── /projekt ───────────────────────────────────────────────────────
    def befehl(self, name, arg):
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst danach (esc stoppt)"
            return
        if name == "projekte":
            self.oeffnen()
            return
        arg = " ".join(arg.split())
        if arg.lower() in WORTE_KEIN:
            self.zuordnen(None)
            return
        teile = arg.split(None, 1)
        if teile and teile[0].lower() == WORT_NEU:
            if len(teile) < 2:
                AI["msg"] = "/projekt neu <name> legt ein projekt an"
                return
            self.anlegen(teile[1], zuordnen=True)
            return
        liste = self.projekte_holen()
        if liste is None:
            return
        if not arg:
            if AI.get("gid") == "erinnerungen":
                AI["msg"] = "„erinnerungen“ gehört zu keinem projekt"
                return
            w = wahl(liste, AI.get("projekt") or "")
            w["aktion"] = self._gewaehlt
            AI["wahl"] = w
            return
        p = finden(liste, arg)
        if p is None:
            AI["msg"] = "kein projekt „%s“ — /projekt neu %s legt es an" % (arg, arg)
            return
        self.zuordnen(p["id"])

    def _gewaehlt(self, daten):
        """Aus der Auswahl von /projekt."""
        if daten.get("neu"):
            AI = self.AI
            AI["input"] = "/projekt neu "
            AI["cur"] = len(AI["input"])
            AI["msg"] = "namen tippen, enter legt das projekt an"
            return
        self.zuordnen(daten.get("projekt"))

    def zuordnen(self, pid):
        """Das offene Gespräch (oder das nächste neue) einem Projekt
        zuordnen; pid None löst es."""
        AI = self.AI
        if AI.get("gid") == "erinnerungen" and pid:
            AI["msg"] = "„erinnerungen“ gehört zu keinem projekt"
            return False
        d = self._rufen("/api/projekte/zuordnen", "POST",
                        {"gespraech": AI.get("gid"), "projekt": pid},
                        fehlschlag="nicht zugeordnet")
        if not isinstance(d, dict):
            return False
        with self.chat.AI_LOCK:
            AI["projekt"] = d.get("name") or ""
            for e in AI.get("gespraeche") or []:
                if e.get("id") == AI.get("gid"):
                    e["projekt"], e["projekt_name"] = pid, d.get("name")
        AI["msg"] = ("gehört jetzt zum projekt „%s“" % d.get("name")) if pid \
            else "gehört zu keinem projekt mehr"
        return True

    def anlegen(self, name, zuordnen=False):
        d = self._rufen("/api/projekte", "POST", {"name": name},
                        fehlschlag="nicht angelegt")
        if not isinstance(d, dict):
            return None
        if zuordnen:
            if self.zuordnen(d.get("id")):
                self.AI["msg"] = "projekt „%s“ angelegt — dieses gespräch gehört dazu" % d.get("name")
        else:
            self.AI["msg"] = "projekt „%s“ angelegt" % d.get("name")
        return d

    # ── Übersicht ──────────────────────────────────────────────────────
    def oeffnen(self, archiv=False):
        AI = self.AI
        liste = self.projekte_holen(archiv)
        if liste is None:
            return
        alt = AI.get("projekte") or {}
        AI["projekte"] = {"liste": liste, "idx": min(alt.get("idx", 0), max(0, len(liste) - 1)),
                          "archiv": archiv, "detail": None, "wahl": 0,
                          "eingabe": None, "scroll": 0}
        AI["liste"] = None
        AI["gedaechtnis"] = None
        AI["ablage"] = None
        AI["msg"] = ""

    def schliessen(self):
        self.AI["projekte"] = None

    def detail_laden(self, pid):
        d = self._rufen("/api/projekte/%s" % pid, fehlschlag="projekt nicht geladen")
        if isinstance(d, dict):
            P = self.AI["projekte"]
            P["detail"], P["scroll"] = d, 0
            P["wahl"] = min(P.get("wahl", 0), max(0, len(d.get("gespraeche") or []) - 1))
        return d

    def gewaehlt(self):
        P = self.AI["projekte"]
        if not P["liste"]:
            return None
        P["idx"] = max(0, min(P["idx"], len(P["liste"]) - 1))
        return P["liste"][P["idx"]]

    def taste(self, ch):
        P = self.AI["projekte"]
        if P["eingabe"] is not None:
            self._taste_eingabe(ch)
        elif P["detail"] is not None:
            self._taste_detail(ch)
        else:
            self._taste_liste(ch)

    def _taste_liste(self, ch):
        P, AI = self.AI["projekte"], self.AI
        n = len(P["liste"])
        if ch == 27:
            self.schliessen()
        elif ch in (curses.KEY_UP, curses.KEY_DOWN) and n:
            P["idx"] = (P["idx"] + (1 if ch == curses.KEY_DOWN else -1)) % n
        elif ch in (10, 13, curses.KEY_ENTER):
            p = self.gewaehlt()
            if p:
                self.detail_laden(p["id"])
        elif ch == ord("n"):
            P["eingabe"] = {"art": "name", "text": "", "cur": 0, "u8": b""}
        elif ch == ord("z"):
            self.oeffnen(archiv=not P["archiv"])
        elif ch == ord("a"):
            p = self.gewaehlt()
            if p:
                an = not P["archiv"]
                if self._rufen("/api/projekte/%s/archiv" % p["id"], "POST", {"an": an},
                               fehlschlag="nicht archiviert") is not None:
                    self.oeffnen(P["archiv"])
                    AI["msg"] = ("„%s“ archiviert — z zeigt das archiv" % p["name"]) if an \
                        else ("„%s“ zurückgeholt" % p["name"])

    def _taste_detail(self, ch):
        P, AI = self.AI["projekte"], self.AI
        d = P["detail"]
        gespraeche = d.get("gespraeche") or []
        if ch == 27:
            P["detail"] = None
        elif ch in (curses.KEY_UP, curses.KEY_DOWN) and gespraeche:
            P["wahl"] = (P["wahl"] + (1 if ch == curses.KEY_DOWN else -1)) % len(gespraeche)
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            P["scroll"] = max(0, P["scroll"] + (-10 if ch == curses.KEY_PPAGE else 10))
        elif ch in (10, 13, curses.KEY_ENTER) and gespraeche:
            g = gespraeche[max(0, min(P["wahl"], len(gespraeche) - 1))]
            self.schliessen()
            self.chat.gespraech_oeffnen(g["id"])
        elif ch == ord("n"):
            self.neues_gespraech(d)
        elif ch == ord("e"):
            self.anweisungen_bearbeiten(d)
        elif ch == ord("w"):
            P["eingabe"] = {"art": "pfad", "text": "", "cur": 0, "u8": b""}
        elif ch == ord("r"):
            self.detail_laden(d["id"])

    def _taste_eingabe(self, ch):
        P = self.AI["projekte"]
        e = P["eingabe"]
        if ch == 27:
            P["eingabe"] = None
        elif ch in (10, 13, curses.KEY_ENTER):
            P["eingabe"] = None
            text = e["text"].strip()
            if not text:
                return
            if e["art"] == "name":
                if self.anlegen(text) is not None:
                    self.oeffnen(False)
            else:
                self.wissen_hinzufuegen(P["detail"], text)
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            e["text"], e["cur"] = eingabe.zurueck(e["text"], e["cur"])
        elif ch == curses.KEY_LEFT:
            e["text"], e["cur"] = eingabe.links(e["text"], e["cur"])
        elif ch == curses.KEY_RIGHT:
            e["text"], e["cur"] = eingabe.rechts(e["text"], e["cur"])
        elif isinstance(ch, int) and 32 <= ch <= 126:
            e["text"], e["cur"] = eingabe.einfuegen(e["text"], e["cur"], chr(ch), grenze=400)
        elif isinstance(ch, int) and 128 <= ch <= 255:
            e["u8"], z = eingabe.utf8_byte(e["u8"], ch)
            if z is not None and eingabe.druckbar(z):
                e["text"], e["cur"] = eingabe.einfuegen(e["text"], e["cur"], z, grenze=400)

    # ── Aktionen im Projekt ────────────────────────────────────────────
    def neues_gespraech(self, d):
        """n im Projekt: das nächste Senden beginnt ein Gespräch darin."""
        AI = self.AI
        if AI["streaming"]:
            AI["msg"] = "antwort läuft noch — erst stoppen (esc)"
            return
        if self._rufen("/api/chat/clear", "POST", {"projekt": d["id"]},
                       fehlschlag="kein neues gespräch") is None:
            return
        self.schliessen()
        self.chat.leeren()
        AI["projekt"] = d.get("name") or ""
        AI["msg"] = "neues gespräch im projekt „%s“" % AI["projekt"]

    def wissen_hinzufuegen(self, d, pfad):
        """Eine Datei per Pfad ins Projekt. Das Backend liest sie; läuft es
        auf einem anderen Rechner (zentrale-remote), liest die TUI sie hier
        und schickt den Text mit — die Sperrliste prüft das Backend so oder
        so am Pfad."""
        AI = self.AI
        voll = os.path.abspath(os.path.expanduser(pfad))
        try:
            r = api_call("/api/projekte/%s/wissen" % d["id"], "POST", {"pfad": voll})
        except urllib.error.HTTPError as e:
            antwort = _antwort(e)
            if not (e.code == 404 and antwort.get("fehlt")):
                AI["msg"] = (antwort.get("error") or "nicht hinzugefügt").lower()
                return
            r = self._hier_lesen_und_schicken(d, voll)
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht hinzugefügt"
            return
        if isinstance(r, dict) and r.get("name"):
            AI["msg"] = "„%s“ liegt jetzt im projekt" % r["name"]
            self.detail_laden(d["id"])

    def _hier_lesen_und_schicken(self, d, voll):
        AI = self.AI
        try:
            if not os.path.isfile(voll):
                AI["msg"] = "die datei gibt es nicht: " + voll
                return None
            if os.path.getsize(voll) > MAX_DATEI:
                AI["msg"] = "die datei ist zu groß"
                return None
            with open(voll, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            AI["msg"] = "die datei ist keine lesbare textdatei"
            return None
        return self._rufen("/api/projekte/%s/wissen" % d["id"], "POST",
                           {"pfad": voll, "text": text}, fehlschlag="nicht hinzugefügt")

    def anweisungen_bearbeiten(self, d):
        """Anweisungen im externen Editor (wie die Kernakten im Gedächtnis).
        Scheitert das Speichern, bleibt die Zwischendatei liegen."""
        AI = self.AI
        cmd = editor_befehl()
        if cmd is None:
            AI["msg"] = "kein editor gefunden (nano fehlt)"
            return
        d = self.detail_laden(d["id"]) or d          # den neuesten Stand bearbeiten
        alt = d.get("anweisungen") or ""
        fd, pfad = tempfile.mkstemp(prefix="zentrale-projekt-%s-" % d["id"], suffix=".md")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(alt)
        stdscr = self.chat.z.stdscr
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.call(cmd + [pfad])
        except OSError:
            pass
        finally:
            curses.reset_prog_mode()
            stdscr.clear()
            stdscr.refresh()
        try:
            with open(pfad, encoding="utf-8") as f:
                neu = f.read()
        except OSError:
            AI["msg"] = "datei aus dem editor nicht lesbar"
            return
        if neu.strip() == alt.strip():
            os.unlink(pfad)
            AI["msg"] = "nichts geändert"
            return
        if self._rufen("/api/projekte/%s/anweisungen" % d["id"], "PUT",
                       {"text": neu, "stand": d.get("stand")},
                       fehlschlag="nicht gespeichert") is None:
            AI["msg"] += " — dein text liegt in " + pfad
            self.detail_laden(d["id"])
            return
        os.unlink(pfad)
        self.detail_laden(d["id"])
        AI["msg"] = "anweisungen gespeichert (die alte fassung bleibt als sicherung)"

    # ── Zeichnen ───────────────────────────────────────────────────────
    def fusszeile(self):
        P = self.AI["projekte"]
        if P["eingabe"] is not None:
            return "enter fertig · esc abbrechen"
        if P["detail"] is not None:
            return ("↑↓ gespräch · enter öffnen · n neues gespräch · e anweisungen · "
                    "w wissen · esc zurück")
        return ("↑↓ wählen · enter öffnen · n neues projekt · "
                + ("a zurückholen · z zurück" if P["archiv"] else "a archivieren · z archiv")
                + " · esc zu")

    def zeichnen(self, by, bx, bh, bw):
        z = self.chat.z
        C, addclip = z.C, z.addclip
        P = self.AI["projekte"]
        inx, inw = bx + 2, max(6, bw - 4)
        d = P["detail"]
        if d is not None:
            kopf = "projekt · " + str(d.get("name") or "")
            if d.get("archiviert"):
                kopf += " (archiv)"
        else:
            kopf = "projekte · archiv" if P["archiv"] else "projekte"
        addclip(by + 1, inx, kopf, inw, C["acc"])

        fuss = []
        msg = self.AI.get("msg")
        if msg:
            fuss.append(msg)
        e = P["eingabe"]
        if e is not None:
            frage = "name des neuen projekts: " if e["art"] == "name" else "pfad der datei: "
            fuss.append(frage + e["text"] + "▌")
        fuss.append(self.fusszeile())
        zeilen_fuss = []
        for f in fuss:
            zeilen_fuss += [f[i:i + inw] for i in range(0, len(f), inw)] or [""]
        zeilen_fuss = zeilen_fuss[-max(1, bh - 4):]
        oben, unten = by + 3, by + bh - 2 - len(zeilen_fuss)
        platz = max(1, unten - oben + 1)

        stile = {"": C["bright"], "kopf": C["acc"], "liste": C["bright"], "code": C["dim"],
                 "leise": C["faint"], "gewaehlt": C["bright"] | curses.A_BOLD,
                 "normal": C["dim"]}
        if d is not None:
            zeilen, ziel = detail_zeilen(d, P["wahl"], inw)
            if ziel and (ziel < P["scroll"] or ziel >= P["scroll"] + platz):
                P["scroll"] = max(0, ziel - platz // 2)
        else:
            zeilen = liste_zeilen(P["liste"], P["idx"], inw)
            ziel = P["idx"]
            if not zeilen:
                zeilen = [("noch keine projekte — n legt eins an" if not P["archiv"]
                           else "archiv ist leer", "leise")]
            P["scroll"] = max(0, min(ziel - platz // 2, len(zeilen) - platz))
        P["scroll"] = max(0, min(P["scroll"], max(0, len(zeilen) - platz)))
        for i, (text, art) in enumerate(zeilen[P["scroll"]:P["scroll"] + platz]):
            addclip(oben + i, inx, text, inw, stile.get(art, C["dim"]))
        if P["scroll"] + platz < len(zeilen) and unten >= oben:
            addclip(unten, inx + inw - 1, "↓", 1, C["faint"])
        y = by + bh - 1 - len(zeilen_fuss)
        for i, f in enumerate(zeilen_fuss):
            addclip(y + i, inx, f, inw, C["warn"] if (msg and i == 0) else C["faint"])


def _antwort(e):
    try:
        d = json.loads(e.read().decode("utf-8", "replace"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _fehlertext(e, rueckfall):
    """Die Klartext-Meldung aus einer Fehler-Antwort des Backends."""
    return (_antwort(e).get("error") or rueckfall).lower()
