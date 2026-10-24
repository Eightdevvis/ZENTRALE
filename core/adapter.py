# core/adapter.py
#
# Der Adapter — die eine Tür zu fremden Diensten (memory/hub/adapter.md,
# Sasha 24.10.2026). Eine App, immer installiert, deren Konfiguration überall
# abgleicht. Hier: die Anschlüsse selbst und was der Abgleich über sie wissen
# muss.
#
#   data/adapter/anschluesse/<id>.json   je Anschluss eine Beschreibung
#                                        (core/adapter_anschluss.schema.json),
#                                        nie ein Geheimnis
#   data/adapter/geheim.enc              Zugangsdaten, verschlüsselt
#                                        (core/adapter_geheim.py)
#   data/adapter/bruecke/<id>.json       wer die Brücke gerade fährt
#                                        (core/adapter_bruecke.py)
#
# Der Kalender über die Cloud: data/kalender/** gleicht nur ab, wenn es einen
# Kalender-Anschluss gibt (kalender_ueber_cloud). Ein Gerät, das zum ersten
# Mal mitmacht und nicht selbst der Ursprung ist, legt seinen alten Kalender
# vorher beiseite (vor_abgleich) — sonst trüge es längst gelöschte Termine in
# die Cloud, und die Brücke lüde sie zu Google hoch (Geister).
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md). Kennt weder den
# Abgleich noch den Kalender — wer Pfade braucht, gibt sie herein.

import datetime
import json
import os
import shutil

import ai_config
import dateien

FORMAT = "zentrale-anschluss/1"
SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapter_anschluss.schema.json")
_PROJEKT = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# Die Muster im Namensraum der Positivliste (core/abgleich_auswahl.py).
ANSCHLUESSE_MUSTER = "data/adapter/anschluesse/*.json"
BRUECKE_MUSTER = "data/adapter/bruecke/**"
GEHEIM_MUSTER = "data/adapter/geheim.enc"
KALENDER_MUSTER = "data/kalender/**"

# Arten, die mit einem fremden Dienst abgleichen und deshalb genau EINE
# Brücke brauchen (die übrigen nutzt jedes Gerät selbst).
MIT_BRUECKE = ("kalender-vdirsyncer",)


class AdapterFehler(Exception):
    """Für Menschen lesbar (englisch, wie zentrale_cli)."""


# ── Orte ───────────────────────────────────────────────────────────────

def ordner(wurzel=None) -> str:
    """data/adapter dieses Geräts. `wurzel` = ein ZENTRALE-Ordner (Tests,
    zwei gespielte Geräte); sonst Einstellung `adapter_ordner`, sonst der
    eigene."""
    if wurzel:
        return os.path.join(str(wurzel), "data", "adapter")
    return os.path.expanduser(ai_config.setting("adapter_ordner") or
                              os.path.join(_PROJEKT, "data", "adapter"))


def lauf_ordner(aid: str) -> str:
    """Örtliches für einen Anschluss, das nie abgleicht (erzeugte
    vdirsyncer-Konfiguration). Außerhalb von data/."""
    basis = ai_config.setting("adapter_lauf") or "~/.local/share/zentrale/adapter"
    return os.path.join(os.path.expanduser(basis), aid)


def _anschluss_pfad(aid, wurzel=None) -> str:
    return os.path.join(ordner(wurzel), "anschluesse", aid + ".json")


# ── Anschlüsse ─────────────────────────────────────────────────────────

def pruefen(a: dict) -> list:
    """Fehler gegen das Schema (leer = gut)."""
    import jsonschema
    with open(SCHEMA, encoding="utf-8") as f:
        s = json.load(f)
    return [e.message for e in jsonschema.Draft202012Validator(s).iter_errors(a)]


def alle(wurzel=None) -> dict:
    """id → Anschluss. Unlesbare oder ungültige Dateien fallen weg (mit
    einer Zeile) — ein kaputter Anschluss darf den Abgleich nicht kippen."""
    d = os.path.join(ordner(wurzel), "anschluesse")
    raus = {}
    try:
        namen = sorted(os.listdir(d))
    except OSError:
        return {}
    for n in namen:
        if not n.endswith(".json") or n.startswith("."):
            continue
        try:
            with open(os.path.join(d, n), encoding="utf-8") as f:
                a = json.load(f)
        except (OSError, ValueError):
            print(f"[adapter] {n} nicht lesbar — übergangen")
            continue
        if not isinstance(a, dict) or a.get("id") != n[:-5] or pruefen(a):
            print(f"[adapter] {n} ungültig — übergangen")
            continue
        raus[a["id"]] = a
    return raus


def lesen(aid, wurzel=None):
    return alle(wurzel).get(aid)


def speichern(a: dict, wurzel=None) -> None:
    a = dict(a, format=FORMAT)
    fehler = pruefen(a)
    if fehler:
        raise AdapterFehler("Invalid connection: " + "; ".join(fehler[:3]))
    dateien.json_schreiben(_anschluss_pfad(a["id"], wurzel), a)


def neu(aid, art, speist, titel="", einstellungen=None) -> dict:
    return {"format": FORMAT, "id": aid, "art": art, "speist": speist,
            "titel": titel or aid,
            "eingerichtet": {"am": datetime.datetime.now().replace(microsecond=0).isoformat(),
                             "auf": dateien.knoten()},
            "einstellungen": einstellungen or {}}


def braucht_bruecke(a: dict) -> bool:
    return a.get("art") in MIT_BRUECKE


def kalender_anschluss(wurzel=None):
    """Der Anschluss, der den Kalender speist und eine Brücke braucht, oder None."""
    for a in alle(wurzel).values():
        if a.get("speist") == "kalender" and braucht_bruecke(a):
            return a
    return None


def kalender_ueber_cloud(wurzel=None) -> bool:
    """Gleicht data/kalender/** über die Mitte ab? Genau dann, wenn es einen
    Kalender-Anschluss gibt — dann fährt immer nur EIN Gerät die Brücke zu
    Google, alle anderen bekommen die Termine aus der Cloud."""
    return kalender_anschluss(wurzel) is not None


# ── Der Kalender kommt dazu (einmal je Gerät) ──────────────────────────
#
# Merkzettel je Gerät im Ordner des Abgleichs (außerhalb von data/, wandert
# nie): ab wann dieses Gerät den Kalender über die Cloud abgleicht.

def _merkzettel(abgleich_ordner) -> str:
    return os.path.join(abgleich_ordner, "kalender_dabei.json")


def kalender_dabei(abgleich_ordner) -> bool:
    return os.path.exists(_merkzettel(abgleich_ordner))


def vor_abgleich(wurzel, abgleich_ordner, muster) -> str | None:
    """Vor einem Abgleich, in dem der Kalender zum ersten Mal mitläuft: ist
    dieses Gerät NICHT der Ursprung des Kalender-Anschlusses, wandert sein
    bisheriger data/kalender/ beiseite (nie gelöscht), und es übernimmt den
    Stand der Cloud. → Ort des Beiseitegelegten oder None.

    Warum: ohne Basis würde jede Datei, die nur hier liegt, als „neu" in die
    Cloud gehen — auch Termine, die bei Google längst gelöscht sind. Die
    Brücke trüge sie dann wieder zu Google (Geister). Der Ursprung dagegen
    bringt die Wahrheit mit."""
    if KALENDER_MUSTER not in muster or kalender_dabei(abgleich_ordner):
        return None
    a = kalender_anschluss(wurzel)
    if a is None:
        return None
    if (a.get("eingerichtet") or {}).get("auf") == dateien.knoten():
        return None
    vdir = os.path.join(str(wurzel), "data", "kalender")
    da = [os.path.join(w, f) for w, _d, fs in os.walk(vdir) for f in fs]
    if not da:
        return None
    ziel = os.path.join(abgleich_ordner, "kalender-vor-cloud",
                        datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    shutil.move(vdir, ziel)
    print(f"[adapter] Kalender kommt jetzt aus der Cloud — der bisherige liegt in {ziel}")
    return ziel


def nach_abgleich(abgleich_ordner, muster) -> None:
    """Nach einem gelungenen Abgleich mit dem Kalender: merken, dass dieses
    Gerät dabei ist (dann erst darf es die Brücke übernehmen)."""
    if KALENDER_MUSTER in muster and not kalender_dabei(abgleich_ordner):
        dateien.json_schreiben(_merkzettel(abgleich_ordner),
                               {"seit": datetime.datetime.now().replace(microsecond=0).isoformat()})


def als_ursprung_merken(abgleich_ordner) -> None:
    """Das Gerät, das den Kalender-Anschluss anlegt, ist von Anfang an dabei."""
    dateien.json_schreiben(_merkzettel(abgleich_ordner),
                           {"seit": datetime.datetime.now().replace(microsecond=0).isoformat(),
                            "ursprung": True})
