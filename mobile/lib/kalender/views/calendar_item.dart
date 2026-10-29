// The data the calendar views draw — and nothing else.
//
// The views (day, week, month) are a pure layout layer: they get a list of
// [CalendarItem]s per day and draw them. They never reach into the .ics
// files, the sync or the crypto. That keeps them reusable as the future
// `zeitraster` building block of the app engine
// (memory/hub/app_motor_plan.md): whatever produces items — today the
// phone's own calendar (calendar_source.dart), later an app answer — the
// views stay the same.
//
// Times are local wall-clock times on a UTC carrier (DateTime.utc), the
// same convention as the rest of lib/kalender: no time zone ever shifts a day.

import 'dart:ui' show Color;

/// What kind of entry this is — decides weight and drawing order.
enum ItemKind {
  /// Committed appointment: full colour.
  event,

  /// An option, not committed yet: weaker, striped, drawn beneath.
  tentative,

  /// A phase of the daily rhythm (sleep, meals): subtle background band.
  rhythm,

  /// A deadline: a marker line at its "must" time.
  deadline,
}

class CalendarItem {
  const CalendarItem({
    required this.id,
    required this.kind,
    required this.label,
    required this.start,
    this.end,
    this.allDay = false,
    this.color,
    this.place,
    this.softDeadline,
    this.waiting = false,
    this.switchedOff = false,
    this.payload,
  });

  /// Stable per occurrence (used as widget key).
  final String id;
  final ItemKind kind;
  final String label;

  /// Start (all-day: midnight of the day).
  final DateTime start;

  /// End, may be on the next day (phases across midnight); null = a point.
  final DateTime? end;
  final bool allDay;

  /// Calendar colour (vdir `color`), null = the view picks one by [kind].
  final Color? color;
  final String? place;

  /// Deadlines: the "should" time (before the "must" time = [start]).
  final DateTime? softDeadline;

  /// Entered on the phone, not yet confirmed by the sync.
  final bool waiting;

  /// One occurrence of a series switched off: drawn as an outline only.
  final bool switchedOff;

  /// Whatever the producer wants back on tap (the views never look inside).
  final Object? payload;

  /// Should has passed, must not yet ("soll verpasst").
  bool softMissed(DateTime now) {
    final s = softDeadline;
    return kind == ItemKind.deadline && s != null && !now.isBefore(s) && now.isBefore(start);
  }

  /// End used for layout: a point event still gets [minimum] of height.
  DateTime layoutEnd([Duration minimum = const Duration(minutes: 30)]) {
    final e = end;
    if (e == null || !e.isAfter(start)) return start.add(minimum);
    return e;
  }
}

/// Day key and day arithmetic on the UTC carrier.
DateTime dayOf(DateTime d) => DateTime.utc(d.year, d.month, d.day);
DateTime addDays(DateTime d, int n) => DateTime.utc(d.year, d.month, d.day + n);

/// Monday of the week containing [d].
DateTime weekStart(DateTime d) => addDays(dayOf(d), -(d.weekday - 1));
DateTime monthStart(DateTime d) => DateTime.utc(d.year, d.month);

/// Whole days between two days (DST-proof: UTC carrier).
int daysBetween(DateTime a, DateTime b) => dayOf(b).difference(dayOf(a)).inDays;

int monthsBetween(DateTime a, DateTime b) => (b.year - a.year) * 12 + b.month - a.month;

/// Supplies items for an inclusive day range. Implementations should be
/// cheap to call repeatedly (cache); the views call it on every page build.
abstract class CalendarItemSource {
  /// Items touching each day of [from, to] (keys are [dayOf] values).
  /// A timed item that crosses midnight is listed on every day it touches.
  Map<DateTime, List<CalendarItem>> itemsFor(DateTime from, DateTime to);
}

/// A source over a fixed list (tests, previews, later app answers).
class ListItemSource implements CalendarItemSource {
  ListItemSource(List<CalendarItem> items) {
    for (final i in items) {
      final first = dayOf(i.start);
      final last = i.allDay || i.end == null
          ? first
          : dayOf(i.end!.subtract(const Duration(microseconds: 1)));
      for (var d = first; !d.isAfter(last); d = addDays(d, 1)) {
        _byDay.putIfAbsent(d, () => []).add(i);
      }
    }
  }

  final Map<DateTime, List<CalendarItem>> _byDay = {};

  @override
  Map<DateTime, List<CalendarItem>> itemsFor(DateTime from, DateTime to) => {
        for (var d = dayOf(from); !d.isAfter(to); d = addDays(d, 1))
          if (_byDay[d] != null) d: _byDay[d]!,
      };
}
