"""Ein synthetischer Kalender mit ALLEN Feldern, die die alte JSON kennt —
und ein paar, die sie nur aus Versehen kennt (kaputte Daten, leere Tage,
unbekannte Felder). Gebraucht von den .ics-Speicher- und Migrations-Tests.

Absichtlich enthalten, weil es so in Sashas echten Daten vorkommt oder
vorkommen kann:
  * Uhrzeiten ohne Minuten ("10", "9:30") — echte Daten, 2026-07/08
  * zwei Routinen mit demselben Namen (Geigenstunde 17:45 und 18:00)
  * Pausen für eine Routine, die zweimal existiert
  * eine Spanne mit Uhrzeit an einem Tag in der Mitte (Basel)
  * Tage, die nicht nach Datum sortiert im Dict stehen
"""

import copy

VOLL = {
    "version": 1,
    "layers": {
        "termine": {
            "label": "Termine", "color": "#ff5500", "default_visible": True,
            "entries": {
                "2026-06-03": [{"label": "TÜV-Frist"},
                               {"label": "Arzt", "time": "09:30", "ende": "10:15",
                                "ort": "Praxis", "tags": ["x"]}],
                "2026-06-08": [{"label": "Ungarn-Reise", "bis": "2026-06-12", "ort": "Ungarn"}],
                "2026-07-13": [{"label": "Basel", "bis": "2026-07-17",
                                "times": {"2026-07-14": "10", "2026-07-16": "12:30"}}],
                "2026-07-04": [{"label": "Früh", "time": "9:30"},
                               {"label": "Nacht", "time": "23:00", "ende": "24:00"}],
                "2026-07-05": [{"label": "Komisch", "time": "18:00", "ende": "17:00",
                                "absage_noetig": True, "unbekannt": {"a": [1, 2]}}],
                "2026-13-01": [{"label": "Kaputtes Datum"}],
                "2026-07-06": [],
                "2026-07-07": [{"label": "Verdreht", "bis": "2026-07-01"}],
                "2026-06-09": [{"label": "Termin um 10 Uhr", "time": "10:00", "ende": "11:00"},
                               {"label": "Zur selben Zeit", "time": "10:00", "ende": "10:30"},
                               {"label": "Zur selben Zeit", "time": "10:00", "ende": "10:30"}],
            },
            "routines": [],
        },
        "routinen": {
            "label": "Routinen", "color": "#5577ff", "default_visible": True,
            "entries": {"2026-06-10": [{"label": "Ausnahme", "time": "12:00"}]},
            "routines": [
                {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
                 "ende": "18:30", "ort": "Geigenschule", "absage_noetig": True},
                {"label": "Fahrschule", "rrule": "FREQ=WEEKLY;BYDAY=TU,TH", "time": "19:00",
                 "ende": "20:00", "ort": "Fahrschule", "aus": ["2026-06-30", "2026-07-14"]},
                {"label": "Parkour", "rrule": "FREQ=WEEKLY;BYDAY=WE", "time": "18:00",
                 "aus": ["2026-07-15", "kein-datum"]},
                {"label": "Weihnachten", "rrule": "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"},
                {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "18:00"},
                {"label": "Miete", "rrule": "FREQ=MONTHLY;BYMONTHDAY=1", "notiz": "Dauerauftrag"},
            ],
        },
        "erlebt": {
            "label": "Erlebt (auto)", "color": "#888888", "default_visible": False,
            "entries": {"2026-05-19": [{"label": "Sport"}], "2026-08-16": [{"label": "Fieber"}]},
            "routines": [],
        },
        "eigene": {
            "label": "Eigene Ebene", "color": "#123456", "default_visible": False,
            "extra_meta": 1,
            "entries": {"2026-08-01": [{"label": "Privat", "time": "20:00"}]},
            "routines": [],
        },
    },
    "reisezeiten": {"Geigenschule": {"Fahrschule": 10}},
    "puffer_min": 15,
    "pausen": [
        {"label": "Geigenstunde", "von": "2026-06-29", "bis": "2026-08-07", "grund": "Sommerferien"},
        {"label": "Niemand", "von": "2026-06-01", "bis": "2026-06-02"},
        {"label": "Parkour", "von": "2026-08-01", "bis": "kaputt", "grund": "x"},
        {"label": "Geigenstunde", "von": "2026-10-05", "bis": "2026-10-16", "grund": "Herbstferien"},
    ],
    "unbekannt_oben": {"x": 1},
}


def voll():
    return copy.deepcopy(VOLL)


def ohne_erlebt():
    d = voll()
    del d["layers"]["erlebt"]
    return d
