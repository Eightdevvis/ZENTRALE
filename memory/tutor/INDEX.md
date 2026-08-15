# Sprach-Tutor — Index

Der Tutor ist ein **eigenes Projekt** in `tutor/`, am Stück rausziehbar. Die
einzige Naht zum Kern ist `core/tutor_port.py`; Keys und die cloud/local-Wahl
gehören dem Kern, nie dem Tutor.

| Was du wissen willst | Datei |
|---|---|
| **Einstieg.** Aufbau des Persona-Portals, Sprachprofile, Vokabel-Modell, austauschbare Provider | [tutor_system.md](tutor_system.md) |
| Wie die Persona zuverlässig kurz und in der Zielsprache bleibt — Testläufe gegen echtes qwen-plus | [tutor_persona_tuning.md](tutor_persona_tuning.md) |
| Die Roleplay-Features (Zimmer, Shop, Kisten) und warum sie so entschieden wurden | [tutor_roleplay_features.md](tutor_roleplay_features.md) |

## Grenze zum Kern

Der Tutor hat sein **eigenes** Gedächtnis (`tutor/memory.py`, Notiz-Modell) —
**nicht** den Konzept-Graphen der Kern-KI. Die beiden Speicher fassen sich nie
an. Wie die Kern-KI sich erinnert, steht in
[../ki/ki_system.md](../ki/ki_system.md).
