// Abgleich zwischen Handy-Ablage und Mitte — konfliktfrei by design.
//
// Regel (abgestimmt mit ASSISTANT, 08.10.2026):
//   HOLEN   gespraeche/** und mobil/kontext.json, außer den eigenen Dateien
//           (die eigenen nur, wenn sie hier fehlen — z. B. nach Neuinstallation).
//   BRINGEN nur, was allein das Handy schreibt:
//           gespraeche/<id>/<knoten>.jsonl, gespraeche/_knoten/<knoten>.json,
//           und kopf.json eines hier neu angelegten Gesprächs, solange die
//           Mitte noch keinen hat.
// Weil nie zwei Knoten dieselbe Datei schreiben, kann nichts überschrieben
// werden. Ein umbenanntes Gespräch kommt als neuer kopf.json zurück.

import 'dart:convert';

import 'package:crypto/crypto.dart';

import '../ablage/ablage.dart';
import '../gespraeche/gespraeche.dart' as g;
import '../ki/kontext.dart';
import 'mitte.dart';

const _merkPfad = 'abgleich/stand.json';

class Ergebnis {
  Ergebnis(this.geholt, this.gebracht);
  final int geholt;
  final int gebracht;
}

class Abgleich {
  Abgleich(this.ablage, this.mitte, {this.knoten = 'handy'});

  final Ablage ablage;
  final Mitte mitte;
  final String knoten;

  bool _eigene(String pfad) =>
      pfad.endsWith('/$knoten.jsonl') || pfad == '${g.wurzel}/_knoten/$knoten.json';

  static String _hash(String s) => sha1.convert(utf8.encode(s)).toString();

  Future<Map<String, dynamic>> _merkLesen() async {
    final t = await ablage.lesen(_merkPfad);
    if (t == null) return {'geholt': <String, dynamic>{}, 'gebracht': <String, dynamic>{}};
    return jsonDecode(t) as Map<String, dynamic>;
  }

  Future<Ergebnis> laufen() async {
    final merk = await _merkLesen();
    final geholtMerk = (merk['geholt'] as Map).cast<String, dynamic>();
    final gebrachtMerk = (merk['gebracht'] as Map).cast<String, dynamic>();
    var geholt = 0, gebracht = 0;

    // ── Holen ──
    final fern = {
      ...await mitte.stand(g.wurzel),
      ...await mitte.stand(kontextPfad),
    };
    for (final MapEntry(key: pfad, value: fassung) in fern.entries) {
      if (_eigene(pfad)) {
        if (await ablage.lesen(pfad) != null) continue;
      } else if (geholtMerk[pfad] == fassung) {
        continue;
      }
      final inhalt = await mitte.lesen(pfad);
      if (inhalt == null) continue;
      await ablage.schreiben(pfad, inhalt);
      geholtMerk[pfad] = fassung;
      geholt++;
    }

    // ── Bringen ──
    for (final pfad in await ablage.alleDateien(g.wurzel)) {
      final kopfNeu = pfad.endsWith('/kopf.json') && !fern.containsKey(pfad);
      if (!_eigene(pfad) && !kopfNeu) continue;
      final inhalt = await ablage.lesen(pfad);
      if (inhalt == null) continue;
      final h = _hash(inhalt);
      if (gebrachtMerk[pfad] == h && fern.containsKey(pfad)) continue;
      geholtMerk[pfad] = await mitte.schreiben(pfad, inhalt);
      gebrachtMerk[pfad] = h;
      gebracht++;
    }

    await ablage.schreiben(_merkPfad, jsonEncode({'geholt': geholtMerk, 'gebracht': gebrachtMerk}));
    return Ergebnis(geholt, gebracht);
  }
}
