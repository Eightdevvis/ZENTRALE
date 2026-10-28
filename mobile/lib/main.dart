// ZEN-MOBILE — ZENTRALE auf dem Handy.
//
// Das Handy ist ein Knoten wie Laptop und PC (memory/system/zen_mobile.md):
// eigene Gesprächs-Datei, Abgleich über die Mitte (die ZENTRALE-Cloud),
// KI direkt in der Cloud, Kalender aus der Mitte mit Erinnerungen.
// Hier wird nur zusammengesteckt; jede Aufgabe hat ihren eigenen Ordner.

import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'ablage/ablage.dart';
import 'auge/pupillen_route.dart';
import 'chat/chat_seite.dart';
import 'chat/chat_steuerung.dart';
import 'dienste.dart';
import 'einstellungen/einstellungen.dart';
import 'einstellungen/einstellungen_seite.dart';
import 'gespraeche/gespraeche.dart';
import 'kalender/erinnerungen.dart';
import 'kalender/kalender_steuerung.dart';
import 'kalender/zeit.dart';
import 'ki/anthropic.dart';
import 'ki/ki.dart';
import 'konto/geheim.dart';
import 'konto/konto.dart';
import 'mitte/abgleich_steuerung.dart';
import 'mitte/regeln.dart';
import 'start/startseite.dart';
import 'thema/farben.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  zonenLaden();
  final dokumente = await getApplicationDocumentsDirectory();
  final ablage = PlattenAblage(Directory('${dokumente.path}/daten'));
  await ablage.wurzel.create(recursive: true);
  final einstellungen = Einstellungen();
  final konto = Konto(KeystoreSitzung());
  final abgleich = AbgleichSteuerung(ablage: ablage, konto: konto);
  final kalender = KalenderSteuerung(
      ablage: ablage, erinnerungen: AndroidErinnerungen(), anstossen: abgleich.jetzt);
  abgleich.nachher.add(kalender.laden);
  final steuerung = ChatSteuerung(
    ablage: ablage,
    gespraeche: Gespraeche(ablage, knoten: knotenName),
    ki: AnthropicAnbieter(kiSchluessel(einstellungen, ablage, konto),
        ohneSchluessel: () async => SchluesselFehlt(angemeldet: await konto.sitzung() != null)),
    abgleich: abgleich,
    kalender: kalender.ueberblick,
  );
  runApp(Dienste(
    ablage: ablage,
    einstellungen: einstellungen,
    abgleich: abgleich,
    kalender: kalender,
    child: ZenMobile(steuerung: steuerung),
  ));
  await abgleich.laden();
  unawaited(kalender.laden());
  await steuerung.start(); // gleicht beim Start ab
}

class ZenMobile extends StatelessWidget {
  const ZenMobile({super.key, required this.steuerung});

  final ChatSteuerung steuerung;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'ZENTRALE',
        debugShowCheckedModeBanner: false,
        theme: zentraleThema(Brightness.light),
        darkTheme: zentraleThema(Brightness.dark),
        home: Builder(
          builder: (context) => Startseite(
            kiOeffnen: (mandel) => Navigator.of(context).push(pupillenRoute<void>(
              mandel: mandel,
              farbe: AugeFarben.von(context).pupille,
              seite: (_) => ChatSeite(
                steuerung: steuerung,
                einstellungen: () {
                  final d = Dienste.von(context);
                  return EinstellungenSeite(
                      einstellungen: d.einstellungen, ablage: d.ablage, abgleich: d.abgleich);
                },
              ),
            )),
          ),
        ),
      );
}
