// Der Krypto-Nachbau des Handys gegen die Testvektoren des Kerns
// (contracts/account-keys/1/konto_testvektoren.json, dieselbe Datei) und gegen
// Vektoren der Mitte, die scripts/handy_testvektoren.py mit dem echten Kern
// erzeugt (contracts/cloud-sync/1/mitte_testvektoren.json).

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:zen_mobile/krypto/fernet.dart';
import 'package:zen_mobile/krypto/konto_schluessel.dart';
import 'package:zen_mobile/krypto/tresor.dart';
import 'vectors.dart';

Map<String, dynamic> _json(String name) =>
    jsonDecode(File(vectorPath(name)).readAsStringSync()) as Map<String, dynamic>;

List<int> _hex(String h) =>
    [for (var i = 0; i < h.length; i += 2) int.parse(h.substring(i, i + 2), radix: 16)];

String _hexText(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();

void main() {
  final v = _json('konto_testvektoren.json');

  test('Argon2id → Hauptschlüssel (64 MiB, im Isolate)', () async {
    final uhr = Stopwatch()..start();
    final haupt = await hauptschluessel(
        v['passwort'] as String, _hex(v['salz_hex'] as String), Kdf.lesen(v['kdf']));
    // ignore: avoid_print
    print('Argon2id: ${uhr.elapsedMilliseconds} ms');
    expect(_hexText(haupt), v['hauptschluessel_hex']);
  }, timeout: const Timeout(Duration(minutes: 3)));

  test('HKDF, anmelde_schluessel, verpack_schluessel, auspacken', () async {
    final haupt = _hex(v['hauptschluessel_hex'] as String);
    expect(await anmeldeSchluessel(haupt), v['anmelde_schluessel_b64u']);
    final verpack = await verpackSchluessel(haupt);
    expect(verpack, v['verpack_schluessel_fernet']);
    expect(await auspacken(verpack, v['verpackt_passwort'] as String), v['konto_schluessel']);
    expect(() => auspacken(v['notfall_schluessel_fernet'] as String, v['verpackt_passwort'] as String),
        throwsA(isA<KontoSchluesselFehler>()));
  });

  test('Fernet mit fester Zeit und IV Byte für Byte wie Python', () async {
    final f = v['fernet_fest'] as Map;
    final token = await Fernet(v['verpack_schluessel_fernet'] as String).zu(
        ascii.encode(v['konto_schluessel'] as String),
        zeit: f['zeit'] as int, iv: _hex(f['iv_hex'] as String));
    expect(token, v['verpackt_passwort']);
    final m = _json('mitte_testvektoren.json')['fest'] as Map;
    expect(
        await Fernet(v['konto_schluessel'] as String)
            .zu(base64.decode(m['klar_b64'] as String), zeit: m['zeit'] as int, iv: _hex(m['iv_hex'] as String)),
        m['token']);
  });

  test('KDF-Werte: zu schwach wird abgelehnt', () {
    expect(() => Kdf.lesen({'name': 'argon2id', 't': 3, 'm': 1024, 'p': 4}),
        throwsA(isA<KontoSchluesselFehler>()));
    expect(() => Kdf.lesen({'name': 'scrypt'}), throwsA(isA<KontoSchluesselFehler>()));
    expect(Kdf.lesen({'iterations': 2, 'memory': 65536, 'parallelism': 1}).t, 2);
  });

  group('Tresor wie core/abgleich_schluessel.Tresor', () {
    final m = _json('mitte_testvektoren.json');
    final t = Tresor(m['konto_schluessel'] as String);

    test('versteckte Namen', () {
      for (final MapEntry(:key, :value) in (m['namen'] as Map).entries) {
        expect(t.name(key as String), value, reason: key);
      }
    });

    test('inhalt.enc, Datei, Umschlag, geheim.enc', () async {
      final inhalt = jsonDecode(utf8.decode(await t.auf(ascii.encode(m['inhalt_token'] as String))));
      expect(inhalt, m['inhalt']);
      final datei = await t.auf(ascii.encode(m['datei_token'] as String));
      expect(base64.encode(datei), m['datei_klar_b64']);
      expect(Tresor.sha(datei), (m['inhalt'] as Map)['dateien']['data/mobil/kontext.json']['sha']);
      expect(jsonDecode(utf8.decode(await t.auf(ascii.encode(m['umschlag_token'] as String)))),
          m['umschlag']);
      final geheim = jsonDecode(m['geheim_enc'] as String) as Map;
      expect(await t.eintragAuf(geheim['eintraege']['ki/ANTHROPIC_API_KEY']['wert'] as String),
          m['geheim_ki']);
      // Hin und zurück mit zufälligem IV
      final zu = await t.zu(utf8.encode('rund'));
      expect(utf8.decode(await t.auf(zu)), 'rund');
    });

    test('falscher Schlüssel und verändertes Token: HMAC schlägt an', () async {
      final fremd = Tresor(v['verpack_schluessel_fernet'] as String);
      expect(() => fremd.auf(ascii.encode(m['datei_token'] as String)), throwsA(isA<FernetFehler>()));
      final roh = b64uLesen(m['datei_token'] as String);
      roh[30] ^= 1;
      expect(() => t.auf(ascii.encode(base64Url.encode(roh))), throwsA(isA<FernetFehler>()));
    });
  });
}
