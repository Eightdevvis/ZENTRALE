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
# Der Kalender: woher er kommt, sagt die Einstellung der Kalender-App
# (core/kalender_einstellung.py, quelle ∈ google | zencloud | lokal) — überall
# dieselbe Datei, kein Zustand je Gerät. Hier nur, was der Abgleich daraus
# wissen muss: gleicht data/kalender/** über die Cloud ab
# (kalender_ueber_cloud), darf Google laufen (kalender_google_an), und ein
# Gerät, dessen Kalender zum ersten Mal mit der Cloud abgleicht, legt seinen
# alten beiseite, wenn die Cloud schon einen hat (vor_abgleich) — die Cloud
# wird nie überschrieben.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md). Kennt weder den
# Abgleich noch den Kalender — wer Pfade braucht, gibt sie herein.

import contextlib
import datetime
import json
import os
import shutil

import ai_config
import dateien
import formats
import kalender_einstellung as ke

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
    neuer = None
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
        if ke.ist_einstellung(a) or (isinstance(a, dict) and a.get("art") == "kalender-mitte"):
            continue        # Einstellung der Kalender-App (kalender_einstellung), kein Anschluss
        if _neuer(a):
            # A newer ZENTRALE wrote it: never interpreted, never written.
            neuer = formats.major(a.get("format"))
            print(f"[adapter] {n} ist neuer als diese Fassung — nur gelesen")
            continue
        if not isinstance(a, dict) or a.get("id") != n[:-5] or pruefen(a):
            print(f"[adapter] {n} ungültig — übergangen")
            continue
        raus[a["id"]] = a
    if neuer is None:
        formats.clear("adapter-connection")
    else:
        formats.note_newer("adapter-connection", neuer)
    return raus


# The fields this version knows: a caller may drop one on purpose; any other
# field in the file stays.
_BEKANNT = ("format", "id", "art", "titel", "speist", "eingerichtet", "einstellungen")


def _neuer(a) -> bool:
    return isinstance(a, dict) and formats.is_newer(a.get("format"), "adapter-connection")


def _datei(aid, wurzel=None):
    try:
        with open(_anschluss_pfad(aid, wurzel), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def lesen(aid, wurzel=None):
    return alle(wurzel).get(aid)


def speichern(a: dict, wurzel=None) -> None:
    """Write a connection. One a newer ZENTRALE wrote is never overwritten;
    fields a newer minor added stay (building_kit_plan.md 2.2 rules 2, 3)."""
    alt = _datei(a.get("id", ""), wurzel) if a.get("id") else None
    if _neuer(alt):
        formats.note_newer("adapter-connection", formats.major(alt.get("format")))
        raise AdapterFehler(formats.newer_text("adapter-connection"))
    a = formats.keep_unknown(alt if alt and alt.get("format") == FORMAT else None,
                             dict(a, format=FORMAT), owned=_BEKANNT)
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
    """Der Anschluss, der den Kalender speist und eine Brücke braucht
    (google-kalender), oder None. Er trägt nur Zugangsdaten — OB Google
    läuft, sagt die Quelle (kalender_google_an)."""
    for a in alle(wurzel).values():
        if a.get("speist") == "kalender" and braucht_bruecke(a):
            return a
    return None


def kalender_ueber_cloud(wurzel=None, ordner="data/kalender") -> bool:
    """Gleicht der Kalender-Ordner über die Cloud ab? Genau dann, wenn die
    Kalender-App, die ihn hat, quelle=zencloud trägt. Ohne Einstellung gilt
    der Stand von vor dem 28.10.: mit Google-Anschluss ja (eine Brücke per
    Mietvertrag, alle anderen aus der Cloud), sonst nein."""
    for e in ke.instanzen(wurzel).values():
        if e["ordner"] == ordner:
            return e["quelle"] == "zencloud"
    return ordner == ke.HAUPT_ORDNER and kalender_anschluss(wurzel) is not None


def kalender_google_an(wurzel=None) -> bool:
    """Darf auf diesem (und jedem) Gerät ein Google-Abgleich laufen
    (`zentrale adapter run`, scripts/kalender_sync.py)? Nur bei
    quelle=google — ohne Einstellung ist das die Vorgabe. Eine eigene
    vdirsyncer-Konfiguration ist nur Zugang, keine Entscheidung."""
    return ke.quelle(ke.HAUPT, wurzel) == "google"


def kalender_mit_vertrag(wurzel=None) -> bool:
    """Der alte Weg (keine Einstellung, Google-Anschluss): der Kalender kommt
    über die Cloud, Google fährt EIN Gerät mit Mietvertrag. Mit gesetzter
    quelle=google fährt jedes Gerät selbst (die Cloud trägt dann keine
    Termine — zwei Wege gäbe es nicht)."""
    return kalender_google_an(wurzel) and kalender_ueber_cloud(wurzel)


# ── Der Kalender kommt zur Cloud (erstes Mal je Gerät) ─────────────────
#
# Kein Merkzettel je Gerät: „erstes Mal" heißt, die Basis des Abgleichs
# kennt noch keine Datei des Kalender-Ordners (abgleich.basis_kennt). Ob die
# Cloud schon einen Kalender hat, sagt abgleich.mitte_hat_kalender. Beides
# gibt der Abgleich herein — der Adapter importiert ihn nicht (Import-Kreis,
# tests/test_kern_bauplan.py).


def _hat_termine(vdir) -> bool:
    return any(fs for _w, _d, fs in os.walk(vdir))


def beiseite_legen(wurzel, abgleich_ordner, ordner="data/kalender") -> str | None:
    """Den Kalender-Ordner nach <abgleich>/kalender-vor-cloud/<zeit>/
    schieben (nie gelöscht) — Sasha wählt dort selbst. → Ziel oder None
    (nichts da)."""
    vdir = os.path.join(str(wurzel), *ordner.split("/"))
    if not _hat_termine(vdir):
        return None
    zeit = datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    name = ordner.split("/")[-1]
    ziel = os.path.join(abgleich_ordner, "kalender-vor-cloud",
                        zeit if name == "kalender" else f"{zeit}-{name}")
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    shutil.move(vdir, ziel)
    # Die Grabsteine des alten Kalenders (data/kalender_verlauf/grabsteine,
    # für den rsync-Weg) gehören zu ihm: sie hielten sonst Termine aus der
    # Cloud für Geister und räumten sie weg.
    steine = os.path.join(str(wurzel), "data", "kalender_verlauf", "grabsteine")
    if name == "kalender" and os.path.isdir(steine):
        shutil.move(steine, os.path.join(ziel, ".grabsteine"))
    print(f"[adapter] Kalender kommt jetzt aus der Cloud — der bisherige liegt in {ziel}")
    return ziel


# Ordner, deren Kalender dieser Prozess gerade bewusst in die Cloud bringt
# (adapter_ablauf.kalender_quelle_setzen, nachdem die Mitte „leer" sagte).
# Nur im Speicher, nur für diesen einen Abgleich — kein Zustand je Gerät.
_FUELLT = set()


@contextlib.contextmanager
def kalender_fuellt(ordner="data/kalender"):
    """Der Abgleich in diesem Block bringt den hiesigen Kalender in die
    (leere) Cloud, statt ihn beiseitezulegen."""
    _FUELLT.add(ordner)
    try:
        yield
    finally:
        _FUELLT.discard(ordner)


def vor_abgleich(wurzel, abgleich_ordner, muster, mitte_hat_kalender=None,
                 basis_kennt=None) -> str | None:
    """Vor jedem Abgleich (core/abgleich): gleicht der Kalender diesmal mit,
    hat sich dieses Gerät mit der Mitte noch nie über ihn geeinigt (die Basis
    kennt keine Datei aus data/kalender/) und liegen hier Termine, gilt
    „die Cloud wird nie überschrieben":

      Cloud hat schon einen Kalender → der hiesige wandert beiseite
          (beiseite_legen, nie gelöscht), das Gerät übernimmt die Cloud;
      Cloud leer → der hiesige füllt sie;
      unbekannt → MitteFehler, kein Abgleich (lieber keiner als Geister).

    `mitte_hat_kalender(ordner) -> bool|None` und `basis_kennt(ordner) ->
    bool` gibt der Abgleich herein (core/abgleich._adapter_vorher; der
    Adapter importiert den Abgleich nicht — kein Import-Kreis). Fehlt eine,
    ist es unbekannt → MitteFehler. Im Block kalender_fuellt → füllt.
    Für jedes Gerät dieselbe Regel. → Ziel oder None."""
    if KALENDER_MUSTER not in muster or not kalender_ueber_cloud(wurzel):
        return None
    if not _hat_termine(os.path.join(str(wurzel), "data", "kalender")):
        return None
    if ke.HAUPT_ORDNER in _FUELLT:
        return None
    if basis_kennt is None:
        import abgleich_mitte       # Schicht 1, tiefer als der Abgleich
        raise abgleich_mitte.MitteFehler(
            "Kalender: ohne die Basis des Abgleichs ist „erstes Mal“ nicht zu klären — "
            "nicht abgeglichen (nichts überschrieben).")
    if basis_kennt(ke.HAUPT_ORDNER):
        return None
    frage = mitte_hat_kalender
    hat = None
    if frage is not None:
        try:
            hat = frage(ordner=ke.HAUPT_ORDNER)
        except Exception as e:      # noqa: BLE001 — unbekannt
            print(f"[adapter] Mitte nach dem Kalender gefragt: {e}")
        hat = hat if hat is True or hat is False else None
    if hat is None:
        import abgleich_mitte       # Schicht 1, tiefer als der Abgleich
        raise abgleich_mitte.MitteFehler(
            "Kalender: ob die Cloud schon Termine hat, ist gerade nicht zu klären — "
            "nicht abgeglichen (nichts überschrieben).")
    return beiseite_legen(wurzel, abgleich_ordner) if hat else None


def nach_abgleich(abgleich_ordner, muster) -> None:
    """Früher: Merkzettel kalender_dabei.json. Heute weiß das die Basis des
    Abgleichs selbst (abgleich.basis_kennt) — nichts zu tun. Bleibt, weil
    core/abgleich es ruft."""
    return None
