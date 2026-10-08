// Die Chat-Logik ohne Oberfläche: welches Gespräch offen ist, Senden mit
// Strom, Stoppen, Wiederholen. Die Seiten zeichnen nur, was hier steht
// (wie im Kern: Logik front-agnostisch, Fronten zeichnen nur).

import 'dart:async';

import 'package:flutter/foundation.dart';

import '../ablage/ablage.dart';
import '../gespraeche/gespraeche.dart';
import '../ki/ki.dart';
import '../ki/kontext.dart';
import '../mitte/abgleich.dart';

/// Die Antwort, die gerade entsteht (noch nicht gespeichert).
class Entstehend {
  String text = '';
  String denken = '';
}

class ChatSteuerung extends ChangeNotifier {
  ChatSteuerung({
    required this.ablage,
    required this.gespraeche,
    required this.ki,
    this.abgleich,
  });

  final Ablage ablage;
  final Gespraeche gespraeche;
  final KiAnbieter ki;
  final Abgleich? abgleich;

  String? gespraech;
  String titel = '';
  List<Nachricht> nachrichten = [];
  List<Uebersicht> liste = [];
  Entstehend? entstehend;
  String? fehler;
  bool gleichtAb = false;

  StreamSubscription<KiStueck>? _strom;
  Completer<void>? _fertig;

  bool get denkt => entstehend != null;

  Future<void> start() async {
    await abgleichen();
    gespraech = await gespraeche.aktiv();
    await _neuLaden();
  }

  Future<void> _neuLaden() async {
    liste = await gespraeche.liste();
    if (gespraech != null) {
      nachrichten = await gespraeche.nachrichten(gespraech!);
      titel = (await gespraeche.kopf(gespraech!))['titel'] as String? ?? '';
    } else {
      nachrichten = [];
      titel = '';
    }
    notifyListeners();
  }

  Future<void> abgleichen() async {
    if (abgleich == null || gleichtAb) return;
    gleichtAb = true;
    notifyListeners();
    try {
      await abgleich!.laufen();
    } catch (e) {
      fehler = 'Abgleich ging nicht: $e';
    } finally {
      gleichtAb = false;
    }
    await _neuLaden();
  }

  Future<void> oeffnen(String? id) async {
    if (denkt) await stoppen();
    gespraech = id;
    fehler = null;
    await gespraeche.aktivSetzen(id);
    await _neuLaden();
  }

  Future<void> neu() => oeffnen(null);

  Future<void> senden(String text) async {
    text = text.trim();
    if (text.isEmpty || denkt) return;
    fehler = null;
    var id = gespraech;
    if (id == null) {
      id = await gespraeche.neu();
      gespraech = id;
      await gespraeche.aktivSetzen(id);
      await gespraeche.titelSetzen(id, _titelAus(text));
    }
    await gespraeche.anhaengen(id, 'user', text);
    await _antworten(id);
  }

  /// Letzte Antwort verwerfen und neu fragen.
  Future<void> wiederholen() async {
    final id = gespraech;
    if (id == null || denkt || nachrichten.isEmpty) return;
    final letzte = nachrichten.last;
    if (letzte.vonSasha) {
      await _antworten(id);
      return;
    }
    await gespraeche.verwerfenAb(id, letzte.id);
    await _antworten(id);
  }

  Future<void> _antworten(String id) async {
    final kontext = await Kontext.laden(ablage);
    final verlauf = await gespraeche.verlaufFuerKi(id);
    nachrichten = await gespraeche.nachrichten(id);
    final e = entstehend = Entstehend();
    notifyListeners();

    final fertig = _fertig = Completer<void>();
    var abgebrochen = true;
    String? grund;
    _strom = ki
        .antworten(system: kontext.system, verlauf: verlauf,
            modell: kontext.modell, effort: kontext.effort)
        .listen((s) {
      switch (s) {
        case KiText(:final text):
          e.text += text;
        case KiDenken(:final text):
          e.denken += text;
        case KiEnde(grund: final g):
          abgebrochen = false;
          grund = g;
      }
      notifyListeners();
    }, onError: (Object err) {
      fehler = '$err';
      if (!fertig.isCompleted) fertig.complete();
    }, onDone: () {
      if (!fertig.isCompleted) fertig.complete();
    }, cancelOnError: true);
    await fertig.future;
    _strom = null;

    if (grund == 'refusal' && e.text.isEmpty) {
      e.text = '(Die KI hat diese Anfrage abgelehnt.)';
    }
    if (e.text.isNotEmpty || e.denken.isNotEmpty) {
      await gespraeche.anhaengen(id, 'assistant', e.text,
          denken: e.denken, anbieter: kontext.anbieter, modell: kontext.modell,
          abgebrochen: abgebrochen);
    }
    entstehend = null;
    await _neuLaden();
    unawaited(abgleichen());
  }

  Future<void> stoppen() async {
    await _strom?.cancel();
    final f = _fertig;
    if (f != null && !f.isCompleted) f.complete();
  }

  /// Wie der Wort-Titel im Kern: die ersten Wörter der ersten Frage.
  static String _titelAus(String text) {
    final w = text.split(RegExp(r'\s+')).where((x) => x.isNotEmpty).take(6).join(' ');
    return w.length > 60 ? '${w.substring(0, 60)}…' : w;
  }

  @override
  void dispose() {
    _strom?.cancel();
    super.dispose();
  }
}
