# core/adapter_geheim.py
#
# Die Zugangsdaten des Adapters (memory/hub/adapter.md „Sicherheitsregeln"):
# KI-Schlüssel, Google-Zugang für den Kalender, später mehr. Eine Datei,
# data/adapter/geheim.enc:
#
#   {"format": "zentrale-geheim/1",
#    "eintraege": {"<name>": {"zu": "konto"|"geraet", "wert": "<Fernet-Token>"}}}
#
# Warum je Eintrag verschlüsselt und nicht die ganze Datei als ein Block:
# zwei Geräte, die verschiedene Einträge ändern (das eine einen KI-Schlüssel,
# das andere — die Brücke — den erneuerten Google-Token), sollen beide
# gewinnen. Die JSON-Regel des Abgleichs führt Eintrag für Eintrag zusammen;
# ein einziger verschlüsselter Block wäre „als Ganzes" — einer verlöre. Was
# lesbar bleibt, sind nur die Namen der Einträge (auf dem Gerät, 600; in der
# Cloud ist die ganze Datei noch einmal verschlüsselt).
#
# Mit welchem Schlüssel:
#   konto   angemeldet → der konto_schluessel (core/konto.py). Nur DANN gleicht
#           die Datei ab (adapter_geheim.darf_abgleichen) — jedes Gerät des
#           Kontos kann sie lesen, der Server nie.
#   geraet  ohne Konto → ein Schlüssel nur dieses Geräts
#           (~/.config/zentrale/adapter.schluessel, 600). Nicht Klartext mit
#           600, weil data/ an mehr Orte kopiert wird als ~/.config (der alte
#           rsync-Weg nimmt ganz data/ mit, Sicherungen, ein USB-Stick): dort
#           bliebe die Datei unlesbar.
# Wechsel: beim Anmelden schlüsselt vor_abgleich alles auf `konto` um, vor dem
# Abmelden vor_abmelden auf `geraet` — sonst wäre nach dem Abmelden nichts
# mehr lesbar.
#
# NIE in der Datensicherung (scripts/daten_sichern.py schickt Klartext nach
# GitHub): geheim.enc steht nur auf NUR_ABGLEICH, nicht auf SICHERN
# (core/abgleich_auswahl.py; Test tests/test_adapter_geheim.py).
#
# Fundament (Schicht 1).

import base64
import json
import os

import adapter
import ai_config
import dateien
import konto

FORMAT = "zentrale-geheim/1"
VORGABE_SCHLUESSEL = "~/.config/zentrale/adapter.schluessel"
KI = "ki/"                # Einträge der KI-Anbieter: ki/<ENV-NAME>


class GeheimFehler(Exception):
    pass


def datei(wurzel=None) -> str:
    return os.path.join(adapter.ordner(wurzel), "geheim.enc")


def _schluessel_pfad() -> str:
    return os.path.expanduser(ai_config.setting("adapter_schluessel") or VORGABE_SCHLUESSEL)


def _geraete_schluessel(anlegen: bool):
    p = _schluessel_pfad()
    try:
        with open(p, encoding="ascii") as f:
            return f.read().strip().encode("ascii")
    except FileNotFoundError:
        if not anlegen:
            return None
    from cryptography.fernet import Fernet
    k = Fernet.generate_key()
    dateien.atomar_schreiben(p, k.decode("ascii") + "\n", geheim=True)
    return k


def _fernet(art: str, anlegen=False):
    from cryptography.fernet import Fernet
    if art == "konto":
        try:
            return Fernet(konto.konto_schluessel())
        except konto.KontoFehler:
            return None
    k = _geraete_schluessel(anlegen)
    return Fernet(k) if k else None


def ziel_art() -> str:
    """Womit neu verschlüsselt wird."""
    return "konto" if konto.angemeldet() else "geraet"


def darf_abgleichen() -> bool:
    """geheim.enc verlässt das Gerät nur verschlüsselt mit dem Kontoschlüssel."""
    return konto.angemeldet()


# ── Datei ──────────────────────────────────────────────────────────────

def _laden(wurzel=None) -> dict:
    try:
        with open(datei(wurzel), encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return {"format": FORMAT, "eintraege": {}}
    except (OSError, ValueError):
        raise GeheimFehler(f"{datei(wurzel)} is damaged.") from None
    if not isinstance(d, dict) or not isinstance(d.get("eintraege"), dict):
        raise GeheimFehler(f"{datei(wurzel)} is damaged.")
    return d


def _ablegen(d, wurzel=None):
    dateien.json_schreiben(datei(wurzel), d, geheim=True)


def namen(wurzel=None) -> list:
    try:
        return sorted(_laden(wurzel)["eintraege"])
    except GeheimFehler:
        return []


def lesen(name, wurzel=None):
    """Klartext eines Eintrags oder None (fehlt / mit einem Schlüssel
    verschlüsselt, den dieses Gerät nicht hat)."""
    from cryptography.fernet import InvalidToken
    try:
        e = _laden(wurzel)["eintraege"].get(name)
    except GeheimFehler as f:
        print(f"[adapter] {f}")
        return None
    if not isinstance(e, dict):
        return None
    f = _fernet(e.get("zu") or "")
    if f is None:
        return None
    try:
        return f.decrypt(str(e.get("wert") or "").encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def lesen_bytes(name, wurzel=None):
    w = lesen(name, wurzel)
    return None if w is None else base64.b64decode(w)


def setzen(name, wert: str, wurzel=None) -> bool:
    """Ablegen; → True, wenn sich etwas geändert hat. Derselbe Wert wird nicht
    neu verschlüsselt (Fernet würfelt — jede Fassung sähe sonst anders aus,
    und der Abgleich hielte sie für geändert)."""
    if lesen(name, wurzel) == wert:
        return False
    art = ziel_art()
    f = _fernet(art, anlegen=True)
    d = _laden(wurzel)
    d["eintraege"][name] = {"zu": art,
                            "wert": f.encrypt(str(wert).encode("utf-8")).decode("ascii")}
    _ablegen(d, wurzel)
    return True


def setzen_bytes(name, roh: bytes, wurzel=None) -> bool:
    return setzen(name, base64.b64encode(roh).decode("ascii"), wurzel)


def loeschen(name, wurzel=None) -> bool:
    d = _laden(wurzel)
    if d["eintraege"].pop(name, None) is None:
        return False
    _ablegen(d, wurzel)
    return True


def umschluesseln(ziel: str = None, wurzel=None) -> int:
    """Alle lesbaren Einträge, die nicht mit `ziel` verschlüsselt sind, neu
    verschlüsseln. → Anzahl. Unlesbare bleiben, wie sie sind."""
    ziel = ziel or ziel_art()
    try:
        d = _laden(wurzel)
    except GeheimFehler:
        return 0
    neu = [n for n, e in d["eintraege"].items() if isinstance(e, dict) and e.get("zu") != ziel]
    if not neu:
        return 0
    f = _fernet(ziel, anlegen=True)
    if f is None:
        return 0
    n = 0
    for name in neu:
        w = lesen(name, wurzel)
        if w is None:
            continue
        d["eintraege"][name] = {"zu": ziel, "wert": f.encrypt(w.encode("utf-8")).decode("ascii")}
        n += 1
    if n:
        _ablegen(d, wurzel)
    return n


def vor_abmelden(wurzel=None) -> int:
    """Vor dem Abmelden: alles auf den Geräteschlüssel, sonst wäre nach dem
    Abmelden kein Schlüssel mehr lesbar."""
    return umschluesseln("geraet", wurzel)


# ── KI-Schlüssel ───────────────────────────────────────────────────────

def ki_namen(wurzel=None) -> list:
    return [n[len(KI):] for n in namen(wurzel) if n.startswith(KI)]


def schluessel_einspielen(wurzel=None) -> list:
    """Die KI-Schlüssel aus dem Adapter in os.environ, damit die SDKs sie
    finden. Rangfolge: echte Umgebung > Adapter > data/ai_config.json (der
    alte Ort, nur noch Rückfall). → gesetzte Namen."""
    gesetzt = []
    for env in ki_namen(wurzel):
        w = lesen(KI + env, wurzel)
        if not w:
            continue
        if os.environ.get(env) and env not in ai_config.injiziert:
            continue                       # echte Umgebung gewinnt
        if os.environ.get(env) != w:
            os.environ[env] = w
            ai_config.injiziert.add(env)
            gesetzt.append(env)
    return gesetzt


def ki_uebernehmen(wurzel=None) -> dict:
    """Einmalig und beliebig oft: die Schlüssel aus data/ai_config.json in den
    Adapter. Ein Schlüssel verlässt ai_config.json erst, wenn er im Adapter
    wieder lesbar ist. Steht im Adapter schon ein ANDERER Wert, bleibt der
    alte hier stehen (Rückfall) — nichts geht verloren.
    → {"uebernommen": [...], "behalten": [...]}"""
    alt = dict(ai_config.alte_schluessel())
    raus = {"uebernommen": [], "behalten": []}
    if not alt:
        return raus
    weg = []
    for env, wert in sorted(alt.items()):
        wert = str(wert)
        da = lesen(KI + env, wurzel)
        if da is None:
            setzen(KI + env, wert, wurzel)
            da = lesen(KI + env, wurzel)
        if da == wert:
            weg.append(env)
            raus["uebernommen"].append(env)
        else:
            raus["behalten"].append(env)
    if weg:
        ai_config.alte_schluessel_entfernen(weg)
    return raus
