# Archiv: der KI-Ring der TUI (ring_punkte / ring_zeilen) + Lage-Poll

**Stand 2026-10-04:** aus dem Live-Code entfernt. Nichts davon läuft mehr.

- **Was es tat:** Zeichnete ZENTRALE in der Mitte der TUI-Startseite als
  ASCII-Ring, dessen Glyphe/Helligkeit die Anwesenheits-Lage zeigte
  (`offen` / `woanders` / `weg`, aus `core/anwesenheit.py`). Beim Denken
  wanderte ein heller Bogen um den Ring. Der Lage-Poll-Thread fragte dafür
  alle 5 s `anwesenheit.lage()` ab (ruft u. a. zweimal `i3-msg`).
- **Warum archiviert:** Seit dem Rad-Redesign vom 02.10.2026 zeichnet die
  Startseite das App-Rad statt des Rings. `ring_zeilen` wurde nur noch von
  Tests aufgerufen, `LAGE` las niemand mehr — der Poll-Thread startete
  trotzdem und rief alle 5 s `i3-msg` für nichts.
- **Wann wieder nützlich:** Wenn ZENTRALE sich auf der Startseite wieder
  „selbst zeigen" soll (der freie Platz über dem Rad ist dafür vorgesehen,
  siehe Kommentar an der Rad-Stelle in `tui/zentrale_tui.py`), oder wenn die
  TUI die Anwesenheit sichtbar machen soll.
- **Abhängigkeiten:** `core/anwesenheit.py` (`lage()`, bleibt im Code — der
  Takt nutzt es), `core/melden.py` (`sichtbar()` via i3), curses-Stile
  `ring`, `ring_matt`, `ring_still`, `ring_hell` (waren in der Palette nie
  definiert — bei Reaktivierung anlegen), `math`. Der Poll braucht `os`,
  `sys`, `time` und lief als Thread in `main()` der TUI.

## tui/zentrale_tui.py Z. 1698–1797 (Commit c52f1e1)

```python
# ── Der Ring: ZENTRALE zeigt sich selbst ─────────────────────────────────
#
# Sasha, 20.08.2026: die Befehle wandern aus der Mitte in die Fussleiste, und
# in der Mitte bleibt SIE stehen — "sie zeigt sich als einen mit ascii
# gezeichneten ring".
#
# Der Ring zeigt, was sie ueber die Lage weiss (core/anwesenheit.py):
#
#   offen     Sasha hat ZENTRALE offen. Sie hat seine Aufmerksamkeit —
#             heller, geschlossener Ring.
#   woanders  Er ist da, aber bei etwas anderem. Sie schaut zu, ohne zu
#             stoeren — matter Ring.
#   weg       Niemand an der Maschine. Sie ruht — nur noch eine Andeutung.
#
# Gerechnet statt gemalt: ein festes ASCII-Bild passt genau in EINE
# Fenstergroesse. Der Ring hier waechst mit dem Kasten mit, und weil er aus
# Winkeln entsteht, ist die wandernde Helle beim Denken nur ein Offset —
# kein zweites Bild, das man synchron halten muesste.
#
# Terminalzellen sind etwa doppelt so hoch wie breit. Ohne die Korrektur
# (rx = 2*ry) waere es kein Ring, sondern ein liegendes Ei.

# Was unter dem Ring steht. Kurz und in Sashas Ton — der Kasten soll den
# Zustand zeigen, nicht ihn erklaeren.
LAGE_TEXT = {
    "offen":     "du bist da",
    "woanders":  "du bist da, arbeitest woanders",
    "weg":       "niemand an der maschine",
    "unbekannt": "",
}

RING_GLYPHEN = {
    "offen":     "●",
    "woanders":  "◦",
    "weg":       "·",
    "unbekannt": "·",
}


def ring_punkte(h, breite):
    """Die Zellen des Rings, nach Winkel sortiert. -> [(dy, dx, winkel)]

    (0,0) ist die Mitte. Doppelt belegte Zellen fallen raus — sonst
    ueberschreibt der Bogen sich selbst und die wandernde Helle stockt an
    genau den Stellen, wo zwei Winkel dieselbe Zelle treffen.
    """
    import math
    # Ein Drittel dessen, was in den Kasten passen wuerde (Sasha,
    # 20.08.2026: "der ring ist viel zu groß. mach ihn etwa ein drittel so
    # groß"). Er soll ein Zeichen sein, kein Rahmen — der Kasten hat schon
    # einen.
    ry = min((h - 2) // 2, (breite - 2) // 4) // 3
    if ry < 2:
        return []
    rx = ry * 2
    gesehen, punkte = set(), []
    # Doppelt so fein abgetastet, wie der Umfang Zellen hat. Bei genau einer
    # Probe pro Zelle bleiben Loecher: die Schrittzahl war ungerade, der
    # Winkel fuer "ganz unten" wurde nie getroffen, und im Ring klaffte eine
    # Luecke an der auffaelligsten Stelle.
    schritte = max(64, int(4 * math.pi * rx))
    for i in range(schritte):
        winkel = 2 * math.pi * i / schritte
        dy = int(round(-math.cos(winkel) * ry))     # oben = 0 rad
        dx = int(round(math.sin(winkel) * rx))
        if (dy, dx) in gesehen:
            continue
        gesehen.add((dy, dx))
        punkte.append((dy, dx, winkel))
    return punkte


def ring_zeilen(h, breite, lage="unbekannt", aktiv=False, phase=0.0):
    """Der Ring als Plot-Anweisungen. -> [(dy, dx, zeichen, stil)]

    `aktiv` = sie denkt oder spricht gerade: ein heller Bogen wandert mit
    `phase` (0..1) um den Ring. Ruht sie, steht er still — eine dauernd
    kreisende Animation wuerde im Augenwinkel ziehen, und das waere genau
    das Gegenteil von "stoert nicht".
    """
    import math
    punkte = ring_punkte(h, breite)
    if not punkte:
        return []
    grund = RING_GLYPHEN.get(lage, RING_GLYPHEN["unbekannt"])
    stil_grund = {"offen": "ring", "woanders": "ring_matt",
                  "weg": "ring_still", "unbekannt": "ring_still"}.get(
                      lage, "ring_still")

    aus = []
    kopf = (phase % 1.0) * 2 * math.pi
    bogen = math.pi / 5          # wie lang die helle Stelle ist
    for dy, dx, winkel in punkte:
        zeichen, stil = grund, stil_grund
        if aktiv:
            ab = abs((winkel - kopf + math.pi) % (2 * math.pi) - math.pi)
            if ab < bogen:
                zeichen, stil = "●", "ring_hell"
        aus.append((dy, dx, zeichen, stil))
    return aus
```

## tui/zentrale_tui.py Z. 2905–2927 (Commit c52f1e1) — Lage-Poll in main()

```python
    # Was ZENTRALE ueber die Lage weiss — fuer den Ring in der Mitte.
    # Bewusst LOKAL bestimmt und nicht vom Backend geholt: die Frage ist,
    # ob jemand an DIESER Maschine sitzt und ob DIESES Fenster offen ist.
    # Auf dem Laptop haengt die TUI am PC-Backend; dessen Anwesenheit hilft
    # hier niemandem.
    LAGE = {"wert": "unbekannt"}

    def lage_poll():
        """Alle paar Sekunden nachsehen, ob Sasha da ist. Wirft nie."""
        try:
            core_dir = os.path.join(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))), "core")
            if core_dir not in sys.path:
                sys.path.insert(0, core_dir)
            import anwesenheit
        except Exception:
            return                      # ohne das Modul bleibt es unbekannt
        while True:
            try:
                LAGE["wert"] = anwesenheit.lage()
            except Exception:
                LAGE["wert"] = "unbekannt"
            time.sleep(5)
```

## tui/zentrale_tui.py Z. 3562 (Commit c52f1e1) — Thread-Start

```python
    threading.Thread(target=lage_poll, daemon=True, name="lage").start()
```

## tests/test_tui_helpers.py Z. 448–531 (Commit a14d4b0) — Geometrie-Tests

Import dazu war `ring_punkte, ring_zeilen, RING_GLYPHEN` aus `tui.zentrale_tui`.

```python
# ── Der Ring: ZENTRALE zeigt sich selbst ──────────────────────────────
#
# Gerechnet statt gemalt (siehe die Notiz an der Funktion). Getestet wird
# deshalb die Geometrie: dass es wirklich ein Ring ist, dass er in seinen
# Kasten passt, und dass er bei keiner Fenstergroesse umfaellt.

def _gitter(h, w, **kw):
    feld = [[" "] * w for _ in range(h)]
    for dy, dx, ch, _st in ring_zeilen(h, w, **kw):
        feld[h // 2 + dy][w // 2 + dx] = ch
    return feld


def test_der_ring_ist_geschlossen():
    """Eine Luecke faellt an der auffaelligsten Stelle auf. Genau das ist
    beim ersten Versuch passiert: bei einer Probe pro Zelle war die
    Schrittzahl ungerade, der Winkel fuer 'ganz unten' wurde nie getroffen,
    und unten im Ring klaffte ein Loch.

    Gemessen wird der ZUSAMMENHANG der Zellen, nicht der Winkelabstand: bei
    einem kleinen Ring sind die Winkelspruenge zwischen zwei benachbarten
    Zellen naturgemaess gross, ohne dass etwas fehlt. Eine feste
    Winkel-Grenze haette also genau die kleinen Ringe fuer kaputt erklaert
    — und klein sind sie seit dem 20.08.2026 alle."""
    for h, w in ((16, 52), (20, 60), (12, 40), (30, 100), (14, 41), (34, 69)):
        punkte = ring_punkte(h, w)
        if not punkte:
            continue
        folge = [(p[0], p[1]) for p in punkte]
        ring = folge + [folge[0]]         # der Kreis schliesst sich
        for (y1, x1), (y2, x2) in zip(ring, ring[1:]):
            assert max(abs(y1 - y2), abs(x1 - x2)) <= 2, (h, w, (y1, x1), (y2, x2))


def test_der_ring_ist_rund_und_kein_ei():
    """Terminalzellen sind etwa doppelt so hoch wie breit. Ohne die
    Korrektur waere es kein Ring, sondern ein liegendes Ei."""
    punkte = ring_punkte(24, 80)
    breite = max(p[1] for p in punkte) - min(p[1] for p in punkte)
    hoehe = max(p[0] for p in punkte) - min(p[0] for p in punkte)
    assert 1.7 < breite / hoehe < 2.3


def test_der_ring_bleibt_im_kasten():
    for h, w in ((10, 30), (16, 52), (40, 140)):
        for dy, dx, _ch, _st in ring_zeilen(h, w, "offen"):
            assert abs(dy) <= h // 2 - 1, (h, w, dy)
            assert abs(dx) <= w // 2 - 1, (h, w, dx)


def test_in_einem_winzigen_kasten_zeichnet_er_nichts():
    """Lieber leer als ein Klumpen aus drei Zeichen."""
    for h, w in ((4, 10), (2, 60), (6, 6), (0, 0)):
        assert ring_zeilen(h, w, "offen") == []


def test_jede_lage_hat_ihr_eigenes_zeichen():
    """Die Lage soll man SEHEN, ohne den Text darunter zu lesen."""
    gezeichnet = {lage: {ch for _y, _x, ch, _s in ring_zeilen(20, 60, lage)}
                  for lage in ("offen", "woanders", "weg")}
    assert gezeichnet["offen"] != gezeichnet["woanders"]
    assert gezeichnet["woanders"] != gezeichnet["weg"]


def test_beim_denken_wandert_eine_helle_stelle():
    """Und zwar nur beim Denken: ein dauernd kreisender Ring zieht im
    Augenwinkel, und das waere das Gegenteil von 'stoert nicht'."""
    def helle(phase):
        return {(y, x) for y, x, _ch, st in
                ring_zeilen(20, 60, "woanders", aktiv=True, phase=phase)
                if st == "ring_hell"}
    assert helle(0.0) and helle(0.5)
    assert helle(0.0) != helle(0.5)
    assert not any(st == "ring_hell" for _y, _x, _ch, st in
                   ring_zeilen(20, 60, "woanders", aktiv=False))


def test_ring_wirft_nie():
    """Dieselbe Eigenschaft wie bei den uebrigen Helfern."""
    for h in (-3, 0, 1, 5, 21, 400):
        for w in (-3, 0, 1, 7, 53, 999):
            for lage in ("offen", "weg", "quatsch", "", None):
                ring_zeilen(h, w, lage, aktiv=True, phase=0.37)
                ring_punkte(h, w)
```

## tests/test_tui_mitte.py Z. 233–239 (Commit ba4d8cd)

```python
def test_der_ring_bleibt_ein_zeichen_kein_rahmen():
    """Ring-Helfer (heute nicht auf der Startseite) bleiben heil."""
    m = _modul()
    h, w = 34, 69
    punkte = m.ring_punkte(h, w)
    hoehe = max(p[0] for p in punkte) - min(p[0] for p in punkte)
    assert hoehe < (h - 2) // 2
```
