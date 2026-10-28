// Fernet — das Format, mit dem ZENTRALE alles in der Mitte verschlüsselt
// (memory/betrieb/abgleich_fremde_knoten.md, „Verschlüsseln (Fernet, Version 0x80)").
//
//   token = base64url( 0x80 ‖ zeit(8, BE) ‖ iv(16) ‖ AES-128-CBC(PKCS7) ‖ HMAC-SHA256 )
//   Schlüssel = 32 Bytes (base64url mit '='): 0–15 Signieren, 16–31 Verschlüsseln
//
// Nachgebaut aus Grundbausteinen von package:cryptography statt eines fertigen
// Fernet-Pakets: so ist Byte für Byte sichtbar, was passiert, und der Prüfstein
// (test/krypto_test.dart gegen die Testvektoren des Kerns) deckt alles ab.
// Entschlüsseln prüft ZUERST den HMAC — ein falscher Schlüssel oder ein
// verändertes Token kommt nie bis zu AES.

import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

class FernetFehler implements Exception {
  FernetFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

/// base64url lesen, mit oder ohne '='-Auffüllung.
Uint8List b64uLesen(String text) {
  final t = text.trim();
  return base64Url.decode(t + '=' * ((4 - t.length % 4) % 4));
}

/// base64url ohne Auffüllung (alles, was an den Server geht).
String b64u(List<int> roh) => base64Url.encode(roh).replaceAll('=', '');

class Fernet {
  Fernet._(this._sign, this._enc, this.zeile);

  /// Aus der Schlüssel-Zeile (44 Zeichen, base64url mit '=').
  factory Fernet(String zeile) {
    zeile = zeile.trim();
    Uint8List roh;
    try {
      roh = b64uLesen(zeile);
    } on FormatException {
      throw FernetFehler('Kein gültiger Schlüssel (base64url erwartet).');
    }
    if (roh.length != 32) throw FernetFehler('Ein Schlüssel hat 32 Bytes, nicht ${roh.length}.');
    return Fernet._(roh.sublist(0, 16), roh.sublist(16), zeile);
  }

  final Uint8List _sign;
  final Uint8List _enc;

  /// Die Schlüssel-Zeile, wie sie gespeichert wird (für die versteckten Namen).
  final String zeile;

  static final _aes = AesCbc.with128bits(macAlgorithm: MacAlgorithm.empty);
  static final _hmac = Hmac.sha256();
  static final _zufall = Random.secure();

  /// Verschlüsseln. [zeit] und [iv] nur für Testvektoren — im echten Betrieb
  /// IMMER zufällig (ein fester IV verriete gleiche Klartexte).
  Future<String> zu(List<int> klartext, {int? zeit, List<int>? iv}) async {
    iv ??= List<int>.generate(16, (_) => _zufall.nextInt(256));
    final sekunden = zeit ?? DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final box = await _aes.encrypt(klartext, secretKey: SecretKey(_enc), nonce: iv);
    final kopf = ByteData(9)
      ..setUint8(0, 0x80)
      ..setUint64(1, sekunden);
    final teil = BytesBuilder(copy: false)
      ..add(kopf.buffer.asUint8List())
      ..add(iv)
      ..add(box.cipherText);
    final ohneMac = teil.toBytes();
    final mac = await _hmac.calculateMac(ohneMac, secretKey: SecretKey(_sign));
    return base64Url.encode([...ohneMac, ...mac.bytes]);
  }

  /// Entschlüsseln: erst HMAC (sonst FernetFehler), dann AES-CBC, PKCS7 weg.
  /// Die Zeit im Token wird nicht geprüft (wie im Kern).
  Future<Uint8List> auf(String token) async {
    Uint8List roh;
    try {
      roh = b64uLesen(token);
    } on FormatException {
      throw FernetFehler('Kein Fernet-Token.');
    }
    if (roh.length < 1 + 8 + 16 + 16 + 32 || roh[0] != 0x80) {
      throw FernetFehler('Kein Fernet-Token.');
    }
    final teil = roh.sublist(0, roh.length - 32);
    final mac = roh.sublist(roh.length - 32);
    final soll = await _hmac.calculateMac(teil, secretKey: SecretKey(_sign));
    if (!_gleich(mac, soll.bytes)) {
      throw FernetFehler('Der Schlüssel passt nicht (Prüfsumme falsch).');
    }
    final iv = teil.sublist(9, 25);
    final chiffrat = teil.sublist(25);
    try {
      final klar = await _aes.decrypt(SecretBox(chiffrat, nonce: iv, mac: Mac.empty),
          secretKey: SecretKey(_enc));
      return Uint8List.fromList(klar);
    } catch (_) {
      throw FernetFehler('Das Token ist beschädigt.');
    }
  }

  /// Zeitkonstant vergleichen — ein früher Abbruch verriete, ab welchem Byte
  /// eine gefälschte Prüfsumme falsch ist.
  static bool _gleich(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var d = 0;
    for (var i = 0; i < a.length; i++) {
      d |= a[i] ^ b[i];
    }
    return d == 0;
  }
}
