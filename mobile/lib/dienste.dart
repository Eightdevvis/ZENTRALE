// Die Dienste der App an EINER Stelle für die Seiten: Ablage, Einstellungen,
// Abgleich, Kalender. main.dart steckt sie einmal zusammen; eine Seite, die
// über die Liste `bereiche` (start/startseite.dart) geöffnet wird, holt sie
// sich hier — so bleibt die Liste ein schlichter Eintrag je Bereich.

import 'package:flutter/widgets.dart';

import 'ablage/ablage.dart';
import 'einstellungen/einstellungen.dart';
import 'kalender/kalender_steuerung.dart';
import 'mitte/abgleich_steuerung.dart';

class Dienste extends InheritedWidget {
  const Dienste({
    super.key,
    required this.ablage,
    required this.einstellungen,
    required this.abgleich,
    required this.kalender,
    required super.child,
  });

  final Ablage ablage;
  final Einstellungen einstellungen;
  final AbgleichSteuerung abgleich;
  final KalenderSteuerung kalender;

  static Dienste von(BuildContext context) {
    final d = context.dependOnInheritedWidgetOfExactType<Dienste>();
    assert(d != null, 'Dienste fehlen über dieser Seite (main.dart)');
    return d!;
  }

  @override
  bool updateShouldNotify(Dienste alt) => false; // werden nie ersetzt
}
