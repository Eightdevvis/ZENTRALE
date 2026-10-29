# Tutor: no bench for behaviour — a language pack can drift unnoticed

**Stand 2026-10-29:** Open, does not wait for Sasha. Repo:
`Eightdevvis/language-tutor`. Asked by Sasha 19.09.2026 („wir brauchen einen
EINzIGEN blueprint plan der struktur und solche tuning voraussetzt, damit man
einen tutor immer damit abgleichen kann vollständig" + „nen harness und testlauf
… der direkt das ding als up to date oder outdated aufschreibt").

## What is missing

`docs/bauplan.md` (the blueprint) and `tests/test_tutor_bauplan.py` check
**structure** — paths, routes, mandatory files and profile fields per package.
Nothing checks **behaviour**. That is how Ling Ling could drift: `zh` was tuned
against qwen in July on the *old* prompt; when the new master prompt arrived
(25.07.), Lucía was rebuilt and verified against the real model, Ling Ling only
got the translation. Result in September: stage directions in brackets despite
the ban, three questions per turn, tool calls told as prose. Nothing went red.

## What to build (plan of 19.09., steps 3, 3b and 6)

- **Rule table in the blueprint** (`## 7. Prüfstand`), one id per rule: R1 target
  language/script · R2 short (char cap per pack) · R3 one thing, ≤1 question ·
  R4 no praise/correction/quizzing · R5 no stage directions, emojis or tool text
  (leak count 0) · R6 movement only via `express`, a new word only via
  `show_thought`, never a known word · R7 honest AI · R8 culture incidental ·
  R9 hook · R10 no repetition across turns · R11 `?` → simpler + show/puzzled,
  no new question · R12 gloss in the mother tongue · R13 no empty or invalid
  tool calls.
- **Per pack `pruefstand.json`**: the fixed probes (greeting, small talk in the
  mother tongue, meaning question, nationality probe, "what are you", tired
  line, `?`, greeting twice, a mangled STT word) plus a `werkzeuge` section with
  direct orders ("wave", "put music on", "show me the word for water", "show me
  water again") and the expected tool/arguments.
- **Runner `scripts/tutor_pruefstand.py`** after the pattern of ZENTRALE's
  `scripts/pruefstand.py`: sandboxed save state, `session.activate()` +
  `respond_stream()`, tool events via `debug.subscribe()`, `--wiederholungen 3`
  (turn 1 sets the tone — single runs mean nothing, see
  `docs/tutor_persona_tuning.md`), ✓/✗ per rule with pass rate and cost, writes
  `pruefstand.ergebnis.json`.
- **Test suite for the tool calls** (`tests/test_tutor_tools_live.py`, live only
  with a key, otherwise skipped) and a deterministic offline counterpart for the
  contract — both using the same scoring functions as the runner, so report and
  test cannot diverge.
- **Up-to-date / outdated check** (`scripts/tutor_bauplan_check.py`): fingerprint
  over everything that shapes behaviour (profile, prompt, few-shot, tool texts,
  core vocab, seeds) plus the contract and a `Bauplan-Version`; compare against
  the fingerprint stored in the last bench result; write
  `bauplan.status.json` per pack with `aktuell`/`veraltet` **and the reason**
  („prompt changed since the bench", „rule R5 at 60 %"). The blueprint test goes
  red while a pack is `veraltet`; the backend logs the status line on start.

„Tuning against qwen" means: send the fixed probes to the real model, read the
raw output, change prompt/few-shot/tool texts until every rule holds — the
method of `docs/tutor_persona_tuning.md`, made repeatable.

Depends on [tutor_tool_channel.md](tutor_tool_channel.md) (same plan file:
`~/.claude/plans/gut-jetzt-lass-uns-pure-castle.md`).
