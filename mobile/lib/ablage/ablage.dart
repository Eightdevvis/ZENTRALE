// Ablage: Dateien des Handys, Pfade wie unter ZENTRALE/data/.
//
// Das Handy hält einen Spiegel der Teile von data/, die es braucht
// (gespraeche/**, mobil/kontext.json). Alles darüber — Gespräche, Kontext,
// Abgleich — redet nur über diese Schnittstelle, nie direkt mit dem
// Dateisystem. So laufen die Tests im Speicher und die App auf der Platte.

import 'dart:io';

abstract class Ablage {
  /// Inhalt der Datei oder null, wenn es sie nicht gibt.
  Future<String?> lesen(String pfad);

  /// Datei ganz ersetzen (legt Ordner an).
  Future<void> schreiben(String pfad, String inhalt);

  /// Eine Zeile anhängen — so wächst eine Rechner-jsonl, nie anders.
  Future<void> anhaengen(String pfad, String zeile);

  /// Namen der Einträge (Dateien und Ordner) direkt in [ordner].
  Future<List<String>> auflisten(String ordner);

  /// Alle Dateipfade unter [ordner], rekursiv, relativ zur Wurzel.
  Future<List<String>> alleDateien(String ordner);
}

/// Die echte Ablage im App-Speicher des Handys.
class PlattenAblage implements Ablage {
  PlattenAblage(this.wurzel);

  final Directory wurzel;

  File _datei(String pfad) {
    if (pfad.contains('..')) throw ArgumentError('Pfad verlässt die Ablage: $pfad');
    return File('${wurzel.path}/$pfad');
  }

  @override
  Future<String?> lesen(String pfad) async {
    final f = _datei(pfad);
    return await f.exists() ? f.readAsString() : null;
  }

  @override
  Future<void> schreiben(String pfad, String inhalt) async {
    final f = _datei(pfad);
    await f.parent.create(recursive: true);
    // Erst daneben schreiben, dann umbenennen: ein Absturz hinterlässt
    // nie eine halbe Datei.
    final tmp = File('${f.path}.tmp');
    await tmp.writeAsString(inhalt, flush: true);
    await tmp.rename(f.path);
  }

  @override
  Future<void> anhaengen(String pfad, String zeile) async {
    final f = _datei(pfad);
    await f.parent.create(recursive: true);
    await f.writeAsString(zeile, mode: FileMode.append, flush: true);
  }

  @override
  Future<List<String>> auflisten(String ordner) async {
    final d = Directory('${wurzel.path}/$ordner');
    if (!await d.exists()) return [];
    return [
      await for (final e in d.list()) e.uri.pathSegments.where((s) => s.isNotEmpty).last
    ];
  }

  @override
  Future<List<String>> alleDateien(String ordner) async {
    final d = Directory('${wurzel.path}/$ordner');
    if (!await d.exists()) return [];
    final raus = <String>[];
    await for (final e in d.list(recursive: true)) {
      if (e is File && !e.path.endsWith('.tmp')) {
        raus.add(e.path.substring(wurzel.path.length + 1));
      }
    }
    return raus;
  }
}

/// Ablage im Speicher — für Tests.
class SpeicherAblage implements Ablage {
  final Map<String, String> dateien = {};

  @override
  Future<String?> lesen(String pfad) async => dateien[pfad];

  @override
  Future<void> schreiben(String pfad, String inhalt) async => dateien[pfad] = inhalt;

  @override
  Future<void> anhaengen(String pfad, String zeile) async =>
      dateien[pfad] = (dateien[pfad] ?? '') + zeile;

  @override
  Future<List<String>> auflisten(String ordner) async {
    final vorne = '$ordner/';
    return {
      for (final p in dateien.keys)
        if (p.startsWith(vorne)) p.substring(vorne.length).split('/').first
    }.toList();
  }

  @override
  Future<List<String>> alleDateien(String ordner) async =>
      [for (final p in dateien.keys) if (p.startsWith('$ordner/')) p];
}
