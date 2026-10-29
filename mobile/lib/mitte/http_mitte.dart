// Die Mitte als ZENTRALE-Cloud, für einen fremden Knoten — genau nach
// memory/betrieb/abgleich_fremde_knoten.md („Format für fremde Knoten“, „Über die
// Cloud“) und memory/hub/knoten_beitritt.md (Schnittstelle):
//
//   holen    GET /v1/mitte → {kennung, namen}; GET /v1/mitte/datei/inhalt.enc
//            → Inhaltsverzeichnis (Fernet, JSON {dateien: {pfad: {name, sha}}, geloescht})
//   lesen    GET /v1/mitte/datei/d/<name>.enc → entschlüsseln, sha prüfen
//   senden   NUR in den Eingang knoten/<knoten>/<name(pfad)>.enc, Inhalt =
//            Umschlag {format: 1, pfad, inhalt: base64} — als EIN
//            POST /v1/mitte/stand {basis, schreiben|verweise, loeschen}.
//            Inline zusammen ≤ 256 KiB, Größeres als Blob (fehlende →
//            PUT /v1/mitte/blob/<sha256>). 409 jemand_schneller → Kopf neu
//            holen, nochmal; 400 blob_fehlt → nachladen, nochmal.
//
// Der Server sieht nur verschlüsselte Namen und Inhalte. Das Handy schreibt
// nie inhalt.enc und nie d/ — das tun nur die Rechner.

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as c;

import '../krypto/fernet.dart';
import '../krypto/tresor.dart';
import 'cloud.dart';
import 'mitte.dart';

/// Inline-Dateien je Stand (cloud/src/mitte.ts MAX_INLINE).
const maxInline = 256 * 1024;
const maxBlob = 24 * 1024 * 1024;

class HttpMitte implements Mitte {
  HttpMitte(this.client, this.tresor, {this.knoten = 'handy'});

  final CloudClient client;
  final Tresor tresor;
  final String knoten;

  String? _kennung;
  Set<String> _namen = {};
  Map<String, Map<String, dynamic>> _dateien = {};

  String get _eingang => 'knoten/$knoten/';
  String _eingangName(String pfad) => '$_eingang${tresor.name(pfad)}.enc';

  Future<T> _rufen<T>(Future<T> Function() f) async {
    try {
      return await f();
    } on CloudFehler catch (e) {
      throw MitteFehler(e.text, abgemeldet: e.status == 401);
    } on FernetFehler catch (e) {
      throw MitteFehler('Der Kontoschlüssel passt nicht zur Mitte ($e).');
    }
  }

  @override
  Future<MitteStand> holen() => _rufen(() async {
        final d = await client.get('/v1/mitte');
        _kennung = d['kennung'] as String?;
        _namen = {for (final n in (d['namen'] as List? ?? const [])) '$n'};
        _dateien = {};
        var geloescht = <String>{};
        var receipts = <String, Receipt>{};
        if (_kennung != null && _namen.contains('inhalt.enc')) {
          final roh = await client.bytesHolen('/v1/mitte/datei/inhalt.enc');
          final inhalt = jsonDecode(utf8.decode(await tresor.auf(roh))) as Map<String, dynamic>;
          _dateien = {
            for (final e in ((inhalt['dateien'] as Map?) ?? const {}).entries)
              '${e.key}': (e.value as Map).cast<String, dynamic>()
          };
          geloescht = {for (final k in ((inhalt['geloescht'] as Map?) ?? const {}).keys) '$k'};
          final mine = ((inhalt['eingang'] as Map?) ?? const {})[knoten];
          if (mine is Map) {
            receipts = {
              for (final e in mine.entries)
                if (Receipt.parse(e.value) != null) '${e.key}': Receipt.parse(e.value)!
            };
          }
        }
        final namen = _namen;
        return MitteStand(
          kennung: _kennung,
          dateien: {for (final e in _dateien.entries) e.key: '${e.value['sha']}'},
          geloescht: geloescht,
          imEingang: (pfad) => namen.contains(_eingangName(pfad)),
          receipts: receipts,
        );
      });

  @override
  Future<Uint8List> lesen(String pfad) => _rufen(() async {
        final e = _dateien[pfad];
        if (e == null) throw MitteFehler('In der Mitte fehlt $pfad.');
        final name = '${e['name']}';
        if (name != tresor.name(pfad)) throw MitteFehler('Falscher Name für $pfad in der Mitte.');
        Uint8List roh;
        try {
          roh = await client.bytesHolen('/v1/mitte/datei/d/$name.enc');
        } on CloudFehler catch (f) {
          // Mitten im Lesen weitergelaufen: beim nächsten Abgleich neu.
          if (f.status == 404) throw MitteFehler('Die Mitte hat sich beim Lesen geändert.');
          rethrow;
        }
        final klar = await tresor.auf(roh);
        if (Tresor.sha(klar) != e['sha']) {
          throw MitteFehler('Prüfwert von $pfad passt nicht — die Mitte hat sich beim Lesen geändert.');
        }
        return klar;
      });

  @override
  Future<Map<String, Uint8List>> eingangLesen() => _rufen(() async {
        final raus = <String, Uint8List>{};
        for (final n in _namen.where((n) => n.startsWith(_eingang) && n.endsWith('.enc'))) {
          try {
            final u = jsonDecode(utf8.decode(await tresor.auf(await client.bytesHolen('/v1/mitte/datei/$n'))));
            final pfad = '${u['pfad']}';
            // Nur, was wirklich unter diesem Namen liegen darf.
            if ('$_eingang${tresor.name(pfad)}.enc' != n) continue;
            final inhalt = u['inhalt'];
            if (inhalt is! String) continue; // a deletion carries no file
            raus[pfad] = base64.decode(inhalt);
          } on FernetFehler {
            continue;
          } on FormatException {
            continue;
          }
        }
        return raus;
      });

  @override
  Future<void> eingangSenden(Map<String, Uint8List> schreiben, Set<String> entfernen,
          {Map<String, Uint8List> envelopes = const {}}) =>
      _rufen(() async {
        if (_kennung == null) {
          // Noch kein Rechner in der Mitte: warten (ein fremder Knoten legt
          // nie den ersten Stand an).
          throw MitteFehler('Noch hat kein Rechner abgeglichen — die Mitte ist leer.');
        }
        final dateien = <String, Uint8List>{};
        for (final MapEntry(key: pfad, value: inhalt) in schreiben.entries) {
          final token = await tresor.zu(envelope(pfad, inhalt));
          if (token.length > maxBlob) throw MitteFehler('$pfad ist zu groß für die Cloud.');
          dateien[_eingangName(pfad)] = token;
        }
        for (final MapEntry(key: pfad, value: klar) in envelopes.entries) {
          final token = await tresor.zu(klar);
          if (token.length > maxBlob) throw MitteFehler('$pfad ist zu groß für die Cloud.');
          dateien[_eingangName(pfad)] = token;
        }
        final loeschen = [
          for (final p in entfernen)
            if (_namen.contains(_eingangName(p)) && !dateien.containsKey(_eingangName(p))) _eingangName(p)
        ];
        if (dateien.isEmpty && loeschen.isEmpty) return;

        // Klein inline, der Rest als Blob nach Prüfsumme.
        final inline = <String, String>{}, verweise = <String, String>{};
        final blobs = <String, Uint8List>{};
        var summe = 0;
        for (final MapEntry(key: n, value: b) in (dateien.entries.toList()..sort((a, b) => a.value.length - b.value.length))) {
          if (summe + b.length <= maxInline) {
            inline[n] = base64.encode(b);
            summe += b.length;
          } else {
            final sha = c.sha256.convert(b).toString();
            verweise[n] = sha;
            blobs[sha] = b;
          }
        }
        await _hochladen(blobs, blobs.keys.toList());
        for (var versuch = 0; versuch < 5; versuch++) {
          try {
            final d = await client.post('/v1/mitte/stand',
                {'basis': _kennung, 'schreiben': inline, 'verweise': verweise, 'loeschen': loeschen});
            _kennung = d['kennung'] as String? ?? _kennung;
            _namen = {..._namen.difference(loeschen.toSet()), ...dateien.keys};
            return;
          } on CloudFehler catch (e) {
            if (e.status == 409 && versuch < 4) {
              // Ein Rechner war schneller. Der Eingang gehört nur uns, also
              // nichts zusammenzuführen: neuen Kopf holen, nochmal.
              final k = await client.get('/v1/mitte');
              _kennung = k['kennung'] as String?;
              _namen = {for (final n in (k['namen'] as List? ?? const [])) '$n'};
              continue;
            }
            if (e.code == 'blob_fehlt' && versuch < 4) {
              final fehlen = [for (final x in (e.daten['fehlen'] as List? ?? const [])) '$x'];
              await _hochladen(blobs, fehlen.isEmpty ? blobs.keys.toList() : fehlen);
              continue;
            }
            rethrow;
          }
        }
        throw MitteFehler('Die Mitte hat sich fünfmal hintereinander geändert — später nochmal.');
      });

  Future<void> _hochladen(Map<String, Uint8List> blobs, List<String> welche) async {
    if (welche.isEmpty) return;
    final d = await client.post('/v1/mitte/fehlende', {'sha256': welche});
    for (final sha in (d['fehlen'] as List? ?? const [])) {
      final b = blobs['$sha'];
      if (b != null) await client.bytesSenden('/v1/mitte/blob/$sha', b);
    }
  }
}
