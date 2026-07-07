# Ling-Ling Persona-Tuning — Testläufe gegen echtes qwen-plus (2026-07-07)

Punkt-in-der-Zeit-Protokoll. Sasha meldete nach dem ersten Testlauf: die Persona
redet **fast nur Deutsch**, **labert Monologe**, **fake-lobt** ("ich hab deine
Töne genau gehört!") und drückt **erzwungenes Länder-Spam** rein. Gewünscht ist
das Gegenteil: natürlicher, **kurzer Gesprächspartner**, **nur Mandarin**, kein
Fake-Lob, Kultur **beiläufig statt erzwungen**, **kein Fake-Mensch**.

Getestet mit einer Harness (`scripts/`-Stil, hier: Job-Tmp), die ein 5-6-Turn-
Skriptgespräch gegen das **echte qwen-plus** (DashScope) fährt und pro Antwort
Länge + Latein/Deutsch-Anteil misst. Turns u.a.: `你好` · "ich koch gleich was"
· "wie sagt man danke?" · `你是中国人吗？` · "was bist du eigentlich?" · `我有点累`.

## 1. Baseline (der kaputte alte Prompt) — Score 1/10

~95-98% Deutsch, 700-1250 Zeichen pro Turn, Fake-Lob, Reiseführer-Spam. Auszug:

> **你好** → „你好 (nǐ hǎo)！ — ach, du bist schon da! Ich hab gerade an dich
> gedacht… und an *jiaozi*. (lacht) … Wusstest du, dass es im 3. Jahrhundert
> schon *bāozi*-ähnliche Teigwaren gab? …" (722 Zeichen, 98% Deutsch)

Ursache lag im Prompt selbst: „vernarrt in China / nerdest über Geschichte+
Politik / dreh ihr ein Nationalgericht an" + deutscher Prompt-Text → belohnte
genau die Monologe und das Deutsch.

## 2. Workflow (4 Philosophien parallel gegen qwen, adversarisch bewertet)

Ein Multi-Agent-Workflow testete Baseline + 3 schlanke Philosophien (ultra-
minimal / „Mitbewohner der zufällig chinesisch ist" / strikte Kurz-Regeln teils
auf Chinesisch), ließ jede von einem strengen Kritiker bewerten (Mandarin-Anteil,
Kürze, kein Fake-Lob, Kultur beiläufig) und schärfte die besten zwei nach.

**Gewinner (Score 9/10):** „Mitbewohner der zufällig chinesisch ist" — und zwar
**auf Chinesisch verfasst**. Das war die Schlüssel-Erkenntnis: einen Prompt in
der **Zielsprache** zu schreiben hält qwen zuverlässig im Chinesischen; ein
deutscher Prompt ließ es auf Deutsch antworten.

## 3. Zwei Nachfixes von Hand (gegen qwen verifiziert)

**a) Fake-Biografie raus.** Der Workflow-Gewinner enthielt `你从小在中国长大`
(„du bist in China aufgewachsen") — genau die erfundene Vergangenheit, die Sasha
nicht will. Ersetzt durch kulturelle Nähe OHNE Biografie (`中国的日常你很熟`) +
explizit `你是 AI…也没在中国生活过`. Prüf-Frage `你是中国人吗？` ergab zuerst
noch `我是德国人` (auch eine erfundene Identität!) → Ehrlichkeits-Zeile nochmal
geschärft → jetzt `我不是真人，我是AI`.

**b) Varianz war der eigentliche Feind.** Ohne gesetzte Temperatur war qwen ein
Würfel: **Turn 1 entscheidet den Ton für den ganzen Rest**. Manche Läufe kurz+
chinesisch, andere komplett deutscher Monolog — mit demselben Prompt. Prompt-
Wording allein zähmte das nicht (auch bei temp=0.3 noch Monologe). Zuverlässig
wurde es erst **strukturell**:

- **Few-Shot-Beispiele** im Prompt (zeigen statt sagen — 5 kurze Muster-Turns),
- **harte Verbote** (keine deutschen Sätze, keine `*Regie*`-Anweisungen, keine Emojis),
- **`temperature ≈ 0.4`** + **`max_tokens`-Cap (~200)** im Cloud-Pfad
  (`tutor_openai_compat` / `tutor_cloud`).

Über 3 Läufe wurde das Verhalten damit praktisch identisch.

## 4. Ergebnis — Produktions-Komposition (Prompt + Vokabel-Kontext), 2 Läufe

| Sasha | Ling Ling (reproduzierbar) |
|---|---|
| 你好 | 你好！今天想吃什么？ |
| 你是中国人吗？ | 不是，我是 AI，不是真人。 |
| was bist du eigentlich? | 我是 AI，会说中文，但没去过中国。 |
| ich koch gleich was | 哦，做什么吃的？ |
| wie sagt man danke? | 谢谢（xiè xie）。你饿了吗？ |
| 我有点累 | 那歇会儿吧。 |

Kurz · nur Mandarin (deutscher Halbsatz nur auf explizite Bedeutungsfrage) ·
kein Fake-Lob · kein Fake-Mensch · Kultur beiläufig. Genau das Gegenteil vom
Baseline-Roman.

## 5. Was in den Code ging

- `core/tutor_langs.py`: `_ZH_PROMPT` = getunter chinesischer Prompt (Few-Shot +
  Verbote); `_ZH_VOCAB_HINT` (chinesischer Vokabel-Kontext, `{words}`). Skizzen-
  Sprachen nutzen weiter die schlanke generische `_build_prompt` (deutsch) — beim
  Aktivieren pro Sprache genauso hand-tunen.
- `core/tutor_session.py`: hängt den Vokabel-Kontext in der ZIELSPRACHE ans
  Prompt-Ende (ein deutscher Block kippt qwen zurück ins Deutsche — verifiziert).
- `core/tutor_openai_compat.py` + `core/tutor_cloud.py`: `TUTOR_TEMPERATURE`
  (0.4) + `TUTOR_MAX_TOKENS` (200), per Env übersteuerbar.

**Offen / Follow-up:** die Auto-Progression (correct_use hochzählen, introduce_new
für neue Wörter) hing früher an Tool-Calls, die der Prompt ansagte. Der schlanke
Prompt sagt das nicht mehr an; die Tools bleiben verfügbar, aber verlässlicher
wäre ein deterministischer Hintergrund-Mechanismus. Das „begrenzte Set halten"
ist über den injizierten Vokabel-Kontext gesichert.
