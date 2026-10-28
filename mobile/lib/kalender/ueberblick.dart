// Der Kalender der nächsten Tage als kurzer Text für die KI am Handy.
//
// Wie „Jetzt und als Nächstes“ am Rechner (KI-Bibel KT-07, P-06): Daten im
// wechselnden Teil, mit dem Satz „im Blick, nicht aufsagen“ — sonst antwortet
// die KI auf „wie geht's“ mit einer Terminliste. Der Rhythmus (Schlaf, Essen)
// steht nicht drin: täglich dasselbe, nur Rauschen. Versteckte Vorkommen
// (abgeschaltet, Pause) auch nicht.

import 'kalender.dart';
import 'regel.dart';

const _wt = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];

String _zeit(Vorkommen v) {
  if (v.zeit == null) return 'ganztägig';
  return v.ende == null ? v.zeit! : '${v.zeit}–${v.ende}';
}

String _zeile(Vorkommen v, DateTime jetzt) {
  final b = StringBuffer();
  if (v.deadline) {
    b.write('Deadline ${v.zeit ?? ''} ${v.label}');
    final s = v.sollBeginn;
    if (s != null) {
      b.write(' (Soll ${_wt[s.weekday - 1]} ${s.day}.${s.month}. ${s.hour.toString().padLeft(2, '0')}:'
          '${s.minute.toString().padLeft(2, '0')}${v.sollVerpasst(jetzt) ? ', Soll verpasst' : ''})');
    }
  } else {
    b.write('${_zeit(v)} ${v.label}');
  }
  if (v.ort != null) b.write(' · ${v.ort}');
  if (v.ebene == ebeneVielleicht) b.write(' (vielleicht)');
  if (v.wartet) b.write(' (eben am Handy eingetragen)');
  return b.toString();
}

/// null, wenn der Kalender leer ist (dann weiß die KI: keiner da).
String? kalenderUeberblick(Kalender k, DateTime jetzt, {int tage = 14}) {
  if (k.istLeer) return null;
  final heute = tagVon(jetzt);
  final b = StringBuffer()
    ..writeln('## Kalender der nächsten Tage')
    ..writeln('Jetzt: ${_wt[jetzt.weekday - 1]} ${jetzt.day}.${jetzt.month}.${jetzt.year}, '
        '${jetzt.hour.toString().padLeft(2, '0')}:${jetzt.minute.toString().padLeft(2, '0')}. '
        'Das hast du im Blick — nicht ungefragt aufzählen; fragt Sasha danach, antworte daraus.');
  var leer = true;
  for (final MapEntry(key: tag, value: l) in k.vorkommen(heute, heute.add(Duration(days: tage - 1))).entries) {
    final sichtbar = [for (final v in l) if (!v.versteckt && v.ebene != ebeneRhythmus) v];
    if (sichtbar.isEmpty) continue;
    leer = false;
    final d = isoTagLesen(tag)!;
    b.writeln('- ${_wt[d.weekday - 1]} ${d.day}.${d.month}.: ${sichtbar.map((v) => _zeile(v, jetzt)).join('; ')}');
  }
  if (leer) b.writeln('- keine Termine in den nächsten $tage Tagen');
  return b.toString().trimRight();
}
