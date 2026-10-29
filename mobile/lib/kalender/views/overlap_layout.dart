// Side-by-side layout of overlapping timed items in one day column.
//
// The classic algorithm: sort by start (longer first on ties), split into
// clusters of transitively overlapping items, give each item the first
// column that is free at its start. All items of a cluster share the
// cluster's column count. Afterwards an item grows to the right over
// columns that stay free for its whole duration — so a lone short event
// next to a long one is not squeezed to a sliver.
//
// Pure Dart, no widgets: unit-tested in test/calendar_views_test.dart.

import 'calendar_item.dart';

class PlacedItem {
  PlacedItem(this.item, this.start, this.end, this.column, this.span, this.columns);

  final CalendarItem item;

  /// Clipped to the day: minutes since the day's midnight (0 … 1440).
  final int start, end;

  /// First column (0-based), how many columns it covers, columns in its cluster.
  final int column, span, columns;

  double get left => column / columns;
  double get width => span / columns;
}

/// Minutes of [t] relative to the midnight of [day], clipped to 0 … 1440.
int minutesInDay(DateTime day, DateTime t) {
  final m = t.difference(dayOf(day)).inMinutes;
  return m < 0 ? 0 : (m > 24 * 60 ? 24 * 60 : m);
}

/// Lay out [items] (timed, not all-day) for [day]. [minMinutes] is the
/// minimum visual height so point events stay tappable.
List<PlacedItem> layoutDay(DateTime day, List<CalendarItem> items, {int minMinutes = 30}) {
  final spans = <(CalendarItem, int, int)>[];
  for (final i in items) {
    final s = minutesInDay(day, i.start);
    var e = minutesInDay(day, i.layoutEnd(Duration(minutes: minMinutes)));
    if (e - s < minMinutes) e = s + minMinutes;
    if (s >= 24 * 60) continue;
    spans.add((i, s, e));
  }
  spans.sort((a, b) {
    final c = a.$2.compareTo(b.$2);
    if (c != 0) return c;
    return (b.$3 - b.$2).compareTo(a.$3 - a.$2);
  });

  final out = <PlacedItem>[];
  var cluster = <(CalendarItem, int, int, int)>[]; // item, start, end, column
  var columnEnds = <int>[];
  var clusterEnd = -1;

  void flush() {
    if (cluster.isEmpty) return;
    final n = columnEnds.length;
    for (final (item, s, e, col) in cluster) {
      // Grow right while the next column is free over [s, e).
      var span = 1;
      while (col + span < n &&
          !cluster.any((o) => o.$4 == col + span && o.$2 < e && s < o.$3)) {
        span++;
      }
      out.add(PlacedItem(item, s, e, col, span, n));
    }
    cluster = [];
    columnEnds = [];
  }

  for (final (item, s, e) in spans) {
    if (s >= clusterEnd) {
      flush();
      clusterEnd = e;
    } else if (e > clusterEnd) {
      clusterEnd = e;
    }
    var col = columnEnds.indexWhere((end) => end <= s);
    if (col < 0) {
      col = columnEnds.length;
      columnEnds.add(e);
    } else {
      columnEnds[col] = e;
    }
    cluster.add((item, s, e, col));
  }
  flush();
  return out;
}
