# core/kalender_zeitraum.py
#
# Relative Zeiträume ("diese_woche", "naechster_monat") in konkrete Daten
# übersetzen — reine Datums-Arithmetik, kein Kalender-Inhalt.
#
# Am 2026-10-06 aus core/kalender.py herausgelöst, als dort die Speicher-
# schicht getauscht wurde (memory/werkzeuge/kalender_ics_bauplan.md): die
# Fassade war ein eingefrorener Riese (Bauplan "Altlast: Riesen"), und dieser
# Teil braucht nichts außer dem Datum. kalender.py reicht RANGE_BUCKETS und
# resolve_range unverändert weiter — ai.py und die Profile benutzen sie dort.

from datetime import date, timedelta


# ── Range-Auflösung ───────────────────────────────────────────────────
#
# Designentscheidung (2026-06): der Kalender wird NICHT mehr in den Prompt
# geklebt. Die KI greift ihn ausschließlich über das read_calendar-Tool ab
# - für JEDEN Zeitraum (Woche, Monat, Quartal, Vergangenheit). Grund: Glue
# skaliert nicht ("was steht in 3 Monaten an?" lässt sich nicht mitkleben)
# und erzeugt einen faulen Halb-Weg, auf dem das 14B-Modell aus dem
# geklebten Block antwortet statt das Tool zu rufen → unnötige Rückfragen.
#
# Die Datums-Arithmetik macht hier Python, NICHT das Modell. Ein 14B kann
# eine Frage gut in einen Bucket KLASSIFIZIEREN ("den Monat" → dieser_monat),
# aber schlecht ISO-Grenzen RECHNEN. Also: Modell wählt den Bucket, resolve_range
# liefert die exakten Daten. Beliebige Sonderfälle ("ab dem 15." / weit in der
# Zukunft) gehen weiter über explizite start/end-Daten.

# Erlaubte Buckets für das `zeitraum`-Arg von read_calendar. Reihenfolge =
# Reihenfolge im Tool-Enum. Werte sind bewusst sprechend, damit das Modell
# sie aus der User-Frage ableiten kann.
RANGE_BUCKETS = [
    "heute", "morgen", "gestern",
    "diese_woche", "naechste_woche", "diese_und_naechste_woche", "letzte_woche",
    "dieser_monat", "naechster_monat", "letzter_monat",
    "naechste_7_tage", "naechste_30_tage", "naechste_90_tage",
    "letzte_7_tage", "letzte_30_tage",
]


def _month_last_day(d: date) -> date:
    """Letzter Tag des Monats, in dem `d` liegt (über 1. des Folgemonats - 1)."""
    if d.month == 12:
        first_next = date(d.year + 1, 1, 1)
    else:
        first_next = date(d.year, d.month + 1, 1)
    return first_next - timedelta(days=1)


def resolve_range(zeitraum: str, reference: date | None = None
                  ) -> tuple[date, date] | None:
    """
    Übersetzt einen relativen Bucket-Namen in ein konkretes (start, end)-Paar
    (beide inklusive). Gibt None zurück wenn der Bucket unbekannt ist - dann
    soll der Aufrufer auf explizite start/end-Daten zurückfallen.

    "Aktuelle"-Buckets (diese_woche, dieser_monat) starten bei HEUTE, nicht
    am Perioden-Anfang: wer "was steht diese Woche an?" fragt, will keine
    bereits vergangenen Tage. Vergangenes holt man gezielt über start/end.
    """
    today = reference or date.today()
    if zeitraum == "heute":
        return today, today
    if zeitraum == "morgen":
        t = today + timedelta(days=1)
        return t, t
    if zeitraum == "gestern":
        t = today - timedelta(days=1)
        return t, t
    if zeitraum == "diese_woche":
        sunday = today + timedelta(days=6 - today.weekday())
        return today, sunday
    if zeitraum == "naechste_woche":
        next_monday = today + timedelta(days=7 - today.weekday())
        return next_monday, next_monday + timedelta(days=6)
    if zeitraum == "diese_und_naechste_woche":
        # heute bis Sonntag der NÄCHSTEN Woche - die häufigste Frage
        # ("steht diese oder nächste Woche was an?") in einem Call.
        return today, today + timedelta(days=13 - today.weekday())
    if zeitraum == "letzte_woche":
        prev_monday = today - timedelta(days=today.weekday() + 7)
        return prev_monday, prev_monday + timedelta(days=6)
    if zeitraum == "dieser_monat":
        return today, _month_last_day(today)
    if zeitraum == "naechster_monat":
        first_next = _month_last_day(today) + timedelta(days=1)
        return first_next, _month_last_day(first_next)
    if zeitraum == "letzter_monat":
        last_prev  = date(today.year, today.month, 1) - timedelta(days=1)
        first_prev = date(last_prev.year, last_prev.month, 1)
        return first_prev, last_prev
    if zeitraum == "naechste_7_tage":
        return today, today + timedelta(days=6)
    if zeitraum == "naechste_30_tage":
        return today, today + timedelta(days=29)
    if zeitraum == "naechste_90_tage":
        return today, today + timedelta(days=89)
    if zeitraum == "letzte_7_tage":
        return today - timedelta(days=6), today
    if zeitraum == "letzte_30_tage":
        return today - timedelta(days=29), today
    return None
