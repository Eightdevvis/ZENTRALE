// Colours and sizes of the calendar views, day AND night, derived from the
// eye palette (thema/farben.dart). One place to tune the look — the views
// only ask here.
//
// Readability first (E-ink rule): no text below [minText] px, and every
// text colour is checked against its own background for contrast ≥ 4.5:1
// ([readableOn]); if the preferred colour fails, the stronger fallback wins.

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../thema/farben.dart';
import 'calendar_item.dart';

// ── Sizes (logical px) ──────────────────────────────────────────────────────

/// Never smaller than this (memory: E-Ink-Lesbarkeit).
const double minText = 10;

/// Height of one hour in the day and week grid.
const double hourHeightDay = 56, hourHeightWeek = 48;

/// Width of the hour labels on the left.
const double gutterWidth = 44;

/// Tapping an empty slot snaps to this many minutes.
const int slotMinutes = 30;

/// Point events (no end) still get this height in minutes.
const int pointMinutes = 30;

/// How far to scroll above "now" when a grid opens.
const Duration scrollBeforeNow = Duration(hours: 2);

// ── Colours ─────────────────────────────────────────────────────────────────

class CalendarPalette {
  const CalendarPalette._({
    required this.night,
    required this.background,
    required this.text,
    required this.mutedText,
    required this.gridLine,
    required this.hourLine,
    required this.pad,
    required this.today,
    required this.now,
    required this.warning,
    required this.eventDefault,
    required this.tentativeDefault,
    required this.rhythmDefault,
    required this.outsideMonth,
  });

  final bool night;
  final Color background, text, mutedText, gridLine, hourLine, pad, today, now, warning;
  final Color eventDefault, tentativeDefault, rhythmDefault, outsideMonth;

  static CalendarPalette of(BuildContext context) => forTheme(Theme.of(context));

  static CalendarPalette forTheme(ThemeData theme) {
    final night = theme.brightness == Brightness.dark;
    final a = night ? AugeFarben.nacht : AugeFarben.tag;
    final scheme = theme.colorScheme;
    return CalendarPalette._(
      night: night,
      background: a.bg,
      text: scheme.onSurface,
      mutedText: night ? const Color(0xFF93A8B8) : const Color(0xFF4A5D6B),
      // Hour lines as thin traces, a solder pad where they meet the gutter.
      gridLine: Color.lerp(a.bg, a.lid, night ? .45 : .55)!,
      hourLine: Color.lerp(a.bg, a.lid, night ? .8 : 1)!,
      pad: Color.lerp(a.bg, a.falte, night ? .6 : .7)!,
      today: night ? a.rand : a.rand,
      now: night ? const Color(0xFFFF6B5E) : const Color(0xFFC62828),
      warning: scheme.error,
      eventDefault: a.iris,
      tentativeDefault: a.schatten,
      rhythmDefault: a.falte,
      outsideMonth: Color.lerp(a.bg, a.lid, night ? .12 : .18)!,
    );
  }

  /// Colour of an item: its calendar colour, else one by kind.
  Color colorOf(CalendarItem i) =>
      i.color ??
      switch (i.kind) {
        ItemKind.tentative => tentativeDefault,
        ItemKind.rhythm => rhythmDefault,
        ItemKind.deadline => warning,
        ItemKind.event => eventDefault,
      };

  /// Fill of a committed block: the calendar colour, a touch softened at night.
  Color eventFill(Color c) => night ? Color.lerp(c, background, .25)! : c;

  /// Fill of a tentative block: a weak tint of its colour.
  Color tentativeFill(Color c) => Color.lerp(background, c, night ? .22 : .16)!;

  /// Band behind the grid for a rhythm phase.
  Color rhythmBand(Color c) => Color.lerp(background, c, night ? .16 : .12)!;

  /// Text on [bg]: [preferred] if it reaches 4.5:1, else black or white,
  /// whichever reads better.
  Color readableOn(Color bg, [Color? preferred]) {
    if (preferred != null && contrast(preferred, bg) >= 4.5) return preferred;
    return contrast(Colors.black, bg) >= contrast(Colors.white, bg) ? Colors.black : Colors.white;
  }
}

/// WCAG contrast ratio of two opaque colours.
double contrast(Color a, Color b) {
  final la = a.computeLuminance(), lb = b.computeLuminance();
  return (math.max(la, lb) + .05) / (math.min(la, lb) + .05);
}
