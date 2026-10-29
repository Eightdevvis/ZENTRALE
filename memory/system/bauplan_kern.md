# Bauplan des Kerns — Schichten, Türen, Altlasten

**Wozu:** Sasha, 2026-10-05: *„ich will nich dass wir irgendwann an einen
punkt kommen an dem der code unwartbar wird und alles um die ohren fliegt!"*
ZENTRALE hatte an diesem Tag 71.000 Zeilen. Die Außengrenze hielt (Backend
und Fronten getrennt, `state.py` als einzige Brücke, Tutor hinter einer Tür),
aber **innen** sagte nichts, wer wen benutzen darf. So entstanden 15
Import-Kanten im Kreis im KI-Kern und eine TUI-Funktion mit 7.700 Zeilen.

**Es driftet nicht, weil ein Test es erzwingt:** `tests/test_kern_bauplan.py`
liest die Tabellen dieser Datei und wird rot, wenn eine Kern-Datei keine
Schicht hat, eine Abhängigkeit nach oben zeigt, ein neuer Import-Kreis
entsteht, jemand an einer Tür vorbeigeht oder ein Riese wächst.
**Pflegeregel:** Struktur ändern → Bauplan im selben Commit ändern.

Verhalten steht woanders: Gesamtbild in [architektur.md](architektur.md).
Der Tutor ist seit 2026-10-09 eine eigene App (Repo `language-tutor`, mit
eigenem Bauplan); wie Hub und Apps zusammenhängen, steht in
[hub_bauplan.md](../hub/hub_bauplan.md).

## Die Schichten

```
   Fronten — eigene Programme, reden per HTTP mit den Routen
   tui/zentrale_tui.py   (Apps wie der Tutor: eigene Prozesse, eigene Repos)
                     │ HTTP
 ┌───────────────────▼──────────────────────────────────────────────┐
 │ 5  Routen         ui/app.py + ui/routen/ — darf alles darunter   │
 ├──────────────────────────────────────────────────────────────────┤
 │ 4  Ablauf         Event-Loop, Hot Reload                         │
 ├──────────────────────────────────────────────────────────────────┤
 │ 3  KI-Kern        denken: Modelle, Schleife, Prompt-Schienen     │
 ├──────────────────────────────────────────────────────────────────┤
 │ 2  Dienste        das Fach: Kalender, Mail, Listen, Gedächtnis … │
 ├──────────────────────────────────────────────────────────────────┤
 │ 1  Fundament      weiß nichts vom Fach: state, net, Config …     │
 └──────────────────────────────────────────────────────────────────┘
```

**Die eine Regel:** Ein Modul darf Module aus seiner **eigenen oder einer
tieferen** Schicht importieren, nie aus einer höheren. Gezählt wird auch der
Import innerhalb einer Funktion — er ist dieselbe Abhängigkeit, nur
versteckt.

Braucht ein tieferes Modul doch etwas von oben, gibt es zwei saubere Wege:
das Gebrauchte nach unten verschieben, oder es von oben **hereingeben**
(als Argument oder Callback), statt es zu importieren.

## Module

Die Schicht-Nummer ist die Wahrheit, die der Test liest. Pakete (`profil/`)
zählen als ein Modul.

| Modul | Schicht | Was |
|---|---|---|
| `state` | 1 | Geteilter Zustand, thread-safe — die einzige Brücke zwischen Event-Loop und Flask |
| `events` | 1 | Event-Konstanten |
| `net` | 1 | HTTP-Wrapper mit Terminal-Logging |
| `datasync` | 1 | Nach echter Daten-Änderung: Abgleich über die Mitte anstoßen (gedrosselt) bzw. alter Push-on-write zum Peer |
| `abgleich` | 1 | Abgleich über die Mitte, ein Lauf von vorn bis hinten: Basis, Vorhaben (absturzsicher), Hinweise, Zustand, Weg umstellen |
| `abgleich_auswahl` | 1 | Positivliste: was den Rechner verlassen darf (Datensicherung und Abgleich) |
| `abgleich_schluessel` | 1 | Der Schlüssel der Mitte: anlegen, laden, ablegen, Fernet, versteckte Dateinamen |
| `abgleich_zusammenfuehren` | 1 | Drei-Wege-Regeln über die Basis: JSON nach Eintrag/Feld, Zähler, Zeilen, Text mit beiden Fassungen |
| `abgleich_mitte` | 1 | Die Mitte hinter vier Handgriffen (holen, vorbereiten, senden, enthaelt); Umsetzung git und (seit 2026-10-22) http = die ZENTRALE-Cloud (`HttpMitte`) |
| `abgleich_apps` | 1 | Was dieses Gerät abgleicht, je App (seit 2026-10-23, löst `abgleich_bereiche` ab): Tabelle der Apps mit `[daten]` (geschnitten mit der Positivliste), Wahl je Gerät (Einstellung `abgleich_apps`, liest die alte `abgleich_bereiche` mit), wer Daten hat, wer noch fragen muss |
| `abgleich_ics` | 1 | .ics-Dateien im Abgleich je Termin (UID + RECURRENCE-ID) über die Basis zusammenführen; beide geändert → späterer LAST-MODIFIED (seit 2026-10-24) |
| `abgleich_vorschlaege` | 1 | Was ein fremder Knoten (Handy) vorschlagen darf: Kopf eines neuen Gesprächs, Termine als ganze .ics (`kalender_vorschlag_annehmen`: neu, ändern je VEVENT über `basis_sha`, Vorkommen, Ebene, löschen — Widerspruch → abgelehnt, nie überschrieben) (seit 2026-10-28, geweitet 2026-10-29) |
| `adapter` | 1 | Der Adapter (memory/hub/adapter.md): Anschlüsse `data/adapter/anschluesse/<id>.json` (Schema `adapter_anschluss.schema.json`), Kalender über die Cloud ja/nein und Google an/aus (abgeleitet aus der Quelle der Kalender-App), erstes Mal mit der Cloud: beiseitelegen, wenn sie schon einen Kalender hat |
| `kalender_einstellung` | 1 | Einstellung der Kalender-App je Instanz (`data/adapter/anschluesse/kalender-<id>.json`, Schema `kalender_einstellung.schema.json`): `quelle` google/zencloud/lokal, Ordner; lesen und den Wert setzen (seit 2026-10-29) |
| `adapter_geheim` | 1 | Zugangsdaten des Adapters `data/adapter/geheim.enc`: je Eintrag Fernet mit Konto- oder Geräteschlüssel, umschlüsseln, KI-Schlüssel aus ai_config übernehmen und in die Umgebung legen |
| `adapter_bruecke` | 1 | Mietvertrag der Brücke (`data/adapter/bruecke/<id>.json`, 15 min, wer zuerst in der Mitte war) und der mitreisende Stand von vdirsyncer |
| `adapter_vdirsyncer` | 1 | vdirsyncer-Konfiguration ↔ Vorlage im Anschluss (Geheimnisse, Token-Datei, Kalender-Ordner als Platzhalter); auf der Brücke bauen, erneuerten Token zurückschreiben |
| `adapter_ablauf` | 1 | Einrichten (KI-Schlüssel, vorhandene vdirsyncer-Konfiguration als Anschluss) und ein Lauf des Kalender-Timers: Brücke nehmen → abgleichen → nur als Inhaber Google; die Quelle der Kalender-App umstöpseln (`kalender_quelle_setzen`) |
| `eingebaute_apps` | 1 | Die eingebauten Apps (fokus, notizen, kalender … und `cloud`) mit Titel und `[daten]` wie ein app.toml, dazu der Ersatz für den Tutor, solange sein app.toml kein `[daten]` hat (seit 2026-10-23) |
| `i18n` | 1 | UI text through Python gettext: English msgids, German first (`core/locale/<lang>/LC_MESSAGES/zentrale.po` + `.mo`), language from `ZENTRALE_LANG` (since 2026-10-29) |
| `konto_schluessel` | 1 | Schlüssel-Schema des Kontos, nur Rechnen: Argon2id, HKDF-Infos, Fernet-Verpackung, Notfallschlüssel als Base32 — nachbaubar aus der Doku, Prüfstein `tests/daten/konto_testvektoren.json` (seit 2026-10-22) |
| `cloud_api` | 1 | Der Draht zur ZENTRALE-Cloud: urllib, Bearer, Fehler als `CloudFehler` mit englischem Satz; Adresse an einer Stelle (`VORGABE`, Env `ZENTRALE_CLOUD`) (seit 2026-10-22) |
| `cloud_nutzung` | 1 | Gratis-Grenzen der Cloud für den Betreiber: `GET /v1/nutzung` holen, 1 h merken in `~/.local/state/zentrale/nutzung.json`, `warnung()` für Start/Status nie blockierend und nie mit Ausnahme (seit 2026-10-23) |
| `konto` | 1 | Das Konto: anlegen (Entwurf → Notfallschlüssel zeigen → anlegen), anmelden, abmelden, Notfall, Passwort ändern; Sitzung + `konto_schluessel` in `~/.config/zentrale/konto.json` (600) — ohne Terminal, jede Oberfläche ruft es (seit 2026-10-22) |
| `knoten` | 1 | Knoten-Beschreibung dieses Geräts: Name, Sorte, erkannte Hardware (GPU, Bildschirm, Mikro, Lautsprecher aus /proc und /sys), Programm-Fassung (seit 2026-10-22) |
| `kachel_form` | 1 | Form einer Kachel-Antwort ohne Fachwissen: Fehler (ungültig, weg, zu klein), kürzen auf w×h, `stand` als Fingerabdruck (seit 2026-10-10) |
| `kachel_parameter` | 1 | Parameter einer Kachel-Art im Katalog als JSON Schema 2020-12 (seit 2026-10-10, vorher eigene `felder`): Werte aus der Adresse typen, gegen das Schema prüfen (Paket `jsonschema`), Fehler als ein deutscher Satz; Auswahl/Vorgaben zur Fragezeit eintragen |
| `adressen` | 1 | „Ein Objekt, eine Adresse": `zentrale://<app>/<pfad>?…` bauen, lesen, kanonisch machen (nur `urllib.parse`); alter Kachel-Verweis → Adresse (seit 2026-10-10) |
| `stil` | 1 | Aussehen als CSS-Eigenschaften (seit 2026-10-10): Wörter (Rahmen, Farben als #rrggbb, Muster `--zentrale-muster`, Icon gesperrt), JSON Schema des Angebots, Prüfung, Hex lesen, Angebot `KASTEN`, CSS-Deklarationsliste (`als_css`/`aus_css`), CSS3-Farbnamen (iCalendar COLOR) — stdlib-only, geteilt von Farbwähler/Stylebox der TUI und dem Backend |
| `farbrollen` | 1 | Wörterbuch der Farbrollen (Name + Bedeutung), das Apps und Oberflächen teilen; die Farbe wählt jede Oberfläche selbst (seit 2026-10-10) |
| `listen_baum` | 1 | Reine Helfer über den Eintrags-Baum einer Liste (zählen, erledigt, Reihenfolge einer Ebene, flach, Pfad, Bernstein-Steine) — geteilt von Listen-Ansicht der TUI und Listen-Kachel, ohne Imports (seit 2026-10-10) |
| `listen_bild` | 1 | DAS Bild einer Listen-Ebene (seit 2026-10-11): Kopf, Bernstein, Einträge als Kästen mit Titel und Markern, Auswahl als Rolle — neutrale Stücke `[text, rolle]`; Listen-Kachel und Listen-Ansicht der TUI malen beide nur das (Regel: [listen_app.md](../hub/listen_app.md)). Importiert nur `listen_baum`, steht in `deploy/aussenposten.txt` |
| `graph_reihen` | 1 | Reine Helfer über die Messwerte eines Graphen (Zahl prüfen, Uhrzeit, Dauer, Reihe je Typ, letzter Wert, Sparkline) — geteilt von Graph-Werkzeug der TUI und Graph-Kachel, ohne Imports (seit 2026-10-10) |
| `uhr` | 1 | Die eine Uhr (seit 2026-10-20): `heute()`/`jetzt()` bei jedem Aufruf, in Tests stellbar (`stellen`/`gestellt`/`vorstellen`), und das Tageswechsel-Ereignis (`Tageswechsel`) für die Schleifen von Backend und TUI — stdlib-only, ohne Imports; Regel: [gefahrzonen.md](gefahrzonen.md) |
| `titel_wochentag` | 1 | Welche Wochentage ein Titel sicher nennt („(Mo)“, „mittwochs“; nie „To Do“, „Montagsrunde“) und ob sie zur Regel bzw. zum Datum passen (seit 2026-10-22; Adapter bricht mit `K-TITEL-WOCHENTAG` ab, der Kalender-Kern darf es für eine Warnung mitbenutzen) — stdlib-only |
| `tastentabelle` | 1 | Format der Tastentabelle (welche Tasten eine App je Ansicht nimmt): Beschriftung → neutrale Tastennamen, prüfen, aus dem app.toml; geteilt von TUI (`tasten.py`, Bausteine) und `GET /api/tasten`, ohne Imports (seit 2026-10-11) |
| `zugang` | 1 | Zugangsschlüssel des Backends: anlegen, laden, zeitkonstant vergleichen, Modus aus/melden/an, Keks und Browser-Link (Prüfung selbst: `ui/routen/zugang.py`) |
| `werkzeug_gruppen` | 1 | Welche KI-Werkzeuge immer geladen sind, Gruppen und Schlagworte für die Werkzeug-Suche, die Vorauswahl des qwen-Profils, der Schalter `werkzeug_suche` (seit 2026-10-14) |
| `werkzeug_beispiele` | 1 | Aufruf-Beispiele (`input_examples`) für wenige gross-Werkzeuge mit typischen Fehlgriffen, nur Anthropic-Weg, gegen das Schema geprüft (seit 2026-10-22, KI-Bibel W-05) |
| `dateien` | 1 | Atomar schreiben (alte oder neue Fassung, nie eine halbe) — für alle Datendateien; Rechnername für Dateien pro Rechner |
| `ai_config` | 1 | Kill-Switches und API-Keys aus `data/ai_config.json`, `setting()`-Rangfolge |
| `providers` | 1 | Anbieter-Liste des Kerns (URL, Key, Dialekt, Modelle) |
| `prices` | 1 | Preistabelle der Cloud-Modelle, keine Logik |
| `usage` | 1 | Buchführung der Cloud-Kosten pro Tag und Monat |
| `kidebug` | 1 | Devtools-Bus der KI (`scripts/ai_devtools.py`) |
| `transkript` | 1 | Rohes Gesagtes, append-only jsonl |
| `context` | 1 | Datei-Zugriff nur über die Whitelist |
| `nutzer_ordner` | 1 | Sashas Nutzerordner (Einstellung `nutzer_ordner`, Standard ~/Zentrale) mit Input/ und Output/: anlegen, Pfade auflösen ohne Weg hinaus — seit 2026-10-11 nicht mehr für die KI (die liest die Ablage), nur noch Desk-Bilder und Werkstatt |
| `ablage_ort` | 1 | WO die Ablage liegt (Einstellung `ablage_dir`, Standard ~/Zentrale/Ablage; Köpfe/Fassungen versteckt in `.ablage/dokumente/`) — für Ablage und Abgleich |
| `cloud_folder` | 1 | Where the cloud folder lives (setting `cloud_folder_dir`, default ~/Zentrale/Cloud) and which files in it never sync (.git, node_modules, partial downloads …) — for sync and TUI (2026-10-29) |
| `tabelle_formel` | 1 | Excel-Formeln: deutsch → Excel-Standard (englisch, Komma) sicher übersetzen, unbekannte Funktionen ablehnen |
| `nutzer_angaben` | 1 | Name und Pronomen des Nutzers (Einstellungen `nutzer_name`, `nutzer_pronomen`) für die Platzhalter in den Prompt-Texten; Standard = der alte Text |
| `zip_sicher` | 1 | Eine Zip sicher lesen und auspacken (kein `..`/absolut/Symlink, Grenzen für Zahl und Größe, Auslassen von Verstecktem/Schlüsseln) — geteilt von `skill_import` und `ablage_zip` |
| `melden` | 1 | Meldung auf dem Desktop |
| `categories` | 1 | Data-Collection-Kategorien |
| `host_metrics` | 1 | CPU/GPU/VRAM/Temp/RAM des PCs |
| `aussenposten` | 1 | Pakete für Knoten ohne Backend (auch Dateien von Apps, `app:<name>/…`) |
| `app_prozess` | 1 | Eine Prozess-App starten, „lebt sie?" (`/hub/gesund`), anhalten; Python und Befehl aus dem Manifest — stdlib-only, geteilt vom Hub (`app_verwaltung`) und dem Zimmer-Starter `scripts/open_tutor_room.py` (seit 2026-10-22, steht in `deploy/aussenposten.txt`) |
| `apps` | 1 | Installierte Apps (Hub-Bauplan): Ordner (`app_pfad_<name>`), Manifest `app.toml`, Abonnenten eines Ereignisses; seit 2026-10-10 auch die selbst gebauten (`apps_ordner`, Standard `data/apps/*/app.toml`) — liest nur, importiert nie App-Code |
| `app_register` | 1 | Was aus dem Schaufenster installiert ist (seit 2026-10-25): Register je Rechner `<installiert_ordner>/apps-<rechner>.json` (Name, Quelle, Ordner, gewählte Ansichten), wo Apps wohnen (`app_ordner`), wie die Quelle einer App im Katalog aussieht (`downloadUrl`, `app_name`) |
| `theme` | 1 | Tag/Nacht-Modus, die Datei als einzige Wahrheit |
| `tone` | 1 | Ton-Erzeuger fürs TUI-Klavier |
| `pc_status` | 1 | Ist der andere Knoten gerade da? |
| `kalender_sync_zustand` | 1 | Stand des Google-Kalender-Syncs (letzter Versuch/Erfolg, Fehler im Klartext), Urteil „alt/Problem" und Alarm dazu (seit 2026-10-16) |
| `zug` | 1 | Der laufende Chat-Zug: Gesprächs-id und Stopp-Signal für die Werkzeuge, Ereignisse von Werkzeugen an die TUI (z. B. `ablage`) |
| `zug_ablauf` | 1 | Ablauf-Protokoll des laufenden Chat-Zugs (nur Cloud, gross): Kontext, Text zwischen Werkzeugen, Werkzeuge mit vollem Ergebnis, Fragen, Prüfung, Antwort, Kosten — nur mitschreiben; als Text für /trace |
| `werkzeug_befund` | 1 | Was ein Werkzeug zurückgibt: Status (`[ergebnis: ok/fehlgeschlagen/…]`), Beleg und Fehlercode; feste Formen ERLEDIGT/ABGEBROCHEN; die Schiene des laufenden Werkzeug-Aufrufs |
| `fehlercodes` | 1 | Die eine Tabelle der Fehlercodes der KI-Werkzeuge (Code → Ursache, was tun); `explain_error` liest sie |
| `schreib_sicherung` | 1 | „Ganz oder gar nicht" für Dienste ohne eigenes Zurück: Dateien/Ordner vor dem Schreiben merken, bei Abbruch Byte für Byte zurücklegen |
| `bild_vorschau` | 1 | Sashas ASCII-Filter (aus dem alten Browser-Frontend) in Python: Bild → Zeilen aus [Zeichen, Farbe] für Terminalzellen (2:1), Auto-Levels, mono/farbe, höchstens 32 Farben (xterm-256), LRU nach Datei-Stand; Pixel-Icon fürs Rad (16×16-PNG, wenige Farben) und sein Raster (seit 2026-10-10); Pillow erst bei Bedarf |
| `kalender` | 2 | Termine, Routinen, Konflikt-Alarm — die Fassade, Speicher austauschbar |
| `kalender_zeitraum` | 2 | Relative Zeiträume („diese_woche") in Daten übersetzen |
| `kalender_regel` | 2 | Wann eine Routine stattfindet (RRULE → Tage), eine Stelle für Fassade und .ics |
| `kalender_speicher` | 2 | Wählt den Kalender-Speicher (`kalender_speicher`: json/ics), alle Kalender-Pfade |
| `kalender_json` | 2 | Der alte Speicher `data/ai_calendar.json`, atomar, mit Rückfall-Sperre |
| `kalender_ics_abbildung` | 2 | Ein Termin/eine Routine ↔ VEVENT, verlustfrei oder gar nicht |
| `kalender_ics` | 2 | Der .ics-Speicher: vdir lesen (Cache), nur Unterschiede schreiben, Nebendaten |
| `kalender_sicherung` | 2 | Atomar schreiben, Datei-Sperre, Verlauf, Grabsteine, Snapshots, Massenlösch-Sperre |
| `kalender_spiegel` | 2 | git-Spiegel der Kalenderdaten außerhalb von `data/` |
| `kalender_migration` | 2 | Umzug JSON → .ics: prüfen (alle Lesefunktionen über beide Speicher, Feld-Inventar), ausführen, Rückweg |
| `kalender_bearbeiten` | 2 | Bearbeiten wie calcurse/Handy: Wiederholung (Typ/Intervall/Ende), Routine gezielt ändern, „nur dieser Tag", Spannen mit Zeit pro Tag, Einmal-Termine genau treffen |
| `kalender_konflikte` | 2 | Kollisionen, Fahrzeiten, Pausen-Grund, Abwesenheit, Alarme, Lese-Text und Abdruck für die KI (aus kalender.py ausgezogen, dort weitergereicht) |
| `kalender_kennung` | 2 | Termine/Routinen per fester Kennung (UID) lesen und ändern; `KalenderAbgelehnt` mit festen Codes (`CODES`), ein Schreibvorgang, Ablehnung schreibt nichts |
| `kalender_rhythmus` | 2 | Tagesrhythmus (seit 2026-10-10): Ebene `rhythmus`, fester Katalog `MOTIVE`, Motiv prüfen, „über Mitternacht" — nur Konstanten und reine Prüfungen (braucht nur `kalender_fehler`); Schreiben in `kalender_kennung` |
| `kalender_kategorie` | 2 | Gruppen (CATEGORIES, seit 2026-10-10): fester Katalog `KATEGORIEN` + keine/custom, prüfen/setzen, Anzeigename, ↔ .ics-Namen; Kurs-Schlüssel eines Titels (`titel_schluessel`, `KURZFORMEN`) — rein (braucht nur `kalender_fehler`) |
| `kalender_quelle` | 2 | Titel aus Liste/Projekt (seit 2026-10-10): Feld `quelle` {art: liste/projekt, id} prüfen (Form, Existenz), ↔ .ics (`X-ZENTRALE-QUELLE`, `URL:zentrale://fokus/…`), live auflösen = oberstes offenes Blatt (`listen_baum.ordnen`), leer/fehlt, an Ausgaben hängen (Listen einmal je Abruf über `lists.read_lists`), Auswahl für die Route |
| `kalender_deadline` | 2 | Termintyp deadline (seit 2026-10-20): Zeitpunkt mit Vorwarnung — Felder `typ`/`vorwarnung` prüfen/setzen, Dauer lesen („3d", „1d12h"), Rest bis zum Zeitpunkt, Vorwarn-Fenster, Text für Alarm und KI — rein (braucht nur `kalender_fehler`); Doku [kalender_deadline.md](../werkzeuge/kalender_deadline.md) |
| `kalender_fehler` | 2 | Unterstes Kalender-Modul ohne Kalender-Abhängigkeit: `CODES`, `KalenderAbgelehnt`, Uhrzeit- und Reihenfolge-Prüfung (damit kalender/kalender_kennung/kalender_bearbeiten ohne Import-Kreis dieselbe Ablehnung werfen) |
| `lists` | 2 | Listen-Registry (To-Do, Checklisten) |
| `notes` | 2 | Notiz-Registry des TUI-Notiz-Werkzeugs |
| `melodies` | 2 | Melodie-Registry des Klaviers |
| `graphs` | 2 | Lifestyle-Messreihen (≠ `graph`) |
| `cycle` | 2 | Zyklus/PMS-Vorhersage aus dem »periode«-Graphen |
| `mail` | 2 | Mail-Triage: IMAP rein, sortieren, zurückschreiben |
| `mail_rules` | 2 | Triage-Keymap (Sender → Ordner/Aktion) |
| `mail_oauth` | 2 | OAuth2 für Outlook.com-IMAP |
| `mail_secrets` | 2 | Verschlüsselter Speicher der Mail-Zugangsdaten |
| `mail_puffer` | 2 | Puffer des Mail-Panels (Live-Zählung, Ordner-Inhalte) und seine Hintergrund-Jobs |
| `news` | 2 | Persönliche Tagesschau: RSS und Briefing |
| `web` | 2 | Gegatete Internet-Pipe (Suche, Seite holen) |
| `embeddings` | 2 | Vektoren lokal (bge-m3) oder in der Cloud |
| `graph` | 2 | Konzept-Graph der KI (seit 18.08.2026 aus) |
| `gedaechtnis` | 2 | Das Datei-Gedächtnis, das die KI liest und fortschreibt (nach Themen: anlegen/ergänzen, Kataloge, Tagebuch, archivieren, Suche, Prompt-Kopf; liest den alten Aufbau bis zum Umzug mit) |
| `gedaechtnis_ablage` | 2 | Wie das Gedächtnis auf der Platte liegt: `themen/<thema>/`, Kopf im Format von Claudes Datei-Gedächtnis (name, description, metadata), Dateien finden, archivieren, INDEX.md, Ort einer Messreihe |
| `gedaechtnis_katalog` | 2 | Katalog-Einträge als Text: lesen, rendern, upsert, Dossier-Kopf setzen, Vorlagen |
| `gespraeche` | 2 | Chat-Gespräche auf der Platte: Ordner pro Gespräch, Datei pro Rechner, Ereignisse (nachricht/verwerfen), Liste, aktiv pro Rechner |
| `rueckmeldungen` | 2 | Bewertungen der KI-Antworten (gut/schlecht + Kommentar): eine jsonl pro Rechner, nur anhängen, das letzte Ereignis je Antwort gilt; mit Anbieter, Modell, Werkzeugen und Skills der Antwort |
| `chat_suche` | 2 | Suche quer durch alle Gespräche und das alte Transkript (search_chats, read_chat): normalisierte Wörter, Rang nach Dichte und Aktualität |
| `ascii_lib` | 2 | ASCII-Bibliothek für Bild-Marker |
| `audio` | 2 | HTTP-Client für Whisper und TTS |
| `telemetry` | 2 | Telemetrie-Aggregat PC + Pi |
| `anwesenheit` | 2 | Ist Sasha da, schaut er hin? |
| `hub_ereignisse` | 2 | Ereignisse an Apps schicken, die sie abonniert haben (HTTP POST, im Hintergrund, Fehler nur geloggt) |
| `takt` | 2 | Wann ZENTRALE von sich aus spricht |
| `ollama` | 2 | Anbindung an Ollama: Adresse, Modell, Kontext, Sampling, Erreichbarkeit, Warmup — einmal |
| `sandbox` | 2 | Code abgeschottet ausführen (bubblewrap): eigener Arbeitsordner, kein Netz, keine Dateien von Sasha, Zeit-/Speicher-/Ausgabe-Grenzen |
| `skills` | 2 | Skills der KI im Claude-Format (Ordner mit SKILL.md): Liste für den Prompt, laden samt Dateien, vorschlagen/ändern, an/aus, Erstbefüllung (eigene + Anthropic-Vorlagen) |
| `skill_format` | 2 | Das Skill-Format von Claude: SKILL.md mit YAML-Kopf lesen (auch fremde Felder) und schreiben, gültige Namen |
| `skill_umzug` | 2 | Umzug alter Skill-Dateien (`<name>.md`) ins Claude-Format, alte beiseite nach `_alt/`; „kurz“ → Hausregel |
| `skill_import` | 2 | Claude-Skills aus .zip oder Ordner übernehmen (Plugin, Skill-Ordner, SKILL.md in der Wurzel): sicher auspacken, prüfen, atomar in den Skill-Ordner, ganz oder gar nicht; nur aus Input/ |
| `ablage` | 2 | Die Ablage: Dokumente der KI, Sandbox-Dateien, Anhänge, Eingeworfenes — Ordner pro Dokument, jede Fassung eine neue Datei, nie löschen; Papierkorb als Feld, ersetzen, wem es gehört |
| `anhang` | 2 | Anhänge im Chat: Sperrliste, Art erkennen (PDF/Word als Original, Text dazu), in die Ablage; Verweise für den Verlauf der KI auflösen |
| `ablage_text` | 2 | Der Text einer PDF- oder Word-Datei (Anhang, Ablage-Vorschau), gemerkt nach Inhalt |
| `ablage_sichtbar` | 2 | Die Ablage als Ordner für Sasha: neueste Fassung als lesbare Datei, Einwurf (fremde Datei → Dokument), Änderung → Fassung, Umbenennen/Löschen nachziehen; Stand je Rechner |
| `ablage_suche` | 2 | Suchen in der Ablage: nach Titel (find_files), nach Text auch in PDF/Word/Excel (search_files), auflisten (list_files gross) — jede Suche sagt, wie vollständig sie war |
| `ablage_zip` | 2 | Eine Zip der Ablage ansehen oder auspacken: jede Datei ein Dokument (Sashas), ganz oder gar nicht |
| `tabelle_datei` | 2 | Excel (.xlsx) lesen/anlegen/ändern — openpyxl im begrenzten Kindprozess, Zip-Bomben-Prüfung, Verlust-Prüfung; CSV lesen/schreiben; Tabelle als Text |
| `textbloecke` | 2 | Kleines Markdown → Blöcke (Überschrift, Absatz, Liste, Tabelle, Code) und Stücke normal/fett — für PDF- und Word-Schreiber |
| `pdf_datei` | 2 | PDFs lesen (Text je Seite, Tabellen geraten, Formularfelder), zusammenfügen, Seiten herausnehmen — pypdf im begrenzten Kindprozess |
| `pdf_schreiben` | 2 | Neues PDF aus Markdown: A4, Grundschriften, Umbruch, Tabellen, Seitenzahlen — ohne Fremdbibliothek |
| `word_datei` | 2 | Word (.docx) lesen, aus Markdown anlegen, geänderte Kopie (ersetzen über Lauf-Grenzen, anhängen) — nur Standardbibliothek |
| `projekte` | 2 | Projekte: Rahmen für ein Thema mit Anweisungen und Wissensdateien im Gedächtnis, Block für den Prompt, Wissen lesen/hinzufügen (Sperrliste), archivieren |
| `modell_liste` | 2 | Welche Chat-Modelle ein Anbieter wirklich hat: vom Anbieter geholt, 24 h gecacht (pro Rechner unter `~/.cache`), Rückfall auf `providers.py` |
| `morgenblick_daten` | 2 | Was der Morgenblick weiß: Sammler je Quelle (Kalender, Mail, Erinnerungen, Gespräche, Listen, Projekte, Ablage), nur lesen, kein Netz; Form des Tages, drei Akte |
| `ehrlichkeit_erkennen` | 2 | Satzmuster in Antworten der KI: Erledigt-Behauptungen („hab ich eingetragen"), Zusagen („trag ich gleich ein"), Kalender-Kennungen — reines Python, auf wenige Falschtreffer gebaut |
| `quellen` | 2 | Quellen-Zeile eines Zugs: welche Seiten tatsächlich gelesen wurden (Browser: wo die KI stehen blieb oder browser_read; fetch_url; fetch_document per URL — nie web_search), aus den Werkzeug-Ergebnissen |
| `selbstauskunft` | 2 | Die Felder der KI am Werkzeug `antwort` (gross): `erledigt` (Bereiche), `fragt_erlaubnis`, `schiebt_auf`, `ungeprueft`, `auftrag`, `nicht_gefunden` — Vokabular der Bereiche, Schema, tolerant lesen; sprachfrei statt Wortlisten (seit 2026-10-10) |
| `klassifikator_beispiele` | 2 | Beispiele für einen späteren eigenen Klassifikator: je geprüfte Antwort eine Zeile (Sätze, Selbstauskunft, Befunde, Protokoll) in `data/klassifikator_beispiele/<YYYY-MM>-<knoten>.jsonl`, nur anhängen, nur lokal; Einstellung `beispiele_sammeln` (seit 2026-10-10) |
| `zusagen` | 2 | Offene Zusagen der KI je Gespräch: eine Datei pro Rechner im Gesprächsordner, nur abhaken, nie löschen |
| `browser_sitzung` | 2 | Ein Browser ohne Fenster (Chromium über Playwright) in eigenem Thread: je Gespräch eine Sitzung, Seite als Text + nummerierte Elemente, klicken/tippen/zurück, Bild; nur erlaubte Hosts, nie das eigene Netz, keine Downloads, 10 min Leerlauf → zu; im Prüfstand nur die Adressen des Falls (`nur_erlauben`) |
| `morgenblick_bild` | 2 | Der Morgenblick als HTML: Gelände-SVG, Akte, Listen — deterministisch, alles escaped, Fraunces eingebettet |
| `desk` | 2 | Desk View: eine `.canvas`-Datei (JSON Canvas 1.0) pro Desk in `desk_ordner` (Standard `data/desk/`): auflisten, anlegen, laden in Zellen (1 Spalte = 10 px, 1 Zeile = 20 px), ganz speichern mit `stand`-Schutz, umbenennen, löschen (seit 2026-10-10); Fremdes in der Datei bleibt stehen |
| `desk_bild` | 2 | Bilder auf dem Desk: aus `~/Zentrale/Input` (oder einem Pfad) nach `<desk_ordner>/bilder/` kopieren, nur echte Bilder; Vorschau über `bild_vorschau` mit „weg"/„kein bild"; was die TUI zum Öffnen braucht (Pfad, `bild_betrachter`) |
| `werkstatt` | 2 | Werkstatt (seit 2026-10-10): selbst gebaute Apps aus Vorlagen — `<apps_ordner>/<slug>/app.toml` (dasselbe Manifest wie Prozess-Apps, ohne `start`, mit `vorlage`/`desk`) + `icon.png` aus einem Bild in Input/ (über `bild_vorschau`); anlegen, umbenennen, Symbol ändern, löschen; Kurzname prüfen (reserviert, vergeben); Desks umbenennen/löschen mit Blick auf Apps, die auf sie zeigen |
| `app_verwaltung` | 2 | Prozess-Apps des Hubs (seit 2026-10-22): Liste für `GET /api/apps` (läuft?), starten, nur Eigenes stoppen (Marken im Laufzeit-Ordner überleben den Hot Reload), Autostart mit dem Backend (`autostart = true`, Einstellung `apps_autostart`) |
| `app_installation` | 2 | Apps aus dem Schaufenster installieren (seit 2026-10-25): git-Repo aus `downloadUrl` holen (Zwischenlager, vorhandener Checkout desselben Repos wird übernommen), app.toml prüfen, Ansichten zur Wahl; einrichten mit den gewählten Ansichten (über `app_register`, `apps`, `shop`) |
| `app_weiterleitung` | 2 | Routen-Weiterleitung (seit 2026-10-22): Pfad → App laut `routen` im `app.toml`, Anfrage unverändert an ihre `adresse`, Antwort unverändert zurück; aus → 503 `aus` |
| `kachel_http` | 2 | Kachel-Quelle hinter HTTP (seit 2026-10-22): Katalog aus `[kachel.<art>]` im `app.toml`, Fragen an `/hub/kachel*` der App mit 0,5 s Budget — dieselbe Schnittstelle wie eine Quelle im Prozess |
| `kacheln` | 2 | Hub für Kacheln (seit 2026-10-10): Anfrage prüfen, Recht `<app>:lesen`, Quelle aus `QUELLEN` fragen (im Prozess, Anfrage/Antwort durch JSON wie über HTTP), kürzen, `stand`/`ttl`, zu klein/weg/aus; Aktion „oeffnen“ → `zeige` |
| `kachel_kalender` | 2 | Kachel-Quelle `kalender`/`ausschnitt`: Bereich fest oder mitlaufend (≤ 31 Tage), Woche bis 7 Tage, sonst Monatsraster; liest nur über `kalender.month_view`, schreibt nie; Spanne zwischen zwei Daten (≤ 31 Tage, „bis" nicht vor „von") in `pruefen()`, weil JSON Schema sie nicht ausdrücken kann |
| `kachel_fokus` | 2 | Kachel-Quelle `fokus`/`liste` (seit 2026-10-10): oberste Ebene einer Liste, gezeichnet NUR über `listen_bild` (kein eigener Look, seit 2026-10-11), blättern mit `oben`; `erledigte` = die abgeschlossenen zeigen, `tiefe` veraltet; Liste im Katalog frisch zur Wahl (`parameter_jetzt`); liest nur über `lists.read_lists`, schreibt nie |
| `kachel_graph` | 2 | Kachel-Quelle `graph`/`verlauf` (seit 2026-10-10): letzte N Tage eines Graphen als Blockbalken, letzter Wert, min/max; Graph im Katalog frisch zur Wahl (`parameter_jetzt`); liest nur über `graphs.list_graphs`/`read_values` |
| `shop` | 2 | Schaufenster (seit 2026-10-10): Katalog als schema.org-`ItemList` (JSON-LD, `core/shop_katalog.jsonld`, Tauschstelle `_katalog_roh` für Sashas Server), Kategorien/Themen, ein Stück je Adresse `zentrale://shop/<kategorie>/<id>`; holen (heute nur Preis 0) schreibt `OwnershipInfo` in `<shop_ordner>/besitz-<rechner>.jsonld`, Besitz = Vereinigung aller Rechner |
| `ai` | 3 | Ollama-Weg, Tool-Liste und -Ausführung, Erlaubnis-Abfrage, Prompt-Bausteine |
| `ai_backends` | 3 | Wer denkt: lokal oder Cloud, Anbieter, Modell, Effort, Rundengrenze |
| `cloud` | 3 | Anthropic-Weg |
| `cloud_openai` | 3 | OpenAI-kompatibler Weg |
| `werkzeug_schleife` | 3 | Die eine Tool-Schleife aller Wege |
| `profil` | 3 | Prompt-Schienen klein und gross, Modell-Profile darüber (`profil/modelle/`, z. B. qwen) |
| `consolidation` | 3 | Nach dem Zug: Transkript (und Graph-Extraktion, wenn an) |
| `erlaubnis` | 3 | Das Erlaubnis-Gate: die Tür, durch die die Schleife fragt (Regeln und Fragen stehen im Werkzeug-Register); Geltungsbereiche einmal / dieses Gespräch / immer |
| `ki_antwort` | 3 | Fertige Antwort: Bild-Marker ziehen, Zug zum Merken vormerken |
| `ki_prompt` | 3 | Prompt-Bausteine für jeden Weg: Jetzt-Block, Imprint, Alarme, Denk-Heuristik, Schalter |
| `ki_einstellungen` | 3 | Chat-Einstellungen (Anbieter, Modell, Effort, Budget, Weg) lesen und mit Klartext-Prüfung setzen — für `/api/ai/einstellungen` |
| `ki_werkzeuge` | 3 | Was ein KI-Werkzeug tut: ausfuehren(name, args) → Kalender, Notizen, Netz, Mail, Messreihen |
| `werkzeug_register` | 3 | Ein Eintrag pro KI-Werkzeug: Schema, Beschreibung je Schiene, Erlaubnis-Regel + Frage; die Ausführer melden sich aus `ki_werkzeuge` an |
| `werkzeug_suche` | 3 | Werkzeug-Suche (`search_tools`): Index aus dem Register + Skills, BM25, Treffer mit Gruppe, Freischaltung im Zug und über Züge hinweg, Index als MCP-Liste (seit 2026-10-14) |
| `werkzeug_nachschlagen` | 3 | Register-Einträge der Nachschlage-Werkzeuge (explain_error, read_series, search_tools); hinten ans Register gehängt |
| `werkzeug_eintrag` | 3 | Wie ein Werkzeug-Eintrag aussieht (die Klasse `Werkzeug`), damit Einträge auch außerhalb des Registers stehen können |
| `werkzeug_pdf_word` | 3 | Einträge und Fragen der PDF-/Word-Werkzeuge (Skills pdf, word); hinten ans Register gehängt |
| `werkzeug_gedaechtnis` | 3 | Register-Einträge der Gedächtnis-Werkzeuge seit dem Umbau nach Themen (`archive_note`); hinten ans Register gehängt |
| `werkzeug_browser` | 3 | Einträge und Fragen der Browser-Werkzeuge; Erlaubnis je Host und Gespräch; hinten ans Register gehängt |
| `ki_browser` | 3 | Was die Browser-Werkzeuge tun: Seite als Text für die KI (Adresse als Beleg, Inhalt = Daten), Liste, Suchen, Bild in die Ablage |
| `ki_pdf_word` | 3 | Was die PDF-/Word-Werkzeuge tun: Quelle (Ablage oder Datei), lesen, neue Datei in die Ablage, nachlesen mit Beleg |
| `werkzeug_ablage` | 3 | Die Ablage als Quelle des Werkzeug-Erzeugers: Schemas von replace_document, trash_document, restore_document und ihr Gate (Sashas Dokumente: jedes Mal fragen) |
| `ki_ablage_adapter` | 3 | Adapter der Ablage für den Erzeuger: ersetzen (neu + alt in den Papierkorb), wegräumen, zurückholen; Fragen und Sätze |
| `werkzeug_tabelle` | 3 | Einträge und Gate von read_xlsx, create_xlsx, edit_xlsx (Skill excel); hinten ans Register |
| `ki_tabelle` | 3 | Was die Tabellen-Werkzeuge tun: Werte/Formeln prüfen, anlegen, ändern (ersetzen, daneben, CSV-Fassung), nachlesen mit Beleg |
| `werkzeug_dateien` | 3 | Einträge und Fragen von find_files, search_files, import_skill, unzip (alles Ablage) und die gross-Fassung von list_files/read_file |
| `ki_dateien` | 3 | Was find_files, search_files, import_skill, unzip tun; list_files/read_file auf gross lesen die Ablage |
| `werkzeug_fragen` | 3 | Die Ja/Nein-Fragen an Sasha vor bestätigungspflichtigen Werkzeugen und die Regeln, die von den Argumenten abhängen |
| `ki_kalender` | 3 | Der Kalender, wie die KI ihn liest: Kennungen (`#r3f9c`), alle Felder, Warnungen frisch, Belege nach dem Schreiben |
| `ki_kalender_aendern` | 3 | Die schreibenden Kalender-Werkzeuge der KI: genau EIN Eintrag, nur genannte Felder, mit Beleg und Status |
| `werkzeug_erzeuger` | 3 | KI-Werkzeuge aus dem Schema einer Quelle ERZEUGEN (seit 2026-10-10): Aktions-Schemas in MCP-Form + Adapter → Register-Einträge (gross) mit derselben Schutzschicht (Schema-Prüfung, Gate-Frage aus Feldern, Nachlesen, Zurücknehmen, feste Satzform, Bereich, Zuschnitt je Modellprofil); Einstellung `werkzeuge_erzeugt`; seit 2026-10-11 auch der ALLGEMEINE Adapter für Anbindungs-Beschreibungen (JSON Schema, MCP/HTTP-Transport, Stufen, Probefahrt; Einstellung `anbindung_<name>`, Standard aus) |
| `werkzeug_kalender` | 3 | Die Aktions-Schemas des eigenen Kalenders (erste Quelle des Erzeugers): Termine, Routinen, Pausen, Phasen, Gruppe, Ebene |
| `ki_kalender_adapter` | 3 | Adapter des Kalenders für den Erzeuger: jede Aktion auf `kalender_kennung`, was nachgelesen dastehen muss, Rückbau, Sätze |
| `ehrlichkeit` | 3 | Live-Prüfer eines Zugs: Tat gegen Wort, Kennungen, „nicht da", „nicht gefunden" nach nur einer Stichwortsuche (Korrekturrunden bis bestanden, höchstens `pruefer_runden`, danach Warnungen), „frag nicht, tu" und „Aufschub eines Auftrags" (je eine Runde, keine Warnung), Erledigt-Zeile aus dem Werkzeug-Protokoll, offene Zusagen in den Kontext-Umschlag; Selbstauskunft gegen Protokoll, Widerspruch zur Wortliste → „unsicher" (Klassifikator); Einstellung `ehrlichkeit_pruefer` |
| `ehrlichkeit_kalender` | 3 | Nachprüfung nach Kalender-Schreibaufrufen (seit 2026-10-22): von/bis/ende ohne Grundlage in Sashas Text (eine Runde, dann Warnung) und Behauptungen gegen die echten Aufrufe (Ebene vielleicht, Deadline, Anzahl, Zeitspanne); von `ehrlichkeit.befunde` gerufen |
| `auftrag_abrechnung` | 3 | Auftrags-Abrechnung (Feld `auftrag` an `antwort`): „erledigt" gegen das Werkzeug-Protokoll, „offen" mit sicherem Teil → eine Runde, fehlende Abrechnung bei mehreren Aufträgen (sprachfrei erkannt) → eine Runde; Zeile „offen: …" für Sasha (seit 2026-10-10) |
| `klassifikator` | 3 | Satzarten (`behauptung_tat`, `erlaubnisfrage`, `aufschub` …) und Deckung hinter einer Schnittstelle: Wortlisten (Rückfall), günstiges Cloud-Modell (Ja/Nein, gecacht, über `billig`), lokal vorbereitet; nur bei „unsicher" gefragt, Einstellung `klassifikator` (Standard aus) (seit 2026-10-10) |
| `kern` | 3 | Der eine Einstieg: kern.chat(verlauf) wählt den Weg (lokal/Anthropic/OpenAI) und fährt ihn |
| `billig` | 3 | Ein Einmal-Aufruf beim billigen Modell des aktiven Anbieters (beide Dialekte, Kosten gebucht) — Graph-Extraktor, Gesprächstitel |
| `gespraech_titel` | 3 | Gesprächstitel: sofort aus den ersten Wörtern, nach der ersten Antwort vom billigen Modell |
| `morgenblick` | 3 | Morgenblick auf Abruf: sammeln, billiges Modell schreibt Sätze (JSON, Daten nie Anweisung; ohne Cloud feste Sätze), Seite in die Ablage; signierte Knöpfe → neues Gespräch |
| `mobil_kontext` | 3 | Kontextpaket fürs Handy (`data/mobil/kontext.json`): fester Cloud-System-Prompt + Anbieter/Modell/Effort, beim Abgleich abgelegt, nie Schlüssel |
| `main` | 4 | Event-Loop |
| `brain` | 4 | Input → neue Events |
| `actions` | 4 | Events → Nebenwirkungen |
| `clock` | 4 | Uhrzeit-Events |
| `sensors` | 4 | Sensor-Simulation |
| `hot_reload` | 4 | Hot Reload fürs Backend |
| `takt_treiber` | 4 | Der Takt-Thread: fragt `takt`, spricht über den KI-Kern ins Gespräch „Erinnerungen“, meldet |
| `ablage_wache` | 4 | Thread: alle 3 s `ablage_sichtbar.abgleichen()` (Einstellung `ablage_wache`) |

Schicht 5 liegt außerhalb von `core/` und steht deshalb nicht in der
Tabelle, sondern im nächsten Abschnitt.

## Routen (Schicht 5)

Seit 2026-10-06 hat jede Gruppe von HTTP-Routen ein eigenes Modul. Vorher
standen alle 89 Routen in `ui/app.py` (2.400 Zeilen), und jede Änderung,
egal woran, ging durch dieselbe Datei.

- `ui/app.py` legt nur die App an, hängt die Bereiche ein (`routen.einhaengen`)
  und startet. **Hier steht keine Route** — der Test prüft das.
- `ui/routen/<bereich>.py` hält die Routen eines Bereichs als Flask-Blueprint
  `bp`. Jedes Modul steht in `ui/routen/__init__.py` unter `BEREICHE` — der
  Test prüft auch das, sonst gäbe es Routen, die nie eingehängt werden.
- `ui/routen/gemeinsam.py` hält, was mehrere Bereiche brauchen (Pfad zu
  `data/`, die 503-Antwort für „keine KI").
- Routen sind **dünne Adapter**: Anfrage lesen, Kern fragen, Antwort formen.
  Zustand, Caches und Hintergrund-Threads gehören in den Kern.

| Bereich | Was |
|---|---|
| `zustand` | State-Polling, Sensor-Webhook, Telemetrie, Aussenposten-Pakete |
| `erfassung` | Data-Collection, `/api/log`, Lifestyle-Graphen, Zyklus |
| `klavier` | Melodien |
| `listen` | Listen, Einträge, Projekte |
| `notizen` | Block-Notizen |
| `kalender` | Kalender; Stand des Google-Syncs (`/api/calendar/sync`) |
| `ki` | Chat-Stream, Wiederholen, Stoppen, Verlauf, Erlaubnis, Status, Backend-Wahl, Einstellungen, Devtools |
| `gespraeche` | Gesprächs-Liste, neu, öffnen, laden, umbenennen, archivieren; Bewertungen der Antworten |
| `stimme` | Sprechen und Zuhören |
| `mail` | Mail-Triage |
| `skills` | Skills der KI (Liste, an/aus) und das Gedächtnis für Sasha: Kernakten, Bereiche, Kernakte ändern |
| `ablage` | Ablage: Liste, Dokument lesen, archivieren; Anhänge annehmen |
| `projekte` | Projekte: Liste, anlegen, laden, Anweisungen ändern, Wissen hinzufügen, archivieren, Gespräch zuordnen |
| `morgenblick` | Morgenblick erstellen, Knopf einlösen (nur localhost, signiert) |
| `abgleich` | Zustand des Abgleichs über die Mitte (letzter Lauf, Fehler, Hinweise) |
| `desk` | Desk View: Desks auflisten, anlegen, laden, ganz speichern (409 bei Änderung von woanders), umbenennen, löschen (über `werkstatt`, 2026-10-10) |
| `kachel` | Kacheln: Inhalt einer Kachel holen, Aktion weiterreichen (über `core/kacheln.py`, seit 2026-10-10) |
| `hub_apps` | Apps des Hubs (seit 2026-10-22): `GET /api/apps`, Start/Stopp, und die Weiterleitung der Pfade, die eine App laut `routen` besitzt (über `core/app_verwaltung.py`, `core/app_weiterleitung.py`; hängt direkt nach `zugang` ein) |
| `shop` | Schaufenster: Katalog, Kategorien/Themen, ein Stück, holen, Besitz (über `core/shop.py`, seit 2026-10-10) |
| `werkstatt` | Werkstatt: eigene Apps auflisten, Namen prüfen, bauen, ändern, löschen; Vorlagen, Bilder fürs Symbol (über `core/werkstatt.py`, seit 2026-10-10) |

## Türen

Eine Front wohnt im selben Repo, gehört aber nicht zum Kern. Was sie aus dem
Kern importieren darf, steht hier und **nur** hier. Apps (seit 2026-10-09 der
Sprach-Tutor) wohnen in eigenen Repos und importieren gar nichts von hier —
umgekehrt importiert hier niemand ein Modul namens `tutor` (der Test prüft
das für `core/`, `ui/`, `tui/`, `scripts/`).

| Bereich | Darf aus dem Kern | Warum |
|---|---|---|
| `tui/` | `theme`, `tone`, `pc_status`, `listen_baum`, `listen_bild`, `graph_reihen`, `stil`, `tastentabelle`, `uhr` | Reine Helfer ohne Kern-Abhängigkeit. Alles andere holt die TUI per HTTP von den Routen (`ui/routen/`). `listen_baum`/`graph_reihen` seit 2026-10-10: Ansicht und Kachel rechnen dasselbe; `listen_bild` seit 2026-10-11: Ansicht und Kachel zeigen dasselbe Bild einer Liste; `stil` seit 2026-10-10: Farbwähler und Stylebox prüfen CSS wie das Backend; `tastentabelle` seit 2026-10-11: TUI und Hub lesen Tastentabellen gleich; `uhr` seit 2026-10-20: dieselbe Uhr und derselbe Tageswechsel wie das Backend; alle stehen in `deploy/aussenposten.txt`. |
| `zentrale_cli/` | `abgleich`, `abgleich_apps`, `abgleich_mitte`, `abgleich_schluessel`, `adapter`, `adapter_ablauf`, `adapter_bruecke`, `adapter_geheim`, `adapter_vdirsyncer`, `ai_config`, `cloud_api`, `cloud_nutzung`, `dateien`, `kalender_einstellung`, `kalender_sync_zustand`, `knoten`, `konto`, `mobil_kontext` | Der Befehl `zentrale` (seit 2026-10-22) ist eine Front wie `scripts/abgleich.py`: er bedient Konto, Abgleich, Gerät und (seit 2026-10-24) den Adapter direkt, ohne laufendes Backend (er läuft auch, bevor es eines gibt). `mobil_kontext`: `sync --automatic` ist der Timer und frischt wie `scripts/abgleich.py` das Handy-Paket auf. Rechnen und Netz bleiben im Kern; hier stehen nur Fragen, Ausgabe und Texte (`zentrale_cli/texte.py`). |

Mit Apps redet der Hub nur über HTTP: starten und stoppen
(`core/app_verwaltung.py`, `POST /api/apps/<name>/start|stop`, Autostart mit
dem Backend; das Zimmer des Tutors über `scripts/open_tutor_room.py`, beide
mit den Handgriffen aus `core/app_prozess.py`), Routen weiterreichen
(`core/app_weiterleitung.py`, `routen` im `app.toml`), Kacheln holen
(`core/kachel_http.py`), Ereignisse schicken (`core/hub_ereignisse.py`).

Die Tür der TUI **wächst nicht mehr** (Wächter E2 seit 2026-10-22,
`TUI_TUER_HOECHSTENS` im Test): jedes Modul darin muss von `tui/` benutzt
werden, keins darf einer ausgezogenen App gehören, und ein neues kommt nicht
dazu — die TUI holt Fach-Bild und -Zahl über HTTP
([kern_auszug_inventur.md](../hub/kern_auszug_inventur.md) E2).

### Ausgezogene Apps

Module dieser Namen importiert in `core/`, `ui/`, `tui/`, `scripts/`
**niemand** (Wächter E1, `tests/test_kern_bauplan.py`), und in `core/` gibt
es sie nicht mehr. Eine App zieht aus → Zeile hier, im selben Commit.

| Modulname | Repo | seit |
|---|---|---|
| `tutor` | `language-tutor` | 2026-10-09 |
| `karte`, `map`, `glossary` | `zentrale-karte` (vorher `core/map/`, `core/glossary.py`, `ui/routen/karte.py`, `scripts/map_window.py`) | 2026-10-22 |

## Altlasten

Was am 05.10.2026 schon gegen die Regeln verstieß. Die Listen dürfen nur
schrumpfen: der Test meldet eine erledigte Altlast und verlangt, sie hier
auszutragen. Neues kommt nie hinzu — wer eine neue Ausnahme braucht, löst
das Problem statt es einzutragen.

### Altlast: Kreis-Kanten

Ein Import-Kreis heißt: A braucht B, B braucht A — auch über Umwege.

**Keine mehr.** Am 2026-10-05 verbanden 15 Kanten sechs Module des KI-Kerns
zu einem Knoten (`ai`, `ai_backends`, `cloud`, `cloud_openai`,
`consolidation`, `werkzeug_schleife`). Ursache: `ai.py` war ab Mai 2026 die
einzige KI-Datei und wurde zum Ersatzteillager; jeder neue Teil wurde
daneben gebaut und bediente sich dort. Am 2026-10-06 in fünf Schritten
aufgelöst (`memory/ki/kern_aufbau.md`, K1–K5): Ollama-Anbindung, Merken,
Erlaubnis, Antwort, Prompt-Bausteine und Werkzeuge bekamen je ein eigenes
Modul, und `kern.chat` wurde der eine Einstieg. Die Tabelle bleibt für den
Test stehen; ein neuer Kreis wird rot und darf hier NICHT eingetragen werden.

| Kante | Wofür |
|---|---|

### Altlast: Türen

Keine mehr — die letzte (`ui/app.py → tutor.debug`) ist am 2026-10-06
gelöst; seit 2026-10-09 ist der Tutor ganz ausgezogen. Die Tabelle bleibt für
den Test stehen.

| Weg | Wofür |
|---|---|

### Altlast: Riesen

Grenze: eine Funktion über 250 Zeilen, eine Datei über 1.500 Zeilen (in
`core/`, `ui/`, `tui/`). Die Zahl rechts ist **eingefroren**: der
Riese darf nicht wachsen, und wenn er schrumpft, wird die Zahl hier gesenkt.
Sasha, 05.10.2026: einfrieren, dann zerlegen (Punkt 3).

| Wo | Zeilen höchstens |
|---|---|
| `core/mail.py` | 1924 |

## Wenn der Test rot wird

- **„steht nicht im Bauplan"** — neues Modul in die Tabelle *Module*, in die
  niedrigste Schicht, deren Regel es erfüllt.
- **„Abhängigkeit nach OBEN"** — das Gebrauchte eine Schicht tiefer ziehen,
  oder es als Argument hereingeben.
- **„Neuer Import-Kreis"** — was beide brauchen, in ein eigenes, tieferes
  Modul ziehen. Nicht als Altlast eintragen.
- **„Tür umgangen"** — TUI: über eine Route in `ui/routen/` gehen. Zu einer
  App: nie per Import, nur per HTTP (`hub_ereignisse`, Starter).
- **„Riese gewachsen"** — das Neue in eine eigene Funktion oder Datei legen.
  In der TUI heißt das: eine eigene Ansicht in `tui/ansichten/`
  ([tui_bauplan.md](tui_bauplan.md)).
- **„Gut gemacht — kleiner geworden"** — die Zahl oben senken oder die Zeile
  streichen. Das ist der Sinn der Sache.
