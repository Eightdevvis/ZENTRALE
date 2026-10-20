# core/werkzeug_kalender.py
#
# Der eigene Kalender als ERSTE Quelle des Werkzeug-Erzeugers
# (core/werkzeug_erzeuger/, Plan: memory/hub/hub_bauplan.md „KI-Werkzeuge
# aus dem Schema erzeugen"). Hier stehen nur die Aktions-Schemas (MCP-Form:
# name, description, inputSchema, annotations, x-zentrale); was eine Aktion
# TUT, steht im Adapter (core/ki_kalender_adapter.py).
#
# Entscheidungen 2026-10-10:
#   - Namen der bisherigen Werkzeuge bleiben (add_calendar_entry,
#     edit_calendar_routine …): Prompts, Skills und Prüfstand-Fälle passen
#     weiter. Ihre klein-Felder stehen unverändert drin (tests/test_profil.py:
#     gross darf nur ergänzen).
#   - Phasen, Gruppe, Ebene als EIGENE Werkzeuge, nicht als Felder an den
#     bestehenden: ein schwaches Modell sieht am Namen, was geht
#     (set_calendar_group statt „kategorie irgendwo in edit_…"), und eine
#     Phase braucht andere Pflichtfelder als eine Routine (motiv, Beginn; kein
#     Zeitraum-Zwang, über Mitternacht erlaubt).
#   - Gruppe beim Anlegen PFLICHT (Sasha: im Normalfall „keine"; eine Gruppe
#     nur für Einträge, die im Monat als Block zusammengefasst werden). Pflicht
#     heißt: das Modell muss sich entscheiden, statt sie zu vergessen.
#   - Beschreibungen knapp (Deckel in tests/test_profil.py); die Erklärungen
#     stehen in den Feldern.
#
# Kataloge (Gruppen, Motive) sind feste Konstanten des Kalender-Kerns — das
# Schema bleibt pro Prozess gleich (Prompt-Cache).
#
# KI-Kern (Schicht 3, memory/system/bauplan_kern.md).

import kalender_kategorie
import kalender_kennung
import kalender_quelle
import kalender_rhythmus
import ki_kalender_adapter
import stil
import werkzeug_erzeuger

X = "x-zentrale"


def _s(beschreibung: str, **x) -> dict:
    """Ein Text-Feld; x = unsere Verwaltung (Kopf von werkzeug_erzeuger/schema.py)."""
    feld = {"type": "string", "description": beschreibung}
    if x:
        feld[X] = x
    return feld


_DATUM = "YYYY-MM-DD"
_KENNUNG = _s("Kennung aus read_calendar, z.B. '#r3f9c'.", ziel=True)
_KENNUNG_PFLICHT = _s("Kennung aus read_calendar, z.B. '#r3f9c'.", ziel=True,
                      fehlt="PFLICHTFELD")

_GRUPPEN = list(kalender_kategorie.KATEGORIEN) + [kalender_kategorie.KEINE,
                                                    kalender_kategorie.CUSTOM]
_GRUPPE = {
    "type": "string", "enum": _GRUPPEN,
    "description": ("Gruppe. Im Normalfall 'keine'. 'uni'/'arbeit' NUR für Einträge, die in "
                    "der Monatsansicht zu einem Block zusammengefasst werden (Uni-"
                    "Veranstaltung, Arbeitsschicht); 'custom' + kategorie_name für einen "
                    "eigenen Namen."),
    X: {"wort": "Gruppe", "ungueltig": "KATEGORIE-UNBEKANNT"},
}
_GRUPPE_NAME = _s("Nur bei kategorie 'custom': der eigene Name der Gruppe.",
                  wort="Gruppenname", schwach=False)
_QUELLE_ART = {"type": "string", "enum": list(kalender_quelle.ARTEN),
               "description": ("Optional: der Titel kommt live aus einer Liste ('liste') oder "
                               "einem Projekt ('projekt') — angezeigt wird ihr oberster offener "
                               "Punkt. Mit quelle_id; die Auswahl liefert read_calendar_sources."),
               X: {"wort": "aus", "ungueltig": "QUELLE-ART-UNBEKANNT"}}
_QUELLE_ID = _s("id aus read_calendar_sources (nie raten).", wort="Quelle")
_ENDE = _s("Ende HH:MM (24h), wenn bekannt.")
_ORT = _s("Ort, wenn bekannt.")
_ZEITRAUM_VON = _s(f"{_DATUM}: erster Tag der Serie (z. B. Semesteranfang).", fehlt="ZEITRAUM-FEHLT")
_ZEITRAUM_BIS = _s(f"{_DATUM}: letzter Tag der Serie. Das Ende nur hier, nie UNTIL/COUNT in "
                   "der rrule. Unbekannt? Sasha fragen, nie ‚für immer' annehmen.",
                   fehlt="ZEITRAUM-FEHLT")
_RRULE = _s("iCal RRULE ohne DTSTART und ohne Ende, z.B. 'FREQ=WEEKLY;BYDAY=TU' | "
            "'FREQ=WEEKLY;BYDAY=MO,WE,FR' | 'FREQ=MONTHLY;BYMONTHDAY=1' | "
            "'FREQ=MONTHLY;BYDAY=2TU' (2. Dienstag im Monat).")
_NUR_AM = _s(f"{_DATUM}: nur dieses eine Datum ändern (bzw. bei 'loeschen' absagen).")
_NUR_VON = _s(f"{_DATUM}: erster Tag, an dem die Änderung gilt (mit nur_bis; nur diese "
              "Tage, höchstens 366). Die Serie bleibt sonst, wie sie ist.")
_NUR_BIS = _s(f"{_DATUM}: letzter Tag, an dem die Änderung gilt (mit nur_von).")
# Termintyp deadline (2026-10-20, Kern: core/kalender_deadline.py). Die
# Erklärung steht in den Feldern — der Werkzeug-Text zählt gegen den
# Kalender-Deckel (tests/test_profil.py), die Felder nicht.
_TYP_NEU = {"type": "string", "enum": ["normal", "deadline"],
            "description": ("'deadline' für eine Frist oder Abgabe: ein Zeitpunkt, keine belegte "
                            "Zeit; leuchtet vorher rot und erinnert. Braucht time (nennt Sasha "
                            "keine Uhrzeit, 23:59 vorschlagen), hat kein ende. Sonst weglassen."),
            X: {"wort": "Typ", "ungueltig": "TYP-UNBEKANNT"}}
_TYP_AENDERN = {**_TYP_NEU,
                "description": ("'deadline' macht daraus eine Frist (Zeitpunkt zu time; ein "
                                "bisheriges Ende fällt weg), 'normal' wieder einen gewöhnlichen "
                                "Termin ohne Vorwarnung.")}
_VORWARNUNG = _s("Nur bei deadline: wie lange vorher sie rot leuchtet und erinnert, z. B. "
                 "'3d', '12h', '1d12h' (Standard 3d, höchstens 366d).",
                 wort="Vorwarnung", ungueltig="VORWARNUNG-UNGUELTIG")


def _aktion(name, beschreibung, felder, pflicht=(), **x) -> dict:
    return {"name": name, "description": beschreibung,
            "inputSchema": {"type": "object", "properties": felder,
                            "required": list(pflicht)},
            "annotations": {"readOnlyHint": False,
                            "destructiveHint": x.get("art") == "loeschen"},
            X: x}


AKTIONEN = [
    # ── die bisherigen (Namen und klein-Felder bleiben) ──
    _aktion(
        "add_calendar_entry",
        "Trägt einen Einmal-Termin oder eine Frist (typ deadline) ein. Ende und Ort "
        "mitgeben, wenn bekannt — fehlt das Ende, wird keins angenommen; nenn dann auch keins.",
        {
            "layer": _s("Ebene: 'termine' (Standard, fest zugesagt) oder 'uncommitted' "
                        "(vielleicht).", schwach=False),
            "day": _s(_DATUM),
            "label": _s("Kurzer Titel, ohne Ort (mit quelle: Rückfall-Titel, darf fehlen)"),
            "time": _s("Optional HH:MM (24h). Weglassen wenn ganztags."),
            "ende": _ENDE, "ort": _ORT,
            "kategorie": _GRUPPE, "kategorie_name": _GRUPPE_NAME,
            "quelle_art": _QUELLE_ART, "quelle_id": _QUELLE_ID,
            "typ": _TYP_NEU, "vorwarnung": _VORWARNUNG,
        },
        pflicht=("day", "kategorie"),
        art="anlegen", alltag="termine eintragen", worte=("Termin eingetragen", "Termin eintragen"),
        immer_erlaubbar=True,
        beweis="liest den Termin per Kennung nach: Tag, Zeit, Ende, Ort, Gruppe",
        einfach="Trägt EINEN Termin ein. Ende nur, wenn Sasha es nennt.",
    ),
    _aktion(
        "add_calendar_routine",
        "Trägt eine Wiederholung (Routine) mit Zeitraum von/bis ein. Fehlt das Ende der "
        "Uhrzeit, wird keins angenommen — frag nach, statt eins zu nennen.",
        {
            "layer": _s("Ebene, im Zweifel weglassen (termine).", schwach=False),
            "label": _s("Kurzer Titel, ohne Ort (mit quelle: Rückfall-Titel, darf fehlen)"),
            "rrule": _RRULE,
            "time": _s("Optional HH:MM (24h)"),
            "ende": _ENDE, "ort": _ORT,
            "von": _ZEITRAUM_VON, "bis": _ZEITRAUM_BIS,
            "kategorie": _GRUPPE, "kategorie_name": _GRUPPE_NAME,
            "quelle_art": _QUELLE_ART, "quelle_id": _QUELLE_ID,
            "typ": _TYP_NEU, "vorwarnung": _VORWARNUNG,
        },
        pflicht=("rrule", "von", "bis", "kategorie"),
        art="anlegen", alltag="routinen eintragen",
        worte=("Routine eingetragen", "Routine eintragen"), immer_erlaubbar=True,
        beweis="liest die Routine per Kennung nach, mit ihrem nächsten Termin",
    ),
    _aktion(
        "edit_calendar_routine",
        "Ändert oder löscht EINE Routine per kennung aus read_calendar. Nur genannte Felder "
        "ändern sich — nie löschen und neu anlegen, nie add_calendar_routine dafür. Einzelne "
        "Tage: nur_am oder nur_von/nur_bis.",
        {
            "kennung": _KENNUNG,
            "label": _s("Ohne kennung: Titel der Routine (nur bei genau einem Treffer)"),
            "aktion": {"type": "string", "enum": ["aendern", "loeschen"],
                       "description": "'aendern' oder 'loeschen'",
                       X: {"ungueltig": "AKTION-UNGUELTIG", "fehlt": "AKTION-UNGUELTIG"}},
            "time": _s("Neue Uhrzeit HH:MM (24h)"),
            "ende": _s("Neues Ende HH:MM (24h)"),
            "rrule": _s("Neue Wiederholung, z.B. 'FREQ=WEEKLY;BYDAY=MO' (ohne Ende)"),
            "ort": _s("Neuer Ort"),
            "neuer_titel": _s("Neuer Titel, falls die Aktivität anders heißt"),
            "nur_am": _NUR_AM, "nur_von": _NUR_VON, "nur_bis": _NUR_BIS,
            "von": _s(f"{_DATUM}: neuer erster Tag der ganzen Serie. Nur mitgeben, wenn sich "
                      "der Zeitraum der Serie ändern soll."),
            "bis": _s(f"{_DATUM}: neuer letzter Tag der ganzen Serie (begrenzt auch Serien "
                      "„ohne Enddatum“). Nur mitgeben, wenn sich der Zeitraum ändern soll."),
            "typ": _TYP_AENDERN, "vorwarnung": _VORWARNUNG,
        },
        pflicht=("aktion",),
        art="aendern", alltag="routinen ändern", worte=("Routine geändert", "Routine ändern"),
        beweis="liest die Routine (bzw. die Tage) per Kennung nach",
    ),
    _aktion(
        "add_calendar_pause",
        "Pause für eine Routine (Ferien, Ausfall): in dem Zeitraum findet sie nicht statt. "
        "Ende unbekannt: bis weglassen — dann fällt nur der Tag von aus; frag nach dem Ende.",
        {
            "kennung": _KENNUNG,
            "label": _s("Ohne kennung: GENAUER Titel der Routine (wie im Kalender)"),
            "von": _s(f"Start der Pause, {_DATUM} (inkl.)", fehlt="PFLICHTFELD"),
            "bis": _s(f"Ende der Pause, {_DATUM} (inkl.)"),
            "grund": _s("Optional kurzer Grund, z.B. 'Sommerferien', 'Feiertag'"),
        },
        pflicht=("von",),
        art="aendern", nichts="nichts eingetragen", immer_erlaubbar=True,
        alltag="routinen pausieren", worte=("Pause eingetragen", "Pause eintragen"),
        beweis="liest die Routine nach und nennt, welche Termine ausfallen",
    ),
    _aktion(
        "delete_calendar_entry",
        "Löscht EINEN Einzeltermin per kennung (mehrtägige ganz). Routinen: "
        "edit_calendar_routine, Phasen: delete_calendar_phase.",
        {
            "kennung": _KENNUNG,
            "day": _s(f"Ohne kennung: {_DATUM} des Termins"),
            "label": _s("Ohne kennung: Titel des Termins (nur bei genau einem Treffer)"),
            "layer": _s("Optional Ebene; weglassen = in allen suchen", schwach=False),
        },
        art="loeschen", alltag="termine löschen", worte=("gelöscht", "Löschen"),
        beweis="liest per Kennung nach: der Termin ist weg",
    ),
    _aktion(
        "edit_calendar_entry",
        "Ändert EINEN Einzeltermin per kennung; nur die genannten Felder ändern sich.",
        {
            "kennung": _KENNUNG,
            "day": _s(f"Ohne kennung: bisheriger Tag {_DATUM}."),
            "label": _s("Ohne kennung: bisheriger Titel (nur bei genau einem Treffer)."),
            "neuer_tag": _s(_DATUM),
            "time": _s("Neuer Beginn HH:MM"),
            "ende": _s("Neues Ende HH:MM"),
            "ort": _s("Neuer Ort"),
            "neuer_titel": _s("Neuer Titel"),
            "bis": _s(f"Nur mehrtägig: neuer letzter Tag {_DATUM}"),
            "typ": _TYP_AENDERN, "vorwarnung": _VORWARNUNG,
        },
        art="aendern", alltag="termine ändern", worte=("Termin geändert", "Termin ändern"),
        beweis="liest den Termin per Kennung nach: Tag, Zeit, Ende, Ort",
    ),
    # ── neu 2026-10-10: Tagesrhythmus, Gruppe, Ebene ──
    _aktion(
        "set_calendar_phase",
        "Trägt eine Phase des Tagesrhythmus ein (Schlaf, Essen, Fokus …): kein Termin, nur "
        "Hintergrund. Über Mitternacht erlaubt.",
        {
            "label": _s("Titel, z.B. 'Schlaf'", fehlt="TITEL-LEER", wort="Titel"),
            "motiv": {"type": "string", "enum": list(kalender_rhythmus.MOTIVE),
                      "description": "Art der Phase: " + ", ".join(
                          f"{k} ({v['was']})" for k, v in kalender_rhythmus.MOTIVE.items()),
                      X: {"wort": "Art", "ungueltig": "MOTIV-UNBEKANNT"}},
            "time": _s("Beginn HH:MM (24h)", fehlt="PHASE-OHNE-ZEIT", wort="Beginn"),
            "ende": _s("Ende HH:MM; vor dem Beginn = am Folgetag (Schlaf 23:00–07:00).",
                       wort="Ende"),
            "rrule": _s("Wiederholung, Standard täglich (FREQ=DAILY); ohne Ende.",
                        wort="Wiederholung", schwach=False),
            "von": _s(f"{_DATUM}: erster Tag, Standard heute.", wort="ab"),
            "bis": _s(f"{_DATUM}: letzter Tag; weglassen = bis auf Weiteres.", wort="bis"),
        },
        pflicht=("label", "motiv", "time"),
        art="anlegen", alltag="tagesrhythmus eintragen", frage="die Phase eintragen",
        worte=("Phase eingetragen", "Phase eintragen"), immer_erlaubbar=True,
        einfach="Trägt eine Phase des Tagesrhythmus ein (z.B. Schlaf 23:00–07:00). Kein Termin.",
    ),
    _aktion(
        "edit_calendar_phase",
        "Ändert EINE Phase per kennung: ab jetzt, oder nur einzelne Tage (nur_am, "
        "nur_von/nur_bis).",
        {
            "kennung": _KENNUNG_PFLICHT,
            "time": _s("Neuer Beginn HH:MM", wort="Beginn"),
            "ende": _s("Neues Ende HH:MM; vor dem Beginn = am Folgetag.", wort="Ende"),
            "neuer_titel": _s("Neuer Titel", wort="Titel"),
            "motiv": {"type": "string", "enum": list(kalender_rhythmus.MOTIVE),
                      "description": "Neue Art der Phase.",
                      X: {"wort": "Art", "ungueltig": "MOTIV-UNBEKANNT", "schwach": False}},
            "rrule": _s("Neue Wiederholung (ohne Ende).", wort="Wiederholung", schwach=False),
            "von": _s(f"{_DATUM}: neuer erster Tag der Phase.", wort="ab", schwach=False),
            "bis": _s(f"{_DATUM}: neuer letzter Tag; 'offen' = bis auf Weiteres.",
                      wort="bis", schwach=False),
            "nur_am": _s(f"{_DATUM}: nur dieser eine Tag.", wort="nur am"),
            "nur_von": _s(f"{_DATUM}: erster Tag, an dem die Änderung gilt (mit nur_bis).",
                          wort="nur vom"),
            "nur_bis": _s(f"{_DATUM}: letzter Tag, an dem die Änderung gilt.", wort="bis"),
        },
        pflicht=("kennung",),
        art="aendern", alltag="tagesrhythmus ändern", frage="die Phase",
        worte=("Phase geändert", "Phase ändern"),
        einfach="Ändert EINE Phase per kennung; einzelne Tage mit nur_am oder nur_von+nur_bis.",
    ),
    _aktion(
        "delete_calendar_phase",
        "Löscht EINE Phase des Tagesrhythmus per kennung.",
        {"kennung": _KENNUNG_PFLICHT},
        pflicht=("kennung",),
        art="loeschen", alltag="tagesrhythmus löschen", frage="die Phase löschen",
        worte=("Phase gelöscht", "Phase löschen"),
    ),
    _aktion(
        "set_calendar_group",
        "Setzt die Gruppe EINES Eintrags per kennung (fasst ihn in der Monatsansicht zu "
        "einem Block, z.B. Uni).",
        {"kennung": _KENNUNG_PFLICHT, "kategorie": _GRUPPE, "kategorie_name": _GRUPPE_NAME},
        pflicht=("kennung", "kategorie"),
        art="aendern", alltag="gruppen setzen", frage="die Gruppe setzen für",
        worte=("Gruppe gesetzt", "Gruppe setzen"),
    ),
    _aktion(
        "set_calendar_layer",
        "Legt EINEN Eintrag per kennung auf fest (termine) oder vielleicht (uncommitted).",
        {"kennung": _KENNUNG_PFLICHT,
         "ebene": {"type": "string",
                   "enum": [kalender_kennung.VERBINDLICH, kalender_kennung.UNVERBINDLICH],
                   "description": "'termine' = fest zugesagt, 'uncommitted' = vielleicht.",
                   X: {"wort": "Ebene", "ungueltig": "EBENE-UNBEKANNT"}}},
        pflicht=("kennung", "ebene"),
        art="aendern", alltag="termine fest/vielleicht setzen", frage="umlegen",
        worte=("Ebene gewechselt", "Ebene wechseln"),
    ),
    # ── Aussehen eines Eintrags (2026-10-11, Kern: stil, KALENDER 458a658) ──
    # Flache Felder statt eines CSS-Dicts: schwache Modelle füllen einzelne
    # Werte zuverlässiger als ein verschachteltes Objekt. Der Adapter baut
    # daraus das CSS-Dict (stil.KASTEN) für kalender_kennung.stil_setzen.
    _aktion(
        "set_calendar_style",
        "Rahmen, Farben, Muster EINES Eintrags per kennung; nur genannte Felder ändern sich.",
        {"kennung": _KENNUNG_PFLICHT,
         "rahmen": {"type": "string", "enum": [w for w, _ in stil.RAHMEN],
                    "description": "Rahmenart: " + ", ".join(f"{w}={t}" for w, t in stil.RAHMEN),
                    X: {"wort": "Rahmen", "ungueltig": "STIL-UNGUELTIG"}},
         "rahmenfarbe": _s("Rahmenfarbe als #rrggbb, z. B. #ff8800."),
         "hintergrund": _s("Hintergrundfarbe als #rrggbb."),
         "schrift": _s("Schriftfarbe als #rrggbb."),
         "muster": {"type": "string", "enum": [w for w, _ in stil.MUSTER],
                    "description": "Innenmuster: " + ", ".join(f"{w}={t}" for w, t in stil.MUSTER),
                    X: {"wort": "Muster", "ungueltig": "STIL-UNGUELTIG"}},
         # 2026-10-11: einzelne Eigenschaften wieder „nicht gesetzt" (Sasha:
         # kein ausdrückliches none, nur nicht gesetzt — stil.py seit e511c74).
         "zuruecksetzen": {"type": "array",
                           "items": {"type": "string",
                                     "enum": ["rahmen", "rahmenfarbe", "hintergrund",
                                              "schrift", "muster"]},
                           "description": "Diese Eigenschaften wieder auf nicht gesetzt."},
         "entfernen": {"type": "string", "enum": ["ja"],
                       "description": "'ja' = eigenes Aussehen ganz entfernen."}},
        pflicht=("kennung",),
        art="aendern", alltag="termine einfärben", frage="das Aussehen ändern von",
        worte=("Aussehen geändert", "Aussehen ändern"),
    ),
    # ── Titel aus Liste/Projekt (2026-10-10, Kern: kalender_quelle) ──
    _aktion(
        "read_calendar_sources",
        "Listen und Projekte, aus denen ein Termin seinen Titel nehmen kann "
        "(quelle_art, quelle_id).",
        {}, art="lesen",
    ),
    _aktion(
        "set_calendar_source",
        "Gibt EINEM Eintrag per kennung eine Quelle: sein Titel ist dann live der oberste "
        "offene Punkt der Liste/des Projekts.",
        {"kennung": _KENNUNG_PFLICHT,
         "quelle_art": {**_QUELLE_ART, "description": "'liste' oder 'projekt'."},
         "quelle_id": {**_QUELLE_ID, X: {"wort": "Quelle", "fehlt": "QUELLE-UNGUELTIG"}},
         "label": _s("Optional Rückfall-Titel; weglassen = Name der Quelle.",
                     wort="Rückfall-Titel", schwach=False)},
        pflicht=("kennung", "quelle_art", "quelle_id"),
        art="aendern", alltag="termintitel aus listen", frage="den Titel live nehmen lassen für",
        worte=("Quelle gesetzt", "Quelle setzen"),
    ),
    _aktion(
        "clear_calendar_source",
        "Löst die Quelle EINES Eintrags per kennung.",
        {"kennung": _KENNUNG_PFLICHT,
         "titel_uebernehmen": {"type": "boolean",
                               "description": "true = den jetzigen Punkt als festen Titel behalten.",
                               X: {"wort": "Titel behalten"}}},
        pflicht=("kennung",),
        art="aendern", alltag="termintitel aus listen", frage="die Quelle lösen für",
        worte=("Quelle gelöst", "Quelle lösen"),
    ),
]


QUELLE = werkzeug_erzeuger.Quelle(name="kalender", praefix="K", bereich="kalender",
                                  aktionen=AKTIONEN,
                                  adapter=ki_kalender_adapter.KalenderAdapter())
