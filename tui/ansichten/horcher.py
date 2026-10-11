# tui/ansichten/horcher.py
#
# Der Horcher: der Client der Leiste ganz unten. Er fragt jedes Programm,
# sobald es in ZENTRALE verkabelt wird, welche Tasten es in welcher Ansicht
# nimmt, und merkt sich die Antwort. Die Leiste fragt danach nur noch ihn
# (ein Nachschlagen pro Bild, keine Rechenlast beim Öffnen). Sasha,
# 2026-10-11: „einmal die shortcuts finden und dann speichern für die
# einzelnen ansichten, noch besser direkt sobald etwas verkabelt ist".
#
# Woher die Antwort kommt:
#   1. Tastentabelle des Programms (TASTEN, tasten.py) — der Normalfall.
#      Was dort steht, verteilt das Programm auch; nichts kann auseinander-
#      laufen.
#   2. Tastentabelle aus dem app.toml einer App ([tasten],
#      core/tastentabelle.aus_manifest).
#   3. Sonst ABHÖREN: der Horcher baut das Programm über eine Fabrik frisch
#      (die Fabrik sorgt für eine Wegwerf-Umgebung — er drückt echte
#      Tasten!), drückt in jeder erreichten Ansicht jede Kandidaten-Taste
#      und notiert, welche etwas ändern. Namen kennt er dann keine; die
#      Leiste zeigt nur die Taste. Läuft im Hintergrund, einmal.

import copy
import threading

from . import tasten as T

# Was abgehört wird: was eine gewöhnliche Tastatur ohne Kunststücke schickt.
KANDIDATEN = (["up", "down", "left", "right", "enter", "esc", "tab", "space",
               "backspace", "del", "pgup", "pgdn", "home", "end"]
              + [chr(c) for c in range(ord("a"), ord("z") + 1)]
              + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
              + list("0123456789+-<>!?#.,"))


class Horcher:
    def __init__(self):
        self._ablage = {}          # programm -> {ansicht: [(taste, text)]}
        self._freitext = {}        # programm -> {ansicht, …} mit „type"
        self._herkunft = {}        # programm -> "tabelle" | "manifest" | "abgehört" | "läuft"
        self._lock = threading.Lock()

    # ── Verkabeln ─────────────────────────────────────────────────────
    def verkabeln(self, name, programm=None, manifest=None, fabrik=None,
                  im_hintergrund=True):
        """Programm `name` anmelden. Reihenfolge: TASTEN → manifest → fabrik
        (abhören). Ohne alles: das Programm zeigt keine Tasten."""
        tab = getattr(programm, "TASTEN", None) if programm is not None else None
        if isinstance(tab, T.Tasten):
            self._merken(name, tab, "tabelle")
            return
        if manifest is not None:
            daten = T.tt.aus_manifest(manifest)
            if daten is not None:
                self._merken(name, T.Tasten(daten), "manifest")
                return
        if fabrik is not None:
            with self._lock:
                self._herkunft[name] = "läuft"
            if im_hintergrund:
                threading.Thread(target=self._abhoeren_und_merken, args=(name, fabrik),
                                 daemon=True).start()
            else:
                self._abhoeren_und_merken(name, fabrik)
            return
        with self._lock:
            self._ablage[name], self._freitext[name] = {}, set()
            self._herkunft[name] = "ohne"

    def _merken(self, name, tab, herkunft):
        with self._lock:
            self._ablage[name] = {a: tab.eintraege(a) for a in tab.ansichten()}
            self._freitext[name] = {a for a in tab.ansichten() if tab.freitext(a)}
            self._herkunft[name] = herkunft

    def _abhoeren_und_merken(self, name, fabrik):
        try:
            gefunden = abhoeren(fabrik)
        except Exception as e:                      # nie die TUI umwerfen
            print("[horcher] %s abhören fehlgeschlagen: %s" % (name, e), flush=True)
            gefunden = {}
        with self._lock:
            self._ablage[name] = {a: [(t, "") for t in ts] for a, ts in gefunden.items()}
            self._freitext[name] = set()
            self._herkunft[name] = "abgehört"

    # ── Fragen ────────────────────────────────────────────────────────
    def kennt(self, name):
        with self._lock:
            return name in self._ablage

    def herkunft(self, name):
        with self._lock:
            return self._herkunft.get(name)

    def eintraege(self, name, ansicht):
        """[(taste, text)] fürs Programm in dieser Ansicht (Kopie)."""
        with self._lock:
            return list((self._ablage.get(name) or {}).get(ansicht) or [])

    def ansichten(self, name):
        with self._lock:
            return list(self._ablage.get(name) or {})

    def freitext(self, name, ansicht):
        with self._lock:
            return ansicht in self._freitext.get(name, ())


def _stand(programm):
    """Fingerabdruck eines Programms: seine einfachen Daten (Zustands-Dicts,
    Zahlen, Texte). Was sich da ändert, hat die Taste bewirkt."""
    roh = {}
    for k, v in vars(programm).items():
        if isinstance(v, (dict, list, tuple, str, int, float, bool, type(None))):
            try:
                roh[k] = repr(copy.deepcopy(v))
            except Exception:
                roh[k] = repr(v)
    return roh


def abhoeren(fabrik, kandidaten=KANDIDATEN, tiefe=2):
    """Welche Tasten nimmt ein Programm ohne Tabelle? fabrik() → frisches
    Programm (in einer Wegwerf-Umgebung) mit taste(ch) und gern ansicht().
    Breitensuche über die Ansichten bis `tiefe` Tasten weit. → {ansicht:
    [taste, …]} in der Reihenfolge der Kandidaten."""
    def ansicht(p):
        f = getattr(p, "ansicht", None)
        return f() if callable(f) else "start"

    def druecken(p, name):
        cs = T.codes(name)
        stdscr = getattr(getattr(p, "z", None), "stdscr", None)
        if len(cs) > 1 and hasattr(stdscr, "folge"):
            stdscr.folge = list(cs[1:])
        return p.taste(cs[0])

    gefunden, wege = {}, {}
    start = fabrik()
    wege[ansicht(start)] = []
    offen = [ansicht(start)]
    while offen:
        a = offen.pop(0)
        weg = wege[a]
        nimmt = []
        for k in kandidaten:
            p = fabrik()
            for schritt in weg:
                druecken(p, schritt)
            vorher = _stand(p)
            try:
                raus = druecken(p, k)
            except Exception:
                continue
            if raus is not None or _stand(p) != vorher:
                nimmt.append(k)
                neu = ansicht(p)
                if neu not in wege and len(weg) < tiefe:
                    wege[neu] = weg + [k]
                    offen.append(neu)
        gefunden[a] = nimmt
    return gefunden
