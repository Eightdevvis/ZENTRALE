// Der Draht zur ZENTRALE-Cloud — wie core/cloud_api.py: eine Adresse an
// einer Stelle, Sitzung als Bearer, Fehler als CloudFehler mit dem Code des
// Servers ({"fehler": "<code>", "text": "<english sentence>"}).

import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// Die eine Stelle für die Adresse (core/cloud_api.VORGABE).
const cloudVorgabe = 'https://zentrale-cloud.sevendevs.workers.dev';

class CloudFehler implements Exception {
  CloudFehler(this.text, {this.code = '', this.status = 0, this.daten = const {}});
  final String text;

  /// Fehler-Code des Servers ("jemand_schneller", "blob_fehlt" …) oder "netz".
  final String code;

  /// HTTP-Status, 0 = gar keine Antwort.
  final int status;

  /// Weitere Felder der Fehler-Antwort (z. B. "fehlen" bei blob_fehlt).
  final Map<String, dynamic> daten;

  @override
  String toString() => text;
}

const _texte = {
  401: 'Nicht angemeldet oder Sitzung abgelaufen — bitte neu anmelden.',
  403: 'Der Server hat die Anfrage abgelehnt.',
  404: 'Auf dem Server nicht gefunden.',
  409: 'Jemand anderes war schneller.',
  429: 'Zu viele Versuche — bitte ein paar Minuten warten.',
};

class CloudClient {
  CloudClient({String? basis, this.token, http.Client? client})
      : basis = (basis ?? cloudVorgabe).replaceAll(RegExp(r'/+$'), ''),
        _c = client ?? http.Client();

  final String basis;
  final String? token;
  final http.Client _c;

  Map<String, String> _kopf([String? art]) => {
        'Accept': 'application/json',
        'User-Agent': 'zentrale-handy',
        if (art != null) 'Content-Type': art,
        if (token != null) 'Authorization': 'Bearer $token',
      };

  Future<http.Response> _senden(Future<http.Response> Function() f) async {
    http.Response r;
    try {
      r = await f().timeout(const Duration(seconds: 30));
    } catch (e) {
      throw CloudFehler('ZENTRALE-Cloud nicht erreichbar ($e).', code: 'netz');
    }
    if (r.statusCode >= 400) {
      var code = '', text = '';
      var daten = <String, dynamic>{};
      try {
        daten = (jsonDecode(utf8.decode(r.bodyBytes)) as Map).cast<String, dynamic>();
        code = '${daten['fehler'] ?? ''}';
        text = '${daten['text'] ?? ''}';
      } catch (_) {}
      throw CloudFehler(
          text.isNotEmpty ? text : _texte[r.statusCode] ?? 'Die Cloud antwortete mit Fehler ${r.statusCode}.',
          code: code, status: r.statusCode, daten: daten);
    }
    return r;
  }

  Map<String, dynamic> _json(http.Response r) {
    if (r.bodyBytes.isEmpty) return {};
    try {
      return (jsonDecode(utf8.decode(r.bodyBytes)) as Map).cast<String, dynamic>();
    } catch (_) {
      throw CloudFehler('Unlesbare Antwort der Cloud.', code: 'antwort', status: r.statusCode);
    }
  }

  Uri _url(String pfad) => Uri.parse(basis + pfad);

  Future<Map<String, dynamic>> get(String pfad) async =>
      _json(await _senden(() => _c.get(_url(pfad), headers: _kopf())));

  Future<Map<String, dynamic>> post(String pfad, Object daten) async => _json(await _senden(
      () => _c.post(_url(pfad), headers: _kopf('application/json'), body: jsonEncode(daten))));

  Future<void> delete(String pfad) async => _senden(() => _c.delete(_url(pfad), headers: _kopf()));

  Future<Uint8List> bytesHolen(String pfad) async =>
      (await _senden(() => _c.get(_url(pfad), headers: _kopf()))).bodyBytes;

  Future<void> bytesSenden(String pfad, Uint8List daten) async => _senden(
      () => _c.put(_url(pfad), headers: _kopf('application/octet-stream'), body: daten));
}
