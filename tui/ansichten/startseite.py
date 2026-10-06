# tui/ansichten/startseite.py
#
# Die Startseite der TUI: das App-Rad, das Technik-Rad und die Galaxie, auf
# der beide liegen (seit 02./03.10.2026, memory/system/dashboard.md). Hier
# wohnen die reine Geometrie (rad_zeilen, galaxie_lage, der Schleuder-Gag …)
# und das Zeichnen. Den Zustand der Räder (RAD, META, TRAD) besitzt weiter
# tui/zentrale_tui.py: er überlebt dort run_ui-Neustarts und reist beim Hot
# Reload über die Umgebung mit — die Startseite bekommt ihn hereingereicht.
# Bis 06.10.2026 lag das alles in zentrale_tui.py, siehe
# memory/system/tui_bauplan.md.

import curses
import time

try:                                    # Pixel-Baustein (tui/pixel.py)
    from tui import pixel
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    import pixel


# ── Das Rad (Startseite) ─────────────────────────────────────────────────────
# Sasha, 02.10.2026: statt KI fett in der Mitte und Tasten-Leiste unten ein
# Durchklicker — ←/→ dreht ein Rad, vorne steht EINE App, enter geht rein.
# Die Apps sitzen auf einem liegenden Ring, den man leicht von oben sieht:
# vorne = unten, gross und hell; hinten = oben, klein und blass. Gedreht
# wird über `pos` (Kommazahl), damit der Übergang gleitet statt springt.
RAD_APPS = [
    ("k", "klavier"), ("p", "post"), ("c", "kalender"), ("f", "fokus"),
    ("n", "notizen"), ("g", "graph"), ("m", "karte"), ("u", "tutor"),
    ("e", "elektronik"),
]
# Apps mit Pixel-Symbol (tui/pixel.py): im Rad eine Pille, vorn klappt das
# Symbol auf. Seit 03.10.2026: elektronik (Sasha), am selben Abend alle
# anderen auch (pixel.MOTIVE: Brief, Globus, Kalenderblatt, Klaviatur …).
RAD_SYMBOLE = tuple(a[1] for a in RAD_APPS)


# ── Die Galaxie (Startseite seit 03.10.2026) ─────────────────────────────────
# Sasha: das 3-Spalten-Dashboard braucht es nicht mehr. Die Startseite ist
# EINE Fläche, eine Galaxie: das App-Rad und das Technik-Rad (was vorher in
# den Seitenspalten stand) sind zwei Sonnensysteme auf einer RIESIGEN Bahn —
# so gross, dass man im Ausschnitt nur einen flachen Bogen sieht und die
# beiden praktisch nebeneinander liegen. ←/→ wechselt zwischen ihnen, der
# Ausschnitt gleitet dabei ein Stück zum gewählten. enter geht ins gewählte
# System (dann dreht ←/→ dessen Apps, enter öffnet), esc wieder raus. Die alte Ansicht bleibt als Backup: /dashboard an.
TECH_APPS = [("system", "external + telemetrie"), ("stdout", "das ganze log"),
             ("netz", "outbound + laufzeit")]


def meta_taste(meta, rad, trad, taste):
    """Eine Taste auf der Galaxie-Startseite. PURE bis auf die drei
    Zustands-Dicts. Sasha: ←/→ dreht direkt das gewählte Rad, alt+←/→
    wechselt das Rad, enter öffnet die App vorn.
    taste: "links" | "rechts" | "alt_links" | "alt_rechts" | "enter".
    -> None | ("app", buchstabe) | ("technik", name)"""
    if taste in ("alt_links", "alt_rechts"):   # nebeneinander: links = apps, rechts = technik
        meta["gsel"] = meta["fokus"] = 1 if taste == "alt_rechts" else 0
        return None
    ziel = rad if meta["fokus"] == 0 else trad
    if taste == "links":
        ziel["sel"] -= 1
        rad_anstoss(ziel, -1)
    elif taste == "rechts":
        ziel["sel"] += 1
        rad_anstoss(ziel, 1)
    elif taste == "enter":
        if meta["fokus"] == 0:
            return ("app", RAD_APPS[rad_index(rad["sel"])][0])
        return ("technik", TECH_APPS[rad_index(trad["sel"], len(TECH_APPS))][0])
    return None


# ── Der Schleuder-Gag (Sasha, 03.10.2026) ────────────────────────────────────
# Hält man die Pfeiltaste zu lange, dreht das Rad so schnell, dass die Apps
# abreissen: ALLE im selben Moment, und jede fliegt GERADEAUS weiter, in die
# Richtung, in die sie sich gerade gedreht hat (tangential, wie ein Stein
# aus der Schleuder). Das leere Rad dreht weiter. Kurz in Ruhe lassen → alle
# sitzen wieder drauf. Jeder Druck gibt Schwung, Schwung verfliegt; normales
# Tippen kommt nie über die Schwelle, eine Tastenwiederholung (~25-30/s)
# nach rund einer Sekunde schon.
SCHWUNG_ZERFALL = 0.6        # Sekunden (e-Faltung)
SCHLEUDER_AB = 12.0          # ab so viel Schwung reissen die Apps ab
SCHLEUDER_RUHE = 1.0         # so lange nichts gedrückt → sie sind zurück
SCHLEUDER_TEMPO = 70.0       # Spalten pro Sekunde im Flug


def rad_anstoss(rad, richtung=1, jetzt=None):
    """Ein Pfeildruck am Rad: Schwung +1, Drehrichtung und Zeitpunkt merken."""
    rad["schwung"] = rad.get("schwung", 0.0) + 1.0
    rad["richtung"] = 1 if richtung >= 0 else -1
    rad["letzt"] = time.monotonic() if jetzt is None else jetzt


def schwung_schritt(schwung, dt):
    """Schwung verfliegt. PURE."""
    import math
    return schwung * math.exp(-max(0.0, dt) / SCHWUNG_ZERFALL)


def schleuder_wurf(labels, pos, richtung, breite, hoehe, tempo=SCHLEUDER_TEMPO):
    """Der Moment des Abreissens. PURE. Gleiche Ellipse wie rad_zeilen.
    -> [(name, dy, dx_mitte, vy, vx)]: Startpunkt jeder App relativ zur
    Radmitte und ihre gerade Flugrichtung (Zellen pro Sekunde) — die
    Tangente der Drehung. Zeilen sind etwa doppelt so hoch wie Spalten
    breit, darum zählt die Senkrechte im Bild doppelt."""
    import math
    n = len(labels)
    rx = min(breite // 2 - 10, 38)
    ry = max(1, min(3, (hoehe - 4) // 4))
    if n == 0 or rx < 12:
        return []
    aus = []
    for i, name in enumerate(labels):
        w = ((i - pos) / n) * 2 * math.pi
        # pos wächst → w schrumpft: Bewegung = -richtung · d(Ort)/dw
        tx = -richtung * math.cos(w) * rx
        ty = -richtung * -math.sin(w) * ry
        laenge = math.hypot(tx, 2 * ty) or 1.0
        aus.append((name, math.cos(w) * ry, math.sin(w) * rx,
                    tempo * ty / laenge, tempo * tx / laenge))
    return aus


def wurf_zeilen(teile, t):
    """Wo sind die abgerissenen Apps `t` Sekunden nach dem Wurf? PURE.
    Gerade Linie, kein Bogen. -> [(dy, dx, name, "nah")] wie rad_zeilen."""
    aus = []
    for name, y, x, vy, vx in teile:
        ny, nx = y + vy * t, x + vx * t
        aus.append((int(round(ny)), int(round(nx - len(name) / 2)), name, "nah"))
    return aus


# Eine Giga-Galaxie dreht schwer (Sasha): langsam anlaufen, sanft ausrollen.
GALAXIE_DAUER = 1.6          # Sekunden für einen Wechsel


def galaxie_schritt(von, nach, t, dauer=GALAXIE_DAUER):
    """Stellung der Galaxie `t` Sekunden nach Fahrtbeginn. PURE.
    Ease-in-out (Sinus): träge los, gleichmäßig, weich aus — kein Ruck an
    den Enden. Nach `dauer` steht sie exakt auf `nach`."""
    import math
    if dauer <= 0 or t >= dauer:
        return float(nach)
    if t <= 0:
        return float(von)
    return von + (nach - von) * (1 - math.cos(math.pi * t / dauer)) / 2


def galaxie_lage(gpos, breiten, luecke=0.1):
    """Wo liegen die Sonnensysteme im Ausschnitt bei Kamera-Stellung `gpos`
    (0 = erstes gewählt … n-1 = letztes)? PURE.
    `breiten` = Anteil der Bildbreite je System, `luecke` = Abstand zwischen
    zwei Systemen (ebenfalls Bildanteil).
    -> [(i, quer, naehe)]: quer = Mitte des Systems, -1 (linker Rand) … 1
    (rechter Rand), darf darüber hinaus gehen; naehe 1 = gewählt, 0 = ein
    System oder weiter weg.
    Die Kamera steht auf dem gewählten System (Mitte); die anderen liegen
    weiter draussen und dürfen am Rand abgeschnitten sein (Sasha)."""
    mitten, x = [], 0.0
    for i, b in enumerate(breiten):
        if i:
            x += breiten[i - 1] + luecke + b
        mitten.append(x)
    n = len(mitten)
    g = max(0.0, min(float(n - 1), gpos))
    k = min(int(g), n - 2) if n > 1 else 0
    kamera = mitten[k] + (g - k) * ((mitten[k + 1] - mitten[k]) if n > 1 else 0.0)
    return [(i, m - kamera, max(0.0, 1 - abs(i - gpos))) for i, m in enumerate(mitten)]


def rad_offen_schritt(offen, vorn, dt):
    """Ein Frame Klappen: vorn in 0,23 s auf, sonst in 0,17 s zu."""
    if vorn:
        return min(1.0, offen + dt / 0.23)
    return max(0.0, offen - dt / 0.17)


def rad_schritt(pos, sel):
    """Ein Frame Drehung: pos gleitet auf sel zu und rastet am Ende ein."""
    d = sel - pos
    return float(sel) if abs(d) < 0.02 else pos + d * 0.3


def rad_index(sel, n=None):
    """Welche App steht bei Auswahl `sel` vorn? `sel` zählt frei weiter
    (auch negativ), damit das Rad beim Umlauf nicht zurückspult."""
    return sel % (n or len(RAD_APPS))


def rad_zeilen(labels, pos, breite, hoehe, symbole=None):
    """Das Rad als Plot-Anweisungen, hinten zuerst. -> [(dy, dx, text, stil)]

    (0,0) ist die Radmitte, `dx` ist der linke Rand des Texts. Stile:
    spur (Laufbahn), fern / nah (Apps nach Tiefe), vorn + rahmen (die
    gewählte App, sobald das Rad steht).

    `symbole` {name: offen} — Apps mit Pixel-Symbol: hinten als Pille
    (Stil pille / pille_fern, Text mit je einem Leerzeichen Polster), vorn
    bzw. solange noch offen als `symbol:<name>` (dx = Mitte, Text leer).
    """
    import math
    n = len(labels)
    rx = min(breite // 2 - 10, 38)
    ry = max(1, min(3, (hoehe - 4) // 4))
    if n == 0 or rx < 12:
        return []
    aus = []
    # Laufbahn: eine Ellipse aus Punkten, hinter allem.
    gesehen = set()
    for i in range(int(4 * math.pi * rx)):
        w = 2 * math.pi * i / int(4 * math.pi * rx)
        zelle = (int(round(math.cos(w) * ry)), int(round(math.sin(w) * rx)))
        if zelle not in gesehen:
            gesehen.add(zelle)
            aus.append((zelle[0], zelle[1], "·", "spur"))
    # Apps nach Tiefe sortiert: hinten zuerst, vorn malt drüber.
    steht = abs(pos - round(pos)) < 0.08
    apps = []
    for i, name in enumerate(labels):
        w = ((i - pos) / n) * 2 * math.pi
        tiefe = math.cos(w)                      # 1 = vorn, -1 = hinten
        apps.append((tiefe, i, name, w))
    apps.sort()
    for tiefe, i, name, w in apps:
        dy = int(round(tiefe * ry))
        mitte = int(round(math.sin(w) * rx))
        if symbole is not None and name in symbole:
            if (tiefe > 0.97 and steht) or symbole[name] > 0:
                aus.append((dy, mitte, "", "symbol:" + name))
            elif tiefe > -0.8:
                aus.append((dy, mitte - len(name) // 2 - 1, " " + name + " ",
                            "pille" if tiefe > 0.2 else "pille_fern"))
            continue
        if tiefe > 0.97 and steht:
            text = " ".join(name.upper())
            x = mitte - len(text) // 2
            aus.append((dy - 1, x - 2, "╭" + "─" * (len(text) + 2) + "╮", "rahmen"))
            aus.append((dy, x - 2, "│ " + " " * len(text) + " │", "rahmen"))
            aus.append((dy, x, text, "vorn"))
            aus.append((dy + 1, x - 2, "╰" + "─" * (len(text) + 2) + "╯", "rahmen"))
        elif tiefe > -0.8:                       # ganz hinten verschwindet sie
            aus.append((dy, mitte - len(name) // 2, name,
                        "nah" if tiefe > 0.2 else "fern"))
    return aus


class Startseite:
    """Die Startseite: Galaxie mit App-Rad und Technik-Rad (oder im alten
    Dashboard nur das App-Rad). Zeichnet; welche Taste was öffnet, entscheidet
    run_ui, weil es dafür alle Ansichten kennen muss."""

    def __init__(self, z, rad, meta, trad, technik):
        self.z = z
        # Die Räder gehören zentrale_tui.py (überleben run_ui und Hot Reload).
        self.RAD, self.META, self.TRAD = rad, meta, trad
        self.technik = technik              # die letzten Log-Zeilen unten

    def rad_symbol_vorn(self):
        """Name der Symbol-App, die gerade vorn STEHT (Rad in Ruhe) — sonst None."""
        RAD = self.RAD
        pos = RAD["pos"]
        if abs(pos - round(pos)) >= 0.08:
            return None
        name = RAD_APPS[rad_index(int(round(pos)))][1]
        return name if name in RAD_SYMBOLE else None

    def draw_rad(self, y0, h, bx, bw, labels, rad, symbole_an=False, gedimmt=False,
                 mitte=None, mass=None, blass=False):
        """Ein Rad in den Kasten (y0, bx, h, bw) zeichnen, Mitte bei 5/8 der
        Höhe. `rad` = {"sel", "pos"}; symbole_an nur fürs App-Rad (RAD).
        Galaxie: `mitte` (y, x) setzt den Mittelpunkt frei, `mass` (breite,
        hoehe) die Grösse; der Kasten bleibt die Grenze.
        Zu schmal für die Ellipse → eine schlichte Liste, vorn mit ▸."""
        C, PIX_MODUS, RAD, addclip = self.z.C, self.z.PIX_MODUS, self.RAD, self.z.addclip
        pix_attr, rad_symbol_vorn = self.z.pix_attr, self.rad_symbol_vorn
        safe_addstr = self.z.safe_addstr
        rad["pos"] = rad_schritt(rad["pos"], rad["sel"])
        cyc, ccx = mitte or (y0 + (h * 5) // 8, bx + bw // 2)
        jetzt_s = time.monotonic()
        dt_s = min(0.1, jetzt_s - rad.get("t_schl", jetzt_s))
        rad["t_schl"] = jetzt_s
        rad["schwung"] = schwung_schritt(rad.get("schwung", 0.0), dt_s)
        rb, rh = mass or (bw, h - 2)
        if rad.get("wurf") is None and rad["schwung"] > SCHLEUDER_AB:
            rad["wurf"] = (jetzt_s, schleuder_wurf(labels, rad["pos"],   # abgerissen!
                                                   rad.get("richtung", 1), rb, rh))
        elif rad.get("wurf") and jetzt_s - rad.get("letzt", 0.0) > SCHLEUDER_RUHE:
            rad["wurf"] = None                    # in Ruhe gelassen → alle wieder drauf
            rad["schwung"] = 0.0
        if rad.get("wurf"):
            symbole_an = False                    # im Flug kein aufklappendes Symbol
        rad_stil = {"spur": C["faint"], "fern": C["faint"],
                    "nah": C["faint"] if gedimmt else C["dim"],
                    "rahmen": C["faint"] if gedimmt else C["acc"],
                    "vorn": C["dim"] if gedimmt else C["bright"] | curses.A_BOLD}
        if blass:                                 # weit weg: alles nur noch ein Hauch
            rad_stil = dict.fromkeys(rad_stil, C["faint"])
        # Pixel-Symbole (tui/pixel.py): hinten eine Pille, vorn klappt das
        # Symbol auf (0,23 s), beim Wegdrehen wieder zu (0,17 s). Ohne 256
        # Farben bleibt es beim gewohnten Rahmen-Schriftzug.
        jetzt = time.monotonic()
        symbole = None
        pix_bg = C.get("pix_bg")
        if symbole_an:
            dt = min(0.1, jetzt - RAD["takt"]) if RAD["takt"] else 0.0
            RAD["takt"] = jetzt
            if pix_bg is not None and PIX_MODUS != "off":
                vorn = rad_symbol_vorn()
                symbole = {}
                for name in RAD_SYMBOLE:
                    alt = RAD["offen"].get(name, 0.0)
                    neu = rad_offen_schritt(alt, vorn == name, dt)
                    if neu >= 1 and alt < 1:
                        RAD["offen_seit"][name] = jetzt
                    RAD["offen"][name] = symbole[name] = neu
                RAD["schnell"] = any(0 < v < 1 for v in symbole.values()) or (
                    vorn is not None and symbole.get(vorn, 0) < 1)
            else:
                RAD["schnell"] = False
        farben = "nacht" if pix_bg is not None and sum(pix_bg) < 384 else "tag"
        pmodus = "half" if PIX_MODUS == "half" else "mix"

        def zeichne_symbol(name, y, x):
            """Pixel-Symbol, Schriftplatte auf Zeile y, mittig um x."""
            offen = round(symbole.get(name, 0.0), 2)
            t_ms = 0
            if offen >= 1:
                t_ms = int((jetzt - RAD["offen_seit"].get(name, jetzt)) * 1000) // 60 * 60
            zeilen, schrift = pixel.symbol_zellen(name, offen, t_ms, farben, pmodus)
            r0, c0 = y - pixel.EL_LABEL_ZEILE, x - pixel.EL_W // 2
            for r, line in enumerate(zeilen):
                yy = r0 + r
                if not (y0 < yy < y0 + h - 1):
                    continue
                for c, z in enumerate(line):
                    xx = c0 + c
                    if z and bx < xx < bx + bw - 1:
                        safe_addstr(yy, xx, z[0], pix_attr(z[1], z[2]))
            for c, ch, fg, bg in schrift:
                if (y0 < r0 + pixel.EL_LABEL_ZEILE < y0 + h - 1
                        and bx < c0 + c < bx + bw - 1):       # nie über den Rahmen
                    safe_addstr(r0 + pixel.EL_LABEL_ZEILE, c0 + c, ch,
                                pix_attr(fg, bg) | curses.A_BOLD)

        zeilen = rad_zeilen(labels, rad["pos"], rb, rh, symbole)
        if rad.get("wurf"):                       # leeres Rad + geradeaus fliegende Apps
            t0, teile = rad["wurf"]
            zeilen = [z for z in zeilen if z[3] == "spur"] + wurf_zeilen(teile, jetzt_s - t0)
        if not zeilen and labels and mitte is None:
            # Liste statt Ellipse: die gewählte mittig, Nachbarn drumherum.
            vorn = rad_index(rad["sel"], len(labels))
            platz = max(1, h - 2)
            lo, hi = -((len(labels) - 1) // 2), len(labels) // 2   # jede App einmal
            for k in range(max(lo, -(platz // 2)), min(hi, platz - platz // 2 - 1) + 1):
                name = labels[(vorn + k) % len(labels)]
                yy = y0 + 1 + platz // 2 + k
                if k == 0:
                    addclip(yy, bx + 2, "▸ " + name.upper(), bw - 4, rad_stil["vorn"])
                else:
                    addclip(yy, bx + 4, name, bw - 6, C["faint"])
            return
        for dy, dx, txt, st in zeilen:
            y, x = cyc + dy, ccx + dx
            if st.startswith("symbol:"):
                zeichne_symbol(st[7:], y, x)
                continue
            if st in ("pille", "pille_fern"):            # getönter Grund, halbe Kappen
                if y0 < y < y0 + h - 1 and bx < x - 1 and x + len(txt) + 1 < bx + bw:
                    grund, schrift = pixel.symbol_pille(txt.strip(), st == "pille_fern", farben)
                    safe_addstr(y, x - 1, "▐", pix_attr(grund, pix_bg))
                    safe_addstr(y, x, txt, pix_attr(schrift, grund)
                                | (curses.A_BOLD if st == "pille" else 0))
                    safe_addstr(y, x + len(txt), "▌", pix_attr(grund, pix_bg))
                continue
            if y0 < y < y0 + h - 1 and bx < x and x + len(txt) < bx + bw:
                safe_addstr(y, x, txt, rad_stil.get(st, C["faint"]))

    def zeichne_galaxie(self, top, body_h, W, up, nets, state):
        """Die Galaxie (seit 03.10.2026): EINE Fläche. Zwei Sonnensysteme
        (Apps, Technik) auf einer riesigen Bahn — im Ausschnitt nur ein
        flacher Bogen, die beiden liegen praktisch nebeneinander. ✦ = Sonne
        des Systems, GROSS = gewählt, ● = man ist drin.
        -> läuft unten gerade eine Log-Zeile als Laufschrift?"""
        C, META, RAD, TRAD = self.z.C, self.META, self.RAD, self.TRAD
        addclip, draw_box, safe_addstr = self.z.addclip, self.z.draw_box, self.z.safe_addstr
        draw_rad, draw_stdout = self.draw_rad, self.technik.draw_stdout
        draw_box(top, 0, body_h, W, "zentrale")
        jetzt_g = time.monotonic()
        fahrt = META["fahrt"]
        if META["gpos"] != META["gsel"] and (fahrt is None or fahrt[1] != META["gsel"]):
            fahrt = META["fahrt"] = (META["gpos"], META["gsel"], jetzt_g)  # neu / umgelenkt
        if fahrt:
            META["gpos"] = galaxie_schritt(fahrt[0], fahrt[1], jetzt_g - fahrt[2])
            if META["gpos"] == fahrt[1]:
                META["fahrt"] = None
        gcx = W // 2
        gcy = top + (body_h * 9) // 16
        bogen = max(1, body_h // 12)              # so viel sackt der Bogen zum Rand ab
        innen = lambda yy, xx: top < yy < top + body_h - 1 and 0 < xx < W - 1  # noqa: E731
        systeme = [("apps", [a[1] for a in RAD_APPS], RAD),
                   ("technik", [a[0] for a in TECH_APPS], TRAD)]
        breiten = (0.55, 0.36)                    # das App-Rad trägt 9 Apps, Technik 3
        rad_h = max(6, body_h // 2)
        lage = []                                 # (i, naehe, cy, cx, rx, ry, rad_b)
        for i, quer, naehe in galaxie_lage(META["gpos"], breiten):
            rad_b = int(W * breiten[i])
            lage.append((i, naehe, gcy - int(round(quer * quer * bogen)),
                         gcx + int(round(quer * W / 2)),
                         min(rad_b // 2 - 10, 38), max(1, min(3, (rad_h - 4) // 4)),
                         rad_b))
        # der Bogen der Galaxie: kaum zu sehen, weit gepunktet, und dort
        # ausgespart, wo ein Sonnensystem liegt
        for xx in range(2, W - 2, 5):
            q = (xx - gcx) / (W / 2)
            yy = gcy - int(round(q * q * bogen))
            if innen(yy, xx) and not any(abs(yy - l[2]) <= l[5] + 1
                                         and abs(xx - l[3]) <= l[4] + 8 for l in lage):
                safe_addstr(yy, xx, "·", C["faint"])
        for i, naehe, cy, cx, _rx, _ry, rad_b in lage:
            name, labels, rad = systeme[i]
            gewaehlt = META["fokus"] == i and naehe > 0.98
            # Sonne ZUERST: ein aufgeklapptes Pixel-Symbol (elektronik)
            # ragt bis in die Mitte und muss über ihr liegen, nicht drunter.
            if gewaehlt:
                sonne, sonne_attr = "✦ " + name.upper(), C["acc"] | curses.A_BOLD
            else:
                sonne, sonne_attr = "✦ " + name, C["faint"]
            sx = cx - len(sonne) // 2
            if innen(cy, sx) and innen(cy, sx + len(sonne)):
                safe_addstr(cy, sx, sonne, sonne_attr)
            # Pixel-Symbole nur im nahen Rad — weit draussen und blass
            # wäre ein leuchtend blaues Feld genau falsch.
            draw_rad(top, body_h, 0, W, labels, rad, symbole_an=(i == 0 and naehe >= 0.5),
                     gedimmt=not gewaehlt, mitte=(cy, cx),
                     mass=(rad_b, rad_h), blass=naehe < 0.5)
        lz = "up %s · net %s" % (up, "traffic !" if nets else "offline ✓")
        addclip(top + 1, max(2, W - len(lz) - 3), lz, W - 4,
                C["warn"] if nets else C["faint"])
        if body_h >= 24:                          # unten die letzten Log-Zeilen
            return draw_stdout(top + body_h - 5, 0, 5, W,
                               state.get("logs", []) or [], None)
        return False
