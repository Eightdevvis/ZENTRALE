# tui/bausteine/feld_dialog.py
#
# Ein kleiner Dialog, gebaut aus einem JSON Schema (2026-10-10). Das Schema
# kommt aus dem Katalog des Hubs (`GET /api/kacheln`, je Eintrag
# `parameter`; memory/hub/hub_bauplan.md „Katalog", core/
# kachel_parameter.py) — der Dialog kennt keine App. So bringt eine neue App
# ihren Anlege-Dialog mit, ohne dass die TUI etwas über sie weiß. Bis
# 2026-10-10 war es eine selbst erfundene `felder`-Liste; Sasha: Standards
# statt Eigenformat.
#
# Gelesen wird nur die Teilmenge, die der Hub benutzt — ohne Paket, die TUI
# bleibt bei der Standardbibliothek: properties mit type string|integer|
# number|boolean, title, description, default, minimum/maximum,
# minLength/maxLength, format date, oneOf [{const, title}] oder enum;
# deprecated (Feld wird nicht angeboten); required; allOf [{if:
# {properties: {x: {const}}}, then: {required, properties: {y: false}}}]
# (y gilt dann nicht). Der Dialog prüft nur leicht
# (Typ, Grenzen, Pflicht); Herr über die Regeln ist der Hub — was er
# ablehnt (z. B. „höchstens 31 tage" zwischen zwei Daten, was JSON Schema
# nicht sagen kann), zeigt der Dialog als `fehler`.
#
# Nur Tastatur: ↑↓ (tab) Feld, ←→ (leertaste) wählt bei Auswahl/ja-nein,
# Ziffern/„-"/Text tippen, ⌫ löscht, enter (ctrl+s) legt an, esc bricht ab.
# Ein Modal im Sinn von canvas_arten.py (titel, taste, anzeige,
# aenderungen) mit eigener Tastentabelle (2026-10-11): die Ansicht richtet
# sich nach dem Feld unter dem Cursor (tippen | waehlen) und danach, ob es
# mehr als ein Feld gibt (nur dann gehen ↑↓).

from datetime import date

try:
    from tui.bausteine import tastenteil
except ImportError:                     # als Skript gestartet: tui/ liegt im Pfad
    from bausteine import tastenteil

TIPPEN = ("zahl", "datum", "text")


def _bedingung(wenn):
    """`if` eines allOf-Eintrags → {name: wert} (nur const/ein enum-Wert)."""
    raus = {}
    for name, s in ((wenn or {}).get("properties") or {}).items():
        if isinstance(s, dict) and "const" in s:
            raus[name] = s["const"]
        elif isinstance(s, dict) and len(s.get("enum") or []) == 1:
            raus[name] = s["enum"][0]
    return raus


def regeln(schema):
    """Die if/then-Regeln eines Schemas → [(bedingung, then)]."""
    teile = [x for x in schema.get("allOf") or [] if isinstance(x, dict)] + [schema]
    return [(_bedingung(t["if"]), t.get("then") or {})
            for t in teile if isinstance(t.get("if"), dict)]


def feld_aus(name, s):
    """Eine Eigenschaft des Schemas → Feld (dict) für den Dialog."""
    typ = s.get("type")
    f = {"name": name, "titel": str(s.get("title") or name), "hilfe": s.get("description"),
         "vorgabe": s.get("default"), "min": s.get("minimum"), "max": s.get("maximum"),
         "max_laenge": s.get("maxLength")}
    wahl = [(w.get("const"), str(w.get("title") or w.get("const")))
            for w in s.get("oneOf") or [] if isinstance(w, dict) and "const" in w]
    wahl = wahl or [(w, str(w)) for w in s.get("enum") or []]
    if wahl:
        f.update(art="wahl", wahl=wahl)
    elif typ == "boolean":
        f["art"] = "bool"
    elif typ in ("integer", "number"):
        f.update(art="zahl", ganz=typ == "integer")
    elif s.get("format") == "date":
        f["art"] = "datum"
    else:
        f["art"] = "text"
    return f


def _wert(f, roh):
    """Eingabe → (wert, None) oder (None, grund)."""
    if f["art"] == "zahl":
        s = str(roh).strip()
        try:
            wert = int(s) if f.get("ganz") else (float(s) if "." in s else int(s))
        except ValueError:
            spanne = " (%s bis %s)" % (f["min"] if f["min"] is not None else "…",
                                       f["max"] if f["max"] is not None else "…")
            art = "eine ganze zahl" if f.get("ganz") else "eine zahl"
            return None, "%s: %s%s" % (f["titel"], art,
                                       spanne if (f["min"], f["max"]) != (None, None) else "")
        return wert, None
    if f["art"] == "datum":
        try:
            return date.fromisoformat(str(roh)).isoformat(), None
        except ValueError:
            return None, "%s: datum als JJJJ-MM-TT" % f["titel"]
    return roh, None


def _grenze(f, wert):
    if f["art"] == "zahl" and f["max"] is not None and wert > f["max"]:
        return "höchstens %s %s" % (f["max"], f["titel"])
    if f["art"] == "zahl" and f["min"] is not None and wert < f["min"]:
        return "%s: mindestens %s" % (f["titel"], f["min"])
    if f["art"] == "text" and f["max_laenge"] is not None and len(wert) > f["max_laenge"]:
        return "%s: höchstens %d zeichen" % (f["titel"], f["max_laenge"])
    return None


class FeldDialog:
    """Dialog aus einem JSON Schema (Katalog `parameter`). aenderungen() →
    {"werte": {name: wert}} mit getypten Werten, nur Felder, die gerade
    gelten."""
    breite = 52

    # Tasten: Feld unter dem Cursor tippen oder wählen; „felder:" = mehr als
    # ein Feld (dann ↑↓/tab), „leer" = kein Feld gilt gerade.
    _ENDE = [("enter", "nehmen", "add"), ("ctrl+s", "nehmen"), ("esc", "abbrechen", "cancel")]
    _TIPPEN = [("type", "tippen", "type"), ("⌫", "zurueck")]
    _WAEHLEN = [("←→", "wert", "choose"), ("space", "wert")]
    _FELDER = [("↑↓", "feld", "field"), ("tab/shift+tab", "feld")]
    TASTEN = {
        "tippen": _TIPPEN + _ENDE, "waehlen": _WAEHLEN + _ENDE,
        "felder:tippen": _FELDER + _TIPPEN + _ENDE, "felder:waehlen": _FELDER + _WAEHLEN + _ENDE,
        "leer": _ENDE,
    }

    def __init__(self, schema, titel="neu", kopf=None):
        schema = schema if isinstance(schema, dict) else {}
        self.schema = schema
        props = schema.get("properties") or {}
        self.felder = [feld_aus(n, s) for n, s in props.items()   # deprecated: nur für alte Werte
                       if isinstance(s, dict) and not s.get("deprecated")]
        self.pflicht = set(schema.get("required") or [])
        self.regeln = regeln(schema)
        self.titel = titel
        self.kopf = kopf or titel
        self.eingabe = {}                    # name → Text (tippen) oder Wert (wahl/bool)
        for f in self.felder:
            v = f["vorgabe"]
            if f["art"] == "wahl":
                werte = [w for w, _t in f["wahl"]]
                self.eingabe[f["name"]] = v if v in werte else werte[0]
            elif f["art"] == "bool":
                self.eingabe[f["name"]] = bool(v)
            else:
                self.eingabe[f["name"]] = "" if v is None else str(v)
        self.feld = 0
        self.fehler = ""                     # auch von außen (Hub sagt nein)
        self.werte = None

    @property
    def hoehe(self):
        hilfe = sum(1 for f in self.felder if f.get("hilfe"))
        return len(self.felder) + hilfe + 6

    # ── Zustand ───────────────────────────────────────────────────────
    def _geltende_regeln(self):
        return [then for wenn, then in self.regeln
                if all(self.eingabe.get(k) == v for k, v in wenn.items())]

    def sichtbar(self):
        """Die Felder, die bei den jetzigen Eingaben gelten (if/then)."""
        aus = {n for then in self._geltende_regeln()
               for n, s in (then.get("properties") or {}).items() if s is False}
        return [f for f in self.felder if f["name"] not in aus]

    def _muss(self, name):
        return name in self.pflicht or any(name in (then.get("required") or [])
                                           for then in self._geltende_regeln())

    def pruefen(self):
        """→ (werte, None) oder (None, grund) — leicht; der Hub prüft ganz."""
        werte = {}
        for f in self.sichtbar():
            roh = self.eingabe[f["name"]]
            if f["art"] in TIPPEN and roh == "":
                if self._muss(f["name"]):
                    return None, "%s fehlt" % f["titel"]
                if f["art"] != "text":
                    continue
            wert, grund = _wert(f, roh)
            grund = grund or _grenze(f, wert)
            if grund:
                return None, grund
            werte[f["name"]] = wert
        return werte, None

    def _aktuell(self):
        felder = self.sichtbar()
        self.feld = max(0, min(self.feld, len(felder) - 1))
        return felder[self.feld] if felder else None

    def __repr__(self):                  # Zustand sichtbar (Tests vergleichen repr)
        return "FeldDialog(%r)" % ((self.feld, self.eingabe, self.fehler),)

    # ── Tasten ────────────────────────────────────────────────────────
    def ansicht(self):
        f = self._aktuell()
        if f is None:
            return "leer"
        art = "tippen" if f["art"] in TIPPEN else "waehlen"
        return ("felder:" + art) if len(self.sichtbar()) > 1 else art

    def taste(self, ch):
        return tastenteil.verteilen(self, ch)

    def aktion_abbrechen(self, _taste):
        return "abbrechen"

    def aktion_nehmen(self, _taste):
        self.werte, self.fehler = self.pruefen()
        self.fehler = self.fehler or ""
        return "speichern" if self.werte is not None else None

    def aktion_feld(self, taste):
        n = len(self.sichtbar())
        self.feld = (self.feld + (-1 if taste in ("up", "shift+tab") else 1)) % n
        self.fehler = ""

    def aktion_wert(self, taste):
        f = self._aktuell()
        name = f["name"]
        if f["art"] == "wahl":
            werte = [w for w, _t in f["wahl"]]
            i = werte.index(self.eingabe[name]) if self.eingabe[name] in werte else 0
            self.eingabe[name] = werte[(i + (-1 if taste == "left" else 1)) % len(werte)]
        else:                                    # ja/nein
            self.eingabe[name] = not self.eingabe[name]
        self.fehler = ""

    def aktion_zurueck(self, _taste):
        f = self._aktuell()
        self.eingabe[f["name"]] = self.eingabe[f["name"]][:-1]
        self.fehler = ""

    def aktion_tippen(self, zeichen):
        f = self._aktuell()
        if self._passt(f, ord(zeichen)):
            self.eingabe[f["name"]] += zeichen
            self.fehler = ""

    def _passt(self, f, ch):
        """Darf dieses Zeichen in dieses Feld?"""
        if not 32 <= ch < 127:
            return False
        c, text = chr(ch), self.eingabe[f["name"]]
        if f["art"] == "zahl":
            komma = c == "." and not f.get("ganz") and "." not in text
            return (c.isdigit() or c == "-" and not text or komma) and len(text) < 9
        if f["art"] == "datum":
            return (c.isdigit() or c == "-") and len(text) < 10
        return len(text) < (f["max_laenge"] or 200)

    # ── Zeichnen ──────────────────────────────────────────────────────
    def _zeigen(self, f):
        v = self.eingabe[f["name"]]
        if f["art"] == "wahl":
            return "‹ %s ›" % next((t for w, t in f["wahl"] if w == v), v)
        if f["art"] == "bool":
            return "‹ %s ›" % ("ja" if v else "nein")
        return str(v)

    def anzeige(self, breite, hoehe):
        felder = self.sichtbar()
        aktuell = self._aktuell()
        rand = max([len(f["titel"]) for f in self.felder] + [3]) + 2
        zeilen, cursor = [], (0, 0)
        for f in felder:
            if f is aktuell:
                spalte = rand if f["art"] not in TIPPEN else rand + len(self.eingabe[f["name"]])
                cursor = (len(zeilen), spalte)
            zeilen.append(f["titel"].ljust(rand) + self._zeigen(f))
            if f.get("hilfe"):
                zeilen.append(" " * rand + str(f["hilfe"]))
        zeilen.append("")
        _w, grund = self.pruefen()
        zeilen.append(self.fehler or grund or "")
        zr, zs = cursor
        return [z[:breite] for z in zeilen[:hoehe]], (zr, min(zs, max(0, breite - 1)))

    def aenderungen(self):
        return {"werte": self.werte if self.werte is not None else (self.pruefen()[0] or {})}
