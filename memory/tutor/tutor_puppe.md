# Die gemalte Puppe (Rig) — wie die Persona aussieht

Bis 2026-09-04 war die Persona im Zimmerfenster (`tutor/room.py`) aus
pygame-Primitiven zusammengesetzt: Kleid als Trapez, Gliedmassen als
Rechtecke, Kopf als Kreis. Das war robust, sah aber grob aus. Sasha malt
selbst, deshalb wird die Figur durch **gemalte Einzelteile** ersetzt.

## Warum eine Puppe und kein Video-Modell

Der Tutor muss über Monate **immer gleich aussehen**. Generative Video- oder
Bildmodelle liefern pro Aufruf eine leicht andere Figur — Gesicht, Farben und
Proportionen driften. Deshalb entsteht die Figur genau **einmal** (gemalt) und
wird danach nur noch **bewegt**. Konsistenz ist so eine Eigenschaft der
Konstruktion, nicht eine Hoffnung an ein Modell.

3D wurde verworfen: der angestrebte Look ist ein handgemalter Story-Stil, und
den in 3D zu erreichen ist der weiteste Umweg, den es gibt — er entwertet
ausgerechnet die Fähigkeit, die vorhanden ist (malen).

## Aufbau

Drei Teile, klar getrennt:

| Datei | Aufgabe |
|---|---|
| `tutor/assets/figuren/<figur>/rig.json` | **Bauplan**: Leinwandmass, Slots, Drehpunkte, Zeichenreihenfolge, Mimik-Varianten |
| `tutor/sprites.py` | **Lader**: liest den Bauplan, lädt die PNGs, dreht Teile um ihren Drehpunkt, blittet sie |
| `tutor/room.py` (`Persona`) | **Pose**: rechnet pro Frame die Winkel aller Gliedmassen aus und ruft den Lader |
| `tutor/schablone.py` | erzeugt die **Mal-Schablone** aus `rig.json` (Zahlen → Bild) |
| `tutor/gelenke.py` | liest **gemalte Gelenkpunkte** zurück nach `rig.json` (Bild → Zahlen) |

Anleitung für den Malenden: `tutor/assets/figuren/LIES_MICH.md`.

## Die tragende Idee: gemeinsame Leinwand

Jedes Teilbild ist **gleich gross** (512 × 640) und zeigt das Teil an der
Stelle, wo es am Körper sitzt. Dadurch sind alle Teilbilder deckungsgleich und
ein Drehpunkt ist bloss noch **eine Koordinate in `rig.json`** — beim Malen
muss nichts markiert oder technisch angelegt werden, es genügt, jede Ebene
einzeln zu exportieren.

Intern schneidet `sprites.py` jedes PNG auf seinen sichtbaren Bereich zu (der
Rest ist transparent) und verschiebt den Drehpunkt korrekt mit — sonst würde
bei jeder Drehung eine fast leere 512 × 640-Fläche rotiert.

## Mischbetrieb — der Grund, warum das gefahrlos ist

- **Kein Bild im Ordner** → `room.py` zeichnet unverändert die alte
  Polygon-Figur (`_draw_klassisch`). Nichts kann kaputtgehen.
- **Einzelne Bilder da** → die Puppe wird gebaut; gemalte Teile werden
  gezeichnet, noch fehlende als schlichter Platzhalter an derselben Stelle.
- **Hot-Reload**: neue oder geänderte Dateien werden im laufenden Fenster
  einmal pro Sekunde nachgezogen. Malen, speichern, hinschauen.

Es gibt also **keinen Stichtag**, an dem alles fertig sein muss.

## Winkel-Konvention

Für alle Gliedmassen gilt: **0° = Teil hängt gerade nach unten** (so, wie es
gemalt wurde), **+90° = zeigt nach rechts**, −90° = nach links. Richtungsvektor
ist `(sin w, cos w)`; `sprites.py` dreht mit demselben Vorzeichen wie pygame.
`l`/`r` in den Slotnamen sind **aus Betrachtersicht**.

Gelenkketten stecken in `rig.json` (`eltern`), die Positionen rechnet
`Persona._draw_rig` aus: Ellbogen = Schulter + Richtung(Oberarmwinkel) · Länge.

## Proportionen: Sasha gibt vor, nicht der Bauplan

Die mitgelieferten Drehpunkte bilden noch die alte Polygon-Figur ab (grosser
Kopf, kurze Beine). Das ist aber nur ein Startwert, keine Bindung: mit
`tutor/gelenke.py` geht es **andersherum** — Sasha malt die Figur, wie er sie
will, setzt auf einer eigenen Ebene je Gelenk einen Farbklecks, und der
Bauplan richtet sich danach. Farbtabelle: `GELENK_FARBEN.png` (aus
`gelenke.py --farbkarte`), Kontrollbild vor dem Schreiben.

**Der Maßstab wird nicht festgenagelt**, sondern aus dem Bauplan abgelesen:
`Rig.einheiten_faktor()` misst den Abstand Fusspunkt→Nacken und teilt ihn
durch dieselbe Strecke in den Einheiten der alten Figur (64). Dadurch darf die
Leinwand jede Grösse und die Figur jede Proportion haben — das Zimmer skaliert
automatisch richtig. Eine feste Konstante dafür wäre genau die Falle gewesen,
die eine schlankere Figur zu gross oder zu klein gemacht hätte.

## Sitzen

In der Frontalansicht ist Sitzen schwach: die Oberschenkel zeigten in der
alten Figur waagerecht nach vorn, was frontal nicht darstellbar ist. Aktuell
werden die Beine nur leicht gespreizt. Sauber wird das erst mit **eigens
gemalten Sitz-Teilen** oder einer Seitenansicht.

## Später: Kleidung als eigene Schicht

Die Struktur ist bereits darauf ausgelegt (gleicher Slot, gleicher Drehpunkt,
gleiche Leinwand → Kleidung kann über dem nackten Teil liegen und
Skalierungen des Körperbaus automatisch erben). Bewusst **noch nicht gebaut**:
Priorität ist ein spielbarer Mockup, nicht ein Baukasten. Fürs Erste wird die
Figur fertig angezogen gemalt. Der spätere Umbau entwertet nichts, was jetzt
entsteht.
