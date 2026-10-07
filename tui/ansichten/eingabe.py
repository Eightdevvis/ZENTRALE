# tui/ansichten/eingabe.py
#
# Das Eingabefeld des KI-Chats als reine Funktionen: Text + Cursor rein,
# Text + Cursor raus. Kein curses, kein Zustand — damit testbar
# (tests/test_chat_eingabe.py), und damit chat.py nur noch Tasten auf diese
# Funktionen verteilt.
#
# Bis 07.10.2026 war die Chat-Eingabe eine Zeile, nur ASCII, ohne Cursor
# (Claude-Web-Plan, Phase 1). Sasha schreibt Deutsch — Umlaute gingen nicht.
#
# Regeln (auch in memory/system/tui_bauplan.md):
#   ←→         Cursor um ein Zeichen
#   Pos1/Ende  Anfang/Ende der Zeile, in der der Cursor steht (auch Strg+A/E)
#   ⌫ / Entf   löscht vor / unter dem Cursor
#   Alt+Enter  neue Zeile; Enter schickt ab
#   ↑↓         EINZEILIG (kein Zeilenumbruch drin): scrollen den Verlauf, wie
#              bisher. MEHRZEILIG: bewegen den Cursor zwischen den Zeilen —
#              den Verlauf scrollen dann Bild↑/Bild↓.
#
# Zeichen kommen als Bytes (getch, nicht get_wch): die Hauptschleife liefert
# allen Ansichten Ganzzahlen, und auf get_wch umzustellen hieße, jede Ansicht
# anzufassen. Ein Umlaut kommt deshalb als zwei Bytes und wird hier
# zusammengesetzt (utf8_byte) — derselbe Weg wie im Post-Antwort-Editor.

GRENZE = 4000          # Zeichen; mehrzeilig darf es mehr sein als die alten 1000
HOEHE = 5              # so viele Zeilen wächst das Feld, dann scrollt es


# ── Text bearbeiten: (text, pos) → (text, pos) ─────────────────────────

def einfuegen(text, pos, s, grenze=GRENZE):
    """s an der Cursorstelle einfügen (gekappt auf die Grenze)."""
    platz = max(0, grenze - len(text))
    s = s[:platz]
    return text[:pos] + s + text[pos:], pos + len(s)


def zurueck(text, pos):
    """Backspace: das Zeichen VOR dem Cursor weg."""
    if pos <= 0:
        return text, 0
    return text[:pos - 1] + text[pos:], pos - 1


def entfernen(text, pos):
    """Entf: das Zeichen UNTER dem Cursor weg."""
    return text[:pos] + text[pos + 1:], pos


def links(text, pos):
    return text, max(0, pos - 1)


def rechts(text, pos):
    return text, min(len(text), pos + 1)


def zeilenanfang(text, pos):
    return text, text.rfind("\n", 0, pos) + 1


def zeilenende(text, pos):
    ende = text.find("\n", pos)
    return text, len(text) if ende < 0 else ende


def mehrzeilig(text):
    """Hat die Eingabe einen Zeilenumbruch? Dann gehören ↑↓ dem Cursor."""
    return "\n" in text


def _zeile_spalte(text, pos):
    anfang = text.rfind("\n", 0, pos) + 1
    return text.count("\n", 0, pos), pos - anfang


def _pos_von(text, zeile, spalte):
    zeilen = text.split("\n")
    zeile = max(0, min(zeile, len(zeilen) - 1))
    vorher = sum(len(z) + 1 for z in zeilen[:zeile])
    return vorher + min(spalte, len(zeilen[zeile]))


def hoch(text, pos):
    """Eine Zeile nach oben, Spalte halten (so weit die Zeile reicht).
    In der ersten Zeile: an den Anfang."""
    zeile, spalte = _zeile_spalte(text, pos)
    if zeile == 0:
        return text, 0
    return text, _pos_von(text, zeile - 1, spalte)


def runter(text, pos):
    """Eine Zeile nach unten, Spalte halten. In der letzten: ans Ende."""
    zeile, spalte = _zeile_spalte(text, pos)
    if zeile >= text.count("\n"):
        return text, len(text)
    return text, _pos_von(text, zeile + 1, spalte)


# ── Bytes und Tasten deuten ────────────────────────────────────────────

def utf8_byte(puffer, ch):
    """Ein Byte (128–255) aus getch an den Puffer hängen. -> (puffer, zeichen)
    zeichen ist der fertige Buchstabe, sobald er vollständig ist, sonst None.
    Ein kaputtes Stück wird nach 4 Bytes verworfen statt ewig zu warten."""
    puffer = puffer + bytes([ch & 0xFF])
    try:
        return b"", puffer.decode("utf-8")
    except UnicodeDecodeError:
        return (puffer if len(puffer) < 4 else b""), None


def druckbar(zeichen):
    """Darf das ins Feld? Steuerzeichen nicht (Tab wird zu Leerzeichen)."""
    return zeichen == "\t" or (zeichen >= " " and zeichen != "\x7f")


# 343 = curses.KEY_ENTER (hier ohne curses-Import, damit testbar)
ENTER_CODES = (10, 13, 343)


def esc_folge(folge, enter=ENTER_CODES):
    """Was nach einem ESC kam (Tasten, die innerhalb von 50 ms folgten).
    -> "esc" (allein stehend), "alt_enter" oder None (andere Alt-Taste —
    nichts tun). Alt+Enter schickt das Terminal als ESC + CR/LF."""
    if not folge:
        return "esc"
    if len(folge) == 1 and folge[0] in enter:
        return "alt_enter"
    return None


# ── Anzeige ────────────────────────────────────────────────────────────

def anzeige(text, pos, breite, hoehe=HOEHE):
    """Die Eingabe auf Bildschirmzeilen der Breite `breite` umbrechen (harte
    Zeilen bei '\\n', weiche bei voller Breite) und so ausschneiden, dass der
    Cursor sichtbar ist. -> (zeilen, cur_y, cur_x, oben); cur_y zählt in
    `zeilen`, oben = wie viele Zeilen darüber gerade nicht zu sehen sind.

    Breite = Zeichenzahl: Umlaute sind eine Zelle breit. Doppelt breite
    Zeichen (Emoji, CJK) verrutschen den Cursor optisch — selten im Chat,
    und eine Breiten-Tabelle wäre hier mehr Code als Nutzen."""
    breite = max(1, breite)
    zeilen, cur = [], (0, 0)
    start = 0
    for logisch in text.split("\n"):
        stuecke = [logisch[i:i + breite] for i in range(0, len(logisch), breite)] or [""]
        for k, stueck in enumerate(stuecke):
            von = start + k * breite
            bis = von + len(stueck)
            letzte = k == len(stuecke) - 1
            # Cursor gehört in dieses Stück; am Ende eines VOLLEN Stücks,
            # das weitergeht, steht er schon am Anfang des nächsten.
            if von <= pos < bis or (pos == bis and letzte):
                cur = (len(zeilen), pos - von)
            zeilen.append(stueck)
        start += len(logisch) + 1
    # Cursor am Ende einer voll belegten Zeile: eine leere Zeile dahinter,
    # sonst stünde er außerhalb des Felds.
    if cur[1] >= breite:
        zeilen.insert(cur[0] + 1, "")
        cur = (cur[0] + 1, 0)
    # Fenster so, dass die Cursorzeile die unterste sichtbare ist, solange
    # das Feld voll ist — beim Tippen am Ende (der Normalfall) sieht man so
    # immer die letzten Zeilen.
    hoehe = max(1, hoehe)
    oben = max(0, cur[0] - hoehe + 1)
    return zeilen[oben:oben + hoehe], cur[0] - oben, cur[1], oben
