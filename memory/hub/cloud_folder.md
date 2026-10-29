# Cloud folder — the app `cloud_folder` (2026-10-29)

Sasha: *„ne allg cloud app für zentrale, wo man einfach nen ordner in den
files kriegt der als die allg cloud fungiert. die app im zentrale programm
selbst is einfach n icon, wenn man es anklickt öffnet es im file manager den
ordner direkt. dann kann ich da random shit reindumpen."*

Yardstick ([../leitbild.md](../leitbild.md)): groundwork — "alles, was sie
weiß, gehört dir", now also for plain files.

## What it is

- **A folder:** `~/Zentrale/Cloud` (next to `~/Zentrale/Ablage`; setting
  `cloud_folder_dir`, env `ZENTRALE_CLOUD_FOLDER_DIR`, machine-level path).
  Anything goes in: files, subfolders, any format — stored as they are
  (no own format).
- **No second sync system.** In the sync namespace the folder is
  `data/cloud/**` (like the Ablage is `data/ablage/**`): one line in
  `NUR_ABGLEICH` (`core/abgleich_auswahl.py`, never the plain-text backup),
  `AUSSEN` maps it to the home folder, the built-in app `cloud_folder`
  (`core/eingebaute_apps.py`) owns the pattern. It rides the normal sync —
  timer every 5 minutes, `zentrale sync`, Zero-Knowledge Fernet as for
  everything else. Dropping a file does not trigger a sync by itself; the
  timer picks it up.
- **The icon:** `cloud` in the app wheel of the TUI (`tui/ansichten/startseite.py`,
  pixel motif `cloud` in `tui/pixel.py`, shop icon). Enter → `tui/ansichten/cloud_folder.py`
  asks the backend where the folder is (`GET /api/abgleich` → `cloud_folder`),
  creates it if missing and opens it with `xdg-open` (else `gio open`, macOS
  `open`) — the desktop's default file manager for `inode/directory`, so
  the same on i3/X11 and sway/Wayland. Without `DISPLAY`/`WAYLAND_DISPLAY`
  only the path is shown. TUI text: own gettext table
  `tui/ansichten/locale/` (`translate.py`) — the TUI door to the core does
  not grow.

## Rules

| Case | What happens |
|---|---|
| Both devices changed the same file | The cloud wins, the version from here goes to `<abgleich_dir>/konflikte/<time>/data/cloud/…`, note. Never merged inside (rule `ganz`, `core/abgleich_zusammenfuehren.py`): no conflict markers in someone's `.md`, no JSON merge. |
| Device joins later with own versions | First sync (`erstabgleich`) or app chosen later („App neu dabei"): the cloud wins per file, differing local versions are kept aside, files only here are added. |
| Deleted here | Tombstone in the cloud; other devices move the file to `beiseite/<time>/`. |
| File too large (blob > 24 MiB, i.e. file ≳ 18 MiB after Fernet) | **Held back**: not read, not sent, not deleted, base untouched. One note when it first happens, listed under "Not synced" in `zentrale status` (`zustand.json` → `held_back`). Everything else syncs. Applies to every synced file, not only the cloud folder. |
| Folder missing or empty while ≥ 3 of its files are still in the cloud | Held back as a whole (reason `folder_missing`), nothing deleted anywhere, one note. Emptying on purpose: delete all but two, sync, then the rest. |
| `.git`, `node_modules`, `__pycache__`, `.venv`, caches, trash, `.part`/`.crdownload`, editor swap/lock files, `.DS_Store`, symlinks, `..` paths | Never synced (`core/cloud_folder.py`), not even walked. |

## Activate on a new device

The device's app choice (`abgleich_apps`) decides, like for every app:
logged in and the cloud already has files in it → `zentrale sync` (or the
start of `zentrale`, if the local folder has files) asks once "Cloud folder
has data — sync it?". Yes → the sync creates `~/Zentrale/Cloud` and fills it.
A device that never chose apps (`abgleich_apps` unset = everything) syncs it
right away.

## Other platforms (prepared, not built)

The phone is a foreign node: it reads the Mitte and writes only its inbox.
For the cloud folder it would list `data/cloud/**` from `inhalt.enc`, fetch
files on demand and hand new ones in as proposals (a rule like
`abgleich_vorschlaege` for `data/cloud/`, "only if the cloud has no such
file"). Opening = the platform's own file view (Android: Storage Access
Framework / share sheet). Nothing of that exists yet.

## Open

- Every run reads all files of the folder into memory and keeps a plain copy
  in the base (`<abgleich_dir>/basis/`): fine for documents, heavy for
  gigabytes. Free R2 is 10 GB in total (brake at 100 %).
- The cloud refuses more than 20 000 names per stand and a 4 MiB stand JSON —
  a folder with tens of thousands of files would make the whole sync fail.
- No large-file support (chunking) — the server limit stays 24 MiB per blob.
