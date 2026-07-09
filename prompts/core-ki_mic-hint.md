# Core-KI: Spracheingabe-Hinweis + Jetzt-Block

- **Live-Sprache:** de

Zwei kleine, konditional/dynamisch eingesetzte Prompt-Bausteine der Core-KI.

## 1. Spracheingabe-Hinweis (`_MIC_INPUT_HINT`)

- **Quelle:** `core/ai.py:400` (`_MIC_INPUT_HINT`)
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

- **Quelle:** `core/ai.py:138` (`_now_prompt`)
- **Rolle:** Wird bei **jedem** Turn frisch gebaut und **ganz vorne** in den
  System-Prompt gehängt. Schließt die Zeit-Blindheit: das aktuelle Datum/die
  Uhrzeit werden hart reingeschrieben (nicht halluzinierbar), plus der Hinweis,
  dass der Kalender ausschließlich über das `read_calendar`-Tool abzufragen ist.

Der Text ist **dynamisch** (Datum/Uhrzeit werden eingesetzt). Beispiel-Ausgabe
für Montag, 8. Juni 2026, 14:05:

> **## Jetzt**
> Heute ist Montag, der 8. Juni 2026. Aktuelle Uhrzeit: 14:05. Dieser Block ist
> die einzige verlässliche Zeitquelle - aktivierte Datums-Knoten aus dem
> Konzept-Graph sind Erinnerungen an frühere Tage, NICHT der aktuelle Tag.
>
> Kalender/Termine: du hast keine Termine im Kopf. Für JEDE Frage nach Plänen,
> Terminen oder Daten (heute, diese/nächste Woche, Monat, Vergangenheit,
> beliebiger Zeitraum) rufst du zuerst read_calendar - nie raten, nie ohne Tool
> zurückfragen.

Wochentag (`_WEEKDAYS_DE`) und Monat (`_MONTHS_DE`) sind ausgeschriebene deutsche
Namen; die restlichen Sätze sind konstant.
