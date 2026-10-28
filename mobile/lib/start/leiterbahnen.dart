// Der Knopf-Ring als Platine: vom Rand des geschlossenen Auges laufen
// Leiterbahnen zu den Knöpfen — gerade raus, dann ein Knick um 45° wie auf
// einer echten Platine, Lötaugen am Anfang und am Knick, ein leiser Schein in
// den Farben des Auges (Sasha, 28.10.2026).
//
// Getrennt in Planen (reine Geometrie, einmal je Größe und Anzahl) und Malen
// (jedes Bild nur ein Stück des fertigen Weges) — so kostet die Animation
// keine Neuberechnung je Bild.

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

import '../auge/auge_regler.dart';
import '../auge/zeit.dart';
import '../thema/farben.dart';

/// Eine geplante Bahn: Weg vom Auge (start) über den Knick zum Knopf (ziel).
class Bahn {
  Bahn(this.start, this.knick, this.ziel)
      : pfad = Path()
          ..moveTo(start.dx, start.dy)
          ..lineTo(knick.dx, knick.dy)
          ..lineTo(ziel.dx, ziel.dy) {
    _messung = pfad.computeMetrics().first;
  }

  final Offset start, knick, ziel;
  final Path pfad;
  late final ui.PathMetric _messung;

  double get laenge => _messung.length;

  /// Das Stück vom Anfang bis zum Anteil p (0..1).
  Path stueck(double p) => _messung.extractPath(0, _messung.length * p.clamp(0.0, 1.0));
}

/// Wo die Knöpfe sitzen: gleichmäßig auf einer Ellipse um das Auge, der
/// erste oben. Ellipse statt Kreis, weil das Handy höher als breit ist.
List<Offset> knopfOrte(int n, Offset c, double rxRing, double ryRing) => [
      for (var i = 0; i < n; i++)
        c + Offset(math.cos(-math.pi / 2 + 2 * math.pi * i / n) * rxRing,
                   math.sin(-math.pi / 2 + 2 * math.pi * i / n) * ryRing),
    ];

/// Bahnen vom Rand der Mandel (halbe Breite rx, Höhe ry) zu jedem Knopf.
/// Nur waagrecht/senkrecht und 45° — so sieht es nach Platine aus.
List<Bahn> bahnenPlanen(Offset c, double rx, double ry, List<Offset> knoepfe) {
  double halb(double dx) =>
      ry * math.pow(math.max(0.0, 1 - dx * dx), mandelSpitze).toDouble();
  final abstand = ry * .14; // kleine Lücke zwischen Lidkante und Lötauge
  return [
    for (final b in knoepfe)
      () {
        final d = b - c;
        final senkrecht = d.dy.abs() >= d.dx.abs() * .7;
        final Offset s;
        if (senkrecht) {
          // Oben/unten: aus dem Lid heraus, ein Stück zur Seite des Knopfs.
          final u = (d.dx / rx * .45).clamp(-.5, .5);
          s = c + Offset(u * rx, d.dy.sign * (halb(u) + abstand));
        } else {
          // Seitlich: aus dem Augenwinkel.
          s = c + Offset(d.dx.sign * (rx + abstand), 0);
        }
        // Erst gerade entlang der Hauptrichtung, dann 45° bis zum Knopf.
        final w = b - s;
        final a = w.dx.abs(), h = w.dy.abs();
        // Gerade wird entlang der Achse mit dem längeren Rest gelaufen, sonst
        // ginge der Knick nicht in genau 45° auf.
        final knick = h >= a
            ? s + Offset(0, w.dy.sign * (h - a))
            : s + Offset(w.dx.sign * (a - h), 0);
        return Bahn(s, knick, b);
      }(),
  ];
}

/// Malt die Bahnen bis zum Stand r (0..1 der ganzen Ring-Bewegung).
class LeiterbahnMaler extends CustomPainter {
  LeiterbahnMaler(this.bahnen, this.stand, this.f, this.nacht) : super(repaint: stand);

  final List<Bahn> bahnen;
  final Animation<double> stand;
  final AugeFarben f;
  final bool nacht;

  @override
  void paint(Canvas canvas, Size size) {
    final p = sanft((stand.value - bahnenVon) / (bahnenBis - bahnenVon));
    if (p <= 0) return;
    final schein = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = bahnSchein
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 3)
      ..color = f.iris.withValues(alpha: nacht ? bahnScheinNacht : bahnScheinTag);
    final kern = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = bahnBreite
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..color = f.rand.withValues(alpha: .9);
    final ring = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.3
      ..color = f.rand.withValues(alpha: .9);
    final punkt = Paint()..color = f.irishell.withValues(alpha: .9);
    final voll = Paint()..color = f.rand.withValues(alpha: .9);

    for (final b in bahnen) {
      final stueck = b.stueck(p);
      canvas.drawPath(stueck, schein);
      canvas.drawPath(stueck, kern);
      // Lötauge am Auge: Ring mit hellem Kern, taucht mit der Bahn auf.
      final a = sanft(p * 6);
      canvas.drawCircle(b.start, lotaugeRadius * a, ring);
      if (nacht) canvas.drawCircle(b.start, lotaugeRadius * .45 * a, punkt);
      // Knick: ein kleines Durchkontakt-Pünktchen, sobald die Bahn dort ist.
      final bisKnick = (b.knick - b.start).distance / b.laenge;
      if (bisKnick > .02 && bisKnick < .98 && p > bisKnick) {
        canvas.drawCircle(b.knick, knickRadius * sanft((p - bisKnick) * 8), voll);
      }
    }
  }

  @override
  bool shouldRepaint(LeiterbahnMaler alt) =>
      alt.bahnen != bahnen || alt.f != f || alt.nacht != nacht || alt.stand != stand;
}

/// Ein Knopf als Chip: abgerundeter Körper, Beinchen an jeder Seite.
class ChipMaler extends CustomPainter {
  ChipMaler(this.f, this.nacht);

  final AugeFarben f;
  final bool nacht;

  @override
  void paint(Canvas canvas, Size size) {
    final r = Offset.zero & size;
    final koerper = r.deflate(size.width * .14);
    final bein = Paint()
      ..color = f.rand.withValues(alpha: .75)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    final lang = size.width * .1;
    for (var i = 0; i < chipBeinchen; i++) {
      final u = (i + 1) / (chipBeinchen + 1);
      final x = koerper.left + koerper.width * u, y = koerper.top + koerper.height * u;
      canvas.drawLine(Offset(x, koerper.top), Offset(x, koerper.top - lang), bein);
      canvas.drawLine(Offset(x, koerper.bottom), Offset(x, koerper.bottom + lang), bein);
      canvas.drawLine(Offset(koerper.left, y), Offset(koerper.left - lang, y), bein);
      canvas.drawLine(Offset(koerper.right, y), Offset(koerper.right + lang, y), bein);
    }
    final rr = RRect.fromRectAndRadius(koerper, const Radius.circular(chipRundung));
    if (nacht) {
      canvas.drawRRect(rr, Paint()
        ..color = f.iris.withValues(alpha: .25)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6));
    }
    canvas.drawRRect(rr, Paint()..color = Color.lerp(f.bg, f.lid, nacht ? .45 : .35)!);
    canvas.drawRRect(rr, Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4
      ..color = f.rand.withValues(alpha: .9));
    // Kerbe oben links wie bei einem echten Chip (Pin 1)
    canvas.drawCircle(koerper.topLeft + const Offset(6, 6), 1.8,
        Paint()..color = f.rand.withValues(alpha: .6));
  }

  @override
  bool shouldRepaint(ChipMaler alt) => alt.f != f || alt.nacht != nacht;
}
