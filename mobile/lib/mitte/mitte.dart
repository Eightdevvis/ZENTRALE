// Die Mitte: der Ort, über den alle Knoten abgleichen.
//
// Heute ist das ein privates Git-Repo (Eightdevvis/data), später der
// Heimserver. Das Handy kennt nur diese Schnittstelle — wer die Mitte ist,
// ist ein Wert in den Einstellungen, kein eigener Code-Weg.
//
// Pfade sind Klartext-Pfade wie unter data/ („gespraeche/<id>/handy.jsonl").
// Ver- und Entschlüsselung ist Sache der Umsetzung (eigene Schicht darunter);
// das Format legt der Abgleich-Plan fest: memory/betrieb/abgleich.md.

abstract class Mitte {
  /// Alle Dateien unter [ordner] mit einer Fassungs-Kennung (Hash, Version).
  /// Ändert sich die Kennung, hat sich die Datei geändert.
  Future<Map<String, String>> stand(String ordner);

  Future<String?> lesen(String pfad);

  /// Schreibt und gibt die neue Fassungs-Kennung zurück — damit der
  /// Abgleich das eben Gebrachte beim nächsten Mal nicht wieder holt.
  Future<String> schreiben(String pfad, String inhalt);
}

/// Keine Mitte eingerichtet: das Handy arbeitet allein weiter, nichts geht verloren,
/// beim ersten Abgleich mit einer echten Mitte wandert alles hoch.
class KeineMitte implements Mitte {
  const KeineMitte();
  @override
  Future<Map<String, String>> stand(String ordner) async => {};
  @override
  Future<String?> lesen(String pfad) async => null;
  @override
  Future<String> schreiben(String pfad, String inhalt) async => '';
}

/// Mitte im Speicher — für Tests.
class SpeicherMitte implements Mitte {
  final Map<String, String> dateien = {};
  int _zaehler = 0;
  final Map<String, String> _fassung = {};

  @override
  Future<Map<String, String>> stand(String ordner) async => {
        for (final p in dateien.keys)
          if (p.startsWith('$ordner/') || p == ordner) p: _fassung[p]!
      };

  @override
  Future<String?> lesen(String pfad) async => dateien[pfad];

  @override
  Future<String> schreiben(String pfad, String inhalt) async {
    dateien[pfad] = inhalt;
    return _fassung[pfad] = '${++_zaehler}';
  }
}
