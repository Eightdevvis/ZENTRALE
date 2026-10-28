// Geheimnisse des Handys: liegen im Android-Keystore (flutter_secure_storage),
// nie im Klartext in der Ablage. Hier: der von Hand eingetragene
// Claude-Schlüssel (Notbehelf; sonst kommt er nach dem Login über die Mitte).

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

  // Sitzung und Kontoschlüssel des ZENTRALE-Kontos liegen ebenfalls im
  // Keystore, eigener Eintrag: lib/konto/konto.dart (KeystoreSitzung).
}
