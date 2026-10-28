// Zeit → Bewegung: fester Zufall, Blick, Blinzeln, Pupille nach Uhrzeit.
// Alles reine Funktionen der Zeit — kein Zustand, darum testbar und in
// derselben Millisekunde immer gleich (wie pixel._blick / pixel._lid der TUI).

import 'dart:math' as math;

import 'auge_regler.dart';

/// Fester Zufall pro Zeitabschnitt k (0..1): dasselbe Auge sieht in derselben
/// Sekunde gleich aus, ohne Zustand mitzuschleppen.
double festerZufall(int k, int salz) {
  final x = math.sin(k * 12.9898 + salz * 78.233) * 43758.5453;
  return x - x.floorToDouble();
}

/// Weiches An- und Auslaufen (smoothstep) für 0..1.
double sanft(double t) {
  final u = t.clamp(0.0, 1.0);
  return u * u * (3 - 2 * u);
}

/// Wohin schaut das Auge? Gelassen: alle 3,2 s ein neues Ziel, kleine Wege.
(double, double) blick(int ms) {
  final seg = ms ~/ 3200, rest = ms % 3200;
  (double, double) ziel(int k) => festerZufall(k, 5) < .45
      ? (0, 0) // geradeaus
      : ((festerZufall(k, 7) * 2 - 1) * 5, (festerZufall(k, 11) * 2 - 1) * 1.5);
  final a = ziel(seg - 1), b = ziel(seg);
  final u = sanft(rest / 900); // 0,9 s Blickwechsel
  return (a.$1 + (b.$1 - a.$1) * u, a.$2 + (b.$2 - a.$2) * u);
}

/// Lidöffnung durch Blinzeln: alle ~5–8 s, 1 → 0 → 1 in 0,36 s. Wie ein
/// echtes Lid: schnell zu, langsamer wieder auf, beides weich angefahren —
/// früher ein Dreieck mit hartem Knick in der Mitte.
double lidBlinzeln(int ms) {
  final periode = 5200 + (festerZufall(ms ~/ 5200, 3) * 2800).toInt();
  final p = ms % periode;
  if (p >= 360) return 1;
  return p < 130 ? 1 - sanft(p / 130) : sanft((p - 130) / 230);
}

/// Wie weit das Auge offen ist, aus dem Stand des Knopf-Rings „zu" (siehe
/// AugeSteuerung.zu): < 0 → ein Hauch weiter auf (Nachfedern beim Öffnen),
/// 0..1 → weich zu, > 1 → fest zu (Rückgabe < 0, der Schlafbogen hängt tiefer).
double offenNachZu(double zu) {
  if (zu < 0) return 1 + math.min(.15, -zu * 1.5);
  if (zu > 1) return -math.min(.5, (zu - 1) * 3);
  return 1 - _weich(zu);
}

/// Weicher als smoothstep: ruhiger Anfang, ruhiges Ende (easeInOutCubic).
double _weich(double t) => t < .5 ? 4 * t * t * t : 1 - math.pow(-2 * t + 2, 3) / 2;

/// 0..1: wie weit „drin" ist die Stunde h im Bereich [von, bis) — über
/// Mitternacht hinweg, mit weichen Rändern statt Sprüngen.
double _drin(double h, double von, double bis) {
  final r = uebergangStunden / 2;
  // Abstand zur Grenze auf dem 24-h-Kreis (-12..12 h).
  double rampe(double grenze, bool steigt) {
    var d = h - grenze;
    if (d > 12) d -= 24;
    if (d < -12) d += 24;
    final u = sanft((d + r) / (2 * r));
    return steigt ? u : 1 - u;
  }

  // Drinnen heißt: nach dem Anfang UND vor dem Ende. Mit Abstand auf dem
  // Kreis reicht das Kleinere, solange beide Bereiche länger als der
  // Übergang sind.
  return math.min(rampe(von, true), rampe(bis, false));
}

/// Pupillengröße als Faktor auf [pupilleTag]: nachts etwas weiter, zwischen
/// 3 und 5 Uhr winzig. Lokale Zeit, damit es die Nacht des Handys ist.
double pupilleNachUhrzeit(DateTime t) {
  final h = t.hour + t.minute / 60 + t.second / 3600 + t.millisecond / 3600000;
  final nacht = _drin(h, nachtVon, nachtBis);
  final spuk = _drin(h, spukVon, spukBis);
  final f = 1 + (pupilleNachtFaktor - 1) * nacht;
  return f + (pupilleSpukFaktor - f) * spuk;
}
