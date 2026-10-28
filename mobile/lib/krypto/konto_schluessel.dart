// Das Schlüssel-Schema des Kontos, nur Rechnen — nachgebaut aus der Doku
// (memory/hub/knoten_beitritt.md „Schlüssel", Vorbild core/konto_schluessel.py),
// Prüfstein: test/daten/konto_testvektoren.json (Kopie der Datei des Kerns).
//
//   passwort ─Argon2id(salz, t, m, p)→ hauptschluessel (32 B)
//   hauptschluessel ─HKDF info="zentrale/anmelden/v1"→ anmelde_schluessel → Server
//   hauptschluessel ─HKDF info="zentrale/verpacken/v1"→ verpack_schluessel (Fernet)
//   konto_schluessel = Fernet(verpack_schluessel).auf(verpackt_passwort)
//
// Festlegungen des Kerns (gleich übernommen): HKDF-SHA256 ohne Salz (32
// Null-Bytes), Länge 32; Passwort UTF-8 nach NFC; Untergrenze m ≥ 19456 KiB —
// schwächere Werte nimmt das Handy auch vom Server NICHT an (ein böser
// Server bekäme sonst billig durchprobierbare anmelde_schluessel).
//
// Argon2id mit 64 MiB dauert auf dem Handy Sekunden. Es läuft darum in einem
// eigenen Isolate (Isolate.run) — die Oberfläche friert nicht ein; das Paket
// verteilt die Spuren (p=4) zusätzlich auf eigene Isolates.

import 'dart:convert';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:cryptography/dart.dart';

import 'fernet.dart';

const kdfMinM = 19456;
const infoAnmelden = 'zentrale/anmelden/v1';
const infoVerpacken = 'zentrale/verpacken/v1';

class KontoSchluesselFehler implements Exception {
  KontoSchluesselFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

class Kdf {
  const Kdf({required this.t, required this.m, required this.p});
  final int t, m, p;

  /// Die KDF-Werte vom Server prüfen (wie konto_schluessel.kdf_lesen).
  factory Kdf.lesen(Object? roh) {
    final d = roh is Map ? roh : const {};
    final name = '${d['name'] ?? d['art'] ?? 'argon2id'}'.toLowerCase();
    if (name != 'argon2id') {
      throw KontoSchluesselFehler('Unbekannte Schlüsselableitung „$name“ (erwartet argon2id).');
    }
    int zahl(List<String> namen, int vorgabe) {
      for (final n in namen) {
        final w = d[n];
        if (w is int) return w;
        if (w is String && int.tryParse(w) != null) return int.parse(w);
        if (w != null) throw KontoSchluesselFehler('Der Server schickte unlesbare KDF-Werte.');
      }
      return vorgabe;
    }

    final t = zahl(['t', 'iterations'], 3);
    final m = zahl(['m', 'memory'], 65536);
    final p = zahl(['p', 'parallelism', 'lanes'], 4);
    if (t < 1 || p < 1 || m < 8 * p) {
      throw KontoSchluesselFehler('Der Server schickte ungültige KDF-Werte.');
    }
    if (m < kdfMinM) {
      throw KontoSchluesselFehler('Der Server verlangt eine schwächere Ableitung als erlaubt '
          '($m KiB < $kdfMinM KiB) — abgelehnt.');
    }
    return Kdf(t: t, m: m, p: p);
  }
}

/// Unicode-NFC für das Passwort. Dart hat keine eingebaute Normalisierung;
/// getippte Passwörter auf Android kommen als NFC (vorkomponiert) an. Was
/// nicht reines NFC sein kann, lehnen wir lieber ab, als still einen anderen
/// Schlüssel zu rechnen: kombinierende Zeichen (U+0300–U+036F) stehen nur in
/// NFD-Text — dann ein klarer Fehler statt „falsches Passwort“.
List<int> passwortBytes(String passwort) {
  if (RegExp('[̀-ͯ]').hasMatch(passwort)) {
    throw KontoSchluesselFehler(
        'Das Passwort enthält zerlegte Sonderzeichen — bitte die Umlaute direkt tippen.');
  }
  return utf8.encode(passwort);
}

Future<Uint8List> _argon2(List<int> passwort, List<int> salz, Kdf kdf) async {
  final a = DartArgon2id(
      parallelism: kdf.p, memory: kdf.m, iterations: kdf.t, hashLength: 32);
  final k = await a.deriveKey(secretKey: SecretKey(passwort), nonce: salz);
  return Uint8List.fromList(await k.extractBytes());
}

/// Hauptschlüssel aus Passwort und Salz — im eigenen Isolate.
Future<Uint8List> hauptschluessel(String passwort, List<int> salz, Kdf kdf) {
  final roh = passwortBytes(passwort);
  final s = List<int>.from(salz);
  return Isolate.run(() => _argon2(roh, s, kdf));
}

Future<Uint8List> hkdf(List<int> eingabe, String info) async {
  final h = Hkdf(hmac: Hmac.sha256(), outputLength: 32);
  final k = await h.deriveKey(
      secretKey: SecretKey(eingabe), nonce: List<int>.filled(32, 0), info: utf8.encode(info));
  return Uint8List.fromList(await k.extractBytes());
}

Future<String> anmeldeSchluessel(List<int> haupt) async => b64u(await hkdf(haupt, infoAnmelden));

/// Der Fernet-Schlüssel zum Auspacken (base64url MIT Auffüllung).
Future<String> verpackSchluessel(List<int> haupt) async =>
    base64Url.encode(await hkdf(haupt, infoVerpacken));

/// verpackt_passwort → konto_schluessel (die 44 Zeichen), oder Fehler.
Future<String> auspacken(String fernetSchluessel, String verpackt) async {
  Uint8List k;
  try {
    k = await Fernet(fernetSchluessel).auf(verpackt);
  } on FernetFehler {
    throw KontoSchluesselFehler('Der Kontoschlüssel ließ sich mit diesem Passwort nicht öffnen.');
  }
  final zeile = ascii.decode(k, allowInvalid: true);
  try {
    Fernet(zeile);
  } on FernetFehler {
    throw KontoSchluesselFehler('Der Kontoschlüssel vom Server ist beschädigt.');
  }
  return zeile;
}
