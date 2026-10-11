# core/stil.py
#
# Das Aussehen eines Objekts als CSS-Eigenschaften (2026-10-10, Sasha:
# „kein eigenes Format"). Ein Stil ist ein dict {css-name: css-wert}, z. B.
# {"border-style": "dashed", "border-color": "#ff8800"}. Hier stehen die
# Wörter (welche Eigenschaften es gibt, welche Werte sie nehmen), die
# Prüfung und das Lesen von Hex-Farben — damit Backend, TUI (Stylebox in
# tui/bausteine/stylebox.py) und spätere Oberflächen dieselbe Liste haben.
#
# Welche Eigenschaften ein Objekt anbietet, sagt der Aufrufer; `schema()`
# beschreibt sie als JSON Schema 2020-12 (dieselbe Teilmenge wie die
# Kachel-Parameter, core/kachel_parameter.py), damit jede Oberfläche daraus
# ihren Dialog baut.
#
# Werte bewusst enger als CSS (2026-10-10): Farben nur als #rrggbb (das kann
# jede Oberfläche ohne Farbnamen-Tabelle), Rahmen nur Stile, die ein
# Terminal mit Kastenzeichen zeigen kann. Muster gibt es in CSS nicht als
# Wort — deshalb eine eigene Eigenschaft `--zentrale-muster`; eigene
# Eigenschaften mit `--` sind Standard-CSS (Custom Properties).
#
# Nur Standardbibliothek, keine Kern-Imports: die TUI darf es durch ihre
# Tür (memory/system/bauplan_kern.md), auch auf dem Pi.
# Doku: memory/system/bausteine_farbe_stil.md.
#
# Fundament (Schicht 1).

import re

ENTWURF = "https://json-schema.org/draft/2020-12/schema"
HEX_MUSTER = "^#[0-9a-fA-F]{6}$"
_HEX = re.compile(r"#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})")

MUSTER_EIGENSCHAFT = "--zentrale-muster"

# Rahmen: CSS border-style, nur was ein Terminal zeichnen kann.
RAHMEN = (("solid", "durchgezogen"), ("dashed", "gestrichelt"),
          ("dotted", "gepunktet"), ("double", "doppelt"), ("none", "keiner"))

# Innenmuster (`--zentrale-muster`): Name → Anzeigename. Was ein Browser
# daraus macht, steht in der Doku (CSS-Abbildung); die TUI hat ihre Zeichen
# in der Stylebox.
MUSTER = (("none", "keins"), ("punkte", "Punkte"), ("raster", "Raster"),
          ("dicht", "dicht"), ("streifen", "Streifen"), ("schraeg", "schräg"),
          ("karo", "Karo"))

# Nur EIN „nichts" (11.10.2026, Sasha): nicht gesetzt (‹ keine ›, die
# Eigenschaft fehlt). Das alte „none" („keiner"/„keins") wird nicht mehr
# angeboten — weder im Schema noch in der Stylebox. Gelesen wird es weiter
# (alte Stile, .ics): wert_pruefen nimmt es an, Oberflächen behandeln es als
# nicht gesetzt (alt_nichts). RAHMEN/MUSTER bleiben vollständig, weil das
# KI-Werkzeug set_calendar_style (core/werkzeug_kalender.py) sie so reicht.
NICHTS = "none"
ALT_NICHTS = frozenset({"border-style", MUSTER_EIGENSCHAFT})


def alt_nichts(name, wert):
    """Ist das ein altes „none", das heute „nicht gesetzt" heißt?"""
    return name in ALT_NICHTS and str(wert or "").strip().lower() == NICHTS


def _ohne_nichts(paare):
    return tuple((w, t) for w, t in paare if w != NICHTS)


def _farbe(titel):
    return {"type": "string", "title": titel, "pattern": HEX_MUSTER}


def _wahl(titel, paare, vorgabe=None):
    s = {"type": "string", "title": titel,
         "oneOf": [{"const": w, "title": t} for w, t in paare]}
    if vorgabe is not None:
        s["default"] = vorgabe
    return s


# Alle Eigenschaften, die ZENTRALE kennt — als Schema-Stücke. Reihenfolge =
# Reihenfolge in Dialogen, wenn der Aufrufer nur „alle" sagt.
EIGENSCHAFTEN = {
    "border-style": _wahl("Rahmen", _ohne_nichts(RAHMEN), "solid"),
    "border-color": _farbe("Rahmenfarbe"),
    "background-color": _farbe("Fläche"),
    "color": _farbe("Schrift"),
    MUSTER_EIGENSCHAFT: _wahl("Muster", _ohne_nichts(MUSTER)),     # ohne: kein Muster
    # Icon hochladen gibt es noch nicht: das Feld steht da, ist aber
    # gesperrt (readOnly ist ein Standard-Schlüsselwort), 2026-10-10.
    "background-image": {"type": "string", "title": "Icon",
                         "description": "noch gesperrt", "readOnly": True,
                         "pattern": r"^(none|url\(.+\))$"},
}
GESPERRT = frozenset(n for n, s in EIGENSCHAFTEN.items() if s.get("readOnly"))
FARBEN = frozenset(n for n, s in EIGENSCHAFTEN.items() if s.get("pattern") == HEX_MUSTER)


# ── Hex-Farben (CSS #rrggbb) ────────────────────────────────────────────────
def hex_lesen(text):
    """'#FF8800', 'ff8800', '#f80' → '#ff8800'; alles andere → None."""
    m = _HEX.fullmatch(str(text or "").strip())
    if not m:
        return None
    ziffern = m.group(1).lower()
    if len(ziffern) == 3:
        ziffern = "".join(z * 2 for z in ziffern)
    return "#" + ziffern


def hex_zu_rgb(text):
    """'#ff8800' → (255, 136, 0); ungültig → ValueError."""
    h = hex_lesen(text)
    if h is None:
        raise ValueError("keine farbe: %r" % (text,))
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def rgb_zu_hex(rgb):
    """(255, 136, 0) → '#ff8800' (Werte auf 0..255 gerundet und begrenzt)."""
    return "#" + "".join("%02x" % max(0, min(255, round(v))) for v in rgb)


# ── Schema und Prüfung ──────────────────────────────────────────────────────
def schema(namen=None):
    """JSON Schema (object) für die angebotenen Eigenschaften, in dieser
    Reihenfolge. `namen` = Liste von CSS-Namen (None = alle). Unbekannte
    Namen → ValueError, damit ein Tippfehler im Aufrufer sofort auffällt."""
    namen = list(EIGENSCHAFTEN) if namen is None else list(namen)
    fremd = [n for n in namen if n not in EIGENSCHAFTEN]
    if fremd:
        raise ValueError("unbekannte stil-eigenschaft: %s" % ", ".join(map(str, fremd)))
    return {"$schema": ENTWURF, "type": "object", "additionalProperties": False,
            "properties": {n: dict(EIGENSCHAFTEN[n]) for n in namen}}


def namen_aus(optionen):
    """Was ein Aufrufer als Angebot reicht → Liste der Namen. Erlaubt: Liste
    von Namen oder ein Schema wie aus `schema()`."""
    if isinstance(optionen, dict):
        return list((optionen.get("properties") or {}).keys())
    return list(optionen or [])


def wert_pruefen(name, wert):
    """Ein Wert für eine Eigenschaft → (sauberer_wert, None) oder (None, grund)."""
    s = EIGENSCHAFTEN.get(name)
    if s is None:
        return None, "unbekannte eigenschaft: %s" % name
    if not isinstance(wert, str):
        return None, "%s: text erwartet" % s["title"]
    if name in FARBEN:
        h = hex_lesen(wert) if wert.strip().startswith("#") else None
        return (h, None) if h else (None, "%s: farbe als #rrggbb" % s["title"])
    if "oneOf" in s:
        erlaubt = [w["const"] for w in s["oneOf"]]
        w = wert.strip().lower()
        if alt_nichts(name, w):                 # altes „none": lesbar, nicht angeboten
            return w, None
        return (w, None) if w in erlaubt else (
            None, "%s: eins von %s" % (s["title"], ", ".join(erlaubt)))
    if s.get("pattern") and not re.fullmatch(s["pattern"], wert.strip()):
        return None, "%s: ungültiger wert" % s["title"]
    return wert.strip(), None


def pruefen(stil, namen=None, entfernen=False):
    """Ein Stil-dict → gesäubertes dict (Farben klein und sechsstellig).
    Eigenschaften außerhalb von `namen` (falls gegeben) oder mit falschem
    Wert → ValueError mit einem deutschen Satz. `entfernen=True` prüft eine
    Änderung (Rückgabe der Stylebox): dort heißt None „Eigenschaft
    entfernen" und bleibt None."""
    if not isinstance(stil, dict):
        raise ValueError("stil muss ein dict sein")
    erlaubt = set(EIGENSCHAFTEN if namen is None else namen)
    raus = {}
    for name, wert in stil.items():
        if name not in erlaubt:
            raise ValueError("nicht angeboten: %s" % name)
        if wert is None and entfernen:
            raus[name] = None
            continue
        sauber, grund = wert_pruefen(name, wert)
        if grund:
            raise ValueError(grund)
        raus[name] = sauber
    return raus


def unterschied(alt, neu):
    """Nur, was sich gegenüber `alt` geändert hat — eine Änderung: neue oder
    andere Werte, und was in `alt` stand, in `neu` aber fehlt, als None
    („entfernen", 2026-10-10). Es gilt `anwenden(alt, unterschied(alt, neu))
    == neu`."""
    alt, neu = alt or {}, neu or {}
    raus = {k: v for k, v in neu.items() if alt.get(k) != v}
    raus.update({k: None for k in alt if k not in neu})
    return raus


def anwenden(alt, aenderung):
    """Eine Änderung (z. B. die Rückgabe der Stylebox) auf einen Stil → neues
    dict; `alt` bleibt unberührt. Wert None = Eigenschaft entfernen.
    Aufrufer nehmen das statt `dict.update`: update würde None als Wert
    hineinschreiben (2026-10-10, Kalender: „Eigenschaft entfernen")."""
    raus = dict(alt or {})
    for name, wert in (aenderung or {}).items():
        if wert is None:
            raus.pop(name, None)
        else:
            raus[name] = wert
    return raus


# ── Angebot für einen Kasten (Termin im Kalender, 2026-10-10) ──────────────
# Sasha: „In der Stylebox kann man den Kasten genau stylen: Rahmenstil +
# Rahmenfarbe, Innenfarbe, Schriftfarbe, Innenmuster; ‚Icon hochladen' wird
# angezeigt, bleibt aber gesperrt." Backend (core/kalender.py prüft damit)
# und TUI (Formular-Feld „Stylebox") reichen dieselbe Liste.
KASTEN = ("border-style", "border-color", "background-color", "color",
          MUSTER_EIGENSCHAFT, "background-image")


# ── Als CSS-Deklarationsliste (Text) ────────────────────────────────────────
# Für Speicher, die nur Text kennen (.ics: X-ZENTRALE-STIL). Standard-CSS, wie
# im style-Attribut von HTML: „border-style: double; border-color: #ff8800".
def als_css(stil):
    """dict → „name: wert; name: wert" in der Reihenfolge von EIGENSCHAFTEN
    (gleicher Stil = gleicher Text). Leeres dict → ""."""
    stil = stil or {}
    reihe = [n for n in EIGENSCHAFTEN if n in stil] + sorted(n for n in stil if n not in EIGENSCHAFTEN)
    return "; ".join("%s: %s" % (n, stil[n]) for n in reihe)


def aus_css(text):
    """„name: wert; …" → dict (roh, ungeprüft — danach `pruefen`). Ein `;`
    in Klammern oder Anführungszeichen (url("a;b")) trennt nicht. Kaputte
    Stücke ohne Doppelpunkt → ValueError."""
    teile, jetzt, tiefe, quote = [], "", 0, None
    for ch in str(text or ""):
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            tiefe += 1
        elif ch == ")":
            tiefe = max(0, tiefe - 1)
        elif ch == ";" and tiefe == 0:
            teile.append(jetzt)
            jetzt = ""
            continue
        jetzt += ch
    teile.append(jetzt)
    raus = {}
    for stueck in teile:
        if not stueck.strip():
            continue
        name, doppel, wert = stueck.partition(":")
        if not doppel or not name.strip():
            raise ValueError("keine css-deklaration: %r" % stueck.strip())
        raus[name.strip().lower()] = wert.strip()
    return raus


# ── CSS3-Farbnamen (für iCalendar COLOR, RFC 7986) ──────────────────────────
# RFC 7986 will als COLOR einen CSS3-Farbnamen, kein Hex. Wer nur COLOR liest
# (Thunderbird, Apple), bekommt den nächsten Namen; den genauen Hex trägt die
# Stil-Zeile daneben. Die 147 Namen aus CSS Color Module Level 3, §4.3.
_CSS3 = (
    "aliceblue f0f8ff antiquewhite faebd7 aqua 00ffff aquamarine 7fffd4 azure f0ffff "
    "beige f5f5dc bisque ffe4c4 black 000000 blanchedalmond ffebcd blue 0000ff "
    "blueviolet 8a2be2 brown a52a2a burlywood deb887 cadetblue 5f9ea0 chartreuse 7fff00 "
    "chocolate d2691e coral ff7f50 cornflowerblue 6495ed cornsilk fff8dc crimson dc143c "
    "cyan 00ffff darkblue 00008b darkcyan 008b8b darkgoldenrod b8860b darkgray a9a9a9 "
    "darkgreen 006400 darkgrey a9a9a9 darkkhaki bdb76b darkmagenta 8b008b "
    "darkolivegreen 556b2f darkorange ff8c00 darkorchid 9932cc darkred 8b0000 "
    "darksalmon e9967a darkseagreen 8fbc8f darkslateblue 483d8b darkslategray 2f4f4f "
    "darkslategrey 2f4f4f darkturquoise 00ced1 darkviolet 9400d3 deeppink ff1493 "
    "deepskyblue 00bfff dimgray 696969 dimgrey 696969 dodgerblue 1e90ff firebrick b22222 "
    "floralwhite fffaf0 forestgreen 228b22 fuchsia ff00ff gainsboro dcdcdc "
    "ghostwhite f8f8ff gold ffd700 goldenrod daa520 gray 808080 green 008000 "
    "greenyellow adff2f grey 808080 honeydew f0fff0 hotpink ff69b4 indianred cd5c5c "
    "indigo 4b0082 ivory fffff0 khaki f0e68c lavender e6e6fa lavenderblush fff0f5 "
    "lawngreen 7cfc00 lemonchiffon fffacd lightblue add8e6 lightcoral f08080 "
    "lightcyan e0ffff lightgoldenrodyellow fafad2 lightgray d3d3d3 lightgreen 90ee90 "
    "lightgrey d3d3d3 lightpink ffb6c1 lightsalmon ffa07a lightseagreen 20b2aa "
    "lightskyblue 87cefa lightslategray 778899 lightslategrey 778899 "
    "lightsteelblue b0c4de lightyellow ffffe0 lime 00ff00 limegreen 32cd32 linen faf0e6 "
    "magenta ff00ff maroon 800000 mediumaquamarine 66cdaa mediumblue 0000cd "
    "mediumorchid ba55d3 mediumpurple 9370db mediumseagreen 3cb371 "
    "mediumslateblue 7b68ee mediumspringgreen 00fa9a mediumturquoise 48d1cc "
    "mediumvioletred c71585 midnightblue 191970 mintcream f5fffa mistyrose ffe4e1 "
    "moccasin ffe4b5 navajowhite ffdead navy 000080 oldlace fdf5e6 olive 808000 "
    "olivedrab 6b8e23 orange ffa500 orangered ff4500 orchid da70d6 "
    "palegoldenrod eee8aa palegreen 98fb98 paleturquoise afeeee palevioletred db7093 "
    "papayawhip ffefd5 peachpuff ffdab9 peru cd853f pink ffc0cb plum dda0dd "
    "powderblue b0e0e6 purple 800080 red ff0000 rosybrown bc8f8f royalblue 4169e1 "
    "saddlebrown 8b4513 salmon fa8072 sandybrown f4a460 seagreen 2e8b57 "
    "seashell fff5ee sienna a0522d silver c0c0c0 skyblue 87ceeb slateblue 6a5acd "
    "slategray 708090 slategrey 708090 snow fffafa springgreen 00ff7f steelblue 4682b4 "
    "tan d2b48c teal 008080 thistle d8bfd8 tomato ff6347 turquoise 40e0d0 violet ee82ee "
    "wheat f5deb3 white ffffff whitesmoke f5f5f5 yellow ffff00 yellowgreen 9acd32").split()
CSS3_FARBEN = {_CSS3[i]: "#" + _CSS3[i + 1] for i in range(0, len(_CSS3), 2)}


def css_name(farbe):
    """'#ff8800' → nächster CSS3-Name ('darkorange'). Abstand „redmean"
    (grobe Annäherung ans Auge, ohne Farbraum-Bibliothek). Ungültig → None."""
    if hex_lesen(farbe) is None:
        return None
    r, g, b = hex_zu_rgb(farbe)

    def abstand(name):
        r2, g2, b2 = hex_zu_rgb(CSS3_FARBEN[name])
        rm = (r + r2) / 2
        return ((2 + rm / 256) * (r - r2) ** 2 + 4 * (g - g2) ** 2
                + (2 + (255 - rm) / 256) * (b - b2) ** 2)
    return min(CSS3_FARBEN, key=abstand)


def hex_aus_name(name):
    """CSS3-Name (oder Hex) → '#rrggbb'; Unbekanntes → None."""
    s = str(name or "").strip().lower()
    return CSS3_FARBEN.get(s) or (hex_lesen(s) if s.startswith("#") else None)


def kastenfarbe(stil):
    """Die EINE Farbe eines Kastens für Leser, die nur eine kennen (COLOR):
    Fläche, sonst Rahmen, sonst Schrift; keine → None."""
    for n in ("background-color", "border-color", "color"):
        if (stil or {}).get(n):
            return stil[n]
    return None
