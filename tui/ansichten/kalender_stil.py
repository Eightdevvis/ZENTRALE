"""Aussehen eines Termins in den Kalender-Ansichten (Feld `stil`, 10.10.2026).

Sasha: „Im Terminformular gibt es NUR eine Option ‚Stylebox' … das Ergebnis
wird auf den Termin (seinen Container/Kasten im Kalender) angewendet." Ein
Stil ist ein dict aus CSS-Eigenschaften (core/stil.py), eingestellt in der
Stylebox (tui/bausteine/stylebox.py). Hier steht, wie er in A/B/C aussieht —
reine Funktionen auf der Leinwand von kalender_ansichten.py, kein curses.

Farben aus dem Stil sind Hex, keine Palettenrolle. Darum eine eigene
Rollenform: „$<schrift>$<grund>$<rolle>" (je sechs Hex-Ziffern oder leer).
kalender.py macht daraus ein Farbpaar (Kontext.pix_attr, im 256er-Modus
gerundet); <rolle> ist der Rückfall ohne Farben und liefert, was der Stil
offen lässt (z. B. die Kursfläche, wenn nur der Rahmen gefärbt ist).

Ohne Stil ändert sich nichts: Kurs-/Listenfarbe, Glas für uncommitted,
Gruppen bleiben, wie sie sind. Mit Stil:
  C  der Block: Rahmen rundherum, wenn er mind. 4×4 Zellen hat, sonst nur
     links und rechts (ab 3 Spalten), darunter gar keiner; Fläche, Schrift,
     Muster im Inneren.
  A  der Titel: ein Rahmenzeichen davor, Schrift in der Stilfarbe, mit
     Fläche als kleines Schild.
  B  die Zeile: Schrift in der Stilfarbe, Ganztägiges/Spannen als Fläche.
"""
from __future__ import annotations

try:
    from tui.bausteine.stylebox import RAHMEN_ZEICHEN, muster_zeichen
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine.stylebox import RAHMEN_ZEICHEN, muster_zeichen

import stil as stil_kern                # core/stil.py (Pfad: bausteine/__init__.py)

# Was die Stylebox im Terminformular anbietet — dieselbe Liste prüft das
# Backend (core/kalender.py, stil.KASTEN).
ANGEBOT = stil_kern.KASTEN
MARKE = "$"


# ── Stil lesen ─────────────────────────────────────────────────────────
def von(roh) -> dict:
    """Der Stil eines API-Eintrags, nur saubere Werte (Kaputtes fällt still
    weg — die Anzeige soll daran nie scheitern). Kein Stil → {}."""
    st = (roh or {}).get("stil") if isinstance(roh, dict) else None
    if not isinstance(st, dict):
        return {}
    raus = {}
    for name, wert in st.items():
        if name in ANGEBOT:
            sauber, grund = stil_kern.wert_pruefen(name, wert)
            if not grund:
                raus[name] = sauber
    return raus


def _rgb(h):
    return stil_kern.hex_zu_rgb(h)


def _mix(a, b, t):
    return stil_kern.rgb_zu_hex(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))


def _hell(h) -> float:
    def k(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (k(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lesbar_auf(grund) -> str:
    """Schwarz oder Weiß, je nachdem, was auf `grund` besser zu lesen ist —
    wenn der Stil eine Fläche, aber keine Schrift hat."""
    return "#000000" if _hell(grund) > 0.179 else "#ffffff"


def farben(st: dict) -> dict:
    """Stil → {schrift, grund, rand, leise, rahmen, muster} (Hex oder None).
    rahmen = CSS border-style oder None (kein Rahmen); eine Rahmenfarbe ohne
    Stil heißt durchgezogen (wie in der Stylebox-Vorschau)."""
    grund = st.get("background-color")
    schrift = st.get("color") or (lesbar_auf(grund) if grund else None)
    rand = st.get("border-color") or schrift
    rahmen = st.get("border-style") or ("solid" if st.get("border-color") else None)
    if rahmen == "none":
        rahmen = None
    leise = _mix(schrift, grund, .35) if schrift and grund else schrift
    return {"schrift": schrift, "grund": grund, "rand": rand, "leise": leise,
            "rahmen": rahmen, "muster": st.get(stil_kern.MUSTER_EIGENSCHAFT, "none")}


# ── Rollen „$schrift$grund$rückfall" ───────────────────────────────────
def rolle(basis: str, schrift=None, grund=None) -> str:
    """Palettenrolle + Hex-Farben → Rolle für die Leinwand; ohne Farben
    bleibt es die Palettenrolle."""
    if not schrift and not grund:
        return basis
    return "%s%s%s%s%s" % (MARKE, (schrift or "")[1:], MARKE, (grund or "")[1:], MARKE) + basis


def teile(r: str) -> tuple:
    """„$ff8800$$k_t3_inv" → ("k_t3_inv", "#ff8800", None); keine Stil-Rolle
    → (r, None, None)."""
    if not r.startswith(MARKE):
        return r, None, None
    _leer, s, g, basis = r.split(MARKE, 3)
    return basis, ("#" + s if s else None), ("#" + g if g else None)


def text_rolle(basis: str, st: dict) -> str:
    """Eine Textzeile auf dem Grund des Themes (A, B): Schrift in der Farbe
    des Stils — Schrift, sonst Rahmen, sonst Fläche."""
    farbe = st.get("color") or st.get("border-color") or st.get("background-color")
    return rolle(basis, farbe, None)


def flaechen_rolle(basis: str, st: dict) -> str:
    """Eine Fläche (Band in B/C, Spannen-Balken): Fläche + Schrift des Stils."""
    f = farben(st)
    return rolle(basis, f["schrift"], f["grund"])


# ── Formular: die Zeile „Stylebox" ─────────────────────────────────────
def vorschau_text(st: dict) -> str:
    """Kurz für die Formularzeile: „╔═╗ rand #ff8800 · fläche #202030 ·
    Punkte" — oder „keine"."""
    st = st or {}
    if not st:
        return "keine"
    f = farben(st)
    teile_ = []
    if f["rahmen"]:
        z = RAHMEN_ZEICHEN.get(f["rahmen"], RAHMEN_ZEICHEN["solid"])
        teile_.append(z[0] + z[1] + z[2])
    for name, wort in (("border-color", "rand"), ("background-color", "fläche"),
                       ("color", "schrift")):
        if st.get(name):
            teile_.append("%s %s" % (wort, st[name]))
    muster = st.get(stil_kern.MUSTER_EIGENSCHAFT)
    if muster and muster != "none":
        teile_.append(dict(stil_kern.MUSTER).get(muster, muster))
    if st.get("background-image") not in (None, "none"):
        teile_.append("icon")
    return " · ".join(teile_) if teile_ else "keine"


def vorschau_rahmen(st: dict):
    """(Zeichen, Rolle) für die drei Rahmenzeichen vorn in der Formularzeile
    — in der Rahmenfarbe auf der Fläche; None ohne Rahmen."""
    f = farben(st or {})
    if not f["rahmen"]:
        return None
    z = RAHMEN_ZEICHEN.get(f["rahmen"], RAHMEN_ZEICHEN["solid"])
    return z[0] + z[1] + z[2], rolle("dim", f["rand"], f["grund"])


# ── C: der Block ───────────────────────────────────────────────────────
def c_block(lw, y: int, x: int, w: int, h: int, texte: list, basis: str, st: dict,
            leise_basis: str | None = None, gewaehlt: bool = False) -> None:
    """Einen Block w×h ab (y, x) im Stil zeichnen. `texte` wie
    kalender_ansichten._c_zeilen (Zeile 1 Titel, darunter leise), `basis` die
    Fläche ohne Stil (z. B. „k_t3_inv"), `leise_basis` ihre leise Schrift.
    Gewählt: Farben der Auswahl (basis), die Rahmenform bleibt."""
    from .kalender_ansichten import kuerzen     # spät: die Ansichten importieren uns
    if w < 1 or h < 1:
        return
    f = farben(st)
    if gewaehlt:
        f = {**f, "schrift": None, "grund": None, "rand": None, "leise": None}
    leise_basis = leise_basis or basis
    voll = f["rahmen"] and w >= 4 and h >= 4          # rundherum
    seiten = f["rahmen"] and not voll and w >= 3      # nur links/rechts
    z = RAHMEN_ZEICHEN.get(f["rahmen"] or "solid", RAHMEN_ZEICHEN["solid"])
    rand = rolle(basis, f["rand"], f["grund"])
    fuell = rolle(basis, f["schrift"], f["grund"])
    leise = rolle(leise_basis, f["leise"], f["grund"])
    if voll:
        lw.setze(y, x, z[0] + z[1] * (w - 2) + z[2], rand)
        lw.setze(y + h - 1, x, z[4] + z[1] * (w - 2) + z[5], rand)
    iy0, iy1 = (y + 1, y + h - 2) if voll else (y, y + h - 1)
    ix0, iw = (x + 1, w - 2) if (voll or seiten) else (x, w)
    for k, yy in enumerate(range(iy0, iy1 + 1)):
        if voll or seiten:
            lw.setze(yy, x, z[3], rand)
            lw.setze(yy, x + w - 1, z[3], rand)
        txt = kuerzen(texte[k], iw) if k < len(texte) else ""
        ende = lw.setze(yy, ix0, txt, fuell if k == 0 else leise) if txt else ix0
        for cx in range(ende, ix0 + iw):
            zeichen = muster_zeichen(f["muster"], yy - y, cx - x) if f["muster"] != "none" else " "
            lw.setze(yy, cx, zeichen, leise if zeichen != " " else fuell)


# ── A: der Titel ───────────────────────────────────────────────────────
def a_titel(lw, y: int, x: int, w: int, titel: str, basis: str, st: dict) -> None:
    """Der Titel eines Termins in A ab Spalte x (Platz w): vorn das senkrechte
    Rahmenzeichen in der Rahmenfarbe, dann der Titel — mit Fläche als kleines
    Schild „ Uni ", sonst in der Schriftfarbe."""
    from .kalender_ansichten import kuerzen, text_breite   # spät, wie oben
    f = farben(st)
    if f["rahmen"] and x >= 2:
        z = RAHMEN_ZEICHEN.get(f["rahmen"], RAHMEN_ZEICHEN["solid"])
        lw.setze(y, x - 2, z[3], rolle("dim", f["rand"], None))
    if f["grund"]:
        t = kuerzen(titel, max(1, w - 2))
        lw.setze(y, x, " %s " % t, rolle(basis, f["schrift"], f["grund"]))
        if f["muster"] != "none":
            ende = x + text_breite(t) + 2
            lw.setze(y, ende, muster_zeichen(f["muster"], 0, 0) * min(2, max(0, x + w - ende)),
                     rolle(basis, f["leise"], f["grund"]))
        return
    lw.setze(y, x, kuerzen(titel, w), text_rolle(basis, st))
