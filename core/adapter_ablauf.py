# core/adapter_ablauf.py
#
# Die Abläufe des Adapters (memory/hub/adapter.md):
#
#   einrichten()     was auf diesem Gerät schon angekabelt ist, in den
#                    Adapter holen — KI-Schlüssel aus data/ai_config.json,
#                    die vorhandene vdirsyncer-Konfiguration als Anschluss
#                    `google-kalender`. Beliebig oft, ändert nur, was fehlt.
#   bruecke_lauf()   ein Lauf des Kalender-Timers auf irgendeinem Gerät:
#                    Brücke nehmen oder verlängern → abgleichen → nur wenn
#                    der Abgleich den eigenen Namen zurückbrachte, Google
#                    abgleichen → Token und Stand zurück → abgleichen.
#   kalender_mitte_einschalten()
#                    der Schalter „Kalender über die Mitte, ohne Google":
#                    Anschluss `kalender-mitte` (keine Brücke, kein Timer).
#
# Fundament (Schicht 1). Den Lauf von vdirsyncer selbst (mit allen
# Sicherungen, scripts/kalender_sync.py) gibt der Aufrufer herein.

import os
import shutil

import abgleich
import adapter
import adapter_bruecke as bruecke
import adapter_geheim
import adapter_vdirsyncer as vdir_cfg
import dateien
import kalender_sync_zustand

KALENDER_ID = "google-kalender"
KI_ID = "ki-anbieter"


def _ki_anschluss(wurzel=None):
    namen = adapter_geheim.ki_namen(wurzel)
    if not namen:
        return None
    a = adapter.lesen(KI_ID, wurzel)
    if a and sorted((a.get("einstellungen") or {}).get("schluessel") or []) == sorted(namen):
        return None
    neu = a or adapter.neu(KI_ID, "ki-anbieter", "assistent", "AI providers")
    neu["einstellungen"] = {"schluessel": sorted(namen)}
    adapter.speichern(neu, wurzel)
    return neu


def einrichten(vdir=None, wurzel=None, kalender=True) -> dict:
    """→ {"ki": {...}, "kalender": "angelegt"|"vorhanden"|"keine_config"|None}.
    `vdir` = data/kalender/ dieses Geräts (nur für den Kalender nötig)."""
    raus = {"ki": adapter_geheim.ki_uebernehmen(wurzel), "kalender": None}
    _ki_anschluss(wurzel)
    if not kalender or vdir is None:
        return raus
    if adapter.kalender_anschluss(wurzel):
        raus["kalender"] = "vorhanden"
        return raus
    cfg = vdir_cfg.vorgabe_config()
    if not os.path.isfile(cfg):
        raus["kalender"] = "keine_config"
        return raus
    einst = vdir_cfg.vorlage_aus(cfg, KALENDER_ID, vdir, wurzel)
    a = adapter.neu(KALENDER_ID, "kalender-vdirsyncer", "kalender", "Google Calendar", einst)
    if not vdir_cfg.kalender_paare(a):
        raus["kalender"] = "kein_paar"
        return raus
    adapter.speichern(a, wurzel)
    # Dieses Gerät brachte den Kalender mit: von Anfang an dabei, und sein
    # bisheriger Stand von vdirsyncer reist ab jetzt mit.
    adapter.als_ursprung_merken(abgleich.ordner())
    bruecke.einpacken(KALENDER_ID, vdir_cfg.status_dir(a), vdir_cfg.kalender_paare(a),
                      _stand_datei(), dateien.knoten(), wurzel)
    raus["kalender"] = "angelegt"
    return raus


def kalender_mitte_einschalten(wurzel) -> tuple:
    """Der Schalter „Kalender über die Mitte, ohne Google" (Sasha 28.10.2026:
    Google wird abgelöst). Legt den Anschluss `kalender-mitte` an — Art ohne
    Brücke: data/kalender/** gleicht über die Mitte ab, niemand spricht mit
    Google. Die Mitte ist die Wahrheit; Ursprung ist nur, wer als ERSTER
    einschaltet:

      1. erst abgleichen — bringt einen Kalender-Anschluss, den ein anderes
         Gerät schon angelegt hat (ohne Mitte oder offline: nichts tun);
      2. gab es schon einen Kalender-Anschluss, ist dieses Gerät NICHT der
         Ursprung: kein Merkzettel, beim nächsten Abgleich wandert sein alter
         data/kalender/ beiseite (vor_abgleich, nie gelöscht) und es übernimmt
         den Stand der Mitte;
      3. sonst ist es der Ursprung (als_ursprung_merken): sein Kalender füllt
         die Mitte und wandert nie beiseite;
      4. abgleichen — der Anschluss (und beim Ursprung der Kalender) geht
         gleich hinaus.

    Löscht nie eine .ics. Ausschalten = Anschluss-Datei entfernen (dann
    schneidet abgleich_apps.jetzt_erlaubt den Kalender wieder heraus).
    → (ergebnis, fehler): ergebnis ∈ ursprung | dazu | vorhanden |
    ohne_mitte | offline; fehler = Text des letzten Abgleichs oder None."""
    if nur_lokal():
        return "ohne_mitte", None
    fehler = _abgleichen(wurzel)
    if fehler:
        return "offline", fehler
    if adapter.lesen(adapter.MITTE_ID, wurzel):
        return "vorhanden", _abgleichen(wurzel)
    # Liegen schon Termine in der Mitte, war ein anderes Gerät zuerst — auch
    # wenn sein Anschluss hier noch nicht angekommen ist (abgleich.mitte_hat_kalender).
    schon = adapter.kalender_ueber_cloud(wurzel) or abgleich.mitte_hat_kalender() is True
    adapter.speichern(adapter.neu(adapter.MITTE_ID, "kalender-mitte", "kalender",
                                  "Calendar through your account"), wurzel)
    if not schon:
        adapter.als_ursprung_merken(abgleich.ordner())
    return ("dazu" if schon else "ursprung"), _abgleichen(wurzel)


def _stand_datei():
    # Die Liste der Löschsperre von scripts/kalender_sync.py (dort STAND).
    return os.path.expanduser(os.environ.get("ZENTRALE_KALENDER_SYNC_STAND")
                              or "~/.local/share/vdirsyncer/zentrale_stand.json")


def nur_lokal() -> bool:
    """Ohne Mitte (kein Konto bzw. kein Schlüssel) ist jedes Gerät seine
    eigene Brücke. Bewusst NICHT nach `abgleich_weg`: wer angemeldet ist,
    kann abgleichen (auch `zentrale sync` auf dem alten rsync-Weg) — ein
    solches Gerät ohne Vertrag fahren zu lassen, hieße zwei Brücken."""
    return not abgleich.schluessel_da()


class Lauf:
    """Ergebnis von bruecke_lauf: gefahren (Exit-Code) oder warum nicht."""

    def __init__(self, art, code=0, miete=None, text=""):
        self.art, self.code, self.miete, self.text = art, code, miete, text

    def __repr__(self):
        return f"Lauf({self.art!r}, {self.code})"


def _abgleichen(wurzel):
    try:
        abgleich.abgleichen(str(wurzel))
        return None
    except abgleich.Besetzt:
        return "a sync is already running"
    except Exception as e:      # noqa: BLE001 — offline, abgemeldet, Mitte weg
        return str(e)[:120]


def bruecke_lauf(a, wurzel, vdir, fahren, jetzt=None) -> Lauf:
    """Ein Lauf auf diesem Gerät. `fahren(config_pfad) → Exit-Code` ist der
    eigentliche Google-Abgleich (mit Sicherungen). Arten des Ergebnisses:
    gefahren, andere (jemand anders hält die Brücke), wartet (noch nicht
    dabei / kein vdirsyncer), offline (kein Abgleich möglich), fehlt (ein
    Geheimnis ist hier nicht lesbar)."""
    ich = dateien.knoten()
    aid = a["id"]
    if not shutil.which("vdirsyncer"):
        return Lauf("wartet", text="vdirsyncer is not installed on this device")
    if nur_lokal():
        return _fahren(a, wurzel, vdir, fahren, ich, jetzt, lokal=True)
    if not adapter.kalender_dabei(abgleich.ordner()):
        fehler = _abgleichen(wurzel)            # holt den Kalender zum ersten Mal
        if fehler or not adapter.kalender_dabei(abgleich.ordner()):
            return Lauf("wartet", text=fehler or "calendar not synced to this device yet")
    miete = bruecke.lesen(aid, wurzel)
    if not bruecke.frei_fuer(miete, ich, jetzt):
        return Lauf("andere", miete=miete)
    bruecke.beanspruchen(aid, ich, jetzt, wurzel)
    fehler = _abgleichen(wurzel)
    if fehler:
        return Lauf("offline", text=fehler)
    miete = bruecke.lesen(aid, wurzel)
    if not bruecke.haelt(miete, ich, jetzt):
        return Lauf("andere", miete=miete)
    a = adapter.lesen(aid, wurzel) or a        # kann mit dem Abgleich neu gekommen sein
    lauf = _fahren(a, wurzel, vdir, fahren, ich, jetzt)
    # Verlängern, und den Stand dieses Laufs für alle Geräte mitgeben.
    bruecke.beanspruchen(aid, ich, None, wurzel,
                         zustand=dict(kalender_sync_zustand.lesen() or {}, bruecke=ich))
    _abgleichen(wurzel)                         # Termine, Token, Stand gleich hinaus
    return lauf


def _fahren(a, wurzel, vdir, fahren, ich, jetzt, lokal=False) -> Lauf:
    aid = a["id"]
    status = vdir_cfg.status_dir(a)
    if not lokal:
        bruecke.auspacken(aid, status, _stand_datei(), wurzel)
    try:
        cfg = vdir_cfg.bauen(a, vdir, wurzel)
    except adapter.AdapterFehler as e:
        return Lauf("fehlt", code=1, text=str(e))
    fehler = vdir_cfg.entdecken(a, cfg, shutil.which("vdirsyncer") or "vdirsyncer")
    if fehler:
        return Lauf("fehlt", code=1, text=fehler)
    alt = os.environ.get("VDIRSYNCER_CONFIG")
    os.environ["VDIRSYNCER_CONFIG"] = cfg
    try:
        code = fahren(cfg)
    finally:
        if alt is None:
            os.environ.pop("VDIRSYNCER_CONFIG", None)
        else:
            os.environ["VDIRSYNCER_CONFIG"] = alt
    vdir_cfg.zurueckschreiben(a, wurzel)
    if not lokal:
        bruecke.einpacken(aid, status, vdir_cfg.kalender_paare(a), _stand_datei(), ich, wurzel)
    return Lauf("gefahren", code=code)
