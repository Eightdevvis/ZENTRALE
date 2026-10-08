// Geheimnisse des Handys: liegen im Android-Keystore (flutter_secure_storage),
// nie in der Ablage — die wandert in die Mitte.

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class Einstellungen {
  Einstellungen([FlutterSecureStorage? speicher])
      : _s = speicher ?? const FlutterSecureStorage();

  final FlutterSecureStorage _s;

  static const _anthropic = 'anthropic_key';

  Future<String?> anthropicSchluessel() => _s.read(key: _anthropic);

  Future<void> anthropicSetzen(String? wert) => wert == null || wert.trim().isEmpty
      ? _s.delete(key: _anthropic)
      : _s.write(key: _anthropic, value: wert.trim());

  // Mitte (GitHub-Token, Abgleich-Schlüssel) kommt hierher, sobald das
  // Format der Mitte steht (memory/betrieb/abgleich.md).
}
