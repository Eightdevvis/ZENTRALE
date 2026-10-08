# Mail neu — Übergabe an eine eigene Sitzung (Stand 08.10.2026)

Für eine neue Claude-Sitzung, die Mail in ZENTRALE neu aufbaut. Erst diese
Datei lesen, dann `CLAUDE.md`, `memory/claude_hinweise.md` („Das
Strukturziel") und `memory/werkzeuge/mail_system.md` (der heutige Stand).

## Was Sasha will (seine Worte)

- „unser mail programm is iwie.. naja. ungail. total verbuggt war das ganze
  ding immer und hat nix richtig geladen … da war ja eigentlich die idee nen
  mail programm einfach anzubinden damit es nich mehr so worries gibt. die
  idee gabs ja auch beim calendar.. bis es besser wurde sie einfach neu
  selbst zu machen"
- „ich hab viele verschiedene, gmail, outlook, posteo, help, aber ich will
  auch die ansicht und alles neu machen ich hab das nie benutzt das war mir
  alles zu unübersichtlich."

Also: **Daten und Abholen über bewährte Werkzeuge, Ansicht ganz neu.**
„help" ist unklar (eigene Domain? Hilfe-Postfach?) — als Erstes fragen.

## Vorbild: der Kalender

Der Kalender lief genauso schlecht, bis er umgestellt wurde (siehe
`memory/werkzeuge/kalender_ics_bauplan.md`): ein Standardformat ist die
einzige Wahrheit (.ics-Dateien), ein bewährtes Werkzeug gleicht ab
(vdirsyncer), ZENTRALE liest und schreibt nur über eine Fassade. Für Mail:

- **Abholen:** mbsync/isync (IMAP → Maildir, normale Dateien auf der Platte)
- **Suchen/Ordnen:** notmuch (Index, Tags, sehr schnell)
- **Senden:** msmtp
- **Fallstrick:** Gmail und Outlook wollen **OAuth2** (XOAUTH2) statt
  Passwort; Outlook erlaubt keine App-Passwörter mehr. mbsync kann das über
  ein SASL-Modul (prüfen, ob es auf Linux Mint 22.3 als Paket da ist).
  Posteo geht mit normalem Passwort. Es gibt schon `core/mail_oauth.py` —
  ansehen, was davon trägt.
- Geheimnisse: Passwörter/Tokens nie im Klartext und nie in Git; heute
  `core/mail_secrets.py` (verschlüsselt, Datei 600). Sasha nutzt **KeePass**.

## Was heute da ist (zum Ansehen, nicht zum Weiterflicken)

`core/mail.py`, `core/mail_puffer.py`, `core/mail_oauth.py`,
`core/mail_rules.py`, `core/mail_secrets.py`, Ansicht `tui/ansichten/post.py`
— zusammen ~4 250 Zeilen, IMAP-Triage per Absender-Liste, „der Ordner ist der
Status". Wer liest Mail mit: der **Morgenblick** (`core/morgenblick_daten.py`,
Sammler „mail" über `mail.recent`) und das KI-Werkzeug `read_mail`. Beide
müssen auf den neuen Weg umziehen.

## Regeln dieses Projekts (Kurzfassung)

- Git: Worktree, testen, `merge --ff-only`, `push origin main`; nie
  `--force`. Andere Sitzungen arbeiten parallel (ASSISTANT: KI-Chat,
  Werkzeuge, Abgleich; KALENDER: alles in `core/kalender*.py`,
  `tui/ansichten/kalender*.py`) — deren Dateien nicht anfassen, bei
  Berührung Bescheid geben.
- Schichten-Bauplan `memory/system/bauplan_kern.md` + Test; Daten atomar
  (`core/dateien.py`), Geheimnisse mit `geheim=True`; Einstellungen nur über
  `ai_config.setting`; Tests nie gegen echte `data/` (conftest lenkt um).
- Für Sasha sichtbare Texte: Alltagswörter, keine erfundenen Begriffe;
  Tasten/Befehle englisch.
- Sasha schreibt Shell-Befehle selbst und lernt das — ihm keine fertigen
  Befehle vorsagen, nur sagen, was zu tun ist (globale Regel in
  `~/.claude/CLAUDE.md`).
- Vorgehen nach Sashas Wunsch: erst planen und **alle** Fragen/Freigaben
  gebündelt einsammeln, Dauer ansagen, dann lange allein durcharbeiten;
  Kleinentscheidungen in eine Liste für Sasha.

## Erste Fragen an Sasha

1. Welche Konten genau (Gmail, Outlook, Posteo, „help" = ?), und welche
   davon sollen auch **senden** können?
2. Neues Mail-TUI daneben (z. B. aerc) oder nur die neue Ansicht in ZENTRALE?
3. Was soll die neue Ansicht können (Posteingang über alle Konten, Suchen,
   Antworten, Ablegen, „wartet auf Antwort" für den Morgenblick …)?
4. Wie lange zurück sollen Mails lokal liegen (alles / 1 Jahr / …)?
