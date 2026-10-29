// The self-update in settings (and on its own page from the start-screen
// hint): installed version, status, check / download / permission / install.
// Draws only; the logic is in UpdateController. Text from lib/l10n.

import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import 'release_source.dart';
import 'update_controller.dart';

class UpdateSection extends StatelessWidget {
  const UpdateSection({super.key, required this.controller});

  final UpdateController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: controller,
        builder: (context, _) => _build(context, AppLocalizations.of(context)),
      );

  String? _failureText(AppLocalizations t, UpdateFailure? f) => switch (f) {
        UpdateFailure.network => t.updateFailedNetwork,
        UpdateFailure.checksum => t.updateFailedChecksum,
        UpdateFailure.server => t.updateFailedServer,
        UpdateFailure.install => t.updateFailedInstall,
        null => null,
      };

  String? _statusText(AppLocalizations t) {
    final c = controller;
    return switch (c.status) {
      UpdateStatus.idle => null,
      UpdateStatus.disabled => t.updateDisabled,
      UpdateStatus.notLoggedIn => t.updateNotLoggedIn,
      UpdateStatus.checking => t.updateChecking,
      UpdateStatus.upToDate => t.updateUpToDate,
      UpdateStatus.noRelease => t.updateNoRelease,
      UpdateStatus.available || UpdateStatus.askMetered => t.updateAvailable(c.release!.version),
      UpdateStatus.downloading => t.updateDownloading((c.progress * 100).floor()),
      UpdateStatus.verifying => t.updateVerifying,
      UpdateStatus.needsPermission => t.updateNeedsPermission,
      UpdateStatus.installerOpened => t.updateInstallerOpened,
      UpdateStatus.failed => _failureText(t, c.failure),
    };
  }

  Widget _build(BuildContext context, AppLocalizations t) {
    final c = controller;
    final i = c.installed;
    final r = c.release;
    final status = _statusText(t);
    final error = c.status == UpdateStatus.failed;
    final buttons = <Widget>[
      if (c.status == UpdateStatus.askMetered) ...[
        FilledButton(onPressed: () => c.download(allowMetered: true), child: Text(t.updateDownloadAnyway)),
        TextButton(onPressed: c.later, child: Text(t.updateLater)),
      ] else if (c.status == UpdateStatus.needsPermission) ...[
        FilledButton(onPressed: c.openPermission, child: Text(t.updateOpenPermission)),
        OutlinedButton(onPressed: c.install, child: Text(t.updateInstall)),
      ] else if (c.status == UpdateStatus.installerOpened) ...[
        OutlinedButton(onPressed: c.install, child: Text(t.updateInstall)),
      ] else if (c.hasUpdate && !c.busy) ...[
        FilledButton(onPressed: c.download, child: Text(t.updateDownload)),
      ] else if (c.status != UpdateStatus.disabled) ...[
        OutlinedButton(onPressed: c.busy ? null : c.check, child: Text(t.updateCheck)),
      ],
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      ListTile(
        contentPadding: EdgeInsets.zero,
        leading: c.busy
            ? SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                    strokeWidth: 2, value: c.status == UpdateStatus.downloading ? c.progress : null))
            : Icon(c.hasUpdate ? Icons.system_update_outlined : Icons.verified_outlined),
        title: Text(i == null ? '…' : t.updateInstalled(i.versionName, i.versionCode)),
        subtitle: Text(
          [
            ?status,
            if (c.hasUpdate && r != null && r.notes.isNotEmpty) t.updateNotes(r.notes),
            if (c.status == UpdateStatus.askMetered && r != null)
              t.updateMetered((r.size / (1024 * 1024)).ceil()),
          ].join('\n'),
          style: error ? TextStyle(color: Theme.of(context).colorScheme.error) : null,
        ),
      ),
      Wrap(spacing: 8, runSpacing: 8, children: buttons),
    ]);
  }
}

/// The update on its own page — opened from the hint on the start screen.
class UpdatePage extends StatelessWidget {
  const UpdatePage({super.key, required this.controller});

  final UpdateController controller;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(AppLocalizations.of(context).updateTitle)),
        body: ListView(padding: const EdgeInsets.all(16), children: [UpdateSection(controller: controller)]),
      );
}

/// A small, calm dot on the start screen while a newer version is known.
/// Nothing at all otherwise.
class UpdateHint extends StatelessWidget {
  const UpdateHint({super.key, required this.controller, required this.onTap});

  final UpdateController controller;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: controller,
        builder: (context, _) {
          if (!controller.hasUpdate) return const SizedBox.shrink();
          final color = Theme.of(context).colorScheme.primary;
          final label = AppLocalizations.of(context).updateHint;
          return Semantics(
            button: true,
            label: label,
            child: Tooltip(
              message: label,
              child: InkResponse(
                onTap: onTap,
                radius: 24,
                child: SizedBox(
                  width: 48,
                  height: 48,
                  child: Center(
                    child: Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: color,
                        boxShadow: [BoxShadow(color: color.withValues(alpha: .55), blurRadius: 10, spreadRadius: 2)],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      );
}
