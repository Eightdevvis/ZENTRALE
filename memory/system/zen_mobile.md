# ZEN-MOBILE — die Handy-App

**Stand 2026-10-28** (Mitte, Login, Kalender; Auge siehe unten). Flutter-App in `mobile/` (Android). Sasha: „sie muss
eigentlich nicht viel können" — die ZENTRALE-KI unterwegs, statt der
Claude-App, damit Gedächtnis und Gespräche nicht auseinanderlaufen
(Fahrplan Punkt 3, `memory/ueberblick.md` → „Fahrplan").

## Was man sieht

- **Start:** ein Auge in der Mitte — dasselbe Wesen wie das KI-Auge der TUI
  (`tui/pixel.py`, `AUGE_FARBEN`), nur glatt gezeichnet: Mandel, schweres
  Oberlid und gespiegeltes Unterlid, große Iris, blinzelt, schaut sich gelassen
  um, denkt mit Funkenring.
  Tag/Nacht folgt dem Handy.
- **Auge antippen → KI-Chat** (die Pupille füllt erst das Auge, siehe
  „Das Auge"), schlicht wie die Claude-App: Gesprächsliste im
  Seitenmenü, Sashas Nachrichten als Blasen, Antworten als Markdown,
  aufklappbare Gedanken, Stopp, Kopieren, Neu antworten.
- **Knöpfe um das Auge:** die Liste `bereiche` in `lib/start/startseite.dart`.
  Erster Knopf seit 28.10.: **Kalender** (unten). Standard: Auge offen, keine Knöpfe. Runterwischen schließt das Auge und
  lässt die Knöpfe herauswachsen (siehe „Das Auge"). Ein neuer Bereich = ein
  Eintrag, die Knöpfe ordnen sich für jede Anzahl selbst auf einer Ellipse.

## Das Auge (`lib/auge/`, Stand 2026-10-28)

**Alle Stellschrauben** (Lidtiefe, Falten, Pupille nach Uhrzeit, Launen-
Häufigkeit, Zeiten fürs Antippen und den Knopf-Ring, Bahn- und Chip-Stil)
stehen in `lib/auge/auge_regler.dart` — Ästhetik entscheidet Sasha, dort
wird gedreht. Probebilder aller Zustände: `flutter test test/auge_test.dart`
schreibt PNGs nach `mobile/build/auge_vorschau/` (nicht im Repo).

- **Form:** Das Unterlid ist das Spiegelbild des schweren Oberlids an der
  Waagrechten durch die Pupille („einfach ne x-achse durch die pupille nehmen
  und das design spiegeln") — halb geschlossen, ruhig, nicht erschrocken.
  Die Lider laufen zur Mandelkante hin durchsichtig aus (Haut, kein Glas).
  Falten oben und gespiegelt unten sind halbe Sinusbögen, in der Mitte am
  dicksten, zu den Enden auf null. Blinzeln: beide Lider treffen sich in der
  Mitte. Maler: `auge_maler.dart`; Bewegung (Blick, Blinzeln): `zeit.dart`.
- **Uhrzeit:** 21–7 Uhr ist die Pupille etwas größer, 3–5 Uhr winzig
  („extra spooky"); Übergänge weich über je eine Stunde um die Grenze.
  Lokale Zeit, die Uhr ist ins Widget steckbar (`Auge(uhr: ...)`, Tests).
- **Launen** (`launen.dart`): selten (Zeitfenster 3 min, in ~65 % davon
  eine, also etwa alle 4–5 min), fest gewürfelt je Fenster wie `_rnd`, nie
  beim Denken, Aufgehen, Antippen oder geschlossen. Jede kommt und geht weich
  und ist bei Stärke 0 das normale Auge. Heute zwölf: stern (wandert statt
  der Pupille), zwillinge (zwei Iriden umkreisen sich), unscharf, katze
  (Schlitz, gelblich), spirale, farbreise (einmal durch alle Farben),
  doppelblinzeln, funken (Pupille zerspringt und fügt sich wieder),
  mond (Sichel spiegelt sich), augenrollen, zwinkern, herz (schlägt, Iris
  rosa). Neue Laune = eine Klasse + ein Eintrag in `alleLaunen`; der Maler
  kennt nur die Schnittstelle `Laune` (formen / maleIris / malePupille /
  maleLicht).
- **Vorschau:** langes Drücken aufs Auge der Startseite spielt die nächste
  Laune der Reihe nach und nennt ihren Namen unten.
- **Antippen:** die Pupille wächst in ~0,6 s, bis sie die ganze Mandel füllt;
  genau diese Mandel wächst dann in Pupillenfarbe über den Schirm, aus dem
  Dunkel blendet der Chat auf (`pupillen_route.dart`). Zurück endet es in der
  vollen Mandel, dann zieht sich die Pupille wieder zusammen.
- **Knopf-Ring** (`lib/start/leiterbahnen.dart`): Runterwischen (irgendwo auf
  dem Schirm) → das Auge schließt sich ruhig, dann zeichnen sich Leiterbahnen
  vom Lid zu jedem Knopf (gerade raus, ein Knick um 45°, Lötaugen am Anfang
  und am Knick, leiser Schein in den Augenfarben), am Ende wachsen die Knöpfe
  als kleine Chips auf. Hochwischen oder Tippen aufs geschlossene Auge → alles
  rückwärts. Knöpfe sind nur fertig gezeigt tippbar.
- **Kleine Augen im Chat** (Leer-Zustand, Denk-Anzeige) nutzen denselben
  Maler; die Denk-Anzeige bekommt nie Launen.

## Warum das Handy ein eigener Knoten ist (kein Client des Backends)

Kein Rechner läuft zuverlässig dauerhaft, das Handy soll aber von überall
gehen. Darum spricht es die KI **selbst** (Claude-API) und gleicht über die
**Mitte** ab — die ZENTRALE-Cloud (`https://zentrale-cloud.sevendevs.workers.dev`,
dieselbe Adresse wie `core/cloud_api.VORGABE`, in Dart `lib/mitte/cloud.dart`).
Das Handy ist ein **fremder Knoten**: es liest das Inhaltsverzeichnis, schreibt
aber nur in seinen Eingang `knoten/handy/` (Format:
`memory/betrieb/abgleich.md` → „Format für fremde Knoten“). Der alte Plan einer
`GitHubMitte` ist damit erledigt.

- **Anmelden (einmal):** Benutzername + Passwort des ZENTRALE-Kontos in den
  Einstellungen (Sasha, 28.10.2026). Wie `core/konto.anmelden`:
  `POST /v1/vorab` → Argon2id im eigenen Isolate (`lib/krypto/`, ~1,7 s am
  Laptop, am Handy einige Sekunden, die Oberfläche bleibt flüssig) →
  `POST /v1/sitzung` (`knoten: "handy"`) → `konto_schluessel` auspacken. Das
  Passwort wird **nie** gespeichert; im Keystore liegen nur Sitzung und
  `konto_schluessel` (`lib/konto/konto.dart`). Abmelden löscht beides. Danach
  kommen Claude-Schlüssel, Gespräche, Kontext und Kalender von selbst.
- **Claude-Schlüssel:** aus den Zugangsdaten des Adapters
  (`data/adapter/geheim.enc`, Eintrag `ki/ANTHROPIC_API_KEY`, je Eintrag mit dem
  `konto_schluessel` verschlüsselt — entschlüsselt nur im Moment des Aufrufs,
  `lib/konto/geheim.dart`). Ein von Hand eingetragener Schlüssel hat Vorrang
  (Notbehelf in den Einstellungen).
- **Gespräche:** exakt das Format von `core/gespraeche.py`. Das Handy heißt
  Knoten `handy` und schreibt nur `gespraeche/<id>/handy.jsonl` und
  `gespraeche/_knoten/handy.json` — darum keine Konflikte. Zeitstempel
  Byte-gleich zu Pythons `isoformat(timespec="microseconds")` (Test).
- **Eine KI, nicht zwei:** den System-Prompt baut nur der Kern. Er legt ihn
  als `data/mobil/kontext.json` in die Mitte (`core/mobil_kontext.py`):
  `{version, stand, anbieter, modell, effort, system}`. Das Handy hängt einen
  Absatz an (`lib/ki/kontext.dart`): läuft auf dem Handy, sieht den Kalender
  der nächsten zwei Wochen **nur lesend**, sonst **keine Werkzeuge**, ehrlich
  sagen, was es von hier nicht sehen kann. Fehlt das Paket: Notbetrieb mit
  `claude-sonnet-5` / effort `low` und Minimal-Prompt. Der Kalender-Überblick
  (`lib/kalender/ueberblick.dart`, „im Blick, nicht aufsagen“ wie KT-07) steht
  als zweiter System-Block **hinter** dem gecachten festen Teil.
- **Abgleich** (`lib/mitte/`): beim Start, nach jeder Antwort, beim
  Herunterziehen (Chat, Kalender), nach einem neuen Termin; nie zwei Läufe
  gleichzeitig (`abgleich_steuerung.dart`). Holt `data/gespraeche/**`,
  `data/mobil/kontext.json`, `data/kalender/**` (.ics, `color`,
  `displayname`) und `data/adapter/geheim.enc`; was in der Mitte verschwindet,
  verschwindet hier. Bringt nur Eigenes, den `kopf.json` eines hier begonnenen
  Gesprächs (solange die Mitte keinen hat) und neue Termine als Vorschlag.
  Nach einer Neuinstallation holt es sein Eigenes aus dem Eingang zurück. Ist
  die Mitte leer (noch kein Rechner), schreibt es nichts. Einen Termin-
  Vorschlag nimmt es aus dem Eingang, sobald die Mitte ihn kennt.
- **Pfade:** in der Mitte ab dem ZENTRALE-Ordner (`data/gespraeche/…`), in der
  Ablage des Handys ab `data/` (`gespraeche/…`). Übersetzt wird an EINER
  Stelle: `lib/mitte/regeln.dart` (dort auch, was geholt und gebracht wird).
- **Austauschbar:** der Abgleich kennt nur die Schnittstelle `Mitte`
  (`holen`, `lesen`, `eingangLesen`, `eingangSenden`); `HttpMitte` ist die
  Cloud, `SpeicherMitte` die der Tests — der Heimserver wird eine weitere.
- **Krypto** (`lib/krypto/`, Paket `cryptography` + `crypto`): Fernet aus
  AES-128-CBC und HMAC-SHA256 (HMAC zuerst geprüft), HKDF-SHA256, Argon2id
  (rein Dart, im Isolate), versteckte Namen per HMAC. Prüfsteine:
  `test/daten/konto_testvektoren.json` (Kopie des Kerns) und
  `test/daten/mitte_testvektoren.json` (erzeugt mit dem echten Kern).

## Der Kalender (`lib/kalender/`, seit 2026-10-28)

Sasha will Google Kalender ablösen — die App muss können, was Google tat.

- **Ansehen:** heute und die nächsten drei Wochen als Liste. Ebenen =
  Ordner: `termine` (zugesagt) voll, `uncommitted` (Optionen) leiser und
  kursiv, `rhythmus` (Schlaf, Essen) als eine dezente Zeile je Tag. Farben
  aus dem vdir (`color`), sonst aus dem Auge. Abgeschaltete und pausierte
  Vorkommen (X-ZENTRALE-AUS/PAUSE, EXDATE, abgesagt) fehlen.
- **Deadlines:** ⚑ mit Muss-Zeit und Soll-Zeit (`X-ZENTRALE-SOLL`); ist das
  Soll vorbei, das Muss noch nicht → „soll verpasst“ in Warnfarbe (Regel wie
  `tui/ansichten/kalender_deadline.py`).
- **Rechnen wie der Kern:** `termin_lesen.dart` liest .ics wie
  `kalender_ics_abbildung.lesen` (Art, Spannen, Routinen, `seit`, Pausen,
  Aus-Tage, RECURRENCE-ID, Extras), `regel.dart` rechnet RRULE wie dateutil,
  `kalender.dart` die Vorkommen wie `kalender.entries_in_range`. Prüfstein:
  `test/daten/kalender_testvektoren.json` — erzeugt von
  `scripts/handy_testvektoren.py` mit dem echten Kern aus ausgedachten,
  echt geformten Terminen (Wochen-/Monatsregeln, INTERVAL, COUNT, UNTIL,
  EXDATE, Pausen, verschobene/abgesagte Vorkommen, Spannen, Phasen über
  Mitternacht, Deadlines, UTC vor/nach der Zeitumstellung). Ändert sich der
  Kern, Skript neu laufen lassen, dann `flutter test`.
- **Eintragen:** Titel, Tag, Beginn oder ganztägig, Dauer, Ebene (Vorgabe
  `termine`). Das Handy schreibt eine NEUE .ics Byte für Byte wie
  `termin_kalender` (UID `<uuid4-hex>@zentrale`, Datei
  `data/kalender/<ebene>/<uid>.ics`, Test gegen den Kern) als Vorschlag in
  seinen Eingang; sie steht sofort in der Liste mit „wartet auf Abgleich“.
  Ein Rechner übernimmt sie nur als neuen Termin
  (`core/abgleich_vorschlaege.kalender_vorschlag_annehmen`).
- **Ändern, Löschen, einzelne Vorkommen aus:** noch nicht — die Seite sagt
  es beim Antippen. Nächster Schritt (Kalender-Session): ein Vorschlag bleibt
  eine ganze .ics im Eingang; der Kern weitet nur die eine Annahme-Regel auf
  „je VEVENT zusammenführen“.
- **Erinnerungen** (`erinnerungen.dart`): jeder VALARM wird eine Android-
  Benachrichtigung (relativ zum Beginn/Ende oder fester Zeitpunkt; Google
  -PT7H ebenso wie unsere Deadline-Vorwarnung -P3D). Nach jedem Abgleich alle
  weg und die nächsten 30 Tage neu (höchstens 120), über einen Neustart
  hinweg (`flutter_local_notifications` + `timezone`, Boot-Receiver im
  Manifest). Erlaubnis (Benachrichtigungen, pünktliche Wecker) fragt die App
  erst, wenn es zum ersten Mal etwas zu erinnern gibt; ohne „pünktlich“
  kommen sie ungenau (Android darf schieben).
- **Kommt der Kalender nicht?** `data/kalender/**` ist nur in der Mitte, wenn
  ein Rechner ihn hineingibt (`abgleich_apps.jetzt_erlaubt`; am 28.10. noch
  nicht — die Kalender-Session schaltet es frei). Die Einstellungen zeigen
  „noch nicht in der Mitte“; Vorschläge warten bis dahin im Eingang.

## Aufbau `mobile/lib/`

| Ordner | Aufgabe |
|---|---|
| `ablage/` | Dateien des Handys, Pfade ab `data/` (Platte / Speicher für Tests) |
| `gespraeche/` | Format und Regeln von `core/gespraeche.py` (Zusammenlegen, Verwerfen, Titel) |
| `ki/` | Schnittstelle `KiAnbieter`, Claude per HTTP+SSE, Kontextpaket |
| `mitte/` | Schnittstelle `Mitte`, `HttpMitte` (Cloud), Abgleich, `regeln.dart` (was hin und her darf, Pfade), `abgleich_steuerung.dart` (wann) |
| `krypto/` | Fernet, Argon2id/HKDF (Konto), Tresor (versteckte Namen) |
| `konto/` | Anmelden/Abmelden, Sitzung im Keystore, Zugangsdaten des Adapters lesen |
| `kalender/` | .ics lesen/schreiben, RRULE, Vorkommen, Erinnerungen, Überblick für die KI, Seiten |
| `dienste.dart` | Die Dienste für Seiten aus `bereiche` (InheritedWidget) |
| `chat/` | `ChatSteuerung` (Logik) und die Seiten (zeichnen nur) |
| `auge/`, `start/`, `thema/` | Auge (Stellschrauben `auge_regler.dart`), Startseite mit Knopf-Ring, Farben Tag/Nacht |
| `einstellungen/` | Claude-Schlüssel von Hand + Einstellungsseite (Konto, Mitte, Kalender, KI) |

Tests: `mobile/test/` (Format, Zusammenlegen, Strom-Parser, Anfrage, Auge;
Krypto und Kalender gegen die Vektoren des Kerns; Mitte und Login gegen eine
gespielte Cloud `test/falsche_cloud.dart` — nie Netz, nie echte Konten).

## Offen

1. **Auf dem Handy ausprobieren** — bisher nur Tests und Analyse. Sasha:
   APK neu bauen (nicht auf dem 3,8-GB-Laptop), einmal anmelden.
2. Kalender in die Mitte (Kalender-Session), dann Ändern/Löschen vom Handy.
3. Argon2id-Dauer auf dem echten Handy messen; ist sie zu lang, eine native
   Umsetzung hinter dieselbe Funktion `hauptschluessel` stecken.
