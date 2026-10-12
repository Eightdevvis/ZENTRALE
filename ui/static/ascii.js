/* ============================================================================
   ZENTRALE — ASCII-Bibliothek (ascii.js)
   ----------------------------------------------------------------------------
   Die KI „gestikuliert" über Text statt über echte Bilder/Video: Gesichter
   (nach Zustand), rotierende 3D-Objekte (Torus/Würfel — als vorberechnete
   Flipbooks) und eine animierte Weltkarte mit pulsierenden Hotspots. Alles
   wird EINMAL gebaut → Laufzeit nur textContent-Tausch (Pi-3B-tauglich).
   ========================================================================== */
(function (global) {
  'use strict';
  var ASCII = {};

  /* ── Gesichter ───────────────────────────────────────────────────────────
     Konsistentes 19×7-Kästchen. Augen/Mund je 9 Zeichen breit. */
  function face(eyes, mouth) {
    return [
      '  ┌───────────────┐',
      '  │               │',
      '  │   ' + eyes + '   │',
      '  │               │',
      '  │   ' + mouth + '   │',
      '  │               │',
      '  └───────────────┘'
    ].join('\n');
  }
  ASCII.faces = {
    neutral:  [face(' ●     ● ', '  ─────  '), face(' ●     ● ', '  ─────  '), face(' ─     ─ ', '  ─────  ')],
    denkt:    [face(' ◔     ◔ ', '  · · ·  '), face(' ◑     ◑ ', '  · · ·  '), face(' ◔     ◔ ', '  ·· ·   ')],
    spricht:  [face(' ●     ● ', '  ═════  '), face(' ●     ● ', '  ◌◌◌◌◌  '), face(' ●     ● ', '  ═══──  ')],
    freut:    [face(' ⌣     ⌣ ', '  ╲▁▁▁╱  ')],
    hoert:    [face(' ●     ● ', '    ◦    ')],
    skeptisch:[face(' ●     ─ ', '  ──╮    ')]
  };
  // Liefert je nach Zustand+Tick ein Gesicht (Blinzeln/Reden animiert)
  ASCII.faceFrame = function (state, fi) {
    if (state === 'thinking') return ASCII.faces.denkt[fi % 3];
    if (state === 'streaming') return ASCII.faces.spricht[fi % 3];
    // idle: meist neutral, gelegentlich blinzeln
    return (fi % 22 === 0) ? ASCII.faces.neutral[2] : ASCII.faces.neutral[0];
  };

  /* ── Bild → ASCII Filter ───────────────────────────────────────────────────
     Das Herzstück: ein Canvas (echtes/gezeichnetes Bild) wird blockweise auf
     Helligkeit gemittelt und auf eine Zeichen-Rampe gemappt — genau das, was
     jp2a / chafa / aalib tun. Schiebt man später ein echtes Foto- oder Webcam-
     Frame in den Canvas, läuft dieselbe Funktion drüber. */
  ASCII.canvasToAscii = function (cv, cols, rows, opts) {
    opts = opts || {};
    var ramp = opts.ramp || ' .:-=+*#%@';
    var gamma = opts.gamma || 1, invert = !!opts.invert;
    var ctx = cv.getContext('2d'), W = cv.width, H = cv.height;
    var data = ctx.getImageData(0, 0, W, H).data;
    var cw = W / cols, ch = H / rows, out = '';
    for (var r = 0; r < rows; r++) {
      for (var c = 0; c < cols; c++) {
        var x0 = (c*cw)|0, y0 = (r*ch)|0, x1 = ((c+1)*cw)|0, y1 = ((r+1)*ch)|0, sum = 0, n = 0;
        for (var y = y0; y < y1; y++) { var ro = y*W*4; for (var x = x0; x < x1; x++) { var i = ro + x*4; sum += 0.299*data[i] + 0.587*data[i+1] + 0.114*data[i+2]; n++; } }
        var l = (sum/(n||1))/255; l = Math.pow(l, gamma); if (invert) l = 1 - l;
        if (l < 0) l = 0; if (l > 1) l = 1;
        out += ramp[(l*(ramp.length-1))|0];
      }
      out += '\n';
    }
    return out;
  };

  function shade(v) { v = v < 0 ? 0 : (v > 1 ? 1 : v); var n = Math.round(v*255); return 'rgb(' + n + ',' + n + ',' + n + ')'; }

  /* ── Graustufen-Porträt zeichnen (Quelle für den Filter) ──────────────────── */
  ASCII.drawPortrait = function (ctx, W, H, p) {
    p = p || {};
    var cx = W/2, faceCy = H*0.46, rx = W*0.30*(p.wide?1.12:1.0), ry = H*0.34, skin = p.skin||0;
    ctx.clearRect(0,0,W,H); ctx.fillStyle = '#f4f4f4'; ctx.fillRect(0,0,W,H);
    ctx.fillStyle = shade(0.62+skin); ctx.fillRect(cx-W*0.11, faceCy+ry*0.62, W*0.22, H*0.4);
    ctx.fillStyle = 'rgba(0,0,0,0.18)'; ctx.fillRect(cx-W*0.11, faceCy+ry*0.62, W*0.07, H*0.4);
    ctx.save();
    ctx.beginPath(); ctx.ellipse(cx, faceCy, rx, ry, 0, 0, 7); ctx.closePath(); ctx.clip();
    var g = ctx.createLinearGradient(0, faceCy-ry, 0, faceCy+ry);
    g.addColorStop(0, shade(0.90+skin)); g.addColorStop(0.55, shade(0.80+skin)); g.addColorStop(1, shade(0.66+skin));
    ctx.fillStyle = g; ctx.fillRect(0,0,W,H);
    var rg = ctx.createRadialGradient(cx-rx*0.45, faceCy-ry*0.35, rx*0.2, cx+rx*0.5, faceCy+ry*0.5, rx*1.5);
    rg.addColorStop(0,'rgba(0,0,0,0)'); rg.addColorStop(1,'rgba(0,0,0,0.34)');
    ctx.fillStyle = rg; ctx.fillRect(0,0,W,H);
    ctx.restore();
    var noseTop = faceCy-ry*0.12, noseBot = faceCy+ry*0.22;
    ctx.strokeStyle='rgba(255,255,255,0.5)'; ctx.lineWidth=W*0.022; ctx.lineCap='round';
    ctx.beginPath(); ctx.moveTo(cx-W*0.004, noseTop); ctx.lineTo(cx-W*0.008, noseBot); ctx.stroke();
    ctx.strokeStyle='rgba(0,0,0,0.16)'; ctx.lineWidth=W*0.02;
    ctx.beginPath(); ctx.moveTo(cx+W*0.028, noseTop); ctx.lineTo(cx+W*0.018, noseBot); ctx.stroke();
    ctx.fillStyle='rgba(0,0,0,0.30)';
    ctx.beginPath(); ctx.ellipse(cx-W*0.032, noseBot, W*0.016, H*0.011,0,0,7); ctx.fill();
    ctx.beginPath(); ctx.ellipse(cx+W*0.032, noseBot, W*0.016, H*0.011,0,0,7); ctx.fill();
    var eyeY = faceCy - ry*0.08, eyeDX = rx*0.44, ew = rx*0.22, eh = ry*0.085;
    [-1, 1].forEach(function (s0) {
      var exx = cx + s0*eyeDX;
      if (p.eyes === 'closed') { ctx.strokeStyle='#3a3a3a'; ctx.lineWidth=H*0.012; ctx.beginPath(); ctx.moveTo(exx-ew, eyeY); ctx.lineTo(exx+ew, eyeY); ctx.stroke(); }
      else {
        ctx.fillStyle='rgba(0,0,0,0.10)'; ctx.beginPath(); ctx.ellipse(exx, eyeY, ew*1.3, eh*1.8,0,0,7); ctx.fill();
        ctx.fillStyle='#fbfbfb'; ctx.beginPath(); ctx.ellipse(exx, eyeY, ew, eh,0,0,7); ctx.fill();
        var iy = eyeY + (p.eyes==='up'? -eh*0.5 : 0);
        ctx.fillStyle='#2b2b2b'; ctx.beginPath(); ctx.ellipse(exx, iy, eh*0.95, eh*0.95,0,0,7); ctx.fill();
        ctx.strokeStyle='rgba(0,0,0,0.4)'; ctx.lineWidth=H*0.006; ctx.beginPath(); ctx.ellipse(exx, eyeY, ew, eh, 0, Math.PI*1.05, Math.PI*1.95); ctx.stroke();
      }
      ctx.strokeStyle=shade(0.30); ctx.lineWidth=(p.brow? H*0.018 : H*0.012); ctx.lineCap='round';
      var by = eyeY - eh - ry*0.11 + (p.think && s0>0 ? -ry*0.05 : 0);
      ctx.beginPath(); ctx.moveTo(exx-ew, by+ry*0.01); ctx.quadraticCurveTo(exx, by-ry*0.03, exx+ew, by); ctx.stroke();
    });
    var mY = faceCy + ry*0.5;
    if (p.mouth === 'open' || p.mouth === 'wide') {
      var mh = (p.mouth==='wide'? ry*0.14 : ry*0.08);
      ctx.fillStyle='#5a3a3a'; ctx.beginPath(); ctx.ellipse(cx, mY, rx*0.26, mh, 0,0,7); ctx.fill();
      ctx.fillStyle='#e8e8e8'; ctx.fillRect(cx-rx*0.2, mY-mh*0.7, rx*0.4, mh*0.5);
    } else {
      ctx.strokeStyle=shade(0.42); ctx.lineWidth=H*0.013; ctx.lineCap='round';
      var mw = rx*(p.lips?0.30:0.24);
      ctx.beginPath(); ctx.moveTo(cx-mw, mY); ctx.quadraticCurveTo(cx, mY+ry*0.03, cx+mw, mY); ctx.stroke();
      ctx.strokeStyle='rgba(255,255,255,0.35)'; ctx.lineWidth=H*0.01; ctx.beginPath(); ctx.moveTo(cx-rx*0.16, mY+ry*0.04); ctx.lineTo(cx+rx*0.16, mY+ry*0.04); ctx.stroke();
    }
    if (p.beard) { ctx.save(); ctx.beginPath(); ctx.ellipse(cx, faceCy, rx, ry,0,0,7); ctx.clip(); ctx.fillStyle='rgba(35,35,35,0.55)'; ctx.beginPath(); ctx.ellipse(cx, faceCy+ry*0.62, rx*0.82, ry*0.5,0,0,7); ctx.fill(); ctx.restore(); }
    if (p.hair !== 'glatze') {
      ctx.fillStyle = p.hairLight ? shade(0.5) : shade(0.22);
      ctx.beginPath(); ctx.ellipse(cx, faceCy-ry*0.6, rx*1.05, ry*0.72, 0, Math.PI*0.98, Math.PI*2.02); ctx.fill();
      ctx.beginPath(); ctx.ellipse(cx, faceCy-ry*0.8, rx*1.02, ry*0.5,0,0,7); ctx.fill();
      if (p.hair === 'lang') { ctx.fillRect(cx-rx*1.05, faceCy-ry*0.5, rx*0.26, ry*1.5); ctx.fillRect(cx+rx*0.79, faceCy-ry*0.5, rx*0.26, ry*1.5); }
    }
    if (p.glasses) { ctx.strokeStyle='#2e2e2e'; ctx.lineWidth=H*0.008; [-1,1].forEach(function (s0) { var exx=cx+s0*eyeDX; ctx.strokeRect(exx-ew*1.25, eyeY-eh*1.7, ew*2.5, eh*3.4); }); ctx.beginPath(); ctx.moveTo(cx-eyeDX+ew*1.25, eyeY-eh*0.2); ctx.lineTo(cx+eyeDX-ew*1.25, eyeY-eh*0.2); ctx.stroke(); }
  };

  /* ── Mehrere Menschen × Ausdrücke → ASCII (vorberechnet) ──────────────────── */
  ASCII.buildPeople = function (opts) {
    opts = opts || {};
    var cols = opts.cols || 48, rows = opts.rows || 46, W = 176, H = 212;
    var cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    var ctx = cv.getContext('2d');
    var ramp = opts.ramp || ' .:-=+*#%@';
    function render(p) { ASCII.drawPortrait(ctx, W, H, p); return ASCII.canvasToAscii(cv, cols, rows, { ramp: ramp, invert: true, gamma: 1.15 }); }
    var defs = [
      { name: 'NOVA', hair: 'kurz', brow: true, skin: 0.00 },
      { name: 'IRIS', hair: 'lang', hairLight: true, lips: true, skin: 0.10 },
      { name: 'KORE', hair: 'kurz', beard: true, wide: true, skin: -0.08 },
      { name: 'ECHO', hair: 'glatze', glasses: true, skin: 0.05 }
    ];
    return defs.map(function (d) {
      function ex(o) { var q = {}; for (var k in d) q[k] = d[k]; for (var k2 in o) q[k2] = o[k2]; return q; }
      return {
        name: d.name,
        neutral: render(ex({ eyes: 'open', mouth: 'line' })),
        blink:   render(ex({ eyes: 'closed', mouth: 'line' })),
        denkt:   render(ex({ eyes: 'up', mouth: 'line', think: true })),
        talk:  [ render(ex({ eyes: 'open', mouth: 'open' })), render(ex({ eyes: 'open', mouth: 'wide' })) ]
      };
    });
  };
  ASCII.personFrame = function (person, state, fi) {
    if (state === 'thinking') return person.denkt;
    if (state === 'streaming') return person.talk[fi % 2];
    return (fi % 24 < 1) ? person.blink : person.neutral;
  };

  /* ── Rotierender Torus (klassischer ASCII-Donut) ─────────────────────────── */
  ASCII.torusFlipbook = function (opts) {
    opts = opts || {};
    var COLS = opts.cols || 58, ROWS = opts.rows || 28, N = opts.frames || 60;
    var ramp = opts.ramp || '.,-~:;=!*#$@';
    var R1 = 1, R2 = 2, K2 = 5;
    var K1 = COLS * K2 * 3 / (8 * (R1 + R2));
    var frames = [];
    for (var f = 0; f < N; f++) {
      var A = f / N * Math.PI * 2, B = f / N * Math.PI * 4;
      var cA = Math.cos(A), sA = Math.sin(A), cB = Math.cos(B), sB = Math.sin(B);
      var out = new Array(ROWS * COLS).fill(' '), zb = new Array(ROWS * COLS).fill(0);
      for (var th = 0; th < 6.283; th += 0.10) {
        var ct = Math.cos(th), st = Math.sin(th);
        for (var ph = 0; ph < 6.283; ph += 0.03) {
          var cp = Math.cos(ph), sp = Math.sin(ph);
          var cx = R2 + R1 * ct, cy = R1 * st;
          var x = cx * (cB * cp + sA * sB * sp) - cy * cA * sB;
          var y = cx * (sB * cp - sA * cB * sp) + cy * cA * cB;
          var z = K2 + cA * cx * sp + cy * sA, ooz = 1 / z;
          var xp = Math.floor(COLS / 2 + K1 * ooz * x);
          var yp = Math.floor(ROWS / 2 - K1 * ooz * y * 0.5);
          var L = cp * ct * sB - cA * ct * sp - sA * st + cB * (cA * st - ct * sA * sp);
          if (L > 0 && xp >= 0 && xp < COLS && yp >= 0 && yp < ROWS) {
            var idx = xp + COLS * yp;
            if (ooz > zb[idx]) { zb[idx] = ooz; var l = Math.floor(L * 8); out[idx] = ramp[l > ramp.length - 1 ? ramp.length - 1 : l]; }
          }
        }
      }
      var s = ''; for (var r = 0; r < ROWS; r++) s += out.slice(r * COLS, (r + 1) * COLS).join('') + '\n';
      frames.push(s);
    }
    return { frames: frames, cols: COLS, rows: ROWS };
  };

  /* ── Rotierender Drahtgitter-Würfel ──────────────────────────────────────── */
  ASCII.cubeFlipbook = function (opts) {
    opts = opts || {};
    var COLS = opts.cols || 48, ROWS = opts.rows || 26, N = opts.frames || 60;
    var ramp = opts.ramp || '·:-=+*#@';
    var V = [[-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],[-1,-1,1],[1,-1,1],[1,1,1],[-1,1,1]];
    var E = [[0,1],[1,2],[2,3],[3,0],[4,5],[5,6],[6,7],[7,4],[0,4],[1,5],[2,6],[3,7]];
    var sX = COLS * 0.30, sY = ROWS * 0.34, tilt = 0.5;
    var cT = Math.cos(tilt), sT = Math.sin(tilt);
    var frames = [];
    for (var f = 0; f < N; f++) {
      var ay = f / N * Math.PI * 2, cy0 = Math.cos(ay), sy0 = Math.sin(ay);
      var grid = new Array(ROWS * COLS).fill(' '), zb = new Array(ROWS * COLS).fill(-9);
      var P = V.map(function (v) {
        var x = v[0] * cy0 + v[2] * sy0, z = -v[0] * sy0 + v[2] * cy0, y = v[1];
        var y2 = y * cT - z * sT, z2 = y * sT + z * cT;
        return { x: COLS / 2 + x * sX, y: ROWS / 2 - y2 * sY, z: z2 };
      });
      function plot(px, py, pz) {
        var xi = Math.round(px), yi = Math.round(py);
        if (xi < 0 || xi >= COLS || yi < 0 || yi >= ROWS) return;
        var i = xi + COLS * yi;
        if (pz > zb[i]) { zb[i] = pz; var t = (pz + 1.8) / 3.6; var li = Math.floor(t * (ramp.length - 1)); grid[i] = ramp[li < 0 ? 0 : (li > ramp.length - 1 ? ramp.length - 1 : li)]; }
      }
      E.forEach(function (e) {
        var a = P[e[0]], b = P[e[1]], steps = 26;
        for (var s = 0; s <= steps; s++) { var t = s / steps; plot(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t); }
      });
      var str = ''; for (var r = 0; r < ROWS; r++) str += grid.slice(r * COLS, (r + 1) * COLS).join('') + '\n';
      frames.push(str);
    }
    return { frames: frames, cols: COLS, rows: ROWS };
  };

  /* ── Weltkarte: Canvas-Kontinente → ASCII-Filter ─────────────────────────
     Kontinente als weiche Ellipsen-Gruppen auf einem Canvas (mit Blur für
     organische Küsten), dann durch denselben Helligkeits-Filter. Ergibt
     schattierte Küsten statt harter Blöcke. Darüber ein feines Gradnetz und
     pulsierende, neutral benannte Hotspots (AOI-n). */
  ASCII.buildWorld = function (opts) {
    opts = opts || {};
    var cols = opts.cols || 78, rows = opts.rows || 30;
    var W = cols * 5, H = rows * 5;
    var cv = document.createElement('canvas'); cv.width = W; cv.height = H;
    var ctx = cv.getContext('2d');
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
    // Kontinente als Ellipsen-Gruppen in normierten [0..1]-Koordinaten
    var cont = [
      [[0.15,0.27,0.085,0.10],[0.20,0.35,0.07,0.10],[0.10,0.30,0.045,0.07],[0.235,0.22,0.05,0.05],[0.165,0.45,0.03,0.05]], // Nordamerika
      [[0.30,0.17,0.035,0.045]],                                                                                            // Grönland
      [[0.275,0.60,0.045,0.07],[0.30,0.72,0.03,0.10],[0.255,0.54,0.035,0.045]],                                            // Südamerika
      [[0.495,0.27,0.04,0.055],[0.46,0.30,0.02,0.03]],                                                                      // Europa
      [[0.525,0.50,0.05,0.085],[0.55,0.62,0.04,0.075],[0.495,0.43,0.035,0.045],[0.565,0.45,0.025,0.04]],                   // Afrika
      [[0.66,0.29,0.125,0.095],[0.75,0.23,0.07,0.06],[0.60,0.36,0.045,0.05]],                                              // Asien
      [[0.655,0.46,0.038,0.05]],                                                                                            // Indien
      [[0.79,0.55,0.045,0.025],[0.815,0.50,0.018,0.018],[0.835,0.58,0.02,0.015]],                                          // SO-Asien Inseln
      [[0.85,0.71,0.055,0.045]],                                                                                            // Australien
      [[0.535,0.86,0.18,0.05]]                                                                                              // Antarktis-Saum
    ];
    ctx.filter = 'blur(' + Math.max(2, W*0.006) + 'px)';
    ctx.fillStyle = '#fff';
    cont.forEach(function (grp) { grp.forEach(function (e) { ctx.beginPath(); ctx.ellipse(e[0]*W, e[1]*H, e[2]*W, e[3]*H, 0, 0, 7); ctx.fill(); }); });
    ctx.filter = 'none';
    var base = ASCII.canvasToAscii(cv, cols, rows, { ramp: ' ..:-=+o*#', invert: false, gamma: 0.72 }).split('\n').map(function (r) { return r.split(''); });
    // feines Gradnetz auf offener See
    for (var y = 0; y < rows; y++) for (var x = 0; x < cols; x++) {
      if (base[y] && (base[y][x] === ' ' || base[y][x] === undefined)) { base[y][x] = (x % 9 === 0 && y % 4 === 2) ? '·' : ' '; }
    }
    var zones = opts.zones || [
      { x: Math.round(0.20*cols), y: Math.round(0.34*rows), l: 'AOI-1' },
      { x: Math.round(0.50*cols), y: Math.round(0.30*rows), l: 'AOI-2' },
      { x: Math.round(0.55*cols), y: Math.round(0.55*rows), l: 'AOI-3' },
      { x: Math.round(0.66*cols), y: Math.round(0.34*rows), l: 'AOI-4' },
      { x: Math.round(0.30*cols), y: Math.round(0.66*rows), l: 'AOI-5' }
    ];
    return {
      cols: cols, rows: rows, zones: zones,
      frame: function (phase) {
        var g = base.map(function (r) { return r.slice(); });
        zones.forEach(function (z, i) {
          if (z.y < 0 || z.y >= rows || z.x < 0 || z.x >= cols) return;
          var on = ((phase + i) % 4) < 2;
          g[z.y][z.x] = on ? '◉' : '○';
        });
        return g.map(function (r) { return r.join(''); }).join('\n');
      }
    };
  };

  global.ASCII = ASCII;
})(window);
