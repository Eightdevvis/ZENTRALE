# Tutor-Roleplay-Features — Über-Nacht-Bau (2026-07-09) + Entscheidungs-Log

Sasha hat den Tutor-Prompt auf ein reiches **Roleplay-Framing** umgestellt (gegen
qwen validiert, `tutor_langs._ZH_PROMPT`) und darin viele neue Features skizziert
(`prompts/tutor_generisch-fallback.md`, sein „Sasha Stil"-Draft). Auftrag: über
Nacht alle Features durchbauen, bei Unsicherheit selbst entscheiden + hier
dokumentieren, morgen gemeinsam reviewen.

## Leitplanken (gelten für alles)
- **Live-Prompt bleibt in der Zielsprache** (Deutsch → qwen antwortet deutsch,
  verifiziert). Roleplay-Framing ja, aber pro Sprache in ihrer Sprache.
- **Jede Fähigkeit braucht ein Tool.** Ohne Tool spielt die KI die Aktion als
  Text vor (Regie-Anweisung) — das wollen wir nicht. Frame gewährt nur, was ein
  Tool/State hat.
- **Kurz + kein Fake-Lob/-Mensch** bleibt (getunt). Neue Features dürfen das
  nicht regressieren → nach Prompt-Änderungen gegen echtes qwen gegentesten.
- **Content (Filme/Musik/Bilder)** kann ich nicht lizenzieren → Mechanik bauen,
  Content-Lücke markieren.

## Bau-Reihenfolge (Abhängigkeiten)
1. Reichere Gesten + Mimik (express erweitern + Persona-Animation)
2. Soziale Batterie / Stimmung (State + Decay + Kopplung an Mimik)
3. Vokabel-Feinmodell (pro-Wort-Vertrautheit + neue Strukturen)
4. Visuelle Vokabel-Hilfe (Gedanken-Bubble: Übersetzung jetzt, Bild später)
5. Presence im Hintergrund (brain.py PRESENCE_DETECTED → Zimmer/Anquatschen)
6. Lokale Landes-News (Zeitung/TV-News-Tool, an core/news.py angelehnt)
7. Musik (Tool + mixer.music + Bibliothek nach Stimmung)
8. TV + Film-Mediathek (TV-Objekt + Tool + Bibliothek nach Stimmung/Level)

## Entscheidungen (wird beim Bauen ergänzt)

### 1. Reichere Gesten + Mimik + Schlafen ✅
- **express-Tool** erweitert: Haltungen +`sleep`; Gesten +`arms_up`/`cross_arms`/
  `shrug`; NEU **Mimik** (anhaltend): `happy`/`sad`/`surprised`/`tired`/`neutral`.
  Ein Enum, geroutet in `tutor_session.set_expression` (Stance|Geste|Face).
- `tutor_session._expr` hat jetzt `face`; `room_state()` liefert es; das Fenster
  pollt + `Persona.set_face`. `set_face()` auch direkt aufrufbar (für Feature 2,
  Stimmung→Mimik).
- Render: `sleep` = auf der Couch, Augen zu, „zzz"; `cross_arms` = Arme waagerecht
  vor der Brust; Mimik ändert Augen (überrascht=weit, müde/schlaf=zu) + Mund
  (happy=breit, sad=runter, surprised=O, tired=Strich).
- **Entscheidung/Annahme:** Mimik ist ein eigener anhaltender Zustand (nicht
  one-shot), damit Feature 2 (Batterie) sie treiben kann. Gesten bleiben one-shot.
- **Offen/Review:** die Sprite-Optik ist simpel (Primitive) — reicht funktional,
  könnte man später hübscher machen.

### 2. Soziale Batterie / Stimmung ✅
- `tutor_session._battery` (Level + Zeitstempel), **zeitbasiert** berechnet (kein
  Ticker): sinkt ~3.5/min (≈30 min von voll auf leer), **+9 pro echtem Sasha-Turn**
  (`battery_bump` in respond_stream). `room_state()` liefert `battery` (0-100) +
  `mood` (happy≥68 / ok / low<32). activate() setzt auf 55.
- Fenster: **Laune-Balken** oben rechts (grün/amber/rot). Die Stimmung **färbt die
  Mimik** — aber NUR wenn die KI nicht selbst eine gesetzt hat: `eff_face = KI-Face
  sonst mood→(low=tired/happy=happy)`. So gewinnt bewusster Ausdruck, sonst zeigt
  sich die Grundstimmung.
- **Entscheidungen/Annahmen:** Decay/Refill-Werte frei gewählt (tunebar oben in
  tutor_session). „Verstanden werden lädt mehr" (Sashas Idee) ist vereinfacht:
  jeder echte Sasha-Turn lädt (= sie hat geantwortet = verstanden genug). Feiner
  (Confidence/Verständnis messen) wäre Follow-up. Nudge lädt NICHT (sie kriegt ja
  keine Antwort).
- **Offen/Review:** Werte fürs Gefühl nachjustieren; evtl. bei sehr niedriger
  Batterie auch die Rede-Lust drosseln (sie wird wortkarger).

### 3. Vokabel-Feinmodell + Satz-Strukturen ✅
- **Pro-Wort-Vertrautheit** war schon da (correct_use + confirmed). Jetzt besser
  exponiert: `tutor.vocab_split()` → (gefestigt, im-Lernen); der injizierte
  Vokabel-Kontext (tutor_session) zeigt beides getrennt („放心多用" vs „多带带").
- **Strukturen** (NEU, das genuin Fehlende): paralleler Pool für Satzmuster/neue
  Sagweisen (`tutor/data/structures_mandarin.json`) + 3 Tools `get_structures /
  introduce_structure / increment_structure` (auto-„掌握" ab 3× korrekt). In den
  Kontext injiziert. So kann die Persona nicht nur neue WÖRTER, sondern auch neue
  STRUKTUREN stückweise einführen (Sashas „新词或新说法").
- **Entscheidung/Annahme:** Strukturen mandarin-fest (wie die Vokabeldatei —
  vocab_*.json ist eh hardcoded zh; Multi-Sprache ist ein separater Umbau).
- **Offen/Review:** qwen-Verhaltens-Recheck mit dem VOLLEN Tool-Set (jetzt 8
  Tools) steht noch aus — mache ich gesammelt gegen Ende. Bisher: Prompt
  unverändert, Tools nur Schemas (nicht erzwungen) → Regressions-Risiko gering.

### 4. Visuelle Vokabel-Hilfe (Gedanken-Blase) ✅
- **show_thought(word, meaning)**-Tool (9. Tool): die KI zeigt „in ihrem Kopf"
  ein Wort + dessen deutsche Bedeutung. `tutor.show_thought` → `tutor_session.
  set_thought` (State `_thought` mit hochzählender id). `room_state()` liefert
  `thought_word/thought_meaning/thought_id`.
- **Render** (`tutor/room.py`): `draw_thought()` zeichnet eine helle
  Gedanken-Blase neben dem Kopf (kleine Trail-Kringel), Wort (Zielsprache, groß)
  + Übersetzung (klein). `watch_room` pollt `thought_id` one-shot (wie Gesten) →
  `S['thought']` + TTL 6 s, blendet in der letzten Sekunde aus.
- **Bild-Variante:** liegt in `tutor/data/vocab_images/<wort>.png` ein Bild, wird es
  über dem Wort gezeigt (gecacht, `_vocab_image`). Prompt-Zeile (zh) ergänzt:
  „想帮她记住一个词时，可以用 show_thought …".
- **Entscheidung/Annahme:** die Übersetzungs-Variante ist voll funktionsfähig
  (KI liefert Wort+Bedeutung). Bilder sind ein **Drop-in-Ordner** ohne
  mitgelieferte Assets — **Content-Lücke** (kein lizenziertes Bildmaterial), rein
  Mechanik. Später: Wort→Bild-Zuordnung (manuell kuratiert oder generiert).
- **Offen/Review:** TTL/Position der Blase nach Gefühl justieren; evtl. Kollision
  mit der Sprechblase prüfen (steht bewusst nach links versetzt).

### 5. Presence im Hintergrund ✅ (bewusst konservativ, REVIEW)
- **Spannungsfeld:** die Roadmap sagt „PRESENCE_DETECTED → Zimmer/Anquatschen",
  ABER `memory/tutor_system.md` verbietet **explizit** den Presence-Auto-Start in
  brain.py (Sequencing — und der schlechte Auto-Trigger war 2026-05-14 der
  *Anlass* der Deaktivierung). Ich habe zugunsten des dokumentierten Guardrails
  entschieden und die Mechanik **konservativ** gebaut:
- `tutor_session.presence_ping()`: **startet NIE** eine Session. Läuft die Session
  schon, reagiert die Persona **nonverbal** — schaut hoch (`look`), Mimik `happy`,
  +6 Batterie. Gedrosselt (`_PRESENCE_COOLDOWN=90s`) gegen PIR-Zucken. Der Laptop-
  Raum sieht die Reaktion über den `room_state`-Poll.
- `brain.py` PRESENCE_DETECTED: Hook hinter **Env-Flag `TUTOR_PRESENCE_REACT=1`,
  default AUS** → Default-Laufzeit **unverändert** („kein Trigger aktiv"). Flag an
  = nonverbale Reaktion (nur bei aktiver Session).
- **Bewusst NICHT gebaut:** der verbale Auto-Gruß („Anquatschen" per Cloud-Turn)
  aus einem Sensor-Event — das IST der schlechte Auto-Trigger. Erst wenn Core-KI-
  Sequencing durch ist / Sasha es freigibt, als eigener Schritt (eigenes Flag).
- **Review-Frage an Sasha:** reicht die nonverbale Reaktion, oder willst du den
  verbalen Gruß doch — dann unter welcher Bedingung (nur bei offenem Fenster, mit
  Rate-Limit)? Cooldown/Flag-Namen sind Vorschläge.

### 6. Lokale Landes-News ✅ (Mechanik, Content-Lücke)
- **get_local_news**-Tool (10. Tool): die Persona bringt beiläufig EIN Thema aus
  ihrem Land auf (Wetter/Essen/Feste/„was man gerade so guckt"), rotierend per
  Cursor, damit sie nicht dranklebt. Kein Nachrichten-Vorlesen — der Tool-Text
  weist ausdrücklich auf „随口带一句, 别像播新闻".
- **Sandbox strikt gewahrt:** eigener persona-isolierter Pool, fasst **NIE**
  core/news.py an (das sind Sashas DE/World-Feeds der Core-KI). Der Allowlist-
  Kommentar in tutor.py wurde entsprechend von „nur 4 Vokabel-Tools" auf die
  reale Invariante nachgezogen (nur tutor-eigene Dateien + UI-State).
- **Seed lebt im CODE** (`_NEWS_SEED` in tutor.py), NICHT in data/*.json — letzteres
  ist gitignored (rsync-Runtime) und käme sonst nicht mit; die Datei
  `tutor/data/persona_news_zh.json` hält nur den Rotations-Cursor und bootstrappt beim
  ersten Aufruf aus dem Seed. Prompt-Zeile (zh) ergänzt.
- **Entscheidung/Annahme:** kein echter Feed → **evergreen-nahe** Themen (keine
  datierten Schlagzeilen, die veralten). Ehrlich-KI-Framing: sie erzählt „中国的情况",
  kein Ich-war-dort. Content-Lücke = echter, tutor-isolierter China-Feed-Ingest
  (könnte news.py `_parse_feed` gegen einen China-RSS in einen SEPARATEN Store
  nutzen — bewusst nicht gebaut: online + eigener Sandbox-Store nötig).
- **Offen/Review:** willst du echte tagesaktuelle China-News (dann Feed-Quelle +
  isolierter Ingest festlegen), oder reicht der Evergreen-Gesprächsstoff?

### 7. Musik (Mechanik, Content-Lücke) ✅
- **play_music(mood)** + **stop_music** (Tools 11+12): die Persona legt Musik nach
  Stimmung auf — `chill/happy/focus/sad/energetic`. `tutor.session` hält nur den
  WUNSCH (action/mood, id-getriggert); **abgespielt wird im Fenster** über
  `pygame.mixer.music` aus `tutor/data/persona_music/<mood>/*.{ogg,mp3,wav,flac}` (zufällige
  Datei, geloopt, leise ~0.35). `♪ <mood>`-HUD zeigt's an.
- **Mixer-Konflikt gelöst:** TTS (`play_wav`) reinitialisiert den Mixer bei
  abweichender Rate → das stoppt `mixer.music`. Zwei Schutzmaßnahmen: (a) während
  sie SPRICHT wird die Musik **geduckt** (leiser), nicht gestoppt; (b) muss doch
  reinit passieren, wird der Track danach wieder aufgezogen. In der Praxis ist TTS
  konstant 22 kHz → nach dem ersten Ton bleibt der Mixer stabil, ein Reinit mitten
  in der Session passiert fast nie.
- **Entscheidung/Annahme:** Ordner-nach-Stimmung ist die simpelste Bibliothek
  (keine Metadaten-DB nötig). Moods frei gewählt. **Content-Lücke:** kein Audio
  mitgeliefert (Lizenz) — `tutor/data/persona_music/` ist leer/gitignored; sobald Sasha
  dort Dateien reinlegt, läuft es sofort. Headless getestet (dummy audio, inkl.
  Reinit-Resume), aber **nicht mit echtem Audiogerät + echten Musikdateien**.
- **Offen/Review:** Musikquelle klären (eigene Files / gemeinfrei / lokal
  gerippt?); Lautstärke/Duck-Werte nach Gefühl; evtl. sanftes Fade statt hartem
  Volume-Sprung.

### 8. TV + Film-Mediathek (Mechanik, Playback deferred) ✅
- **watch_tv(mood)** + **turn_off_tv** (Tools 13+14): die Persona macht den
  Fernseher an und schlägt etwas **Level-gerechtes** vor (für Anfänger eher
  Leichtes). Katalog `_TV_SEED` **im Code** (Titel + mood + level + note), rotiert
  per Cursor (`tutor/data/persona_tv_zh.json`, gitignored-Runtime wie News).
- **Raum:** ein TV an der Wand (`draw_tv`) — aus = dunkler Schirm; an = leuchtet
  bläulich mit leichtem Flackern + Scanlinien und zeigt den **Titel** (umgebrochen).
  `tutor_session._tv` (an/Titel, id) → `room_state` → Fenster.
- **Entscheidung/Annahme:** echtes **Video-Playback ist DEFERRED** — keine Files,
  Lizenz, und pygame-Video ist schwach. Die Mechanik ist „TV an + Titel + beiläufig
  referenzieren" (comprehensible-input-Idee: sie guckt was Einfaches, Sasha schaut
  mit). Titel sind echte Werke — **nennen** ist ok, es wird nichts gestreamt.
  Katalog ist ein Seed (kuratierbar). Headless gerendert getestet.
- **Offen/Review:** willst du echtes Mitgucken (dann Quelle/Format klären — lokale
  Files? Untertitel-Sync fürs Lernen?), oder reicht „sie guckt was, ihr redet
  drüber"? Katalog erweitern/kuratieren.

---

## Abschluss Über-Nacht-Lauf (2026-07-09)

**Alle 8 Features gebaut** (Commits „Roleplay-Feature 1..8"), jeweils lokal auf
`main` ff-gemerged. Tool-Set gewachsen von 4 → **14** (alle in `_ALLOWED`-Sandbox,
deckungsgleich mit `TUTOR_TOOLS`, statisch verifiziert). Jede neue Prompt-Zeile
auf Chinesisch (hält qwen im Chinesischen — statisch geprüft, keine deutschen
Streuwörter im `_ZH_PROMPT`).

**Ein Punkt bewusst offen (kein Zugriff):** der **Live-qwen-Verhaltens-Recheck**
mit dem vollen 14-Tool-Set konnte NICHT laufen — in dieser Umgebung ist kein
`DASHSCOPE_API_KEY` gesetzt. Statt zu faken: statisch abgesichert (Tool-Integrität,
Prompt-Sprache, kein Crash bei leerem arg). **Bitte morgen einmal live gegen qwen
gegentesten** (kurz? Chinesisch? in-character? kein Fake-Lob? nutzt sie die neuen
Tools sinnvoll und sparsam?) — das ist der letzte Verifikations-Schritt.

**Content-/Playback-Lücken (Mechanik steht, Assets fehlen):** Vokabel-Bilder
(`tutor/data/vocab_images/`), Musik (`tutor/data/persona_music/<mood>/`), echter China-News-Feed,
Film-Video-Playback. Alles Drop-in bzw. dokumentierte Folge-Entscheidungen.

**Weitere Review-Fragen** stehen pro Feature oben unter „Offen/Review".
