# core/abgleich_zusammenfuehren.py
#
# Zwei Fassungen einer Datei zusammenführen — über ihre gemeinsame Vorfassung
# (die Basis: worauf sich dieser Rechner zuletzt mit der Mitte geeinigt hat).
# Die Regeln und ihr Warum stehen in memory/betrieb/abgleich.md; hier nur,
# wie sie gebaut sind.
#
# Drei-Wege statt „neueste gewinnt" (2026-10-08): mit der Basis sieht man,
# WER etwas geändert hat, ohne auf eine Uhr zu schauen. Hat nur eine Seite
# geändert, gilt sie. Haben beide dasselbe geändert, gibt es eine Regel und
# einen Hinweis — aber nie ein stilles Verlieren.
#
# Reine Funktionen: Bytes rein, Bytes raus, kein Dateisystem.

import difflib
import json
from collections import Counter

FEHLT = None   # „gibt es auf dieser Seite nicht" (Datei oder Wert)

# Felder, bei denen der spätere Wert ohne Hinweis gewinnt: es sind
# Zeitstempel, die beide Seiten bei jeder Änderung mitschreiben. Ein Hinweis
# „modified war verschieden" bei jeder Notiz wäre Lärm.
ZEIT_FELDER = {"modified", "geaendert", "aktualisiert", "updated", "last_seen",
               "zuletzt", "letzte_aktivitaet"}

_KEIN = object()   # innen: Schlüssel fehlt (FEHLT=None ist in JSON ein Wert)


class Ergebnis:
    """inhalt (bytes oder None = gelöscht), konflikte (Liste von Stellen)."""

    def __init__(self, inhalt, konflikte=()):
        self.inhalt = inhalt
        self.konflikte = list(konflikte)


def art(rel: str, *fassungen) -> str:
    """json | zaehler | zeilen | text | ganz | abgeleitet — nach Pfad, Endung, Inhalt."""
    if rel.startswith("data/mobil/"):
        return "abgeleitet"
    if rel.endswith("ai_usage.json"):
        return "zaehler"
    if rel.endswith(".json"):
        return "json"
    if rel.endswith(".jsonl"):
        return "zeilen"
    for f in fassungen:
        if f is None:
            continue
        try:
            f.decode("utf-8")
        except UnicodeDecodeError:
            return "ganz"
    return "text"


def zusammenfuehren(rel, basis, lokal, mitte, name_lokal="hier") -> Ergebnis:
    """Die Regel für eine Datei. basis/lokal/mitte: bytes oder None (fehlt).
    Bei einem Widerspruch bleibt die Fassung der Mitte (für JSON/Ganzes) bzw.
    stehen beide Fassungen im Text; `konflikte` sagt, wo."""
    if lokal == mitte:
        return Ergebnis(lokal)
    if basis is not None and lokal == basis:
        return Ergebnis(mitte)
    if basis is not None and mitte == basis:
        return Ergebnis(lokal)
    # Ohne Basis heißt „fehlt auf einer Seite": dort nie gehabt, nur dazu.
    # Mit Basis ist es Löschen gegen Ändern — die Änderung gewinnt.
    if lokal is None:
        return Ergebnis(mitte, [] if basis is None else
                        ["hier gelöscht, in der Mitte geändert — bleibt"])
    if mitte is None:
        return Ergebnis(lokal, [] if basis is None else
                        ["in der Mitte gelöscht, hier geändert — bleibt"])
    a = art(rel, basis, lokal, mitte)
    if a == "abgeleitet":
        # Neu erzeugt aus den Daten dieses Rechners (Kontextpaket fürs Handy):
        # die frische Fassung von hier gilt, ein Widerspruch ist keiner.
        return Ergebnis(lokal)
    try:
        if a in ("json", "zaehler"):
            return _json_datei(basis, lokal, mitte, zaehler=(a == "zaehler"))
        if a == "zeilen":
            return Ergebnis(_zeilen(basis, lokal, mitte))
        if a == "text":
            return _text(basis, lokal, mitte, name_lokal)
    except (ValueError, UnicodeDecodeError):
        pass   # kaputtes JSON o. ä.: als Ganzes behandeln
    return Ergebnis(mitte, ["beide Fassungen verschieden — die aus der Mitte bleibt"])


# ── JSON ────────────────────────────────────────────────────────────────

def _json_datei(basis, lokal, mitte, zaehler):
    b = json.loads(basis.decode("utf-8")) if basis is not None else _KEIN
    l = json.loads(lokal.decode("utf-8"))
    m = json.loads(mitte.decode("utf-8"))
    ctx = _Ctx(zaehler, _hoechste_id(b, l, m))
    r = ctx.wert(b, l, m, ())
    _zaehler_nachziehen(r)
    text = json.dumps(r, indent=2, ensure_ascii=False)
    return Ergebnis(text.encode("utf-8"), ctx.konflikte)


def json_zusammenfuehren(basis, lokal, mitte, zaehler=False):
    """Für Tests und Einzelwerte: (wert, konflikte). basis=_KEIN-artig: None
    heißt hier „keine Basis"."""
    ctx = _Ctx(zaehler, _hoechste_id(basis, lokal, mitte))
    r = ctx.wert(_KEIN if basis is None else basis, lokal, mitte, ())
    _zaehler_nachziehen(r)
    return r, ctx.konflikte


def _ganze_zahl(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _zahl(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _ids(x):
    """Alle ganzzahligen `id` irgendwo in x."""
    if isinstance(x, dict):
        if _ganze_zahl(x.get("id")):
            yield x["id"]
        for v in x.values():
            yield from _ids(v)
    elif isinstance(x, list):
        for v in x:
            yield from _ids(v)


def _hoechste_id(*xs):
    return max((i for x in xs if x is not _KEIN for i in _ids(x)), default=0)


def _zaehler_nachziehen(x):
    """`next_item`, `next_block` … müssen über allen Nummern darunter liegen —
    sonst vergibt die App nach einer Umnummerierung eine Nummer doppelt."""
    if isinstance(x, dict):
        for k, v in x.items():
            if k.startswith("next_") and _ganze_zahl(v):
                hoechste = max(_ids({kk: vv for kk, vv in x.items() if kk != k}), default=0)
                if v <= hoechste:
                    x[k] = hoechste + 1
        for v in x.values():
            _zaehler_nachziehen(v)
    elif isinstance(x, list):
        for v in x:
            _zaehler_nachziehen(v)


def _schluessel(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False)


class _Ctx:
    def __init__(self, zaehler, hoechste_id):
        self.zaehler = zaehler
        self.naechste_id = hoechste_id + 1
        self.konflikte = []

    def wert(self, b, l, m, pfad):
        if l == m:
            return l
        if b is not _KEIN and l == b:
            return m
        if b is not _KEIN and m == b:
            return l
        # beide verschieden geändert (oder ohne Basis verschieden)
        if l is _KEIN:
            if b is not _KEIN:
                self._notiere(pfad, "hier gelöscht, in der Mitte geändert — bleibt")
            return m
        if m is _KEIN:
            if b is not _KEIN:
                self._notiere(pfad, "in der Mitte gelöscht, hier geändert — bleibt")
            return l
        if isinstance(l, dict) and isinstance(m, dict):
            return self._objekt(b if isinstance(b, dict) else {}, l, m, pfad)
        if isinstance(l, list) and isinstance(m, list):
            bl = b if isinstance(b, list) else []
            if all(isinstance(e, dict) and "id" in e for e in bl + l + m):
                return self._nach_id(bl, l, m, pfad, b is _KEIN)
            return _menge(bl, l, m, b is _KEIN)
        feld = pfad[-1] if pfad else ""
        if isinstance(feld, str) and feld.startswith("next_") and _ganze_zahl(l) and _ganze_zahl(m):
            return max(l, m)
        if feld in ZEIT_FELDER and isinstance(l, str) and isinstance(m, str):
            return max(l, m)
        if self.zaehler and _zahl(l) and _zahl(m):
            basis = b if _zahl(b) else 0
            return round(m + (l - basis), 6) if isinstance(m + l, float) else m + (l - basis)
        self._notiere(pfad, "beide verschieden geändert — die Fassung aus der Mitte bleibt")
        return m

    def _notiere(self, pfad, was):
        stelle = "/".join(str(p) for p in pfad) or "(ganze Datei)"
        self.konflikte.append(f"{stelle}: {was}")

    def _objekt(self, b, l, m, pfad):
        raus = {}
        for k in list(m) + [k for k in l if k not in m]:
            r = self.wert(b.get(k, _KEIN), l.get(k, _KEIN), m.get(k, _KEIN), pfad + (k,))
            if r is not _KEIN:
                raus[k] = r
        return raus

    def _nach_id(self, b, l, m, pfad, ohne_basis):
        """Einträge mit `id`: jeder für sich. Reihenfolge der Mitte, eigene
        neue Einträge hinter ihrem Vorgänger aus der eigenen Liste."""
        def nach_id(xs):
            return {_schluessel(e["id"]): e for e in xs}
        bd, ld, md = nach_id(b), nach_id(l), nach_id(m)
        umbenannt = {}
        for k, e in list(ld.items()):
            # Beide haben offline einen NEUEN Eintrag mit derselben Nummer
            # angelegt (Zähler next_item lief auf beiden Rechnern gleich):
            # das sind zwei verschiedene Dinge. Der eigene bekommt eine neue
            # Nummer, beide bleiben.
            if (k in md and k not in bd and _ganze_zahl(e["id"]) and not ohne_basis
                    and _schluessel(md[k]) != _schluessel(e)):
                neu = dict(e, id=self.naechste_id)
                self.naechste_id += 1
                umbenannt[k] = _schluessel(neu["id"])
                ld[umbenannt[k]] = neu
        reihe = [_schluessel(e["id"]) for e in m]
        lokal_reihe = [umbenannt.get(_schluessel(e["id"]), _schluessel(e["id"])) for e in l]
        for i, k in enumerate(lokal_reihe):
            if k in reihe:
                continue
            vor = next((lokal_reihe[j] for j in range(i - 1, -1, -1) if lokal_reihe[j] in reihe), None)
            reihe.insert(reihe.index(vor) + 1 if vor else 0, k)
        for k in bd:
            if k not in reihe:
                reihe.append(k)
        raus = []
        for k in reihe:
            if k in umbenannt:          # die Nummer gehört jetzt dem Eintrag der Mitte
                raus.append(md[k])
                continue
            r = self.wert(bd.get(k, _KEIN), ld.get(k, _KEIN), md.get(k, _KEIN), pfad + (json.loads(k),))
            if r is not _KEIN:
                raus.append(r)
        return raus


def _menge(b, l, m, ohne_basis):
    """Listen ohne `id` (Messwerte, Zeilen): Mitte, plus was hier dazukam,
    minus was hier wegfiel. Ohne Basis: alles, was eine Seite hat, einmal."""
    cb = Counter(_schluessel(e) for e in b)
    cl = Counter(_schluessel(e) for e in l)
    raus, gesehen = [], Counter()
    weg = cb - cl                     # hier gelöscht
    for e in m:
        k = _schluessel(e)
        if weg[k] > 0:
            weg[k] -= 1
            continue
        raus.append(e)
        gesehen[k] += 1
    dazu = cl if ohne_basis else cl - cb
    for e in l:
        k = _schluessel(e)
        if ohne_basis:
            if gesehen[k] < dazu[k]:
                raus.append(e)
                gesehen[k] += 1
        elif dazu[k] > 0:
            raus.append(e)
            dazu[k] -= 1
    return raus


# ── Zeilen (.jsonl, nur angehängt) ─────────────────────────────────────

def _zeilen(basis, lokal, mitte):
    def teile(x):
        return x.decode("utf-8").splitlines() if x is not None else []
    r = _menge(teile(basis), teile(lokal), teile(mitte), basis is None)
    return ("\n".join(r) + "\n").encode("utf-8") if r else b""


# ── Text (Gedächtnis), Drei-Wege über Zeilen ───────────────────────────

ANFANG = "⟪ Abgleich: hier gibt es zwei Fassungen — eine behalten, den Rest löschen ⟫\n"
ENDE = "⟪ Ende der zwei Fassungen ⟫\n"


def _treffer(a, b):
    """Zeilennummer in a → passende Zeilennummer in b (gleiche Zeile)."""
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    raus = {}
    for blk in sm.get_matching_blocks():
        for t in range(blk.size):
            raus[blk.a + t] = blk.b + t
    return raus


def text_zusammenfuehren(basis: str, lokal: str, mitte: str, name_lokal="hier"):
    """Drei-Wege über Zeilen. → (text, anzahl_widersprueche)."""
    b = basis.splitlines(keepends=True)
    l = lokal.splitlines(keepends=True)
    m = mitte.splitlines(keepends=True)
    for xs in (l, m):                  # letzte Zeile ohne Umbruch angleichen
        if xs and not xs[-1].endswith("\n"):
            xs[-1] += "\n"
    tl, tm = _treffer(b, l), _treffer(b, m)
    # Ankerzeilen: in beiden Fassungen unverändert und in Reihenfolge.
    anker, lj, mk = [], -1, -1
    for i in range(len(b)):
        if i in tl and i in tm and tl[i] > lj and tm[i] > mk:
            anker.append(i)
            lj, mk = tl[i], tm[i]
    raus, widersprueche = [], 0
    i = j = k = 0
    for a in anker + [None]:
        ai, aj, ak = (len(b), len(l), len(m)) if a is None else (a, tl[a], tm[a])
        sb, sl, sm_ = b[i:ai], l[j:aj], m[k:ak]
        if sl == sb:
            raus += sm_
        elif sm_ == sb or sl == sm_:
            raus += sl
        else:
            widersprueche += 1
            raus += [ANFANG, f"⟪ Fassung von {name_lokal} ⟫\n"] + sl
            raus += ["⟪ Fassung aus der Mitte ⟫\n"] + sm_ + [ENDE]
        if a is not None:
            raus.append(b[a])
            i, j, k = a + 1, aj + 1, ak + 1
    return "".join(raus), widersprueche


def _text(basis, lokal, mitte, name_lokal):
    t, n = text_zusammenfuehren(basis.decode("utf-8") if basis is not None else "",
                                lokal.decode("utf-8"), mitte.decode("utf-8"), name_lokal)
    konflikte = [f"{n} Stelle(n) auf beiden Seiten verschieden geändert — "
                 "beide Fassungen stehen in der Datei"] if n else []
    return Ergebnis(t.encode("utf-8"), konflikte)
