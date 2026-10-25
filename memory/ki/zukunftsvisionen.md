# Zukunftsvisionen

> **Über allem steht das Leitbild** ([../leitbild.md](../leitbild.md)): das
> Zuhause, das hört, sieht, spricht und handelt. Die Ideen hier ordnen sich
> dort in die Etappen ein; der Hub ist Unterbau, nicht Ziel.

Ideen von Sasha für später. Nichts davon ist gebaut oder geplant. Hier steht
nur, WAS gewünscht ist, damit es nicht verloren geht. Wird etwas davon
angegangen, bekommt es eine eigene Themendatei, und hier bleibt nur der
Verweis. Klassifikator-Ideen für die KI selbst (Werkzeuge vorab einlegen,
Fokus-Prüfkette, Modell als Richter): KI-Bibel
[bibel/klassifikatoren.md](bibel/klassifikatoren.md).

## Was mache ich gerade? (Klassifikator, 11.10.2026)

Ein selbst trainierter Klassifikator soll erkennen, was Sasha gerade macht und
wie viel freie Zeit er gerade hat.

Wofür:
- Die Assistenz meldet sich dann im passenden Moment und nicht mitten in etwas
  hinein.
- Sie schätzt, ob gerade Zeit für Lernen, Training oder Erledigungen ist.

Anknüpfen kann das an:
- den bestehenden Klassifikator mit seiner Beispiel-Sammlung
  ([ehrlichkeit_live.md](ehrlichkeit_live.md)), der Weg „erst Beispiele
  sammeln, dann trainieren“ ist dort schon angelegt,
- an Kalender, Tagesphasen und Schlafzeiten von der Smartwatch.

## Gesundheits-, Aktivitäts- und Krankheits-Logbuch (11.10.2026)

Sasha möchte ein vollständiges Logbuch über Gesundheit, Aktivität und
Krankheit führen. Die Messreihen im Gedächtnis-Thema `gesundheit` sind ein
Anfang ([gedaechtnis.md](gedaechtnis.md)).

Gibt es das Logbuch, wandert der Punkt „Aktuell gedrosselt: er war krank“ aus
den Zielen dorthin. Die Ziele sagen dann nur noch, wohin es geht, und das
Logbuch sagt, wie es gerade steht.

## Prüfkette „stört es den Fokus?“ (14.10.2026)

Im Steckbrief stand, die stabilen Regeln seien „der Grund, warum eine Antwort
manchmal gegen den spontanen Wunsch geht“. Als Satz im Prompt bewirkt das
nichts Prüfbares, deshalb ist er gestrichen. Stattdessen später eine harte
Prüfkette (oder ein Klassifikator): erst den aktuellen Fokus prüfen, dann
Sashas Nachricht abwägen, dann entscheiden, ob das Gewünschte den Fokus
stört. Gehört zum Schema, das nach der Grund-KI kommt.

## Der Tagesplan und das Reinschauen (24.10.2026) — die nächste der drei

Näher in der Zeit als „Parasite" und „Chefkoch". ZENTRALE entwirft den
Tagesplan (Vorbild: Claude plante Sasha am 24.10. das Wochenende — Pflicht
heute, der Rest verteilt, Wege zusammengelegt). Und sie **schaut ab und zu
rein**:

> *„zentrale schaut aber auch zu, und merkt, wenn ich auf meinen technischen
> geräten youtube anschmeiße statt zu arbeiten wie ich es sollte. damit kann
> zentrale mutti spielen. nagut, 10 minuten noch schauen. danach aber an die
> arbeit, sonst wirds zu spät. oh nein, so spät schon, ab ins bettchen. also
> nich in dem ton. aber du checkst es lol. zentrale soll nich immer überwachen
> was ich so mache, wie eine mutti ja auch nich pausenlos auf deine hände
> starrt, aber ab und zu checkt sie halt mal rein um zu sehen obs läuft."*

- **Stichprobe, nicht Dauerblick:** ab und zu nachsehen, nie pausenlos.
- **Ton:** freundlich, auf Augenhöhe — „noch 10 Minuten, dann weiter"; nie
  von oben. Passt zur Haltung aus dem Leitbild: ZENTRALE traut dem Menschen.
- Grundlage: „Was mache ich gerade?" (oben), Anwesenheit
  ([../system/anwesenheit_und_ring.md](../system/anwesenheit_und_ring.md)),
  Tagesphasen, Schemen ([../leitbild.md](../leitbild.md), Etappe 5).
  Gesehen wird lokal; was sie bemerkt, bleibt bei Sasha.

## Chefkoch in der Küche (24.10.2026)

> *„ich komme in die küche, frage chefkoch, was wir machen sollen. ein display
> an der wand. chefkoch zeigt mir direkt visuell was wir machen wollen. oder
> ich komme vom einkaufen zurück, mit kameras erfasst er direkt was ich gekauft
> habe und updated den virtuellen bestand. oder zentrale scanner der das budget
> gemacht hat reicht die infos auch direkt an chefkoch weiter, wenn er
> mitkriegt dass chefkoch hier benachrichtigt sein sollte."*

- Chefkoch als App im Hub, mit Bildschirm in der Küche (eine Oberfläche dort).
- Einkauf erkennen per Kamera → Vorrat; oder über die Quittung, die der
  Scanner fürs Budget gelesen hat (Szene „Heimkommen mit Einkäufen" im
  Leitbild) — **dieselbe Quittung, zwei Apps**: der Hub reicht sie weiter,
  wenn eine App sie brauchen kann (Ereignisse, „dasselbe Objekt, nicht kopiert").
- Heute gibt es Chefkoch als Claude-Skill (`chefkoch-ai`); als ZENTRALE-App
  wäre er der erste Mieter der Küche.

## ZENTRALE Parasite (24.10.2026)

> *„man kann zentrale parasite aufs handy laden und aktivieren und das ding
> wird quasi als app anfangen, app zentrale, und dann stück für stück dein
> ganzes gerät umbauen und umformen bis alles was du vom handy siehst quasi
> nur noch ein remote controller für zentrale ist."*

- Fängt als gewöhnliche App an und übernimmt Stück für Stück das Gerät —
  Startbildschirm, Benachrichtigungen, Eingabe — bis das Handy nur noch eine
  Fernbedienung für ZENTRALE ist.
- Weg dahin auf Android: Launcher → Standard-Apps (SMS, Telefon, Assistent) →
  Bedienungshilfen/Geräteverwaltung; jeder Schritt mit ausdrücklicher
  Zustimmung (Grundpfeiler, nichts heimlich) und jederzeit umkehrbar.
- Baut auf dem Handy als Knoten auf ([../system/zen_mobile.md](../system/zen_mobile.md)).
