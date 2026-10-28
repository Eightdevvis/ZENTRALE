// Das Auge: Pupille nach Uhrzeit, Plan der Launen, Antippen und Vorschau —
// und Probebilder aller Zustände nach build/auge_vorschau/ (nicht im Repo),
// damit man das Aussehen anschauen kann, ohne das Handy zu bauen.

import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/rendering.dart';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/auge/auge.dart';
import 'package:zen_mobile/auge/auge_maler.dart';
import 'package:zen_mobile/auge/auge_regler.dart';
import 'package:zen_mobile/auge/launen.dart';
import 'package:zen_mobile/auge/zeit.dart';
import 'package:zen_mobile/start/leiterbahnen.dart';
import 'package:zen_mobile/start/startseite.dart';
import 'package:zen_mobile/thema/farben.dart';

DateTime um(int h, [int m = 0]) => DateTime(2026, 10, 28, h, m);

/// Zustand mitten in einer Laune — wie das Auge ihn baut.
AugeZustand inLaune(Laune l, double t, [AugeZustand z = const AugeZustand()]) {
  final s = launenStaerke(t);
  return l.formen(z.mit(laune: l, launeT: t, launeS: s), t, s);
}

Future<void> malen(WidgetTester tester, String name, AugeZustand z,
    {AugeFarben f = AugeFarben.nacht, Size groesse = const Size(400, 440)}) async {
  await tester.runAsync(() async {
    final rec = ui.PictureRecorder();
    final c = Canvas(rec);
    c.drawRect(Offset.zero & groesse, Paint()..color = f.bg);
    AugeMaler(z, f).paint(c, groesse);
    final bild = await rec.endRecording().toImage(groesse.width.ceil(), groesse.height.ceil());
    final png = await bild.toByteData(format: ui.ImageByteFormat.png);
    final datei = File('build/auge_vorschau/$name.png');
    await datei.parent.create(recursive: true);
    await datei.writeAsBytes(png!.buffer.asUint8List());
  });
}

/// Erfundene Bereiche für die Ring-Bilder.
List<Bereich> attrappen(int n) => [
      for (var i = 0; i < n; i++)
        Bereich('B$i', Icons.circle_outlined, (_) => const SizedBox()),
    ];

/// Die Startseite als Bild (wie auf einem 400×800-Handy).
Future<void> schirmBild(WidgetTester tester, GlobalKey rahmen, String name) async {
  final ro = tester.renderObject<RenderRepaintBoundary>(find.byKey(rahmen));
  await tester.runAsync(() async {
    final bild = await ro.toImage();
    final png = await bild.toByteData(format: ui.ImageByteFormat.png);
    final datei = File('build/auge_vorschau/$name.png');
    await datei.parent.create(recursive: true);
    await datei.writeAsBytes(png!.buffer.asUint8List());
  });
}

Future<GlobalKey> startseiteZeigen(WidgetTester tester, int n, {bool nacht = true}) async {
  tester.view.physicalSize = const Size(400, 800);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  final rahmen = GlobalKey();
  await tester.pumpWidget(RepaintBoundary(
    key: rahmen,
    child: MaterialApp(
      theme: zentraleThema(nacht ? Brightness.dark : Brightness.light),
      home: Startseite(kiOeffnen: (_) async {}, knoepfe: attrappen(n)),
    ),
  ));
  await tester.pump(const Duration(milliseconds: 1500)); // aufgehen
  return rahmen;
}

/// Wischen und das erste Bild der Bewegung abwarten (dort steht die Zeit
/// der Animation noch auf null, erst ab dem nächsten läuft sie).
Future<void> wischen(WidgetTester tester, double dy) async {
  await tester.fling(find.byType(Startseite), Offset(0, dy), 800);
  await tester.pump();
}

void main() {
  group('Pupille nach Uhrzeit', () {
    test('Tag, Nacht, Spuk', () {
      expect(pupilleNachUhrzeit(um(12)), 1);
      expect(pupilleNachUhrzeit(um(23)), closeTo(pupilleNachtFaktor, 1e-9));
      expect(pupilleNachUhrzeit(um(1)), closeTo(pupilleNachtFaktor, 1e-9));
      expect(pupilleNachUhrzeit(um(4)), closeTo(pupilleSpukFaktor, 1e-9));
      expect(pupilleNachUhrzeit(um(8)), 1);
    });

    test('an den Grenzen halb, nie ein Sprung', () {
      expect(pupilleNachUhrzeit(um(21)), closeTo((1 + pupilleNachtFaktor) / 2, 1e-9));
      expect(pupilleNachUhrzeit(um(7)), closeTo((1 + pupilleNachtFaktor) / 2, 1e-9));
      var vorher = pupilleNachUhrzeit(um(0));
      for (var m = 1; m <= 24 * 60; m++) {
        final jetzt = pupilleNachUhrzeit(DateTime(2026, 10, 28).add(Duration(minutes: m)));
        expect((jetzt - vorher).abs(), lessThan(.03), reason: 'Minute $m');
        vorher = jetzt;
      }
    });
  });

  group('Launen', () {
    test('mindestens acht, Namen eindeutig, jede passt in ihr Fenster', () {
      expect(alleLaunen.length, greaterThanOrEqualTo(8));
      expect(alleLaunen.map((l) => l.name).toSet().length, alleLaunen.length);
      for (final l in alleLaunen) {
        expect(l.dauerMs, lessThan(launenFensterMs ~/ 4));
      }
    });

    test('Plan: fest, selten, alle kommen dran', () {
      final start = DateTime(2026, 10, 28).millisecondsSinceEpoch;
      final gesehen = <String>{};
      var anfaenge = 0, laufendeMs = 0;
      (Laune, double)? vorher;
      for (var ms = start; ms < start + 7 * 24 * 3600000; ms += 250) {
        final l = launeZu(ms);
        expect(launeZu(ms)?.$2, l?.$2); // dieselbe Zeit, dieselbe Antwort
        if (l != null) {
          laufendeMs += 250;
          gesehen.add(l.$1.name);
          if (vorher == null) anfaenge++;
        }
        vorher = l;
      }
      final proTag = anfaenge / 7;
      // „ab und zu": etwa eine alle paar Minuten, nie dauernd
      expect(proTag, inInclusiveRange(200, 450));
      expect(laufendeMs / (7 * 24 * 3600000), lessThan(.05));
      expect(gesehen, alleLaunen.map((l) => l.name).toSet());
    });

    test('Stärke kommt und geht weich', () {
      expect(launenStaerke(0), 0);
      expect(launenStaerke(1), 0);
      expect(launenStaerke(.5), 1);
    });

    test('bei Stärke 0 ist jede Laune das normale Auge', () {
      const z = AugeZustand(blickX: 2, blickY: -1);
      for (final l in alleLaunen) {
        final a = l.formen(z, 0, 0);
        expect((a.lid, a.blickX, a.blickY, a.pupille, a.unschaerfe, a.lidSchief),
            (z.lid, z.blickX, z.blickY, z.pupille, z.unschaerfe, z.lidSchief), reason: l.name);
        expect(a.farbDrehung % 360, 0, reason: l.name);
      }
    });
  });

  group('Startseite', () {
    testWidgets('Antippen füllt erst das Auge, dann öffnet die KI', (tester) async {
      Rect? mandel;
      await tester.pumpWidget(MaterialApp(home: Startseite(kiOeffnen: (m) async => mandel = m)));
      await tester.pump(const Duration(milliseconds: 1500)); // aufgehen
      await tester.tap(find.byType(Auge));
      await tester.pump(const Duration(milliseconds: tippenMs ~/ 2));
      expect(mandel, isNull); // die Pupille wächst noch
      await tester.pump(const Duration(milliseconds: tippenMs));
      await tester.pump(const Duration(milliseconds: 16));
      expect(mandel, isNotNull);
      expect(mandel!.width / mandel!.height, closeTo(1 / mandelHoehe, 1e-6));
      await tester.pump(const Duration(milliseconds: uebergangZurueckMs + zurueckMs + 100));
    });

    testWidgets('langes Drücken zeigt die nächste Laune', (tester) async {
      await tester.pumpWidget(MaterialApp(home: Startseite(kiOeffnen: (_) async {})));
      await tester.pump(const Duration(milliseconds: 1500));
      await tester.longPress(find.byType(Auge));
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.text('Laune: ${alleLaunen.first.name}'), findsOneWidget);
      await tester.pump(const Duration(seconds: 3));
    });
  });

  group('Knopf-Ring', () {
    test('Bahnen: nur waagrecht, senkrecht oder 45°', () {
      const c = Offset(200, 400);
      for (final n in [1, 2, 3, 5, 6, 9]) {
        final orte = knopfOrte(n, c, 150, 200);
        for (final b in bahnenPlanen(c, 120, 120 * mandelHoehe, orte)) {
          for (final (a, z) in [(b.start, b.knick), (b.knick, b.ziel)]) {
            final d = z - a;
            if (d.distance < 1e-6) continue;
            final gerade = d.dx.abs() < 1e-6 || d.dy.abs() < 1e-6;
            final schraeg = (d.dx.abs() - d.dy.abs()).abs() < 1e-6;
            expect(gerade || schraeg, isTrue, reason: 'n=$n $a→$z');
          }
          expect((b.ziel - b.start).distance, greaterThan(10));
        }
      }
    });

    testWidgets('runter: zu + Knöpfe; hoch: auf, Knöpfe weg', (tester) async {
      await startseiteZeigen(tester, 3);
      expect(find.byType(Tooltip), findsNothing); // Standard: keine Knöpfe
      await wischen(tester, 300);
      await tester.pump(const Duration(milliseconds: ringMs + 100));
      expect(find.byType(Tooltip), findsNWidgets(3));
      // geschlossen öffnet Tippen das Auge, nicht die KI
      await tester.tap(find.byType(Auge));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: ringZurueckMs + 100));
      expect(find.byType(Tooltip), findsNothing);
      await wischen(tester, 300);
      await tester.pump(const Duration(milliseconds: ringMs + 100));
      await wischen(tester, -300);
      await tester.pump(const Duration(milliseconds: ringZurueckMs + 100));
      expect(find.byType(Tooltip), findsNothing);
    });

    testWidgets('Ring-Bilder', (tester) async {
      for (final (n, nacht) in [(1, true), (3, true), (6, true), (3, false), (6, false)]) {
        final rahmen = await startseiteZeigen(tester, n, nacht: nacht);
        final art = nacht ? 'nacht' : 'tag';
        if (n == 3 && nacht) await schirmBild(tester, rahmen, 'r0_offen_${n}_$art');
        await wischen(tester, 300);
        if (n == 6 || n == 3 && nacht) {
          for (final ms in [250, 550, 800]) {
            await tester.pump(Duration(milliseconds: ms - (ms == 250 ? 0 : ms == 550 ? 250 : 550)));
            await schirmBild(tester, rahmen, 'r${n}_${art}_${ms}ms');
          }
        }
        await tester.pump(const Duration(milliseconds: ringMs + 100));
        await schirmBild(tester, rahmen, 'r${n}_${art}_fertig');
        await tester.pumpWidget(const SizedBox());
      }
    });
  });

  group('Probebilder', () {
    testWidgets('alle Zustände', (tester) async {
      final tag = pupilleNachUhrzeit(um(12)), nacht = pupilleNachUhrzeit(um(23));
      final spuk = pupilleNachUhrzeit(um(4));
      await malen(tester, '01_tag_nachtfarben', AugeZustand(pupille: tag));
      await malen(tester, '02_tag_tagfarben', AugeZustand(pupille: tag), f: AugeFarben.tag);
      await malen(tester, '03_nacht_23uhr', AugeZustand(pupille: nacht));
      await malen(tester, '04_spuk_04uhr', AugeZustand(pupille: spuk));
      await malen(tester, '05_blinzeln_halb', const AugeZustand(lid: .5));
      await malen(tester, '06_blinzeln_zu', const AugeZustand(lid: 0));
      await malen(tester, '07_blick_rechts', const AugeZustand(blickX: 5, blickY: 1.5));
      await malen(tester, '08_denkt', const AugeZustand(denkt: true, puls: .6, ring: 1));
      await malen(tester, '09_tippen_50', const AugeZustand(fuellen: .5));
      await malen(tester, '10_tippen_100', const AugeZustand(fuellen: 1));
      await malen(tester, '11_klein_denkt', const AugeZustand(denkt: true, puls: .6, ring: 1),
          groesse: const Size(56, 40));
      await malen(tester, '12_klein_leer', const AugeZustand(), groesse: const Size(120, 90),
          f: AugeFarben.tag);
      for (final (i, l) in alleLaunen.indexed) {
        final n = (20 + i).toString();
        await malen(tester, '${n}_laune_${l.name}', inLaune(l, .5));
        await malen(tester, '${n}_laune_${l.name}_b', inLaune(l, .3), f: AugeFarben.tag);
      }
    });
  });
}
