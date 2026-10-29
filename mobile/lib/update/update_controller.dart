// When and how the app updates itself — without UI (memory/system/zen_mobile.md
// "Self-update"). Checks on start and on the button in settings; downloads
// only when asked (and asks again on a metered network); verifies the SHA-256
// right before handing the file to Android, which asks the user once.
//
// The release comes from the cloud of the logged-in session only (no session,
// no check). A Play build or a Play-installed copy never updates itself.

import 'dart:io';

import 'package:flutter/foundation.dart';

import '../konto/konto.dart';
import 'release.dart';
import 'release_source.dart';
import 'update_platform.dart';

enum UpdateStatus {
  idle,
  disabled,
  notLoggedIn,
  checking,
  upToDate,
  noRelease,
  available,
  askMetered,
  downloading,
  verifying,
  needsPermission,
  installerOpened,
  failed,
}

class UpdateController extends ChangeNotifier {
  UpdateController({
    required this.platform,
    required this.session,
    ReleaseSource Function(Sitzung s)? sourceFor,
  }) : _sourceFor = sourceFor ?? ((s) => ReleaseSource(server: s.server, token: s.token));

  final UpdatePlatform platform;
  final Future<Sitzung?> Function() session;
  final ReleaseSource Function(Sitzung s) _sourceFor;

  UpdateStatus status = UpdateStatus.idle;
  InstalledApp? installed;
  Release? release;
  UpdateFailure? failure;

  /// Download progress 0…1 while [status] is downloading.
  double progress = 0;
  File? _file;
  ReleaseSource? _source;

  /// A newer release is known (drives the hint on the start screen).
  bool get hasUpdate {
    final r = release, i = installed;
    return r != null && i != null && i.selfUpdate && r.isNewerThan(i.versionCode);
  }

  bool get busy =>
      status == UpdateStatus.checking || status == UpdateStatus.downloading || status == UpdateStatus.verifying;

  void _set(UpdateStatus s, {UpdateFailure? failed}) {
    status = s;
    failure = failed;
    notifyListeners();
  }

  /// Ask the cloud for the current release. Never throws.
  Future<void> check() async {
    if (busy) return;
    try {
      installed ??= await platform.info();
    } catch (e) {
      debugPrint('update: no platform info ($e)');
      return _set(UpdateStatus.disabled);
    }
    if (!installed!.selfUpdate) return _set(UpdateStatus.disabled);
    final s = await session();
    if (s == null) return _set(UpdateStatus.notLoggedIn);
    _set(UpdateStatus.checking);
    try {
      final source = _source = _sourceFor(s);
      final r = await source.latest();
      release = r;
      if (r == null) return _set(UpdateStatus.noRelease);
      await _cleanUp(r);
      _set(r.isNewerThan(installed!.versionCode) ? UpdateStatus.available : UpdateStatus.upToDate);
    } on UpdateException catch (e) {
      debugPrint('update: $e');
      _set(UpdateStatus.failed, failed: e.failure);
    }
  }

  /// Download (asking first on a metered network), then install.
  Future<void> download({bool allowMetered = false}) async {
    final r = release, i = installed, source = _source;
    if (r == null || i == null || source == null || busy || !hasUpdate) return;
    final dir = Directory(i.updateDir);
    final cached = File('${dir.path}/${apkFileName(r)}');
    if (!await cached.exists()) {
      if (!allowMetered && await platform.isMetered()) return _set(UpdateStatus.askMetered);
      progress = 0;
      _set(UpdateStatus.downloading);
      try {
        _file = await source.download(r, dir, progress: (got, total) {
          progress = total == 0 ? 0 : got / total;
          notifyListeners();
        });
      } on UpdateException catch (e) {
        debugPrint('update: $e');
        return _set(UpdateStatus.failed, failed: e.failure);
      }
    } else {
      _file = cached;
    }
    await install();
  }

  /// Verify the downloaded file again and hand it to Android's installer.
  Future<void> install() async {
    final r = release, f = _file;
    if (r == null || f == null) return;
    if (!await platform.canInstall()) return _set(UpdateStatus.needsPermission);
    _set(UpdateStatus.verifying);
    if (!await matchesRelease(f, r)) {
      if (await f.exists()) await f.delete();
      _file = null;
      return _set(UpdateStatus.failed, failed: UpdateFailure.checksum);
    }
    try {
      await platform.install(f.path);
      _set(UpdateStatus.installerOpened);
    } catch (e) {
      debugPrint('update: installer ($e)');
      _set(UpdateStatus.failed, failed: UpdateFailure.install);
    }
  }

  /// Android's "install unknown apps" screen for this app. Afterwards the
  /// user taps Install again (the permission is read fresh each time).
  Future<void> openPermission() => platform.openInstallSettings();

  /// Back from the metered question without downloading.
  void later() {
    if (status == UpdateStatus.askMetered) _set(UpdateStatus.available);
  }

  /// Old downloads (other version codes, unfinished parts) go away.
  Future<void> _cleanUp(Release current) async {
    final dir = Directory(installed!.updateDir);
    if (!await dir.exists()) return;
    await for (final e in dir.list()) {
      if (e is File && !e.path.endsWith('/${apkFileName(current)}')) {
        try {
          await e.delete();
        } catch (_) {}
      }
    }
  }
}
