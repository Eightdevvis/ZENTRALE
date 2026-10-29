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
