// Device motion → window movement. Pure Dart (no widgets), so the mapping is
// unit-tested with synthetic sensor streams.
//
// Model: you hold the phone above a table and swing it like a flashlight.
// The gyroscope says how fast the phone turns (device frame), the
// accelerometer where "up" is. The turn rate is split against "up" into
//   yaw   — turning around the vertical      → pans left/right
//   pitch — top edge up/down                  → pans up/down the table
//   roll  — right edge down / left edge down  → pans left/right too
// This split works whether the phone lies flat, is tilted toward you or is
// held upright, and the three parts never double count. Only rates are
// integrated; the frame clamps the window to the surface, so drift can never
// carry it away. Drift itself is fought by a soft dead zone and a gyroscope
// bias estimate that learns only while the phone is still.
//
// Device axes (Android): x to the right, y to the top of the screen, z out
// of the screen. Gyroscope positive = counter-clockwise (right-hand rule).

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' show Offset;

import 'package:sensors_plus/sensors_plus.dart';

import 'peephole_tuning.dart';

/// Minimal 3-vector (avoids a direct vector_math dependency).
class Vec3 {
  const Vec3(this.x, this.y, this.z);
  static const zero = Vec3(0, 0, 0);
  final double x, y, z;

  Vec3 operator +(Vec3 o) => Vec3(x + o.x, y + o.y, z + o.z);
  Vec3 operator -(Vec3 o) => Vec3(x - o.x, y - o.y, z - o.z);
  Vec3 operator *(double k) => Vec3(x * k, y * k, z * k);
  double dot(Vec3 o) => x * o.x + y * o.y + z * o.z;
  Vec3 cross(Vec3 o) => Vec3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);
  double get length => math.sqrt(dot(this));
  Vec3 normalized() {
    final l = length;
    return l < 1e-9 ? this : this * (1 / l);
  }

  @override
  String toString() => 'Vec3(${x.toStringAsFixed(3)}, ${y.toStringAsFixed(3)}, ${z.toStringAsFixed(3)})';
}

/// One gyroscope reading with the latest accelerometer reading.
class MotionSample {
  const MotionSample({required this.time, required this.gyro, required this.accel});

  /// Monotonic sensor time.
  final Duration time;

  /// Turn rate (rad/s), device frame.
  final Vec3 gyro;

  /// Acceleration incl. gravity (m/s²), device frame; lying flat ≈ (0, 0, 9.81).
  final Vec3 accel;
}

/// Where motion comes from. The real one reads the sensors; tests feed a
/// stream. The stream errors (or stays silent) when there are no sensors —
/// the view then falls back to finger panning.
abstract class MotionSource {
  Stream<MotionSample> samples();
}

/// Gyroscope + accelerometer via the `sensors_plus` package.
class SensorMotionSource implements MotionSource {
  @override
  Stream<MotionSample> samples() {
    late StreamController<MotionSample> out;
    StreamSubscription<GyroscopeEvent>? gyro;
    StreamSubscription<AccelerometerEvent>? acc;
    var lastAccel = const Vec3(0, 0, gravity);
    out = StreamController<MotionSample>(
      onListen: () {
        try {
          acc = accelerometerEventStream(samplingPeriod: SensorInterval.gameInterval).listen(
            (e) => lastAccel = Vec3(e.x, e.y, e.z),
            onError: (Object _) {}, // without accelerometer: "up" stays from the gyroscope
          );
          gyro = gyroscopeEventStream(samplingPeriod: SensorInterval.gameInterval).listen(
            (e) => out.add(
              MotionSample(
                time: Duration(microseconds: e.timestamp.microsecondsSinceEpoch),
                gyro: Vec3(e.x, e.y, e.z),
                accel: lastAccel,
              ),
            ),
            onError: out.addError,
          );
        } catch (e) {
          out.addError(e);
        }
      },
      onCancel: () async {
        await gyro?.cancel();
        await acc?.cancel();
      },
    );
    return out.stream;
  }
}

double _soft(double v, double dz) => v.abs() <= dz ? 0 : v - dz * v.sign;

/// Turns sensor samples into window movement (screen pixels).
class MotionMapper {
  Vec3? _up;
  Vec3 _right = const Vec3(1, 0, 0);
  Vec3 _bias = Vec3.zero;
  Duration? _last;
  double _stillFor = 0;

  /// Current estimate of "up" in device coordinates (for tests/debugging).
  Vec3? get up => _up;

  /// Current gyroscope bias estimate.
  Vec3 get bias => _bias;

  /// Forget timing (after a pause); keeps the learnt bias.
  void reset() {
    _last = null;
    _up = null;
    _stillFor = 0;
  }

  /// Movement of the window for this sample: dx to the right, dy down the
  /// table, in screen pixels.
  Offset update(MotionSample s) {
    final last = _last;
    _last = s.time;
    final a = s.accel;
    final an = a.length;
    if (last == null || _up == null) {
      _up = an > 0.5 ? a.normalized() : const Vec3(0, 0, 1);
      return Offset.zero;
    }
    var dt = (s.time - last).inMicroseconds / 1e6;
    if (dt > maxSampleGap) return Offset.zero;
    if (dt <= 0) dt = nominalSamplePeriod;

    // Drift: learn the gyroscope bias only while really still.
    final raw = s.gyro;
    final still = (raw - _bias).length < stillRate && (an - gravity).abs() < stillAccel;
    _stillFor = still ? _stillFor + dt : 0;
    if (_stillFor >= stillMinSeconds) {
      final b = _bias + (raw - _bias) * (dt / (biasTau + dt));
      _bias = Vec3(b.x.clamp(-biasMax, biasMax), b.y.clamp(-biasMax, biasMax), b.z.clamp(-biasMax, biasMax));
    }
    final w = raw - _bias;

    // Up: follow the gyroscope (a world vector seen from a turning device
    // turns the other way: du/dt = u × ω), pulled toward the accelerometer.
    var u = (_up! + _up!.cross(w) * dt).normalized();
    if (an > 0.5 && (an - gravity).abs() < gravityTrust) {
      final k = dt / (gravityTau + dt);
      u = (u * (1 - k) + a.normalized() * k).normalized();
    }
    _up = u;

    // Horizontal "right" axis: device x flattened onto the table. When x
    // points almost straight up/down (phone on its side) keep the last one.
    const x = Vec3(1, 0, 0);
    final r = x - u * x.dot(u);
    if (r.length > 0.3) _right = r.normalized();
    final f = u.cross(_right); // horizontal "forward"

    final yaw = _soft(w.dot(u), deadZoneRate);
    final pitch = _soft(w.dot(_right), deadZoneRate);
    final roll = _soft(w.dot(f), deadZoneRate);

    final k = panPixelsPerRadian * dt;
    return Offset((-yaw + rollPanShare * roll) * k, -pitch * pitchPanShare * k);
  }
}
