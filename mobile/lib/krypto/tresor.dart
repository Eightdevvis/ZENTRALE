// Der Tresor: ver- und entschlüsseln mit dem Schlüssel der Mitte und die
// versteckten Dateinamen — genau wie core/abgleich_schluessel.Tresor.
//
//   namen_schluessel = SHA256("zentrale-abgleich-namen" ‖ 0x00 ‖ <44 Zeichen>)
//   name(pfad)       = erste 32 Zeichen von hex(HMAC-SHA256(namen_schluessel, pfad))
//
// Über die Cloud ist der Schlüssel der konto_schluessel (memory/betrieb/abgleich.md
// „Die Mitte als Cloud"): dasselbe Fernet-Format, dieselben Namen.

import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as c;

import 'fernet.dart';

class Tresor {
  Tresor(String schluesselZeile)
      : _fernet = Fernet(schluesselZeile),
        _namen = c.sha256
            .convert([...utf8.encode('zentrale-abgleich-namen'), 0, ...ascii.encode(schluesselZeile.trim())])
            .bytes;

  final Fernet _fernet;
  final List<int> _namen;

  Future<Uint8List> zu(List<int> klar) async => ascii.encode(await _fernet.zu(klar));

  Future<Uint8List> auf(List<int> geheim) => _fernet.auf(ascii.decode(geheim, allowInvalid: true));

  /// Versteckter Name in der Mitte für einen Pfad relativ zum ZENTRALE-Ordner.
  String name(String pfad) =>
      c.Hmac(c.sha256, _namen).convert(utf8.encode(pfad)).toString().substring(0, 32);

  /// Der Klartext-Prüfwert, den inhalt.enc je Datei trägt.
  static String sha(List<int> klar) => c.sha256.convert(klar).toString();

  /// Ein einzelner Eintrag aus data/adapter/geheim.enc ({zu: konto, wert:
  /// Fernet-Token}) — derselbe Schlüssel, nur als Text.
  Future<String> eintragAuf(String wert) async => utf8.decode(await _fernet.auf(wert));
}
