// Abgleich zwischen Handy-Ablage und Mitte — konfliktfrei durch Bauart.
//
// Das Handy ist ein fremder Knoten (memory/betrieb/abgleich_fremde_knoten.md):
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
import 'proposals.dart';
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

/// Zeilen zweier .jsonl-Fassungen vereinen: erst alle der Cloud, dann die von
/// hier, die dort fehlen. Die Gespräche ordnen ohnehin nach `ts`.
String zeilenVereinen(String cloud, String hier) {
  final zeilen = const LineSplitter().convert(cloud).where((z) => z.trim().isNotEmpty).toList();
  final da = zeilen.toSet();
  for (final z in const LineSplitter().convert(hier)) {
    if (z.trim().isNotEmpty && da.add(z)) zeilen.add(z);
  }
  return zeilen.isEmpty ? '' : '${zeilen.join('\n')}\n';
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
    final props = await Proposals.load(a);
    final pending = {
      for (final p in props.list)
        if (p.state == ProposalState.pending) p.target
    };
    return {
      for (final p in await a.alleDateien('kalender'))
        if (r.istTermin(p) && (!geholt.containsKey(p) || pending.contains(p))) p
    };
  }

  /// sha of the cloud version this phone last fetched for [ap] (the basis
  /// of a change), or null if the file did not come from the cloud.
  static Future<String?> seenSha(Ablage a, String ap) async =>
      ((await _merkLesen(a))['geholt'] as Map<String, dynamic>)[ap] as String?;

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
    final entfernen = <String>{};

    // ── Receipts: a computer has decided on a proposed change ──
    final props = await Proposals.load(ablage);
    for (final p in [...props.list]) {
      final sent = p.sentAs;
      if (p.envelope == null || sent == null) continue;
      final rc = stand.receipts[sent];
      if (rc == null || rc.envelope != p.envelope) continue;
      entfernen.add(sent); // decided: clear it from the inbox
      p.sentAs = null;
      if (rc.rejected) {
        p
          ..state = ProposalState.rejected
          ..code = rc.code
          ..reason = rc.reason;
        final cloud = r.mittePfad(p.from ?? p.target);
        p.cloudText = stand.dateien.containsKey(cloud)
            ? utf8.decode(await mitte.lesen(cloud), allowMalformed: true)
            : null;
      } else {
        props.list.remove(p);
        geholt.remove(p.target); // fetch the cloud's merged version
      }
    }
    final protect = props.protected;

    // ── Erster Lauf (neu installiert oder erst jetzt angemeldet): das Eigene
    // aus dem Eingang zurück. Grundsatz (abgleich.md): die Cloud wird nie
    // überschrieben. Gibt es eine eigene Datei hier UND im Eingang, gewinnt
    // nicht still die von hier: eine .jsonl bekommt die Zeilen beider
    // (erst die aus der Cloud), alles andere nimmt die Fassung der Cloud.
    if (geholt.isEmpty && gebracht.isEmpty) {
      for (final MapEntry(key: mp, value: inhalt) in (await mitte.eingangLesen()).entries) {
        final ap = r.ablagePfad(mp);
        if (ap == null) continue;
        final fern = utf8.decode(inhalt, allowMalformed: true);
        final hier = await ablage.lesen(ap);
        if (hier == null || hier == fern) {
          if (hier == null) await ablage.schreiben(ap, fern);
          gebracht[ap] = Tresor.sha(inhalt);
          continue;
        }
        // Beide verschieden: zusammenlegen; gebracht bleibt leer → geht hinaus.
        await ablage.schreiben(ap, ap.endsWith('.jsonl') ? zeilenVereinen(fern, hier) : fern);
      }
    }

    // ── Holen ──
    final fern = <String, String>{}; // Ablage-Pfad → sha
    for (final MapEntry(key: mp, value: sha) in stand.dateien.entries) {
      final ap = r.ablagePfad(mp);
      if (ap != null && r.holen(ap)) fern[ap] = sha;
    }
    for (final MapEntry(key: ap, value: sha) in fern.entries) {
      if (protect.contains(ap)) continue; // own change waits for its receipt
      if (r.eigene(ap, knoten) && await ablage.lesen(ap) != null) continue;
      if (geholt[ap] == sha) continue;
      final inhalt = await mitte.lesen(r.mittePfad(ap));
      await ablage.schreiben(ap, utf8.decode(inhalt, allowMalformed: true));
      geholt[ap] = sha;
      nHolen++;
    }
    // In der Mitte verschwunden → hier auch (nur, was von dort kam).
    for (final ap in geholt.keys.toList()) {
      if (fern.containsKey(ap) || protect.contains(ap)) continue;
      await ablage.loeschen(ap);
      geholt.remove(ap);
    }

    // ── Bringen ──
    final schreiben = <String, Uint8List>{};
    final kandidaten = {
      ...await ablage.alleDateien('gespraeche'),
      ...await ablage.alleDateien('kalender'),
    };
    for (final ap in kandidaten) {
      if (protect.contains(ap)) continue; // sent as a change below
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
      if (!r.istTermin(ap) || kandidaten.contains(ap) || protect.contains(ap)) continue;
      if (stand.imEingang(r.mittePfad(ap))) entfernen.add(r.mittePfad(ap));
      gebracht.remove(ap);
    }
    // Changes to existing events: one envelope each, with basis_sha.
    final envs = <String, Uint8List>{};
    for (final p in props.list) {
      if (p.state != ProposalState.pending || p.envelope != null) continue;
      final mp = r.mittePfad(p.target);
      Uint8List? inhalt;
      if (!p.delete) {
        final t = await ablage.lesen(p.target);
        if (t == null) continue;
        inhalt = _bytes(t);
      }
      final env = envelope(mp, inhalt,
          baseSha: p.baseSha, base: p.base == null ? null : _bytes(p.base!), delete: p.delete);
      envs[mp] = env;
      if (p.sentAs != null && p.sentAs != mp) entfernen.add(p.sentAs!);
      p
        ..sentAs = mp
        ..envelope = Tresor.sha(env);
      nBringen++;
    }
    if (schreiben.isNotEmpty || entfernen.isNotEmpty || envs.isNotEmpty) {
      await mitte.eingangSenden(schreiben, entfernen, envelopes: envs);
    }
    await props.save(ablage);

    await ablage.schreiben(_merkPfad, jsonEncode({'geholt': geholt, 'gebracht': gebracht}));
    await _zustand({'kalender_in_mitte': fern.keys.any(r.istTermin)});
    return Ergebnis(nHolen, nBringen);
  }
}
