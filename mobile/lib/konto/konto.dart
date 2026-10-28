// Das ZENTRALE-Konto auf dem Handy: einmal anmelden mit Benutzername und
// Passwort, danach kommen Claude-Schlüssel, Gespräche, Kontext und Kalender
// von selbst (Sasha, 28.10.2026). Wie core/konto.anmelden:
//
//   POST /v1/vorab {name} → {salz, kdf}
//   Argon2id(passwort, salz) → hauptschluessel (im Isolate, lib/krypto)
//   POST /v1/sitzung {name, anmelde_schluessel, knoten: "handy"}
//        → {token, laeuft_ab, verpackt_passwort}
//   konto_schluessel = Fernet(verpack_schluessel).auf(verpackt_passwort)
//
// Das Passwort wird NIE gespeichert. Im Android-Keystore liegen nur Sitzung
// und konto_schluessel (Sitzungsspeicher). Abmelden löscht beides.

import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../krypto/fernet.dart';
import '../krypto/konto_schluessel.dart' as ks;
import '../mitte/cloud.dart';
import '../mitte/regeln.dart';

class KontoFehler implements Exception {
  KontoFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

class Sitzung {
  Sitzung({required this.server, required this.name, required this.token,
      required this.kontoSchluessel, this.laeuftAb});
  final String server, name, token, kontoSchluessel;
  final String? laeuftAb;

  Map<String, dynamic> alsJson() => {'format': 1, 'server': server, 'name': name, 'token': token,
      'laeuft_ab': laeuftAb, 'konto_schluessel': kontoSchluessel};

  static Sitzung? ausJson(String? t) {
    if (t == null) return null;
    try {
      final d = jsonDecode(t) as Map;
      return Sitzung(server: d['server'] as String, name: d['name'] as String,
          token: d['token'] as String, kontoSchluessel: d['konto_schluessel'] as String,
          laeuftAb: d['laeuft_ab'] as String?);
    } catch (_) {
      return null;
    }
  }
}

/// Wo die Sitzung liegt. Echt: Keystore; Tests: Speicher.
abstract class SitzungSpeicher {
  Future<Sitzung?> lesen();
  Future<void> schreiben(Sitzung? s);
}

class KeystoreSitzung implements SitzungSpeicher {
  KeystoreSitzung([FlutterSecureStorage? s]) : _s = s ?? const FlutterSecureStorage();
  final FlutterSecureStorage _s;
  static const _schluessel = 'konto_sitzung';

  @override
  Future<Sitzung?> lesen() async => Sitzung.ausJson(await _s.read(key: _schluessel));

  @override
  Future<void> schreiben(Sitzung? s) => s == null
      ? _s.delete(key: _schluessel)
      : _s.write(key: _schluessel, value: jsonEncode(s.alsJson()));
}

class SpeicherSitzung implements SitzungSpeicher {
  Sitzung? s;
  @override
  Future<Sitzung?> lesen() async => s;
  @override
  Future<void> schreiben(Sitzung? neu) async => s = neu;
}

/// Benutzername wie core/konto.name_lesen (getrimmt, klein).
String nameLesen(String name) {
  if (name.contains('@')) {
    throw KontoFehler('Keine Mail nötig — ZENTRALE-Konten sind anonym. Den Benutzernamen eingeben.');
  }
  final n = name.trim().toLowerCase();
  if (!RegExp(r'^[a-z][a-z0-9._-]{2,31}$').hasMatch(n)) {
    throw KontoFehler('Ein Benutzername hat 3–32 Zeichen (a–z, 0–9, „.“, „_“, „-“) '
        'und beginnt mit einem Buchstaben.');
  }
  return n;
}

class Konto {
  Konto(this.speicher, {CloudClient Function(String? token)? client})
      : _client = client ?? ((t) => CloudClient(token: t));

  final SitzungSpeicher speicher;
  final CloudClient Function(String? token) _client;

  Future<Sitzung?> sitzung() => speicher.lesen();

  /// Anmelden und Sitzung + konto_schluessel ablegen.
  Future<Sitzung> anmelden(String name, String passwort) async {
    name = nameLesen(name);
    if (passwort.isEmpty) throw KontoFehler('Bitte das Passwort eingeben.');
    final c = _client(null);
    try {
      final v = await c.post('/v1/vorab', {'name': name});
      final salz = b64uLesen('${v['salz']}');
      final haupt = await ks.hauptschluessel(passwort, salz, ks.Kdf.lesen(v['kdf']));
      Map<String, dynamic> d;
      try {
        d = await c.post('/v1/sitzung',
            {'name': name, 'anmelde_schluessel': await ks.anmeldeSchluessel(haupt), 'knoten': knotenName});
      } on CloudFehler catch (e) {
        if (e.status == 401 || e.status == 403) throw KontoFehler('Benutzername oder Passwort falsch.');
        rethrow;
      }
      final k = await ks.auspacken(await ks.verpackSchluessel(haupt), '${d['verpackt_passwort']}');
      final s = Sitzung(server: c.basis, name: name, token: '${d['token']}',
          kontoSchluessel: k, laeuftAb: d['laeuft_ab'] as String?);
      await speicher.schreiben(s);
      return s;
    } on CloudFehler catch (e) {
      throw KontoFehler(e.text);
    } on ks.KontoSchluesselFehler catch (e) {
      throw KontoFehler(e.meldung);
    } on FormatException {
      throw KontoFehler('Die Cloud schickte unlesbare Anmeldewerte.');
    }
  }

  /// Beim Server abmelden (wenn erreichbar) und alles vom Handy löschen.
  Future<void> abmelden() async {
    final s = await speicher.lesen();
    if (s != null) {
      try {
        await _client(s.token).delete('/v1/sitzung');
      } catch (_) {
        // offline abmelden geht trotzdem; die Sitzung läuft dort ab
      }
    }
    await speicher.schreiben(null);
  }
}
