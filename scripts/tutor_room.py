#!/usr/bin/env python3
# scripts/tutor_room.py
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
# Backend (core/tutor_session.py, /api/tutor/*). Die Antworten kommen als SSE-
# Token-Stream (wie im Browser/TUI), landen in einer Sprechblase.
#
# Start:
#   venv/bin/python scripts/tutor_room.py [--url http://host:5000]
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
_VOCAB_IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'vocab_images')
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
    bx = max(8, int(cx - cw - 70))
    by = max(8, int(top_y - ch - 24))
    tmp = pygame.Surface((cw, ch + 16), pygame.SRCALPHA)
    pygame.draw.rect(tmp, THOUGHT_BG, (0, 0, cw, ch), border_radius=16)
    y = 10
    if img:
        tmp.blit(pygame.transform.smoothscale(img, (iw, ih)), ((cw - iw) // 2, y)); y += ih + 6
    tmp.blit(w_word, ((cw - w_word.get_width()) // 2, y)); y += w_word.get_height() + 3
    if w_mean:
        tmp.blit(w_mean, ((cw - w_mean.get_width()) // 2, y))
    pygame.draw.circle(tmp, THOUGHT_BG, (cw - 14, ch + 3), 6)   # Trail Richtung Kopf
    pygame.draw.circle(tmp, THOUGHT_BG, (cw - 4, ch + 11), 4)
    if alpha < 255:
        tmp.set_alpha(alpha)
    surf.blit(tmp, (bx, by))
# Feedback-Loop (gedeckelt, damit die Cloud-Kosten winzig bleiben): nach kurzer
# Stille EIN Anstoß (die KI schaut/winkt/fragt), danach chillt sie — client-
# seitig, kostenlos. Bleibt das Fenster offen, alle ~15 min ein neuer Versuch.
NUDGE_AFTER_S   = 25.0    # s Stille bis zum ersten Anstoß
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
MUSIC_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'persona_music')
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
             'big': _font(26, True), 'log': _font(18)}
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
        wav = be.speak(text, lang, a.speaker, a.speed)
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
            line = S['buf'].strip()
            if line:
                S['last'] = line
        if not err and line:
            log_add('tutor', line)   # in den Verlauf
            speak(line)              # ihre Stimme (nach dem Stream, Antworten sind kurz)
        # buf jetzt leeren, damit die Blase verhallen KANN — sonst hält der
        # stehengebliebene Text has_text ewig true und bub_age wird nie größer.
        with S['lock']:
            S['buf'] = ''

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
        st = be.status()
        with S['lock']:
            S['available'] = bool(st and st.get('available'))
            S['tts'] = bool(st and st.get('tts'))
            active = bool(st and st.get('active'))
            if st and st.get('privacy_warning'):
                S['msg'] = st['privacy_warning']
        if S['available'] and not active:
            run_stream('/api/tutor/start', {})

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
                ok = S['available'] and not S['busy'] and not S['streaming']
                lu = S['last_user_ms']; nudged = S['nudged']; nm = S['nudge_ms']
            if not ok:
                continue
            silence = (now - lu) / 1000.0
            if not nudged and silence > NUDGE_AFTER_S:
                with S['lock']:
                    S['nudged'] = True; S['nudge_ms'] = now
                run_stream('/api/tutor/nudge', {})
            elif nudged and (now - nm) / 1000.0 > CHILL_RECHECK_S:
                with S['lock']:
                    S['nudge_ms'] = now
                run_stream('/api/tutor/nudge', {})

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
            elif ev.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((ev.w, ev.h), pygame.RESIZABLE)
                persona.layout(ev.w, ev.h)
                set_ime_rect()
            elif ev.type == pygame.TEXTINPUT:
                # fertig committeter Text (bei CJK: das gewählte Zeichen)
                with S['lock']:
                    S['compose'] = ''
                    if len(S['input']) < 200:
                        S['input'] += ev.text
            elif ev.type == pygame.TEXTEDITING:
                # laufende IME-Komposition (Pinyin, noch nicht bestätigt)
                with S['lock']:
                    S['compose'] = ev.text
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
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
            cur = buf
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

        # zeichnen
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
            hint = '↑/↓ Verlauf · Enter reden · Alt+M stumm · Esc'
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

        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
