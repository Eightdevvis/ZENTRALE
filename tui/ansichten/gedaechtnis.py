# tui/ansichten/gedaechtnis.py
#
# Das Gedächtnis der KI zum Ansehen und Ändern (Claude-Web-Plan Phase 3,
# 2026-10-07): eine Überlagerung IM Chat-Kasten wie die Gesprächsliste,
# geöffnet mit /gedaechtnis (bzw. /skills, dann gleich bei den Skills).
#
# Zeigt in fünf Abschnitten: Hausregeln, Steckbrief, Ziele (die drei
# Kernakten, die bei jedem Zug ganz im Kopf der KI stehen), die Bereiche
# (nur Titel) und die Skills. Ändern kann Sasha hier zweierlei:
#   - eine Kernakte im Editor ($VISUAL/$EDITOR, sonst nano, sonst vi) —
#     zurück geht sie über PUT /api/gedaechtnis/<akte>; das Backend legt die
#     alte Fassung als .bak ab. Die TUI kann auf dem Laptop gegen das
#     PC-Backend laufen, darum Text per HTTP und eine Zwischendatei hier;
#   - einen Skill an/aus (POST /api/skills/<name>/status) — Sasha soll dafür
#     nicht in Dateien müssen.
#
# Warum Überlagerung im Chat und kein eigener Platz im Rad: das Gedächtnis
# gehört zum Gespräch mit der KI, und ein Rad-Platz braucht ein eigenes
# Pixel-Symbol, eine Taste und verschiebt die gespeicherte Rad-Stellung —
# offen bis Sasha sagt, ob er es dort will.
#
# Reine Helfer (reiter, inhalt_zeilen, naechster_status, editor_befehl) sind
# ohne curses und ohne HTTP testbar (tests/test_gedaechtnis_ansicht.py).

import curses
import json
import os
import shlex
import shutil
import subprocess
import tempfile
import urllib.error

from . import fussleiste
from .basis import api_call
from .text import md_zeilen

ABSCHNITTE = [("hausregeln", "hausregeln"), ("steckbrief", "steckbrief"),
              ("ziele", "ziele"), ("bereiche", "bereiche"), ("skills", "skills")]
KERNAKTEN = ("hausregeln", "steckbrief", "ziele")

# Wörter, die Sasha sieht (keine Fachwörter aus der Datei).
STATUS_WORT = {"aktiv": "an", "aus": "aus", "vorgeschlagen": "vorgeschlagen"}
HERKUNFT_WORT = {"sasha": "von dir", "ki": "von der ki", "anthropic": "von anthropic",
                 "zentrale": "mitgeliefert"}


# ── Reine Helfer ─────────────────────────────────────────────────────────

def naechster_status(status):
    """Umschalten: an → aus, alles andere → an."""
    return "aus" if status == "aktiv" else "aktiv"


def editor_befehl(umgebung=None, finden=shutil.which):
    """Der Editor als Argumentliste, oder None. $VISUAL vor $EDITOR (wie
    git), sonst nano, sonst vi."""
    umgebung = os.environ if umgebung is None else umgebung
    for name in (umgebung.get("VISUAL"), umgebung.get("EDITOR")):
        if name and name.strip():
            try:
                teile = shlex.split(name)
            except ValueError:
                continue
            if teile and finden(teile[0]):
                return teile
    for kandidat in ("nano", "vi"):
        if finden(kandidat):
            return [kandidat]
    return None


def reiter(idx, breite):
    """Die Abschnitts-Leiste. -> [(text, gewaehlt)]. Passt sie nicht in die
    Breite, nur der gewählte mit Pfeilen und Nummer."""
    teile = [(name, i == idx) for i, (_s, name) in enumerate(ABSCHNITTE)]
    lang = sum(len(t) for t, _ in teile) + 3 * (len(teile) - 1)
    if lang <= breite:
        raus = []
        for i, t in enumerate(teile):
            if i:
                raus.append((" · ", False))
            raus.append(t)
        return raus
    return [("‹ %s ›  %d/%d" % (ABSCHNITTE[idx][1], idx + 1, len(ABSCHNITTE)), True)]


def _akte(daten, schluessel):
    for k in (daten or {}).get("kernakten") or []:
        if isinstance(k, dict) and k.get("akte") == schluessel:
            return k
    return None


def inhalt_zeilen(daten, abschnitt, breite, wahl=0):
    """Der Inhalt eines Abschnitts. -> ([(text, art)], zeile_der_wahl)
    art: "" | "kopf" | "liste" | "code" | "leise" | "gewaehlt" | "aus".
    zeile_der_wahl: wo der gewählte Skill steht (sonst 0), fürs Scrollen."""
    breite = max(6, int(breite))
    if abschnitt in KERNAKTEN:
        akte = _akte(daten, abschnitt) or {}
        text = (akte.get("text") or "").strip()
        if not text:
            return [("(noch leer) — e öffnet sie im editor", "leise")], 0
        return md_zeilen(text, breite), 0
    if abschnitt == "bereiche":
        zeilen = [("was die ki nachlesen kann (nur die titel stehen in ihrem kopf):",
                   "leise"), ("", "")]
        for b in (daten or {}).get("bereiche") or []:
            titel = b.get("titel") or []
            zeilen.append(("%s/  (%d)" % (b.get("bereich"), len(titel)), "kopf"))
            if titel:
                for z in md_zeilen(", ".join(titel), breite - 2):
                    zeilen.append(("  " + z[0], ""))
            else:
                zeilen.append(("  —", "leise"))
        return zeilen, 0
    # skills
    skills = (daten or {}).get("skills") or []
    if not skills:
        return [("noch keine skills", "leise")], 0
    zeilen, ziel = [], 0
    breite = min(breite, 64)          # auf breiten Schirmen bleibt der Status beim Namen
    for i, s in enumerate(skills):
        status = s.get("status") or "aus"
        punkt = "●" if status == "aktiv" else ("◌" if status == "vorgeschlagen" else "○")
        zeiger = "›" if i == wahl else " "
        rechts = "%s · %s" % (STATUS_WORT.get(status, status),
                              HERKUNFT_WORT.get(s.get("herkunft"), s.get("herkunft") or "-"))
        links = "%s %s %s" % (zeiger, punkt, s.get("name") or "?")
        luecke = max(1, breite - len(links) - len(rechts))
        if i == wahl:
            ziel = len(zeilen)
        art = "gewaehlt" if i == wahl else ("aus" if status != "aktiv" else "")
        zeilen.append(((links + " " * luecke + rechts)[:breite], art))
        for z in md_zeilen(s.get("beschreibung") or "", breite - 4)[:2]:
            zeilen.append(("    " + z[0], "leise"))
        # 2026-10-07: warum ein Skill aus ist („braucht: …") oder was Sasha
        # zu ihm wissen soll (vermerk) — je eine Zeile, aus /api/skills.
        for wort, feld in (("braucht", "braucht"), ("hinweis", "vermerk")):
            if s.get(feld):
                for z in md_zeilen("%s: %s" % (wort, s[feld]), breite - 4)[:2]:
                    zeilen.append(("    " + z[0], "leise"))
    return zeilen, ziel


# ── Die Überlagerung ─────────────────────────────────────────────────────

class Gedaechtnis:
    """Zustand liegt in chat.AI["gedaechtnis"] (None = zu):
    {abschnitt, daten, scroll, wahl}."""

    def __init__(self, chat):
        self.chat = chat
        self.AI = chat.AI
        self.AI.setdefault("gedaechtnis", None)

    # ── Daten ──────────────────────────────────────────────────────────
    def holen(self):
        try:
            d = api_call("/api/gedaechtnis")
        except (urllib.error.URLError, OSError, ValueError):
            return None
        return d if isinstance(d, dict) else None

    def oeffnen(self, abschnitt=None):
        AI = self.AI
        d = self.holen()
        if d is None:
            AI["msg"] = "keine verbindung — gedächtnis nicht geladen"
            return
        alt = AI.get("gedaechtnis") or {}
        idx = next((i for i, (s, _n) in enumerate(ABSCHNITTE) if s == abschnitt),
                   alt.get("abschnitt", 0))
        AI["gedaechtnis"] = {"abschnitt": idx, "daten": d, "scroll": 0,
                             "wahl": alt.get("wahl", 0)}
        AI["liste"] = None
        AI["msg"] = ""

    def neu_laden(self):
        G = self.AI["gedaechtnis"]
        d = self.holen()
        if d is None:
            self.AI["msg"] = "keine verbindung"
            return
        G["daten"] = d

    def schliessen(self):
        self.AI["gedaechtnis"] = None

    def abschnitt(self):
        return ABSCHNITTE[self.AI["gedaechtnis"]["abschnitt"]][0]

    # ── Tasten ─────────────────────────────────────────────────────────
    def taste(self, ch):
        G = self.AI["gedaechtnis"]
        ab = self.abschnitt()
        n_skills = len(G["daten"].get("skills") or [])
        if ch == 27:
            self.schliessen()
        elif ch in (curses.KEY_RIGHT, 9):
            G["abschnitt"], G["scroll"] = (G["abschnitt"] + 1) % len(ABSCHNITTE), 0
        elif ch in (curses.KEY_LEFT, curses.KEY_BTAB):
            G["abschnitt"], G["scroll"] = (G["abschnitt"] - 1) % len(ABSCHNITTE), 0
        elif ord("1") <= ch <= ord("0") + len(ABSCHNITTE):
            G["abschnitt"], G["scroll"] = ch - ord("1"), 0
        elif ab == "skills" and ch in (curses.KEY_UP, curses.KEY_DOWN) and n_skills:
            G["wahl"] = (G["wahl"] + (1 if ch == curses.KEY_DOWN else -1)) % n_skills
        elif ch in (curses.KEY_UP, curses.KEY_DOWN):
            G["scroll"] = max(0, G["scroll"] + (1 if ch == curses.KEY_DOWN else -1))
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            G["scroll"] = max(0, G["scroll"] + (-10 if ch == curses.KEY_PPAGE else 10))
        elif ch == ord("r"):
            self.neu_laden()
        elif ab in KERNAKTEN and ch in (10, 13, curses.KEY_ENTER, ord("e")):
            self.bearbeiten(ab)
        elif ab == "skills" and ch in (10, 13, curses.KEY_ENTER, ord(" ")) and n_skills:
            self.umschalten()

    def umschalten(self):
        G, AI = self.AI["gedaechtnis"], self.AI
        skills = G["daten"].get("skills") or []
        s = skills[max(0, min(G["wahl"], len(skills) - 1))]
        neu = naechster_status(s.get("status"))
        try:
            d = api_call("/api/skills/%s/status" % s["name"], "POST", {"status": neu})
        except urllib.error.HTTPError as e:
            AI["msg"] = _fehlertext(e, "nicht umgeschaltet")
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — nicht umgeschaltet"
            return
        if isinstance(d, dict) and isinstance(d.get("skill"), dict):
            s.update(d["skill"])
        AI["msg"] = "skill „%s“ ist jetzt %s" % (s["name"], STATUS_WORT.get(neu, neu))

    def bearbeiten(self, akte):
        """Kernakte im Editor öffnen, danach zurückschreiben. Die Zwischen-
        datei bleibt liegen, wenn das Speichern scheitert — sonst wäre
        Getipptes weg."""
        AI = self.AI
        cmd = editor_befehl()
        if cmd is None:
            AI["msg"] = "kein editor gefunden (nano fehlt)"
            return
        self.neu_laden()                       # den neuesten Stand bearbeiten
        stand_akte = _akte(AI["gedaechtnis"]["daten"], akte) or {}
        alt = stand_akte.get("text") or ""
        fd, pfad = tempfile.mkstemp(prefix="zentrale-%s-" % akte, suffix=".md")
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
        try:
            api_call("/api/gedaechtnis/%s" % akte, "PUT",
                     {"text": neu, "stand": stand_akte.get("stand")})
        except urllib.error.HTTPError as e:
            AI["msg"] = _fehlertext(e, "nicht gespeichert") + " — dein text liegt in " + pfad
            self.neu_laden()
            return
        except (urllib.error.URLError, OSError, ValueError):
            AI["msg"] = "keine verbindung — dein text liegt in " + pfad
            return
        os.unlink(pfad)
        self.neu_laden()
        AI["msg"] = "%s gespeichert (die alte fassung bleibt als sicherung)" % akte

    # ── Zeichnen ───────────────────────────────────────────────────────
    def tasten(self):
        """Tasten je Abschnitt — Fußleiste und Hinweis im Kasten (2026-10-07)."""
        ab = self.abschnitt()
        if ab in KERNAKTEN:
            mitte = [("↑↓", "scroll"), ("e", "edit in editor")]
        elif ab == "skills":
            mitte = [("↑↓", "select"), ("enter", "on/off")]
        else:
            mitte = [("↑↓", "scroll")]
        return [("←→", "section")] + mitte + [("r", "reload"), ("esc", "close")]

    def fusszeile(self):
        return fussleiste.text(self.tasten())

    def zeichnen(self, by, bx, bh, bw):
        z = self.chat.z
        C, addclip = z.C, z.addclip
        G = self.AI["gedaechtnis"]
        inx, inw = bx + 2, max(6, bw - 4)
        x = inx
        for text, gewaehlt in reiter(G["abschnitt"], inw):
            addclip(by + 1, x, text, max(1, inx + inw - x),
                    (C["bright"] | curses.A_REVERSE) if gewaehlt else C["dim"])
            x += len(text)

        fuss = [self.fusszeile()]
        msg = self.AI.get("msg")
        if msg:
            fuss = [msg] + fuss
        zeilen_fuss = []
        for f in fuss:
            zeilen_fuss += [f[i:i + inw] for i in range(0, len(f), inw)] or [""]
        zeilen_fuss = zeilen_fuss[:max(1, bh - 4)]   # winziger Kasten: Fuß nie über den Rand
        oben, unten = by + 3, by + bh - 2 - len(zeilen_fuss)
        platz = max(1, unten - oben + 1)

        zeilen, ziel = inhalt_zeilen(G["daten"], self.abschnitt(), inw, G["wahl"])
        if self.abschnitt() == "skills":
            # Die Wahl sichtbar halten (Name + Beschreibung).
            if ziel < G["scroll"]:
                G["scroll"] = ziel
            elif ziel + 2 >= G["scroll"] + platz:
                G["scroll"] = ziel + 3 - platz
        G["scroll"] = max(0, min(G["scroll"], max(0, len(zeilen) - platz)))
        # Dieselben Rollen wie der Chat-Verlauf (chat.py, draw_ai).
        stile = {"": C["bright"], "kopf": C["acc"], "liste": C["bright"],
                 "code": C["dim"], "leise": C["faint"],
                 "gewaehlt": C["bright"] | curses.A_BOLD, "aus": C["faint"]}
        for i, (text, art) in enumerate(zeilen[G["scroll"]:G["scroll"] + platz]):
            addclip(oben + i, inx, text, inw, stile.get(art, C["dim"]))
        if G["scroll"] + platz < len(zeilen) and unten >= oben:
            addclip(unten, inx + inw - 1, "↓", 1, C["faint"])
        y = by + bh - 1 - len(zeilen_fuss)
        for i, f in enumerate(zeilen_fuss):
            addclip(y + i, inx, f, inw, C["warn"] if (msg and i == 0) else C["faint"])


def _fehlertext(e, rueckfall):
    """Die Klartext-Meldung aus einer Fehler-Antwort des Backends."""
    try:
        grund = json.loads(e.read().decode("utf-8", "replace")).get("error") or ""
    except Exception:
        grund = ""
    return (grund or rueckfall).lower()
