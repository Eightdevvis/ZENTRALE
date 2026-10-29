// Kalender in der App: Erinnerungen aus VALARMs, Überblick für die KI,
// neuer Termin als Vorschlag, die Seite zeichnet die drei Ebenen.

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/eintrag_seite.dart';
import 'package:zen_mobile/kalender/erinnerungen.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/kalender_seite.dart';
import 'package:zen_mobile/kalender/kalender_steuerung.dart';
import 'package:zen_mobile/kalender/termin_schreiben.dart';
import 'package:zen_mobile/kalender/ueberblick.dart';
import 'package:zen_mobile/kalender/views/view_mode.dart';
import 'package:zen_mobile/kalender/zeit.dart';
import 'package:zen_mobile/l10n/app_localizations.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/mitte.dart';

final _v = jsonDecode(File('test/daten/kalender_testvektoren.json').readAsStringSync())
    as Map<String, dynamic>;

/// Die Vektor-Dateien kommen wie im Betrieb über die Mitte aufs Handy.
Future<SpeicherAblage> _ablage() async {
  final m = SpeicherMitte();
  for (final MapEntry(:key, :value) in (_v['dateien'] as Map).entries) {
    m.rechnerSchreibt('data/$key', utf8.encode(value as String));
  }
  final a = SpeicherAblage();
  await Abgleich(a, m).laufen();
  return a;
}

void main() {
  setUpAll(zonenLaden);

  test('Erinnerungen: jeder VALARM, nichts Verstecktes, nichts Vergangenes', () async {
    final k = await Kalender.laden(await _ablage());
    final jetzt = DateTime.utc(2026, 11, 15, 12);
    final w = planen(k, jetzt);
    String wann(String titel) => w.firstWhere((x) => x.titel.startsWith(titel)).wann.toIso8601String();
    // Deadline-VALARM -P3D vor Fr 20.11. 12:00
    expect(wann('Steuererklärung'), '2026-11-17T12:00:00.000Z');
    // Google -PT7H vor Mi 18:00 — der 18.11. ist abgesagt, also der 25.11.
    expect(wann('Chorprobe'), '2026-11-25T11:00:00.000Z');
    // Wochenbericht: 7 h vor Fr 16:00
    expect(wann('Wochenbericht'), '2026-11-20T09:00:00.000Z');
    expect(w.every((x) => x.wann.isAfter(jetzt)), isTrue);
    expect(w.map((x) => x.id).toSet().length, w.length);
    for (var i = 1; i < w.length; i++) {
      expect(!w[i].wann.isBefore(w[i - 1].wann), isTrue);
    }
    // Vorwarnung 0 („Geschenke fertig“) erinnert zur Muss-Zeit selbst.
    final g = planen(k, DateTime.utc(2026, 12, 20));
    expect(g.any((x) => x.titel == 'Geschenke fertig' && x.wann == DateTime.utc(2026, 12, 24, 18)), isTrue);
  });

  test('Überblick für die KI: 14 Tage, ohne Rhythmus und Abgesagtes, mit Soll', () async {
    final k = await Kalender.laden(await _ablage());
    final t = kalenderUeberblick(k, DateTime.utc(2026, 11, 10, 9))!;
    expect(t, startsWith('## Kalender der nächsten Tage'));
    expect(t, contains('nicht ungefragt aufzählen'));
    expect(t, contains('Di 10.11.: '));
    expect(t, contains('17:00–17:45 Geige'));
    final frueh = kalenderUeberblick(k, DateTime.utc(2026, 11, 2, 9))!;
    expect(frueh, isNot(contains(RegExp(r'Di 3\.11\.:[^\n]*Geige')))); // am 3.11. abgeschaltet
    expect(t, isNot(contains('Schlaf')));
    expect(t, contains('Deadline 12:00 Steuererklärung abgeben (Soll Di 17.11. 18:00)'));
    expect(t, contains('Do 12.11.: ganztägig Messe'));
    final verpasst = kalenderUeberblick(k, DateTime.utc(2026, 11, 19, 9))!;
    expect(verpasst, contains('Soll verpasst'));
    expect(kalenderUeberblick(Kalender.leer, DateTime.utc(2026)), isNull);
  });

  test('neuer Termin: sofort sichtbar, wartet, stößt den Abgleich an', () async {
    final ablage = await _ablage();
    var angestossen = 0;
    final e = SpeicherErinnerungen();
    final s = KalenderSteuerung(ablage: ablage, erinnerungen: e,
        uhr: () => DateTime.utc(2026, 11, 2, 9), anstossen: () async => angestossen++);
    await s.laden();
    expect(e.gefragt, 1); // es gibt Erinnerungen → einmal gefragt
    final uid = await s.eintragen(NeuerTermin(titel: 'Friseur', tag: DateTime.utc(2026, 11, 4), zeit: '15:00', ende: '16:00'));
    expect(angestossen, 1);
    final o = s.kalender.vorkommen(DateTime.utc(2026, 11, 4), DateTime.utc(2026, 11, 4))['2026-11-04']!
        .firstWhere((v) => v.kennung == uid);
    expect((o.label, o.wartet, o.ebene), ('Friseur', true, 'termine'));
    expect(s.ebenenZumEintragen.map((x) => x.name), isNot(contains('rhythmus')));
    // Nach dem Abgleich (Mitte kennt ihn) wartet er nicht mehr.
    final m = SpeicherMitte();
    for (final p in ablage.dateien.keys.where((p) => p.startsWith('kalender/'))) {
      m.rechnerSchreibt('data/$p', utf8.encode(ablage.dateien[p]!));
    }
    await Abgleich(ablage, m).laufen();
    await s.laden();
    expect(s.kalender.vorkommen(DateTime.utc(2026, 11, 4), DateTime.utc(2026, 11, 4))['2026-11-04']!
        .firstWhere((v) => v.kennung == uid).wartet, isFalse);
  });

  test('Dauer → Ende am selben Tag, sonst abgelehnt', () {
    expect(endeAus(const TimeOfDay(hour: 23, minute: 0), 60), '24:00');
    expect(endeAus(const TimeOfDay(hour: 23, minute: 30), 60), isNull);
    expect(endeAus(const TimeOfDay(hour: 9, minute: 15), 90), '10:45');
    expect(dauerText(90), '1 h 30 min');
  });

  testWidgets('Kalender-Seite: Ebenen, Deadline mit Soll, „wartet auf Abgleich“', (t) async {
    final ablage = await _ablage();
    final s = KalenderSteuerung(ablage: ablage, uhr: () => DateTime.utc(2026, 11, 19, 9));
    await t.runAsync(() async {
      await s.laden();
      await s.eintragen(NeuerTermin(titel: 'Vom Handy', tag: DateTime.utc(2026, 11, 19), zeit: '18:00'));
    });
    await t.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: const Locale('de'),
        home: KalenderSeite(steuerung: s, initialMode: CalendarViewMode.agenda)));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await t.pump();
    expect(find.text('Heute · 19.11.'), findsOneWidget);
    expect(find.text('Vom Handy'), findsOneWidget);
    expect(find.text('wartet auf Abgleich'), findsOneWidget);
    expect(find.textContaining('Steuererklärung'), findsOneWidget);
    expect(find.text('soll verpasst'), findsOneWidget);
    expect(find.textContaining('Mittagessen 12:30–13:15'), findsWidgets);
    await t.tap(find.text('Vom Handy'));
    await t.pumpAndSettle();
    expect(find.textContaining('kommt mit dem nächsten Abgleich'), findsOneWidget);
  });
}
