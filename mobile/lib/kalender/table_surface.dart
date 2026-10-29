// The calendar as one big spread on the table, seen through the peephole:
// weeks as rows, days as columns, the events written into each day.
//
// Built only from the occurrences (Kalender.vorkommen) — no sync, no crypto.
// Same weights as the list page: committed events full, "maybe" quieter and
// italic, rhythm (sleep, meals) as one faint line per day, deadlines ⚑ in the
// warning colour.

import 'package:flutter/painting.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../l10n/app_localizations.dart';
import '../peephole/peephole_surface.dart';
import '../peephole/peephole_tuning.dart';
import 'kalender.dart';
import 'regel.dart';

// ── Layout of the spread (surface units) ────────────────────────────────────

/// Weeks shown: the current one and the following ones.
const tableWeeks = 6;

/// Day cell size, gutter for the week label, inner padding.
const tableCellWidth = 200.0, tableCellHeight = 212.0, tableGutter = 54.0, tablePad = 10.0;

/// Text sizes (surface units) and the height of one event line.
const tableHeaderSize = 15.0, tableEventSize = 13.0, tableTimeSize = 11.5, tableLineHeight = 21.0;

/// Width reserved for the time in front of an event.
const tableTimeWidth = 42.0;

class CalendarTableSurface extends PeepholeSurface {
  CalendarTableSurface({
    required this.calendar,
    required this.today,
    required this.layerColor,
    required this.strings,
    this.locale = 'de',
  }) : start = _monday(today),
       _days = calendar.vorkommen(_monday(today), _monday(today).add(const Duration(days: tableWeeks * 7 - 1)));

  final Kalender calendar;

  /// Today (UTC-carrier day like everywhere in lib/kalender).
  final DateTime today;

  /// Colour of a layer (ebene) — from the vdir colour or the eye palette.
  final Color Function(String layer) layerColor;
  final AppLocalizations strings;
  final String locale;

  /// Monday of the first row.
  final DateTime start;
  final Map<String, List<Vorkommen>> _days;
  final _text = <String, TextPainter>{};

  static DateTime _monday(DateTime d) => tagVon(d).subtract(Duration(days: d.weekday - 1));

  @override
  Size get size => const Size(tableGutter + 7 * tableCellWidth, tableWeeks * tableCellHeight);

  @override
  double get comfortableViewWidth => tableCellWidth * 1.9;

  @override
  Offset get home => _cell(today).center;

  Rect _cell(DateTime day) {
    final i = tagVon(day).difference(start).inDays;
    return Rect.fromLTWH(
      tableGutter + (i % 7) * tableCellWidth,
      (i ~/ 7) * tableCellHeight,
      tableCellWidth,
      tableCellHeight,
    );
  }

  DateTime _dayAt(int row, int col) => start.add(Duration(days: row * 7 + col));

  /// Shown occurrences of a day, rhythm separated.
  (List<Vorkommen>, List<Vorkommen>) _of(DateTime day) {
    final all = [
      for (final v in _days[isoTag(day)] ?? const <Vorkommen>[])
        if (!v.versteckt) v,
    ];
    return (
      [
        for (final v in all)
          if (v.ebene != ebeneRhythmus) v,
      ],
      [
        for (final v in all)
          if (v.ebene == ebeneRhythmus) v,
      ],
    );
  }

  int _linesFit() => ((tableCellHeight - tablePad * 2 - 28 - 20) / tableLineHeight).floor();

  TextPainter _tp(String s, TextStyle st, double maxWidth, {int lines = 1}) {
    final key =
        '$s|${st.fontFamily}|${st.fontSize}|${st.color?.toARGB32()}|${st.fontWeight}|${st.fontStyle}|$maxWidth|$lines';
    return _text.putIfAbsent(
      key,
      () => TextPainter(
        text: TextSpan(text: s, style: st),
        textDirection: TextDirection.ltr,
        maxLines: lines,
        ellipsis: '…',
      )..layout(maxWidth: maxWidth),
    );
  }

  String _time(Vorkommen v) => v.zeit ?? strings.calendarTableAllDay;

  @override
  void paint(Canvas canvas, Rect visible, PeepholeStyle style) {
    final eye = style.eye;
    final text = PeepholeSurface.textVisible(tableEventSize, style, minTextPixels);
    final headerText = PeepholeSurface.textVisible(tableHeaderSize, style, minTextPixels);
    final line = Paint()
      ..color = eye.falte.withValues(alpha: style.night ? .30 : .38)
      ..strokeWidth = 1 / style.scale;
    final dateFmt = DateFormat.MEd(locale);
    final todayIdx = tagVon(today).difference(start).inDays;

    for (var row = 0; row < tableWeeks; row++) {
      final y = row * tableCellHeight;
      if (y > visible.bottom || y + tableCellHeight < visible.top) continue;
      // Week label in the gutter.
      if (headerText) {
        final week = _isoWeek(_dayAt(row, 0));
        final tp = _tp(
          strings.calendarWeekNumber(week),
          TextStyle(
            fontFamily: style.fontFamily,
            fontSize: tableTimeSize,
            color: style.inkMuted,
            fontWeight: FontWeight.w600,
          ),
          tableGutter - 8,
        );
        tp.paint(canvas, Offset(8, y + tablePad + 2));
      }
      canvas.drawLine(Offset(0, y), Offset(size.width, y), line);

      for (var col = 0; col < 7; col++) {
        final day = _dayAt(row, col);
        final cell = _cell(day);
        if (!cell.overlaps(visible)) continue;
        final idx = row * 7 + col;
        final isToday = idx == todayIdx;
        if (col >= 5) {
          canvas.drawRect(cell, Paint()..color = eye.lid.withValues(alpha: style.night ? .10 : .16));
        }
        canvas.drawLine(cell.topLeft, cell.bottomLeft, line);

        // Header: date (and "today").
        final inner = cell.deflate(tablePad);
        if (headerText) {
          final label = isToday ? '${strings.calendarTableToday} · ${dateFmt.format(day)}' : dateFmt.format(day);
          _tp(
            label,
            TextStyle(
              fontFamily: style.fontFamily,
              fontSize: tableHeaderSize,
              color: isToday ? eye.rand : style.ink,
              fontWeight: isToday ? FontWeight.w700 : FontWeight.w600,
            ),
            inner.width,
          ).paint(canvas, inner.topLeft);
        }

        final (events, rhythm) = _of(day);
        final fit = _linesFit();
        var ey = inner.top + 28;
        for (var i = 0; i < events.length && i < fit; i++) {
          final v = events[i];
          final maybe = v.ebene == ebeneVielleicht;
          final color = layerColor(v.ebene);
          if (text && i == fit - 1 && events.length > fit) {
            _tp(
              strings.calendarTableMore(events.length - i),
              TextStyle(fontFamily: style.fontFamily, fontSize: tableTimeSize, color: style.inkMuted),
              inner.width - 8,
            ).paint(canvas, Offset(inner.left + 8, ey + 3));
            break;
          }
          final bar = Rect.fromLTWH(inner.left, ey + 3, 3, tableLineHeight - 6);
          if (maybe) {
            canvas.drawRect(
              bar.deflate(.5),
              Paint()
                ..style = PaintingStyle.stroke
                ..strokeWidth = 1
                ..color = color,
            );
          } else {
            canvas.drawRect(bar, Paint()..color = color);
          }
          if (text) {
            _tp(
              _time(v),
              TextStyle(fontFamily: style.fontFamily, fontSize: tableTimeSize, color: style.inkMuted),
              tableTimeWidth - 4,
            ).paint(canvas, Offset(inner.left + 8, ey + 3.5));
            _tp(
              v.deadline ? '⚑ ${v.label}' : v.label,
              TextStyle(
                fontFamily: style.fontFamily,
                fontSize: tableEventSize,
                fontStyle: maybe ? FontStyle.italic : FontStyle.normal,
                color: v.deadline ? style.warning : (maybe ? style.inkMuted : style.ink),
              ),
              inner.width - 8 - tableTimeWidth,
            ).paint(canvas, Offset(inner.left + 8 + tableTimeWidth, ey + 2));
          } else {
            // Far out: just show how full the day is.
            canvas.drawRect(
              Rect.fromLTWH(inner.left + 8, ey + 7, inner.width * .7, tableLineHeight - 12),
              Paint()..color = color.withValues(alpha: maybe ? .35 : .6),
            );
          }
          ey += tableLineHeight;
        }

        if (rhythm.isNotEmpty) {
          final ry = inner.bottom - 16;
          final rc = layerColor(ebeneRhythmus);
          if (PeepholeSurface.textVisible(tableTimeSize, style, minTextPixels)) {
            final s = rhythm.map((v) => '${v.label} ${v.zeit ?? ''}${v.ende != null ? '–${v.ende}' : ''}').join(' · ');
            _tp(
              '≈ $s',
              TextStyle(fontFamily: style.fontFamily, fontSize: tableTimeSize, color: style.inkMuted),
              inner.width,
            ).paint(canvas, Offset(inner.left, ry));
          } else {
            canvas.drawRect(
              Rect.fromLTWH(inner.left, ry + 4, inner.width, 4),
              Paint()..color = rc.withValues(alpha: .4),
            );
          }
        }

        if (idx < todayIdx) {
          canvas.drawRect(cell, Paint()..color = style.sheet.withValues(alpha: .42)); // past: quieter
        }
        if (isToday) {
          canvas.drawRRect(
            RRect.fromRectAndRadius(cell.deflate(2.5), const Radius.circular(6)),
            Paint()
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2.2
              ..color = eye.iris,
          );
        }
      }
    }

    if (calendar.istLeer && headerText) {
      _tp(
        strings.calendarTableEmpty,
        TextStyle(fontFamily: style.fontFamily, fontSize: tableHeaderSize, color: style.inkMuted),
        tableCellWidth * 2,
      ).paint(canvas, _cell(today).bottomLeft + const Offset(tablePad, -60));
    }
  }

  @override
  PeepholeHit? hitTest(Offset point) {
    final p = point;
    if (p.dx < tableGutter || p.dy < 0) return null;
    final col = ((p.dx - tableGutter) / tableCellWidth).floor(), row = (p.dy / tableCellHeight).floor();
    if (col > 6 || row >= tableWeeks) return null;
    final day = _dayAt(row, col);
    final inner = _cell(day).deflate(tablePad);
    final i = ((p.dy - inner.top - 28) / tableLineHeight).floor();
    final (events, _) = _of(day);
    if (i < 0 || i >= events.length || i >= _linesFit()) return null;
    final v = events[i];
    final when =
        '${DateFormat.yMEd(locale).format(day)} · ${_time(v)}${v.ende != null && v.zeit != null ? '–${v.ende}' : ''}';
    final layer = calendar.ebene(v.ebene)?.titel ?? v.ebene;
    return PeepholeHit(
      title: v.label,
      detail: [when, layer, ?v.ort, if (v.wartet) strings.calendarWaitingForSync].join(' · '),
      payload: v,
    );
  }
}

/// ISO 8601 week number.
int _isoWeek(DateTime d) {
  final day = DateTime.utc(d.year, d.month, d.day);
  final thursday = day.add(Duration(days: 4 - day.weekday));
  final jan1 = DateTime.utc(thursday.year, 1, 1);
  return thursday.difference(jan1).inDays ~/ 7 + 1;
}
