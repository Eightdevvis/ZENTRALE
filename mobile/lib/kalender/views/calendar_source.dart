// The one bridge between the phone's calendar (kalender.dart) and the
// views: turns occurrences into [CalendarItem]s.
//
// Performance: occurrences (incl. RRULE expansion) are computed per month
// only when a visible page asks for it, and kept for the last few months
// (LRU). Paging a week or a day therefore costs a map lookup; a new month
// costs one Kalender.vorkommen call over ~32 days. A new Kalender object
// (after every sync) means a fresh cache.

import 'dart:ui' show Color;

import '../kalender.dart';
import 'calendar_item.dart';

class KalenderItemSource implements CalendarItemSource {
  KalenderItemSource(this.kalender, {this.keepMonths = 8});

  final Kalender kalender;
  final int keepMonths;
  final Map<DateTime, Map<DateTime, List<CalendarItem>>> _months = {};

  /// How many months were expanded so far (tests check the cache works).
  int expandedMonths = 0;

  @override
  Map<DateTime, List<CalendarItem>> itemsFor(DateTime from, DateTime to) {
    final out = <DateTime, List<CalendarItem>>{};
    for (var d = dayOf(from); !d.isAfter(to); d = addDays(d, 1)) {
      final l = _month(monthStart(d))[d];
      if (l != null) out[d] = l;
    }
    return out;
  }

  Map<DateTime, List<CalendarItem>> _month(DateTime m) {
    final hit = _months.remove(m);
    if (hit != null) return _months[m] = hit; // re-insert = most recent
    expandedMonths++;
    final last = DateTime.utc(m.year, m.month + 1, 0);
    // One day before: phases that start the evening before and cross midnight.
    final occ = kalender.vorkommen(addDays(m, -1), last);
    final byDay = <DateTime, List<CalendarItem>>{};
    for (final l in occ.values) {
      for (final v in l) {
        if (v.versteckt && !v.switchedOff) continue; // switched-off: shown faint, can go back on
        final item = itemFromOccurrence(v, _color(v.ebene));
        final first = dayOf(item.start);
        final lastDay = item.allDay || item.end == null
            ? first
            : dayOf(item.end!.subtract(const Duration(microseconds: 1)));
        for (var d = first; !d.isAfter(lastDay); d = addDays(d, 1)) {
          if (d.isBefore(m) || d.isAfter(last)) continue;
          byDay.putIfAbsent(d, () => []).add(item);
        }
      }
    }
    _months[m] = byDay;
    while (_months.length > keepMonths) {
      _months.remove(_months.keys.first);
    }
    return byDay;
  }

  final Map<String, Color?> _colors = {};
  Color? _color(String layer) => _colors.putIfAbsent(layer, () => parseVdirColor(kalender.ebene(layer)?.farbe));
}

/// vdir `color` ("#3b82f6", also "#3b82f6ff") → Color, else null.
Color? parseVdirColor(String? raw) {
  final m = RegExp(r'^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$').firstMatch(raw?.trim() ?? '');
  if (m == null) return null;
  return Color(0xFF000000 | int.parse(m.group(1)!, radix: 16));
}

ItemKind kindOf(Vorkommen v) {
  if (v.deadline) return ItemKind.deadline;
  return switch (v.ebene) {
    ebeneVielleicht => ItemKind.tentative,
    ebeneRhythmus => ItemKind.rhythm,
    _ => ItemKind.event,
  };
}

CalendarItem itemFromOccurrence(Vorkommen v, Color? color) {
  final allDay = v.zeit == null;
  return CalendarItem(
    id: '${v.kennung ?? v.label}@${v.tag.toIso8601String()}',
    kind: kindOf(v),
    label: v.label,
    start: v.beginn,
    end: allDay ? null : v.endeZeit,
    allDay: allDay,
    color: color,
    colour: v.colour,
    place: v.ort,
    softDeadline: v.sollBeginn,
    waiting: v.wartet,
    switchedOff: v.switchedOff,
    payload: v,
  );
}
