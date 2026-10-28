// Das Handy an der Mitte: Anmelden, Holen, Bringen in den Eingang — gegen
// eine gespielte Cloud (test/falsche_cloud.dart), nie gegen das Netz.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/gespraeche/gespraeche.dart';
import 'package:zen_mobile/kalender/regel.dart';
import 'package:zen_mobile/kalender/termin_schreiben.dart';
import 'package:zen_mobile/konto/geheim.dart';
import 'package:zen_mobile/konto/konto.dart';
import 'package:zen_mobile/krypto/tresor.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/cloud.dart';
import 'package:zen_mobile/mitte/http_mitte.dart';
import 'package:zen_mobile/mitte/mitte.dart';

import 'falsche_cloud.dart';

Map<String, dynamic> _json(String n) =>
    jsonDecode(File('test/daten/$n').readAsStringSync()) as Map<String, dynamic>;

final _konto = _json('konto_testvektoren.json');
final _mitteV = _json('mitte_testvektoren.json');
final _tresor = Tresor(_konto['konto_schluessel'] as String);

List<int> _b(String s) => utf8.encode(s);

/// Cloud mit einem Stand, wie ihn ein Rechner hinterlässt.
Future<FalscheCloud> _cloud() async {
  final c = FalscheCloud(vektoren: _konto);
  await c.rechnerSchreibt(_tresor, {
    'data/gespraeche/g1/kopf.json': _b('{"titel":"vom Laptop"}'),
    'data/gespraeche/g1/0RAMMachine.jsonl': _b('{"text":"laptop"}\n'),
    'data/mobil/kontext.json': _b('{"version":1,"system":"Du bist ZENTRALE.","stand":"x"}'),
    'data/kalender/termine/color': _b('#3b82f6\n'),
    'data/kalender/termine/abc.ics': _b('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n'),
    'data/adapter/geheim.enc': _b(_mitteV['geheim_enc'] as String),
    'data/lists.json': _b('[]'), // gehört nicht aufs Handy
  });
  return c;
}

HttpMitte _mitte(FalscheCloud c) =>
    HttpMitte(CloudClient(basis: 'https://cloud.test', token: c.token, client: c.client), _tresor);

void main() {
  test('Anmelden: Argon2id → Sitzung → konto_schluessel, Passwort nie gespeichert', () async {
    final c = FalscheCloud(vektoren: _konto);
    final speicher = SpeicherSitzung();
    final konto = Konto(speicher,
        client: (t) => CloudClient(basis: 'https://cloud.test', token: t, client: c.client));
    final s = await konto.anmelden('  Sasha ', _konto['passwort'] as String);
    expect(s.kontoSchluessel, _konto['konto_schluessel']);
    expect(s.token, c.token);
    expect(jsonEncode(speicher.s!.alsJson()), isNot(contains(_konto['passwort'] as String)));
    await expectLater(konto.anmelden('sasha', 'falsch'), throwsA(isA<KontoFehler>()));
    expect(() => nameLesen('a@b.de'), throwsA(isA<KontoFehler>()));
    await konto.abmelden();
    expect(speicher.s, isNull);
    expect(c.anfragen, contains('DELETE /v1/sitzung'));
  }, timeout: const Timeout(Duration(minutes: 2)));

  test('holen: nur was aufs Handy gehört, ohne data/ in der Ablage', () async {
    final c = await _cloud();
    final ablage = SpeicherAblage();
    final r = await Abgleich(ablage, _mitte(c)).laufen();
    expect(r.geholt, 6);
    expect(ablage.dateien['gespraeche/g1/0RAMMachine.jsonl'], '{"text":"laptop"}\n');
    expect(ablage.dateien['kalender/termine/color'], '#3b82f6\n');
    expect(ablage.dateien.containsKey('lists.json'), isFalse);
    expect(await geheimLesen(ablage, _konto['konto_schluessel'] as String, kiAnthropic),
        _mitteV['geheim_ki']);
    final z = await AbgleichZustand.lesen(ablage);
    expect((z.fehler, z.kalenderInMitte), (null, true));
    // Zweiter Lauf: nichts geändert, nichts geholt, kein neuer Stand.
    final vorher = c.kennung;
    expect((await Abgleich(ablage, _mitte(c)).laufen()).geholt, 0);
    expect(c.kennung, vorher);
  });

  test('bringen nur in den Eingang: eigene Datei, neuer Kopf, neuer Termin', () async {
    final c = await _cloud();
    final ablage = SpeicherAblage();
    await Abgleich(ablage, _mitte(c)).laufen();
    final g = Gespraeche(ablage);
    final id = await g.neu();
    await g.titelSetzen(id, 'Unterwegs');
    await g.anhaengen(id, 'user', 'vom Handy');
    await g.anhaengen('g1', 'user', 'Antwort ins Laptop-Gespräch');
    final uid = neueUid();
    final termin = 'kalender/termine/${dateiName(uid)}';
    await ablage.schreiben(termin, terminIcs(
        NeuerTermin(titel: 'Zahnarzt', tag: isoTagLesen('2026-11-03')!, zeit: '10:00', ende: '11:00'),
        uid, DateTime.utc(2026, 10, 28)));
    c.schnellerBeim = 1; // ein Rechner gleicht genau dazwischen ab → 409 → nochmal
    final r = await Abgleich(ablage, _mitte(c)).laufen();
    final ein = await c.eingang(_tresor);
    expect(ein.keys, containsAll(['data/gespraeche/$id/handy.jsonl', 'data/gespraeche/$id/kopf.json',
        'data/gespraeche/g1/handy.jsonl', 'data/$termin']));
    expect(ein.keys, isNot(contains('data/gespraeche/g1/kopf.json')));
    expect(r.gebracht, ein.length);
    expect(c.namen.keys.where((n) => n.startsWith('d/') || n == 'inhalt.enc').length, 8,
        reason: 'das Handy schreibt nie ins Inhaltsverzeichnis');
    expect(await Abgleich.wartend(ablage), {termin});

    // Der Rechner übernimmt den Termin (abgleich_vorschlaege) → das Handy
    // räumt seinen Eingang auf, der Termin wartet nicht mehr.
    await c.rechnerSchreibt(_tresor, {'data/$termin': _b(ablage.dateien[termin]!)});
    await Abgleich(ablage, _mitte(c)).laufen();
    expect((await c.eingang(_tresor)).keys, isNot(contains('data/$termin')));
    expect(await Abgleich.wartend(ablage), isEmpty);

    // Später am Rechner gelöscht → auch am Handy weg.
    await c.rechnerSchreibt(_tresor, {}, loeschen: ['data/$termin']);
    await Abgleich(ablage, _mitte(c)).laufen();
    expect(ablage.dateien.containsKey(termin), isFalse);
  });

  test('große Dateien als Blob, blob_fehlt wird nachgeladen', () async {
    final c = await _cloud();
    final ablage = SpeicherAblage();
    await Abgleich(ablage, _mitte(c)).laufen();
    final zeile = '${jsonEncode({'text': 'x' * 1000})}\n';
    await ablage.schreiben('gespraeche/g1/handy.jsonl', zeile * 400); // ~400 KB
    c.blobVergessen = true;
    await Abgleich(ablage, _mitte(c)).laufen();
    expect(c.anfragen.where((a) => a.startsWith('PUT /v1/mitte/blob/')).length, 2);
    expect((await c.eingang(_tresor))['data/gespraeche/g1/handy.jsonl'], zeile * 400);
  });

  test('nach Neuinstallation kommen die eigenen Dateien aus dem Eingang zurück', () async {
    final c = await _cloud();
    final alt = SpeicherAblage();
    await Abgleich(alt, _mitte(c)).laufen();
    await alt.schreiben('gespraeche/g1/handy.jsonl', 'alt\n');
    await Abgleich(alt, _mitte(c)).laufen();
    final neu = SpeicherAblage();
    await Abgleich(neu, _mitte(c)).laufen();
    expect(neu.dateien['gespraeche/g1/handy.jsonl'], 'alt\n');
  });

  test('leere Mitte: das Handy wartet, schreibt nichts', () async {
    final c = FalscheCloud(vektoren: _konto);
    final ablage = SpeicherAblage();
    await ablage.schreiben('gespraeche/g9/handy.jsonl', 'x\n');
    final r = await Abgleich(ablage, _mitte(c)).laufen();
    expect(r.mitteLeer, isTrue);
    expect(c.namen, isEmpty);
  });

  test('abgelaufene Sitzung: klarer Fehler, als abgemeldet erkennbar', () async {
    final c = await _cloud();
    final m = HttpMitte(CloudClient(basis: 'https://cloud.test', token: 'alt', client: c.client), _tresor);
    final ablage = SpeicherAblage();
    await expectLater(Abgleich(ablage, m).laufen(),
        throwsA(isA<MitteFehler>().having((e) => e.abgemeldet, 'abgemeldet', isTrue)));
    expect((await AbgleichZustand.lesen(ablage)).fehler, isNotNull);
  });

  test('SpeicherMitte: dieselbe Schnittstelle (für den Heimserver später)', () async {
    final m = SpeicherMitte()..rechnerSchreibt('data/mobil/kontext.json', _b('{}'));
    final ablage = SpeicherAblage();
    await ablage.schreiben('gespraeche/_knoten/handy.json', '{}');
    await Abgleich(ablage, m).laufen();
    expect(ablage.dateien['mobil/kontext.json'], '{}');
    expect(m.eingang.keys, ['data/gespraeche/_knoten/handy.json']);
    expect(Uint8List.fromList(m.eingang.values.first), _b('{}'));
  });
}
