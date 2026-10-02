"""
pc_status — ist der andere Knoten (PC bzw. Laptop) gerade da? Eine Quelle.

Sasha, 02.10.2026: *„oft versuchst du irgendwas zum pc zu holen, und auch am
anfang wenn zentrale aufgeht versucht sie lange den pc zu erreichen. dabei
wäre es viel einfacher wenn einfach direkt ein pc verbunden oder nicht
gewusst wäre."*

Vorher fragte jeder selbst: der Boot-Abgleich (find-pc mit Ping über das
ganze /24, dann ssh mit 4 s Wartezeit), zentrale-pull (find-pc, dann ssh
OHNE Zeitgrenze — hing an dem Tag über zwei Minuten), der Daten-Push. Jeder
wartete einzeln, keiner wusste vom anderen.

Jetzt steht die Antwort in EINER Datei ($XDG_RUNTIME_DIR/zentrale/peer.json,
also im RAM, pro Boot frisch):

    {"peer": "pc", "verbunden": false, "ip": "10.73.45.12",
     "geprueft": 1790950000.0, "seit": 1790949000.0, "grund": "..."}

Geprüft wird billig: TCP auf Port 22 der zuletzt bekannten Adresse (aus dem
find-pc-Block in ~/.ssh/config), 1 s. Nur wenn das scheitert UND sich das
Netz geändert hat oder lange nicht gesucht wurde, läuft der teure Finder
(ARP-Scan) — mit einer Runde statt drei und harter Zeitgrenze.

Wer fragt:
  - die TUI hält die Datei warm (Thread, alle 15 s) und zeigt PC ✓/✗ oben
  - scripts/zentrale-pc-status (CLI) — für Skripte und für Claude:
        zentrale-pc-status          → "verbunden"/"getrennt", Exit 0/1
    liest die Datei und prüft nur selbst, wenn sie alt ist.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import time

FRISCH_S = 30          # so lange gilt ein Ergebnis ohne neue Prüfung
SUCHE_ALLE_S = 300     # teurer Finder höchstens so oft (außer Netz neu)


def _laufzeit_dir():
    basis = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    return os.path.join(basis, "zentrale")


def status_pfad():
    return (os.environ.get("ZENTRALE_PEER_STATUS")
            or os.path.join(_laufzeit_dir(), "peer.json"))


def peer_name():
    """Laptop sucht den PC ('pc'), der PC den Laptop ('0RAMMachine')."""
    if os.environ.get("ZENTRALE_PEER"):
        return os.environ["ZENTRALE_PEER"]
    if shutil.which("find-0RAMMachine") and not shutil.which("find-pc"):
        return "0RAMMachine"
    return "pc"


def anzeige_name(peer=None):
    return "PC" if (peer or peer_name()) == "pc" else "LAPTOP"


def ip_aus_ssh_config(alias, pfad=None):
    """HostName des Alias aus ~/.ssh/config (den find-* aktuell hält)."""
    pfad = pfad or os.path.expanduser("~/.ssh/config")
    try:
        zeilen = open(pfad, encoding="utf-8").read().splitlines()
    except OSError:
        return None
    drin = False
    for z in zeilen:
        t = z.strip().split()
        if not t:
            continue
        if t[0].lower() == "host":
            drin = alias in t[1:]
        elif drin and t[0].lower() == "hostname" and len(t) > 1:
            return t[1]
    return None


def netz_kennung():
    """Woran man merkt, dass man in einem anderen Netz ist: die Default-Route."""
    try:
        with open("/proc/net/route") as f:
            for z in f.read().splitlines()[1:]:
                t = z.split()
                if len(t) > 2 and t[1] == "00000000":
                    return t[0] + ":" + t[2]
    except OSError:
        pass
    return None


def tcp_offen(ip, port=22, timeout=1.0):
    if not ip:
        return False
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def lesen(pfad=None):
    try:
        with open(pfad or status_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _schreiben(d, pfad=None):
    pfad = pfad or status_pfad()
    try:
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        tmp = pfad + ".tmp%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, pfad)
    except OSError:
        pass


def _finder(peer, timeout=6):
    """Den teuren Finder laufen lassen (aktualisiert ~/.ssh/config)."""
    exe = shutil.which("find-" + peer)
    if not exe:
        return False
    try:
        r = subprocess.run([exe], timeout=timeout, env=dict(os.environ, FIND_RETRIES="1"),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def pruefen(suchen_erlaubt=True, jetzt=None, pfad=None):
    """Jetzt nachsehen, Ergebnis schreiben und zurückgeben."""
    jetzt = jetzt or time.time()
    peer = peer_name()
    alt = lesen(pfad) or {}
    netz = netz_kennung()
    ip = ip_aus_ssh_config(peer)
    d = {"peer": peer, "ip": ip, "geprueft": jetzt, "netz": netz,
         "gesucht": alt.get("gesucht", 0) if alt.get("netz") == netz else 0}

    if not netz:
        d.update(verbunden=False, grund="kein netz")
    elif tcp_offen(ip):
        d.update(verbunden=True, grund="ssh-port antwortet")
    elif suchen_erlaubt and jetzt - d["gesucht"] > SUCHE_ALLE_S:
        d["gesucht"] = jetzt
        if _finder(peer):
            d["ip"] = ip_aus_ssh_config(peer)
        if tcp_offen(d["ip"]):
            d.update(verbunden=True, grund="neu gefunden")
        else:
            d.update(verbunden=False, grund="nicht im netz gefunden")
    else:
        d.update(verbunden=False, grund="letzte adresse antwortet nicht")

    d["seit"] = (alt.get("seit") if alt.get("verbunden") == d["verbunden"]
                 and alt.get("seit") else jetzt)
    _schreiben(d, pfad)
    return d


def aktuell(max_alter=FRISCH_S, pfad=None):
    """Der Stand — aus der Datei, wenn frisch genug, sonst neu geprüft."""
    d = lesen(pfad)
    if d and time.time() - float(d.get("geprueft") or 0) <= max_alter \
            and d.get("peer") == peer_name():
        return d
    return pruefen(pfad=pfad)


def main(argv):
    if "-h" in argv or "--help" in argv:
        print("zentrale-pc-status [--frisch] [--json]\n"
              "  Exit 0 = verbunden, 1 = getrennt. --frisch prüft sofort neu.")
        return 0
    d = pruefen() if "--frisch" in argv else aktuell()
    if "--json" in argv:
        print(json.dumps(d))
    else:
        alter = int(time.time() - float(d.get("seit") or time.time()))
        print("%s %s (%s, seit %ds)" % (anzeige_name(d.get("peer")),
                                        "verbunden" if d["verbunden"] else "getrennt",
                                        d.get("grund", ""), alter))
    return 0 if d["verbunden"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
