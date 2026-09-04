# Bilder für die Tutor-Puppe

Ort: `tutor/assets/figuren/` — neben den anderen Mitgebrachten des
Tutors (Schriften und dergleichen liegen eine Ebene höher in
`tutor/assets/`).

Hier liegen die gemalten Teile der Persona. Ein Ordner pro Figur
(`lucia/`, später weitere). Solange in einem Ordner **kein einziges** Teil
liegt, zeichnet das Zimmer weiter die alte Polygon-Figur — es geht also
nichts kaputt, während gemalt wird.

## Das Verfahren in drei Schritten

1. **`lucia/SCHABLONE.png` als unterste Ebene öffnen.** Darauf sind alle
   Drehpunkte als rote Fadenkreuze eingezeichnet, dazu die Silhouette der
   jetzigen Figur als Größenorientierung und die Bodenlinie.
2. **Jedes Körperteil auf eine eigene Ebene malen**, an der Stelle, wo es am
   Körper sitzt. Leinwand bleibt **512 × 640**, es wird **nichts verschoben**.
3. **Jede Ebene einzeln als PNG exportieren** — volle Leinwandgröße, Rest
   transparent, Dateiname aus der Tabelle unten. Ins Ordner `lucia/` legen.

Fertig. Das Zimmerfenster zieht neue Dateien im Laufen nach: malen,
speichern, hinschauen — kein Neustart nötig.

## Die eine Regel

**Alle Teile auf gleich großer Leinwand, nichts verschieben.**

Daraus folgt alles andere von allein. Weil jedes Teilbild denselben
Bildausschnitt zeigt, weiß der Code aus `rig.json`, wo das Gelenk sitzt —
ein Drehpunkt muss also **nirgends markiert werden**. Die Fadenkreuze auf
der Schablone sind nur zum Hingucken: dort dreht sich das Teil später, dort
sollte es also nicht dünn auslaufen oder abgeschnitten wirken. Ein Oberarm
darf ruhig ein Stück in die Schulter hineinragen — beim Drehen füllt das die
Lücke.

Ränder dürfen überstehen. Ein weiter Ärmel, der über den blauen Kasten
hinausgeht, ist kein Problem; die Kästen sind Anhaltspunkte, keine Grenzen.

## Dateinamen

`l` und `r` sind aus **Betrachtersicht** (also `arm_l` = der Arm, der im
Bild links liegt).

| Datei | Teil | dreht sich um |
|---|---|---|
| `torso.png` | Rumpf samt Kleid | Hüfte |
| `kopf.png` | Kopf mit Haaren, ohne Augen und Mund | Nacken |
| `arm_l_ober.png` / `arm_r_ober.png` | Oberarm | Schulter |
| `arm_l_unter.png` / `arm_r_unter.png` | Unterarm samt Hand | Ellbogen |
| `bein_l_ober.png` / `bein_r_ober.png` | Oberschenkel | Hüftgelenk |
| `bein_l_unter.png` / `bein_r_unter.png` | Unterschenkel samt Fuß | Knie |

Wer den Arm zunächst **in einem Stück** malen will: als `_ober` speichern
und `_unter` weglassen. Dann knickt der Ellbogen halt nicht — alles andere
funktioniert.

## Gesicht

Augen und Mund liegen als **austauschbare Bilder** im Unterordner
`lucia/gesicht/`, weil sie die Mimik machen:

| Datei | wann |
|---|---|
| `auge_l_offen.png`, `auge_r_offen.png` | normal |
| `auge_l_zu.png`, `auge_r_zu.png` | Lidschlag, müde, Schlaf |
| `auge_l_weit.png`, `auge_r_weit.png` | überrascht |
| `mund_zu.png` | normal, und beim Reden jeder zweite Takt |
| `mund_offen.png` | Reden, überrascht |
| `mund_laecheln.png` | fröhlich |
| `mund_traurig.png` | traurig |
| `mund_strich.png` | müde, Schlaf |

Auch diese auf voller 512 × 640-Leinwand, an der Stelle im Gesicht, wo sie
hingehören. Fehlt eine Variante, nimmt der Code das nächstbeste vorhandene
Bild — es müssen also nicht alle auf einmal existieren.

## Eigene Proportionen: die Gelenke selbst setzen

Die mitgelieferte Schablone bildet die **alte** Figur ab (großer Kopf, kurze
Beine — sie stammt aus den Polygonen). Das muss niemanden binden. Der
bequemere Weg herum ist: **die Figur malen, wie sie sein soll, und dem Code
hinterher sagen, wo die Gelenke sitzen.**

1. Figur malen, Proportionen völlig frei, Leinwand beliebig groß.
2. Eine **neue leere Ebene** darüber. Darauf pro Gelenk **einen Klecks** in
   der jeweiligen Farbe setzen — die Farben stehen in `lucia/GELENK_FARBEN.png`
   und lassen sich von dort mit der Pipette abgreifen. Pinselgröße egal, die
   Mitte des Kleckses zählt.
3. Nur diese Ebene als PNG exportieren.
4. Einlesen lassen (`tutor/gelenke.py`). Es entsteht ein **Kontrollbild** mit
   Beschriftungen zum Prüfen; erst danach wird `rig.json` wirklich geändert.

Links und rechts musst du nicht auseinanderhalten: wo eine Farbe zweimal
vorkommt — Schultern, Ellbogen, Hüftgelenke, Knie, Augen — entscheidet die
Lage im Bild. Stimmt die Anzahl der Kleckse pro Farbe nicht, wird nichts
geschrieben, sondern gemeldet, was fehlt oder zu viel ist.

Wichtig ist der **Fusspunkt** (schwarzer Klecks): daran hängt, wie groß die
Figur im Zimmer erscheint und wo sie auf dem Boden steht. Der Maßstab wird
aus dem Abstand Fusspunkt→Nacken abgelesen, deshalb darf die Leinwand jede
Größe haben — das Zimmer rechnet sich automatisch darauf um.

Die Schablone wird nach dem Einlesen neu gezeichnet und zeigt dann **deine**
Gelenke. Ab da malst du gegen deine eigene Vorlage.

## Schablone von Hand neu bauen

Sie wird aus `rig.json` erzeugt und ist daher nie veraltet. Zuständig ist
`tutor/schablone.py`; nach einem Einlesen mit `tutor/gelenke.py` passiert es
von allein.

## Was hier später dazukommt

Die Puppe ist absichtlich schon so gebaut, dass Kleidung eines Tages als
eigene Schicht über den Körperteilen liegen kann (gleicher Slot, gleicher
Drehpunkt, gleiche Leinwand). Fürs Erste wird die Figur einfach **fertig
angezogen** gemalt — Arm samt Ärmel als ein Bild. Der Umbau auf austauschbare
Outfits ändert daran nichts, was jetzt gemalt wird.
