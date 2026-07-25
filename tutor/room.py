#!/usr/bin/env python3
# tutor/room.py
#
# Natives Zimmer-Fenster (pygame) für die Sprach-Tutor-Persona (Ling Ling & Co).
# Der Tutor ist keine Chat-Box, sondern eine Person — hier WOHNT sie: ein
# gezeichnetes Wohnzimmer, in dem die Persona rumläuft, auf der Couch sitzt und
# mit dir quatscht. Gleiches Prinzip wie scripts/map_window.py: ein zweites
# X11-Fenster, das aus der TUI heraus aufklappt (Taste/Command im Tutor-Panel),
# echte antialiased Vektorgrafik statt curses.
#
# Architektur = Kassetten-Prinzip: dieses File ZEICHNET nur + spricht die
# Tutor-API. Keine KI-Logik hier — Session/Sprache/Persona/Memory leben im
# Backend (tutor/session.py, /api/tutor/*). Die Antworten kommen als SSE-
# Token-Stream (wie im Browser/TUI), landen in einer Sprechblase.
#
# Start:
#   venv/bin/python tutor/room.py [--url http://host:5000]
#
# Steuerung:
#   tippen + Enter   an die Persona reden
#   Backspace        löschen
#   Esc              Fenster schließen
#
# Braucht DISPLAY (X11) + pygame im venv. CJK-Font: notosanscjksc (Noto Sans CJK).

import os
import sys
import io
import re
import wave
import json
import math
import random
import argparse
import threading
import urllib.request
import urllib.error

import pygame

# ── Palette (warmes Wohnzimmer — bewusst anders als die Karte) ───────────────
WALL_TOP   = (58, 47, 62)      # Wand oben (gedämpftes Aubergine)
WALL_BOT   = (74, 60, 74)      # Wand unten, minimal heller
FLOOR_TOP  = (92, 66, 48)      # Dielenboden hinten
FLOOR_BOT  = (66, 46, 33)      # Boden vorne (dunkler)
RUG        = (140, 74, 66)     # Teppich (Terrakotta)
RUG_RING   = (176, 104, 92)    # Teppich-Rand
COUCH      = (92, 108, 120)    # Couch (staubiges Blau)
COUCH_DK   = (70, 84, 96)      # Couch-Schatten
COUCH_LT   = (116, 134, 148)   # Couch-Highlight
WINDOW_SKY = (36, 52, 82)      # Nachthimmel im Fenster
WINDOW_FR  = (150, 132, 120)   # Fensterrahmen
MOON       = (226, 224, 198)   # Mond
PLANT      = (78, 120, 70)     # Pflanze
POT        = (150, 92, 62)     # Blumentopf
LAMP_GLOW  = (255, 224, 150)   # Lampenlicht
# Persona
SKIN       = (240, 206, 178)
HAIR       = (44, 34, 40)
DRESS      = (196, 74, 74)     # Ling Lings warmes Rot
DRESS_DK   = (156, 54, 54)
LIMB       = (232, 196, 168)
# UI
BUBBLE_BG  = (250, 248, 240)
BUBBLE_FG  = (32, 28, 30)
BUBBLE_BD  = (210, 205, 194)
HUD_FG     = (206, 194, 200)
HUD_DIM    = (150, 138, 146)
INPUT_BG   = (40, 33, 42)
INPUT_FG   = (238, 232, 236)
CARET      = (226, 150, 150)
# Verlaufs-Leiste + Rollen
BAR_BG     = (16, 12, 20, 214)   # translucentes Panel unten
ROLE_USER  = (150, 200, 230)     # Sasha (kühl)
ROLE_TUTOR = (240, 202, 172)     # Persona (warm)
BAR_DIM    = (128, 118, 128)
# Gesagtes „verhallt": Blase steht kurz voll, dann blendet sie aus.
BUBBLE_LINGER = 4.0   # s voll sichtbar nach dem Sprechen
BUBBLE_FADE   = 1.3   # s Ausblenden danach
# Gedanken-Blase (Vokabel-Hilfe: Wort + Übersetzung, optional Bild)
THOUGHT_BG  = (240, 242, 250)
THOUGHT_FG  = (40, 44, 60)
THOUGHT_SUB = (96, 102, 128)
THOUGHT_TTL = 6.0     # s sichtbar, dann aus
_VOCAB_IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'vocab_images')
_img_cache = {}


def _vocab_image(word):
    """Bild zu einem Wort aus data/vocab_images/<wort>.png (falls vorhanden),
    gecacht. Kein Bild → None (dann nur Wort+Übersetzung)."""
    if word in _img_cache:
        return _img_cache[word]
    img = None
    try:
        p = os.path.join(_VOCAB_IMG_DIR, word + '.png')
        if os.path.exists(p):
            img = pygame.image.load(p).convert_alpha()
    except Exception:
        img = None
    _img_cache[word] = img
    return img


def draw_thought(surf, font, small, word, meaning, cx, top_y, alpha=255):
    """Gedanken-Blase (heller als die Sprechblase, mit kleinen Trail-Kringeln)
    über/neben dem Kopf: optional Bild, dann Wort (Zielsprache), dann Übersetzung."""
    if not word or alpha <= 0:
        return
    img = _vocab_image(word)
    iw = ih = 0
    if img:
        iw = min(80, img.get_width())
        ih = int(img.get_height() * (iw / img.get_width())) if img.get_width() else 0
    w_word = font.render(word, True, THOUGHT_FG)
    w_mean = small.render(meaning, True, THOUGHT_SUB) if meaning else None
    cw = max(iw, w_word.get_width(), (w_mean.get_width() if w_mean else 0)) + 26
    ch = 12 + (ih + 6 if ih else 0) + w_word.get_height() + (w_mean.get_height() + 4 if w_mean else 0) + 10
    # Entzerrt neben dem Kopf (links, auf Kopf-Höhe abwärts): die Sprechblase
    # sitzt MITTIG ÜBER dem Kopf. Verankert man die Gedanken-Blase mit ihrer
    # OBERKANTE knapp unter der Kopf-Oberkante, liegen beide garantiert in
    # getrennten vertikalen Bändern und können sich NIE überlappen — egal wie
    # breit die Sprechblase gerade ist. Trail-Kringel zeigen nach rechts → Kopf.
    trail = 16
    bx = max(8, int(cx - cw - 28))    # rechte Kante ~28px links vom Kopf (Lücke)
    by = max(8, int(top_y + 6))       # Oberkante unter der Sprechblasen-Unterkante
    tmp = pygame.Surface((cw + trail, ch), pygame.SRCALPHA)
    pygame.draw.rect(tmp, THOUGHT_BG, (0, 0, cw, ch), border_radius=16)
    y = 10
    if img:
        tmp.blit(pygame.transform.smoothscale(img, (iw, ih)), ((cw - iw) // 2, y)); y += ih + 6
    tmp.blit(w_word, ((cw - w_word.get_width()) // 2, y)); y += w_word.get_height() + 3
    if w_mean:
        tmp.blit(w_mean, ((cw - w_mean.get_width()) // 2, y))
    pygame.draw.circle(tmp, THOUGHT_BG, (cw + 3, 15), 5)   # Trail nach rechts → Kopf
    pygame.draw.circle(tmp, THOUGHT_BG, (cw + 11, 6), 3)
    if alpha < 255:
        tmp.set_alpha(alpha)
    surf.blit(tmp, (bx, by))
# Feedback-Loop (gedeckelt, damit die Cloud-Kosten winzig bleiben): nach kurzer
# Stille EIN Anstoß (die KI schaut/winkt/fragt), danach chillt sie — client-
# seitig, kostenlos. Bleibt das Fenster offen, alle ~15 min ein neuer Versuch.
NUDGE_AFTER_S   = 90.0    # s Stille bis zum ersten Anstoß (war 25 = Spam; sie lebt
                          # lieber in ihrem Zimmer weiter, als dich ständig anzuquatschen)
CHILL_RECHECK_S = 900.0   # s (15 min) bis zum nächsten Versuch
# Immer-Zuhören (STT): Mikro im Fenster, webrtcvad segmentiert Sprache, das Mikro
# ist gegated während die Persona spricht (sonst hört sie sich selbst zu).
MIC_RATE          = 16000  # Hz (webrtcvad kann 8/16/32k)
MIC_FRAME_MS      = 20      # ms pro VAD-Frame
MIC_VAD_AGGR      = 2       # 0..3 (höher = strenger, weniger Fehl-Trigger)
MIC_SILENCE_MS    = 700     # Pause nach Sprache → Äußerung fertig
MIC_MINSPEECH_MS  = 300     # kürzere „Äußerungen" verwerfen (Blips/Husten)
MIC_MAX_MS        = 12000   # harte Obergrenze pro Äußerung


def _font(size, bold=False):
    """CJK-fähige Schrift (Noto Sans CJK), Fallback auf Default. Sasha-Text ist
    Chinesisch — ohne CJK-Font kämen Kästchen."""
    f = pygame.font.SysFont("notosanscjksc,notosansmonocjksc,droidsansfallback,dejavusans", size, bold=bold)
    return f or pygame.font.Font(None, size)


# ── Backend (Tutor-API, dumm & robust) ───────────────────────────────────────
class Backend:
    def __init__(self, url):
        self.url = url.rstrip('/')

    def _get(self, path, timeout=3.0):
        try:
            with urllib.request.urlopen(self.url + path, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return None

    def status(self):
        return self._get('/api/tutor/status')

    def config(self):
        return self._get('/api/tutor/config')

    def room_state(self):
        return self._get('/api/tutor/room_state', timeout=2.0)

    def set_config(self, changes):
        """POST /api/tutor/config (JSON, KEIN SSE) → aufgelöste Config oder None.
        Für den Live-Sprachwechsel aus dem Zimmer (Sprache/Provider umstellen)."""
        try:
            req = urllib.request.Request(
                self.url + '/api/tutor/config',
                data=json.dumps(changes).encode('utf-8'), method='POST',
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return None

    def assessment(self):
        """GET /api/tutor/assessment → Kern-Wörter + Lernstand fürs Drill
        (deterministisch, kein LLM). None bei Fehler."""
        return self._get('/api/tutor/assessment', timeout=5.0)

    def answer(self, word, result):
        """POST /api/tutor/assessment/answer {word, result} → neuer Stand."""
        try:
            req = urllib.request.Request(
                self.url + '/api/tutor/assessment/answer',
                data=json.dumps({'word': word, 'result': result}).encode('utf-8'),
                method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=6) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return None

    def stop(self):
        """POST /api/tutor/stop — laufende Session beenden (vor dem Sprachwechsel,
        damit die neue Persona in der neuen Sprache frisch begrüßt)."""
        try:
            req = urllib.request.Request(
                self.url + '/api/tutor/stop', data=b'{}', method='POST',
                headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass

    def transcribe(self, wav_bytes, lang):
        """WAV → (Text, Fehler). Fehler ist None bei Erfolg, sonst ein kurzer
        Grund (damit das Fenster nicht mehr STILL scheitert)."""
        boundary, body = _multipart_audio({'lang': lang or 'zh'}, wav_bytes)
        req = urllib.request.Request(
            self.url + '/api/transcribe', data=body, method='POST',
            headers={'Content-Type': 'multipart/form-data; boundary=' + boundary})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.loads(r.read().decode('utf-8', 'replace'))
                return (d.get('text') or '').strip(), None
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode('utf-8', 'replace')).get('error') or ('HTTP %s' % e.code)
            except Exception:
                msg = 'HTTP %s' % e.code
            return '', msg
        except (urllib.error.URLError, OSError):
            return '', 'backend nicht erreichbar'
        except Exception:
            return '', 'STT-fehler'

    def speak(self, text, lang, speaker, speed):
        """Text → WAV-Bytes (Backend-TTS, /api/speak). None bei Fehler/503
        (z.B. Modell fehlt oder KI gedrosselt) — dann bleibt die Persona stumm."""
        if not text:
            return None
        body = json.dumps({'text': text, 'lang': lang,
                           'speaker': speaker, 'speed': speed}).encode('utf-8')
        req = urllib.request.Request(
            self.url + '/api/speak', data=body, method='POST',
            headers={'Content-Type': 'application/json', 'Accept': 'audio/wav'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                if r.headers.get('Content-Type', '').startswith('audio'):
                    return r.read()
                return None
        except Exception:
            return None

    def stream(self, path, payload, on_token):
        """POST + SSE lesen (wie die TUI): 'data: {token|done}'. Gibt einen
        Fehlerstring zurück (oder None bei Erfolg)."""
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            self.url + path, data=data, method='POST',
            headers={'Content-Type': 'application/json',
                     'Accept': 'text/event-stream'})
        resp = None
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            for raw in resp:
                line = raw.decode('utf-8', 'replace').rstrip('\r\n')
                if not line.startswith('data:'):
                    continue
                try:
                    evt = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if 'token' in evt:
                    on_token(str(evt['token']))
                elif 'done' in evt:
                    break
            return None
        except urllib.error.HTTPError as e:
            return ('backend gedrosselt? /cloud on' if e.code == 503
                    else 'fehler HTTP %s' % e.code)
        except (urllib.error.URLError, OSError):
            return 'keine verbindung (backend an?)'
        finally:
            if resp is not None:
                try: resp.close()
                except OSError: pass


# ── Mikro/STT-Helfer ─────────────────────────────────────────────────────────
def _pcm_to_wav(pcm_bytes, rate=MIC_RATE):
    """Rohe int16-mono-Frames → WAV-Bytes (für /api/transcribe)."""
    bio = io.BytesIO()
    with wave.open(bio, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(pcm_bytes)
    return bio.getvalue()


def _multipart_audio(fields, wav_bytes):
    """Minimaler multipart/form-data-Body (audio-Datei + Felder) — ohne requests,
    passend zu /api/transcribe."""
    boundary = '----zroom' + format(len(wav_bytes), 'x')
    parts = []
    for k, v in fields.items():
        parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                      % (boundary, k, v)).encode('utf-8'))
    parts.append(('--%s\r\nContent-Disposition: form-data; name="audio"; '
                  'filename="speech.wav"\r\nContent-Type: audio/wav\r\n\r\n' % boundary).encode('utf-8'))
    parts.append(wav_bytes)
    parts.append(b'\r\n')
    parts.append(('--%s--\r\n' % boundary).encode('utf-8'))
    return boundary, b''.join(parts)


# ── Stimme: WAV vom Backend abspielen ────────────────────────────────────────
_mixer_lock = threading.Lock()


# ── Hintergrund-Musik (Feature 7) ────────────────────────────────────────────
# Die Persona legt Musik nach Stimmung auf (mixer.music-Stream, resampelt anders
# als mixer.Sound automatisch auf die Mixer-Rate). Bibliothek nach Stimmung:
# data/persona_music/<mood>/*.{ogg,mp3,wav}. KEIN Audio mitgeliefert (Lizenz) →
# Content-Lücke; sobald Dateien drin sind, läuft es. Während sie SPRICHT wird die
# Musik geduckt (leiser), nicht gestoppt.
MUSIC_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'persona_music')
MUSIC_VOLUME = 0.35    # normale Lautstärke
MUSIC_DUCK   = 0.10    # gedämpft, während die Persona spricht
_music_state = {"path": None, "playing": False, "ducked": False}


def _music_pick(mood):
    """Zufällige Datei aus data/persona_music/<mood>/ (oder None, wenn leer)."""
    folder = os.path.join(MUSIC_DIR, mood)
    try:
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.lower().endswith(('.ogg', '.mp3', '.wav', '.flac'))]
    except Exception:
        files = []
    return random.choice(files) if files else None


def music_play(mood):
    """Lädt einen Track der Stimmung und spielt ihn geloopt (leise im Hintergrund).
    Keine Datei da → still (Content-Lücke), kein Crash."""
    path = _music_pick(mood)
    if not path:
        return False
    try:
        with _mixer_lock:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.load(path)
            vol = MUSIC_DUCK if _music_state["ducked"] else MUSIC_VOLUME
            pygame.mixer.music.set_volume(vol)
            pygame.mixer.music.play(-1)
            _music_state.update(path=path, playing=True)
        return True
    except Exception:
        return False


def music_stop():
    try:
        with _mixer_lock:
            pygame.mixer.music.stop()
    except Exception:
        pass
    _music_state.update(path=None, playing=False)


def music_duck(on):
    """Musik während des Sprechens leiser (on) bzw. zurück (off)."""
    _music_state["ducked"] = bool(on)
    if not _music_state["playing"]:
        return
    try:
        with _mixer_lock:
            pygame.mixer.music.set_volume(MUSIC_DUCK if on else MUSIC_VOLUME)
    except Exception:
        pass


def play_wav(wav_bytes):
    """Spielt WAV-Bytes über pygame.mixer. Initialisiert den Mixer bei Bedarf auf
    die Sample-Rate der Datei — pygame resampelt NICHT, sonst käme die Stimme
    zu hoch/tief. Gibt den Channel zurück (zum Busy-Pollen) oder None. Schlägt
    Audio fehl (kein Gerät, Pi-ALSA), bleibt es still statt zu crashen.

    Muss der Mixer für eine abweichende Rate neu init werden, stoppt das die
    laufende mixer.music — darum den Track danach wieder aufziehen (aus praktischen
    Gründen von vorn; TTS ist konstant 22 kHz, ein Reinit passiert also fast nie
    mitten in einer Session)."""
    try:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            fr = wf.getframerate()
        with _mixer_lock:
            init = pygame.mixer.get_init()
            need_reinit = (not init) or init[0] != fr
            resume = _music_state["path"] if (need_reinit and _music_state["playing"]) else None
            if need_reinit:
                try: pygame.mixer.quit()
                except Exception: pass
                pygame.mixer.init(frequency=fr)
                if resume:
                    try:
                        pygame.mixer.music.load(resume)
                        pygame.mixer.music.set_volume(MUSIC_DUCK if _music_state["ducked"] else MUSIC_VOLUME)
                        pygame.mixer.music.play(-1)
                    except Exception:
                        _music_state.update(path=None, playing=False)
            snd = pygame.mixer.Sound(io.BytesIO(wav_bytes))
            return snd.play()
    except Exception:
        return None


# ── Persona-Sprite: läuft, sitzt, blinzelt, redet ────────────────────────────
class Persona:
    """Ein schlichtes, freundliches Figürchen, das im Zimmer lebt. Zeichnet sich
    aus pygame-Primitiven (kein Sprite-Sheet nötig) und hat eine kleine Verhaltens-
    Maschine: idle → schlendert los → sitzt sich auf die Couch → steht wieder auf.
    Redet die Persona (SSE läuft), nickt sie zugewandt."""

    def __init__(self):
        self.x = 0.0
        self.facing = 1
        self.state = 'idle'          # idle | walk | sit | talk
        self.t = 0.0
        self.blink = 0.0
        self.idle_timer = 0.0
        self.target = None           # ziel-x zum hinlaufen
        self.want_sit = False
        self.sitting = False
        self.stance = 'idle'         # von der KI gesetzt (express-Tool)
        self.gesture = None          # laufende einmalige Geste
        self.gesture_t = 0.0
        self.pause_t = 0.0           # Schlender-Pause bei 'wander'
        self.face = 'neutral'        # Mimik (happy/sad/surprised/tired/neutral)
        # layout (in layout() gesetzt)
        self.floor_y = 0.0
        self.couch_x = 0.0
        self.couch_seat_y = 0.0
        self.xmin = 0.0
        self.xmax = 0.0
        self.scale = 1.0

    def layout(self, w, h):
        self.floor_y = h * 0.80          # wo die Füße im Stehen sind
        self.scale = max(0.7, min(1.6, h / 560.0))
        self.couch_x = w * 0.76
        self.couch_seat_y = h * 0.70
        self.xmin = w * 0.10
        self.xmax = w * 0.66             # freier Lauf-Bereich (links der Couch)
        if self.x == 0.0:
            self.x = w * 0.35

    def set_stance(self, stance):
        """Vom Backend (KI per express-Tool) gesetzte Haltung — ersetzt das
        frühere hardcoded-Random. Bewegt sich nur, wenn die KI es will."""
        if not stance or stance == self.stance:
            return
        self.stance = stance
        mid = (self.xmin + self.xmax) * 0.5
        if stance in ('sit', 'sleep'):    # sleep = auf der Couch sitzen + Augen zu
            self.want_sit = True;  self.target = self.couch_x
        elif stance == 'come_closer':
            self.sitting = False; self.want_sit = False; self.target = mid
        elif stance == 'wander':
            self.sitting = False; self.want_sit = False
            self.target = random.uniform(self.xmin, self.xmax)
        elif stance == 'pace':
            self.sitting = False; self.want_sit = False
            self.target = self.xmax if self.x < mid else self.xmin
        else:  # 'stand' / 'idle'
            self.sitting = False; self.want_sit = False; self.target = None

    def play_gesture(self, kind):
        """Einmalige Geste (winken/nicken/strecken/arme hoch/schulterzucken), ~1.3 s.
        cross_arms hält etwas länger (Pose)."""
        self.gesture = kind
        self.gesture_t = 2.2 if kind == 'cross_arms' else 1.3

    def set_face(self, face):
        if face:
            self.face = face

    def update(self, dt, talking):
        self.t += dt
        self.blink -= dt
        if self.blink < 0:
            self.blink = random.uniform(2.2, 5.0)  # nächster Lidschlag
        if self.gesture_t > 0:
            self.gesture_t -= dt
            if self.gesture_t <= 0:
                self.gesture = None

        if talking:
            # redet zugewandt; steht dabei nicht extra auf (auch von der Couch ok)
            self.state = 'talk'
            self.facing = 1
            return

        # zum Ziel laufen (von set_stance gesetzt)
        if self.target is not None:
            dx = self.target - self.x
            if abs(dx) > 3:
                sp = 70 * self.scale * dt
                self.x += math.copysign(min(sp, abs(dx)), dx)
                self.facing = 1 if dx > 0 else -1
                self.state = 'walk'
                return
            self.x = self.target
            self.target = None
            if self.want_sit and abs(self.x - self.couch_x) < 8:
                self.sitting = True
            # anhaltende Bewegungen: neues Ziel nach dem Erreichen
            if self.stance == 'pace':
                self.target = self.xmin if abs(self.x - self.xmax) < 12 else self.xmax
            elif self.stance == 'wander':
                self.pause_t = random.uniform(1.5, 3.5)   # kurz stehen, dann weiter

        # Schlender-Pause bei 'wander'
        if self.stance == 'wander' and self.target is None:
            self.pause_t -= dt
            if self.pause_t <= 0:
                self.target = random.uniform(self.xmin, self.xmax)

        self.state = 'sit' if self.sitting else 'idle'

    # -- Zeichnen ------------------------------------------------------------
    def head_top(self):
        """y der Kopf-Oberkante — die Sprechblase hängt sich hier dran."""
        s = self.scale
        if self.sitting or self.state == 'sit':
            base = self.couch_seat_y
        else:
            base = self.floor_y
        bob = math.sin(self.t * 3.0) * 2 * s
        return base - 92 * s + bob

    def draw(self, surf):
        s = self.scale
        talking = self.state == 'talk'
        sitting = self.sitting or self.state == 'sit'
        base_y = (self.couch_seat_y if sitting else self.floor_y)
        # sanftes Wippen; beim Reden etwas lebhafter, beim Laufen Schritt-Bob
        if talking:
            bob = math.sin(self.t * 7.0) * 2.2 * s
        elif self.state == 'walk':
            bob = abs(math.sin(self.t * 8.0)) * 3 * s
        else:
            bob = math.sin(self.t * 3.0) * 2 * s
        x = self.x
        y = base_y + bob

        col_leg = LIMB
        # Beine
        if sitting:
            # Oberschenkel waagerecht auf der Couch, Unterschenkel runter
            pygame.draw.rect(surf, col_leg, (x - 12*s, y - 20*s, 26*s, 9*s), border_radius=int(4*s))
            pygame.draw.rect(surf, col_leg, (x + 6*s, y - 12*s, 8*s, 22*s), border_radius=int(4*s))
            pygame.draw.rect(surf, col_leg, (x - 12*s, y - 12*s, 8*s, 22*s), border_radius=int(4*s))
        elif self.state == 'walk':
            sw = math.sin(self.t * 8.0) * 7 * s
            pygame.draw.rect(surf, col_leg, (x - 9*s + sw, y - 26*s, 8*s, 28*s), border_radius=int(4*s))
            pygame.draw.rect(surf, col_leg, (x + 1*s - sw, y - 26*s, 8*s, 28*s), border_radius=int(4*s))
        else:
            pygame.draw.rect(surf, col_leg, (x - 9*s, y - 26*s, 8*s, 28*s), border_radius=int(4*s))
            pygame.draw.rect(surf, col_leg, (x + 1*s, y - 26*s, 8*s, 28*s), border_radius=int(4*s))

        # Körper (Kleid, leicht trapezförmig)
        body_top = y - 62*s
        pts = [(x - 15*s, y - 22*s), (x + 15*s, y - 22*s),
               (x + 12*s, body_top), (x - 12*s, body_top)]
        pygame.draw.polygon(surf, DRESS, pts)
        pygame.draw.polygon(surf, DRESS_DK, [(x - 15*s, y - 22*s), (x - 8*s, y - 22*s),
                                             (x - 7*s, body_top), (x - 12*s, body_top)])
        # Arme — mit Gesten (winken/strecken/arme hoch/schulterzucken/abtorsten)
        g = self.gesture
        gp = (1.3 - self.gesture_t) * 7.0    # Gesten-Phase
        la_off = ra_off = 0.0
        if g == 'wave':
            ra_off = -26*s + math.sin(gp) * 5*s
        elif g in ('stretch', 'arms_up'):
            la_off = ra_off = -26*s
        elif g == 'shrug':
            la_off = ra_off = -8*s
        arm_sw = math.sin(self.t * 8.0) * 6 * s if self.state == 'walk' else 0
        if g == 'cross_arms':                 # Arme waagerecht vor der Brust
            pygame.draw.rect(surf, LIMB, (x - 14*s, body_top + 12*s, 28*s, 6*s), border_radius=int(3*s))
            pygame.draw.rect(surf, LIMB, (x - 12*s, body_top + 19*s, 24*s, 6*s), border_radius=int(3*s))
        else:
            pygame.draw.rect(surf, LIMB, (x - 17*s, body_top + 3*s + arm_sw + la_off, 6*s, 30*s), border_radius=int(3*s))
            pygame.draw.rect(surf, LIMB, (x + 11*s, body_top + 3*s - arm_sw + ra_off, 6*s, 30*s), border_radius=int(3*s))

        # Kopf (nicken = kurzer Ab-Bob)
        nod = abs(math.sin(gp)) * 6*s if g == 'nod' else 0.0
        hy = body_top - 16*s + nod
        pygame.draw.circle(surf, SKIN, (int(x), int(hy)), int(15*s))
        # Haare (Bob): Kappe oben + zwei seitliche Strähnen
        pygame.draw.circle(surf, HAIR, (int(x), int(hy - 3*s)), int(15*s))
        pygame.draw.rect(surf, SKIN, (x - 15*s, hy, 30*s, 15*s))  # Gesicht frei
        pygame.draw.rect(surf, HAIR, (x - 15*s, hy - 2*s, 5*s, 16*s), border_radius=int(2*s))
        pygame.draw.rect(surf, HAIR, (x + 10*s, hy - 2*s, 5*s, 16*s), border_radius=int(2*s))
        # Augen — Mimik: schlafen/müde = zu/halb, überrascht = weit, sonst Punkte
        sleeping = (self.stance == 'sleep')
        blinking = self.blink < 0.14
        face = self.face
        ex = 5.2*s; ey = hy + 1*s; ew = max(1, int(1.6*s))
        if sleeping or face == 'tired' or blinking:
            for sx in (-ex, ex):
                pygame.draw.line(surf, HAIR, (x + sx - 2.5*s, ey), (x + sx + 2.5*s, ey), ew)
        elif face == 'surprised':
            for sx in (-ex, ex):
                pygame.draw.circle(surf, HAIR, (int(x + sx), int(ey)), max(2, int(2.8*s)), width=max(1, int(1.4*s)))
        elif face == 'puzzled':
            for sx in (-ex, ex):
                pygame.draw.circle(surf, HAIR, (int(x + sx), int(ey)), max(1, int(2*s)))
            # eine hochgezogene Augenbraue (rechts) → fragender Blick
            pygame.draw.line(surf, HAIR, (x + ex - 2.5*s, ey - 3.4*s), (x + ex + 2.5*s, ey - 4.8*s), ew)
        else:
            for sx in (-ex, ex):
                pygame.draw.circle(surf, HAIR, (int(x + sx), int(ey)), max(1, int(2*s)))
        # Mund — Mimik: reden > überrascht(O) > traurig(runter) > müde(Strich) >
        # glücklich(breites Lächeln) > neutral(kleines Lächeln)
        my = hy + 8*s; mw = max(1, int(1.6*s))
        if talking and int(self.t * 8) % 2 == 0:
            pygame.draw.circle(surf, DRESS_DK, (int(x), int(my)), max(2, int(2.6*s)))
        elif face == 'surprised':
            pygame.draw.circle(surf, DRESS_DK, (int(x), int(my)), max(2, int(2.4*s)), width=mw)
        elif face == 'sad':
            pygame.draw.arc(surf, DRESS_DK, (x - 5*s, my, 10*s, 8*s), 0, math.pi, mw)
        elif face == 'tired' or sleeping:
            pygame.draw.line(surf, DRESS_DK, (x - 3.5*s, my), (x + 3.5*s, my), mw)
        elif face == 'puzzled':
            pygame.draw.line(surf, DRESS_DK, (x - 3*s, my + 1.2*s), (x + 3*s, my - 1.2*s), mw)  # schiefer, unsicherer Strich
        elif face == 'happy':
            pygame.draw.arc(surf, DRESS_DK, (x - 6*s, my - 5*s, 12*s, 10*s), math.pi, 2*math.pi, max(1, int(2*s)))
        else:
            pygame.draw.arc(surf, DRESS_DK, (x - 5*s, my - 4*s, 10*s, 8*s), math.pi, 2*math.pi, mw)


# ── Zimmer zeichnen ──────────────────────────────────────────────────────────
def draw_room(surf, w, h, t):
    # Wand (vertikaler Verlauf)
    wall_h = int(h * 0.62)
    for i in range(wall_h):
        f = i / max(1, wall_h)
        col = (int(WALL_TOP[0] + (WALL_BOT[0]-WALL_TOP[0])*f),
               int(WALL_TOP[1] + (WALL_BOT[1]-WALL_TOP[1])*f),
               int(WALL_TOP[2] + (WALL_BOT[2]-WALL_TOP[2])*f))
        pygame.draw.line(surf, col, (0, i), (w, i))
    # Boden
    for i in range(wall_h, h):
        f = (i - wall_h) / max(1, h - wall_h)
        col = (int(FLOOR_TOP[0] + (FLOOR_BOT[0]-FLOOR_TOP[0])*f),
               int(FLOOR_TOP[1] + (FLOOR_BOT[1]-FLOOR_TOP[1])*f),
               int(FLOOR_TOP[2] + (FLOOR_BOT[2]-FLOOR_TOP[2])*f))
        pygame.draw.line(surf, col, (0, i), (w, i))
    # Dielen-Fugen (perspektivisch angedeutet)
    for k in range(1, 7):
        fx = int(w * k / 7)
        pygame.draw.line(surf, (FLOOR_BOT[0], FLOOR_BOT[1], FLOOR_BOT[2]),
                         (fx, wall_h), (int(w*0.5 + (fx-w*0.5)*1.7), h), 1)

    # Fenster mit Mond
    fw, fh = int(w*0.20), int(h*0.28)
    fx, fy = int(w*0.13), int(h*0.14)
    pygame.draw.rect(surf, WINDOW_FR, (fx-8, fy-8, fw+16, fh+16), border_radius=8)
    pygame.draw.rect(surf, WINDOW_SKY, (fx, fy, fw, fh))
    pygame.draw.circle(surf, MOON, (fx + int(fw*0.68), fy + int(fh*0.32)), int(min(fw,fh)*0.16))
    for (sx, sy) in [(0.2,0.25),(0.35,0.6),(0.5,0.2),(0.8,0.7),(0.28,0.8)]:
        pygame.draw.circle(surf, (200,210,230), (fx+int(fw*sx), fy+int(fh*sy)), 1)
    pygame.draw.line(surf, WINDOW_FR, (fx+fw//2, fy), (fx+fw//2, fy+fh), 3)
    pygame.draw.line(surf, WINDOW_FR, (fx, fy+fh//2), (fx+fw, fy+fh//2), 3)

    # Teppich (Ellipse auf dem Boden)
    rug_c = (int(w*0.42), int(h*0.86))
    pygame.draw.ellipse(surf, RUG, (rug_c[0]-int(w*0.26), rug_c[1]-int(h*0.07),
                                    int(w*0.52), int(h*0.14)))
    pygame.draw.ellipse(surf, RUG_RING, (rug_c[0]-int(w*0.26), rug_c[1]-int(h*0.07),
                                         int(w*0.52), int(h*0.14)), 3)

    # Stehlampe (links) mit Glühen
    lx = int(w*0.06)
    pygame.draw.line(surf, POT, (lx, int(h*0.86)), (lx, int(h*0.55)), 4)
    glow = pygame.Surface((80, 80), pygame.SRCALPHA)
    pygame.draw.circle(glow, (LAMP_GLOW[0], LAMP_GLOW[1], LAMP_GLOW[2], 60), (40, 40), 34)
    surf.blit(glow, (lx-40, int(h*0.55)-52))
    pygame.draw.polygon(surf, LAMP_GLOW, [(lx-16, int(h*0.55)), (lx+16, int(h*0.55)), (lx+10, int(h*0.50)), (lx-10, int(h*0.50))])

    # Pflanze (rechts hinten)
    px = int(w*0.92)
    py = int(h*0.70)
    pygame.draw.rect(surf, POT, (px-14, py, 28, 24), border_radius=4)
    for ang in (-0.6, -0.2, 0.2, 0.6):
        ex = px + int(math.sin(ang)*26)
        ey = py - 40 - int(math.cos(ang)*20)
        pygame.draw.line(surf, PLANT, (px, py), (ex, ey), 5)
        pygame.draw.circle(surf, PLANT, (ex, ey), 9)

    # Couch (rechts, wo die Persona sitzt)
    cx, cy = int(w*0.76), int(h*0.72)
    cw, ch = int(w*0.26), int(h*0.16)
    pygame.draw.rect(surf, COUCH_DK, (cx-cw//2, cy, cw, ch), border_radius=14)          # Sitzfläche/Schatten
    pygame.draw.rect(surf, COUCH, (cx-cw//2, cy-int(ch*0.7), cw, int(ch*0.9)), border_radius=14)  # Rückenlehne
    pygame.draw.rect(surf, COUCH_LT, (cx-cw//2, cy-int(ch*0.7), cw, int(ch*0.22)), border_radius=14)  # Licht oben
    pygame.draw.rect(surf, COUCH, (cx-cw//2-10, cy-int(ch*0.4), 20, int(ch*0.8)), border_radius=10)   # Armlehne li
    pygame.draw.rect(surf, COUCH, (cx+cw//2-10, cy-int(ch*0.4), 20, int(ch*0.8)), border_radius=10)   # Armlehne re
    # zwei Kissen
    for kx in (cx-int(cw*0.22), cx+int(cw*0.06)):
        pygame.draw.rect(surf, COUCH_LT, (kx, cy-int(ch*0.1), int(cw*0.16), int(ch*0.4)), border_radius=8)


def _wrap(font, text, max_w, max_lines=6):
    """Zeilenumbruch — zeichenweise (CJK hat keine Wort-Grenzen). max_lines=None
    → kein Limit (für die Verlaufs-Leiste, wo lange Antworten ganz stehen)."""
    lines, cur = [], ''
    for ch in text:
        if ch == '\n':
            lines.append(cur); cur = ''; continue
        if font.size(cur + ch)[0] > max_w and cur:
            lines.append(cur); cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines if max_lines is None else lines[:max_lines]


def _transcript_lines(log, persona_name, font, max_w):
    """Log (Liste von (role, text)) → flache Liste (farbe, zeile) für die
    Verlaufs-Leiste, umgebrochen; Fortsetzungszeilen leicht eingerückt."""
    out = []
    for role, txt in log:
        who = "Sasha" if role == 'user' else (persona_name or "Ling Ling")
        col = ROLE_USER if role == 'user' else ROLE_TUTOR
        wrapped = _wrap(font, f"{who}: {txt}", max_w, max_lines=None)
        for i, ln in enumerate(wrapped):
            out.append((col, ln if i == 0 else "  " + ln))
    return out


def draw_tv(surf, w, h, on, title, font, t):
    """Fernseher an der Wand. Aus = dunkler Schirm; an = leuchtet (bläulich,
    leichtes Flackern) und zeigt den Titel. Echtes Video ist DEFERRED — der
    Schirm zeigt nur den Titel + ein Schimmern (Content-/Playback-Lücke)."""
    tw, th = int(w * 0.17), int(h * 0.14)
    tx, ty = int(w * 0.40) - tw // 2, int(h * 0.20)
    # Standfuß/Rahmen
    pygame.draw.rect(surf, (28, 26, 32), (tx - 6, ty - 6, tw + 12, th + 12), border_radius=8)
    if on:
        # Glühen um den TV
        glow = pygame.Surface((tw + 80, th + 80), pygame.SRCALPHA)
        pygame.draw.rect(glow, (120, 170, 220, 46), (24, 24, tw + 32, th + 32), border_radius=20)
        surf.blit(glow, (tx - 40, ty - 40))
        flick = 12 + int(6 * math.sin(t * 7.0))
        screen_col = (52 + flick, 78 + flick, 120 + flick)
        pygame.draw.rect(surf, screen_col, (tx, ty, tw, th))
        # ein paar Scanlinien / Schimmer
        for k in range(0, th, 6):
            pygame.draw.line(surf, (screen_col[0] + 10, screen_col[1] + 10, screen_col[2] + 14),
                             (tx, ty + k), (tx + tw, ty + k), 1)
        # Titel (umgebrochen, zentriert)
        if title:
            words = title
            maxw = tw - 12
            lines, cur = [], ''
            for chch in words:
                if font.size(cur + chch)[0] > maxw and cur:
                    lines.append(cur); cur = chch
                else:
                    cur += chch
            if cur:
                lines.append(cur)
            lines = lines[:3]
            yy = ty + th // 2 - (len(lines) * font.get_linesize()) // 2
            for ln in lines:
                r = font.render(ln, True, (235, 242, 252))
                surf.blit(r, (tx + (tw - r.get_width()) // 2, yy)); yy += font.get_linesize()
    else:
        pygame.draw.rect(surf, (20, 22, 28), (tx, ty, tw, th))
        pygame.draw.line(surf, (40, 44, 52), (tx + 6, ty + 6), (tx + tw - 10, ty + th - 8), 2)  # Reflex


# ── Rede säubern: Regie-Klammern + geleakte Tool-Zeilen raus ──────────────────
# Sicherheitsnetz gegen qwens Roleplay-Prior (schreibt Aktionen als „（…）" und
# leakt manchmal Tool-Namen wie „show_thought: …" in den Text). Was Sasha SIEHT
# und HÖRT, wird hier bereinigt — unabhängig davon, wie brav das Modell ist.
_TOOL_NAMES = ('express', 'show_thought', 'mark_known', 'play_music', 'stop_music',
               'watch_tv', 'turn_off_tv', 'get_local_news', 'get_confirmed_vocab',
               'get_testing_vocab', 'increment_correct_use', 'introduce_new',
               'get_structures', 'introduce_structure', 'increment_structure')
_PAREN_RE    = re.compile(r'（[^）]*）|\([^)]*\)')          # Regie in Klammern
_TOOLLINE_RE = re.compile(r'^\s*(?:' + '|'.join(_TOOL_NAMES) + r')\b.*$', re.IGNORECASE)


def _clean_speech(text):
    """Streift （Regie） und geleakte Tool-Zeilen aus dem sichtbaren/gesprochenen
    Text. Klammer-Gruppen müssen geschlossen sein (offene bleiben, bis der Stream
    sie schließt) — bei fertigen Zeilen ist alles zu."""
    if not text:
        return text
    text = _PAREN_RE.sub('', text)
    lines = []
    for ln in text.split('\n'):
        ln = ln.strip()
        if ln and not _TOOLLINE_RE.match(ln):   # leere + reine Tool-Zeilen raus
            lines.append(ln)
    return '\n'.join(lines).strip()


def draw_bubble(surf, font, text, cx, top_y, w, alpha=255):
    """Sprechblase über dem Kopf; alpha<255 blendet sie aus (Gesagtes verhallt).
    Auf eine Temp-Surface gemalt, damit der Alpha gleichmäßig wirkt."""
    if not text or alpha <= 0:
        return
    max_w = min(int(w*0.5), 420)
    lines = _wrap(font, text, max_w - 28)
    lh = font.get_linesize()
    bw = min(max_w, max((font.size(l)[0] for l in lines), default=40) + 28)
    bh = lh * len(lines) + 20
    bx = int(cx - bw/2)
    by = int(top_y - bh - 16)
    bx = max(8, min(bx, surf.get_width() - bw - 8))
    by = max(8, by)
    tipx = int(max(bx+18, min(cx, bx+bw-18)))
    tmp = pygame.Surface((bw, bh + 14), pygame.SRCALPHA)
    pygame.draw.rect(tmp, BUBBLE_BG, (0, 0, bw, bh), border_radius=14)
    pygame.draw.rect(tmp, BUBBLE_BD, (0, 0, bw, bh), 2, border_radius=14)
    lx = tipx - bx
    pygame.draw.polygon(tmp, BUBBLE_BG, [(lx-9, bh-2), (lx+9, bh-2), (lx, bh+12)])  # Schnabel
    for i, ln in enumerate(lines):
        tmp.blit(font.render(ln, True, BUBBLE_FG), (14, 10 + i*lh))
    if alpha < 255:
        tmp.set_alpha(alpha)
    surf.blit(tmp, (bx, by))


# ── App ──────────────────────────────────────────────────────────────────────
# ── Assessment-Screen: das harte Gate vor der Persona ────────────────────────
# Solange der Kern-Wortschatz nicht gemeistert ist, sieht Sasha NICHT das Zimmer
# und nicht die Figur — nur diese ruhige, DETERMINISTISCHE Vokabel-Abfrage (kein
# LLM). Lucías STIMME liest die Wörter vor (TTS), aber die Persona „lebt" hier
# nicht. Der Ablauf wird lokal getrieben (asv-Controller in main); dies ist nur
# das Rendering. Freischaltung bei ratio ≥ 0.75, dann übernimmt das Zimmer.
ASSESS_TOP  = (28, 36, 52)
ASSESS_BOT  = (40, 50, 70)
ASSESS_ACC  = (150, 200, 230)     # kühles Blau, Fortschritt
ASSESS_GOLD = (240, 206, 120)     # warmer Pop: Ziel/Freischaltung
COIN_HI     = (246, 214, 128)     # Münze hell
COIN_LO     = (206, 158, 66)      # Münze dunkel

# Spiel-Schicht: Lucía baut sich beim Lernen aus Teilen zusammen. Die Teile
# „schweben" beim Erhalt aus einer zufälligen Richtung herein und rasten an
# ihren Platz (Sashas Vorgabe: keine eigene Box, sie arrangieren sich selbst).
# Namen decken sich mit tutor/tools.py::_PARTS.
_PART_SCATTER = {'hair': (-72, -46), 'head': (64, -52), 'arml': (-96, 18),
                 'armr': (98, 12), 'dress': (6, 86), 'legl': (-54, 74),
                 'legr': (58, 80)}
_PRIO_LOCAL = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _draw_coin(surf, cx, cy, r):
    """Kleine Münze (Farbverlauf angedeutet) — Währungs-HUD."""
    pygame.draw.circle(surf, COIN_LO, (int(cx), int(cy)), int(r))
    pygame.draw.circle(surf, COIN_HI, (int(cx), int(cy)), int(r), max(1, int(r * 0.28)))
    pygame.draw.circle(surf, COIN_HI, (int(cx - r * 0.3), int(cy - r * 0.3)), max(1, int(r * 0.28)))


def _draw_lucia(surf, cx, cy, s, parts, anim=None):
    """Lucía aus ihren erhaltenen Teilen zeichnen (pygame-Primitive, gleiche
    Optik wie die Persona). `parts` = erhaltene Teile; `anim=(name, p)` lässt EIN
    frisches Teil aus seiner Streu-Richtung an den Platz gleiten (p: 0→1)."""
    pset = set(parts or [])

    def off(name):
        if anim and anim[0] == name:
            p = max(0.0, min(1.0, anim[1])); e = 1 - (1 - p) * (1 - p)   # easeOut
            sx, sy = _PART_SCATTER.get(name, (0, -40))
            return ((1 - e) * sx * s, (1 - e) * sy * s)
        return (0.0, 0.0)

    # Boden-Schatten (nur wenn schon etwas da ist)
    if pset:
        sh = pygame.Surface((int(70 * s), int(16 * s)), pygame.SRCALPHA)
        pygame.draw.ellipse(sh, (0, 0, 0, 60), sh.get_rect())
        surf.blit(sh, (int(cx - 35 * s), int(cy + 88 * s)))
    # Beine
    for nm, dx in (('legl', -14), ('legr', 5)):
        if nm in pset:
            ox, oy = off(nm)
            pygame.draw.rect(surf, LIMB, (cx + dx * s + ox, cy + 42 * s + oy, 9 * s, 46 * s), border_radius=int(4 * s))
    # Kleid (Trapez)
    if 'dress' in pset:
        ox, oy = off('dress')
        pygame.draw.polygon(surf, DRESS, [(cx - 12 * s + ox, cy - 20 * s + oy), (cx + 12 * s + ox, cy - 20 * s + oy),
                                          (cx + 22 * s + ox, cy + 44 * s + oy), (cx - 22 * s + ox, cy + 44 * s + oy)])
        pygame.draw.polygon(surf, DRESS_DK, [(cx - 12 * s + ox, cy - 20 * s + oy), (cx - 6 * s + ox, cy - 20 * s + oy),
                                             (cx - 14 * s + ox, cy + 44 * s + oy), (cx - 22 * s + ox, cy + 44 * s + oy)])
    # Arme
    for nm, dx in (('arml', -26), ('armr', 18)):
        if nm in pset:
            ox, oy = off(nm)
            pygame.draw.rect(surf, LIMB, (cx + dx * s + ox, cy - 14 * s + oy, 8 * s, 46 * s), border_radius=int(4 * s))
    # Haar (hinter dem Kopf)
    if 'hair' in pset:
        ox, oy = off('hair')
        pygame.draw.circle(surf, HAIR, (int(cx + ox), int(cy - 42 * s + oy)), int(16 * s))
    # Kopf + kleines Gesicht
    if 'head' in pset:
        ox, oy = off('head')
        hx, hy = cx + ox, cy - 38 * s + oy
        pygame.draw.circle(surf, SKIN, (int(hx), int(hy)), int(15 * s))
        if 'hair' in pset:   # Ponyfransen, wenn Haar schon da
            pygame.draw.rect(surf, SKIN, (hx - 15 * s, hy, 30 * s, 14 * s))
        for sx in (-5 * s, 5 * s):
            pygame.draw.circle(surf, HAIR, (int(hx + sx), int(hy + 1 * s)), max(1, int(2 * s)))
        pygame.draw.arc(surf, DRESS_DK, (hx - 5 * s, hy + 4 * s, 10 * s, 7 * s), math.pi, 2 * math.pi, max(1, int(1.6 * s)))

_CAT_DE = {'pronoun':'Pronomen','verb_core':'Kernverb','verb_action':'Verb',
           'question':'Fragewort','spatial':'Ort','time':'Zeit','response':'Antwort',
           'emotion':'Gefühl','adjective':'Eigenschaft','noun_household':'Zuhause',
           'noun_substance':'Ding','tutor_activity':'Alltag','family':'Familie',
           'connector':'Bindewort','modifier':'Verstärker','article':'Artikel',
           'politeness':'Höflichkeit','greeting':'Gruß'}


def _hint_row(screen, font, w, y, items, center_x=None):
    """Reihe [Taste] Label — sagt dem Nutzer, was er tun kann. Standard mittig
    auf w; `center_x` verschiebt die Reihe (z.B. unter die links sitzende Karte)."""
    gap = 18
    cx = w // 2 if center_x is None else center_x
    widths = [(font.size(k)[0] + 16) + 8 + font.size(l)[0] for k, l in items]
    x = cx - (sum(widths) + gap * (len(items) - 1)) // 2
    for (k, l), wd in zip(items, widths):
        ks = font.render(k, True, (16, 22, 32)); kw = ks.get_width() + 16
        pygame.draw.rect(screen, ASSESS_ACC, (x, y, kw, font.get_height() + 8), border_radius=7)
        screen.blit(ks, (x + 8, y + 4))
        screen.blit(font.render(l, True, (206, 216, 230)), (x + kw + 8, y + 4))
        x += wd + gap


def _draw_coin_hud(screen, fonts, w, asv):
    """Münz-Zähler oben rechts + „+N"-Pop, wenn gerade eine Münze fiel."""
    coins = int(asv.get('coins', 0))
    r = 9; cx = w - 20 - r; cy = 22
    txt = fonts['big'].render(str(coins), True, COIN_HI)
    tx = cx - r - 8 - txt.get_width()
    screen.blit(txt, (tx, cy - txt.get_height() // 2))
    _draw_coin(screen, cx, cy, r)
    pop = asv.get('coin_pop')
    if pop and pop.get('t', 0) > 0:
        rise = int((1.0 - pop['t']) * 20)
        pr = fonts['hud'].render('+%d' % pop['n'], True, COIN_HI)
        pr.set_alpha(int(255 * min(1.0, pop['t'])))
        screen.blit(pr, (tx - pr.get_width() - 6, cy - 8 - rise))


def _draw_reveal(screen, fonts, w, h, asv):
    """Kisten-Ergebnis kurz einblenden (Teil ODER Münzen — beides zufällig)."""
    rv = asv.get('reveal')
    if not rv:
        return
    box_w, box_h = 300, 96
    bx, by = w // 2 - box_w // 2, 96
    panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    panel.fill((26, 32, 46, 235))
    pygame.draw.rect(panel, ASSESS_GOLD, panel.get_rect(), width=2, border_radius=14)
    screen.blit(panel, (bx, by))
    head = fonts['big'].render('▣  Kiste!', True, ASSESS_GOLD)
    screen.blit(head, (w // 2 - head.get_width() // 2, by + 14))
    if rv.get('kind') == 'part':
        sub = fonts['log'].render('ein neues Teil von Lucía', True, HUD_FG)
    else:
        sub = fonts['log'].render('+%d Münzen' % int(rv.get('amount', 0)), True, COIN_HI)
    screen.blit(sub, (w // 2 - sub.get_width() // 2, by + 54))


def draw_assessment(screen, w, h, fonts, asv, speaking, caret_t):
    for y in range(h):
        f = y / max(1, h - 1)
        col = tuple(int(a + (b - a) * f) for a, b in zip(ASSESS_TOP, ASSESS_BOT))
        pygame.draw.line(screen, col, (0, y), (w, y))

    phase = asv.get('phase', 'welcome')
    got = asv.get('got', 0); total = asv.get('total', 0) or 76; ratio = asv.get('ratio', 0.0)
    parts = asv.get('parts', []); parts_total = asv.get('parts_total', 7)
    cy = h // 2 + 6

    def ctr(surf, y): screen.blit(surf, (w // 2 - surf.get_width() // 2, y))

    # Fortschrittsbalken + Münz-HUD (immer, außer Willkommen)
    if phase != 'welcome':
        bw = min(520, w - 220); bx = 60; by = 52; bh = 13
        pygame.draw.rect(screen, (20, 26, 38), (bx, by, bw, bh), border_radius=7)
        fw = int(bw * max(0.0, min(1.0, ratio)))
        if fw > 0:
            pygame.draw.rect(screen, ASSESS_ACC, (bx, by, fw, bh), border_radius=7)
        mx = bx + int(bw * 0.75)
        pygame.draw.line(screen, ASSESS_GOLD, (mx, by - 4), (mx, by + bh + 4), 2)
        screen.blit(fonts['hud'].render(f'{got} / {total} · {int(round(100*ratio))}%', True, HUD_FG),
                    (bx, by - fonts['hud'].get_height() - 5))
        screen.blit(fonts['hud'].render('Lucía ab 75 %', True, ASSESS_GOLD), (mx + 6, by + bh + 4))
        _draw_coin_hud(screen, fonts, w, asv)

    if phase == 'welcome':
        ctr(fonts['word'].render('Hola', True, (236, 238, 246)), cy - 150)
        ctr(fonts['big'].render('Ich bin Lucía.', True, (232, 236, 244)), cy - 78)
        for i, ln in enumerate(['Zuerst gehen wir zusammen die wichtigsten Wörter durch — hak ab, was du kannst.',
                                'Dabei sammelst du Münzen und puzzelst mich Stück für Stück zusammen.']):
            ctr(fonts['log'].render(ln, True, HUD_DIM), cy - 22 + i * 26)
        _hint_row(screen, fonts['hud'], w, cy + 82, [('Enter', 'Los geht’s')])
        return

    # Lucía baut sich rechts zusammen (schwebende Teile). Bei Freischaltung komplett.
    fig_x = int(w * 0.82); fig_y = int(h * 0.52); fig_s = max(0.8, min(1.5, h / 620.0))
    show_parts = _PART_SCATTER.keys() if phase == 'unlock' else parts
    anim = None
    np = asv.get('new_part')
    if np and np.get('t', 1) < 1.0:
        anim = (np['name'], np['t'])
    _draw_lucia(screen, fig_x, fig_y, fig_s, show_parts, anim)
    cap = 'Lucía · komplett' if phase == 'unlock' else f'Lucía · {len(parts)}/{parts_total} Teile'
    capr = fonts['hud'].render(cap, True, HUD_DIM)
    screen.blit(capr, (fig_x - capr.get_width() // 2, fig_y + int(96 * fig_s)))

    if phase == 'unlock':
        ctr(fonts['word'].render('¡Hola!', True, ASSESS_GOLD), cy - 96)
        ctr(fonts['big'].render('Lucía ist da.', True, (236, 238, 246)), cy - 18)
        ctr(fonts['log'].render('Du kannst genug — ab jetzt redet ihr wirklich, auf Spanisch.',
                                True, HUD_DIM), cy + 26)
        _hint_row(screen, fonts['hud'], w, cy + 78, [('Enter', 'zu Lucía')])
        return

    # phase == 'card' — die Karte etwas links vom Zentrum, damit sie Lucía nicht überlappt
    ccx = int(w * 0.40)

    def ctl(surf, y): screen.blit(surf, (ccx - surf.get_width() // 2, y))

    cur = asv.get('cur')
    if not cur:
        ctl(fonts['big'].render('…', True, HUD_DIM), cy)
        _draw_reveal(screen, fonts, w, h, asv)
        return
    cat = _CAT_DE.get(cur.get('category', ''), '')
    if cat:
        ctl(fonts['hud'].render(cat.upper(), True, ASSESS_ACC), cy - 108)
    ctl(fonts['word'].render(cur.get('word', ''), True, (238, 240, 248)), cy - 74)
    if speaking:
        ctl(fonts['hud'].render('◗ Lucía spricht …', True, ASSESS_ACC), cy - 2)

    if asv.get('sub') == 'learn':
        ctl(fonts['bubble'].render('= ' + (cur.get('de') or '…'), True, ASSESS_GOLD), cy + 26)
    else:
        ctl(fonts['bubble'].render('Kennst du das Wort?', True, (210, 218, 230)), cy + 26)
    # Tasten: Abhaken (primär) · Repeat · Next
    _hint_row(screen, fonts['hud'], w, cy + 82,
              [('Leer', 'Abhaken ✓'), ('R', 'Repeat'), ('N', 'Next')], center_x=ccx)

    _draw_reveal(screen, fonts, w, h, asv)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default=os.environ.get('ZENTRALE_URL', 'http://localhost:5000'))
    ap.add_argument('--w', type=int, default=920)
    ap.add_argument('--h', type=int, default=600)
    # Stimme: Sprecher-ID (vits-zh-aishell3 hat 174 — Wert durchprobieren) + Tempo.
    ap.add_argument('--speaker', type=int, default=int(os.environ.get('TUTOR_TTS_SPEAKER', '66')))
    ap.add_argument('--speed', type=float, default=float(os.environ.get('TUTOR_TTS_SPEED', '1.0')))
    ap.add_argument('--mute', action='store_true', help='ohne Stimme starten')
    ap.add_argument('--no-mic', action='store_true', help='ohne Immer-Zuhören (STT) starten')
    a = ap.parse_args()

    pygame.init()
    pygame.display.set_caption('ZENTRALE — Persona')
    screen = pygame.display.set_mode((a.w, a.h), pygame.RESIZABLE)
    clock = pygame.time.Clock()

    def set_ime_rect():
        """SDL/IME sagen, WO die Eingabe ist — sonst dockt das Pinyin-Kandidaten-
        fenster (ibus/fcitx) nicht an und Mandarin-Eingabe kommt gar nicht an."""
        try:
            w, h = screen.get_size()
            pygame.key.set_text_input_rect(pygame.Rect(14, h - 34, max(60, w - 28), 28))
        except Exception:
            pass

    try:
        pygame.key.start_text_input()  # IME/Unicode-Eingabe (auch CJK) einschalten
    except Exception:
        pass
    set_ime_rect()

    fonts = {'bubble': _font(22), 'hud': _font(15), 'input': _font(20),
             'big': _font(26, True), 'log': _font(18), 'word': _font(52, True)}
    be = Backend(a.url)
    persona = Persona()

    S = {
        'lock': threading.Lock(),
        'busy': False,
        'streaming': False,
        'speaking': False,     # Audio läuft gerade → Mund bewegt sich
        'buf': '',
        'last': '',            # letzte fertige Zeile (bleibt in der Blase stehen)
        'msg': '',
        'available': None,
        'persona': 'Ling Ling',
        'lang': 'zh',          # aus /api/tutor/config (TTS-Sprache)
        'langs': [],           # wählbare (enabled) Sprachen fürs Menü (Alt+L)
        'menu': None,          # offenes Sprach-Menü: {'sel': int} oder None
        'input': '',
        'compose': '',         # laufende IME-Komposition (Pinyin vor dem Commit)
        'tts': None,           # Backend-TTS verfügbar? (status['tts'])
        'mute': bool(a.mute),  # Stimme aus (Alt+M togglet)
        'log': [],             # Verlauf: Liste von (role, text) — 'user' | 'tutor'
        'scroll': 0,           # Verlaufs-Scroll (0 = neuestes unten)
        'stance': 'idle',      # von der KI gesetzte Haltung (room_state-Poll)
        'face': 'neutral',     # von der KI gesetzte Mimik
        'battery': 60, 'mood': 'ok',   # soziale Batterie / Stimmung
        'thought': None,       # (wort, bedeutung) Vokabel-Gedanke, oder None
        'thought_id': 0,       # letzte gesehene Gedanken-id (one-shot wie Geste)
        'thought_t': 0.0,      # Restlaufzeit der Gedanken-Blase (s)
        'music': None,         # laufende Musik-Stimmung (♪-HUD), oder None
        'tv': (False, ''),     # (an?, titel) Fernseher-Zustand
        'pending_gesture': None,  # einmalige Geste, die die Persona abspielen soll
        'last_user_ms': 0,     # letzte Sasha-Eingabe (Feedback-Loop)
        'nudged': False,       # Anstoß in dieser Stille schon gemacht?
        'nudge_ms': 0,
        'mic': not a.no_mic,   # Immer-Zuhören an? (Alt+H togglet)
        'hearing': False,      # gerade Sprache am Mikro?
        'transcribing': False, # Segment wird gerade erkannt
        'mic_err': '',         # kein Mikro / Lib fehlt
        'focused': True,       # Fenster fokussiert? (Sensor: wird sie „angeschaut")
        # ── Assessment-Gate (room_state-Poll) ──────────────────────────────
        'mode': 'room',        # 'assessment' = Drill (kein Zimmer) / 'room' = Persona frei
        'core_got': 0,         # gefestigte Kern-Wörter
        'core_total': 0,       # Kern-Wörter gesamt
        'core_ratio': 0.0,     # Deckung 0..1 (Fortschritt zur Freischaltung)
        'tts_speed': a.speed,  # gerampter Sprech-Speed (0.7→1.0 nach Meisterung)
        # ── Deterministische Abfrage (asv = assessment view controller) ────
        # None = keine Abfrage (Zimmer/Persona). Sonst ein Dict mit dem lokalen
        # Drill-Zustand; die KI ist hier NICHT beteiligt (nur TTS + REST-Antworten).
        'asv': None,
    }

    def log_add(role, text):
        text = (text or '').strip()
        if not text:
            return
        with S['lock']:
            S['log'].append((role, text))
            S['scroll'] = 0        # bei neuem Eintrag ans neueste springen

    def on_token(tok):
        with S['lock']:
            S['buf'] += tok

    def speak(text):
        """Zeile vom Backend synthetisieren (WAV) und abspielen; währenddessen
        S['speaking'] setzen, damit sich der Mund bewegt. Stumm/kein Audio → egal,
        die Blase steht ja trotzdem da."""
        if not text:
            return
        with S['lock']:
            if S['mute']:
                return
            lang = S['lang']
            spd = S['tts_speed']       # gerampt: im Assessment langsam, dann natürlich
        wav = be.speak(text, lang, a.speaker, spd)
        if not wav:
            return
        music_duck(True)         # Musik leiser, solange sie redet
        ch = play_wav(wav)
        if ch is None:
            music_duck(False)
            return
        with S['lock']:
            S['speaking'] = True
        try:
            while ch.get_busy():
                pygame.time.wait(60)
        finally:
            with S['lock']:
                S['speaking'] = False
            music_duck(False)    # Musik wieder auf normal

    def run_stream(path, payload):
        with S['lock']:
            if S['busy']:
                return
            S['busy'] = True
            S['streaming'] = True
            S['buf'] = ''
            S['msg'] = ''
        err = be.stream(path, payload, on_token)
        with S['lock']:
            S['streaming'] = False
            S['busy'] = False
            if err:
                S['msg'] = err
            line = _clean_speech(S['buf'].strip())   # Regie/Tool-Leak raus
            if line:
                S['last'] = line
        if not err and line:
            log_add('tutor', line)   # in den Verlauf
            speak(line)              # ihre Stimme (nach dem Stream, Antworten sind kurz)
        # buf jetzt leeren, damit die Blase verhallen KANN — sonst hält der
        # stehengebliebene Text has_text ewig true und bub_age wird nie größer.
        with S['lock']:
            S['buf'] = ''

    # ── Deterministische Abfrage (asv) — das harte Gate, KEIN LLM ────────────
    # Das Frontend geht die Kern-Wörter Karte für Karte durch: zeigen, vorlesen
    # (TTS), Antwort per REST verbuchen. Kein Sprachmodell, keine Wartezeit. Erst
    # ab 75 % Deckung wird die Persona (run_stream) gestartet.
    def asv_speak(word):
        """Wort vorlesen (TTS, gerampter Speed) — in einem Thread, nicht blockend."""
        if not word:
            return
        def _s():
            with S['lock']:
                if S['mute']:
                    return
                lang = S['lang']; spd = S['tts_speed']
            wav = be.speak(word, lang, a.speaker, spd)
            if not wav:
                return
            music_duck(True); ch = play_wav(wav)
            if ch is None:
                music_duck(False); return
            with S['lock']: S['speaking'] = True
            try:
                while ch.get_busy(): pygame.time.wait(60)
            finally:
                with S['lock']: S['speaking'] = False
                music_duck(False)
        threading.Thread(target=_s, daemon=True).start()

    def _pick(v):
        """Nächste Karte per SRS: fällige (due ≤ seen) zuerst, sonst die mit dem
        kleinsten due; Gleichstand nach Priorität. Reine Funktion (kein Lock)."""
        work = v.get('work') or []
        if not work:
            return None
        seen = v.get('seen', 0)
        ready = [c for c in work if c.get('due', 0) <= seen]
        pool = sorted(ready or work,
                      key=lambda c: (c.get('due', 0), _PRIO_LOCAL.get(c.get('priority'), 9)))
        return pool[0]

    def asv_show():
        """Aktuelle Karte (per SRS gewählt) setzen (sub='ask') und vorlesen."""
        with S['lock']:
            v = S['asv']
            if not v or not v.get('work'):
                return
            cur = _pick(v)
            v['sub'] = 'ask'; v['cur'] = cur
            word = cur['word'] if cur else None
        if word:
            asv_speak(word)

    def asv_advance():
        """Zähler hoch, nächste Karte; nichts mehr offen oder ≥75 % → Freischaltung."""
        with S['lock']:
            v = S['asv']
            if not v:
                return
            if v.get('ratio', 0) >= 0.75 or not v.get('work'):
                v['phase'] = 'unlock'; v['cur'] = None; return
            v['seen'] = v.get('seen', 0) + 1
        asv_show()

    def asv_abhaken():
        """ABHAKEN — der Haupt-Zug: Review verbuchen (REST), Münzen/Kisten/Teile
        aus der Antwort übernehmen, SRS-Fälligkeit setzen (gemeistert → raus),
        dann weiter. Die Spiel-Ökonomie kommt komplett vom Backend (persistiert)."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('busy') or not v.get('cur') or v.get('reveal'):
                return
            v['busy'] = True; card = v['cur']; word = card['word']
        res = be.answer(word, 'learned')
        unlocked = False
        with S['lock']:
            v = S['asv']
            if v:
                v['busy'] = False
                if res:
                    v['got'] = res.get('got', v.get('got', 0))
                    v['total'] = res.get('total', v.get('total', 0))
                    v['ratio'] = res.get('ratio', v.get('ratio', 0.0))
                    v['coins'] = int(res.get('coins', v.get('coins', 0)))
                    gain = int(res.get('coin_gain', 0) or 0)
                    if gain > 0:
                        v['coin_pop'] = {'n': gain, 't': 1.0}
                    if isinstance(res.get('parts'), list):
                        v['parts'] = res['parts']
                    crate = res.get('crate')
                    if crate:
                        v['reveal'] = {'kind': crate.get('kind'),
                                       'amount': int(crate.get('amount', 0) or 0), 't': 2.2}
                        if crate.get('kind') == 'part' and crate.get('part'):
                            v['new_part'] = {'name': crate['part'], 't': 0.0}   # schwebt herein
                    reps = int(res.get('reps', card.get('reps', 0) + 1))
                    card['reps'] = reps
                    if res.get('mastered') or res.get('confirmed'):
                        v['work'] = [c for c in v.get('work', []) if c['word'] != word]
                    else:                                     # SRS: später wieder auffrischen
                        gap = (3, 8, 20)[min(max(reps, 1) - 1, 2)]
                        card['due'] = v.get('seen', 0) + gap
                    unlocked = bool(res.get('unlocked'))
        if unlocked:
            with S['lock']:
                if S['asv']:
                    S['asv']['phase'] = 'unlock'; S['asv']['cur'] = None
            return
        asv_advance()

    def asv_repeat():
        """REPEAT — Bedeutung zeigen + Wort nochmal vorlesen (kein Zähler-Effekt)."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('reveal'):
                return
            v['sub'] = 'learn'
            cur = v.get('cur')
        if cur:
            asv_speak(cur['word'])

    def asv_next():
        """NEXT — Karte kurz zurückstellen (bald wieder dran), ohne zu werten."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('busy') or not v.get('cur') or v.get('reveal'):
                return
            v['cur']['due'] = v.get('seen', 0) + 2
        asv_advance()

    def asv_key(ev):
        """Tastendruck im Abfrage-Modus (kein Text-Input dahinter).
        card-Phase: Leer/Enter = Abhaken · R = Repeat · N/→ = Next."""
        with S['lock']:
            v = S['asv']
            if not v:
                return
            phase = v.get('phase')
        if phase == 'welcome':
            if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                with S['lock']:
                    if S['asv']: S['asv']['phase'] = 'card'
                asv_show()
            return
        if phase == 'unlock':
            if ev.key == pygame.K_RETURN:
                with S['lock']:
                    S['asv'] = None; foc = S['focused']       # Abfrage aus → Persona
                threading.Thread(target=run_stream,
                                 args=('/api/tutor/start', {'focus': foc}), daemon=True).start()
            return
        # phase == 'card'
        if ev.key == pygame.K_r:
            asv_repeat()
        elif ev.key in (pygame.K_SPACE, pygame.K_RETURN):
            threading.Thread(target=asv_abhaken, daemon=True).start()
        elif ev.key in (pygame.K_n, pygame.K_RIGHT):
            asv_next()

    def asv_init():
        """Abfrage starten, falls die Sprache im Assessment-Gate steckt: Queue +
        Spielstand holen, Willkommen zeigen. True = Drill übernimmt (KEIN LLM);
        False = kein Gate → normaler Persona-Start."""
        data = be.assessment()
        if not isinstance(data, dict) or data.get('mode') != 'assessment':
            return False
        game = data.get('game') or {}
        work = [{'word': e['word'], 'de': e.get('de', ''),
                 'category': e.get('category', ''), 'priority': e.get('priority', 'medium'),
                 'reps': int(e.get('reps', 0) or 0), 'due': 0}
                for e in (data.get('queue') or []) if not e.get('confirmed')]
        with S['lock']:
            S['asv'] = {'phase': 'welcome', 'sub': 'ask', 'cur': None,
                        'work': work, 'seen': 0,
                        'got': data.get('got', 0), 'total': data.get('total', 0),
                        'ratio': data.get('ratio', 0.0), 'busy': False,
                        'coins': int(game.get('coins', 0)),
                        'parts': list(game.get('parts', [])),
                        'parts_total': int(game.get('parts_total', 7)),
                        'reveal': None, 'coin_pop': None, 'new_part': None}
        return True

    # ── Sprach-Menü (Alt+L): live zwischen Personas/Sprachen umschalten ──────
    # Der Kern kann das schon (POST /api/tutor/config {lang}); hier ist nur die
    # sichtbare Auswahl im Zimmer statt eines Konsolen-Befehls (/lang). Wechsel =
    # Config setzen (persist) → Session beenden → neu starten, damit die neue
    # Persona in IHRER Sprache frisch begrüßt (active_lang friert beim Start ein).
    def open_lang_menu():
        with S['lock']:
            langs = list(S['langs'])
        if not langs:                       # Cache leer (kickoff-Race) → nachholen
            cf = be.config()
            langs = [l for l in (cf.get('langs') if cf else []) if l.get('enabled')]
        if not langs:
            with S['lock']: S['msg'] = 'keine Sprachen verfügbar'
            return
        with S['lock']:
            cur = S['lang']
            S['langs'] = langs
            S['menu'] = {'sel': next((i for i, l in enumerate(langs)
                                      if l['code'] == cur), 0)}

    def menu_key(ev):
        """Taste im offenen Menü. Gibt einen zu wechselnden Sprachcode zurück
        (Enter/Zifferwahl) oder None (Navigation/Schließen)."""
        with S['lock']:
            m = S['menu']
            if not m:
                return None
            langs = S['langs']; n = len(langs)
            close = (ev.key == pygame.K_ESCAPE) or \
                    (ev.key == pygame.K_l and (ev.mod & pygame.KMOD_ALT))
            if close or n == 0:
                S['menu'] = None; return None
            if ev.key in (pygame.K_UP, pygame.K_k):
                m['sel'] = (m['sel'] - 1) % n; return None
            if ev.key in (pygame.K_DOWN, pygame.K_j):
                m['sel'] = (m['sel'] + 1) % n; return None
            if pygame.K_1 <= ev.key <= pygame.K_9:
                i = ev.key - pygame.K_1
                if i < n:
                    S['menu'] = None; return langs[i]['code']
                return None
            if ev.key == pygame.K_RETURN:
                S['menu'] = None; return langs[m['sel']]['code']
        return None

    def switch_lang(code):
        """Sprache/Persona live umschalten (läuft in einem Thread — Netz + Stream)."""
        with S['lock']:
            same = (code == S['lang'])
            S['menu'] = None
        if same:
            return
        cf = be.set_config({'lang': code, 'persist': True})
        if not cf:
            with S['lock']: S['msg'] = 'Sprachwechsel fehlgeschlagen'
            return
        be.stop()                            # alte Session beenden
        with S['lock']:
            S['lang']    = cf.get('lang', code)
            S['persona'] = cf.get('persona_name', S['persona'])
            S['log']     = []                # neue Persona → eigener Verlauf
            S['last']    = ''; S['buf'] = ''
            S['msg']     = f"→ {S['persona']} ({cf.get('lang_name', '')})"
            foc = S['focused']
        run_stream('/api/tutor/start', {'focus': foc})   # neue Begrüßung

    def kickoff():
        """Status/Config holen; wenn erreichbar und keine Session läuft, die
        Persona von selbst begrüßen lassen (kein Enter — sie quatscht los)."""
        cf = be.config()
        if cf:
            with S['lock']:
                if cf.get('persona_name'):
                    S['persona'] = cf['persona_name']
                if cf.get('lang'):
                    S['lang'] = cf['lang']
                if cf.get('langs'):
                    # nur fertige Sprachen sind wählbar (Skizzen raus)
                    S['langs'] = [l for l in cf['langs'] if l.get('enabled')]
        st = be.status()
        with S['lock']:
            S['available'] = bool(st and st.get('available'))
            S['tts'] = bool(st and st.get('tts'))
            active = bool(st and st.get('active'))
            if st and st.get('privacy_warning'):
                S['msg'] = st['privacy_warning']
        # Steckt die Sprache im Assessment-Gate? Dann die DETERMINISTISCHE Abfrage
        # starten (kein LLM, keine Persona), statt zu begrüßen. Braucht kein
        # Backend-Modell — nur die Vokabel-Dateien + TTS.
        if asv_init():
            return
        if S['available'] and not active:
            with S['lock']:
                foc = S['focused']
            run_stream('/api/tutor/start', {'focus': foc})   # Öffnen = Lage-Meldung

    def watch_status():
        """Status leichtgewichtig nachpollen — damit avail/tts aktuell bleiben,
        wenn das Backend oder der TTS-Service später hoch-/runterkommt."""
        while True:
            pygame.time.wait(4000)
            st = be.status()
            if st is not None:
                with S['lock']:
                    S['available'] = bool(st.get('available'))
                    S['tts'] = bool(st.get('tts'))

    def watch_room():
        """Ausdrucks-Zustand pollen (Haltung/Geste, von der KI per express-Tool
        gesetzt) und ans Fenster reichen. Persona wird NUR im Render-Thread
        mutiert → hier nur S['stance']/S['pending_gesture'] setzen."""
        last_gid = 0; last_tid = 0; last_mid = 0
        while True:
            pygame.time.wait(250)
            rs = be.room_state()
            if not isinstance(rs, dict):
                continue
            gid = int(rs.get('gesture_id') or 0)
            tid = int(rs.get('thought_id') or 0)
            mid = int(rs.get('music_id') or 0)
            with S['lock']:
                S['stance'] = rs.get('stance') or 'idle'
                S['face'] = rs.get('face') or 'neutral'
                S['battery'] = int(rs.get('battery', 60)); S['mood'] = rs.get('mood') or 'ok'
                # Assessment-Gate: Modus + Fortschritt + gerampter Speed
                S['mode'] = rs.get('mode') or 'room'
                S['core_got'] = int(rs.get('core_got') or 0)
                S['core_total'] = int(rs.get('core_total') or 0)
                S['core_ratio'] = float(rs.get('core_ratio') or 0.0)
                if rs.get('tts_speed'):
                    S['tts_speed'] = float(rs['tts_speed'])
                # Deckung von außen auf ≥75 % gesprungen → Drill auf Freischaltung.
                # NUR am echten Deckungswert festmachen (nicht an mode — das kann
                # 'room' sein, obwohl noch gar nicht freigeschaltet).
                if (S['asv'] and S['core_ratio'] >= 0.75
                        and S['asv'].get('phase') != 'unlock'):
                    S['asv']['phase'] = 'unlock'; S['asv']['cur'] = None
                if gid != last_gid:
                    S['pending_gesture'] = rs.get('gesture')
                if tid != last_tid:   # neuer Vokabel-Gedanke → Blase zeigen
                    w = (rs.get('thought_word') or '').strip()
                    S['thought'] = (w, (rs.get('thought_meaning') or '').strip()) if w else None
                    S['thought_id'] = tid
                    S['thought_t'] = THOUGHT_TTL if w else 0.0
                S['tv'] = (bool(rs.get('tv_on')), (rs.get('tv_title') or ''))
                music_now = rs.get('music_mood') if rs.get('music_action') == 'play' else None
            if mid != last_mid:   # neuer Musik-Wunsch (auflegen/stoppen)
                if rs.get('music_action') == 'play':
                    ok = music_play(music_now or 'chill')
                    with S['lock']:
                        S['music'] = music_now if ok else None
                else:
                    music_stop()
                    with S['lock']:
                        S['music'] = None
            last_gid = gid; last_tid = tid; last_mid = mid

    def feedback_loop():
        """Merkt, wenn Sasha eine Weile nichts sagt → EIN Anstoß (die KI schaut/
        winkt/fragt kurz). Danach chillt sie; erst nach ~15 min ein neuer
        Versuch. Gedeckelt = winzige Cloud-Kosten."""
        while True:
            pygame.time.wait(1000)
            now = pygame.time.get_ticks()
            with S['lock']:
                # im Assessment-Drill (asv) NIE die KI anstoßen — kein LLM da drin
                ok = (S['asv'] is None and S['available']
                      and not S['busy'] and not S['streaming'])
                lu = S['last_user_ms']; nudged = S['nudged']; nm = S['nudge_ms']
            if not ok:
                continue
            silence = (now - lu) / 1000.0
            with S['lock']:
                foc = S['focused']
            if not nudged and silence > NUDGE_AFTER_S:
                with S['lock']:
                    S['nudged'] = True; S['nudge_ms'] = now
                run_stream('/api/tutor/nudge', {'focus': foc})
            elif nudged and (now - nm) / 1000.0 > CHILL_RECHECK_S:
                with S['lock']:
                    S['nudge_ms'] = now
                run_stream('/api/tutor/nudge', {'focus': foc})

    with S['lock']:
        S['last_user_ms'] = pygame.time.get_ticks()   # Stille-Uhr ab Fenster-Öffnen
    threading.Thread(target=kickoff, daemon=True).start()
    threading.Thread(target=watch_status, daemon=True).start()
    threading.Thread(target=watch_room, daemon=True).start()
    threading.Thread(target=feedback_loop, daemon=True).start()

    def send(text):
        text = text.strip()
        if not text:
            return
        with S['lock']:
            if S['busy'] or not S['available']:
                return
            S['last_user_ms'] = pygame.time.get_ticks()   # Stille-Uhr zurücksetzen
            S['nudged'] = False
        log_add('user', text)      # in den Verlauf
        threading.Thread(target=run_stream,
                         args=('/api/tutor/respond', {'text': text}), daemon=True).start()

    def _do_transcribe(wav):
        with S['lock']:
            lang = S['lang']; S['transcribing'] = True
        txt, err = be.transcribe(wav, lang)
        with S['lock']:
            S['transcribing'] = False
            if err:
                S['msg'] = 'STT: ' + err     # sichtbar machen statt still scheitern
        t = (txt or '').strip()
        if t and len(t) >= 2:      # winzige Blips/Halluzinationen verwerfen
            send(t)

    def listen_loop():
        """Immer-Zuhören: Dauer-Mikro, webrtcvad segmentiert Sprache; das Mikro
        ist GEGATED, solange die Persona spricht/antwortet (sonst hört sie sich
        selbst). Endpointing: nach MIC_SILENCE_MS Pause → Segment an Whisper.
        Kein Mikro / STT-Libs fehlen → still deaktivieren."""
        try:
            import sounddevice as sd
            import webrtcvad
        except Exception:
            with S['lock']:
                S['mic'] = False; S['mic_err'] = 'STT-Libs fehlen (pip install)'
            return
        n = int(MIC_RATE * MIC_FRAME_MS / 1000)   # samples/Frame
        try:
            vad = webrtcvad.Vad(MIC_VAD_AGGR)
            stream = sd.RawInputStream(samplerate=MIC_RATE, channels=1, dtype='int16', blocksize=n)
            stream.start()
        except Exception:
            with S['lock']:
                S['mic'] = False; S['mic_err'] = 'kein Mikrofon'
            return
        buf = []; in_speech = False; silence = 0; speech = 0
        while True:
            with S['lock']:
                on = S['mic']; gated = S['speaking'] or S['busy'] or S['streaming']
            try:
                data, _ = stream.read(n)
            except Exception:
                pygame.time.wait(20); continue
            if (not on) or gated:
                if in_speech or buf:
                    buf, in_speech, silence, speech = [], False, 0, 0
                    with S['lock']: S['hearing'] = False
                continue
            frame = bytes(data)
            if len(frame) < n * 2:
                continue
            try:
                is_sp = vad.is_speech(frame, MIC_RATE)
            except Exception:
                continue
            if is_sp:
                buf.append(frame); in_speech = True; speech += MIC_FRAME_MS; silence = 0
                with S['lock']: S['hearing'] = True
            elif in_speech:
                buf.append(frame); silence += MIC_FRAME_MS
                if silence >= MIC_SILENCE_MS:
                    with S['lock']: S['hearing'] = False
                    if speech >= MIC_MINSPEECH_MS:
                        threading.Thread(target=_do_transcribe,
                                         args=(_pcm_to_wav(b''.join(buf)),), daemon=True).start()
                    buf, in_speech, silence, speech = [], False, 0, 0
            if (speech + silence) >= MIC_MAX_MS:      # harte Obergrenze
                if speech >= MIC_MINSPEECH_MS:
                    threading.Thread(target=_do_transcribe,
                                     args=(_pcm_to_wav(b''.join(buf)),), daemon=True).start()
                buf, in_speech, silence, speech = [], False, 0, 0
                with S['lock']: S['hearing'] = False

    threading.Thread(target=listen_loop, daemon=True).start()

    running = True
    caret_t = 0.0
    bub_text = ''      # aktuell in der Blase stehender Text
    bub_age  = 999.0   # s seit letztem Sprechen — steuert das Ausblenden
    while running:
        dt = clock.tick(30) / 1000.0
        caret_t += dt
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == getattr(pygame, 'WINDOWFOCUSGAINED', -1):
                with S['lock']: S['focused'] = True    # sie wird angeschaut
            elif ev.type == getattr(pygame, 'WINDOWFOCUSLOST', -2):
                with S['lock']: S['focused'] = False
            elif ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
                persona.layout(ev.w, ev.h)
                set_ime_rect()
            elif ev.type == pygame.TEXTINPUT:
                # fertig committeter Text (bei CJK: das gewählte Zeichen).
                # Bei offenem Menü ODER laufender Abfrage ignorieren.
                with S['lock']:
                    if S['menu'] is None and S['asv'] is None:
                        S['compose'] = ''
                        if len(S['input']) < 200:
                            S['input'] += ev.text
            elif ev.type == pygame.TEXTEDITING:
                # laufende IME-Komposition (Pinyin, noch nicht bestätigt)
                with S['lock']:
                    if S['menu'] is None and S['asv'] is None:
                        S['compose'] = ev.text
            elif ev.type == pygame.KEYDOWN:
                # Offenes Sprach-Menü fängt die Tasten ab (Navigation/Auswahl/
                # Schließen) — kein Reden, kein Quit, keine Texteingabe dahinter.
                with S['lock']:
                    menu_open = S['menu'] is not None
                if menu_open:
                    code = menu_key(ev)
                    if code:
                        threading.Thread(target=switch_lang, args=(code,),
                                         daemon=True).start()
                    continue
                # Deterministische Abfrage: Tasten steuern das Drill (kein Text-
                # Input, kein Reden). Esc/Alt+M bleiben; alles andere → asv_key.
                with S['lock']:
                    asv_on = S['asv'] is not None
                if asv_on:
                    if ev.key == pygame.K_ESCAPE:
                        running = False
                    elif ev.key == pygame.K_m and (ev.mod & pygame.KMOD_ALT):
                        with S['lock']:
                            S['mute'] = not S['mute']; muted = S['mute']
                            S['msg'] = 'stumm' if muted else 'stimme an'
                        if muted:
                            try: pygame.mixer.stop()
                            except Exception: pass
                    else:
                        asv_key(ev)
                    continue
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_l and (ev.mod & pygame.KMOD_ALT):
                    open_lang_menu()                 # Sprache/Persona umschalten
                elif ev.key == pygame.K_m and (ev.mod & pygame.KMOD_ALT):
                    with S['lock']:
                        S['mute'] = not S['mute']
                        muted = S['mute']
                        S['msg'] = 'stumm' if muted else 'stimme an'
                    if muted:
                        try: pygame.mixer.stop()
                        except Exception: pass
                elif ev.key == pygame.K_h and (ev.mod & pygame.KMOD_ALT):
                    with S['lock']:
                        S['mic'] = not S['mic']
                        S['msg'] = 'zuhören an' if S['mic'] else 'mikro aus'
                elif ev.key == pygame.K_RETURN:
                    with S['lock']:
                        txt = S['input']; S['input'] = ''
                    send(txt)
                elif ev.key == pygame.K_BACKSPACE:
                    with S['lock']:
                        S['input'] = S['input'][:-1]
                elif ev.key in (pygame.K_UP, pygame.K_PAGEUP):
                    with S['lock']:
                        S['scroll'] += (3 if ev.key == pygame.K_PAGEUP else 1)
                elif ev.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                    with S['lock']:
                        S['scroll'] = max(0, S['scroll'] - (3 if ev.key == pygame.K_PAGEDOWN else 1))

        w, h = screen.get_size()
        persona.layout(w, h)
        with S['lock']:
            streaming = S['streaming']; speaking = S['speaking']
            buf = S['buf']; last = S['last']; msg = S['msg']
            inp = S['input']; avail = S['available']; pname = S['persona']
            compose = S['compose']; tts_ok = S['tts']
            log = list(S['log']); scroll = S['scroll']
            stance = S['stance']; pend = S['pending_gesture']; S['pending_gesture'] = None
            face = S['face']; battery = S['battery']; mood = S['mood']
            mic = S['mic']; hearing = S['hearing']; transcribing = S['transcribing']; mic_err = S['mic_err']
            if S['thought_t'] > 0:
                S['thought_t'] = max(0.0, S['thought_t'] - dt)
            thought = S['thought'] if S['thought_t'] > 0 else None
            thought_t = S['thought_t']
            music = S['music']; tv_on, tv_title = S['tv']
            menu = S['menu']; menu_langs = list(S['langs']); cur_lang = S['lang']
            mode = S['mode']; core_got = S['core_got']; core_total = S['core_total']
            core_ratio = S['core_ratio']
            # Spiel-Animationen tickern (Kisten-Reveal, Münz-Pop, einschwebendes Teil)
            if S['asv']:
                a2 = S['asv']
                if a2.get('reveal'):
                    a2['reveal']['t'] -= dt
                    if a2['reveal']['t'] <= 0:
                        a2['reveal'] = None
                if a2.get('coin_pop'):
                    a2['coin_pop']['t'] -= dt
                    if a2['coin_pop']['t'] <= 0:
                        a2['coin_pop'] = None
                if a2.get('new_part'):
                    a2['new_part']['t'] = min(1.0, a2['new_part']['t'] + dt / 0.6)
                    if a2['new_part']['t'] >= 1.0:
                        a2['new_part'] = None
            asv_snap = dict(S['asv']) if S['asv'] else None

        # Der Mund bewegt sich NUR, wenn wirklich Text ankommt oder Audio läuft.
        has_text = bool(buf.strip())
        talking  = (streaming and has_text) or speaking
        thinking = streaming and not has_text
        # Haltung/Geste/Mimik kommen von der KI (express-Tool → room_state-Poll).
        # Die Stimmung (soziale Batterie) färbt die Mimik NUR, wenn die KI nicht
        # selbst eine gesetzt hat (dann gewinnt die KI-Mimik).
        eff_face = face if face != 'neutral' else {'low': 'tired', 'happy': 'happy'}.get(mood, 'neutral')
        persona.set_stance(stance)
        persona.set_face(eff_face)
        if pend:
            persona.play_gesture(pend)
        persona.update(dt, talking)

        # Gesagtes „verhallt": solange sie redet/denkt bleibt die Blase frisch,
        # danach altert sie und blendet aus (bub_age). Kein ewiges Herumhängen.
        if avail is False:
            cur = ''
        elif thinking:
            cur = '…'
        elif has_text:
            cur = _clean_speech(buf)   # Regie/Tool-Leak auch in der Live-Blase raus
        elif streaming or speaking:
            cur = last
        else:
            cur = None            # nichts Aktives mehr
        if cur:
            bub_text = cur; bub_age = 0.0
        elif streaming or speaking:
            bub_age = 0.0
        else:
            bub_age += dt

        # zeichnen — HARTES GATE: läuft die deterministische Abfrage (asv), NICHT
        # das Zimmer/die Figur, sondern den Übungs-Screen. Lucías Stimme (TTS)
        # liest die Wörter vor; kein LLM beteiligt.
        if asv_snap is not None:
            draw_assessment(screen, w, h, fonts, asv_snap, speaking, caret_t)
        else:
            draw_room(screen, w, h, caret_t)
            draw_tv(screen, w, h, tv_on, tv_title, fonts['hud'], caret_t)
            persona.draw(screen)

            # Blase mit Ausblenden
            if bub_text and avail is not False and bub_age < BUBBLE_LINGER + BUBBLE_FADE:
                if bub_age <= BUBBLE_LINGER:
                    alpha = 255
                else:
                    alpha = int(255 * max(0.0, 1 - (bub_age - BUBBLE_LINGER) / BUBBLE_FADE))
                draw_bubble(screen, fonts['bubble'], bub_text, persona.x, persona.head_top(), w, alpha)

            # Gedanken-Blase (Vokabel-Hilfe): Wort + Übersetzung (+ Bild, falls da),
            # neben dem Kopf, blendet in der letzten Sekunde aus.
            if thought and avail is not False:
                t_alpha = 255 if thought_t > 1.0 else int(255 * max(0.0, thought_t))
                draw_thought(screen, fonts['bubble'], fonts['log'],
                             thought[0], thought[1], persona.x, persona.head_top(), t_alpha)

        # Persona-HUD (Name, Mic, Laune, Verlaufs-Leiste, Eingabe) NUR im Zimmer.
        # Im Drill (asv) ist der Screen bewusst nackt — draw_assessment trägt alles.
        if asv_snap is None:
            # schläft/nicht erreichbar
            if avail is False:
                zz = fonts['big'].render('zzz…', True, HUD_DIM)
                screen.blit(zz, (int(persona.x)+18, int(persona.head_top())-10))
            elif stance == 'sleep':
                screen.blit(fonts['big'].render('zzz', True, HUD_DIM),
                            (int(persona.x)+18, int(persona.head_top())-6))

            # HUD oben: Name + kompakte Steuerung/Meldung (unten ist jetzt die Leiste)
            screen.blit(fonts['big'].render(pname, True, HUD_FG), (16, 12))
            if msg:
                hint = msg
            elif avail is False:
                hint = 'verbinde…'
            elif avail and not tts_ok:
                hint = '🔇 keine Stimme (tts-service aus?)'
            else:
                hint = '↑/↓ Verlauf · Enter reden · Alt+L Sprache · Alt+M stumm · Esc'
            screen.blit(fonts['hud'].render(hint, True, HUD_DIM), (16, 44))

            # Mic-Indikator (Immer-Zuhören): Zustand + Alt+H
            if mic_err:
                mic_line, mic_col = 'Mic: ' + mic_err, HUD_DIM
            elif not mic:
                mic_line, mic_col = 'Mic aus · Alt+H', HUD_DIM
            elif transcribing:
                mic_line, mic_col = 'Mic: versteht…', ROLE_USER
            elif hearing:
                mic_line, mic_col = 'Mic: hört dich ●', ROLE_USER
            else:
                mic_line, mic_col = 'Mic: hört zu · Alt+H', HUD_DIM
            screen.blit(fonts['hud'].render(mic_line, True, mic_col), (16, 66))
            if music:
                screen.blit(fonts['hud'].render(f'♪ {music}', True, ROLE_USER), (16, 88))

            # Soziale Batterie oben rechts (grün hoch / amber mittel / rot niedrig)
            bw2, bh2 = 92, 12
            bx2, by2 = w - bw2 - 16, 18
            bcol = (120, 200, 120) if mood == 'happy' else ((214, 176, 96) if mood == 'ok' else (214, 112, 112))
            pygame.draw.rect(screen, (44, 38, 48), (bx2, by2, bw2, bh2), border_radius=5)
            pygame.draw.rect(screen, bcol, (bx2 + 2, by2 + 2, int((bw2 - 4) * max(0, min(100, battery)) / 100), bh2 - 4), border_radius=4)
            lab = fonts['hud'].render('Laune', True, HUD_DIM)
            screen.blit(lab, (bx2 - lab.get_width() - 8, by2 - 2))

            # ── Verlaufs-Leiste unten (translucent, umbrechend, ↑/↓ scrollt) ────
            lf = fonts['log']; lh = lf.get_linesize()
            VIS = 3
            input_h = 36
            bar_h = lh * VIS + 10
            bar_y = h - input_h - bar_h
            panel = pygame.Surface((w, bar_h), pygame.SRCALPHA); panel.fill(BAR_BG)
            screen.blit(panel, (0, bar_y))
            tl = _transcript_lines(log, pname, lf, w - 24)
            total = len(tl)
            maxscroll = max(0, total - VIS)
            sc = min(scroll, maxscroll)
            start = max(0, total - VIS - sc)
            for i, (col, ln) in enumerate(tl[start:start + VIS]):
                screen.blit(lf.render(ln, True, col), (12, bar_y + 5 + i*lh))
            if start > 0:                                  # es gibt Älteres oberhalb
                screen.blit(lf.render('↑', True, BAR_DIM), (w - 22, bar_y + 4))
            if sc > 0:                                     # nicht ganz unten
                screen.blit(lf.render('↓', True, BAR_DIM), (w - 22, h - input_h - lh - 2))

            # Eingabezeile ganz unten: Text + laufende IME-Komposition (Pinyin)
            iy = h - input_h + 7
            pygame.draw.rect(screen, INPUT_BG, (0, h - input_h, w, input_h))
            base = fonts['input'].render(inp, True, INPUT_FG)
            screen.blit(base, (14, iy))
            xo = 14 + base.get_width()
            if compose:
                comp = fonts['input'].render(compose, True, CARET)   # Pinyin-Vorschau
                pygame.draw.line(screen, CARET, (xo, iy + comp.get_height() - 1),
                                 (xo + comp.get_width(), iy + comp.get_height() - 1), 1)
                screen.blit(comp, (xo, iy))
                xo += comp.get_width()
            if (caret_t % 1.0) < 0.5:
                screen.blit(fonts['input'].render('▏', True, INPUT_FG), (xo, iy))

        # ── Sprach-Menü-Overlay (Alt+L) ─────────────────────────────────────
        if menu is not None and menu_langs:
            ov = pygame.Surface((w, h), pygame.SRCALPHA); ov.fill((0, 0, 0, 150))
            screen.blit(ov, (0, 0))
            rh = fonts['input'].get_linesize() + 8
            mw = min(380, w - 40)
            mh = 52 + rh * len(menu_langs) + 30
            mx = (w - mw) // 2; my = max(20, (h - mh) // 2)
            pygame.draw.rect(screen, (34, 30, 40), (mx, my, mw, mh), border_radius=12)
            pygame.draw.rect(screen, (96, 86, 104), (mx, my, mw, mh), width=1, border_radius=12)
            screen.blit(fonts['big'].render('Sprache', True, HUD_FG), (mx + 18, my + 14))
            yy = my + 52
            sel = menu.get('sel', 0)
            for i, l in enumerate(menu_langs):
                if i == sel:
                    pygame.draw.rect(screen, (62, 55, 74),
                                     (mx + 8, yy - 2, mw - 16, rh), border_radius=8)
                label = f"{i + 1}. {l.get('persona_name', l['code'])} — {l.get('name', l['code'])}"
                if l['code'] == cur_lang:
                    label += '   ●'
                screen.blit(fonts['input'].render(label, True,
                            HUD_FG if i == sel else HUD_DIM), (mx + 20, yy))
                yy += rh
            screen.blit(fonts['hud'].render('↑/↓ · Enter · 1–9 · Esc', True, HUD_DIM),
                        (mx + 18, yy + 6))

        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
