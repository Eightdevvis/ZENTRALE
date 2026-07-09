# Tutor: Tool-Beschreibungen

- **Quelle:** `core/tutor.py:161` (`TUTOR_TOOLS`)
- **Live-Sprache:** de (vier Vokabel-Tools) — **zh** (nur `express`)
- **Rolle:** Diese Tool-Beschreibungen bekommt die Tutor-KI als verfügbare
  Werkzeuge während einer Session. Vier verwalten die Vokabelliste, das fünfte
  (`express`) steuert die Körper-Ausdrücke im Persona-Zimmer. **Sandbox-Hinweis:**
  die Tutor-/Cloud-KI darf ausschließlich diese fünf Tools nutzen (geschlossene
  Allowlist, siehe `core/tutor.py`), sie fassen nur `vocab_*.json` bzw. reine
  UI-Bewegung an — kein Zugriff auf den lokalen Core-Graphen oder lokale Tools.

## Vokabel-Tools (deutsch, LIVE-Wortlaut)

### get_confirmed_vocab

> Gibt alle bestätigten Mandarin-Vokabeln zurück. Zu Session-Beginn aufrufen um
> den 80%-Pool zu kennen.

### get_testing_vocab

> Gibt alle Vokabeln im Testing-Pool zurück (noch nicht bestätigt). Zu
> Session-Beginn aufrufen. Falls count < 10: introduce_new aufrufen.

### increment_correct_use

> Erhöht den Zähler für ein korrekt verwendetes Wort. Aufrufen wenn die Lernende
> das Wort korrekt und sinnvoll in einem Satz genutzt hat.

Parameter `word`: „Das chinesische Wort (Zeichen), z.B. '你好'"

### introduce_new

> Fügt ein neues Wort zum Testing-Pool hinzu. Nur aufrufen wenn get_testing_vocab
> weniger als 10 Wörter zurückgibt.

Parameter `word`: „Chinesisches Zeichen, z.B. '谢谢'" · `pinyin`: „Pinyin mit
Tönen, z.B. 'xiè xie'"

## express (Körper-Ausdruck im Zimmer)

- **Live-Sprache:** zh
- **Rolle:** Lässt die Persona sich im Zimmer bewegen (Haltung ODER einmalige
  Geste). Das Persona-Fenster pollt den Zustand.

### ⚠ Die LIVE-Beschreibung ist CHINESISCH

Diese deutsche Fassung ist **nur zum Review** — bewusst chinesisch, damit qwen im
Chinesischen bleibt. **Nicht 1:1 auf Deutsch zurückspielen.** Der `action`-Enum
(die Werte `sit`, `stand`, `pace`, `wander`, `come_closer`, `wave`, `nod`, `look`,
`stretch`) bleibt englisch — er ist die technische Schnittstelle zum Fenster.

#### Deutsche Übersetzung (nur Review)

> Drück dich im Zimmer aus (nutze dies zum Bewegen, schreib es nicht als Text):
> hinsetzen `sit` / aufstehen `stand` / auf und ab gehen `pace` / umherwandern
> `wander` / näher kommen `come_closer`; oder eine Geste: winken `wave` / nicken
> `nod` / sie ansehen `look` / sich strecken `stretch`. Nutze es natürlich, beweg
> dich, wenn dir danach ist.

#### Chinesisches Original (das LIVE in den Code gehört)

```
在房间里表达自己（用这个来动，别写成文字）：坐下 sit / 站起 stand / 踱步 pace / 走动 wander / 靠近 come_closer；或一个动作：招手 wave / 点头 nod / 看着她 look / 伸懒腰 stretch。自然地用，想动就动。
```
