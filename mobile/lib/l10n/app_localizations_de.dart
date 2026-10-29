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
  String get calendarAllDay => 'ganztägig';

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
}
