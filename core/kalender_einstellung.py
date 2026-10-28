# core/kalender_einstellung.py
#
# Die Einstellung der Kalender-App (memory/hub/adapter.md „Die Quelle der
# Kalender-App", Sasha 28.10.2026): woher eine installierte Kalender-App ihre
# Termine nimmt. Ein WERT, kein eigener Code-Weg:
#
#   quelle ∈ {"google", "zencloud", "lokal"}
#
# Die Wahl gehört der Kalender-App (Instanz), nicht dem Konto und nicht dem
# Hub: „wenn du 2 installierst dann hast du halt 2 verschiedene". Je Instanz
# EINE Datei {id, quelle, ordner, …} (Schema kalender_einstellung.schema.json),
# heute nur `kalender-haupt` → data/kalender.
#
# Wo sie liegt: data/adapter/anschluesse/<id>.json. Das ist der einzige Ort,
# der heute auf JEDES Gerät abgleicht und nie abgewählt wird (App `adapter`,
# pflicht) — die Einstellung muss überall dieselbe sein, sonst entscheidet
# wieder jedes Gerät selbst. data/kalender/** taugt nicht (gleicht genau dann
# NICHT ab, wenn die Quelle nicht zencloud ist), kalender_neben.json auch
# nicht (schreibt der Speicher dauernd, gehört zur abwählbaren App), ein
# eigener Pfad bräuchte die Positivliste (core/abgleich_auswahl.py).
# Die Kalender-App steckt sich damit an eine Pforte des Adapters.
#
# Keine Datei = der Stand von vor dem 28.10. (zählt als google, siehe
# adapter.kalender_ueber_cloud). Nichts legt die Datei von selbst an.
#
# Fundament (Schicht 1). Rein Daten: lesen, prüfen, schreiben. Das
# Umstöpseln mit Abgleich steht in adapter_ablauf.kalender_quelle_setzen.

import datetime
import json
import os

import ai_config
import dateien

FORMAT = "zentrale-kalender-app/1"
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kalender_einstellung.schema.json")
QUELLEN = ("google", "zencloud", "lokal")
HAUPT = "kalender-haupt"
HAUPT_ORDNER = "data/kalender"
VORGABE = "google"          # ohne Datei: wie bisher

# Altlast aus 1f32e6a (28.10.2026): der Anschluss `kalender-mitte` war der
# Schalter „ohne Google". Er gilt als kalender-haupt mit quelle=zencloud, bis
# kalender_quelle_setzen die neue Datei schreibt (und ihn dabei entfernt).
ALT_MITTE = "kalender-mitte"


_PROJEKT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


class EinstellungFehler(ValueError):
    """Für Menschen lesbar (englisch, wie zentrale_cli)."""


def _anschluesse(wurzel=None) -> str:
    # Derselbe Ort wie adapter.ordner()/anschluesse — hier selbst gerechnet,
    # weil core/adapter dieses Modul braucht (kein Kreis, test_kern_bauplan).
    if wurzel:
        return os.path.join(str(wurzel), "data", "adapter", "anschluesse")
    return os.path.join(os.path.expanduser(ai_config.setting("adapter_ordner") or
                                           os.path.join(_PROJEKT, "data", "adapter")), "anschluesse")


def _pfad(iid, wurzel=None) -> str:
    return os.path.join(_anschluesse(wurzel), iid + ".json")


def ist_einstellung(d) -> bool:
    return isinstance(d, dict) and d.get("format") == FORMAT


def pruefen(e: dict) -> list:
    import jsonschema
    with open(SCHEMA, encoding="utf-8") as f:
        s = json.load(f)
    return [x.message for x in jsonschema.Draft202012Validator(s).iter_errors(e)]


def _roh(pfad):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def alt_mitte_da(wurzel=None) -> bool:
    """Liegt noch der alte Anschluss kalender-mitte (1f32e6a)?"""
    d = _roh(_pfad(ALT_MITTE, wurzel))
    return isinstance(d, dict) and d.get("art") == "kalender-mitte"


def instanzen(wurzel=None) -> dict:
    """id → Einstellung aller Kalender-Apps. Ungültige fallen weg (mit
    Zeile); der alte Anschluss kalender-mitte zählt als kalender-haupt mit
    quelle=zencloud, solange es keine eigene Datei gibt."""
    d = _anschluesse(wurzel)
    raus = {}
    try:
        namen = sorted(os.listdir(d))
    except OSError:
        namen = []
    for n in namen:
        if not n.endswith(".json") or n.startswith("."):
            continue
        e = _roh(os.path.join(d, n))
        if not ist_einstellung(e):
            continue
        if e.get("id") != n[:-5] or pruefen(e):
            print(f"[kalender] Einstellung {n} ungültig — übergangen")
            continue
        raus[e["id"]] = e
    if HAUPT not in raus and alt_mitte_da(wurzel):
        raus[HAUPT] = neu(HAUPT, "zencloud")
    return raus


def instanz(iid=HAUPT, wurzel=None):
    return instanzen(wurzel).get(iid)


def eingestellt(iid=HAUPT, wurzel=None) -> bool:
    return instanz(iid, wurzel) is not None


def quelle(iid=HAUPT, wurzel=None) -> str:
    """Die Quelle der Instanz; ohne Datei VORGABE (google, wie bisher)."""
    e = instanz(iid, wurzel)
    return e["quelle"] if e else VORGABE


def ordner(iid=HAUPT, wurzel=None) -> str:
    e = instanz(iid, wurzel)
    return e["ordner"] if e else HAUPT_ORDNER


def mit_quelle(q, wurzel=None) -> list:
    """Die Instanzen, die gerade aus Quelle `q` speisen."""
    return [e for e in instanzen(wurzel).values() if e["quelle"] == q]


def neu(iid, q, ordner_rel=None, titel="") -> dict:
    return {"format": FORMAT, "id": iid, "quelle": q,
            "ordner": ordner_rel or (HAUPT_ORDNER if iid == HAUPT else "data/" + iid.replace("-", "_")),
            "titel": titel or ("Calendar" if iid == HAUPT else iid)}


def schreiben(iid, q, wurzel=None, ordner_rel=None) -> dict:
    """Nur den Wert setzen (die eine Stelle zum Umstöpseln). Löscht nie
    Termine. (Den alten Anschluss kalender-mitte nimmt
    adapter_ablauf.kalender_quelle_setzen danach weg: alt_mitte_weg.)"""
    if q not in QUELLEN:
        raise EinstellungFehler(f"Unknown calendar source '{q}' — use one of: {', '.join(QUELLEN)}")
    alt = instanz(iid, wurzel)
    e = neu(iid, q, ordner_rel or (alt or {}).get("ordner"), (alt or {}).get("titel", ""))
    e["geaendert"] = {"am": datetime.datetime.now().replace(microsecond=0).isoformat(),
                      "auf": dateien.knoten(), "von": (alt or {}).get("quelle") or VORGABE}
    fehler = pruefen(e)
    if fehler:
        raise EinstellungFehler("Invalid calendar setting: " + "; ".join(fehler[:3]))
    dateien.json_schreiben(_pfad(iid, wurzel), e)
    return e


def roh_lesen(iid, wurzel=None):
    """Die Datei als Bytes (oder None) — zum Zurücknehmen eines Umstöpselns,
    das nicht hinausging."""
    try:
        with open(_pfad(iid, wurzel), "rb") as f:
            return f.read()
    except OSError:
        return None


def roh_zurueck(iid, roh, wurzel=None) -> None:
    if roh is None:
        try:
            os.remove(_pfad(iid, wurzel))
        except FileNotFoundError:
            pass
    else:
        dateien.atomar_schreiben(_pfad(iid, wurzel), roh)


def alt_mitte_weg(wurzel=None) -> None:
    if alt_mitte_da(wurzel):
        os.remove(_pfad(ALT_MITTE, wurzel))
