// Das Auge gezeichnet — die glatte Fassung des Pixel-Auges der TUI
// (tui/pixel.py, „Das Auge der KI", Sasha 04.10.2026: „unendlich weise und
// entspannt"). Mandel, große Iris, durchscheinend, zu den Rändern hin
// ausblendend, „als ob es grad von hinten nach raus fadet".
//
// Seit 28.10.2026 gespiegelt: das Unterlid deckt die Iris genauso wie das
// schwere Oberlid, gespiegelt an der Waagrechten durch die Pupille — ruhig,
// halb geschlossen statt unten weit aufgerissen. Die Falten darüber und
// darunter sind halbe Sinusbögen, die sich weich um das Auge legen.
//
// Maße relativ zum Radius rx (halbe Breite); eine Entwurfseinheit k = rx/24,5
// wie im 52er-Entwurf der TUI. Stellschrauben: auge_regler.dart.

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

import '../thema/farben.dart';
import 'auge_regler.dart';
import 'zeit.dart';

/// Eine Laune: ein paar Sekunden lang passiert etwas Seltsames im Auge.
/// Sie darf den Zustand formen (Lid, Blick, Unschärfe, Farbe …) und Iris,
/// Pupille oder Lichtpunkt selbst malen. Die Liste aller: launen.dart.
abstract class Laune {
  const Laune(this.name, {this.dauerMs = 4500});

  final String name;
  final int dauerMs;

  /// t = Fortschritt 0..1, s = Stärke 0..1 (blendet ein und aus).
  AugeZustand formen(AugeZustand z, double t, double s) => z;

  /// true = selbst gemalt, der Maler lässt seine Fassung weg.
  bool maleIris(IrisBild b) => false;
  bool malePupille(IrisBild b) => false;
  bool maleLicht(IrisBild b) => false;
}

/// Was eine Laune zum Malen braucht. Ein Pinsel zum Wiederverwenden, damit
/// pro Bild keine Paint-Flut entsteht.
class IrisBild {
  IrisBild(this.canvas, this.mitte, this.ir, this.pu, this.k, this.f, this.puls, this.t, this.s);

  final Canvas canvas;
  final Offset mitte;

  /// Radius der Iris und der Pupille in Pixeln; k = eine Entwurfseinheit.
  final double ir, pu, k;
  final AugeFarben f;
  final double puls, t, s;
  final Paint pinsel = Paint()..isAntiAlias = true;
}

/// Der sichtbare Zustand eines Augenblicks (wie pixel.auge_zustand).
class AugeZustand {
  const AugeZustand({
    this.lid = 1, this.blickX = 0, this.blickY = 0,
    this.puls = 0, this.ring = 0, this.da = 1, this.denkt = false,
    this.pupille = 1, this.fuellen = 0, this.unschaerfe = 0,
    this.farbDrehung = 0, this.lidSchief = 0,
    this.laune, this.launeT = 0, this.launeS = 0,
  });

  /// 0 = zu, 1 = offen (in Ruhe hängen beide Lider trotzdem tief).
  final double lid;

  /// Blickrichtung in Entwurfseinheiten (±5 x, ±1,5 y).
  final double blickX, blickY;

  /// Denken: Puls 0..1 und Drehwinkel des Funkenrings.
  final double puls, ring;

  /// Auftauchen aus dem Hintergrund 0..1.
  final double da;
  final bool denkt;

  /// Pupillengröße als Faktor (Uhrzeit, Launen).
  final double pupille;

  /// Antippen: 0 = normal, 1 = Pupille füllt das ganze Auge.
  final double fuellen;

  /// Unschärfe in Entwurfseinheiten (Laune „unscharf").
  final double unschaerfe;

  /// Drehung des Iris-Farbtons in Grad.
  final double farbDrehung;

  /// Zwinkern: die rechte Seite schließt um so viel mehr (0..1).
  final double lidSchief;

  /// Die laufende Laune, ihr Fortschritt und ihre Stärke.
  final Laune? laune;
  final double launeT, launeS;

  AugeZustand mit({
    double? lid, double? blickX, double? blickY, double? pupille,
    double? unschaerfe, double? farbDrehung, double? lidSchief,
    Laune? laune, double? launeT, double? launeS, double? fuellen,
  }) => AugeZustand(
        lid: lid ?? this.lid, blickX: blickX ?? this.blickX, blickY: blickY ?? this.blickY,
        puls: puls, ring: ring, da: da, denkt: denkt,
        pupille: pupille ?? this.pupille, fuellen: fuellen ?? this.fuellen,
        unschaerfe: unschaerfe ?? this.unschaerfe,
        farbDrehung: farbDrehung ?? this.farbDrehung, lidSchief: lidSchief ?? this.lidSchief,
        laune: laune ?? this.laune, launeT: launeT ?? this.launeT, launeS: launeS ?? this.launeS,
      );

  @override
  bool operator ==(Object other) =>
      other is AugeZustand && other.lid == lid && other.blickX == blickX && other.blickY == blickY &&
      other.puls == puls && other.ring == ring && other.da == da && other.denkt == denkt &&
      other.pupille == pupille && other.fuellen == fuellen && other.unschaerfe == unschaerfe &&
      other.farbDrehung == farbDrehung && other.lidSchief == lidSchief &&
      other.laune == laune && other.launeT == launeT && other.launeS == launeS;

  @override
  int get hashCode => Object.hash(lid, blickX, blickY, puls, ring, da, denkt, pupille,
      fuellen, unschaerfe, farbDrehung, lidSchief, laune, launeT, launeS);
}

/// Halbe Breite der Mandel in einer Fläche: die Mandel und die innere Falte
/// müssen hinein, die äußere Falte darf ein Stück überstehen.
double mandelRadius(Size s) => math.min(s.width / 2, s.height / 1.9);

/// Die ganze Mandel als Pfad um c — auch für den Übergang zum Chat, der in
/// genau dieser Form weiterwächst (pupillen_route.dart).
Path mandelPfad(Offset c, double rx) {
  final ry = rx * mandelHoehe;
  return _kurve(c, rx, (dx) => -_halb(dx, ry))
    ..extendWithPath(_kurve(c, rx, (dx) => _halb(dx, ry), von: 1, bis: -1), Offset.zero)
    ..close();
}

double _halb(double dx, double ry) =>
    ry * math.pow(math.max(0.0, 1 - dx * dx), mandelSpitze).toDouble();

Path _kurve(Offset c, double rx, double Function(double dx) y,
    {double von = -1, double bis = 1, int n = 48}) {
  final p = Path();
  for (var i = 0; i <= n; i++) {
    final dx = von + (bis - von) * i / n;
    final x = c.dx + dx * rx, yy = c.dy + y(dx);
    i == 0 ? p.moveTo(x, yy) : p.lineTo(x, yy);
  }
  return p;
}

/// Eine Falte: halbe Sinusperiode, in der Mitte am dicksten, zu den Enden
/// auf null auslaufend. vorzeichen −1 = oben, +1 = unten.
Path _falte(Offset c, double rx, double ry, double faktor, double breite, double dicke,
    double vorzeichen) {
  // Die Enden sitzen knapp außerhalb der Mandel, die Mitte bei faktor·ry —
  // so umarmt der Bogen das Auge, statt es zu schneiden.
  final ende = _halb(breite, ry) * faktor;
  double hoehe(double u) => ende + (ry * faktor - ende) * math.sin(math.pi * u);
  double dick(double u) => dicke / 2 * math.sin(math.pi * u);
  const n = 40;
  final p = Path();
  for (var i = 0; i <= n; i++) {
    final u = i / n;
    final x = c.dx + (u * 2 - 1) * breite * rx;
    final y = c.dy + vorzeichen * (hoehe(u) + dick(u));
    i == 0 ? p.moveTo(x, y) : p.lineTo(x, y);
  }
  for (var i = n; i >= 0; i--) {
    final u = i / n;
    p.lineTo(c.dx + (u * 2 - 1) * breite * rx, c.dy + vorzeichen * (hoehe(u) - dick(u)));
  }
  return p..close();
}

/// Falten hängen nur von der Größe ab — einmal bauen, nicht 60-mal je Sekunde.
final _faltenSpeicher = <Size, List<(Path, double)>>{};

List<(Path, double)> _falten(Size size, Offset c, double rx, double k) {
  final da = _faltenSpeicher[size];
  if (da != null) return da;
  if (_faltenSpeicher.length > 8) _faltenSpeicher.clear(); // nur wenige Größen
  final ry = rx * mandelHoehe;
  final neu = [
    for (final (faktor, breite, a) in faltenOben) ...[
      (_falte(c, rx, ry, faktor, breite, faltenDicke * k, -1), a),
      (_falte(c, rx, ry, faktor, breite * .92, faltenDicke * .9 * k, 1), a * faltenUntenAnteil),
    ],
  ];
  return _faltenSpeicher[size] = neu;
}

/// Iris mit Verlauf und Fasern — eigene Funktion, damit Launen (Zwillinge)
/// sie mehrfach malen können.
void zeichneIris(Canvas canvas, Offset mitte, double ir, double pu, AugeFarben f, double puls,
    double k) {
  final p = (pu / ir).clamp(.05, .78);
  canvas.drawCircle(mitte, ir, Paint()
    ..shader = RadialGradient(
      colors: [f.irishell, Color.lerp(f.irishell, f.iris, .5 + .3 * puls)!, f.iris, f.irisrand],
      stops: [p, (p + 1) / 2 - .1, .86, 1],
    ).createShader(Rect.fromCircle(center: mitte, radius: ir)));
  // Irisfasern: 22 feine Strahlen (sin(11·w) im Raster)
  final faser = Paint()
    ..color = f.irisrand.withValues(alpha: .18)
    ..strokeWidth = .6 * k;
  final innen = math.min(pu, ir * .8) + .8 * k;
  for (var i = 0; i < 22; i++) {
    final w = i * math.pi / 11;
    final r = Offset(math.cos(w), math.sin(w));
    canvas.drawLine(mitte + r * innen, mitte + r * (ir - 1.4 * k), faser);
  }
}

void zeichnePupille(Canvas canvas, Offset mitte, double pu, AugeFarben f) =>
    canvas.drawCircle(mitte, pu, Paint()..color = f.pupille.withValues(alpha: .95));

void zeichneLicht(Canvas canvas, Offset mitte, double k, AugeFarben f, [double a = 1]) =>
    canvas.drawCircle(mitte + Offset(-2.2 * k, -1.2 * k), 1.3 * k,
        Paint()..color = f.irishell.withValues(alpha: a));

Color _drehe(Color c, double grad) {
  final h = HSVColor.fromColor(c);
  return h.withHue((h.hue + grad) % 360).toColor();
}

AugeFarben _gedreht(AugeFarben f, double grad) => grad == 0
    ? f
    : AugeFarben(
        bg: f.bg, weiss: f.weiss, schatten: f.schatten,
        iris: _drehe(f.iris, grad), irishell: _drehe(f.irishell, grad),
        irisrand: _drehe(f.irisrand, grad),
        pupille: f.pupille, rand: f.rand, lid: f.lid, falte: f.falte,
      );

class AugeMaler extends CustomPainter {
  AugeMaler(this.z, this.f);

  final AugeZustand z;
  final AugeFarben f;

  @override
  void paint(Canvas canvas, Size size) {
    final rx = mandelRadius(size);
    final k = rx / 24.5; // eine Entwurfseinheit
    final ry = rx * mandelHoehe;
    final c = Offset(size.width / 2, size.height / 2);

    double halb(double dx) => _halb(dx, ry);

    // Die Lidkanten als Höhe über der Mitte (negativ = oben), je Stelle dx.
    // Offen: Oberlid bei −(1 − lidTief), Unterlid bei +(1 − unterlidTief)
    // der halben Mandelhöhe. Zu: beide treffen sich nicht auf einem Strich,
    // sondern auf einem Bogen, der nach unten hängt wie ein schlafendes Auge
    // (schlafBogen). lid < 0 heißt „fest zu": der Bogen hängt dann ein wenig
    // tiefer — das Nachfedern beim Schließen. Beim Antippen reißt das Auge
    // ganz auf, damit die Pupille alles füllen kann.
    final auf = Curves.easeInOut.transform(z.fuellen.clamp(0.0, 1.0));
    final o = math.max(0.0, z.lid);
    final druck = 1 + math.min(.5, math.max(0.0, -z.lid));
    double schlaf(double dx) => halb(dx) * schlafBogen * druck;
    double offenHier(double dx) => o * (1 - z.lidSchief * (dx + 1) / 2);
    double oben(double dx) {
      final zu = schlaf(dx), ruhe = zu + (-halb(dx) * (1 - lidTief) - zu) * offenHier(dx);
      return ruhe + (-halb(dx) - ruhe) * auf;
    }

    double unten(double dx) {
      final zu = schlaf(dx), ruhe = zu + (halb(dx) * (1 - unterlidTief) - zu) * offenHier(dx);
      return ruhe + (halb(dx) - ruhe) * auf;
    }

    // Alles in eine Ebene, die zum Rand hin ausblendet (Randschwund), als
    // Ganzes auftaucht (da) und bei der Laune „unscharf" verschwimmt.
    final rect = Rect.fromCenter(center: c, width: size.width, height: size.height + rx);
    final ebene = Paint();
    if (z.unschaerfe > 0) {
      final s = z.unschaerfe * k;
      ebene.imageFilter = ui.ImageFilter.blur(sigmaX: s, sigmaY: s);
    }
    canvas.saveLayer(rect, ebene);

    // ── Falten: halbe Sinusbögen über und unter dem Auge ──
    final faltenPinsel = Paint();
    for (final (pfad, a) in _falten(size, c, rx, k)) {
      canvas.drawPath(pfad, faltenPinsel..color = f.falte.withValues(alpha: a));
    }

    // ── Die offene Fläche zwischen den Lidkanten ──
    final offen = _kurve(c, rx, oben)
      ..extendWithPath(_kurve(c, rx, unten, von: 1, bis: -1), Offset.zero)
      ..close();

    canvas.save();
    canvas.clipPath(offen);
    // durchscheinendes Weiß, zu den Winkeln hin im Schatten
    canvas.drawRect(rect, Paint()
      ..shader = RadialGradient(
        colors: [f.weiss.withValues(alpha: .62), f.schatten.withValues(alpha: .55)],
        stops: const [.35, 1],
      ).createShader(Rect.fromCenter(center: c, width: rx * 2, height: rx * 2)));

    final farben = _gedreht(f, z.farbDrehung);
    final mitte = c + Offset(z.blickX * k, z.blickY * k);
    final ir = 13.0 * k;
    final pu = (z.denkt ? 3.2 + .5 * z.puls : pupilleTag * z.pupille) * k;
    final laune = z.laune;
    final bild = laune == null
        ? null
        : IrisBild(canvas, mitte, ir, pu, k, farben, z.puls, z.launeT, z.launeS);

    if (!(bild != null && laune!.maleIris(bild))) {
      zeichneIris(canvas, mitte, ir, pu, farben, z.puls, k);
      if (!(bild != null && laune!.malePupille(bild))) zeichnePupille(canvas, mitte, pu, farben);
    }
    if (!(bild != null && laune!.maleLicht(bild))) zeichneLicht(canvas, mitte, k, farben);

    // Antippen: die Pupille wächst, bis sie die ganze offene Fläche füllt.
    if (auf > 0) {
      final w = Curves.easeIn.transform(z.fuellen.clamp(0.0, 1.0));
      zeichnePupille(canvas, mitte, pu + (rx * 1.1 - pu) * w, f);
    }

    // Funkenring beim Denken: Bogenstücke, die kreisen
    if (z.denkt) {
      final funke = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.1 * k
        ..strokeCap = StrokeCap.round
        ..color = f.irishell.withValues(alpha: .9);
      final rr = Rect.fromCircle(center: mitte, radius: ir + 1.8 * k);
      for (var i = 0; i < 4; i++) {
        canvas.drawArc(rr, z.ring + i * math.pi / 2, math.pi / 6, false, funke);
      }
    }

    // Schatten der Lider auf Iris und Weiß — oben kräftiger, unten gespiegelt
    // und leiser, wie Licht von oben.
    final lidOben = c.dy + oben(0), lidUnten = c.dy + unten(0);
    final schatten = Paint();
    final obenRect = Rect.fromLTRB(rect.left, lidOben, rect.right, lidOben + 4 * k);
    canvas.drawRect(obenRect, schatten
      ..shader = LinearGradient(
        begin: Alignment.topCenter, end: Alignment.bottomCenter,
        colors: [f.pupille.withValues(alpha: .45), f.pupille.withValues(alpha: 0)],
      ).createShader(obenRect));
    final untenRect = Rect.fromLTRB(rect.left, lidUnten - 3 * k, rect.right, lidUnten);
    canvas.drawRect(untenRect, schatten
      ..shader = LinearGradient(
        begin: Alignment.bottomCenter, end: Alignment.topCenter,
        colors: [f.pupille.withValues(alpha: .28), f.pupille.withValues(alpha: 0)],
      ).createShader(untenRect));
    canvas.restore();

    // ── Ober- und Unterlid: von der Mandelkante bis zur Lidkante ──
    // Die Lider sind Haut, keine Linse: kräftig an der Lidkante, zur
    // Mandelkante hin leiser — sonst wirkt die gespiegelte Form wie ein Glas.
    Paint lidFarbe(double vorzeichen) => Paint()
      ..shader = LinearGradient(
        begin: Alignment.center,
        end: vorzeichen < 0 ? Alignment.topCenter : Alignment.bottomCenter,
        colors: [f.lid.withValues(alpha: .75), f.lid.withValues(alpha: .5), f.lid.withValues(alpha: 0)],
        stops: const [0, .55, 1],
      ).createShader(Rect.fromCenter(center: c, width: rx * 2, height: ry * 2));
    canvas.drawPath(
        _kurve(c, rx, (dx) => -halb(dx))
          ..extendWithPath(_kurve(c, rx, oben, von: 1, bis: -1), Offset.zero)
          ..close(),
        lidFarbe(-1));
    canvas.drawPath(
        _kurve(c, rx, (dx) => halb(dx))
          ..extendWithPath(_kurve(c, rx, unten, von: 1, bis: -1), Offset.zero)
          ..close(),
        lidFarbe(1));

    final strich = Paint()
      ..style = PaintingStyle.stroke
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round;
    canvas.drawPath(_kurve(c, rx, (dx) => -halb(dx)),
        strich..color = f.rand.withValues(alpha: .12)..strokeWidth = .5 * k);
    canvas.drawPath(_kurve(c, rx, (dx) => halb(dx)),
        strich..color = f.rand.withValues(alpha: .10)..strokeWidth = .5 * k);
    canvas.drawPath(_kurve(c, rx, oben),
        strich..color = f.rand.withValues(alpha: .85)..strokeWidth = 1.1 * k);
    canvas.drawPath(_kurve(c, rx, unten),
        strich..color = f.rand.withValues(alpha: .75)..strokeWidth = 1.0 * k);

    // ── Wimpern: nur am (fast) geschlossenen Auge, sonst stünden sie in der
    // Iris. Feine Striche vom Oberlid nach unten und außen, zu den Winkeln
    // hin kürzer — sie machen aus dem Bogen ein schlafendes Auge.
    final wimpern = sanft((wimpernAb - o) / wimpernAb) * (1 - auf);
    if (wimpern > 0) {
      final pfad = Path();
      for (var i = 0; i < wimpernAnzahl; i++) {
        final dx = (i / (wimpernAnzahl - 1) * 2 - 1) * wimpernBreite;
        final fuss = c + Offset(dx * rx, oben(dx));
        final lang = wimpernLaenge * k * (1 - dx * dx * .75) * (.4 + .6 * wimpern);
        // Richtung: in der Mitte senkrecht nach unten, zu den Seiten nach
        // außen geneigt; zur Spitze hin biegt sie noch etwas weiter nach außen.
        final neig = dx * wimpernNeigung;
        final r = Offset(math.sin(neig), math.cos(neig));
        final quer = Offset(r.dy, -r.dx); // senkrecht zur Wimper
        final aussen = Offset(dx == 0 ? 0 : dx.sign, 0);
        final spitze = fuss + r * lang + aussen * (lang * .28 * dx.abs());
        final mitte = fuss + r * (lang * .55);
        // spitz zulaufend: breit am Lid, fein an der Spitze (gefüllt, kein Strich)
        final b = wimpernDicke * k;
        final l = fuss + quer * b, rr = fuss - quer * b;
        pfad
          ..moveTo(l.dx, l.dy)
          ..quadraticBezierTo(mitte.dx + quer.dx * b * .45, mitte.dy + quer.dy * b * .45,
              spitze.dx, spitze.dy)
          ..quadraticBezierTo(mitte.dx - quer.dx * b * .45, mitte.dy - quer.dy * b * .45,
              rr.dx, rr.dy)
          ..close();
      }
      canvas.drawPath(pfad, Paint()..color = f.rand.withValues(alpha: .85 * wimpern));
    }

    // ── Randschwund + Auftauchen: Maske von der Mitte nach außen ──
    canvas.drawRect(rect, Paint()
      ..blendMode = BlendMode.dstIn
      ..shader = LinearGradient(
        colors: [
          const Color(0x00000000),
          Color.fromRGBO(0, 0, 0, z.da),
          Color.fromRGBO(0, 0, 0, z.da),
          const Color(0x00000000),
        ],
        stops: const [0, .3, .7, 1],
      ).createShader(Rect.fromCenter(center: c, width: rx * 2.15, height: 1)));
    canvas.restore();

    // Am Ende des Antippens deckt die Pupillenfarbe die ganze Mandel, ohne
    // Randschwund — genau diese Form übernimmt der Übergang zum Chat.
    if (z.fuellen > .7) {
      final a = sanft((z.fuellen - .7) / .3);
      final deck = Paint()..color = f.pupille.withValues(alpha: a);
      final pfad = mandelPfad(c, rx);
      canvas.drawPath(pfad, deck);
      canvas.drawPath(pfad, deck..style = PaintingStyle.stroke..strokeWidth = 1.4 * k);
    }
  }

  @override
  bool shouldRepaint(AugeMaler alt) => alt.f != f || alt.z != z;
}
