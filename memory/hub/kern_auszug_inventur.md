# Core extraction — inventory: what computes in the TUI, what moves out as an app

**Stand 2026-10-31 (re-measured, docs only, no code changed):** Done since the
first inventory (22.10.): the security hole in `/api/data`, `/api/log`
(`a4c4872`), hub basics (`15d4aa1`: `/api/apps`, start/stop/autostart, route
forwarding, tiles over HTTP, guards E1/E2/E4), the map as its own app
(`db9e40b`, repo `zentrale-karte`), calendar colours from the core (A3, A4,
`fff210d`). Beside that the hub grew a lot that the old inventory did not know:
the building kit (ports, wires, Run gate, plug dialog, bundle, keeper, dev
mode, Schematix), the adapter, account/cloud. **Nothing else moved out**: core
is 263 modules / 76,700 lines (was 184 / 67,900), the TUI door is unchanged
(9 modules), 78 TUI routes still have no description (was 81). The TUI logic
rows A1, A2, A5–A19 are all still open; A5 grew (Muss/Soll mode).
**Recommended next step:** D step 3 — make Lists ready to move *inside* the
core (A8, A9, a resolve route for the calendar, Prüfstand by setting) plus the
cheap guards E5/E7/E8; recipe in [list_extraction_plan.md](list_extraction_plan.md).
Two hub gaps every later app needs are now named and placed in D: **apps
bring their own AI tools and skills** (section F) and **a generic frame for
local device adapters** (section G). Since 2026-10-31 (`7b0bab0`, Sasha,
permanent) **apps live outside the core**: no new app is built into it, and
the built-in apps of `core/eingebaute_apps.py` are a legacy list that may only
shrink (CLAUDE.md, [bauplan_kern.md](../system/bauplan_kern.md) "Altlast:
Built-in apps"). Decisions only Sasha can make: section H.

**Why (Sasha, 2026-10-22):** ZENTRALE runs on every conceivable format
(Android, browser, tablet, Pi full screen, AR/StardustXR …). Two rules follow
([hub_bauplan.md](hub_bauplan.md) "Leitlinie: überall deploybar"): (1) every
function sits behind an interface (HTTP), the TUI only calls; (2) the core
becomes bare, the modules move out as apps — like the tutor. Since 30.10. the
building kit says the same from the consumer side: "Everything else —
calendar, lists, notes, graphs, assistant, desk, workshop, mail, piano, tutor,
map, wiring map — is a package" ([building_kit_plan.md](building_kit_plan.md)
3.1). This file is the measured basis for deciding the order.

**Measured, not estimated (2026-10-31):** AST import graph over `core/ ui/
tui/ scripts/` (imports inside functions counted; fan-in without tests),
`@…route` decorators in `ui/` for routes, the path keys of `openapi.yaml`,
grep for file access, processes and `/api/` calls, plus reading each row's
code. Script kept outside the repo (`/tmp/inventur_2026-10-31/measure.py`).
"Hub" vs "must move" is a classification by module name (list in section C);
it is a judgement, the line counts are exact. `mobile/` was not measured
(⚠ prüfen: the phone app has its own copies, e.g. `mitte/regeln.dart`, see
[app_motor_plan.md](app_motor_plan.md) "Warum").

## Numbers

| What | 2026-10-22 | 2026-10-31 |
|---|---|---|
| Core `core/` (all `.py`, packages counted per file) | 184 modules, ~67,900 lines | **263 modules, 76,706 lines** |
| of which hub (section C) | ~55 modules, ~11,200 lines | **97 modules, 19,185 lines** — the building kit, adapter, account/cloud added ~40 modules |
| of which apps to extract per the legacy list of 31.10. (Schematix 7, Werkstatt 1, Desk app 3 — ⚠ prüfen: which of `desk`, `desk_bild`, `bild_vorschau` is the Desk *building block* that stays) | — | up to 11 modules, 2,569 lines → **tiny core ≈ 86–89 modules, ~16,600–17,600 lines** |
| of which must move | ~129 modules, ~56,700 lines | **166 modules, 57,521 lines** (map left, calendar colours came) |
| of which AI tool machinery that should stay hub (section F) | — | 13 units, 7,352 lines (still counted under "must move") |
| Routes in `ui/` | 171 (145 paths) in 25 areas | **192 (160 paths) in 25 route modules**; the map's 5 are forwarded now |
| paths in `openapi.yaml` | 21 | **48**; 41 of the 160 backend paths described: apps, schematix, wires, pieces, werkstatt, shop, desk, kachel(n), tasten. Calendar, lists, graphs, notes, mail, AI: **none** |
| TUI routes without description (E4 legacy list) | 81 | **78** (only the map left, 23.10.) |
| TUI `tui/` | ~31,100 lines | **33,798 lines**, 94 files (Schematix view ~1,200 new) |
| Calendar in the TUI | 14 files, 6,148 lines | **15 files, 6,495 lines** |
| TUI → core import door | `theme tone pc_status listen_baum listen_bild graph_reihen stil tastentabelle uhr` | **unchanged** (guard E2 holds it) |

Size of the groups that move (core only): calendar 29 modules / 12,058 lines,
memory+projects+skills 30 / 9,958 (6,497 of it skill templates), Ablage and
file formats 14 / 4,054, mail 5 / 3,272, concept graph 3 / 2,497 (off since
18.08.), lists 4 / 1,380, Schematix 7 / 1,282, Morgenblick 3 / 1,049, graphs 5 / 991.

The logic still does not sit in forbidden imports but **in the TUI itself**,
mostly in the calendar. A core module "in process" stays unreachable for a
Dart/JS node even when it is pure (`listen_bild`, `graph_reihen`).

## A. Logic only in the TUI

Size = effort to pull it behind a route: S (one place + test), M (route +
several files + tests), L (several sessions). Line numbers checked 2026-10-31.

| # | Place | What is computed/decided there | Route today / missing | Size | Stand 2026-10-31 |
|---|---|---|---|---|---|
| A1 | `tui/ansichten/kalender_werkzeuge.py:1117–1290` (`formular_bearbeiten`), executor `kalender_bedienung.py:590–690` | **Editing = up to 7 write calls** (`typ` before, `PUT eintrag/routine`, `kategorie`, `stil`, `quelle`, `typ` after, `ebene`); "once → recurring/span" = create new + delete old. An abort mid-way leaves half a state, **no rollback** | missing: **one change = one call**, all or nothing | L | open, unchanged — **bug risk** |
| A2 | `kalender_werkzeuge.py:40–150` (`zeit`, `dauer`, `datum`, `wochentage`, `regel_text`), `kalender_phasen.py:42–86` (`regel_lesen`, `regel_bauen`), `kalender_advanced.py:80` `_dauer_lesen` (copy of `core/kalender_deadline.dauer_lesen`) | read input ("9.30", "+2h", "14.10.", "mo-fr"), build and read RRULE | missing: raw text to the core (`POST /api/calendar/…` preview/error sentence), RRULE only in the core | M | open, unchanged |
| A3 | `kalender_ansichten.py` `KURZFORMEN`/`titel_schluessel` | copy of `core/kalender_kategorie` | `/api/calendar` carries `colour.key` | S | **done `fff210d`** ([calendar_colours.md](../werkzeuge/calendar_colours.md)) |
| A4 | course colours per device in `~/.local/state/zentrale/kalender_farben.json` | phone/browser would assign differently | `data/calendar_colours.json` (synced), answer carries `colour.slot`; the core migrates the old file once (`core/calendar_colours.py:345`) | M | **done `fff210d`** |
| A5 | `kalender_deadline.py` `VORWARNUNG_STANDARD`, `SOLL_TAGE` (copies), `rest_minuten`, `stufe`, and since 24.10. **`soll_anwenden`/`modus_anwenden`/`verpasst`** (Muss/Soll mode, `c0b1368`, `3cd1467`) | warning stage of a deadline; where a Soll copy stands, "soll verpasst" | missing: `/api/calendar` delivers `rest`/`stufe`/Soll position (core has `im_fenster`, `rest_text`, `SOLL_HOECHSTENS`) | S → **M** | open, **grew** |
| A6 | `kalender_ansichten.py:376–450` `_normiere`, `_tag_eintraege` | what stands on a day (cancelled/disabled hidden, one-day span = event, end rules, order) | missing: normalised day list from `/api/calendar` | M | open, unchanged |
| A7 | `kalender_motive.py:25` `EBENE = "rhythmus"` (copy), resolving phases | part of A6 | — | S | open, unchanged |
| A8 | `tui/ansichten/fokus.py` (`l_desc_view`, `l_container`, `l_vitems`, `l_forest_targets`) via `listen_baum` **in process** | done/total counts, display order, path, "file into" targets | `GET /api/lists` gives the raw tree; counts/order/targets missing | M | open, unchanged |
| A9 | `fokus.py:27–28` imports `listen_bild` | **the picture of the list in process**; `/api/kachel` only reaches the *top* level (`core/kachel_fokus.py` has no `pfad`/`auswahl`) | missing: tile/picture with `pfad`, `auswahl`, `erledigte` — **precondition for moving Lists** | M | open, unchanged |
| A10 | `graphen.py:117` `_vorhersage_tage` | estimates for gaps (mean of last 7); `/predict` only sets the flag | missing: server delivers estimates | S | open, unchanged |
| A11 | `graphen.py:33, 50` `GRAPH_TYPES`, `cycle_axis` | duplicate of `graphs.VALID_TYPES`; cycle window → days | `/api/graphs/typen`, `/api/cycle` with days | S | open, unchanged |
| A12 | `graphen.py:596–602`, `basis.py:88` `parse_clock` | value per type checked in the client; `/api/log` checks only that the category is known (since `a4c4872`), not the value | check in the graph route | S | open (route half: category check done) |
| A13 | `graphen.py` overlay vs `core/kachel_graph.bild` | two painters for one graph — breaks "program and tile share ONE picture" | one `graph_bild` like `listen_bild` | M | open, unchanged |
| A14 | `tui/ansichten/notizen.py:47, 150–210` | block model in the client (`next_block/next_item`), whole note **PUT without `stand`** (last wins), `n_float_pos` mirrors `core.notes` | missing: block actions or PUT with `stand` → 409 | M | open, unchanged |
| A15 | `tui/ansichten/app_start.py:13–66` | TUI starts the tutor via `scripts/open_tutor_room.py` as a subprocess | `POST /api/apps/<n>/start|stop` **exists** (`15d4aa1`), `app_oeffnen.py` uses it for store apps; key `u` still runs the starter. ⚠ prüfen: opening the room window is device UI (may stay), starting the tutor *server* should go through the route | M → S | **half done** |
| A16 | `tui/ansichten/startseite.py:34` `RAD_APPS` | fixed app list in the client | `GET /api/apps` **exists** and feeds store apps into the wheel (`eigene_apps.py:58`, since 25.10.); built-ins still fixed | S | **half done** |
| A17 | `einstellungen.py:45` `GRUPPEN`, `verlauf.py:27` `NAMEN` | tool → word → group, duplicate of `core/werkzeug_gruppen` | `/api/ai/werkzeuge` delivers `alltag` but no `gruppe` | S | open |
| A18 | `projekte.py:43` `MAX_DATEI` | copy of `core/projekte.MAX_WISSEN_BYTES` | limit in the answer/error sentence | S | open, unchanged |
| A19 | `karte.py` `m_time_step` | time axis clamp | — | S | **gone with the map** (`db9e40b`) |
| A20 | `tui/ansichten/schematix_draht.py` `fits`, `misfit` (new, building kit step 15, `9c6cc74`) | socket fit rule, "same rule as `core/schematix_run.fits`" — a documented copy for the red ✕ while drawing; the gate stays in the core | e.g. `GET /api/schematix/map` carries the fit table | S | new, accepted for now (convenience only, compiler decides) |

**No finding** (surface, may stay): chat (SSE only), mail view (all over
`/api/mail`), piano (note rendering and sound on the device, melodies over
`/api/melodies`), Desk (JSON Canvas saved whole with `stand`), Schematix map
(laid by `GET /api/schematix/map`, whole board back by `PUT`), technical
views, device settings under `~/.config/zentrale`, reading a file for upload,
clipboard, image viewer. [tui_bauplan.md](../system/tui_bauplan.md) line 61
still calls `kalender_werkzeuge` "reine Logik … daraus Backend-Aufrufe" —
contradicts the rule of 22.10.; fix it when A1/A2 move.

**Side finding security (22.10.):** `/api/data/<id>` and `/api/log` took any
id → **fixed `a4c4872`** (only known categories/graphs, test
`tests/test_erfassung_grenzen.py`). Still open from that finding: `/api/log`
writes non-atomically as a second write path beside `graphs.log_value`
(`ui/routen/erfassung.py:162–200`), and the backend listens on `0.0.0.0`
(`ui/app.py:90`) with access mode "melden" by default (`core/zugang.py:35`) →
decision H1.

## B. App candidates

Fan-in = who outside the group imports it (core/ui/tui/scripts, no tests).
Fan-out = what the group needs from the rest of the core. Measured 2026-10-31.

**Moved out:** tutor (`language-tutor`, 09.10.), **map** (`zentrale-karte`,
`db9e40b`, 22./23.10.; `core/map/`, `glossary`, `ui/routen/karte.py`,
`scripts/map_window.py` gone; listed in [bauplan_kern.md](../system/bauplan_kern.md)
"Ausgezogene Apps"). Both are still wired in by hard-coded entries, not via
the store ([store_tutor_map_migration.md](../open/store_tutor_map_migration.md)).
Budget (`budgeter`) is the first app installed through the store.

### Lists (`fokus`) — next

| | |
|---|---|
| Files | `core/lists.py` (875), `listen_baum.py` (153), `listen_bild.py` (223), `kachel_fokus.py` (129), `ui/routen/listen.py` (17 routes), `tui/ansichten/fokus.py` (1,255) |
| Data | `data/lists.json`, `data/features.json` (Sasha's tracker `l_zentrale`!) |
| AI | none |
| Fan-in | 6: `kacheln.py` (`kachel_fokus`), **`kalender_quelle.py`** (`lists` + `listen_baum`, live on every calendar fetch), `morgenblick_daten.py`, **`ui/routen/kalender.py`** (`weekplan`), Prüfstand `umgebung.py:134` (bends `lists._DATA_DIR`), `lauf.py`; plus the TUI door (A8/A9) |
| Fan-out | `adressen`, `datasync`, `dateien`, `kachel_form`, `kachel_parameter`, `state` |
| Verdict | unchanged since 22.10.: own logic cleanly separated, no AI, but four readers in the core and the TUI hangs on the in-process picture. **M**. Recipe: [list_extraction_plan.md](list_extraction_plan.md) |

### Notes (`core/notes.py`, not the AI memory) · Piano

- **Notes:** `notes.py` (287), `ui/routen/notizen.py` (5), `tui/ansichten/notizen.py`
  (666) · `data/notes.json` · AI none · fan-in **0** · fan-out `datasync`,
  `dateien`, `state` · **loose, S** (+ A14 M). Unchanged since 22.10.
- **Piano:** `melodies.py` (152), `tone.py` (355, in the TUI door),
  `ui/routen/klavier.py` (4), `tui/ansichten/klavier.py` (1,158) · fan-in 0
  (only the own TUI view uses `tone`) · fan-out `datasync`, `dateien`, `state` ·
  **loose, S**; whether it belongs in the product at all: decision H4.

### Graphs / series + cycle

| | |
|---|---|
| Files | `graphs.py` (263), `graph_reihen.py` (132), `kachel_graph.py` (268), `cycle.py` (284), `categories.py` (44), `ui/routen/erfassung.py` (10 routes), `tui/ansichten/graphen.py` (1,245) |
| Data | `data/graphs.json`; values **in the AI memory** `themen/<topic>/<name>.reihe.json` (`graphs.reihe_pfad`), else `data/g_*.json`; `data/sleep_quality.json` shares the store |
| AI | `create_series`, `log_series`, `read_series` — still reach **private** `graphs._REGISTRY`, `graphs._values_path` (`ki_werkzeuge.py:467, 473, 531`) |
| Fan-in | 6: `kacheln.py`, `ki_werkzeuge.py`, `ui/routen/kalender.py` (`cycle` marks in `/api/calendar`), TUI `basis.py` (`graph_reihen` via the door), Prüfstand `pruefstand_verhalten.py:74–75`, `umgebung.py:121–124` (bend `_DATA_DIR`/`_REGISTRY`) |
| Fan-out | **`gedaechtnis`, `gedaechtnis_ablage`**, `uhr`, `dateien`, `datasync`, `adressen`, `kachel_form`, `kachel_parameter`, `state` |
| Verdict | unchanged: **tightly bound** to the AI memory and the calendar; health data (cycle) local only. **L**, untangle first (D step 9) and decide H2 |

### Schematix (wiring map) — built-in app, measured on request of the building-kit session

| | |
|---|---|
| Files | `core/schematix_{kinds,map,pieces,run,scheme,store,versions}.py` (7 modules, 1,282), `ui/routen/schematix.py` (10 routes, all in `openapi.yaml`), `tui/ansichten/schematix{,_arten,_bild,_draht}.py` (~1,200), contract `contracts/schematix/1/` |
| Data | `data/schematix/**` (synced) |
| Registered | built-in app in `core/eingebaute_apps.py:45` (`titel`, `daten`) and `:105` (`needs: [data→sync]`) |
| AI / tile | none / none |
| Fan-in | **0** in the core; the TUI wheel knows it by name (`startseite.py` `ERSCHAFFEN_APPS`, `rad_wahl.py`, `fenster.py`, `zentrale_tui.py`) |
| Fan-out | 18 core modules: wiring (`wires`, `sketch_compiler`, `generations`, `port_types`, `formats`), apps/store (`apps`, `app_register`, `eingebaute_apps`, `shop`), account/sync (`abgleich`, `abgleich_apps`, `konto`, `knoten`, `datasync`, `dateien`), `desk`, `ai_config`, `i18n`; TUI: the shared canvas `tui/bausteine/canvas.py` |
| Open item | [schematix_extraction.md](../open/schematix_extraction.md) (`7b0bab0`: built into the core by mistake on 30.10.) |
| Verdict | clean on the inbound side (fan-in 0, all routes described), heavy on the outbound side — but those are hub services it is *meant* to use. Target ([building_kit_plan.md](building_kit_plan.md) 3+4): **own package, preinstalled at signup like the cloud, deselectable and holdable.** Dependencies that stay in the core and may only be used through their public interface: the Desk canvas block (`tui/bausteine/canvas.py`) and the wiring modules (`wires.py`, `sketch_compiler.py`, `generations.py`, `port_types.py`). Before the move: its in-process imports of `apps`, `shop`, `konto`, `abgleich`, `desk` need HTTP or public functions (⚠ prüfen which already have routes). **M.** Timing: only after the current Schematix restyle and the canvas navigation rework are merged — the building-kit session says when the code is quiet |

### Mail · News · Morgenblick

- **Mail:** `core/mail*` 5 modules, 3,272 lines (`mail.py` 1,924, the only
  frozen giant), 12 routes, AI `read_mail`, fan-in `ki_werkzeuge`, `main.py`
  (fetcher), `morgenblick_daten`. Rebuild planned (mbsync/notmuch) →
  **build as a new app instead of moving, M–L.** Unchanged.
- **News:** `news.py` (875), no route, AI `read_news`, fan-in `ki_werkzeuge`,
  `main.py`, **no tests**, untouched for weeks → decision H3.
- **Morgenblick:** 3 modules, 1,049 lines, 2 routes, fan-out 10 (all sources).
  Collector over everything → **only when the sources have HTTP + rights. M, late.**

### Calendar

| | |
|---|---|
| Files | 29 core modules, 12,058 lines (was 21+5 / ~10,700): `kalender*`, `ki_kalender*`, `kachel_kalender`, `titel_wochentag`, `werkzeug_kalender`, `ehrlichkeit_kalender`, new `calendar_colours` (432), `vevent_merge`; `core/anbindungen/kalender_kern.json`; TUI 15 files, 6,495 lines; `ui/routen/kalender.py` 34 routes (749 lines) |
| New since 22.10. | the calendar **source** is a setting of the calendar app (google / zencloud / local, `5f358a7`, via the adapter, [adapter.md](adapter.md)); phone reads and proposes changes over the Mitte (`afd35b1`, `32b89f6`); colours one rule in the core (`fff210d`); Muss/Soll mode (`c0b1368`) |
| AI | 17 calendar tools of 72 in the register (counted 2026-10-31); `core/anbindungen/kalender_kern.json` is the generator's only shipped description (its `kk_*` tools are not in the default register) |
| Verdict | still the most entangled; logic in the TUI (A1, A2, A5–A7) must go into the core **before** the move, else it moves with the TUI. **L, after lists, notes, graphs** |

### Desk, Werkstatt, Shop

`desk.py`, `desk_bild.py`, `bild_vorschau.py` (989 lines; fan-in `apps`,
`werkstatt`, `schematix_scheme`; fan-out `adressen`, `ai_config`, `datasync`,
`dateien`, `nutzer_ordner`, `werkstatt`), `werkstatt.py`, `shop.py`. Shop is
the store client = core. **Decided 2026-10-31** (`7b0bab0`): the Desk
*building block* (the canvas, `tui/bausteine/canvas.py`) stays in the core;
the `desk` and `werkstatt` *apps* are on the legacy list to extract.
⚠ prüfen: the cut through `desk.py`/`desk_bild.py` (storage and picture of a
desk — block or app?) is not drawn yet. Schematix and own apps use the block.

### Ablage, memory/projects/skills, assistant

- **Ablage** 14 modules, 4,054 lines; fan-in mostly AI tools. `ablage_ort`
  stays hub (sync).
- **Memory/projects/skills** 30 modules, 9,958 lines (incl. 6,497 lines of
  skill templates in `core/skill_vorlagen/`); carries the graph series.
- **Assistant** (`ai`, `cloud*`, `kern`, `ki_*`, `werkzeug_*`, `ehrlichkeit*`,
  `klassifikator*`, `profil/`, `zug*`, `takt*` …). `ki_werkzeuge.py` imports
  calendar, mail, news, graphs, memory, Ablage, web, sandbox, skills directly
  (`:24–43`). Which parts are hub and which belong to the apps: **section F**.
- **Concept graph** (`graph.py`, `consolidation`, `embeddings`, 2,497 lines)
  off since 18.08.; `cloud.py`/`ai.py` still import it → delete, don't move
  (decision H5).

### Sensors

`sensors`, `anwesenheit`, `telemetry`, `host_metrics`, `pc_status`, `audio`,
`scripts/pi_sensor_bridge.py`, `services/` — hub service "sensors", as a
switchable module. Port types now exist for the hardware (`mic`, `speaker`,
`display`, `gpio` …, `contracts/ports/1/types.json`); the adapters that
*offer* them do not (section G).

## C. What the bare core keeps

| Hub service | Today (2026-10-31) | Gap |
|---|---|---|
| Apps | `apps.py`, `app_prozess`, `app_weiterleitung`, `app_register`, `app_installation`, `app_verwaltung`, `app_update` (BUNDLE + holds), `builtin_store_apps` (cloud, cloud folder as store items, `79482b5`), `eingebaute_apps` (built-ins in transition); `GET /api/apps`, start/stop, autostart, forwarding (`15d4aa1`) | tutor/map still hard-coded ([store_tutor_map_migration.md](../open/store_tutor_map_migration.md)); downloaded apps cannot be uninstalled (501) ([store_app_lifecycle.md](../open/store_app_lifecycle.md)); **route ownership unchecked** (E8) |
| Manifest + rights | `needs`/`offers` as typed ports (`app_ports.py`, `contracts/ports/1/`), wires (`wires.py`, `/api/wires`), Run gate (`sketch_compiler`, `generations`), plug dialog at install (`plugs.py`, `plug_store.py`), `erlaubnis.py` (AI tools), `kacheln._recht` | old `rechte` words still granted without asking; ⚠ prüfen: an app's HTTP call into the hub is not checked against its wires at request time (no wire lookup in `ui/routen/zugang.py` or `app_weiterleitung.py`) |
| Data folder per app | `dateien`, `nutzer_ordner`; sync choice per app from `[daten]` (`abgleich_apps`, [cloud_app.md](cloud_app.md)) | no `daten/<app>/`; everything in `data/` |
| Events | `events`, `state`, `main`, `brain`, `actions`, `clock`, `uhr`, `hub_ereignisse` (only `anwesenheit`); port type `event` exists | `termin.beginnt`, `mail.neu`, `daten.geaendert` |
| Sensors / devices | section B "Sensors"; port types for hardware | **device-adapter frame (section G)** |
| Model access | `providers`, `prices`, `usage`, `ai_config`, `modell_liste`, `ollama`; port type `model` + plug; key per provider in the adapter | the call itself still sits in `cloud.py`/`cloud_openai.py` between prompt, memory and tools; no bare model call an app can use over HTTP; budget per app |
| AI tool machinery | generator, register, tool search, gate, skill loader — section F | **apps cannot bring tools or skills (F)** |
| Sync | `abgleich*`, `datasync`, `aussenposten`, `schreib_sicherung` | Mitte active only after `umstellen mitte` |
| Account / cloud / node | `konto*`, `cloud_api`, `cloud_notices`, `cloud_nutzung`, `knoten`, `key_rotation`, `account_ownership`, `cloud_folder` | [key_rotation_old_data.md](../open/key_rotation_old_data.md), [node_lifecycle_followups.md](../open/node_lifecycle_followups.md) |
| Adapter (outside services) | `adapter*` (5 modules, 1,471): connections + encrypted credentials, calendar bridge | only `kalender-vdirsyncer`, `ki-anbieter` (section G) |
| Building kit | `port_types`, `app_ports`, `wires`, `plugs`, `plug_store`, `generations`, `sketch_compiler`, `translators`, `formats` (9 modules, 1,812); `contracts/`; keeper timers, auto-update with self-test/self-heal, setup wizard (`zentrale_cli/wizard.py`), linger, dev mode (`devkit/`, `zentrale dev`) | [run_gate_followups.md](../open/run_gate_followups.md); rule: all writes to wiring owners only through the gate in `core/wires.py` |
| Surface | `kacheln`, `kachel_form`, `kachel_parameter`, `kachel_http`, `adressen`, `farbrollen`, `tastentabelle`, `stil`, `theme`, `i18n`, Shop, the Desk canvas block | Desk app, Werkstatt, Schematix are on the legacy list to extract (`7b0bab0`) |
| Foundation | `net`, `melden`, `hot_reload`, `kidebug`, `sandbox`, `zip_sicher`, `nutzer_angaben` | — |

**Must move** (166 modules, 57,521 lines; the classification used):
`kalender*`, `ki_kalender*`, `kachel_kalender`, `titel_wochentag`,
`calendar_colours`, `vevent_merge`, `lists`/`listen_*`/`kachel_fokus`,
`graphs`/`graph_reihen`/`kachel_graph`/`cycle`/`categories`, `notes`,
`melodies`/`tone`, `mail*`, `news`, `morgenblick*`, `ablage*` + file modules,
`gedaechtnis*`/`projekte`/`skill*`, the assistant (`ai`, `ai_backends`,
`billig`, `cloud`, `cloud_openai`, `kern`, `ki_*`, `werkzeug_*`,
`ehrlichkeit*`, `klassifikator*`, `profil`, `context`, `gespraech*`,
`chat_suche`, `transkript`, `zusagen`, `rueckmeldungen`, `selbstauskunft`,
`quellen`, `auftrag_abrechnung`, `zug`, `zug_ablauf`, `fehlercodes`), `ascii_lib`,
`web`, `browser_sitzung`, `mobil_kontext`, `takt*`, concept graph. Section F
takes ~7,350 lines of that back into the hub.

## D. Order

| # | What | Why at this place | Size | Stand |
|---|---|---|---|---|
| 0 | Security `/api/data`, `/api/log` | keys readable from the LAN | S | **done `a4c4872`** (rest: H1) |
| 1 | Hub basics: `/api/apps`, start/stop, autostart, forwarding, tile over HTTP, E1/E2/E4 | every app needs it | M | **done `15d4aa1`** |
| 2 | Map as proof app | fan-out 0, tests only the hub mechanics | S | **done `db9e40b`** |
| 3 | **Lists ready to move, inside the core** (A9, A8, resolve route for the calendar, Prüfstand by setting) + guards **E5, E7, E8** | **next step.** No move, no new repo, no decision of Sasha needed; shrinks the TUI door by `listen_baum`/`listen_bild`; the guards are read-only tests that stop new copies and route clashes before more apps leave | M | open |
| 4 | **One way to get an app**: tutor and map through the store, uninstall for downloaded apps | before Lists leaves the repo, every node (PC, Pi, Mini-PC) must get it the normal way, or a node silently loses its lists (the Mini-PC lesson, [building_kit_plan.md](building_kit_plan.md) 0) | S–M | open ([store_tutor_map_migration.md](../open/store_tutor_map_migration.md), [store_app_lifecycle.md](../open/store_app_lifecycle.md)) |
| 5 | **Lists moves out** as a package (`offers: tile`, `needs: data/sync`), calendar and Morgenblick ask over HTTP | first app with readers in the core; needs 3 + 4 | M | open |
| 6 | Notes, Piano | same template, no AI tools, fan-in 0 (Notes + A14; Piano only if H4 = keep) | S each | open |
| 7 | **Hub gap F: apps bring AI tools and skills** (generator and skill loader read installed packages; skills row in [app_motor_plan.md](app_motor_plan.md)) | every later app has AI tools (graphs, mail, calendar), and the screen guide needs it ([screen_guide_plan.md](../ki/screen_guide_plan.md) step 0b). Not needed for 3–6, so it does not block the next step | M | open |
| 8 | **Hub gap G: device-adapter frame** | printer and screen guide wait on it; independent of the extraction, can run in parallel once 7 is done | M | open ([printer_adapter.md](../open/printer_adapter.md)) |
| 9 | Graphs + cycle | untangle first: H2, AI tools through F instead of privates, one write path, one picture (A13), cycle marks over HTTP, A10–A12 | L | open |
| 10 | Schematix as its own package, preinstalled, deselectable | after the restyle and canvas rework are merged (building-kit session gives the word); needs 4 (store path, holds) | M | open ([schematix_extraction.md](../open/schematix_extraction.md)) |
| 11 | Mail (rebuild as app), News (H3) | AI tools through F, rights | M–L | open |
| 12 | Calendar | A1, A2, A5–A7 into the core **first**; A1 can be pulled forward any time as a bug fix (H6) | L | open |
| 13 | Morgenblick | needs HTTP of all sources | M | open |
| 14 | Ablage + memory + assistant | after F, the assistant's own tools leave with it | L | open |

**Why Lists before the AI gap (F):** Lists has no AI tool, so F would only
delay the first real extraction that has readers in the core — the hard case
the hub has to prove. F is next in line after the first app without tools,
and before any app with tools.

**Why Graphs is still not early:** values live in the AI memory, AI tools
write past every interface, `/api/log` is a second write path, the cycle
feeds `/api/calendar`, the Prüfstand bends module variables, the TUI
computes the forecast and paints its own picture (unchanged since 22.10.).

## E. Boundary guards

| # | Test | Enforces | Stand 2026-10-31 |
|---|---|---|---|
| E1 | `tests/test_kern_bauplan.py` (`_tuer_verstoesse`, `ausgezogene_apps`, table "Ausgezogene Apps" in `bauplan_kern.md`) | the hub imports no moved app | **built `15d4aa1`**; list: `tutor`, `karte`/`map`/`glossary` |
| E2 | `test_kern_bauplan.py` `TUI_TUER_HOECHSTENS`, `test_tui_tuer_schrumpft_nur`, `test_jedes_modul_der_tui_tuer_wird_gebraucht` | TUI door only shrinks | **built `15d4aa1`**; still 9 modules |
| E3 | per app repo: `zentrale-karte/tests/test_karte_grenze.py`, `language-tutor/tests/test_tutor_grenze.py` | one app, one root | **built** for tutor and map; ⚠ prüfen: `budgeter` |
| E4 | `tests/test_routen_beschrieben.py` + [routen_altlast.md](routen_altlast.md) | every TUI route described | **built `15d4aa1`**; 81 → 78, unchanged since 23.10. |
| E5 | no copies in `tui/` ("wie core/…", constants equal to a core value) | no second truth | **not built**; today A2, A5, A7, A18, A20, `notizen.n_float_pos` → legacy list |
| E6 | one user action = at most ONE write call (calendar plan builder) | all or nothing in the core | **not built**; A1 is the only known case |
| E7 | no data file in `tui/` (writes only on an allowlist) | no domain state in the surface | **not built**; `kalender_farben.json` gone (A4) |
| E8 | route ownership: a path belongs to the hub or exactly one app; forwarding only there | no route without owner | **not built**: `app_weiterleitung.besitzer` takes the longest prefix, an app's `routen` can shadow a hub route and two apps can claim the same prefix unnoticed |
| E9 | `test_kern_bauplan.py` `test_no_new_built_in_apps`, `BUILT_IN_APPS_AT_MOST` + [bauplan_kern.md](../system/bauplan_kern.md) "Altlast: Built-in apps" | no new app inside the core; the built-in list only shrinks | **built `7b0bab0`** (31.10.) |

E5, E7, E8 are read-only tests, seconds to run; E6 needs a legacy table.

## F. AI tools and skills: hub machinery vs. app-owned

The old inventory put "the whole assistant" into "must move". The app motor
([app_motor_plan.md](app_motor_plan.md) section 1: an app package carries
`ki/werkzeuge.json`, MCP tool definitions + `x-zentrale`) and the screen guide
make the cut finer: the **machinery** that lets any app give the AI a tool is
hub; the **tools themselves** belong to the app whose data they touch.

| Part | Files | Belongs to |
|---|---|---|
| Tool generator (description → tool, transports HTTP / MCP stdio / Python) | `core/werkzeug_erzeuger/` (2,293; `anbindung.schema.json`) | hub |
| Register mechanism (`Werkzeug` entry, rails, groups) | `werkzeug_eintrag`, parts of `werkzeug_register` (1,496 — today mostly tool texts), `werkzeug_gruppen`, `werkzeug_befund`, `werkzeug_beispiele`, `werkzeug_fragen` | hub (mechanism) / apps (texts) |
| Tool search | `werkzeug_suche` (371) | hub |
| Permission gate | `erlaubnis` (240) | hub |
| Tool loop | `werkzeug_schleife` (546) | assistant app ⚠ prüfen: hub if more than one assistant may run |
| Error codes | `fehlercodes` (539) | hub table, codes per app |
| Skill loader / format / import | `skills` (630), `skill_format`, `skill_import`, `skill_umzug` | hub |
| Shipped skills | `core/skill_vorlagen/` (8 skills, 6,497 lines, incl. Anthropic's) | packages (assistant or the app the skill serves) |
| App-owned tools | `ki_werkzeuge.py` (881, imports calendar, mail, news, graphs, memory, Ablage, web, sandbox, skills), `werkzeug_kalender`, `werkzeug_ablage`, `werkzeug_dateien`, `werkzeug_pdf_word`, `werkzeug_tabelle`, `werkzeug_browser`, `werkzeug_gedaechtnis`, `werkzeug_nachschlagen`, `ki_kalender*`, `ki_pdf_word`, `ki_tabelle`, `ki_browser`, `ki_dateien`, `ki_ablage_adapter` | calendar (17 of 72 tools), mail 1, news 1, graphs 3, memory 5, skills 4, Ablage/files/docs ~14, PDF/Word/Excel 9, browser 8, web 2, past chats 2, `run_code` 1; chat control (`antwort`, `ask_choice`, `explain_error`, `search_tools`, `read_time`) stays with the assistant |

**The gap (hub, every app needs it):** tool descriptions load only from
`core/anbindungen/` and `data/anbindungen/`
(`core/werkzeug_erzeuger/anbindung.py:41, 76–80`; only `kalender_kern.json`
exists), and skills only from the memory folder `ki/skills/`
(`core/skills.py:105–113`, `gedaechtnis.skills_ordner`, filled from
`core/skill_vorlagen/`). **Nothing is read from installed app packages**, and
the app package table has no skills row. Fix (D step 7): generator and skill
loader also read `ki/werkzeuge.json` and `ki/skills/` of every installed app,
trust level by package signature (today only `core/anbindungen/` may use the
Python transport), tool visible only while the app is installed and its
wires are live. Contradiction to settle first: decision H7.

## G. Generic frame for local device adapters

Adapters today are **connections to outside services**:
`core/adapter_anschluss.schema.json` allows only `kalender-vdirsyncer` and
`ki-anbieter` ([adapter.md](adapter.md)). A local device that *offers* a
hardware port (`print`, `scan`, `mic`, `display` … already in
`contracts/ports/1/types.json`; `screen` not yet) has no home: hardware ports
are only detected by the node (`core/knoten.py`), nothing docks and offers
them. Waiting on this frame: the printer
([printer_adapter.md](../open/printer_adapter.md): core = broker, an interface
per device kind, adapter docks with its own manifest) and the screen guide
([screen_guide_plan.md](../ki/screen_guide_plan.md) step 0, parked since
2026-10-31 until this inventory is clean). Agreed: build the frame **once**,
screen first, printer second. Place: D step 8, after F (both users ship an AI
tool in their package).

## H. Decisions for Sasha

1. **Backend reachable from the LAN:** listens on `0.0.0.0` with access mode
   "melden". Switch to "an" (needs the key on the Pi) or bind narrower?
2. **Where graph series live:** in the AI memory (`themen/…reihe.json`, today)
   or in the graphs app's own data? Blocks D step 9.
3. **News:** keep (then as an app with tests) or drop?
4. **Piano:** part of the product or not ([produkt_inventur.md](produkt_inventur.md))?
5. **Concept graph** (2,497 lines, off since 18.08.): delete?
6. **Calendar A1** (edit = up to 7 writes, no rollback): fix now as a bug, or
   wait for the calendar extraction (D step 12)?
7. **Where an app's AI tool lives:** inside the app package
   ([screen_guide_plan.md](../ki/screen_guide_plan.md), [app_motor_plan.md](app_motor_plan.md))
   or as a separate store package the hub offers after install
   ([printer_adapter.md](../open/printer_adapter.md): "AI tool is its own
   store package, not given to the AI automatically")? The two plans
   contradict each other; F needs one answer.
8. **Lists data:** stays at `data/lists.json`/`data/features.json` and the app
   finds it by setting (22.10. plan), or moves to an app data folder
   ([listen_app.md](listen_app.md) item 3)?

## Historie

- **2026-10-31** — re-measured and checked row by row against the code
  (docs only). New: numbers table old/new, A20, Schematix in B and D, sections
  F (AI tools/skills), G (device adapters), H (decisions). The step-by-step
  Lists recipe moved to [list_extraction_plan.md](list_extraction_plan.md).
- **2026-10-22** — first inventory (`e0df238`, read only). Same evening:
  security fix `a4c4872`, hub basics `15d4aa1`; map moved out `db9e40b` (23.10.).
