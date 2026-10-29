// The peephole ("Guckloch"): a phone-sized window over a large virtual
// surface lying on a table. Swing the phone and the window moves as if you
// looked down at a different spot of the table; pinch zooms; dragging with a
// finger always works too (and is all there is without sensors). Long press
// or the button glides back to the surface's home.
//
// Frame feature, not app feature: any [PeepholeSurface] can be shown. The
// motion mapping lives in motion.dart, the window math in
// peephole_controller.dart, every knob in peephole_tuning.dart.

import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import '../l10n/app_localizations.dart';
import '../thema/farben.dart';
import 'motion.dart';
import 'peephole_controller.dart';
import 'peephole_surface.dart';
import 'peephole_tuning.dart';

class PeepholeView extends StatefulWidget {
  const PeepholeView({
    super.key,
    required this.surface,
    this.motion,
    this.onHit,
    this.controller,
    this.showMinimap = true,
    this.showHint = true,
  });

  final PeepholeSurface surface;

  /// Where motion comes from; null = finger only.
  final MotionSource? motion;

  /// A tap found something on the surface.
  final void Function(PeepholeHit hit)? onHit;

  /// Pass one to read or steer the window from outside (tests, app bar).
  final PeepholeController? controller;
  final bool showMinimap, showHint;

  @override
  State<PeepholeView> createState() => _PeepholeViewState();
}

class _PeepholeViewState extends State<PeepholeView> with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late PeepholeController _c;
  late bool _ownController;
  late final Ticker _ticker;
  Duration _lastTick = Duration.zero;
  final _mapper = MotionMapper();
  StreamSubscription<MotionSample>? _sub;
  Timer? _startTimer, _hintTimer;
  bool _wantMotion = true, _hint = true;
  double _lastPinch = 1;

  @override
  void initState() {
    super.initState();
    _ownController = widget.controller == null;
    _c =
        widget.controller ??
        PeepholeController(
          surfaceSize: widget.surface.size,
          home: widget.surface.home,
          comfortableViewWidth: widget.surface.comfortableViewWidth,
        );
    _c.addListener(_changed);
    _ticker = createTicker(_tick);
    WidgetsBinding.instance.addObserver(this);
    _hint = widget.showHint;
    if (_hint) _hintTimer = Timer(const Duration(seconds: 5), () => setState(() => _hint = false));
    _startMotion();
  }

  @override
  void didUpdateWidget(PeepholeView old) {
    super.didUpdateWidget(old);
    _c.resizeSurface(widget.surface.size, widget.surface.home);
    if (old.motion != widget.motion) {
      _stopMotion();
      _startMotion();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _c.removeListener(_changed);
    _stopMotion(keepState: true);
    _hintTimer?.cancel();
    _ticker.dispose();
    if (_ownController) _c.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState s) {
    // Sensors cost battery; and after a pause the time gap must not count.
    if (s == AppLifecycleState.resumed) {
      _startMotion();
    } else if (s == AppLifecycleState.paused || s == AppLifecycleState.hidden) {
      _stopMotion(keepState: true);
    }
  }

  void _startMotion() {
    final m = widget.motion;
    if (m == null) {
      _c.motionState = MotionState.unavailable;
      return;
    }
    if (!_wantMotion) {
      _c.motionState = MotionState.off;
      return;
    }
    if (_sub != null || _c.motionState == MotionState.unavailable) return;
    _mapper.reset();
    _c.motionState = MotionState.starting;
    _startTimer = Timer(sensorStartTimeout, () {
      if (_c.motionState == MotionState.starting) _giveUp();
    });
    try {
      _sub = m.samples().listen(_sample, onError: (Object _) => _giveUp(), cancelOnError: true);
    } catch (_) {
      _giveUp();
    }
  }

  void _stopMotion({bool keepState = false}) {
    _startTimer?.cancel();
    _startTimer = null;
    unawaited(_sub?.cancel());
    _sub = null;
    if (!keepState && _c.motionState != MotionState.unavailable) {
      _c.motionState = widget.motion == null ? MotionState.unavailable : MotionState.off;
    }
  }

  void _giveUp() {
    _stopMotion(keepState: true);
    if (mounted) _c.motionState = MotionState.unavailable;
  }

  void _sample(MotionSample s) {
    if (_c.motionState == MotionState.starting) _c.motionState = MotionState.active;
    if (_c.motionState != MotionState.active) return;
    _c.moveByMotion(_mapper.update(s));
  }

  void _toggleMotion() {
    _wantMotion = !_wantMotion;
    if (_wantMotion) {
      _startMotion();
    } else {
      _stopMotion();
    }
  }

  void _recenter() {
    HapticFeedback.selectionClick();
    _c.recenter();
  }

  MotionState? _shownState;

  void _changed() {
    if (!_c.settled && !_ticker.isActive) {
      _lastTick = Duration.zero;
      _ticker.start();
    }
    // The painter listens to the controller itself; rebuild only for the controls.
    if (mounted && _c.motionState != _shownState) setState(() => _shownState = _c.motionState);
  }

  void _tick(Duration elapsed) {
    final dt = ((elapsed - _lastTick).inMicroseconds / 1e6).clamp(0.0, 0.1);
    _lastTick = elapsed;
    _c.tick(dt == 0 ? 1 / 60 : dt);
    if (_c.settled) _ticker.stop();
  }

  PeepholeStyle _style(BuildContext context) {
    final eye = AugeFarben.von(context);
    final night = Theme.of(context).brightness == Brightness.dark;
    final scheme = Theme.of(context).colorScheme;
    return PeepholeStyle(
      eye: eye,
      night: night,
      ink: scheme.onSurface,
      inkMuted: scheme.onSurfaceVariant,
      sheet: sheetColor(eye, night),
      warning: scheme.error,
      scale: _c.scale,
      locale: Localizations.localeOf(context).toLanguageTag(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final t = AppLocalizations.of(context);
    final style = _style(context);
    return LayoutBuilder(
      builder: (context, box) {
        _c.layout(box.biggest);
        final styled = style.withScale(_c.scale);
        final state = _c.motionState;
        return Stack(
          fit: StackFit.expand,
          children: [
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onScaleStart: (_) => _lastPinch = 1,
              onScaleUpdate: (d) {
                if (d.pointerCount > 1) {
                  _c.zoomAt(d.scale / _lastPinch, d.localFocalPoint);
                  _lastPinch = d.scale;
                }
                _c.dragBy(d.focalPointDelta);
              },
              onTapUp: (d) {
                final hit = widget.surface.hitTest(_c.toSurface(d.localPosition));
                if (hit != null) widget.onHit?.call(hit);
              },
              onLongPress: _recenter,
              child: CustomPaint(
                painter: PeepholePainter(
                  controller: _c,
                  surface: widget.surface,
                  style: styled,
                  minimap: widget.showMinimap,
                ),
              ),
            ),
            Positioned(
              left: 12,
              bottom: 12,
              child: _Controls(
                state: state,
                onToggle: widget.motion == null || state == MotionState.unavailable ? null : _toggleMotion,
                onRecenter: _recenter,
                t: t,
              ),
            ),
            if (_hint || state == MotionState.unavailable)
              Positioned(
                left: 16,
                right: 16,
                top: 12,
                child: IgnorePointer(
                  child: Center(
                    child: _Pill(
                      text: state == MotionState.unavailable ? t.peepholeMotionUnavailable : t.peepholeHint,
                      style: styled,
                    ),
                  ),
                ),
              ),
          ],
        );
      },
    );
  }
}

/// The sheet's own colour (lifted a little from the table).
Color sheetColor(AugeFarben eye, bool night) => night ? Color.lerp(eye.bg, eye.lid, .30)! : eye.bg;

Color _tableColor(AugeFarben eye, bool night) =>
    night ? Color.lerp(eye.bg, eye.lid, .10)! : Color.lerp(eye.bg, eye.lid, .38)!;

class _Pill extends StatelessWidget {
  const _Pill({required this.text, required this.style});
  final String text;
  final PeepholeStyle style;

  @override
  Widget build(BuildContext context) => DecoratedBox(
    decoration: BoxDecoration(
      color: style.sheet.withValues(alpha: .94),
      borderRadius: BorderRadius.circular(16),
      border: Border.all(color: style.eye.falte.withValues(alpha: .5)),
    ),
    child: Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: TextStyle(fontSize: 13, color: style.ink),
      ),
    ),
  );
}

class _Controls extends StatelessWidget {
  const _Controls({required this.state, required this.onToggle, required this.onRecenter, required this.t});
  final MotionState state;
  final VoidCallback? onToggle, onRecenter;
  final AppLocalizations t;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final eye = AugeFarben.von(context);
    final on = state == MotionState.active || state == MotionState.starting;
    final label = switch (state) {
      MotionState.active => t.peepholeMotionOn,
      MotionState.starting => t.peepholeMotionStarting,
      MotionState.off => t.peepholeMotionOff,
      MotionState.unavailable => t.peepholeMotionUnavailable,
    };
    return Material(
      color: scheme.surface.withValues(alpha: .92),
      shape: StadiumBorder(side: BorderSide(color: eye.falte.withValues(alpha: .5))),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (onToggle != null)
            IconButton(
              key: const Key('peephole-motion'),
              tooltip: label,
              onPressed: onToggle,
              icon: Icon(
                on ? Icons.screen_rotation_alt : Icons.pan_tool_outlined,
                color: on ? eye.iris : scheme.onSurfaceVariant,
              ),
            ),
          IconButton(
            key: const Key('peephole-recenter'),
            tooltip: t.peepholeRecenter,
            onPressed: onRecenter,
            icon: Icon(Icons.center_focus_strong_outlined, color: scheme.onSurface),
          ),
        ],
      ),
    );
  }
}

/// Paints table, sheet, surface and minimap. Public so tests can render it
/// straight into a PNG.
class PeepholePainter extends CustomPainter {
  PeepholePainter({required this.controller, required this.surface, required this.style, this.minimap = true})
    : super(repaint: Listenable.merge([controller, surface.repaint]));

  final PeepholeController controller;
  final PeepholeSurface surface;
  final PeepholeStyle style;
  final bool minimap;

  @override
  void paint(Canvas canvas, Size size) {
    final c = controller;
    final s = c.scale;
    final eye = style.eye;
    canvas.drawRect(Offset.zero & size, Paint()..color = _tableColor(eye, style.night));
    _grid(canvas, size);

    final sheet = Rect.fromPoints(c.toScreen(Offset.zero), c.toScreen(surface.size.bottomRight(Offset.zero)));
    final rr = RRect.fromRectAndRadius(sheet, const Radius.circular(sheetRadius));
    canvas.drawRRect(
      rr.shift(const Offset(0, 3)),
      Paint()
        ..color = Colors.black.withValues(alpha: style.night ? .55 : .14)
        ..maskFilter = const MaskFilter.blur(BlurStyle.normal, sheetShadow / 2),
    );
    canvas.drawRRect(rr, Paint()..color = style.sheet);

    canvas.save();
    canvas.clipRRect(rr);
    final o = c.toScreen(Offset.zero);
    canvas.translate(o.dx, o.dy);
    canvas.scale(s);
    surface.paint(canvas, c.visible.intersect(Offset.zero & surface.size), style.withScale(s));
    canvas.restore();
    canvas.drawRRect(
      rr,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1
        ..color = eye.falte.withValues(alpha: .35),
    );

    if (minimap) _minimap(canvas, size);
  }

  void _grid(Canvas canvas, Size size) {
    final c = controller;
    final eye = style.eye;
    final a = style.night ? tableGridOpacityNight : tableGridOpacityDay;
    final cellPx = tableGridCell * c.scale;
    final step = cellPx < 9 ? tableGridPadEvery : 1; // zoomed far out: pads only
    final v = c.visible.inflate(tableGridCell);
    final i0 = (v.left / tableGridCell).floor(), i1 = (v.right / tableGridCell).ceil();
    final j0 = (v.top / tableGridCell).floor(), j1 = (v.bottom / tableGridCell).ceil();
    final dot = Paint()..color = eye.falte.withValues(alpha: a);
    final pad = Paint()..color = eye.falte.withValues(alpha: a * 1.3);
    final trace = Paint()
      ..color = eye.falte.withValues(alpha: a * .55)
      ..strokeWidth = 1;
    // Faint traces along every n-th line, with pads where they cross.
    for (var i = i0; i <= i1; i++) {
      if (i % tableGridPadEvery != 0) continue;
      final x = c.toScreen(Offset(i * tableGridCell, 0)).dx;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), trace);
    }
    for (var j = j0; j <= j1; j++) {
      if (j % tableGridPadEvery != 0) continue;
      final y = c.toScreen(Offset(0, j * tableGridCell)).dy;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), trace);
    }
    for (var i = i0 - i0 % step; i <= i1; i += step) {
      for (var j = j0 - j0 % step; j <= j1; j += step) {
        final p = c.toScreen(Offset(i * tableGridCell, j * tableGridCell));
        final isPad = i % tableGridPadEvery == 0 && j % tableGridPadEvery == 0;
        canvas.drawCircle(p, isPad ? tableGridPad : tableGridDot, isPad ? pad : dot);
      }
    }
  }

  void _minimap(Canvas canvas, Size size) {
    final c = controller;
    final sv = Offset.zero & surface.size;
    final vis = c.visible;
    if (vis.contains(sv.topLeft) && vis.contains(sv.bottomRight)) return;
    final k = minimapWidth / surface.size.width;
    final h = math.min(surface.size.height * k, size.height * .3);
    final kk = math.min(k, h / surface.size.height);
    final box = Rect.fromLTWH(
      size.width - minimapMargin - surface.size.width * kk,
      minimapMargin,
      surface.size.width * kk,
      surface.size.height * kk,
    );
    final eye = style.eye;
    canvas.drawRRect(
      RRect.fromRectAndRadius(box.inflate(3), const Radius.circular(4)),
      Paint()..color = style.sheet.withValues(alpha: .9),
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(box.inflate(3), const Radius.circular(4)),
      Paint()
        ..style = PaintingStyle.stroke
        ..color = eye.falte.withValues(alpha: .6),
    );
    final win = Rect.fromLTRB(
      box.left + vis.left * kk,
      box.top + vis.top * kk,
      box.left + vis.right * kk,
      box.top + vis.bottom * kk,
    ).intersect(box.inflate(3));
    canvas.drawRect(win, Paint()..color = eye.iris.withValues(alpha: .22));
    canvas.drawRect(
      win,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.4
        ..color = eye.iris,
    );
    final home = box.topLeft + c.home * kk;
    canvas.drawCircle(home, 2, Paint()..color = eye.rand);
  }

  @override
  bool shouldRepaint(PeepholePainter old) =>
      old.surface != surface ||
      old.style.night != style.night ||
      old.style.locale != style.locale ||
      old.style.ink != style.ink;
}
