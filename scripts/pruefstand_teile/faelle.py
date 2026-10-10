# Fälle laden — und aus einem echten Gespräch einen Entwurf machen.
#
# Ein Fall ist eine YAML-Datei in tests/pruefstand/faelle/ (verdeckte in
# faelle/verdeckt/). Das Format steht in memory/ki/pruefstand.md und am
# Beispiel jedes Falls; geprüft wird hier nur, was der Lauf braucht, damit
# ein Tippfehler im Fall nicht erst nach bezahlten Zügen auffällt.

import glob
import json
import os
import re
from datetime import date, datetime

import yaml

WURZEL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FAELLE_DIR = os.path.join(WURZEL, "tests", "pruefstand", "faelle")

_ERLAUBT = {"id", "titel", "verdeckt", "herkunft", "jetzt", "geschaetzt",
            "worum", "einstellungen", "kalender", "gedaechtnis", "netz",
            "antworten", "zuege", "endzustand", "browser"}


class FallFehler(ValueError):
    pass


def alle(mit_verdeckten: bool = True) -> list:
    """Alle Fälle, sortiert nach Datei. -> [fall-dict]"""
    pfade = sorted(glob.glob(os.path.join(FAELLE_DIR, "*.yaml")))
    if mit_verdeckten:
        pfade += sorted(glob.glob(os.path.join(FAELLE_DIR, "verdeckt", "*.yaml")))
    return [laden(p) for p in pfade]


def finden(namen: list, mit_verdeckten: bool = True) -> list:
    """Fälle nach id oder Anfang der id/des Dateinamens (f01 → f01_geige…)."""
    faelle = alle(mit_verdeckten=True)
    raus = []
    for n in namen:
        # Erst „n_…" (f01 → f01_geige, nicht auch f01k_geige_kurz, 2026-10-10:
        # sonst liefe mit --fall f01 still ein zweiter, bezahlter Fall mit),
        # dann jeder Anfang.
        treffer = [f for f in faelle if f["id"] == n] or \
                  [f for f in faelle if f["id"].startswith(n + "_")
                   or os.path.basename(f["_pfad"]).startswith(n + "_")] or \
                  [f for f in faelle if f["id"].startswith(n)
                   or os.path.basename(f["_pfad"]).startswith(n)]
        if not treffer:
            raise FallFehler(f"Kein Fall {n!r}. Es gibt: "
                             + ", ".join(f["id"] for f in faelle))
        raus.extend(t for t in treffer if t not in raus)
    if not mit_verdeckten:
        raus = [f for f in raus if not f.get("verdeckt")]
    return raus


def laden(pfad: str) -> dict:
    with open(pfad, encoding="utf-8") as f:
        fall = yaml.safe_load(f) or {}
    fall["_pfad"] = os.path.abspath(pfad)
    pruefen(fall)
    return fall


def pruefen(fall: dict) -> None:
    """Wirft FallFehler mit einer Meldung, die sagt, WAS fehlt."""
    name = os.path.basename(fall.get("_pfad", "?"))
    def fehler(text):
        raise FallFehler(f"{name}: {text}")
    fremd = set(fall) - _ERLAUBT - {"_pfad"}
    if fremd:
        fehler(f"unbekannte Felder {sorted(fremd)}")
    for pflicht in ("id", "titel", "zuege", "endzustand"):
        if not fall.get(pflicht):
            fehler(f"Feld {pflicht!r} fehlt")
    if fall.get("jetzt"):
        try:
            jetzt_von(fall)
        except ValueError:
            fehler(f"jetzt {fall['jetzt']!r} ist kein Zeitpunkt (2026-10-08T15:24)")
    for i, z in enumerate(fall["zuege"], 1):
        if not isinstance(z, dict) or not str(z.get("sagt") or "").strip():
            fehler(f"Zug {i}: 'sagt' fehlt")
    for i, p in enumerate(fall["endzustand"], 1):
        if not isinstance(p, dict) or not p.get("was"):
            fehler(f"Endzustand {i}: 'was' fehlt")
        grund = _pruefung_fehlt(p)
        if grund:
            fehler(f"Endzustand {i} ({p['was']}): {grund}")
    for s in (fall.get("browser") or {}).get("seiten") or []:
        if not isinstance(s, dict) or not str(s.get("pfad", "")).startswith("/"):
            fehler(f"browser.seiten: jede Seite braucht einen pfad, der mit / beginnt ({s})")


def _pruefung_fehlt(p: dict) -> str | None:
    """Was an einer Endzustand-Prüfung nicht laufen würde — vor dem Lauf
    sagen, nicht nach bezahlten Zügen (Arten: endzustand.ARTEN)."""
    from .endzustand import ARTEN
    if not any(k in p for k in ARTEN):
        return f"braucht eins von {', '.join(ARTEN)}"
    for alternative in p.get("eins_von") or []:
        for q in alternative:
            g = _pruefung_fehlt(q) if isinstance(q, dict) else "Variante ist keine Prüfung"
            if g:
                return g
    a = p.get("antwort")
    if a is not None:
        if not isinstance(a, dict):
            return "antwort muss ein Abschnitt sein"
        for feld in ("muster", "eins_von_muster", "nicht_muster"):
            for m in a.get(feld) or []:
                try:
                    re.compile(m)
                except re.error as e:
                    return f"{feld} {m!r} ist kein gültiges Muster ({e})"
    q = p.get("quellen")
    if q is not None and not isinstance(q, dict):
        return "quellen muss ein Abschnitt sein"
    z = (p.get("regeln") or {}).get("zeitraum") if isinstance(p.get("regeln"), dict) else None
    if z is not None:
        try:
            von, bis = (v if isinstance(v, date) else date.fromisoformat(str(v))
                        for v in (z["von"], z["bis"]))
        except (KeyError, TypeError, ValueError):
            return "zeitraum braucht von und bis als Datum (2026-10-12)"
        if von > bis:
            return "zeitraum: von liegt nach bis"
    return None


def jetzt_von(fall: dict):
    roh = fall.get("jetzt")
    if not roh:
        return None
    if isinstance(roh, datetime):
        return roh.replace(tzinfo=None)
    return datetime.fromisoformat(str(roh))


# ── Aus einer Rückmeldung einen Fall machen ────────────────────────────
#
# Ziel (Sasha, 08.10.2026): Was er mit 👎 bewertet, soll ein Prüffall werden
# können. Bewusst NICHT automatisch: ein Fall braucht einen Ausgangszustand
# und einen Endzustand, und beides weiß nur, wer das Gespräch versteht. Die
# Hilfe hier nimmt die Fleißarbeit ab — Nutzer-Nachrichten wörtlich, die
# Werkzeug-Aufrufe als Hinweis auf den Ausgangszustand — und lässt die
# Lücken als TODO stehen.
#
# Woher die Rückmeldung kommt (core/rueckmeldungen.py, falls es das gibt):
# aufrufen mit der Gesprächs-id und optional der id der bewerteten Antwort;
# dann endet der Entwurf mit dem Zug, der die Antwort ausgelöst hat.

def entwurf_aus_gespraech(gespraeche_dir: str, gid: str,
                          bis_nachricht: str | None = None) -> str:
    """YAML-Entwurf eines Falls aus einem gespeicherten Gespräch. Liest nur."""
    ordner = os.path.join(gespraeche_dir, gid)
    if not os.path.isdir(ordner):
        raise FallFehler(f"Kein Gespräch {gid!r} unter {gespraeche_dir}")
    nachrichten = []
    for datei in sorted(glob.glob(os.path.join(ordner, "*.jsonl"))):
        with open(datei, encoding="utf-8") as f:
            for zeile in f:
                try:
                    d = json.loads(zeile)
                except ValueError:
                    continue
                if d.get("art") == "nachricht":
                    nachrichten.append(d)
    nachrichten.sort(key=lambda d: d.get("ts", ""))
    if bis_nachricht:
        ids = [n.get("id") for n in nachrichten]
        if bis_nachricht in ids:
            nachrichten = nachrichten[:ids.index(bis_nachricht) + 1]

    zuege, hinweise = [], []
    for n in nachrichten:
        if n.get("rolle") == "user":
            zuege.append({"sagt": n.get("text", "")})
        else:
            for w in n.get("werkzeuge") or []:
                hinweise.append(f"{w.get('name')}({w.get('args', '')}) → "
                                f"{w.get('ergebnis', '')}")
    erster = nachrichten[0].get("ts", "") if nachrichten else ""
    fall = {
        "id": f"neu_{gid[-6:]}",
        "titel": "TODO: worum es geht",
        "verdeckt": False,
        "herkunft": f"Gespräch {gid}" + (f", bewertet: {bis_nachricht}" if bis_nachricht else ""),
        "jetzt": erster[:16] if erster else None,
        "geschaetzt": "TODO: was am Ausgangszustand geschätzt ist",
        "kalender": {"termine": [], "routinen": [], "pausen": []},
        "antworten": {"erlaubnis": "ja", "knopf": None},
        "zuege": zuege,
        "endzustand": [{"was": "TODO: was danach im Kalender stehen muss"}],
    }
    kopf = ("# Entwurf aus einem echten Gespräch — Ausgangszustand und Endzustand\n"
            "# von Hand ergänzen. Hinweise aus den Werkzeug-Aufrufen damals:\n"
            + "".join(f"#   {h[:200]}\n" for h in hinweise))
    return kopf + yaml.safe_dump(fall, allow_unicode=True, sort_keys=False, width=100)
