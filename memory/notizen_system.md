# Notizen-System (freie Notiz aus gestapelten Blöcken)

> **STATUS (2026-07): TUI + Backend live, browser-front offen.** Taste `n` auf
> der Startseite öffnet direkt eine Notiz. Eine Notiz ist eine geordnete Folge
> von **Blöcken** (text / liste / float), die sich in der MITTE-Box automatisch
> untereinander stapeln und dynamisch mitwachsen. Bewusst **TUI-first**; die
> Browser-Front (`monolith.html`) kommt später als eigenes Feature.
>
> Recherche vorab: es gibt **kein** fertiges Tool zum Einbinden — TUI-Notiz-Apps
> sind linear/Markdown oder ein festes Post-it-Grid, spatial-freie Canvas-Notizen
> nur als GUI (Obsidian Canvas). Ein Framework (Textual) würde mit dem
> handgezeichneten raw-curses-Renderer kollidieren → Eigenbau im Projektstil.

## Datenmodell — `core/notes.py` + `data/notes.json`

Registry-Muster 1:1 wie `core/graphs.py` (`_load`/`_save` mit
`datasync.notify_change`, id via `_slug` → `n_<slug>`). `data/notes.json` fällt
unter `data/*.json` → wird vom bestehenden Sync (push-on-write + boot)
mitgezogen, kein neuer Sync-Code.

```
note  = {id:'n_<slug>', title, created, modified, next_block, blocks:[…]}
block = {id, type}  +  je Typ:
  text  → {text}                              # mehrzeilig (\n)
  list  → {items:[{id,text,done}], next_item} # exakt die Item-Shape aus core/lists.py, aktuell flach
  float → {terms:[{id,text}], next_term}      # Position wird beim ZEICHNEN gestreut, nicht gespeichert
```

CRUD: `list_notes` (übersicht, neueste zuerst) · `get_note` · `create_note` ·
`save_note(nid, title=, blocks=)` (ganze Notiz ersetzen, stempelt `modified`,
normalisiert Blöcke via `_clean_blocks` → krude API-Bodies können nichts
kaputtmachen) · `delete_note`.

**Reine Layout-Helfer** (curses-frei, testbar): `wrap_text`, `block_height`,
`stack_layout`, `float_positions` (Float-Terme werden nach ihrer **echten
Breite** zeilenweise gepackt → wächst nach unten, nie Überlappung; deterministisch,
**kein `random`** → stabil/diffbar). Die TUI **spiegelt** diese als lokale
`n_*`-Funktionen (analog
`l_done ↔ core.lists.is_done`), weil die TUI ein reiner HTTP-Client ist und auf
dem Laptop gegen das PC-Backend laufen kann — sie importiert `core` nicht.

## REST — `ui/app.py` (dünner Adapter über `core/notes`)

`GET /api/notes` · `POST /api/notes` · `GET /api/notes/<id>` ·
`PUT /api/notes/<id>` (title+blocks) · `DELETE /api/notes/<id>`.

## Bedienung (TUI, Taste `n`) — zwei Ebenen

`n` auf der Startseite → **direkt in die zuletzt bearbeitete Notiz** (oder eine
frische). **`n` in der Notiz → Übersicht** aller Notizen (also „zweimal n").

- **Ebene 1 (navigieren/anlegen):** `↑/↓` Block wählen · `t`/`l`/`f` neuer Block
  (text/liste/float) → springt **direkt** in Ebene 2, man tippt sofort los ·
  `e`/Enter → vorhandenen Block bearbeiten · `d` Block löschen (leerer Block
  sofort, befüllter fragt erst nach `j/n`) · `r` Titel · `n` Übersicht · `Esc`
  speichern & schließen.
- **Ebene 2 (bearbeiten), je Blocktyp:**
  - **text:** tippen; Enter = neue Zeile; Esc fertig. Höhe = Zeilen.
  - **liste:** tippen editiert das gewählte Item; Enter neues Item; `Tab` hakt
    ab; `Entf` löscht; Esc fertig.
  - **float:** tippen + Enter setzt einen Begriff, der verstreut in der Box
    auftaucht; `←/→` wählt bestehende Begriffe zum Nachbearbeiten; `Entf` löscht.
- **Übersicht:** `↑/↓` wählen · Enter öffnen · `n` neu · `d` löschen · `Esc`
  zurück zur Notiz (bzw. Tool zu).

Gespeichert wird bei jeder strukturellen Änderung (block anlegen/löschen,
haken) und beim Verlassen von Ebene 2 bzw. dem Schließen (`n_save` → PUT).

## Kassetten / offen

TUI + Backend fertig. **Offen:** Browser-Front (`monolith.html`) und
verschachtelte Unterpunkte in der listenbox (aktuell flach). Feature-Tracking
im `zentrale`-Baum (`l_zentrale`); die Tastenbelegung steht oben unter
„Bedienung".
