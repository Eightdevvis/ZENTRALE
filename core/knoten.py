# core/knoten.py
#
# Die Knoten-Beschreibung dieses Geräts (memory/hub/knoten_beitritt.md,
# „1. Knoten-Beschreibung"): Name, Sorte, erkannte Hardware, Programm-Fassung.
# Klartext-Metadaten ohne Inhalt — die Cloud bekommt sie über
# PUT /v1/knoten/<name>. Hardware wird ERKANNT, nicht gefragt.
#
# Kein Terminal, kein Netz: hier wird nur beschrieben. Erkennen liest /proc
# und /sys; `sys_wurzel` lässt Tests eine erfundene Maschine hinlegen.

import datetime
import glob
import os
import shutil

import dateien
import port_types

SORTEN = ("gehirn", "vollknoten", "aussenposten", "medienknoten", "fremd")
_PROJEKT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _lies(pfad):
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def gpu(sys_wurzel="/") -> bool:
    """Eine Grafikkarte, die für lokale KI taugt: NVIDIA (Treiber geladen)
    oder AMD mit eigenem Speicher ≥ 2 GiB. Ein Chip im Prozessor zählt nicht."""
    if os.path.isdir(os.path.join(sys_wurzel, "proc/driver/nvidia")) or \
            (sys_wurzel == "/" and shutil.which("nvidia-smi")):
        return True
    for karte in glob.glob(os.path.join(sys_wurzel, "sys/class/drm/card[0-9]*/device")):
        if _lies(os.path.join(karte, "vendor")).strip() == "0x10de":
            return True
        vram = _lies(os.path.join(karte, "mem_info_vram_total")).strip()
        if vram.isdigit() and int(vram) >= 2 * 1024 ** 3:
            return True
    return False


def bildschirm(sys_wurzel="/", umgebung=None) -> bool:
    umgebung = os.environ if umgebung is None else umgebung
    if umgebung.get("DISPLAY") or umgebung.get("WAYLAND_DISPLAY"):
        return True
    for status in glob.glob(os.path.join(sys_wurzel, "sys/class/drm/card*-*/status")):
        if _lies(status).strip() == "connected":
            return True
    return False


def _pcm(sys_wurzel, art):
    return any(art in z for z in _lies(os.path.join(sys_wurzel, "proc/asound/pcm")).splitlines())


def mikro(sys_wurzel="/") -> bool:
    return _pcm(sys_wurzel, "capture")


def lautsprecher(sys_wurzel="/") -> bool:
    return _pcm(sys_wurzel, "playback")


def hardware(sys_wurzel="/", umgebung=None) -> dict:
    return {"gpu": gpu(sys_wurzel), "bildschirm": bildschirm(sys_wurzel, umgebung),
            "mikro": mikro(sys_wurzel), "lautsprecher": lautsprecher(sys_wurzel)}


def fassung(wurzel=_PROJEKT) -> str:
    """Die Programm-Fassung: VERSION (steht in jedem Paket, scripts/paket_bauen.py)
    oder, im Entwickler-Checkout, deploy/RELEASE + „-dev"."""
    v = _lies(os.path.join(wurzel, "VERSION")).strip()
    if v:
        return v
    r = _lies(os.path.join(wurzel, "deploy", "RELEASE")).strip()
    return (r or "0") + "-dev"


def beschreibung(sorte="vollknoten", sys_wurzel="/", umgebung=None, beigetreten=None,
                 wurzel=_PROJEKT) -> dict:
    jetzt = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    if sorte not in SORTEN:
        raise ValueError(f"Unknown node kind '{sorte}' ({', '.join(SORTEN)}).")
    return {"name": dateien.knoten(), "sorte": sorte,
            "beigetreten": beigetreten or jetzt, "zuletzt_gesehen": jetzt,
            "hardware": hardware(sys_wurzel, umgebung),
            "dienste": ["backend", "tui", "abgleich"],
            "apps": [], "programm": fassung(wurzel),
            "netz": {"lan": None, "wireguard_oeffentlich": None, "ssh_oeffentlich": None},
            # Building kit step 9b (memory/hub/port_types.md): the port type
            # versions this node speaks, and that it runs the apply agent
            # (core/generations.py). A description without them = unmanaged.
            "types": port_types.supported(), "apply_agent": port_types.APPLY_AGENT}
