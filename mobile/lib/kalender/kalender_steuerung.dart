// Die Kalender-Logik ohne Oberfläche: laden (nach jedem Abgleich), neuen
// Termin vorschlagen, Erinnerungen neu stellen, Überblick für die KI. Die
// Seiten zeichnen nur, was hier steht.

import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../ablage/ablage.dart';
import '../krypto/tresor.dart';
import '../mitte/abgleich.dart';
import '../mitte/proposals.dart';
import 'event_edit.dart';
import 'erinnerungen.dart';
import 'kalender.dart';
import 'termin_schreiben.dart';
import 'ueberblick.dart';
import 'zeit.dart';

class KalenderSteuerung extends ChangeNotifier {
  KalenderSteuerung({required this.ablage, this.erinnerungen, DateTime Function()? uhr, this.anstossen})
      : _uhr = uhr ?? jetztBerlin;

  final Ablage ablage;
  final ErinnerungsDienst? erinnerungen;

  /// Abgleich anstoßen, nachdem ein Termin dazukam (bringt ihn in den Eingang).
  final Future<void> Function()? anstossen;
  final DateTime Function() _uhr;

  Kalender kalender = Kalender.leer;

  /// Changes proposed from the phone (pending or rejected), as of [laden].
  Proposals proposals = Proposals([]);

  /// Rejected proposals: the phone's own version (target path → text).
  Map<String, String?> mineText = {};
  bool _gefragt = false;

  DateTime get jetzt => _uhr();

  Future<void> laden() async {
    proposals = await Proposals.load(ablage);
    mineText = {
      for (final p in proposals.list)
        if (p.state == ProposalState.rejected) p.target: await ablage.lesen(p.target)
    };
    kalender = await Kalender.laden(ablage, wartend: await Abgleich.wartend(ablage));
    notifyListeners();
    await _erinnerungenStellen();
  }

  Future<void> _erinnerungenStellen() async {
    final e = erinnerungen;
    if (e == null) return;
    try {
      final w = planen(kalender, jetzt);
      // Erlaubnis erst fragen, wenn es wirklich etwas zu erinnern gibt.
      if (w.isNotEmpty && !_gefragt) {
        _gefragt = true;
        await e.erlaubnisFragen();
      }
      await e.stellen(w);
    } catch (f) {
      debugPrint('Erinnerungen nicht gestellt: $f');
    }
  }

  /// Ebenen, in die das Handy eintragen darf (die es in der Mitte gibt).
  List<Ebene> get ebenenZumEintragen =>
      [for (final e in kalender.ebenen) if (e.name != ebeneRhythmus) e];

  /// Neuer Termin als Vorschlag: Datei in die Ablage (sofort sichtbar, „wartet
  /// auf Abgleich“), dann Abgleich → Eingang → ein Rechner übernimmt ihn.
  Future<String> eintragen(NeuerTermin t, {String ebene = ebeneTermine}) async {
    String uid;
    do {
      uid = neueUid();
    } while (kalender.uids.contains(uid));
    final pfad = '$kalenderOrdner/$ebene/${dateiName(uid)}';
    await ablage.schreiben(pfad, terminIcs(t, uid, DateTime.now().toUtc()));
    await laden();
    final a = anstossen;
    if (a != null) await a();
    return uid;
  }

  /// Für die KI: der Kalender der nächsten 14 Tage (null = keiner da).
  Future<String?> ueberblick() async {
    if (kalender.istLeer) await laden();
    return kalenderUeberblick(kalender, jetzt);
  }

  // ── Changing existing events (memory/betrieb/abgleich_fremde_knoten.md
  // "Termine vom Handy"). Each writes the new file at once (shown with
  // "wartet auf Abgleich"), records the proposal, and kicks the sync.

  /// The proposal touching the file of [v], if any.
  Proposal? proposalFor(Vorkommen v) {
    final path = v.kennung == null ? null : kalender.pathOf(v.kennung!);
    return path == null ? null : proposals.touching(path);
  }

  /// Rejected proposals (to show and let Sasha choose).
  List<Proposal> get rejected => [for (final p in proposals.list) if (p.state == ProposalState.rejected) p];

  /// Edit title/place/time (and optionally move to [layer]).
  Future<void> change(Vorkommen v, EventChange c, {String? layer}) async {
    final uid = v.kennung!, path = kalender.pathOf(uid)!;
    final text = await ablage.lesen(path);
    if (text == null) return;
    final neu = applyChange(text, uid, c, now: DateTime.now().toUtc(), series: v.serie);
    await _propose(uid, path, neu, layer: layer);
  }

  /// Switch the occurrence [v] of a series off or back on.
  Future<void> setOccurrenceOff(Vorkommen v, {required bool off}) async {
    final uid = v.kennung!, path = kalender.pathOf(uid)!;
    final text = await ablage.lesen(path);
    if (text == null) return;
    final start = kalender.entryOf(uid)?.daten['time'] as String?;
    final neu = setOccurrenceOffIn(text, uid, v.occurrenceDay, off: off, timeOfDay: start);
    await _propose(uid, path, neu);
  }

  /// Delete the whole event (series: the whole series).
  Future<void> delete(Vorkommen v) async {
    final uid = v.kennung!, path = kalender.pathOf(uid)!;
    await _propose(uid, path, null, delete: true);
  }

  /// Rejected: propose my version again on top of the cloud's current one.
  Future<void> keepMine(Proposal p) async {
    final cloud = p.cloudText;
    if (cloud == null) return; // gone in the cloud: only "take the cloud's" is possible
    p
      ..base = cloud
      ..baseSha = Tresor.sha(utf8.encode(cloud))
      ..state = ProposalState.pending
      ..envelope = null
      ..code = null
      ..reason = null
      ..cloudText = null;
    await _saveAndSync();
  }

  /// Rejected: drop my version, show the cloud's.
  Future<void> takeCloud(Proposal p) async {
    for (final x in p.paths) {
      await ablage.loeschen(x);
    }
    final cloud = p.cloudText;
    if (cloud != null) await ablage.schreiben(p.from ?? p.target, cloud);
    proposals.list.remove(p);
    await _saveAndSync();
  }

  Future<void> _propose(String uid, String path, String? text, {String? layer, bool delete = false}) async {
    final props = await Proposals.load(ablage);
    var p = props.touching(path);
    final seen = await Abgleich.seenSha(ablage, path);
    String targetFor(String current) {
      if (layer == null || current.split('/')[1] == layer) return current;
      return '$kalenderOrdner/$layer/${dateiName(uid)}';
    }

    if (p == null && seen == null) {
      // Own new event, not in the cloud yet: still a plain new proposal.
      final target = targetFor(path);
      if (target != path || delete) await ablage.loeschen(path);
      if (!delete) await ablage.schreiben(target, text!);
      return _reloadAndSync();
    }
    if (p == null) {
      p = Proposal(target: path, baseSha: seen!, base: await ablage.lesen(path));
      props.list.add(p);
    }
    final origin = p.from ?? p.target;
    for (final x in p.paths) {
      await ablage.loeschen(x);
    }
    if (delete) {
      p
        ..target = origin
        ..from = null
        ..delete = true;
    } else {
      final target = targetFor(p.target);
      p
        ..target = target
        ..from = target == origin ? null : origin
        ..delete = false;
      await ablage.schreiben(target, text!);
    }
    p
      ..state = ProposalState.pending
      ..envelope = null // an undecided envelope may be replaced
      ..code = null
      ..reason = null
      ..cloudText = null;
    proposals = props;
    await _saveAndSync();
  }

  Future<void> _saveAndSync() async {
    await proposals.save(ablage);
    await _reloadAndSync();
  }

  Future<void> _reloadAndSync() async {
    await laden();
    final a = anstossen;
    if (a != null) await a();
  }
}
