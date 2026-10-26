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
from datetime import date, datetime, timedelta

import kalender_deadline
import kalender_kategorie
import kalender_quelle
import kalender_rhythmus
import nutzer_angaben
import titel_wochentag
import uhr  # die eine Uhr (core/uhr.py)

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
# Tagesrhythmus (10.10.2026): Phasen sind gar kein Termin — Hintergrund.
RHYTHMUS = kalender_rhythmus.EBENE
NUR_HINWEIS = (UNVERBINDLICH, RHYTHMUS)


def _verbindlich(e: dict) -> bool:
    # Ausfall (16.10.2026): ein Vorkommen, das eine Pause wegnimmt
    # („Herbstferien"), findet nicht statt — es kann mit nichts kollidieren.
    return (e.get("layer") not in NUR_HINWEIS and not e.get("deaktiviert")
            and not e.get("ausfall"))


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
    if kalender_deadline.ist_deadline(e):
        return None      # Deadline (20.10.2026): ein Zeitpunkt, belegt keine Zeit
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
        if lname in NUR_HINWEIS:
            continue                     # Vielleicht-Reise/Phase macht nicht abwesend
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
            if kalender_deadline.ist_deadline(e):
                continue  # Deadline: man muss nicht hin, abgeben geht auch von unterwegs
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
                if e.get("layer") in NUR_HINWEIS:
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


def _ebene_text(e: dict) -> str:
    """Was in der Klammer vor einer Zeile steht: Ebene, bei Unverbindlichem
    „vielleicht", bei Phasen das Motiv, dahinter die Gruppe (wenn gesetzt):
    [termine] · [uncommitted · vielleicht] · [rhythmus · schlaf] · [termine · Uni]"""
    lname = e.get("layer")
    if lname == UNVERBINDLICH:
        teile = ["uncommitted · vielleicht"]
    elif lname == RHYTHMUS:
        teile = [RHYTHMUS] + ([e["motiv"]] if e.get("motiv") else [])
    else:
        teile = [str(lname)]
    if kalender_deadline.ist_deadline(e):
        # „[deadline]" statt „[termine]" (die Ebene termine ist der Normalfall)
        teile = (["deadline"] if lname == "termine" else teile + ["deadline"])
    gruppe = kalender_kategorie.anzeige(e)
    if gruppe:
        teile.append(gruppe)
    return " · ".join(teile)


def _deadline_rest(e: dict, day_iso: str, stunden: bool = True) -> str:
    """„ (in 2 Tagen)" hinter einer Deadline — ab der echten Uhr; mit
    Soll-Zeit „ (in 2 Tagen · Soll: Di 21.10. 18:00, Muss: Fr 24.10. 12:00)"."""
    if not kalender_deadline.ist_deadline(e):
        return ""
    rest = kalender_deadline.rest_text(e, day_iso, uhr.jetzt(), stunden)
    soll = kalender_deadline.soll_muss_text(e, day_iso)
    return f" ({rest} · {soll})" if soll else f" ({rest})"


def render_range_for_tool(start: date, end: date,
                          layers: list[str] | None = None,
                          suche: str | None = None, *, stunden: bool = True) -> str:
    """
    Formatiert die Einträge in [start, end] als Tool-Antwort für die KI.
    `stunden`: Deadlines heute mit „in 3 h" (der Imprint: ohne, s. dort).

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
                            if needle in e.get("label", "").casefold()
                            or needle in kalender_quelle.anzeige_titel(e).casefold()])
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
            if e.get("time") and e.get("ende") and e.get("ueber_nacht"):
                t = f"{e['time']}-{e['ende']} (bis Folgetag) "
            elif e.get("time") and e.get("ende"):
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
            # Titel aus Liste/Projekt: das oberste Item, dahinter dezent die
            # Liste — „10:00-12:00 Steuern planen (aus Liste: todo)".
            lines.append(f"  [{_ebene_text(e)}] {t}{kalender_quelle.anzeige_titel(e)}{bis}{ort}"
                         f"{_deadline_rest(e, day_iso, stunden)}")
        # (Keine ⚠-Warnzeilen mehr hier - die laufen über den Alarm-Kanal,
        #  siehe open_alarms. Der Read bleibt saubere Terminliste.)
    return "\n".join(lines)


# ── Imprint: was ansteht, ohne Tool-Runde ──────────────────────────────

IMPRINT_TAGE = int(os.environ.get("ZENTRALE_IMPRINT_TAGE", "1"))


# Der Grenz-Text unter dem Imprint (Begründung: imprint_for_prompt).
# {nur}/{einmal}/{kein} sind die Hervorhebungen — betont (klein) in
# Großbuchstaben, sonst klein geschrieben; {nutzer}, {er} … füllt
# nutzer_angaben.
_IMPRINT_BETONT = {"{nur}": "NUR", "{einmal}": "EINMAL", "{kein}": "KEIN"}
_IMPRINT_GRENZE = (
    "Das ist {nur} der nahe Horizont. Für jeden anderen Zeitraum "
    "(nächste Woche, ein bestimmtes Datum, 'wann war X') "
    "read_calendar rufen — aus diesem Block lässt sich das "
    "nicht beantworten.\n\n"
    "Und: das hier ist stehender Hintergrund, keine Meldung. {nutzer} "
    "sieht denselben Kalender vor sich. Einen Termin sagst du "
    "{einmal} an; hat {er} ihn zur Kenntnis genommen, ist das Thema "
    "durch — auch wenn die Uhrzeit näher rückt. Kein zweiter "
    "Hinweis, kein Countdown. Nur wenn {er} selbst etwas sagt, das "
    "damit kollidiert, sagst du es nochmal.\n\n"
    "[uncommitted · vielleicht] heißt: unverbindlich, noch nicht "
    "zugesagt. Erwähne es höchstens als Möglichkeit, plane nicht "
    "fest damit und warne nicht, wenn es mit etwas kollidiert.\n\n"
    "[rhythmus · <motiv>] ist {nutzers} Tagesrhythmus (wann {er} meist "
    "schläft, isst, runterkommt …) — {kein} Termin. Stiller "
    "Hintergrund: nicht ansagen, nicht warnen, nie als belegt "
    "zählen; nur nutzen, um besser einzuschätzen (z. B. nichts "
    "ungefragt in die Schlafzeit legen). Er ist variabel und darf "
    "geändert werden, wenn {nutzer} es sagt.")
_IMPRINT_LISTE = (
    "\n\n„… (aus Liste: X)“ bzw. „(aus Projekt: X)“: ein "
    "Zeitfenster, das {nutzer} für diese Liste reserviert hat. Der "
    "Titel davor ist der Punkt, der dort gerade oben steht — er "
    "wechselt von selbst, wenn {nutzer} umsortiert oder abhakt. Es "
    "ist ein normaler Termin (belegt).")
_IMPRINT_DEADLINE = (
    "\n\n[deadline] ist ein Zeitpunkt (Abgabe, Frist), keine belegte Zeit: "
    "{er} muss bis dahin fertig sein, nicht dort sein. Kollidiert nie. In "
    "der Klammer steht, wie lange es noch hin ist (bis zur Muss-Zeit). "
    "Steht dort „Soll: …, Muss: …\", ist Soll {seine} eigene frühere "
    "Wunsch-Abgabe, Muss die harte Frist — nenne beide, rechne mit Muss.")


def imprint_for_prompt(tage: int | None = None, *, betont: bool = True) -> str:
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

    `betont` (2026-10-14): die Schiene klein bekommt die Hervorhebungen in
    Großbuchstaben (NUR, EINMAL, KEIN) — so ist das qwen gemessen. Die
    Schiene gross bekommt dieselben Wörter klein geschrieben: Anthropic
    rät von Großbuchstaben-Befehlen ab, aktuelle Modelle befolgen sie zu
    eifrig. Der Nutzer steht als Platzhalter drin (core/nutzer_angaben.py);
    mit den Standardwerten ist der Text byte-gleich wie vorher.
    """
    tage = IMPRINT_TAGE if tage is None else tage
    if tage < 0:
        return ""
    heute = uhr.heute()
    try:
        data = _load_raw()
    except Exception:
        return ""
    layers = [name for name, lyr in data.get("layers", {}).items()
              if lyr.get("default_visible", True)]
    liste = render_range_for_tool(heute, heute + timedelta(days=tage),
                                  layers=layers, stunden=False)
    grenze = _IMPRINT_GRENZE
    if "(aus Liste: " in liste or "(aus Projekt: " in liste:
        grenze += _IMPRINT_LISTE
    if "[deadline" in liste or " · deadline" in liste:
        grenze += _IMPRINT_DEADLINE
    for platzhalter, wort in _IMPRINT_BETONT.items():
        grenze = grenze.replace(platzhalter, wort if betont else wort.lower())
    grenze = nutzer_angaben.einsetzen(grenze)
    return f"## Was ansteht\n{liste}\n\n{grenze}"


# ── Jetzt und als Nächstes (26.10.2026) ────────────────────────────────
# Sasha: schreibt er „meow", soll sie nichts nachschlagen müssen, sondern im
# Blick haben, was laut Kalender gerade läuft und als Nächstes kommt — und
# höchstens sanft fragen („fertig mit Analysis?"). Der Imprint („Was
# ansteht") weiß das nicht: er steht im gecachten Kopf und kennt die Uhr
# nicht. Dieser Abschnitt steht deshalb im wechselnden Teil (cloud.
# _volatile_text, nur gross) und liest dieselben Einträge wie der Imprint
# (entries_in_range, sichtbare Ebenen, anzeige_titel) und dieselben
# Deadline-Zeilen wie der Alarm-Kanal (_deadline_zeilen) — dasselbe Objekt,
# nicht kopiert. Keine Minuten, kein „in 20 min": nur Uhrzeiten (der
# Countdown-Befund vom 18.08., siehe ki_prompt._now_prompt).
# Leitbild: Szene „Bei ihr einchecken"; KI-Bibel P-06, KT-07.

JETZT_NAECHSTE = 3          # wie viele kommende Termine höchstens
JETZT_DEADLINE_TAGE = 30    # Horizont für Deadlines, wie open_alarms

_JETZT_UMGANG = (
    "Das ist aus dem Kalender gelesen, dafür brauchst du kein Werkzeug. Du hast "
    "es im Blick und sagst es nicht auf. Passt es ins Gespräch, fragst du "
    "höchstens sanft nach (etwa „fertig mit …?“). Ob {er} etwas erledigt hat, "
    "weißt du nicht — nimm es nicht an.")
_JETZT_LAEUFT = "- Laut Kalender läuft gerade: {was}. Ob {er} dabei ist, weißt du nicht."


def _deadline_zeilen(day_iso: str, entries: list, jetzt) -> list[str]:
    """Die Deadlines eines Tages, deren Vorwarn-Fenster offen ist, als
    fertige Zeile („Deadline Analysis HÜ morgen (Di 27.10. 23:59)").
    Eine Quelle für den Alarm-Kanal und für „Jetzt und als Nächstes"."""
    return [kalender_deadline.alarm_text(e, day_iso, jetzt) for e in entries
            if kalender_deadline.ist_deadline(e)
            and kalender_deadline.im_fenster(e, day_iso, jetzt)]


def _um(tag: date, minuten: int) -> datetime:
    return datetime.combine(tag, datetime.min.time()) + timedelta(minutes=minuten)


def _spanne(e: dict, tag: date):
    """(beginn, ende) als datetime eines Eintrags mit Uhrzeit und Ende, oder
    None. Endet er vor dem Beginn (Schlaf 23:00–07:00), endet er am Folgetag."""
    b, z = _to_minutes(e.get("time") or ""), _to_minutes(e.get("ende") or "")
    if b is None or z is None:
        return None
    beginn = _um(tag, b)
    ende = _um(tag, z) + timedelta(days=1 if z <= b else 0)
    return beginn, ende


def _wann_kurz(zp, jetzt) -> str:
    """„22:00" heute, sonst „morgen 22:00" — nie Minuten bis dahin."""
    tage = (zp.date() - jetzt.date()).days
    vorn = {0: "", 1: "morgen "}.get(tage, zp.strftime("%d.%m. "))
    return vorn + zp.strftime("%H:%M")


def jetzt_und_naechstes(jetzt=None) -> str:
    """Der Abschnitt „## Jetzt und als Nächstes" für den wechselnden Teil.

    - was laut Kalender gerade läuft (bis wann), Termin und Tagesrhythmus
      getrennt — der Rhythmus ist kein Termin;
    - die nächsten Termine heute/morgen (höchstens JETZT_NAECHSTE);
    - Deadlines in ihrem Vorwarn-Fenster.
    Vorbereitung steht nicht da: dafür gibt es keine Daten, und erfunden
    wird nichts. Nichts davon → "" (kein Abschnitt)."""
    jetzt = jetzt or uhr.jetzt()
    heute = jetzt.date()
    try:
        data = _load_raw()
    except Exception:
        return ""
    sichtbar = [n for n, lyr in data.get("layers", {}).items()
                if lyr.get("default_visible", True)]
    tage = entries_in_range(heute - timedelta(days=1), heute + timedelta(days=1),
                            layers=sichtbar)
    laeuft, rhythmus, kommt = [], [], []
    for iso in sorted(tage):
        tag = date.fromisoformat(iso)
        for e in tage[iso]:
            if e.get("deaktiviert") or e.get("ausfall") or kalender_deadline.ist_deadline(e):
                continue
            titel = kalender_quelle.anzeige_titel(e)
            if e.get("layer") == UNVERBINDLICH:
                titel += " (vielleicht)"
            sp = _spanne(e, tag)
            if sp and sp[0] <= jetzt < sp[1]:
                bis = f"bis {_wann_kurz(sp[1], jetzt)}"
                (rhythmus if e.get("layer") == RHYTHMUS else laeuft).append(f"{titel} ({bis})")
                continue
            if e.get("layer") == RHYTHMUS or tag < heute:
                continue
            b = _to_minutes(e.get("time") or "")
            if b is None:
                continue          # ganztags: kein „als Nächstes"
            beginn = _um(tag, b)
            if beginn > jetzt:
                kommt.append((beginn, f"{_wann_kurz(beginn, jetzt)} {titel}"))
    kommt = [t for _, t in sorted(kommt, key=lambda x: x[0])][:JETZT_NAECHSTE]

    # Deadlines über alle Ebenen, wie open_alarms — dieselben Zeilen wie
    # dort (auf gross stehen sie deshalb nur noch hier, ki_prompt._alarm_gross).
    fristen = []
    try:
        horizont = entries_in_range(heute, heute + timedelta(days=JETZT_DEADLINE_TAGE))
    except Exception:
        horizont = {}
    for iso, es in horizont.items():
        fristen += _deadline_zeilen(iso, [e for e in es if _verbindlich(e)], jetzt)

    if not (laeuft or rhythmus or kommt or fristen):
        return ""
    z = ["## Jetzt und als Nächstes"]
    if laeuft:
        z.append(nutzer_angaben.einsetzen(_JETZT_LAEUFT).replace("{was}", "; ".join(laeuft)))
    else:
        z.append("- Laut Kalender läuft gerade kein Termin.")
    if rhythmus:
        z.append("- Tagesrhythmus gerade (kein Termin, nicht ansagen): "
                 + "; ".join(rhythmus) + ".")
    if kommt:
        z.append("- Als Nächstes: " + " · ".join(kommt) + ".")
    for f in fristen:
        z.append(f"- {f}.")
    z.append(nutzer_angaben.einsetzen(_JETZT_UMGANG))
    return "\n".join(z)


def conflicts_for_proposed(layer: str, day: str, label: str,
                           time: str | None = None, ende: str | None = None,
                           ausser: str | None = None) -> list[str]:
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

    `ausser` (19.10.2026): Kennung des Eintrags, der gerade BEARBEITET wird —
    er fällt aus den vorhandenen Einträgen raus, sonst kollidiert die neue
    Fassung mit der alten, also mit sich selbst (Sasha: „überlappt komplett
    mit demselben Termin"). Bei einer Routine tragen alle Vorkommen dieselbe
    Kennung; gelesen wird nur `day`, also fällt genau das Vorkommen dort raus.

    Gibt [] bei ungültigem Datum ODER wenn der geplante Termin konfliktfrei ist.
    """
    try:
        d = date.fromisoformat((day or "").strip())
    except ValueError:
        return []
    if layer in NUR_HINWEIS:
        return []                         # Unverbindliches/Phasen fragen nie nach
    existing = [e for e in entries_in_range(d, d).get(d.isoformat(), [])
                if _verbindlich(e)    # deaktiviert, uncommitted, Ausfall zählen nicht mit
                and not (ausser and e.get("kennung") == ausser)]   # nicht mit sich selbst
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


# Titel nennt einen falschen Wochentag (22.10.2026, Wunsch der KI-Session):
# qwen hatte „Sprechstunde Jonas Schömer (Mo)" als Serie mit BYDAY=WE
# gespeichert. Die Adapter-Prüfung (K-TITEL-WOCHENTAG) fängt das künftig beim
# Speichern; dieser Alarm findet, was schon im Kalender steht. Geprüft wird
# jeder Eintrag, der im Alarm-Horizont vorkommt — auch uncommitted, Ausfall
# und Deadlines (der Titel ist trotzdem falsch), nicht Phasen und nicht
# mehrtägige Spannen. Höchstens EIN Alarm je Eintrag, nicht je Vorkommen.
_TAG_NAME = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
             "Samstag", "Sonntag")


def _tage_text(tage, adverb: bool = False) -> str:
    namen = [_TAG_NAME[t].lower() + "s" if adverb else _TAG_NAME[t] for t in sorted(tage)]
    return namen[0] if len(namen) == 1 else ", ".join(namen[:-1]) + " und " + namen[-1]


def _wochentag_alarme(im_horizont: dict) -> list[tuple]:
    raus: list[tuple] = []
    gesehen: set = set()
    for day_iso, entries in im_horizont.items():
        d = date.fromisoformat(day_iso)
        for e in entries:
            if e.get("layer") == RHYTHMUS or e.get("spanning"):
                continue
            label = e.get("label") or ""
            if e.get("recurring"):
                schluessel = e.get("kennung") or (e.get("layer"), label, e.get("rrule"))
                # Erstes Vorkommen als Start: legt bei FREQ=WEEKLY ohne BYDAY
                # den Wochentag fest (wie DTSTART der Serie).
                tage = titel_wochentag.aus_regel(e.get("rrule"), d)
            else:
                schluessel = e.get("kennung") or (e.get("layer"), day_iso, label, e.get("time"))
                tage = {d.weekday()}
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            if not titel_wochentag.widerspruch(label, tage):
                continue
            falsch = titel_wochentag.im_titel(label) - set(tage)
            if e.get("recurring"):
                text = (f"Titel nennt {_tage_text(falsch)}, die Serie läuft "
                        f"{_tage_text(tage, adverb=True)}: {label}")
                raus.append(("Wochentag", text, None))
            else:
                text = (f"Titel nennt {_tage_text(falsch)}, der Termin ist am "
                        f"{_TAG_NAME[d.weekday()]}, {d.strftime('%d.%m.')}: {label}")
                raus.append(("Wochentag", text, day_iso))
    return raus


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
    today = uhr.heute()
    end   = today + timedelta(days=max(0, horizon_days))
    away_blocks = _away_blocks(today, end)

    raw: list[tuple] = []   # (kind, roh-Zeile, tag|None) in Anzeige-Reihenfolge
    for line in _absage_alarms(away_blocks):
        raw.append(("ABSAGEN", line, None))
    jetzt = uhr.jetzt()
    im_horizont = entries_in_range(today, end)
    for day_iso, entries in im_horizont.items():
        d = date.fromisoformat(day_iso)
        entries = [e for e in entries if _verbindlich(e)]  # deaktiviert/uncommitted/Ausfall: kein Alarm
        # Deadline im Vorwarn-Fenster (20.10.2026): EIN Hinweis, dessen Text
        # sich höchstens einmal am Tag ändert („in 2 Tagen" → „morgen").
        for text in _deadline_zeilen(day_iso, entries, jetzt):
            raw.append(("Deadline", text, day_iso))
        for line in _conflict_lines(d, entries, away_blocks):
            raw.append(("KONFLIKT", line, day_iso))
        for line in day_warnings(entries):
            # kind aus dem Zeilenkopf ableiten (Kollision/Teil-Überlappung/Knapp)
            kind = line.split(":", 1)[0].replace("⚠", "").strip() or "Warnung"
            raw.append((kind, line, day_iso))
    raw.extend(_wochentag_alarme(im_horizont))

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
