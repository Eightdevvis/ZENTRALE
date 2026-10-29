# KI initiative: works on her own while Sasha is away

**Stand 2026-10-29:** Planned, nothing built except part d. **Waits for
Sasha** (okay for run 1). Source: scene „Bei ihr einchecken“ (Sasha,
26.10.2026) in [../leitbild.md](../leitbild.md) — the scene, the failed
conversation `20261026-201032-04ec42` and the open question „how to organise
this“ are there, not repeated here.

## Blueprint

- **a) Activity log** `data/gedaechtnis/ki/taetigkeiten.jsonl`. Only Python
  writes it, after a real run: `zeit, aufgabe, status
  (fertig|abgebrochen|zu_teuer), befund_pfad, euro, modell`. Plus a tool
  `read_own_activity`; the rule „only tell from this log“ goes into its
  description (W-01), not the prompt.
- **b) Background run via `core/takt.py`:** new trigger
  `hintergrund:<tag>:<aufgabe>`, once a day when Sasha is not there.
  `arbeiten()` next to `sprechen()` (`core/takt_treiber.py` ~107), no
  notification, cost pot `herkunft_block("hintergrund")` (`core/usage.py`
  ~84), round limit 4, only read tools plus writing to `ki/befunde/`.
  Cap 0.05 €/day and 1 €/month — `ai_backends.budget_lage` (~458) only counts
  the chat pot today, so the cap must be built new. About 0.30 €/month with
  Haiku.
- **c) Her own project** under `ki/projekt/<name>.md`, one step a week. Honest
  limit: she can read, plan and run code in the sandbox, but not train her own
  KI. Build only after a and b ran cleanly for two weeks.
- **d) Done 26.10.** (9e74d38, 630beb7): block „Jetzt und als Nächstes“, no
  forced tool use on small talk (KT-07). Still open: there is no data on what
  needs preparation.
- **e)** Tone „partner check-in“ hangs on B-01 — see
  [persona_nudging.md](persona_nudging.md).
- **f)** Switch `eigeninitiative`, later a right in the app manifest.

## First piece (needs Sasha's okay)

Run 1 = a plus one b task: „look through the measurement series of the last
7 days, write a finding“. News only with a local KI
([../werkzeuge/news_system.md](../werkzeuge/news_system.md)).

Bible: B-01, KL-02, P-06, KT-07 ([../ki/bibel/README.md](../ki/bibel/README.md)).
