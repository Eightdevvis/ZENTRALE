# core/listen_baum.py
#
# Reine Helfer über den Eintrags-Baum einer Liste (core/lists.py): zählen,
# erledigt?, Fokus darunter?, Anzeige-Reihenfolge einer Ebene, flach
# klopfen, Pfad zu einem Eintrag, die Steine der Bernsteinleiste. Kein
# Lesen, kein Schreiben, keine Imports — nur Rechnen über Dicts.
#
# Warum ein eigenes Modul (2026-10-10): die Listen-Ansicht der TUI
# (tui/ansichten/fokus.py) und die Listen-Kachel (core/kachel_fokus.py)
# sollen eine Liste GLEICH zeigen — dieselbe Reihenfolge, derselbe
# Fortschritt. Leitlinie „dasselbe Objekt, nicht kopiert": die Helfer
# wohnten bis dahin in fokus.py und sind hierher umgezogen; fokus.py nimmt
# sie von hier (Tür `tui/` → Kern, bauplan_kern.md). Weil die TUI auch auf
# einem Aussenposten ohne Backend läuft, steht die Datei in
# deploy/aussenposten.txt — sie darf darum nichts aus dem Kern importieren.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md).


def _dicts(items):
    return [it for it in (items or []) if isinstance(it, dict)]


def _kinder(it):
    kids = it.get("items")
    return kids if isinstance(kids, list) and kids else None


def zaehlen(items):
    """(erledigt, gesamt) über die BLÄTTER einer Eintragsliste. Ordner zählen
    nicht selbst mit — sie sind nur Gruppierung."""
    d = t = 0
    for it in _dicts(items):
        kids = _kinder(it)
        if kids:
            cd, ct = zaehlen(kids)
            d += cd
            t += ct
        else:
            t += 1
            if it.get("done"):
                d += 1
    return d, t


def knoten_zaehlen(node):
    """(erledigt, gesamt) EINES Knotens: über seine Blätter, ein Blatt zählt
    als ein Punkt (wie core/lists.node_progress)."""
    kids = _kinder(node)
    if kids:
        return zaehlen(kids)
    return (1 if node.get("done") else 0, 1)


def erledigt(it):
    """Effektiver Erledigt-Status (wie core/lists.is_done): Blatt = eigenes
    'done'; Ordner = erledigt, wenn ALLE Kinder erledigt sind."""
    kids = _kinder(it)
    if kids:
        return all(erledigt(c) for c in _dicts(kids))
    return bool(it.get("done"))


def hat_fokus(it):
    """Trägt der Eintrag selbst oder irgendwas darunter den Fokus?"""
    if it.get("focus"):
        return True
    return any(hat_fokus(c) for c in _dicts(it.get("items")))


def ordnen(items, erledigte=False):
    """Anzeige-Reihenfolge einer Ebene.

    erledigte=False: nur OFFENE Einträge — der Fokus (oder ein Ordner, in dem
    er steckt) klebt oben, der Rest nach Anzahl OFFENER Punkte aufsteigend
    (was kaum noch Saft braucht, steht oben — 31/37 vor 1/2), bei gleich
    vielen offenen das mit mehr Erledigtem zuerst; danach bleibt die
    gespeicherte Reihenfolge.
    erledigte=True: nur die abgeschlossenen (Inhalt der Bernsteinleiste)."""
    rows = _dicts(items)
    if erledigte:
        return [it for it in rows if erledigt(it)]

    def rest(it):
        d, t = zaehlen([it])
        return t - d, -d

    offen = [it for it in rows if not erledigt(it)]
    return sorted(offen, key=lambda it: (not hat_fokus(it), rest(it)))


def steine(done, total, breite):
    """Spalten der Bernsteinleiste: je Spalte 'L' (leuchtender Stein), 'U'
    (leerer Stein) oder ' ' (Fuge). Ein Stein = ein Punkt; die Steinbreite
    rechnet sich aus Breite/Anzahl. Passen nicht alle Punkte als eigene Spalte
    rein, steht jede Spalte anteilig für mehrere (dann ohne Fugen)."""
    try:
        total, done, breite = int(total), int(done), int(breite)
    except (TypeError, ValueError):
        return []
    if total <= 0 or breite <= 0:
        return []
    done = max(0, min(done, total))
    if total > breite:                          # zu viele Punkte → skalieren
        lit = done * breite // total
        return ["L"] * lit + ["U"] * (breite - lit)
    fuge = breite // total >= 2                 # 1 Spalte Fuge, wenn Platz ist
    out = []
    for i in range(total):                      # Steine über die VOLLE Breite verteilen
        zelle = (i + 1) * breite // total - i * breite // total
        last = i == total - 1
        stein = zelle if (not fuge or last) else zelle - 1
        out += ["L" if i < done else "U"] * stein
        out += [" "] * (zelle - stein)
    return out


def pfad_zu(items, iid, acc=None):
    """id-Kette von der Listen-Wurzel bis zu iid (inklusive) — oder None."""
    if acc is None:
        acc = []
    for it in _dicts(items):
        if it.get("id") == iid:
            return acc + [iid]
        kids = _kinder(it)
        if kids:
            sub = pfad_zu(kids, iid, acc + [it.get("id")])
            if sub is not None:
                return sub
    return None


def flach(items, depth=0, out=None):
    """Den Eintrags-Baum in eine flache [(item, tiefe), …]-Liste klopfen,
    Eltern vor Kindern, gespeicherte Reihenfolge."""
    if out is None:
        out = []
    for it in _dicts(items):
        out.append((it, depth))
        kids = _kinder(it)
        if kids:
            flach(kids, depth + 1, out)
    return out


def finden(items, iid):
    """Den Eintrag mit iid irgendwo im Baum (oder None)."""
    for it, _d in flach(items):
        if it.get("id") == iid:
            return it
    return None
