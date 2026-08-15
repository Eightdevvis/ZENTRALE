# Werkzeuge — Index

Was ZENTRALE für Sasha konkret tut: die einzelnen Panels und Rechner. Jedes
hier ist ein Ding, das man aufmacht und benutzt — im Unterschied zu
[../system/](../system/INDEX.md), wo steht, wie das Ganze gebaut ist.

| Werkzeug | Was es macht | Datei |
|---|---|---|
| **Kalender** | Layer-Modell (termine / routinen / pausen / erlebt), Konflikte, Alarme | [kalender_system.md](kalender_system.md) |
| **Mail** | IMAP-Triage per Sender-Keymap; der Ordner IST der Status, kein Flag | [mail_system.md](mail_system.md) |
| **News** | persönliche Tagesschau aus Bausteinen, KI-moderiertes Briefing | [news_system.md](news_system.md) |
| **Notizen** | freie Notiz aus gestapelten Blöcken (text / liste / float) | [notizen_system.md](notizen_system.md) |
| **Zyklus/PMS** | Vorhersage aus dem »periode«-Graphen | [zyklus_pms.md](zyklus_pms.md) |
| **Morgen-Messenger** | Deckel auf → ZENTRALE grüßt, auch wenn sie schlief | [morgen_messenger.md](morgen_messenger.md) |

## Was die KI davon anfassen darf

Lesen darf sie fast alles (Kalender, Mail, News). **Schreibende** Aktionen —
Termin eintragen, löschen, pausieren — laufen immer durch das Erlaubnis-Gate:
Python fängt den Tool-Call ab und fragt, bevor irgendetwas passiert. Nicht
modellgetrieben. Siehe [../ki/ki_system.md](../ki/ki_system.md).

Die **Listen** gehören Sasha (`data/lists.json`) — bis auf die eine Liste
`zentrale`, den Feature-Tracker, den Claude pflegt (`data/features.json`).
Details in `CLAUDE.md`.
