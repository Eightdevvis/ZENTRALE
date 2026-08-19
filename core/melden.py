# core/melden.py
#
# ZENTRALE meldet sich auf dem Desktop.
#
# ── Warum es das braucht ──────────────────────────────────────────────
# Seit dem Takt (core/takt.py) kann ZENTRALE von sich aus sprechen. Nur:
# ihre Initiative endete bisher an der Fensterkante. Sie legte einen Satz
# in den Chat-Verlauf, und wenn der Kasten hinter einem Browser lag, sah
# Sasha ihn Stunden spaeter — oder nie. Eine Terminerinnerung, die man
# erst nach dem Termin liest, ist keine.
#
# Sashas Entscheidung (19.08.2026): eine echte Systembenachrichtigung, wie
# sie jedes andere Programm auch schickt.
#
# ── Zurueckhaltung ist Teil der Sache ─────────────────────────────────
# Ein Popup unterbricht. Deshalb: nur was der Takt ausloest, nie eine
# Antwort auf etwas, das Sasha gerade selbst gefragt hat — und nicht,
# wenn ZENTRALE ohnehin vor ihm auf dem Schirm steht.

from __future__ import annotations

import os
import shutil
import subprocess

AN = os.environ.get("ZENTRALE_NOTIFY", "1") == "1"

# Der Fenster-Rolle, unter der ZENTRALE im Scratchpad liegt (siehe
# deploy/i3/zentrale.conf). Ueber sie erkennen wir, ob sie sichtbar ist.
ROLLE = "zentrale"

_MAX = 220          # Zeichen; ein Popup ist kein Textfenster


def _kuerzen(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= _MAX else text[:_MAX - 1].rstrip() + "…"


def sichtbar() -> bool | None:
    """Steht ZENTRALE gerade auf dem Schirm? None = nicht feststellbar.

    Best effort ueber i3. Die Unterscheidung None vs. False ist der Punkt:
    wer nicht weiss, ob der Benutzer hinschaut, soll ihn benachrichtigen —
    eine verpasste Erinnerung ist teurer als ein ueberfluessiges Popup.
    """
    if not shutil.which("i3-msg"):
        return None

    def frag(was):
        try:
            import json
            roh = subprocess.run(["i3-msg", "-t", was],
                                 capture_output=True, text=True, timeout=3)
            if roh.returncode != 0:
                return None
            return json.loads(roh.stdout)
        except Exception:
            return None

    # Welche Workspaces gerade auf einem Bildschirm liegen. NUR hier steht
    # das: `get_tree` fuehrt bei Workspace-Knoten KEIN `visible`-Feld, ein
    # Blick dorthin liefert None und damit stumm immer "unsichtbar".
    ws_liste = frag("get_workspaces")
    baum = frag("get_tree")
    if ws_liste is None or baum is None:
        return None
    offen = {w.get("name") for w in ws_liste if w.get("visible")}

    # Zwei Dinge muessen stimmen, damit "sichtbar" auch heisst, dass er
    # hinschaut: das Fenster darf nicht im Scratchpad-Ast haengen, UND sein
    # Workspace muss gerade angezeigt werden. Eingeblendet auf einem
    # Workspace, den er verlassen hat, ist genauso unsichtbar wie weggelegt.
    def suchen(knoten, im_scratchpad=False, ws=None):
        if (knoten.get("name") or "") == "__i3_scratch":
            im_scratchpad = True
        if knoten.get("type") == "workspace":
            ws = knoten.get("name")
        rolle = (knoten.get("window_properties") or {}).get("window_role")
        if rolle == ROLLE:
            return (not im_scratchpad) and ws in offen
        for kind in (knoten.get("nodes") or []) + (knoten.get("floating_nodes") or []):
            t = suchen(kind, im_scratchpad, ws)
            if t is not None:
                return t
        return None

    return suchen(baum)


def desktop(text: str, titel: str = "ZENTRALE",
            nur_wenn_versteckt: bool = True) -> bool:
    """Eine Desktop-Benachrichtigung schicken. -> True, wenn sie rausging.

    Wirft nie. Eine Meldung, die den Chat abreissen laesst, waere schlimmer
    als keine Meldung.
    """
    if not AN:
        return False
    text = _kuerzen(text)
    if not text:
        return False
    if nur_wenn_versteckt and sichtbar() is True:
        return False
    if not shutil.which("notify-send"):
        return False

    umgebung = dict(os.environ)
    # Als systemd-User-Dienst ist DISPLAY nicht gesetzt — der Dienst kennt
    # die Sitzung nicht, in der er meldet. Ohne das faellt notify-send
    # stumm auf die Nase, und zwar genau dann, wenn ZENTRALE als
    # Systemeinheit laeuft: also immer.
    umgebung.setdefault("DISPLAY", ":0")
    try:
        subprocess.run(
            ["notify-send", "-a", "ZENTRALE", "-u", "normal", titel, text],
            env=umgebung, timeout=5,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False
