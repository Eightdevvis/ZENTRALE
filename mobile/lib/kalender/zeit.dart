// Zeitwerte aus .ics lesen — wie _lokal in core/kalender_ics_abbildung.py:
// alles in Berliner Ortszeit OHNE Zone, Ganztags-Werte als Tag. Floating
// Time (ohne TZID) bleibt, wie sie ist; UTC und andere Zonen werden
// umgerechnet (Sommerzeit über package:timezone, dieselbe tz-Datenbank wie
// Pythons zoneinfo).
//
// Träger für „Ortszeit ohne Zone“ ist DateTime.utc(...) — so rechnet Dart
// nie still mit der Zone des Handys.

import 'package:timezone/data/latest.dart' as tzdaten;
import 'package:timezone/timezone.dart' as tz;

const tzName = 'Europe/Berlin';
bool _geladen = false;

/// Einmal die Zeitzonen laden (main und Tests).
void zonenLaden() {
  if (_geladen) return;
  tzdaten.initializeTimeZones();
  _geladen = true;
}

tz.Location get berlin {
  zonenLaden();
  return tz.getLocation(tzName);
}

/// Ein Wert aus DTSTART/DTEND/RECURRENCE-ID/EXDATE.
class IcsZeit {
  IcsZeit(this.wert, {required this.ganztags});

  /// Ortszeit (UTC-Träger) bzw. Tag um Mitternacht.
  final DateTime wert;
  final bool ganztags;

  DateTime get tag => DateTime.utc(wert.year, wert.month, wert.day);
}

final _muster = RegExp(r'^(\d{4})(\d\d)(\d\d)(?:T(\d\d)(\d\d)(\d\d)(Z)?)?$');

/// Einen Wert lesen; [tzid] aus dem Parameter TZID, [nurDatum] aus VALUE=DATE.
IcsZeit? zeitLesen(String roh, {String? tzid}) {
  final m = _muster.firstMatch(roh.trim());
  if (m == null) return null;
  int g(int i) => int.parse(m.group(i)!);
  if (m.group(4) == null) return IcsZeit(DateTime.utc(g(1), g(2), g(3)), ganztags: true);
  final wand = DateTime.utc(g(1), g(2), g(3), g(4), g(5), g(6));
  if (m.group(7) == 'Z') return IcsZeit(_nachBerlin(wand), ganztags: false);
  if (tzid != null && tzid.isNotEmpty && tzid != tzName) {
    zonenLaden();
    tz.Location? ort;
    try {
      ort = tz.getLocation(tzid);
    } catch (_) {
      ort = null; // unbekannte Zone: wie floating stehen lassen
    }
    if (ort != null) {
      final dort = tz.TZDateTime(ort, wand.year, wand.month, wand.day, wand.hour, wand.minute, wand.second);
      return IcsZeit(_nachBerlin(dort.toUtc()), ganztags: false);
    }
  }
  return IcsZeit(wand, ganztags: false);
}

DateTime _nachBerlin(DateTime utc) {
  final b = tz.TZDateTime.from(DateTime.fromMillisecondsSinceEpoch(utc.millisecondsSinceEpoch, isUtc: true), berlin);
  return DateTime.utc(b.year, b.month, b.day, b.hour, b.minute, b.second);
}

/// Ortszeit Berlin (UTC-Träger) → echter Zeitpunkt (für Erinnerungen).
tz.TZDateTime alsBerlin(DateTime wand) =>
    tz.TZDateTime(berlin, wand.year, wand.month, wand.day, wand.hour, wand.minute, wand.second);

/// RFC-5545-Dauer („-P3D“, „-PT7H“, „-P2DT18H“, „P1W“) → Duration, sonst null.
Duration? dauerLesen(String roh) {
  final m = RegExp(r'^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$')
      .firstMatch(roh.trim().toUpperCase());
  if (m == null || roh.trim().toUpperCase().replaceAll(RegExp('[+-]'), '') == 'P') return null;
  int g(int i) => int.tryParse(m.group(i) ?? '') ?? 0;
  final d = Duration(days: g(2) * 7 + g(3), hours: g(4), minutes: g(5), seconds: g(6));
  return m.group(1) == '-' ? -d : d;
}

String hhmm(DateTime d) => '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';

/// Jetzt als Berliner Ortszeit (UTC-Träger) — die Zeit, in der der Kalender
/// rechnet, egal in welcher Zone das Handy gerade steht.
DateTime jetztBerlin([DateTime? echt]) {
  final b = tz.TZDateTime.from((echt ?? DateTime.now()).toUtc(), berlin);
  return DateTime.utc(b.year, b.month, b.day, b.hour, b.minute, b.second);
}
