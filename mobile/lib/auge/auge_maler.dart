// Das Auge gezeichnet — die glatte Fassung des Pixel-Auges der TUI
// (tui/pixel.py, „Das Auge der KI", Sasha 04.10.2026: „unendlich weise und
// entspannt"). Gleiche Form: Mandel, schweres Oberlid halb über der großen
// Iris, Falten darüber und darunter, durchscheinend, zu den Rändern hin
// ausblendend, „als ob es grad von hinten nach raus fadet".
//
// Maße sind relativ zum Radius rx (halbe Breite); die TUI-Werte sind auf
// ihren 52er-Entwurf bezogen (_AK), hier ist 24,5 Einheiten = rx.

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import '../thema/farben.dart';

/// Der sichtbare Zustand eines Augenblicks (wie pixel.auge_zustand).
class AugeZustand {
  const AugeZustand({
    this.lid = 1, this.blickX = 0, this.blickY = 0,
    this.puls = 0, this.ring = 0, this.da = 1, this.denkt = false,
  });

  /// 0 = zu, 1 = offen (in Ruhe hängt das Oberlid trotzdem tief).
  final double lid;

  /// Blickrichtung in Entwurfseinheiten (±5 x, ±1,5 y).
  final double blickX, blickY;

  /// Denken: Puls 0..1 und Drehwinkel des Funkenrings.
  final double puls, ring;

  /// Auftauchen aus dem Hintergrund 0..1.
  final double da;
  final bool denkt;
}

const _lidTief = .62; // so weit hängt das Oberlid in die Mandel

class AugeMaler extends CustomPainter {
  AugeMaler(this.z, this.f);

  final AugeZustand z;
  final AugeFarben f;

  @override
  void paint(Canvas canvas, Size size) {
    // Breite 2·rx, Höhe der Mandel 2·ry; Falten brauchen Platz drumherum.
    final rx = math.min(size.width / 2, size.height / 1.25);
    final k = rx / 24.5; // eine Entwurfseinheit
    final ry = 17.0 * k;
    final c = Offset(size.width / 2, size.height / 2);

    double halb(double dx) => ry * math.pow(math.max(0.0, 1 - dx * dx), .85);

    final o = z.lid;
    // Lidkante relativ zur Mitte, als Funktion von dx (wie im Raster)
    double lidkante(double dx) {
      final h = halb(dx);
      return -h * (1 - _lidTief) + (1 - o) * h * (1.45 - _lidTief);
    }

    double unten(double dx) => halb(dx) - (1 - o) * halb(dx) * .55;

    Path kurve(double Function(double dx) y, {double von = -1, double bis = 1}) {
      final p = Path();
      const n = 64;
      for (var i = 0; i <= n; i++) {
        final dx = von + (bis - von) * i / n;
        final pt = c + Offset(dx * rx, y(dx));
        i == 0 ? p.moveTo(pt.dx, pt.dy) : p.lineTo(pt.dx, pt.dy);
      }
      return p;
    }

    // Alles in eine Ebene, die zum Rand hin ausblendet (Randschwund) und
    // als Ganzes auftaucht (da).
    final rect = Rect.fromCenter(center: c, width: size.width, height: size.height);
    canvas.saveLayer(rect, Paint());

    final strich = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round;

    // ── Falten: zwei Bögen über dem Auge, zwei Tränensäcke darunter ──
    for (final (faktor, breite, a) in [(1.28, .78, .55), (1.55, .62, .35)]) {
      canvas.drawPath(kurve((dx) => -halb(dx) * faktor, von: -breite, bis: breite),
          strich..color = f.falte.withValues(alpha: a)..strokeWidth = 1.1 * k);
    }
    for (final (faktor, breite, a) in [(1.22, .6, .45), (1.42, .42, .3)]) {
      canvas.drawPath(kurve((dx) => halb(dx) * faktor, von: -breite, bis: breite),
          strich..color = f.falte.withValues(alpha: a)..strokeWidth = 1.0 * k);
    }

    // ── Die offene Fläche: zwischen Lidkante und Unterlid ──
    final offen = Path()..addPath(kurve(lidkante), Offset.zero);
    final unterPfad = kurve(unten, von: 1, bis: -1);
    offen.extendWithPath(unterPfad, Offset.zero);
    offen.close();

    canvas.save();
    canvas.clipPath(offen);
    // durchscheinendes Weiß, zu den Winkeln hin im Schatten
    canvas.drawRect(rect, Paint()
      ..shader = RadialGradient(
        colors: [f.weiss.withValues(alpha: .62), f.schatten.withValues(alpha: .55)],
        stops: const [.35, 1],
      ).createShader(Rect.fromCenter(center: c, width: rx * 2, height: rx * 2)));

    // Iris (leicht oval wie im Raster: y-Faktor 1,5 auf Feinpixel ≈ rund)
    final mitte = c + Offset(z.blickX * k, z.blickY * k);
    final ir = 13.0 * k;
    final pu = (z.denkt ? 3.2 + .5 * z.puls : 5.6) * k;
    final irisRect = Rect.fromCircle(center: mitte, radius: ir);
    canvas.drawCircle(mitte, ir, Paint()
      ..shader = RadialGradient(
        colors: [f.irishell, Color.lerp(f.irishell, f.iris, .5 + .3 * z.puls)!, f.iris, f.irisrand],
        stops: [pu / ir, (pu / ir + 1) / 2 - .1, .86, 1],
      ).createShader(irisRect));
    // Irisfasern: 22 feine Strahlen (sin(11·w) im Raster)
    final faser = Paint()
      ..color = f.irisrand.withValues(alpha: .18)
      ..strokeWidth = .6 * k;
    for (var i = 0; i < 22; i++) {
      final w = i * math.pi / 11;
      final r = Offset(math.cos(w), math.sin(w));
      canvas.drawLine(mitte + r * (pu + .8 * k), mitte + r * (ir - 1.4 * k), faser);
    }
    canvas.drawCircle(mitte, pu, Paint()..color = f.pupille.withValues(alpha: .95));
    canvas.drawCircle(mitte + Offset(-2.2 * k, -1.2 * k), 1.3 * k,
        Paint()..color = f.irishell); // Lichtpunkt

    // Funkenring beim Denken: Bogenstücke, die kreisen
    if (z.denkt) {
      final funke = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.1 * k
        ..strokeCap = StrokeCap.round
        ..color = f.irishell.withValues(alpha: .9);
      final rr = Rect.fromCircle(center: mitte, radius: ir + 1.8 * k);
      for (var i = 0; i < 4; i++) {
        canvas.drawArc(rr, z.ring + i * math.pi / 2, math.pi / 6, false, funke);
      }
    }

    // Schatten des Lids auf Iris und Weiß
    final lidY = c.dy + lidkante(0);
    canvas.drawRect(Rect.fromLTRB(rect.left, lidY, rect.right, lidY + 4 * k), Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [f.pupille.withValues(alpha: .45), f.pupille.withValues(alpha: 0)],
      ).createShader(Rect.fromLTRB(rect.left, lidY, rect.right, lidY + 4 * k)));
    canvas.restore();

    // ── Oberlid: von der Mandel-Oberkante bis zur Lidkante ──
    final lid = Path()..addPath(kurve((dx) => -halb(dx)), Offset.zero);
    lid.extendWithPath(kurve(lidkante, von: 1, bis: -1), Offset.zero);
    lid.close();
    canvas.drawPath(lid, Paint()..color = f.lid.withValues(alpha: .62));
    canvas.drawPath(kurve((dx) => -halb(dx)),
        strich..color = f.rand.withValues(alpha: .8)..strokeWidth = .9 * k);
    canvas.drawPath(kurve(lidkante),
        strich..color = f.rand.withValues(alpha: .85)..strokeWidth = 1.1 * k);
    canvas.drawPath(kurve(unten),
        strich..color = f.rand.withValues(alpha: .7)..strokeWidth = .9 * k);

    // ── Randschwund + Auftauchen: Maske von der Mitte nach außen ──
    canvas.drawRect(rect, Paint()
      ..blendMode = BlendMode.dstIn
      ..shader = LinearGradient(
        colors: [
          const Color(0x00000000),
          Color.fromRGBO(0, 0, 0, z.da),
          Color.fromRGBO(0, 0, 0, z.da),
          const Color(0x00000000),
        ],
        stops: const [0, .3, .7, 1],
      ).createShader(Rect.fromCenter(center: c, width: rx * 2.15, height: 1)));
    canvas.restore();
  }

  @override
  bool shouldRepaint(AugeMaler alt) =>
      alt.f != f ||
      alt.z.lid != z.lid || alt.z.blickX != z.blickX || alt.z.blickY != z.blickY ||
      alt.z.puls != z.puls || alt.z.ring != z.ring || alt.z.da != z.da ||
      alt.z.denkt != z.denkt;
}
