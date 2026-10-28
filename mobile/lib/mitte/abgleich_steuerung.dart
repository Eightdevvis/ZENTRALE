// Wann abgeglichen wird und was danach passiert — ohne Oberfläche.
//
// Anlässe (Sasha, 28.10.2026): beim Start, nach jeder Antwort der KI, beim
// Herunterziehen in Chat und Kalender, nach einem neuen Termin. Nie zwei
// Läufe gleichzeitig: ein Anstoß während eines Laufs merkt sich nur, dass
// danach noch einer nötig ist. Danach laden Kalender & Co. neu ([nachher]).
//
// Die Mitte entsteht aus der Sitzung (Konto) — abgemeldet gibt es keinen
// Abgleich, und das Handy arbeitet allein weiter: nichts geht verloren, beim
// ersten Abgleich nach dem Anmelden wandert alles Eigene hoch.

import 'package:flutter/foundation.dart';

import '../ablage/ablage.dart';
import '../konto/konto.dart';
import '../krypto/tresor.dart';
import 'abgleich.dart';
import 'cloud.dart';
import 'http_mitte.dart';
import 'mitte.dart';

class AbgleichSteuerung extends ChangeNotifier {
  AbgleichSteuerung({
    required this.ablage,
    required this.konto,
    Mitte Function(Sitzung s)? mitteFuer,
  }) : _mitteFuer = mitteFuer ?? _cloudMitte;

  final Ablage ablage;
  final Konto konto;
  final Mitte Function(Sitzung s) _mitteFuer;

  /// Läuft nach jedem Abgleich (auch nach einem fehlgeschlagenen: lokal
  /// kann sich etwas geändert haben).
  final List<Future<void> Function()> nachher = [];

  static Mitte _cloudMitte(Sitzung s) =>
      HttpMitte(CloudClient(basis: s.server, token: s.token), Tresor(s.kontoSchluessel));

  Sitzung? sitzung;
  AbgleichZustand zustand = AbgleichZustand({});
  bool laeuft = false;
  bool _nochmal = false;

  bool get angemeldet => sitzung != null;

  Future<void> laden() async {
    sitzung = await konto.sitzung();
    zustand = await AbgleichZustand.lesen(ablage);
    notifyListeners();
  }

  /// Einmal abgleichen (oder, wenn gerade einer läuft, danach noch einmal).
  Future<void> jetzt() async {
    if (laeuft) {
      _nochmal = true;
      return;
    }
    laeuft = true;
    notifyListeners();
    try {
      do {
        _nochmal = false;
        sitzung ??= await konto.sitzung();
        final s = sitzung;
        if (s == null) break;
        try {
          await Abgleich(ablage, _mitteFuer(s)).laufen();
        } catch (e) {
          // Steht schon im Zustand (Einstellungen zeigen ihn); weiter offline.
          debugPrint('Abgleich: $e');
        }
      } while (_nochmal);
    } finally {
      laeuft = false;
      zustand = await AbgleichZustand.lesen(ablage);
      notifyListeners();
    }
    for (final f in nachher) {
      try {
        await f();
      } catch (e) {
        debugPrint('Nach dem Abgleich: $e');
      }
    }
  }

  Future<void> anmelden(String name, String passwort) async {
    sitzung = await konto.anmelden(name, passwort);
    notifyListeners();
    await jetzt();
  }

  Future<void> abmelden() async {
    await konto.abmelden();
    sitzung = null;
    notifyListeners();
  }
}
