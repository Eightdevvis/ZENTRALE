// The detail sheet of one occurrence: what it is, its sync state, and what
// the phone can do with it — edit (incl. layer), delete, switch one
// occurrence of a series off/on, and for a rejected change: show both
// versions and let Sasha pick.

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../mitte/proposals.dart';
import 'eintrag_seite.dart';
import 'kalender.dart';
import 'kalender_steuerung.dart';
import 'termin_lesen.dart';

/// Translate a core reason code (core/abgleich_vorschlaege.REASONS).
String reasonText(AppLocalizations l, String? code) => switch (code) {
      'not_found' => l.reasonNotFound,
      'delete_needs_base' => l.reasonDeleteNeedsBase,
      'changed_not_deleted' => l.reasonChangedNotDeleted,
      'unreadable' => l.reasonUnreadable,
      'one_uid' => l.reasonOneUid,
      'no_master' => l.reasonNoMaster,
      'name_taken' => l.reasonNameTaken,
      'deleted_in_cloud' => l.reasonDeletedInCloud,
      'no_layer' => l.reasonNoLayer,
      'bad_name' => l.reasonBadName,
      'uid_twice' => l.reasonUidTwice,
      'other_name' => l.reasonOtherName,
      'target_taken' => l.reasonTargetTaken,
      'needs_base' => l.reasonNeedsBase,
      'base_unknown' => l.reasonBaseUnknown,
      'merge_unreadable' => l.reasonMergeUnreadable,
      'conflict' => l.reasonConflict,
      'same_file' => l.reasonSameFile,
      'conflict_changed' => l.reasonConflictChanged,
      'conflict_deleted' => l.reasonConflictDeleted,
      _ => l.reasonUnknown(code ?? '?'),
    };

/// One line about an .ics version: title, day, time (for "show both").
String versionSummary(AppLocalizations l, String? text) {
  if (text == null) return l.calendarCloudGone;
  try {
    final s = stueckeLesen(text).first;
    final d = s.daten;
    final time = d['time'] as String?;
    final day = d['tag'] as String? ?? d['seit'] as String? ?? '';
    return [
      d['label'] ?? '',
      if (day.isNotEmpty) day,
      time == null ? l.calendarAllDayShort : '$time${d['ende'] != null ? '–${d['ende']}' : ''}',
      if (d['ort'] != null) d['ort'],
    ].join(' · ');
  } catch (_) {
    return '?';
  }
}

void showEventSheet(BuildContext context, Vorkommen v, KalenderSteuerung s) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => EventSheet(v: v, steuerung: s),
  );
}

class EventSheet extends StatelessWidget {
  const EventSheet({super.key, required this.v, required this.steuerung});
  final Vorkommen v;
  final KalenderSteuerung steuerung;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final k = steuerung.kalender;
    final scheme = Theme.of(context).colorScheme;
    final layer = k.ebene(v.ebene)?.titel ?? v.ebene;
    final p = steuerung.proposalFor(v);
    final muted = TextStyle(fontSize: 13, color: scheme.onSurfaceVariant);
    final canChange = v.kennung != null && k.pathOf(v.kennung!) != null && !v.deadline && v.ebene != ebeneRhythmus;
    final time = v.zeit == null ? l.calendarAllDayShort : '${v.zeit}${v.ende != null ? '–${v.ende}' : ''}';

    Future<void> run(Future<void> Function() f) async {
      Navigator.of(context).pop();
      await f();
    }

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(v.label,
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  decoration: v.switchedOff ? TextDecoration.lineThrough : null)),
          const SizedBox(height: 6),
          Text([
            '${v.tag.day}.${v.tag.month}.${v.tag.year}',
            time,
            layer,
            if (v.serie) l.calendarRecurring,
            if (v.switchedOff) l.calendarSwitchedOff,
          ].join(' · ')),
          if (v.ort != null) Text(v.ort!),
          if (p?.state == ProposalState.pending || v.wartet) ...[
            const SizedBox(height: 10),
            Row(children: [
              Icon(Icons.cloud_upload_outlined, size: 16, color: scheme.onSurfaceVariant),
              const SizedBox(width: 6),
              Expanded(child: Text(l.calendarPendingHint, style: muted)),
            ]),
          ],
          if (p != null && p.state == ProposalState.rejected)
            RejectedBox(proposal: p, steuerung: steuerung, onDone: () => Navigator.of(context).pop()),
          const SizedBox(height: 12),
          if (canChange)
            Wrap(spacing: 8, runSpacing: 4, children: [
              if (!v.switchedOff)
                FilledButton.tonalIcon(
                  key: const ValueKey('event-edit'),
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  label: Text(l.calendarEdit),
                  onPressed: () {
                    final nav = Navigator.of(context);
                    nav.pop();
                    nav.push(MaterialPageRoute<void>(
                        builder: (_) => EintragSeite(steuerung: steuerung, editing: v)));
                  },
                ),
              if (v.serie)
                OutlinedButton.icon(
                  key: const ValueKey('event-occurrence'),
                  icon: Icon(v.switchedOff ? Icons.event_available_outlined : Icons.event_busy_outlined, size: 18),
                  label: Text(v.switchedOff ? l.calendarOccurrenceOn : l.calendarOccurrenceOff),
                  onPressed: () => run(() => steuerung.setOccurrenceOff(v, off: !v.switchedOff)),
                ),
              OutlinedButton.icon(
                key: const ValueKey('event-delete'),
                icon: const Icon(Icons.delete_outline, size: 18),
                label: Text(v.serie ? l.calendarDeleteSeries : l.calendarDelete),
                onPressed: () async {
                  final ok = await showDialog<bool>(
                    context: context,
                    builder: (c) => AlertDialog(
                      content: Text(l.calendarDeleteConfirm(v.label)),
                      actions: [
                        TextButton(onPressed: () => Navigator.of(c).pop(false), child: Text(l.calendarCancel)),
                        FilledButton(
                            key: const ValueKey('event-delete-confirm'),
                            onPressed: () => Navigator.of(c).pop(true),
                            child: Text(l.calendarDelete)),
                      ],
                    ),
                  );
                  if (ok == true && context.mounted) await run(() => steuerung.delete(v));
                },
              ),
            ]),
        ]),
      ),
    );
  }
}

/// A rejected change: the reason, both versions, and the two choices.
class RejectedBox extends StatelessWidget {
  const RejectedBox({super.key, required this.proposal, required this.steuerung, this.onDone});
  final Proposal proposal;
  final KalenderSteuerung steuerung;
  final VoidCallback? onDone;

  @override
  Widget build(BuildContext context) {
    final l = AppLocalizations.of(context);
    final scheme = Theme.of(context).colorScheme;
    final p = proposal;
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        border: Border.all(color: scheme.error),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(l.calendarRejected(reasonText(l, p.code)),
            style: TextStyle(color: scheme.error, fontWeight: FontWeight.w600)),
        const SizedBox(height: 6),
        Text(l.calendarMine(p.delete ? l.calendarDeletedHere : versionSummary(l, _mine(p)))),
        Text(p.cloudText == null ? l.calendarCloudGone : l.calendarCloud(versionSummary(l, p.cloudText))),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 4, children: [
          if (p.cloudText != null)
            FilledButton.tonal(
              key: const ValueKey('rejected-keep-mine'),
              onPressed: () {
                onDone?.call();
                steuerung.keepMine(p);
              },
              child: Text(l.calendarKeepMine),
            ),
          OutlinedButton(
            key: const ValueKey('rejected-take-cloud'),
            onPressed: () {
              onDone?.call();
              steuerung.takeCloud(p);
            },
            child: Text(l.calendarTakeCloud),
          ),
        ]),
      ]),
    );
  }

  String? _mine(Proposal p) => steuerung.mineText[p.target];
}
