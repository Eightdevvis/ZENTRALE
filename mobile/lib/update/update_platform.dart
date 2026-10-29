// What the update needs from Android (MainActivity.kt, channel
// "de.zentrale.zen_mobile/update"): the installed version, whether this copy
// may update itself, the "install unknown apps" permission, metered network,
// and handing a verified APK to the package installer. Tests use a fake.

import 'package:flutter/services.dart';

class InstalledApp {
  const InstalledApp({
    required this.versionName,
    required this.versionCode,
    required this.selfUpdate,
    required this.updateDir,
  });

  final String versionName;
  final int versionCode;

  /// False for a Play build (Gradle zentrale.distribution=play) and for a copy
  /// Google Play installed — those are updated by Play only.
  final bool selfUpdate;

  /// The only folder the installer may read from (FileProvider, update_paths.xml).
  final String updateDir;
}

abstract class UpdatePlatform {
  Future<InstalledApp> info();
  Future<bool> canInstall();
  Future<void> openInstallSettings();
  Future<bool> isMetered();
  Future<void> install(String apkPath);
}

class AndroidUpdatePlatform implements UpdatePlatform {
  const AndroidUpdatePlatform();

  static const _channel = MethodChannel('de.zentrale.zen_mobile/update');

  @override
  Future<InstalledApp> info() async {
    final d = (await _channel.invokeMapMethod<String, dynamic>('info'))!;
    return InstalledApp(
      versionName: '${d['versionName'] ?? ''}',
      versionCode: (d['versionCode'] as num).toInt(),
      selfUpdate: d['selfUpdate'] == true,
      updateDir: d['updateDir'] as String,
    );
  }

  @override
  Future<bool> canInstall() async => await _channel.invokeMethod<bool>('canInstall') ?? false;

  @override
  Future<void> openInstallSettings() => _channel.invokeMethod<void>('openInstallSettings');

  @override
  Future<bool> isMetered() async {
    try {
      return await _channel.invokeMethod<bool>('isMetered') ?? false;
    } on PlatformException {
      return false;
    }
  }

  @override
  Future<void> install(String apkPath) => _channel.invokeMethod<void>('install', {'path': apkPath});
}
