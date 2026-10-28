// Das lebende Auge: öffnet sich beim Erscheinen, blinzelt ab und zu, schaut
// sich langsam um; denkt die KI, schaut es geradeaus, die Pupille zieht sich
// zusammen, die Iris pulst, ein Funkenring kreist. Zeiten wie in der TUI
// (pixel._blick, pixel._lid). Dazu seit 28.10.2026: die Pupille folgt der
// Uhrzeit, ab und zu kommt eine Laune, und angetippt füllt die Pupille das
// ganze Auge (Steuerung von außen über [AugeSteuerung]).

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

import '../thema/farben.dart';
import 'auge_maler.dart';
import 'auge_regler.dart';
import 'launen.dart';
import 'zeit.dart';

/// Fernbedienung fürs Auge — die Startseite hält eine, das Auge meldet sich
/// an. Warum kein Zustand im Widget-Baum: Antippen und Vorschau sind
/// Ereignisse, keine Eigenschaften.
class AugeSteuerung {
  _AugeState? _auge;
  int _naechste = 0;

  /// 0 = offen, 1 = ganz geschlossen (Knopf-Ring der Startseite). Ein Feld
  /// statt eines Ereignisses, weil es Bild für Bild mitläuft — das Auge liest
  /// es in jedem Takt seines Tickers, ohne dass jemand neu baut.
  double zu = 0;

  /// Die Pupille wächst, bis sie das Auge füllt; erfüllt, wenn sie es tut.
  Future<void> fuellen() => _auge?._fuellenNach(1) ?? Future.value();

  /// Zurück zum normalen Auge (nach der Rückkehr aus dem Chat).
  Future<void> leeren() => _auge?._fuellenNach(0) ?? Future.value();

  /// Vorschau: spielt die nächste Laune der Reihe nach sofort ab und nennt
  /// ihren Namen — damit Sasha alle sehen kann, ohne Minuten zu warten.
  String naechsteLaune() {
    final l = alleLaunen[_naechste++ % alleLaunen.length];
    _auge?._vorschau(l);
    return l.name;
  }
}

class Auge extends StatefulWidget {
  const Auge({
    super.key,
    this.denkt = false,
    this.oeffnenIn = const Duration(milliseconds: 1400),
    this.steuerung,
    this.uhr,
    this.launen = true,
  });

  final bool denkt;

  /// Wie lange das Aufgehen dauert (Duration.zero: gleich offen).
  final Duration oeffnenIn;

  final AugeSteuerung? steuerung;

  /// Woher die Uhrzeit kommt (Tests setzen eine feste); sonst die des Handys.
  final DateTime Function()? uhr;

  /// Ob von selbst Launen kommen (denkend nie).
  final bool launen;

  @override
  State<Auge> createState() => _AugeState();
}

class _AugeState extends State<Auge> with SingleTickerProviderStateMixin {
  late final Ticker _ticker;
  Duration _t = Duration.zero;

  // Antippen: von wo nach wo, ab wann, und wer auf das Ende wartet.
  double _fuellVon = 0, _fuellZiel = 0;
  int _fuellAb = 0, _fuellDauer = 1;
  Completer<void>? _fuellFertig;

  // Vorschau-Laune (langes Drücken) mit ihrem Beginn.
  Laune? _vorschauLaune;
  int _vorschauAb = 0;

  @override
  void initState() {
    super.initState();
    widget.steuerung?._auge = this;
    _ticker = createTicker(_tick)..start();
  }

  @override
  void didUpdateWidget(Auge alt) {
    super.didUpdateWidget(alt);
    if (alt.steuerung != widget.steuerung) {
      if (alt.steuerung?._auge == this) alt.steuerung?._auge = null;
      widget.steuerung?._auge = this;
    }
  }

  @override
  void dispose() {
    if (widget.steuerung?._auge == this) widget.steuerung?._auge = null;
    _ticker.dispose();
    _fuellFertig?.complete();
    super.dispose();
  }

  void _tick(Duration t) {
    setState(() => _t = t);
    final fertig = _fuellFertig;
    if (fertig != null && t.inMilliseconds - _fuellAb >= _fuellDauer) {
      _fuellFertig = null;
      fertig.complete();
    }
  }

  double _fuellWert(int ms) {
    final u = ((ms - _fuellAb) / _fuellDauer).clamp(0.0, 1.0);
    return _fuellVon + (_fuellZiel - _fuellVon) * u;
  }

  Future<void> _fuellenNach(double ziel) {
    final ms = _t.inMilliseconds;
    _fuellVon = _fuellWert(ms);
    _fuellZiel = ziel;
    _fuellAb = ms;
    // Die Dauer anteilig zum Weg, damit ein halber Weg nicht schleicht.
    final weg = (ziel - _fuellVon).abs();
    _fuellDauer = math.max(1, ((ziel > 0 ? tippenMs : zurueckMs) * weg).round());
    _fuellFertig?.complete();
    return (_fuellFertig = Completer<void>()).future;
  }

  void _vorschau(Laune l) {
    _vorschauLaune = l;
    _vorschauAb = _t.inMilliseconds;
  }

  AugeZustand _zustand() {
    final ms = _t.inMilliseconds;
    final dauer = widget.oeffnenIn.inMilliseconds;
    final offen = dauer == 0 ? 1.0 : math.min(1.0, ms / dauer);
    // Geschlossen (Knopf-Ring): beide Lider treffen sich ruhig in der Mitte,
    // der Blick kehrt dabei zur Mitte zurück.
    final zu = sanft(widget.steuerung?.zu ?? 0);
    final o = sanft(offen) * (offen >= 1 ? lidBlinzeln(ms) : 1) * (1 - zu);
    var (bx, by) = offen >= 1 ? blick(ms) : (0.0, 0.0);
    bx *= 1 - zu;
    by *= 1 - zu;
    final denkt = widget.denkt;
    if (denkt) bx = by = 0; // denkend schaut es geradeaus
    final jetzt = (widget.uhr ?? DateTime.now)();
    final fuellen = _fuellWert(ms);
    var z = AugeZustand(
      lid: o,
      blickX: bx,
      blickY: by,
      puls: denkt ? .5 + .5 * math.sin(ms / 220) : 0,
      ring: denkt ? ms / 300 : 0,
      da: math.min(1, offen * 1.4),
      denkt: denkt,
      // denkend gilt die Denk-Pupille, sonst die der Uhrzeit
      pupille: denkt ? 1 : pupilleNachUhrzeit(jetzt),
      fuellen: fuellen,
    );

    // Launen nur, wenn das Auge in Ruhe ist: offen, nicht denkend, nicht
    // gerade angetippt, nicht geschlossen. Die Vorschau geht der Uhr vor.
    if (denkt || offen < 1 || fuellen > 0 || zu > 0) return z;
    (Laune, double)? laune;
    final v = _vorschauLaune;
    if (v != null) {
      final t = (ms - _vorschauAb) / v.dauerMs;
      if (t < 1) {
        laune = (v, t);
      } else {
        _vorschauLaune = null;
      }
    }
    if (laune == null && widget.launen) laune = launeZu(jetzt.millisecondsSinceEpoch);
    if (laune == null) return z;
    final (l, t) = laune;
    final s = launenStaerke(t);
    return l.formen(z.mit(laune: l, launeT: t, launeS: s), t, s);
  }

  @override
  Widget build(BuildContext context) => RepaintBoundary(
        child: CustomPaint(painter: AugeMaler(_zustand(), AugeFarben.von(context))),
      );
}
