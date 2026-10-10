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


def _farbe(titel):
    return {"type": "string", "title": titel, "pattern": HEX_MUSTER}


def _wahl(titel, paare, vorgabe):
    return {"type": "string", "title": titel, "default": vorgabe,
            "oneOf": [{"const": w, "title": t} for w, t in paare]}


# Alle Eigenschaften, die ZENTRALE kennt — als Schema-Stücke. Reihenfolge =
# Reihenfolge in Dialogen, wenn der Aufrufer nur „alle" sagt.
EIGENSCHAFTEN = {
    "border-style": _wahl("Rahmen", RAHMEN, "solid"),
    "border-color": _farbe("Rahmenfarbe"),
    "background-color": _farbe("Fläche"),
    "color": _farbe("Schrift"),
    MUSTER_EIGENSCHAFT: _wahl("Muster", MUSTER, "none"),
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
        return (w, None) if w in erlaubt else (
            None, "%s: eins von %s" % (s["title"], ", ".join(erlaubt)))
    if s.get("pattern") and not re.fullmatch(s["pattern"], wert.strip()):
        return None, "%s: ungültiger wert" % s["title"]
    return wert.strip(), None


def pruefen(stil, namen=None):
    """Ein Stil-dict → gesäubertes dict (Farben klein und sechsstellig).
    Eigenschaften außerhalb von `namen` (falls gegeben) oder mit falschem
    Wert → ValueError mit einem deutschen Satz."""
    if not isinstance(stil, dict):
        raise ValueError("stil muss ein dict sein")
    erlaubt = set(EIGENSCHAFTEN if namen is None else namen)
    raus = {}
    for name, wert in stil.items():
        if name not in erlaubt:
            raise ValueError("nicht angeboten: %s" % name)
        sauber, grund = wert_pruefen(name, wert)
        if grund:
            raise ValueError(grund)
        raus[name] = sauber
    return raus


def unterschied(alt, neu):
    """Nur, was sich gegenüber `alt` geändert hat (für die Rückgabe der
    Stylebox: der Aufrufer macht `stil.update(...)`)."""
    alt = alt or {}
    return {k: v for k, v in (neu or {}).items() if alt.get(k) != v}
