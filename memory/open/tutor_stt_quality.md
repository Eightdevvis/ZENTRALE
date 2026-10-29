# Tutor: speech recognition invents sentences, and they reach the persona

**Stand 2026-10-29:** Open, does not wait for Sasha. Repo:
`Eightdevvis/language-tutor` (microphone side) and ZENTRALE
(`services/whisper_service.py`). Found 18.09.2026 in the room log on the
laptop; measured again 08.10. (`docs/diagnose_2026-10-08.md`, complaint 6:
"measured, options listed, **not** switched").

## What happens

With German speech or plain background noise Whisper returned fluent Spanish
sentences — the room log is full of `[mikro] verstanden: y nos vemos en el
próximo video`, `¿Qué tal? ¿Qué tal?`, `Sometimes...`. Every one of those went
to the persona as if Sasha had said it, which is a second reason she answered
"random stuff" (see `docs/diagnose_2026-10-08.md`).

Three causes, none of them fixed:

- **Language pinned to the target language.** The service is called with
  `lang=<target>`, so anything it hears is decoded *as* that language; noise
  becomes plausible target-language text. Loosening it (auto-detect, or
  accepting the mother tongue as a second language and discarding those turns)
  was listed as an option, not done.
- **Model `base` instead of `small`** — set by the start script, measurably
  worse on short utterances.
- **No word list as a hint.** The learner's vocabulary (we have it per save
  state) is never passed as an initial prompt, so the decoder has nothing to
  lean on.

A first guard exists in the room (`_STT_HALLU_RE`: "Amara.org", "thanks for
watching" …) and ZENTRALE now answers `/api/transcribe` with 503 instead of
handing `[STT nicht erreichbar]` to the persona as text — both are nets, not
fixes. A confidence threshold is not used at all.

## What to do

Switch the model, pass the vocabulary as a hint, decide what happens when the
recognised language is not the target language (discard, or treat as the
mother tongue), and drop segments below a confidence threshold instead of
sending them. Then verify against a real microphone — the October night had
none.
