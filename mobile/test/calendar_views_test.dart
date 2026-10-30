// Calendar views (day, week, month, agenda): overlap layout, paging, mode
// switch, tap-to-create — and preview images of every view, day and night,
// into build/kalender_vorschau/ (not in the repo), so the look can be
// checked without building the phone app.

import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/eintrag_seite.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/kalender_seite.dart';
import 'package:zen_mobile/kalender/kalender_steuerung.dart';
import 'package:zen_mobile/kalender/views/calendar_item.dart';
import 'package:zen_mobile/kalender/views/calendar_pager.dart';
import 'package:zen_mobile/kalender/views/calendar_palette.dart';
import 'package:zen_mobile/kalender/views/calendar_source.dart';
import 'package:zen_mobile/kalender/views/month_grid.dart';
import 'package:zen_mobile/kalender/views/overlap_layout.dart';
import 'package:zen_mobile/kalender/views/view_mode.dart';
import 'package:zen_mobile/kalender/zeit.dart';
import 'package:zen_mobile/l10n/app_localizations.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/mitte.dart';
import 'package:zen_mobile/thema/farben.dart';
import 'vectors.dart';

// ── Synthetic week: Mon 16.11. … Sun 22.11.2026, now Thu 19.11. 10:20 ─────

final now = DateTime.utc(2026, 11, 19, 10, 20);
DateTime at(int day, int h, [int m = 0]) => DateTime.utc(2026, 11, day, h, m);

const blue = Color(0xFF3B82F6), orange = Color(0xFFF59E0B), purple = Color(0xFF8B5CF6);

CalendarItem ev(String id, String label, DateTime s, DateTime? e,
        {ItemKind kind = ItemKind.event, Color? color = blue, bool allDay = false, String? place,
        DateTime? soft, bool waiting = false}) =>
    CalendarItem(id: id, kind: kind, label: label, start: s, end: e, allDay: allDay, color: color,
        place: place, softDeadline: soft, waiting: waiting);

List<CalendarItem> synthetic() => [
      // Monday: three overlapping, one of them tentative
      ev('a', 'Planung', at(16, 9), at(16, 10, 30), place: 'Büro'),
      ev('b', 'Zahnarzt', at(16, 10), at(16, 11), color: orange, place: 'Dr. Lenz'),
      ev('c', 'Kaffee mit Jo?', at(16, 10, 15), at(16, 10, 45), kind: ItemKind.tentative, color: purple),
      ev('d', 'Messe', at(16, 0), null, allDay: true, color: orange),
      ev('d2', 'Messe', at(17, 0), null, allDay: true, color: orange),
      // Wednesday: tentative workshop under a committed appointment
      ev('e', 'Workshop', at(18, 14), at(18, 16, 30), kind: ItemKind.tentative, color: purple),
      ev('f', 'Arzt', at(18, 15), at(18, 16)),
      // Thursday (today): deadline with should time already passed
      ev('g', 'Steuererklärung', at(19, 12), null, kind: ItemKind.deadline, color: null, soft: at(19, 9)),
      ev('h', 'Anruf Mama', at(19, 18), null, waiting: true),
      ev('i', 'Geige', at(19, 17), at(19, 17, 45), color: purple),
      // Friday: all-day deadline, many all-day entries
      ev('j', 'Abgabe Bericht', at(20, 0), null, kind: ItemKind.deadline, color: null, allDay: true),
      ev('k', 'Urlaub Anna', at(20, 0), null, allDay: true),
      ev('l', 'Geburtstag Ben', at(20, 0), null, allDay: true, color: purple),
      ev('m', 'Müll raus', at(20, 0), null, allDay: true, color: orange),
      for (final (i, h) in [(0, 8), (1, 9), (2, 11), (3, 13), (4, 15)])
        ev('n$i', 'Termin $i', at(20, h), at(20, h + 1), color: i.isEven ? blue : orange),
      // Rhythm every day: sleep across midnight, lunch
      for (var d = 14; d <= 30; d++) ...[
        ev('s$d', 'Schlaf', at(d, 23), at(d + 1, 7), kind: ItemKind.rhythm, color: null),
        ev('l$d', 'Mittagessen', at(d, 12, 30), at(d, 13, 15), kind: ItemKind.rhythm, color: null),
      ],
      // A few more for the month
      ev('o', 'Chorprobe', at(4, 18), at(4, 20)),
      ev('p', 'Chorprobe', at(11, 18), at(11, 20)),
      ev('q', 'Chorprobe', at(25, 18), at(25, 20)),
      ev('r', 'Reise', at(26, 0), null, allDay: true, color: orange),
      ev('r2', 'Reise', at(27, 0), null, allDay: true, color: orange),
    ];

Widget app(Widget home, {bool night = false, Locale locale = const Locale('de')}) => MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: zentraleThema(night ? Brightness.dark : Brightness.light),
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    );

Future<void> loadFonts() async {
  final root = Platform.environment['FLUTTER_ROOT'] ?? '${Platform.environment['HOME']}/flutter';
  final dir = '$root/bin/cache/artifacts/material_fonts';
  Future<void> load(String family, List<String> files) async {
    final l = FontLoader(family);
    for (final f in files) {
      final file = File('$dir/$f');
      if (file.existsSync()) l.addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())));
    }
    await l.load();
  }

  await load('Roboto', ['Roboto-Regular.ttf', 'Roboto-Medium.ttf', 'Roboto-Bold.ttf', 'Roboto-Italic.ttf']);
  await load('MaterialIcons', ['MaterialIcons-Regular.otf']);
}

Future<void> snapshot(WidgetTester t, GlobalKey key, String name) async {
  final ro = t.renderObject<RenderRepaintBoundary>(find.byKey(key));
  await t.runAsync(() async {
    final img = await ro.toImage(pixelRatio: 2);
    final png = await img.toByteData(format: ui.ImageByteFormat.png);
    final f = File('build/kalender_vorschau/$name.png');
    await f.parent.create(recursive: true);
    await f.writeAsBytes(png!.buffer.asUint8List());
  });
}

Widget previewPage(CalendarViewMode mode, DateTime focus, String title, CalendarItemSource src) => Scaffold(
      appBar: AppBar(title: Text(title)),
      body: CalendarPager(
        mode: mode,
        focus: focus,
        source: src,
        now: now,
        onFocusChanged: (_) {},
      ),
    );

void phone(WidgetTester t) {
  t.view.physicalSize = const Size(400, 800);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

// ── The real calendar from the core's test vectors ──────────────────────────

final _v = jsonDecode(File(vectorPath('kalender_testvektoren.json')).readAsStringSync()) as Map<String, dynamic>;

Future<SpeicherAblage> vectorAblage() async {
  final m = SpeicherMitte();
  for (final MapEntry(:key, :value) in (_v['dateien'] as Map).entries) {
    m.rechnerSchreibt('data/$key', utf8.encode(value as String));
  }
  final a = SpeicherAblage();
  await Abgleich(a, m).laufen();
  return a;
}

Future<KalenderSteuerung> loadedSteuerung(WidgetTester t, DateTime clock) async {
  final s = KalenderSteuerung(ablage: await t.runAsync(vectorAblage) as SpeicherAblage, uhr: () => clock);
  await t.runAsync(s.laden);
  return s;
}

Future<void> settle(WidgetTester t) async {
  await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
  await t.pumpAndSettle();
}

void main() {
  setUpAll(zonenLaden);

  group('overlap layout', () {
    final day = DateTime.utc(2026, 11, 16);
    CalendarItem span(String id, int h1, int m1, int h2, int m2) =>
        ev(id, id, day.add(Duration(hours: h1, minutes: m1)), day.add(Duration(hours: h2, minutes: m2)));
    Map<String, (int, int, int)> cols(List<CalendarItem> l) =>
        {for (final p in layoutDay(day, l)) p.item.id: (p.column, p.span, p.columns)};

    test('separate events take the full width', () {
      expect(cols([span('a', 9, 0, 10, 0), span('b', 10, 0, 11, 0)]), {'a': (0, 1, 1), 'b': (0, 1, 1)});
    });

    test('two overlapping stand side by side', () {
      expect(cols([span('a', 9, 0, 10, 30), span('b', 10, 0, 11, 0)]), {'a': (0, 1, 2), 'b': (1, 1, 2)});
    });

    test('a column freed early is reused; a lone item grows right', () {
      // a 9–12 long, b 9–10, c 10:30–11 reuses b's column.
      final r = cols([span('a', 9, 0, 12, 0), span('b', 9, 0, 10, 0), span('c', 10, 30, 11, 0)]);
      expect(r['a'], (0, 1, 2));
      expect(r['b'], (1, 1, 2));
      expect(r['c'], (1, 1, 2));
      // three-way overlap in one cluster: x grows over the free third column
      final t3 = cols([
        span('x', 9, 0, 9, 30),
        span('y', 9, 0, 11, 0),
        span('z', 9, 0, 10, 0),
        span('w', 9, 45, 10, 30), // reuses x's column once x has ended
      ]);
      expect(t3, {'y': (0, 1, 3), 'z': (1, 1, 3), 'x': (2, 1, 3), 'w': (2, 1, 3)});
      final all = layoutDay(day, [span('a', 9, 0, 12, 0), span('b', 9, 0, 9, 30), span('c', 9, 0, 9, 30), span('d', 10, 0, 11, 0)]);
      final d = all.firstWhere((p) => p.item.id == 'd');
      // d starts after b and c ended: it takes column 1 and spreads over 1+2.
      expect((d.column, d.span, d.columns), (1, 2, 3));
    });

    test('longer first on equal start; point events get a minimum height', () {
      final l = layoutDay(day, [span('short', 9, 0, 9, 15), span('long', 9, 0, 11, 0)]);
      expect(l.firstWhere((p) => p.item.id == 'long').column, 0);
      final p = layoutDay(day, [ev('p', 'p', day.add(const Duration(hours: 18)), null)]).single;
      expect(p.end - p.start, 30);
    });

    test('items crossing midnight are clipped to the day', () {
      final s = ev('s', 's', DateTime.utc(2026, 11, 15, 23), DateTime.utc(2026, 11, 16, 7), kind: ItemKind.rhythm);
      final src = ListItemSource([s]);
      expect(src.itemsFor(DateTime.utc(2026, 11, 15), DateTime.utc(2026, 11, 17)).keys,
          [DateTime.utc(2026, 11, 15), DateTime.utc(2026, 11, 16)]);
      expect((minutesInDay(day, s.start), minutesInDay(day, s.end!)), (0, 420));
    });
  });

  test('palette: every text colour reaches 4.5:1 on its background', () {
    for (final night in [false, true]) {
      final p = CalendarPalette.forTheme(zentraleThema(night ? Brightness.dark : Brightness.light));
      expect(contrast(p.text, p.background), greaterThanOrEqualTo(4.5));
      expect(contrast(p.mutedText, p.background), greaterThanOrEqualTo(4.5), reason: 'muted night=$night');
      for (final c in [blue, orange, purple, p.eventDefault, p.tentativeDefault, p.rhythmDefault, p.warning,
        const Color(0xFFFFFF00), const Color(0xFF777777)]) {
        for (final bg in [p.eventFill(c), p.tentativeFill(c), p.rhythmBand(c), p.outsideMonth]) {
          expect(contrast(p.readableOn(bg, p.mutedText), bg), greaterThanOrEqualTo(4.5));
          expect(contrast(p.readableOn(bg), bg), greaterThanOrEqualTo(4.5));
        }
      }
    }
  });

  test('source expands per month and caches', () async {
    final k = await Kalender.laden(await vectorAblage());
    final src = KalenderItemSource(k);
    final a = src.itemsFor(DateTime.utc(2026, 11, 16), DateTime.utc(2026, 11, 22));
    expect(a.values.expand((x) => x).any((i) => i.label.contains('Steuererklärung')), isTrue);
    src.itemsFor(DateTime.utc(2026, 11, 1), DateTime.utc(2026, 11, 30));
    expect(src.expandedMonths, 1);
    src.itemsFor(DateTime.utc(2026, 11, 30), DateTime.utc(2026, 12, 6));
    expect(src.expandedMonths, 2);
    // Sleep across midnight: also on the following morning.
    final mornings = src.itemsFor(DateTime.utc(2026, 11, 17), DateTime.utc(2026, 11, 17)).values.single;
    expect(mornings.where((i) => i.kind == ItemKind.rhythm && dayOf(i.start) == DateTime.utc(2026, 11, 16)),
        isNotEmpty);
    expect(parseVdirColor('#3b82f6'), const Color(0xFF3B82F6));
    expect(parseVdirColor('blue'), isNull);
  });

  test('performance: 600 events incl. weekly rules, a year of month pages', () async {
    final a = SpeicherAblage();
    final b = StringBuffer();
    for (var i = 0; i < 600; i++) {
      final d = DateTime.utc(2026, 1, 1).add(Duration(days: i % 365, hours: 8 + i % 10));
      String f(DateTime x) =>
          '${x.year}${x.month.toString().padLeft(2, '0')}${x.day.toString().padLeft(2, '0')}T'
          '${x.hour.toString().padLeft(2, '0')}0000';
      b.write('BEGIN:VEVENT\r\nUID:p$i@zentrale\r\nSUMMARY:E$i\r\nDTSTART:${f(d)}\r\n'
          'DTEND:${f(d.add(const Duration(hours: 1)))}\r\n'
          '${i % 6 == 0 ? 'RRULE:FREQ=WEEKLY;BYDAY=MO,WE\r\n' : ''}END:VEVENT\r\n');
    }
    await a.schreiben('kalender/termine/big.ics',
        'BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:test\r\n${b}END:VCALENDAR\r\n');
    final k = await Kalender.laden(a);
    final src = KalenderItemSource(k);
    final sw = Stopwatch()..start();
    var n = 0;
    for (var m = 1; m <= 12; m++) {
      final days = monthGridDays(DateTime.utc(2026, m));
      n += src.itemsFor(days.first, days.last).values.fold(0, (s, l) => s + l.length);
    }
    final perMonth = sw.elapsedMilliseconds / 12;
    // ignore: avoid_print
    print('600 events: ${perMonth.toStringAsFixed(1)} ms per month page, $n items');
    expect(n, greaterThan(600));
    expect(perMonth, lessThan(150));
    // Cached: a week inside a known month costs nearly nothing.
    final sw2 = Stopwatch()..start();
    for (var i = 0; i < 100; i++) {
      src.itemsFor(DateTime.utc(2026, 12, 7), DateTime.utc(2026, 12, 13));
    }
    expect(sw2.elapsedMilliseconds, lessThan(50));
  });

  testWidgets('mode switch: week → month → day → agenda, remembered', (t) async {
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 19, 9));
    final mem = MemoryViewModeMemory();
    await t.pumpWidget(app(KalenderSeite(steuerung: s, viewMemory: mem)));
    await settle(t);
    expect(find.byType(CalendarPager), findsOneWidget);
    expect(find.textContaining('KW 47'), findsOneWidget);

    Future<void> pick(CalendarViewMode m) async {
      await t.tap(find.byKey(const ValueKey('calendar-mode')));
      await t.pumpAndSettle();
      await t.tap(find.byKey(ValueKey('calendar-mode-${m.name}')));
      await settle(t);
    }

    await pick(CalendarViewMode.month);
    expect(find.byType(MonthGrid), findsOneWidget);
    expect(find.text('November 2026'), findsOneWidget);
    expect(mem.mode, CalendarViewMode.month);
    // Tap a day in the month → that day's view.
    await t.tap(find.byKey(ValueKey('month-day-${DateTime.utc(2026, 11, 20).toIso8601String()}')));
    await settle(t);
    expect(find.textContaining('20. Nov'), findsOneWidget);
    await pick(CalendarViewMode.agenda);
    expect(find.text('Heute · 19.11.'), findsOneWidget);
    expect(mem.mode, CalendarViewMode.agenda);

    // A new page opens in the remembered mode.
    await t.pumpWidget(const SizedBox());
    await t.pumpWidget(app(KalenderSeite(steuerung: s, viewMemory: MemoryViewModeMemory(CalendarViewMode.day))));
    await settle(t);
    expect(find.textContaining('19. Nov'), findsOneWidget);
  });

  testWidgets('paging: swipe to next/previous day, "today" returns', (t) async {
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 19, 9));
    await t.pumpWidget(app(KalenderSeite(steuerung: s, initialMode: CalendarViewMode.day)));
    await settle(t);
    expect(find.textContaining('19. Nov'), findsOneWidget);
    await t.fling(find.byType(PageView), const Offset(-300, 0), 1000);
    await settle(t);
    expect(find.textContaining('20. Nov'), findsOneWidget);
    await t.fling(find.byType(PageView), const Offset(300, 0), 1000);
    await settle(t);
    await t.fling(find.byType(PageView), const Offset(300, 0), 1000);
    await settle(t);
    expect(find.textContaining('18. Nov'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('calendar-today')));
    await settle(t);
    expect(find.textContaining('19. Nov'), findsOneWidget);
  });

  testWidgets('week paging changes the week number', (t) async {
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 19, 9));
    await t.pumpWidget(app(KalenderSeite(steuerung: s, initialMode: CalendarViewMode.week)));
    await settle(t);
    await t.fling(find.byType(PageView), const Offset(-300, 0), 1000);
    await settle(t);
    expect(find.textContaining('KW 48'), findsOneWidget);
  });

  testWidgets('tap on an empty slot opens the form prefilled with day and time', (t) async {
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 19, 9));
    await t.pumpWidget(app(KalenderSeite(steuerung: s, initialMode: CalendarViewMode.day)));
    await settle(t);
    // The grid opens scrolled to now − 2 h (07:00 at the top); 07:00 + 3.5 h.
    final grid = t.getRect(find.byType(SingleChildScrollView).first);
    await t.tapAt(Offset(grid.left + 200, grid.top + 3.5 * TimeGridHours.day + 5));
    await settle(t);
    expect(find.byType(EintragSeite), findsOneWidget);
    expect(find.text('19.11.2026'), findsOneWidget);
    expect(find.text('Beginn 10:30'), findsOneWidget);
  });

  testWidgets('tap on an event opens its details', (t) async {
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 20, 8));
    await t.pumpWidget(app(KalenderSeite(steuerung: s, initialMode: CalendarViewMode.day)));
    await settle(t);
    final deadline = find.textContaining('Steuererklärung');
    expect(deadline, findsWidgets);
    await t.tap(deadline.first, warnIfMissed: false);
    await settle(t);
    expect(find.byType(BottomSheet), findsOneWidget);
  });

  // ── Preview images ────────────────────────────────────────────────────────

  for (final night in [false, true]) {
    final tag = night ? 'night' : 'day';
    testWidgets('preview images ($tag)', (t) async {
      await t.runAsync(loadFonts);
      phone(t);
      final src = ListItemSource(synthetic());
      final key = GlobalKey();
      Future<void> shot(CalendarViewMode mode, DateTime focus, String title, String name) async {
        await t.pumpWidget(RepaintBoundary(key: key, child: app(previewPage(mode, focus, title, src), night: night)));
        await t.pumpAndSettle();
        await snapshot(t, key, '${name}_$tag');
      }

      await shot(CalendarViewMode.week, now, 'Nov. 2026 · KW 47', 'week');
      await shot(CalendarViewMode.day, DateTime.utc(2026, 11, 16), 'Mo., 16. Nov.', 'day_overlaps');
      await shot(CalendarViewMode.day, now, 'Do., 19. Nov.', 'day_today');
      await shot(CalendarViewMode.day, DateTime.utc(2026, 11, 20), 'Fr., 20. Nov.', 'day_allday');
      await shot(CalendarViewMode.month, now, 'November 2026', 'month');
    });
  }

  testWidgets('preview image: the real page from the core vectors', (t) async {
    await t.runAsync(loadFonts);
    phone(t);
    final s = await loadedSteuerung(t, DateTime.utc(2026, 11, 19, 9, 40));
    final key = GlobalKey();
    for (final m in [CalendarViewMode.week, CalendarViewMode.month]) {
      await t.pumpWidget(RepaintBoundary(key: key, child: app(KalenderSeite(steuerung: s, initialMode: m))));
      await settle(t);
      await snapshot(t, key, 'page_${m.name}');
    }
  });
}

/// Hour height of the day view, for tap coordinates in tests.
abstract final class TimeGridHours {
  static const day = hourHeightDay;
}
