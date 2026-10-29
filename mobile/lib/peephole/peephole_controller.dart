// The window over the surface: where it looks (center, surface units), how
// big things are (scale, screen px per unit), and how it glides toward the
// motion target. Pure state + math, no widgets — the view only draws it.

import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import 'peephole_tuning.dart';

/// Where the movement comes from right now.
enum MotionState {
  /// Waiting for the first sensor sample.
  starting,

  /// The phone's motion moves the window.
  active,

  /// No sensors on this device (or they failed) — finger only.
  unavailable,

  /// Switched off by hand — finger only.
  off,
}

class PeepholeController extends ChangeNotifier {
  PeepholeController({required Size surfaceSize, required Offset home, required this.comfortableViewWidth})
    : _surface = surfaceSize,
      _home = home,
      _target = home,
      _shown = home;

  Size _surface;
  Offset _home;
  final double comfortableViewWidth;

  Size _screen = Size.zero;
  double _scale = 1;
  Offset _target, _shown;
  double _tau = followTau;
  MotionState _state = MotionState.starting;
  bool _sized = false;

  Size get surfaceSize => _surface;
  Offset get home => _home;
  Size get screen => _screen;
  double get scale => _scale;
  MotionState get motionState => _state;

  /// The center that is drawn (glides) and the one motion aims for.
  Offset get center => _shown;
  Offset get target => _target;

  /// Visible part of the surface (surface units).
  Rect get visible => Rect.fromCenter(center: _shown, width: _screen.width / _scale, height: _screen.height / _scale);

  double get minScale {
    if (_screen.isEmpty) return 0.01;
    return math.min(_screen.width / _surface.width, _screen.height / _surface.height) * minZoomFit;
  }

  double get maxScale => math.max(minScale, _screen.width / comfortableViewWidth * maxZoomFactor);

  bool get settled => (_target - _shown).distance * _scale < settleDistance;

  set motionState(MotionState s) {
    if (s == _state) return;
    _state = s;
    notifyListeners();
  }

  /// The view tells its size; the first time it also sets the start zoom.
  void layout(Size screen) {
    if (screen == _screen || screen.isEmpty) return;
    _screen = screen;
    if (!_sized) {
      _sized = true;
      _scale = (screen.width / comfortableViewWidth).clamp(minScale, maxScale);
    } else {
      _scale = _scale.clamp(minScale, maxScale);
    }
    _target = _clamp(_target);
    _shown = _clamp(_shown);
  }

  /// The surface changed size (new data) — keep looking at the same spot.
  void resizeSurface(Size size, Offset home) {
    if (size == _surface && home == _home) return;
    _surface = size;
    _home = home;
    _scale = _scale.clamp(minScale, maxScale);
    _target = _clamp(_target);
    _shown = _clamp(_shown);
    notifyListeners();
  }

  /// Motion: move the target by [screenDelta] (screen px); the shown window
  /// follows smoothly in [tick].
  void moveByMotion(Offset screenDelta) {
    if (screenDelta == Offset.zero) return;
    _tau = followTau;
    _target = _clamp(_target + screenDelta / _scale);
    notifyListeners();
  }

  /// Finger: dragging the sheet by [screenDelta] moves the window the other
  /// way, directly (no glide).
  void dragBy(Offset screenDelta) {
    _target = _clamp(_target - screenDelta / _scale);
    _shown = _clamp(_shown - screenDelta / _scale);
    notifyListeners();
  }

  /// Pinch: zoom by [factor] around [focal] (screen px), the surface point
  /// under the fingers stays under the fingers.
  void zoomAt(double factor, Offset focal) {
    final s = (_scale * factor).clamp(minScale, maxScale);
    if (s == _scale) return;
    final before = toSurface(focal);
    _scale = s;
    final after = toSurface(focal);
    _shown = _clamp(_shown + before - after);
    _target = _clamp(_target + before - after);
    notifyListeners();
  }

  /// Back to [home] (glides).
  void recenter() {
    _tau = recenterTau;
    _target = _clamp(_home);
    notifyListeners();
  }

  /// One frame of gliding ([dt] seconds).
  void tick(double dt) {
    if (settled) {
      if (_shown != _target) {
        _shown = _target;
        notifyListeners();
      }
      _tau = followTau;
      return;
    }
    final k = 1 - math.exp(-dt / _tau);
    _shown = Offset.lerp(_shown, _target, k)!;
    notifyListeners();
  }

  Offset toSurface(Offset screenPoint) => _shown + (screenPoint - _screen.center(Offset.zero)) / _scale;

  Offset toScreen(Offset surfacePoint) => (surfacePoint - _shown) * _scale + _screen.center(Offset.zero);

  Offset _clamp(Offset c) {
    if (_screen.isEmpty) return c;
    final halfW = _screen.width / _scale / 2, halfH = _screen.height / _scale / 2;
    final m = overscrollPixels / _scale;
    double axis(double v, double half, double extent) {
      if (half * 2 >= extent) return extent / 2; // all of it fits: keep it centred
      return v.clamp(half - m, extent - half + m);
    }

    return Offset(axis(c.dx, halfW, _surface.width), axis(c.dy, halfH, _surface.height));
  }
}
