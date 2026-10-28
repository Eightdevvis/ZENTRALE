// Abgleich zwischen Handy-Ablage und Mitte — konfliktfrei durch Bauart.
//
// Das Handy ist ein fremder Knoten (memory/betrieb/abgleich.md):
//   HOLEN   alles aus dem Inhaltsverzeichnis, was regeln.holen nennt
//           (Gespräche, Kontextpaket, Kalender, Zugangsdaten). Was dort
//           verschwindet (gelöscht), verschwindet auch hier.
//   BRINGEN nur in den eigenen Eingang: die eigenen Dateien (regeln.eigene),
//           den Kopf eines hier begonnenen Gesprächs, solange die Mitte
//           keinen hat, und neue Termine als ganze .ics (Vorschlag).
//   AUFRÄUMEN einen Termin-Vorschlag, sobald die Mitte ihn kennt (oder ihn
//           gelöscht hat), aus dem Eingang nehmen.
// Weil nie zwei Knoten dieselbe Datei schreiben, kann nichts überschrieben
// werden. Ein Merkzettel (abgleich/stand.json) hält fest, welche Fassung
// geholt und welche gebracht ist — so wandert nur, was sich geändert hat.

import 'dart:convert';
import 'dart:typed_data';

import '../ablage/ablage.dart';
import '../krypto/tresor.dart';
import 'mitte.dart';
import 'regeln.dart' as r;

const _merkPfad = 'abgleich/stand.json';
const zustandPfad = 'abgleich/zustand.json';

class Ergebnis {
  Ergebnis(this.geholt, this.gebracht, {this.mitteLeer = false});
  final int geholt;
  final int gebracht;

  /// Noch kein Rechner hat in die Mitte abgeglichen.
  final bool mitteLeer;
}

/// Was die Einstellungsseite über den Abgleich zeigt.
class AbgleichZustand {
  AbgleichZustand(this.daten);
  final Map<String, dynamic> daten;
  String? get letzterErfolg => daten['letzter_erfolg'] as String?;
  String? get letzterVersuch => daten['letzter_versuch'] as String?;
  String? get fehler => daten['fehler'] as String?;
  bool get kalenderInMitte => daten['kalender_in_mitte'] == true;
  int get geholt => daten['geholt'] as int? ?? 0;
  int get gebracht => daten['gebracht'] as int? ?? 0;

  static Future<AbgleichZustand> lesen(Ablage a) async {
    final t = await a.lesen(zustandPfad);
    try {
      return AbgleichZustand(t == null ? {} : (jsonDecode(t) as Map).cast<String, dynamic>());
    } catch (_) {
      return AbgleichZustand({});
    }
  }
}

class Abgleich {
  Abgleich(this.ablage, this.mitte, {this.knoten = r.knotenName, DateTime Function()? uhr})
      : _uhr = uhr ?? DateTime.now;

  final Ablage ablage;
  final Mitte mitte;
  final String knoten;
  final DateTime Function() _uhr;

  static Future<Map<String, dynamic>> _merkLesen(Ablage a) async {
    final t = await a.lesen(_merkPfad);
    if (t == null) return {'geholt': <String, dynamic>{}, 'gebracht': <String, dynamic>{}};
    try {
      final d = (jsonDecode(t) as Map).cast<String, dynamic>();
      return {
        'geholt': ((d['geholt'] as Map?) ?? {}).cast<String, dynamic>(),
        'gebracht': ((d['gebracht'] as Map?) ?? {}).cast<String, dynamic>(),
      };
    } catch (_) {
      return {'geholt': <String, dynamic>{}, 'gebracht': <String, dynamic>{}};
    }
  }

  /// Termine, die das Handy vorgeschlagen hat und die die Mitte noch nicht
  /// zurückgegeben hat („wartet auf Abgleich“) — Ablage-Pfade.
  static Future<Set<String>> wartend(Ablage a) async {
    final geholt = (await _merkLesen(a))['geholt'] as Map<String, dynamic>;
    return {
      for (final p in await a.alleDateien('kalender'))
        if (r.istTermin(p) && !geholt.containsKey(p)) p
    };
  }

  static Uint8List _bytes(String s) => Uint8List.fromList(utf8.encode(s));

  Future<Ergebnis> laufen() async {
    final jetzt = _uhr().toUtc().toIso8601String();
    try {
      final e = await _laufen();
      await _zustand({'letzter_versuch': jetzt, if (!e.mitteLeer) 'letzter_erfolg': jetzt,
          'fehler': e.mitteLeer ? 'Die Mitte ist noch leer — erst an einem Rechner abgleichen.' : null,
          'geholt': e.geholt, 'gebracht': e.gebracht});
      return e;
    } catch (f) {
      await _zustand({'letzter_versuch': jetzt, 'fehler': '$f'});
      rethrow;
    }
  }

  Future<void> _zustand(Map<String, dynamic> neu) async {
    final alt = (await AbgleichZustand.lesen(ablage)).daten;
    await ablage.schreiben(zustandPfad, jsonEncode({...alt, ...neu}));
  }

  Future<Ergebnis> _laufen() async {
    final merk = await _merkLesen(ablage);
    final geholt = merk['geholt'] as Map<String, dynamic>;
    final gebracht = merk['gebracht'] as Map<String, dynamic>;
    var nHolen = 0, nBringen = 0;

    final stand = await mitte.holen();
    if (stand.kennung == null) return Ergebnis(0, 0, mitteLeer: true);

    // ── Nach einer Neuinstallation: das Eigene aus dem Eingang zurück ──
    if (geholt.isEmpty && gebracht.isEmpty) {
      for (final MapEntry(key: mp, value: inhalt) in (await mitte.eingangLesen()).entries) {
        final ap = r.ablagePfad(mp);
        if (ap == null || await ablage.lesen(ap) != null) continue;
        await ablage.schreiben(ap, utf8.decode(inhalt, allowMalformed: true));
        gebracht[ap] = Tresor.sha(inhalt);
      }
    }

    // ── Holen ──
    final fern = <String, String>{}; // Ablage-Pfad → sha
    for (final MapEntry(key: mp, value: sha) in stand.dateien.entries) {
      final ap = r.ablagePfad(mp);
      if (ap != null && r.holen(ap)) fern[ap] = sha;
    }
    for (final MapEntry(key: ap, value: sha) in fern.entries) {
      if (r.eigene(ap, knoten) && await ablage.lesen(ap) != null) continue;
      if (geholt[ap] == sha) continue;
      final inhalt = await mitte.lesen(r.mittePfad(ap));
      await ablage.schreiben(ap, utf8.decode(inhalt, allowMalformed: true));
      geholt[ap] = sha;
      nHolen++;
    }
    // In der Mitte verschwunden → hier auch (nur, was von dort kam).
    for (final ap in geholt.keys.toList()) {
      if (fern.containsKey(ap)) continue;
      await ablage.loeschen(ap);
      geholt.remove(ap);
    }

    // ── Bringen ──
    final schreiben = <String, Uint8List>{};
    final entfernen = <String>{};
    final kandidaten = {
      ...await ablage.alleDateien('gespraeche'),
      ...await ablage.alleDateien('kalender'),
    };
    for (final ap in kandidaten) {
      final mp = r.mittePfad(ap);
      final bringen = r.eigene(ap, knoten) ||
          (r.istKopf(ap) && !fern.containsKey(ap)) ||
          (r.istTermin(ap) && !geholt.containsKey(ap));
      if (r.istTermin(ap) && stand.geloescht.contains(mp) && !geholt.containsKey(ap)) {
        // Vorschlag wurde übernommen und inzwischen gelöscht: weg damit.
        await ablage.loeschen(ap);
        if (stand.imEingang(mp)) entfernen.add(mp);
        gebracht.remove(ap);
        continue;
      }
      if (!bringen) {
        // Ein Termin-Vorschlag, den die Mitte jetzt kennt: Eingang aufräumen.
        if (r.istTermin(ap) && gebracht.containsKey(ap)) {
          if (stand.imEingang(mp)) entfernen.add(mp);
          gebracht.remove(ap);
        }
        continue;
      }
      final text = await ablage.lesen(ap);
      if (text == null) continue;
      final b = _bytes(text);
      final h = Tresor.sha(b);
      if (gebracht[ap] == h && stand.imEingang(mp)) continue;
      schreiben[mp] = b;
      gebracht[ap] = h;
      nBringen++;
    }
    // Gebrachte Termine, die es hier nicht mehr gibt (übernommen und danach
    // in der Mitte gelöscht): auch aus dem Eingang.
    for (final ap in gebracht.keys.toList()) {
      if (!r.istTermin(ap) || kandidaten.contains(ap)) continue;
      if (stand.imEingang(r.mittePfad(ap))) entfernen.add(r.mittePfad(ap));
      gebracht.remove(ap);
    }
    if (schreiben.isNotEmpty || entfernen.isNotEmpty) {
      await mitte.eingangSenden(schreiben, entfernen);
    }

    await ablage.schreiben(_merkPfad, jsonEncode({'geholt': geholt, 'gebracht': gebracht}));
    await _zustand({'kalender_in_mitte': fern.keys.any(r.istTermin)});
    return Ergebnis(nHolen, nBringen);
  }
}
