// Month view: six weeks of seven days, each cell with the day number and as
// many small chips as fit, then "+n". Tapping a day opens it. Pure layout
// layer like time_grid.dart — the rhythm (daily the same) is left out here.

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../l10n/app_localizations.dart';
import 'calendar_item.dart';
import 'calendar_palette.dart';
import 'time_grid.dart';

/// The 42 days shown for the month of [month] (Monday first).
List<DateTime> monthGridDays(DateTime month) {
  final first = weekStart(monthStart(month));
  return [for (var i = 0; i < 42; i++) addDays(first, i)];
}

/// Order inside a cell: all-day, then by start.
List<CalendarItem> monthCellItems(List<CalendarItem> l) => [
      for (final i in l)
        if (i.kind != ItemKind.rhythm && !i.switchedOff) i
    ]..sort((a, b) {
        if (a.allDay != b.allDay) return a.allDay ? -1 : 1;
        return a.start.compareTo(b.start);
      });

class MonthGrid extends StatelessWidget {
  const MonthGrid({
    super.key,
    required this.month,
    required this.items,
    required this.now,
    this.onDayTap,
    this.onItemTap,
  });

  final DateTime month;
  final Map<DateTime, List<CalendarItem>> items;
  final DateTime now;
  final ValueChanged<DateTime>? onDayTap;
  final ItemTap? onItemTap;

  static const _chipHeight = 16.0, _numberHeight = 22.0;

  @override
  Widget build(BuildContext context) {
    final p = CalendarPalette.of(context);
    final l = AppLocalizations.of(context);
    final days = monthGridDays(month);
    final today = dayOf(now);
    final weekday = DateFormat.E(Localizations.localeOf(context).toLanguageTag());
    return ColoredBox(
      color: p.background,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(children: [
            for (var i = 0; i < 7; i++)
              Expanded(
                child: Text(weekday.format(days[i]),
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600, color: p.mutedText)),
              ),
          ]),
        ),
        Expanded(
          child: LayoutBuilder(builder: (context, box) {
            final cellH = box.maxHeight / 6;
            final fit = ((cellH - _numberHeight - 2) / _chipHeight).floor().clamp(0, 6);
            return Column(children: [
              for (var r = 0; r < 6; r++)
                Expanded(
                  child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                    for (var c = 0; c < 7; c++)
                      Expanded(
                        child: _cell(context, days[r * 7 + c], today, fit, p, l),
                      ),
                  ]),
                ),
            ]);
          }),
        ),
      ]),
    );
  }

  Widget _cell(BuildContext context, DateTime d, DateTime today, int fit, CalendarPalette p, AppLocalizations l) {
    final inMonth = d.month == month.month;
    final list = monthCellItems(items[d] ?? const []);
    // Keep one row for "+n" if not everything fits.
    final shown = list.length <= fit ? list.length : (fit - 1).clamp(0, fit);
    final isToday = d == today;
    final bg = inMonth ? p.background : p.outsideMonth;
    return InkWell(
      key: ValueKey('month-day-${d.toIso8601String()}'),
      onTap: onDayTap == null ? null : () => onDayTap!(d),
      child: Container(
        decoration: BoxDecoration(
          color: bg,
          border: Border(
            top: BorderSide(color: p.hourLine, width: 1),
            left: BorderSide(color: p.gridLine, width: 1),
          ),
        ),
        padding: const EdgeInsets.fromLTRB(1, 2, 1, 1),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Center(
            child: Container(
              width: 20,
              height: 20,
              alignment: Alignment.center,
              decoration: isToday ? BoxDecoration(color: p.today, shape: BoxShape.circle) : null,
              child: Text('${d.day}',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: isToday ? FontWeight.w700 : FontWeight.w500,
                      color: isToday ? p.readableOn(p.today) : p.readableOn(bg, inMonth ? p.text : p.mutedText))),
            ),
          ),
          const SizedBox(height: 2),
          for (final i in list.take(shown))
            SizedBox(
              height: _chipHeight,
              child: itemChip(context, i, now, p, null, fontSize: minText),
            ),
          if (shown < list.length)
            Text(l.calendarMore(list.length - shown),
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: minText, color: p.readableOn(bg, p.mutedText))),
        ]),
      ),
    );
  }
}
