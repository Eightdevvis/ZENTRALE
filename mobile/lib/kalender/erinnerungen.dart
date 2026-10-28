// Erinnerungen am Handy: jeder VALARM eines Termins wird eine Android-
// Benachrichtigung (Sasha will Google Kalender ablösen — die App muss
// erinnern, wie Google es tat). Nach jedem Abgleich wird ALLES neu gestellt:
// alte weg, die nächsten [tageVoraus] Tage neu. So gibt es keine verwaisten
// Erinnerungen an gelöschte oder verschobene Termine.
//
// Zwei Teile: [planen] rechnet rein (testbar), [ErinnerungsDienst] stellt sie
// (Android: flutter_local_notifications; Tests: im Speicher). Versteckte
// Vorkommen (abgeschaltet, Pause) erinnern nie.

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'kalender.dart';
import 'regel.dart';
import 'zeit.dart';

const tageVoraus = 30;

/// Android hält höchstens ~500 Wecker je App — wir bleiben weit darunter.
const hoechstens = 120;

class Wecker {
  Wecker({required this.id, required this.wann, required this.titel, required this.text});
  final int id;

  /// Ortszeit Berlin (UTC-Träger).
  final DateTime wann;
  final String titel, text;
}

/// Stabile Nummer je (Termin, Tag, Abstand) — dieselbe Erinnerung behält ihre id.
int _id(String s) {
  var h = 0x811c9dc5;
  for (final c in s.codeUnits) {
    h = ((h ^ c) * 0x01000193) & 0x7fffffff;
  }
  return h;
}

String _wann(Vorkommen v) {
  if (v.zeit == null) return 'ganztägig';
  return v.deadline ? 'Deadline ${v.zeit}' : v.zeit!;
}

/// Die Erinnerungen von [jetzt] bis [tageVoraus] Tage danach, früheste zuerst.
List<Wecker> planen(Kalender k, DateTime jetzt, {int tage = tageVoraus}) {
  final von = tagVon(jetzt);
  // Ein Vorwarnung von 3 Tagen für einen Termin in 31 Tagen fällt in die
  // nächsten 30 — darum die Vorkommen etwas weiter voraus holen.
  final raus = <Wecker>[];
  final gesehen = <int>{};
  for (final MapEntry(key: tag, value: l) in k.vorkommen(von, von.add(Duration(days: tage + 31))).entries) {
    for (final v in l) {
      if (v.versteckt) continue;
      for (final e in v.erinnerungen) {
        DateTime? wann;
        if (e.absolut != null) {
          wann = e.absolut;
        } else if (e.minutenVorher != null) {
          final bezug = e.vomEnde ? (v.endeZeit ?? v.beginn) : v.beginn;
          wann = bezug.subtract(Duration(minutes: e.minutenVorher!));
        }
        if (wann == null || !wann.isAfter(jetzt) || wann.isAfter(jetzt.add(Duration(days: tage)))) continue;
        final id = _id('${v.kennung}|$tag|${wann.toIso8601String()}');
        if (!gesehen.add(id)) continue;
        final ort = v.ort == null ? '' : ' · ${v.ort}';
        raus.add(Wecker(id: id, wann: wann, titel: v.label,
            text: '${_tagText(v.tag, jetzt)} ${_wann(v)}$ort'));
      }
    }
  }
  raus.sort((a, b) => a.wann.compareTo(b.wann));
  return raus.take(hoechstens).toList();
}

const _wt = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

String _tagText(DateTime tag, DateTime jetzt) {
  final d = tag.difference(tagVon(jetzt)).inDays;
  if (d == 0) return 'Heute';
  if (d == 1) return 'Morgen';
  return '${_wt[tag.weekday - 1]} ${tag.day}.${tag.month}.';
}

abstract class ErinnerungsDienst {
  /// Alle bisherigen Erinnerungen weg, diese neu.
  Future<void> stellen(List<Wecker> wecker);

  /// Erlaubnis fragen (Benachrichtigungen, pünktliche Wecker). Einmal, wenn
  /// es zum ersten Mal Erinnerungen gibt — nicht beim Start.
  Future<void> erlaubnisFragen();
}

class SpeicherErinnerungen implements ErinnerungsDienst {
  List<Wecker> gestellt = [];
  int gefragt = 0;
  @override
  Future<void> stellen(List<Wecker> wecker) async => gestellt = [...wecker];
  @override
  Future<void> erlaubnisFragen() async => gefragt++;
}

/// Android über flutter_local_notifications.
class AndroidErinnerungen implements ErinnerungsDienst {
  final _p = FlutterLocalNotificationsPlugin();
  bool _bereit = false;

  static const _kanal = AndroidNotificationDetails(
    'termine', 'Termine',
    channelDescription: 'Erinnerungen an Termine und Deadlines aus dem ZENTRALE-Kalender',
    importance: Importance.high,
    priority: Priority.high,
  );

  Future<AndroidFlutterLocalNotificationsPlugin?> _bereiten() async {
    if (!_bereit) {
      await _p.initialize(
          settings: const InitializationSettings(android: AndroidInitializationSettings('@mipmap/ic_launcher')));
      _bereit = true;
    }
    return _p.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
  }

  @override
  Future<void> erlaubnisFragen() async {
    final a = await _bereiten();
    await a?.requestNotificationsPermission();
    if (await a?.canScheduleExactNotifications() != true) await a?.requestExactAlarmsPermission();
  }

  @override
  Future<void> stellen(List<Wecker> wecker) async {
    final a = await _bereiten();
    await _p.cancelAll();
    // Pünktlich, wenn erlaubt; sonst lässt Android sie bis zu einigen Minuten später kommen.
    final genau = await a?.canScheduleExactNotifications() == true;
    for (final w in wecker) {
      await _p.zonedSchedule(
        id: w.id,
        title: w.titel,
        body: w.text,
        scheduledDate: alsBerlin(w.wann),
        notificationDetails: const NotificationDetails(android: _kanal),
        androidScheduleMode:
            genau ? AndroidScheduleMode.exactAllowWhileIdle : AndroidScheduleMode.inexactAllowWhileIdle,
      );
    }
  }
}
