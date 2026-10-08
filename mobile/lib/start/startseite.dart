// Die Startseite: das Auge in der Mitte. Tippen → die KI.
//
// Um das Auge bilden sich Knöpfe — einer je Bereich aus [bereiche]. Heute
// gibt es außer der KI (dem Auge selbst) noch keinen, also bleibt der Ring
// leer. Ein neuer Bereich ist ein Eintrag in der Liste, kein Umbau.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../auge/auge.dart';
import '../thema/farben.dart';

class Bereich {
  const Bereich(this.name, this.symbol, this.seite);
  final String name;
  final IconData symbol;
  final WidgetBuilder seite;
}

/// Die Knöpfe um das Auge. Noch leer: „aber weil wir noch nix außer der ki
/// drin haben, bilden sich doch keine knöpfe drum rum yet" (Sasha, 08.10.2026).
const List<Bereich> bereiche = [];

class Startseite extends StatelessWidget {
  const Startseite({super.key, required this.kiOeffnen});

  final VoidCallback kiOeffnen;

  @override
  Widget build(BuildContext context) {
    final farben = AugeFarben.von(context);
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(builder: (context, platz) {
          final breite = math.min(platz.maxWidth * .72, 340.0);
          final mitte = Offset(platz.maxWidth / 2, platz.maxHeight / 2);
          return Stack(children: [
            Positioned(
              left: mitte.dx - breite / 2,
              top: mitte.dy - breite * .4,
              width: breite,
              height: breite * .8,
              child: Semantics(
                button: true,
                label: 'ZENTRALE-KI öffnen',
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: kiOeffnen,
                  child: const Auge(),
                ),
              ),
            ),
            for (final (i, b) in bereiche.indexed)
              _knopf(context, b, mitte, breite * .78, i, bereiche.length, farben),
          ]);
        }),
      ),
    );
  }

  Widget _knopf(BuildContext context, Bereich b, Offset mitte, double radius,
      int i, int n, AugeFarben farben) {
    final w = -math.pi / 2 + 2 * math.pi * i / n;
    final p = mitte + Offset(math.cos(w), math.sin(w)) * radius;
    return Positioned(
      left: p.dx - 28,
      top: p.dy - 28,
      width: 56,
      height: 56,
      child: IconButton.outlined(
        tooltip: b.name,
        icon: Icon(b.symbol, color: farben.rand),
        onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: b.seite)),
      ),
    );
  }
}
