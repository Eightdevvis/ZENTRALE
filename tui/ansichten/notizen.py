# tui/ansichten/notizen.py
#
# Das Notiz-Werkzeug der TUI (Zeichner gegen /api/notes; core/notes.py hält
# die Registry, das Layout rechnet die TUI hier selbst). Bis 06.10.2026
# Closures in run_ui (tui/zentrale_tui.py), siehe memory/system/tui_bauplan.md.

import curses

from .basis import BEENDEN, api_call


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

    def taste(self, ch):
        """Eine Taste, während das Notiz-Werkzeug den Fokus hat (früher ein Zweig
        der Hauptschleife in run_ui). Gibt BEENDEN zurück, wenn die TUI enden soll."""
        NOTE, n_add_block, n_commit_float = self.NOTE, self.n_add_block, self.n_commit_float
        n_commit_list, n_enter_edit = self.n_commit_list, self.n_enter_edit
        n_load_list, n_loadbuf, n_new = self.n_load_list, self.n_loadbuf, self.n_new
        n_save = self.n_save
        n = NOTE["note"]
        blocks = (n.get("blocks") if n else None) or []
        if NOTE["view"] == "list":                          # ── Übersicht ──
            if NOTE["confirm"]:
                if ch in (ord("y"), ord("Y"), ord("j"), ord("J"),
                          10, 13, curses.KEY_ENTER):
                    if NOTE["notes"]:
                        gone = NOTE["notes"][NOTE["sel"]]["id"]
                        try:
                            api_call("/api/notes/" + gone, method="DELETE")
                            NOTE["msg"] = "gelöscht"
                        except Exception:
                            NOTE["msg"] = "löschen fehlgeschlagen"
                        if NOTE["note"] and NOTE["note"].get("id") == gone:
                            NOTE["note"] = None             # aktuelle Notiz war es
                    NOTE["confirm"] = False; n_load_list()
                elif ch != -1:
                    NOTE["confirm"] = False; NOTE["msg"] = ""
            elif ch == 27:                                  # Esc → zurück/zu
                if NOTE["note"]:
                    NOTE["view"] = "edit"; NOTE["msg"] = ""
                else:
                    NOTE["active"] = False
            elif ch in (ord("q"), ord("Q")):
                return BEENDEN
            elif ch in (curses.KEY_UP, ord("k")):
                NOTE["sel"] = max(0, NOTE["sel"] - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                NOTE["sel"] = min(max(0, len(NOTE["notes"]) - 1), NOTE["sel"] + 1)
            elif ch in (10, 13, curses.KEY_ENTER):
                if NOTE["notes"]:
                    try:
                        full = api_call("/api/notes/" + NOTE["notes"][NOTE["sel"]]["id"])
                    except Exception:
                        full = None
                    if full is not None:
                        n_enter_edit(full)
            elif ch in (ord("n"), ord("N")):
                n_new()
            elif ch in (ord("d"), ord("D")):
                if NOTE["notes"]:
                    NOTE["confirm"] = True; NOTE["msg"] = ""
        elif NOTE["titling"]:                               # ── Titel tippen ──
            if ch == 27:
                NOTE["titling"] = False; NOTE["msg"] = ""
            elif ch in (10, 13, curses.KEY_ENTER):
                if n is not None:
                    n["title"] = NOTE["buf"].strip(); n_save(); n_load_list()
                NOTE["titling"] = False; NOTE["msg"] = "titel gesetzt"
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                NOTE["buf"] = NOTE["buf"][:-1]
            elif 32 <= ch <= 126 and len(NOTE["buf"]) < 60:
                NOTE["buf"] += chr(ch)
        elif NOTE["layer"] == 1:                            # ── Ebene 1: navigieren/anlegen ──
            if NOTE["bconfirm"]:                            # Block-Lösch-Nachfrage offen
                if ch in (ord("y"), ord("Y"), ord("j"), ord("J"),
                          10, 13, curses.KEY_ENTER):
                    if blocks and 0 <= NOTE["bsel"] < len(blocks):
                        del blocks[NOTE["bsel"]]
                        NOTE["bsel"] = min(NOTE["bsel"], max(0, len(blocks) - 1))
                        n_save()
                    NOTE["bconfirm"] = False; NOTE["msg"] = "gelöscht"
                elif ch != -1:                             # alles andere → abbrechen
                    NOTE["bconfirm"] = False; NOTE["msg"] = ""
            elif ch == 27:
                n_save(); NOTE["active"] = False
            elif ch in (ord("q"), ord("Q")):
                n_save(); return BEENDEN
            elif ch in (ord("n"), ord("N")):
                n_save(); n_load_list()
                NOTE["view"] = "list"; NOTE["sel"] = 0
                NOTE["confirm"] = False; NOTE["msg"] = ""
            elif ch in (curses.KEY_UP, ord("k")):
                NOTE["bsel"] = max(0, NOTE["bsel"] - 1)
            elif ch in (curses.KEY_DOWN, ord("j")):
                NOTE["bsel"] = min(max(0, len(blocks) - 1), NOTE["bsel"] + 1)
            elif ch in (ord("t"), ord("T")):
                n_add_block("text")
            elif ch in (ord("l"), ord("L")):
                n_add_block("list")
            elif ch in (ord("f"), ord("F")):
                n_add_block("float")
            elif ch in (ord("r"), ord("R")):
                if n is not None:
                    NOTE["titling"] = True; NOTE["buf"] = str(n.get("title") or "")
            elif ch in (ord("d"), ord("D")):
                if blocks and 0 <= NOTE["bsel"] < len(blocks):
                    if n_block_empty(blocks[NOTE["bsel"]]):
                        del blocks[NOTE["bsel"]]           # leer → sofort weg
                        NOTE["bsel"] = min(NOTE["bsel"], max(0, len(blocks) - 1))
                        n_save()
                    else:
                        NOTE["bconfirm"] = True; NOTE["msg"] = ""  # befüllt → nachfragen
            elif ch in (ord("e"), 10, 13, curses.KEY_ENTER):
                if blocks and 0 <= NOTE["bsel"] < len(blocks):
                    NOTE["layer"] = 2
                    blk = blocks[NOTE["bsel"]]
                    if blk["type"] in ("list", "float"):
                        seq = blk.get("items") if blk["type"] == "list" else blk.get("terms")
                        NOTE["esel"] = len(seq or [])       # auf den 'neu'-Slot
                    else:
                        NOTE["esel"] = 0
                    NOTE["buf"] = ""
        else:                                               # ── Ebene 2: Block bearbeiten ──
            blk = blocks[NOTE["bsel"]] if (blocks and 0 <= NOTE["bsel"] < len(blocks)) else None
            if blk is None:
                NOTE["layer"] = 1
            elif blk["type"] == "text":
                if ch == 27:
                    n_save(); NOTE["layer"] = 1
                elif ch in (10, 13, curses.KEY_ENTER):
                    blk["text"] = blk.get("text", "") + "\n"
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    blk["text"] = blk.get("text", "")[:-1]
                elif 32 <= ch <= 126:
                    blk["text"] = blk.get("text", "") + chr(ch)
            elif blk["type"] == "list":
                items = blk.setdefault("items", [])
                if ch == 27:
                    n_commit_list(blk); n_save(); NOTE["layer"] = 1
                elif ch in (10, 13, curses.KEY_ENTER):
                    n_commit_list(blk)
                    NOTE["esel"] = len(blk["items"]); NOTE["buf"] = ""
                elif ch == curses.KEY_UP:
                    n_commit_list(blk)
                    NOTE["esel"] = max(0, NOTE["esel"] - 1); n_loadbuf(blk)
                elif ch == curses.KEY_DOWN:
                    n_commit_list(blk)
                    NOTE["esel"] = min(len(blk["items"]), NOTE["esel"] + 1); n_loadbuf(blk)
                elif ch == 9:                               # Tab → haken
                    if NOTE["esel"] < len(items):
                        items[NOTE["esel"]]["done"] = not items[NOTE["esel"]].get("done")
                        n_save()
                elif ch == curses.KEY_DC:                   # Entf → weg
                    if NOTE["esel"] < len(items):
                        del items[NOTE["esel"]]
                        NOTE["esel"] = min(NOTE["esel"], len(items)); n_loadbuf(blk); n_save()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if NOTE["buf"]:
                        NOTE["buf"] = NOTE["buf"][:-1]
                    elif NOTE["esel"] < len(items):
                        del items[NOTE["esel"]]
                        NOTE["esel"] = min(NOTE["esel"], len(items)); n_loadbuf(blk); n_save()
                elif 32 <= ch <= 126:
                    NOTE["buf"] += chr(ch)
            elif blk["type"] == "float":
                terms = blk.setdefault("terms", [])
                if ch == 27:
                    n_commit_float(blk); n_save(); NOTE["layer"] = 1
                elif ch in (10, 13, curses.KEY_ENTER):
                    n_commit_float(blk)
                    NOTE["esel"] = len(blk["terms"]); NOTE["buf"] = ""
                elif ch in (curses.KEY_LEFT, curses.KEY_UP):
                    n_commit_float(blk)
                    NOTE["esel"] = max(0, NOTE["esel"] - 1); n_loadbuf(blk)
                elif ch in (curses.KEY_RIGHT, curses.KEY_DOWN):
                    n_commit_float(blk)
                    NOTE["esel"] = min(len(blk["terms"]), NOTE["esel"] + 1); n_loadbuf(blk)
                elif ch == curses.KEY_DC:
                    if NOTE["esel"] < len(terms):
                        del terms[NOTE["esel"]]
                        NOTE["esel"] = min(NOTE["esel"], len(terms)); n_loadbuf(blk); n_save()
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    if NOTE["buf"]:
                        NOTE["buf"] = NOTE["buf"][:-1]
                    elif NOTE["esel"] < len(terms):
                        del terms[NOTE["esel"]]
                        NOTE["esel"] = min(NOTE["esel"], len(terms)); n_loadbuf(blk); n_save()
                elif 32 <= ch <= 126:
                    NOTE["buf"] += chr(ch)

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
            if NOTE["confirm"]:
                addclip(bottom, ix, "wirklich löschen? j/n", iw, C["bright"])
            else:
                addclip(bottom, ix, ("enter öffnen · n neu · d löschen · esc zu  " + NOTE["msg"]).strip(),
                        iw, C["faint"])
            return

        n = NOTE["note"]                              # ── eine Notiz ──
        if not n:
            addclip(by + 1, ix, "keine notiz (backend erreichbar?)", iw, C["faint"])
            return
        if NOTE["titling"]:
            addclip(by + 1, ix, "titel: " + NOTE["buf"] + "_", iw, C["bright"])
        else:
            addclip(by + 1, ix, str(n.get("title") or "ohne titel"), iw - 10, C["bright"])
            safe_addstr(by + 1, bx + bw - 11, "[r titel]", C["faint"])
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
            addclip(area_top, ix, "leer — t text · l liste · f float", iw, C["faint"])
        for bi, (blk, ry, rh, editing) in enumerate(layout):
            sy = area_top + ry - NOTE["scroll"]
            if sy + rh - 1 < area_top or sy > area_bottom:
                continue
            n_drawblock(blk, sy, rh, bi == NOTE["bsel"], editing, ix, iw, area_top, area_bottom)

        if NOTE["bconfirm"]:
            tip = "block löschen? j/n"
        elif NOTE["layer"] == 2 and blocks:
            tip = {"text": "tippen · enter zeile · esc fertig",
                   "list": "tippen · enter neu · tab haken · entf weg · esc fertig",
                   "float": "tippen · enter setzen · ←→ wählen · entf weg · esc fertig"
                   }.get(blocks[NOTE["bsel"]]["type"], "esc fertig")
        else:
            tip = "↑↓ block · t/l/f neu · e bearb · d weg · n übersicht · esc zu"
        addclip(by + bh - 2, ix, (tip + ("  " + NOTE["msg"] if NOTE["msg"] else "")).strip(),
                iw, C["faint"])
