// Changes to EXISTING events the phone has proposed (edit, occurrence
// off/on, layer move, delete) — kept until a computer's receipt decides.
// memory/betrieb/abgleich_fremde_knoten.md "Termine vom Handy".
//
// New events stay as before (a file not yet in the cloud = a proposal);
// this register is only for files the cloud already has. It lives in the
// phone's own Ablage folder abgleich/ (never synced).
//
// Optimistic: the changed file is written into the Ablage at once (the
// calendar shows it with "wartet auf Abgleich"); the sync leaves protected
// paths alone until the receipt is there.

import 'dart:convert';

import '../ablage/ablage.dart';

const proposalsPath = 'abgleich/proposals.json';

enum ProposalState { pending, rejected }

class Proposal {
  Proposal({
    required this.target,
    this.from,
    required this.baseSha,
    this.base,
    this.delete = false,
    this.envelope,
    this.sentAs,
    this.state = ProposalState.pending,
    this.code,
    this.reason,
    this.cloudText,
  });

  /// Ablage path the change goes to (for a delete: the file itself).
  String target;

  /// Layer move: the Ablage path the file came from.
  String? from;

  /// sha256 of the cloud version the phone saw, and that version.
  String baseSha;
  String? base;
  bool delete;

  /// sha256 of the envelope plaintext sent; null = (re)send at next sync.
  String? envelope;

  /// Mitte path the envelope lies under (to clear it when the target moves).
  String? sentAs;
  ProposalState state;

  /// Rejected: reason code (core REASONS) and the computer's text.
  String? code, reason;

  /// Rejected: the cloud's current version (to show both).
  String? cloudText;

  Set<String> get paths => {target, ?from};

  Map<String, Object?> toJson() => {
        'target': target,
        'from': from,
        'basis_sha': baseSha,
        'basis': base,
        'delete': delete,
        'envelope': envelope,
        'sent_as': sentAs,
        'state': state.name,
        'code': code,
        'reason': reason,
        'cloud': cloudText,
      };

  static Proposal fromJson(Map<String, dynamic> j) => Proposal(
        target: j['target'] as String,
        from: j['from'] as String?,
        baseSha: j['basis_sha'] as String,
        base: j['basis'] as String?,
        delete: j['delete'] == true,
        envelope: j['envelope'] as String?,
        sentAs: j['sent_as'] as String?,
        state: ProposalState.values.where((s) => s.name == j['state']).firstOrNull ?? ProposalState.pending,
        code: j['code'] as String?,
        reason: j['reason'] as String?,
        cloudText: j['cloud'] as String?,
      );
}

class Proposals {
  Proposals(this.list);
  final List<Proposal> list;

  static Future<Proposals> load(Ablage a) async {
    final t = await a.lesen(proposalsPath);
    if (t == null) return Proposals([]);
    try {
      return Proposals([
        for (final x in (jsonDecode(t) as List)) Proposal.fromJson((x as Map).cast<String, dynamic>())
      ]);
    } catch (_) {
      return Proposals([]);
    }
  }

  Future<void> save(Ablage a) => a.schreiben(proposalsPath, jsonEncode([for (final p in list) p.toJson()]));

  /// The proposal touching [path] (as target or origin), if any.
  Proposal? touching(String path) => list.where((p) => p.paths.contains(path)).firstOrNull;

  /// Paths the sync must not overwrite or delete locally.
  Set<String> get protected => {for (final p in list) ...p.paths};
}
