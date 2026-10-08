// Gespräche im selben Format wie core/gespraeche.py — das Handy ist ein
// Knoten wie Laptop und PC (Doku: memory/ki/gespraeche.md).
//
//   gespraeche/<id>/kopf.json         Titel, erstellt, archiviert, projekt
//   gespraeche/<id>/<knoten>.jsonl    nur dieser Knoten schreibt, nur anhängen
//   gespraeche/_knoten/<knoten>.json  was hier offen ist, was gelesen ist
//
// Lesen = alle Knoten-Dateien zusammenlegen, nach ts sortieren, Ereignisse
// anwenden ("nachricht" hängt an, "verwerfen" schneidet ab). Das Handy
// schreibt nur seine eigene jsonl — darum gibt es beim Abgleich keine
// Konflikte. Nichts wird gelöscht, nur archiviert.

import 'dart:convert';

import '../ablage/ablage.dart';
import 'zeit.dart';

const wurzel = 'gespraeche';
const erinnerungenId = 'erinnerungen';

/// So viele Nachrichten gehen an die KI (gespraeche.FENSTER).
const fenster = 50;
const vermerkAbgebrochen = '(abgebrochen)';
const auftragVorsatz =
    '[Automatischer Auftrag von ZENTRALE, nicht von Sasha geschrieben] ';

class Nachricht {
  Nachricht(this.daten);

  final Map<String, dynamic> daten;

  String get id => daten['id'] as String;
  String get ts => daten['ts'] as String;
  String get rolle => daten['rolle'] as String? ?? 'user';
  String get text => daten['text'] as String? ?? '';
  String? get denken => daten['denken'] as String?;
  String get knoten => daten['knoten'] as String? ?? '';
  bool get abgebrochen => daten['abgebrochen'] == true;
  bool get versteckt => daten['versteckt'] == true;
  bool get vonSasha => rolle == 'user';

  /// Der Text, wie ihn die KI sieht (gespraeche.text_fuer_ki).
  String get textFuerKi {
    var t = text;
    if (abgebrochen) t = '${t.trimRight()}\n\n$vermerkAbgebrochen';
    if (versteckt && vonSasha) t = auftragVorsatz + t;
    return t;
  }
}

class Uebersicht {
  Uebersicht(this.id, this.titel, this.letzte, this.anzahl);
  final String id;
  final String titel;
  final String letzte;
  final int anzahl;
}

bool gueltigeId(String id) =>
    id.isNotEmpty && !id.startsWith('_') && !id.startsWith('.') &&
    !id.contains('/') && !id.contains('\\') && id == id.trim();

/// Ereignisse aus jsonl-Texten (je Knoten einer) in geltende Nachrichten.
/// Reine Funktion — dieselbe Regel wie gespraeche._ereignisse/_anwenden.
List<Nachricht> zusammenlegen(Map<String, String> dateien) {
  final roh = <(String, String, int, Map<String, dynamic>)>[];
  for (final inhalt in dateien.values) {
    final zeilen = const LineSplitter().convert(inhalt);
    for (var nr = 0; nr < zeilen.length; nr++) {
      Object? e;
      try {
        e = jsonDecode(zeilen[nr]);
      } on FormatException {
        continue; // halbe Zeile nach Absturz: überspringen
      }
      if (e is Map<String, dynamic> && e['ts'] is String && e['id'] != null) {
        roh.add((e['ts'] as String, '${e['knoten'] ?? ''}', nr, e));
      }
    }
  }
  roh.sort((a, b) {
    final c = a.$1.compareTo(b.$1);
    if (c != 0) return c;
    final k = a.$2.compareTo(b.$2);
    return k != 0 ? k : a.$3.compareTo(b.$3);
  });
  final liste = <Nachricht>[];
  for (final (_, _, _, e) in roh) {
    if (e['art'] == 'nachricht') {
      liste.add(Nachricht(e));
    } else if (e['art'] == 'verwerfen') {
      final i = liste.indexWhere((n) => n.id == e['ab']);
      if (i >= 0) liste.removeRange(i, liste.length);
    }
  }
  return liste;
}

class Gespraeche {
  Gespraeche(this.ablage, {this.knoten = 'handy'});

  final Ablage ablage;

  /// Name dieses Knotens — steht im Dateinamen und in jedem Ereignis.
  final String knoten;

  String _ordner(String id) => '$wurzel/$id';
  String get _knotenPfad => '$wurzel/_knoten/$knoten.json';

  Future<Map<String, dynamic>> kopf(String id) async {
    final t = await ablage.lesen('${_ordner(id)}/kopf.json');
    if (t == null) return {};
    try {
      final k = jsonDecode(t);
      return k is Map<String, dynamic> ? k : {};
    } on FormatException {
      return {};
    }
  }

  Future<bool> gibtEs(String id) async =>
      gueltigeId(id) && await ablage.lesen('${_ordner(id)}/kopf.json') != null;

  /// Ein Gespräch anlegen. Titel kommt beim ersten Senden (titelSetzen).
  Future<String> neu() async {
    final id = gespraechsId();
    await ablage.schreiben('${_ordner(id)}/kopf.json', jsonEncode({
      'titel': null,
      'titel_von': null,
      'erstellt': jetztTs(),
      'archiviert': false,
      'projekt': null,
    }));
    return id;
  }

  /// Titel automatisch setzen ("woerter") — nie über einen von Sasha.
  Future<void> titelSetzen(String id, String titel, {String von = 'woerter'}) async {
    final k = await kopf(id);
    if (von != 'sasha' && k['titel_von'] == 'sasha') return;
    final sauber = titel.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).join(' ');
    if (sauber.isEmpty) return;
    k['titel'] = sauber.length > 120 ? sauber.substring(0, 120) : sauber;
    k['titel_von'] = von;
    await ablage.schreiben('${_ordner(id)}/kopf.json', jsonEncode(k));
  }

  Future<Map<String, dynamic>> _anhaengen(String id, Map<String, dynamic> e) async {
    final ereignis = {...e, 'id': e['id'] ?? ereignisId(), 'ts': jetztTs(), 'knoten': knoten};
    await ablage.anhaengen('${_ordner(id)}/$knoten.jsonl', '${jsonEncode(ereignis)}\n');
    return ereignis;
  }

  Future<Nachricht> anhaengen(String id, String rolle, String text,
      {String? denken, String? anbieter, String? modell, bool abgebrochen = false}) async {
    final e = await _anhaengen(id, {
      'art': 'nachricht',
      'rolle': rolle,
      'text': text,
      if (denken != null && denken.isNotEmpty) 'denken': denken,
      'anbieter': ?anbieter,
      'modell': ?modell,
      if (abgebrochen) 'abgebrochen': true,
    });
    return Nachricht(e);
  }

  /// Diese Nachricht und alle späteren zählen nicht mehr.
  Future<void> verwerfenAb(String id, String nachrichtId) =>
      _anhaengen(id, {'art': 'verwerfen', 'ab': nachrichtId});

  Future<List<Nachricht>> nachrichten(String id, {bool versteckte = false}) async {
    final dateien = <String, String>{};
    for (final name in await ablage.auflisten(_ordner(id))) {
      if (!name.endsWith('.jsonl') || name.startsWith('.')) continue;
      final t = await ablage.lesen('${_ordner(id)}/$name');
      if (t != null) dateien[name] = t;
    }
    final alle = zusammenlegen(dateien);
    return versteckte ? alle : alle.where((n) => !n.versteckt).toList();
  }

  /// [{role, content}] für die KI — die letzten [fenster] Nachrichten.
  Future<List<Map<String, String>>> verlaufFuerKi(String id) async {
    final alle = await nachrichten(id, versteckte: true);
    final teil = alle.length > fenster ? alle.sublist(alle.length - fenster) : alle;
    final raus = [for (final n in teil) {'role': n.rolle, 'content': n.textFuerKi}];
    // Die API will mit Sasha anfangen; ein abgeschnittenes Fenster kann
    // mit einer KI-Antwort beginnen.
    while (raus.isNotEmpty && raus.first['role'] != 'user') {
      raus.removeAt(0);
    }
    return raus;
  }

  /// Alle nicht archivierten Gespräche, neueste Aktivität zuerst,
  /// „Erinnerungen" oben. Leere Gespräche fehlen (wie in liste()).
  Future<List<Uebersicht>> liste() async {
    final raus = <Uebersicht>[];
    for (final id in await ablage.auflisten(wurzel)) {
      if (!await gibtEs(id)) continue;
      final k = await kopf(id);
      if (k['archiviert'] == true) continue;
      final ns = await nachrichten(id);
      if (ns.isEmpty && id != erinnerungenId) continue;
      raus.add(Uebersicht(id, (k['titel'] as String?) ?? 'neues gespräch',
          ns.isNotEmpty ? ns.last.ts : (k['erstellt'] as String? ?? ''), ns.length));
    }
    raus.sort((a, b) => b.letzte.compareTo(a.letzte));
    raus.sort((a, b) => (a.id == erinnerungenId ? 0 : 1) - (b.id == erinnerungenId ? 0 : 1));
    return raus;
  }

  // ── Was auf diesem Knoten offen ist ──────────────────────────────────

  Future<Map<String, dynamic>> _knotenLesen() async {
    final t = await ablage.lesen(_knotenPfad);
    if (t == null) return {};
    try {
      final d = jsonDecode(t);
      return d is Map<String, dynamic> ? d : {};
    } on FormatException {
      return {};
    }
  }

  Future<String?> aktiv() async {
    final id = (await _knotenLesen())['aktiv'] as String?;
    return id != null && await gibtEs(id) ? id : null;
  }

  Future<void> aktivSetzen(String? id) async {
    final d = await _knotenLesen();
    d['aktiv'] = id;
    d['neu_projekt'] = null;
    await ablage.schreiben(_knotenPfad, jsonEncode(d));
  }
}
