// Strom-Parser und Anthropic-Anbieter gegen einen nachgebauten Server-Strom.

import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:zen_mobile/ablage/ablage.dart';
import 'package:zen_mobile/ki/anthropic.dart';
import 'package:zen_mobile/ki/ki.dart';
import 'package:zen_mobile/ki/kontext.dart';
import 'package:zen_mobile/ki/sse.dart';

const strom = '''event: message_start
data: {"type":"message_start","message":{}}

event: content_block_delta
data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"hm"}}

event: ping
data: {"type": "ping"}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Hal"}}

event: content_block_delta
data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"lo"}}

event: message_delta
data: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}

event: message_stop
data: {"type":"message_stop"}

''';

void main() {
  test('SSE: Ereignisse und Daten', () async {
    final es = await sseZerlegen(Stream.value(utf8.encode(strom))).toList();
    expect(es.first.event, 'message_start');
    expect(es.length, 7);
  });

  test('Anthropic: Denken, Text, Ende; Anfrage wie core/cloud.py', () async {
    late Map<String, dynamic> body;
    late Map<String, String> kopf;
    final client = MockClient.streaming((anfrage, bytes) async {
      body = jsonDecode(await utf8.decodeStream(bytes)) as Map<String, dynamic>;
      kopf = anfrage.headers;
      return http.StreamedResponse(Stream.value(utf8.encode(strom)), 200);
    });
    final ki = AnthropicAnbieter(() async => 'sk-test', client: client);
    final teile = await ki.antworten(
      system: 'S', verlauf: [{'role': 'user', 'content': 'hi'}],
      modell: 'claude-sonnet-5', effort: 'low').toList();

    expect(teile.whereType<KiDenken>().map((t) => t.text).join(), 'hm');
    expect(teile.whereType<KiText>().map((t) => t.text).join(), 'Hallo');
    expect((teile.last as KiEnde).grund, 'end_turn');
    expect(kopf['x-api-key'], 'sk-test');
    expect(body['thinking'], {'type': 'adaptive', 'display': 'summarized'});
    expect(body['output_config'], {'effort': 'low'});
    expect(body['stream'], true);
    expect((body['system'] as List).first['cache_control'], {'type': 'ephemeral'});
  });

  test('Anthropic: Fehlermeldung der API kommt lesbar an', () async {
    final client = MockClient((_) async =>
        http.Response('{"type":"error","error":{"type":"x","message":"kaputt"}}', 400));
    final ki = AnthropicAnbieter(() async => 'k', client: client);
    expect(
      ki.antworten(system: '', verlauf: [], modell: 'm', effort: 'low').toList(),
      throwsA(isA<KiFehler>().having((e) => e.meldung, 'meldung', contains('kaputt'))),
    );
  });

  test('ohne Schlüssel: klare Meldung statt Netzfehler', () {
    final ki = AnthropicAnbieter(() async => null);
    expect(ki.antworten(system: '', verlauf: [], modell: 'm', effort: 'low').toList(),
        throwsA(isA<KiFehler>()));
  });

  test('Kontext: Paket aus dem Kern, sonst Notbetrieb; Handy-Absatz immer dran', () async {
    final ablage = SpeicherAblage();
    final not = await Kontext.laden(ablage);
    expect(not.ausDemKern, isFalse);
    expect(not.modell, standardModell);
    expect(not.system, contains('KEINE Werkzeuge'));

    await ablage.schreiben(kontextPfad, jsonEncode({
      'version': 1, 'stand': '2026-10-08T12:00:00+00:00', 'anbieter': 'claude',
      'modell': 'claude-opus-5-5', 'effort': 'medium', 'system': 'Du bist ZENTRALE.'}));
    final k = await Kontext.laden(ablage);
    expect(k.ausDemKern, isTrue);
    expect(k.modell, 'claude-opus-5-5');
    expect(k.system, startsWith('Du bist ZENTRALE.'));
    expect(k.system, contains('KEINE Werkzeuge'));
  });
}
