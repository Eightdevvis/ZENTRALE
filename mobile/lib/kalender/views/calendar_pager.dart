// Swipe left/right through days, weeks or months. Virtualised: a
// PageView.builder builds only the visible page and its neighbours, each
// asks the source for just its own days (the source expands per month and
// caches). The vertical scroll position is shared between pages, so paging
// keeps the same hours in view; on first open the grid scrolls to now.

import 'package:flutter/material.dart';

import 'calendar_item.dart';
import 'month_grid.dart';
import 'time_grid.dart';
import 'view_mode.dart';

/// Pages either side of the start — far more than anyone swipes.
const _base = 100000;

class CalendarPager extends StatefulWidget {
  const CalendarPager({
    super.key,
    required this.mode,
    required this.focus,
    required this.source,
    required this.now,
    required this.onFocusChanged,
    this.onItemTap,
    this.onSlotTap,
    this.onDayOpen,
  }) : assert(mode != CalendarViewMode.agenda);

  final CalendarViewMode mode;

  /// The day in focus; its day/week/month is the page shown.
  final DateTime focus;
  final CalendarItemSource source;
  final DateTime now;
  final ValueChanged<DateTime> onFocusChanged;
  final ItemTap? onItemTap;
  final SlotTap? onSlotTap;

  /// Month cell or week header tapped: open that day.
  final ValueChanged<DateTime>? onDayOpen;

  @override
  State<CalendarPager> createState() => _CalendarPagerState();
}

/// First day of the page that contains [d] in [mode].
DateTime pageStart(CalendarViewMode mode, DateTime d) => switch (mode) {
      CalendarViewMode.week => weekStart(d),
      CalendarViewMode.month => monthStart(d),
      _ => dayOf(d),
    };

class _CalendarPagerState extends State<CalendarPager> {
  late DateTime _origin = pageStart(widget.mode, widget.now);
  late PageController _pages = PageController(initialPage: _indexOf(widget.focus));
  double? _offset; // shared vertical position of day/week grids

  int _indexOf(DateTime d) {
    final s = pageStart(widget.mode, d);
    return _base +
        switch (widget.mode) {
          CalendarViewMode.week => daysBetween(_origin, s) ~/ 7,
          CalendarViewMode.month => monthsBetween(_origin, s),
          _ => daysBetween(_origin, s),
        };
  }

  DateTime _startOf(int index) {
    final k = index - _base;
    return switch (widget.mode) {
      CalendarViewMode.week => addDays(_origin, 7 * k),
      CalendarViewMode.month => DateTime.utc(_origin.year, _origin.month + k),
      _ => addDays(_origin, k),
    };
  }

  @override
  void didUpdateWidget(CalendarPager old) {
    super.didUpdateWidget(old);
    if (old.mode != widget.mode) {
      _origin = pageStart(widget.mode, widget.now);
      _offset = null;
      _pages.dispose();
      _pages = PageController(initialPage: _indexOf(widget.focus));
      return;
    }
    final want = _indexOf(widget.focus);
    if (_pages.hasClients && (_pages.page?.round() ?? want) != want) {
      _pages.jumpToPage(want);
    }
  }

  @override
  void dispose() {
    _pages.dispose();
    super.dispose();
  }

  void _changed(int index) {
    final s = _startOf(index);
    final today = dayOf(widget.now);
    // Keep "today" in focus when its page comes back, else the page start.
    final f = pageStart(widget.mode, today) == s ? today : s;
    if (f != widget.focus) widget.onFocusChanged(f);
  }

  @override
  Widget build(BuildContext context) {
    return PageView.builder(
      key: ValueKey(widget.mode),
      controller: _pages,
      onPageChanged: _changed,
      itemBuilder: (context, index) {
        final s = _startOf(index);
        switch (widget.mode) {
          case CalendarViewMode.month:
            final days = monthGridDays(s);
            return MonthGrid(
              month: s,
              items: widget.source.itemsFor(days.first, days.last),
              now: widget.now,
              onDayTap: widget.onDayOpen,
              onItemTap: widget.onItemTap,
            );
          default:
            final n = widget.mode == CalendarViewMode.week ? 7 : 1;
            final days = [for (var i = 0; i < n; i++) addDays(s, i)];
            return _GridPage(
              key: ValueKey(s),
              initialOffset: () => _offset,
              onOffset: (o) => _offset = o,
              builder: (controller) => TimeGrid(
                days: days,
                items: widget.source.itemsFor(days.first, days.last),
                now: widget.now,
                controller: controller,
                compact: n > 1,
                onItemTap: widget.onItemTap,
                onSlotTap: widget.onSlotTap,
                onDayTap: n > 1 ? widget.onDayOpen : null,
              ),
              nowOffset: (hourHeight) => scrollOffsetFor(widget.now, hourHeight),
              hourHeight: n > 1 ? TimeGrid.weekHour : TimeGrid.dayHour,
            );
        }
      },
    );
  }
}

/// One grid page with its own scroll controller, starting where the last
/// page was (or at now).
class _GridPage extends StatefulWidget {
  const _GridPage({
    super.key,
    required this.initialOffset,
    required this.onOffset,
    required this.builder,
    required this.nowOffset,
    required this.hourHeight,
  });

  final double? Function() initialOffset;
  final ValueChanged<double> onOffset;
  final Widget Function(ScrollController) builder;
  final double Function(double hourHeight) nowOffset;
  final double hourHeight;

  @override
  State<_GridPage> createState() => _GridPageState();
}

class _GridPageState extends State<_GridPage> {
  late final ScrollController _c = ScrollController(
      initialScrollOffset: widget.initialOffset() ?? widget.nowOffset(widget.hourHeight))
    ..addListener(() => widget.onOffset(_c.offset));

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => widget.builder(_c);
}
