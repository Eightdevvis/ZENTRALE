// Die KI-Schnittstelle des Handys. Anbieter sind austauschbar (Strukturziel:
// „Anbieter, Modell, lokal oder Cloud sind Werte, keine eigenen Code-Wege"):
// die Chat-Steuerung kennt nur KiAnbieter, nie Anthropic direkt.

sealed class KiStueck {}

/// Ein Stück zusammengefasstes Denken (Anzeige wie „Denken" in der Claude-App).
class KiDenken extends KiStueck {
  KiDenken(this.text);
  final String text;
}

/// Ein Stück Antworttext.
class KiText extends KiStueck {
  KiText(this.text);
  final String text;
}

/// Fertig. grund: end_turn, max_tokens, refusal …
class KiEnde extends KiStueck {
  KiEnde(this.grund);
  final String? grund;
}

class KiFehler implements Exception {
  KiFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

abstract class KiAnbieter {
  /// Antwort als Strom. [verlauf] ist [{role, content}], älteste zuerst.
  /// Abbrechen = die Subscription kündigen.
  Stream<KiStueck> antworten({
    required String system,
    required List<Map<String, String>> verlauf,
    required String modell,
    required String effort,
  });
}
