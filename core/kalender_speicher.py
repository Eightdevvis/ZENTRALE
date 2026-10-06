# core/kalender_speicher.py
#
# Welcher Speicher hält den Kalender — die alte JSON oder der .ics-Ordner?
#
# Die eine Stelle für diese Entscheidung und für alle Pfade, die daran
# hängen. Die Fassade (core/kalender.py) fragt hier bei JEDEM Zugriff nach,
# statt sich den Speicher beim Import zu merken: so wirkt ein in Tests
# umgebogenes `kalender.CAL_PATH` auch auf den .ics-Ordner, und die
# Einstellung lässt sich ohne Neuimport umschalten.
#
# Umschalter: Einstellung `kalender_speicher` über ai_config.setting —
# Env ZENTRALE_KALENDER_SPEICHER > data/ai_config.json > Default "json".
# Default bleibt "json", bis Sasha mit scripts/kalender_migrieren.py umlegt
# (memory/werkzeuge/kalender_ics_bauplan.md).

from pathlib import Path

import ai_config
import kalender_spiegel
from kalender_ics import IcsSpeicher
from kalender_json import JsonSpeicher

MODI = ("json", "ics")
DEFAULT_LOESCHSPERRE = 5
DEFAULT_GIT_SPIEGEL = Path.home() / ".local" / "share" / "zentrale" / "kalender-git"


def modus() -> str:
    """"json" oder "ics". Ein unbekannter Wert fällt auf "json" zurück — der
    bisherige, bewährte Weg — statt auf einen halben Zustand."""
    wert = str(ai_config.setting("kalender_speicher", "json") or "json").strip().lower()
    return wert if wert in MODI else "json"


def pfade(cal_path: Path, ics_dir: Path | None = None) -> dict:
    """Alle Kalender-Pfade, abgeleitet aus dem Ort der alten JSON.

    Alles liegt nebeneinander in data/, damit der bestehende Sync (alles
    Ungetrackte in data/) es ohne neue Regel mitnimmt — auch Verlauf und
    Snapshots, die so automatisch auf dem anderen Knoten liegen."""
    basis = Path(cal_path).parent
    return {
        "json": Path(cal_path),
        "vdir": Path(ics_dir) if ics_dir else basis / "kalender",
        "neben": basis / "kalender_neben.json",
        "verlauf": basis / "kalender_verlauf",
        "snapshots": basis / "kalender_snapshots",
    }


def loeschsperre() -> int:
    """Wie viele Termine eine einzige Operation höchstens löschen darf."""
    try:
        return max(0, int(ai_config.setting("kalender_loeschsperre",
                                            DEFAULT_LOESCHSPERRE)))
    except (TypeError, ValueError):
        return DEFAULT_LOESCHSPERRE


def git_spiegel_pfad() -> Path | None:
    """Ziel des git-Spiegels, None = aus. Bewusst AUSSERHALB von data/:
    ein git-Repo in data/ würde der dateiweise Sync zerstören."""
    wert = ai_config.setting("kalender_git_spiegel", "")
    wert = str(wert).strip() if wert is not None else ""
    if wert.lower() in ("aus", "off", "0", "nein", "false"):
        return None
    return Path(wert).expanduser() if wert else DEFAULT_GIT_SPIEGEL


def ics_speicher(cal_path: Path, ics_dir: Path | None = None,
                 mit_spiegel: bool = True, **kw) -> IcsSpeicher:
    p = pfade(cal_path, ics_dir)
    spiegel = None
    ziel = git_spiegel_pfad() if mit_spiegel else None
    if ziel is not None:
        def spiegel(grund, _p=p, _ziel=ziel):
            kalender_spiegel.spiegeln({"kalender": _p["vdir"],
                                       "kalender_neben.json": _p["neben"]},
                                      _ziel, grund)
    kw.setdefault("loeschsperre", loeschsperre())
    return IcsSpeicher(p["vdir"], p["neben"], p["verlauf"], p["snapshots"],
                       spiegel=spiegel, **kw)


def json_speicher(cal_path: Path, ics_dir: Path | None = None) -> JsonSpeicher:
    p = pfade(cal_path, ics_dir)
    return JsonSpeicher(p["json"], neben=p["neben"])


def speicher_fuer(cal_path: Path, ics_dir: Path | None = None,
                  art: str | None = None):
    """Der Speicher, den die Einstellung gerade verlangt."""
    if (art or modus()) == "ics":
        return ics_speicher(cal_path, ics_dir)
    return json_speicher(cal_path, ics_dir)
