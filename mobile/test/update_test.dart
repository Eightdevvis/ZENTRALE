// Self-update (lib/update/): manifest parsing, version compare, download with
// SHA-256 check, the controller's steps, and the UI — against a fake cloud
// (MockClient, same contract as cloud/src/phone.ts) and a fake Android. Never the network.

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as c;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:zen_mobile/konto/konto.dart';
import 'package:zen_mobile/l10n/app_localizations.dart';
import 'package:zen_mobile/update/release.dart';
import 'package:zen_mobile/update/release_source.dart';
import 'package:zen_mobile/update/update_controller.dart';
import 'package:zen_mobile/update/update_platform.dart';
import 'package:zen_mobile/update/update_section.dart';

const server = 'https://cloud.test';
final apk = Uint8List.fromList(List.generate(300000, (i) => i * 7 % 251));
final apkSha = '${c.sha256.convert(apk)}';

Map<String, dynamic> manifest({int code = 5, String? sha, int? size}) => {
      'version': '0.2.0',
      'version_code': code,
      'sha256': sha ?? apkSha,
      'size': size ?? apk.length,
      'notes': 'Calmer eye',
      'published_at': '2026-10-29T10:00:00.000Z',
    };

/// The cloud of cloud/src/phone.ts: Bearer required, manifest + APK by code.
class FakeCloud {
  Map<String, dynamic>? release = manifest();
  Uint8List body = apk;
  final List<String> requests = [];

  MockClient get client => MockClient((req) async {
        requests.add('${req.method} ${req.url}');
        if (req.headers['Authorization'] != 'Bearer tok') return http.Response('{"fehler":"x"}', 401);
        if (req.url.path == '/v1/phone/release') {
          return release == null
              ? http.Response('{"fehler":"no_release","text":"none"}', 404)
              : http.Response(jsonEncode(release), 200);
        }
        if (req.url.path == '/v1/phone/release/${release?['version_code']}.apk') {
          return http.Response.bytes(body, 200);
        }
        return http.Response('{"fehler":"nicht_gefunden"}', 404);
      });
}

class FakePlatform implements UpdatePlatform {
  FakePlatform(this.dir, {this.code = 4, this.selfUpdate = true});
  final Directory dir;
  final int code;
  final bool selfUpdate;
  bool allowed = true;
  bool metered = false;
  final List<String> installed = [];
  int settingsOpened = 0;

  @override
  Future<InstalledApp> info() async =>
      InstalledApp(versionName: '0.1.0', versionCode: code, selfUpdate: selfUpdate, updateDir: dir.path);
  @override
  Future<bool> canInstall() async => allowed;
  @override
  Future<void> openInstallSettings() async => settingsOpened++;
  @override
  Future<bool> isMetered() async => metered;
  @override
  Future<void> install(String apkPath) async => installed.add(apkPath);
}

Sitzung session() => Sitzung(server: server, name: 'sasha', token: 'tok', kontoSchluessel: 'k');

void main() {
  late Directory dir;
  setUp(() => dir = Directory.systemTemp.createTempSync('update_test'));
  tearDown(() => dir.deleteSync(recursive: true));

  group('Release', () {
    test('parses the manifest and compares by version code', () {
      final r = Release.fromJson(manifest());
      expect(r.version, '0.2.0');
      expect(r.versionCode, 5);
      expect(r.publishedAt, DateTime.utc(2026, 10, 29, 10));
      expect(r.isNewerThan(4), isTrue);
      expect(r.isNewerThan(5), isFalse);
      expect(r.isNewerThan(6), isFalse);
    });

    test('refuses anything odd', () {
      for (final bad in [
        {...manifest(), 'version': '../x'},
        {...manifest(), 'version_code': 0},
        {...manifest(), 'version_code': '5'},
        {...manifest(), 'sha256': 'AB' * 32},
        {...manifest(), 'size': 0},
        {...manifest(), 'size': maxApkBytes + 1},
        {...manifest(), 'notes': 3},
      ]) {
        expect(() => Release.fromJson(bad), throwsFormatException, reason: '$bad');
      }
    });
  });

  group('ReleaseSource', () {
    test('asks its own cloud with the session; 404 means no release', () async {
      final cloud = FakeCloud();
      final s = ReleaseSource(server: '$server/', token: 'tok', client: cloud.client);
      expect((await s.latest())!.versionCode, 5);
      expect(cloud.requests, ['GET $server/v1/phone/release']);
      cloud.release = null;
      expect(await s.latest(), isNull);
    });

    test('an unreadable manifest is a server failure, a refused one a network failure', () async {
      final broken = ReleaseSource(
          server: server, token: 'tok', client: MockClient((_) async => http.Response('{"version": 1}', 200)));
      await expectLater(broken.latest(),
          throwsA(isA<UpdateException>().having((e) => e.failure, 'failure', UpdateFailure.server)));
      final wrongToken = ReleaseSource(server: server, token: 'other', client: FakeCloud().client);
      await expectLater(wrongToken.latest(),
          throwsA(isA<UpdateException>().having((e) => e.failure, 'failure', UpdateFailure.network)));
    });

    test('download streams to a file and checks size and SHA-256', () async {
      final cloud = FakeCloud();
      final s = ReleaseSource(server: server, token: 'tok', client: cloud.client);
      final seen = <int>[];
      final f = await s.download(Release.fromJson(manifest()), dir, progress: (got, _) => seen.add(got));
      expect(f.path, '${dir.path}/zentrale-5.apk');
      expect(await f.readAsBytes(), apk);
      expect(seen.last, apk.length);
      expect(cloud.requests.last, 'GET $server/v1/phone/release/5.apk');
      expect(await matchesRelease(f, Release.fromJson(manifest())), isTrue);
    });

    test('a wrong SHA-256 or size leaves no file behind', () async {
      for (final m in [manifest(sha: '0' * 64), manifest(size: apk.length + 1), manifest(size: apk.length - 1)]) {
        final cloud = FakeCloud()..release = m;
        final s = ReleaseSource(server: server, token: 'tok', client: cloud.client);
        await expectLater(s.download(Release.fromJson(m), dir),
            throwsA(isA<UpdateException>().having((e) => e.failure, 'failure', UpdateFailure.checksum)));
        expect(dir.listSync(), isEmpty);
      }
    });
  });

  group('UpdateController', () {
    UpdateController controller(FakePlatform p, FakeCloud cloud, {Sitzung? s}) => UpdateController(
          platform: p,
          session: () async => s,
          sourceFor: (s) => ReleaseSource(server: s.server, token: s.token, client: cloud.client),
        );

    test('off in a Play build, idle without a session', () async {
      final cloud = FakeCloud();
      final play = controller(FakePlatform(dir, selfUpdate: false), cloud, s: session());
      await play.check();
      expect(play.status, UpdateStatus.disabled);
      expect(cloud.requests, isEmpty);
      final out = controller(FakePlatform(dir), cloud);
      await out.check();
      expect(out.status, UpdateStatus.notLoggedIn);
      expect(cloud.requests, isEmpty);
    });

    test('up to date, no release, newer release', () async {
      final cloud = FakeCloud();
      final same = controller(FakePlatform(dir, code: 5), cloud, s: session());
      await same.check();
      expect(same.status, UpdateStatus.upToDate);
      expect(same.hasUpdate, isFalse);
      cloud.release = null;
      await same.check();
      expect(same.status, UpdateStatus.noRelease);
      cloud.release = manifest(code: 6);
      await same.check();
      expect(same.status, UpdateStatus.available);
      expect(same.hasUpdate, isTrue);
    });

    test('download → permission → install with the verified file', () async {
      final p = FakePlatform(dir)..allowed = false;
      final u = controller(p, FakeCloud(), s: session());
      await u.check();
      await u.download();
      expect(u.status, UpdateStatus.needsPermission);
      expect(p.installed, isEmpty);
      await u.openPermission();
      expect(p.settingsOpened, 1);
      p.allowed = true;
      await u.install();
      expect(u.status, UpdateStatus.installerOpened);
      expect(p.installed, ['${dir.path}/zentrale-5.apk']);
    });

    test('asks first on a metered network', () async {
      final p = FakePlatform(dir)..metered = true;
      final cloud = FakeCloud();
      final u = controller(p, cloud, s: session());
      await u.check();
      await u.download();
      expect(u.status, UpdateStatus.askMetered);
      expect(cloud.requests.where((r) => r.endsWith('.apk')), isEmpty);
      u.later();
      expect(u.status, UpdateStatus.available);
      await u.download(allowMetered: true);
      expect(p.installed, hasLength(1));
    });

    test('a tampered file is never installed', () async {
      final p = FakePlatform(dir);
      final cloud = FakeCloud()..body = Uint8List.fromList([...apk]..[10] ^= 1);
      final u = controller(p, cloud, s: session());
      await u.check();
      await u.download();
      expect(u.status, UpdateStatus.failed);
      expect(u.failure, UpdateFailure.checksum);
      expect(p.installed, isEmpty);
      // A file changed after the download is caught before the installer too.
      File('${dir.path}/zentrale-5.apk').writeAsBytesSync([...apk]..[0] ^= 1);
      await u.download();
      expect(u.failure, UpdateFailure.checksum);
      expect(p.installed, isEmpty);
      expect(File('${dir.path}/zentrale-5.apk').existsSync(), isFalse);
    });

    test('old downloads are cleaned up on check', () async {
      File('${dir.path}/zentrale-3.apk').writeAsBytesSync([1]);
      File('${dir.path}/zentrale-5.apk.part').writeAsBytesSync([1]);
      final u = controller(FakePlatform(dir), FakeCloud(), s: session());
      await u.check();
      expect(dir.listSync(), isEmpty);
    });
  });

  group('UI', () {
    Widget app(Widget child, [Locale locale = const Locale('de')]) => MaterialApp(
          locale: locale,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(body: child),
        );

    testWidgets('settings section and the start-screen dot', (tester) async {
      final p = FakePlatform(dir);
      final cloud = FakeCloud();
      final u = UpdateController(
        platform: p,
        session: () async => session(),
        sourceFor: (s) => ReleaseSource(server: s.server, token: s.token, client: cloud.client),
      );
      var tapped = 0;
      await tester.pumpWidget(app(Column(children: [
        UpdateHint(controller: u, onTap: () => tapped++),
        UpdateSection(controller: u),
      ])));
      expect(find.byType(Tooltip), findsNothing); // no update known → no dot
      expect(find.text('Nach Update suchen'), findsOneWidget);

      await tester.runAsync(u.check);
      await tester.pump();
      expect(find.text('Installiert: 0.1.0 (4)'), findsOneWidget);
      expect(find.textContaining('Neue Version 0.2.0 ist da.'), findsOneWidget);
      expect(find.textContaining('Neu: Calmer eye'), findsOneWidget);
      expect(find.text('Laden und installieren'), findsOneWidget);
      await tester.tap(find.byTooltip('Update verfügbar'));
      expect(tapped, 1);
    });

    testWidgets('English table', (tester) async {
      final u = UpdateController(platform: FakePlatform(dir, selfUpdate: false), session: () async => null);
      await tester.pumpWidget(app(UpdateSection(controller: u), const Locale('en')));
      await tester.runAsync(u.check);
      await tester.pump();
      expect(find.text('This copy is updated through the Play Store.'), findsOneWidget);
    });
  });
}
