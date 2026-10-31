# Lists (`fokus`) moves out — step plan

**Stand 2026-10-31: plan, nothing built.** The recipe for D steps 3 and 5 of
[kern_auszug_inventur.md](kern_auszug_inventur.md): first make Lists ready
*inside* the core (step 3, the recommended next step), then, once every node
can get an app through the store (step 4), move it into its own repo as a
package. What belongs to the list program and why it has ONE picture:
[listen_app.md](listen_app.md). Open item: [list_app_extraction.md](../open/list_app_extraction.md).

**Why Lists next (and not Graphs):** own logic already separated, no AI tool,
fan-out only hub helpers. But it has readers in the core (calendar source,
week plan, Morgenblick, Prüfstand), and the TUI view draws through an
in-process import — exactly the hard case the hub must prove after the map
(which had fan-out 0). Graphs is blocked by the AI memory (inventory D step 9).

## Step 3 — in the core, no move (each with a test)

- **A9:** the picture of one list level over HTTP — `POST /api/kachel` with
  `pfad`, `auswahl`, `erledigte` (or `GET /api/lists/<lid>/bild`).
- **A8:** `GET /api/lists` delivers per node `erledigt/gesamt`, the display
  order, and a route for "file into" targets.
- Then `tui/ansichten/fokus.py` imports neither `listen_baum` nor
  `listen_bild` → both leave the TUI door (`TUI_TUER_HOECHSTENS` in
  `tests/test_kern_bauplan.py`, `bauplan_kern.md`, `deploy/aussenposten.txt`).
- **Resolve route for the calendar:** `POST /api/lists/aufloesen {quellen}` →
  `{titel, zustand, offene}` (replaces `listen_baum` in `kalender_quelle.py`).
- **Prüfstand:** list location by setting instead of bending
  `lists._DATA_DIR` (`scripts/pruefstand_teile/umgebung.py:134`).
- New routes go straight into `openapi.yaml` (E4).
- Guards E5, E7, E8 in the same run (inventory section E).

## Step 5 — the move (after step 4: one way to get an app)

**Moves** (new repo next to ZENTRALE, like `language-tutor`, package `fokus/`):
`core/lists.py`, `listen_baum.py`, `listen_bild.py`, `kachel_fokus.py`
(→ HTTP handlers `/hub/kachel`, `/hub/kacheln`, `/hub/kachel/aktion`),
`ui/routen/listen.py` (→ own server, **the same** paths `/api/lists*`,
`/api/projects*`), tests `test_lists`, `test_lists_uniform`,
`test_listen_bild`, the lists half of `test_kacheln_fokus_graph`, doc
`listen_app.md` → `docs/`. Instead of hub imports: errors as HTTP answers
(`kachel_form`), parameters as a fixed JSON Schema (`kachel_parameter`),
address with `urllib.parse` (`adressen`), atomic write of its own (`dateien`,
~20 lines); `datasync.notify_change` goes (rsync/Mitte see the file).

**`app.toml`** (building kit, [port_types.md](port_types.md)): `start`,
`adresse`, `routen = ["/api/lists", "/api/projects"]`, `offers` a `tile`
port, `needs` `data`→`sync` (like the built-ins in
`core/eingebaute_apps.py`), `[daten]` with the list files; installed through
the store on every node, part of the bundle.

**Stays in the hub (adapter):** entry `fokus` in `kacheln.QUELLEN` → HTTP;
forwarding of `/api/lists*`, `/api/projects*`; a small HTTP-only client for
`morgenblick_daten` (`week_items`, `get_focus`), `ui/routen/kalender.py`
(`weekplan`), `kalender_quelle.py` (resolve); the TUI view `fokus.py` as the
terminal view (HTTP only).

**Data:** where `data/lists.json` and `data/features.json` (Sasha's tracker
`l_zentrale`) live afterwards is decided: lists are their own app, data with the app (inventory section H).

**What proves nothing broke:**
- record answers before the move (`GET /api/lists`, `/api/projects`,
  `/api/projects/focused`, `POST /api/kachel`, `GET /api/kacheln` on a fixed
  test set) — afterwards **byte-equal** through the forwarding (the map did
  the same: `zentrale-karte/tests/aufnahme_vor_umzug.json`);
- unchanged green in ZENTRALE: `test_kalender_quelle`, `test_morgenblick`,
  `test_desk_kacheln`, `test_kacheln`, `test_openapi`,
  `test_kalender_bedienung_tui`, `test_kalender_quellen_tui`,
  `test_tui_bernstein`, `test_fussleiste`, `test_tui_helpers`, PTY
  `tasten_zustaende/fokus.py`, `test_pruefstand_pruefungen`,
  `test_werkzeug_kalender_erzeugt`, `test_kern_bauplan` (door and module
  table shrunk), `test_hub_grundlagen`;
- in the app repo: the moved tests + `test_fokus_grenze` (E3, template
  `zentrale-karte/tests/test_karte_grenze.py`).

**Risks:**
1. The Prüfstand bends `lists._DATA_DIR` today — if the new way is wrong,
   **the Prüfstand writes into Sasha's real lists** (incl. `l_zentrale`).
2. Second process: if `fokus` is not running, calendar titles, week plan and
   Morgenblick lose their lists → "aus" everywhere instead of an error,
   fallback titles.
3. A node that never installs the package loses the lists silently → step 4
   first.
4. Pi as remote TUI: every key in the list is a round trip over WLAN → fetch a
   level once, selection/scrolling stays in the surface.
5. Backend hot reload does not restart the app.

## Historie

- **2026-10-31** — moved out of `kern_auszug_inventur.md` ("So zieht Listen
  aus", 22.10.), updated to the building kit (ports in `app.toml`, store path,
  bundle) and the guards that exist now.
