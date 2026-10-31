# Laptop (0RAMMachine) retirement: things that exist only there

**Stand 2026-10-30:** Open. **Waits for Sasha** (decide per item). Full
inventory: `~/Zentrale/Ablage/inventur-laptop-2026-10-28.md` (laptop).
Do not wipe the laptop before this list is empty.

- **Repos without remote:** `~/codicus/zentrale-karte` (28 commits),
  `~/codicus/viscope` (8), `~/.local/share/zentrale/kalender-git` (287,
  calendar history). Need a remote (GitHub has to be created by hand, no `gh`).
- **This repo:** ~35 old `worktree-agent-*` branches with ~40 commits on no
  remote (probably discarded agent work), `worktree-import-memory-pruefen`
  (1 commit); untracked `zentrale-cloud-plan.md` (610 lines),
  `claude_web_template/`, `INPUT/`; `data/` parts outside the sync
  (`ai_graph*.json` — since 2026-10-31 in
  `~/.local/share/zentrale/archive/concept-graph-2026-10-31/`, `kalender_snapshots/`, `kalender_verlauf/`,
  `klassifikator_beispiele/`, `_beiseite/`).
- **Other repos:** `trading` has uncommitted `bot/`, `scripts/`,
  `run_backtest.py`.
- **KeePass** `~/Documents/keepass/Passwords.kdbx`: Sasha picks a proper sync
  (not copy-paste).
- **Secrets** (move only encrypted / directly, never via git): SSH key,
  `data/ai_config.json`, `data/mail_secrets.enc`, Kunstwolff `.env` /
  `.dev.vars` / `.gemini_test_key`, blog `.env`, vdirsyncer tokens, Android
  debug keystore, Wrangler login.
- **MediaWiki:** `/var/www/html/mediawiki` + MariaDB database `mediawiki` —
  needs a database export, or the content is gone.
- **Visible Ablage** `~/Zentrale/Ablage` (251 files): only the hidden
  `.ablage/dokumente` part syncs.
- Small non-git folders: `~/tidal`, `~/3d`, `~/codicus/3d`,
  `~/codicus/wavepatterns`, Arduino/MIT/inmoov folders, notes in `~`.
- Configs worth taking (no dotfile repo): bash, tmux, nvim, helix, fcitx5,
  CopyQ rule, `~/.local/bin` scripts, user units. i3 config only as a template
  (mini runs sway). Laptop-only, do not take: xcape, Mac keyboard fixes, lid
  rule, TLP, Broadcom, MacBook camera.
