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

  @override
  String get peepholeRecenter => 'Back to center';

  @override
  String get peepholeMotionOn => 'Motion steers';

  @override
  String get peepholeMotionOff => 'Motion off – finger pans';

  @override
  String get peepholeMotionStarting => 'Starting sensors …';

  @override
  String get peepholeMotionUnavailable =>
      'No motion sensors – pan with your finger';

  @override
  String get peepholeHint =>
      'Swing the phone over the table · long press: back to center';

  @override
  String get calendarTableTitle => 'Peephole';

  @override
  String get calendarTableOpen => 'Peephole – calendar as a table';

  @override
  String get calendarTableAllDay => 'all day';

  @override
  String calendarTableMore(int count) {
    return '+$count more';
  }

  @override
  String get calendarTableToday => 'Today';

  @override
  String get calendarTableEmpty => 'No calendar on the phone yet.';
}
