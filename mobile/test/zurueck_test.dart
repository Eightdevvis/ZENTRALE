// Zurück zum Auge: aus dem Chat per System-Zurück (Taste/Geste) und per
// Augen-Knopf oben links; aus einer Bereichs-Seite des Knopf-Rings ebenso.
// Anlass 29.10.2026: auf dem Handy steckte man im Chat fest.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/auge/auge.dart';
import 'package:zen_mobile/chat/chat_seite.dart';
import 'package:zen_mobile/chat/chat_steuerung.dart';
import 'package:zen_mobile/gespraeche/gespraeche.dart';
import 'package:zen_mobile/ki/anthropic.dart';
import 'package:zen_mobile/main.dart';
import 'package:zen_mobile/start/startseite.dart';

/// Bild für Bild pumpen (das Auge tickt ewig, darum kein pumpAndSettle).
Future<void> laufen(WidgetTester tester, [int ms = 2000]) async {
  for (var t = 0; t < ms; t += 16) {
    await tester.pump(const Duration(milliseconds: 16));
  }
}

Future<void> chatOeffnen(WidgetTester tester) async {
  final ablage = SpeicherAblage();
  final chat = ChatSteuerung(
    ablage: ablage,
    gespraeche: Gespraeche(ablage, knoten: 'handy'),
    ki: AnthropicAnbieter(() async => null),
  );
  await tester.pumpWidget(ZenMobile(steuerung: chat));
  await laufen(tester, 1500); // Auge geht auf
  await tester.tap(find.byType(Auge).first);
  await laufen(tester); // Pupille füllt, Übergang läuft
  expect(find.byType(ChatSeite), findsOneWidget);
}

void main() {
  testWidgets('System-Zurück führt aus dem Chat zurück zum Auge', (tester) async {
    await chatOeffnen(tester);
    expect(await tester.binding.handlePopRoute(), isTrue); // Flutter hat es genommen
    await laufen(tester);
    expect(find.byType(ChatSeite), findsNothing);
    expect(find.byType(Startseite), findsOneWidget);
  });

  testWidgets('Augen-Knopf oben links führt zurück, Menü bleibt erreichbar', (tester) async {
    await chatOeffnen(tester);
    await tester.tap(find.byTooltip('Gespräche'));
    await laufen(tester, 500);
    expect(find.byType(Drawer), findsOneWidget);
    await tester.binding.handlePopRoute(); // schließt erst das Menü
    await laufen(tester, 500);
    expect(find.byType(ChatSeite), findsOneWidget);
    await tester.tap(find.byTooltip('Zum Auge'));
    await laufen(tester);
    expect(find.byType(ChatSeite), findsNothing);
    expect(find.byType(Startseite), findsOneWidget);
  });

  testWidgets('aus einer Bereichs-Seite zurück zum Auge', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Startseite(kiOeffnen: (_) async {}, knoepfe: [
        Bereich('Probe', Icons.circle_outlined,
            (_) => Scaffold(appBar: AppBar(title: const Text('Probe-Seite')))),
      ]),
    ));
    await laufen(tester, 1500);
    await tester.fling(find.byType(Startseite), const Offset(0, 300), 800);
    await laufen(tester);
    await tester.tap(find.byTooltip('Probe'));
    await laufen(tester, 800);
    expect(find.text('Probe-Seite'), findsOneWidget);
    expect(find.byType(BackButton), findsOneWidget); // sichtbarer Weg zurück
    await tester.binding.handlePopRoute();
    await laufen(tester, 800);
    expect(find.text('Probe-Seite'), findsNothing);
  });
}
