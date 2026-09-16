# Naturalisierung des Tutors — die Referenz für den Ausbau

**Stand 2026-09-16.** Das ist nicht ein Plan, sondern *die* Referenzdatei für
alles, was Lucía von „labert vor sich hin" zu „ich lerne organisch mit" bringt.
Wird fortgeschrieben.

## Der Kern (Sasha, 2026-09-15)

Der Kern des Tutors ist **nicht**, dass sie merkt, wann man da ist. Der Kern:
**sie fängt leicht an, und man lernt die Vokabeln organisch mit.** Heute:
sie redet, Sasha versteht nichts, sagt „no entiendo", sie redet anderes.

Comprehensible Input ist mehr als „sie spricht langsam": es ist eine **ganze
Welt, in der die Sprache alles unterstreicht**. Das kann die KI nicht aus dem
Nichts liefern — sie füllt nur die Sprache in die Lücken. Die Welt, das Programm,
der Prompt sind **unsere** Arbeit. Recherche 2026-09-15: niemand baut genau
das; die Teile existieren getrennt (Gesten-Forschung für KI-Lehrer, VR-Welten
mit Beschriftungen, CI-Apps) — also **zentimeterweise**, jeder Schritt an der
Wand getestet. Reihenfolge immer **vom Kern nach außen**: erst „versteht er
sie?", dann Welt-Kontext, zuletzt Präsenz/Sensorik.

## Die Umgebung — was eine echte Welt liefert und Lucía nicht

| # | Kontext-Quelle (Sashas Liste) | Was es dem Lerner gibt | Stand |
|---|---|---|---|
| 1 | **Gestik** (Zeigen, Hände, übertrieben) | Konzept direkt: *das* meint sie; Vibe | `express` mit 19 Aktionen, nicht auf Objekte gerichtet |
| 2 | **Mimik / Grimassen** (übertrieben) | zeigt unbewusst *wie* man ausspricht, nicht nur wie es klingt; Gefühl | 6 Gesichter (`happy sad surprised tired puzzled neutral`), keine Mund-Form |
| 3 | **Zeigen auf Menschen/Objekte** | übersetzt das Konzept ohne Wörterbuch | fehlt — Zimmer hat Objekte (Sofa, Fenster, TV, Lampe, Pflanze), sie zeigt nicht darauf |
| 4 | **Text auf Dingen** (Café-Schild, Verpackung, Plakat) | Lesen nebenbei, Wort ↔ Ding | fehlt — nichts im Zimmer trägt Schrift |
| 5 | **Viele Menschen, die dauernd miteinander reden** | Sprache als Hintergrund, Muster ohne Druck | fehlt — nur Lucía |
| 6 | **Musik** | Rhythmus, Wiederholung, Gefühl | `play_music` nach Stimmung (Dateien), kein Bezug zur Sprache |
| 7 | **Fernsehen** | Level-gerechte Sendungen, Bild + Ton | `watch_tv` zeigt nur Titel (Katalog), kein Inhalt |
| 8 | **Der Mensch, der merkt, dass du nichts verstehst** | hört auf, viele Wörter zu sagen: einzelne, langsamer, deutlicher, lauter, Grimassen, Zeigen | fehlt — **das ist der erste Zentimeter** (Skill `no_entiendo`) |
| 9 | **Emotion durch synthetisierte Musik** (neu, Sasha) | Stimmung hörbar, ohne Worte: Tonart/Tempo folgen ihrer Laune | fehlt — Idee: kleine Synth-Motive (Dur/Moll, Tempo, Lautstärke) aus `battery/mood` erzeugen, nicht aus Dateien |

## Der erste Zentimeter: Skill `no_entiendo`

**Was ein Skill hier ist:** ein kurzes Verhaltens-Dokument in der Zielsprache
(~200 Wörter), das **nur dann** in den System-Prompt kommt, wenn die Situation
eintritt. Auslöser deterministisch (Code), Verhalten ihres (Modell). Kein
zweiter LLM-Aufruf, keine Kappung — abgeschnittene Sätze wären Müll.

**Auslöser (Code, `session.py`):** Sasha sagt „no entiendo" / „?" / „no
comprendo" / „qué?" / „was?", oder er antwortet zweimal hintereinander mit
etwas, das kein bekanntes Wort enthält. Aus: sobald er ein Wort aus ihrer
letzten Äußerung selbst benutzt (`note_spoken` trifft) oder einen normalen Satz
sagt.

**Was im Skill steht (für sie, auf Spanisch):**
1. *Stopp.* Nicht neu erklären, nicht mehr Wörter. Bleib bei **dem einen**
   Wort/Gedanken, um den es ging.
2. *Eins.* Sag höchstens drei Wörter. Dasselbe Wort noch einmal, langsam,
   deutlich (Tempo setzt das Programm auf 0.6, nicht sie).
3. *Zeig es.* `show_thought(wort, bedeutung)` — der Gedanke mit Bild/Bedeutung
   ersetzt die Erklärung. Dazu **eine** übertriebene Geste/Grimasse
   (`express`), die zum Wort passt (müde → `tired`, Frage → `puzzled`).
4. *Warte.* Frag nichts Neues. Wenn er wieder nichts versteht: dasselbe Wort,
   noch kürzer, dann ein halber deutscher Hinweis — nie ein neuer Satz.
5. *Zurück.* Erst wenn er das Wort benutzt: ein kurzer Satz **mit diesem Wort**,
   dann normal weiter. Beispiele: zwei Mini-Dialoge (richtig / falsch).

**Flow der KI im Turn** (heute, mit Skill):
```
Transkript → Auslöser? ─ja→ Skill anhängen, Tempo 0.6 ─┐
                     └nein→ normaler Prompt ────────────┤
                                                        ▼
       System-Prompt = Persona + Vokabel-Status + Kern-Hinweis + Gedächtnis (+ Skill)
                                                        ▼
       Modell (qwen-plus): Text + Tool-Calls (express / show_thought / …)
                                                        ▼
       Zimmer: Sprechblase, Geste, Gedanke; TTS (Regie/Emoji raus); Mikro wieder auf
```

## Tool-Calls, die sie heute machen kann (`tutor/tools.py`)

| Tool | Wirkung |
|---|---|
| `express(action)` | Haltung/Geste/Mimik: `sit stand pace wander come_closer sleep wave nod look stretch arms_up cross_arms shrug happy sad surprised tired puzzled neutral` |
| `show_thought(word, meaning, reading)` | Gedankenblase mit Wort + Bedeutung; nimmt das Wort in die Vokabelliste |
| `introduce_new(word, reading)` | Wort in die Liste (meist über `show_thought`) |
| `get_structures` / `introduce_structure(pattern)` / `increment_structure(pattern)` | Satzmuster ansehen, einführen, als benutzt zählen |
| `play_music(mood)` / `stop_music` | Musik nach Stimmung `chill happy focus sad energetic` |
| `watch_tv(mood)` / `turn_off_tv` | Fernseher mit Katalog-Titel |
| `get_local_news` | leichtes Thema aus Spanien zum Anreißen |
| `get_due_reviews` | fällige Wörter (SRS) zum beiläufigen Einbauen |

Nicht als Tool, sondern Kontext: Vokabel-Status pro Wort (`nueva / la reconoce /
…`), Kern-Wörter, ihr eigenes Gedächtnis. Sie zählt nichts selbst.

## Tool-Calls, die geplant sind (Reihenfolge = Kern → außen)

| Tool (Plan) | Wozu | Kontext-Quelle |
|---|---|---|
| `point_at(objekt)` | auf Sofa/Fenster/TV/Lampe/Pflanze/Tür zeigen, Objekt leuchtet kurz | 3 |
| `label(objekt, wort)` | Schild ans Objekt hängen (bleibt, bis er das Wort benutzt) | 4 |
| `mouth(form)` / Mund-Animation zur Silbe | zeigt *wie* man's ausspricht | 2 |
| `slow(faktor)` / `loud()` | sie selbst drosselt Tempo/Lautstärke (heute macht es der Code) | 8 |
| `gesture_at(person)` | auf Sasha zeigen (tú) vs. auf sich (yo) | 1, 3 |
| `hum(stimmung)` / Synth-Motiv | Emotion als Klang: Dur/Moll, Tempo, Lautstärke aus ihrer Laune | 9 |
| `background_voices(thema)` | zwei Stimmen im Hintergrund reden leise auf Level (Radio-Ecke) | 5 |
| `tv_play(clip)` | echte kurze Clips/Untertitel statt Titel | 7 |
| `write_on(objekt, text)` | Text auf Verpackung/Tasse/Plakat im Zimmer | 4 |

Jedes geplante Tool bekommt erst dann Code, wenn der Zentimeter davor an der
Wand funktioniert hat. Nichts davon ist Sensorik — die kommt zuletzt.

## Was schon steht (damit es nicht nochmal gebaut wird)

Zimmer als Wandbild (Kiosk `room`), Persona ohne Sperre, Grundvokabular
freigegeben, Mikro immer offen (VAD → Whisper), Regie/Emoji nicht vorgelesen,
Whisper-Floskeln verworfen, Alt+P Pause, Nachhaken nach 15 s, Sprechtempo rampt
nach Lernstand (0.7 → 1.0). Präsenz: Worte zählen; PIR vorbereitet (Bridge
GPIO4), **bewusst zurückgestellt**. Siehe `tutor_system.md`,
`../system/audio_strasse.md`.
