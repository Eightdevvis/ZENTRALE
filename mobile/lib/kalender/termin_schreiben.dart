// Einen NEUEN Einmal-Termin als .ics schreiben — Byte für Byte so, wie der
// Kern ihn schreibt (core/kalender_ics_abbildung.termin_kalender +
// zusammenfuehren(None, …)). Prüfstein: „neu“ in kalender_testvektoren.json.
//
// Das Handy legt die Datei als VORSCHLAG in seinen Eingang (data/kalender/
// <ebene>/<uid>.ics); ein Rechner übernimmt sie nur, solange es die UID noch
// nicht gibt (core/abgleich.kalender_vorschlag_annehmen). Ändern und Löschen
// vorhandener Termine kommt im nächsten Schritt.

import 'dart:math';

import 'ics.dart';
import 'regel.dart';

/// Ein Termin, wie das Formular ihn kennt.
class NeuerTermin {
  NeuerTermin({required this.titel, required this.tag, this.zeit, this.ende});
  final String titel;
  final DateTime tag;

  /// "HH:MM" oder null = ganztägig.
  final String? zeit;

  /// "HH:MM" am selben Tag (nach [zeit]) oder "24:00"; null = ohne Ende.
  final String? ende;
}

/// Neue UID wie abb.neue_uid(): uuid4 als 32 Hex-Zeichen + "@zentrale".
String neueUid([Random? zufall]) {
  final z = zufall ?? Random.secure();
  final b = List<int>.generate(16, (_) => z.nextInt(256));
  b[6] = (b[6] & 0x0f) | 0x40; // Version 4
  b[8] = (b[8] & 0x3f) | 0x80; // Variante RFC 4122
  return '${b.map((x) => x.toRadixString(16).padLeft(2, '0')).join()}@zentrale';
}

/// Dateiname im Kalender-Ordner (dateien.sicherer_name(uid) + ".ics").
String dateiName(String uid) {
  final s = uid.replaceAll(RegExp(r'[^A-Za-z0-9@.\-]'), '_').replaceAll(RegExp(r'^\.+|\.+$'), '');
  return '${s.isEmpty ? '_' : s}.ics';
}

const _vtimezone = [
  'BEGIN:VTIMEZONE', 'TZID:Europe/Berlin', 'BEGIN:DAYLIGHT', 'DTSTART:19700329T020000',
  'RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3', 'TZNAME:CEST', 'TZOFFSETFROM:+0100',
  'TZOFFSETTO:+0200', 'END:DAYLIGHT', 'BEGIN:STANDARD', 'DTSTART:19701025T030000',
  'RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10', 'TZNAME:CET', 'TZOFFSETFROM:+0200',
  'TZOFFSETTO:+0100', 'END:STANDARD', 'END:VTIMEZONE',
];

String _z(int x, [int n = 2]) => x.toString().padLeft(n, '0');
String _datum(DateTime d) => '${_z(d.year, 4)}${_z(d.month)}${_z(d.day)}';
String _wand(DateTime d) => '${_datum(d)}T${_z(d.hour)}${_z(d.minute)}${_z(d.second)}';

class TerminFehler implements Exception {
  TerminFehler(this.meldung);
  final String meldung;
  @override
  String toString() => meldung;
}

int? _min(String? hhmm) {
  final m = RegExp(r'^(\d\d):(\d\d)$').firstMatch(hhmm ?? '');
  if (m == null) return null;
  final h = int.parse(m.group(1)!), mi = int.parse(m.group(2)!);
  if (h == 24 && mi == 0) return 24 * 60;
  return h > 23 || mi > 59 ? null : h * 60 + mi;
}

/// Die .ics-Datei. [jetzt] = DTSTAMP/LAST-MODIFIED (UTC, ohne Bruchteile).
String terminIcs(NeuerTermin t, String uid, DateTime jetzt) {
  final titel = t.titel.trim();
  if (titel.isEmpty) throw TerminFehler('Ein Termin braucht einen Titel.');
  final tag = tagVon(t.tag);
  final z = <String>['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ZENTRALE//Kalender//DE'];
  final ev = <String>['BEGIN:VEVENT', 'SUMMARY:${textSchreiben(titel)}'];
  if (t.zeit != null) {
    final b = _min(t.zeit);
    if (b == null || b >= 24 * 60) throw TerminFehler('Uhrzeit ${t.zeit} gibt es nicht.');
    ev.add('DTSTART;TZID=Europe/Berlin:${_wand(tag.add(Duration(minutes: b)))}');
    if (t.ende != null) {
      final e = _min(t.ende);
      if (e == null || e <= b) {
        throw TerminFehler('Das Ende muss am selben Tag nach dem Beginn liegen.');
      }
      ev.add('DTEND;TZID=Europe/Berlin:${_wand(tag.add(Duration(minutes: e)))}');
    }
    z.addAll(_vtimezone);
  } else {
    ev
      ..add('DTSTART;VALUE=DATE:${_datum(tag)}')
      ..add('DTEND;VALUE=DATE:${_datum(tag.add(const Duration(days: 1)))}');
  }
  final u = jetzt.toUtc();
  final stempel = '${_wand(DateTime.utc(u.year, u.month, u.day, u.hour, u.minute, u.second))}Z';
  ev
    ..add('DTSTAMP:$stempel')
    ..add('UID:$uid')
    ..add('LAST-MODIFIED:$stempel')
    ..add('X-ZENTRALE-ART:TERMIN')
    ..add('END:VEVENT');
  z
    ..addAll(ev)
    ..add('END:VCALENDAR');
  return '${z.map(falten).join('\r\n')}\r\n';
}
