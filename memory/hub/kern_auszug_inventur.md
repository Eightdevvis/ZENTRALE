# Kern-Auszug — Inventur: was in der TUI rechnet, was als App auszieht

**Stand 2026-10-22, nur gelesen, nichts umgebaut.** Anlass, Sasha: ZENTRALE
läuft auf jedem erdenklichen Format (Android, Browser, Tablet, Pi-Vollbild,
AR/StardustXR …). Daraus zwei Regeln ([hub_bauplan.md](hub_bauplan.md)
„Leitlinie: überall deploybar"): (1) jede Funktion steht hinter einer
Schnittstelle (HTTP), die TUI ruft nur; (2) der Kern wird leer, die Module
ziehen als Apps aus — wie der Tutor.

**Stand der Umsetzung:** D Schritt 1 (Hub-Grundlagen) gebaut 2026-10-22 —
`GET /api/apps`, Start/Stopp/Autostart, Routen-Weiterleitung, Kachel-Quelle
über HTTP, Wächter E1, E2, E4 ([hub_bauplan.md](hub_bauplan.md) „Apps
starten, stoppen, weiterreichen"). Die Zahlen unten sind der Stand VOR dem
Umbau.

**Gemessen, nicht geschätzt:** Import-Graph per AST über `core/ ui/ tui/
scripts/ tests/` (Importe in Funktionen mitgezählt), dazu grep auf
Datei-Zugriffe, Prozesse und `/api/`-Aufrufe. Nicht gezählt: was die Sitzungen
`qwen-kalender`, `shortcut-leiste`, `cloud-server`, `cloud-client` gerade
bauen (`konto.py`, `HttpMitte`, `zentrale`-CLI).

## Zahlen vorweg

| Was | Wert |
|---|---|
| Kern `core/` | 184 Module, ~67.900 Zeilen |
| davon Hub (Abschnitt C) | ~55 Module, ~11.200 Zeilen |
| davon muss raus | ~129 Module, ~56.700 Zeilen |
| Routen | 171 (145 Pfade) in 25 Bereichen |
| davon in `openapi.yaml` beschrieben | 21 Pfade (Kachel, Desk, Shop, Werkstatt, Tasten) — Listen, Kalender, Graphen, Notizen: **nicht** |
| TUI `tui/` | ~31.100 Zeilen |
| Import-Tür `tui/ → core/` | **hält**: nur `theme tone pc_status listen_baum listen_bild graph_reihen stil tastentabelle uhr` |

Die Logik steckt also nicht in verbotenen Importen, sondern **in der TUI
selbst** — vor allem im Kalender (14 Dateien, 6.148 Zeilen). Und ein
Kern-Modul heute „im Prozess" ist für einen Dart-/JS-Knoten unerreichbar,
auch wenn es rein ist (`listen_bild`, `graph_reihen`).

## A. Logik nur in der TUI

Größe = Aufwand, sie hinter eine Route zu ziehen: S (eine Stelle + Test), M (Route + mehrere Dateien + Tests), L (mehrere Sitzungen).

| # | Stelle | Was dort gerechnet/entschieden wird | Route heute / fehlt | Größe |
|---|---|---|---|---|
| A1 | `tui/ansichten/kalender_werkzeuge.py:1078–1300`, Ausführer `kalender_bedienung.py:590–640` | **Ändern = Folge von bis zu 7 Schreib-Aufrufen** (`typ` vorher, `PUT eintrag/routine`, `kategorie`, `stil`, `quelle`, `typ` nachher, `ebene`); „einmal → Wiederholung/Spanne" = neu anlegen + alten löschen (`:1092–1104`). Bricht ein Aufruf mittendrin ab: **kein Zurückrollen**, halber Stand bleibt | fehlt: **eine Änderung = ein Aufruf**, ganz oder gar nicht (z. B. `PUT /api/calendar/eintrag/<kennung>` mit allen Feldern; `kalender_kennung` kann Kennungs-Schreiben schon) | L |
| A2 | `kalender_werkzeuge.py:40–150` (`zeit`, `dauer`, `datum`, `wochentage`, `regel_text`), `kalender_phasen.py:42–86` (`regel_lesen`, `regel_bauen`), `kalender_advanced.py:74` (Kopie von `core/kalender_deadline.dauer_lesen`) | Eingaben lesen („9.30", „+2h", „14.10." = nächstes ab heute, „mo-fr"), RRULE bauen und vorlesen | fehlt: Rohtext an den Kern (`POST /api/calendar/lesen` für Vorschau/Fehlersatz), RRULE nur im Kern | M |
| A3 | `kalender_ansichten.py:88–115` | `KURZFORMEN`/`titel_schluessel` — erklärte **Kopie** von `core/kalender_kategorie` (Test hält beide gleich) | `/api/calendar` liefert `kurs` je Eintrag | S |
| A4 | `kalender.py:105–131`, `kalender_ansichten.py:157` `farben_vergeben` | feste Kursfarbe, **je Gerät** in `~/.local/state/zentrale/kalender_farben.json` — Handy/Browser vergeben anders | fehlt: Farbplatz je Kurs im Kalender selbst (abgeglichen), Antwort trägt den Platz | M |
| A5 | `kalender_deadline.py:36–120` | `VORWARNUNG_STANDARD` (Kopie), `rest_minuten`, `stufe` — Vorwarn-Stufe einer Deadline | `/api/calendar` liefert `rest`/`stufe` (Kern hat `im_fenster`, `rest_text`) | S |
| A6 | `kalender_ansichten.py:443–520` `_normiere`, `_tag_eintraege` | Regeln, was an einem Tag steht: Ausfall/deaktiviert ausblenden, eintägige Spanne = Termin, „einzelne Uhrzeit am letzten Spannentag = Ende", Deadline ohne Ende, Reihenfolge | `/api/calendar` liefert die normierte Tagesliste | M |
| A7 | `kalender_motive.py:25, 86–130` | `EBENE = "rhythmus"` (Kopie), Phasen eines Tages auflösen | Teil von A6 | S |
| A8 | `tui/ansichten/fokus.py:145–310` (`l_desc_view`, `l_container`, `l_vitems`, `l_forest_targets`) | erledigt/gesamt zählen, Anzeige-Reihenfolge, Pfad kürzen, Einordnen-Ziele ohne eigenen Teilbaum — über `listen_baum` **im Prozess**; Zyklus prüft der Server zusätzlich (400) | `GET /api/lists` liefert Rohbaum; Zählungen/Reihenfolge/Ziele fehlen | M |
| A9 | `fokus.py:178, 1010, 1196` | **Das Bild der Liste per Import `listen_bild`**. Browser/Handy kommen nur über `/api/kachel` an die *oberste* Ebene; Ebene mit Pfad, Auswahl, „nur erledigte" gibt es nicht über HTTP | fehlt: `POST /api/kachel` mit `pfad`/`auswahl`/`erledigte` (oder `GET /api/lists/<lid>/bild`) — **Voraussetzung für den Listen-Auszug** | M |
| A10 | `tui/ansichten/graphen.py:117–145` `_vorhersage_tage` | Schätzwerte für Lücken (Mittel der letzten 7) — nur im Client; `/predict` setzt nur das Flag | fehlt: Server liefert Schätzwerte (`_pred`) | S |
| A11 | `graphen.py:31, 50, 86` | `GRAPH_TYPES` doppelt zu `graphs.VALID_TYPES`; Zyklus-Fenster → Tage (`cycle_axis`) | `/api/graphs/typen`, `/api/cycle` liefert Tage | S |
| A12 | `graphen.py:585–613`, `basis.py:88` `parse_clock` | Wert je Typ prüfen (HH:MM → Minuten, period von/bis) — `/api/log` prüft **nichts** | Prüfung in die Graph-Route | S |
| A13 | `graphen.py` Überlagerung vs. `core/kachel_graph.bild` | zwei Zeichner für denselben Graphen — Regel „Programm und Kachel teilen EIN Bild" ([listen_app.md](listen_app.md)) verletzt | ein `graph_bild` wie `listen_bild`, Route wie A9 | M |
| A14 | `tui/ansichten/notizen.py:150–210`, `27–66` | Block-Modell im Client: ids vergeben (`next_block/next_item/next_term`), Einträge anlegen/löschen, dann **ganze Notiz per PUT ohne `stand`** (letzter gewinnt); `n_float_pos` = „Spiegel von core.notes" | fehlt: Block-Aktionen oder PUT mit `stand` → 409 (wie Desk) | M |
| A15 | `tui/ansichten/app_start.py:34–66` | **TUI startet die App** als Unterprozess (`scripts/open_tutor_room.py`) | fehlt: `POST /api/apps/<name>/start|stop` | M |
| A16 | `tui/ansichten/startseite.py:34` `RAD_APPS` | feste App-Liste im Client; nur eigene Apps kommen vom Backend | fehlt: `GET /api/apps` (alle, mit Symbol) | S |
| A17 | `einstellungen.py:45` `GRUPPEN`, `verlauf.py:27` `NAMEN` | Werkzeug → Wort → Gruppe, doppelt zu `core/werkzeug_gruppen` | `/api/ai/werkzeuge` liefert `gruppe`, `wort` | S |
| A18 | `projekte.py:43` `MAX_DATEI` | Kopie von `core/projekte.MAX_WISSEN_BYTES` | Grenze in der Antwort/Fehlersatz | S |
| A19 | `karte.py:102–126` `m_time_step` | Zeitachse klemmen aus min/max der Layer-Antwort | unkritisch (Bedienung) | S |

**Kein Befund** (Oberfläche, darf so): Chat (nur SSE), Post (alles über
`/api/mail`), Klavier (Notensatz und Ton am Gerät, Melodien über
`/api/melodies`), Desk (JSON Canvas ganz speichern mit `stand`), Technik,
Geräte-Einstellungen unter `~/.config/zentrale`, Datei zum Hochladen lesen
(`chat_ablage`, `projekte`), Zwischenablage, Bildbetrachter. Die TUI-Doku
nennt `kalender_werkzeuge` noch ausdrücklich „reine Logik … daraus
Backend-Aufrufe" ([tui_bauplan.md](../system/tui_bauplan.md) Zeile 61) —
das widerspricht der Leitlinie vom 22.10.

**Nebenbefund Routen, Sicherheit (sofort, unabhängig vom Auszug):**
`ui/routen/erfassung.py:33–45, 150–181` — `/api/data/<id>` und `/api/log`
setzen die id ungeprüft in `data/<id>.json`. `GET /api/data/ai_config`
liefert `data/ai_config.json` (**API-Schlüssel**); Zugang steht standardmäßig
auf „melden" (`core/zugang.py:35`), das Backend lauscht auf `0.0.0.0` → aus
dem LAN lesbar. `POST /api/log` mit `category="../…"` schreibt außerhalb von
`data/`, mit `ai_config` überschreibt es die Einstellungen. Außerdem schreibt
`/api/log` selbst, nicht atomar, als zweite Schreibstelle neben
`graphs.log_value`. Reparatur S: id nur, wenn Graph oder Kategorie.

## B. App-Kandidaten

Fan-in = wer außerhalb der Gruppe importiert (ohne Tests). Fan-out = was die
Gruppe aus dem übrigen Kern braucht.

### Karte — sauberster Kandidat

| | |
|---|---|
| Dateien | `core/map/` (558 Z. Python + 29 MB Daten), `ui/routen/karte.py`, `tui/ansichten/karte.py`, `scripts/map_window.py` (Fenster), `map_render_proto.py`, `ingest_shipdensity.py` |
| Daten | `core/map/data/` (im Repo) |
| Routen | 5 `/api/map/*` |
| KI / Kachel | — / — |
| Fan-in | `ui/routen/karte.py`, `scripts/map_window.py`, `scripts/map_render_proto.py` |
| Fan-out | **keins** (nur stdlib + numpy) |
| Tests | `test_map_layers`, `test_map_political`, `test_map_viina` |
| Urteil | lose. Hat schon eine Fenster-Ansicht als eigenen Prozess (wie das Tutor-Zimmer). **S** |

### Notizen (`core/notes.py`, nicht das KI-Gedächtnis)

Dateien `core/notes.py` (287), `ui/routen/notizen.py`, `tui/ansichten/notizen.py`
(666) · Daten `data/notes.json` · Routen 5 `/api/notes*` · KI: keins
(`read_note`/`write_note` sind das Gedächtnis) · Fan-in nur die Route · Fan-out
`dateien`, `datasync` · Test `test_notes` · **lose, S** (+ A14 M).

### Klavier

`core/melodies.py` (152), `core/tone.py` (in der TUI-Tür), `ui/routen/klavier.py`,
`tui/ansichten/klavier.py` (1.158) · `data/melodies.json` · 4 `/api/melodies*`
(auch `monolith.html`) · Fan-in Route + TUI(`tone`) · Fan-out `dateien`,
`datasync` · Tests `test_melodies`, `test_tone`, `test_backend_api` · **lose, S**;
Produkt-Inventur fragt, ob es überhaupt rein soll.

### Listen (`fokus`)

| | |
|---|---|
| Dateien | `core/lists.py` (875), `listen_baum.py` (153, Schicht 1), `listen_bild.py` (223, Schicht 1), `kachel_fokus.py` (129), `ui/routen/listen.py` (261), `tui/ansichten/fokus.py` (1.255) |
| Daten | `data/lists.json`, `data/features.json` (Sashas Tracker `l_zentrale`!) — beide in `abgleich_auswahl.py` |
| Routen | 16: `/api/lists*`, `/api/projects*` (auch `monolith.html`: 17× lists, 5× projects; Kalender-TUI: toggle/reorder/items) |
| KI | keins |
| Kachel | `fokus/liste` |
| Fan-in | `kacheln.py`; **`kalender_quelle.py`** (`read_lists` + `listen_baum.finden/ordnen/erledigt`, live bei jedem Kalender-Abruf); `morgenblick_daten.py` (`week_items`, `get_focus`); **`ui/routen/kalender.py:81`** (`weekplan`); Prüfstand `lauf.py:75` (`create_list`, `add_item`), `umgebung.py:120` (biegt `lists._REGISTRY` um); `tui/ansichten/fokus.py` |
| Fan-out | `dateien`, `datasync`, `adressen`, `kachel_form`, `kachel_parameter` |
| Geteilt | Kalender (Titel aus Liste, Wochenplan, ToDo-Kasten), Morgenblick |
| Tests | `test_lists`, `test_lists_uniform`, `test_listen_bild`, `test_kacheln_fokus_graph`, `test_tui_bernstein`, `test_desk_kacheln`, `test_kalender_quelle`, `test_openapi`, `test_pruefstand_pruefungen`, `test_werkzeug_kalender_erzeugt`, `test_kalender_bedienung_tui`, `test_kalender_quellen_tui`, PTY `tests/tasten_zustaende/fokus.py`, Fake-Backend `tests/tui_schirm/backend.py` |
| Urteil | mittel. Eigene Logik schon sauber getrennt ([listen_app.md](listen_app.md)), aber vier Leser im Kern und die TUI-Ansicht hängt am Import-Bild (A8/A9). **M** |

### Graphen / Messreihen (`graph`) + Zyklus

| | |
|---|---|
| Dateien | `core/graphs.py` (263), `graph_reihen.py` (132), `kachel_graph.py` (268), `cycle.py` (284), `categories.py` (44), `ui/routen/erfassung.py` (182), `tui/ansichten/graphen.py` (1.245), `erinnerung.py`, `dashboard.py` |
| Daten | `data/graphs.json`; Werte **im Gedächtnis** `themen/<thema>/<name>.reihe.json` (seit 11.10., `graphs.reihe_pfad` → `gedaechtnis_ablage.reihe_finden`), sonst `data/g_*.json`; dieselbe Ablage nutzt die Datensammlung (`data/sleep_quality.json`) |
| Routen | 10: `/api/graphs*`, `/api/data/<id>`, `/api/log`, `/api/categories`, `/api/cycle`; dazu Zyklus-Marken **in** `/api/calendar` (`ui/routen/kalender.py:96`) |
| KI | `create_series`, `log_series`, `read_series` — greifen in **Privates**: `graphs._REGISTRY`, `graphs._values_path` (`ki_werkzeuge.py:465, 471, 529`) |
| Kachel | `graph/verlauf` (eigenes Bild, A13) |
| Fan-in | `kacheln.py`, `ki_werkzeuge.py`, `ui/routen/erfassung.py`, `ui/routen/kalender.py` (`cycle`), Prüfstand `umgebung.py`, `pruefstand_verhalten.py` (biegen `_DATA_DIR/_REGISTRY` um), TUI `basis.py`, `graphen.py` |
| Fan-out | **`gedaechtnis`, `gedaechtnis_ablage`** (Ablageort, Archivieren beim Löschen), `uhr`, `dateien`, `datasync`, `adressen`, `kachel_*` |
| Tests | `test_cycle`, `test_kacheln_fokus_graph`, `test_tui_cycle_axis`, `test_gedaechtnis_themen`, `test_backend_api`, `test_werkzeug_belege`, `test_reichweite_gross`, `test_fehlercodes`, `test_keine_seiteneffekte`, `test_openapi`, `test_desk_kacheln` |
| Urteil | **eng** mit dem KI-Gedächtnis und dem Kalender verflochten; Gesundheitsdaten (Zyklus) nur lokal. **L**, erst entflechten |

### Mail

`core/mail.py` (1.924, einziger eingefrorener Riese), `mail_rules`, `mail_oauth`,
`mail_secrets`, `mail_puffer` · Daten `mail_state.json`, `mail_rules.json`,
`mail_secrets.enc`, Zähler-Caches · 12 `/api/mail*` · KI `read_mail` · Fan-in
`ki_werkzeuge`, **`main.py`** (startet den Abholer), `morgenblick_daten`, Route ·
Fan-out `dateien`, `state` · Tests 3 · lose nach innen, aber Neubau ist geplant
(mbsync/notmuch) → **als neue App bauen statt umziehen, M–L**.

### News

`core/news.py` (875) · `news_digest.json`, `news_stories.json` · **keine Route** ·
KI `read_news` · Fan-in `ki_werkzeuge`, `main.py` · Fan-out `embeddings`, `web`,
`net`, `state` · **keine Tests** · seit Wochen unberührt. Erst klären, ob es
bleibt; sonst mit dem Assistenten. **M**

### Morgenblick

`morgenblick.py`, `morgenblick_daten.py`, `morgenblick_bild.py` (~1.050) +
`morgenblick_assets/` · 2 Routen · KI: billiges Modell · Fan-out **10**:
`ablage`, `ai_backends`, `billig`, `gespraeche`, `kalender`, `kalender_rhythmus`,
`lists`, `mail`, `projekte`, `state` · Tests `test_morgenblick`, `test_zugang`.
Sammler über alle → erst, wenn die Quellen HTTP + Rechte haben. **M, spät**

### Kalender

| | |
|---|---|
| Dateien | 21 Kern-Module (`kalender*`, `kachel_kalender`, `titel_wochentag`, 7.774 Z.) + 5 KI-Module (`ki_kalender*`, `werkzeug_kalender`, `ehrlichkeit_kalender`, 2.899 Z.) + `core/anbindungen/kalender_kern.json`; TUI 14 Dateien, 6.148 Z. |
| Daten | `data/ai_calendar.json`, `kalender_neben.json`, `data/kalender/**` (.ics-vdir), git-Spiegel außerhalb `data/` |
| Routen | 36 `/api/calendar*` |
| KI | `read_calendar`, `add_calendar_entry`, `add_calendar_routine`, `edit_calendar_routine`, `add_calendar_pause`, `delete_calendar_entry`, `edit_calendar_entry`, `read_calendar_warnings` + die erzeugten |
| Kachel | `kalender/ausschnitt` |
| Fan-in | 25: `ai`, `ki_prompt`, `ki_werkzeuge`, `werkzeug_register`, `werkzeug_fragen`, **`main`** (Alarme), `takt`, `morgenblick_daten`, `kacheln`, Route, 9 Skripte (Sync, Migration, Prüfstand) |
| Fan-out | `lists` + `listen_baum` (Quelle), `datasync`, `dateien`, `state`, `stil`, `uhr`, `ai_config`, `nutzer_angaben`, `adressen`, `kachel_*` |
| Tests | 42 |
| Urteil | am stärksten verflochten, Logik in der TUI (A1–A7), zwei Sitzungen bauen gerade daran. **L, nach Listen** |

### Desk, Werkstatt, Shop

`desk.py`, `desk_bild.py`, `bild_vorschau.py`, `werkstatt.py`, `shop.py` (+
`shop_katalog.jsonld`) · 23 Routen, in `openapi.yaml` · Fan-out `apps`,
`nutzer_ordner`, `adressen`. Werkstatt und Shop **sind** Hub (Apps holen,
bauen). Desk ist laut Sasha ein Baustein (Vorlage `desk` eigener Apps) →
**bleibt vorerst**, später Vorlagen-App.

### Ablage, Gedächtnis/Projekte/Skills, Assistent

- **Ablage** 15 Module, 4.165 Z. (`ablage*`, `anhang`, `pdf_*`, `word_datei`,
  `tabelle_*`, `textbloecke`, `zip_sicher`); Fan-in 19, fast alles KI-Werkzeuge.
  `ablage_ort` bleibt Hub (Abgleich).
- **Gedächtnis/Projekte/Skills** 3.451 Z.; Fan-in 17; trägt die Messreihen
  (siehe Graphen).
- **Assistent** ~55 Module (`ai`, `cloud*`, `kern`, `ki_*`, `werkzeug_*`,
  `ehrlichkeit*`, `klassifikator*`, `profil/`, `werkzeug_erzeuger/` …);
  `ki_werkzeuge` importiert Kalender, Mail, News, Graphen, Gedächtnis, Ablage.
  `takt`/`takt_treiber` (spricht von sich aus) gehören dazu. **Zuletzt** (Bauplan
  Schritt 4), mit Ablage und Gedächtnis zusammen.
- **Konzept-Graph** (`graph.py`, `consolidation`, `embeddings`) ist seit 18.08.
  aus, `cloud.py`/`ai.py` importieren ihn noch → Kandidat zum Löschen, nicht zum
  Umziehen.

### Sensorik

`sensors`, `anwesenheit`, `telemetry`, `host_metrics`, `pc_status`, `audio`,
`scripts/pi_sensor_bridge.py`, `services/` (Whisper, TTS) — **Hub-Dienst
„Sensoren"**, aber als abschaltbares Modul fassen (Sashas Hardware).

## C. Was der leere Kern behält

| Hub-Dienst ([hub_bauplan.md](hub_bauplan.md)) | heute | Lücke |
|---|---|---|
| Apps | `apps.py` (Manifest, Abonnenten), Start in `scripts/open_tutor_room.py` **und** in der TUI (`app_start.py`) | `GET /api/apps`, `POST /api/apps/<n>/start|stop`, Autostart mit dem Backend, **Weiterleitung** von App-Routen |
| Manifest + Rechte | `erlaubnis.py` (nur KI-Werkzeuge), `kacheln._recht` (Platzhalter) | Rechte je App (`fokus:lesen`) geprüft im Hub |
| Datenordner je App | `dateien.py`, `nutzer_ordner.py` | `daten/<app>/` fehlt; alles in `data/` |
| Ereignisse | `events`, `state`, `main`, `brain`, `actions`, `clock`, `uhr`, `hub_ereignisse` (nur `anwesenheit`) | `termin.beginnt`, `mail.neu`, `daten.geaendert` |
| Sensoren | Abschnitt B „Sensorik" | als Modul abschaltbar |
| Modell-Zugang | Anbieter, Preise, Verbrauch: `providers`, `prices`, `usage`, `ai_config`, `modell_liste`, `ollama`; der eigentliche Aufruf steckt in `cloud.py`/`cloud_openai.py` **zwischen** Prompt, Gedächtnis, Werkzeugen. `kern.fahrzeug/fahren` aus dem Bauplan **gibt es im Code nicht** | nackter Modell-Aufruf als eigenes Hub-Modul, Budget je App |
| Abgleich | `abgleich*`, `datasync`, `aussenposten`, `schreib_sicherung` | (Cloud-Sitzungen bauen) |
| Zugang | `zugang.py`, `ui/routen/zugang.py` | (Cloud-Sitzungen bauen) |
| Oberfläche | `kacheln`, `kachel_form`, `kachel_parameter`, `adressen`, `farbrollen`, `tastentabelle`, `stil`, `theme`, `werkstatt`, `shop`, Desk | Kachel-Quelle über HTTP; App-Ansichten ins Rad |
| Fundament | `net`, `melden`, `hot_reload`, `kidebug`, `sandbox` (Grundlage für fremde Apps), `zip_sicher`, `nutzer_angaben` | — |

**Muss raus** (≈129 Module, ≈56.700 Z.): alles `kalender*`/`ki_kalender*`,
`lists`/`listen_*`/`kachel_fokus`, `graphs`/`graph_reihen`/`kachel_graph`/`cycle`/`categories`,
`notes`, `melodies`/`tone`, `mail*`, `news`, `map/`, `morgenblick*`, `ablage*` + Datei-Module,
`gedaechtnis*`/`projekte`/`skill*`, der ganze Assistent (s. o.), `glossary`, `ascii_lib`,
`web`, `browser_sitzung`, `mobil_kontext`, `takt*`, Konzept-Graph.

## D. Reihenfolge

| # | Was | Warum jetzt | Größe |
|---|---|---|---|
| 0 | Nebenbefund Sicherheit (`/api/data`, `/api/log`) | Schlüssel aus dem LAN lesbar | S |
| 1 | **Hub-Grundlagen**: `GET /api/apps`, Start/Stopp, Autostart, **Routen-Weiterleitung** (Manifest `routen = ["/api/map"]` → Hub reicht Methode/Pfad/Body/Status unverändert an `adresse`; App aus → 503 `{"fehler":"aus"}`), Kachel-Quelle über HTTP, Grenz-Wächter E1–E4 | jede weitere App braucht genau das; alte Pfade bleiben, also bleiben TUI, `monolith.html` und `tests/tui_schirm` unverändert | M |
| 2 | **Karte** als Beweis-App | Fan-out 0, ein Routen-Modul, keine KI, keine Kachel, keine Daten im Abgleich, Fenster-Ansicht schon eigener Prozess → testet nur die Hub-Mechanik | S |
| 3 | **Listen (`fokus`)** | eigene Logik schon getrennt, keine KI; vorher A8/A9 im Kern | M |
| 4 | Notizen, Klavier | gleiche Schablone, je S (Notizen + A14) | S |
| 5 | Graphen + Zyklus | erst entflechten (unten) | L |
| 6 | Mail (Neubau als App), News (klären) | KI-Werkzeuge dann über Rechte | M–L |
| 7 | Kalender | nach den Kalender-Sitzungen; A1–A7 **vorher** in den Kern, sonst zieht die Logik der TUI mit um | L |
| 8 | Morgenblick | braucht HTTP aller Quellen | M |
| 9 | Ablage + Gedächtnis + Assistent | Bauplan Schritt 4 | L |

### Listen und Graphen heute Nacht als erste zwei?

**Nein.** Graphen gar nicht, Listen nicht als erste.

**Graphen nicht**, weil: die Werte liegen im KI-Gedächtnis (`themen/…reihe.json`,
Löschen = Gedächtnis-Archiv); die KI-Werkzeuge schreiben an `graphs._REGISTRY`/
`_values_path` vorbei an jeder Schnittstelle; `/api/log`/`/api/data` teilen die
Ablage mit der Datensammlung (`sleep_quality`) und haben die Lücke aus dem
Nebenbefund; der Zyklus speist `/api/calendar`; der Prüfstand biegt Modul-Variablen
um; die TUI rechnet die Vorhersage (A10) und zeichnet ein anderes Bild als die
Kachel (A13). Vorher nötig: Messreihen-Ort entscheiden (Gedächtnis oder
`daten/graph/`), KI-Werkzeuge auf öffentliche Funktionen/HTTP, eine
Schreibstelle, ein Bild, Zyklus-Marken per HTTP.

**Listen nicht als erste**, weil sie gleichzeitig drei neue Dinge bräuchte
(Weiterleitung, Kachel über HTTP, Bild über HTTP für die TUI) **und** vier Leser
im Kern umstellen müsste — zwei davon (`kalender_quelle.py`,
`ui/routen/kalender.py`) in Dateien, an denen die Kalender-Sitzungen gerade
arbeiten. Der richtige Erste ist **Karte** (Schritt 1+2); danach Listen.

### So zieht Listen aus (Schritt 3)

**Vorher im Kern, ohne Umzug (risikoarm, je mit Test):**
- A9: Bild einer Ebene über HTTP (`/api/kachel` mit `pfad`, `auswahl`,
  `erledigte`); A8: `GET /api/lists` liefert je Knoten `erledigt/gesamt`, die
  Anzeige-Reihenfolge und eine Route für Einordnen-Ziele. Danach liest
  `tui/ansichten/fokus.py` kein `listen_baum`/`listen_bild` mehr → beide aus der
  TUI-Tür und aus `deploy/aussenposten.txt`.
- Auflösen für den Kalender als Route: `POST /api/lists/aufloesen {quellen}` →
  `{titel, zustand, offene}` (ersetzt `listen_baum` in `kalender_quelle.py`).
- Prüfstand: Listen-Ort per Einstellung statt `lists._REGISTRY` umbiegen.

**Ziehen um** (neues Repo neben ZENTRALE, wie `language-tutor`, Paket `fokus/`):
`core/lists.py`, `core/listen_baum.py`, `core/listen_bild.py`,
`core/kachel_fokus.py` (→ HTTP-Handler `/hub/kachel`, `/hub/kacheln`,
`/hub/kachel/aktion`), `ui/routen/listen.py` (→ eigener Server, **dieselben**
Pfade `/api/lists*`, `/api/projects*`), Tests `test_lists`,
`test_lists_uniform`, `test_listen_bild`, Fokus-Hälfte von
`test_kacheln_fokus_graph`, Doku `listen_app.md` → `docs/`. Statt Hub-Importen:
Fehler als HTTP-Antwort (`kachel_form`), Parameter als festes JSON Schema
(`kachel_parameter`), Adresse mit `urllib.parse` (`adressen`), atomar schreiben
(`dateien`, 20 Zeilen eigen), `datasync.notify_change` entfällt (rsync/Mitte
sehen die Datei). `app.toml`: `start`, `adresse`, `routen`, `rechte = []`,
`liefert = ["kachel:liste"]`.

**Bleibt im Hub (Adapter):** Eintrag `fokus` in `kacheln.QUELLEN` → HTTP;
Weiterleitung `/api/lists*`, `/api/projects*`; `core/fokus_klient.py` (Schicht 2,
nur HTTP) für `morgenblick_daten` (`week_items`, `get_focus`), `ui/routen/kalender.py`
(`weekplan`), `kalender_quelle.py` (aufloesen); die TUI-Ansicht `fokus.py` als
Terminal-Ansicht (ruft nur HTTP).

**Daten bleiben liegen:** `data/lists.json`, `data/features.json` am alten Ort,
App findet sie per Einstellung (wie der Tutor `tutor/data`). Kein Eingriff in
`abgleich_auswahl.py` — daran arbeitet `cloud-client`.

**Was beweist, dass nichts kaputt ist:**
- vor dem Umzug Antworten aufzeichnen (`GET /api/lists`, `/api/projects`,
  `/api/projects/focused`, `POST /api/kachel`, `GET /api/kacheln` auf
  festem Testbestand) — danach **byte-gleich** über die Weiterleitung;
- unverändert grün in ZENTRALE: `test_kalender_quelle`, `test_morgenblick`,
  `test_desk_kacheln`, `test_kacheln`, `test_openapi`, `test_kalender_bedienung_tui`,
  `test_kalender_quellen_tui`, `test_tui_bernstein`, `test_fussleiste`,
  `test_tui_helpers`, PTY `tasten_zustaende/fokus.py`, `test_pruefstand_pruefungen`,
  `test_werkzeug_kalender_erzeugt`, `test_kern_bauplan` (Tür und Modultabelle
  geschrumpft);
- im App-Repo: die umgezogenen Tests + `test_fokus_grenze` (E3);
- neu im Hub: `test_hub_weiterleitung` (Status/Body durch, aus → 503),
  `test_kachel_http` (Antwort im Prozess = Antwort über HTTP).

**Was der Hub bieten muss:** Routen-Weiterleitung, Start mit dem Backend
(sonst fehlen Listen im Kalender, im Morgenblick, in `monolith.html`),
Kachel-Quelle über HTTP mit 0,5-s-Grenze, `GET /api/apps`; Ereignisse braucht
Listen nicht (Kalender und Morgenblick ziehen).

**Risiken:**
1. Prüfstand biegt heute `lists._REGISTRY` um — stimmt der neue Weg nicht,
   **schreibt der Prüfstand in Sashas echte Listen** (inkl. `l_zentrale`).
2. Zweiter Prozess: läuft `fokus` nicht, verlieren Kalender-Titel, Wochenplan
   und Morgenblick ihre Listen → überall „aus" statt Fehler, Rückfall-Titel.
3. Konflikte mit den Kalender-Sitzungen (`kalender_quelle.py`,
   `ui/routen/kalender.py`) → erst nach deren Merge anfassen.
4. Pi als Fern-TUI: jeder Tastendruck in der Liste ein Hin und Zurück über
   WLAN → Ebene einmal ganz holen, Auswahl/Scrollen macht die Oberfläche.
5. Backend-Hot-Reload startet die App nicht mit neu.

## E. Grenz-Wächter

| # | Test | erzwingt |
|---|---|---|
| E1 | `test_kern_bauplan` erweitern: Liste ausgezogener Apps (`map`, `lists` …); `core/`, `ui/`, `tui/`, `scripts/` importieren keinen dieser Namen (wie heute für `tutor`) | Hub importiert keinen App-Code |
| E2 | TUI-Tür schrumpft nur: jede Zeile der Tür braucht einen Grund; App-eigene Helfer (`listen_*`, `graph_reihen`) fliegen beim Auszug raus | TUI holt Fach-Bild/-Zahl über HTTP |
| E3 | je App (im App-Repo, Vorlage `language-tutor/tests/test_tutor_grenze.py`): Importe nur eigene Wurzel + stdlib + Allowlist aus `requirements.txt`; kein `sys.path` auf `../ZENTRALE`; Dateipfade nur unter dem eigenen Datenordner | eine App, eine Wurzel |
| E4 | jede Route der TUI steht in `openapi.yaml` (AST über `api_call(...)`/`_plan(...)`-Pfade in `tui/` ↔ Pfade der Datei); heute 21 von 145 Pfaden beschrieben → Altlasten-Liste, die nur schrumpfen darf | ein Dart-/JS-Knoten kann jede Funktion aus der Doku bauen |
| E5 | keine Kopien in `tui/`: Kommentar „wie core/…"/„KOPIE von core" oder Konstanten gleich einem Kern-Wert → rot (heute A3, A5, A7, A2, A18) | keine zweite Wahrheit |
| E6 | eine Nutzer-Aktion = höchstens EIN schreibender Aufruf (Plan-Bauer der Kalender-TUI prüfen); Ausnahmen in einer Altlasten-Liste | ganz oder gar nicht liegt im Kern |
| E7 | keine Daten-Datei in `tui/`: `open(...,"w")`/`json.dump`/`os.replace` nur auf Allowlist (Log, Geräte-Einstellungen unter `~/.config|~/.local/state/zentrale`, Zwischenordner); `kalender_farben.json` (A4) als Altlast | Oberfläche hält keinen Fach-Zustand |
| E8 | Routen-Besitz: jeder Pfad gehört dem Hub oder genau einer App laut `routen` im Manifest; Weiterleitung nur dorthin | keine Route ohne Besitzer |

E1, E2, E5, E7 sind reine Lese-Tests und laufen in einer Sekunde; E4 und E6
brauchen eine Altlasten-Tabelle wie die Riesen in
[bauplan_kern.md](../system/bauplan_kern.md).
