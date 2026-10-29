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

  @override
  String get calendarEditTitle => 'Termin ändern';

  @override
  String get calendarSave => 'Speichern';

  @override
  String get calendarPlace => 'Ort';

  @override
  String get calendarSeriesHint =>
      'Gilt für die ganze Serie; der erste Tag bleibt.';

  @override
  String get calendarProposalHint =>
      'Steht sofort hier und geht beim nächsten Abgleich als Vorschlag an die Rechner.';

  @override
  String get calendarEdit => 'Ändern';

  @override
  String get calendarDelete => 'Löschen';

  @override
  String get calendarDeleteSeries => 'Ganze Serie löschen';

  @override
  String calendarDeleteConfirm(String title) {
    return '„$title“ löschen?';
  }

  @override
  String get calendarCancel => 'Abbrechen';

  @override
  String get calendarOccurrenceOff => 'Nur dieses Vorkommen aus';

  @override
  String get calendarOccurrenceOn => 'Dieses Vorkommen wieder an';

  @override
  String get calendarSwitchedOff => 'ausgeschaltet';

  @override
  String get calendarRecurring => 'wiederkehrend';

  @override
  String get calendarAllDayShort => 'ganztägig';

  @override
  String get calendarPendingHint =>
      'Am Handy geändert — kommt mit dem nächsten Abgleich auf die Rechner.';

  @override
  String calendarRejected(String reason) {
    return 'Abgelehnt: $reason';
  }

  @override
  String calendarRejectedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count Änderungen wurden abgelehnt',
      one: 'Eine Änderung wurde abgelehnt',
    );
    return '$_temp0';
  }

  @override
  String calendarMine(String summary) {
    return 'Am Handy: $summary';
  }

  @override
  String calendarCloud(String summary) {
    return 'In der Cloud: $summary';
  }

  @override
  String get calendarCloudGone => 'In der Cloud gelöscht';

  @override
  String get calendarDeletedHere => 'am Handy gelöscht';

  @override
  String get calendarKeepMine => 'Meine Fassung neu vorschlagen';

  @override
  String get calendarTakeCloud => 'Fassung der Cloud nehmen';

  @override
  String get reasonNotFound => 'den Termin gibt es nicht';

  @override
  String get reasonDeleteNeedsBase =>
      'zum Löschen fehlt, welche Fassung das Handy sah';

  @override
  String get reasonChangedNotDeleted =>
      'inzwischen in der Cloud geändert — nicht gelöscht';

  @override
  String get reasonUnreadable => 'kein lesbarer Termin';

  @override
  String get reasonOneUid => 'eine Datei enthält genau einen Termin';

  @override
  String get reasonNoMaster => 'der Hauptteil des Termins fehlt';

  @override
  String get reasonNameTaken =>
      'unter diesem Namen liegt schon ein anderer Termin';

  @override
  String get reasonDeletedInCloud =>
      'in der Cloud gelöscht, am Handy geändert — nicht wiederhergestellt';

  @override
  String get reasonNoLayer => 'diese Ebene gibt es nicht';

  @override
  String get reasonBadName => 'der Dateiname passt nicht zur UID';

  @override
  String get reasonUidTwice => 'diese UID gibt es in der Cloud mehrmals';

  @override
  String get reasonOtherName => 'den Termin gibt es schon unter anderem Namen';

  @override
  String get reasonTargetTaken => 'am Ziel liegt schon eine andere Datei';

  @override
  String get reasonNeedsBase =>
      'den Termin gibt es schon — zum Ändern fehlt, welche Fassung das Handy sah';

  @override
  String get reasonBaseUnknown =>
      'inzwischen in der Cloud geändert, und die Fassung vom Handy ist dort unbekannt';

  @override
  String get reasonMergeUnreadable =>
      'Zusammenführen ergab keinen lesbaren Termin';

  @override
  String get reasonConflict =>
      'Widerspruch — am Handy und in der Cloud verschieden geändert';

  @override
  String get reasonSameFile => 'ein anderer Vorschlag betrifft dieselbe Datei';

  @override
  String get reasonConflictChanged =>
      'am Handy und in der Cloud verschieden geändert';

  @override
  String get reasonConflictDeleted =>
      'auf einer Seite gelöscht, auf der anderen geändert';

  @override
  String reasonUnknown(String code) {
    return 'abgelehnt ($code)';
  }
}
