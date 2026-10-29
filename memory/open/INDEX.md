# Open items — index

How this folder works: [README.md](README.md). One line per open item.

| Item | What | Waits for Sasha |
|---|---|---|
| [pc_launcher_menu.md](pc_launcher_menu.md) | `zentrale` on the PC probably still calls the removed cassette menu | no (needs PC online) |
| [docs_test_hook.md](docs_test_hook.md) | No hook runs the docs tests; `main` went red twice | no |
| [rsync_helpers_removal.md](rsync_helpers_removal.md) | Old rsync helpers in `~/.local/bin` go after the switch to the Mitte | yes |
| [main_checkout_clutter.md](main_checkout_clutter.md) | Untracked leftovers in the main checkout to sort out | yes |
| [test_suite_memory.md](test_suite_memory.md) | Measure how much RAM the test suite needs | yes (Sasha measures himself) |
| [small_fixes.md](small_fixes.md) | Stale docstrings, comments, a fallback text, an index section, the word „Takt" | partly |
| [calendar_frames.md](calendar_frames.md) | Pixel-art frames, selection and "running now" markers for calendar blocks: drafted, not built | yes (pick styles) |
| [browser_ui_rebuild.md](browser_ui_rebuild.md) | Old dashboard back to the archive, browser UI rebuilt in today's TUI style: asked 13.10., not started | yes (pick approach) |
| [store_app_lifecycle.md](store_app_lifecycle.md) | Store apps: no uninstall, update or rights dialog yet | no |
| [store_tutor_map_migration.md](store_tutor_map_migration.md) | Tutor and map still hard-coded, not installed through the store | no |
| [budgeter_followups.md](budgeter_followups.md) | Budget app: German code, no import, small gaps, look | partly (look) |
| [test_pruefstand_isolation_red.md](test_pruefstand_isolation_red.md) | `test_pruefstand_isolation` red on main (`SYSTEMD_USER`) | no |
| [printer_adapter.md](printer_adapter.md) | Printer via pluggable adapters (core as broker): blueprint + IPP adapter not started; printer not on a shared network yet | yes (network, go) |
| [smartwatch_import.md](smartwatch_import.md) | Xiaomi Smart Band 11 → ZENTRALE: Gadgetbridge test pending, no importer exists yet | yes (test on phone) |
| [list_app_extraction.md](list_app_extraction.md) | List app (`fokus`) not pulled out of ZENTRALE yet; hub imports, direct `lists` readers, deprecated `tiefe` | no |
| [list_names_english.md](list_names_english.md) | List rebuild left German names (`listen_bild`, `listen_app.md`, role `auswahl`) | no |
| [backup_dashboard_focus_box.md](backup_dashboard_focus_box.md) | Backup dashboard draws the focus box the old way (`proj_render`, pink bars) | yes (decide) |
| [tracker_rename_decisions.md](tracker_rename_decisions.md) | Tracker after the 11.10. rename: unclear items, German titles, items to tick off | yes (Sasha keeps the tracker) |
| [calendar_soll_ki_tools.md](calendar_soll_ki_tools.md) | KI calendar tools/adapter don't know `soll_abstand` of deadlines | no |
| [calendar_cloud_sync_gaps.md](calendar_cloud_sync_gaps.md) | Calendar via Mitte: switch-back deletion risk, no n/N progress, first-run and race gaps, Google timer | no |
| [calendar_phone_merge_limits.md](calendar_phone_merge_limits.md) | Phone edits: two different occurrences off = conflict; removing by omission doesn't work | no |
| [tui_bauplan_over_limit.md](tui_bauplan_over_limit.md) | `memory/system/tui_bauplan.md` has 620 lines (limit 600) | no |
| [study_plan_followups.md](study_plan_followups.md) | Study plan: ExPhy Soll, chemistry exam blocks, Parkour, PhyProg ECTS, pause test, mechanics doc | yes (partly) |
| [calendar_form_hints.md](calendar_form_hints.md) | Hint text for greyed-out rows in the calendar Advanced window | no |
| [claude_max_assistant.md](claude_max_assistant.md) | Assistant via Sasha's Claude Max subscription (Agent SDK, in-process MCP): blueprint, nothing built | yes (okay for measuring script, claude.ai privacy setting) |
| [ai_initiative.md](ai_initiative.md) | KI works on her own while Sasha is away: activity log, background run, own project | yes (okay for run 1) |
| [ai_budget_model_choice.md](ai_budget_model_choice.md) | October budget over (booked > real), default/fallback model, `claude-fable-5-1` missing in prices | yes (budget, model) |
| [tool_search_followups.md](tool_search_followups.md) | Tool search stays off: round limit 100 → ~20–25, repeat guard, research rule, new test run, W-09 | partly (test budget) |
| [persona_nudging.md](persona_nudging.md) | B-01 nudging vs. „bietest dich nicht an“; servant phrase, gross has no stop list, „Sekretärin“ in ziele.md | yes (how to nudge) |
| [skills_review.md](skills_review.md) | Sasha reviews skills (incl. imported claude.ai ones) before removal (S-02) | yes |
| [tool_merge_proposals.md](tool_merge_proposals.md) | Merge overlapping tools (W-04 proposals) | yes (decide) |
| [measured_canon_texts.md](measured_canon_texts.md) | klein „muss Sasha bestätigen“ (W-03), qwen rule 5 „laut Suchtreffer“: change only after re-measuring | no |
| [leitbild_checkin_stage.md](leitbild_checkin_stage.md) | Check-in scene mapped to stage 5 by an agent | yes (check) |
| [ai_small_leftovers.md](ai_small_leftovers.md) | Skill backup returns via rsync, qwen `input_examples`, long read results (W-05, W-06) | no |
| [tutor_tool_channel.md](tutor_tool_channel.md) | Tutor (repo `language-tutor`): prompts name tools in prose, no tool-call example, soft contract — the model narrates calls; front only strips them | no |
| [tutor_behaviour_bench.md](tutor_behaviour_bench.md) | Tutor: blueprint checks structure, not behaviour — no bench, no up-to-date/outdated status per language pack | no |
| [tutor_stt_quality.md](tutor_stt_quality.md) | Tutor: Whisper pinned to the target language invents sentences from noise; model `base`, no vocabulary hint, no confidence threshold | no |
| [docs_pruefen_markers.md](docs_pruefen_markers.md) | Eleven `⚠ prüfen:` markers in `memory/` from the 18.09. docs rework, unanswered | partly |
| [task_prioritization.md](task_prioritization.md) | KI asks what to do with dumped ideas/duties instead of deciding their status herself; prompt rule forbids ordering | yes (one decision) |
| [mini_pc_tty_login.md](mini_pc_tty_login.md) | Mini-PC: greeter has no window without a monitor → switch to text-console login (prepared) | yes (2 commands + reboot) |
| [mini_pc_network.md](mini_pc_network.md) | Mini-PC still on the laptop's hotspot: eduroam (mini + tablet), home Wi-Fi, optional own hotspot | yes (credentials) |
| [mini_pc_zentrale_setup.md](mini_pc_zentrale_setup.md) | ZENTRALE not installed on the mini; cloud folder to activate; `uds` only copied; repo paths for Claude sessions | yes (login) |
| [second_screen.md](second_screen.md) | Tablet as second screen works; script only on the mini, no ZENTRALE app button yet | partly (where the script lives) |
| [laptop_retirement_leftovers.md](laptop_retirement_leftovers.md) | Things only on the laptop: repos without remote, branches, secrets, KeePass, MediaWiki, visible Ablage | yes (per item) |
| [cloud_folder_limits.md](cloud_folder_limits.md) | Cloud folder: memory per run, 20 000 names, ~18 MiB per file, two-step emptying, phone not built | no |
| [phone_release_0_1_0_3.md](phone_release_0_1_0_3.md) | Phone app 0.1.0+3 (calendar colours) not built/published yet — first real self-update test | yes (RAM / build) |
| [calendar_colours_followups.md](calendar_colours_followups.md) | Course colour table migrates on next backend restart; full suite after the colour change not run (OOM) | partly |
| [phone_device_checks.md](phone_device_checks.md) | Phone: back gesture, login time, reminders, peephole feel, eye shape, edit flow only tested in simulation | yes (phone) |
| [phone_self_update_hardening.md](phone_self_update_hardening.md) | Self-update: no Ed25519 manifest signature; Play build must drop the install permission | no |
| [phone_local_export.md](phone_local_export.md) | Phone: ZIP of local-only data to Downloads + "export everything" so uninstall loses nothing | no |
| [phone_onboarding.md](phone_onboarding.md) | Phone: tutorial/onboarding, wanted later | yes (later) |
| [app_engine_decisions.md](app_engine_decisions.md) | App engine: questions 3–7 open; step 1 (apps/ folders, register, install gating) not started | yes (questions) |
| [english_renaming_wave.md](english_renaming_wave.md) | Big run renaming existing German code/docs to English: not planned or started | yes (commission) |
