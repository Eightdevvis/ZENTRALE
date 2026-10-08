# Datensicherung — das private Daten-Repo

> **Wird abgelöst (2026-10-08):** der Abgleich über die Mitte
> ([abgleich.md](abgleich.md)) legt dieselben Dateien verschlüsselt und mit
> ganzer Geschichte ins selbe Repo (Zweig `abgleich`), alle paar Minuten.
> Nach Sashas Umstellung kann der tägliche Sicherungs-Timer aus. ⚠ Die
> Zweige `knoten/<rechner>` dieser Sicherung liegen **im Klartext** auf
> GitHub — ob sie gelöscht werden, entscheidet Sasha. Die Positivliste steht
> seit heute in `core/abgleich_auswahl.py` (eine Stelle für beide).

**Stand 2026-10-07.** Sasha legte am 06.10. das private Repo
`git@github.com:Eightdevvis/data.git` an: *„wo wir backup und alles was so an
sensible daten in ne cloud will reinschmeißen können."* Code und Daten bleiben
getrennt: das ZENTRALE-Repo hält Code, dieses hier Sashas Daten.

## Wie es gebaut ist

`scripts/daten_sichern.py` spiegelt eine **Positivliste** von Dateien in einen
eigenen Klon unter `~/.local/share/zentrale/daten-sicherung`, committet und
pusht.

- **Positivliste statt Sperrliste.** Gesichert wird nur, was in `SICHERN` im
  Skript steht. Eine neue Datei mit Schlüsseln kann nie aus Versehen mitrutschen.
- **Schlüssel-Scanner** vor jedem Commit (zweimal: auf der Auswahl und auf dem
  Klon). Sieht etwas nach API-Schlüssel, Token, Passwort oder Private Key aus,
  wird nichts committet und nichts gepusht. Ein privates GitHub-Repo zählt als
  „draußen" (`CLAUDE.md`: ein Key dort gilt als kompromittiert).
- **Ein Branch pro Rechner:** `knoten/<hostname>`. PC und Laptop schreiben nie
  in denselben Branch — kein Konflikt, kein Überschreiben.
- **Klon außerhalb von `data/`**, damit der rsync-Sync zwischen den Rechnern
  ihn nicht dateiweise zerlegt.
- **Spiegel mit Historie:** was in ZENTRALE gelöscht wird, verschwindet im
  nächsten Stand; jede frühere Fassung steht in der git-Historie.

## Was drin ist — und was bewusst nicht

| Drin | Nicht drin |
|---|---|
| Gedächtnis (`data/gedaechtnis/`), Transkripte, Listen, Notizen, Tracker (`features.json`), Messreihen (`g_*.json`, `graphs.json`), Kalender (`ai_calendar.json`, später `data/kalender/`), Mail-Keymap, Kostenbuch, Tutor-Stände und -Fortschritt | `ai_config.json` (Klartext-Schlüssel), Caches (Mail-Ordner/-Zähler/-Zustand, News), TTS-Modell, `data/_beiseite/` |

⚠ **Offen für Sasha:** `data/mail_secrets.enc` (verschlüsselte Mail-Zugänge) ist
nicht drin. Verschlüsselt wäre es auf GitHub nur so sicher wie die Passphrase.
Soll es rein, ist das eine Zeile in `SICHERN`.

## Täglich automatisch

`deploy/zentrale-sicherung.service` + `.timer` (systemd-**User**-Einheiten):
täglich 03:30, verpasste Läufe beim nächsten Start nachgeholt. Einschalten:
die beiden Dateien in den Ordner für User-Einheiten legen, systemd neu einlesen
lassen und den Timer aktivieren — auf jedem Rechner, der sichern soll.

## Wiederherstellen

Im Repo den Branch des Rechners öffnen, die gewünschte Fassung einer Datei aus
der Historie holen und an denselben relativen Pfad im ZENTRALE-Ordner legen.
Danach das Backend neu starten (bzw. Hot Reload abwarten).

Verwandt: Kalender-Absicherung mit eigenem Verlauf und Git-Spiegel —
[../werkzeuge/kalender_ics_bauplan.md](../werkzeuge/kalender_ics_bauplan.md).
