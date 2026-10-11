# tui/ansichten/kalender_kasten.py
#
# Was die Kästen des Kalenders (Rückfrage, Formular, Advanced, „welche
# Liste?", Rhythmus, Stylebox, Farbwähler) für ihre Tastentabellen teilen
# (tasten.py, 2026-10-11): jeder Kasten hat EINE Tabelle, aus der er seine
# Tasten verteilt; der Kalender setzt sie mit Tasten.zusammen zu seiner
# Tabelle zusammen, damit die Leiste ganz unten auch im Kasten stimmt
# (vorher zeigte sie dort nichts, die Tasten standen im Kasten).
#
#   tippen_byte  Umlaute: curses liefert UTF-8 Byte für Byte, die Tabelle
#                kennt nur ASCII — wer Freitext nimmt, setzt die Bytes hier
#                zusammen, bevor die Tabelle verteilt.
#   zustand      repr eines Kastens mit allem, was drinsteckt (Fehlersuche;
#                die Tastentests sehen so, ob eine Taste etwas getan hat).
#   Stylebox und Farbwähler sind Bausteine mit eigener Tabelle
#   (tui/bausteine/tastenteil.py); der Kalender bindet sie direkt ein.


def tippen_byte(kasten, ch):
    """Ein Byte ≥ 0x80 eines UTF-8-Zeichens → das Zeichen, sobald es ganz
    ist (sonst None). Merkt sich das Angefangene in kasten._u8."""
    kasten._u8 = getattr(kasten, "_u8", b"") + bytes([ch])
    try:
        zeichen = kasten._u8.decode("utf-8")
    except UnicodeDecodeError:
        if len(kasten._u8) >= 4:
            kasten._u8 = b""
        return None
    kasten._u8 = b""
    return zeichen


def _rein(wert, tiefe, gesehen):
    if tiefe > 16:
        return "…"
    if isinstance(wert, dict):
        return {k: _rein(v, tiefe + 1, gesehen) for k, v in wert.items()}
    if isinstance(wert, (list, tuple)):
        return [_rein(v, tiefe + 1, gesehen) for v in wert]
    if hasattr(wert, "__dict__") and not callable(wert) and id(wert) not in gesehen:
        gesehen.add(id(wert))
        return (type(wert).__name__, _rein(vars(wert), tiefe + 1, gesehen))
    return wert


def zustand(kasten):
    """repr mit dem ganzen Zustand (Felder, offene Unterkästen …)."""
    return repr(_rein(kasten, 0, set()))
