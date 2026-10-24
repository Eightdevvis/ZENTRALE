# Leitbild und Plan — wofür es ZENTRALE gibt

**Stand 2026-10-23: beschlossen.** Diese Datei steht über allen anderen. Jede
Entscheidung — Feature, Umbau, Reihenfolge — wird zuerst hieran gemessen.
Hub, Knoten, Cloud und Apps ([hub/hub_bauplan.md](hub/hub_bauplan.md)) sind
**Unterbau**: nötig, aber nebenläufig, nie das Ziel.

## Das Leitbild

> **ZENTRALE ist das Nervensystem deines Zuhauses.** Sie hört, sieht und
> spricht in jedem Raum — über Mikros, Lautsprecher, Kameras und
> Bildschirme. Kommst du heim, macht sie das Licht an, begrüßt dich und
> fragt im Plaudern nach deinem Tag. Alles, was sich mit Information
> erledigen lässt, übernimmt sie. **Und alles, was sie weiß, gehört dir.**

Sasha, 23.10.2026: *„die hauptvision die den ganzen anfang prägte war einfach
nur ein — ich komme heim, zentrale schaltet die lampe an und begrüßt mich und
nimmt mir ein paar datenpunkte im small talk ab für die datenanalyse."* Und:
*„zentrale war die idee einer voll vertechnisierten umgebung. mikros,
lautsprecher, kameras, überall und überall traffic, auch bildschirme.
zentrale lauscht, zentrale spricht, zentrale überwacht. zentrale analysiert,
zentrale stellt bereit, zentrale macht alles in deinem leben was irgendwie
per information gehandhabt werden kann."*

Anlass: *„wenn leute mich fragen was das ist. ich kanns nich erklären … das
projekt ist ausgeufert in alle möglichen richtungen, außer in die, in die es
geplant war."*

### Die sechs Tätigkeiten

| ZENTRALE … | heißt | heute |
|---|---|---|
| **lauscht** | Mikros in den Räumen, Sprache und Geräusche | ein USB-Mikro am Pi, Whisper am PC; Audio-Straße entworfen ([system/audio_strasse.md](system/audio_strasse.md)) |
| **spricht** | Lautsprecher in den Räumen, Begrüßung, Small Talk, Antworten | TTS (de/zh/es) am PC, Lautsprecher am Pi |
| **überwacht** | Anwesenheit, Tür, Licht, Bewegung, später Kameras | PIR vorbereitet (GPIO4), **nicht angeschlossen**; Tür/Licht nur Tastatur-Simulation; Rechner-Anwesenheit per Code ([system/anwesenheit_und_ring.md](system/anwesenheit_und_ring.md)) |
| **analysiert** | Datenpunkte aus Small Talk und Sensoren, Messreihen, Muster | Messreihen/Graphen, Zyklus, Schlaf (erster Datenpunkt 15.03.2026) |
| **stellt bereit** | den Plan über alle Lebensbereiche halten und dich mit passendem Stoff umgeben — die **Schemen-Mechanik** | entworfen ([ki/cloud_umstieg_plan.md](ki/cloud_umstieg_plan.md) §4), **nicht gebaut** |
| **handelt** | Lampe, Steckdosen, Relais, „Mechanik" | **nichts** — `core/actions.py` druckt nur |

### Überwachung, die dir gehört

Das Leitbild widerspricht den Grundpfeilern nicht — es braucht sie.
Überwachung ist nur gruselig, wenn sie jemand anderem gehört. Bei ZENTRALE
gehören Mikros, Kameras und Daten dem Menschen, dessen Zuhause es ist. Das
kann kein Alexa- und kein Google-Gerät versprechen.

## Szenen (Sasha, 2026-10-24)

So soll es sich anfühlen. Jede Szene ist ein Prüfstein: ist sie echt, ist
ZENTRALE ein Stück weiter.

**Heimkommen mit Einkäufen.** *„ich komme heim und zentrale grüßt, macht
lichter an. ich war draußen und hab sachen gekauft. ich sage zentrale
bescheid was ich so gekauft habe. alles per sprache. ich lege ihr quittungen
in meinen scanner. sie kann dort automatisch die quittungen auslesen. sie
sammelt die infos und managed mein budget. sie trägt die ausgaben ein, sieht
zu, dass alles auch in den graphen für die übersicht landet und adjustiert das
offenstehende budget, was auch auf kategorie gefiltert werden kann."*

**Der Drucker gehört ihr.** *„der scanner — das ist mein druckergerät. von
hp. zentrale hat volle macht über ihn. kann dort auf mein kommando scannen
oder mir über den drucker dokumente direkt in die hand spucken."*

**Ein schwerer Tag.** *„ich bin daheim. ich bin traurig. mir gehts mental
etwas schwierig. zentrale spricht mit mir. aber sie nimmt nichts vorweg. sie
weiß ich sorge schon für mich selbst und dass ich das hinkriege. sie spuckt mir
aus dem drucker ein zu meiner situation passendes meme aus zur begleitenden
aufmunterung. sie tut das — nicht weil es explizit in ihrem prompt steht.
nein, stattdessen soll zentrale so selbstständig sein, dass sie meinen zustand
vermerkt, zugriff auf die tools hat, und eine kleine aufmunterung ohne mein
vorwissen einplanen kann. passend dem scheming konzept. weil zentrale nich die
druckerpatronen zu sehr wasten will druckt sie ein meme was eher auf zeichen
auf weiß basiert."*

**ZENTRALE im Raum.** *„ich ziehe die AR brille auf und es gibt optionen,
die AR version von zentrale zu installieren.. und jeweils für einzelne apps.
alles sachen die einzeln ausgearbeitet werden müssen. aber es wäre cool
zentrale anzumachen und direkt den AR modus anzuschalten. die einzelnen teile
von zentrale 3D im raum. das rad zum beispiel wäre eine hammer 3D ansicht."*
— AR ist eine weitere Oberfläche (Knoten, „überall deploybar" unten): der
Hub bietet eine AR-Fassung an, jede App ihre eigene AR-Ansicht zum Dazuholen;
ein Schalter „AR-Modus" beim Start. Brille: XREAL Air 2 Pro über StardustXR
([betrieb/mobiler_knoten.md](betrieb/mobiler_knoten.md)) — Fenster auf
Armlänge und weiter weg.

**Die Installation erkennt, wo sie ist.** Sasha: AR ist *„quasi ein
spezialisierter oberflächentyp, nodetyp"*, und die Installation soll
*„direkt versuchen zu erkennen wo man sie grad installiert und dementsprechend
sowas vorschlagen"* — Brille angesteckt → AR-Fassung anbieten; Pi mit
Bildschirm an der Wand → Vollansicht; Mikro/Lautsprecher da → Sprach-Knoten;
kein Bildschirm → Dienst. Grundlage: die Hardware-Erkennung der
Knoten-Beschreibung (`core/knoten.py`, [hub/knoten_beitritt.md](hub/knoten_beitritt.md)).

**Das System sehen.** *„du bist auf einer app drauf, in der siehst du das
zentrale system. und wie es funktioniert. du siehst den hauptknoten. oder
einzelne kleine knoten. ganz nach dem wie dein system aufgebaut ist. es zeigt
einfach nur die verbindungen von zentrale an. zwischen den knoten wird die art
des traffics angezeigt. an den knotentypen sieht man mit kleinen symbolen was
dort stattfindet, welche sensorik aktiv, angeschlossen, inaktiv ist. man hat
hier vollen überblick. wo internet reinfließt, wo sachen in die cloud gehen,
was nicht am internet steht, welche daten wo liegen und liegen bleiben oder
weiterwandern, wo die ki sachen zieht, wo autobahnen switchen, wo welcher
schutz draufliegt, welches system woraufliegt, was womit bedient wird, usw."*
— Das ist der Datenschutz-Grundpfeiler zum Anschauen: der Mensch sieht
selbst, wohin seine Daten gehen. Speist sich aus dem, was es schon gibt
(Knoten-Beschreibungen in der Cloud, `[daten]` der Apps, Adapter-Anschlüsse,
Positivliste, Brücken-Vertrag) — die Karte zeigt die Originale, sie führt
keine eigene Liste ([dasselbe Objekt, nicht kopiert]).

Was in den Szenen steckt (für die Etappen):

| Szene braucht | Tätigkeit | Etappe |
|---|---|---|
| Sprache als Haupteingabe (Einkäufe erzählen) | lauscht | 3 |
| Scanner + Drucker als Werkzeuge der KI (HP-Gerät, lokal über offene Standards — eSCL/AirScan, IPP; keine HP-Cloud) | handelt | 1–3 |
| Quittungen lesen (OCR), Ausgaben, Budget je Kategorie, Graphen | analysiert | 4 |
| Zustand vermerken (Stimmung) — Gesundheitsdaten, **nur lokal** | überwacht / analysiert | 4 |
| Eine Aufmerksamkeit selbst einplanen, ohne Vorwegnehmen, ohne dass es im Prompt steht | stellt bereit (Schemen) | 5 |
| Sparsam mit Tinte: Linien und Zeichen auf Weiß | Stil, Rücksicht | — |
| AR-Fassung des Hubs + AR-Ansicht je App, Rad in 3D | spricht / zeigt | 3 (Bildschirme) |
| Installation erkennt die Hardware und schlägt Knotentyp + Oberflächen vor | — | Unterbau, mit 3 |
| App „das System sehen": Knoten, Verbindungen, Art des Verkehrs, Sinne an/aus, Internet/Cloud/offline, wo Daten liegen, wo die KI zieht, Schutz | überwacht (sich selbst) | 2 (Hardware-Karte) |

Haltung daraus: ZENTRALE **traut dem Menschen** (nimmt nichts vorweg, keine
Ratschläge von oben), handelt **selbstständig** aus Werkzeugen und
Gedächtnis statt aus Regeln im Prompt, und ist **sparsam** mit dem, was
etwas kostet.

## Die Grundpfeiler (Sasha, 2026-10-23)

*„leg das prinzip von anonymität als grundpfeiler fest — anonymität,
datenschutz, open source."* Jede Entscheidung wird daran gemessen:

1. **Anonymität** — ZENTRALE fragt nie nach Identität: keine Mail, kein
   Klarname, keine Telefonnummer. Ein Konto ist ein selbst gewählter Name
   oder eine gewürfelte Kontonummer (wie bei Mullvad). IP-Adressen nur
   gehasht und kurzlebig.
2. **Datenschutz** — Zero-Knowledge: alles wird auf dem Gerät verschlüsselt,
   der Server sieht nur Bytes ([hub/knoten_beitritt.md](hub/knoten_beitritt.md)).
   So wenig speichern wie möglich; Daten gehören dem Nutzer. Für das
   Zuhause heißt das: **was in der Wohnung passiert, bleibt in der
   Wohnung** — Sinne werden lokal verarbeitet, nach draußen geht nur, was
   der Nutzer bewusst freigibt (der Satz von 05/2026, „keine Daten verlassen
   das Heimnetz“, wieder in Kraft; die Cloud-KI bekommt nur, was man ihr gibt).
3. **Open Source** — der Code ist offen. **Offen:** welche Lizenz. Weg 3
   ([betrieb/verteilung.md](betrieb/verteilung.md)) sah „lesbar, aber
   Kopieren verboten" vor — das ist *source-available*, nicht Open Source.
   Vorschlag: **AGPL-3.0** (offen; wer es ändert oder als Dienst betreibt,
   muss seinen Code ebenfalls offenlegen; Geld über Server/Abo bleibt
   möglich). Entscheidet Sasha.

Prüffragen bei jedem Feature: Braucht es Identität? Speichert es mehr als
nötig? Sieht der Server Klartext? Im Zweifel weglassen.

## Die Messlatte

Bei jedem Vorhaben zuerst fragen:

1. **Bringt es das Zuhause näher, das hört, sieht, spricht und handelt?**
   Wenn nein: warten lassen — außer es ist Unterbau, den eine Etappe unten
   jetzt braucht.
2. Besteht es die drei Prüffragen der Grundpfeiler (Identität? mehr
   gespeichert als nötig? Klartext beim Server?)
3. Ist es mit offenen Standards gebaut ([../CLAUDE.md](../CLAUDE.md),
   „Standards statt Eigenformat") — für Geräte heißt das: MQTT, Zigbee,
   Matter statt Herstellerwolke.

## Der Plan

Jede Etappe endet mit etwas, das man im Zuhause **spürt**, nicht nur im Code.

### Etappe 1 — Heimkommen (die Ursprungsszene)

1. **Heimkommen erkennen:** Türkontakt (Reed) + PIR am Pi; der Kern macht
   daraus `HOMECOMING` (das Ereignis gibt es seit 14.05.2026 in
   `core/events.py`, nur ohne echten Sensor).
2. **Licht an:** eine schaltbare Steckdose oder ein Relais — die erste echte
   Aktion in der Welt.
3. **Begrüßung** über den Lautsprecher.
4. **Small Talk:** zwei, drei Fragen („wie war dein Tag?", „wie hast du
   geschlafen?"); die Antworten werden zu Datenpunkten in den Messreihen.

Fertig, wenn: Sasha kommt heim, das Licht geht an, ZENTRALE begrüßt ihn und
fragt; die Antwort steht danach als Wert im Graphen.

### Etappe 2 — Die Hardware-Karte der Wohnung

Welcher Raum welche Sinne bekommt (Mikro, Lautsprecher, Kamera, Bildschirm,
Sensoren, Aktoren), womit (Pi, Mikrocontroller, Zigbee …), wie verkabelt bzw.
gefunkt, was es kostet. Eine Tabelle Raum × Sinn, dazu Einkaufsliste und
Schaltpläne. Die Seite, die in der Doku bisher fast fehlt
([betrieb/hardware.md](betrieb/hardware.md) kennt nur den einen Pi).

### Etappe 3 — Sinne in jedem Raum

- **Lauschen + sprechen überall:** die Audio-Straße fertig bauen (Weiche
  entscheiden), ein Mikro + Lautsprecher je Raum, mehrere Räume synchron.
- **Sehen:** Kamera(s), lokal ausgewertet (Anwesenheit, wer ist da), keine
  Aufzeichnung ohne ausdrücklichen Wunsch.
- **Bildschirme:** die Pi-Vollansicht an der Wand („ich will Linux nicht
  sehen", README vom 07.03.2026) als eigener Knoten.

### Etappe 4 — Analysieren

Datenpunkte aus Small Talk, Sensoren und Smartwatch zusammenführen:
Messreihen, Gesundheits-Logbuch, „Was mache ich gerade?"
([ki/zukunftsvisionen.md](ki/zukunftsvisionen.md)). Die Daten gehören dem
Nutzer.

### Etappe 5 — Bereitstellen: die Schemen-Mechanik

Der Plan über alle Lebensbereiche (vier Ebenen, Fenster und Kapazität,
[ki/cloud_umstieg_plan.md](ki/cloud_umstieg_plan.md) §4) und das „von Stoff
umgeben sein". Wartet auf Daten aus Etappe 1 und 4 — so war es schon
geplant (`system/takt.md`: „das Schemen baut auf dem auf, was der Takt
erzeugt").

### Etappe 6 — Handeln, wo immer Information reicht

Weitere Aktoren und Abläufe: Licht nach Tageszeit, Wecken, Erinnern im Raum,
in dem man gerade ist, Geräte schalten. Jede neue Fähigkeit ist eine App im
Hub.

### Der Unterbau — nur, wenn eine Etappe ihn braucht

Hub (leerer Kern, Apps), Knoten, Cloud, Login, Pakete, Handy-App. Er ist
seit 22.10.2026 weit genug: Sensoren und Aktoren werden **Apps**, die Räume
**Knoten**. Weiter ausgebaut wird er nur, wenn eine Etappe oben es verlangt.

**Überall deploybar** (Sasha, 2026-10-22):

*„zentrale muss im kern barebone sein und überall drauf gemorpht werden
können — android mit app, browser app, tablet app, raspberry pi full view, AR
stardust XR environment usw."* Nachtrag: auf **jedem nur erdenklichen
Format** — die genannten sind Beispiele, keine Grenze. Jede Oberfläche ist nur ein weiterer **Knoten**
([hub/knoten_beitritt.md](hub/knoten_beitritt.md)). Darum: Protokolle (Cloud, Mitte,
Kacheln) nur HTTP + JSON + Standard-Krypto, beschrieben in OpenAPI/JSON
Schema und mit **Testvektoren**, damit eine Dart-, JS- oder Rust-Fassung sie
allein aus der Doku nachbauen und Byte für Byte prüfen kann. Keine Logik in
einer Oberfläche — Terminal und TUI rufen nur auf.

**Das Terminal bleibt immer** (Sasha, 2026-10-24): *„der rückfall auf die
commands in nem terminal für zentrale bedienung muss immer da sein … stell dir
vor ich schließe ar brille an, installiere nur dafür, und hab später nen
anderen bildschirm dran, alles verbuggt sich. mit zentrale terminal kommandos
hat man immer direkten zugang zum programm."* Jede Installation, jeder
Knotentyp hat den Befehl `zentrale` mit allen Unterbefehlen (`status`,
`sync`, `setup`, `adapter` …) — das ist der Rückfall. **Die TUI ist eine
Oberfläche** wie AR, Wand, Fenster und Handy: **Zusätze**, nie Ersatz; auch
sie kann ausfallen, die Unterbefehle nicht. Die Erkennung beim Installieren
schlägt Oberflächen nur vor; sie entfernt nie das Terminal, und jede
Oberfläche lässt sich per Befehl ab- und umschalten.

**`zentrale` allein fragt, welche Oberfläche** (Sasha, 2026-10-24): *„zentrale
ohne zusatz scannt umgebung auf vorhandene oberflächen möglichkeiten und
schlägt dann vor, welche man haben will, wobei man zentrale auch direkt mit
einer preinstallen kann."* Oberflächen, die es geben soll: **TUI**,
**Browser** (*„voll browserfähig … wer es nich im terminal haben will"* —
die heutige Browser-Front braucht dafür einen großen Nachzug),
**natives Fenster, selbst gemalt**, **AR**, **Wand** (Pi-Vollansicht).
Vorschlag fürs Bauen: beim ersten Mal fragen und merken; beim Installieren
eine Vorgabe setzbar; direkt wählbar mit `zentrale <oberfläche>`.

### Was ruht

Werkstatt, Shop, Desk-Ausbau, Karte, News, Verkaufen/Abo. Nicht gestrichen —
sie warten, bis die Etappen 1–3 stehen.

## Offene Entscheidungen

- **Funk für Sensoren/Aktoren:** Zigbee (eigener Stick, keine Cloud), WLAN mit
  offener Firmware (Tasmota/ESPHome über MQTT) oder Kabel am Pi-GPIO —
  Etappe 2.
- **Audio-Weiche:** wo sie sitzt ([system/audio_strasse.md](system/audio_strasse.md)).
- **Kamera:** welche Auswertung, was nie gespeichert wird.
- **Lizenz** (Vorschlag AGPL-3.0).

## Woher es kommt (Kurzfassung)

| Datum | Was |
|---|---|
| 07.03.2026 | Erster Commit `58d6685`: „Event-getriebene Zentrale für einen Wand-Monitor auf Raspberry Pi … Sensor-/Zeit-Inputs … Aktionen (Display, Sound, Mechanik)". V1 = Morgengruß. |
| 14.03.2026 | „i want the tutot in there now!" — Lernen gehört von Anfang an dazu. |
| 05.05.2026 | Dashboard, lokale KI: „vollständig offline … keine Daten verlassen das Heimnetz". |
| 14.05.2026 | PC wird Gehirn, Pi wird Kiosk + Sensor-Brücke; `HOMECOMING` erfunden. |
| Juni–Okt. | KI, Gedächtnis, TUI, Karte, Mail, Kalender, Hub, Cloud — die Plattform wächst, die Wohnung nicht. |
| 23.10.2026 | Rückkehr zum Ursprung: dieses Leitbild. |

Ausführlich: Bericht vom 23.10.2026 (Git-Historie, 785 Commits).

## Historie

- **2026-10-23** — angelegt nach Sashas Rückbesinnung; Hub zum Unterbau
  erklärt, Etappen 1–6 festgelegt.
