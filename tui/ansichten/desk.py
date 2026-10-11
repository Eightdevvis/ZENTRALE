# tui/ansichten/desk.py
#
# Desk View (Taste `d` im Rad, 2026-10-09). Sasha: „ich klappe z.B.
# ‚Elektronik' auf und habe einen infinity canvas vor mir." Erst eine
# Auswahl der Desks (+ neuer Desk), dann die Fläche. Die Fläche selbst ist
# der Baustein tui/bausteine/canvas.py — er weiß nichts vom Desk. Diese
# Ansicht ist die App drumherum: Desks laden und speichern (HTTP
# /api/desk, core/desk.py), das Bearbeiten-Modal mittig zeigen, die
# Tastentabelle (Canvas und Modale bringen ihre als Bausteine mit; Tasten
# zeigt nur die Leiste ganz unten). So kann Desk View später als eigene
# Hub-App ausziehen, ohne den Canvas mitzunehmen, und andere Apps nehmen
# den Canvas ohne den Desk.
# Doku: memory/hub/desk_view.md.
#
# Kacheln (2026-10-10): ihr Inhalt kommt im Hintergrund über den Hub
# (desk_kacheln.py, `POST /api/kachel`), gezeichnet wird aus dem Puffer.
# `o` auf einer Kachel fragt `POST /api/kachel/aktion`; die App antwortet
# mit einer Adresse, und `zeigen(adresse)` (der Adress-Router aus
# sprung.py, von zentrale_tui.py hereingegeben) öffnet die passende
# Ansicht. Im Wähler hinter `+` steht neben Zettel und Bild alles aus dem
# Katalog des Hubs (`GET /api/kacheln`, desk_neu.py) — mit einem Dialog,
# den feld_dialog.py aus dem JSON Schema des Eintrags baut (`parameter`,
# 2026-10-10). Esc in der Ansicht, die `o` geöffnet hat, führt zurück auf
# diesen Desk an dieselbe Stelle (`zurueck`, der Router merkt es sich).

import curses
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import basis, bild_betrachter, desk_kacheln, desk_neu, tasten
from .basis import api_call
from .tasten import Tasten

try:
    from tui.bausteine import canvas as cv
    from tui.bausteine import canvas_bild
    from tui.bausteine.canvas_arten import TextModal, standard_arten
    from tui.bausteine.feld_dialog import FeldDialog
    from tui.bausteine.textfeld import TASTEN_ZEILE, Textfeld
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine import canvas as cv
    from bausteine import canvas_bild
    from bausteine.canvas_arten import TextModal, standard_arten
    from bausteine.feld_dialog import FeldDialog
    from bausteine.textfeld import TASTEN_ZEILE, Textfeld

# Rolle des Canvas → Farbrolle der TUI (ansichten/farben.py).
FARBEN = {"raster": "faint", "schnur": "dim", "schnur_vor": "acc", "rahmen": "dim",
          "fokus": "acc", "griff": "warn", "groesse": "warn", "ziel": "acc", "text": "ink", "leise": "faint",
          "notiz_titel": "amberhi", "bild": "ink", "bild_titel": "bright"}
FETT = {"fokus", "griff", "groesse", "ziel", "notiz_titel", "bild_titel"}

# Die Modale, die der Desk zeigt, und wie ihre Ansichten in der
# Tastentabelle heißen („text:schreiben" …).
MODALE = (("text", TextModal), ("titel", canvas_bild.TitelModal), ("dialog", FeldDialog))


def _pfad(name):
    return "/api/desk/" + urllib.parse.quote(name, safe="")


class Desk:
    """Desk View: Auswahl der Desks, dann die Fläche. Zustand in self.DESK
    (auch z.DESK, damit fenster.py den Fokus sieht)."""

    def __init__(self, z):
        self.z = z
        self.arten = standard_arten(cv.Arten())
        # zeigen(adresse) -> bool: die Ansicht zu einer Adresse öffnen (o auf
        # einer Kachel). Kommt von außen (zentrale_tui.py, sprung.Router),
        # damit diese Ansicht keine andere kennen muss.
        self.zeigen = None
        # Wie im Hintergrund geholt wird; Tests setzen „gleich ausführen".
        self.starten = lambda f: threading.Thread(target=f, daemon=True).start()
        self.DESK = z.DESK = {
            "active": False,
            "ebene": "wahl",            # wahl | canvas
            "desks": [], "sel": 0,
            "name": None,               # Textfeld, solange ein neuer Name getippt wird
            "desk": None, "stand": None,
            "canvas": None,             # cv.Canvas des offenen Desks
            "modal": None, "modal_id": None,
            "modal_neu": None,          # Wahl hinter +, deren Dialog gerade offen ist
            "zentrieren": False,
            "msg": "",
            # Wähler hinter `+` (2026-10-10): erst die Art, beim Bild dann
            # die Datei (Input/ oder Pfad tippen).
            "art_wahl": None,           # {"arten": [...], "sel": i}
            "bild_wahl": None,          # {"quellen": [...], "sel": i, "pfad": Textfeld|None}
            # Direkt geöffnet (Elektronik im Rad, eigene Apps; 2026-10-10):
            # Esc auf der Fläche schließt dann ganz statt zur Desk-Auswahl.
            "direkt": False,
        }

    # ── Daten ─────────────────────────────────────────────────────────
    def oeffnen(self):
        D = self.DESK
        D.update(active=True, ebene="wahl", name=None, modal=None, canvas=None, msg="",
                 art_wahl=None, bild_wahl=None, modal_neu=None, direkt=False)
        self._liste_laden()

    def direkt(self, name):
        """Einen Desk gleich auf der Fläche öffnen, ohne Auswahl; fehlt er,
        wird er angelegt (2026-10-10, Sasha: Elektronik im Rad öffnet „seinen"
        Desk; eine selbst gebaute App ihren). Esc führt dorthin zurück, woher
        man kam."""
        D = self.DESK
        D.update(active=True, ebene="wahl", name=None, modal=None, canvas=None, msg="",
                 art_wahl=None, bild_wahl=None, modal_neu=None, direkt=True, desks=[])
        self.desk_oeffnen(name)
        if D["ebene"] != "canvas":
            zuerst = D["msg"]
            self._anlegen(name)
            if D["ebene"] != "canvas" and "gibt es schon" in D["msg"]:
                D["msg"] = zuerst            # kaputt statt fehlend: der erste Grund zählt

    def _liste_laden(self):
        D = self.DESK
        try:
            D["desks"] = (api_call("/api/desk") or {}).get("desks") or []
        except Exception:
            D["desks"] = []
            D["msg"] = "backend nicht erreichbar"
        D["sel"] = max(0, min(D["sel"], len(D["desks"])))   # letzte Zeile: „neuer desk"

    def _fehlertext(self, e):
        if isinstance(e, urllib.error.HTTPError):
            try:
                body = json.loads(e.read().decode("utf-8"))
                return body.get("error") or body.get("text") or body.get("fehler") or str(e.code)
            except Exception:
                return "fehler %s" % e.code
        return "backend nicht erreichbar"

    def desk_oeffnen(self, name):
        D = self.DESK
        try:
            d = api_call(_pfad(name))
        except Exception as e:
            D["msg"] = "„%s\" geht nicht auf: %s" % (name, self._fehlertext(e))
            return
        if not isinstance(d, dict):
            D["msg"] = "„%s\" geht nicht auf" % name
            return
        # Ohne Fabrik meldet der Canvas bei + „neu_waehlen": Zettel oder Bild.
        c = cv.Canvas(self.arten, list(d.get("elemente") or []), list(d.get("verbindungen") or []))
        # Weich gleiten + schneller beim Gedrückthalten (2026-10-10).
        c.weich, c.uhr = True, time.monotonic
        c.vor_groesse = self._groesse_vorbereiten
        D.update(ebene="canvas", desk=d.get("name", name), stand=d.get("stand"), msg="",
                 zentrieren=True, art_wahl=None, bild_wahl=None, canvas=c)

    def _anlegen(self, name):
        D = self.DESK
        try:
            d = api_call("/api/desk", "POST", {"name": name})
        except Exception as e:
            D["msg"] = "desk nicht angelegt: " + self._fehlertext(e)
            return
        self.desk_oeffnen((d or {}).get("name") or name)

    def speichern(self):
        """Den ganzen Desk schicken. Wurde er woanders geändert (409), wird
        neu geladen und das gesagt; geht das Backend nicht, bleibt alles hier
        liegen und das nächste Speichern schickt es mit."""
        D = self.DESK
        c = D["canvas"]
        # Felder mit „_" legt nur die Ansicht zwischen (Vorschau, Blätterlage).
        # Eine Kachel nimmt ihren Klartext als Rückfall für Obsidian mit.
        elemente = [desk_kacheln.fuer_datei(e) for e in c.elemente]
        body = {"elemente": elemente, "verbindungen": c.verbindungen_mit_seiten(),
                "stand": D["stand"]}
        try:
            d = api_call(_pfad(D["desk"]), "PUT", body)
        except urllib.error.HTTPError as e:
            if e.code == 409:
                self.desk_oeffnen(D["desk"])
                D["msg"] = "desk wurde woanders geändert — neu geladen, letzte änderung fehlt"
            else:
                D["msg"] = "nicht gespeichert: " + self._fehlertext(e)
            return
        except Exception:
            D["msg"] = "nicht gespeichert — backend nicht erreichbar"
            return
        if isinstance(d, dict) and d.get("stand"):
            D["stand"] = d["stand"]
        D["msg"] = ""

    def bewegt_sich(self):
        """Gleitet der Ausschnitt gerade? Dann tickt zentrale_tui.py schnell
        (33 ms), sonst ruhig — kein Dauerlauf, wenn nichts passiert."""
        D = self.DESK
        c = D["canvas"]
        return bool(D["active"] and D["ebene"] == "canvas" and c is not None
                    and c.bewegt_sich())

    # ── Tasten: EINE Tabelle (tasten.py, 2026-10-11) ──────────────────
    # Eigene Ansichten: wahl (Desks), name (neuer Desk), neu (Wähler hinter
    # +), bild (Bild aus Input), pfad (Pfad tippen). Die Fläche und die
    # Modale bringen ihre Tabelle als Bausteine mit (Tasten.zusammen):
    # canvas:<zustand|art>, text:…, titel:…, dialog:…. Ohne Text =
    # verarbeitet, aber nicht gezeigt.
    TASTEN = Tasten.zusammen({
        "wahl": [("↑↓", "waehlen", "select"), ("enter", "oeffnen", "open"),
                 ("n", "neuer_desk", "new desk"), ("esc", "schliessen", "close")],
        "name": [("type", "name_tippen", "type name"), ("enter", "name_anlegen", "create"),
                 ("esc", "name_abbrechen", "cancel"), (TASTEN_ZEILE, "name_feld")],
        "neu": [("↑↓", "art_waehlen", "select"), ("enter/+", "art_nehmen", "take"),
                ("esc", "art_abbrechen", "cancel")],
        "bild": [("↑↓", "quelle_waehlen", "select"), ("enter", "quelle_nehmen", "take"),
                 ("esc", "bild_abbrechen", "cancel")],
        "pfad": [("type", "pfad_tippen", "type path"), ("enter", "pfad_nehmen", "take"),
                 ("esc", "pfad_zurueck", "back"), (TASTEN_ZEILE, "pfad_feld")],
    }, dict({"canvas": (Tasten(cv.tabelle_mit(standard_arten(cv.Arten()))),
                        lambda d: d.DESK["canvas"] or cv.Canvas)},
            # Ist das Teil nicht offen, steht seine Klasse da (die Methoden
            # gibt es trotzdem; gedrückt wird dort ohnehin nichts).
            **{name: (Tasten(klasse.TASTEN),
                      lambda d, k=klasse: d.DESK["modal"] if isinstance(d.DESK["modal"], k) else k)
               for name, klasse in MODALE}))

    def ansicht(self):
        """Welche Ansicht der Tabelle gerade offen ist."""
        D = self.DESK
        if D["modal"] is not None:
            name = next(n for n, k in MODALE if isinstance(D["modal"], k))
            return name + ":" + D["modal"].ansicht()
        if D["bild_wahl"] is not None:
            return "bild" if D["bild_wahl"]["pfad"] is None else "pfad"
        if D["art_wahl"] is not None:
            return "neu"
        if D["name"] is not None:
            return "name"
        if D["ebene"] == "wahl":
            return "wahl"
        return "canvas:" + D["canvas"].ansicht()

    def _textfeld(self):
        """Das Textfeld, in das gerade getippt wird (oder None)."""
        D = self.DESK
        if D["modal"] is not None:
            feld = getattr(D["modal"], "eingabe", None)
            return feld if isinstance(feld, Textfeld) else None
        if D["bild_wahl"] is not None:
            return D["bild_wahl"]["pfad"]
        return D["name"]

    def taste(self, ch):
        D = self.DESK
        if ch == -1:
            return None
        ansicht = self.ansicht()
        # Umlaute kommen als UTF-8-Bytes; die Tabelle liest nur ASCII als
        # Zeichen — das Textfeld setzt sie selbst zusammen.
        if 0x80 <= ch <= 0xFF and self.TASTEN.freitext(ansicht):
            feld = self._textfeld()
            if feld is not None:
                feld.taste(ch)
            return None
        # Alt+… ist nie „abbrechen" (wie bisher): auch wo die Tabelle keine
        # Alt-Taste hat (dort horcht tasten.py nicht nach), erst kurz auf
        # eine Folge horchen — sonst schlösse Alt+x beim Tippen das Modal.
        if ch == 27 and self.TASTEN.nimmt(ansicht, "alt+up") is None \
                and tasten.name_von(27, self.z.stdscr, alt=True) != "esc":
            return None
        auf_flaeche = ansicht.startswith("canvas:")
        if auf_flaeche and D["msg"] and D["canvas"].modus != "frage":
            D["msg"] = ""                    # eine Meldung gilt bis zur nächsten Taste
        erg = self.TASTEN.verteilen(self, ansicht, ch)
        if auf_flaeche:
            self._canvas_ergebnis(erg)
        elif D["modal"] is not None and ansicht.split(":")[0] in dict(MODALE):
            self._modal_ergebnis(erg)
        return None

    # ── wahl: die Desks ──
    def aktion_waehlen(self, taste):
        D = self.DESK
        D["sel"] = max(0, D["sel"] - 1) if taste == "up" else min(len(D["desks"]), D["sel"] + 1)

    def aktion_oeffnen(self, _taste):
        D = self.DESK
        if D["sel"] < len(D["desks"]):
            self.desk_oeffnen(D["desks"][D["sel"]]["name"])
        else:                                # letzte Zeile: „+ neuer desk"
            D["name"] = Textfeld("")

    def aktion_neuer_desk(self, _taste):
        self.DESK["name"] = Textfeld("")

    def aktion_schliessen(self, _taste):
        self.DESK["active"] = False

    # ── name: neuen Desk benennen ──
    def aktion_name_tippen(self, zeichen):
        self.DESK["name"].taste(ord(zeichen))

    def aktion_name_feld(self, taste):
        self.DESK["name"].taste_name(taste)

    def aktion_name_anlegen(self, _taste):
        D = self.DESK
        name = D["name"].text.strip()
        D["name"] = None
        if name:
            self._anlegen(name)

    def aktion_name_abbrechen(self, _taste):
        self.DESK["name"] = None

    # ── Fläche: was der Canvas meldet ──
    def _canvas_ergebnis(self, erg):
        D = self.DESK
        if not isinstance(erg, cv.Ergebnis):
            return
        if erg.art == "zu":
            D.update(ebene="wahl", canvas=None, desk=None, msg="")
            if D["direkt"]:
                D["active"] = False
            else:
                self._liste_laden()
        elif erg.art == "bearbeiten":
            D["modal"] = self.arten.holen(erg.element.get("art")).modal(erg.element)
            D["modal_id"] = erg.element["id"]
        elif erg.art == "geaendert":
            self.speichern()
        elif erg.art == "neu_waehlen":
            D["art_wahl"] = {"arten": self.arten.anlegbar() + self._katalog(), "sel": 0}
        elif erg.art == "aktion":
            was = erg.grund[0] if isinstance(erg.grund, tuple) and erg.grund else None
            if was == "bild_oeffnen":
                self.bild_oeffnen(erg.grund[1])
            elif was == "kachel_oeffnen":
                self.kachel_oeffnen(erg.grund[1])

    def _groesse_vorbereiten(self, fokus):
        """r auf einer Kachel (Haken vor_groesse des Canvas): erst ihre
        Grenzen aus dem Katalog des Hubs holen (min, max — die App bestimmt,
        wie klein sie lesbar ist). Kurz und auf Tastendruck wie `+`. → False,
        wenn es nicht geht (dann bleibt die Größe, und die Statuszeile sagt
        warum)."""
        D = self.DESK
        if not desk_kacheln.ist_kachel(fokus):
            return True
        try:
            g = desk_kacheln.grenzen(fokus, api_call("/api/kacheln"))
        except Exception as e:
            D["msg"] = "größe geht gerade nicht: " + self._fehlertext(e)
            return False
        if g is None:
            D["msg"] = "größe geht nicht: diese kachel kennt der hub nicht"
            return False
        fokus["_grenzen"] = g
        return True

    # ── + : Art wählen, Bild wählen (2026-10-10) ──────────────────────
    def _katalog(self):
        """Was der Hub als Kachel kennt → Wahlen für `+`. Jedes Mal frisch
        (auf Tastendruck, kurz): eine neue App steht so gleich im Wähler.
        Geht das Backend nicht, bleiben Zettel und Bild."""
        try:
            return desk_neu.wahlen(api_call("/api/kacheln"))
        except Exception as e:
            self.DESK["msg"] = "kacheln nicht lesbar: " + self._fehlertext(e)
            return []

    def _kachel_anlegen(self, wahl, werte):
        """Kachel aus Katalog-Wahl + Dialog-Werten hinlegen. Erst den Hub
        fragen (0×0 Zellen: nichts wird gezeichnet): er prüft die Werte mit
        denselben Regeln und sagt die Größe für GENAU diesen Bezug. → None
        oder der Grund, warum nicht (der Dialog bleibt dann offen)."""
        D = self.DESK
        adresse = wahl.adresse(werte.get("werte") or {})
        try:
            a = api_call("/api/kachel", "POST", {"adresse": adresse, "w": 0, "h": 0}) or {}
        except Exception as e:
            return self._fehlertext(e)
        innen = a.get("bevorzugt") if isinstance(a.get("bevorzugt"), dict) else None
        D["canvas"].neu_ablegen(wahl.neu(cv.neue_id(), 0, 0, werte, innen))
        return None

    # ── neu: Wähler hinter + ──
    def aktion_art_waehlen(self, taste):
        w = self.DESK["art_wahl"]
        w["sel"] = max(0, w["sel"] - 1) if taste == "up" else min(len(w["arten"]) - 1, w["sel"] + 1)

    def aktion_art_nehmen(self, _taste):
        D = self.DESK
        w = D["art_wahl"]
        art = w["arten"][w["sel"]] if w["arten"] else None
        D["art_wahl"] = None
        if art is None:
            return
        if art.name == "bild":
            self._bild_wahl_oeffnen()
        elif isinstance(art, desk_neu.KatalogWahl):
            # Erst fragen (Schema aus dem Katalog), dann hinlegen; ohne
            # Felder gleich.
            dialog = art.neu_dialog()
            if dialog.felder:
                D["modal"], D["modal_neu"], D["modal_id"] = dialog, art, None
            else:
                D["msg"] = self._kachel_anlegen(art, {}) or ""
        else:
            D["canvas"].neu_ablegen(art.neu(cv.neue_id(), 0, 0))

    def aktion_art_abbrechen(self, _taste):
        self.DESK["art_wahl"] = None

    def _bild_wahl_oeffnen(self):
        D = self.DESK
        try:
            quellen = (api_call("/api/desk-bild/quellen") or {}).get("quellen") or []
        except Exception as e:
            quellen = []
            D["msg"] = "bilder nicht lesbar: " + self._fehlertext(e)
        D["bild_wahl"] = {"quellen": quellen, "sel": 0, "pfad": None}

    # ── bild: Bild aus Input, pfad: Pfad tippen ──
    def aktion_quelle_waehlen(self, taste):
        w = self.DESK["bild_wahl"]
        n = len(w["quellen"])                       # letzte Zeile: Pfad tippen
        w["sel"] = max(0, w["sel"] - 1) if taste == "up" else min(n, w["sel"] + 1)

    def aktion_quelle_nehmen(self, _taste):
        w = self.DESK["bild_wahl"]
        if w["sel"] < len(w["quellen"]):
            self._bild_hinlegen(w["quellen"][w["sel"]]["name"])
        else:
            w["pfad"] = Textfeld("")

    def aktion_bild_abbrechen(self, _taste):
        self.DESK["bild_wahl"] = None

    def aktion_pfad_tippen(self, zeichen):
        self.DESK["bild_wahl"]["pfad"].taste(ord(zeichen))

    def aktion_pfad_feld(self, taste):
        self.DESK["bild_wahl"]["pfad"].taste_name(taste)

    def aktion_pfad_nehmen(self, _taste):
        w = self.DESK["bild_wahl"]
        text = w["pfad"].text.strip()
        if text:
            self._bild_hinlegen(text)
        else:
            w["pfad"] = None

    def aktion_pfad_zurueck(self, _taste):
        self.DESK["bild_wahl"]["pfad"] = None

    def _bild_hinlegen(self, quelle):
        """Bild in den Desk-Ordner kopieren lassen, dann als neues Element
        in die Hand (enter legt ab und speichert)."""
        D = self.DESK
        try:
            info = api_call("/api/desk-bild", "POST", {"quelle": quelle}, timeout=15) or {}
        except Exception as e:
            D["msg"] = "bild nicht übernommen: " + self._fehlertext(e)
            D["bild_wahl"] = None
            return
        D["bild_wahl"] = None
        bild = self.arten.holen("bild")
        D["canvas"].neu_ablegen(bild.neu(cv.neue_id(), 0, 0, info.get("datei", ""),
                                         int(info.get("w") or 34), int(info.get("h") or 12)))
        D["msg"] = ""

    # ── Bilder: Vorschau holen, öffnen ────────────────────────────────
    def _invert(self):
        """Auf hellem Grund (Tag) ist dicht = dunkel: Rampe umdrehen."""
        bg = self.z.C.get("pix_bg")
        return bool(bg) and sum(bg) / 3 > 128

    def vorschauen_holen(self, c):
        """Für jedes sichtbare Bild ohne passende Vorschau eine holen und am
        Element zwischenlegen (der Baustein fragt nie das Backend). Das
        Backend merkt sich fertige Vorschauen; gezeichnet wird von hier."""
        invert = self._invert()
        # Während der Größe-Änderung nicht je Pfeil neu holen (das Holen
        # hier wartet auf das Backend) — nach enter/esc gilt die neue Größe.
        in_arbeit = c.groesse["id"] if c.groesse else None
        for e in c.elemente:
            if e.get("art") != "bild" or e.get("id") == in_arbeit:
                continue
            if e["x"] + e["w"] <= c.vx or e["x"] >= c.vx + c.vw \
                    or e["y"] + e["h"] <= c.vy or e["y"] >= c.vy + c.vh:
                continue
            sp, ze = canvas_bild.vorschau_groesse(e)
            fuer = (e.get("datei"), sp, ze, e.get("modus") or "mono", invert)
            if e.get("_vorschau_fuer") == fuer:
                continue
            e["_vorschau_fuer"] = fuer
            try:
                e["_vorschau"] = api_call("/api/desk-bild/vorschau", "POST",
                                          {"datei": fuer[0], "w": sp, "h": ze,
                                           "modus": fuer[3], "invert": invert}, timeout=10)
            except Exception as ex:
                e["_vorschau"] = {"status": "fehler", "text": "keine vorschau: " + self._fehlertext(ex)}

    def bild_oeffnen(self, datei):
        """Im Bildbetrachter DIESES Rechners öffnen. Liegt das Bild hier nicht
        (TUI auf einem anderen Rechner als das Backend), erst holen."""
        D = self.DESK
        try:
            info = api_call("/api/desk-bild/oeffnen", "POST", {"datei": datei}) or {}
        except Exception as e:
            D["msg"] = "bild geht nicht auf: " + self._fehlertext(e)
            return
        pfad = info.get("pfad") or ""
        if not (info.get("da") and os.path.isfile(pfad)):
            if not info.get("da"):
                D["msg"] = "bild fehlt: " + str(datei)
                return
            try:
                pfad = self._bild_holen(datei)
            except Exception as e:
                D["msg"] = "bild nicht geholt: " + self._fehlertext(e)
                return
        try:
            prog = bild_betrachter.oeffnen([pfad], info.get("betrachter") or "system")
        except OSError as e:
            D["msg"] = str(e)
            return
        D["msg"] = "geöffnet mit " + prog

    @staticmethod
    def _bild_holen(datei):
        url = basis.BASE_URL + "/api/desk-bild/datei?datei=" + urllib.parse.quote(datei)
        ziel = os.path.join(bild_betrachter.zwischenordner(), os.path.basename(datei))
        with urllib.request.urlopen(url, timeout=30) as r, open(ziel, "wb") as f:
            f.write(r.read())
        return ziel

    def kachel_oeffnen(self, el):
        """o auf einer Kachel: den Hub fragen, WAS aufgehen soll (die App
        antwortet mit einer Adresse), dann den Router die Ansicht öffnen
        lassen. Kurz und auf Tastendruck — wie Speichern synchron; das Holen
        der Inhalte bleibt im Hintergrund."""
        D = self.DESK
        try:
            a = api_call("/api/kachel/aktion", "POST",
                         dict(desk_kacheln.verweis(el), aktion="oeffnen"))
        except Exception as e:
            D["msg"] = "öffnen geht nicht: " + self._fehlertext(e)
            return
        adresse = ((a or {}).get("zeige") or {}).get("adresse") or "?"
        if not (self.zeigen and self.zeigen(adresse, zurueck=self.zurueck)):
            D["msg"] = "„%s“ kann ich von hier nicht öffnen" % adresse

    def zurueck(self):
        """Die mit `o` geöffnete Ansicht ist zu (2026-10-10): wieder auf
        diesen Desk, an dieselbe Stelle. Canvas, Ausschnitt und Fokus liegen
        noch in DESK — der Router hat nur `active` abgeschaltet."""
        D = self.DESK
        if D["canvas"] is not None:
            D.update(active=True, msg="")

    def _modal_ergebnis(self, was):
        """Was ein Modal nach einer Taste meldet: "speichern", "abbrechen"
        oder None (weiter tippen)."""
        D = self.DESK
        if D["modal_neu"] is not None and was in ("speichern", "abbrechen"):
            art, werte = D["modal_neu"], D["modal"].aenderungen()
            grund = self._kachel_anlegen(art, werte) if was == "speichern" else None
            if grund:
                D["modal"].fehler = grund     # der Hub sagt nein: Dialog bleibt
            else:
                D["modal"] = D["modal_neu"] = None
            return None
        if was == "speichern":
            el = D["canvas"].element(D["modal_id"])
            if el is not None:
                el.update(D["modal"].aenderungen())
                D["modal"] = None
                self.speichern()
            else:
                D["modal"] = None
        elif was == "abbrechen":
            D["modal"] = None
        return None

    def status_text(self):
        """Statuszeile im Kasten: die Frage, die Größe beim Ändern (mit
        Anschlag), eine Meldung — Tasten zeigt nur die Leiste ganz unten."""
        D = self.DESK
        c = D["canvas"]
        if c and c.modus == "frage":
            return c.frage["text"]
        if c and c.modus == "groesse":
            # Größe immer sichtbar, auch wenn eine Grenze anschlägt.
            e = c.element(c.groesse["id"])
            groesse = "%d×%d" % (e["w"], e["h"]) if e else "?"
            anschlag = c.groesse["anschlag"]
            return "%s · %s" % (groesse, anschlag) if anschlag else groesse
        return D["msg"]

    # ── Zeichnen ──────────────────────────────────────────────────────
    def titel(self):
        D = self.DESK
        return "desk · " + D["desk"] if D["ebene"] == "canvas" and D["desk"] else "desk"

    def draw_desk(self, top, mx, h, w):
        if self.DESK["ebene"] == "wahl":
            self._draw_wahl(top, mx, h, w)
        else:
            self._draw_canvas(top, mx, h, w)

    def _draw_wahl(self, top, mx, h, w):
        D, C, z = self.DESK, self.z.C, self.z
        y = top + 2
        z.addclip(y, mx + 3, "deine desks", w - 6, C["dim"])
        y += 2
        zeilen = [d["name"] + ("" if d.get("elemente") is None else "  · %d" % d["elemente"])
                  for d in D["desks"]] + ["+ neuer desk"]
        for i, text in enumerate(zeilen):
            if y >= top + h - 3:
                break
            gewaehlt = i == D["sel"]
            z.addclip(y, mx + 3, ("› " if gewaehlt else "  ") + text, w - 6,
                      (C["acc"] | curses.A_BOLD) if gewaehlt else C["ink"])
            y += 1
        if D["name"] is not None:
            sicht, (_r, s) = D["name"].anzeige(max(1, w - 20), 1)
            text = sicht[0] if sicht else ""
            z.addclip(top + h - 3, mx + 3, "name: ", 6, C["dim"])
            z.addclip(top + h - 3, mx + 9, text, w - 12, C["bright"])
            z.addclip(top + h - 3, mx + 9 + s, (text[s:s + 1] or " "), 1, C["bright"] | curses.A_REVERSE)
        elif D["msg"]:
            z.addclip(top + h - 2, mx + 3, D["msg"], w - 6, C["warn"])

    def _draw_canvas(self, top, mx, h, w):
        D, C, z = self.DESK, self.z.C, self.z
        c = D["canvas"]
        ch_, cw = max(1, h - 3), max(1, w - 2)
        c.vw, c.vh = cw, ch_
        if D["zentrieren"]:
            self._zentrieren(c)
            c.springen()                 # beim Öffnen nicht hingleiten
            D["zentrieren"] = False
        c.gleiten()                      # ein Bild weiter auf (vx, vy) zu
        self.vorschauen_holen(c)
        desk_kacheln.pflegen(c.elemente, lambda *a, **k: api_call(*a, **k), self.starten)
        for j, stuecke in enumerate(c.bild(ch_, cw)):
            for x, text, rolle in stuecke:
                attr = self._farbe(rolle)
                if rolle in FETT:
                    attr |= curses.A_BOLD
                z.safe_addstr(top + 1 + j, mx + 1 + x, text, attr)
        # Wo die Mitte gerade IST (beim Gleiten unterwegs), nicht wohin sie
        # will — sonst springt die Zahl voraus (2026-10-10).
        ax, ay = c.anzeige_lage()
        lage = "%d,%d" % (ax + cw // 2, ay + ch_ // 2)
        status = self.status_text()
        anschlag = c.modus == "groesse" and c.groesse["anschlag"]
        farbe = C["warn"] if (D["msg"] or c.modus == "frage" or anschlag) else C["faint"]
        z.addclip(top + h - 2, mx + 2, status, max(0, w - 6 - len(lage)), farbe)
        z.addclip(top + h - 2, mx + w - 2 - len(lage), lage, len(lage), C["faint"])
        if D["modal"] is not None:
            self._draw_modal(top, mx, h, w)
        elif D["bild_wahl"] is not None:
            self._draw_bild_wahl(top, mx, h, w)
        elif D["art_wahl"] is not None:
            self._draw_art_wahl(top, mx, h, w)

    def _farbe(self, rolle):
        """Rolle → curses-Attribut. „#rrggbb" (Bild in Farbe) wird ein
        Pixel-Farbpaar auf dem Theme-Grund; ohne 256 Farben normale Schrift."""
        C = self.z.C
        if rolle and rolle[0] == "#" and len(rolle) == 7:
            if not C.get("pix_bg"):
                return C.get("ink", 0)
            rgb = (int(rolle[1:3], 16), int(rolle[3:5], 16), int(rolle[5:7], 16))
            return self.z.pix_attr(rgb, C["pix_bg"])
        return C.get(FARBEN.get(rolle, rolle), 0)

    def _kasten(self, top, mx, h, w, titel, zeilen, sel, mh=None):
        """Kleiner Wähler mittig über der Fläche."""
        C, z = self.z.C, self.z
        mw = max(24, min(56, w - 6))
        mh = mh or max(5, min(len(zeilen) + 4, h - 4))
        y0 = top + (h - mh) // 2
        x0 = mx + (w - mw) // 2
        for j in range(mh):
            z.safe_addstr(y0 + j, x0, " " * mw, C["ink"])
        z.draw_box(y0, x0, mh, mw, titel, C["acc"])
        platz = mh - 4
        oben = max(0, min(sel - platz + 1, len(zeilen) - platz)) if sel >= platz else 0
        for j, text in enumerate(zeilen[oben:oben + platz]):
            gewaehlt = oben + j == sel
            z.addclip(y0 + 1 + j, x0 + 2, ("› " if gewaehlt else "  ") + text, mw - 4,
                      (C["acc"] | curses.A_BOLD) if gewaehlt else C["ink"])
        return y0, x0, mw, mh

    def _draw_art_wahl(self, top, mx, h, w):
        wahl = self.DESK["art_wahl"]
        self._kasten(top, mx, h, w, "neu", [a.neu_label for a in wahl["arten"]],
                     wahl["sel"])

    def _draw_bild_wahl(self, top, mx, h, w):
        C, z = self.z.C, self.z
        wahl = self.DESK["bild_wahl"]
        zeilen = [q["name"] for q in wahl["quellen"]] + ["pfad tippen …"]
        leer = [] if wahl["quellen"] else ["(keine bilder in ~/Zentrale/Input)"]
        if wahl["pfad"] is None:
            self._kasten(top, mx, h, w, "bild aus Input", leer + zeilen,
                         wahl["sel"] + len(leer))
            return
        y0, x0, mw, mh = self._kasten(top, mx, h, w, "bild: pfad", leer + zeilen,
                                      len(leer) + len(zeilen) - 1)
        sicht, (_r, s) = wahl["pfad"].anzeige(max(1, mw - 12), 1)
        text = sicht[0] if sicht else ""
        z.addclip(y0 + mh - 3, x0 + 2, "pfad: ", 6, C["dim"])
        z.addclip(y0 + mh - 3, x0 + 8, text, mw - 10, C["bright"])
        z.addclip(y0 + mh - 3, x0 + 8 + s, (text[s:s + 1] or " "), 1, C["bright"] | curses.A_REVERSE)

    @staticmethod
    def _zentrieren(c):
        """Beim Öffnen: Mitte aller Elemente in die Mitte des Ausschnitts."""
        if not c.elemente:
            c.vx, c.vy = -(c.vw // 2), -(c.vh // 2)
            return
        x0 = min(e["x"] for e in c.elemente)
        y0 = min(e["y"] for e in c.elemente)
        x1 = max(e["x"] + e["w"] for e in c.elemente)
        y1 = max(e["y"] + e["h"] for e in c.elemente)
        c.vx = (x0 + x1) // 2 - c.vw // 2
        c.vy = (y0 + y1) // 2 - c.vh // 2
        if x1 - x0 > c.vw or y1 - y0 > c.vh:        # passt nicht: oben links anfangen
            c.vx, c.vy = x0 - 1, y0 - 1

    def _draw_modal(self, top, mx, h, w):
        """Das Bearbeiten-Modal mittig über der Fläche."""
        D, C, z = self.DESK, self.z.C, self.z
        m = D["modal"]
        mw = max(20, min(getattr(m, "breite", 64), w - 6))
        mh = max(7, min(getattr(m, "hoehe", 18), h - 4))    # ein Dialog darf kleiner sein
        y0 = top + (h - mh) // 2
        x0 = mx + (w - mw) // 2
        for j in range(mh):
            z.safe_addstr(y0 + j, x0, " " * mw, C["ink"])
        z.draw_box(y0, x0, mh, mw, getattr(m, "kopf", None) or m.titel + " bearbeiten", C["acc"])
        sicht, (cr, cs) = m.anzeige(mw - 4, mh - 4)
        for j, zeile in enumerate(sicht):
            z.addclip(y0 + 1 + j, x0 + 2, zeile, mw - 4, C["bright"])
        if 0 <= cr < len(sicht) or not sicht:
            zeile = sicht[cr] if sicht else ""
            z.addclip(y0 + 1 + cr, x0 + 2 + cs, zeile[cs:cs + 1] or " ", 1,
                      C["bright"] | curses.A_REVERSE)
