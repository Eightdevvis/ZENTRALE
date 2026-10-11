# Skills — `load_skill`, `propose_skill`, `edit_skill`

**Stand 2026-10-11:** Skills im Format von Claude (`SKILL.md` mit `name` +
`description`) unter `data/gedaechtnis/ki/skills/<name>/` (bis zum Gedächtnis-Umzug vom 11.10.2026: `skills/<name>/`). Drei Stufen: Liste im
festen Kopf (Deckel 6.000 Zeichen, wird nicht gleichmäßig gekürzt), Anleitung
per `load_skill`, Dateien per `load_skill(datei=…)`; Skripte nur über
`run_code(skill=…)`. Anlegen/Umschreiben ist gegatet, abschalten kann nur Sasha.
14 Anthropic-Skills als Vorlagen. Übernehmen von Claude-Skills aus Input/:
[nutzerordner.md](nutzerordner.md).

**Warum:** Sasha: echte Claude-Skills sollen ohne Umbau hineinpassen. Ein Skill
ist eine Anleitung für eine Art Aufgabe, keine Regel — was immer gilt, sind
Hausregeln. Aus `ki_system.md` ausgelagert am 2026-10-11 (Inhalt unverändert übernommen).

## Skills — `load_skill`, `propose_skill`, `edit_skill` (seit 2026-10-07)

Phase 4 des [Claude-Web-Plans](claude_web_plan.md); seit dem Abend des
07.10. im **Format von Claude** (Sasha: echte Claude-Skills sollen ohne
Umbau hineinpassen). Ein Skill ist eine **Anleitung für eine Art Aufgabe**
(„Woche planen", „einen Skill bauen"), keine Regel: was immer gilt, sind
Hausregeln. Module `core/skills.py`, `core/skill_format.py`,
`core/skill_umzug.py` (Schicht 2), Ordner `data/gedaechtnis/ki/skills/<name>/`
mit `SKILL.md` — Aufbau, Status, Umzug und Erstbefüllung in
[gedaechtnis_dateien.md](gedaechtnis_dateien.md), Abschnitt „Skills".

**Drei Stufen wie bei Claude („Progressive Disclosure"):**
1. **Liste im Kopf.** `skills.prompt_block()` steht im festen, gecachten
   Kopf (`cloud._static_system`, hinter dem Gedächtnis-Kopf, nur wenn die
   Schiene `MERKMALE["skills"]` hat — `gross` ja, `klein` nicht): eine
   Zeile `- name — description` je **aktivem** Skill, nach Name sortiert,
   ohne Datum oder Zähler. Die `description` ist Claudes Auslöser und darf
   bis 1.024 Zeichen lang sein. **Deckel für die ganze Liste: 6.000
   Zeichen** (`LISTE_MAX`, ≈ 1.700 Token, gecacht ≈ 0,05 Cent je Zug; nicht
   größer als der übrige feste Kopf). Die Start-Skills brauchen ~4.300.
   **Seit 2026-10-08 nicht mehr gleichmäßig gekürzt** (Sasha: das
   verschlechtert alle Beschreibungen): sie bleiben vollständig, und
   Customize → Skills zeigt „Liste zu lang: N von 6 000 Zeichen — schalte
   Skills aus, die du nicht brauchst" (`skills.liste_lage()`, in
   `/api/skills` und `/api/gedaechtnis` als `skill_liste`). Nur als letzte
   Rettung bekommen die **längsten** nacheinander eine Kurzfassung
   (`skills.kurzfassung`: erster Satz, 160–320 Zeichen), bis es passt; die
   kurzen bleiben unangetastet. Reicht das nicht, stehen die längsten nur mit
   Namen da. Reihenfolge (Länge absteigend, Name) — deterministisch.
2. **Anleitung per `load_skill(name)`** als Werkzeug-Ergebnis (wandert mit
   dem Verlauf, berührt den Cache-Anfang nicht): der Text der SKILL.md ohne
   Kopf, je Aufruf 20.000 Zeichen (weiter mit `ab`), dazu die Liste seiner
   Dateien (ohne Lizenz und `_zentrale.json`). Liegt `references/zentrale.md`
   im Skill (ZENTRALEs Zusatz zu einem fremden Skill), steht vorne der
   Hinweis, sie zuerst zu lesen.
3. **Dateien per `load_skill(name, datei=…)`** (references/, assets/,
   scripts/ lesen); kein Weg aus dem Skill-Ordner (echter Pfad muss drin
   liegen, Verweise aufgelöst), Binärdateien nur als Hinweis. **Skripte
   laufen nur über `run_code(skill=…)`** in der Sandbox (s. [sandbox.md](sandbox.md)).

Wann laden, wann vorschlagen: Meta-Regel 6 in `profil/gross.py`.

| Werkzeug | Was | Gate |
|---|---|---|
| `load_skill(name, datei?, ab?)` | Anleitung bzw. Datei eines aktiven Skills; ausgeschaltete/vorgeschlagene geben nichts heraus | nein |
| `propose_skill(name, beschreibung, inhalt)` | neuen Skill anlegen: `SKILL.md` (Kopf nur `name` + `description`) + `_zentrale.json` (`herkunft: ki`, `status: aktiv`); bestehender Name → Fehler | **ja** — Frage zeigt Name, Beschreibung, erste drei Zeilen |
| `edit_skill(name, inhalt)` | Anleitung ersetzen; der YAML-Kopf bleibt Zeichen für Zeichen (auch fremde Felder), alte Fassung als `SKILL.md.bak` | **ja** |

Sagt Sasha nein, läuft der Ausführer gar nicht: die Schleife meldet dem
Modell „abgelehnt — nichts ausführen" (`werkzeug_schleife.run_tool`), es
entsteht keine Datei. Ein vom Modell mitgeschickter Kopf (mit `name` oder
`description`) wird bei `edit_skill` verworfen: Name und Beschreibung ändert
nur Sasha, Status und Herkunft stehen ohnehin in `_zentrale.json`. Grenzen:
Beschreibung ≤ 1.024 Zeichen ohne `<` `>` (Claudes Regeln), Anleitung ≤
20.000. Die KI kann nur die SKILL.md schreiben, keine weiteren Dateien.
Text-Budget der drei Beschreibungen: eigener Deckel < 600 Zeichen in
`tests/test_profil.py`. Anzeige: `GET /api/skills` mit `braucht` und
`vermerk` ([api_endpoints.md](../system/api_endpoints.md)). Sasha sieht und
schaltet Skills in der TUI (`/skills` im Chat, Gedächtnis-Ansicht;
`POST /api/skills/<name>/status`) — die KI kann keinen Skill abschalten.

**Skills von Anthropic** (seit 2026-10-07): 14 Skills aus
github.com/anthropics/skills (Commit 683bc88, nur Apache 2.0) liegen als
Vorlagen in `core/skill_vorlagen/anthropic/` (Herkunft und Lizenz:
`README.md` dort). An: skill-creator, academy-guide, claude-api,
discernment-nudge, frontend-design, internal-comms. Aus mit „braucht: …"
(Browser, Bildausgabe, Node/npm, MCP, Slack): die übrigen acht. Der
skill-creator bekam `references/zentrale.md` dazu — was davon hier geht
(Testläufe selbst ausführen, Ergebnisse in die Ablage, kein `claude -p`,
kein Browser).

**`import-memory`** (seit 2026-10-08, `herkunft: zentrale`): Erinnerungen aus
einer anderen KI übernehmen, nach Claudes Skill gleichen Namens neu
geschrieben. Geschrieben wird nur über `write_note(…, herkunft="claude")` —
zeilenweise, nur Neues, mit Herkunftsvermerk, nie Kataloge/Tagebuch
([gedaechtnis_dateien.md](gedaechtnis_dateien.md), „Import aus einer
anderen KI").

## Historie

- **2026-10-07** — Phase 4, abends auf das Claude-Format umgestellt; Anthropic-Skills.
- **2026-10-08** — Liste nicht mehr gleichmäßig gekürzt; `import-memory`.
- **2026-10-11** — aus `ki_system.md` ausgelagert.
