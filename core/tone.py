# core/tone.py
# Ton-Erzeugung für das Klavier-Werkzeug der TUI-Kassette.
#
# Der Browser macht seinen Ton mit der WebAudio-API (Oszillator + Hüllkurve,
# siehe ui/templates/monolith.html). Die TUI hat kein WebAudio — sie rechnet
# die Wellenform selbst und schiebt sie über sounddevice an die Soundkarte.
# Beides bleibt bewusst SYNTHETISCH: kein Sample, kein Download, keine
# Bibliothek mit Klangdateien → läuft offline auf Pi und PC.
#
# Zwei Ebenen, damit sich das Klangliche ohne Soundkarte prüfen lässt:
#   Voice  – reine Rechnung (Halbton → Wellenform-Block). Braucht nur numpy,
#            kein Gerät; genau das testen tests/test_tone.py.
#   Synth  – hält den sounddevice-Ausgabestrom offen und mischt die klingenden
#            Voices im Audio-Callback zusammen (Polyphonie = Akkorde).
#
# WICHTIG — warum ein Anschlag eine FESTE Länge hat: das Terminal meldet nur
# Tastendrücke, kein Loslassen (curses kennt kein key-up). Die TUI kann eine
# Haltedauer also gar nicht messen. Darum klingt jeder Anschlag wie am echten
# Klavier von selbst aus (Abklingen über DEFAULT_DUR_MS). Melodien AUS DEM
# BROWSER tragen ihre echten Haltedauern (d in ms) — die spielt play_sequence
# genau so ab, jede Note mit ihrer eigenen Länge.
#
# Fehlt sounddevice oder gibt es kein Ausgabegerät (headless, Pi ohne Audio),
# bleibt alles still und meldet das nach oben (available()/Synth.start() ->
# False) — das Klavier funktioniert dann stumm weiter (Noten + Aufnahme).

import os
import threading
import time

SAMPLERATE = 44100
BLOCKSIZE = 256              # ~6 ms Latenz — klein genug, dass Spielen sich direkt anfühlt
DEFAULT_DUR_MS = 420         # Länge eines Anschlags (Terminal kennt kein Loslassen)
MAX_VOICES = 24              # Deckel: mehr gleichzeitig klingende Töne bringt nur Matsch
MASTER_GAIN = 0.22           # Kopfraum, damit ein voller Akkord nicht übersteuert
ATTACK_S = 0.006             # Anschlag-Rampe (ohne sie knackst der Einsatz)

# Teiltöne eines angeschlagenen Saitentons: Grundton + abfallende Obertöne.
# Reiner Sinus klingt nach Testton, Sägezahn nach Synthesizer — diese Mischung
# liegt dazwischen und trägt auf kleinen Lautsprechern.
HARMONICS = ((1.0, 1.0), (2.0, 0.38), (3.0, 0.16), (4.0, 0.07), (5.0, 0.03))


def midi_to_freq(n):
    """MIDI-Notennummer → Frequenz in Hz (69 = a' = 440 Hz)."""
    return 440.0 * (2.0 ** ((float(n) - 69.0) / 12.0))


def _numpy():
    """numpy nachladen (None, wenn es fehlt) — der Import kostet, also erst
    beim ersten Ton und nicht schon beim Start der TUI."""
    try:
        import numpy
        return numpy
    except Exception:
        return None


def _device_from_env():
    """ZENTRALE_AUDIO_DEVICE auswerten: Zahl → Geräte-Index, Text → Gerätename,
    leer → None (System-Default)."""
    raw = (os.environ.get("ZENTRALE_AUDIO_DEVICE") or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return raw


def available():
    """Kann diese Maschine überhaupt Ton machen? (numpy + sounddevice da).
    Ob ein Gerät wirklich aufgeht, zeigt erst Synth.start()."""
    if _numpy() is None:
        return False
    try:
        import sounddevice  # noqa: F401
        return True
    except Exception:
        return False


class Voice:
    """Ein klingender Ton. Rechnet seine Wellenform blockweise und ADDIERT sie
    in den übergebenen Puffer (mehrere Voices = Akkord).

    Die Hüllkurve ist die eines angeschlagenen Klaviertons: kurze Rampe hoch,
    dann exponentielles Abklingen. dur_ms steuert, wie schnell abgeklungen
    wird — eine lang gehaltene Browser-Note klingt also wirklich länger.
    """

    def __init__(self, midi, dur_ms=DEFAULT_DUR_MS, gain=1.0, samplerate=SAMPLERATE):
        self.midi = int(midi)
        self.freq = midi_to_freq(self.midi)
        self.gain = float(gain)
        self.sr = int(samplerate)
        dur = max(0.02, float(dur_ms) / 1000.0)
        # Zeitkonstante so, dass der Ton am Ende von dur auf ~5 % gefallen ist.
        self.tau = dur / 3.0
        # Danach noch ein Stück ausklingen lassen, sonst bricht der Ton hörbar ab.
        self.life = int(self.sr * dur * 1.6)
        self.pos = 0
        self.done = False
        # Nur Teiltöne unter der Nyquist-Grenze — höhere würden als
        # Alias-Pfeifen zurückfalten.
        self.parts = [(m, a) for m, a in HARMONICS if self.freq * m < self.sr * 0.45]

    def render(self, out, np):
        """Nächsten Block in out addieren (out: 1-D float-Array). Setzt done,
        sobald der Ton verklungen ist."""
        n = len(out)
        if n <= 0 or self.done:
            return
        i = np.arange(self.pos, self.pos + n, dtype=np.float64)
        t = i / float(self.sr)
        env = np.exp(-t / self.tau)
        att = max(1.0, ATTACK_S * self.sr)
        if self.pos < att:                       # Einsatz weich anrampen
            env = env * np.minimum(1.0, i / att)
        sig = np.zeros(n, dtype=np.float64)
        two_pi_t = (2.0 * np.pi) * t
        for mult, amp in self.parts:
            sig += amp * np.sin(two_pi_t * (self.freq * mult))
        out += (self.gain * env * sig).astype(out.dtype)
        self.pos += n
        if self.pos >= self.life:
            self.done = True


class Synth:
    """Offener Ausgabestrom + die gerade klingenden Voices.

    Der Strom bleibt offen, solange das Klavier-Panel offen ist: ihn pro Ton
    auf- und zuzumachen kostet auf dem Pi zu viel (hörbare Verzögerung beim
    ersten Anschlag). Gemischt wird im Audio-Callback von sounddevice, also in
    EINEM eigenen Thread — die Zeichenschleife der TUI bleibt davon unberührt.
    """

    def __init__(self, samplerate=SAMPLERATE, blocksize=BLOCKSIZE, gain=MASTER_GAIN,
                 device=None):
        self.sr = int(samplerate)
        self.blocksize = int(blocksize)
        self.gain = float(gain)
        # Welches Ausgabegerät? Normalerweise das Default des Systems. Auf
        # Knoten, deren Default über einen NICHT erreichbaren Audio-Server läuft
        # (z.B. PipeWire ohne Session), BLOCKIERT PortAudio beim Öffnen — dann
        # hilft ZENTRALE_AUDIO_DEVICE mit Index ('0') oder Name ('hw:0,0'),
        # um direkt auf die Karte zu gehen.
        self.device = device if device is not None else _device_from_env()
        self._np = None
        self._stream = None
        self._voices = []
        self._lock = threading.Lock()
        self.error = ""            # warum es still bleibt (für die Statuszeile)

    # ── Gerät ──────────────────────────────────────────────────────────
    def start(self):
        """Ausgabestrom öffnen. True = es kann klingen, False = still (self.error
        sagt warum). Mehrfach aufrufbar."""
        if self._stream is not None:
            return True
        self._np = _numpy()
        if self._np is None:
            self.error = "numpy fehlt"
            return False
        try:
            import sounddevice as sd
        except Exception:
            self.error = "sounddevice fehlt"
            return False
        try:
            self._stream = sd.OutputStream(
                samplerate=self.sr, channels=1, dtype="float32",
                blocksize=self.blocksize, callback=self._callback,
                device=self.device)
            self._stream.start()
        except Exception as e:                   # kein Gerät (headless/Pi ohne Audio)
            self._stream = None
            self.error = "kein audio-gerät (%s)" % type(e).__name__
            return False
        self.error = ""
        return True

    def close(self):
        """Strom schließen und alles Klingende verwerfen."""
        self.silence()
        st, self._stream = self._stream, None
        if st is not None:
            try:
                st.stop(); st.close()
            except Exception:
                pass

    # ── Spielen ────────────────────────────────────────────────────────
    def strike(self, midi, dur_ms=DEFAULT_DUR_MS, gain=1.0):
        """Einen Ton anschlagen. Still (und harmlos), wenn kein Gerät offen ist."""
        if self._stream is None or self._np is None:
            return False
        v = Voice(midi, dur_ms=dur_ms, gain=gain, samplerate=self.sr)
        with self._lock:
            # Ältestes opfern, wenn zu viel gleichzeitig klingt.
            if len(self._voices) >= MAX_VOICES:
                del self._voices[0:len(self._voices) - MAX_VOICES + 1]
            self._voices.append(v)
        return True

    def silence(self):
        """Alles sofort verstummen lassen (Panel zu, Wiedergabe abgebrochen)."""
        with self._lock:
            self._voices = []

    def _callback(self, outdata, frames, time_info, status):
        """sounddevice-Callback: alle klingenden Voices in EINEN Block mischen.
        Läuft im Audio-Thread — darf nie werfen, sonst reißt der Strom ab."""
        np = self._np
        try:
            buf = np.zeros(frames, dtype=np.float32)
            with self._lock:
                voices = list(self._voices)
            for v in voices:
                v.render(buf, np)
            done = [v for v in voices if v.done]
            if done:
                with self._lock:
                    self._voices = [v for v in self._voices if not v.done]
            # Summe begrenzen: lieber leiser als ein knackender Übersteuerer.
            np.clip(buf * self.gain, -1.0, 1.0, out=buf)
            outdata[:, 0] = buf
        except Exception:
            try:
                outdata.fill(0)
            except Exception:
                pass


class Playback:
    """Eine Melodie abspielen: schlägt ihre Noten zu ihren Startzeiten an.

    Läuft in einem eigenen Thread (die Zeichenschleife darf nicht schlafen).
    on_note(midi, dur_ms) meldet jeden Anschlag zurück — die TUI leuchtet damit
    die Taste auf und schreibt die Note ins Notensystem.
    """

    def __init__(self, synth, notes, on_note=None, on_done=None):
        self.synth = synth
        self.notes = sorted(
            [e for e in (notes or []) if isinstance(e, dict) and e.get("n") is not None],
            key=lambda e: (int(e.get("t", 0)), int(e.get("n", 0))))
        self.on_note = on_note
        self.on_done = on_done
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        t0 = time.time()
        try:
            for e in self.notes:
                if self._stop.is_set():
                    break
                start = int(e.get("t", 0)) / 1000.0
                wait = t0 + start - time.time()
                if wait > 0 and self._stop.wait(wait):
                    break
                dur = int(e.get("d", DEFAULT_DUR_MS) or DEFAULT_DUR_MS)
                n = int(e.get("n", 60))
                self.synth.strike(n, dur_ms=dur)
                if self.on_note:
                    try:
                        self.on_note(n, dur)
                    except Exception:
                        pass
        finally:
            if self.on_done:
                try:
                    self.on_done()
                except Exception:
                    pass


def play_sequence(synth, notes, on_note=None, on_done=None):
    """Bequemer Einzeiler: Melodie abspielen, Handle zum Abbrechen zurück."""
    return Playback(synth, notes, on_note=on_note, on_done=on_done).start()
