// Das Kontextpaket: wer die KI ist, was sie über Sasha weiß, welches Modell.
//
// Den System-Prompt baut der Kern (Python) — das Handy baut ihn NICHT nach,
// sonst gäbe es zwei Fassungen derselben KI. Der Kern legt ihn beim Abgleich
// fertig als mobil/kontext.json in die Mitte (core/mobil_kontext.py, baut
// die ASSISTANT-Seite). Das Handy hängt nur an, was nur hier gilt.

import 'dart:convert';

import '../ablage/ablage.dart';

const kontextPfad = 'mobil/kontext.json';

/// Wie core/providers.py + ai_backends: Modell und Denk-Tiefe der Cloud-Schiene.
const standardModell = 'claude-sonnet-5';
const standardEffort = 'low';

const _handyAbsatz = '''

## Wo du gerade läufst
Du läufst auf Sashas Handy (ZEN-MOBILE), unterwegs. Hier hast du KEINE Werkzeuge:
keinen Kalender, keine Ablage, kein Web, keine Listen. Fragt Sasha nach etwas, das
du nur mit einem Werkzeug wissen könntest (z. B. „was steht heute an"), sag ehrlich,
dass du es von hier aus nicht sehen kannst — rate nie.''';

const _minimalPrompt =
    'Du bist ZENTRALE, Sashas persönlicher Assistent. Antworte auf Deutsch, kurz und klar.';

class Kontext {
  Kontext({
    required this.systemKern,
    required this.anbieter,
    required this.modell,
    required this.effort,
    this.stand,
  });

  final String systemKern;
  final String anbieter;
  final String modell;
  final String effort;

  /// Wann der Kern das Paket gebaut hat; null = Notbetrieb ohne Paket.
  final String? stand;

  bool get ausDemKern => stand != null;
  String get system => systemKern + _handyAbsatz;

  static Kontext get notbetrieb => Kontext(
      systemKern: _minimalPrompt, anbieter: 'claude',
      modell: standardModell, effort: standardEffort);

  static Future<Kontext> laden(Ablage ablage) async {
    final t = await ablage.lesen(kontextPfad);
    if (t == null) return notbetrieb;
    try {
      final d = jsonDecode(t) as Map<String, dynamic>;
      final system = d['system'] as String?;
      if (system == null || system.trim().isEmpty) return notbetrieb;
      return Kontext(
        systemKern: system,
        anbieter: d['anbieter'] as String? ?? 'claude',
        modell: d['modell'] as String? ?? standardModell,
        effort: d['effort'] as String? ?? standardEffort,
        stand: d['stand'] as String? ?? '?',
      );
    } catch (_) {
      return notbetrieb;
    }
  }
}
