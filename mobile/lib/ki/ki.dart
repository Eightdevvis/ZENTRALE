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

/// Ohne Claude-Schlüssel kann das Handy nicht antworten. Der Grund entscheidet,
/// was Sasha tun soll: nicht angemeldet → erst anmelden (dann kommt der
/// Schlüssel von selbst über die Mitte); angemeldet → der Schlüssel fehlt im
/// Tresor von ZENTRALE, das richtet man am Rechner. Der Chat zeigt dazu einen
/// Knopf zu den Einstellungen.
class SchluesselFehlt extends KiFehler {
  SchluesselFehlt({required this.angemeldet})
      : super(angemeldet
            ? 'Der Claude-Schlüssel fehlt im ZENTRALE-Tresor. Am Rechner in '
                'ZENTRALE eintragen — das Handy holt ihn beim nächsten Abgleich.'
            : 'Melde dich zuerst an — Einstellungen → Konto.');

  final bool angemeldet;
}

abstract class KiAnbieter {
  /// Antwort als Strom. [verlauf] ist [{role, content}], älteste zuerst.
  /// [wechselnd] = was sich von Zug zu Zug ändert (heute: der Kalender der
  /// nächsten Tage) — steht HINTER dem festen Prompt und außerhalb des
  /// Caches, damit der große feste Teil gecacht bleibt.
  /// Abbrechen = die Subscription kündigen.
  Stream<KiStueck> antworten({
    required String system,
    String? wechselnd,
    required List<Map<String, String>> verlauf,
    required String modell,
    required String effort,
  });
}
