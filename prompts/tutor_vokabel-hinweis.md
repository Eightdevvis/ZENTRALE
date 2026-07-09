# Tutor: Vokabel-Hinweis (Ling Ling)

- **Quelle:** `core/tutor_langs.py:99` (`_ZH_VOCAB_HINT`)
- **Live-Sprache:** zh
- **Rolle:** Wird in `tutor_session.respond_stream` mit den aktuell gelernten
  Wörtern gefüllt (`{words}`) und **ans Ende des Persona-Prompts** gehängt. Sagt
  der Persona als Hintergrund-Info, welche Vokabeln Sasha gerade lernt, damit sie
  sich ans begrenzte Set hält und ab und zu ein neues Wort einstreut. Ersetzt das
  frühere „ruf zu Beginn `get_confirmed_vocab()` auf".

## ⚠ Der LIVE-Hinweis ist CHINESISCH

Diese deutsche Fassung ist **nur zum Review**. Der Hinweis ist bewusst chinesisch
— ein deutscher Block hier kippt qwen zurück ins Deutsche/in einen Monolog (gegen
echtes qwen verifiziert). **Nicht 1:1 auf Deutsch zurückspielen.** `{words}` ist
ein Platzhalter, den der Code mit den bekannten/gelernten Wörtern füllt (per `、`
verkettet).

## Deutsche Übersetzung (nur Review)

> (Hintergrund, erwähne es nicht im Gespräch: sie lernt gerade diese Wörter,
> nutze diese oft, ab und zu bring ein neues ein: {words})

## Chinesisches Original (das LIVE in den Code gehört)

```
（背景，别在对话里提：她在学这几个词，多用这些，偶尔带一个新的：{words}）
```
