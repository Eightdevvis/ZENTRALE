// Das lebende Auge: öffnet sich beim Erscheinen, blinzelt ab und zu, schaut
// sich langsam um; denkt die KI, schaut es geradeaus, die Pupille zieht sich
// zusammen, die Iris pulst, ein Funkenring kreist. Zeiten wie in der TUI
// (pixel._blick, pixel._lid).

import 'dart:math' as math;

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

import '../thema/farben.dart';
import 'auge_maler.dart';

/// Fester Zufall pro Zeitabschnitt — dasselbe Auge sieht in derselben
/// Sekunde gleich aus, ohne Zustand mitzuschleppen.
double _rnd(int k, int salz) {
  final x = math.sin(k * 12.9898 + salz * 78.233) * 43758.5453;
  return x - x.floorToDouble();
}

double _ease(double t) => t * t * (3 - 2 * t);

(double, double) _blick(int ms) {
  final seg = ms ~/ 3200, rest = ms % 3200;
  (double, double) ziel(int k) => _rnd(k, 5) < .45
      ? (0, 0) // geradeaus
      : ((_rnd(k, 7) * 2 - 1) * 5, (_rnd(k, 11) * 2 - 1) * 1.5);
  final a = ziel(seg - 1), b = ziel(seg);
  final u = _ease(math.min(1, rest / 900)); // 0,9 s Blickwechsel
  return (a.$1 + (b.$1 - a.$1) * u, a.$2 + (b.$2 - a.$2) * u);
}

double _lidBlinzeln(int ms) {
  final abschnitt = ms ~/ 5200;
  final periode = 5200 + (_rnd(abschnitt, 3) * 2800).toInt();
  final p = ms % periode;
  return p < 360 ? (1 - p / 180).abs() : 1; // 1 → 0 → 1 in 0,36 s
}

class Auge extends StatefulWidget {
  const Auge({super.key, this.denkt = false, this.oeffnenIn = const Duration(milliseconds: 1400)});

  final bool denkt;

  /// Wie lange das Aufgehen dauert (Duration.zero: gleich offen).
  final Duration oeffnenIn;

  @override
  State<Auge> createState() => _AugeState();
}

class _AugeState extends State<Auge> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  Duration _t = Duration.zero;

  @override
  void initState() {
    super.initState();
    _ticker = createTicker((t) => setState(() => _t = t))..start();
  }

  @override
  void dispose() {
    _ticker.dispose();
    super.dispose();
  }

  AugeZustand _zustand() {
    final ms = _t.inMilliseconds;
    final dauer = widget.oeffnenIn.inMilliseconds;
    final offen = dauer == 0 ? 1.0 : math.min(1.0, ms / dauer);
    final o = _ease(offen) * (offen >= 1 ? _lidBlinzeln(ms) : 1);
    var (bx, by) = offen >= 1 ? _blick(ms) : (0.0, 0.0);
    final denkt = widget.denkt;
    if (denkt) bx = by = 0; // denkend schaut es geradeaus
    return AugeZustand(
      lid: o,
      blickX: bx,
      blickY: by,
      puls: denkt ? .5 + .5 * math.sin(ms / 220) : 0,
      ring: denkt ? ms / 300 : 0,
      da: math.min(1, offen * 1.4),
      denkt: denkt,
    );
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(painter: AugeMaler(_zustand(), AugeFarben.von(context))),
      );
}
