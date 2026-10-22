# KI-Bibel — der Leitfaden, wie die KI gebaut wird

**Stand 2026-10-22 (abends):** 77 Einträge in zehn Teilen. Status: 21 umgesetzt,
17 teilweise, 39 offen (nach dem Durchgang Recherche). Jede Regel hat eine Quelle (offiziell
von Anthropic, inoffiziell oder von Sasha). Wer an der KI baut, liest vorher
die betroffenen Einträge und zieht danach den Status nach (Pflegeregeln unten).

## Zweck

Hier stehen alle Regeln und Tipps, nach denen ZENTRALEs KI gebaut wird,
geordnet und mit Quelle. Sasha will alles umsetzen, auch das Inoffizielle.
Später geht pro Eintrag ein Agent durch die Architektur und setzt ihn um.

Die Bibel sagt, **wonach** gebaut wird. **Wie** es heute gebaut ist, steht in
den Themendateien von `memory/ki/` (z. B. `memory/ki/prompt_aufbau.md`,
`memory/ki/werkzeuge.md`, `memory/ki/werkzeug_suche.md`). Die Bibel verweist
auf sie und kopiert nichts.

## Pflegeregeln

1. **Nichts ohne Quelle.** Jeder Eintrag nennt URL oder „Sasha“ und ein Datum.
2. **Neue Erkenntnisse kommen sofort in die Bibel**, in den passenden Teil,
   mit neuer Kennung (fortlaufend, Kennungen werden nie neu vergeben).
3. **Vorher lesen, danach nachziehen.** Wer an der KI baut (Prompt,
   Werkzeuge, Schienen, Prüfer), liest vorher die betroffenen Einträge. Danach
   stellt er den Status um, mit Fundstelle und Commit-Hash.
4. **Inoffizielles ist deutlich markiert** (fett **inoffiziell**, mit
   „unbestätigt“, wenn es aus einem Leak stammt).
5. **Das Prompt-Budget gilt** (`tests/test_prompt_budget.py`, 21.000 Zeichen).
   Eine Regel, die nur ein Werkzeug betrifft, gehört in dessen Beschreibung,
   nicht in den Prompt.
6. Die Übersichten unten (Inhalt, nach Modell/Schiene) sind nur Verweise.
   Kommt ein Eintrag dazu oder ändert sich sein „Gilt für“, beide mitziehen.

## Legende

Jeder Eintrag hat eine Kennung und dieses Schema:

| Feld | Bedeutung |
|---|---|
| **Regel** | was gilt, deutsch, kurz |
| **Zitat** | Originaltext (englisch), falls vorhanden; sonst — |
| **Quelle** | URL oder „Sasha“; Art: offiziell / **inoffiziell** / Sasha; Datum. „erfasst“ = Tag der Aufnahme in die Bibel, die Quelle wurde dabei nicht neu abgerufen |
| **Gilt für** | `alle` · `claude-gross` (Claude auf der Schiene gross) · `qwen` (qwen-Profil beim Budget-Rückfall) · `klein/ollama` (lokales Modell, Schiene klein) |
| **Status** | `umgesetzt` · `teilweise` · `offen`, mit Fundstelle im Code (~Zeile) und Commit, falls bekannt. Beim Anlegen nur kurz per Suche geprüft; wo unklar: offen |
| **Heute bei ZENTRALE** | ein, zwei Sätze zum Ist-Stand |

Kennungen: `P` Prompt · `W` Werkzeuge · `R` Recherche · `H` Handeln ·
`S` Skills · `KT` Kontext (nicht `K`, das sind die Fehlercodes) · `D` Denken ·
`PR` Prüfung · `KL` Klassifikatoren · `B` Baustellen.

„Sasha (Befund im Code)“ heißt: ein Fehler, den wir in ZENTRALE gefunden
haben, keine Regel von außen.

## Inhalt

| Teil | Einträge | Status (u/t/o) |
|---|---|---|
| [prompt.md](prompt.md) — Länge, Aufbau, Ton, Großbuchstaben | P-01 Länge wie Anthropic · P-02 keine Großbuchstaben-Befehle · P-03 Flughöhe, Abschnitte · P-04 Beispiele statt Sonderfälle · P-05 Anthropic nachahmen · P-06 keine Kalender-Schlagseite | 1/2/3 |
| [werkzeuge.md](werkzeuge.md) — Beschreibungen, Suche, Ergebnisse | W-01 Beschreibung wichtigster Hebel · W-02 Fehler sagen, was tun · W-03 Freigabe-Text stimmt · W-04 keine Überschneidung · W-05 Beispiele · W-06 knappe Ergebnisse · W-07 Werkzeug-Suche, max. 5 · W-08 Suche im Prompt (Schritt 9) · W-09 Prüfstand A/B (Schritt 10) · W-10 Sashas Wörter · W-11 Großbuchstaben in Beschreibungen · W-12 Programmatic Tool Calling · W-13 Claude Code ~15 geladen · W-14 Kalender-Felder nur aus Sashas Angaben | 1/5/8 |
| [recherche.md](recherche.md) — suchen, lesen, Runden, Fazit | R-01 Lesen anweisen · R-02 suchen → auswählen → lesen · R-03 breit, dann eng · R-04 Aufrufe nach Schwierigkeit · R-05 Adresse immer lesen · R-06 Schnipsel reichen nicht · R-07 Widersprüche → weitersuchen · R-08 Erfolgskriterien · R-09 Hypothesen, Notizen · R-10 erst nachsehen · R-11 nicht endlos suchen · R-12 Aktuelles nachprüfen · R-13 Recherche-Skill · R-14 Rechenschaft · R-15 mehrere Runden · R-16 schnelle Suche · R-17 Platz für Suchregeln · R-18 Vorbilder | 14/2/2 |
| [handeln.md](handeln.md) — handeln statt fragen | H-01 standardmäßig handeln · H-02 Ideen/Plan → anhalten · H-03 weiterarbeiten bis fertig · H-04 fertig → berichten · H-05 Rückfragen nur auf Verlangen | 0/1/4 |
| [skills.md](skills.md) — Kurzfassung, voller Text bei Bedarf | S-01 progressive disclosure · S-02 Sasha sichtet vor dem Entfernen | 0/1/1 |
| [kontext.md](kontext.md) — Kontext klein | KT-01 wenig, aber gehaltvoll · KT-02 knapp ≠ kurz · KT-03 Verweise statt Daten · KT-04 alte Ergebnisse raus · KT-05 Kompaktierung · KT-06 Notizen außerhalb | 0/4/2 |
| [denken.md](denken.md) — Nachdenken, effort, parallel | D-01 nach Ergebnissen nachdenken · D-02 effort statt Budget · D-03 parallele Aufrufe · D-04 Selbstcheck · D-05 niedriger effort | 1/0/4 |
| [pruefung.md](pruefung.md) — Richter, Evals, Python-Prüfer | PR-01 Prüfschleife mit Kriterien · PR-02 Regeln für Richter · PR-03 Werkzeuge per Evals · PR-04 Prüfer blind für Recherche · PR-05 Suche ≠ Tat · PR-06 „oder“ · PR-07 eine Runde · PR-08 Bestanden sichtbar · PR-09 Befunde überschrieben · PR-10 Argumente abgleichen · PR-11 Statuszeile · PR-12 Kalender-Werte ohne Grundlage · PR-13 Wochentag im Titel | 4/1/8 |
| [klassifikatoren.md](klassifikatoren.md) — Ideenecke, nicht bauen | KL-01 Werkzeuge vorab einlegen · KL-02 Fokus-Prüfkette · KL-03 Modell als Richter | 0/0/3 |
| [baustellen.md](baustellen.md) — Offenes im eigenen Bau | B-01 Anstupsen · B-02 „Sasha“ im Gedächtnis-Kopf · B-03 Alarm-Block · B-04 Ausweichweg weg · B-05 Budget-Rückfall qwen | 0/1/4 |
| **gesamt** | 77 | **21/17/39** |

## Nach Modell/Schiene

Nur Kennungen; der Inhalt steht im jeweiligen Teil. `alle` gilt zusätzlich
für jede Schiene.

| Gilt für | Einträge |
|---|---|
| **alle** | P-03, P-04, P-06 · W-01–W-06, W-10 · R-01–R-16 · H-01–H-05 · S-02 · KT-01–KT-04, KT-06 · D-01, D-04 · PR-01–PR-03, PR-11 · KL-01–KL-03 · B-01, B-02 |
| **claude-gross** | P-01, P-02, P-05 · W-07, W-08, W-09, W-11, W-12, W-13, W-14 · R-17, R-18 · S-01 · KT-05 · D-02, D-03, D-05 · PR-04–PR-10, PR-12, PR-13 · B-03, B-04 |
| **qwen** | W-07 (Vorauswahl), W-14 · PR-10, PR-12, PR-13 · B-05 |
| **klein/ollama** | nur die `alle`-Einträge; bewusst ausgenommen ist P-02 (klein bleibt in Großbuchstaben, so ist das lokale qwen gemessen) |

## Historie

- **2026-10-22** — angelegt: Struktur von Sasha abgesegnet, Inhalt aus der
  Sammlung vom 14.–22.10. (Anthropic-Doku, Leak Sonnet 5.5, Sashas Regeln,
  Befunde zum Prüfer).
- **2026-10-22** — W-14, PR-12, PR-13 neu (Sasha/Kalender-Session, Gespräch
  20261022-111358-dd6127), PR-10 umgesetzt, B-05 teilweise.
- **2026-10-22** — Durchgang Recherche (R-01–R-18, dazu W-01, W-03, PR-04):
  Werkzeug-Texte, Ergebnis von web_search, Prompt „## Recherche“, Skill,
  Prüfer-Befund `ungelesen` (9cce25a, b41de54, fadfb92, ee018c2).
