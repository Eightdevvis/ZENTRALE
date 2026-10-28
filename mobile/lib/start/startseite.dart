// Die Startseite: das Auge in der Mitte.
//
// - Tippen aufs offene Auge → die Pupille füllt das Auge, dann geht die KI
//   auf (auge/pupillen_route.dart). Lange drücken → die nächste Laune als
//   Vorschau (auge/launen.dart).
// - Runterwischen → das Auge schließt sich, aus seinem Rand wachsen
//   Leiterbahnen zu den Knöpfen, einer je Bereich aus [bereiche]
//   (leiterbahnen.dart). Hochwischen oder aufs geschlossene Auge tippen →
//   alles läuft zurück ins Auge. Standard: Auge offen, keine Knöpfe — die
//   KI ist das Wichtigste, der Rest wartet hinter dem geschlossenen Auge.
//
// Ein neuer Bereich ist ein Eintrag in der Liste, kein Umbau: die Knöpfe
// ordnen sich für jede Anzahl selbst auf einer Ellipse um das Auge.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../auge/auge.dart';
import '../auge/auge_maler.dart';
import '../auge/auge_regler.dart';
import '../auge/zeit.dart';
import '../kalender/kalender_seite.dart';
import '../thema/farben.dart';
import 'leiterbahnen.dart';

class Bereich {
  const Bereich(this.name, this.symbol, this.seite);
  final String name;
  final IconData symbol;
  final WidgetBuilder seite;
}

/// Die Knöpfe um das Auge — der Kalender ist der erste (Sasha, 28.10.2026).
const List<Bereich> bereiche = [
  Bereich('Kalender', Icons.calendar_month_outlined, kalenderSeite),
];

class Startseite extends StatefulWidget {
  const Startseite({super.key, required this.kiOeffnen, this.knoepfe = bereiche});

  /// Öffnet die KI; bekommt die Mandel des Auges in Bildschirm-Koordinaten,
  /// damit der Übergang genau dort weitermacht. Erfüllt, wenn die KI wieder zu ist.
  final Future<void> Function(Rect mandel) kiOeffnen;

  /// Die Knöpfe im Ring — sonst [bereiche]; Tests geben eigene.
  final List<Bereich> knoepfe;

  @override
  State<Startseite> createState() => _StartseiteState();
}

class _StartseiteState extends State<Startseite> with SingleTickerProviderStateMixin {
  final _auge = AugeSteuerung();
  final _augeOrt = GlobalKey();
  bool _oeffnet = false;
  double _zug = 0;

  /// Der Ring: 0 = Auge offen, keine Knöpfe; 1 = Auge zu, Knöpfe da.
  late final AnimationController _ring = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: ringMs),
    reverseDuration: const Duration(milliseconds: ringZurueckMs),
  )..addListener(() => _auge.zu = (_ring.value / augeZuBis).clamp(0.0, 1.0));

  // Bahnen hängen nur von Fläche und Anzahl ab — einmal planen.
  (Size, int, List<Offset>, List<Bahn>)? _plan;

  bool get _ringDa => _ring.value > 0 && _ring.status != AnimationStatus.reverse;

  @override
  void dispose() {
    _ring.dispose();
    super.dispose();
  }

  void _schliessen() => _ring.forward();

  void _aufmachen() => _ring.reverse();

  Future<void> _tippen() async {
    if (_ringDa) return _aufmachen(); // geschlossenes Auge: aufmachen
    if (_oeffnet || _ring.value > 0) return; // doppeltes Tippen öffnet nicht zweimal
    _oeffnet = true;
    try {
      await _auge.fuellen();
      final box = _augeOrt.currentContext?.findRenderObject() as RenderBox?;
      if (!mounted || box == null) return;
      final rx = mandelRadius(box.size);
      final mitte = box.localToGlobal(box.size.center(Offset.zero));
      await widget.kiOeffnen(
          Rect.fromCenter(center: mitte, width: 2 * rx, height: 2 * rx * mandelHoehe));
      // Der Rückweg endet in der vollen Mandel — erst danach zieht sich die
      // Pupille zusammen, sonst sähe man das Auge unter dem Fleck springen.
      await Future<void>.delayed(const Duration(milliseconds: uebergangZurueckMs));
      if (mounted) await _auge.leeren();
    } finally {
      _oeffnet = false;
    }
  }

  void _vorschau() {
    if (_ring.value > 0) return; // geschlossen sieht man keine Laune
    final name = _auge.naechsteLaune();
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('Laune: $name'), duration: const Duration(seconds: 2)));
  }

  void _gewischt(DragEndDetails d) {
    final tempo = d.primaryVelocity ?? 0;
    if (tempo > wischTempo || (tempo.abs() <= wischTempo && _zug > wischWeg)) {
      _schliessen();
    } else if (tempo < -wischTempo || _zug < -wischWeg) {
      _aufmachen();
    }
    _zug = 0;
  }

  @override
  Widget build(BuildContext context) {
    final farben = AugeFarben.von(context);
    final nacht = Theme.of(context).brightness == Brightness.dark;
    return Scaffold(
      body: SafeArea(
        child: GestureDetector(
          // Wischen überall auf dem Schirm, damit man das Auge nicht genau
          // treffen muss; Tippen nur aufs Auge.
          behavior: HitTestBehavior.opaque,
          onVerticalDragStart: (_) => _zug = 0,
          onVerticalDragUpdate: (d) => _zug += d.primaryDelta ?? 0,
          onVerticalDragEnd: _gewischt,
          child: LayoutBuilder(builder: (context, platz) {
            final breite = math.min(platz.maxWidth * .72, 340.0);
            final mitte = Offset(platz.maxWidth / 2, platz.maxHeight / 2);
            // Höhe mit Platz für die Falten über und unter dem Auge.
            final hoehe = breite * 1.1;
            final (orte, bahnen) = _planen(platz.biggest, mitte, breite, hoehe);
            return Stack(children: [
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(painter: LeiterbahnMaler(bahnen, _ring, farben, nacht)),
                ),
              ),
              Positioned(
                left: mitte.dx - breite / 2,
                top: mitte.dy - hoehe / 2,
                width: breite,
                height: hoehe,
                child: Semantics(
                  button: true,
                  label: 'ZENTRALE-KI öffnen',
                  child: GestureDetector(
                    key: _augeOrt,
                    behavior: HitTestBehavior.opaque,
                    onTap: _tippen,
                    onLongPress: _vorschau,
                    child: Auge(steuerung: _auge),
                  ),
                ),
              ),
              for (final (i, b) in widget.knoepfe.indexed)
                _knopf(context, b, orte[i], i, farben, nacht),
            ]);
          }),
        ),
      ),
    );
  }

  (List<Offset>, List<Bahn>) _planen(Size flaeche, Offset mitte, double breite, double hoehe) {
    final n = widget.knoepfe.length;
    final alt = _plan;
    if (alt != null && alt.$1 == flaeche && alt.$2 == n) return (alt.$3, alt.$4);
    final rx = mandelRadius(Size(breite, hoehe));
    // Ellipse so weit, dass Chips nicht über den Rand ragen und die Bahnen
    // sichtbar lang genug sind, um nach Platine auszusehen.
    final rxRing = math.min(flaeche.width / 2 - chipGroesse * .75, rx * 1.55);
    final ryRing = math.min(flaeche.height / 2 - chipGroesse * .75, rx * 1.75);
    final orte = knopfOrte(n, mitte, rxRing, ryRing);
    final bahnen = bahnenPlanen(mitte, rx, rx * mandelHoehe, orte);
    _plan = (flaeche, n, orte, bahnen);
    return (orte, bahnen);
  }

  Widget _knopf(BuildContext context, Bereich b, Offset ort, int i, AugeFarben farben, bool nacht) {
    const g = chipGroesse;
    return Positioned(
      left: ort.dx - g / 2,
      top: ort.dy - g / 2,
      width: g,
      height: g,
      child: AnimatedBuilder(
        animation: _ring,
        builder: (context, kind) {
          // Jeder Chip wächst am Ende seiner Bahn auf, einer nach dem anderen.
          final von = knoepfeVon + i * knopfVersatz;
          final w = sanft((_ring.value - von) / math.max(.05, 1 - von));
          if (w <= 0) return const SizedBox.shrink();
          return IgnorePointer(
            ignoring: !(_ringDa && _ring.value >= 1), // nur fertig gezeigt tippbar
            child: Opacity(opacity: w, child: Transform.scale(scale: .3 + .7 * w, child: kind)),
          );
        },
        child: Tooltip(
          message: b.name,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: b.seite)),
            child: CustomPaint(
              painter: ChipMaler(farben, nacht),
              child: Center(child: Icon(b.symbol, size: g * .42, color: farben.rand)),
            ),
          ),
        ),
      ),
    );
  }
}
