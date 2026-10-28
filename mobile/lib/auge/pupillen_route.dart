// Der Weg vom Auge in den Chat: die Pupille hat die Mandel gefüllt (Auge
// antippen), genau diese Mandel wächst in Pupillenfarbe über den ganzen
// Schirm, und aus dem Dunkel blendet der Chat auf. Zurück läuft es rückwärts
// und endet wieder in der vollen Mandel, aus der sich die Pupille dann
// zusammenzieht (startseite.dart). So gibt es keinen Schnitt, nur eine Bewegung.

import 'dart:math' as math;

import 'package:flutter/widgets.dart';

import 'auge_maler.dart';
import 'auge_regler.dart';
import 'zeit.dart';

/// mandel: die Mandel des Auges in Bildschirm-Koordinaten (Breite = 2·rx).
PageRouteBuilder<T> pupillenRoute<T>({
  required Rect mandel,
  required Color farbe,
  required WidgetBuilder seite,
}) =>
    PageRouteBuilder<T>(
      transitionDuration: const Duration(milliseconds: uebergangMs),
      reverseTransitionDuration: const Duration(milliseconds: uebergangZurueckMs),
      pageBuilder: (context, _, _) => seite(context),
      transitionsBuilder: (_, anim, _, kind) => Stack(fit: StackFit.expand, children: [
        FadeTransition(
          opacity: CurvedAnimation(parent: anim, curve: const Interval(.45, 1, curve: Curves.easeOut)),
          child: kind,
        ),
        IgnorePointer(child: CustomPaint(painter: _Fleck(mandel, farbe, anim))),
      ]),
    );

class _Fleck extends CustomPainter {
  _Fleck(this.mandel, this.farbe, this.anim) : super(repaint: anim);

  final Rect mandel;
  final Color farbe;
  final Animation<double> anim;

  @override
  void paint(Canvas canvas, Size size) {
    final u = anim.value;
    final deck = 1 - sanft((u - .45) / .5);
    if (deck <= 0) return;
    final rx = mandel.width / 2;
    // Groß genug, dass schon der dicke Mittelteil der Mandel (halbe Breite)
    // den Schirm deckt — auch die entfernteste Ecke.
    final ecke = [
      size.topLeft(Offset.zero), size.topRight(Offset.zero),
      size.bottomLeft(Offset.zero), size.bottomRight(Offset.zero),
    ].map((p) => (p - mandel.center).distance).reduce(math.max);
    final groesste = ecke / (rx * .5 * mandelHoehe);
    final s = 1 + (groesste - 1) * Curves.easeIn.transform((u / .55).clamp(0.0, 1.0));
    canvas.drawPath(mandelPfad(mandel.center, rx * s), Paint()..color = farbe.withValues(alpha: deck));
  }

  @override
  bool shouldRepaint(_Fleck alt) => alt.mandel != mandel || alt.farbe != farbe;
}
