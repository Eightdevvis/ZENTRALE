// Changing events from the phone: the .ics edits against vectors from the
// real core (scripts/handy_aendern_testvektoren.py), and the proposal flow
// through a played cloud — envelope with basis_sha, receipts, rejection with
// both versions, delete, layer move (memory/betrieb/abgleich_fremde_knoten.md
// "Termine vom Handy").

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/eintrag_seite.dart';
import 'package:zen_mobile/kalender/event_edit.dart';
import 'package:zen_mobile/kalender/event_sheet.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/kalender_seite.dart';
import 'package:zen_mobile/kalender/kalender_steuerung.dart';
import 'package:zen_mobile/kalender/regel.dart';
import 'package:zen_mobile/kalender/termin_lesen.dart';
import 'package:zen_mobile/kalender/views/view_mode.dart';
import 'package:zen_mobile/kalender/zeit.dart';
import 'package:zen_mobile/krypto/tresor.dart';
import 'package:zen_mobile/l10n/app_localizations.dart';
import 'package:zen_mobile/l10n/app_localizations_de.dart';
import 'package:zen_mobile/l10n/app_localizations_en.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/mitte.dart';
import 'package:zen_mobile/mitte/proposals.dart';
import 'vectors.dart';

final _edit = jsonDecode(File(vectorPath('kalender_aendern_testvektoren.json')).readAsStringSync())
    as Map<String, dynamic>;
final _cal = jsonDecode(File(vectorPath('kalender_testvektoren.json')).readAsStringSync()) as Map<String, dynamic>;

final _now = DateTime.utc(2026, 11, 2, 9);

/// A phone that has synced the vector calendar once, and its cloud.
Future<(SpeicherAblage, SpeicherMitte, KalenderSteuerung)> world() async {
  final m = SpeicherMitte();
  for (final MapEntry(:key, :value) in (_cal['dateien'] as Map).entries) {
    m.rechnerSchreibt('data/$key', utf8.encode(value as String));
  }
  final a = SpeicherAblage();
  await Abgleich(a, m).laufen();
  final s = KalenderSteuerung(ablage: a, uhr: () => _now, anstossen: () async => Abgleich(a, m).laufen());
  await s.laden();
  return (a, m, s);
}

Vorkommen occ(KalenderSteuerung s, String label, {bool hidden = false}) {
  final all = s.kalender.vorkommen(DateTime.utc(2026, 10, 1), DateTime.utc(2027, 3, 1));
  return all.values.expand((l) => l).firstWhere((v) => v.label == label && (hidden || !v.versteckt));
}

Map<String, dynamic> env(SpeicherMitte m, String path) =>
    (jsonDecode(utf8.decode(m.envelopes[path]!)) as Map).cast<String, dynamic>();

String sha(String t) => Tresor.sha(utf8.encode(t));

void main() {
  setUpAll(zonenLaden);

  group('ics edits against the core', () {
    test('X-ZENTRALE-AUS is encoded byte for byte like the core', () {
      for (final v in _edit['x_aus'] as List) {
        final list = [for (final x in v['list'] as List) '$x'];
        expect(encodeSwitchedOff(list), v['encoded']);
        expect(decodeSwitchedOff(v['encoded'] as String), list);
      }
    });

    for (final c in (_edit['cases'] as List).cast<Map<String, dynamic>>()) {
      test('${c['name']}: reads like the core after its own change', () {
        final uid = c['uid'] as String;
        final a = (c['action'] as Map).cast<String, dynamic>();
        String out;
        if (a.containsKey('edit')) {
          final e = (a['edit'] as Map).cast<String, dynamic>();
          final series = stueckeLesen(c['input'] as String).first.art == 'routine';
          out = applyChange(
              c['input'] as String,
              uid,
              EventChange(
                  title: e['title'] as String?,
                  place: e['place'] as String?,
                  day: isoTagLesen(e['day'] as String?),
                  start: e['start'] as String?,
                  end: e['end'] as String?),
              now: DateTime.utc(2026, 11, 2),
              series: series);
          if (e['day'] != null) expect(stueckeLesen(out).first.daten['tag'], e['day']);
        } else {
          final off = a.containsKey('off');
          out = setOccurrenceOffIn(c['input'] as String, uid, isoTagLesen((a['off'] ?? a['on']) as String)!,
              off: off, timeOfDay: a['time'] as String?, now: DateTime.utc(2026, 11, 2));
        }
        // For a look with the real core (not in the repo): build/kalender_aendern_out/.
        File('build/kalender_aendern_out/${(c['name'] as String).replaceAll(' ', '_')}.ics')
          ..parent.createSync(recursive: true)
          ..writeAsStringSync(out);
        final d = stueckeLesen(out).firstWhere((s) => s.uid == uid).daten;
        final expect_ = (c['expect'] as Map).cast<String, dynamic>();
        for (final k in ['label', 'time', 'ende', 'ort', 'aus', 'seit']) {
          if (expect_.containsKey(k)) {
            expect(d[k], expect_[k], reason: k);
          } else if (k == 'aus' || k == 'ort') {
            expect(d[k] == null || (d[k] is List && (d[k] as List).isEmpty), isTrue, reason: '$k should be gone');
          }
        }
        // Untouched parts stay: DESCRIPTION and foreign VALARMs of Google files.
        if ((c['input'] as String).contains('DESCRIPTION:Noten')) {
          expect(out, contains('DESCRIPTION:Noten mitbringen'));
          expect(out, contains('TRIGGER:-PT30M'));
        }
      });
    }

    test('every core reason code has its own translation', () {
      for (final l in [AppLocalizationsDe(), AppLocalizationsEn()]) {
        for (final code in (_edit['reasons'] as List).cast<String>()) {
          expect(reasonText(l, code), isNot(l.reasonUnknown(code)), reason: code);
        }
      }
    });
  });

  group('proposal flow', () {
    test('edit: optimistic, waits, envelope with basis; accepted → inbox cleared', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Omas Geburtstag');
      final path = s.kalender.pathOf(v.kennung!)!;
      final mp = 'data/$path';
      final base = (await a.lesen(path))!;
      await s.change(v, const EventChange(title: 'Omas 90. Geburtstag'));
      expect(occ(s, 'Omas 90. Geburtstag').wartet, isTrue);
      final e = env(m, mp);
      expect(e.keys.toList(), ['format', 'pfad', 'inhalt', 'basis_sha', 'basis']);
      expect(e['basis_sha'], sha(base));
      expect(utf8.decode(base64.decode(e['basis'] as String)), base);
      expect(utf8.decode(base64.decode(e['inhalt'] as String)), contains('SUMMARY:Omas 90. Geburtstag'));

      // A second sync without a receipt sends nothing new.
      final n = m.staende;
      await Abgleich(a, m).laufen();
      expect(m.staende, n);

      // The computer accepts and writes its merged version + the receipt.
      final merged = utf8.decode(base64.decode(e['inhalt'] as String));
      m.rechnerSchreibt(mp, utf8.encode(merged));
      m.receipts[mp] = Receipt(envelope: Tresor.sha(m.envelopes[mp]!), result: 'angenommen');
      await Abgleich(a, m).laufen();
      expect(m.envelopes.containsKey(mp), isFalse);
      await s.laden();
      expect(s.proposals.list, isEmpty);
      expect(occ(s, 'Omas 90. Geburtstag').wartet, isFalse);
    });

    test('rejected: reason kept, both versions, keep mine re-proposes on the cloud', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Abendessen bei Kim'); // foreign Google file name
      final path = s.kalender.pathOf(v.kennung!)!;
      expect(path, 'kalender/termine/abc123googlecom.ics');
      final mp = 'data/$path';
      await s.change(v, const EventChange(place: 'Bei Kim zu Hause'));
      // Meanwhile the cloud changed the same event differently → rejected.
      final cloud = (await a.lesen(path))!.replaceFirst('SUMMARY:Abendessen bei Kim', 'SUMMARY:Essen bei Kim');
      m.rechnerSchreibt(mp, utf8.encode(cloud));
      m.receipts[mp] = Receipt(
          envelope: Tresor.sha(m.envelopes[mp]!), result: 'abgelehnt', code: 'conflict_changed', reason: 'x');
      await Abgleich(a, m).laufen();
      await s.laden();
      final p = s.rejected.single;
      expect((p.code, p.cloudText), ('conflict_changed', cloud));
      expect(m.envelopes.containsKey(mp), isFalse); // decided → cleared
      expect(s.mineText[p.target], contains('Bei Kim zu Hause')); // mine stays visible
      expect((await a.lesen(path))!, contains('LOCATION:Bei Kim zu Hause'));

      await s.keepMine(p);
      final e = env(m, mp);
      expect(e['basis_sha'], sha(cloud));
      expect(s.rejected, isEmpty);
    });

    test('rejected: take the cloud drops mine', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Omas Geburtstag');
      final path = s.kalender.pathOf(v.kennung!)!, mp = 'data/$path';
      await s.change(v, const EventChange(title: 'Mine'));
      m.receipts[mp] = Receipt(envelope: Tresor.sha(m.envelopes[mp]!), result: 'abgelehnt', code: 'base_unknown');
      await Abgleich(a, m).laufen();
      await s.laden();
      await s.takeCloud(s.rejected.single);
      expect(s.proposals.list, isEmpty);
      expect(occ(s, 'Omas Geburtstag').label, 'Omas Geburtstag');
    });

    test('occurrence off and on: EXDATE + X-ZENTRALE-AUS, hidden but switchable', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Geige');
      await s.setOccurrenceOff(v, off: true);
      final off = s.kalender.vorkommen(v.tag, v.tag)[isoTag(v.tag)]!.firstWhere((x) => x.label == 'Geige');
      expect((off.versteckt, off.switchedOff), (true, true));
      final mp = 'data/${s.kalender.pathOf(v.kennung!)}';
      final text = utf8.decode(base64.decode(env(m, mp)['inhalt'] as String));
      expect(text, contains('EXDATE'));
      expect(decodeSwitchedOff(RegExp(r'X-ZENTRALE-AUS:(\S+)').firstMatch(text)!.group(1)), contains(isoTag(v.tag)));
      // Back on before any receipt: the envelope is replaced, same basis.
      final basis = env(m, mp)['basis_sha'];
      await s.setOccurrenceOff(off, off: false);
      expect(env(m, mp)['basis_sha'], basis);
      final on = s.kalender.vorkommen(v.tag, v.tag)[isoTag(v.tag)]!.firstWhere((x) => x.label == 'Geige');
      expect(on.versteckt, isFalse);
    });

    test('delete: loeschen + basis_sha, no inhalt; file gone at once', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Omas Geburtstag');
      final path = s.kalender.pathOf(v.kennung!)!, mp = 'data/$path';
      final base = (await a.lesen(path))!;
      await s.delete(v);
      final e = env(m, mp);
      expect(e.keys.toList(), ['format', 'pfad', 'basis_sha', 'basis', 'loeschen']);
      expect((e['loeschen'], e['basis_sha']), (true, sha(base)));
      expect(await a.lesen(path), isNull);
      // The sync does not bring it back while the proposal waits.
      await Abgleich(a, m).laufen();
      expect(await a.lesen(path), isNull);
      // Accepted: the computer deletes it (tombstone).
      m.receipts[mp] = Receipt(envelope: Tresor.sha(m.envelopes[mp]!), result: 'angenommen');
      m.rechnerLoescht(mp);
      await Abgleich(a, m).laufen();
      await s.laden();
      expect(s.proposals.list, isEmpty);
      expect(await a.lesen(path), isNull);
    });

    test('layer move: new path under the UID name, basis of the old file, no delete', () async {
      final (a, m, s) = await world();
      final v = occ(s, 'Abendessen bei Kim');
      final old = s.kalender.pathOf(v.kennung!)!;
      final base = (await a.lesen(old))!;
      await s.change(v, const EventChange(), layer: 'uncommitted');
      final uid = v.kennung!;
      final target = 'kalender/uncommitted/${uid.replaceAll(RegExp(r'[^A-Za-z0-9@.\-]'), '_')}.ics';
      expect(await a.lesen(old), isNull);
      expect(await a.lesen(target), isNotNull);
      final e = env(m, 'data/$target');
      expect(e['basis_sha'], sha(base));
      expect(e.containsKey('loeschen'), isFalse);
      expect(m.envelopes.containsKey('data/$old'), isFalse);
      expect(occ(s, 'Abendessen bei Kim').ebene, 'uncommitted');
    });

    test('envelope plaintext sha is what the receipt compares', () {
      final b = envelope('data/x.ics', Uint8List.fromList([1, 2]), baseSha: 'ab', delete: false);
      expect(jsonDecode(utf8.decode(b)), {'format': 1, 'pfad': 'data/x.ics', 'inhalt': 'AQI=', 'basis_sha': 'ab'});
    });

    test('proposals survive a restart (register in the Ablage)', () async {
      final (a, m, s) = await world();
      await s.change(occ(s, 'Omas Geburtstag'), const EventChange(title: 'X'));
      final again = await Proposals.load(a);
      expect(again.list.single.envelope, isNotNull);
    });
  });

  testWidgets('sheet: delete with confirm, edit opens the form prefilled', (t) async {
    t.view.physicalSize = const Size(400, 800);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    final (a, m, s) = (await t.runAsync(world))!;
    await t.pumpWidget(MaterialApp(
      locale: const Locale('de'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: KalenderSeite(steuerung: s, initialMode: CalendarViewMode.agenda),
    ));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await t.pumpAndSettle();
    final v = occ(s, 'Geige');
    showEventSheet(t.element(find.byType(KalenderSeite)), v, s);
    await t.pumpAndSettle();
    expect(find.byKey(const ValueKey('event-occurrence')), findsOneWidget);
    expect(find.text('Ganze Serie löschen'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('event-edit')));
    await t.pumpAndSettle();
    expect(find.byType(EintragSeite), findsOneWidget);
    expect(find.text('Termin ändern'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Geige'), findsOneWidget);
    expect(find.text('Beginn ${v.zeit}'), findsOneWidget);
    Navigator.of(t.element(find.byType(EintragSeite))).pop();
    await t.pumpAndSettle();

    final o = occ(s, 'Omas Geburtstag');
    showEventSheet(t.element(find.byType(KalenderSeite)), o, s);
    await t.pumpAndSettle();
    await t.tap(find.byKey(const ValueKey('event-delete')));
    await t.pumpAndSettle();
    expect(find.text('„Omas Geburtstag“ löschen?'), findsOneWidget);
    await t.runAsync(() async {
      await t.tap(find.byKey(const ValueKey('event-delete-confirm')));
      await Future<void>.delayed(const Duration(milliseconds: 100));
    });
    await t.pumpAndSettle();
    final path = 'data/kalender/termine/00000000000000000000000000000002@zentrale.ics';
    expect(env(m, path)['loeschen'], true);
  });

  testWidgets('rejected banner shows the translated reason and both versions', (t) async {
    final (a, m, s) = (await t.runAsync(() async {
      final w = await world();
      final (a, m, s) = w;
      final v = occ(s, 'Omas Geburtstag');
      final mp = 'data/${s.kalender.pathOf(v.kennung!)}';
      await s.change(v, const EventChange(title: 'Mine'));
      m.receipts[mp] = Receipt(envelope: Tresor.sha(m.envelopes[mp]!), result: 'abgelehnt', code: 'conflict_changed');
      await Abgleich(a, m).laufen();
      await s.laden();
      return w;
    }))!;
    await t.pumpWidget(MaterialApp(
      locale: const Locale('de'),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: KalenderSeite(steuerung: s, initialMode: CalendarViewMode.week),
    ));
    await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await t.pumpAndSettle();
    expect(find.text('Eine Änderung wurde abgelehnt'), findsOneWidget);
    await t.tap(find.byKey(const ValueKey('calendar-rejected')));
    await t.pumpAndSettle();
    expect(find.textContaining('am Handy und in der Cloud verschieden geändert'), findsOneWidget);
    expect(find.textContaining('Am Handy: Mine'), findsOneWidget);
    expect(find.textContaining('In der Cloud: Omas Geburtstag'), findsOneWidget);
    expect(a, isNotNull);
  });
}
