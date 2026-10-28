// Launen: ab und zu passiert für ein paar Sekunden etwas Seltsames im Auge,
// dann ist alles wieder wie immer (Sasha, 28.10.2026). Eine neue Laune ist
// eine Klasse und ein Eintrag in [alleLaunen] — sonst nichts. Der Maler kennt
// nur die Schnittstelle [Laune] (auge_maler.dart), nie eine einzelne Laune.
//
// Jede Laune bekommt t (Fortschritt 0..1) und s (Stärke, blendet weich ein
// und aus) und muss bei s = 0 genau das normale Auge ergeben — darum
// springt nichts, wenn sie kommt oder geht.

import 'dart:math' as math;

import 'package:flutter/painting.dart';

import 'auge_maler.dart';
import 'auge_regler.dart';
import 'zeit.dart';

/// Alle Launen — der EINE Ort zum Hinzufügen. Die Reihenfolge ist auch die
/// der Vorschau (langes Drücken aufs Auge der Startseite).
const List<Laune> alleLaunen = [
  _Stern(), _Zwillinge(), _Unscharf(), _Katze(), _Spirale(), _Farbreise(),
  _Doppelblinzeln(), _Funken(), _Mond(), _Augenrollen(), _Zwinkern(), _Herz(),
];

/// Welche Laune läuft zur Wanduhr-Zeit ms (seit Epoche)? → (Laune, t) oder
/// null. Fest aus dem Zeitfenster gewürfelt: wer dieselbe Zeit fragt, bekommt
/// dieselbe Antwort — testbar und ohne mitgeschleppten Zustand.
(Laune, double)? launeZu(int ms, [List<Laune> launen = alleLaunen]) {
  if (launen.isEmpty) return null;
  final fenster = ms ~/ launenFensterMs;
  if (festerZufall(fenster, 23) >= launenChance) return null;
  final l = launen[(festerZufall(fenster, 29) * launen.length).floor() % launen.length];
  final beginn = fenster * launenFensterMs +
      (festerZufall(fenster, 31) * (launenFensterMs - l.dauerMs)).floor();
  final d = ms - beginn;
  if (d < 0 || d >= l.dauerMs) return null;
  return (l, d / l.dauerMs);
}

/// Stärke einer Laune zum Fortschritt t: weich rein, halten, weich raus.
double launenStaerke(double t) => sanft(math.min(t, 1 - t) / launenRampe);

/// Ein Buckel 0 → 1 → 0 zwischen a und b (für Blinzler).
double _buckel(double t, double a, double b) =>
    t <= a || t >= b ? 0 : math.sin(math.pi * (t - a) / (b - a));

// ── Die Launen ──────────────────────────────────────────────────────────────

/// Statt der Pupille wandert ein Stern durch die Iris.
class _Stern extends Laune {
  const _Stern() : super('stern', dauerMs: 6000);

  @override
  bool malePupille(IrisBild b) {
    final w = 2 * math.pi * b.t * 1.5;
    final ort = b.mitte + Offset(math.cos(w) * 5, math.sin(w) * 2) * b.k * b.s;
    if (b.s < 1) zeichnePupille(b.canvas, b.mitte, b.pu * (1 - b.s), b.f);
    final r = b.pu * 1.4 * b.s;
    final p = Path();
    for (var i = 0; i < 10; i++) {
      final a = -math.pi / 2 + i * math.pi / 5 + w * .3;
      final rr = i.isEven ? r : r * .45;
      final q = ort + Offset(math.cos(a), math.sin(a)) * rr;
      i == 0 ? p.moveTo(q.dx, q.dy) : p.lineTo(q.dx, q.dy);
    }
    b.canvas.drawPath(p..close(), b.pinsel..color = b.f.pupille.withValues(alpha: .95));
    return true;
  }
}

/// Zwei Iriden mit Pupillen umkreisen einander.
class _Zwillinge extends Laune {
  const _Zwillinge() : super('zwillinge', dauerMs: 6000);

  @override
  bool maleIris(IrisBild b) {
    final w = 2 * math.pi * b.t * 1.2;
    final weg = Offset(math.cos(w) * 7.5, math.sin(w) * 2.5) * b.k * b.s;
    final ir = b.ir * (1 - .32 * b.s), pu = b.pu * (1 - .2 * b.s);
    for (final m in [b.mitte + weg, b.mitte - weg]) {
      zeichneIris(b.canvas, m, ir, pu, b.f, b.puls, b.k);
      zeichnePupille(b.canvas, m, pu, b.f);
      zeichneLicht(b.canvas, m, b.k, b.f);
    }
    return true;
  }

  @override
  bool maleLicht(IrisBild b) => true; // schon je Iris gemalt
}

/// Das Auge verliert den Fokus und verschwimmt.
class _Unscharf extends Laune {
  const _Unscharf() : super('unscharf', dauerMs: 4000);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) =>
      z.mit(unschaerfe: 1.0 * s, pupille: z.pupille * (1 + .15 * s));
}

/// Katzenauge: die Pupille wird ein senkrechter Schlitz, die Iris gelblich.
class _Katze extends Laune {
  const _Katze() : super('katze', dauerMs: 5000);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) =>
      z.mit(farbDrehung: z.farbDrehung - 75 * s);

  // Der runde Lichtpunkt würde den Schlitz anknabbern — er tritt zurück.
  @override
  bool maleLicht(IrisBild b) {
    zeichneLicht(b.canvas, b.mitte, b.k, b.f, 1 - b.s);
    return true;
  }

  @override
  bool malePupille(IrisBild b) {
    final breit = b.pu * (1 - .72 * b.s), hoch = b.pu + (b.ir * .95 - b.pu) * b.s;
    b.canvas.drawOval(Rect.fromCenter(center: b.mitte, width: breit * 2, height: hoch * 2),
        b.pinsel..color = b.f.pupille.withValues(alpha: .95));
    return true;
  }
}

/// Eine Spirale dreht sich aus der Pupille heraus.
class _Spirale extends Laune {
  const _Spirale() : super('spirale', dauerMs: 5500);

  @override
  bool malePupille(IrisBild b) {
    zeichnePupille(b.canvas, b.mitte, b.pu * (1 - .65 * b.s), b.f);
    if (b.s <= 0) return true;
    final dreh = -2 * math.pi * b.t * 2.5;
    final aussen = b.ir * .82 * b.s;
    const n = 90, windungen = 3.0;
    final p = Path();
    for (var i = 0; i <= n; i++) {
      final u = i / n, a = dreh + u * windungen * 2 * math.pi;
      final q = b.mitte + Offset(math.cos(a), math.sin(a)) * (aussen * u);
      i == 0 ? p.moveTo(q.dx, q.dy) : p.lineTo(q.dx, q.dy);
    }
    b.canvas.drawPath(p, b.pinsel
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.3 * b.k
      ..strokeCap = StrokeCap.round
      ..color = b.f.pupille.withValues(alpha: .9 * b.s));
    return true;
  }
}

/// Die Iris wandert einmal durch alle Farben und kommt beim Grün wieder an.
class _Farbreise extends Laune {
  const _Farbreise() : super('farbreise', dauerMs: 7000);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) =>
      z.mit(farbDrehung: z.farbDrehung + 360 * sanft(t));
}

/// Zweimal schnell hintereinander blinzeln.
class _Doppelblinzeln extends Laune {
  const _Doppelblinzeln() : super('doppelblinzeln', dauerMs: 1400);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) {
    final zu = math.max(_buckel(t, .08, .38), _buckel(t, .5, .8));
    return z.mit(lid: z.lid * (1 - zu));
  }
}

/// Die Pupille zerspringt in Funken, die auseinanderfliegen und sich wieder
/// zusammensetzen.
class _Funken extends Laune {
  const _Funken() : super('funken', dauerMs: 3200);

  @override
  bool malePupille(IrisBild b) {
    final weit = math.sin(math.pi * b.t);
    final r = b.pu * (1 - .65 * weit), weg = 9.5 * b.k * weit;
    for (var i = 0; i < 8; i++) {
      final a = i * math.pi / 4 + b.t * math.pi;
      final q = b.mitte + Offset(math.cos(a), math.sin(a) * .6) * weg;
      b.canvas.drawCircle(q, r, b.pinsel..color = b.f.pupille.withValues(alpha: .95));
      b.canvas.drawCircle(q, r * .35, b.pinsel..color = b.f.irishell.withValues(alpha: .7 * weit));
    }
    return true;
  }
}

/// Ein kleiner Mond spiegelt sich und zieht langsam über die Iris.
class _Mond extends Laune {
  const _Mond() : super('mond', dauerMs: 6500);

  @override
  bool maleLicht(IrisBild b) {
    zeichneLicht(b.canvas, b.mitte, b.k, b.f, 1 - b.s);
    if (b.s <= 0) return true;
    final x = (b.t * 2 - 1) * b.ir * .6;
    final ort = b.mitte + Offset(x, -1.6 * b.k - math.sin(math.pi * b.t) * 1.2 * b.k);
    final r = 2.3 * b.k;
    final sichel = Path.combine(
      PathOperation.difference,
      Path()..addOval(Rect.fromCircle(center: ort, radius: r)),
      Path()..addOval(Rect.fromCircle(center: ort + Offset(r * .5, -r * .25), radius: r * .88)),
    );
    b.canvas.drawPath(sichel, b.pinsel..color = b.f.irishell.withValues(alpha: .95 * b.s));
    return true;
  }
}

/// Das Auge rollt einmal im Kreis.
class _Augenrollen extends Laune {
  const _Augenrollen() : super('augenrollen', dauerMs: 3000);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) {
    final w = 2 * math.pi * sanft(t);
    return z.mit(
      blickX: z.blickX * (1 - s) + 6 * math.sin(w) * s,
      blickY: z.blickY * (1 - s) - 3.5 * math.sin(w / 2) * s,
    );
  }
}

/// Zwinkern: eine Seite schließt sich, die andere bleibt halb offen.
class _Zwinkern extends Laune {
  const _Zwinkern() : super('zwinkern', dauerMs: 1800);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) {
    final zu = sanft(_buckel(t, .1, .9) * 1.3);
    return z.mit(lid: z.lid * (1 - .45 * zu), lidSchief: zu);
  }
}

/// Die Pupille wird ein schlagendes Herz, die Iris rosa.
class _Herz extends Laune {
  const _Herz() : super('herz', dauerMs: 5000);

  @override
  AugeZustand formen(AugeZustand z, double t, double s) =>
      z.mit(farbDrehung: z.farbDrehung + 165 * s);

  @override
  bool malePupille(IrisBild b) {
    if (b.s < 1) zeichnePupille(b.canvas, b.mitte, b.pu * (1 - b.s), b.f);
    final schlag = math.pow(math.sin(b.t * math.pi * 7).abs(), 6).toDouble();
    final r = b.pu * 1.35 * b.s * (1 + .14 * schlag) / 17;
    const n = 48;
    final p = Path();
    for (var i = 0; i <= n; i++) {
      final a = i / n * 2 * math.pi;
      final x = 16 * math.pow(math.sin(a), 3);
      final y = -(13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a));
      final q = b.mitte + Offset(x * r, (y + 2) * r);
      i == 0 ? p.moveTo(q.dx, q.dy) : p.lineTo(q.dx, q.dy);
    }
    b.canvas.drawPath(p..close(), b.pinsel..color = b.f.pupille.withValues(alpha: .95));
    return true;
  }
}
