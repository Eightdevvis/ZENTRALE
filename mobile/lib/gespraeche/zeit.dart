// Zeitstempel und ids genau wie core/gespraeche.py.
//
// Die Rechner-Dateien werden beim Lesen nach ts als TEXT sortiert. Darum muss
// das Handy Byte für Byte dasselbe Format schreiben wie Pythons
// datetime.isoformat(timespec="microseconds") in UTC:
//   2026-10-08T13:24:04.123456+00:00
// Sonst sortieren sich Handy-Nachrichten falsch zwischen die vom Laptop.

import 'dart:math';

final _zufall = Random.secure();
String _letzte = '';

String _zwei(int n) => n.toString().padLeft(2, '0');

String isoUtc(DateTime t) {
  final u = t.toUtc();
  final mikro = u.millisecond * 1000 + u.microsecond;
  return '${u.year.toString().padLeft(4, '0')}-${_zwei(u.month)}-${_zwei(u.day)}'
      'T${_zwei(u.hour)}:${_zwei(u.minute)}:${_zwei(u.second)}'
      '.${mikro.toString().padLeft(6, '0')}+00:00';
}

/// Jetzt, in dieser App streng steigend (wie gespraeche.jetzt_ts).
String jetztTs([DateTime? jetzt]) {
  var t = (jetzt ?? DateTime.now()).toUtc();
  var ts = isoUtc(t);
  if (ts.compareTo(_letzte) <= 0) {
    t = DateTime.parse(_letzte).add(const Duration(microseconds: 1));
    ts = isoUtc(t);
  }
  _letzte = ts;
  return ts;
}

String _hex(int bytes) =>
    List.generate(bytes, (_) => _zufall.nextInt(256).toRadixString(16).padLeft(2, '0')).join();

/// Wie uuid.uuid4().hex: 32 Hex-Zeichen.
String ereignisId() => _hex(16);

/// Wie gespraeche._neue_id: nach Erstellzeit sortierbar, auf allen Knoten eindeutig.
String gespraechsId([DateTime? jetzt]) {
  final u = (jetzt ?? DateTime.now()).toUtc();
  return '${u.year}${_zwei(u.month)}${_zwei(u.day)}-'
      '${_zwei(u.hour)}${_zwei(u.minute)}${_zwei(u.second)}-${_hex(3)}';
}
