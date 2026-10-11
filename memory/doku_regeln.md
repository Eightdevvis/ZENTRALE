# Doku-Regeln für `memory/`

**Stand 2026-10-11:** Die acht Regeln unten gelten für jede Datei unter
`memory/`. Der einmalige Umbau vom 18.09. ist erledigt (Historie unten).

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

## Historie

- **2026-09-18** — Einmaliger Umbau durch einen Hintergrund-Agenten: alle
  `memory/**/*.md` außer den Indizes auf die Regeln 1–7 gebracht (ein Commit
  je Bereich). Erledigt; seither gilt Regel 8 („beim Anfassen sofort").
