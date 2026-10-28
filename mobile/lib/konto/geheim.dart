// Zugangsdaten des Adapters lesen (data/adapter/geheim.enc, core/adapter_geheim.py):
//
//   {"format": "zentrale-geheim/1",
//    "eintraege": {"ki/ANTHROPIC_API_KEY": {"zu": "konto", "wert": "<Fernet-Token>"}}}
//
// Die Datei kommt über die Mitte (dort noch einmal als Ganzes verschlüsselt)
// und liegt in der Ablage — jeder Eintrag bleibt mit dem konto_schluessel
// verschlüsselt, der nur im Keystore liegt. Entschlüsselt wird erst, wenn ein
// Wert gebraucht wird, und nichts davon wird abgelegt. Einträge mit
// zu: "geraet" gehören einem anderen Gerät — das Handy kann sie nicht lesen.

import 'dart:convert';

import '../ablage/ablage.dart';
import '../einstellungen/einstellungen.dart';
import '../krypto/tresor.dart';
import 'konto.dart';

const geheimPfad = 'adapter/geheim.enc';
const kiAnthropic = 'ki/ANTHROPIC_API_KEY';

/// Klartext eines Eintrags oder null (fehlt, fremdes Gerät, falscher Schlüssel).
Future<String?> geheimLesen(Ablage ablage, String kontoSchluessel, String name) async {
  final t = await ablage.lesen(geheimPfad);
  if (t == null) return null;
  try {
    final e = ((jsonDecode(t) as Map)['eintraege'] as Map)[name];
    if (e is! Map || e['zu'] != 'konto') return null;
    final w = await Tresor(kontoSchluessel).eintragAuf('${e['wert']}');
    return w.trim().isEmpty ? null : w.trim();
  } catch (_) {
    return null;
  }
}

/// Der Claude-Schlüssel: von Hand eingetragen (Vorrang, als Notbehelf) —
/// sonst aus den Zugangsdaten des Adapters, sobald angemeldet und
/// abgeglichen. So steht nach dem Login ohne Abtippen eine KI da.
Future<String?> Function() kiSchluessel(Einstellungen e, Ablage ablage, Konto konto) => () async {
      final hand = await e.anthropicSchluessel();
      if (hand != null && hand.isNotEmpty) return hand;
      final s = await konto.sitzung();
      return s == null ? null : geheimLesen(ablage, s.kontoSchluessel, kiAnthropic);
    };
