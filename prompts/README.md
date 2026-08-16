# Prompts der Core-KI — Lesefassung

Hier liegen die **Prompts der ZENTRALE-KI selbst** und der KI, die im
Hintergrund für sie arbeitet (Graph-Extraktor, News). Auf Deutsch, am Stück
lesbar, damit man sie durchsehen und umschreiben kann, ohne sich durch Python
zu wühlen.

**Keine zweite Quelle der Wahrheit.** Live steht jeder Prompt im Code; jede
Datei nennt oben, in welcher **Code-Datei** und unter welchem **Konstantennamen**.
Änderungen wandern von hier aus **von Hand** zurück in den Code — es gibt keinen
Generator, der das abgleicht. Wer hier ändert und den Code vergisst, hat nichts
geändert.

> **Keine Tutor-Prompts.** Die liegen seit dem Herauslösen des Tutors in
> `tutor/prompts/` und in `tutor/langs/<sprache>/`. Das Projekt ist am Stück
> rausziehbar, seine Prompts gehören dazu. Der frühere Tutor-Teil dieses
> README (inklusive der Warnung, chinesische Persona-Prompts **nicht**
> ins Deutsche zurückzuspielen) steht jetzt in `tutor/prompts/README.md`.

## Welche Schiene steht hier?

Seit dem Schienen-Umbau 08/2026 hat **nicht mehr jedes Modell denselben
Prompt** (`core/profil/`):

| Schiene | für | Datei |
|---|---|---|
| `klein` | qwen3.5:9b und Verwandte, lokal über Ollama | `core/profil/klein.py` |
| `gross` | Claude, GPT, Gemini & Co. über den Cloud-Pfad | `core/profil/gross.py` |

**Die Dateien hier zitieren `klein`** — die ausführliche Fassung mit allen
Krücken für kleine Modelle. `gross` **kopiert die Persona nicht**, sondern
leitet sie ab und nimmt heraus, was reine Modellgröße ist: das `antwort`-Tool,
die Bild-Marker, den Dashboard-Block, `## Text-Effekte`, das Turn-Beispiel und
die 9B-Belehrungen aus den Meta-Regeln. Wer sie IST, bleibt in beiden gleich —
sonst hätte ZENTRALE zwei Persönlichkeiten, je nachdem welches Backend läuft.

### Den Cloud-Prompt willst du sehen? Nicht hier — im Skript

Weil `gross` teils abgeleitet ist, gibt es von ihm **absichtlich keine
Abschrift** in diesem Ordner: eine dritte Fassung würde still wegdriften.
Stattdessen baut ein Skript den Prompt aus dem Live-Code:

```
scripts/prompt_zeigen.py                 # der Cloud-Prompt, genau wie er rausgeht
scripts/prompt_zeigen.py --tools         # dazu das Tool-Schema
scripts/prompt_zeigen.py --diff          # was gross gegenüber klein weglässt
scripts/prompt_zeigen.py --woher         # Landkarte: welchen Regler dreh ich wo?
scripts/prompt_zeigen.py --schiene klein # die lokale Fassung
```

`--woher` ist der wichtige: es sagt dir, welche Änderung **nur** die Cloud
trifft und welche **beide** Schienen — die Persona ist geteilt, die Meta-Regeln
nicht. Warum welcher Schnitt fällt, steht ausführlich im Kopfkommentar von
`core/profil/gross.py`; jede betroffene Datei hier sagt es oben im ⚠-Block kurz.

## Dateien

### Core-KI — geht bei jedem Chat-Turn mit raus

| Datei | Was | Schiene |
|-------|-----|---------|
| [core-ki_system.md](core-ki_system.md) | System-Prompt: Rolle, Stimme, Länge | `klein`, `gross` leitet ab |
| [core-ki_meta-regeln.md](core-ki_meta-regeln.md) | Meta-Regeln (nicht lügen, nichts erfinden, Subjekt-Grenze) | `klein`, `gross` hat eigene |
| [core-ki_mic-hint.md](core-ki_mic-hint.md) | Spracheingabe-Hinweis + „Jetzt"-Block | beide |
| [core-ki_selbstbild.md](core-ki_selbstbild.md) | kann / kann-nicht — **kein Prompt-Text**, sondern Graph-Knoten | schienen-unabhängig |

`core-ki_selbstbild.md` fällt bewusst aus der Reihe: das Selbstbild steht nicht
im Prompt, sondern als Knoten im Graphen und kommt nur dann in den Kontext,
wenn die Frage thematisch dorthin greift.

### Hintergrund-KI — läuft ohne Sasha im Bild

| Datei | Was |
|-------|-----|
| [memory-extraktor.md](memory-extraktor.md) | Graph-Extraktor: Turn → Knoten und Kanten |
| [news.md](news.md) | News-Pipeline: Label, Sendung, Rückblick, Aufholmodus |

## Wenn du hier etwas änderst

1. Prompt-Text in der genannten Code-Datei anpassen — das ist der Live-Stand.
2. Prüfen, ob die Änderung **beide** Schienen betrifft. Ein Schnitt in der
   Persona von `klein` erreicht `gross` automatisch (abgeleitet); ein Schnitt
   in den Meta-Regeln **nicht** (eigener Text).
3. Diese Lesefassung nachziehen, sonst driftet sie weg.
4. `venv/bin/python -m pytest tests/test_profil.py` — dort ist festgenagelt,
   was in welcher Schiene stehen muss.
