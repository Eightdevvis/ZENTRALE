# Doku-Regeln für `memory/` — und der einmalige Umbau

**Warum (Sasha, 2026-09-18):** Die Doku ist Claudes wichtigstes Hilfsmittel —
und sie driftet. Zwei Fälle an einem Tag: `betrieb/auto_unlock.md` behauptete
„Reboot-Test offen", `tutor/tutor_system.md` „das Gate ist Pflicht". Beides
wurde zuerst geglaubt. Eine falsche Doku ist schlimmer als keine.

Was die Doku leisten muss, kann der Code nicht: das **Warum** (Entscheidungen,
Fehlschläge, Absichten). Was der Code kann — Struktur, Dateien, Routen — gehört
nicht in Prosa, sondern in einen Bauplan mit Test (`tutor/bauplan.md`,
`tests/test_tutor_bauplan.py`).

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

## Der einmalige Umbau (Hintergrund-Agent, 2026-09-18)

Auftrag: alle `memory/**/*.md` außer `INDEX.md`-Dateien auf die Regeln 1–7
bringen. Reihenfolge nach Nutzen: `betrieb/`, `system/`, `tutor/`, `ki/`,
`werkzeuge/`, `maps/`, dann `ueberblick.md`, `claude_hinweise.md`.

Pro Datei:
- Stand-Block oben (aus dem, was in der Datei als aktuell erkennbar ist —
  neuestes Datum gewinnt; bei Zweifel gegen den Code prüfen).
- Warum/Entscheidungen behalten; Historie nach unten und eindampfen.
- Mehrfachnennungen zwischen Dateien auflösen (eine Heimat, sonst Verweis).
- Widersprüche mit `⚠ prüfen:` markieren, nicht auflösen durch Raten.
- Verweise (`siehe …`, Pfade) müssen nach dem Umbau noch stimmen.
- `INDEX.md`-Zeilen nur anpassen, wenn sich Dateinamen oder Themen ändern.

Nicht anfassen: `tutor/bauplan.md`, `tutor/naturalisierung.md`,
`betrieb/wachplan.md`, `system/audio_strasse.md` (frisch, schon in Form).

Ergebnis: ein Commit je Bereich auf dem Arbeits-Branch, nicht gepusht —
Claude schaut den Diff durch, dann geht es nach `main`.
