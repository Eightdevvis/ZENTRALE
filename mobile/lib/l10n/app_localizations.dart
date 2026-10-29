import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_de.dart';
import 'app_localizations_en.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'l10n/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('de'),
    Locale('en'),
  ];

  /// Calendar mode: one day as a time grid
  ///
  /// In de, this message translates to:
  /// **'Tag'**
  String get calendarViewDay;

  /// Calendar mode: seven days as a time grid
  ///
  /// In de, this message translates to:
  /// **'Woche'**
  String get calendarViewWeek;

  /// Calendar mode: month grid
  ///
  /// In de, this message translates to:
  /// **'Monat'**
  String get calendarViewMonth;

  /// Calendar mode: the agenda list of the next days
  ///
  /// In de, this message translates to:
  /// **'Liste'**
  String get calendarViewAgenda;

  /// Tooltip of the view mode menu in the app bar
  ///
  /// In de, this message translates to:
  /// **'Ansicht wechseln'**
  String get calendarViewSwitch;

  /// Tooltip: jump to today
  ///
  /// In de, this message translates to:
  /// **'Heute'**
  String get calendarToday;

  /// Calendar week label
  ///
  /// In de, this message translates to:
  /// **'KW {week}'**
  String calendarWeekNumber(int week);

  /// More entries than fit in a month cell or all-day strip
  ///
  /// In de, this message translates to:
  /// **'+{count}'**
  String calendarMore(int count);

  /// Deadline marker: the hard 'must' time
  ///
  /// In de, this message translates to:
  /// **'Muss {time}'**
  String calendarDeadlineMust(String time);

  /// Marker of a deadline's soft 'should' time
  ///
  /// In de, this message translates to:
  /// **'Soll: {label}'**
  String calendarDeadlineShould(String label);

  /// The should time has passed, the must time not yet
  ///
  /// In de, this message translates to:
  /// **'Soll verpasst'**
  String get calendarDeadlineShouldMissed;

  /// Entered on the phone, not yet confirmed by the sync
  ///
  /// In de, this message translates to:
  /// **'wartet auf Abgleich'**
  String get calendarWaitingForSync;

  /// Tooltip: glide the peephole window back to its home point
  ///
  /// In de, this message translates to:
  /// **'Zurück zur Mitte'**
  String get peepholeRecenter;

  /// Tooltip/state: phone motion moves the window; tap switches it off
  ///
  /// In de, this message translates to:
  /// **'Bewegung steuert'**
  String get peepholeMotionOn;

  /// Tooltip/state: motion switched off by hand; tap switches it on
  ///
  /// In de, this message translates to:
  /// **'Bewegung aus – Finger schiebt'**
  String get peepholeMotionOff;

  /// Waiting for the first motion sensor reading
  ///
  /// In de, this message translates to:
  /// **'Sensoren starten …'**
  String get peepholeMotionStarting;

  /// Device has no usable gyroscope; finger panning only
  ///
  /// In de, this message translates to:
  /// **'Keine Bewegungssensoren – mit dem Finger schieben'**
  String get peepholeMotionUnavailable;

  /// Short hint shown when the peephole opens
  ///
  /// In de, this message translates to:
  /// **'Schwenk das Handy über den Tisch · lang drücken: zurück zur Mitte'**
  String get peepholeHint;

  /// Title of the calendar spread seen through the peephole
  ///
  /// In de, this message translates to:
  /// **'Guckloch'**
  String get calendarTableTitle;

  /// Tooltip of the calendar app bar action that opens the peephole
  ///
  /// In de, this message translates to:
  /// **'Guckloch – Kalender als Tisch'**
  String get calendarTableOpen;

  /// Event without a time
  ///
  /// In de, this message translates to:
  /// **'ganztags'**
  String get calendarTableAllDay;

  /// More events in a day cell than fit
  ///
  /// In de, this message translates to:
  /// **'+{count} weitere'**
  String calendarTableMore(int count);

  /// Marks today's cell
  ///
  /// In de, this message translates to:
  /// **'Heute'**
  String get calendarTableToday;

  /// No calendar data synced yet
  ///
  /// In de, this message translates to:
  /// **'Noch kein Kalender auf dem Handy.'**
  String get calendarTableEmpty;

  /// Title of the edit form
  ///
  /// In de, this message translates to:
  /// **'Termin ändern'**
  String get calendarEditTitle;

  /// Save button of the edit form
  ///
  /// In de, this message translates to:
  /// **'Speichern'**
  String get calendarSave;

  /// Place field
  ///
  /// In de, this message translates to:
  /// **'Ort'**
  String get calendarPlace;

  /// Edit form of a recurring event
  ///
  /// In de, this message translates to:
  /// **'Gilt für die ganze Serie; der erste Tag bleibt.'**
  String get calendarSeriesHint;

  /// Below the entry form
  ///
  /// In de, this message translates to:
  /// **'Steht sofort hier und geht beim nächsten Abgleich als Vorschlag an die Rechner.'**
  String get calendarProposalHint;

  /// Detail sheet action
  ///
  /// In de, this message translates to:
  /// **'Ändern'**
  String get calendarEdit;

  /// Detail sheet action
  ///
  /// In de, this message translates to:
  /// **'Löschen'**
  String get calendarDelete;

  /// Detail sheet action for a recurring event
  ///
  /// In de, this message translates to:
  /// **'Ganze Serie löschen'**
  String get calendarDeleteSeries;

  /// Confirm dialog
  ///
  /// In de, this message translates to:
  /// **'„{title}“ löschen?'**
  String calendarDeleteConfirm(String title);

  /// Dialog button
  ///
  /// In de, this message translates to:
  /// **'Abbrechen'**
  String get calendarCancel;

  /// Switch one occurrence of a series off
  ///
  /// In de, this message translates to:
  /// **'Nur dieses Vorkommen aus'**
  String get calendarOccurrenceOff;

  /// Switch one occurrence back on
  ///
  /// In de, this message translates to:
  /// **'Dieses Vorkommen wieder an'**
  String get calendarOccurrenceOn;

  /// State of a switched-off occurrence
  ///
  /// In de, this message translates to:
  /// **'ausgeschaltet'**
  String get calendarSwitchedOff;

  /// A recurring event
  ///
  /// In de, this message translates to:
  /// **'wiederkehrend'**
  String get calendarRecurring;

  /// Time of an all-day event
  ///
  /// In de, this message translates to:
  /// **'ganztägig'**
  String get calendarAllDayShort;

  /// Detail sheet: change waits for sync
  ///
  /// In de, this message translates to:
  /// **'Am Handy geändert — kommt mit dem nächsten Abgleich auf die Rechner.'**
  String get calendarPendingHint;

  /// A computer rejected the change
  ///
  /// In de, this message translates to:
  /// **'Abgelehnt: {reason}'**
  String calendarRejected(String reason);

  /// Banner above the calendar
  ///
  /// In de, this message translates to:
  /// **'{count, plural, =1{Eine Änderung wurde abgelehnt} other{{count} Änderungen wurden abgelehnt}}'**
  String calendarRejectedCount(int count);

  /// Phone's version of a rejected change
  ///
  /// In de, this message translates to:
  /// **'Am Handy: {summary}'**
  String calendarMine(String summary);

  /// Cloud's version of a rejected change
  ///
  /// In de, this message translates to:
  /// **'In der Cloud: {summary}'**
  String calendarCloud(String summary);

  /// The event no longer exists in the cloud
  ///
  /// In de, this message translates to:
  /// **'In der Cloud gelöscht'**
  String get calendarCloudGone;

  /// The phone's version is a deletion
  ///
  /// In de, this message translates to:
  /// **'am Handy gelöscht'**
  String get calendarDeletedHere;

  /// Re-propose the phone's version on top of the cloud's
  ///
  /// In de, this message translates to:
  /// **'Meine Fassung neu vorschlagen'**
  String get calendarKeepMine;

  /// Drop the phone's version
  ///
  /// In de, this message translates to:
  /// **'Fassung der Cloud nehmen'**
  String get calendarTakeCloud;

  /// Reason code reasonNotFound from core REASONS
  ///
  /// In de, this message translates to:
  /// **'den Termin gibt es nicht'**
  String get reasonNotFound;

  /// Reason code reasonDeleteNeedsBase from core REASONS
  ///
  /// In de, this message translates to:
  /// **'zum Löschen fehlt, welche Fassung das Handy sah'**
  String get reasonDeleteNeedsBase;

  /// Reason code reasonChangedNotDeleted from core REASONS
  ///
  /// In de, this message translates to:
  /// **'inzwischen in der Cloud geändert — nicht gelöscht'**
  String get reasonChangedNotDeleted;

  /// Reason code reasonUnreadable from core REASONS
  ///
  /// In de, this message translates to:
  /// **'kein lesbarer Termin'**
  String get reasonUnreadable;

  /// Reason code reasonOneUid from core REASONS
  ///
  /// In de, this message translates to:
  /// **'eine Datei enthält genau einen Termin'**
  String get reasonOneUid;

  /// Reason code reasonNoMaster from core REASONS
  ///
  /// In de, this message translates to:
  /// **'der Hauptteil des Termins fehlt'**
  String get reasonNoMaster;

  /// Reason code reasonNameTaken from core REASONS
  ///
  /// In de, this message translates to:
  /// **'unter diesem Namen liegt schon ein anderer Termin'**
  String get reasonNameTaken;

  /// Reason code reasonDeletedInCloud from core REASONS
  ///
  /// In de, this message translates to:
  /// **'in der Cloud gelöscht, am Handy geändert — nicht wiederhergestellt'**
  String get reasonDeletedInCloud;

  /// Reason code reasonNoLayer from core REASONS
  ///
  /// In de, this message translates to:
  /// **'diese Ebene gibt es nicht'**
  String get reasonNoLayer;

  /// Reason code reasonBadName from core REASONS
  ///
  /// In de, this message translates to:
  /// **'der Dateiname passt nicht zur UID'**
  String get reasonBadName;

  /// Reason code reasonUidTwice from core REASONS
  ///
  /// In de, this message translates to:
  /// **'diese UID gibt es in der Cloud mehrmals'**
  String get reasonUidTwice;

  /// Reason code reasonOtherName from core REASONS
  ///
  /// In de, this message translates to:
  /// **'den Termin gibt es schon unter anderem Namen'**
  String get reasonOtherName;

  /// Reason code reasonTargetTaken from core REASONS
  ///
  /// In de, this message translates to:
  /// **'am Ziel liegt schon eine andere Datei'**
  String get reasonTargetTaken;

  /// Reason code reasonNeedsBase from core REASONS
  ///
  /// In de, this message translates to:
  /// **'den Termin gibt es schon — zum Ändern fehlt, welche Fassung das Handy sah'**
  String get reasonNeedsBase;

  /// Reason code reasonBaseUnknown from core REASONS
  ///
  /// In de, this message translates to:
  /// **'inzwischen in der Cloud geändert, und die Fassung vom Handy ist dort unbekannt'**
  String get reasonBaseUnknown;

  /// Reason code reasonMergeUnreadable from core REASONS
  ///
  /// In de, this message translates to:
  /// **'Zusammenführen ergab keinen lesbaren Termin'**
  String get reasonMergeUnreadable;

  /// Reason code reasonConflict from core REASONS
  ///
  /// In de, this message translates to:
  /// **'Widerspruch — am Handy und in der Cloud verschieden geändert'**
  String get reasonConflict;

  /// Reason code reasonSameFile from core REASONS
  ///
  /// In de, this message translates to:
  /// **'ein anderer Vorschlag betrifft dieselbe Datei'**
  String get reasonSameFile;

  /// Reason code reasonConflictChanged from core REASONS
  ///
  /// In de, this message translates to:
  /// **'am Handy und in der Cloud verschieden geändert'**
  String get reasonConflictChanged;

  /// Reason code reasonConflictDeleted from core REASONS
  ///
  /// In de, this message translates to:
  /// **'auf einer Seite gelöscht, auf der anderen geändert'**
  String get reasonConflictDeleted;

  /// Reason code reasonUnknown from core REASONS
  ///
  /// In de, this message translates to:
  /// **'abgelehnt ({code})'**
  String reasonUnknown(String code);

  /// Heading of the self-update section in settings and title of the update page.
  ///
  /// In de, this message translates to:
  /// **'App-Aktualisierung'**
  String get updateTitle;

  /// The installed app version; code = Android versionCode.
  ///
  /// In de, this message translates to:
  /// **'Installiert: {version} ({code})'**
  String updateInstalled(String version, int code);

  /// Button: ask the cloud for a newer version.
  ///
  /// In de, this message translates to:
  /// **'Nach Update suchen'**
  String get updateCheck;

  /// Status while asking the cloud.
  ///
  /// In de, this message translates to:
  /// **'Suche nach einer neuen Version …'**
  String get updateChecking;

  /// Status: no newer version.
  ///
  /// In de, this message translates to:
  /// **'Die App ist aktuell.'**
  String get updateUpToDate;

  /// Status: the cloud has no release yet.
  ///
  /// In de, this message translates to:
  /// **'Noch keine Version veröffentlicht.'**
  String get updateNoRelease;

  /// Status: no session, so no update check.
  ///
  /// In de, this message translates to:
  /// **'Melde dich beim ZENTRALE-Konto an, dann sucht die App selbst nach Updates.'**
  String get updateNotLoggedIn;

  /// Status: self-update is off (Play build or Play install).
  ///
  /// In de, this message translates to:
  /// **'Diese Fassung wird über den Play Store aktualisiert.'**
  String get updateDisabled;

  /// Status: a newer release exists.
  ///
  /// In de, this message translates to:
  /// **'Neue Version {version} ist da.'**
  String updateAvailable(String version);

  /// Release notes of the new version.
  ///
  /// In de, this message translates to:
  /// **'Neu: {notes}'**
  String updateNotes(String notes);

  /// Button: download the new APK and start the installer.
  ///
  /// In de, this message translates to:
  /// **'Laden und installieren'**
  String get updateDownload;

  /// Download progress.
  ///
  /// In de, this message translates to:
  /// **'Wird geladen … {percent} %'**
  String updateDownloading(int percent);

  /// Status while the SHA-256 is checked.
  ///
  /// In de, this message translates to:
  /// **'Prüfe die Datei …'**
  String get updateVerifying;

  /// Asks before downloading on a metered network.
  ///
  /// In de, this message translates to:
  /// **'Du bist im mobilen Netz. Das Update ist etwa {megabytes} MB groß.'**
  String updateMetered(int megabytes);

  /// Button: download on the metered network.
  ///
  /// In de, this message translates to:
  /// **'Trotzdem laden'**
  String get updateDownloadAnyway;

  /// Button: not now.
  ///
  /// In de, this message translates to:
  /// **'Später'**
  String get updateLater;

  /// The 'install unknown apps' permission is missing.
  ///
  /// In de, this message translates to:
  /// **'Android muss einmal erlauben, dass ZENTRALE Updates installiert.'**
  String get updateNeedsPermission;

  /// Button: open Android's 'install unknown apps' screen.
  ///
  /// In de, this message translates to:
  /// **'Erlaubnis öffnen'**
  String get updateOpenPermission;

  /// Button: hand the verified APK to Android's installer.
  ///
  /// In de, this message translates to:
  /// **'Installieren'**
  String get updateInstall;

  /// Status after the system installer was opened.
  ///
  /// In de, this message translates to:
  /// **'Android fragt jetzt, ob installiert werden soll.'**
  String get updateInstallerOpened;

  /// Error: network or server down.
  ///
  /// In de, this message translates to:
  /// **'Die Cloud ist gerade nicht erreichbar.'**
  String get updateFailedNetwork;

  /// Error: SHA-256 or size mismatch.
  ///
  /// In de, this message translates to:
  /// **'Die geladene Datei stimmt nicht mit der Prüfsumme überein. Nichts wurde installiert.'**
  String get updateFailedChecksum;

  /// Error: unreadable or invalid manifest.
  ///
  /// In de, this message translates to:
  /// **'Die Cloud schickte keine gültige Versionsangabe.'**
  String get updateFailedServer;

  /// Error: Android installer could not be started.
  ///
  /// In de, this message translates to:
  /// **'Der Installer ließ sich nicht öffnen.'**
  String get updateFailedInstall;

  /// Tooltip/semantics of the small dot on the start screen.
  ///
  /// In de, this message translates to:
  /// **'Update verfügbar'**
  String get updateHint;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['de', 'en'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'de':
      return AppLocalizationsDe();
    case 'en':
      return AppLocalizationsEn();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
