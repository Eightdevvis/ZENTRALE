// Where releases come from: the ZENTRALE cloud the phone is logged in to,
// with its own session (contract: server/src/phone.ts). The APK address is
// built from the version code on the same server — a URL inside the manifest
// would never be followed. The download is streamed to a file and hashed on
// the way; a wrong size or SHA-256 deletes the file.

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;

import 'release.dart';

enum UpdateFailure { network, checksum, server, install }

class UpdateException implements Exception {
  UpdateException(this.failure, [this.detail = '']);
  final UpdateFailure failure;
  final String detail;
  @override
  String toString() => 'UpdateException(${failure.name}: $detail)';
}

class ReleaseSource {
  ReleaseSource({required String server, required this.token, http.Client? client})
      : server = server.replaceAll(RegExp(r'/+$'), ''),
        _c = client ?? http.Client();

  final String server;
  final String token;
  final http.Client _c;

  Map<String, String> get _headers =>
      {'Authorization': 'Bearer $token', 'User-Agent': 'zentrale-handy'};

  /// The published release, or null if there is none yet.
  Future<Release?> latest() async {
    http.Response r;
    try {
      r = await _c
          .get(Uri.parse('$server/v1/phone/release'), headers: {..._headers, 'Accept': 'application/json'})
          .timeout(const Duration(seconds: 30));
    } catch (e) {
      throw UpdateException(UpdateFailure.network, '$e');
    }
    if (r.statusCode == 404) return null;
    if (r.statusCode != 200) throw UpdateException(UpdateFailure.network, 'HTTP ${r.statusCode}');
    try {
      return Release.fromJson((jsonDecode(utf8.decode(r.bodyBytes)) as Map).cast<String, dynamic>());
    } catch (e) {
      throw UpdateException(UpdateFailure.server, '$e');
    }
  }

  /// Download the APK of [r] into [dir] and verify it. → the verified file.
  Future<File> download(Release r, Directory dir, {void Function(int received, int total)? progress}) async {
    await dir.create(recursive: true);
    final target = File('${dir.path}/${apkFileName(r)}');
    final part = File('${target.path}.part');
    final req = http.Request('GET', Uri.parse('$server/v1/phone/release/${r.versionCode}.apk'))
      ..headers.addAll(_headers);
    http.StreamedResponse resp;
    try {
      resp = await _c.send(req).timeout(const Duration(seconds: 30));
    } catch (e) {
      throw UpdateException(UpdateFailure.network, '$e');
    }
    if (resp.statusCode != 200) {
      await resp.stream.drain<void>();
      throw UpdateException(UpdateFailure.network, 'HTTP ${resp.statusCode}');
    }
    final out = part.openWrite();
    final digest = _DigestSink();
    final hasher = sha256.startChunkedConversion(digest);
    var received = 0;
    try {
      await for (final chunk in resp.stream.timeout(const Duration(seconds: 60))) {
        received += chunk.length;
        if (received > r.size) throw UpdateException(UpdateFailure.checksum, 'larger than announced');
        hasher.add(chunk);
        out.add(chunk);
        progress?.call(received, r.size);
      }
      hasher.close();
      await out.close();
    } catch (e) {
      await out.close().catchError((_) {});
      if (await part.exists()) await part.delete();
      if (e is UpdateException) rethrow;
      throw UpdateException(UpdateFailure.network, '$e');
    }
    if (received != r.size || '${digest.value}' != r.sha256) {
      await part.delete();
      throw UpdateException(UpdateFailure.checksum, 'size $received, sha256 ${digest.value}');
    }
    return part.rename(target.path);
  }
}

String apkFileName(Release r) => 'zentrale-${r.versionCode}.apk';

/// SHA-256 of a whole file, off the UI thread (an APK is ~55 MB).
Future<String> sha256OfFile(String path) => Isolate.run(() async {
      final digest = await sha256.bind(File(path).openRead()).first;
      return '$digest';
    });

/// True if [file] is exactly the APK the manifest describes.
Future<bool> matchesRelease(File file, Release r) async =>
    await file.exists() && await file.length() == r.size && await sha256OfFile(file.path) == r.sha256;

class _DigestSink implements Sink<Digest> {
  Digest? value;
  @override
  void add(Digest data) => value = data;
  @override
  void close() {}
}
