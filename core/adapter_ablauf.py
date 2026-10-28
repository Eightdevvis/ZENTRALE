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
#   kalender_quelle_setzen()
#                    die eine Stelle zum Umstöpseln: die Quelle einer
#                    Kalender-App (google | zencloud | lokal) setzen
#                    (core/kalender_einstellung.py). Löscht nie etwas.
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
import kalender_einstellung
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
    # Der bisherige Stand von vdirsyncer reist ab jetzt mit.
    bruecke.einpacken(KALENDER_ID, vdir_cfg.status_dir(a), vdir_cfg.kalender_paare(a),
                      _stand_datei(), dateien.knoten(), wurzel)
    raus["kalender"] = "angelegt"
    return raus


def mitte_hat_kalender(ordner="data/kalender"):
    """Hat die Mitte schon Termine in `ordner`? True/False, None =
    unbekannt — abgleich.mitte_hat_kalender, abgefangen (wirft nie)."""
    try:
        r = abgleich.mitte_hat_kalender(ordner=ordner)
    except Exception as e:      # noqa: BLE001 — unbekannt ist nie ein Fehler
        print(f"[adapter] Mitte nach dem Kalender gefragt: {e}")
        return None
    return r if r is True or r is False else None


def kalender_quelle_setzen(iid, quelle, wurzel) -> dict:
    """Die Quelle der Kalender-App `iid` umstöpseln (Sasha 28.10.2026: ein
    Wert, eine Stelle). Setzt nur den Wert in der Einstellung (die überall
    abgleicht) und löscht nie eine Termin-Datei:

      → google / lokal: Wert setzen. Die Termine hier bleiben liegen.
      → zencloud: erst die Mitte fragen (abgleich.mitte_hat_kalender).
          None (offline, unbekannt) → Abbruch, nichts geändert.
          False → dieses Gerät füllt die Cloud: Wert setzen und gleich
              abgleichen (adapter.kalender_fuellt); geht der Abgleich nicht
              hinaus, wird der Wert zurückgenommen (→ "offline") — sonst
              legte der nächste Abgleich den eigenen Kalender beiseite.
          True → die Cloud gilt: Wert setzen, der Kalender hier wandert
              beiseite (<abgleich>/kalender-vor-cloud/<zeit>/, nie gelöscht;
              nur wenn sich das Gerät noch nie mit der Mitte über ihn
              geeinigt hat), dann abgleichen. Jedes spätere Gerät tut beim
              ersten Abgleich dasselbe (adapter.vor_abgleich).

    → {"ergebnis": gleich | gesetzt | fuellt | uebernimmt | ohne_mitte |
       unbekannt | offline, "von": alte Quelle, "beiseite": Pfad|None,
       "fehler": Text|None}"""
    ke = kalender_einstellung
    if quelle not in ke.QUELLEN:
        raise adapter.AdapterFehler(
            f"Unknown calendar source '{quelle}' — use one of: {', '.join(ke.QUELLEN)}")
    alt = ke.quelle(iid, wurzel)
    raus = {"ergebnis": "gleich", "von": alt, "beiseite": None, "fehler": None}
    vorher = ke.roh_lesen(iid, wurzel)
    if alt == quelle and vorher is not None:
        return raus
    ordner = ke.ordner(iid, wurzel)
    if quelle != "zencloud":
        ke.schreiben(iid, quelle, wurzel)
        if iid == ke.HAUPT:
            ke.alt_mitte_weg(wurzel)
        return dict(raus, ergebnis="gesetzt")
    if nur_lokal():
        return dict(raus, ergebnis="ohne_mitte")
    hat = mitte_hat_kalender(ordner)
    if hat is None:
        return dict(raus, ergebnis="unbekannt")
    ke.schreiben(iid, "zencloud", wurzel)
    if hat:
        if not adapter.kalender_in_basis(abgleich.ordner(), ordner):
            raus["beiseite"] = adapter.beiseite_legen(wurzel, abgleich.ordner(), ordner)
        if iid == ke.HAUPT:
            ke.alt_mitte_weg(wurzel)
        return dict(raus, ergebnis="uebernimmt", fehler=_abgleichen(wurzel))
    with adapter.kalender_fuellt(ordner):
        fehler = _abgleichen(wurzel)
    if fehler:
        ke.roh_zurueck(iid, vorher, wurzel)
        return dict(raus, ergebnis="offline", fehler=fehler)
    if iid == ke.HAUPT and ke.alt_mitte_da(wurzel):
        ke.alt_mitte_weg(wurzel)
        _abgleichen(wurzel)
    return dict(raus, ergebnis="fuellt")


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
    if not adapter.kalender_google_an(wurzel):
        return Lauf("aus", text="calendar source is not google")
    if nur_lokal() or not adapter.kalender_mit_vertrag(wurzel):
        # Ohne Mitte, oder quelle=google gesetzt: die Cloud trägt den
        # Kalender nicht, jedes Gerät gleicht selbst mit Google ab.
        return _fahren(a, wurzel, vdir, fahren, ich, jetzt, lokal=True)
    # Der alte Weg mit Mietvertrag: erst fahren, wenn der Kalender aus der
    # Cloud hier ist (die Basis kennt ihn) oder die Cloud keinen hat.
    if not adapter.kalender_in_basis(abgleich.ordner()):
        fehler = _abgleichen(wurzel)            # holt den Kalender zum ersten Mal
        if fehler:
            return Lauf("wartet", text=fehler)
        if not adapter.kalender_in_basis(abgleich.ordner()) and mitte_hat_kalender() is not False:
            return Lauf("wartet", text="calendar not synced to this device yet")
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
