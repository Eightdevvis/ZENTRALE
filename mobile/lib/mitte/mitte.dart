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

import 'dart:convert';
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

/// The envelope plaintext for the inbox — the ONE place it is built, so the
/// sync can compare its sha256 with the receipt (memory/betrieb/
/// abgleich_fremde_knoten.md "Termine vom Handy"). Key order as documented.
Uint8List envelope(String pfad, Uint8List? inhalt,
    {String? baseSha, Uint8List? base, bool delete = false}) {
  final m = <String, Object>{'format': 1, 'pfad': pfad};
  if (inhalt != null) m['inhalt'] = base64.encode(inhalt);
  if (baseSha != null) m['basis_sha'] = baseSha;
  if (base != null) m['basis'] = base64.encode(base);
  if (delete) m['loeschen'] = true;
  return Uint8List.fromList(utf8.encode(jsonEncode(m)));
}

/// A computer's decision on one proposal (in inhalt.enc under `eingang.<knoten>.<pfad>`).
class Receipt {
  Receipt({required this.envelope, required this.result, this.code, this.reason, this.at});
  final String envelope; // sha256 hex of the envelope plaintext
  final String result; // angenommen | abgelehnt | erledigt
  final String? code, reason, at;

  bool get rejected => result == 'abgelehnt';

  static Receipt? parse(Object? o) {
    if (o is! Map) return null;
    final u = o['umschlag'], e = o['ergebnis'];
    if (u is! String || e is! String) return null;
    return Receipt(envelope: u, result: e, code: o['code'] as String?, reason: o['grund'] as String?,
        at: o['am'] as String?);
  }
}

/// Der Stand der Mitte, wie ein fremder Knoten ihn sieht.
class MitteStand {
  MitteStand({
    required this.kennung,
    required this.dateien,
    required this.geloescht,
    required this.imEingang,
    this.receipts = const {},
  });

  /// Receipts for this node's proposals: Mitte path → receipt.
  final Map<String, Receipt> receipts;

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
  /// [envelopes]: ready envelope plaintexts (from [envelope]) per path —
  /// changes, deletions, layer moves with basis_sha.
  Future<void> eingangSenden(Map<String, Uint8List> schreiben, Set<String> entfernen,
      {Map<String, Uint8List> envelopes = const {}});
}

/// Mitte im Speicher — für Tests. Spielt einen Rechner nach: was im Eingang
/// liegt, sieht man in [eingang]; [rechnerSchreibt] legt eine Datei ins
/// Inhaltsverzeichnis.
class SpeicherMitte implements Mitte {
  final Map<String, Uint8List> dateien = {};
  final Map<String, Uint8List> eingang = {};

  /// Every envelope plaintext in the inbox (as a computer would decrypt it).
  final Map<String, Uint8List> envelopes = {};

  /// Receipts a computer has written (tests set them).
  final Map<String, Receipt> receipts = {};
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
        imEingang: envelopes.containsKey,
        receipts: {...receipts},
      );

  @override
  Future<Uint8List> lesen(String pfad) async =>
      dateien[pfad] ?? (throw MitteFehler('In der Mitte fehlt $pfad.'));

  @override
  Future<Map<String, Uint8List>> eingangLesen() async => {...eingang};

  @override
  Future<void> eingangSenden(Map<String, Uint8List> schreiben, Set<String> entfernen,
      {Map<String, Uint8List> envelopes = const {}}) async {
    for (final MapEntry(:key, :value) in schreiben.entries) {
      eingang[key] = value;
      this.envelopes[key] = envelope(key, value);
    }
    for (final MapEntry(:key, :value) in envelopes.entries) {
      this.envelopes[key] = value;
      final i = (jsonDecode(utf8.decode(value)) as Map)['inhalt'];
      if (i is String) {
        eingang[key] = base64.decode(i);
      } else {
        eingang.remove(key);
      }
    }
    for (final p in entfernen) {
      if (schreiben.containsKey(p) || envelopes.containsKey(p)) continue;
      eingang.remove(p);
      this.envelopes.remove(p);
      receipts.remove(p); // the receipt falls once the envelope is gone
    }
    staende++;
  }
}
