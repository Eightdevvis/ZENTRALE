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

  @override
  String get calendarEditTitle => 'Edit event';

  @override
  String get calendarSave => 'Save';

  @override
  String get calendarPlace => 'Place';

  @override
  String get calendarSeriesHint =>
      'Applies to the whole series; the first day stays.';

  @override
  String get calendarProposalHint =>
      'Shows here at once and goes to the computers as a proposal at the next sync.';

  @override
  String get calendarEdit => 'Edit';

  @override
  String get calendarDelete => 'Delete';

  @override
  String get calendarDeleteSeries => 'Delete whole series';

  @override
  String calendarDeleteConfirm(String title) {
    return 'Delete “$title”?';
  }

  @override
  String get calendarCancel => 'Cancel';

  @override
  String get calendarOccurrenceOff => 'Switch off only this occurrence';

  @override
  String get calendarOccurrenceOn => 'Switch this occurrence back on';

  @override
  String get calendarSwitchedOff => 'switched off';

  @override
  String get calendarRecurring => 'recurring';

  @override
  String get calendarAllDayShort => 'all day';

  @override
  String get calendarPendingHint =>
      'Changed on the phone — goes to the computers at the next sync.';

  @override
  String calendarRejected(String reason) {
    return 'Rejected: $reason';
  }

  @override
  String calendarRejectedCount(int count) {
    String _temp0 = intl.Intl.pluralLogic(
      count,
      locale: localeName,
      other: '$count changes were rejected',
      one: 'One change was rejected',
    );
    return '$_temp0';
  }

  @override
  String calendarMine(String summary) {
    return 'On the phone: $summary';
  }

  @override
  String calendarCloud(String summary) {
    return 'In the cloud: $summary';
  }

  @override
  String get calendarCloudGone => 'Deleted in the cloud';

  @override
  String get calendarDeletedHere => 'deleted on the phone';

  @override
  String get calendarKeepMine => 'Propose mine again';

  @override
  String get calendarTakeCloud => 'Take the cloud\'s version';

  @override
  String get reasonNotFound => 'the event does not exist';

  @override
  String get reasonDeleteNeedsBase =>
      'deleting needs to know which version was seen';

  @override
  String get reasonChangedNotDeleted =>
      'changed in the cloud meanwhile — not deleted';

  @override
  String get reasonUnreadable => 'not a readable event';

  @override
  String get reasonOneUid => 'one file holds exactly one event';

  @override
  String get reasonNoMaster => 'the main part of the event is missing';

  @override
  String get reasonNameTaken => 'another event lives under this name';

  @override
  String get reasonDeletedInCloud =>
      'deleted in the cloud, changed on the phone — not restored';

  @override
  String get reasonNoLayer => 'this layer does not exist';

  @override
  String get reasonBadName => 'the file name does not match the UID';

  @override
  String get reasonUidTwice => 'this UID exists more than once in the cloud';

  @override
  String get reasonOtherName => 'this event already exists under another name';

  @override
  String get reasonTargetTaken => 'another file already exists at the target';

  @override
  String get reasonNeedsBase =>
      'this event already exists — changing needs to know which version was seen';

  @override
  String get reasonBaseUnknown =>
      'changed in the cloud meanwhile, and the phone\'s version is unknown there';

  @override
  String get reasonMergeUnreadable => 'merging gave no readable event';

  @override
  String get reasonConflict =>
      'conflict — changed differently on the phone and in the cloud';

  @override
  String get reasonSameFile => 'another proposal touches the same file';

  @override
  String get reasonConflictChanged =>
      'changed differently on the phone and in the cloud';

  @override
  String get reasonConflictDeleted =>
      'deleted on one side, changed on the other';

  @override
  String reasonUnknown(String code) {
    return 'rejected ($code)';
  }

  @override
  String get updateTitle => 'App update';

  @override
  String updateInstalled(String version, int code) {
    return 'Installed: $version ($code)';
  }

  @override
  String get updateCheck => 'Check for update';

  @override
  String get updateChecking => 'Looking for a new version …';

  @override
  String get updateUpToDate => 'The app is up to date.';

  @override
  String get updateNoRelease => 'No version has been published yet.';

  @override
  String get updateNotLoggedIn =>
      'Log in to your ZENTRALE account and the app looks for updates itself.';

  @override
  String get updateDisabled => 'This copy is updated through the Play Store.';

  @override
  String updateAvailable(String version) {
    return 'New version $version is available.';
  }

  @override
  String updateNotes(String notes) {
    return 'New: $notes';
  }

  @override
  String get updateDownload => 'Download and install';

  @override
  String updateDownloading(int percent) {
    return 'Downloading … $percent %';
  }

  @override
  String get updateVerifying => 'Checking the file …';

  @override
  String updateMetered(int megabytes) {
    return 'You are on mobile data. The update is about $megabytes MB.';
  }

  @override
  String get updateDownloadAnyway => 'Download anyway';

  @override
  String get updateLater => 'Later';

  @override
  String get updateNeedsPermission =>
      'Android needs to allow ZENTRALE to install updates once.';

  @override
  String get updateOpenPermission => 'Open permission';

  @override
  String get updateInstall => 'Install';

  @override
  String get updateInstallerOpened => 'Android now asks whether to install.';

  @override
  String get updateFailedNetwork => 'The cloud cannot be reached right now.';

  @override
  String get updateFailedChecksum =>
      'The downloaded file does not match its checksum. Nothing was installed.';

  @override
  String get updateFailedServer =>
      'The cloud did not send a valid version description.';

  @override
  String get updateFailedInstall => 'The installer could not be opened.';

  @override
  String get updateHint => 'Update available';
}
