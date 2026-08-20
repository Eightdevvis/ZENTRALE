# core/anwesenheit.py
#
# Ist Sasha da? Und schaut er ZENTRALE an?
#
# ── Warum das eine eigene Schicht ist ─────────────────────────────────
# Sasha, 20.08.2026:
#
#   "die anwesenheit wird per code assessed. maschine offen und an — ich
#    bin da. oder spaeter auch sensorik. dann kriegt die ai einfach nur ein
#    is da, is nich da."
#
# Das ist die richtige Arbeitsteilung. Ob jemand am Rechner sitzt, ist eine
# MESSUNG, keine Einschaetzung — ein Sprachmodell, das darueber spekuliert,
# spekuliert falsch und selbstbewusst. Es bekommt hier eine fertige Lage
# und entscheidet nur noch, WAS es damit sagt.
#
# Und es ist die Stelle, an der spaeter Sensorik andockt: ein PIR-Melder
# oder ein Mikrofon aendert `da()`, nicht den Prompt.
#
# ── Die drei Lagen ────────────────────────────────────────────────────
# Sashas Unterscheidung, woertlich:
#
#   OFFEN     "sasha hat zentrale offen. ungewiss ob er draufschaut."
#             → sie kann direkt mitteilen, worum es geht.
#   WOANDERS  "sasha hat zentrale zu. er arbeitet an anderem auf der
#             maschine."
#             → sie muss erst Aufmerksamkeit holen: Benachrichtigung.
#   WEG       niemand an der Maschine.
#             → melden trotzdem (er sieht es, wenn er zurueckkommt), aber
#               keine Frage stellen, auf die jemand antworten muesste.
#
# UNBEKANNT ist die vierte und wird bewusst nicht weggerundet: ohne X, ohne
# i3, auf dem Pi. Wer nicht weiss, ob jemand da ist, behandelt ihn wie
# anwesend-aber-abgewandt — lieber einmal zu viel gemeldet als eine
# Erinnerung verschluckt.

from __future__ import annotations

import ctypes
import ctypes.util
import os
import shutil
import subprocess

# Ab wann gilt die Maschine als unbenutzt. Zehn Minuten sind bewusst
# grosszuegig: wer liest, tippt nicht — eine knappe Schwelle wuerde ihn
# mitten im Lesen fuer abwesend erklaeren.
LEERLAUF_MIN = int(os.environ.get("ZENTRALE_LEERLAUF_MIN", "10"))

# Sperrprogramme, die NUR waehrend der Sperre laufen. Der Unterschied ist
# entscheidend und hat mich beim ersten Versuch reingelegt: `light-locker`
# steht in Sashas Autostart und laeuft DAUERND. Ein pgrep darauf meldete
# "gesperrt", solange die Maschine an war — sie haette ihn permanent fuer
# abwesend gehalten. Daemons gehoeren also NICHT in diese Liste.
_SPERREN = ("i3lock", "xsecurelock", "swaylock")

OFFEN, WOANDERS, WEG, UNBEKANNT = "offen", "woanders", "weg", "unbekannt"

_SAETZE = {
    OFFEN:     "Sasha hat ZENTRALE offen. Ungewiss, ob er gerade draufschaut.",
    WOANDERS:  "Sasha ist an der Maschine, hat ZENTRALE aber zu — er arbeitet "
               "gerade an etwas anderem.",
    WEG:       "Sasha ist nicht an der Maschine.",
    UNBEKANNT: "Ob Sasha an der Maschine ist, laesst sich gerade nicht "
               "feststellen.",
}


class _Info(ctypes.Structure):
    _fields_ = [("window", ctypes.c_ulong), ("state", ctypes.c_int),
                ("kind", ctypes.c_int), ("til_or_since", ctypes.c_ulong),
                ("idle", ctypes.c_ulong), ("eventMask", ctypes.c_ulong)]


def leerlauf_ms() -> int | None:
    """Wie lange nichts mehr eingegeben wurde. None = nicht feststellbar.

    Ueber die XScreenSaver-Erweiterung per ctypes, nicht ueber ein externes
    Programm: `xprintidle` ist auf dieser Maschine nicht installiert, und
    eine Abhaengigkeit, die man erst nachinstallieren muss, faellt genau
    dann aus, wenn niemand hinschaut.
    """
    try:
        x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
        xss = ctypes.CDLL(ctypes.util.find_library("Xss"))
        x11.XOpenDisplay.restype = ctypes.c_void_p
        anzeige = x11.XOpenDisplay(None)
        if not anzeige:
            return None
        try:
            xss.XScreenSaverAllocInfo.restype = ctypes.POINTER(_Info)
            info = xss.XScreenSaverAllocInfo()
            wurzel = x11.XDefaultRootWindow(ctypes.c_void_p(anzeige))
            if not xss.XScreenSaverQueryInfo(ctypes.c_void_p(anzeige),
                                             ctypes.c_ulong(wurzel), info):
                return None
            return int(info.contents.idle)
        finally:
            x11.XCloseDisplay(ctypes.c_void_p(anzeige))
    except Exception:
        return None


def _sitzung() -> str | None:
    """Die id der grafischen Sitzung (z.B. "c2").

    Aus der Umgebung, wenn sie da ist. Als systemd-Benutzerdienst ist sie
    das NICHT — dann fragen wir logind nach der Sitzung dieses Benutzers.
    Ohne diesen zweiten Weg funktionierte die Sperr-Erkennung ausgerechnet
    dort nicht, wo ZENTRALE als Systemeinheit laeuft.
    """
    aus_umgebung = os.environ.get("XDG_SESSION_ID")
    if aus_umgebung:
        return aus_umgebung
    if not shutil.which("loginctl"):
        return None
    try:
        import getpass
        roh = subprocess.run(
            ["loginctl", "show-user", getpass.getuser(), "-p", "Display"],
            capture_output=True, text=True, timeout=3)
        wert = roh.stdout.strip().split("=", 1)
        return wert[1] or None if len(wert) == 2 else None
    except Exception:
        return None


def gesperrt() -> bool:
    """Ist der Bildschirm gesperrt? Dann ist er weg, Punkt.

    Zuerst logind: `LockedHint` ist die Auskunft der Sitzungsverwaltung
    selbst und stimmt fuer jeden Sperrer, der sich ordentlich anmeldet
    (light-locker tut das). Erst wenn es die nicht gibt, wird nach
    Prozessen gesucht — und nur nach solchen, die es waehrend der Sperre
    ueberhaupt nur gibt.
    """
    sitzung = _sitzung()
    if sitzung and shutil.which("loginctl"):
        try:
            roh = subprocess.run(
                ["loginctl", "show-session", sitzung, "-p", "LockedHint"],
                capture_output=True, text=True, timeout=3)
            if "LockedHint=yes" in roh.stdout:
                return True
            if "LockedHint=no" in roh.stdout:
                return False
        except Exception:
            pass
    if not shutil.which("pgrep"):
        return False
    for name in _SPERREN:
        try:
            if subprocess.run(["pgrep", "-x", name], timeout=3,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode == 0:
                return True
        except Exception:
            continue
    return False


def da() -> bool | None:
    """Sitzt jemand an der Maschine? None = nicht feststellbar.

    Genau die Frage, die Sasha stellen wollte — "is da, is nich da". Was
    sie beantwortet, darf sich aendern (heute Leerlaufzeit, spaeter
    Sensorik), ohne dass irgendwo sonst etwas angefasst werden muss.
    """
    if gesperrt():
        return False
    ms = leerlauf_ms()
    if ms is None:
        return None
    return ms < LEERLAUF_MIN * 60_000


def lage() -> str:
    """OFFEN | WOANDERS | WEG | UNBEKANNT — die Lage in einem Wort."""
    anwesend = da()
    if anwesend is False:
        return WEG
    try:
        import melden
        sichtbar = melden.sichtbar()
    except Exception:
        sichtbar = None
    if sichtbar is True:
        return OFFEN
    if anwesend is None and sichtbar is None:
        return UNBEKANNT
    # Anwesend (oder unbekannt) und ZENTRALE nicht sichtbar: er ist bei
    # etwas anderem. Dieselbe Behandlung fuer "unbekannt" ist Absicht —
    # lieber einmal zu viel gemeldet als eine Erinnerung verschluckt.
    return WOANDERS


def satz(welche: str | None = None) -> str:
    """Die Lage als EIN Satz fuer die KI.

    Sie bekommt kein Messergebnis und keine Millisekunden — nur, woran sie
    ihr Verhalten ausrichten soll. Alles andere waere eine Einladung, ueber
    Leerlaufzeiten zu spekulieren.
    """
    return _SAETZE.get(welche or lage(), _SAETZE[UNBEKANNT])
