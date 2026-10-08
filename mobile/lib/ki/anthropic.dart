// Claude über die Messages-API, gestreamt. Für Dart gibt es kein offizielles
// SDK, darum direkt per HTTP + SSE. Dieselben Einstellungen wie
// core/cloud.py: adaptives Denken, zusammengefasst angezeigt, effort aus
// dem Kontext, der System-Prompt gecacht (er ist groß und ändert sich selten).

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'ki.dart';
import 'sse.dart';

class AnthropicAnbieter implements KiAnbieter {
  AnthropicAnbieter(this.schluessel, {http.Client? client})
      : _client = client ?? http.Client();

  final Future<String?> Function() schluessel;
  final http.Client _client;

  static final _url = Uri.parse('https://api.anthropic.com/v1/messages');

  @override
  Stream<KiStueck> antworten({
    required String system,
    required List<Map<String, String>> verlauf,
    required String modell,
    required String effort,
  }) async* {
    final key = await schluessel();
    if (key == null || key.isEmpty) {
      throw KiFehler('Kein API-Schlüssel — in den Einstellungen eintragen.');
    }
    final anfrage = http.Request('POST', _url)
      ..headers.addAll({
        'x-api-key': key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json',
      })
      ..body = jsonEncode({
        'model': modell,
        'max_tokens': 32000,
        'stream': true,
        'thinking': {'type': 'adaptive', 'display': 'summarized'},
        'output_config': {'effort': effort},
        'system': [
          {'type': 'text', 'text': system, 'cache_control': {'type': 'ephemeral'}}
        ],
        'messages': verlauf,
      });

    final http.StreamedResponse antwort;
    try {
      antwort = await _client.send(anfrage);
    } catch (e) {
      throw KiFehler('Kein Netz zur KI ($e)');
    }
    if (antwort.statusCode != 200) {
      final text = await antwort.stream.bytesToString();
      throw KiFehler('KI antwortet mit ${antwort.statusCode}: ${_fehlertext(text)}');
    }

    String? grund;
    await for (final e in sseZerlegen(antwort.stream)) {
      final Map<String, dynamic> d;
      try {
        d = jsonDecode(e.data) as Map<String, dynamic>;
      } on FormatException {
        continue;
      }
      switch (d['type']) {
        case 'content_block_delta':
          final delta = d['delta'] as Map<String, dynamic>;
          if (delta['type'] == 'text_delta') yield KiText(delta['text'] as String);
          if (delta['type'] == 'thinking_delta') yield KiDenken(delta['thinking'] as String);
        case 'message_delta':
          grund = (d['delta'] as Map<String, dynamic>?)?['stop_reason'] as String? ?? grund;
        case 'error':
          throw KiFehler(_fehlertext(e.data));
      }
    }
    yield KiEnde(grund);
  }

  static String _fehlertext(String roh) {
    try {
      final d = jsonDecode(roh) as Map<String, dynamic>;
      return (d['error'] as Map<String, dynamic>?)?['message'] as String? ?? roh;
    } catch (_) {
      return roh.length > 200 ? roh.substring(0, 200) : roh;
    }
  }
}
