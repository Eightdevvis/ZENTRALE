// The contract an app fulfils to be shown through the peephole.
//
// A surface is a large virtual sheet lying on a table (a calendar spread, a
// map, a canvas, later any app's `flaeche` building block from the app
// engine — memory/hub/app_motor_plan.md). The peephole is only the frame: it
// owns motion, zoom, the table and the minimap; the surface only says how big
// it is and paints the part that is visible. The same contract is meant for
// later AR (ARCore on the phone, AR glasses on the "Mini"): only the way the
// visible rect is chosen changes, never the surface.

import 'package:flutter/widgets.dart';

import '../thema/farben.dart';

/// Colours and scale handed to [PeepholeSurface.paint]. The surface gets
/// meaning-level colours (ink, muted, accent) — the frame decides the palette.
class PeepholeStyle {
  const PeepholeStyle({
    required this.eye,
    required this.night,
    required this.ink,
    required this.inkMuted,
    required this.sheet,
    required this.warning,
    required this.scale,
    this.locale = 'de',
    this.fontFamily,
  });

  /// The eye palette (lib/thema/farben.dart), day or night.
  final AugeFarben eye;
  final bool night;

  /// Text colours that keep ≥ 4.5:1 on [sheet].
  final Color ink, inkMuted;

  /// Background of the sheet (already painted by the frame).
  final Color sheet;
  final Color warning;

  /// Screen pixels per surface unit right now. Use it for level of detail:
  /// text whose `fontSize * scale` would be below `minTextPixels` should be
  /// left out (see [PeepholeSurface.textVisible]).
  final double scale;

  /// Language for dates and the like (from the app's locale).
  final String locale;

  /// Font for text the surface paints; null = the platform's default.
  final String? fontFamily;

  PeepholeStyle withScale(double s) => PeepholeStyle(
    eye: eye,
    night: night,
    ink: ink,
    inkMuted: inkMuted,
    sheet: sheet,
    warning: warning,
    scale: s,
    locale: locale,
    fontFamily: fontFamily,
  );
}

/// Something a tap on the surface found.
class PeepholeHit {
  const PeepholeHit({required this.title, this.detail, this.payload});
  final String title;
  final String? detail;

  /// Whatever the app needs to act on it (e.g. the calendar occurrence).
  final Object? payload;
}

abstract class PeepholeSurface {
  /// Size in virtual units (any unit; the frame scales).
  Size get size;

  /// How many units wide the window is when it opens (a comfortable reading
  /// width, e.g. two day columns). The frame derives the start zoom from it.
  double get comfortableViewWidth;

  /// Where the window starts and where recenter returns (e.g. today).
  Offset get home;

  /// Repaint when this fires (data changed). Null = static.
  Listenable? get repaint => null;

  /// Paint in surface units. The canvas is already translated and scaled;
  /// [visible] is the visible part in surface units — skip what lies outside
  /// it. The sheet background is painted by the frame.
  void paint(Canvas canvas, Rect visible, PeepholeStyle style);

  /// What lies under [point] (surface units), or null.
  PeepholeHit? hitTest(Offset point) => null;

  /// Helper for level of detail.
  static bool textVisible(double fontSize, PeepholeStyle style, double minPixels) =>
      fontSize * style.scale >= minPixels;
}
