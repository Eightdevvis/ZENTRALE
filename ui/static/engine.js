/* ============================================================================
   ZENTRALE — Live-Daten-Adapter (engine.js)
   ----------------------------------------------------------------------------
   Das ist die ECHTE Variante der ehemaligen Simulations-Engine. Sie bietet
   nach außen dieselbe `ZS`-Pub/Sub-API an, die das Monolith-Design konsumiert
   (on/start, Events tick/sensor/log/net/ai/history/status) — speist sie aber
   aus den realen Flask-Endpoints statt aus Zufallszahlen:

     GET /api/state        (1 s)  → sensors, logs, internet_logs   (Haupt-State)
     GET /api/ai/status    (30 s) → Ollama erreichbar? + Modell-Name   [nur KI-Front]
     GET /api/chat/history (2.5 s)→ Konversation (für Minilog)          [nur KI-Front]

   KI-frei (window.KI_AUS === true, gesetzt vom Template aus kassette.ki_aus()):
   die beiden KI-Polls werden in start() übersprungen — laptop/tui fragen weder
   Ollama-Status noch Chat-History ab. state/telemetry laufen immer.

   Die KI-Zustände (denkt/antwortet) werden NICHT gepollt, sondern vom
   Interaktions-Layer (Chat-Senden in index.html) über ZS.setAi() gesetzt,
   während der SSE-Stream läuft.

   Bewusst framework-frei, kein Build, kein CDN — wie das restliche Projekt
   (siehe memory/dashboard.md). viz.js und ascii.js bleiben unverändert; nur
   diese Datei trägt den Unterschied Fake→Echt.

   Daten-Lücken: Panels ohne echte Quelle (Telemetrie, Tracker Gemüt/Fokus/
   Aktiv, Projekte, Lux-Wert) sind hier ABSICHTLICH leer (metrics=null,
   data.*=[]) — sie werden Stück für Stück verkabelt, sobald die Quelle
   feststeht. Nichts wird erfunden.
   ========================================================================== */
(function (global) {
  'use strict';

  // ── Pub/Sub ────────────────────────────────────────────────────────────────
  // Jeder Kanal hält eine Liste von Callbacks; emit() ruft sie der Reihe nach.
  // try/catch pro Callback: ein kaputter Abonnent legt nicht die anderen lahm.
  var subs = { log: [], net: [], sensor: [], ai: [], tick: [], history: [], status: [] };
  function emit(ch, payload) { (subs[ch] || []).forEach(function (fn) { try { fn(payload); } catch (e) { /* noop */ } }); }

  // ── Diffing-Zustand ──────────────────────────────────────────────────────
  // /api/state liefert IMMER die volle Liste der letzten Logs/Net-Zeilen.
  // Wir merken uns, wie viele wir schon emittiert haben, und feuern nur den
  // neuen Schwanz. Schrumpft die Liste (z.B. nach Backend-Neustart), Reset.
  var lastLogLen = 0, lastNetLen = 0;
  var lastSensors = {};            // name → bool, für Flanken-Erkennung
  var lastHistoryLen = -1;         // um Minilog nur bei Änderung neu zu rendern

  // ── KI-Zustand ─────────────────────────────────────────────────────────────
  var aiState = 'idle';            // 'idle' | 'thinking' | 'streaming'
  var aiHistory = [];              // [{role:'user'|'ai', text}]  (Design-Form)

  // ── Status (Header) ──────────────────────────────────────────────────────
  var model = '…';                 // Modell-Name aus /api/ai/status
  var aiAvailable = false;
  var online = false;              // true sobald internet_logs nicht leer ist (Tripwire)

  // ── Daten-Lücken: bis zur Verkabelung leer (KEINE Fake-Daten) ──────────────
  var data = { sleep: [], mood: [], focus: [], steps: [], projects: [] };
  var metrics = null;              // {cpu:{v},temp:{v},ram:{v},gpu:{v},disk:{v}} sobald /api/telemetry da ist

  // ── Helfer ─────────────────────────────────────────────────────────────────
  function hms() {
    var d = new Date();
    return [d.getHours(), d.getMinutes(), d.getSeconds()].map(function (n) { return ('0' + n).slice(-2); }).join(':');
  }
  // Backend-Log-Eintrag {text,time} → Design-Form {t,text}
  function toEntry(e) { return { t: (e && e.time) || hms(), text: (e && e.text) || '' }; }

  // Sensor-Snapshot in eine Form bringen, die das Design erwartet. Real sind
  // button/light reine Booleans; die im Mockup gezeigten Felder motion/door und
  // der Lux-Wert haben (noch) keine echte Quelle → bleiben weich/leer.
  function shapeSensors(raw) {
    raw = raw || {};
    return {
      button: { active: !!raw.button },
      light:  { active: !!raw.light },   // .value (lux) bewusst weggelassen — keine Quelle
      motion: { active: !!raw.motion },
      door:   { active: !!raw.door }
    };
  }

  // ── Poll: Haupt-State (1 s) ─────────────────────────────────────────────────
  function pollState() {
    fetch('/api/state').then(function (r) { return r.json(); }).then(function (s) {
      var d = new Date();
      // /api/state.time ist das DATUM ("06. June 2026"); die Uhrzeit bauen wir lokal.
      var date = s.time || (d.getDate() + '. ' + ['Jan','Feb','Mär','Apr','Mai','Jun','Jul','Aug','Sep','Okt','Nov','Dez'][d.getMonth()] + ' ' + d.getFullYear());
      var sensors = shapeSensors(s.sensors);

      // tick: treibt Uhr, Datum, Telemetrie-Meter, Sensoren, Uptime + Alarme.
      // alarms = offene Kalender-Warnungen (Reise-Konflikt/Absage), die das
      // Frontend als Warndreieck-Ecke im KI-Canvas rendert.
      emit('tick', { time: hms(), date: date, metrics: metrics, sensors: sensors, uptime_s: s.uptime_s, alarms: s.alarms || [] });

      // Sensor-Flanken: nur bei Wechsel ein 'sensor'-Event
      ['button', 'light', 'motion', 'door'].forEach(function (name) {
        var active = sensors[name].active;
        if (lastSensors[name] !== active) { emit('sensor', { name: name, active: active }); lastSensors[name] = active; }
      });

      // Logs (voller stdout) — nur den neuen Schwanz nachschieben
      var logs = s.logs || [];
      if (logs.length < lastLogLen) lastLogLen = 0;            // Backend neu gestartet → Reset
      for (var i = lastLogLen; i < logs.length; i++) emit('log', toEntry(logs[i]));
      lastLogLen = logs.length;

      // Internet-Tripwire — separater Kanal
      var nets = s.internet_logs || [];
      online = nets.length > 0;
      if (nets.length < lastNetLen) lastNetLen = 0;
      for (var j = lastNetLen; j < nets.length; j++) emit('net', toEntry(nets[j]));
      lastNetLen = nets.length;
    }).catch(function () { /* Backend kurz weg — nächster Tick versucht's erneut */ });
  }

  // ── Poll: Telemetrie (2 s) → PC (lokal) + Pi (vom Pi gepusht) ──────────────
  function pollTelemetry() {
    fetch('/api/telemetry').then(function (r) { return r.json(); }).then(function (t) {
      if (t && !t.error) metrics = t;   // {pc:{...}, pi:{...|leer}}
    }).catch(function () { /* ignore – nächster Tick rendert weiter '–' */ });
  }

  // ── Poll: Ollama-Status (30 s) ──────────────────────────────────────────────
  function pollStatus() {
    fetch('/api/ai/status').then(function (r) { return r.json(); }).then(function (s) {
      model = s.model || '…';
      aiAvailable = !!s.available;
      emit('status', { model: model, available: aiAvailable, online: online });
    }).catch(function () { aiAvailable = false; emit('status', { model: model, available: false, online: online }); });
  }

  // ── Poll: Chat-History (2.5 s) → Minilog ────────────────────────────────────
  // Backend-Form {role:'user'|'assistant', content} → Design-Form {role:'user'|'ai', text}.
  function pollHistory() {
    // Während die KI denkt/antwortet zeigt der Interaktions-Layer die
    // Konversation optimistisch (pushHistory/updateLastHistory) an. Das
    // Backend kennt die KI-Antwort aber erst NACH dem Stream — ein Poll
    // mittendrin würde die laufende Antwort wegwischen. Also: nur im
    // Leerlauf vom Backend re-synchronisieren.
    if (aiState !== 'idle') return;
    fetch('/api/chat/history').then(function (r) { return r.json(); }).then(function (h) {
      if (!Array.isArray(h)) return;
      // Nur neu rendern wenn sich wirklich was geändert hat (spart DOM-Arbeit)
      if (h.length === lastHistoryLen) return;
      lastHistoryLen = h.length;
      aiHistory = h.map(function (m) { return { role: m.role === 'user' ? 'user' : 'ai', text: m.content || '' }; });
      emit('history', { history: aiHistory });
    }).catch(function () { /* ignore */ });
  }

  // ── Loops ────────────────────────────────────────────────────────────────────
  var started = false;
  function start() {
    if (started) return; started = true;
    pollState();  setInterval(pollState, 1000);
    pollTelemetry(); setInterval(pollTelemetry, 2000);
    // KI-Polls nur in der KI-Front. In laptop/tui (window.KI_AUS) gibt es weder
    // Ollama-Status-Header noch Minilog → die Endpoints (503-gegatet) gar nicht
    // erst anfragen.
    if (!global.KI_AUS) {
      pollStatus(); setInterval(pollStatus, 30000);
      pollHistory(); setInterval(pollHistory, 2500);
    }
  }

  // ── Öffentliche API ────────────────────────────────────────────────────────
  global.ZS = {
    on: function (ch, fn) { (subs[ch] || (subs[ch] = [])).push(fn); return this; },
    start: start,

    // Vom Interaktions-Layer (Chat-Senden) aufgerufen, um den KI-Zustand zu
    // setzen, während der SSE-Stream läuft. 'thinking' beim Absenden,
    // 'streaming' sobald Tokens kommen, 'idle' am Ende.
    setAi: function (state) { aiState = state; emit('ai', { state: state }); },

    // Optimistisch eine Zeile in die lokale History schieben (sofortige
    // Minilog-Anzeige, bevor der nächste pollHistory()-Tick sie bestätigt).
    pushHistory: function (role, text) {
      aiHistory.push({ role: role === 'user' ? 'user' : 'ai', text: text || '' });
      lastHistoryLen = -1;                 // nächsten Poll zum Re-Sync zwingen
      emit('history', { history: aiHistory });
    },
    // Letzten (KI-)History-Eintrag live aktualisieren, während Tokens streamen.
    updateLastHistory: function (text) {
      if (aiHistory.length) { aiHistory[aiHistory.length - 1].text = text; emit('history', { history: aiHistory }); }
    },

    get aiState() { return aiState; },
    get aiHistory() { return aiHistory; },
    get model() { return model; },
    get online() { return online; },
    data: data,        // leer bis Verkabelung
    metrics: metrics   // null bis /api/telemetry
  };

  // ── Scale-to-fit: 1920×1080-#stage füllt jeden Viewport/Kiosk-Screen ─────────
  global.fitStage = function (sel) {
    var stage = document.querySelector(sel || '#stage');
    if (!stage) return;
    function fit() {
      var s = Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
      stage.style.transform = 'translate(-50%,-50%) scale(' + s + ')';
    }
    fit(); window.addEventListener('resize', fit);
  };
})(window);
