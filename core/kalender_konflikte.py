# core/kalender_konflikte.py
#
# Was der Kalender ÜBER die Termine weiß: Kollisionen, Fahrzeiten und knappe
# Übergänge, Pausen-Gründe, Abwesenheit, Absage- und Konflikt-Alarme, der
# Text für das Lese-Werkzeug der KI und der Tages-Abdruck im Prompt.
#
# Bis 09.10.2026 Teil von core/kalender.py; ausgezogen, weil kalender.py an
# der Riesen-Grenze stand (1.499 von 1.500 Zeilen, memory/system/
# bauplan_kern.md) und die Kennungen (core/kalender_kennung.py) Platz
# brauchten. Code unverändert. kalender.py reicht alle Namen weiter —
# Aufrufer schreiben weiter kalender.open_alarms() usw.

import hashlib
import os
from datetime import date, timedelta

# Kein `import kalender` (das wäre ein Import-Kreis, kalender reicht dieses
# Modul ja weiter): die zwei Lesewege, die hier gebraucht werden, schließt
# kalender.py beim Laden an (anschliessen() ganz unten in kalender.py). So
# bleibt kalender.CAL_PATH die eine Stelle, an der Tests den Kalender umlenken.
_load_raw = None
entries_in_range = None


# Ebene „uncommitted" (10.10.2026): Unverbindliches löst keinen Alarm und
# keine Rückfrage aus und macht keine Abwesenheit — die KI liest es als
# „vielleicht" (Sasha: „nur als hinweis").
UNVERBINDLICH = "uncommitted"


def _verbindlich(e: dict) -> bool:
    return e.get("layer") != UNVERBINDLICH and not e.get("deaktiviert")


def anschliessen(laden, im_zeitraum) -> None:
    global _load_raw, entries_in_range
    _load_raw, entries_in_range = laden, im_zeitraum


_WEEKDAYS_FULL_DE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
                     "Freitag", "Samstag", "Sonntag"]


def _to_minutes(hhmm: str) -> int | None:
    """'17:45' → 1065 (Minuten seit Mitternacht). None bei Murks."""
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


# Default-Puffer (Minuten), der bei der Reisezeit-Prüfung auf JEDE Fahrt
# draufkommt - Reserve, falls was schiefläuft. Pro Kalender-Datei über das
# Feld "puffer_min" überschreibbar (Entscheidung 2026-06-06).
DEFAULT_PUFFER_MIN = 15


def _interval(e: dict) -> tuple[int, int] | None:
    """
    (start_min, end_min) eines Eintrags in Minuten-seit-Mitternacht, oder
    None wenn er KEIN echtes Zeit-Intervall ist (time/ende fehlt oder
    ende <= start). Ganztags-Einträge (nur 'label') fallen so bewusst raus.
    """
    s  = _to_minutes(e.get("time", ""))
    en = _to_minutes(e.get("ende", ""))
    if s is None or en is None or en <= s:
        return None
    return s, en


def _fmt_min(m: int) -> str:
    """1065 → '17:45' (für Warnzeilen-Zeitangaben)."""
    return f"{m // 60:02d}:{m % 60:02d}"


def _fmt_entry(e: dict) -> str:
    """'Geigenstunde (17:45-18:30)' für eine ⚠-Zeile."""
    return f"{e.get('label', '?')} ({e.get('time', '?')}-{e.get('ende', '?')})"


def find_collisions(entries: list[dict]) -> list[tuple[dict, dict, str]]:
    """
    Findet überlappende Termin-Paare an EINEM Tag und klassifiziert die Art.

    Kollisions-Modell (entschieden 2026-06-06): ein Eintrag zählt nur dann
    mit, wenn er SOWOHL 'time' ALS AUCH 'ende' hat - erst dann ist er ein
    echtes Zeit-Intervall. Einträge ohne Ende gelten als ganztags/unbestimmt
    und lösen bewusst keine Kollision aus (sonst würde jeder zeitlose Eintrag
    mit allem "kollidieren").

    Reine Intervall-Mathematik → gehört in Python, nicht ins Modell (selbes
    Prinzip wie resolve_range fürs Datum, suche fürs Filtern). Das Modell
    bekommt nur die fertige ⚠-Zeile serviert.

    Rückgabe: Liste von (a, b, kind), a startet nicht nach b. kind ist:
      'voll' – einer steckt komplett im anderen (oder identisch) →
               entweder/oder, splitten bringt nichts.
      'teil' – sie überschneiden sich nur teilweise, jeder hat Exklusiv-Zeit
               → man könnte den ersten früher verlassen.

    Overlap (halboffen): a_start < b_end und b_start < a_end. Termine, die
    sich nur an der Grenze berühren (18:00↔18:00), kollidieren NICHT.
    """
    timed = []
    for e in entries:
        iv = _interval(e)
        if iv:
            timed.append((iv[0], iv[1], e))
    timed.sort(key=lambda t: (t[0], t[1]))

    out: list[tuple[dict, dict, str]] = []
    for i in range(len(timed)):
        a_s, a_e, a = timed[i]
        for j in range(i + 1, len(timed)):
            b_s, b_e, b = timed[j]
            if not (a_s < b_e and b_s < a_e):
                continue  # kein Overlap
            # Umschließt einer den anderen vollständig? Dann 'voll', sonst nur
            # teilweise. (Beide Richtungen prüfen, falls gleicher Startzeit-
            # punkt aber unterschiedliche Länge.)
            a_contains_b = a_s <= b_s and a_e >= b_e
            b_contains_a = b_s <= a_s and b_e >= a_e
            kind = "voll" if (a_contains_b or b_contains_a) else "teil"
            out.append((a, b, kind))
    return out


def _load_config() -> tuple[dict, int]:
    """
    (reisezeiten-Matrix, puffer_min) aus der Kalender-Datei. Beide Felder sind
    optional - fehlen sie, gilt leere Matrix bzw. DEFAULT_PUFFER_MIN. Die Matrix
    ist {von: {nach: minuten}} und darf unvollständig/asymmetrisch sein
    (travel_minutes schaut in beide Richtungen).
    """
    try:
        data = _load_raw()
    except Exception:
        return {}, DEFAULT_PUFFER_MIN
    matrix = data.get("reisezeiten") or {}
    try:
        puffer = int(data.get("puffer_min", DEFAULT_PUFFER_MIN))
    except (TypeError, ValueError):
        puffer = DEFAULT_PUFFER_MIN
    return matrix, puffer


def travel_minutes(von: str | None, nach: str | None,
                   matrix: dict | None = None) -> int | None:
    """
    Grobe Reisezeit zwischen zwei Orten in Minuten - die EINE Nahtstelle für
    Ortsdistanz. Heute liest sie eine handgepflegte, symmetrische Matrix aus
    der Kalender-Datei ('reisezeiten'). Später kann hier ein eigener Router
    (Dijkstra o.ä.) oder ein Transit-Grep andocken, OHNE dass der Kalender-
    Layer drumherum sich ändert - bewusst NIE eine Google-Maps-Anbindung.

    Rückgabe:
      0    – gleicher Ort (kein Weg nötig)
      int  – bekannte grobe Fahrzeit
      None – Orte fehlen oder Paar nicht in der Matrix → KEINE Aussage
             (lieber schweigen als eine Distanz erfinden)
    """
    if not von or not nach:
        return None
    if von == nach:
        return 0
    if matrix is None:
        matrix, _ = _load_config()
    if von in matrix and nach in matrix[von]:
        return matrix[von][nach]
    if nach in matrix and von in matrix[nach]:
        return matrix[nach][von]
    return None


def day_warnings(entries: list[dict],
                 matrix: dict | None = None,
                 puffer_min: int | None = None) -> list[str]:
    """
    Baut die ⚠-Warnzeilen für einen Tag - genau die drei Fälle, die wir
    festgelegt haben (2026-06-06):

      • voll überlappt   → entweder/oder
      • teils überlappt  → ersten früher verlassen + Rest beim nächsten?
                           (bewusste Nachfrage - Ausnahme von "keine Rückfragen")
      • kein Overlap, aber Lücke < Fahrzeit+Puffer → wird örtlich knapp

    Reisezeit kommt aus travel_minutes (handgepflegte Matrix, offline). Fehlt
    sie (Ort unbekannt / Paar nicht gepflegt / gleicher Ort), gibt es KEINE
    Knapp-Warnung - der Layer rät nie über Distanzen.
    """
    if matrix is None or puffer_min is None:
        m, p = _load_config()
        matrix     = m if matrix     is None else matrix
        puffer_min = p if puffer_min is None else puffer_min

    warns: list[str] = []

    # 1) Überlappungen (voll / teil)
    for a, b, kind in find_collisions(entries):
        if kind == "voll":
            warns.append(
                f"⚠ Kollision: {_fmt_entry(a)} und {_fmt_entry(b)} "
                "überlappen sich komplett - entweder/oder."
            )
        else:
            # Teil von b, der nach a-Ende noch übrig wäre (lohnt das Hinrennen?)
            rest = _interval(b)[1] - _interval(a)[1]
            warns.append(
                f"⚠ Teil-Überlappung: {_fmt_entry(a)} und {_fmt_entry(b)} "
                f"überschneiden sich teilweise ({b.get('label', '?')} läuft "
                f"{rest} min länger)."
            )

    # 2) Knappe Übergänge zwischen direkt aufeinanderfolgenden Terminen.
    #    Nur benachbarte Paare prüfen - eine Lücke gibt es immer nur zum
    #    unmittelbar nächsten Termin.
    timed = []
    for e in entries:
        iv = _interval(e)
        if iv:
            timed.append((iv[0], iv[1], e))
    timed.sort(key=lambda t: (t[0], t[1]))
    for i in range(len(timed) - 1):
        _a_s, a_e, a = timed[i]
        b_s, _b_e, b = timed[i + 1]
        if b_s < a_e:
            continue  # überlappt → schon unter (1) behandelt
        tt = travel_minutes(a.get("ort"), b.get("ort"), matrix=matrix)
        if not tt:  # None (unbekannt) oder 0 (gleicher Ort) → kein Hinweis
            continue
        gap  = b_s - a_e
        need = tt + puffer_min
        if gap < need:
            warns.append(
                f"⚠ Knapp: zwischen {a.get('label', '?')} (Ende {_fmt_min(a_e)}) "
                f"und {b.get('label', '?')} ({_fmt_min(b_s)}) nur {gap} min - "
                f"du brauchst ~{need} min (Fahrt {tt} + {puffer_min} Puffer)."
            )
    return warns


def _pause_grund(label: str, day: date, pausen: list[dict],
                kennung: str | None = None) -> str | None:
    """
    Grund, falls die Routine `label` an `day` pausiert (Ferien etc.), sonst None.

    Die EINE Nahtstelle für Ausfälle - heute aus der manuell gepflegten
    `pausen`-Liste. Wenn die KI später Internet hat, kann hier zusätzlich eine
    automatische Ferien-/Feiertags-Abfrage andocken, ohne dass der Rest sich
    ändert (bewusst nie über Google).
    """
    for p in pausen:
        # Seit 09.10.2026 hängt eine Pause per `routine_uid` an IHRER Routine
        # (Umbenennen nimmt sie mit). Alte Pausen ohne sie gehen über den Titel.
        if p.get("routine_uid"):
            if p["routine_uid"] != kennung:
                continue
        elif p.get("label") != label:
            continue
        try:
            von = date.fromisoformat(p["von"])
            bis = date.fromisoformat(p["bis"])
        except (ValueError, KeyError):
            continue
        if von <= day <= bis:
            return p.get("grund", "Pause")
    return None


def _away_blocks(start: date, end: date, data: dict | None = None) -> list[dict]:
    """
    Findet Mehrtages-Abwesenheits-Blöcke, die den Bereich [start, end]
    überschneiden. Ein Block ist ein Einmal-Eintrag mit `bis`-Feld (Enddatum)
    UND `ort` - z.B. eine Reise:

        "2026-06-08": [{"label": "Ungarn-Reise", "bis": "2026-06-12", "ort": "Ungarn"}]

    Damit weiß der Kalender über mehrere Tage, WO du bist - die Voraussetzung,
    um lokale Termine in der Spanne (Geige daheim, während du in Ungarn bist)
    als unmöglich zu erkennen. Ohne `bis` ist ein Eintrag ein Punkt und löst
    keine Abwesenheit aus.

    Rückgabe: Liste von {von, bis, ort, label} (von/bis als date).
    """
    if data is None:
        data = _load_raw()
    blocks: list[dict] = []
    for lname, layer in data.get("layers", {}).items():
        if lname == UNVERBINDLICH:
            continue                     # eine Vielleicht-Reise macht nicht abwesend
        for day_iso, day_entries in layer.get("entries", {}).items():
            for e in day_entries:
                bis = e.get("bis")
                if not bis:
                    continue
                try:
                    von_d = date.fromisoformat(day_iso)
                    bis_d = date.fromisoformat(bis)
                except ValueError:
                    continue
                if bis_d < von_d:
                    continue
                # Überschneidet der Block den abgefragten Bereich?
                if bis_d >= start and von_d <= end:
                    blocks.append({"von": von_d, "bis": bis_d,
                                   "ort": e.get("ort"), "label": e.get("label", "?")})
    return blocks


def _conflict_lines(day: date, entries: list[dict],
                    away_blocks: list[dict]) -> list[str]:
    """
    Prüft für EINEN Tag, ob ein konkreter Termin in eine Abwesenheits-Spanne
    fällt, in der du an einem ANDEREN Ort bist - der „du bist in Ungarn, hast
    aber Dienstag Geige"-Fall. Liefert fertige ⚠-KONFLIKT-Zeilen.

    NUR Einmal-Termine (unregelmäßig) lösen Alarm aus. Regelmäßige Routinen
    (recurring=True: Geige, Fahrschule, Parkour) fallen auf einer Reise sowieso
    aus - das ist normal, kein Alarm. Der Unterschied (Sasha 2026-06-07): bei
    Routinen verpasst man Erwartbares, bei Einzelterminen etwas Besonderes, das
    man evtl. aktiv absagen/verschieben muss.

    Modell-Verhalten (Persona): bei so einem KONFLIKT vergewissert sich die KI
    einmal beim User (stimmt die Reise? stimmt der Termin?) und schlägt dann
    laut Alarm (Text + Bild-Marker [[bild: alarm]]) - statt blind oder stumm.
    Python liefert nur das Signal, die KI führt die Verifikation.

    Kein Konflikt, wenn der Termin am selben Ort wie das Reiseziel liegt
    (du hast vor Ort was geplant). Ort unbekannt → trotzdem flaggen: du bist
    verreist, lokale Termine sind dann höchst wahrscheinlich nicht machbar.
    """
    lines: list[str] = []
    for blk in away_blocks:
        if not (blk["von"] <= day <= blk["bis"]):
            continue
        for e in entries:
            if not e.get("time"):
                continue  # nur konkrete (zeitlich verortete) Termine
            if e.get("label") == blk["label"]:
                continue  # der Reise-Eintrag nicht gegen sich selbst
            if e.get("recurring"):
                continue  # Routine → fällt auf der Reise sowieso aus, kein Alarm
            appt_ort = e.get("ort")
            if blk["ort"] and appt_ort and appt_ort == blk["ort"]:
                continue  # gleicher Ort wie Reiseziel → kein Konflikt
            wd = _WEEKDAYS_FULL_DE[day.weekday()]
            ort_str = f" @ {appt_ort}" if appt_ort else ""
            # NUR Fakten - was die KI damit tun soll (rückversichern, Alarm),
            # steht in der read_calendar-Tool-Beschreibung, NICHT hier. Sonst
            # liest das Modell die Regie-Anweisung wörtlich vor.
            #
            # ANMERKUNG (2026-06-07): Versuch, diese Zeile parallel zur ABSAGEN-
            # Zeile auf „Termin X musst du verschieben oder absagen" umzubauen,
            # wurde GEMESSEN ZURÜCKGEROLLT - das „verschieben oder absagen" steht
            # in T1 mit im Kontext und ließ das 9B beim expliziten „lösch den"
            # zögern (T1-Löschquote 100 %→80 %), ohne die T2-Zuordnung zu heben
            # (bench_calendar_delete.py, N=20). Daher bewusst die nüchterne
            # „überschneidet sich"-Form behalten.
            lines.append(
                f"⚠ KONFLIKT: Reise {blk['label']} "
                f"({blk['von'].strftime('%d.%m.')}-{blk['bis'].strftime('%d.%m.')}, "
                f"{blk['ort'] or 'unterwegs'}) überschneidet sich mit Einzeltermin "
                f"'{e['label']}'{ort_str} am {wd} {day.strftime('%d.%m.')}."
            )
    return lines


def _absage_alarms(away_blocks: list[dict]) -> list[str]:
    """
    Findet Routinen, die in eine Reise-Spanne fallen UND aktiv abgesagt werden
    müssen (`absage_noetig`, z.B. Geige bei der Lehrerin). Liefert pro Reise und
    Routine GENAU EINE Alarm-Zeile - egal über wie viele Wochen die Reise geht
    (Sasha sagt einmal „bin von-bis weg", nicht jede Woche neu).

    Abgegrenzt von _conflict_lines (Einmal-Termine, die man verpasst): hier geht
    es um regelmäßige Termine mit Absage-PFLICHT - ein To-do, kein Verpassen.
    Normale Routinen ohne `absage_noetig` (Parkour, Fahrschule) erscheinen hier
    nicht; die fallen auf Reisen einfach weg.
    """
    lines: list[str] = []
    for blk in away_blocks:
        seen: set[str] = set()
        # entries_in_range liest selbst aus der Kalender-Datei und expandiert
        # die Routinen über die Reise-Spanne - so finden wir jedes Vorkommen.
        for day_iso, ents in entries_in_range(blk["von"], blk["bis"]).items():
            for e in ents:
                if not (e.get("recurring") and e.get("absage_noetig")):
                    continue
                if e.get("ausfall"):
                    continue  # fällt eh aus (Ferien) → nichts abzusagen
                if e.get("deaktiviert"):
                    continue  # vom User einzeln deaktiviert → kein Alarm
                if e["label"] in seen:
                    continue
                appt_ort = e.get("ort")
                if blk["ort"] and appt_ort and appt_ort == blk["ort"]:
                    continue  # findet am Reiseziel statt → kein Absagen nötig
                seen.add(e["label"])
                # Formulierung (Umbau 2026-06-07, gemessen): die alte Zeile
                # „Routine 'X' liegt in Reise Y - Pflicht-Absage" las das 9B als
                # Kollisions-Narrativ und klebte sie an einen anderen (oft schon
                # gelöschten) Termin → Alarm-Zuordnung nur 30 % (bench_calendar_
                # delete.py). Jetzt: AKTION + Subjekt nach vorn, der eigene
                # Wochentag des Vorkommens (unterscheidet die Routine vom
                # Einmal-Termin an einem anderen Tag), die Reise als GRUND nach
                # hinten. Immer noch reine Fakten an Sasha, keine Regie-Anweisung
                # ans Modell (die steht in der Tool-/Persona-Beschreibung).
                # Formulierung gemessen prod-treu (N=20, temp 0.7): diese Zeile vs.
                # die alte „Routine 'X' liegt in Reise Y - Pflicht-Absage" → T2-Alarm-
                # Zuordnung 100 % vs 80 %, Episode 85 % vs 60 % (memory/ki/bench_history.md P5).
                # Der Umbau trägt also echt, nicht nur ein temp-1-Artefakt.
                d  = date.fromisoformat(day_iso)
                wd = _WEEKDAYS_FULL_DE[d.weekday()]
                wo = f" (bei {appt_ort})" if appt_ort else ""
                lines.append(
                    f"⚠ {e['label']} absagen: dein wöchentlicher Termin am {wd} "
                    f"({d.strftime('%d.%m.')}) fällt in die Reise {blk['label']} "
                    f"({blk['von'].strftime('%d.%m.')}-"
                    f"{blk['bis'].strftime('%d.%m.')}) - du musst aktiv "
                    f"absagen{wo}, er entfällt nicht von selbst."
                )
    return lines


def render_range_for_tool(start: date, end: date,
                          layers: list[str] | None = None,
                          suche: str | None = None) -> str:
    """
    Formatiert die Einträge in [start, end] als Tool-Antwort für die KI.

    Kernpunkt gegen die Wochentag-Halluzination: jeder Tag kommt MIT
    ausgeschriebenem Wochentag ("Dienstag, 09.06.2026: …"). Vorher gab das
    Tool nackte ISO-Daten zurück und das Modell rechnete den Wochentag selbst
    aus - und verrechnete sich regelmäßig ("Montag" statt "Dienstag"). Steht
    der Wochentag fertig da, muss das Modell nur noch abschreiben.

    `suche`: optionaler Label-Substring-Filter (case-insensitive). Bei Fragen
    nach EINER Aktivität ("wann hab ich Fahrschule?") gibt das Tool damit nur
    die passenden Zeilen zurück, statt der ganzen Monatswand. Grund: schwache
    Modelle (qwen3-Familie) scheitern daran, eine lange Liste selbst nach
    einem Begriff zu durchsuchen - sie sagen dann "keine gefunden" obwohl der
    Eintrag dasteht, kotzen die Rohliste aus oder übersehen Treffer (z.B. den
    Donnerstag). Filtern ist deterministische Arbeit → macht Python, nicht das
    Modell. Selbes Prinzip wie resolve_range fürs Datums-Rechnen.

    Leerer Zeitraum → klare Ansage, damit die KI "nichts geplant" von
    "weiß ich nicht" unterscheiden kann.
    """
    days = entries_in_range(start, end, layers=layers)
    # Label-Filter in Python anwenden, BEVOR gerendert wird.
    if suche:
        needle = suche.casefold()
        days = {
            day_iso: matches
            for day_iso, entries in days.items()
            if (matches := [e for e in entries
                            if needle in e.get("label", "").casefold()])
        }
    span = (f"Kalender {start.strftime('%d.%m.%Y')} bis "
            f"{end.strftime('%d.%m.%Y')}")
    head = f"{span} (gefiltert nach {suche!r}):" if suche else f"{span}:"
    if not days:
        leer = (f"Keine Einträge mit {suche!r} in diesem Zeitraum."
                if suche else "Keine Einträge in diesem Zeitraum.")
        return head + "\n" + leer
    # Reine Arbeitsdaten: NUR die Terminliste. Die ⚠-Warnungen (Reise-KONFLIKT,
    # ABSAGEN, Tages-Kollision) sind hier BEWUSST RAUS - sie kaperten beim
    # kleinen Modell die Aufmerksamkeit (Löschen scheiterte, Add wurde blind).
    # Sie laufen jetzt über den Alarm-Kanal (open_alarms → state → Dashboard-Ecke
    # + ai._alarm_prompt), randständig statt zwischen die Termine gemischt. Die
    # KI darf den Kalender dadurch wieder frei lesen, ohne abgelenkt zu werden.
    lines = [head]
    for day_iso, entries in days.items():
        d = date.fromisoformat(day_iso)
        wd = _WEEKDAYS_FULL_DE[d.weekday()]
        lines.append(f"{wd}, {d.strftime('%d.%m.%Y')}:")
        for e in entries:
            # Fällt die Routine aus (Ferien/Feiertag)? Dann als Erinnerung
            # zeigen statt als normalen Termin - der User soll wissen, dass
            # NICHTS ist, nicht umsonst hinfahren.
            if e.get("ausfall"):
                lines.append(f"  ℹ {e['label']} fällt aus ({e['ausfall']}) "
                             f"- kein Termin an diesem Tag")
                continue
            if e.get("deaktiviert"):
                lines.append(f"  ℹ {e['label']} ist an diesem Tag deaktiviert "
                             f"- findet nicht statt")
                continue
            # Zeit MIT Ende anzeigen, wenn vorhanden ('17:45-18:30'),
            # sonst nur Startzeit - das Modell sieht so die Dauer direkt.
            if e.get("time") and e.get("ende"):
                t = f"{e['time']}-{e['ende']} "
            elif e.get("time"):
                t = f"{e['time']} "
            else:
                t = ""
            ort = f" @ {e['ort']}" if e.get("ort") else ""
            # Mehrtages-Block: Spanne sichtbar machen ('… (bis 12.06.)').
            bis = ""
            if e.get("bis"):
                try:
                    bis = f" (bis {date.fromisoformat(e['bis']).strftime('%d.%m.')})"
                except ValueError:
                    pass
            ebene = ("uncommitted · vielleicht" if e.get("layer") == UNVERBINDLICH
                     else e['layer'])
            lines.append(f"  [{ebene}] {t}{e['label']}{bis}{ort}")
        # (Keine ⚠-Warnzeilen mehr hier - die laufen über den Alarm-Kanal,
        #  siehe open_alarms. Der Read bleibt saubere Terminliste.)
    return "\n".join(lines)


# ── Imprint: was ansteht, ohne Tool-Runde ──────────────────────────────

IMPRINT_TAGE = int(os.environ.get("ZENTRALE_IMPRINT_TAGE", "1"))


def imprint_for_prompt(tage: int | None = None) -> str:
    """Der nahe Horizont, fest im Prompt: heute und morgen.

    Das ersetzt den gelöschten Kalender-Spiegel — und zwar in der richtigen
    Richtung. Der Spiegel wollte der KI den Tag präsent machen, indem er in
    den Kalender SCHRIEB; hier liest sie ihn einfach mit. Nichts wird
    verändert, also braucht es auch keine Erlaubnis.

    Warum überhaupt mitgeliefert, wo es doch `read_calendar` gibt: „was
    steht heute an" ist die häufigste Frage überhaupt, und jede Tool-Runde
    kostet einen kompletten zweiten Call mit vollem Präfix. Zwei Tage sind
    ein paar Zeilen — billiger als die Runde, die sie erspart.

    ── Achtung, das widerspricht einer alten Entscheidung ──
    2026-06 wurde der Kalender BEWUSST aus dem Prompt genommen (siehe die
    Notiz über `RANGE_BUCKETS`): Kleben skaliert nicht, und das damalige
    14B-Modell antwortete faul aus dem geklebten Block, statt für andere
    Zeiträume das Tool zu rufen. Beides gilt hier NICHT:
      * Geklebt wird nur der nahe Horizont, nicht „irgendein Zeitraum" —
        die Skalierungs-Sorge trifft genau das nicht.
      * Gegen die Faulheit steht der Schlusssatz des Blocks, der die Grenze
        ausdrücklich benennt. Bleibt er wirkungslos, gehört der Imprint
        wieder raus — das ist der Prüfstein.

    Sichtbarkeits-Regel: nur Layer, die auch Sasha sieht
    (`default_visible`). Die KI soll nichts wissen, was er nicht nachlesen
    kann — genau diese Asymmetrie hat der `erlebt`-Layer erzeugt.

    Warum am Ende eine Verhaltensregel steht (18.08.2026): weil der Block
    im gecachten Kopf sitzt und der Jetzt-Block die Uhr jede Runde neu
    setzt, rechnete sie bei JEDEM Turn nach, wie lange es noch hin ist —
    "in 16 Minuten", "noch 3 Minuten", obwohl Sasha den Termin laengst
    gesehen hatte. Der Alarm-Block (`ai._alarm_prompt`) hat gegen genau das
    seit jeher einen Satz ("EINMAL aktiv zur Sprache bringen, nicht in jede
    Antwort quetschen"); der Imprint hatte keinen. Das war die ganze
    Asymmetrie. Ein Assistent, der dreimal mahnt, wird abgeschaltet — das
    ist die eigentliche Gefahr proaktiver Schichten.

    Vorlaufzeiten (zwei Tage vor der Abreise ans Packen denken) gehören
    NICHT hierher, sondern in die Schemen-Mechanik: die kennt die Vorhaben
    und kann entscheiden, was wie früh sichtbar werden muss. `tage` ist der
    Hebel, an dem sie das später dreht.
    """
    tage = IMPRINT_TAGE if tage is None else tage
    if tage < 0:
        return ""
    heute = date.today()
    try:
        data = _load_raw()
    except Exception:
        return ""
    layers = [name for name, lyr in data.get("layers", {}).items()
              if lyr.get("default_visible", True)]
    liste = render_range_for_tool(heute, heute + timedelta(days=tage),
                                  layers=layers)
    grenze = ("Das ist NUR der nahe Horizont. Für jeden anderen Zeitraum "
              "(nächste Woche, ein bestimmtes Datum, 'wann war X') "
              "read_calendar rufen — aus diesem Block lässt sich das "
              "nicht beantworten.\n\n"
              "Und: das hier ist stehender Hintergrund, keine Meldung. Sasha "
              "sieht denselben Kalender vor sich. Einen Termin sagst du "
              "EINMAL an; hat er ihn zur Kenntnis genommen, ist das Thema "
              "durch — auch wenn die Uhrzeit näher rückt. Kein zweiter "
              "Hinweis, kein Countdown. Nur wenn er selbst etwas sagt, das "
              "damit kollidiert, sagst du es nochmal.\n\n"
              "[uncommitted · vielleicht] heißt: unverbindlich, noch nicht "
              "zugesagt. Erwähne es höchstens als Möglichkeit, plane nicht "
              "fest damit und warne nicht, wenn es mit etwas kollidiert.")
    return f"## Was ansteht\n{liste}\n\n{grenze}"


def conflicts_for_proposed(layer: str, day: str, label: str,
                           time: str | None = None, ende: str | None = None) -> list[str]:
    """
    Prüft einen NOCH NICHT geschriebenen Einmal-Termin HYPOTHETISCH auf Konflikte
    mit dem schon belegten Tag - ohne ihn zu speichern. Gedacht für die Erlaubnis-
    Frage (ai._permission_question): Sasha soll im JA/NEIN-Dialog schon sehen, ob
    der geplante Termin in eine Reise fällt (⚠ KONFLIKT) oder mit einem
    bestehenden Termin kollidiert (⚠ Kollision/Teil-Überlappung/Knapp) - BEVOR
    sie bestätigt, nicht erst hinterher als Tool-Ergebnis.

    Trick gegen die „Konflikt entsteht erst durchs Schreiben"-Henne-Ei-Falle: wir
    holen die echten Einträge des Tages (alle Layer), hängen den geplanten Termin
    als Phantom-Eintrag dran und lassen die GLEICHEN Konflikt-Funktionen laufen
    wie der Render-Pfad (day_warnings + _conflict_lines) - eine Logik, kein
    Doppel-Code. _absage_alarms (Geige-Pflichtabsage) bleibt bewusst außen vor:
    das ist ein Reise-To-do, kein Konflikt DIESES Termins, und wäre im Add-Dialog
    nur Rauschen.

    Hinweis: _conflict_lines flaggt nur Termine MIT Uhrzeit; ein ganztägiger
    Eintrag (kein `time`) löst also keine Reise-KONFLIKT-Zeile aus - dasselbe
    Verhalten wie im normalen read_calendar-Pfad, bewusst konsistent gehalten.

    Gibt [] bei ungültigem Datum ODER wenn der geplante Termin konfliktfrei ist.
    """
    try:
        d = date.fromisoformat((day or "").strip())
    except ValueError:
        return []
    if layer == UNVERBINDLICH:
        return []                         # Unverbindliches fragt nie nach
    existing = [e for e in entries_in_range(d, d).get(d.isoformat(), [])
                if _verbindlich(e)]   # deaktivierte und uncommitted zählen nicht mit
    phantom: dict = {"layer": (layer or "termine"),
                     "label": (label or "(neuer Termin)")}
    t = (time or "").strip()
    if t:
        phantom["time"] = t
        if (ende or "").strip():          # erst mit Ende ein Intervall (find_collisions)
            phantom["ende"] = ende.strip()
    entries = sorted(existing + [phantom], key=lambda e: e.get("time", "00:00"))
    away = _away_blocks(d, d)
    return day_warnings(entries) + _conflict_lines(d, entries, away)


def open_alarms(horizon_days: int = 30) -> list[dict]:
    """
    Berechnet das KOMPLETTE Set offener Kalender-Alarme von heute über den
    Horizont (Default 30 Tage) und liefert strukturierte Dicts. Das ist die
    EINE Quelle des Alarm-Kanals: kalender → state.set_alarms → (Dashboard-Ecke
    im KI-Canvas + ai._alarm_prompt "offene Erinnerungen"). Bewusst NICHT mehr
    inline in render_range_for_tool - dort kaperten die ⚠-Zeilen die
    Aufmerksamkeit des kleinen Modells (Löschen scheiterte, Add wurde blind).

    Sammelt aus den GLEICHEN Rechenfunktionen wie früher der Render-Pfad, damit
    die Konflikt-Logik an EINER Stelle bleibt (DRY):
      - _absage_alarms(away_blocks) → Pflicht-Absagen (Routine in Reise)
      - _conflict_lines(d, entries, away) → Einzeltermin in Reise
      - day_warnings(entries) → Tages-Kollision / Teil-Überlappung / Knapp

    Form je Alarm: {"id": <stabiler 8-Hex-Hash>, "kind": str, "text": str}.
    'text' ist die fertige Zeile OHNE führendes "⚠ " - jede Senke setzt ihr
    eigenes Symbol (Dreieck im Canvas, "- " im Prompt). 'id' ist stabil über
    Recomputes (md5 über kind+text), damit das Frontend nicht bei jedem Poll
    neu aufflackert. Reihenfolge: Reise-Absagen zuerst (vergisst man am
    leichtesten), dann tagesweise Konflikte + Kollisionen.
    """
    today = date.today()
    end   = today + timedelta(days=max(0, horizon_days))
    away_blocks = _away_blocks(today, end)

    raw: list[tuple] = []   # (kind, roh-Zeile, tag|None) in Anzeige-Reihenfolge
    for line in _absage_alarms(away_blocks):
        raw.append(("ABSAGEN", line, None))
    for day_iso, entries in entries_in_range(today, end).items():
        d = date.fromisoformat(day_iso)
        entries = [e for e in entries if _verbindlich(e)]  # deaktiviert/uncommitted: kein Alarm
        for line in _conflict_lines(d, entries, away_blocks):
            raw.append(("KONFLIKT", line, day_iso))
        for line in day_warnings(entries):
            # kind aus dem Zeilenkopf ableiten (Kollision/Teil-Überlappung/Knapp)
            kind = line.split(":", 1)[0].replace("⚠", "").strip() or "Warnung"
            raw.append((kind, line, day_iso))

    # "tag" (ISO) seit 09.10.2026, wo der Alarm an einem Tag hängt (Wunsch
    # der KI-Werkzeuge: Tages-Kollisionen kamen ohne Datum). Die id bleibt
    # wie sie war, damit schon weggeklickte Alarme nicht wieder auftauchen.
    alarms: list[dict] = []
    for kind, line, tag in raw:
        text = line.lstrip("⚠").strip()
        aid  = hashlib.md5(f"{kind}|{text}".encode("utf-8")).hexdigest()[:8]
        a = {"id": aid, "kind": kind, "text": text}
        if tag:
            a["tag"] = tag
        alarms.append(a)
    return alarms
