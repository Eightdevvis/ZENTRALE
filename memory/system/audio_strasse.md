# Die Audio-Straße: ein Mikro, ein Lautsprecher, mehrere Agenten

**Sasha 2026-09-14:** Tutor und KI-Assistent (und später weitere Agenten)
laufen über dieselben Mikro-/Lautsprecher-Kanäle am Pi. Das soll **eine
Straße** sein, auf der mehrere Autos fahren — nicht jeder Agent seine eigene
Mikro-Logik. Dieses Dokument ist das Design; Stand: **der Tutor fährt schon
darauf**, der Assistent noch nicht.

## Was heute schon die Straße ist (in `tutor/room.py`)

Der Pi ist der **Audio-Knoten**: er hört und spielt ab, rechnet aber nichts.

```
USB-Mikro ──► listen_loop ──► webrtcvad (Sprache?) ──► Segment (WAV) ──► POST /api/transcribe ──► Text
                  │                                                              (Whisper am PC)
                  └──► Pegel vs. Grundrauschen (Geräusch?) ──► activity_ms ──► Anwesenheit
                                                                  (presence_loop → /api/sensor/motion)

Text ◄── Agent-Antwort ◄── POST /api/speak (TTS am PC) ──► WAV ──► pygame.mixer ──► Lautsprecher
                                                         │
                                                         └── S['speaking'] → Mikro GEGATED (hört sich nicht selbst)
```

Regeln, die auf der Straße gelten (alle schon gebaut, `room.py`):

| Regel | Warum |
|---|---|
| **Mikro immer offen**, VAD schneidet Äußerungen (700 ms Pause = fertig, max 12 s) | kein Knopf — am Pi vorbeigehen reicht |
| **Gate während Sprechen/Antworten** | sonst transkribiert sie ihre eigene Stimme |
| **Whisper-Floskeln verwerfen** (`_STT_HALLU_RE`: „Amara.org", „Thanks for watching" …) | Whisper erfindet bei Rauschen Untertitel-Sätze; einer ging als Sashas Aussage durch |
| **Regie nie vorlesen** (`_PAREN_RE`: `(…)`, `（…）`, `*…*`, `[…]`) | die Stimme las „asterisko tired asterisko" |
| **Anwesenheit = Sprache ODER Geräusch** über dem mitlaufenden Grundrauschen; bei eigener Musik nur Sprache | Geräuschsensor am GPIO war unbrauchbar; das Mikro ist eh offen |
| **Ankunft** (Aktivität nach ≥10 min Ruhe) → `motion` an den Kern + Anrede von sich aus | der Kerngedanke des Wand-Tutors |

## Die Entscheidung, die noch offen ist: wo die Weiche sitzt

Ein Transkript kommt rein — **wer antwortet?** Tutor oder Assistent? Zwei
Bauweisen:

**A — Weiche am PC (empfohlen).** Der Pi schickt jedes Transkript an EINEN
Endpoint (`/api/hoer` o.ä.) und spielt ab, was zurückkommt. Der PC entscheidet,
welcher Agent dran ist: Tutor-Session aktiv → Tutor; ein Anruf-Wort („Zentrale,
…") oder ein Sprachwechsel ins Deutsche → Assistent; usw. Der Pi bleibt dumm
(Audio rein, Audio raus), jeder neue Agent ist eine Zeile in der Weiche, und
alle Fronten (Laptop-Mikro, späteres Handy) benutzen dieselbe Weiche.

**B — Weiche am Pi.** Das Zimmer entscheidet selbst und ruft `/api/tutor/respond`
oder `/api/chat`. Schneller gebaut (heute ist es fast so), aber jede Front
bräuchte die Logik nochmal, und Agent-Wechsel-Regeln lägen im Fenster-Code.

**Entschieden 2026-09-14 (Sasha): A — die Weiche sitzt im Core.** Der Pi
rechnet nichts selbst, und die Regeln, wer wann spricht, gehören ins Backend
(dort wohnt auch der Takt, `takt.md`). **Der Umbau ist verschoben**: erst muss
der Tutor rund laufen, die Architektur kommt danach.

## Der Umbau in Schritten (nach der Entscheidung)

1. **Modul rausziehen:** `listen_loop` + `speak` + die Filter aus `room.py` in
   ein eigenes, projektfreies Modul (Kandidat `tutor/audio_strasse.py` bzw. im
   Aussenposten-Paket), Schnittstelle: `hoeren(callback)`, `sprechen(text)`,
   `anwesend()`. `room.py` benutzt es, verhält sich exakt wie heute.
   Bedingung aus `memory/tutor/`: `room.py` importiert nichts aus dem Kern —
   das Modul muss stdlib + sounddevice/webrtcvad/pygame bleiben.
2. **Weiche am PC** (`/api/hoer`): nimmt Text + Sprache + Anwesenheit, gibt
   Antwort-Text + Sprecher zurück; Tutor als erstes Auto (heutiges Verhalten).
3. **Assistent als zweites Auto:** Anruf-Wort / Deutsch → `/api/chat`-Pfad,
   Antwort über dieselbe Stimme (anderer Sprecher). Erst nach Prio 2
   (`../ueberblick.md`).
4. **Weitere Autos** hängen sich an die Weiche, nie ans Mikro.

## Grenzen (bewusst)

- Ein Pi 3 hat **keinen** Audio-Eingang; das USB-Mikro ist Pflicht
  (`../betrieb/hardware.md`).
- Kein Hotword-Modell auf dem Pi (RAM). „Anruf-Wort" heißt: das Backend sieht
  es im Transkript.
- Musik aus dem eigenen Lautsprecher macht das Geräusch-Signal blind; dann
  zählt nur Sprache.
