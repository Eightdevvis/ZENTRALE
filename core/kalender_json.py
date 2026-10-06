# core/kalender_json.py
#
# Der ALTE Kalender-Speicher: eine JSON-Datei (data/ai_calendar.json) mit
# allen Ebenen, Terminen und Routinen.
#
# Bleibt erhalten, weil der Umstieg auf .ics (memory/werkzeuge/kalender_ics_bauplan.md)
# umschaltbar sein soll und der Default bis zu Sashas Umlegen `json` ist.
# Neu gegenüber dem Stand vor 2026-10-06 ist nur zweierlei:
#   * atomar schreiben (vorher konnte ein Absturz mitten im json.dump eine
#     halbe Datei hinterlassen — und damit den ganzen Kalender),
#   * die Rückfall-Sperre: ist der Kalender schon auf .ics umgezogen
#     (Marker in den Nebendaten), wird hier nicht mehr geschrieben.

import json
from pathlib import Path

from kalender_sicherung import KalenderGesperrt, atomar_schreiben


class JsonSpeicher:
    art = "json"
    # Der alte Speicher kennt alle Ebenen, auch `erlebt`.
    ohne_layer = frozenset()

    def __init__(self, pfad: Path, neben: Path | None = None):
        self.pfad = Path(pfad)
        self.neben = Path(neben) if neben else None

    def laden(self) -> dict | None:
        """Das Daten-Dict, oder None, wenn es die Datei (noch) nicht gibt."""
        if not self.pfad.exists():
            return None
        with self.pfad.open(encoding="utf-8") as f:
            return json.load(f)

    def speichern(self, data: dict, erlaube_massenloeschung: bool = False,
                  grund: str = "") -> None:
        sperre = migriert_marker(self.neben)
        if sperre:
            # Ein Knoten, der noch auf json steht, während der andere schon auf
            # .ics umgezogen ist, liefe still auseinander: seine Termine kämen
            # nie im vdir an. Lieber laut verweigern.
            raise KalenderGesperrt(
                f"Kalender ist seit {sperre} auf .ics umgestellt — dieser "
                f"Knoten steht noch auf 'json'. Nichts geschrieben. "
                f"Einstellung kalender_speicher auf 'ics' setzen und neu starten.")
        atomar_schreiben(self.pfad,
                         json.dumps(data, ensure_ascii=False, indent=2))


def migriert_marker(neben: Path | None) -> str | None:
    """Das Datum der Migration aus den Nebendaten, sonst None. Ein unlesbares
    Neben-File zählt NICHT als Marker — die Sperre soll nur greifen, wenn
    die Migration wirklich stattgefunden hat."""
    if not neben or not Path(neben).exists():
        return None
    try:
        d = json.loads(Path(neben).read_text(encoding="utf-8"))
    except Exception:
        return None
    m = d.get("migriert_am") if isinstance(d, dict) else None
    return m if isinstance(m, str) and m else None
