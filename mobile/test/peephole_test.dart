// The peephole: motion → window mapping with synthetic sensor streams
// (steady, drift, tilt sweeps in different postures, gaps), window math
// (glide, clamp, zoom, recenter), the view with a fake sensor source and a
// demo surface, the calendar table — and preview PNGs into
// build/peephole_preview/ (not in the repo).

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/kalender_seite.dart';
import 'package:zen_mobile/kalender/kalender_steuerung.dart';
import 'package:zen_mobile/kalender/regel.dart';
import 'package:zen_mobile/kalender/table_page.dart';
import 'package:zen_mobile/kalender/table_surface.dart';
import 'package:zen_mobile/kalender/zeit.dart';
import 'package:zen_mobile/l10n/app_localizations.dart';
import 'package:zen_mobile/l10n/app_localizations_de.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/mitte.dart';
import 'package:zen_mobile/peephole/motion.dart';
import 'package:zen_mobile/peephole/peephole_controller.dart';
import 'package:zen_mobile/peephole/peephole_surface.dart';
import 'package:zen_mobile/peephole/peephole_tuning.dart';
import 'package:zen_mobile/peephole/peephole_view.dart';
import 'package:zen_mobile/thema/farben.dart';

// ── Synthetic sensors ───────────────────────────────────────────────────────

/// A phone in the hand: keeps its true "up" vector (device frame), turns by
/// the given rate, and reports gyroscope (+ bias, + noise) and accelerometer
/// readings that match.
class SimPhone {
  SimPhone({Vec3 up = const Vec3(0, 0, 1), this.bias = Vec3.zero, this.noise = 0, int seed = 1})
    : _up = up.normalized(),
      _rnd = math.Random(seed);
  Vec3 _up;
  final Vec3 bias;
  final double noise;
  final math.Random _rnd;
  var _t = Duration.zero;

  double _n() => (_rnd.nextDouble() * 2 - 1) * noise;

  /// Samples at [hz] for [seconds] while turning at [rate] (rad/s, device frame).
  Iterable<MotionSample> turn(Vec3 rate, double seconds, {int hz = 100}) sync* {
    final dt = 1 / hz;
    for (var i = 0; i < (seconds * hz).round(); i++) {
      _up = (_up + _up.cross(rate) * dt).normalized();
      _t += Duration(microseconds: (dt * 1e6).round());
      yield MotionSample(
        time: _t,
        gyro: rate + bias + Vec3(_n(), _n(), _n()),
        accel: _up * gravity + Vec3(_n(), _n(), _n()) * 20,
      );
    }
  }

  Iterable<MotionSample> still(double seconds) => turn(Vec3.zero, seconds);

  /// Jump the clock (app was paused).
  void gap(Duration d) => _t += d;
}

Offset feed(MotionMapper m, Iterable<MotionSample> s) => s.fold(Offset.zero, (sum, x) => sum + m.update(x));

/// Expected pan for a turn of [rate] rad/s during [seconds].
double expected(double rate, double seconds) => (rate - deadZoneRate) * panPixelsPerRadian * seconds;

// ── A demo surface: how any app plugs into the peephole ─────────────────────

/// 10 × 10 tiles, each tappable. This is all an app has to provide.
class TileDemoSurface extends PeepholeSurface {
  @override
  Size get size => const Size(1000, 1000);
  @override
  double get comfortableViewWidth => 300;
  @override
  Offset get home => const Offset(500, 500);

  @override
  void paint(Canvas canvas, Rect visible, PeepholeStyle style) {
    for (var i = 0; i < 10; i++) {
      for (var j = 0; j < 10; j++) {
        final r = Rect.fromLTWH(i * 100 + 8, j * 100 + 8, 84, 84);
        if (!r.overlaps(visible)) continue;
        canvas.drawRRect(
          RRect.fromRectAndRadius(r, const Radius.circular(8)),
          Paint()..color = ((i + j).isEven ? style.eye.iris : style.eye.lid).withValues(alpha: .6),
        );
      }
    }
  }

  @override
  PeepholeHit? hitTest(Offset point) =>
      (Offset.zero & size).contains(point) ? PeepholeHit(title: 'tile ${point.dx ~/ 100},${point.dy ~/ 100}') : null;
}

class FakeMotion implements MotionSource {
  final controller = StreamController<MotionSample>.broadcast();
  var listened = 0;
  @override
  Stream<MotionSample> samples() {
    listened++;
    return controller.stream;
  }
}

class BrokenMotion implements MotionSource {
  @override
  Stream<MotionSample> samples() => Stream.error(PlatformException(code: 'NO_SENSOR'));
}

/// Real frames (the glide integrates per frame).
Future<void> frames(WidgetTester t, int ms) async {
  for (var i = 0; i < ms ~/ 16; i++) {
    await t.pump(const Duration(milliseconds: 16));
  }
}

Widget app(Widget home, {bool night = false}) => MaterialApp(
  theme: zentraleThema(night ? Brightness.dark : Brightness.light),
  localizationsDelegates: AppLocalizations.localizationsDelegates,
  supportedLocales: AppLocalizations.supportedLocales,
  locale: const Locale('de'),
  home: home,
);

// ── Calendar data (same vectors as kalender_app_test) ───────────────────────

final _v = jsonDecode(File('test/daten/kalender_testvektoren.json').readAsStringSync()) as Map<String, dynamic>;

Future<SpeicherAblage> _ablage() async {
  final m = SpeicherMitte();
  for (final MapEntry(:key, :value) in (_v['dateien'] as Map).entries) {
    m.rechnerSchreibt('data/$key', utf8.encode(value as String));
  }
  final a = SpeicherAblage();
  await Abgleich(a, m).laufen();
  return a;
}

Future<void> _fonts() async {
  // Real glyphs for the preview PNGs (the test font draws boxes).
  final dir = Directory(
    '${Platform.environment['FLUTTER_ROOT'] ?? '${Platform.environment['HOME']}/flutter'}'
    '/bin/cache/artifacts/material_fonts',
  );
  if (!dir.existsSync()) return;
  for (final family in ['Roboto']) {
    final l = FontLoader(family);
    for (final f in ['Roboto-Regular.ttf', 'Roboto-Bold.ttf', 'Roboto-Italic.ttf', 'Roboto-Medium.ttf']) {
      final file = File('${dir.path}/$f');
      if (file.existsSync()) l.addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())));
    }
    await l.load();
  }
}

void main() {
  setUpAll(() async {
    zonenLaden();
    await initializeDateFormatting('de');
  });

  group('motion → window', () {
    test('steady hand: noise and tremor move nothing', () {
      final m = MotionMapper();
      final p = SimPhone(noise: .006);
      final d = feed(m, p.still(5));
      expect(d.distance, lessThan(2));
    });

    test('drift: a gyroscope bias above the dead zone is learnt away', () {
      final m = MotionMapper();
      final p = SimPhone(bias: const Vec3(.012, -.01, .04), noise: .003);
      final first = feed(m, p.still(1));
      final rest = feed(m, p.still(19));
      // Without learning: (0.04 - dead zone) * 780 px/rad * 20 s ≈ 234 px.
      expect(first.distance + rest.distance, lessThan(25));
      expect(m.bias.z, closeTo(.04, .006));
      // The learnt bias doesn't swallow a real turn afterwards.
      final turn = feed(m, p.turn(const Vec3(0, 0, -.5), 1));
      expect(turn.dx, closeTo(expected(.5, 1), 25));
    });

    test('lying flat: turning right pans right, turning left pans left', () {
      final m = MotionMapper();
      final p = SimPhone();
      feed(m, p.still(.1));
      final right = feed(m, p.turn(const Vec3(0, 0, -.52), 1)); // clockwise seen from above
      expect(right.dx, closeTo(expected(.52, 1), 8));
      expect(right.dy.abs(), lessThan(3));
      final left = feed(m, p.turn(const Vec3(0, 0, .52), 1));
      expect(left.dx, closeTo(-expected(.52, 1), 8));
    });

    test('top edge up pans further up the table, down comes back', () {
      final m = MotionMapper();
      final p = SimPhone();
      feed(m, p.still(.1));
      final up = feed(m, p.turn(const Vec3(.5, 0, 0), .5));
      expect(up.dy, closeTo(-expected(.5, .5), 8));
      expect(up.dx.abs(), lessThan(3));
      final down = feed(m, p.turn(const Vec3(-.5, 0, 0), .5));
      expect(down.dy, closeTo(expected(.5, .5), 8));
    });

    test('right edge down pans right (roll share)', () {
      final m = MotionMapper();
      final p = SimPhone();
      feed(m, p.still(.1));
      final d = feed(m, p.turn(const Vec3(0, .5, 0), .5));
      expect(d.dx, closeTo(rollPanShare * expected(.5, .5), 8));
      expect(d.dy.abs(), lessThan(3));
    });

    test('any posture: held at 45° or upright, a turn around the vertical pans sideways only', () {
      for (final up in [const Vec3(0, .7071, .7071), const Vec3(0, 1, 0), const Vec3(.2, .6, .77)]) {
        final m = MotionMapper();
        final p = SimPhone(up: up);
        feed(m, p.still(.5));
        final turn = feed(m, p.turn(up.normalized() * -.5, 1));
        expect(turn.dx, closeTo(expected(.5, 1), 12), reason: '$up');
        expect(turn.dy.abs(), lessThan(6), reason: '$up');
      }
    });

    test('tilt sweep left-right-left returns to where it began', () {
      final m = MotionMapper();
      final p = SimPhone(noise: .004);
      feed(m, p.still(.5));
      var sum = Offset.zero;
      for (var k = 0; k < 3; k++) {
        sum += feed(m, p.turn(const Vec3(0, 0, -.8), .6));
        sum += feed(m, p.turn(const Vec3(0, 0, .8), .6));
      }
      expect(sum.distance, lessThan(6));
    });

    test('a pause between samples is not integrated', () {
      final m = MotionMapper();
      final p = SimPhone();
      feed(m, p.still(.2));
      p.gap(const Duration(seconds: 3));
      final d = feed(m, p.turn(const Vec3(0, 0, -.5), .01));
      expect(d.distance, lessThan(1));
    });
  });

  group('window', () {
    PeepholeController window() {
      final s = TileDemoSurface();
      return PeepholeController(surfaceSize: s.size, home: s.home, comfortableViewWidth: s.comfortableViewWidth)
        ..layout(const Size(400, 700));
    }

    test('starts at home with the comfortable width', () {
      final c = window();
      expect(c.center, const Offset(500, 500));
      expect(c.visible.width, closeTo(300, .01));
    });

    test('motion target glides, finger is direct', () {
      final c = window();
      c.moveByMotion(const Offset(100, 0));
      expect(c.center.dx, 500);
      c.tick(followTau);
      expect(c.center.dx, greaterThan(540));
      for (var i = 0; i < 60; i++) {
        c.tick(1 / 60);
      }
      expect(c.center.dx, closeTo(575, .01)); // 100 px / scale 1.333
      c.dragBy(const Offset(40, 0));
      expect(c.center.dx, closeTo(545, .01));
    });

    test('never leaves the surface (plus a little table)', () {
      final c = window();
      c.moveByMotion(const Offset(1e6, -1e6));
      final m = overscrollPixels / c.scale;
      expect(c.target.dx, closeTo(1000 - c.visible.width / 2 + m, .01));
      expect(c.target.dy, closeTo(c.visible.height / 2 - m, .01));
    });

    test('pinch keeps the point under the fingers', () {
      final c = window();
      const focal = Offset(100, 200);
      final before = c.toSurface(focal);
      c.zoomAt(1.5, focal);
      expect(c.toSurface(focal).dx, closeTo(before.dx, .01));
      expect(c.toSurface(focal).dy, closeTo(before.dy, .01));
      c.zoomAt(100, focal);
      expect(c.scale, c.maxScale);
      c.zoomAt(.0001, focal);
      expect(c.scale, c.minScale);
    });

    test('recenter glides back home', () {
      final c = window();
      c.dragBy(const Offset(-300, 200));
      c.recenter();
      for (var i = 0; i < 120; i++) {
        c.tick(1 / 60);
      }
      expect(c.center, const Offset(500, 500));
      expect(c.settled, isTrue);
    });
  });

  group('view', () {
    testWidgets('fake sensors move the window; switching motion off stops it', (t) async {
      final motion = FakeMotion();
      final s = TileDemoSurface();
      final c = PeepholeController(surfaceSize: s.size, home: s.home, comfortableViewWidth: 300);
      await t.pumpWidget(
        app(
          Scaffold(
            body: PeepholeView(surface: s, motion: motion, controller: c),
          ),
        ),
      );
      expect(c.motionState, MotionState.starting);
      final p = SimPhone();
      for (final x in [...p.still(.05), ...p.turn(const Vec3(0, 0, -.6), .5)]) {
        motion.controller.add(x);
      }
      await t.pump();
      expect(c.motionState, MotionState.active);
      await frames(t, 600);
      // 0.5 s at 0.6 rad/s ≈ 224 screen px to the right.
      expect((c.center.dx - 500) * c.scale, closeTo(expected(.6, .5), 10));
      await t.tap(find.byKey(const Key('peephole-motion')));
      await t.pump();
      expect(c.motionState, MotionState.off);
      final x = c.center.dx;
      motion.controller.add(p.turn(const Vec3(0, 0, -.6), .01).first);
      await t.pump(const Duration(milliseconds: 300));
      expect(c.center.dx, x);
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 6));
    });

    testWidgets('no sensors → finger panning, message shown, tap and long press work', (t) async {
      final s = TileDemoSurface();
      final c = PeepholeController(surfaceSize: s.size, home: s.home, comfortableViewWidth: 300);
      final hits = <String>[];
      await t.pumpWidget(
        app(
          Scaffold(
            body: PeepholeView(surface: s, motion: BrokenMotion(), controller: c, onHit: (h) => hits.add(h.title)),
          ),
        ),
      );
      await t.pump();
      expect(c.motionState, MotionState.unavailable);
      expect(find.text(AppLocalizationsDe().peepholeMotionUnavailable), findsOneWidget);
      expect(find.byKey(const Key('peephole-motion')), findsNothing);
      await t.drag(find.byType(PeepholeView), const Offset(-200, 0));
      await t.pump();
      expect((c.center.dx - 500) * c.scale, greaterThan(150)); // drag slop eats a little
      await t.tapAt(t.getCenter(find.byType(PeepholeView)));
      await t.pump(const Duration(milliseconds: 400));
      expect(hits.single, startsWith('tile '));
      await t.longPress(find.byType(PeepholeView));
      await frames(t, 1500);
      expect(c.center.dx, closeTo(500, .5));
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 6));
    });

    testWidgets('silent sensors fall back after the start timeout', (t) async {
      final s = TileDemoSurface();
      final c = PeepholeController(surfaceSize: s.size, home: s.home, comfortableViewWidth: 300);
      await t.pumpWidget(
        app(
          Scaffold(
            body: PeepholeView(surface: s, motion: FakeMotion(), controller: c),
          ),
        ),
      );
      await t.pump(sensorStartTimeout + const Duration(milliseconds: 100));
      expect(c.motionState, MotionState.unavailable);
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 6));
    });
  });

  group('calendar table', () {
    testWidgets('opens from the calendar page, shows today, taps show an event', (t) async {
      t.view.physicalSize = const Size(400, 800);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      final ablage = await t.runAsync(_ablage);
      final s = KalenderSteuerung(ablage: ablage!, uhr: () => DateTime.utc(2026, 11, 10, 9));
      await t.runAsync(s.laden);
      final motion = FakeMotion();
      await t.pumpWidget(app(CalendarTablePage(controller: s, motion: motion)));
      await t.pump();
      expect(find.text('Guckloch'), findsOneWidget);
      expect(find.byType(PeepholeView), findsOneWidget);
      // Tue 10.11. holds "Geige 17:00" — find it by hit-testing the surface.
      final surface = (t.widget(find.byType(PeepholeView)) as PeepholeView).surface;
      final cell = Offset(tableGutter + 1 * tableCellWidth + tablePad + 20, 0);
      PeepholeHit? hit;
      for (var y = tablePad + 28.0; y < tableCellHeight; y += tableLineHeight) {
        final h = surface.hitTest(cell + Offset(0, y + 5));
        if (h != null && h.title == 'Geige') hit = h;
      }
      expect(hit, isNotNull);
      expect(hit!.detail, contains('17:00'));
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 6));
    });

    testWidgets('the calendar page has the peephole action', (t) async {
      final ablage = await t.runAsync(_ablage);
      final s = KalenderSteuerung(ablage: ablage!, uhr: () => DateTime.utc(2026, 11, 10, 9));
      await t.pumpWidget(app(KalenderSeite(steuerung: s)));
      await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
      await t.pump();
      expect(find.byKey(const Key('calendar-table')), findsOneWidget);
      expect(find.byTooltip(AppLocalizationsDe().calendarTableOpen), findsOneWidget);
    });

    testWidgets('preview PNGs at a few positions (build/peephole_preview/)', (t) async {
      await t.runAsync(_fonts);
      final ablage = await t.runAsync(_ablage);
      final k = await t.runAsync(() => Kalender.laden(ablage!));
      const screen = Size(400, 760);
      final today = tagVon(DateTime.utc(2026, 11, 10, 9));

      Future<void> shot(String name, {required bool night, void Function(PeepholeController c)? move}) async {
        final eye = night ? AugeFarben.nacht : AugeFarben.tag;
        final theme = zentraleThema(night ? Brightness.dark : Brightness.light);
        Color layer(String l) {
          final raw = k!.ebene(l)?.farbe;
          final m = RegExp(r'^#([0-9a-fA-F]{6})$').firstMatch(raw ?? '');
          if (m != null) return Color(0xFF000000 | int.parse(m.group(1)!, radix: 16));
          return switch (l) {
            ebeneVielleicht => eye.schatten,
            ebeneRhythmus => eye.falte,
            _ => eye.iris,
          };
        }

        final surface = CalendarTableSurface(
          calendar: k!,
          today: today,
          layerColor: layer,
          strings: AppLocalizationsDe(),
          locale: 'de',
        );
        final c = PeepholeController(
          surfaceSize: surface.size,
          home: surface.home,
          comfortableViewWidth: surface.comfortableViewWidth,
        )..layout(screen);
        move?.call(c);
        for (var i = 0; i < 200; i++) {
          c.tick(1 / 60);
        }
        final style = PeepholeStyle(
          eye: eye,
          night: night,
          ink: theme.colorScheme.onSurface,
          inkMuted: theme.colorScheme.onSurfaceVariant,
          sheet: sheetColor(eye, night),
          warning: theme.colorScheme.error,
          scale: c.scale,
          fontFamily: 'Roboto',
        );
        await t.runAsync(() async {
          final rec = ui.PictureRecorder();
          PeepholePainter(controller: c, surface: surface, style: style).paint(Canvas(rec), screen);
          final img = await rec.endRecording().toImage(screen.width.ceil(), screen.height.ceil());
          final png = await img.toByteData(format: ui.ImageByteFormat.png);
          final f = File('build/peephole_preview/$name.png');
          await f.parent.create(recursive: true);
          await f.writeAsBytes(png!.buffer.asUint8List());
        });
        c.dispose();
      }

      await shot('1_home_day', night: false);
      await shot('2_home_night', night: true);
      await shot('3_swung_right_down_night', night: true, move: (c) => c.moveByMotion(const Offset(520, 380)));
      await shot('4_zoomed_out_day', night: false, move: (c) => c.zoomAt(.01, const Offset(200, 380)));
      await shot('5_zoomed_in_night', night: true, move: (c) => c.zoomAt(2, const Offset(200, 300)));
      expect(File('build/peephole_preview/1_home_day.png').existsSync(), isTrue);
    });
  });
}
