// Alle Stellschrauben des Auges an EINER Stelle. Warum: wie das Auge
// aussieht, entscheidet Sasha (Ästhetik ist seine Sache) — er soll drehen
// können, ohne den Maler zu lesen. Längen in Entwurfseinheiten (24,5 = halbe
// Breite der Mandel, wie im 52er-Entwurf der TUI), Zeiten in Millisekunden.

// ── Form ────────────────────────────────────────────────────────────────────

/// So weit hängt das Oberlid in die Mandel (0 = gar nicht, 1 = zu). Das
/// Unterlid ist das Spiegelbild an der Waagrechten durch die Pupille
/// (Sasha, 28.10.2026: „einfach ne x-achse durch die pupille nehmen und das
/// design spiegeln") — darum wirkt das Auge halb geschlossen statt erschrocken.
const lidTief = .60;

/// So weit deckt das Unterlid die untere Hälfte (0 = weit offen wie im
/// ersten Entwurf, lidTief = ganz gespiegelt). Sasha, 29.10.2026: „doch etwas
/// weiter nach unten geöffnet, aber nich so weit wie vorher" → halb dazwischen.
const unterlidTief = .30;

/// Geschlossen treffen sich die Lider auf einem Bogen, der so tief nach unten
/// hängt (Anteil der halben Mandelhöhe) — „kein Strich, sondern ne Kurve nach
/// unten mit Wimpern dran" (Sasha, 29.10.2026).
const schlafBogen = .30;

/// Wimpern am geschlossenen Auge: Anzahl, wie weit sie zu den Winkeln reichen
/// (Anteil der halben Breite), Länge und Dicke (Entwurfseinheiten), Neigung
/// nach außen am Rand (Bogenmaß); Dicke = halbe Breite am Lid. Sie tauchen auf, sobald die Öffnung unter
/// wimpernAb fällt — offen stünden sie in der Iris.
const wimpernAnzahl = 9, wimpernBreite = .72, wimpernLaenge = 4.6, wimpernDicke = .36;
const wimpernNeigung = 1.1, wimpernAb = .45;

/// Höhe der Mandel relativ zur halben Breite (TUI: 17 / 24,5).
const mandelHoehe = 17.0 / 24.5;

/// Wie spitz die Mandel in den Winkeln zuläuft (Exponent; 0,5 wäre Ellipse).
const mandelSpitze = .85;

// ── Falten (je eine halbe Sinusperiode, oben und gespiegelt unten) ──────────

/// Falten über dem Auge: (Abstand als Vielfaches der Mandelhöhe, halbe
/// Breite relativ zur Mandel, Deckkraft). Die untere Reihe spiegelt sie.
const faltenOben = [(1.30, .80, .60), (1.62, .62, .36)];

/// Dicke einer Falte in ihrer Mitte (Entwurfseinheiten). Zu den Enden läuft
/// sie wie der Sinus selbst auf null aus — kein Strich, ein weicher Bogen.
const faltenDicke = 1.9;

/// Die unteren Falten sind etwas leiser als die oberen (1 = genau gleich).
const faltenUntenAnteil = .8;

// ── Pupille nach Uhrzeit ────────────────────────────────────────────────────

/// Tagsüber: Pupille relativ zur Iris (TUI: 5,6 von 13).
const pupilleTag = 5.6;

/// Nachts (21–7 Uhr) etwas weiter, wie bei Dunkelheit.
const pupilleNachtFaktor = 1.25;

/// 3–5 Uhr: winzig. „extra spooky" (Sasha).
const pupilleSpukFaktor = .42;

/// Grenzen in Stunden; die Übergänge sind weich über [uebergangStunden]
/// (zur Hälfte vor, zur Hälfte nach der Grenze), damit nichts springt.
const nachtVon = 21.0, nachtBis = 7.0, spukVon = 3.0, spukBis = 5.0;
const uebergangStunden = 1.0;

// ── Launen ──────────────────────────────────────────────────────────────────

/// Länge eines Zeitfensters; in jedem passiert höchstens eine Laune.
const launenFensterMs = 180000; // 3 min

/// Anteil der Fenster mit Laune → im Mittel eine alle ~4,5 min.
const launenChance = .65;

/// Ein- und Ausblenden einer Laune als Anteil ihrer Dauer — sie kommt und
/// geht weich, nie ein harter Wechsel.
const launenRampe = .18;

// ── Antippen ────────────────────────────────────────────────────────────────

/// So lange wächst die Pupille, bis sie das ganze Auge füllt.
const tippenMs = 620;

/// Die Seite danach: der Fleck in Pupillenfarbe wächst über den Schirm und
/// blendet dann in den Chat (hin / zurück).
const uebergangMs = 520, uebergangZurueckMs = 420;

/// Nach der Rückkehr zieht sich die Pupille so lange wieder zusammen.
const zurueckMs = 700;

// ── Knopf-Ring der Startseite (Wischen) ────────────────────────────────────
// Runterwischen: das Auge schließt sich, aus seinem Rand wachsen Leiterbahnen
// wie auf einer Platine zu den Knöpfen (Sasha, 28.10.2026). Hochwischen:
// alles läuft rückwärts. Die Phasen sind Anteile der Gesamtdauer (0..1).

/// So viele Pixel Fingerweg sind die ganze Bewegung — der Ring folgt dem
/// Finger direkt: langsam gewischt schließt es langsam.
const wischStrecke = 260.0;

/// Die Feder nach dem Loslassen (und beim Tippen): Steifigkeit und Dämpfung
/// (1 = kein Überschwingen; etwas darunter schwingt sie ein Spürchen über
/// und setzt sich — das wirkt lebendig statt mechanisch).
const ringFeder = 140.0, ringDaempfung = .78;

/// Das Auge schließt sich in [0, augeZuBis] der Bewegung.
const augeZuBis = .42;

/// Die Bahnen zeichnen sich in [bahnenVon, bahnenBis] ihren Weg entlang.
const bahnenVon = .22, bahnenBis = .78;

/// Die Knöpfe wachsen ab knoepfeVon am Bahnende auf, jeder folgende um
/// knopfVersatz später (Anteil der Gesamtdauer).
const knoepfeVon = .62, knopfVersatz = .05;

/// Ab so schnell (Pixel/s) zählt beim Loslassen die Richtung des Schnippens,
/// darunter entscheidet, ob der Finger schon über die Hälfte war.
const wischTempo = 320.0;

/// Leiterbahn: Kern, Schein darum, Lötaugen (Pixel). Die Deckkraft des
/// Scheins ist nachts höher (auf Schwarz glimmt es, auf Weiß nicht).
const bahnBreite = 1.6, bahnSchein = 7.0, bahnScheinNacht = .22, bahnScheinTag = .10;
const lotaugeRadius = 3.4, knickRadius = 1.9;

/// Knopf als Chip: Kantenlänge, Rundung, Beinchen je Seite.
const chipGroesse = 50.0, chipRundung = 9.0, chipBeinchen = 3;
