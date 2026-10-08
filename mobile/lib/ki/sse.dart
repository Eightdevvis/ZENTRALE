// Server-Sent Events zerlegen: Textstrom rein, (event, data)-Paare raus.
// Eigene Datei, damit der Parser ohne Netz testbar ist.

import 'dart:async';
import 'dart:convert';

class SseEreignis {
  SseEreignis(this.event, this.data);
  final String event;
  final String data;
}

Stream<SseEreignis> sseZerlegen(Stream<List<int>> bytes) async* {
  var event = 'message';
  final data = <String>[];
  await for (final zeile
      in bytes.transform(utf8.decoder).transform(const LineSplitter())) {
    if (zeile.isEmpty) {
      // Leerzeile beendet ein Ereignis.
      if (data.isNotEmpty) yield SseEreignis(event, data.join('\n'));
      event = 'message';
      data.clear();
    } else if (zeile.startsWith(':')) {
      continue; // Kommentar
    } else if (zeile.startsWith('event:')) {
      event = zeile.substring(6).trim();
    } else if (zeile.startsWith('data:')) {
      data.add(zeile.substring(5).trimLeft());
    }
  }
  if (data.isNotEmpty) yield SseEreignis(event, data.join('\n'));
}
