/* ============================================================================
   ZENTRALE — Simulations-Engine (engine.js)
   ----------------------------------------------------------------------------
   Eine kleine, framework-freie Pub/Sub-Quelle, die den Live-Charakter der
   echten ZENTRALE nachbildet: ein stdout-Stream mit dem echten Log-Vokabular
   (NET → / EVENT IN: / GRAPH ⊕ / STT → / TTS → / WEBHOOK …), Sensor-Trigger,
   KI-Denk-/Stream-Zyklen und Tracker-Daten (Schlaf, Stimmung, Projekte, Pi-
   Telemetrie). Jede Design-Richtung abonniert dieselbe Quelle und rendert sie
   in ihrer eigenen Ästhetik. Vanilla JS, kein Build, kein CDN — wie das echte
   Projekt (siehe memory/dashboard.md).
   ========================================================================== */
(function (global) {
  'use strict';

  // ── deterministischer PRNG, damit die Historie überall gleich „designt" aussieht
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const seed = mulberry32(20260606);
  const rint = (lo, hi) => Math.floor(seed() * (hi - lo + 1)) + lo;

  // ── Tracker-Historie (14 Tage), bewusst mit Rhythmus statt Rauschen ──────
  const DAYS = 14;
  const dayLabels = [];
  (function () {
    const base = new Date(2026, 5, 6); // 6. Juni 2026
    for (let i = DAYS - 1; i >= 0; i--) {
      const d = new Date(base); d.setDate(base.getDate() - i);
      dayLabels.push(('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2));
    }
  })();

  const sleep  = [3, 4, 2, 3, 4, 4, 5, 3, 2, 4, 5, 4, 3, 4];           // 1..5
  const mood   = [3, 3, 4, 2, 3, 4, 4, 5, 4, 3, 4, 5, 4, 4];           // 1..5
  const focus  = [62, 71, 48, 80, 75, 90, 84, 55, 67, 88, 92, 79, 73, 86]; // %
  const steps  = [5.2, 8.1, 3.4, 9.6, 7.2, 11.3, 6.8, 4.1, 8.9, 10.2, 12.6, 7.7, 6.3, 9.1]; // k

  const projects = [
    { id: 'graph-memory',  name: 'Graph-Memory',     pct: 88, status: 'aktiv' },
    { id: 'voice-main',    name: 'Voice im Main-Mode', pct: 41, status: 'wip' },
    { id: 'gpio-pir',      name: 'GPIO / PIR-Sensor', pct: 12, status: 'geplant' },
    { id: 'rss-digest',    name: 'RSS-Zusammenfassung', pct: 0, status: 'idee' },
  ];

  // ── Pi-Telemetrie (live, random-walk um einen Mittelwert) ────────────────
  const metrics = {
    cpu:  { v: 34, min: 6,  max: 96, unit: '%',  label: 'CPU' },
    temp: { v: 52, min: 38, max: 78, unit: '°C', label: 'KERN-TEMP' },
    ram:  { v: 61, min: 20, max: 92, unit: '%',  label: 'RAM' },
    gpu:  { v: 28, min: 4,  max: 88, unit: '%',  label: 'GPU' },
    net:  { v: 2,  min: 0,  max: 40, unit: 'kB', label: 'LAN I/O' },
    disk: { v: 47, min: 30, max: 70, unit: '%',  label: 'DISK' },
  };
  const metHist = {}; // kurze Verläufe je Metrik für Sparklines
  Object.keys(metrics).forEach(k => { metHist[k] = Array.from({ length: 40 }, () => metrics[k].v); });

  // ── Sensoren ─────────────────────────────────────────────────────────────
  const sensors = {
    button: { active: false, label: 'BUTTON', kind: 'puls' },
    light:  { active: true,  label: 'LICHT', kind: 'wert', value: 612, unit: 'lux' },
    motion: { active: false, label: 'BEWEGUNG', kind: 'puls' },
    door:   { active: false, label: 'TÜR', kind: 'puls' },
  };

  // ── KI: Prompt/Antwort-Paare (deutsch, lokal) ────────────────────────────
  const dialog = [
    { q: 'wie war mein schlaf diese woche',
      a: 'Im Schnitt 3.6 von 5. Dienstag war der Ausreißer nach unten — danach ging es wieder stetig hoch. Ich habe das im Graphen mit „Bildschirmzeit" verknüpft.' },
    { q: 'fasse die letzten events zusammen',
      a: 'Drei Bewegungs-Trigger, zweimal Licht-Wechsel, ein Tür-Event um 17:42. Nichts Außergewöhnliches. Alles lokal verarbeitet, keine Pakete nach außen.' },
    { q: 'wie warm ist es im raum',
      a: 'Der Lichtsensor meldet 612 lux, also helles Tageslicht. Eine echte Raumtemperatur habe ich nicht — der HC-SR501 ist noch nicht am GPIO. Steht auf der Roadmap.' },
    { q: 'woran arbeite ich gerade',
      a: 'Graph-Memory ist quasi durch (88%). Voice im Main-Mode hängt bei 41% — die Orb-Lebenszyklen sind verdrahtet, der Mikrofon-Trigger fehlt noch. Soll ich das hochpriorisieren?' },
    { q: 'bist du wirklich offline',
      a: 'Ja. Ollama, Whisper und TTS laufen alle lokal. Das orange Panel rechts unten ist mein Tripwire — solange da nichts steht, ging kein Paket raus.' },
  ];

  // ── Log-Vokabular (gewichteter Pool) ──────────────────────────────────────
  const logPool = [
    () => 'EVENT IN : ' + pick(['MOTION_DETECTED', 'BUTTON_PRESSED', 'LIGHT_CHANGED', 'TIME_REACHED', 'DOOR_OPENED']),
    () => 'EVENT OUT: ' + pick(['GREETING', 'AMBIENT_DIM', 'LOG_VITALS', 'IDLE_RETURN']),
    () => 'NET → 127.0.0.1:11434/api/chat',
    () => 'NET ← 200 qwen2.5:14b (' + (0.8 + seed() * 2.4).toFixed(1) + 's)',
    () => 'NET → 127.0.0.1:11434/api/embeddings',
    () => 'NET ← 200 bge-m3 · ' + rint(384, 1024) + ' dim',
    () => 'GRAPH ⊕ ' + pick(['"Schlaf" ↔ "Bildschirmzeit"', '"Projekt" ↔ "Voice"', '"Raum" ↔ "Bewegung"', '"Routine" ↔ "Abend"']),
    () => 'GRAPH → query: ' + rint(2, 9) + ' nodes · ' + rint(1, 6) + ' edges',
    () => 'GRAPH ← cache hit (' + rint(2, 40) + 'ms)',
    () => 'STT → "' + pick(['wie spät ist es', 'guten morgen', 'was steht heute an', 'wie geht es dir']) + '"',
    () => 'TTS → de · piper · ' + rint(4, 22) + ' words',
    () => 'WEBHOOK: sensor/' + pick(['motion', 'button', 'light', 'door']) + ' von 192.168.4.' + rint(10, 60),
    () => 'CONSOLIDATE ⊕ ' + rint(1, 3) + ' facts → graph',
    () => 'STATE set_sensor ' + pick(['light=true', 'light=false', 'motion=true', 'door=false']),
    () => 'CLOCK → TIME_REACHED ' + ('0' + rint(7, 22)).slice(-2) + ':00',
  ];
  // sehr seltene, echte Internet-Calls (Tripwire-Panel)
  const netPool = [
    () => 'NET → api.github.com/.../deploy/RELEASE',
    () => 'NET ← 200 RELEASE unverändert · kein pull',
    () => 'NET → github.com/zentrale.git (autopull-cron)',
  ];

  function pick(a) { return a[Math.floor(Math.random() * a.length)]; }
  function now2() {
    const d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => ('0' + n).slice(-2)).join(':');
  }

  // ── Pub/Sub ───────────────────────────────────────────────────────────────
  const subs = { log: [], net: [], sensor: [], ai: [], tick: [] };
  function emit(ch, payload) { (subs[ch] || []).forEach(fn => { try { fn(payload); } catch (e) {} }); }

  // ── KI-State-Maschine ──────────────────────────────────────────────────────
  let aiState = 'idle';
  const aiHistory = []; // {role:'user'|'ai', text}
  let dialogIdx = 0;

  function runAiCycle() {
    if (aiState !== 'idle') return;
    const pair = dialog[dialogIdx % dialog.length]; dialogIdx++;

    // 1) thinking
    aiState = 'thinking';
    emit('ai', { state: 'thinking' });
    pushLog('EVENT IN : VOICE_QUERY', false);

    setTimeout(() => {
      aiHistory.push({ role: 'user', text: pair.q });
      emit('ai', { state: 'thinking', user: pair.q });
      pushLog('NET → 127.0.0.1:11434/api/chat', false);

      setTimeout(() => {
        // 2) streaming token-für-token
        aiState = 'streaming';
        const tokens = pair.a.split(/(\s+)/);
        let acc = '';
        const aiEntry = { role: 'ai', text: '' };
        aiHistory.push(aiEntry);
        emit('ai', { state: 'streaming', user: pair.q });
        let i = 0;
        const iv = setInterval(() => {
          if (i >= tokens.length) {
            clearInterval(iv);
            pushLog('NET ← 200 qwen2.5:14b (' + (1.1 + Math.random() * 1.8).toFixed(1) + 's)', false);
            pushLog('GRAPH ⊕ ' + pick(['"Schlaf" ↔ "Routine"', '"Projekt" ↔ "Voice"', '"Raum" ↔ "Bewegung"']), false);
            aiState = 'idle';
            emit('ai', { state: 'idle' });
            return;
          }
          acc += tokens[i]; i++;
          aiEntry.text = acc;
          emit('ai', { state: 'streaming', token: tokens[i - 1], text: acc, user: pair.q });
        }, 55);
      }, 900 + Math.random() * 700);
    }, 500);
  }

  function pushLog(text, internet) {
    const entry = { t: now2(), text: text, internet: !!internet };
    emit('log', entry);
    if (internet) emit('net', entry);
  }

  // ── Sensor-Trigger ──────────────────────────────────────────────────────────
  function fireSensor(name) {
    const s = sensors[name]; if (!s) return;
    if (s.kind === 'puls') {
      s.active = true; emit('sensor', { name, active: true, sensors });
      setTimeout(() => { s.active = false; emit('sensor', { name, active: false, sensors }); }, 1400 + Math.random() * 1600);
    } else { // licht: Wert wechseln
      s.value = rint(40, 980); emit('sensor', { name, active: s.active, value: s.value, sensors });
    }
    pushLog('WEBHOOK: sensor/' + name + ' von 192.168.4.' + rint(10, 60), false);
  }

  // ── Loops ────────────────────────────────────────────────────────────────────
  let started = false;
  function start() {
    if (started) return; started = true;

    // Clock (1s)
    function tick() {
      const d = new Date();
      const time = [d.getHours(), d.getMinutes(), d.getSeconds()].map(n => ('0' + n).slice(-2)).join(':');
      const date = d.getDate() + '. ' + ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'][d.getMonth()] + ' ' + d.getFullYear();

      // Telemetrie random-walk
      Object.keys(metrics).forEach(k => {
        const m = metrics[k];
        let nv = m.v + (Math.random() - 0.5) * (m.max - m.min) * 0.08;
        nv = Math.max(m.min, Math.min(m.max, nv));
        m.v = nv;
        metHist[k].push(nv); if (metHist[k].length > 40) metHist[k].shift();
      });
      // gelegentlich der light-lux drift
      if (Math.random() < 0.25) { sensors.light.value = Math.max(0, Math.min(999, sensors.light.value + rint(-60, 60))); }

      emit('tick', { time, date, metrics, metHist, sensors });
    }
    tick();
    setInterval(tick, 1000);

    // stdout-Stream: alle 1.2–3.2s eine Zeile
    function logLoop() {
      pushLog(pick(logPool)(), false);
      setTimeout(logLoop, 1200 + Math.random() * 2000);
    }
    setTimeout(logLoop, 600);

    // Internet-Tripwire: sehr selten (alle ~70–130s) eine Zeile
    function netLoop() {
      pushLog(pick(netPool)(), true);
      setTimeout(netLoop, 70000 + Math.random() * 60000);
    }
    setTimeout(netLoop, 45000);

    // Sensor-Trigger: zufällig
    function sensorLoop() {
      fireSensor(pick(['motion', 'button', 'light', 'door']));
      setTimeout(sensorLoop, 4000 + Math.random() * 7000);
    }
    setTimeout(sensorLoop, 2500);

    // KI-Zyklus: alle ~16–26s wacht sie auf
    function aiLoop() {
      runAiCycle();
      setTimeout(aiLoop, 16000 + Math.random() * 10000);
    }
    setTimeout(aiLoop, 4500);
  }

  // ── Öffentliche API ────────────────────────────────────────────────────────
  global.ZS = {
    on(ch, fn) { (subs[ch] || (subs[ch] = [])).push(fn); return this; },
    start,
    fireSensor,
    runAiCycle,
    get aiState() { return aiState; },
    data: { dayLabels, sleep, mood, focus, steps, projects },
    metrics, metHist, sensors, aiHistory,
    model: 'qwen2.5:14b',
    embedModel: 'bge-m3',
  };

  // Scale-to-fit Helfer: ein 1920×1080 #stage füllt jeden Viewport/iframe.
  global.fitStage = function (sel) {
    const stage = document.querySelector(sel || '#stage');
    if (!stage) return;
    function fit() {
      const s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
      stage.style.transform = 'translate(-50%,-50%) scale(' + s + ')';
    }
    fit(); window.addEventListener('resize', fit);
  };
})(window);
