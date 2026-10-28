// Die Mitte: der Ort, über den alle Knoten abgleichen (memory/betrieb/abgleich.md).
//
// Heute die ZENTRALE-Cloud (HttpMitte, lib/mitte/http_mitte.dart), später der
// Heimserver — das Handy kennt nur diese Schnittstelle. Wer die Mitte ist,
// ist ein Wert, kein eigener Code-Weg.
//
// Das Handy ist ein FREMDER Knoten: es liest das Inhaltsverzeichnis und die
// Dateien, schreibt aber nie hinein — nur in seinen Eingang knoten/handy/.
// Pfade hier sind relativ zum ZENTRALE-Ordner („data/gespraeche/…“), genau
// wie im Inhaltsverzeichnis. Verschlüsselung ist Sache der Umsetzung.

import 'dart:typed_data';

import '../krypto/tresor.dart';

class MitteFehler implements Exception {
  MitteFehler(this.meldung, {this.abgemeldet = false});
  final String meldung;

  /// Die Sitzung gilt nicht mehr (401) — neu anmelden.
  final bool abgemeldet;
  @override
  String toString() => meldung;
}

/// Der Stand der Mitte, wie ein fremder Knoten ihn sieht.
class MitteStand {
  MitteStand({
    required this.kennung,
    required this.dateien,
    required this.geloescht,
    required this.imEingang,
  });

  /// null = noch kein Rechner hat abgeglichen (dann schreibt das Handy nichts).
  final String? kennung;

  /// Pfad → SHA-256 des Klartexts (aus inhalt.enc).
  final Map<String, String> dateien;

  /// Pfade mit Grabstein (in der Mitte gelöscht).
  final Set<String> geloescht;

  /// Liegt für diesen Pfad gerade eine Datei im eigenen Eingang?
  final bool Function(String pfad) imEingang;

  static MitteStand get leer =>
      MitteStand(kennung: null, dateien: {}, geloescht: {}, imEingang: (_) => false);
}

abstract class Mitte {
  Future<MitteStand> holen();

  /// Eine Datei des zuletzt geholten Stands — Prüfwert geprüft.
  Future<Uint8List> lesen(String pfad);

  /// Der eigene Eingang, entschlüsselt: Pfad → Inhalt (nach Neuinstallation).
  Future<Map<String, Uint8List>> eingangLesen();

  /// In den eigenen Eingang: [schreiben] ganze Dateien, [entfernen] Pfade,
  /// deren Vorschlag sich erledigt hat. Ein Aufruf = ein neuer Stand.
  Future<void> eingangSenden(Map<String, Uint8List> schreiben, Set<String> entfernen);
}

/// Mitte im Speicher — für Tests. Spielt einen Rechner nach: was im Eingang
/// liegt, sieht man in [eingang]; [rechnerSchreibt] legt eine Datei ins
/// Inhaltsverzeichnis.
class SpeicherMitte implements Mitte {
  final Map<String, Uint8List> dateien = {};
  final Map<String, Uint8List> eingang = {};
  final Set<String> geloescht = {};
  String? kennung = 'k1';
  int staende = 0;

  void rechnerSchreibt(String pfad, List<int> inhalt) {
    dateien[pfad] = Uint8List.fromList(inhalt);
    geloescht.remove(pfad);
  }

  void rechnerLoescht(String pfad) {
    dateien.remove(pfad);
    geloescht.add(pfad);
  }

  @override
  Future<MitteStand> holen() async => MitteStand(
        kennung: kennung,
        dateien: {for (final e in dateien.entries) e.key: Tresor.sha(e.value)},
        geloescht: {...geloescht},
        imEingang: eingang.containsKey,
      );

  @override
  Future<Uint8List> lesen(String pfad) async =>
      dateien[pfad] ?? (throw MitteFehler('In der Mitte fehlt $pfad.'));

  @override
  Future<Map<String, Uint8List>> eingangLesen() async => {...eingang};

  @override
  Future<void> eingangSenden(Map<String, Uint8List> schreiben, Set<String> entfernen) async {
    eingang.addAll(schreiben);
    entfernen.forEach(eingang.remove);
    staende++;
  }
}
