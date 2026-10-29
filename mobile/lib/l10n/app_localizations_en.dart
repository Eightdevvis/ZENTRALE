// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get calendarViewDay => 'Day';

  @override
  String get calendarViewWeek => 'Week';

  @override
  String get calendarViewMonth => 'Month';

  @override
  String get calendarViewAgenda => 'Agenda';

  @override
  String get calendarViewSwitch => 'Change view';

  @override
  String get calendarToday => 'Today';

  @override
  String calendarWeekNumber(int week) {
    return 'W$week';
  }

  @override
  String get calendarAllDay => 'all day';

  @override
  String calendarMore(int count) {
    return '+$count';
  }

  @override
  String calendarDeadlineMust(String time) {
    return 'Must $time';
  }

  @override
  String calendarDeadlineShould(String label) {
    return 'Should: $label';
  }

  @override
  String get calendarDeadlineShouldMissed => 'Should missed';

  @override
  String get calendarWaitingForSync => 'waiting for sync';
}
