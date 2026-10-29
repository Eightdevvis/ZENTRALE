# Cloud folder: known limits

**Stand 2026-10-30:** Open (built and merged 29.10., `49a06dd`; report
`~/Zentrale/Ablage/bericht-cloud-app-2026-10-29.md`). Code:
`core/cloud_folder.py`, docs `memory/hub/cloud_folder.md`.

- Every sync run reads all files of the folder into memory, and the base keeps
  a plaintext copy — fine for documents, heavy for gigabytes. R2 is free only
  up to 10 GB in total.
- The cloud takes at most 20 000 names per state; a folder with tens of
  thousands of files would make the whole sync fail.
- Files above ~18 MiB (24 MiB server limit minus Fernet overhead) are skipped
  and listed under „Not synced"; no chunking.
- Emptying the folder on purpose takes two steps (guard against an accidental
  wipe: ≥3 cloud files + empty local folder → folder suspended).
- Phone: prepared in docs only, not built.
- Store catalogue description of the icon is still German (catalogue has no
  translation table).
