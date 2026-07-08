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


# ── Stimme: WAV vom Backend abspielen ────────────────────────────────────────
_mixer_lock = threading.Lock()


def play_wav(wav_bytes):
    """Spielt WAV-Bytes über pygame.mixer. Initialisiert den Mixer bei Bedarf auf
    die Sample-Rate der Datei — pygame resampelt NICHT, sonst käme die Stimme
    zu hoch/tief. Gibt den Channel zurück (zum Busy-Pollen) oder None. Schlägt
    Audio fehl (kein Gerät, Pi-ALSA), bleibt es still statt zu crashen."""
    try:
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wf:
            fr = wf.getframerate()
        with _mixer_lock:
            init = pygame.mixer.get_init()
            if not init or init[0] != fr:
                try: pygame.mixer.quit()
                except Exception: pass
                pygame.mixer.init(frequency=fr)
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

    def _pick_next(self):
        if self.sitting:
            # aufstehen und schlendern
            self.sitting = False
            self.want_sit = False
            self.target = random.uniform(self.xmin, self.xmax)
        elif random.random() < 0.45:
            # zur couch und hinsetzen
            self.want_sit = True
            self.target = self.couch_x
        else:
            self.target = random.uniform(self.xmin, self.xmax)

    def update(self, dt, talking):
        self.t += dt
        self.blink -= dt
        if self.blink < 0:
            self.blink = random.uniform(2.2, 5.0)  # nächster Lidschlag

        if talking:
            # redet zugewandt; steht dabei nicht extra auf (auch von der Couch ok)
            self.state = 'talk'
            self.idle_timer = 0.0
            self.facing = 1
            return

        if self.target is not None:
            dx = self.target - self.x
            if abs(dx) > 3:
                sp = 70 * self.scale * dt
                self.x += math.copysign(min(sp, abs(dx)), dx)
                self.facing = 1 if dx > 0 else -1
                self.state = 'walk'
                return
            # ziel erreicht
            self.x = self.target
            self.target = None
            if self.want_sit and abs(self.x - self.couch_x) < 6:
                self.sitting = True
            self.idle_timer = 0.0

        # ruht (steht oder sitzt)
        self.state = 'sit' if self.sitting else 'idle'
        self.idle_timer += dt
        if self.idle_timer > random.uniform(4.5, 8.0):
            self.idle_timer = 0.0
            self._pick_next()

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
        # Arme
        arm_sw = math.sin(self.t * 8.0) * 6 * s if self.state == 'walk' else 0
        pygame.draw.rect(surf, LIMB, (x - 17*s, body_top + 3*s + arm_sw, 6*s, 30*s), border_radius=int(3*s))
        pygame.draw.rect(surf, LIMB, (x + 11*s, body_top + 3*s - arm_sw, 6*s, 30*s), border_radius=int(3*s))

        # Kopf
        hy = body_top - 16*s
        pygame.draw.circle(surf, SKIN, (int(x), int(hy)), int(15*s))
        # Haare (Bob): Kappe oben + zwei seitliche Strähnen
        pygame.draw.circle(surf, HAIR, (int(x), int(hy - 3*s)), int(15*s))
        pygame.draw.rect(surf, SKIN, (x - 15*s, hy, 30*s, 15*s))  # Gesicht frei
        pygame.draw.rect(surf, HAIR, (x - 15*s, hy - 2*s, 5*s, 16*s), border_radius=int(2*s))
        pygame.draw.rect(surf, HAIR, (x + 10*s, hy - 2*s, 5*s, 16*s), border_radius=int(2*s))
        # Augen (blinzelt kurz)
        blinking = self.blink < 0.14
        ex = 5.2*s
        ey = hy + 1*s
        if blinking:
            pygame.draw.line(surf, HAIR, (x - ex - 2*s, ey), (x - ex + 2*s, ey), max(1, int(1.6*s)))
            pygame.draw.line(surf, HAIR, (x + ex - 2*s, ey), (x + ex + 2*s, ey), max(1, int(1.6*s)))
        else:
            pygame.draw.circle(surf, HAIR, (int(x - ex), int(ey)), max(1, int(2*s)))
            pygame.draw.circle(surf, HAIR, (int(x + ex), int(ey)), max(1, int(2*s)))
        # Mund (redet → offen/zu im Takt, sonst kleines Lächeln)
        my = hy + 8*s
        if talking and int(self.t * 8) % 2 == 0:
            pygame.draw.circle(surf, DRESS_DK, (int(x), int(my)), max(2, int(2.6*s)))
        else:
            pygame.draw.arc(surf, DRESS_DK, (x - 5*s, my - 4*s, 10*s, 8*s), math.pi, 2*math.pi, max(1, int(1.6*s)))


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


def _wrap(font, text, max_w):
    """Zeilenumbruch — zeichenweise (CJK hat keine Wort-Grenzen)."""
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
    return lines[:6]


def draw_bubble(surf, font, text, cx, top_y, w):
    if not text:
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
    pygame.draw.rect(surf, BUBBLE_BG, (bx, by, bw, bh), border_radius=14)
    pygame.draw.rect(surf, BUBBLE_BD, (bx, by, bw, bh), 2, border_radius=14)
    # Schnabel Richtung Kopf
    tipx = int(max(bx+18, min(cx, bx+bw-18)))
    pygame.draw.polygon(surf, BUBBLE_BG, [(tipx-9, by+bh-2), (tipx+9, by+bh-2), (tipx, by+bh+12)])
    for i, ln in enumerate(lines):
        surf.blit(font.render(ln, True, BUBBLE_FG), (bx+14, by+10 + i*lh))


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
            pygame.key.set_text_input_rect(pygame.Rect(14, h - 62, max(60, w - 28), 30))
        except Exception:
            pass

    try:
        pygame.key.start_text_input()  # IME/Unicode-Eingabe (auch CJK) einschalten
    except Exception:
        pass
    set_ime_rect()

    fonts = {'bubble': _font(22), 'hud': _font(16), 'input': _font(20), 'big': _font(26, True)}
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
    }

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
        ch = play_wav(wav)
        if ch is None:
            return
        with S['lock']:
            S['speaking'] = True
        try:
            while ch.get_busy():
                pygame.time.wait(60)
        finally:
            with S['lock']:
                S['speaking'] = False

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
            speak(line)   # ihre Stimme (nach dem Stream, Antworten sind kurz)

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

    threading.Thread(target=kickoff, daemon=True).start()
    threading.Thread(target=watch_status, daemon=True).start()

    def send(text):
        text = text.strip()
        if not text:
            return
        with S['lock']:
            if S['busy'] or not S['available']:
                return
        threading.Thread(target=run_stream,
                         args=('/api/tutor/respond', {'text': text}), daemon=True).start()

    running = True
    caret_t = 0.0
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
                elif ev.key == pygame.K_RETURN:
                    with S['lock']:
                        txt = S['input']; S['input'] = ''
                    send(txt)
                elif ev.key == pygame.K_BACKSPACE:
                    with S['lock']:
                        S['input'] = S['input'][:-1]

        w, h = screen.get_size()
        persona.layout(w, h)
        with S['lock']:
            streaming = S['streaming']; speaking = S['speaking']
            buf = S['buf']; last = S['last']; msg = S['msg']
            inp = S['input']; avail = S['available']; pname = S['persona']
            compose = S['compose']; tts_ok = S['tts']

        # Der Mund bewegt sich NUR, wenn wirklich Text ankommt oder Audio läuft —
        # NICHT während der Cloud-Latenz vor dem ersten Token (sonst wackelt der
        # Mund ins Leere und die Blase poppt erst am Stream-Ende auf).
        has_text = bool(buf.strip())
        talking  = (streaming and has_text) or speaking
        thinking = streaming and not has_text
        persona.update(dt, talking)

        # zeichnen
        draw_room(screen, w, h, caret_t)
        persona.draw(screen)

        # Sprechblase: „…" während des Nachdenkens, dann Live-Stream, dann die
        # letzte Zeile stehen lassen.
        if avail is False:
            bubble = ''            # schläft
        elif thinking:
            bubble = '…'
        elif has_text:
            bubble = buf
        else:
            bubble = last
        draw_bubble(screen, fonts['bubble'], bubble, persona.x, persona.head_top(), w)

        # schläft/nicht erreichbar
        if avail is False:
            zz = fonts['big'].render('zzz…', True, HUD_DIM)
            screen.blit(zz, (int(persona.x)+18, int(persona.head_top())-10))

        # HUD: Persona-Name oben, Hinweis/Fehler unten
        screen.blit(fonts['big'].render(pname, True, HUD_FG), (16, 12))
        if msg:
            hint = msg
        elif avail is False:
            hint = 'verbinde…'
        elif avail and not tts_ok:
            hint = 'tippen + Enter · 🔇 keine Stimme (tts-service aus?) · Esc'
        else:
            hint = 'tippen + Enter zum Reden · Alt+M stumm · Esc schließt'
        screen.blit(fonts['hud'].render(hint, True, HUD_DIM), (16, h - 30))

        # Eingabezeile unten: bestätigter Text + laufende IME-Komposition (Pinyin)
        ih = 34
        pygame.draw.rect(screen, INPUT_BG, (0, h - ih*2, w, ih))
        iy = h - ih*2 + 6
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
