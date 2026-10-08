# tui/ansichten/zwischenablage.py
#
# Die Zwischenablage LESEN — für `/paste` und Strg+V im Chat (2026-10-08).
# Ohne curses und ohne HTTP, damit testbar (tests/test_zwischenablage.py,
# xclip als Attrappe). Schreiben (Antwort kopieren) steht in
# chat_bedienung.zwischenablage.
#
# Warum es das braucht: Sasha, 08.10.2026: „ich wollte jetzt mal nen bild in
# die ki reinpasten damit sie es sich anschaut aber da passiert nix." Ein
# Terminal fügt nur TEXT ein — liegt ein Bild in der Zwischenablage (CopyQ,
# flameshot), schickt Strg+Shift+V gar nichts, und die TUI kann das nicht
# einmal bemerken. Also fragt die TUI die Zwischenablage selbst: xclip unter
# X11, wl-paste unter Wayland. Nur auf Anfrage (/paste, Strg+V), nie im Takt
# der Schleife — ein Dauer-Abfragen wäre ein Prozess alle 250 ms.

import os
import shutil
import subprocess
from collections import namedtuple

# Was die KI als Bild liest (core/anhang.py, Anthropic/OpenAI) — in dieser
# Reihenfolge bevorzugt. CopyQ und flameshot bieten image/png an.
BILD_ARTEN = ("image/png", "image/jpeg", "image/webp", "image/gif")
ENDUNG = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
          "image/gif": ".gif"}
TEXT_ARTEN = ("UTF8_STRING", "text/plain;charset=utf-8", "text/plain", "STRING", "TEXT")
WARTEN_S = 3        # antwortet das Programm, dem die Ablage gehört, nicht: aufgeben

Inhalt = namedtuple("Inhalt", "art daten mime grund")
#   art "bild":  daten = Bytes (b"" wenn nur geprüft), mime = image/…
#   art "text":  daten = str
#   art "leer":  nichts drin
#   art "nein":  geht nicht — grund ist der Satz für Sasha


def programm(umgebung=None, finden=shutil.which):
    """("x11" | "wayland", None) oder (None, grund)."""
    u = os.environ if umgebung is None else umgebung
    if u.get("WAYLAND_DISPLAY") and finden("wl-paste"):
        return "wayland", None
    if u.get("DISPLAY"):
        if finden("xclip"):
            return "x11", None
        return None, "zwischenablage lesen geht nicht — xclip fehlt"
    if u.get("WAYLAND_DISPLAY"):
        return None, "zwischenablage lesen geht nicht — wl-paste fehlt"
    return None, "keine zwischenablage hier — die tui läuft ohne bildschirm (ssh?)"


def _befehl(art, mime):
    """Argumente fürs Lesen; mime None = die Liste der Arten."""
    if art == "wayland":
        return ["wl-paste", "--list-types"] if mime is None else \
            ["wl-paste", "--no-newline", "--type", mime]
    return ["xclip", "-selection", "clipboard", "-o", "-t", mime or "TARGETS"]


def _holen(art, mime, ausfuehren):
    """Bytes aus der Ablage, b"" wenn es diese Art nicht gibt. Wirft
    subprocess.TimeoutExpired / OSError weiter."""
    r = ausfuehren(_befehl(art, mime), stdin=subprocess.DEVNULL,
                   capture_output=True, timeout=WARTEN_S)
    return (r.stdout or b"") if r.returncode == 0 else b""


def lesen(umgebung=None, finden=shutil.which, ausfuehren=subprocess.run, bild_holen=True):
    """Was liegt in der Zwischenablage? -> Inhalt.

    bild_holen=False: bei einem Bild nur sagen, DASS eins da ist (Strg+V
    will nur den Hinweis, nicht Megabytes lesen)."""
    art, grund = programm(umgebung, finden)
    if art is None:
        return Inhalt("nein", None, None, grund)
    try:
        arten = _holen(art, None, ausfuehren).decode("utf-8", "replace").split()
        bild = next((m for m in BILD_ARTEN if m in arten), None)
        if bild:
            daten = _holen(art, bild, ausfuehren) if bild_holen else b""
            if bild_holen and not daten:
                return Inhalt("nein", None, None, "das bild ließ sich nicht lesen")
            return Inhalt("bild", daten, bild, None)
        fremd = next((m for m in arten if m.startswith("image/")), None)
        text_art = next((m for m in TEXT_ARTEN if m in arten), None)
        if fremd and not text_art:
            return Inhalt("nein", None, None, "das bild hat ein format, das die ki nicht "
                          "liest (%s) — png, jpg, webp oder gif gehen" % fremd[6:])
        if not text_art:
            return Inhalt("leer", None, None, None)
        text = _holen(art, text_art, ausfuehren).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return Inhalt("nein", None, None, "die zwischenablage antwortet nicht")
    except OSError:
        return Inhalt("nein", None, None, "zwischenablage lesen ging nicht")
    if not text:
        return Inhalt("leer", None, None, None)
    return Inhalt("text", text, None, None)


def groesse_text(n):
    """312 KB · 1,4 MB — wie man es auf einem Kärtchen liest."""
    if n < 1024 * 1024:
        return "%d KB" % max(1, round(n / 1024))
    return ("%.1f MB" % (n / 1024 / 1024)).replace(".", ",")
