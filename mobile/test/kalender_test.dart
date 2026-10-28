// Der Kalender des Handys gegen den Kern: kalender_testvektoren.json ist mit
// core/kalender.entries_in_range erzeugt (scripts/handy_testvektoren.py) —
// erfundene, echt geformte Termine: Wochen- und Monatsregeln, INTERVAL,
// COUNT, UNTIL, EXDATE, X-ZENTRALE-AUS/PAUSE, verschobene und abgesagte
// Vorkommen, ganztags, Spannen, Phasen über Mitternacht, Deadlines mit Soll,
// UTC-Zeiten vor und nach der Zeitumstellung.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/kalender/kalender.dart';
import 'package:zen_mobile/kalender/regel.dart';
import 'package:zen_mobile/kalender/termin_schreiben.dart';
import 'package:zen_mobile/kalender/zeit.dart';

final _v = jsonDecode(File('test/daten/kalender_testvektoren.json').readAsStringSync())
    as Map<String, dynamic>;

Map<String, Object?> _form(Vorkommen o) => {
      'tag': isoTag(o.tag),
      'layer': o.ebene,
      'kennung': o.kennung,
      'versteckt': o.versteckt,
      'label': o.label,
      if (o.zeit != null) 'time': o.zeit,
      if (o.ende != null) 'ende': o.ende,
      if (o.ort != null) 'ort': o.ort,
      if (o.deadline) 'typ': 'deadline',
      if (o.vorwarnung != null) 'vorwarnung': o.vorwarnung,
      if (o.sollZeit != null) 'soll_zeit': o.sollZeit,
      if (o.ueberNacht) 'ueber_nacht': true,
      if (o.motiv != null) 'motiv': o.motiv,
      if (o.absageNoetig) 'absage_noetig': true,
    };

Future<Kalender> _kalender() async {
  final ablage = SpeicherAblage();
  for (final MapEntry(:key, :value) in (_v['dateien'] as Map).entries) {
    await ablage.schreiben(key as String, value as String);
  }
  return Kalender.laden(ablage);
}

void main() {
  setUpAll(zonenLaden);

  test('Vorkommen wie core/kalender.entries_in_range', () async {
    final k = await _kalender();
    final ist = [
      for (final l in k.vorkommen(isoTagLesen(_v['von'])!, isoTagLesen(_v['bis'])!).values)
        for (final o in l) jsonEncode(_form(o))
    ];
    final soll = [
      for (final o in _v['vorkommen'] as List)
        jsonEncode({
          for (final k in ['tag', 'layer', 'kennung', 'versteckt', 'label', 'time', 'ende', 'ort',
              'typ', 'vorwarnung', 'soll_zeit', 'ueber_nacht', 'motiv', 'absage_noetig'])
            if ((o as Map).containsKey(k)) k: o[k]
        })
    ];
    final fehlt = soll.where((s) => !ist.contains(s)).toList();
    final zuviel = ist.where((s) => !soll.contains(s)).toList();
    expect(fehlt, isEmpty, reason: 'fehlt am Handy');
    expect(zuviel, isEmpty, reason: 'nur am Handy');
    expect(ist.length, soll.length);
  });

  test('Regeln wie kalender_regel.vorkommen (dateutil)', () {
    for (final r in _v['regeln'] as List) {
      final seit = isoTagLesen(r['seit'])!, von = isoTagLesen(r['von'])!;
      final tage = Regel.lesen(r['rrule'] as String)
          .tage(seit, isoTagLesen(r['bis'])!)
          .where((t) => !t.isBefore(von))
          .map(isoTag)
          .toList();
      expect(tage, r['tage'], reason: r['rrule'] as String);
    }
  });

  test('neue Termine Byte für Byte wie termin_kalender', () {
    for (final n in _v['neu'] as List) {
      final e = n['eintrag'] as Map;
      final ics = terminIcs(
          NeuerTermin(titel: e['label'] as String, tag: isoTagLesen(n['tag'])!,
              zeit: e['time'] as String?, ende: e['ende'] as String?),
          n['uid'] as String, DateTime.parse(n['jetzt'] as String));
      expect(ics, n['ics'], reason: e['label'] as String);
    }
  });

  test('neue UID und Dateiname wie der Kern', () {
    final u = neueUid();
    expect(u, matches(RegExp(r'^[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}@zentrale$')));
    expect(dateiName(u), '$u.ics');
    expect(dateiName('abc/../x y'), 'abc_.._x_y.ics');
  });

  test('ein neuer Termin liest sich selbst zurück', () async {
    final ablage = SpeicherAblage();
    final uid = neueUid();
    await ablage.schreiben('kalender/termine/${dateiName(uid)}', terminIcs(
        NeuerTermin(titel: 'Test, mit; Zeichen', tag: isoTagLesen('2026-03-29')!, zeit: '01:30', ende: '03:30'),
        uid, DateTime.utc(2026, 10, 1)));
    final k = await Kalender.laden(ablage, wartend: {'kalender/termine/${dateiName(uid)}'});
    final o = k.vorkommen(isoTagLesen('2026-03-29')!, isoTagLesen('2026-03-29')!)['2026-03-29']!.single;
    expect((o.label, o.zeit, o.ende, o.wartet), ('Test, mit; Zeichen', '01:30', '03:30', true));
  });

  test('Ebenen in fester Reihenfolge mit Farbe aus dem vdir', () async {
    final k = await _kalender();
    expect(k.ebenen.take(3).map((e) => e.name), ['termine', 'uncommitted', 'rhythmus']);
    expect(k.ebene('termine')!.farbe, startsWith('#'));
  });
}
