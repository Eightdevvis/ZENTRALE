# Doku-Regeln für `memory/`

**Stand 2026-10-11:** Die neun Regeln unten gelten für jede Datei unter
`memory/`. Der einmalige Umbau vom 18.09. ist erledigt (Historie unten). Seit
11.10. ist eine Datei höchstens **600 Zeilen** lang (Regel 9);
`tests/test_memory_groesse.py` prüft das gegen die Altlasten-Liste unten.

**Warum (Sasha, 2026-09-18):** Die Doku ist Claudes wichtigstes Hilfsmittel —
und sie driftet. Zwei Fälle an einem Tag: `betrieb/auto_unlock.md` behauptete
„Reboot-Test offen", `tutor/INDEX.md` „das Gate ist Pflicht". Beides
wurde zuerst geglaubt. Eine falsche Doku ist schlimmer als keine.

Was die Doku leisten muss, kann der Code nicht: das **Warum** (Entscheidungen,
Fehlschläge, Absichten). Was der Code kann — Struktur, Dateien, Routen — gehört
nicht in Prosa, sondern in einen Bauplan mit Test (z. B.
`system/bauplan_kern.md` + `tests/test_kern_bauplan.py`; der Tutor-Bauplan
ist am 2026-10-09 mit ins Repo `language-tutor` gezogen).

## Die Regeln (gelten ab jetzt für jede Datei unter `memory/`)

1. **Stand zuerst.** Jede Datei beginnt nach der Überschrift mit einem Block
   `**Stand <Datum>:**` — was *heute* gilt, in wenigen Sätzen. Wer nur das liest,
   weiß Bescheid.
2. **Dann das Warum.** Entscheidungen mit Grund (»weil …«), bekannte Fallen,
   was probiert wurde und scheiterte. Das ist der wertvolle Teil — bleibt,
   wird nicht gekürzt.
3. **Historie ans Ende, komprimiert.** „Früher war es so, dann …"-Erzählung in
   einen Abschnitt `## Historie` unten, auf das Nötige eingedampft (Datum,
   was, warum). Kein Roman.
4. **Ein Fakt, eine Datei.** Steht dasselbe an zwei Stellen, bleibt es an der
   passendsten und die andere verweist (`siehe …`). Sonst müssen bei jeder
   Änderung drei Dateien angefasst werden — und eine wird vergessen.
5. **Nichts erfinden, Widersprüche markieren.** Wer beim Umsortieren einen
   Satz findet, der dem Code oder einer anderen Datei widerspricht und es
   nicht aus dem Code klären kann, schreibt `⚠ prüfen:` davor statt zu raten.
6. **Struktur gehört in Bauplan + Test.** Verzeichnisbäume, Artefakt-Listen,
   Routen-Tabellen in Prosa-Dateien → Verweis auf den Bauplan des Bereichs.
   Gibt es keinen, ist das ein Auftrag für einen (wie beim Tutor).
7. **Index nur Zeiger.** `INDEX.md` sagt WO etwas steht, nie WAS gilt.
8. **Beim Anfassen sofort.** Jede Datei, die man aus einem anderen Grund
   editiert, wird dabei auf diese Regeln gebracht.
9. **Höchstens 600 Zeilen, neues Thema = neue Datei.** Kommt ein neues Thema
   dazu, bekommt es eine eigene Datei und eine Zeile im `INDEX.md` des
   Bereichs. Sammeldateien (Überblicke wie `ki/ki_system.md`, Pläne) bekommen
   dafür nur einen Verweis — keinen neuen Abschnitt. Gilt für alle
   `memory/**/*.md` außer `memory/archive/`.
   **Warum (2026-10-11):** `ki/ki_system.md` war auf 2.065 Zeilen gewachsen,
   weil Agenten bei jeder Änderung einen Abschnitt angehängt haben (51 Commits
   seit 15.09.). So eine Datei liest niemand mehr ganz — also auch nicht den
   Satz, der dem neuen widerspricht. Für Code gibt es dieselbe Grenze längst
   (`system/bauplan_kern.md`, „Altlast: Riesen").

## Altlast: Riesen-Dateien

Grenze: 600 Zeilen je `memory/**/*.md` (ohne `memory/archive/`). Die Zahl
rechts ist **eingefroren**: die Datei darf nicht wachsen, und wenn sie
schrumpft, wird die Zahl hier gesenkt — unter 600 fliegt die Zeile raus.
Neue Dateien kommen nie auf diese Liste: aufteilen statt eintragen.
`tests/test_memory_groesse.py` liest diese Tabelle.

| Datei (unter `memory/`) | Zeilen höchstens |
|---|---|
| `system/dashboard.md` | 1308 |
| `ki/claude_web_plan.md` | 1063 |
| `werkzeuge/kalender_system.md` | 728 |
| `system/tui_bauplan.md` | 650 |
| `werkzeuge/mail_system.md` | 636 |
| `ki/cloud_umstieg_plan.md` | 621 |
| `werkzeuge/kalender_ansichten_vorschau.md` | 606 |

**Wenn der Test rot wird:**
- **„neu über der Grenze"** — das neue Thema in eine eigene Datei ziehen,
  im `INDEX.md` des Bereichs eintragen, in der alten Datei nur verweisen.
- **„Riesen-Datei gewachsen"** — dasselbe: was dazukam, gehört in eine eigene
  Datei. Nicht die Zahl hier erhöhen.
- **„kleiner geworden"** — die Zahl hier senken oder die Zeile streichen.

## Historie

- **2026-10-11** — Regel 9 (600 Zeilen) mit Test und Altlasten-Liste;
  `ki/ki_system.md` nach Themen in 14 Dateien zerlegt (plus Überblick).
- **2026-09-18** — Einmaliger Umbau durch einen Hintergrund-Agenten: alle
  `memory/**/*.md` außer den Indizes auf die Regeln 1–7 gebracht (ein Commit
  je Bereich). Erledigt; seither gilt Regel 8 („beim Anfassen sofort").
