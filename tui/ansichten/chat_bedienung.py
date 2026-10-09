# tui/ansichten/chat_bedienung.py
#
# Bedienung des Chats nach dem Vorbild von Claude Web (2026-10-07): Fokus
# zwischen Seitenleiste / Verlauf / Eingabe / rechts, Ziele im Verlauf
# (aufklappen, kopieren, wiederholen, bewerten, Dokument öffnen), Strg-Tasten, Maus.
# Ein Mixin für Chat (chat.py), wie chat_gespraeche.py.
#
# Fokuswechsel ist F6 (wie im Browser zwischen den Bereichen einer Seite):
# Tab gehört laut Sasha den Gesprächen („tab für gespräche auf und zu klappen
# find ich still good"), Shift+Tab hieße „Tab rückwärts" und wäre damit
# zweideutig, und die Strg-Buchstaben sind schon Befehle.

import curses
import os
import shutil
import subprocess

from . import maus
from .chat_ablage import TRENNER

# Was Enter auf einem Ziel im Verlauf tut — für die Fußleiste.
WAS = {"schritt": "open/close", "denken": "open/close", "voll": "more/less", "kopieren": "copy",
       "wiederholen": "retry", "dok": "open", "gut": "rate good", "schlecht": "rate bad"}

# Ziele unter einer Antwort: ist eines davon gewählt, bewerten + / − sie
# (bewertung.py, 2026-10-08) — „wenn eine Antwort im Verlauf gewählt ist".
UNTER_ANTWORT = ("kopieren", "wiederholen", "gut", "schlecht")


def zwischenablage(umgebung=None, finden=shutil.which):
    """Das Programm, das hier in die Zwischenablage schreibt, als
    Argumentliste — oder None (kein Bildschirm, nichts installiert)."""
    u = os.environ if umgebung is None else umgebung
    if u.get("WAYLAND_DISPLAY") and finden("wl-copy"):
        return ["wl-copy"]
    if u.get("DISPLAY"):
        if finden("xclip"):
            return ["xclip", "-selection", "clipboard"]
        if finden("xsel"):
            return ["xsel", "--clipboard", "--input"]
    return None


class ChatBedienung:

    # ── Seitenleiste und Fokus ─────────────────────────────────────────
    def _seite_sichtbar(self):
        a = getattr(self, "_letzte", None)
        return bool(a and a.seite)

    def seite_umschalten(self):
        """Tab bei leerer Eingabe: Gespräche auf (mit Fokus) bzw. zu."""
        if self._seite_sichtbar():
            self.seite.zuklappen()
        else:
            self.seite.aufklappen()

    def _bereiche(self):
        a = getattr(self, "_letzte", None)
        if a is None:
            return ["eingabe"]
        raus = []
        if a.seite:
            raus.append("seite")
        if a.mitte:
            raus += ["verlauf", "eingabe"]
        if a.rechts:
            raus.append("rechts")
        return raus or ["eingabe"]

    def fokus_weiter(self):
        """F6: nächster Bereich (Leiste → Verlauf → Eingabe → rechts)."""
        AI = self.AI
        reihe = self._bereiche()
        jetzt = AI.get("fokus") or "eingabe"
        neu = reihe[(reihe.index(jetzt) + 1) % len(reihe)] if jetzt in reihe else reihe[0]
        if neu == "verlauf" and AI.get("vwahl") not in self._ziele:
            AI["vwahl"] = self._ziele[-1] if self._ziele else None
            AI["vwahl_folgen"] = True
        self.fokus_setzen(neu)

    # ── Verlauf ────────────────────────────────────────────────────────
    def _tasten_verlauf(self):
        z = self.AI.get("vwahl")
        liste = [("↑↓", "select")] if len(self._ziele) > 1 else []
        if z in self._ziele:
            liste.append(("enter", WAS.get(z[0], "do")))
            if z[0] in UNTER_ANTWORT:
                liste.append(("+/-", "rate"))
        return liste + [("pgup pgdn", "scroll"), ("esc", "back to reply")]

    def _taste_verlauf(self, ch):
        AI = self.AI
        ziele = self._ziele
        if ch == 27:
            AI["fokus"] = "eingabe"
        elif ch in (curses.KEY_UP, curses.KEY_DOWN) and ziele:
            i = ziele.index(AI["vwahl"]) if AI.get("vwahl") in ziele else len(ziele)
            i = max(0, min(len(ziele) - 1, i + (1 if ch == curses.KEY_DOWN else -1)))
            AI["vwahl"], AI["vwahl_folgen"] = ziele[i], True
        elif ch in (10, 13, curses.KEY_ENTER, ord(" ")) and AI.get("vwahl") in ziele:
            self.ziel_ausloesen(AI["vwahl"])
        elif ch in (curses.KEY_PPAGE, curses.KEY_NPAGE):
            AI["scroll"] = max(0, AI["scroll"] + (5 if ch == curses.KEY_PPAGE else -5))
        elif ch == 4:
            self.denken_umschalten()
        elif ch in (ord("+"), ord("-")) and AI.get("vwahl") in ziele \
                and AI["vwahl"][0] in UNTER_ANTWORT:
            self.bewertung.oeffnen(AI["vwahl"][1], 1 if ch == ord("+") else -1)

    def ziel_ausloesen(self, z):
        """Ein Ziel im Verlauf (Klick oder Enter): auf/zu, kopieren,
        wiederholen, Dokument öffnen."""
        AI = self.AI
        art, i = z
        AI["vwahl"] = z
        if art in ("schritt", "denken", "voll"):
            offen = AI.setdefault("offen", set())
            if art == "denken" and AI.get("denken_offen"):
                AI["denken_offen"] = False      # alles war offen: nur dieses bleibt zu
                offen.discard(z)
            elif z in offen:
                offen.discard(z)
            else:
                offen.add(z)
        elif art == "kopieren" and 0 <= i < len(AI["log"]):
            self.kopieren(AI["log"][i][1])
        elif art == "wiederholen":
            self.wiederholen()
        elif art in ("gut", "schlecht"):
            self.bewertung.oeffnen(i, 1 if art == "gut" else -1)
        elif art == "dok" and 0 <= i < len(AI["log"]):
            self.rechts.dokument_zeigen(str(AI["log"][i][1]).split(TRENNER, 1)[0])

    def kopieren(self, text):
        """Eine Antwort in die Zwischenablage. Gibt es keine (Pi-Kiosk,
        SSH ohne X), liegt der Text in einer Datei und die Statuszeile sagt,
        wo — nie still nichts."""
        AI = self.AI
        cmd = zwischenablage()
        if cmd:
            try:
                subprocess.run(cmd, input=text.encode("utf-8"), timeout=3,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                AI["msg"] = "kopiert (%d zeichen)" % len(text)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        # Nicht nach /tmp: dort könnte jeder Nutzer des Rechners mitlesen, und
        # kopiert werden auch private Antworten. Eigener Cache-Ordner, Datei
        # nur für Sasha lesbar (2026-10-08).
        ordner = os.environ.get("ZENTRALE_KOPIE_DIR") or \
            os.path.join(os.path.expanduser("~"), ".cache", "zentrale")
        pfad = os.path.join(ordner, "kopie.txt")
        try:
            os.makedirs(ordner, exist_ok=True)
            fd = os.open(pfad, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(pfad, 0o600)
        except OSError:
            AI["msg"] = "kopieren geht hier nicht — keine zwischenablage (xclip fehlt)"
            return
        AI["msg"] = "keine zwischenablage hier (xclip fehlt) — der text liegt in " + pfad

    # ── Kopf und Leiste unter der Eingabe ──────────────────────────────
    def menue_gespraech(self):
        """▾ am Titel: was man mit diesem Gespräch tun kann (wie Claude)."""
        def tun(was):
            if was == "rename":
                self.AI["input"] = "/rename " + (self.AI.get("titel") or "")
                self.AI["cur"] = len(self.AI["input"])
                self.AI["fokus"] = "eingabe"
            elif was == "archive":
                self.archivieren_aktuell()
            elif was == "project":
                self.befehl("projekt", "")
            elif was == "new":
                self.neues_gespraech()
        self.AI["wahl"] = {"titel": "this chat", "idx": 0, "aktion": tun,
                           "optionen": [("rename …", "rename"), ("move to project …", "project"),
                                        ("archive", "archive"), ("new chat", "new")]}

    def anhang_vorbereiten(self):
        """„+ attach": /attach in die Eingabe, der Pfad wird getippt."""
        AI = self.AI
        AI["input"], AI["fokus"] = "/attach ", "eingabe"
        AI["cur"] = len(AI["input"])
        AI["msg"] = "pfad tippen, enter hängt die datei an (~ geht)"

    def wahl_nehmen(self, i):
        """Klick auf eine Option der offenen Auswahl."""
        wahl = self.AI.get("wahl")
        if not wahl or not 0 <= i < len(wahl["optionen"]):
            return
        self.AI["wahl"] = None
        (wahl.get("aktion") or self.setzen)(wahl["optionen"][i][1])

    def _taste_strg(self, ch):
        """Strg-Tasten im Eingabefeld. -> True, wenn eine davon."""
        from .chat import STRG
        if ch == STRG["o"]:
            self.rechts.outputs_umschalten()
        elif ch == STRG["p"]:
            self.befehl("modell", "")
        elif ch == STRG["t"]:
            self.befehl("effort", "")
        elif ch == STRG["u"]:
            self.anhang_vorbereiten()
        elif ch == STRG["v"]:               # Zwischenablage (chat_ablage.strg_v)
            self.strg_v()
        elif ch == STRG["n"]:
            self.neues_gespraech()
        else:
            return False
        return True

    # ── Maus ───────────────────────────────────────────────────────────
    def maus_pflegen(self):
        """Hauptschleife, jede Runde: Maus-Meldungen nur, solange der Chat
        offen ist und die Maus gewünscht (maus.py: warum)."""
        an = bool(self.AI.get("active") and self.AI.get("maus"))
        if an == getattr(self, "_maus_an", False):
            return
        try:
            curses.mousemask(maus.MASKE if an else 0)
        except curses.error:
            pass
        self._maus_an = an

    def maus_umschalten(self):
        AI = self.AI
        AI["maus"] = not AI.get("maus")
        AI["msg"] = ("maus an — shift + ziehen markiert weiter" if AI["maus"]
                     else "maus aus — das terminal markiert wieder ohne shift")

    def maus_ereignis(self):
        AI = self.AI
        try:
            _id, x, y, _z, bstate = curses.getmouse()
        except curses.error:
            return
        art = maus.deuten(bstate)
        if art in ("rad_hoch", "rad_runter"):
            schritt = 3 if art == "rad_hoch" else -3
            was = maus.rad_treffer(self.raeder, y, x)
            if was == "verlauf":
                AI["scroll"] = max(0, AI["scroll"] + schritt)
            elif was == "dokument" and self.rechts.dokument_offen():
                L = AI["ablage"]["lesen"]
                L["scroll"] = max(0, L["scroll"] - schritt)
            elif was == "seite" and AI.get("liste"):
                n = len(self.liste.sichtbar())
                if n:
                    AI["liste"]["idx"] = max(0, min(n - 1, AI["liste"]["idx"] - schritt // 3))
            return
        if art != "klick" or AI.get("perm"):
            return
        aktion = maus.treffer(self.klicks, y, x)
        if aktion is not None:
            aktion()
