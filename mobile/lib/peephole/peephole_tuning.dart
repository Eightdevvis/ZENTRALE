// Every tuning knob of the peephole in ONE place (same idea as
// lib/auge/auge_regler.dart): how the phone's motion moves the window over
// the virtual table, how calm it glides, how far you can zoom, how the table
// looks. Angles in radians, rates in rad/s, times in seconds, lengths in
// logical screen pixels unless noted.

// ── Motion → window ─────────────────────────────────────────────────────────

/// Screen pixels the window travels per radian of phone rotation. 30° of
/// swing (0.52 rad) moves about one phone width (~400 px). Independent of the
/// zoom: the feel stays the same, zoomed in you just cover less surface.
const panPixelsPerRadian = 780.0;

/// Turning the phone left/right around the vertical (yaw) pans horizontally.
/// Tilting it sideways (right edge down) pans too, scaled by this share
/// (0 = ignore sideways tilt, 1 = as strong as turning).
const rollPanShare = 0.8;

/// Tilting the top up/down (pitch) pans vertically, scaled by this share.
const pitchPanShare = 1.0;

/// Rotation slower than this counts as hand tremor and is ignored (soft dead
/// zone: above it the rate is reduced by this amount, so nothing jumps).
const deadZoneRate = 0.025;

/// Larger jumps between two sensor samples (app paused, sensor hiccup) are
/// not integrated — the window just stays where it is.
const maxSampleGap = 0.25;

/// Used when two samples carry the same timestamp (batched delivery).
const nominalSamplePeriod = 0.02;

// ── Gravity (complementary filter) ─────────────────────────────────────────

/// Standard gravity (m/s²).
const gravity = 9.81;

/// The "up" direction comes from the gyroscope short-term and is pulled
/// toward the accelerometer with this time constant (long = trusts the
/// gyroscope more, short = follows shaky accelerometer readings).
const gravityTau = 0.6;

/// Accelerometer readings further than this from 1 g (the hand is jerking
/// the phone) don't correct the up direction.
const gravityTrust = 2.5;

// ── Drift (gyroscope bias) ─────────────────────────────────────────────────

/// The phone counts as still when it turns slower than this...
const stillRate = 0.06;

/// ...and the accelerometer stays within this of 1 g...
const stillAccel = 0.6;

/// ...for at least this long. Only then the bias estimate learns.
const stillMinSeconds = 0.4;

/// Time constant of the bias estimate while still.
const biasTau = 1.5;

/// The bias estimate is never larger than this (rad/s per axis) — a real
/// slow turn must not be learned away.
const biasMax = 0.05;

// ── Smoothing ───────────────────────────────────────────────────────────────

/// The visible window follows the motion target with this time constant
/// (low-pass). Finger panning is always direct.
const followTau = 0.07;

/// Gliding back after recenter.
const recenterTau = 0.18;

/// The window counts as arrived when closer than this (screen px).
const settleDistance = 0.3;

// ── Sensors ─────────────────────────────────────────────────────────────────

/// No sample within this long after starting → fall back to finger panning.
const sensorStartTimeout = Duration(seconds: 2);

// ── Zoom ───────────────────────────────────────────────────────────────────

/// Furthest in: the surface's comfortable width divided by this.
const maxZoomFactor = 2.5;

/// Furthest out: the whole surface fits, times this (a bit of table around).
const minZoomFit = 0.92;

/// How far the window may go past the surface edge (screen px) — you see
/// the table around the sheet, but never lose it.
const overscrollPixels = 56.0;

// ── Look ────────────────────────────────────────────────────────────────────

/// Faint circuit-board grid on the table: cell size (surface units), dot and
/// pad radius (screen px), every n-th crossing gets a pad, opacity day/night.
const tableGridCell = 48.0;
const tableGridDot = 0.9, tableGridPad = 2.2, tableGridPadEvery = 5;
const tableGridOpacityDay = 0.22, tableGridOpacityNight = 0.28;

/// The sheet lying on the table: corner radius and shadow (screen px).
const sheetRadius = 10.0, sheetShadow = 14.0;

/// Minimap in the corner: width (screen px) and margin; hidden when the
/// whole surface is visible anyway.
const minimapWidth = 76.0, minimapMargin = 12.0;

/// Text smaller than this on screen is not drawn (E-Ink: never under 10 px).
const minTextPixels = 10.0;
