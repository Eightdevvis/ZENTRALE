# tui/ansichten/chat_ablage.py
#
# Was der Chat mit der ABLAGE tut (Claude-Web-Plan Phase 5, 2026-10-07):
# Anhänge (`/anhang <pfad>`), die Zeile „▤ Titel" für ein Dokument, das die
# KI gerade abgelegt hat, und Enter darauf. Ein Mixin für Chat (chat.py),
# eigene Datei wie chat_gespraeche.py — chat.py ruft nur hier herein.
#
# Anhänge: die TUI liest die Datei auf IHREM Rechner (unterwegs spricht der
# Laptop über den Tunnel mit dem PC-Backend; dort gäbe es den Pfad nicht)
# und schickt die Bytes an POST /api/anhang. Das Backend prüft Sperrliste,
# Größe und Art (core/anhang.py) und legt eine Kopie in die Ablage; hier
# bleibt nur die Ablage-id, die mit der nächsten Nachricht mitgeht.

import base64
import json
import os
import threading
import time
import urllib.error

from . import zwischenablage
from .basis import api_call

ANHANG_MAX_BYTES = 10 * 1024 * 1024        # wie core/anhang.DATEI_MAX_BYTES
BILD_MAX_BYTES = 5 * 1024 * 1024           # wie core/ablage.BILD_MAX_BYTES
TRENNER = "\t"                             # Log-Zeile „ablage": id⇥titel


def ablage_eintrag(dok):
    """Ein Dokument (Event oder Verlauf) als Verlaufs-Zeile. -> (rolle, text)"""
    return ("ablage", "%s%s%s" % (dok.get("id") or "", TRENNER,
                                  str(dok.get("titel") or "dokument").replace("\n", " ")))


def anhang_eintrag(a):
    return ("anhang", "anhang: %s" % str(a.get("titel") or "datei").replace("\n", " "))


def kaertchen_text(a):
    """Was ein wartender Anhang im Eingabekasten heißt: das Kärtchen (Bild
    aus der Zwischenablage, mit Größe) oder der Titel."""
    return str(a.get("kaertchen") or a.get("titel") or "datei").replace("\n", " ")


def ablage_anzeige(text, letzte):
    """Was eine „ablage"-Zeile im Verlauf zeigt. Nur die LETZTE öffnet Enter
    (die Eingabe ist ja leer); ältere findet man in /ablage."""
    titel = text.split(TRENNER, 1)[-1]
    return titel + (" — enter öffnet" if letzte else " — in /files")


def letztes_dokument(log):
    """id des neuesten Dokuments im Verlauf, oder None."""
    for rolle, text in reversed(log):
        if rolle == "ablage":
            return text.split(TRENNER, 1)[0] or None
    return None


def pfad_aufloesen(arg):
    """'~/x.pdf' → absoluter, aufgelöster Pfad (Verweise folgen) — so prüft
    das Backend die Sperrliste am echten Ort."""
    roh = (arg or "").strip().strip('"').strip("'")
    if not roh:
        return ""
    return os.path.realpath(os.path.expanduser(roh))


class AblageSteuerung:

    def anhang_dazu(self, arg):
        """/anhang <pfad>: Datei lesen, ans Backend geben, für die nächste
        Nachricht vormerken. Im Hintergrund (ein PDF braucht Sekunden)."""
        AI = self.AI
        pfad = pfad_aufloesen(arg)
        if not pfad:
            n = len(AI.get("anhaenge") or [])
            AI["msg"] = ("/attach <pfad> hängt eine datei an (text, code, pdf, bild)"
                         if not n else "%d anhang/anhänge warten auf die nächste nachricht" % n)
            return
        if not os.path.isfile(pfad):
            AI["msg"] = "die datei gibt es nicht: %s" % arg.strip()
            return
        try:
            groesse = os.path.getsize(pfad)
        except OSError:
            groesse = 0
        if groesse > ANHANG_MAX_BYTES:
            AI["msg"] = "zu groß — höchstens %d mb" % (ANHANG_MAX_BYTES // 1024 // 1024)
            return
        AI["msg"] = "hänge an …"
        threading.Thread(target=self._anhang_senden, args=(pfad,), daemon=True).start()

    def _anhang_senden(self, pfad):
        AI, AI_LOCK = self.AI, self.AI_LOCK
        try:
            with open(pfad, "rb") as f:
                daten = f.read(ANHANG_MAX_BYTES + 1)
        except OSError as e:
            with AI_LOCK:
                AI["msg"] = "lesen ging nicht: %s" % (e.strerror or e)
            return
        self._anhang_schicken(pfad, daten)

    def _anhang_schicken(self, pfad, daten, kaertchen=None):
        """Bytes an POST /api/anhang, die id vormerken. kaertchen: was im
        Eingabekasten steht statt des Titels (Bild aus der Zwischenablage)."""
        AI, AI_LOCK = self.AI, self.AI_LOCK
        body = {"pfad": pfad, "daten": base64.b64encode(daten).decode("ascii")}
        if AI.get("gid"):
            body["gespraech"] = AI["gid"]
        try:
            r = api_call("/api/anhang", "POST", body, timeout=60)
        except urllib.error.HTTPError as e:
            grund = ""
            try:
                grund = json.loads(e.read().decode("utf-8", "replace")).get("error") or ""
            except Exception:
                pass
            with AI_LOCK:
                AI["msg"] = "nicht angehängt: " + (grund or "fehler %s" % e.code)
            return
        except (urllib.error.URLError, OSError, ValueError):
            with AI_LOCK:
                AI["msg"] = "keine verbindung — nicht angehängt"
            return
        if not isinstance(r, dict) or not r.get("id"):
            return
        eintrag = {"id": r["id"], "titel": r.get("titel"), "art": r.get("art")}
        if kaertchen:
            eintrag["kaertchen"] = kaertchen
        with AI_LOCK:
            AI.setdefault("anhaenge", []).append(eintrag)
            AI["msg"] = "angehängt: %s — geht mit der nächsten nachricht%s" % (
                kaertchen or r.get("titel"), (" · " + r["hinweis"]) if r.get("hinweis") else "")

    # ── Zwischenablage (2026-10-08) ─────────────────────────────────────
    # Ein Terminal fügt nur Text ein; ein Bild in der Zwischenablage holt
    # /paste selbst (zwischenablage.py: warum).

    def einfuegen_aus_ablage(self):
        """/paste: ein Bild wird Anhang der nächsten Nachricht, Text kommt
        in die Eingabe (wie Einfügen)."""
        AI = self.AI
        z = zwischenablage.lesen()
        if z.art == "nein":
            AI["msg"] = z.grund
        elif z.art == "leer":
            AI["msg"] = "die zwischenablage ist leer"
        elif z.art == "text":
            self._einfuegen(z.daten)
            AI["msg"] = "text aus der zwischenablage eingefügt"
        elif len(z.daten) > BILD_MAX_BYTES:
            AI["msg"] = "bild zu groß (%s) — höchstens %d mb" % (
                zwischenablage.groesse_text(len(z.daten)), BILD_MAX_BYTES // 1024 // 1024)
        else:
            # Ein Name mit Uhrzeit: in /files sind zwei Bilder auseinanderzuhalten.
            # Kein echter Pfad — das Backend öffnet ihn nie, prüft nur den Namen.
            name = time.strftime("zwischenablage-%Y-%m-%d-%H%M%S") + zwischenablage.ENDUNG[z.mime]
            kaertchen = "bild aus der zwischenablage · " + zwischenablage.groesse_text(len(z.daten))
            AI["msg"] = "hänge an …"
            threading.Thread(target=self._anhang_schicken, args=(name, z.daten, kaertchen),
                             daemon=True).start()

    def strg_v(self):
        """Strg+V im Eingabefeld (raw-Modus: das Terminal reicht es als
        Zeichen 22 durch; eingefügt wird dort mit Strg+Shift+V). Text: wie
        Einfügen. Bild: nur der Hinweis — angehängt wird bewusst mit /paste."""
        AI = self.AI
        z = zwischenablage.lesen(bild_holen=False)
        if z.art == "bild":
            AI["msg"] = "bild in der zwischenablage — /paste hängt es an"
        elif z.art == "text":
            self._einfuegen(z.daten)
        elif z.art == "leer":
            AI["msg"] = "die zwischenablage ist leer"
        else:
            AI["msg"] = z.grund

    def anhaenge_nehmen(self):
        """Die vorgemerkten Anhänge für die nächste Nachricht (und leeren).
        Unter AI_LOCK aufrufen."""
        raus = list(self.AI.get("anhaenge") or [])
        self.AI["anhaenge"] = []
        return raus

    def anhaenge_text(self):
        """Fuß-Hinweis, solange Anhänge warten — oder ''."""
        a = self.AI.get("anhaenge") or []
        if not a:
            return ""
        return "▤ " + ", ".join(kaertchen_text(x) for x in a) + " · geht mit der nächsten nachricht"

    def ablage_event(self, dok):
        """SSE 'ablage': ein Dokument ist entstanden. Unter AI_LOCK."""
        if isinstance(dok, dict) and dok.get("id"):
            self.AI["log"].append(ablage_eintrag(dok))

    def dokument_oeffnen_letztes(self):
        """Enter bei leerer Eingabe: das neueste Dokument im Verlauf lesen.
        -> True, wenn es eins gab."""
        doc_id = letztes_dokument(self.AI["log"])
        if not doc_id:
            return False
        self.ablageliste.lesen(doc_id, direkt=True)
        return True
