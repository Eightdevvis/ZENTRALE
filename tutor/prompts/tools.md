# Tutor: Tool-Beschreibungen (15 Tools)

- **Quelle:** `core/tutor.py` → `TUTOR_TOOLS` + `_ALLOWED`
- **Rolle:** Werkzeuge, die die Tutor-KI während einer Session hat.
- **Sandbox (Choke-Point `_ALLOWED`):** JEDES Tool fasst NUR tutor-isolierte Daten
  an — Vokabel-/Struktur-/News-Dateien (`vocab_*.json`, `structures_mandarin.json`,
  `persona_news_zh.json`) + den UI-Zustand im Zimmer (`tutor_session`). **Kein**
  Zugriff auf den Core-Graphen, lokale Tools oder `core/news.py`. Wer ein Tool
  ergänzt, prüft: berührt es wirklich nur tutor-eigene Daten?

## Vokabel + Skill (Umfang & Vertrautheit)

| Tool | Params | Zweck |
|---|---|---|
| `get_confirmed_vocab` | – | Bestätigte Wörter (der sichere Pool). |
| `get_testing_vocab` | – | Wörter im Lernen (noch nicht bestätigt). |
| `mark_known` | `word`, `pinyin?` | **Vokabel-Check:** ein Wort, das Sasha SCHON kann, als *confirmed* ablegen. Gegenstück zu `show_thought`. |
| `introduce_new` | `word`, `pinyin` | Neues Wort in den Lern-Pool. |
| `increment_correct_use` | `word` | +1 wenn Sasha ein Wort korrekt nutzt (ab Schwelle → confirmed). |
| `get_structures` / `introduce_structure` / `increment_structure` | `pattern`, `note?` | Satzmuster/„neue Sagweisen" führen + festigen (ab 3× → 掌握). |

**`show_thought`** (`word`, `meaning?`, `pinyin?`) — die zentrale Lern-Mechanik:
zeigt Sasha „in Gedanken" ein Wort + seine Bedeutung (Übersetzung, im Fenster ggf.
Bild aus `data/vocab_images/<wort>.png`). **Koppelt ans Tracking:** ist das Wort neu,
wandert es automatisch in die Liste (dedupt) → der Umfang wächst mit dem real
Gezeigten. Regel im Prompt: jedes *neue/ungeübte* Wort IMMER via `show_thought`.

## express (Körper/Mimik im Zimmer) — CHINESISCH (Review-Fassung)

Der `action`-Enum bleibt englisch (technische Schnittstelle zum Fenster).

> **DE (Review):** Drück dich im Zimmer aus (zum Bewegen/Mimik-Wechseln, nicht als
> Text). Haltungen: hinsetzen `sit` / aufstehen `stand` / auf und ab `pace` /
> umherwandern `wander` / näher kommen `come_closer` / schlafen `sleep`. Gesten:
> winken `wave` / nicken `nod` / ansehen `look` / strecken `stretch` / Arme hoch
> `arms_up` / Arme verschränken `cross_arms` / Schulterzucken `shrug`. Mimik: froh
> `happy` / traurig `sad` / überrascht `surprised` / müde `tired` / **fragend
> (nicht verstanden / sie schickt „?") `puzzled`** / neutral `neutral`.

```
在房间里表达自己（用这个来动/换表情，别写成文字）。姿态：坐下 sit / 站起 stand / 踱步 pace / 走动 wander / 靠近 come_closer / 睡觉 sleep。动作：招手 wave / 点头 nod / 看着她 look / 伸懒腰 stretch / 举起手 arms_up / 抱臂 cross_arms / 耸肩 shrug。表情：开心 happy / 难过 sad / 惊讶 surprised / 累 tired / 疑惑（没听懂/她发「?」）puzzled / 平常 neutral。想动、想换表情就自然地用。
```

## Zimmer-Aktionen (Sasha muss Content liefern — Ordner sonst leer)

| Tool | Params | Zweck |
|---|---|---|
| `get_local_news` | – | Beiläufig ein leichtes Landes-Thema (persona-isolierter Seed, rotierend — NIE `core/news.py`). |
| `play_music` / `stop_music` | `mood?` | Musik nach Stimmung aus `data/persona_music/<mood>/` (Fenster spielt). **Content-Lücke:** keine Dateien mitgeliefert. |
| `watch_tv` / `turn_off_tv` | `mood?` | TV an + level-gerechter Titel (`_TV_SEED`). Video-Playback deferred. |

## Roleplay-Erweiterung (2026-07-09/10)

Alle Tools ab `express` kamen mit der Roleplay-/Anfangsphasen-Runde dazu (Log:
`memory/tutor/tutor_roleplay_features.md`). Details zur Anfangsphase (Register, Check,
`?`→puzzled, Fehlhör) in `memory/tutor/tutor_system.md`.
