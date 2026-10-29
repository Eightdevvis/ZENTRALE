// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for German (`de`).
class AppLocalizationsDe extends AppLocalizations {
  AppLocalizationsDe([String locale = 'de']) : super(locale);

  @override
  String get calendarViewDay => 'Tag';

  @override
  String get calendarViewWeek => 'Woche';

  @override
  String get calendarViewMonth => 'Monat';

  @override
  String get calendarViewAgenda => 'Liste';

  @override
  String get calendarViewSwitch => 'Ansicht wechseln';

  @override
  String get calendarToday => 'Heute';

  @override
  String calendarWeekNumber(int week) {
    return 'KW $week';
  }

  @override
  String calendarMore(int count) {
    return '+$count';
  }

  @override
  String calendarDeadlineMust(String time) {
    return 'Muss $time';
  }

  @override
  String calendarDeadlineShould(String label) {
    return 'Soll: $label';
  }

  @override
  String get calendarDeadlineShouldMissed => 'Soll verpasst';

  @override
  String get calendarWaitingForSync => 'wartet auf Abgleich';

  @override
  String get peepholeRecenter => 'Zurück zur Mitte';

  @override
  String get peepholeMotionOn => 'Bewegung steuert';

  @override
  String get peepholeMotionOff => 'Bewegung aus – Finger schiebt';

  @override
  String get peepholeMotionStarting => 'Sensoren starten …';

  @override
  String get peepholeMotionUnavailable =>
      'Keine Bewegungssensoren – mit dem Finger schieben';

  @override
  String get peepholeHint =>
      'Schwenk das Handy über den Tisch · lang drücken: zurück zur Mitte';

  @override
  String get calendarTableTitle => 'Guckloch';

  @override
  String get calendarTableOpen => 'Guckloch – Kalender als Tisch';

  @override
  String get calendarTableAllDay => 'ganztags';

  @override
  String calendarTableMore(int count) {
    return '+$count weitere';
  }

  @override
  String get calendarTableToday => 'Heute';

  @override
  String get calendarTableEmpty => 'Noch kein Kalender auf dem Handy.';
}
