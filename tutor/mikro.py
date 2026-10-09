# tutor/mikro.py
#
# Das Ohr des Zimmers: Dauer-Mikro → Äußerungen (WAV) + Geräusch-Signal.
#
# Bis 2026-10-08 stand das als listen_loop mitten in room.main() (einer der
# Riesen aus memory/system/bauplan_kern.md). Rausgezogen, weil
#   1. es Schritt 1 der Audio-Straße ist (memory/system/audio_strasse.md:
#      „listen_loop … in ein eigenes, projektfreies Modul"),
#   2. die Zählerei (wann ist eine Äußerung fertig, was ist Geräusch) ohne
#      Hardware testbar sein soll — `Ohr` kriegt Frames und sagt, was passiert;
#      tests/test_tutor_mikro.py füttert es mit künstlichen Frames,
#   3. die Zimmer-Tests (tests/test_tutor_room_flows.py) wackelten: das Zimmer
#      öffnete das ECHTE Mikro auch mit --no-mic, und PortAudio riss den
#      Prozess beim Beenden mit einem Speicherzugriffsfehler (SIGSEGV) ab —
#      manchmal, bevor die Ausgabe geschrieben war. Jetzt wird das Mikro erst
#      geöffnet, wenn das Zuhören an ist, und beim Beenden sauber geschlossen.
#
# Verhalten unverändert gegenüber room.py (Schwellen, Gate, Grundrauschen).
# Wie room.py: nur stdlib + sounddevice/webrtcvad, nichts aus dem Projekt —
# das Modul fährt im Aussenposten-Paket mit (deploy/aussenposten.txt).

import array
import io
import math
import sys
import time
import wave

MIC_RATE          = 16000  # Hz (webrtcvad kann 8/16/32k)
MIC_FRAME_MS      = 20      # ms pro VAD-Frame
MIC_VAD_AGGR      = 3       # 0..3 (höher = strenger, weniger Fehl-Trigger) — bei
                            # hohem USB-Pegel hielt Stufe 2 Rauschen für Stimme.
                            # ⚠ Diagnose 2026-10-08: Stufe 3 verschluckt auch leise
                            # / zögernde Lerner-Sprache (memory/tutor/diagnose_2026-10-08.md)
MIC_SILENCE_MS    = 700     # Pause nach Sprache → Äußerung fertig
MIC_MINSPEECH_MS  = 300     # kürzere „Äußerungen" verwerfen (Blips/Husten)
MIC_MAX_MS        = 12000   # harte Obergrenze pro Äußerung
PRES_NOISE_K      = 5.0     # Pegel > k × Grundrauschen = Geräusch
PRES_NOISE_MIN    = 400     # ... und mindestens so laut (RMS, int16) — ein leiser
                            # Raum hat ein winziges Grundrauschen, dann wäre k×floor
                            # fast nichts und das Nebenzimmer zählte mit
PRES_NOISE_MS     = 400     # so lange muss der Pegel oben bleiben (kein Knacks)


def pcm_to_wav(pcm_bytes, rate=MIC_RATE):
    """Rohe int16-mono-Frames → WAV-Bytes (für /api/transcribe)."""
    bio = io.BytesIO()
    with wave.open(bio, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm_bytes)
    return bio.getvalue()


def rms_von(frame: bytes) -> float:
    a = array.array('h', frame)
    return math.sqrt(sum(x * x for x in a) / len(a)) if len(a) else 0.0


class Ohr:
    """Zustand des Zuhörens, ohne Hardware. `frame()` bekommt einen Frame,
    ob der VAD ihn für Sprache hält und ob gerade Musik läuft, und gibt eine
    Liste von Ereignissen zurück:
      ('hoert', bool)      Sprache beginnt/endet (fürs HUD)
      ('geraeusch', floor) lauter als das Grundrauschen, lang genug
      ('aeusserung', pcm)  fertige Äußerung → an Whisper
    """

    def __init__(self):
        self.buf = []; self.in_speech = False; self.silence = 0; self.speech = 0
        self.floor = 0.0; self.loud_ms = 0

    def zuruecksetzen(self):
        """Gate (sie spricht/antwortet) oder Mikro aus: angefangene Äußerung weg."""
        war = self.in_speech or bool(self.buf)
        self.buf, self.in_speech, self.silence, self.speech = [], False, 0, 0
        return [('hoert', False)] if war else []

    def frame(self, frame: bytes, is_sp: bool, musik: bool = False, rms=None):
        ev = []
        if rms is None:
            rms = rms_von(frame)
        if self.floor <= 0.0:
            self.floor = max(rms, 1.0)
        # Geräusch: Pegel gegen ein langsam mitlaufendes Grundrauschen. Läuft
        # Musik aus dem eigenen Lautsprecher, zählt nur Sprache.
        laut = (not musik) and rms > PRES_NOISE_K * self.floor and rms > PRES_NOISE_MIN
        self.loud_ms = self.loud_ms + MIC_FRAME_MS if laut else 0
        # Der Boden lernt NUR aus stillen Frames — sonst zieht ein Gespräch ihn
        # auf Sprachpegel hoch (gesehen: floor 1556) und danach ist nichts mehr
        # „laut". Runter geht es schnell, rauf nur langsam.
        if not is_sp and not laut:
            if rms < self.floor:
                self.floor = self.floor * 0.9 + rms * 0.1
            else:
                self.floor = self.floor * 0.995 + rms * 0.005
        if self.loud_ms >= PRES_NOISE_MS:
            ev.append(('geraeusch', self.floor))
        if is_sp:
            if not self.in_speech:
                ev.append(('hoert', True))
            self.buf.append(frame); self.in_speech = True
            self.speech += MIC_FRAME_MS; self.silence = 0
        elif self.in_speech:
            self.buf.append(frame); self.silence += MIC_FRAME_MS
            if self.silence >= MIC_SILENCE_MS:
                ev.append(('hoert', False))
                if self.speech >= MIC_MINSPEECH_MS:
                    ev.append(('aeusserung', b''.join(self.buf)))
                self.buf, self.in_speech, self.silence, self.speech = [], False, 0, 0
        if (self.speech + self.silence) >= MIC_MAX_MS:      # harte Obergrenze
            if self.speech >= MIC_MINSPEECH_MS:
                ev.append(('aeusserung', b''.join(self.buf)))
            self.buf, self.in_speech, self.silence, self.speech = [], False, 0, 0
            ev.append(('hoert', False))
        return ev


def hoeren(S, aeusserung, jetzt_ms):
    """Die Schleife des Zimmers (eigener Thread). S: der Zustand des Zimmers
    (mit S['lock']). aeusserung(wav_bytes): fertige Äußerung → Whisper.
    jetzt_ms(): Uhr des Zimmers (pygame-Ticks).

    Das Mikro wird erst geöffnet, wenn S['mic'] an ist (vorher: immer, auch
    mit --no-mic), und geschlossen, sobald S['ende'] gesetzt ist."""
    try:
        import sounddevice as sd
        import webrtcvad
    except Exception:
        with S['lock']:
            S['mic'] = False; S['mic_err'] = 'STT-Libs fehlen (pip install)'
        return
    while True:                       # warten, bis Zuhören überhaupt an ist
        with S['lock']:
            if S.get('ende'):
                return
            an = S['mic']
        if an:
            break
        time.sleep(0.2)
    n = int(MIC_RATE * MIC_FRAME_MS / 1000)   # samples/Frame
    try:
        vad = webrtcvad.Vad(MIC_VAD_AGGR)
        stream = sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype='int16', blocksize=n)
        stream.start()
    except Exception:
        with S['lock']:
            S['mic'] = False; S['mic_err'] = 'kein Mikrofon'
        return
    ohr = Ohr()
    log_ms = 0
    try:
        while True:
            with S['lock']:
                if S.get('ende'):
                    return
                on = S['mic'] and not S['pause'] and S['pmenu'] is None
                gated = S['speaking'] or S['busy'] or S['streaming']
                musik = S['music'] is not None
            try:
                data, _ = stream.read(n)
            except Exception:
                time.sleep(0.02); continue
            if (not on) or gated:
                if ohr.zuruecksetzen():
                    with S['lock']: S['hearing'] = False
                continue
            frame = bytes(data)
            if len(frame) < n * 2:
                continue
            try:
                is_sp = vad.is_speech(frame, MIC_RATE)
            except Exception:
                continue
            for art, wert in ohr.frame(frame, is_sp, musik):
                if art == 'hoert':
                    with S['lock']: S['hearing'] = wert
                elif art == 'geraeusch':
                    # Anwesenheit aus GERÄUSCH hier; aus SPRACHE erst, wenn
                    # Whisper echte Wörter daraus gemacht hat (room.py).
                    jetzt = jetzt_ms()
                    with S['lock']:
                        S['activity_ms'] = jetzt; S['noise_floor'] = wert
                    if jetzt - log_ms > 10000:
                        log_ms = jetzt
                        print(f"[mikro] aktiv: geräusch floor={wert:.0f}",
                              file=sys.stderr, flush=True)
                elif art == 'aeusserung':
                    aeusserung(pcm_to_wav(wert))
    finally:
        try:
            stream.stop(); stream.close()
        except Exception:
            pass
