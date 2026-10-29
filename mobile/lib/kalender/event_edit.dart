// Changing an EXISTING .ics on the phone — the file as the cloud has it,
// changed only where the phone means to. Everything else (DESCRIPTION,
// foreign VALARMs, Google fields, X-ZENTRALE-* the phone does not manage,
// pauses, RECURRENCE-ID parts) stays line for line; the computer merges per
// VEVENT (memory/betrieb/abgleich_fremde_knoten.md "Termine vom Handy").
//
// Works on unfolded content lines of the main VEVENT (the one with the UID
// and no RECURRENCE-ID); writes folded CRLF lines like ics.dart.

import 'dart:convert';

import 'ics.dart';
import 'regel.dart';
import 'zeit.dart';

class EditError implements Exception {
  EditError(this.message);
  final String message;
  @override
  String toString() => message;
}

/// X-ZENTRALE-AUS like core/abgleich_vorschlaege.x_aus_schreiben:
/// "b64:" + base64url(json.dumps(list, ensure_ascii=False, sort_keys=True)).
/// Python's json.dumps separates with ", " — written by hand to match bytes.
String encodeSwitchedOff(List<String> days) {
  final json = '[${days.map(jsonEncode).join(', ')}]';
  return 'b64:${base64Url.encode(utf8.encode(json))}';
}

/// The other way round; also raw JSON. null = nothing usable.
List<String>? decodeSwitchedOff(String? raw) {
  if (raw == null) return null;
  try {
    final o = raw.startsWith('b64:')
        ? jsonDecode(utf8.decode(base64Url.decode(base64Url.normalize(raw.substring(4)))))
        : jsonDecode(raw);
    return o is List ? [for (final x in o) '$x'] : null;
  } catch (_) {
    return null;
  }
}

/// What the edit form changes on an event. null fields stay as they are.
class EventChange {
  const EventChange({this.title, this.place, this.day, this.start, this.end, this.allDay = false});
  final String? title;

  /// '' clears the place.
  final String? place;

  /// New day (single events only; series keep their first day).
  final DateTime? day;

  /// "HH:MM" or null with [allDay].
  final String? start, end;
  final bool allDay;
}

class _Lines {
  _Lines(String text) : lines = entfalten(text) {
    var depth = 0;
    int? begin;
    for (var i = 0; i < lines.length; i++) {
      final u = lines[i].toUpperCase();
      if (u.startsWith('BEGIN:')) {
        if (u == 'BEGIN:VEVENT' && depth == 1) begin = i;
        depth++;
      } else if (u.startsWith('END:')) {
        depth--;
        if (u == 'END:VEVENT' && begin != null && depth == 1) {
          events.add((begin, i));
          begin = null;
        }
      }
    }
  }

  final List<String> lines;
  final List<(int, int)> events = [];
  late int start, end; // the main VEVENT, BEGIN … END line indices

  /// Indices of top-level property lines of the main VEVENT (not in VALARM).
  Iterable<int> _own() sync* {
    var depth = 0;
    for (var i = start + 1; i < end; i++) {
      final u = lines[i].toUpperCase();
      if (u.startsWith('BEGIN:')) {
        depth++;
      } else if (u.startsWith('END:')) {
        depth--;
      } else if (depth == 0) {
        yield i;
      }
    }
  }

  void selectMain(String uid) {
    for (final (b, e) in events) {
      start = b;
      end = e;
      final props = [for (final i in _own()) zeileLesen(lines[i])];
      if (props.any((p) => p.name == 'UID' && p.wert.trim() == uid) &&
          !props.any((p) => p.name == 'RECURRENCE-ID')) {
        return;
      }
    }
    throw EditError('main VEVENT of $uid not found');
  }

  IcsProperty? prop(String name) {
    for (final i in _own()) {
      final p = zeileLesen(lines[i]);
      if (p.name == name) return p;
    }
    return null;
  }

  List<IcsProperty> all(String name) => [
        for (final i in _own())
          if (zeileLesen(lines[i]).name == name) zeileLesen(lines[i])
      ];

  /// Replace the first line of [name] (others of that name go), or add it
  /// before the first sub-component / END:VEVENT. null removes all.
  void set(String name, String? line) {
    final idx = [for (final i in _own()) if (zeileLesen(lines[i]).name == name) i];
    if (idx.isEmpty) {
      if (line == null) return;
      var at = end;
      for (var i = start + 1; i < end; i++) {
        if (lines[i].toUpperCase().startsWith('BEGIN:')) {
          at = i;
          break;
        }
      }
      lines.insert(at, line);
      end++;
      return;
    }
    for (final i in (line == null ? idx : idx.skip(1)).toList().reversed) {
      lines.removeAt(i);
      end--;
    }
    if (line != null) lines[idx.first] = line;
  }

  bool get hasBerlinZone => lines.any((l) => l.toUpperCase() == 'TZID:EUROPE/BERLIN');

  void addBerlinZone() {
    if (hasBerlinZone) return;
    final at = lines.indexWhere((l) => l.toUpperCase() == 'BEGIN:VEVENT');
    lines.insertAll(at, _vtimezone);
    start += _vtimezone.length;
    end += _vtimezone.length;
  }

  String write() => '${lines.map(falten).join('\r\n')}\r\n';
}

const _vtimezone = [
  'BEGIN:VTIMEZONE', 'TZID:Europe/Berlin', 'BEGIN:DAYLIGHT', 'DTSTART:19700329T020000',
  'RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3', 'TZNAME:CEST', 'TZOFFSETFROM:+0100',
  'TZOFFSETTO:+0200', 'END:DAYLIGHT', 'BEGIN:STANDARD', 'DTSTART:19701025T030000',
  'RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=10', 'TZNAME:CET', 'TZOFFSETFROM:+0200',
  'TZOFFSETTO:+0100', 'END:STANDARD', 'END:VTIMEZONE',
];

String _z(int x, [int n = 2]) => x.toString().padLeft(n, '0');
String _date(DateTime d) => '${_z(d.year, 4)}${_z(d.month)}${_z(d.day)}';
String _wall(DateTime d) => '${_date(d)}T${_z(d.hour)}${_z(d.minute)}${_z(d.second)}';

String _stamp(DateTime now) {
  final u = now.toUtc();
  return '${_wall(DateTime.utc(u.year, u.month, u.day, u.hour, u.minute, u.second))}Z';
}

int? _minutes(String? hhmm) {
  final m = RegExp(r'^(\d\d):(\d\d)$').firstMatch(hhmm ?? '');
  if (m == null) return null;
  return int.parse(m.group(1)!) * 60 + int.parse(m.group(2)!);
}

/// How DTSTART is written in this file: date, UTC, a zone, or floating.
enum _Form { date, utc, zone, floating }

_Form _formOf(IcsProperty? p) {
  if (p == null) return _Form.zone;
  if ((p.param('VALUE') ?? '').toUpperCase() == 'DATE' || !p.wert.contains('T')) return _Form.date;
  if (p.wert.trim().endsWith('Z')) return _Form.utc;
  if (p.param('TZID') != null) return _Form.zone;
  return _Form.floating;
}

/// A Berlin wall time (UTC carrier) as a DTSTART/DTEND/EXDATE line.
String _timeLine(String name, DateTime wall, _Form form, _Lines l) {
  switch (form) {
    case _Form.utc:
      final u = alsBerlin(wall).toUtc();
      return '$name:${_wall(DateTime.utc(u.year, u.month, u.day, u.hour, u.minute, u.second))}Z';
    case _Form.floating:
      return '$name:${_wall(wall)}';
    case _Form.date:
    case _Form.zone:
      l.addBerlinZone();
      return '$name;TZID=Europe/Berlin:${_wall(wall)}';
  }
}

/// Change title, place, day/time of the event [uid] in [text].
/// [series]: a routine — its first day stays, only the time of day changes.
String applyChange(String text, String uid, EventChange c, {required DateTime now, bool series = false}) {
  final l = _Lines(text)..selectMain(uid);
  if (c.title != null) {
    final t = c.title!.trim();
    if (t.isEmpty) throw EditError('empty title');
    l.set('SUMMARY', 'SUMMARY:${textSchreiben(t)}');
  }
  if (c.place != null) {
    final p = c.place!.trim();
    l.set('LOCATION', p.isEmpty ? null : 'LOCATION:${textSchreiben(p)}');
  }
  final dtstart = l.prop('DTSTART');
  final old = dtstart == null ? null : zeitLesen(dtstart.wert, tzid: dtstart.param('TZID'));
  if (old != null && (c.day != null || c.start != null || c.allDay)) {
    final day = series || c.day == null ? old.tag : tagVon(c.day!);
    if (c.allDay) {
      l.set('DTSTART', 'DTSTART;VALUE=DATE:${_date(day)}');
      l.set('DURATION', null);
      l.set('DTEND', 'DTEND;VALUE=DATE:${_date(day.add(const Duration(days: 1)))}');
    } else {
      final s = _minutes(c.start);
      if (s == null || s >= 24 * 60) throw EditError('bad start ${c.start}');
      final form = _formOf(dtstart) == _Form.date ? _Form.zone : _formOf(dtstart);
      l.set('DTSTART', _timeLine('DTSTART', day.add(Duration(minutes: s)), form, l));
      l.set('DURATION', null);
      final e = _minutes(c.end);
      if (e != null && e > s && e <= 24 * 60) {
        l.set('DTEND', _timeLine('DTEND', day.add(Duration(minutes: e)), form, l));
      } else {
        l.set('DTEND', null);
      }
    }
  }
  _touch(l, now);
  return l.write();
}

/// One occurrence (the day [day] of the series [uid]) off or back on:
/// EXDATE in the same form as DTSTART AND the day in X-ZENTRALE-AUS.
/// [timeOfDay] "HH:MM" = the routine's start (for timed EXDATEs).
String setOccurrenceOffIn(String text, String uid, DateTime day, {required bool off, String? timeOfDay,
    DateTime? now}) {
  final l = _Lines(text)..selectMain(uid);
  final key = isoTag(day);
  final dtstart = l.prop('DTSTART');
  final form = _formOf(dtstart);

  // X-ZENTRALE-AUS: the exact list, order kept.
  final list = decodeSwitchedOff(l.prop('X-ZENTRALE-AUS')?.wert) ?? <String>[];
  if (off && !list.contains(key)) list.add(key);
  if (!off) list.removeWhere((d) => d == key);
  l.set('X-ZENTRALE-AUS', list.isEmpty ? null : 'X-ZENTRALE-AUS:${encodeSwitchedOff(list)}');

  // EXDATE: drop this day from every EXDATE value; add one when off.
  final kept = <String>[];
  for (final p in l.all('EXDATE')) {
    final values = [
      for (final v in p.wert.split(','))
        if (zeitLesen(v, tzid: p.param('TZID'))?.tag != tagVon(day)) v
    ];
    if (values.isEmpty) continue;
    final head = [
      'EXDATE',
      for (final MapEntry(:key, :value) in p.params.entries) '$key=$value',
    ].join(';');
    kept.add('$head:${values.join(',')}');
  }
  if (off) {
    if (form == _Form.date) {
      kept.add('EXDATE;VALUE=DATE:${_date(day)}');
    } else {
      final raw = dtstart!;
      final m = _minutes(timeOfDay);
      final tzid = raw.param('TZID');
      if (form == _Form.zone && tzid != null && tzid != tzName) {
        // Same wall time in the foreign zone as DTSTART has.
        final t = raw.wert.trim();
        kept.add('EXDATE;TZID=$tzid:${_date(day)}${t.substring(t.indexOf('T'))}');
      } else {
        final wall = m == null
            ? DateTime.utc(day.year, day.month, day.day, _wallOf(raw).hour, _wallOf(raw).minute)
            : tagVon(day).add(Duration(minutes: m));
        kept.add(_timeLine('EXDATE', wall, form, l));
      }
    }
  }
  _setAll(l, 'EXDATE', kept);
  _touch(l, now ?? DateTime.now().toUtc());
  return l.write();
}

DateTime _wallOf(IcsProperty dtstart) => zeitLesen(dtstart.wert, tzid: dtstart.param('TZID'))!.wert;

void _setAll(_Lines l, String name, List<String> lines) {
  l.set(name, null);
  for (final x in lines) {
    var at = l.end;
    for (var i = l.start + 1; i < l.end; i++) {
      if (l.lines[i].toUpperCase().startsWith('BEGIN:')) {
        at = i;
        break;
      }
    }
    l.lines.insert(at, x);
    l.end++;
  }
}

void _touch(_Lines l, DateTime now) {
  final s = _stamp(now);
  l.set('DTSTAMP', 'DTSTAMP:$s');
  l.set('LAST-MODIFIED', 'LAST-MODIFIED:$s');
}
