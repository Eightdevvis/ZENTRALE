# Tutor: Wahrnehmungs-Meldungen (Öffnen / Nudge)

- **Quelle:** `core/tutor_session.py` → `_opening_situation()`, `_nudge_situation()`
- **Live-Sprache:** zh
- **Rolle:** Neutrale **Lage-Meldungen**, die der Persona als `user`-Nachricht
  zugehen, damit sie **aus ihrer Person heraus** reagiert. Werden **nur gesendet,
  nie im Gedächtnis gespeichert** (ambient, kein Gespräch).

## ⚠ Umbau 2026-07-10: kein Verhaltens-BEFEHL mehr

Früher stand hier „frag, ob sie da ist" → sie fragte ewig im selben Wortlaut
(„你在吗？"-Spam). Jetzt beschreiben die Meldungen nur die **Situation** (still +
Sensorik); die Reaktion emergiert aus ihrem Charakter (mag kein Ignoriert-werden)
— mal genervt, mal macht sie ihr Ding, mal stupst sie. **Kein vorgeschriebener
Wortlaut.**

Zwei Auslöser:
- **Öffnen** (`user_text=None`, Session-Start): „Sasha kommt gerade rein". Der
  Öffnungs-Turn schickt NUR diese Meldung, **keinen** rohen Verlauf — sonst
  degeneriert sie zu Echo/„我在".
- **Nudge** (`nudge=True`): Stille + Fokus-Sensor (schaut sie zu?) / Ambient.

**Wichtig — als HINTERGRUND markiert:** die Meldungen beginnen mit „(Hintergrund,
nicht Sashas Worte, wiederhol die Zeichen nicht: …)", weil qwen bei Fast-Null-
Wortschatz sonst ein konkretes Wort daraus aufgreift und echot (Bug: „…窗户…" →
sie sagte „窗户！"). Darum auch **keine aufgreifbaren Nomen** in den Meldungen.

## Deutsche Übersetzung (nur Review)

**Öffnen (Fokus an):**
> (Hintergrund, nicht Sashas Worte, wiederhol die Zeichen nicht: Sasha ist gerade
> rübergekommen, schaut dich an.)

**Nudge (Fokus an — du schaust, sagst nichts):**
> (Hintergrund, …: Eine Weile keine Regung, jemand schaut dich an, sagt aber nichts.)

**Nudge (Fokus aus — niemand schaut):**
> (Hintergrund, …: Eine Weile keine Regung, niemand schaut zu.)

## Chinesisches Original (das LIVE in den Code gehört)

```
# Öffnen (focus=True):
（背景，不是 Sasha 说的话，别重复里面的字：Sasha 刚过来了，在看着你。）

# Nudge (focus=True):
（背景，不是 Sasha 说的话，别重复里面的字：一会儿没动静了，有人在看着你，可就是不出声。）

# Nudge (focus=False):
（背景，不是 Sasha 说的话，别重复里面的字：一会儿没动静了，也没人看你。）
```
