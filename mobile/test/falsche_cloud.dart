// Eine gespielte ZENTRALE-Cloud für die Tests — dieselben Routen und Regeln
// wie server/src/mitte.ts und tests/_falsche_cloud.py (Compare-and-Swap auf
// den Kopf, Inline ≤ 256 KiB, blob_fehlt, 401 ohne Sitzung). Nie das Netz.
//
// [rechnerSchreibt] spielt einen Rechner: er legt Dateien verschlüsselt nach
// d/<name>.enc und schreibt inhalt.enc neu — genau wie core/abgleich.py.

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as c;
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:zen_mobile/krypto/tresor.dart';

class FalscheCloud {
  FalscheCloud({this.vektoren});

  /// konto_testvektoren.json — für /v1/vorab und /v1/sitzung.
  final Map<String, dynamic>? vektoren;

  final Map<String, Uint8List> namen = {}; // aktueller Stand: Name → Bytes
  final Map<String, Uint8List> blobs = {};
  String? kennung;
  int _n = 0;
  String token = 'sitzung-1';
  final List<String> anfragen = [];

  /// Vor dem nächsten POST /v1/mitte/stand läuft „ein Rechner“ dazwischen.
  int schnellerBeim = 0;

  /// Blobs verschwinden einmal zwischen Hochladen und Stand.
  bool blobVergessen = false;

  Map<String, dynamic> inhalt = {'format': 1, 'dateien': {}, 'geloescht': {}};

  Future<void> rechnerSchreibt(Tresor t, Map<String, List<int>> dateien,
      {List<String> loeschen = const []}) async {
    for (final MapEntry(key: pfad, value: b) in dateien.entries) {
      final name = t.name(pfad);
      namen['d/$name.enc'] = await t.zu(b);
      (inhalt['dateien'] as Map)[pfad] = {'name': name, 'sha': c.sha256.convert(b).toString()};
      (inhalt['geloescht'] as Map).remove(pfad);
    }
    for (final pfad in loeschen) {
      final e = (inhalt['dateien'] as Map).remove(pfad);
      if (e != null) namen.remove('d/${e['name']}.enc');
      (inhalt['geloescht'] as Map)[pfad] = {'sha': '0' * 64, 'von': 'laptop', 'am': '2026-10-28T10:00:00'};
    }
    namen['inhalt.enc'] = await t.zu(utf8.encode(jsonEncode(inhalt)));
    kennung = 'k${++_n}';
  }

  /// Der entschlüsselte Eingang eines Knotens: Pfad → Klartext.
  Future<Map<String, String>> eingang(Tresor t, [String knoten = 'handy']) async {
    final raus = <String, String>{};
    for (final MapEntry(:key, :value) in namen.entries) {
      if (!key.startsWith('knoten/$knoten/')) continue;
      final u = jsonDecode(utf8.decode(await t.auf(value)));
      expectName(key, 'knoten/$knoten/${t.name(u['pfad'] as String)}.enc');
      raus[u['pfad'] as String] = utf8.decode(base64.decode(u['inhalt'] as String));
    }
    return raus;
  }

  static void expectName(String ist, String soll) {
    if (ist != soll) throw StateError('Eingangsname $ist passt nicht zu $soll');
  }

  http.Response _json(Object d, [int status = 200]) =>
      http.Response(jsonEncode(d), status, headers: {'content-type': 'application/json'});
  http.Response _fehler(int s, String code, [Map<String, dynamic> mehr = const {}]) =>
      _json({'fehler': code, 'text': 'Fehler $code', ...mehr}, s);

  late final http.Client client = MockClient((r) async {
    final p = r.url.path;
    anfragen.add('${r.method} $p');
    if (p == '/v1/vorab') {
      return _json({'salz': vektoren!['salz_b64u'], 'kdf': vektoren!['kdf']});
    }
    if (p == '/v1/sitzung' && r.method == 'POST') {
      final d = jsonDecode(r.body) as Map;
      if (d['anmelde_schluessel'] != vektoren!['anmelde_schluessel_b64u'] || d['knoten'] != 'handy') {
        return _fehler(401, 'falsches_passwort');
      }
      return _json({'token': token, 'laeuft_ab': '2026-11-28T00:00:00Z',
          'verpackt_passwort': vektoren!['verpackt_passwort']});
    }
    if (r.headers['Authorization'] != 'Bearer $token') return _fehler(401, 'nicht_angemeldet');
    if (p == '/v1/sitzung' && r.method == 'DELETE') return http.Response('', 204);
    if (p == '/v1/mitte') return _json({'kennung': kennung, 'namen': namen.keys.toList()..sort()});
    if (p.startsWith('/v1/mitte/datei/')) {
      final b = namen[p.substring('/v1/mitte/datei/'.length)];
      return b == null ? _fehler(404, 'nicht_gefunden') : http.Response.bytes(b, 200);
    }
    if (p == '/v1/mitte/fehlende') {
      final l = (jsonDecode(r.body) as Map)['sha256'] as List;
      return _json({'fehlen': [for (final h in l) if (!blobs.containsKey(h)) h]});
    }
    if (p.startsWith('/v1/mitte/blob/')) {
      final sha = p.substring('/v1/mitte/blob/'.length);
      if (c.sha256.convert(r.bodyBytes).toString() != sha) return _fehler(400, 'pruefsumme');
      blobs[sha] = r.bodyBytes;
      return http.Response('', 204);
    }
    if (p == '/v1/mitte/stand') {
      final d = jsonDecode(r.body) as Map;
      if (schnellerBeim > 0) {
        schnellerBeim--;
        kennung = 'k${++_n}';
        return _fehler(409, 'jemand_schneller');
      }
      if (d['basis'] != kennung) return _fehler(409, 'jemand_schneller');
      final schreiben = (d['schreiben'] as Map? ?? {}).cast<String, String>();
      final inline = schreiben.values.fold<int>(0, (s, v) => s + base64.decode(v).length);
      if (inline > 256 * 1024) return _fehler(413, 'inline_zu_gross');
      if (blobVergessen) {
        blobVergessen = false;
        blobs.clear();
      }
      final verweise = (d['verweise'] as Map? ?? {}).cast<String, String>();
      final fehlen = [for (final h in verweise.values) if (!blobs.containsKey(h)) h];
      if (fehlen.isNotEmpty) return _fehler(400, 'blob_fehlt', {'fehlen': fehlen});
      for (final n in (d['loeschen'] as List? ?? [])) {
        namen.remove(n);
      }
      schreiben.forEach((n, v) => namen[n] = base64.decode(v));
      verweise.forEach((n, h) => namen[n] = blobs[h]!);
      kennung = 'k${++_n}';
      return _json({'kennung': kennung});
    }
    return _fehler(404, 'unbekannt');
  });
}
