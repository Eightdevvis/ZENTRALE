# tui/ansichten/befehle.py
#
# Die Befehlszeile der TUI: '/' öffnet sie in jedem Fenster, eine Live-Liste
# klappt nach oben auf und filtert mit jedem Buchstaben, Enter führt aus.
# Hier stehen die Befehle, die Tastenhilfe je Fenster (TUI_KEYS/CTX_KEYS —
# die EINZIGE Wahrheit über die Belegung, siehe memory/system/tastatur.md),
# die reine Logik (parse_command, overlay_rows; ohne curses, testbar) und der
# Zustand der Zeile (Befehlszeile). Was ein Befehl BEWIRKT (Theme, Cloud,
# Neustart, Hot Reload …), entscheidet die Hauptschleife in zentrale_tui.py —
# dafür muss man alles kennen, das ist ihr Job.
# Bis 06.10.2026 lag das in zentrale_tui.py, siehe memory/system/tui_bauplan.md.

import curses


# ── Befehlszeile: pure Logik (curses-frei, daher unit-testbar) ───────────────
TUI_COMMANDS = [
    ("/help",  "alle Befehle und Tasten zeigen"),
    ("/theme", "Theme: auto | hell | dunkel  (auch 't')"),
    ("/cloud", "Cloud-Drossel: on | off  (Datenschutz/Kosten)"),
    ("/local", "Lokale KI drosseln: on | off  (Ollama-Leitung)"),
    ("/tutor", "Sprach-Tutor TEXT-panel (Mitte, Cloud/Qwen); 'u' öffnet das Zimmer-Fenster"),
    ("/lauf",  "stdout-Laufschrift: an | aus  (auch 's')"),
    ("/dashboard", "altes 3-Spalten-Dashboard: an | aus  (aus = Meta-Rad)"),
    ("/reload", "nur die TUI mit neuem Code laden (passiert bei Code-Änderung auch von selbst)"),
    ("/reboot", "ZENTRALE neu starten: Backend + Fenster, neuer Code"),
    ("/quit",  "ZENTRALE-TUI wirklich beenden  ('q' legt das Fenster nur weg)"),
]
TUI_KEYS = [
    ("←→",    "Startseite: das gewählte Rad drehen — vorn steht die App, die enter öffnet"),
    ("alt+←→", "Startseite: das Rad wechseln (apps | technik), die Galaxie dreht mit"),
    ("enter", "Startseite: die App vorn im gewählten Rad öffnen"),
    ("esc",   "zurück, Stufe für Stufe bis zur Startseite; dort klappt esc ZENTRALE zu (wie $mod+z)"),
    # Die Apps im Rad — seit 02.10.2026 nicht mehr per Buchstabe,
    # sondern übers Rad (Sasha). Links steht deshalb der Name im Rad.
    ("graph", "Graph-Werkzeug (Mitte): anlegen / eintragen · p vorhersage-ergänzung · r tages-reminder"),
    ("notizen", "Notizen (Mitte): freie notiz aus blöcken · ↑↓ block · t/l/f text/liste/float · e bearbeiten · d weg (fragt bei inhalt) · r titel · n übersicht · esc speichern & zu"),
    ("karte", "Karte (Mitte): pan ↑↓←→/hjkl · zoom +/− · 0 reset · Alt+↑↓←→ Land fokussieren · o=Overlay (Handel→Politik→aus) · ,/. Zeit ←→ · ; jetzt · w=Fenster"),
    ("kalender", "Kalender (Mitte), bedienbar wie calcurse: v dreht A Tagesliste → B Monat → C Woche · a neu · e ändern (Kasten) · d löschen · r wiederholen · enter ansehen · c/p kopieren · t/w/m/y springen · g gehe zu · x erledigte · in A tab zwischen Terminen/Kalender/TODO"),
    ("post", "Post/Mail (Mitte): enter rein · e eingang (neu/ungelesen, ●=ungelesen) · f abhaken (gelesen+einsortieren) · lesen: ←→ vor/zurück, ↓ ausklappen/scrollen, ↑ scrollen · v lesen/liste · a antw · s einsort · d lösch · x abgleich · esc zurück"),
    ("space", "KI-Chat (Mitte): tippen + enter fragt die KI · alt+enter oder \\ + enter neue zeile · ←→ home end del: cursor · ↑↓ scrollen (in mehrzeiliger eingabe: zeile wechseln, dann pgup/pgdn) · ctrl+c stoppt eine laufende antwort · esc schließt (die antwort läuft weiter, ● wenn fertig) · /help im chat: /new /chats /model /provider /effort /budget /local /cloud /auto"),
    ("tutor", "Persona-Zimmer (eigenes fenster): die person wohnt drin, läuft rum, redet mit stimme · tippen+enter im fenster · Alt+M stumm · ohne DISPLAY → text-panel · /tutor = text-panel"),
    ("fokus", "Fokus (Mitte): oben projekte, drunter alle listen · enter reindiven · a/s neu · space abhaken · r name · d weg · p projekt · f setzt den knoten als alleinigen fokus (rendert dann allein in der FOCUS-box) · m/> verschieben"),
    ("klavier", "Klavier (Mitte): die Tastatur IST die Klaviatur — y x c v b n m , . - weiß, s d g h j l ö schwarz · ←→ oktave · space nimmt eine melodie auf (fragt beim stoppen nach dem namen) · ↑↓ melodie wählen · enter abspielen · r umbenennen · D löschen · k/esc zu"),
    ("/",   "Befehlszeile öffnen"),
]

# Kontext-Tasten: was im gerade fokussierten Fenster geht. EINE Tabelle für
# zwei Anzeigen: das '/'-Overlay UND die Fußleiste ganz unten
# (fussleiste.py). Seit 07.10.2026 (Sasha: „die leiste zeigt NUR das an was
# auch tatsächlich in dem modus grad genommen werden kann") prüft
# tests/test_fussleiste.py für JEDEN Eintrag, dass die Taste im Fenster
# wirklich etwas tut — eine Zeile hier, die nicht stimmt, macht den Test rot.
# Beschriftung englisch (Sasha, 07.10.2026); welche Codes eine Beschriftung
# meint, liest fussleiste.codes(). '/…'-Einträge sind Befehle der
# Befehlszeile, keine Tasten (die Fußleiste zeigt sie nicht).
# Schlüssel = Kontext aus current_ctx().
CTX_KEYS = {
    "home": [
        ("←→", "turn"), ("alt+←→", "wheel"),
        ("enter", "open"), ("space", "ai chat"), ("esc", "hide"),
        ("/dashboard", "old dashboard"), ("/theme", "theme"),
        ("/lauf", "stdout ticker"), ("/quit", "quit"),
    ],
    "technik": [
        ("esc", "back"),
    ],
    "elektronik": [
        ("esc", "back"),
    ],
    "note:edit": [
        ("↑↓", "block"), ("t/l/f", "new text/list/float"),
        ("e/enter", "edit"), ("d", "delete block"), ("r", "title"),
        ("n", "overview"), ("esc", "save & close"),
    ],
    "note:list": [
        ("↑↓", "select"), ("enter", "open"), ("n", "new"),
        ("d", "delete"), ("esc", "back"),
    ],
    "piano": [
        ("y x c v b n m , . -", "white keys"), ("s d g h j l", "black keys"),
        ("←→", "octave"), ("⌫", "undo note"), ("space", "record"),
        ("↑↓", "melody"), ("enter", "play / stop"),
        ("r", "rename"), ("D", "delete melody"),
        ("L", "lights"), ("t", "theme"), ("k/esc", "close"),
    ],
    "tutor": [
        ("enter", "start / talk"), ("/lang", "language"),
        ("/provider", "provider"), ("/model", "model"),
        ("/models", "models"), ("/tutorstop", "stop"),
        ("↑↓", "scroll"), ("esc", "close"),
    ],
    "graph": [
        ("↑↓", "select"), ("enter", "open"),
        ("n", "new"), ("p", "predict"), ("r", "reminder"),
        ("d", "delete"), ("esc", "close"),
    ],
    "list:forest": [
        ("↑↓", "select"), ("enter", "open / check"), ("s", "open + add"),
        ("n", "new list"), ("f", "focus"), ("r", "rename"), ("p", "project"),
        ("m", "move item"), (">", "place"), ("d", "delete"), ("esc/l", "close"),
    ],
    "list:view": [
        ("enter", "open / check"), ("space", "check"), ("a/s", "add"),
        ("r", "rename"), ("p", "project"), ("f", "focus"), (">", "place"),
        ("m", "move out"), ("d", "delete"), ("esc", "back"),
    ],
    "list:pick": [
        ("↑↓", "select"), ("enter", "take"), ("esc", "cancel"),
    ],
    "map": [
        ("↑↓←→", "pan"), ("+/-", "zoom"), ("0", "reset"),
        ("alt+↑↓←→", "focus country"),
        ("o", "overlay"), ("w", "window"), ("esc", "close"),
    ],
    # Kalender (seit 07.10.2026 nur noch A/B/C, alle wie calcurse bedienbar;
    # Belegung von der KALENDER-Sitzung, hier nur englisch beschriftet)
    "cal:a:termine": [
        ("↑↓", "entry"), ("←→", "day"), ("a", "new"), ("e", "edit"),
        ("d", "delete"), ("r", "repeat"), ("enter", "view"),
        ("c/p", "copy/paste"), ("t/w/m/y", "day/week/month/year (caps: back)"),
        ("g", "go to"), ("x", "show done"), ("tab", "box"),
        ("v", "view"), ("esc", "close"),
    ],
    "cal:a:kalender": [
        ("←→", "day"), ("↑↓", "week"), ("0/$", "week start/end"),
        ("a", "new"), ("enter", "to entries"), ("tab", "box"), ("esc", "close"),
    ],
    "cal:a:todo": [
        ("↑↓", "select"), ("a", "new"), ("e", "edit"), ("d", "delete"),
        ("!", "done"), ("+/-", "up/down"), ("tab", "box"), ("esc", "close"),
    ],
    "cal:b": [
        ("←→", "day"), ("↑↓", "week"), ("tab", "entry of day"), ("a", "new"),
        ("e", "edit"), ("d", "delete"), ("r", "repeat"), ("enter", "view"),
        ("c/p", "copy/paste"), ("m/M", "month"), ("g", "go to"),
        ("v", "view"), ("esc", "close"),
    ],
    "cal:c": [
        ("↑↓", "entry"), ("←→", "day"), ("a", "new"), ("e", "edit"),
        ("d", "delete"), ("r", "repeat"), ("enter", "view"),
        ("c/p", "copy/paste"), ("w/W", "week"), ("g", "go to"),
        ("v", "view"), ("esc", "close"),
    ],
    "mail:cats": [
        ("↑↓", "select"), ("enter", "open"), ("e", "inbox"), ("r", "poll"),
        ("x", "reconcile"), ("z", "recount"), ("esc", "close"),
    ],
    "mail:list": [
        ("↑↓", "select"), ("enter", "read"), ("a", "reply"),
        ("s", "sort in"), ("d", "delete"), ("x", "reconcile"),
        ("z", "recount"), ("esc", "back"),
    ],
    "mail:read": [
        ("←→", "prev/next"), ("↓", "expand/scroll"), ("↑", "scroll/fold"),
        ("a", "reply"), ("s", "sort in"), ("d", "delete"),
        ("v", "list"), ("x", "reconcile"), ("z", "recount"), ("esc", "back"),
    ],
    # Im Eingang: f hakt ab (gelesen + einsortieren), löschen geht erst danach.
    "mail:list:eingang": [
        ("↑↓", "select"), ("enter", "read"), ("f", "done"), ("a", "reply"),
        ("s", "sort in"), ("x", "reconcile"), ("z", "recount"), ("esc", "back"),
    ],
    "mail:read:eingang": [
        ("←→", "prev/next"), ("↓", "expand/scroll"), ("↑", "scroll/fold"),
        ("f", "done"), ("a", "reply"), ("s", "sort in"),
        ("v", "list"), ("x", "reconcile"), ("z", "recount"), ("esc", "back"),
    ],
}
CTX_TITLES = {
    "home": "start", "graph": "graph", "list:forest": "fokus",
    "list:view": "liste", "list:pick": "einordnen", "map": "karte",
    "cal:a:termine": "kalender · termine", "cal:a:kalender": "kalender · monat",
    "cal:a:todo": "kalender · todo", "cal:b": "kalender · monat", "cal:c": "kalender · woche",
    "mail:cats": "post", "mail:list": "post · liste", "mail:read": "post · lesen",
    "mail:list:eingang": "post · eingang", "mail:read:eingang": "post · eingang",
    "elektronik": "elektronik",
    "ai": "ki-chat", "tutor": "tutor",
    "note:edit": "notiz", "note:list": "notizen", "piano": "klavier",
    "technik": "technik",
}


def parse_command(buf, theme_mode):
    """
    Wertet einen getippten Befehl aus. PURE Funktion (kein curses, kein State):
      (buf inkl. '/', aktuelles theme_mode) -> (action, neues theme_mode, msg)
    action: None | "QUIT" | "HELP".  msg: kurze Rückmeldung (z.B. Fehler).
    """
    parts = buf[1:].strip().split()
    if not parts:
        return None, theme_mode, ""
    name = parts[0].lower()
    arg = parts[1].lower() if len(parts) > 1 else None
    if name in ("quit", "q", "exit"):
        return "QUIT", theme_mode, ""
    if name in ("help", "h", "?"):
        return "HELP", theme_mode, ""
    if name in ("theme", "t"):
        mapping = {"hell": "day", "dunkel": "night", "day": "day",
                   "night": "night", "auto": "auto"}
        if arg in mapping:
            theme_mode = mapping[arg]
        else:                                   # ohne Arg: zyklieren wie 't'
            theme_mode = {"auto": "day", "day": "night", "night": "auto"}[theme_mode]
        return None, theme_mode, ""
    if name == "cloud":                          # Cloud-Kill-Switch (POST macht der Aufrufer)
        if arg in ("on", "an"):   return "CLOUD_ON", theme_mode, ""
        if arg in ("off", "aus"): return "CLOUD_OFF", theme_mode, ""
        return "CLOUD_TOGGLE", theme_mode, ""
    if name in ("local", "lokal", "ki"):         # Lokal-Kill-Switch (POST macht der Aufrufer)
        if arg in ("on", "an"):   return "LOCAL_ON", theme_mode, ""
        if arg in ("off", "aus"): return "LOCAL_OFF", theme_mode, ""
        return "LOCAL_TOGGLE", theme_mode, ""
    if name in ("tutor", "sprache"):             # Sprach-Tutor-Panel öffnen (Mitte)
        return "TUTOR_OPEN", theme_mode, ""
    if name in ("reload", "neuladen"):           # nur die TUI, neuer Code, Fenster bleibt
        return "RELOAD", theme_mode, ""
    if name in ("reboot", "neustart", "restart"):  # ganze ZENTRALE neu (Aufrufer beendet)
        return "REBOOT", theme_mode, ""
    if name in ("lauf", "laufschrift"):          # stdout-Laufschrift (Schalter macht der Aufrufer)
        if arg in ("on", "an"):   return "LAUF_ON", theme_mode, ""
        if arg in ("off", "aus"): return "LAUF_OFF", theme_mode, ""
        return "LAUF_TOGGLE", theme_mode, ""
    if name in ("dashboard", "dash"):            # altes 3-Spalten-Layout (Schalter macht der Aufrufer)
        if arg in ("on", "an"):   return "DASH_ON", theme_mode, ""
        if arg in ("off", "aus"): return "DASH_OFF", theme_mode, ""
        return "DASH_TOGGLE", theme_mode, ""
    return None, theme_mode, "unbekannter befehl: /" + name


def overlay_rows(cmd_buf, help_latched, ctx=None):
    """
    Welche Zeilen zeigt das Befehls-Overlay? PURE Funktion → (titel, rows).
    rows-Einträge: ("cmd", name, desc) | ("key", taste, desc) | ("sep",) |
    ("info", "", text).

    - '/help' (oder help_latched) → volle Hilfe inkl. globaler Tasten.
    - nacktes '/' → die Shortcuts des FOKUSSIERTEN Fensters (ctx) plus die
      globalen Slash-Befehle darunter. ctx = (titel, [(taste, desc), …]) oder
      None (dann nur die globalen Befehle).
    - '/<präfix>' → live-gefilterte Slash-Befehlsliste.
    """
    full = help_latched or cmd_buf.startswith("/help")
    if full:
        rows = [("cmd", n, d) for n, d in TUI_COMMANDS]
        rows += [("sep",)]
        rows += [("key", k, d) for k, d in TUI_KEYS]
        return "hilfe", rows
    pref = cmd_buf[1:].split(" ")[0].lower()
    if not pref:                       # nacktes '/': Kontext-Tasten + globale Befehle
        title, keys = ctx if ctx else ("befehle", [])
        rows = [("key", k, d) for k, d in keys]
        if keys:
            rows += [("sep",)]
        rows += [("cmd", n, d) for n, d in TUI_COMMANDS]
        return title, rows
    hits = [(n, d) for n, d in TUI_COMMANDS if n[1:].startswith(pref)]
    rows = [("cmd", n, d) for n, d in hits] or [("info", "", "kein treffer")]
    return "befehle", rows


class _OverlayScreen:
    """Adapter, der render_overlay_body die zwei Zeichen-Primitive reicht, ohne
    dass die Funktion curses kennt. In run_ui mit safe_addstr/addclip befuellt,
    im Test (tests/test_tui_overlay.py) mit einem Zell-Fake derselben Signatur
    → render_overlay_body ist als reine Bildfunktion pruefbar."""
    __slots__ = ("_fill", "_put")

    def __init__(self, fill, put):
        self._fill, self._put = fill, put

    def fill(self, y, x, n, ch, attr=0):
        self._fill(y, x, n, ch, attr)

    def put(self, y, x, text, maxw, attr=0):
        self._put(y, x, text, maxw, attr)


def render_overlay_body(scr, rows, ov_x, ov_y, ov_w, attrs):
    """Zeichnet die Innenzeilen des Befehls-Overlays — DECKEND.

    Curses kennt keine Z-Order/Opazitaet: der Body-stdout ist schon gezeichnet,
    wenn das Overlay drueberklappt. Wo eine Overlay-Zeile kuerzer war als die
    Kasten-Innenbreite, blieb frueher der stdout darunter stehen und „blutete"
    in den Kasten. Fix: JEDE Zeile zuerst ueber die volle Innenbreite blanken,
    erst dann den Inhalt drauf bestempeln.

    Curses-frei: zeichnet ausschliesslich ueber das scr-Adapterobjekt mit genau
    zwei Primitiven — fill(y,x,n,ch,attr) blankt n Zellen, put(y,x,text,maxw,attr)
    schreibt auf maxw gekuerzt. So 1:1 gegen einen Fake-Screen testbar.

    rows-Format wie overlay_rows(): ("cmd",name,desc) | ("key",taste,desc) |
    ("sep",) | ("info","",text). attrs mappt die Rollen acc/num/dim/faint.
    """
    inner_x = ov_x + 1            # erste Innenspalte (rechts vom linken Rahmen)
    inner_w = ov_w - 2            # Innenbreite zwischen den senkrechten Raendern
    for i, r in enumerate(rows):
        yy = ov_y + 1 + i
        if r[0] == "sep":
            # Trennlinie deckt die volle Innenbreite schon selbst ab
            scr.fill(yy, inner_x, inner_w, "─", attrs["faint"])
            continue
        # 1) deckend blanken  2) Inhalt drauf
        scr.fill(yy, inner_x, inner_w, " ", attrs["faint"])
        if r[0] == "cmd":
            scr.put(yy, ov_x + 2, r[1], 11, attrs["acc"])     # /dashboard passt
            scr.put(yy, ov_x + 14, r[2], ov_w - 16, attrs["dim"])
        elif r[0] == "key":
            scr.put(yy, ov_x + 2, r[1], 7, attrs["num"])
            scr.put(yy, ov_x + 10, r[2], ov_w - 12, attrs["dim"])
        else:                     # "info" / Fallback
            scr.put(yy, ov_x + 2, r[2], ov_w - 4, attrs["faint"])


class Befehlszeile:
    """Zustand und Zeichnen der Befehlszeile ('/', unten). Bis 06.10.2026
    vier lose Variablen in run_ui (cmd_mode, cmd_buf, help_latched,
    cmd_msg); die Hauptschleife liest und setzt sie jetzt hier.

    taste(ch) erledigt Tippen, Esc und Backspace selbst; bei Enter gibt sie
    das Ergebnis von parse_command zurück ("QUIT", "RELOAD", "CLOUD_ON" …),
    und die Hauptschleife führt es aus."""

    def __init__(self, z):
        self.z = z
        self.cmd_mode = False        # tippen wir gerade einen Befehl?
        self.cmd_buf = ""            # inkl. führendem '/'
        self.help_latched = False    # volle Hilfe stehen lassen (nach '/help')
        self.cmd_msg = ""            # kurze Rückmeldung (z.B. unbekannter Befehl)

    def oeffnen(self):
        """'/' außerhalb eines Freitext-Felds: Zeile auf, Rückmeldung weg."""
        self.cmd_mode = True; self.cmd_buf = "/"; self.cmd_msg = ""

    def taste(self, ch):
        """Eine Taste bei offener Zeile. -> Ergebnis von parse_command bei
        Enter (die Hauptschleife führt es aus), sonst None."""
        if ch == 27:                       # Esc → Befehl abbrechen
            self.cmd_mode = False; self.cmd_buf = ""
        elif ch in (10, 13, curses.KEY_ENTER):
            # parse_command bleibt eine reine Funktion (gut testbar): sie
            # rechnet nur den neuen Modus aus, geschrieben wird er hier.
            res, _neuer_modus, self.cmd_msg = parse_command(self.cmd_buf,
                                                            self.z.theme_mode_now())
            self.z.set_theme_mode(_neuer_modus)
            self.cmd_mode = False; self.cmd_buf = ""
            if res == "HELP":
                self.help_latched = True
            return res
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            self.cmd_buf = self.cmd_buf[:-1]
            if not self.cmd_buf:           # Slash weggelöscht → zu
                self.cmd_mode = False
        elif 32 <= ch <= 126 and len(self.cmd_buf) < 120:
            self.cmd_buf += chr(ch)
        return None

    def zeichne_overlay(self, ck, top, bot, W):
        """Das Befehls-Overlay (klappt über den Body nach oben auf), nur bei
        offener Zeile oder stehender Hilfe. ck = current_ctx() der Schleife."""
        if not (self.cmd_mode or self.help_latched):
            return
        z = self.z
        C, addclip, safe_addstr = z.C, z.addclip, z.safe_addstr
        ctx = (CTX_TITLES.get(ck, ck), CTX_KEYS.get(ck, [])) if ck else None
        ov_title, rows = overlay_rows(self.cmd_buf, self.help_latched, ctx)
        ov_w = min(W - 4, 56)
        ov_h = len(rows) + 2
        ov_x = 2
        ov_y = max(top, bot - ov_h + 1)
        z.draw_box(ov_y, ov_x, ov_h, ov_w, ov_title)
        # Innenzeilen ueber die testbare, DECKENDE Render-Funktion zeichnen.
        # Adapter reicht ihr curses-frei zwei Primitive: fill (= blanken via
        # safe_addstr) und put (= gekuerzt schreiben via addclip).
        ov_scr = _OverlayScreen(
            lambda y, x, n, ch, attr=0: safe_addstr(y, x, ch * max(0, n), attr),
            lambda y, x, text, maxw, attr=0: addclip(y, x, text, maxw, attr),
        )
        render_overlay_body(
            ov_scr, rows, ov_x, ov_y, ov_w,
            {"acc": C["acc"], "num": C["num"], "dim": C["dim"], "faint": C["faint"]},
        )

    def zeichne_zeile(self, input_row, W, erreichbar=True):
        """Die Zeile selbst (›): offener Befehl, sonst Rückmeldung oder Hinweis.
        erreichbar=False (Freitext-Fenster wie der Chat, 2026-10-07): dort
        öffnet '/' die Zeile nicht, also auch kein Hinweis darauf."""
        z = self.z
        C, addclip, safe_addstr = z.C, z.addclip, z.safe_addstr
        if self.cmd_mode:
            safe_addstr(input_row, 1, "›", C["acc"])
            shown = self.cmd_buf[-(W - 6):]
            addclip(input_row, 3, shown, W - 6, C["bright"])
            safe_addstr(input_row, 3 + len(shown), "_", C["bright"])
        else:
            safe_addstr(input_row, 1, "›", C["faint"])
            if self.cmd_msg:
                addclip(input_row, 3, self.cmd_msg, W - 6, C["warn"])
            else:
                safe_addstr(input_row, 3, "/ for commands" if erreichbar else "", C["faint"])
