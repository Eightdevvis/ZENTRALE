// Day and week view: days side by side over a vertical grid of hours.
//
// Pure layout layer: takes days + items per day, draws them, reports taps.
// Drawing order per day column, bottom to top: rhythm bands (subtle, may
// cross midnight — each day draws its own slice), hour traces, tentative
// blocks (striped), committed blocks, deadline markers, the now line.
// Overlapping blocks stand side by side (overlap_layout.dart).

import 'package:flutter/material.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../../l10n/app_localizations.dart';
import 'calendar_item.dart';
import 'calendar_palette.dart';
import 'overlap_layout.dart';

typedef ItemTap = void Function(CalendarItem item);

/// [allDay] true = the all-day strip was tapped (time is midnight).
typedef SlotTap = void Function(DateTime at, {required bool allDay});

String hhmm(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

class TimeGrid extends StatelessWidget {
  const TimeGrid({
    super.key,
    required this.days,
    required this.items,
    required this.now,
    required this.controller,
    this.onItemTap,
    this.onSlotTap,
    this.onDayTap,
    this.compact = false,
  });

  final List<DateTime> days;
  final Map<DateTime, List<CalendarItem>> items;
  final DateTime now;
  final ScrollController controller;
  final ItemTap? onItemTap;
  final SlotTap? onSlotTap;

  /// Tap on a day's header (week view → open that day).
  final ValueChanged<DateTime>? onDayTap;

  /// Week view: narrower text, smaller hours.
  final bool compact;

  static const dayHour = hourHeightDay, weekHour = hourHeightWeek;

  double get hourHeight => compact ? hourHeightWeek : hourHeightDay;

  @override
  Widget build(BuildContext context) {
    final p = CalendarPalette.of(context);
    final allDay = {
      for (final d in days)
        d: [
          for (final i in items[d] ?? const <CalendarItem>[])
            if (i.allDay && i.kind != ItemKind.rhythm) i
        ]
    };
    return ColoredBox(
      color: p.background,
      child: Column(children: [
        _Header(days: days, now: now, palette: p, onDayTap: onDayTap),
        _AllDayStrip(days: days, items: allDay, now: now, palette: p, compact: compact,
            onItemTap: onItemTap, onSlotTap: onSlotTap),
        Container(height: 1, color: p.hourLine),
        Expanded(
          child: SingleChildScrollView(
            controller: controller,
            child: SizedBox(
              height: 24 * hourHeight,
              child: Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                SizedBox(
                  width: gutterWidth,
                  child: CustomPaint(painter: _GutterPainter(hourHeight, p, DefaultTextStyle.of(context).style)),
                ),
                for (final d in days)
                  Expanded(
                    child: _DayColumn(
                      key: ValueKey(d),
                      day: d,
                      items: items[d] ?? const [],
                      now: now,
                      hourHeight: hourHeight,
                      compact: compact,
                      palette: p,
                      onItemTap: onItemTap,
                      onSlotTap: onSlotTap,
                    ),
                  ),
              ]),
            ),
          ),
        ),
      ]),
    );
  }
}

/// Initial scroll offset so that [now] sits a bit below the top.
double scrollOffsetFor(DateTime now, double hourHeight) {
  final m = now.hour * 60 + now.minute - scrollBeforeNow.inMinutes;
  return (m < 0 ? 0 : m) / 60 * hourHeight;
}

// ── Header with weekday and date ────────────────────────────────────────────

class _Header extends StatelessWidget {
  const _Header({required this.days, required this.now, required this.palette, this.onDayTap});
  final List<DateTime> days;
  final DateTime now;
  final CalendarPalette palette;
  final ValueChanged<DateTime>? onDayTap;

  @override
  Widget build(BuildContext context) {
    final weekday = DateFormat.E(Localizations.localeOf(context).toLanguageTag());
    final today = dayOf(now);
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 4),
      child: Row(children: [
        const SizedBox(width: gutterWidth),
        for (final d in days)
          Expanded(
            child: InkWell(
              onTap: onDayTap == null ? null : () => onDayTap!(d),
              child: Column(children: [
                Text(weekday.format(d),
                    style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w600,
                        color: d == today ? palette.today : palette.mutedText)),
                const SizedBox(height: 2),
                Container(
                  width: 28,
                  height: 28,
                  alignment: Alignment.center,
                  decoration: d == today
                      ? BoxDecoration(color: palette.today, shape: BoxShape.circle)
                      : null,
                  child: Text('${d.day}',
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: d == today ? palette.readableOn(palette.today) : palette.text)),
                ),
              ]),
            ),
          ),
      ]),
    );
  }
}

// ── All-day strip (all-day entries, deadlines without a time) ───────────────

class _AllDayStrip extends StatelessWidget {
  const _AllDayStrip({
    required this.days,
    required this.items,
    required this.now,
    required this.palette,
    required this.compact,
    this.onItemTap,
    this.onSlotTap,
  });

  final List<DateTime> days;
  final Map<DateTime, List<CalendarItem>> items;
  final DateTime now;
  final CalendarPalette palette;
  final bool compact;
  final ItemTap? onItemTap;
  final SlotTap? onSlotTap;

  static const _maxRows = 3;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final rows = items.values.fold<int>(0, (m, x) => x.length > m ? x.length : m);
    if (rows == 0) return const SizedBox(height: 4);
    return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const SizedBox(width: gutterWidth),
      for (final d in days)
        Expanded(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: onSlotTap == null ? null : () => onSlotTap!(d, allDay: true),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 1, vertical: 2),
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                for (final i in items[d]!.take(_maxRows))
                  _Chip(item: i, now: now, palette: palette, onTap: onItemTap),
                if (items[d]!.length > _maxRows)
                  Text(l.calendarMore(items[d]!.length - _maxRows),
                      style: TextStyle(fontSize: minText, color: palette.mutedText)),
              ]),
            ),
          ),
        ),
    ]);
  }
}

/// A one-line chip (all-day strip, month cells).
class _Chip extends StatelessWidget {
  const _Chip({required this.item, required this.now, required this.palette, this.onTap});
  final CalendarItem item;
  final DateTime now;
  final CalendarPalette palette;
  final ItemTap? onTap;

  @override
  Widget build(BuildContext context) => itemChip(context, item, now, palette, onTap);
}

/// Shared with the month view.
Widget itemChip(BuildContext context, CalendarItem item, DateTime now, CalendarPalette p, ItemTap? onTap,
    {double fontSize = 11}) {
  final c = p.colorOf(item);
  final tentative = item.kind == ItemKind.tentative;
  final deadline = item.kind == ItemKind.deadline;
  final missed = item.softMissed(now);
  final fill = tentative || deadline ? p.tentativeFill(deadline ? p.warning : c) : p.eventFill(c);
  final fg = p.readableOn(fill, deadline ? p.warning : (tentative ? p.text : null));
  return GestureDetector(
    onTap: onTap == null ? null : () => onTap(item),
    child: Container(
      margin: const EdgeInsets.only(bottom: 2),
      padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
      decoration: BoxDecoration(
        color: fill,
        borderRadius: BorderRadius.circular(3),
        border: tentative || missed ? Border.all(color: missed ? p.warning : c, width: 1) : null,
      ),
      child: Text.rich(
          flagged(item.label, deadline, fontSize, fg),
          maxLines: 1,
          overflow: TextOverflow.clip,
          softWrap: false,
          style: TextStyle(
              fontSize: fontSize,
              height: 1.25,
              color: fg,
              fontWeight: deadline ? FontWeight.w600 : FontWeight.w500,
              fontStyle: tentative ? FontStyle.italic : FontStyle.normal)),
    ),
  );
}

/// [text] with a flag icon in front for deadlines (an icon, not a glyph:
/// not every font has ⚑).
InlineSpan flagged(String text, bool flag, double size, Color color) => TextSpan(children: [
      if (flag)
        WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: Padding(
            padding: const EdgeInsets.only(right: 2),
            child: Icon(Icons.flag, size: size + 1, color: color),
          ),
        ),
      TextSpan(text: text),
    ]);

// ── Hour labels ─────────────────────────────────────────────────────────────

class _GutterPainter extends CustomPainter {
  _GutterPainter(this.hourHeight, this.p, this.base);
  final double hourHeight;
  final CalendarPalette p;
  final TextStyle base;

  @override
  void paint(Canvas canvas, Size size) {
    for (var h = 1; h < 24; h++) {
      final tp = TextPainter(
        text: TextSpan(
            text: '${h.toString().padLeft(2, '0')}:00',
            style: base.copyWith(fontSize: minText, color: p.mutedText)),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(size.width - tp.width - 6, h * hourHeight - tp.height / 2));
    }
  }

  @override
  bool shouldRepaint(_GutterPainter old) => old.hourHeight != hourHeight || old.p != p;
}

// ── One day column ──────────────────────────────────────────────────────────

class _DayColumn extends StatelessWidget {
  const _DayColumn({
    super.key,
    required this.day,
    required this.items,
    required this.now,
    required this.hourHeight,
    required this.compact,
    required this.palette,
    this.onItemTap,
    this.onSlotTap,
  });

  final DateTime day;
  final List<CalendarItem> items;
  final DateTime now;
  final double hourHeight;
  final bool compact;
  final CalendarPalette palette;
  final ItemTap? onItemTap;
  final SlotTap? onSlotTap;

  double _y(int minutes) => minutes / 60 * hourHeight;

  @override
  Widget build(BuildContext context) {
    final p = palette;
    final rhythm = [for (final i in items) if (i.kind == ItemKind.rhythm && !i.allDay) i];
    final blocks = [
      for (final i in items)
        if (!i.allDay && (i.kind == ItemKind.event || i.kind == ItemKind.tentative)) i
    ];
    final deadlines = [for (final i in items) if (i.kind == ItemKind.deadline && !i.allDay) i];
    final placed = layoutDay(day, blocks, minMinutes: pointMinutes)
      // Tentative first = drawn beneath.
      ..sort((a, b) => (a.item.kind == ItemKind.tentative ? 0 : 1)
          .compareTo(b.item.kind == ItemKind.tentative ? 0 : 1));
    final bands = [
      for (final r in rhythm)
        (r, minutesInDay(day, r.start), minutesInDay(day, r.layoutEnd()))
    ];
    final isToday = dayOf(now) == day;

    return LayoutBuilder(builder: (context, box) {
      final w = box.maxWidth;
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTapUp: onSlotTap == null
            ? null
            : (d) {
                final m = (d.localPosition.dy / hourHeight * 60) ~/ slotMinutes * slotMinutes;
                onSlotTap!(day.add(Duration(minutes: m.clamp(0, 24 * 60 - slotMinutes))), allDay: false);
              },
        child: Stack(clipBehavior: Clip.hardEdge, children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _GridPainter(
                hourHeight: hourHeight,
                palette: p,
                bands: [for (final (r, s, e) in bands) (p.rhythmBand(p.colorOf(r)), s, e)],
              ),
            ),
          ),
          // Rhythm labels: small, at the top of each band's slice.
          for (final (r, s, e) in bands)
            if (!compact && _y(e) - _y(s) >= 14)
              Positioned(
                top: _y(s) + 1,
                left: 3,
                right: 2,
                child: IgnorePointer(
                  child: Text(
                    r.label,
                    maxLines: 1,
                    overflow: TextOverflow.clip,
                    softWrap: false,
                    style: TextStyle(
                        fontSize: minText,
                        color: p.readableOn(p.rhythmBand(p.colorOf(r)), p.mutedText)),
                  ),
                ),
              ),
          for (final b in placed)
            Positioned(
              key: ValueKey(b.item.id),
              top: _y(b.start) + 1,
              height: (_y(b.end) - _y(b.start) - 2).clamp(14, double.infinity),
              left: b.left * w + 1,
              width: b.width * w - 2,
              child: _Block(item: b.item, palette: p, compact: compact, onTap: onItemTap),
            ),
          for (final dl in deadlines) ..._deadline(context, dl, w),
          if (isToday)
            Positioned(
              top: _y(minutesInDay(day, now)) - 4,
              left: 0,
              right: 0,
              height: 8,
              child: IgnorePointer(child: CustomPaint(painter: _NowPainter(p.now))),
            ),
        ]),
      );
    });
  }

  /// Must line (solid, flag + label) and, on its day, the should line (dashed).
  List<Widget> _deadline(BuildContext context, CalendarItem d, double w) {
    final l = AppLocalizations.of(context);
    final p = palette;
    final missed = d.softMissed(now);
    final out = <Widget>[];
    final soft = d.softDeadline;
    if (soft != null && dayOf(soft) == day) {
      out.add(Positioned(
        top: _y(minutesInDay(day, soft)) - 1,
        left: 0,
        right: 0,
        height: 14,
        child: IgnorePointer(
          child: Stack(children: [
            Positioned(
                top: 0, left: 0, right: 0, height: 2,
                child: CustomPaint(painter: _DashPainter(missed ? p.warning : p.mutedText))),
            Positioned(
              top: 2,
              left: 3,
              right: 2,
              child: Text(l.calendarDeadlineShould(d.label),
                  maxLines: 1,
                  overflow: TextOverflow.clip,
                  softWrap: false,
                  style: TextStyle(
                      fontSize: minText, color: missed ? p.warning : p.mutedText, fontWeight: FontWeight.w600)),
            ),
          ]),
        ),
      ));
    }
    if (dayOf(d.start) == day) {
      final label = compact
          ? d.label
          : '${d.label} · ${l.calendarDeadlineMust(hhmm(d.start))}'
              '${missed ? ' · ${l.calendarDeadlineShouldMissed}' : ''}';
      out.add(Positioned(
        top: _y(minutesInDay(day, d.start)) - 1,
        left: 0,
        right: 0,
        height: 18,
        child: GestureDetector(
          onTap: onItemTap == null ? null : () => onItemTap!(d),
          child: Stack(children: [
            Positioned(top: 0, left: 0, right: 0, height: 2, child: ColoredBox(color: p.warning)),
            Positioned(
              top: 2,
              left: 0,
              child: Container(
                constraints: BoxConstraints(maxWidth: w),
                padding: const EdgeInsets.symmetric(horizontal: 3, vertical: 1),
                decoration: BoxDecoration(
                  color: p.warning,
                  borderRadius: const BorderRadius.only(bottomRight: Radius.circular(4)),
                ),
                child: Text.rich(flagged(label, true, compact ? minText : 11, p.readableOn(p.warning)),
                    maxLines: 1,
                    overflow: TextOverflow.clip,
                    softWrap: false,
                    style: TextStyle(
                        fontSize: compact ? minText : 11,
                        fontWeight: FontWeight.w600,
                        color: p.readableOn(p.warning))),
              ),
            ),
          ]),
        ),
      ));
    }
    return out;
  }
}

class _Block extends StatelessWidget {
  const _Block({required this.item, required this.palette, required this.compact, this.onTap});
  final CalendarItem item;
  final CalendarPalette palette;
  final bool compact;
  final ItemTap? onTap;

  @override
  Widget build(BuildContext context) {
    final p = palette;
    final c = p.colorOf(item);
    final tentative = item.kind == ItemKind.tentative;
    final fill = tentative ? p.tentativeFill(c) : p.eventFill(c);
    final fg = p.readableOn(fill, tentative ? p.text : null);
    final small = TextStyle(fontSize: compact ? minText : 11, color: fg, height: 1.2);
    final end = item.end;
    final time = end == null ? hhmm(item.start) : '${hhmm(item.start)}–${hhmm(end)}';
    return GestureDetector(
      onTap: onTap == null ? null : () => onTap!(item),
      child: CustomPaint(
        painter: tentative ? _StripePainter(Color.lerp(fill, c, .35)!) : null,
        child: Container(
          padding: EdgeInsets.symmetric(horizontal: compact ? 2 : 4, vertical: 1),
          decoration: BoxDecoration(
            color: tentative ? null : fill,
            borderRadius: BorderRadius.circular(4),
            border: tentative
                ? Border.all(color: c, width: 1)
                : Border(left: BorderSide(color: Color.lerp(c, p.text, .25)!, width: 2)),
          ),
          child: LayoutBuilder(builder: (context, box) {
            final roomy = box.maxHeight >= 34;
            // Narrow blocks would break words letter by letter: one clipped line.
            final wrap = box.maxWidth >= 44;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(children: [
                  if (item.waiting)
                    Padding(
                      padding: const EdgeInsets.only(right: 2),
                      child: Icon(Icons.cloud_upload_outlined, size: 11, color: fg),
                    ),
                  Expanded(
                    child: Text(item.label,
                        maxLines: roomy && compact && wrap ? 3 : 1,
                        softWrap: wrap,
                        overflow: TextOverflow.clip,
                        style: TextStyle(
                            fontSize: compact ? 11 : 12,
                            height: 1.2,
                            fontWeight: FontWeight.w600,
                            color: fg,
                            fontStyle: tentative ? FontStyle.italic : FontStyle.normal)),
                  ),
                ]),
                if (roomy && !compact) Text(time, maxLines: 1, overflow: TextOverflow.clip, style: small),
                if (roomy && !compact && item.place != null)
                  Text(item.place!, maxLines: 1, overflow: TextOverflow.ellipsis, style: small),
              ],
            );
          }),
        ),
      ),
    );
  }
}

// ── Painters ────────────────────────────────────────────────────────────────

class _GridPainter extends CustomPainter {
  _GridPainter({required this.hourHeight, required this.palette, required this.bands});
  final double hourHeight;
  final CalendarPalette palette;
  final List<(Color, int, int)> bands;

  @override
  void paint(Canvas canvas, Size size) {
    for (final (c, s, e) in bands) {
      canvas.drawRect(Rect.fromLTRB(0, s / 60 * hourHeight, size.width, e / 60 * hourHeight), Paint()..color = c);
    }
    final hour = Paint()
      ..color = palette.hourLine
      ..strokeWidth = 1;
    final half = Paint()
      ..color = palette.gridLine
      ..strokeWidth = 1;
    final pad = Paint()..color = palette.pad;
    for (var h = 0; h < 24; h++) {
      final y = h * hourHeight + .5;
      if (h > 0) canvas.drawLine(Offset(0, y), Offset(size.width, y), hour);
      // A solder pad where the trace leaves the column edge — the PCB hint.
      if (h > 0) canvas.drawCircle(Offset(0, y), 1.6, pad);
      final yh = y + hourHeight / 2;
      for (var x = 0.0; x < size.width; x += 6) {
        canvas.drawLine(Offset(x, yh), Offset(x + 2, yh), half);
      }
    }
    canvas.drawLine(Offset(.5, 0), Offset(.5, size.height), half);
  }

  @override
  bool shouldRepaint(_GridPainter old) =>
      old.hourHeight != hourHeight || old.palette != palette || old.bands.length != bands.length;
}

class _StripePainter extends CustomPainter {
  _StripePainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final r = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(4));
    canvas.save();
    canvas.clipRRect(r);
    canvas.drawRRect(r, Paint()..color = Color.lerp(color, Colors.transparent, .55)!);
    final s = Paint()
      ..color = color
      ..strokeWidth = 2;
    for (var x = -size.height; x < size.width; x += 8) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), s);
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(_StripePainter old) => old.color != color;
}

class _DashPainter extends CustomPainter {
  _DashPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()
      ..color = color
      ..strokeWidth = 1.5;
    for (var x = 0.0; x < size.width; x += 7) {
      canvas.drawLine(Offset(x, 1), Offset(x + 4, 1), p);
    }
  }

  @override
  bool shouldRepaint(_DashPainter old) => old.color != color;
}

/// The now line: a trace with a pad at its start.
class _NowPainter extends CustomPainter {
  _NowPainter(this.color);
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final y = size.height / 2;
    final p = Paint()
      ..color = color
      ..strokeWidth = 2;
    canvas.drawLine(Offset(0, y), Offset(size.width, y), p);
    canvas.drawCircle(Offset(3, y), 4, p);
  }

  @override
  bool shouldRepaint(_NowPainter old) => old.color != color;
}
