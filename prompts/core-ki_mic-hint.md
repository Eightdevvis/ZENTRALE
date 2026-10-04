# Core-KI: Spracheingabe-Hinweis + Jetzt-Block

- **Live-Sprache:** de

Zwei kleine, konditional/dynamisch eingesetzte Prompt-Bausteine der Core-KI.

## 1. Spracheingabe-Hinweis (`_MIC_INPUT_HINT`)

- **Quelle:** `core/profil/klein.py` (`_MIC_INPUT_HINT`; gilt für beide
  Schienen, `gross` reicht ihn durch)
- **Rolle:** Wird **nur** injiziert, wenn die User-Message tatsächlich aus dem
  Mikrofon kam (Whisper, `via_mic=True`). Tastatur-Eingaben sehen den Block nicht.
  Warnt die KI, dass Whisper-small auf CPU einzelne Wörter verstümmeln kann
  (Eigennamen, Akronyme, Fachbegriffe, Anglizismen), damit sie bei semantischen
  Brüchen kurz nachfragt statt auf Transkriptions-Müll zu antworten.

Deutscher Prompt, wörtlich aus dem Code kopiert:

> **## Spracheingabe (diese Nachricht)**
> Diese Nachricht kam per Mikrofon und wurde durch Whisper transkribiert.
> Transkription kann einzelne Wörter verfälschen, besonders Eigennamen, Akronyme,
> Fachbegriffe und Anglizismen. Wenn etwas im Kontext keinen Sinn ergibt oder ein
> Wort verdächtig „danebenliegt", frag kurz nach was gemeint war ("Meinst du
> X?"), statt es wörtlich zu nehmen oder zu raten. Andere Nachrichten in der
> History stammen aus Tastatur-Eingabe - dort ist der Text wörtlich gemeint.

## 2. Jetzt-Block (`_now_prompt()`)

- **Quelle:** `core/ai.py` (`_now_prompt`; gilt für beide Schienen)
- **Rolle:** Wird bei **jedem** Turn frisch gebaut und steht im **wechselnden**
  Teil hinten — lokal am Ende des System-Prompts, in der Cloud an der neuesten
  User-Nachricht (Prompt-Cache, siehe `_PROMPT_ORDER` in `core/ai.py`).
  Schließt die Zeit-Blindheit: das heutige Datum wird hart reingeschrieben.
  Die **Uhrzeit steht seit 18.08.2026 bewusst nicht mehr drin** — sie holt sie
  per `read_time`. Heute/morgen stehen im Imprint-Block „Was ansteht", alles
  andere über `read_calendar`.

Der Text ist **dynamisch** (Datum wird eingesetzt). Beispiel-Ausgabe für
Montag, 8. Juni 2026:

> **## Jetzt**
> Heute ist Montag, der 8. Juni 2026. Dieser Block ist die einzige verlässliche
> Zeitquelle - Daten, die in Notizen oder im Tagebuch stehen, sind Erinnerungen
> an frühere Tage, NICHT der aktuelle Tag.
>
> Die UHRZEIT steht hier bewusst nicht: du weißt nicht, wie spät es ist.
> Brauchst du sie wirklich - weil Sasha danach fragt oder weil es für eine
> Entscheidung zählt - ruf read_time. Rate nie, und rechne nichts aus dem Kopf
> aus.
>
> Kalender/Termine: was heute und morgen ansteht, steht im Block 'Was ansteht'
> - daraus darfst du direkt antworten. Alles andere (jeder weitere Zeitraum,
> ein bestimmtes Datum, die Vergangenheit) hast du NICHT im Kopf: dafür
> read_calendar rufen, nie raten, nie ohne Tool zurückfragen.

Wochentag (`_WEEKDAYS_DE`) und Monat (`_MONTHS_DE`) sind ausgeschriebene deutsche
Namen; die restlichen Sätze sind konstant.
