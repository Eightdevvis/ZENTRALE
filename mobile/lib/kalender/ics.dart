// iCalendar (RFC 5545) lesen und schreiben — nur die Grammatik: Zeilen
// entfalten/falten, Properties mit Parametern, Komponenten als Baum, TEXT
// escapen. Was ein Termin BEDEUTET, steht in termin_lesen.dart.
//
// Schreiben folgt Byte für Byte dem Python-Paket icalendar, mit dem der Kern
// schreibt (core/kalender_ics_abbildung.py): CRLF, gefaltet nach
// icalendar.parser.foldline (neue Zeile, sobald 75 Bytes erreicht wären).
// Prüfstein: test/kalender_test.dart gegen „neu“ in kalender_testvektoren.json.

import 'dart:convert';

class IcsProperty {
  IcsProperty(this.name, this.wert, [Map<String, String>? params]) : params = params ?? {};
  final String name;
  final Map<String, String> params;

  /// Roh, wie in der Datei (TEXT noch escaped).
  final String wert;

  String? param(String n) => params[n.toUpperCase()];

  /// TEXT-Wert ohne Escapes (\\ \; \, \n).
  String get text => textLesen(wert);
}

class IcsKomponente {
  IcsKomponente(this.name);
  final String name;
  final List<IcsProperty> props = [];
  final List<IcsKomponente> kinder = [];

  IcsProperty? prop(String n) {
    for (final p in props) {
      if (p.name == n) return p;
    }
    return null;
  }

  Iterable<IcsProperty> alle(String n) => props.where((p) => p.name == n);

  Iterable<IcsKomponente> walk(String n) sync* {
    if (name == n) yield this;
    for (final k in kinder) {
      yield* k.walk(n);
    }
  }
}

class IcsFehler implements Exception {
  IcsFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

/// Gefaltete Zeilen entfalten (CRLF oder LF + Leerzeichen/Tab).
List<String> entfalten(String text) {
  final raus = <String>[];
  for (final z in const LineSplitter().convert(text)) {
    if ((z.startsWith(' ') || z.startsWith('\t')) && raus.isNotEmpty) {
      raus[raus.length - 1] += z.substring(1);
    } else if (z.isNotEmpty) {
      raus.add(z);
    }
  }
  return raus;
}

/// Eine Inhaltszeile → Property. Parameterwerte dürfen in "…" stehen.
IcsProperty zeileLesen(String z) {
  var i = 0;
  var inAnf = false;
  // Ende des Namens/der Parameter: erster ':' außerhalb von Anführungszeichen.
  for (; i < z.length; i++) {
    final c = z[i];
    if (c == '"') inAnf = !inAnf;
    if (c == ':' && !inAnf) break;
  }
  if (i >= z.length) throw IcsFehler('Zeile ohne Doppelpunkt: $z');
  final kopf = z.substring(0, i);
  final wert = z.substring(i + 1);
  final teile = <String>[];
  var start = 0;
  inAnf = false;
  for (var j = 0; j < kopf.length; j++) {
    if (kopf[j] == '"') inAnf = !inAnf;
    if (kopf[j] == ';' && !inAnf) {
      teile.add(kopf.substring(start, j));
      start = j + 1;
    }
  }
  teile.add(kopf.substring(start));
  final params = <String, String>{};
  for (final p in teile.skip(1)) {
    final g = p.indexOf('=');
    if (g < 0) continue;
    var v = p.substring(g + 1);
    if (v.length >= 2 && v.startsWith('"') && v.endsWith('"')) v = v.substring(1, v.length - 1);
    params[p.substring(0, g).toUpperCase()] = v;
  }
  return IcsProperty(teile.first.toUpperCase(), wert, params);
}

/// Eine .ics-Datei → die oberste Komponente (VCALENDAR).
IcsKomponente icsLesen(String text) {
  final stapel = <IcsKomponente>[];
  IcsKomponente? wurzel;
  for (final z in entfalten(text)) {
    final p = zeileLesen(z);
    if (p.name == 'BEGIN') {
      final k = IcsKomponente(p.wert.trim().toUpperCase());
      if (stapel.isEmpty) {
        wurzel ??= k;
      } else {
        stapel.last.kinder.add(k);
      }
      stapel.add(k);
    } else if (p.name == 'END') {
      if (stapel.isEmpty) throw IcsFehler('END ohne BEGIN');
      stapel.removeLast();
    } else if (stapel.isNotEmpty) {
      stapel.last.props.add(p);
    }
  }
  if (wurzel == null || wurzel.name != 'VCALENDAR') throw IcsFehler('Kein VCALENDAR');
  return wurzel;
}

String textLesen(String roh) {
  final b = StringBuffer();
  for (var i = 0; i < roh.length; i++) {
    final c = roh[i];
    if (c == r'\' && i + 1 < roh.length) {
      final n = roh[++i];
      b.write(n == 'n' || n == 'N' ? '\n' : n);
    } else {
      b.write(c);
    }
  }
  return b.toString();
}

/// TEXT escapen wie icalendar (_escape_char, Reihenfolge zählt).
String textSchreiben(String t) => t
    .replaceAll(r'\N', '\n')
    .replaceAll(r'\', r'\\')
    .replaceAll(';', r'\;')
    .replaceAll(',', r'\,')
    .replaceAll('\r\n', r'\n')
    .replaceAll('\n', r'\n')
    .replaceAll('\r', r'\n');

/// Falten wie icalendar.parser._foldline: erreichte die Zeile mit dem
/// nächsten Zeichen 75 Bytes, kommt davor CRLF + Leerzeichen — aber nie
/// zwischen einen Backslash und das Zeichen, das er escaped.
String falten(String zeile) {
  final zeilen = <String>[];
  var aktuell = <String>[];
  var bytes = 0;
  for (final r in zeile.runes) {
    final c = String.fromCharCode(r);
    final n = utf8.encode(c).length;
    if (aktuell.isNotEmpty && bytes + n >= 75) {
      if (aktuell.length > 1 && (aktuell.last == r'\' || aktuell.last == '^')) {
        final vorn = aktuell.removeLast();
        zeilen.add(aktuell.join());
        aktuell = [vorn];
        bytes = utf8.encode(vorn).length;
      } else {
        zeilen.add(aktuell.join());
        aktuell = [];
        bytes = 0;
      }
    }
    aktuell.add(c);
    bytes += n;
  }
  if (aktuell.isNotEmpty) zeilen.add(aktuell.join());
  return zeilen.join('\r\n ');
}
