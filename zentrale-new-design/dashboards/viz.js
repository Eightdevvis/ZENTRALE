/* ============================================================================
   ZENTRALE — Viz-Helfer (viz.js)
   Kleine, stil-neutrale Generatoren für Sparklines, Balken, Arc-Gauges und
   ASCII-Varianten. Farben/Strokes kommen aus dem CSS der jeweiligen Richtung
   (currentColor / stroke), die Geometrie ist hier zentral.
   ========================================================================== */
(function (global) {
  'use strict';
  const VZ = {};

  // Linien-Pfad (d-Attribut) durch normalisierte Werte
  VZ.sparkPath = function (vals, w, h, pad) {
    pad = pad || 2;
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const rng = (max - min) || 1;
    const n = vals.length;
    const x = i => pad + (i / (n - 1)) * (w - pad * 2);
    const y = v => h - pad - ((v - min) / rng) * (h - pad * 2);
    return vals.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1)).join(' ');
  };

  // Geschlossene Fläche unter der Linie
  VZ.areaPath = function (vals, w, h, pad) {
    pad = pad || 2;
    const line = VZ.sparkPath(vals, w, h, pad);
    return line + ' L' + (w - pad).toFixed(1) + ' ' + (h - pad).toFixed(1) +
           ' L' + pad.toFixed(1) + ' ' + (h - pad).toFixed(1) + ' Z';
  };

  // Balken-Rechtecke {x,y,w,h} für Werte (0..max), max optional fix
  VZ.bars = function (vals, w, h, gap, maxOverride) {
    gap = gap == null ? 3 : gap;
    const max = maxOverride || Math.max.apply(null, vals) || 1;
    const n = vals.length;
    const bw = (w - gap * (n - 1)) / n;
    return vals.map((v, i) => {
      const bh = Math.max(1, (v / max) * h);
      return { x: i * (bw + gap), y: h - bh, w: bw, h: bh, v: v };
    });
  };

  // Arc-Gauge: gibt {dash, gap, len} für einen 270°-Bogen bei Radius r
  VZ.arc = function (pct, r) {
    const sweep = 0.75;                 // 270° von 360°
    const circ = 2 * Math.PI * r;
    const len = circ * sweep;
    const fill = len * Math.max(0, Math.min(1, pct / 100));
    return { len: len, fill: fill, circ: circ };
  };

  // ASCII-Balken: '██████░░░░'
  VZ.asciiBar = function (pct, width, full, empty) {
    full = full || '█'; empty = empty || '░';
    const n = Math.round((Math.max(0, Math.min(100, pct)) / 100) * width);
    return full.repeat(n) + empty.repeat(Math.max(0, width - n));
  };

  // Braille-Sparkline (8-Level Höhe pro Zelle, kompakt)
  VZ.brailleSpark = function (vals) {
    const levels = '⣀⣀⣤⣤⣶⣶⣿⣿';
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const rng = (max - min) || 1;
    return vals.map(v => {
      const idx = Math.round(((v - min) / rng) * (levels.length - 1));
      return levels[idx];
    }).join('');
  };

  // Block-Sparkline mit ▁▂▃▄▅▆▇█
  VZ.blockSpark = function (vals) {
    const blocks = '▁▂▃▄▅▆▇█';
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const rng = (max - min) || 1;
    return vals.map(v => blocks[Math.round(((v - min) / rng) * (blocks.length - 1))]).join('');
  };

  // Rotierende Wireframe-Kugel als ASCII-Flipbook.
  // Punkte auf Längen-/Breitengraden werden rotiert, projiziert und mit
  // Tiefen-Zeichen in ein Zeichengitter geschrieben (z-Buffer → vorne
  // überschreibt hinten). Alle Frames werden EINMAL gebaut → Laufzeit nur
  // textContent-Tausch (Pi-3B-tauglich, keine Mathe/Allokation pro Frame).
  VZ.sphereFlipbook = function (opts) {
    opts = opts || {};
    var COLS = opts.cols || 40, ROWS = opts.rows || 20, N = opts.frames || 72;
    var ramp = opts.ramp || ' .·:-=+o*#@';
    var tilt = opts.tilt == null ? 0.42 : opts.tilt;
    var cx = COLS / 2, cy = ROWS / 2;
    var sY = ROWS * (opts.fill || 0.46), sX = sY * 1.95; // Zeichen sind ~halb so breit wie hoch
    var cosT = Math.cos(tilt), sinT = Math.sin(tilt);
    var frames = [];
    for (var f = 0; f < N; f++) {
      var ay = f / N * Math.PI * 2, cosA = Math.cos(ay), sinA = Math.sin(ay);
      var grid = [], zb = [];
      for (var r = 0; r < ROWS; r++) { grid.push(new Array(COLS).fill(' ')); zb.push(new Array(COLS).fill(-2)); }
      function plot(x, y, z) {
        var x1 = x * cosA + z * sinA, z1 = -x * sinA + z * cosA;
        var y2 = y * cosT - z1 * sinT, z2 = y * sinT + z1 * cosT;
        var sx = Math.round(cx + x1 * sX), sy = Math.round(cy - y2 * sY);
        if (sx < 0 || sx >= COLS || sy < 0 || sy >= ROWS) return;
        if (z2 > zb[sy][sx]) {
          zb[sy][sx] = z2;
          var t = (z2 + 1) / 2; if (t < 0) t = 0; if (t > 1) t = 1;
          grid[sy][sx] = ramp[Math.floor(t * (ramp.length - 1))];
        }
      }
      var DEG = Math.PI / 180;
      // Breitengrade
      for (var la = -80; la <= 80; la += 20) {
        var ph = la * DEG, cp = Math.cos(ph), sp = Math.sin(ph);
        for (var lo = 0; lo < 360; lo += 6) { var th = lo * DEG; plot(cp * Math.cos(th), sp, cp * Math.sin(th)); }
      }
      // Längengrade
      for (var lo2 = 0; lo2 < 360; lo2 += 30) {
        var th2 = lo2 * DEG, ct = Math.cos(th2), st = Math.sin(th2);
        for (var la2 = -90; la2 <= 90; la2 += 6) { var ph2 = la2 * DEG, cp2 = Math.cos(ph2); plot(cp2 * ct, Math.sin(ph2), cp2 * st); }
      }
      frames.push(grid.map(function (row) { return row.join(''); }).join('\n'));
    }
    return { frames: frames, cols: COLS, rows: ROWS };
  };

  global.VZ = VZ;
})(window);
