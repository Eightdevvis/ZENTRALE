// ZEN-MOBILE — ZENTRALE auf dem Handy.
//
// Das Handy ist ein Knoten wie Laptop und PC (memory/system/zen_mobile.md):
// eigene Gesprächs-Datei, Abgleich über die Mitte, KI direkt in der Cloud.
// Hier wird nur zusammengesteckt; jede Aufgabe hat ihren eigenen Ordner.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';

import 'ablage/ablage.dart';
import 'chat/chat_seite.dart';
import 'chat/chat_steuerung.dart';
import 'einstellungen/einstellungen.dart';
import 'einstellungen/einstellungen_seite.dart';
import 'gespraeche/gespraeche.dart';
import 'ki/anthropic.dart';
import 'start/startseite.dart';
import 'thema/farben.dart';

/// Name dieses Knotens in Dateinamen und Ereignissen.
const knoten = 'handy';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final dokumente = await getApplicationDocumentsDirectory();
  final ablage = PlattenAblage(Directory('${dokumente.path}/daten'));
  await ablage.wurzel.create(recursive: true);
  final einstellungen = Einstellungen();
  final steuerung = ChatSteuerung(
    ablage: ablage,
    gespraeche: Gespraeche(ablage, knoten: knoten),
    ki: AnthropicAnbieter(einstellungen.anthropicSchluessel),
    abgleich: null, // kommt, sobald das Format der Mitte steht
  );
  runApp(ZenMobile(steuerung: steuerung, einstellungen: einstellungen, ablage: ablage));
  await steuerung.start();
}

class ZenMobile extends StatelessWidget {
  const ZenMobile({
    super.key,
    required this.steuerung,
    required this.einstellungen,
    required this.ablage,
  });

  final ChatSteuerung steuerung;
  final Einstellungen einstellungen;
  final Ablage ablage;

  @override
  Widget build(BuildContext context) => MaterialApp(
        title: 'ZENTRALE',
        debugShowCheckedModeBanner: false,
        theme: zentraleThema(Brightness.light),
        darkTheme: zentraleThema(Brightness.dark),
        home: Builder(
          builder: (context) => Startseite(
            kiOeffnen: () => Navigator.of(context).push(PageRouteBuilder(
              transitionDuration: const Duration(milliseconds: 350),
              pageBuilder: (_, _, _) => ChatSeite(
                steuerung: steuerung,
                einstellungen: () =>
                    EinstellungenSeite(einstellungen: einstellungen, ablage: ablage),
              ),
              transitionsBuilder: (_, anim, _, kind) =>
                  FadeTransition(opacity: anim, child: kind),
            )),
          ),
        ),
      );
}
