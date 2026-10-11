# tui/ansichten/notizen.py
#
# Das Notiz-Werkzeug der TUI (Zeichner gegen /api/notes; core/notes.py hält
# die Registry, das Layout rechnet die TUI hier selbst). Bis 06.10.2026
# Closures in run_ui (tui/zentrale_tui.py), siehe memory/system/tui_bauplan.md.

import curses

from .basis import BEENDEN, api_call
from .tasten import Tasten


def n_block_empty(blk):
    """Hat der Block KEINEN Inhalt? Leere Blöcke dürfen ohne Nachfrage weg,
    befüllte fragen vor dem Löschen nach (siehe 'd' in Ebene 1)."""
    t = blk.get("type")
    if t == "text":
        return not (blk.get("text") or "").strip()
    if t == "list":
        return not any((it.get("text") or "").strip() for it in (blk.get("items") or []))
    if t == "float":
        return not any((tm.get("text") or "").strip() for tm in (blk.get("terms") or []))
    return True


# ── Notiz-Werkzeug: Layout (Spiegel von core/notes, curses rechnet selbst) ──
def n_wrap(text, width):
    width = max(1, int(width)); out = []
    for raw in str(text).split("\n"):
        if not raw:
            out.append(""); continue
        line = ""
        for word in raw.split(" "):
            while len(word) > width:
                if line:
                    out.append(line); line = ""
                out.append(word[:width]); word = word[width:]
            cand = word if not line else line + " " + word
            if len(cand) <= width:
                line = cand
            else:
                out.append(line); line = word
        out.append(line)
    return out or [""]


def n_float_pos(widths, width):
    """Spiegel von core.notes._float_positions: (positions, rows). Terme
    greedy zeilenweise nach ECHTER Breite gepackt — passt einer nicht mehr,
    bricht er um (Box wächst nach unten), nie Überlappung; kleiner fixer
    Versatz gibt den verstreuten Eindruck."""
    w = max(1, int(width)); gap = 3
    pos, x, row = [], 0, 0
    for i, tw in enumerate(widths):
        tw = min(max(1, int(tw)), w)
        jit = (i * 7) % 3
        if x > 0 and x + jit + tw > w:
            row += 1; x = 0
        px = x + (jit if x + jit + tw <= w else 0)
        px = min(px, max(0, w - tw))
        pos.append((px, row * 2))
        x = px + tw + gap
    return pos, (row + 1 if widths else 0)


class Notizen:
    """Das Notiz-Werkzeug (Mitte, Taste 'n'): eine Notiz aus gestapelten
    Blöcken (text/list/float), Ebene 1 navigiert, Ebene 2 bearbeitet; dazu
    die Übersicht aller Notizen. Zustand in self.NOTE (auch z.NOTE)."""

    def __init__(self, z):
        self.z = z
        # ── Notiz-Werkzeug (füllt die MITTE-Box, Taste 'n') ─────────────────
        # Freie Notiz aus untereinander gestapelten Blöcken (text/list/float).
        # Wie die anderen Werkzeuge ein reiner HTTP-Client (kann auf dem Laptop
        # gegen das PC-Backend laufen) → Daten über /api/notes, das Layout wird
        # HIER lokal gerechnet (kleine Spiegel von core/notes: n_wrap/n_block_h/
        # n_stack/n_scatter — analog l_done↔core.lists.is_done).
        # Zwei Ebenen (layer): 1 = zwischen Blöcken navigieren + neue anlegen
        # (t/l/f), 2 = den fokussierten Block form-spezifisch bearbeiten.
        #   view   : "edit" (eine Notiz) | "list" (Übersicht aller Notizen)
        #   note   : die aktuell offene Notiz (voll, inkl. blocks) oder None
        #   bsel   : fokussierter Block-Index; esel/buf: Ebene-2-Cursor + Tipppuffer
        self.NOTE = z.NOTE = {"active": False, "view": "edit",
                              "notes": [], "sel": 0,
                              "note": None,
                              "layer": 1, "bsel": 0,
                              "esel": 0, "buf": "",
                              "titling": False,
                              "scroll": 0, "confirm": False, "bconfirm": False, "msg": ""}

    # ── Notiz-Werkzeug: Daten (über /api/notes) ─────────────────────────
    def n_load_list(self):
        """Notiz-Übersicht frisch ziehen (kommt neueste-zuerst sortiert)."""
        NOTE = self.NOTE
        try:
            NOTE["notes"] = api_call("/api/notes") or []
        except Exception:
            NOTE["notes"] = []
        if NOTE["sel"] >= len(NOTE["notes"]):
            NOTE["sel"] = max(0, len(NOTE["notes"]) - 1)

    def n_enter_edit(self, full):
        """In den Bearbeiten-Modus einer (frisch geladenen) Notiz springen."""
        NOTE = self.NOTE
        NOTE["note"] = full
        NOTE["view"] = "edit"; NOTE["layer"] = 1
        NOTE["bsel"] = 0; NOTE["esel"] = 0; NOTE["buf"] = ""
        NOTE["scroll"] = 0; NOTE["titling"] = False; NOTE["msg"] = ""

    def n_new(self):
        """Neue leere Notiz anlegen und öffnen. Liefert sie oder None."""
        n_enter_edit = self.n_enter_edit
        try:
            full = api_call("/api/notes", method="POST", body={"title": ""})
        except Exception:
            full = None
        if full is not None:
            n_enter_edit(full)
        return full

    def n_open(self):
        """Öffner von der Startseite: zuletzt bearbeitete Notiz laden, sonst neue."""
        NOTE, n_enter_edit, n_load_list = self.NOTE, self.n_enter_edit, self.n_load_list
        n_new = self.n_new
        n_load_list()
        full = None
        if NOTE["notes"]:
            try:
                full = api_call("/api/notes/" + NOTE["notes"][0]["id"])
            except Exception:
                full = None
        if full is not None:
            n_enter_edit(full)
        else:
            n_new()

    def n_save(self):
        """Aktuelle Notiz (Titel + Blöcke) sichern (PUT). Fehler → nur Meldung."""
        NOTE = self.NOTE
        n = NOTE["note"]
        if not n or not n.get("id"):
            return
        try:
            api_call("/api/notes/" + n["id"], method="PUT",
                     body={"title": n.get("title", ""), "blocks": n.get("blocks") or []})
        except Exception:
            NOTE["msg"] = "speichern fehlgeschlagen"

    def n_add_block(self, btype):
        """Neuen Block anhängen, fokussieren und DIREKT in Ebene 2 (bearbeiten)
        springen — man tippt sofort los, ohne erst 'e'/Enter (next_block = id-Quelle)."""
        NOTE, n_save = self.NOTE, self.n_save
        n = NOTE["note"]
        if not n:
            return
        bid = n.get("next_block") or 1
        blk = {"id": bid, "type": btype}
        if btype == "text":
            blk["text"] = ""
        elif btype == "list":
            blk["items"] = []; blk["next_item"] = 1
        else:  # float
            blk["terms"] = []; blk["next_term"] = 1
        n.setdefault("blocks", []).append(blk)
        n["next_block"] = bid + 1
        NOTE["bsel"] = len(n["blocks"]) - 1
        # frischer Block ist leer → esel auf den 'neu'-Slot (0), Puffer leer.
        NOTE["layer"] = 2; NOTE["esel"] = 0; NOTE["buf"] = ""
        n_save()

    def n_loadbuf(self, blk):
        """Ebene-2-Puffer aus dem gewählten Item/Term füllen (leer = 'neu'-Slot)."""
        NOTE = self.NOTE
        seq = (blk.get("items") if blk.get("type") == "list" else blk.get("terms")) or []
        NOTE["buf"] = seq[NOTE["esel"]]["text"] if NOTE["esel"] < len(seq) else ""

    def n_commit_list(self, blk):
        """Puffer in das gewählte Listen-Item schreiben / neues anhängen. Leerer
        Text auf einem bestehenden Item → Item entfällt."""
        NOTE = self.NOTE
        items = blk.setdefault("items", [])
        txt = NOTE["buf"].strip()
        if NOTE["esel"] < len(items):
            if txt:
                items[NOTE["esel"]]["text"] = txt
            else:
                del items[NOTE["esel"]]
        elif txt:
            iid = blk.get("next_item") or 1
            items.append({"id": iid, "text": txt, "done": False})
            blk["next_item"] = iid + 1

    def n_commit_float(self, blk):
        """Wie n_commit_list, aber für Float-Terme ({id,text})."""
        NOTE = self.NOTE
        terms = blk.setdefault("terms", [])
        txt = NOTE["buf"].strip()
        if NOTE["esel"] < len(terms):
            if txt:
                terms[NOTE["esel"]]["text"] = txt
            else:
                del terms[NOTE["esel"]]
        elif txt:
            tid = blk.get("next_term") or 1
            terms.append({"id": tid, "text": txt})
            blk["next_term"] = tid + 1

    def n_float_widths(self, blk, editing):
        """Display-Breiten der Float-Terme EXAKT wie n_drawblock sie zeichnet
        (inkl. »…« ums gewählte und den '+'-Neu-Slot beim Bearbeiten), damit
        Höhe und Positionen zusammenpassen."""
        NOTE = self.NOTE
        terms = blk.get("terms") or []
        ws = []
        for i, tm in enumerate(terms):
            if editing and i == NOTE["esel"]:
                ws.append(len(NOTE["buf"]) + 2)                # »buf«
            else:
                ws.append(len(str(tm.get("text") or "")))
        if editing:                                            # '+'-Neu-Slot
            ws.append(len(NOTE["buf"]) + 2 if NOTE["esel"] == len(terms) else 1)
        return [max(1, w) for w in ws]

    def n_content_rows(self, blk, inner, editing):
        n_float_widths = self.n_float_widths
        t = blk.get("type")
        if t == "text":
            return max(1, len(n_wrap(blk.get("text", ""), inner)))
        if t == "list":
            return max(1, len(blk.get("items") or []) + (1 if editing else 0))
        _, rows = n_float_pos(n_float_widths(blk, editing), inner)   # float
        return max(3, rows * 2 - 1) if rows else 3

    def n_block_h(self, blk, width, editing=False):
        n_content_rows = self.n_content_rows
        return n_content_rows(blk, max(1, int(width) - 2), editing) + 2

    def n_stack(self, blocks, width, gap=1):
        """[(block, y, h, editing), …]. Der fokussierte Block wächst in Ebene 2
        um die 'neu'-Zeile (Liste/Float), damit die Eingabe Platz hat."""
        NOTE, n_block_h = self.NOTE, self.n_block_h
        out, y = [], 0
        for i, b in enumerate(blocks):
            editing = (NOTE["layer"] == 2 and i == NOTE["bsel"])
            h = n_block_h(b, width, editing)
            out.append((b, y, h, editing))
            y += h + gap
        return out

    def oeffnen(self):
        """Startseite → Notiz-Werkzeug, direkt in eine Notiz."""
        self.NOTE["active"] = True; self.n_open()

    # ── Tasten: EINE Tabelle, aus der Verteilung und Leiste lesen ──────
    # (tasten.py, 2026-10-11). Ohne Text = verarbeitet, aber nicht gezeigt.
    TASTEN = Tasten({
        "liste": [
            ("↑↓", "waehlen", "select"), ("k/j", "waehlen"),
            ("enter", "oeffnen", "open"), ("n/N", "neu", "new"),
            ("d/D", "loeschen", "delete"), ("esc", "zurueck", "back"),
            ("q/Q", "beenden"),
        ],
        "liste:frage": [
            ("j/y/enter", "ja", "delete"), ("J/Y", "ja"), ("any key", "nein", "cancel"),
        ],
        "titel": [
            ("type", "tippen", "type title"), ("enter", "titel_setzen", "set"),
            ("⌫", "zeichen_weg", "delete"), ("esc", "titel_abbrechen", "cancel"),
        ],
        "notiz": [
            ("↑↓", "block_waehlen", "block"), ("k/j", "block_waehlen"),
            ("t/l/f", "block_neu", "new text/list/float"), ("T/L/F", "block_neu"),
            ("e/enter", "bearbeiten", "edit"), ("d/D", "block_loeschen", "delete block"),
            ("r/R", "titel", "title"), ("n/N", "uebersicht", "overview"),
            ("esc", "schliessen", "save & close"), ("q/Q", "beenden"),
        ],
        "notiz:frage": [
            ("j/y/enter", "block_ja", "delete"), ("J/Y", "block_ja"),
            ("any key", "block_nein", "cancel"),
        ],
        "block:text": [
            ("type", "text_tippen", "type"), ("enter", "text_zeile", "new line"),
            ("⌫", "text_weg", "delete"), ("esc", "fertig", "done"),
        ],
        "block:liste": [
            ("type", "puffer_tippen", "type"), ("enter", "eintrag_setzen", "new item"),
            ("↑↓", "eintrag_waehlen", "item"), ("tab", "haken", "check"),
            ("del", "eintrag_weg", "remove"), ("⌫", "puffer_weg", "delete"),
            ("esc", "fertig", "done"),
        ],
        "block:float": [
            ("type", "puffer_tippen", "type"), ("enter", "eintrag_setzen", "set"),
            ("←→", "eintrag_waehlen", "select"), ("↑↓", "eintrag_waehlen"),
            ("del", "eintrag_weg", "remove"), ("⌫", "puffer_weg", "delete"),
            ("esc", "fertig", "done"),
        ],
    })

    def ansicht(self):
        """Welche Ansicht der Tabelle gerade offen ist."""
        NOTE = self.NOTE
        if NOTE["view"] == "list":
            return "liste:frage" if NOTE["confirm"] else "liste"
        if NOTE["titling"]:
            return "titel"
        if NOTE["layer"] == 1:
            return "notiz:frage" if NOTE["bconfirm"] else "notiz"
        blk = self._block()
        if blk is None:
            return "notiz"
        return {"list": "block:liste", "float": "block:float"}.get(blk["type"], "block:text")

    def taste(self, ch):
        """Eine Taste, während das Notiz-Werkzeug den Fokus hat. Gibt BEENDEN
        zurück, wenn die TUI enden soll."""
        if self.NOTE["layer"] == 2 and self._block() is None:   # Block weg → Ebene 1
            self.NOTE["layer"] = 1
        return self.TASTEN.verteilen(self, self.ansicht(), ch)

    def _bloecke(self):
        n = self.NOTE["note"]
        return (n.get("blocks") if n else None) or []

    def _block(self):
        blocks, i = self._bloecke(), self.NOTE["bsel"]
        return blocks[i] if 0 <= i < len(blocks) else None

    # ── Übersicht ──
    def aktion_waehlen(self, taste):
        NOTE = self.NOTE
        if taste in ("up", "k"):
            NOTE["sel"] = max(0, NOTE["sel"] - 1)
        else:
            NOTE["sel"] = min(max(0, len(NOTE["notes"]) - 1), NOTE["sel"] + 1)

    def aktion_oeffnen(self, _taste):
        NOTE = self.NOTE
        if NOTE["notes"]:
            try:
                full = api_call("/api/notes/" + NOTE["notes"][NOTE["sel"]]["id"])
            except Exception:
                full = None
            if full is not None:
                self.n_enter_edit(full)

    def aktion_neu(self, _taste):
        self.n_new()

    def aktion_loeschen(self, _taste):
        if self.NOTE["notes"]:
            self.NOTE["confirm"] = True; self.NOTE["msg"] = ""

    def aktion_zurueck(self, _taste):
        NOTE = self.NOTE
        if NOTE["note"]:
            NOTE["view"] = "edit"; NOTE["msg"] = ""
        else:
            NOTE["active"] = False

    def aktion_beenden(self, _taste):
        if self.NOTE["view"] != "list":
            self.n_save()
        return BEENDEN

    def aktion_ja(self, _taste):
        NOTE = self.NOTE
        if NOTE["notes"]:
            gone = NOTE["notes"][NOTE["sel"]]["id"]
            try:
                api_call("/api/notes/" + gone, method="DELETE")
                NOTE["msg"] = "gelöscht"
            except Exception:
                NOTE["msg"] = "löschen fehlgeschlagen"
            if NOTE["note"] and NOTE["note"].get("id") == gone:
                NOTE["note"] = None                     # aktuelle Notiz war es
        NOTE["confirm"] = False; self.n_load_list()

    def aktion_nein(self, _taste):
        self.NOTE["confirm"] = False; self.NOTE["msg"] = ""

    # ── Titel tippen ──
    def aktion_tippen(self, zeichen):
        if len(self.NOTE["buf"]) < 60:
            self.NOTE["buf"] += zeichen

    def aktion_titel_setzen(self, _taste):
        NOTE, n = self.NOTE, self.NOTE["note"]
        if n is not None:
            n["title"] = NOTE["buf"].strip(); self.n_save(); self.n_load_list()
        NOTE["titling"] = False; NOTE["msg"] = "titel gesetzt"

    def aktion_zeichen_weg(self, _taste):
        self.NOTE["buf"] = self.NOTE["buf"][:-1]

    def aktion_titel_abbrechen(self, _taste):
        self.NOTE["titling"] = False; self.NOTE["msg"] = ""

    # ── Ebene 1: navigieren/anlegen ──
    def aktion_block_waehlen(self, taste):
        NOTE = self.NOTE
        if taste in ("up", "k"):
            NOTE["bsel"] = max(0, NOTE["bsel"] - 1)
        else:
            NOTE["bsel"] = min(max(0, len(self._bloecke()) - 1), NOTE["bsel"] + 1)

    def aktion_block_neu(self, taste):
        self.n_add_block({"t": "text", "l": "list", "f": "float"}[taste.lower()])

    def aktion_bearbeiten(self, _taste):
        NOTE, blk = self.NOTE, self._block()
        if blk is None:
            return
        NOTE["layer"] = 2
        if blk["type"] in ("list", "float"):
            seq = blk.get("items") if blk["type"] == "list" else blk.get("terms")
            NOTE["esel"] = len(seq or [])               # auf den 'neu'-Slot
        else:
            NOTE["esel"] = 0
        NOTE["buf"] = ""

    def _block_weg(self):
        NOTE, blocks = self.NOTE, self._bloecke()
        del blocks[NOTE["bsel"]]
        NOTE["bsel"] = min(NOTE["bsel"], max(0, len(blocks) - 1))
        self.n_save()

    def aktion_block_loeschen(self, _taste):
        blk = self._block()
        if blk is None:
            return
        if n_block_empty(blk):
            self._block_weg()                           # leer → sofort weg
        else:
            self.NOTE["bconfirm"] = True; self.NOTE["msg"] = ""   # befüllt → nachfragen

    def aktion_titel(self, _taste):
        n = self.NOTE["note"]
        if n is not None:
            self.NOTE["titling"] = True; self.NOTE["buf"] = str(n.get("title") or "")

    def aktion_uebersicht(self, _taste):
        NOTE = self.NOTE
        self.n_save(); self.n_load_list()
        NOTE["view"] = "list"; NOTE["sel"] = 0
        NOTE["confirm"] = False; NOTE["msg"] = ""

    def aktion_schliessen(self, _taste):
        self.n_save(); self.NOTE["active"] = False

    def aktion_block_ja(self, _taste):
        if self._block() is not None:
            self._block_weg()
        self.NOTE["bconfirm"] = False; self.NOTE["msg"] = "gelöscht"

    def aktion_block_nein(self, _taste):
        self.NOTE["bconfirm"] = False; self.NOTE["msg"] = ""

    # ── Ebene 2: Block bearbeiten ──
    def aktion_text_tippen(self, zeichen):
        blk = self._block()
        blk["text"] = blk.get("text", "") + zeichen

    def aktion_text_zeile(self, _taste):
        self.aktion_text_tippen("\n")

    def aktion_text_weg(self, _taste):
        blk = self._block()
        blk["text"] = blk.get("text", "")[:-1]

    def _folge(self, blk):
        """Die Einträge eines Listen- oder Float-Blocks."""
        return blk.setdefault("items" if blk["type"] == "list" else "terms", [])

    def _uebernehmen(self, blk):
        (self.n_commit_list if blk["type"] == "list" else self.n_commit_float)(blk)

    def aktion_fertig(self, _taste):
        blk = self._block()
        if blk["type"] in ("list", "float"):
            self._uebernehmen(blk)
        self.n_save(); self.NOTE["layer"] = 1

    def aktion_puffer_tippen(self, zeichen):
        self.NOTE["buf"] += zeichen

    def aktion_eintrag_setzen(self, _taste):
        blk = self._block()
        self._uebernehmen(blk)
        self.NOTE["esel"] = len(self._folge(blk)); self.NOTE["buf"] = ""

    def aktion_eintrag_waehlen(self, taste):
        NOTE, blk = self.NOTE, self._block()
        self._uebernehmen(blk)
        if taste in ("up", "left"):
            NOTE["esel"] = max(0, NOTE["esel"] - 1)
        else:
            NOTE["esel"] = min(len(self._folge(blk)), NOTE["esel"] + 1)
        self.n_loadbuf(blk)

    def aktion_haken(self, _taste):
        NOTE, items = self.NOTE, self._folge(self._block())
        if NOTE["esel"] < len(items):
            items[NOTE["esel"]]["done"] = not items[NOTE["esel"]].get("done")
            self.n_save()

    def aktion_eintrag_weg(self, _taste):
        NOTE, blk = self.NOTE, self._block()
        seq = self._folge(blk)
        if NOTE["esel"] < len(seq):
            del seq[NOTE["esel"]]
            NOTE["esel"] = min(NOTE["esel"], len(seq)); self.n_loadbuf(blk); self.n_save()

    def aktion_puffer_weg(self, taste):
        if self.NOTE["buf"]:
            self.NOTE["buf"] = self.NOTE["buf"][:-1]
        else:
            self.aktion_eintrag_weg(taste)

    def n_drawblock(self, blk, sy, rh, focus, editing, ix, iw, atop, abot):
        """Einen Block-Kasten zeichnen, vertikal an [atop,abot] geklippt."""
        C, NOTE, addclip = self.z.C, self.NOTE, self.z.addclip
        n_float_widths, safe_addstr = self.n_float_widths, self.z.safe_addstr
        battr = C["acc"] if focus else C["faint"]
        label = {"text": "text", "list": "liste", "float": "float"}.get(blk.get("type"), "?")
        for r in range(rh):                       # Rahmen
            yrow = sy + r
            if not (atop <= yrow <= abot):
                continue
            if r == 0:
                safe_addstr(yrow, ix, "┌" + "─" * (iw - 2) + "┐", battr)
                head = ("▸ " if focus else "") + label
                safe_addstr(yrow, ix + 2, " " + head.upper() + " ",
                            C["bright"] if focus else C["acc"])
            elif r == rh - 1:
                safe_addstr(yrow, ix, "└" + "─" * (iw - 2) + "┘", battr)
            else:
                safe_addstr(yrow, ix, "│", battr)
                safe_addstr(yrow, ix + iw - 1, "│", battr)
        cy0, cx, cw = sy + 1, ix + 1, iw - 2      # Inhalts-Region
        cbot = sy + rh - 2
        t = blk.get("type")
        rowok = lambda yr: (atop <= yr <= abot) and yr <= cbot

        if t == "text":
            lines = n_wrap(blk.get("text", ""), cw)
            for i, ln in enumerate(lines):
                yr = cy0 + i
                if yr > cbot:
                    break
                if rowok(yr):
                    cur = "_" if (editing and i == len(lines) - 1) else ""
                    addclip(yr, cx, ln + cur, cw, C["dim"])
        elif t == "list":
            items = blk.get("items") or []
            for i in range(len(items) + (1 if editing else 0)):
                yr = cy0 + i
                if yr > cbot:
                    break
                if not rowok(yr):
                    continue
                if i < len(items):
                    it = items[i]; done = bool(it.get("done"))
                    sel = editing and i == NOTE["esel"]
                    box = "[x]" if done else "[ ]"
                    txt = NOTE["buf"] if sel else str(it.get("text") or "")
                    attr = C["bright"] if sel else (C["faint"] if done else C["dim"])
                    addclip(yr, cx, box + " " + txt + ("_" if sel else ""), cw, attr,
                            strike=done and not sel)
                else:
                    sel = editing and NOTE["esel"] == len(items)
                    addclip(yr, cx, "+ " + (NOTE["buf"] if sel else "") + ("_" if sel else ""),
                            cw, C["bright"] if sel else C["faint"])
        elif t == "float":
            terms = blk.get("terms") or []
            show = len(terms) + (1 if editing else 0)
            pos, _ = n_float_pos(n_float_widths(blk, editing), cw)
            for i in range(show):
                px, py = pos[i]; yr = cy0 + py; col = cx + px; room = cw - px
                if room < 1 or not rowok(yr):
                    continue
                if i < len(terms):
                    sel = editing and i == NOTE["esel"]
                    txt = NOTE["buf"] if sel else str(terms[i].get("text") or "")
                    disp = ("»%s«" % txt) if sel else txt
                else:
                    sel = editing and NOTE["esel"] == len(terms)
                    disp = "+" + (NOTE["buf"] if sel else "") + ("_" if sel else "")
                # Beim Tippen den Rand-Überlauf abfangen: ist der Term breiter als
                # der Platz, das ENDE zeigen — so bleibt der frisch getippte Text
                # (am Cursor) immer sichtbar, statt rechts unsichtbar wegzulaufen.
                if sel and len(disp) > room:
                    disp = disp[-room:]
                addclip(yr, col, disp, room,
                        C["bright"] if sel else (C["dim"] if i < len(terms) else C["faint"]))

    def draw_note_tool(self, by, bx, bh, bw):
        """Inhalt der MITTE-Box fürs Notiz-Werkzeug (Übersicht ODER eine Notiz)."""
        C, NOTE, addclip = self.z.C, self.NOTE, self.z.addclip
        n_drawblock, n_stack = self.n_drawblock, self.n_stack
        safe_addstr = self.z.safe_addstr
        ix, iw = bx + 2, bw - 4
        bottom = by + bh - 2
        if iw < 8:
            return

        if NOTE["view"] == "list":                    # ── Übersicht ──
            addclip(by + 1, ix, "NOTIZEN  (%d)" % len(NOTE["notes"]), iw, C["bright"])
            safe_addstr(by + 2, ix, "─" * iw, C["faint"])
            notes = NOTE["notes"]; yy = by + 3
            if not notes:
                addclip(yy, ix, "noch keine — 'n' legt eine an", iw, C["faint"])
            else:
                avail = max(1, (bottom - 1) - yy)
                start = max(0, min(NOTE["sel"] - avail + 1, len(notes) - avail)) if len(notes) > avail else 0
                for off, nt in enumerate(notes[start:start + avail]):
                    sel = (start + off == NOTE["sel"])
                    title = str(nt.get("title") or "ohne titel")
                    md = str(nt.get("modified") or "")[:16].replace("T", " ")
                    meta = "  %s · %d" % (md, nt.get("nblocks", 0))
                    addclip(yy, ix, ("› " if sel else "  ") + title, iw - len(meta),
                            C["bright"] if sel else C["dim"])
                    safe_addstr(yy, bx + bw - 2 - len(meta), meta, C["faint"])
                    yy += 1
            # Tasten stehen in der Leiste ganz unten (Tastentabelle, 2026-10-11).
            if NOTE["confirm"]:
                addclip(bottom, ix, "wirklich löschen?", iw, C["bright"])
            else:
                addclip(bottom, ix, NOTE["msg"], iw, C["faint"])
            return

        n = NOTE["note"]                              # ── eine Notiz ──
        if not n:
            addclip(by + 1, ix, "keine notiz (backend erreichbar?)", iw, C["faint"])
            return
        if NOTE["titling"]:
            addclip(by + 1, ix, "titel: " + NOTE["buf"] + "_", iw, C["bright"])
        else:
            addclip(by + 1, ix, str(n.get("title") or "ohne titel"), iw, C["bright"])
        safe_addstr(by + 2, ix, "─" * iw, C["faint"])

        area_top, area_bottom = by + 3, by + bh - 3
        blocks = n.get("blocks") or []
        layout = n_stack(blocks, iw)
        area_h = max(1, area_bottom - area_top + 1)
        if blocks and 0 <= NOTE["bsel"] < len(layout):   # Fokus im Blick halten
            _, fy, fh, _e = layout[NOTE["bsel"]]
            if fy < NOTE["scroll"]:
                NOTE["scroll"] = fy
            elif fy + fh > NOTE["scroll"] + area_h:
                NOTE["scroll"] = fy + fh - area_h
        NOTE["scroll"] = max(0, NOTE["scroll"])

        if not blocks:
            addclip(area_top, ix, "leer", iw, C["faint"])
        for bi, (blk, ry, rh, editing) in enumerate(layout):
            sy = area_top + ry - NOTE["scroll"]
            if sy + rh - 1 < area_top or sy > area_bottom:
                continue
            n_drawblock(blk, sy, rh, bi == NOTE["bsel"], editing, ix, iw, area_top, area_bottom)

        # Tasten stehen in der Leiste ganz unten (Tastentabelle, 2026-10-11);
        # hier nur noch Frage oder Rückmeldung.
        frage = "block löschen?" if NOTE["bconfirm"] else NOTE["msg"]
        addclip(by + bh - 2, ix, frage, iw, C["bright"] if NOTE["bconfirm"] else C["faint"])
