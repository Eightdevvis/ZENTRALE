// The release manifest of the phone app, as GET /v1/phone/release sends it
// (server/src/phone.ts, server/openapi.yaml "PhoneRelease"). Parsing is strict:
// anything odd is a FormatException, never a half-trusted release.

final _sha256 = RegExp(r'^[0-9a-f]{64}$');
final _versionName = RegExp(r'^[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}$');

/// Upper bound for an APK (the cloud accepts at most 96 MiB).
const maxApkBytes = 96 * 1024 * 1024;

class Release {
  const Release({
    required this.version,
    required this.versionCode,
    required this.sha256,
    required this.size,
    this.notes = '',
    this.publishedAt,
  });

  final String version;
  final int versionCode;
  final String sha256;
  final int size;
  final String notes;
  final DateTime? publishedAt;

  factory Release.fromJson(Map<String, dynamic> d) {
    final version = d['version'];
    final code = d['version_code'];
    final sha = d['sha256'];
    final size = d['size'];
    final notes = d['notes'] ?? '';
    if (version is! String || !_versionName.hasMatch(version)) {
      throw const FormatException('release: bad version');
    }
    if (code is! int || code < 1) throw const FormatException('release: bad version_code');
    if (sha is! String || !_sha256.hasMatch(sha)) throw const FormatException('release: bad sha256');
    if (size is! int || size < 1 || size > maxApkBytes) throw const FormatException('release: bad size');
    if (notes is! String) throw const FormatException('release: bad notes');
    final at = d['published_at'];
    return Release(
      version: version,
      versionCode: code,
      sha256: sha,
      size: size,
      notes: notes,
      publishedAt: at is String ? DateTime.tryParse(at) : null,
    );
  }

  /// Newer means a higher Android versionCode — the name is only for people.
  bool isNewerThan(int installedCode) => versionCode > installedCode;
}
