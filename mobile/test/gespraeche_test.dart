// ignore_for_file: prefer_interpolation_to_compose_strings
// Das Handy muss Gespräche Byte-genau wie core/gespraeche.py lesen und
// schreiben — sonst sortieren sich Nachrichten falsch oder gehen verloren.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/gespraeche/gespraeche.dart';
import 'package:zen_mobile/gespraeche/zeit.dart';

String zeile(Map<String, dynamic> e) => '${jsonEncode(e)}\n';

void main() {
  test('Zeitstempel wie Python isoformat(timespec=microseconds) in UTC', () {
    final t = DateTime.utc(2026, 10, 8, 13, 24, 4, 123, 456);
    expect(isoUtc(t), '2026-10-08T13:24:04.123456+00:00');
    expect(isoUtc(DateTime.utc(2026, 1, 2, 3, 4, 5)), '2026-01-02T03:04:05.000000+00:00');
  });

  test('jetztTs steigt streng, auch in derselben Mikrosekunde', () {
    final t = DateTime.utc(2030, 1, 1);
    final a = jetztTs(t), b = jetztTs(t);
    expect(b.compareTo(a), greaterThan(0));
  });

  test('ids wie im Kern', () {
    expect(gespraechsId(DateTime.utc(2026, 10, 8, 13, 24, 4)), matches(r'^20261008-132404-[0-9a-f]{6}$'));
    expect(ereignisId(), matches(r'^[0-9a-f]{32}$'));
  });

  test('zusammenlegen: Knoten nach ts gemischt, verwerfen schneidet ab, halbe Zeile egal', () {
    final laptop = zeile({'id': 'a', 'ts': '2026-10-08T10:00:00.000001+00:00', 'knoten': '0RAMMachine',
          'art': 'nachricht', 'rolle': 'user', 'text': 'hallo'}) +
        zeile({'id': 'c', 'ts': '2026-10-08T10:00:02.000000+00:00', 'knoten': '0RAMMachine',
          'art': 'nachricht', 'rolle': 'user', 'text': 'nochmal'}) +
        '{"id": "kaputt", "ts"';
    final handy = zeile({'id': 'b', 'ts': '2026-10-08T10:00:01.000000+00:00', 'knoten': 'handy',
          'art': 'nachricht', 'rolle': 'assistant', 'text': 'hi'}) +
        zeile({'id': 'd', 'ts': '2026-10-08T10:00:03.000000+00:00', 'knoten': 'handy',
          'art': 'verwerfen', 'ab': 'c'});
    final ns = zusammenlegen({'0RAMMachine.jsonl': laptop, 'handy.jsonl': handy});
    expect(ns.map((n) => n.id), ['a', 'b']);
  });

  test('textFuerKi: Vermerk und Auftrags-Vorsatz wie text_fuer_ki', () {
    final n = Nachricht({'id': 'x', 'ts': 't', 'rolle': 'assistant', 'text': 'halb ', 'abgebrochen': true});
    expect(n.textFuerKi, 'halb\n\n(abgebrochen)');
    final v = Nachricht({'id': 'y', 'ts': 't', 'rolle': 'user', 'text': 'tu was', 'versteckt': true});
    expect(v.textFuerKi, startsWith('[Automatischer Auftrag'));
  });

  test('Handy schreibt nur in seine eigene Datei; Liste und Verlauf stimmen', () async {
    final ablage = SpeicherAblage();
    final g = Gespraeche(ablage);
    final id = await g.neu();
    await g.titelSetzen(id, 'Erste Frage');
    await g.anhaengen(id, 'user', 'Wie spät?');
    await g.anhaengen(id, 'assistant', 'Keine Uhr hier.', modell: 'claude-sonnet-5');

    expect(ablage.dateien.keys, containsAll(['gespraeche/$id/kopf.json', 'gespraeche/$id/handy.jsonl']));
    final kopf = jsonDecode(ablage.dateien['gespraeche/$id/kopf.json']!) as Map;
    expect(kopf['titel_von'], 'woerter');
    expect(kopf.keys, containsAll(['titel', 'titel_von', 'erstellt', 'archiviert', 'projekt']));

    final liste = await g.liste();
    expect(liste.single.titel, 'Erste Frage');
    expect(await g.verlaufFuerKi(id), [
      {'role': 'user', 'content': 'Wie spät?'},
      {'role': 'assistant', 'content': 'Keine Uhr hier.'},
    ]);
  });

  test('automatischer Titel überschreibt nie Sashas', () async {
    final ablage = SpeicherAblage();
    final g = Gespraeche(ablage);
    final id = await g.neu();
    await g.titelSetzen(id, 'Von Hand', von: 'sasha');
    await g.titelSetzen(id, 'Automatik');
    expect((await g.kopf(id))['titel'], 'Von Hand');
  });

  test('Verlauf für die KI beginnt immer mit Sasha', () async {
    final ablage = SpeicherAblage();
    final g = Gespraeche(ablage);
    final id = await g.neu();
    await g.anhaengen(id, 'assistant', 'Erinnerung!');
    await g.anhaengen(id, 'user', 'danke');
    expect((await g.verlaufFuerKi(id)).first['role'], 'user');
  });
}
