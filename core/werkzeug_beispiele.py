# core/werkzeug_beispiele.py
#
# Aufruf-Beispiele (`input_examples`) für wenige Werkzeuge mit typischen
# Fehlgriffen — KI-Bibel W-05, 2026-10-22. Anthropic: „for tools with complex
# inputs, nested objects, or format-sensitive parameters, you can use the
# input_examples field" (platform.claude.com/docs/en/agents-and-tools/
# tool-use/define-tools, „Providing tool use examples"). Seit dem Abruf am
# 22.10.2026 ohne Beta-Header; jedes Beispiel muss zum input_schema passen,
# sonst antwortet die API mit 400.
#
# Wer bekommt sie:
#   - nur die Schiene gross und nur der Anthropic-Weg (cloud._to_anthropic_tools
#     mit beispiele=True). klein bleibt byte-gleich; OpenAI-kompatible Wege
#     (qwen & Co.) kennen das Feld nicht und bekommen es nicht.
#   - nur Werkzeuge, die gerade nicht zurückgestellt sind (defer_loading): ob
#     beides zusammen geht, sagt die Doku nicht, und ausprobieren kostet.
#   - nur Beispiele, die gegen das Schema DIESES Prozesses bestehen
#     (jsonschema). Mit werkzeuge_erzeugt = aus (handgeschriebene Kalender-
#     Schemas) fallen unpassende still weg, statt einen 400 zu riskieren.
#
# Die Fehlgriffe, gegen die sie zeigen:
#   read_calendar          eine bestimmte Sache mit 'suche' und ohne 'zeitraum'
#                          suchen (qwen-Profil Regel 3, Prüfstand Runden 6/7).
#   add_calendar_routine   Ende als UNTIL in der rrule, Wochentag im Titel, ein
#                          erfundenes Ende (Gespräch 20261022-111358-dd6127).
#   edit_calendar_routine  von/bis für eine reine Uhrzeit-Änderung (m04);
#                          einen Tag absagen per nur_am statt neuer Routine.
#
# Je Beispiel ~20–50 Tokens; im gecachten Präfix. Mehr als zwei je Werkzeug
# nur mit Grund.
#
# Fundament (Schicht 1, memory/system/bauplan_kern.md): importiert nichts aus dem Kern.

import jsonschema

BEISPIELE = {
    "read_calendar": [
        {"suche": "Geige"},
        {"zeitraum": "naechste_woche"},
    ],
    "add_calendar_routine": [
        {"label": "Geigenstunde", "rrule": "FREQ=WEEKLY;BYDAY=TU", "time": "17:45",
         "von": "2026-10-27", "bis": "2027-02-14", "kategorie": "keine"},
        {"label": "Analysis I", "rrule": "FREQ=WEEKLY;BYDAY=MO,WE", "time": "10:15",
         "ende": "11:45", "ort": "Hörsaal 2", "von": "2026-10-19", "bis": "2027-02-12",
         "kategorie": "uni"},
    ],
    "edit_calendar_routine": [
        {"kennung": "#r3f9c", "aktion": "aendern", "time": "18:00", "ende": "19:00"},
        {"kennung": "#r3f9c", "aktion": "loeschen", "nur_am": "2026-11-03"},
    ],
}


def fuer(name: str, schema: dict) -> list:
    """Die Beispiele zu einem Werkzeug, die gegen `schema` bestehen."""
    raus = []
    for b in BEISPIELE.get(name, ()):
        try:
            jsonschema.validate(b, schema)
        except jsonschema.ValidationError:
            continue
        raus.append(dict(b))
    return raus
