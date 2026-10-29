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
import 'package:flutter/physics.dart';

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
  const Startseite({super.key, required this.kiOeffnen, this.knoepfe = bereiche, this.cornerHint});

  /// Öffnet die KI; bekommt die Mandel des Auges in Bildschirm-Koordinaten,
  /// damit der Übergang genau dort weitermacht. Erfüllt, wenn die KI wieder zu ist.
  final Future<void> Function(Rect mandel) kiOeffnen;

  /// Die Knöpfe im Ring — sonst [bereiche]; Tests geben eigene.
  final List<Bereich> knoepfe;

  /// A small hint in the top right corner (e.g. lib/update UpdateHint) — or nothing.
  final Widget? cornerHint;

  @override
  State<Startseite> createState() => _StartseiteState();
}

class _StartseiteState extends State<Startseite> with SingleTickerProviderStateMixin {
  final _auge = AugeSteuerung();
  final _augeOrt = GlobalKey();
  bool _oeffnet = false;

  /// Der Ring: 0 = Auge offen, keine Knöpfe; 1 = Auge zu, Knöpfe da. Ohne
  /// Grenzen, damit die Feder beim Loslassen ein wenig über das Ziel schwingen
  /// darf und sich setzt — das Auge federt dabei nach (zeit.offenNachZu).
  late final AnimationController _ring = AnimationController.unbounded(vsync: this)
    ..addListener(_ringGeaendert);

  /// Wohin der Ring zuletzt wollte (0 oder 1) — tippbar sind die Knöpfe nur,
  /// wenn er zu ist und dort auch bleiben will.
  double _ziel = 0;

  // Bahnen hängen nur von Fläche und Anzahl ab — einmal planen.
  (Size, int, List<Offset>, List<Bahn>)? _plan;

  bool get _ringDa => _ziel == 1;

  @override
  void dispose() {
    _ring.dispose();
    super.dispose();
  }

  void _ringGeaendert() {
    final r = _ring.value;
    // Das Auge schließt sich im ersten Teil der Bewegung; darüber hinaus
    // (Feder schwingt über 1 oder unter 0) reicht der Ausschlag als Nachfedern weiter.
    _auge.zu = r < 0 ? r : r > 1 ? 1 + (r - 1) : math.min(1.0, r / augeZuBis);
  }

  /// Zum Ziel federn — tempo in Ring-Einheiten je Sekunde (vom Finger).
  void _federn(double ziel, [double tempo = 0]) {
    _ziel = ziel;
    _ring.animateWith(SpringSimulation(
      SpringDescription.withDampingRatio(mass: 1, stiffness: ringFeder, ratio: ringDaempfung),
      _ring.value, ziel, tempo,
      tolerance: const Tolerance(distance: .001, velocity: .01),
    ));
  }

  void _aufmachen() => _federn(0);

  // ── Wischen: der Ring folgt dem Finger, Loslassen entscheidet ──

  void _ziehen(DragUpdateDetails d) {
    if (_ring.isAnimating) _ring.stop();
    _ring.value = (_ring.value + (d.primaryDelta ?? 0) / wischStrecke).clamp(0.0, 1.0);
  }

  void _gewischt(DragEndDetails d) {
    final tempo = (d.primaryVelocity ?? 0) / wischStrecke;
    // Schnell geschnippt zählt die Richtung, sonst wo der Finger losließ.
    final ziel = tempo.abs() > wischTempo / wischStrecke
        ? (tempo > 0 ? 1.0 : 0.0)
        : (_ring.value >= .5 ? 1.0 : 0.0);
    _federn(ziel, tempo);
  }

  Future<void> _tippen() async {
    if (_ringDa) return _aufmachen(); // geschlossenes Auge: aufmachen
    if (_oeffnet || _ring.value.abs() > .01) return; // doppeltes Tippen öffnet nicht zweimal
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
    if (_ring.value.abs() > .01) return; // geschlossen sieht man keine Laune
    final name = _auge.naechsteLaune();
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('Laune: $name'), duration: const Duration(seconds: 2)));
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
          onVerticalDragStart: (_) => _ring.stop(),
          onVerticalDragUpdate: _ziehen,
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
              if (widget.cornerHint != null) Positioned(top: 4, right: 4, child: widget.cornerHint!),
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
          final r = _ring.value;
          final w = sanft((r - von) / math.max(.05, 1 - von));
          if (w <= 0) return const SizedBox.shrink();
          return IgnorePointer(
            ignoring: !(_ringDa && r >= .98), // nur fertig gezeigt tippbar
            // Schwingt die Feder über 1, ploppt der Chip ein Spürchen auf.
            child: Opacity(
                opacity: w,
                child: Transform.scale(scale: (.3 + .7 * w) * (1 + math.max(0.0, r - 1) * .8), child: kind)),
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
