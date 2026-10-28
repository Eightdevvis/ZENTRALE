// Die Kalender-Logik ohne Oberfläche: laden (nach jedem Abgleich), neuen
// Termin vorschlagen, Erinnerungen neu stellen, Überblick für die KI. Die
// Seiten zeichnen nur, was hier steht.

import 'package:flutter/foundation.dart';

import '../ablage/ablage.dart';
import '../mitte/abgleich.dart';
import 'erinnerungen.dart';
import 'kalender.dart';
import 'termin_schreiben.dart';
import 'ueberblick.dart';
import 'zeit.dart';

class KalenderSteuerung extends ChangeNotifier {
  KalenderSteuerung({required this.ablage, this.erinnerungen, DateTime Function()? uhr, this.anstossen})
      : _uhr = uhr ?? jetztBerlin;

  final Ablage ablage;
  final ErinnerungsDienst? erinnerungen;

  /// Abgleich anstoßen, nachdem ein Termin dazukam (bringt ihn in den Eingang).
  final Future<void> Function()? anstossen;
  final DateTime Function() _uhr;

  Kalender kalender = Kalender.leer;
  bool _gefragt = false;

  DateTime get jetzt => _uhr();

  Future<void> laden() async {
    kalender = await Kalender.laden(ablage, wartend: await Abgleich.wartend(ablage));
    notifyListeners();
    await _erinnerungenStellen();
  }

  Future<void> _erinnerungenStellen() async {
    final e = erinnerungen;
    if (e == null) return;
    try {
      final w = planen(kalender, jetzt);
      // Erlaubnis erst fragen, wenn es wirklich etwas zu erinnern gibt.
      if (w.isNotEmpty && !_gefragt) {
        _gefragt = true;
        await e.erlaubnisFragen();
      }
      await e.stellen(w);
    } catch (f) {
      debugPrint('Erinnerungen nicht gestellt: $f');
    }
  }

  /// Ebenen, in die das Handy eintragen darf (die es in der Mitte gibt).
  List<Ebene> get ebenenZumEintragen =>
      [for (final e in kalender.ebenen) if (e.name != ebeneRhythmus) e];

  /// Neuer Termin als Vorschlag: Datei in die Ablage (sofort sichtbar, „wartet
  /// auf Abgleich“), dann Abgleich → Eingang → ein Rechner übernimmt ihn.
  Future<String> eintragen(NeuerTermin t, {String ebene = ebeneTermine}) async {
    String uid;
    do {
      uid = neueUid();
    } while (kalender.uids.contains(uid));
    final pfad = '$kalenderOrdner/$ebene/${dateiName(uid)}';
    await ablage.schreiben(pfad, terminIcs(t, uid, DateTime.now().toUtc()));
    await laden();
    final a = anstossen;
    if (a != null) await a();
    return uid;
  }

  /// Für die KI: der Kalender der nächsten 14 Tage (null = keiner da).
  Future<String?> ueberblick() async {
    if (kalender.istLeer) await laden();
    return kalenderUeberblick(kalender, jetzt);
  }
}
