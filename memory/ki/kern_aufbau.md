# Aufbau des KI-Kerns — wer wofür zuständig ist

**Stand 2026-10-06.** Sasha: *„an sich soll man anbieter, modell, lokal oder
cloud usw schnell austauschen können, einfach nur wie variablen, und das ganze
backend sonst bleibt gleich. alle sprechen quasi den gleichen port an kein
chaos. eine straße, wo jedes auto drauf fahren könnte."*

## Woher wir kommen

`core/ai.py` entstand im Mai 2026 als **die** KI-Datei: der einzige Weg zu
Ollama. Alles KI-Nahe wuchs dort hinein — Tool-Liste, Tool-Ausführung,
Erlaubnis-Abfrage, Prompt-Bausteine, Bild-Marker, Speichern ins Gedächtnis,
Graph-Seed. Als im Juni `ai_backends` und im August die Cloud-Wege dazukamen,
wurden sie **neben** `ai.py` gebaut und bedienten sich dort. Ergebnis am
2026-10-05: 15 Import-Kanten im Kreis zwischen sechs Modulen
(`memory/system/bauplan_kern.md`, „Altlast: Kreis-Kanten"). Und die
Konsolidierung hatte die Ollama-Einstellungen kopiert, mit dem Kommentar
„KRITISCH: identisch zu ai.py" — eine Wahrheit an zwei Stellen, von Hand
gleich gehalten.

## Wohin

Jede Aufgabe hat genau ein Modul, und die Abhängigkeiten zeigen in eine
Richtung — von oben (wer einen Chat startet) nach unten (was er dafür braucht):

```
   kern            der eine Einstieg: kern.chat(verlauf) wählt den Weg
     │
     ├── ai            Weg „lokal" (Ollama-Adapter)
     ├── cloud         Weg „Anthropic"
     └── cloud_openai  Weg „OpenAI-kompatibel"
           │  alle drei benutzen:
           ├── werkzeug_schleife  die eine Tool-Schleife
           │     ├── erlaubnis    welche Tools bestätigt werden müssen + die Frage dazu
           │     └── ki_antwort   Bild-Marker aus der Antwort ziehen, Zug zum Merken geben
           ├── ki_werkzeuge       was ein Tool TUT (Kalender, Notizen, Netz, Mail …)
           ├── ki_prompt          Prompt-Bausteine: Jetzt-Block, Imprint, Alarme, Denk-Heuristik
           └── ai_backends        Einstellungen: wer darf denken, welches Modell, wie tief
   ─────────────── darunter: Dienste und Fundament ───────────────
   consolidation  (nach dem Zug: Transkript, Graph wenn an)   ollama (Ollama-Anbindung)
   graph · gedaechtnis · kalender · mail · news · web …       state · net · providers …
```

## Bauabschnitte (je ein Commit, volle Testsuite dazwischen)

**Stand 2026-10-06 nachts: K1–K5 erledigt, 0 Import-Kreise.** `ai.py` ist von
1.328 auf rund 320 Zeilen geschrumpft (der Ollama-Weg plus Durchreiche).
Geprüft mit der vollen Testsuite und zwei echten Chat-Zügen durch den
laufenden Server gegen die Cloud (einer mit Werkzeug-Aufruf `read_time`).

| # | Was | Löst |
|---|---|---|
| K1 | `core/ollama.py`: Ollama-Adresse, Modell, Kontext, Sampling, Denk-Schalter, Erreichbarkeit, Warmup — einmal | `ai_backends → ai`, die kopierten Werte in `consolidation` |
| K2 | Merken-Warteschlange (`_async_save_turn` + Worker) zieht nach `consolidation` | `consolidation → ai` |
| K3 | `core/erlaubnis.py` und `core/ki_antwort.py` | `werkzeug_schleife → ai` |
| K4 | `core/ki_prompt.py` und `core/ki_werkzeuge.py`; Graph-Seed nach `graph` | `cloud → ai`, `cloud_openai → ai` |
| K5 | `core/kern.py`: der eine Einstieg, wählt den Weg; `ai_backends` wählt kein Modul mehr | `ai_backends → cloud/cloud_openai` |

`ai.py` behält seine alten Namen als **Durchreiche** (z. B. `ai.TOOLS`,
`ai._execute_tool`), damit Bench-Skripte und der Tutor weiterlaufen. Neuer
Code benutzt die eigentlichen Module. Tests, die per `monkeypatch` etwas
ersetzen, zielen auf das Modul, das es wirklich benutzt — sonst ersetzt der
Test eine Durchreiche und das Original läuft unbemerkt weiter.

Danach: die Regler sauber (Env-Wirrwarr aus dem Abgleich vom 05.10.), die
Hausregeln/Steckbrief hinter die Erlaubnis-Abfrage, und — wenn alles steht —
die „Straße" weiter: Ollama als normaler Anbieter in der Anbieter-Liste und
`fahrzeug()` als die eine Stelle, die Anbieter, Modell und Schiene auflöst.
