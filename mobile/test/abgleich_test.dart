// Abgleich: holt fremde Dateien, bringt nur eigene — nie überschreibt das
// Handy, was ein anderer Knoten geschrieben hat.

import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/gespraeche/gespraeche.dart';
import 'package:zen_mobile/mitte/abgleich.dart';
import 'package:zen_mobile/mitte/mitte.dart';

void main() {
  test('holen und bringen, ohne fremde Dateien anzufassen', () async {
    final mitte = SpeicherMitte();
    await mitte.schreiben('gespraeche/g1/kopf.json', '{"titel":"vom Laptop"}');
    await mitte.schreiben('gespraeche/g1/0RAMMachine.jsonl', 'laptop\n');
    await mitte.schreiben('mobil/kontext.json', '{"system":"x"}');
    await mitte.schreiben('anderes/geheim.json', 'nicht fürs Handy');

    final ablage = SpeicherAblage();
    final g = Gespraeche(ablage);
    final eigenes = await g.neu();
    await g.anhaengen(eigenes, 'user', 'vom Handy');
    await g.anhaengen('g1', 'user', 'Antwort im Laptop-Gespräch');

    final a = Abgleich(ablage, mitte);
    final r = await a.laufen();

    expect(ablage.dateien['gespraeche/g1/0RAMMachine.jsonl'], 'laptop\n');
    expect(ablage.dateien['mobil/kontext.json'], '{"system":"x"}');
    expect(ablage.dateien.containsKey('anderes/geheim.json'), isFalse);
    expect(mitte.dateien.containsKey('gespraeche/$eigenes/handy.jsonl'), isTrue);
    expect(mitte.dateien.containsKey('gespraeche/$eigenes/kopf.json'), isTrue);
    expect(mitte.dateien.containsKey('gespraeche/g1/handy.jsonl'), isTrue);
    expect(mitte.dateien['gespraeche/g1/kopf.json'], '{"titel":"vom Laptop"}');
    expect(r.geholt, 3);

    // Zweiter Lauf ohne Änderung: nichts zu tun.
    final r2 = await a.laufen();
    expect((r2.geholt, r2.gebracht), (0, 0));

    // Laptop benennt um → kommt aufs Handy; Handy bringt seinen Kopf nicht zurück.
    await mitte.schreiben('gespraeche/$eigenes/kopf.json', '{"titel":"neu vom Laptop"}');
    await a.laufen();
    expect(ablage.dateien['gespraeche/$eigenes/kopf.json'], '{"titel":"neu vom Laptop"}');
  });

  test('nach Neuinstallation kommen die eigenen Dateien zurück', () async {
    final mitte = SpeicherMitte();
    await mitte.schreiben('gespraeche/g1/kopf.json', '{}');
    await mitte.schreiben('gespraeche/g1/handy.jsonl', 'alt\n');
    final ablage = SpeicherAblage();
    await Abgleich(ablage, mitte).laufen();
    expect(ablage.dateien['gespraeche/g1/handy.jsonl'], 'alt\n');
  });
}
