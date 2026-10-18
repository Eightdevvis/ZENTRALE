# Werkzeuge — Index

Was ZENTRALE für Sasha konkret tut: die einzelnen Panels und Rechner. Jedes
hier ist ein Ding, das man aufmacht und benutzt — im Unterschied zu
[../system/](../system/INDEX.md), wo steht, wie das Ganze gebaut ist.

| Werkzeug | Was es macht | Datei |
|---|---|---|
| **Kalender** | Layer-Modell (termine / uncommitted / rhythmus / pausen; routinen → termine), Konflikte, Alarme, Kennungen | [kalender_system.md](kalender_system.md) |
| **Kalender → iCalendar** | .ics (vdir, live seit Oktober), Google-Sync; Ebene uncommitted, Tagesrhythmus/Phasen, Gruppen, Quellen (Titel aus Listen/Projekten), Stil | [kalender_ics_bauplan.md](kalender_ics_bauplan.md) |
| **Kalender: Google-Sync-Stand** | Zustand nach jedem Sync-Lauf (Zugang abgelaufen, kein Netz, Löschsperre …), Route `/api/calendar/sync`, Warnung in TUI und Alarm-Kanal | [kalender_sync_zustand.md](kalender_sync_zustand.md) |
| **Kalender-Ansichten** | TUI-Entwürfe A/B/C (Tagesliste, Monatsraster, Zeitachse), Taste v dreht jetziger → A → B → C, Tab Woche/Monat; Tagesrhythmus als Hintergrund + Kasten R, Gruppen im Monat + Taste G | [kalender_ansichten_vorschau.md](kalender_ansichten_vorschau.md) |
| **Kalender-Formular** | feste Plätze: Felder wechseln nie den Platz, was nicht gilt steht gedämpft („—") und wird übersprungen; Ganztägig bei Serien | [kalender_formular.md](kalender_formular.md) |
| **Mail** | IMAP-Triage per Sender-Keymap; der Ordner IST der Status, kein Flag | [mail_system.md](mail_system.md) |
| Mail neu: Übergabe an eine eigene Sitzung (Wünsche, Vorbild Kalender, Bestand, erste Fragen) | [mail_neu_uebergabe.md](mail_neu_uebergabe.md) |
| **News** | persönliche Tagesschau aus Bausteinen, KI-moderiertes Briefing | [news_system.md](news_system.md) |
| **Notizen** | freie Notiz aus gestapelten Blöcken (text / liste / float) | [notizen_system.md](notizen_system.md) |
| **Morgenblick** | `/morning` im Chat: der Tag als HTML-Seite (Gelände, drei Akte, „Braucht dich"/„Erledigt"), Knöpfe → neues Gespräch | [morgenblick.md](morgenblick.md) |
| **Zyklus/PMS** | Vorhersage aus dem »periode«-Graphen | [zyklus_pms.md](zyklus_pms.md) |

## Was die KI davon anfassen darf

Lesen darf sie fast alles (Kalender, Mail, News). **Schreibende** Aktionen —
Termin eintragen, löschen, pausieren — laufen immer durch das Erlaubnis-Gate:
Python fängt den Tool-Call ab und fragt, bevor irgendetwas passiert. Nicht
modellgetrieben. Siehe [../ki/erlaubnis_gate.md](../ki/erlaubnis_gate.md).

Die **Listen** gehören Sasha (`data/lists.json`) — bis auf die eine Liste
`zentrale`, den Feature-Tracker (`data/features.json`). Den pflegt seit
2026-10-04 ebenfalls nur Sasha; Claude liest ihn höchstens. Details in
`CLAUDE.md`.
