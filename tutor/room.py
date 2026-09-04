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

# Das Rig (gemalte Einzelteile). Fehlt es, laeuft die alte Polygon-Figur —
# room.py bleibt also auch ohne tutor/sprites.py lauffaehig.
try:
    from tutor import sprites as _sprites
except ImportError:      # als Skript gestartet: tutor/ liegt selbst im Pfad
    try:
        import sprites as _sprites
    except ImportError:
        _sprites = None

# Umrechnung zwischen den Einheiten der alten Polygon-Figur und Sashas
# Mal-Leinwand: eine Einheit hier sind so viele Pixel dort. Ergibt sich aus
# rig.json (Figur 93 Einheiten hoch, auf der Leinwand 558 Pixel).
_LEINWAND_PRO_EINHEIT = 6.0

# ── Palette — an ZENTRALE gekoppelt (night = dunkel, day = hell) ─────────────
# Alle Farbnamen sind Modul-Globals; `apply_theme()` setzt sie je nach Modus um.
# Die Draw-Funktionen lesen die Globals zur Laufzeit → Umschalten wirkt sofort.
# Quelle ist dieselbe Datei wie fürs Terminal: ~/.config/zentrale/theme
# (auto|day|night); auto → day 5–21 Uhr, sonst night.
_NIGHT = dict(
    WALL_TOP=(58, 47, 62), WALL_BOT=(74, 60, 74),
    FLOOR_TOP=(92, 66, 48), FLOOR_BOT=(66, 46, 33),
    RUG=(140, 74, 66), RUG_RING=(176, 104, 92),
    COUCH=(92, 108, 120), COUCH_DK=(70, 84, 96), COUCH_LT=(116, 134, 148),
    WINDOW_SKY=(36, 52, 82), WINDOW_FR=(150, 132, 120), MOON=(226, 224, 198),
    PLANT=(78, 120, 70), POT=(150, 92, 62), LAMP_GLOW=(255, 224, 150),
    SKIN=(240, 206, 178), HAIR=(44, 34, 40), DRESS=(196, 74, 74),
    DRESS_DK=(156, 54, 54), LIMB=(232, 196, 168),
    BUBBLE_BG=(250, 248, 240), BUBBLE_FG=(32, 28, 30), BUBBLE_BD=(210, 205, 194),
    HUD_FG=(206, 194, 200), HUD_DIM=(150, 138, 146),
    INPUT_BG=(40, 33, 42), INPUT_FG=(238, 232, 236), CARET=(226, 150, 150),
    BAR_BG=(16, 12, 20, 214), ROLE_USER=(150, 200, 230),
    ROLE_TUTOR=(240, 202, 172), BAR_DIM=(128, 118, 128),
    THOUGHT_BG=(240, 242, 250), THOUGHT_FG=(40, 44, 60), THOUGHT_SUB=(96, 102, 128),
    # Assessment-Screen
    ASSESS_TOP=(28, 36, 52), ASSESS_BOT=(40, 50, 70),
    ASSESS_ACC=(150, 200, 230), ASSESS_GOLD=(240, 206, 120),
    ASSESS_INK=(236, 238, 246), ASSESS_INK2=(210, 218, 230),
    ASSESS_PANEL=(26, 32, 46, 235), ASSESS_KEY_INK=(16, 22, 32),
    ASSESS_BAR_BG=(20, 26, 38), ASSESS_NODE=(66, 78, 98), ASSESS_NODE_EDGE=(104, 118, 138),
    COIN_HI=(246, 214, 128), COIN_LO=(206, 158, 66),
    # Vokabel-Karte: Papier bleibt Papier, in beiden Themes. Eine Karteikarte,
    # die sich mitfaerbt, sieht nicht mehr nach Karte aus.
    KARTE_BG=(246, 242, 232), KARTE_INK=(34, 38, 50), KARTE_RAND=(206, 198, 182),
    KARTE_RUECK=(232, 226, 212), KARTE_SUB=(122, 116, 104), KARTE_STAPEL=(214, 208, 194),
)
_DAY = dict(
    WALL_TOP=(236, 231, 240), WALL_BOT=(248, 244, 250),
    FLOOR_TOP=(214, 186, 156), FLOOR_BOT=(192, 162, 132),
    RUG=(206, 140, 126), RUG_RING=(224, 166, 150),
    COUCH=(158, 178, 194), COUCH_DK=(130, 152, 170), COUCH_LT=(196, 212, 226),
    WINDOW_SKY=(158, 196, 232), WINDOW_FR=(176, 156, 138), MOON=(250, 232, 158),
    PLANT=(104, 158, 94), POT=(176, 116, 80), LAMP_GLOW=(255, 238, 182),
    SKIN=(240, 206, 178), HAIR=(60, 46, 54), DRESS=(198, 80, 80),
    DRESS_DK=(160, 58, 58), LIMB=(232, 196, 168),
    BUBBLE_BG=(252, 250, 244), BUBBLE_FG=(40, 34, 36), BUBBLE_BD=(206, 198, 186),
    HUD_FG=(58, 50, 62), HUD_DIM=(120, 110, 122),
    INPUT_BG=(232, 226, 236), INPUT_FG=(44, 38, 46), CARET=(198, 90, 90),
    BAR_BG=(250, 246, 252, 222), ROLE_USER=(52, 116, 168),
    ROLE_TUTOR=(176, 96, 58), BAR_DIM=(150, 140, 150),
    THOUGHT_BG=(248, 250, 255), THOUGHT_FG=(40, 44, 60), THOUGHT_SUB=(96, 102, 128),
    ASSESS_TOP=(228, 236, 246), ASSESS_BOT=(206, 220, 236),
    ASSESS_ACC=(48, 120, 172), ASSESS_GOLD=(184, 138, 36),
    ASSESS_INK=(38, 44, 58), ASSESS_INK2=(72, 84, 104),
    ASSESS_PANEL=(248, 250, 253, 238), ASSESS_KEY_INK=(248, 250, 252),
    ASSESS_BAR_BG=(206, 214, 226), ASSESS_NODE=(200, 208, 220), ASSESS_NODE_EDGE=(150, 162, 178),
    COIN_HI=(214, 158, 58), COIN_LO=(176, 128, 44),
    KARTE_BG=(252, 250, 244), KARTE_INK=(34, 38, 50), KARTE_RAND=(196, 190, 176),
    KARTE_RUECK=(238, 233, 220), KARTE_SUB=(122, 116, 104), KARTE_STAPEL=(220, 214, 200),
)
_THEMES = {'night': _NIGHT, 'day': _DAY}


def apply_theme(mode):
    """Farb-Globals auf night(dunkel)/day(hell) setzen. Unbekannt → night."""
    globals().update(_THEMES.get(mode, _NIGHT))


def resolve_theme_mode():
    """Die geltende Farbe (day|night) aus ~/.config/zentrale/theme.now.

    Aufgelöst wird an genau einer Stelle im Projekt, in scripts/zentrale-themed;
    hier steht deshalb bewusst kein Uhrzeit-Code. Fehlt die Datei → night."""
    try:
        pfad = os.environ.get('ZENTRALE_THEME_NOW') or os.path.expanduser(
            '~/.config/zentrale/theme.now')
        with open(pfad) as fh:
            wert = fh.read().strip().lower()
    except Exception:
        return 'night'
    return 'day' if wert == 'day' else 'night'


apply_theme('night')   # Default, bis der echte Modus gelesen ist

# Gesagtes „verhallt": Blase steht kurz voll, dann blendet sie aus.
BUBBLE_LINGER = 4.0   # s voll sichtbar nach dem Sprechen
BUBBLE_FADE   = 1.3   # s Ausblenden danach
THOUGHT_TTL   = 6.0   # s Gedanken-Blase sichtbar, dann aus
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


# Schrift-Kandidaten in Wunsch-Reihenfolge. CJK zuerst (Ling Ling schreibt
# Mandarin), Latein danach — für Lucía reicht DejaVu.
_FONT_KANDIDATEN = ("notosanscjksc", "notosansmonocjksc", "droidsansfallback",
                    "dejavusans", "liberationsans", "freesans")
_font_wahl = None       # einmal ermittelt, dann für alle Größen wiederverwendet


# Zeichen, die in der Oberfläche vorkommen und NICHT in jeder Schrift stecken.
# Fehlt eines, wird es durch seinen ASCII-Ersatz getauscht — lieber ein »>« als
# ein leeres Kästchen.
_SYMBOL_ERSATZ = {"↑": "^", "↓": "v", "←": "<", "→": "->", "✓": "ok",
                  "·": "-", "—": "-", "’": "'", "…": "...", "▣": "[+]",
                  "◗": ">", "«": "\"", "»": "\"", "◆": "*", "▸": ">"}
_fehlende_symbole = set()


def _malt_zeichen(f, zeichen):
    """Kommen beim Rendern dieses Zeichens überhaupt Pixel heraus?

    Die einzige verlässliche Frage. `metrics()` und `size()` melden Zeichen als
    vorhanden, die dann als leeres Kästchen oder als gar nichts erscheinen —
    beides ist auf dem Pi passiert (DroidSansFallback: Kästchen; Ugly Form:
    Akzente unsichtbar). Deshalb wird gerendert und nachgesehen.
    """
    try:
        s = f.render(zeichen, True, (255, 255, 255))
    except Exception:
        return False
    w, h = s.get_size()
    if w == 0 or h == 0:
        return False
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            if s.get_at((x, y))[3] > 40:
                return True
    return False


def _rendert_wirklich(f):
    """Malt diese Schrift Buchstaben — oder nur leere Kästchen?

    Am Pi war genau das der Fall: die Wunschliste löste auf
    DroidSansFallbackFull.ttf auf, und diese Datei lieferte für JEDES Zeichen
    dasselbe leere Kästchen. Das Tückische daran ist, dass sich die Schrift
    nicht als kaputt meldet — `metrics()` behauptet, alle Glyphen seien da,
    und `size()` gibt sogar plausible, unterschiedliche Breiten zurück. Erst
    das GERENDERTE Bild verrät es.

    Deshalb die Probe am Bild: zwei gleich lange Strings, die in jeder echten
    Schrift verschieden breit sind. Kommt dasselbe heraus, ist jedes Zeichen
    gleich breit — also ein Kästchen.
    """
    try:
        schmal = f.render("iiii", True, (255, 255, 255)).get_width()
        breit = f.render("MMMM", True, (255, 255, 255)).get_width()
    except Exception:
        return False
    return breit > schmal * 1.2


def _font(size, bold=False):
    """Schrift, die auf DIESER Maschine auch wirklich lesbar rendert.

    Zwei Bedingungen, beide gelernt statt gedacht:

    1. Die Schrift muss es GEBEN. `SysFont` liefert für einen unbekannten
       Namen klaglos die Standardschrift zurück — die besteht dann jede Probe,
       ist aber nicht die gewünschte. Genau so landete der Pi auf einer
       Schrift ohne Pfeile, obwohl DejaVu (mit Pfeilen) dagestanden hätte.
       `match_font` sagt, ob der Name wirklich auflöst.
    2. Sie muss Buchstaben malen statt Kästchen (siehe _rendert_wirklich).

    Welche Sonderzeichen die gewählte Schrift kann, wird einmal mitgeprüft und
    in _fehlende_symbole gemerkt; _sym() tauscht die fehlenden dann aus.
    """
    global _font_wahl
    if _font_wahl is None:
        for name in _FONT_KANDIDATEN:
            if not pygame.font.match_font(name):
                continue                      # gibt es hier gar nicht
            probe = pygame.font.SysFont(name, 24)
            if probe and _rendert_wirklich(probe):
                _font_wahl = name
                break
        else:
            _font_wahl = ""      # nichts brauchbar -> pygame-Default
        pruef = (pygame.font.SysFont(_font_wahl, 24) if _font_wahl
                 else pygame.font.Font(None, 24))
        _fehlende_symbole.update(z for z in _SYMBOL_ERSATZ
                                 if not _malt_zeichen(pruef, z))
    if not _font_wahl:
        return pygame.font.Font(None, size)
    f = pygame.font.SysFont(_font_wahl, size, bold=bold)
    return f or pygame.font.Font(None, size)


def _sym(text):
    """Sonderzeichen ersetzen, die die gewählte Schrift nicht malen kann.

    Aufgerufen an jeder Stelle, wo ein Pfeil oder Häkchen im Text steht. Auf
    einer Maschine mit vollständiger Schrift ändert sich nichts.
    """
    if not _fehlende_symbole:
        return text
    for zeichen in _fehlende_symbole:
        if zeichen in text:
            text = text.replace(zeichen, _SYMBOL_ERSATZ[zeichen])
    return text


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

    def _post(self, path, koerper, timeout=8):
        try:
            req = urllib.request.Request(
                self.url + path,
                data=json.dumps(koerper).encode('utf-8'),
                method='POST', headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8', 'replace'))
        except Exception:
            return None

    # ── Spielstände ──────────────────────────────────────────────────────
    def staende(self):
        """GET /api/tutor/staende → {aktiv, staende:[…]}. None bei Fehler."""
        return self._get('/api/tutor/staende', timeout=5.0)

    def stand_neu(self, name=None):
        """Neuen Spielstand anlegen und aktivieren."""
        return self._post('/api/tutor/staende', {'name': name or ''})

    def stand_waehlen(self, sid):
        """Auf einen vorhandenen Spielstand umschalten."""
        return self._post('/api/tutor/staende/waehlen', {'id': sid})

    def stand_loeschen(self, sid):
        """Einen Spielstand samt allem Gelernten entfernen."""
        return self._post('/api/tutor/staende/loeschen', {'id': sid})

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
        # Gemalte Teile, falls vorhanden (tutor/assets/figuren/lucia/). Liegt da nichts,
        # bleibt es bei der Polygon-Figur — siehe draw().
        self.rig = _sprites.lade_rig('lucia') if _sprites is not None else None
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

    # -- Gemalte Puppe (Rig) -------------------------------------------------
    # Winkel-Konvention für alle Gliedmassen: 0° = Teil hängt gerade nach
    # unten (so, wie es gemalt wurde), +90° = zeigt nach rechts, -90° = links.
    # Ein Teil dreht sich immer um seinen Drehpunkt aus rig.json.
    #
    # Die Zahlen unten sind die Gelenkpositionen der alten Polygon-Figur in
    # ihren eigenen Einheiten (bei scale=1, gemessen vom Fusspunkt). Genau
    # diese Punkte sind in rig.json auf die Mal-Leinwand umgerechnet — ein
    # Schritt in den Einheiten hier entspricht _LEINWAND_PRO_EINHEIT Pixeln
    # auf Sashas Leinwand.
    _OBERARM = 15.0
    _UNTERARM = 15.0
    _OBERSCHENKEL = 14.0
    _UNTERSCHENKEL = 14.0

    def _winkel_pose(self, talking, sitting):
        """Liefert die Winkel aller Gliedmassen für den aktuellen Zustand."""
        g = self.gesture
        gp = (1.3 - self.gesture_t) * 7.0
        walking = self.state == 'walk'

        # Ruhelage: Arme hängen leicht abgespreizt am Körper
        al, ar = -7.0, 7.0            # Oberarme
        alu, aru = -3.0, 3.0          # Unterarme
        if walking:
            sw = math.sin(self.t * 8.0) * 24.0
            al, ar = -7.0 + sw, 7.0 - sw
        elif talking:
            # beim Reden leichtes Mitgestikulieren
            sw = math.sin(self.t * 3.4) * 6.0
            al, ar = -12.0 - sw, 12.0 + sw
            alu, aru = -10.0 - sw, 10.0 + sw

        if g == 'wave':
            ar = 158.0
            aru = 150.0 + math.sin(gp) * 22.0
        elif g in ('stretch', 'arms_up'):
            al, ar = -168.0, 168.0
            alu, aru = -172.0, 172.0
        elif g == 'shrug':
            al, ar = -28.0, 28.0
            alu, aru = -62.0, 62.0
        elif g == 'cross_arms':
            # Oberarme hängen fast senkrecht, Unterarme quer VOR den Körper —
            # also zur Mitte hin, nicht nach aussen.
            al, ar = -22.0, 22.0
            alu, aru = 78.0, -78.0

        # Beine
        bl = br = 0.0
        blu = bru = 0.0
        if walking:
            sw = math.sin(self.t * 8.0) * 19.0
            bl, br = sw, -sw
            blu, bru = max(0.0, -sw * 0.5), max(0.0, sw * 0.5)
        elif sitting:
            bl, br = -13.0, 13.0

        # Nicken: der Kopf senkt sich (positiv = nach unten), dazu ein Hauch
        # Kippen — in der Frontalansicht ist das Absenken die ehrliche Lösung.
        nod = abs(math.sin(gp)) * 6.0 if g == 'nod' else 0.0
        kopf = math.sin(self.t * 1.7) * 1.5
        return dict(arm_l=al, arm_r=ar, arm_l_u=alu, arm_r_u=aru,
                    bein_l=bl, bein_r=br, bein_l_u=blu, bein_r_u=bru,
                    kopf=kopf, nod=nod)

    def _gesicht_varianten(self, talking):
        """Welche Augen-/Mundbilder gerade gelten (Mimik + Lidschlag + Reden)."""
        sleeping = (self.stance == 'sleep')
        blinking = self.blink < 0.14
        face = self.face
        if sleeping or face == 'tired' or blinking:
            auge = 'zu'
        elif face == 'surprised':
            auge = 'weit'
        else:
            auge = 'offen'
        if talking:
            mund = 'offen' if int(self.t * 8) % 2 == 0 else 'zu'
        elif face == 'surprised':
            mund = 'offen'
        elif face == 'sad':
            mund = 'traurig'
        elif face == 'tired' or sleeping:
            mund = 'strich'
        elif face == 'happy':
            mund = 'laecheln'
        else:
            mund = 'zu'
        return auge, mund

    def draw(self, surf):
        """Zeichnet die Persona — gemalt, wenn Bilder da sind, sonst klassisch.

        Solange in tutor/assets/figuren/lucia/ kein einziges Teil liegt, läuft exakt
        die alte Polygon-Figur. Sobald das erste Bild auftaucht, wird die
        Puppe gebaut: gemalte Teile werden gezeichnet, noch fehlende als
        schlichter Platzhalter — so kann Teil für Teil entstehen."""
        rig = getattr(self, 'rig', None)
        if rig is None or not rig.aktiv or rig.leer():
            return self._draw_klassisch(surf)
        rig.aktualisieren()
        self._draw_rig(surf, rig)

    def _draw_rig(self, surf, rig):
        s = self.scale
        talking = self.state == 'talk'
        sitting = self.sitting or self.state == 'sit'
        base_y = (self.couch_seat_y if sitting else self.floor_y)
        if talking:
            bob = math.sin(self.t * 7.0) * 2.2 * s
        elif self.state == 'walk':
            bob = abs(math.sin(self.t * 8.0)) * 3 * s
        else:
            bob = math.sin(self.t * 3.0) * 2 * s
        x = self.x
        y = base_y + bob
        # Massstab kommt aus dem Bauplan, nicht aus einer Konstante — so
        # darf die gemalte Figur anders proportioniert sein als die alte.
        sk = s / rig.einheiten_faktor()     # Mal-Leinwand → Bildschirm

        w = self._winkel_pose(talking, sitting)
        auge_v, mund_v = self._gesicht_varianten(talking)

        def spitze(px, py, winkel, laenge):
            r = math.radians(winkel)
            return (px + math.sin(r) * laenge * s, py + math.cos(r) * laenge * s)

        # Gelenke in Bildschirm-Koordinaten
        huefte = (x, y - 22 * s)
        nacken = (x, y - 64 * s + w['nod'] * s)
        schulter_l = (x - 14 * s, y - 59 * s)
        schulter_r = (x + 14 * s, y - 59 * s)
        ellbogen_l = spitze(*schulter_l, w['arm_l'], self._OBERARM)
        ellbogen_r = spitze(*schulter_r, w['arm_r'], self._OBERARM)
        bein_l = (x - 5 * s, y - 26 * s)
        bein_r = (x + 5 * s, y - 26 * s)
        knie_l = spitze(*bein_l, w['bein_l'], self._OBERSCHENKEL)
        knie_r = spitze(*bein_r, w['bein_r'], self._OBERSCHENKEL)
        # Kopfmitte, damit Augen/Mund mitwandern
        kopf_m = (nacken[0], nacken[1] - 14 * s)
        auge_ly = (kopf_m[0] - 5.2 * s, kopf_m[1] + 1 * s)
        auge_ry = (kopf_m[0] + 5.2 * s, kopf_m[1] + 1 * s)
        mund_p = (kopf_m[0], kopf_m[1] + 8 * s)

        pose = {
            'torso':        (huefte,      0.0,          None),
            'kopf':         (nacken,      w['kopf'],    None),
            'arm_l_ober':   (schulter_l,  w['arm_l'],   None),
            'arm_l_unter':  (ellbogen_l,  w['arm_l_u'], None),
            'arm_r_ober':   (schulter_r,  w['arm_r'],   None),
            'arm_r_unter':  (ellbogen_r,  w['arm_r_u'], None),
            'bein_l_ober':  (bein_l,      w['bein_l'],  None),
            'bein_l_unter': (knie_l,      w['bein_l_u'], None),
            'bein_r_ober':  (bein_r,      w['bein_r'],  None),
            'bein_r_unter': (knie_r,      w['bein_r_u'], None),
            'auge_l':       (auge_ly,     w['kopf'],    auge_v),
            'auge_r':       (auge_ry,     w['kopf'],    auge_v),
            'mund':         (mund_p,      w['kopf'],    mund_v),
        }

        for slot in rig.reihenfolge:
            eintrag = pose.get(slot)
            if eintrag is None:
                continue
            (px, py), winkel, variante = eintrag
            if not rig.zeichne(surf, slot, px, py, sk, winkel, variante):
                self._platzhalter(surf, slot, px, py, winkel, s)

    def _platzhalter(self, surf, slot, px, py, winkel, s):
        """Grobe Form für ein noch nicht gemaltes Teil — damit die Puppe
        vollständig aussieht, während Sasha sie Stück für Stück malt."""
        def balken(farbe, laenge, dicke):
            r = math.radians(winkel)
            ex = px + math.sin(r) * laenge * s
            ey = py + math.cos(r) * laenge * s
            pygame.draw.line(surf, farbe, (px, py), (ex, ey), max(2, int(dicke * s)))
            pygame.draw.circle(surf, farbe, (int(ex), int(ey)), max(1, int(dicke * s / 2)))

        if slot == 'torso':
            pygame.draw.polygon(surf, DRESS, [
                (px - 15 * s, py), (px + 15 * s, py),
                (px + 12 * s, py - 40 * s), (px - 12 * s, py - 40 * s)])
        elif slot == 'kopf':
            pygame.draw.circle(surf, SKIN, (int(px), int(py - 14 * s)), int(15 * s))
            pygame.draw.circle(surf, HAIR, (int(px), int(py - 17 * s)), int(15 * s))
            pygame.draw.rect(surf, SKIN, (px - 15 * s, py - 14 * s, 30 * s, 15 * s))
        elif slot.startswith('arm'):
            balken(LIMB, self._OBERARM if slot.endswith('ober') else self._UNTERARM, 6)
        elif slot.startswith('bein'):
            balken(LIMB, self._OBERSCHENKEL if slot.endswith('ober') else self._UNTERSCHENKEL, 8)
        elif slot.startswith('auge'):
            pygame.draw.circle(surf, HAIR, (int(px), int(py)), max(1, int(2 * s)))
        elif slot == 'mund':
            pygame.draw.arc(surf, DRESS_DK, (px - 5 * s, py - 4 * s, 10 * s, 8 * s),
                            math.pi, 2 * math.pi, max(1, int(1.6 * s)))

    def _draw_klassisch(self, surf):
        """Die alte Figur aus pygame-Primitiven. Läuft unverändert weiter,
        solange in tutor/assets/figuren/<name>/ noch KEIN einziges Teil gemalt ist."""
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
               'watch_tv', 'turn_off_tv', 'get_local_news', 'get_due_reviews',
               'get_confirmed_vocab', 'get_testing_vocab', 'increment_correct_use',
               'introduce_new', 'get_structures', 'introduce_structure',
               'increment_structure')
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
# das Rendering. Freischaltung, wenn ALLE Wörter durch sind (100 %), dann übernimmt das Zimmer.
KARTE_BG    = (246, 242, 232)     # Papier
KARTE_INK   = (34, 38, 50)        # Tinte
KARTE_RAND  = (206, 198, 182)
KARTE_RUECK = (232, 226, 212)     # Rückseite, einen Hauch dunkler
KARTE_SUB   = (122, 116, 104)
KARTE_STAPEL= (214, 208, 194)     # die Karten dahinter

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
# Wie viele Karten man per ← zurueckblaettern kann. Genug, um das eben
# Gesehene nachzuschlagen — kein Sitzungsprotokoll.
VERLAUF_MAX = 20

# Wie oft ein Wort gewusst werden muss, bis es aus dem Stapel verschwindet.
# Vorher ergab sich das still aus der Länge der Ladder (also 4×) — jetzt steht
# es als eigene Zahl da, weil es die Stellschraube ist, an der man dreht.
FERTIG_NACH = 3

# Session-SR: expanding-retrieval-Abstände (in Karten VORAUS im Stapel). Sashas
# Ladder, deckt sich mit der Forschung (~2× wachsend, gut für Kurzzeit-Retention).
SR_LADDER = (7, 14, 25)   # 1./2./3. korrektes Abhaken → so viele Karten voraus
SR_LAPSE  = 3             # nicht gewusst (Repeat) → in ~3 Karten wieder
SR_SKIP   = 5             # Next (übersprungen, ohne Wertung) → ein paar voraus


def _draw_coin(surf, cx, cy, r):
    """Kleine Münze (Farbverlauf angedeutet) — Währungs-HUD."""
    pygame.draw.circle(surf, COIN_LO, (int(cx), int(cy)), int(r))
    pygame.draw.circle(surf, COIN_HI, (int(cx), int(cy)), int(r), max(1, int(r * 0.28)))
    pygame.draw.circle(surf, COIN_HI, (int(cx - r * 0.3), int(cy - r * 0.3)), max(1, int(r * 0.28)))


def _draw_lucia(surf, cx, cy, s, parts, anim=None, boden=True):
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

    # Boden-Schatten (nur wenn schon etwas da ist). `boden=False` fuer die
    # Nahaufnahme im Geschenk — dort verzerrt der Schatten die Mittelpunkt-
    # Berechnung, weil er weit unter dem eigentlichen Teil liegt.
    if pset and boden:
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
    items = [(_sym(k), _sym(l)) for k, l in items]
    widths = [(font.size(k)[0] + 16) + 8 + font.size(l)[0] for k, l in items]
    x = cx - (sum(widths) + gap * (len(items) - 1)) // 2
    for (k, l), wd in zip(items, widths):
        ks = font.render(_sym(k), True, ASSESS_KEY_INK); kw = ks.get_width() + 16
        pygame.draw.rect(screen, ASSESS_ACC, (x, y, kw, font.get_height() + 8), border_radius=7)
        screen.blit(ks, (x + 8, y + 4))
        screen.blit(font.render(l, True, HUD_FG), (x + kw + 8, y + 4))
        x += wd + gap


def _draw_coin_hud(screen, fonts, asv, cx, cy):
    """Münz-Konto — mittig unter der Tastenzeile.

    Stand vorher oben rechts in der Ecke, also da, wo man beim Lernen nie
    hinschaut: der Blick klebt an der Karte. Unter den Tasten liegt es im
    selben Blickfeld wie alles, was man gerade tut.
    """
    coins = int(asv.get('coins', 0))
    txt = fonts['big'].render(str(coins), True, COIN_HI)
    r = 10
    ganz = txt.get_width() + 8 + r * 2
    links = cx - ganz // 2
    screen.blit(txt, (links, cy - txt.get_height() // 2))
    _draw_coin(screen, links + txt.get_width() + 8 + r, cy, r)


def _draw_crate_icon(screen, cx, cy, groesse, erreicht):
    """Ein Meilenstein auf der Fortschrittsleiste: ein kleines Geschenk.

    Erreichte Geschenke sind golden und haben eine Schleife, noch offene
    stehen blass daneben — man sieht auf einen Blick, was schon geholt ist und
    was noch kommt. Vorher waren das graue Klötzchen, denen man nicht ansah,
    dass etwas drin ist.
    """
    b = max(8, int(groesse))
    h = int(b * 0.86)
    koerper = pygame.Rect(0, 0, b, h)
    koerper.center = (cx, cy + 1)

    if erreicht:
        papier, band, schleife = ASSESS_GOLD, COIN_LO, ASSESS_GOLD
    else:
        papier, band, schleife = ASSESS_NODE, ASSESS_NODE_EDGE, ASSESS_NODE_EDGE

    # Deckel sitzt etwas breiter auf dem Körper — macht es als Päckchen lesbar.
    deckel = pygame.Rect(0, 0, b + 4, max(3, int(h * 0.30)))
    deckel.midbottom = (cx, koerper.top + int(h * 0.30))

    pygame.draw.rect(screen, papier, koerper, border_radius=2)
    pygame.draw.rect(screen, papier, deckel, border_radius=2)
    # Senkrechtes Band
    pygame.draw.line(screen, band, (cx, koerper.top), (cx, koerper.bottom), 2)
    # Schleife: zwei kleine Ohren auf dem Deckel
    ohr = max(2, b // 5)
    pygame.draw.circle(screen, schleife, (cx - ohr, deckel.top - 1), ohr, 0 if erreicht else 1)
    pygame.draw.circle(screen, schleife, (cx + ohr, deckel.top - 1), ohr, 0 if erreicht else 1)

def _draw_coin_drop(surf, fonts, x, y0, asv):
    """Münze fällt an der Karte runter — mit der Zahl daneben.

    Ohne Zahl sieht man nur, DASS es etwas gab, nicht wie viel. Sie steht mit
    »+« davor direkt neben der Münze, blendet zum Ende hin aus und faellt mit
    ihr zusammen — so bleibt der Gewinn dort, wo man ohnehin hinschaut.
    """
    cd = asv.get('coin_drop')
    if not cd or cd.get('t', 0) <= 0:
        return
    p = 1.0 - max(0.0, min(1.0, cd['t']))       # 0 → 1
    y = y0 + int(64 * p)
    r = 11
    _draw_coin(surf, x, y, r)
    n = int(cd.get('n', 0) or 0)
    if n <= 0:
        return
    txt = fonts['big'].render('+%d' % n, True, COIN_HI)
    # Gegen Ende ausblenden, damit die Zahl nicht abrupt verschwindet.
    txt.set_alpha(int(255 * min(1.0, (1.0 - p) * 3.0)))
    surf.blit(txt, (x + r + 8, y - txt.get_height() // 2))


def _draw_reveal(screen, fonts, w, h, asv):
    """Kisten-Ergebnis kurz einblenden (Teil ODER Münzen — beides zufällig)."""
    rv = asv.get('reveal')
    if not rv:
        return
    box_w, box_h = 300, 96
    bx, by = w // 2 - box_w // 2, 96
    panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
    panel.fill(ASSESS_PANEL)
    pygame.draw.rect(panel, ASSESS_GOLD, panel.get_rect(), width=2, border_radius=14)
    screen.blit(panel, (bx, by))
    head = fonts['big'].render(_sym('▣  Kiste!'), True, ASSESS_GOLD)
    screen.blit(head, (w // 2 - head.get_width() // 2, by + 14))
    if rv.get('kind') == 'part':
        sub = fonts['log'].render('ein neues Teil von Lucía', True, HUD_FG)
    else:
        sub = fonts['log'].render('+%d Münzen' % int(rv.get('amount', 0)), True, COIN_HI)
    screen.blit(sub, (w // 2 - sub.get_width() // 2, by + 54))


# ── Geschenk-Sequenz ─────────────────────────────────────────────────────────
#
# Ein Meilenstein soll sich wie ein Gewinn anfuehlen, nicht wie eine Meldung.
# Deshalb vier Stufen statt einer Einblendung: das Bild dunkelt ab und das
# Paket liegt allein da (»zu«) — Pfeil rechts laesst es wackeln (»wackeln«) —
# die Schleife fliegt weg, der Deckel hebt ab, Konfetti und Sternchen stieben
# heraus (»auf«) — und erst DANN steht das gewonnene Teil da, mit einem
# drehenden Strahlenkranz (»teil«).
#
# Der Nutzer druesst zweimal: einmal zum Oeffnen, einmal zum Weitermachen.
# Dazwischen laeuft alles von selbst.

GESCHENK_DAUER = {'wackeln': 0.55, 'auf': 0.85}     # Sekunden je Automatik-Stufe
KONFETTI_FARBEN = ((246, 214, 128), (150, 200, 230), (232, 120, 140),
                   (140, 220, 160), (250, 250, 250))


def _konfetti_streuen(cx, cy, anzahl=46):
    """Teilchen, die beim Oeffnen herausfliegen: Schnipsel und Sternchen."""
    stuecke = []
    for _ in range(anzahl):
        winkel = random.uniform(-math.pi * 0.92, -math.pi * 0.08)
        tempo = random.uniform(190, 430)
        stuecke.append({
            'x': cx + random.uniform(-18, 18), 'y': cy + random.uniform(-10, 10),
            'vx': math.cos(winkel) * tempo, 'vy': math.sin(winkel) * tempo,
            'farbe': random.choice(KONFETTI_FARBEN),
            'stern': random.random() < 0.34,
            'gr': random.uniform(4, 9), 'dreh': random.uniform(0, math.tau),
            'spin': random.uniform(-9, 9),
        })
    return stuecke


def _konfetti_takt(stuecke, dt):
    """Flugbahn: Schwerkraft und etwas Bremsung. Fertig = unten raus."""
    for k in stuecke:
        k['vy'] += 900 * dt
        k['vx'] *= (1 - 1.2 * dt)
        k['x'] += k['vx'] * dt
        k['y'] += k['vy'] * dt
        k['dreh'] += k['spin'] * dt


def _draw_stern(surf, cx, cy, r, farbe, dreh):
    """Vierzackiges Funkeln — schlanker als ein Fuenfeck und liest sich klein."""
    punkte = []
    for i in range(8):
        a = dreh + i * math.pi / 4
        laenge = r if i % 2 == 0 else r * 0.38
        punkte.append((cx + math.cos(a) * laenge, cy + math.sin(a) * laenge))
    pygame.draw.polygon(surf, farbe, punkte)


def _draw_konfetti(surf, stuecke):
    for k in stuecke:
        if k['stern']:
            _draw_stern(surf, k['x'], k['y'], k['gr'], k['farbe'], k['dreh'])
        else:
            schnipsel = pygame.Surface((int(k['gr'] * 2), int(k['gr'])), pygame.SRCALPHA)
            schnipsel.fill(k['farbe'])
            gedreht = pygame.transform.rotate(schnipsel, math.degrees(k['dreh']))
            surf.blit(gedreht, (k['x'] - gedreht.get_width() // 2,
                                k['y'] - gedreht.get_height() // 2))


def _draw_strahlenkranz(surf, cx, cy, radius, winkel, farbe=None):
    """Rotierender Strahlenkranz hinter dem gewonnenen Teil.

    Auf eine eigene Flaeche gemalt und halbdurchsichtig darübergelegt, damit
    sich die Keile nicht gegenseitig aufhellen, wo sie sich am Mittelpunkt
    treffen.
    """
    farbe = farbe or ASSESS_GOLD
    schicht = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    m = radius
    for i in range(14):
        a = winkel + i * math.tau / 14
        breit = math.tau / 90            # schmale Keile — ein Funkeln, kein Windrad
        punkte = [(m, m),
                  (m + math.cos(a - breit) * radius, m + math.sin(a - breit) * radius),
                  (m + math.cos(a + breit) * radius, m + math.sin(a + breit) * radius)]
        pygame.draw.polygon(schicht, (*farbe, 38), punkte)
    surf.blit(schicht, (cx - radius, cy - radius))


def _draw_paket(surf, cx, cy, gr, deckel_hoch=0.0, schleife=True, kippen=0.0):
    """Das Geschenk selbst. `deckel_hoch` 0→1 hebt den Deckel ab."""
    b, h = int(gr), int(gr * 0.84)
    koerper = pygame.Rect(0, 0, b, h)
    koerper.center = (int(cx), int(cy + gr * 0.12))
    pygame.draw.rect(surf, ASSESS_GOLD, koerper, border_radius=6)
    # Band senkrecht + waagerecht
    pygame.draw.line(surf, COIN_LO, (cx, koerper.top), (cx, koerper.bottom), max(3, b // 12))
    pygame.draw.line(surf, COIN_LO, (koerper.left, koerper.centery),
                     (koerper.right, koerper.centery), max(3, b // 16))

    deckel = pygame.Surface((b + int(gr * 0.14), int(h * 0.32)), pygame.SRCALPHA)
    pygame.draw.rect(deckel, ASSESS_GOLD, deckel.get_rect(), border_radius=5)
    pygame.draw.line(deckel, COIN_LO, (deckel.get_width() // 2, 0),
                     (deckel.get_width() // 2, deckel.get_height()), max(3, b // 12))
    if kippen:
        deckel = pygame.transform.rotate(deckel, kippen)
    dy = koerper.top - int(gr * 0.9 * deckel_hoch)
    surf.blit(deckel, (cx - deckel.get_width() // 2, dy - deckel.get_height() // 2))

    if schleife:
        ohr = max(5, int(gr * 0.16))
        oy = dy - deckel.get_height() // 2 - ohr // 2
        pygame.draw.circle(surf, ASSESS_GOLD, (int(cx - ohr), int(oy)), ohr)
        pygame.draw.circle(surf, ASSESS_GOLD, (int(cx + ohr), int(oy)), ohr)
        pygame.draw.circle(surf, COIN_LO, (int(cx - ohr), int(oy)), ohr, 2)
        pygame.draw.circle(surf, COIN_LO, (int(cx + ohr), int(oy)), ohr, 2)


def _draw_teil_mittig(surf, cx, cy, teil, skala):
    """EIN Koerperteil so zeichnen, dass es wirklich in der Mitte sitzt.

    _draw_lucia() setzt jedes Teil an seinen Platz an der Figur — der Kopf
    landet also weit oberhalb des uebergebenen Punktes. Fuer die Nahaufnahme im
    Geschenk brauchen wir es aber mittig: also auf eine eigene Flaeche malen,
    den tatsaechlich bemalten Bereich messen und DEN zentrieren.
    """
    kante = 460
    flaeche = pygame.Surface((kante, kante), pygame.SRCALPHA)
    _draw_lucia(flaeche, kante // 2, kante // 2, 1.6, [teil], boden=False)
    box = flaeche.get_bounding_rect()
    if box.width == 0 or box.height == 0:
        return
    ausschnitt = flaeche.subsurface(box).copy()
    breite = max(1, int(box.width * skala * 2.2))
    hoehe = max(1, int(box.height * skala * 2.2))
    ausschnitt = pygame.transform.smoothscale(ausschnitt, (breite, hoehe))
    surf.blit(ausschnitt, (cx - breite // 2, cy - hoehe // 2))


def _draw_geschenk(screen, fonts, w, h, asv):
    """Die ganze Sequenz. Zeichnet ueber alles andere."""
    g = asv.get('geschenk')
    if not g:
        return
    phase, t = g.get('phase', 'zu'), g.get('t', 0.0)
    cx, cy = w // 2, int(h * 0.46)

    dunkel = pygame.Surface((w, h), pygame.SRCALPHA)
    dunkel.fill((0, 0, 0, 185))
    screen.blit(dunkel, (0, 0))

    def mitte(surf, y):
        screen.blit(surf, (w // 2 - surf.get_width() // 2, y))

    gr = int(min(w, h) * 0.20)

    if phase == 'zu':
        wippen = math.sin(t * 3.0) * gr * 0.03
        _draw_paket(screen, cx, cy + wippen, gr)
        mitte(fonts['big'].render('Ein Geschenk!', True, ASSESS_GOLD), cy - int(gr * 1.5))
        _hint_row(screen, fonts['hud'], w, cy + int(gr * 0.95), [('→', 'aufmachen')])

    elif phase == 'wackeln':
        p = min(1.0, t / GESCHENK_DAUER['wackeln'])
        zittern = math.sin(t * 46) * gr * 0.06 * (1 - p * 0.4)
        _draw_paket(screen, cx + zittern, cy, gr, kippen=zittern * 0.4)
        mitte(fonts['big'].render('…', True, ASSESS_GOLD), cy - int(gr * 1.5))

    elif phase == 'auf':
        p = min(1.0, t / GESCHENK_DAUER['auf'])
        _draw_paket(screen, cx, cy, gr, deckel_hoch=p, schleife=False,
                    kippen=-18 * p)
        # Die Schleife fliegt weg
        ohr = max(5, int(gr * 0.16))
        sx = cx + 120 * p
        sy = cy - int(gr * 0.75) - 190 * p + 240 * p * p
        pygame.draw.circle(screen, ASSESS_GOLD, (int(sx - ohr), int(sy)), ohr)
        pygame.draw.circle(screen, ASSESS_GOLD, (int(sx + ohr), int(sy)), ohr)
        _draw_konfetti(screen, g.get('konfetti') or [])

    else:                                    # 'teil' — der Gewinn steht da
        p = min(1.0, t / 0.45)
        skala = 0.4 + 0.6 * (1 - (1 - p) ** 3)
        _draw_strahlenkranz(screen, cx, cy, int(gr * 1.25), g.get('winkel', 0.0))
        _draw_konfetti(screen, g.get('konfetti') or [])
        if g.get('kind') == 'part' and g.get('part'):
            _draw_teil_mittig(screen, cx, cy, g['part'], skala * gr / 150.0)
            text = 'Ein neues Teil von Lucía'
        else:
            muenze = fonts['word'].render('+%d' % int(g.get('amount', 0)), True, COIN_HI)
            mitte(muenze, cy - muenze.get_height() // 2)
            text = 'Münzen'
        mitte(fonts['big'].render(text, True, ASSESS_GOLD), cy + int(gr * 1.05))
        _hint_row(screen, fonts['hud'], w, cy + int(gr * 1.55), [('→', 'weiter')])


# ── Vokabel-Karte ────────────────────────────────────────────────────────────
#
# Jede Vokabel ist eine eigene Karte auf einem sichtbaren Stapel. Gewusste
# Karten wandern hinten wieder rein, fertige verschwinden. Aufdecken dreht die
# Karte auf die Rueckseite — dieselbe Geste, die man bei echten Karteikarten
# macht, und damit spielerischer als ein Textwechsel.

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
_HANDSCHRIFT = os.path.join(_ASSETS, 'PermanentMarker-Regular.ttf')
_hand_cache = {}


def _hand(size):
    """Die Handschrift fuer das Wort auf der Karte.

    Liegt die Datei nicht (Knoten ohne das Asset), faellt es still auf die
    normale Schrift zurueck — eine fehlende Zierschrift darf das Drill nicht
    verhindern.
    """
    f = _hand_cache.get(size)
    if f is None:
        try:
            f = pygame.font.Font(_HANDSCHRIFT, size)
        except Exception:
            f = _font(size, bold=True)
        _hand_cache[size] = f
    return f


def _karte_flaeche(w, h):
    """Groesse und Mitte der Karte, aus der Fensterflaeche gerechnet."""
    # Bewusst nicht randfuellend: der Stapel dahinter muss zu sehen sein, sonst
    # ist es wieder nur ein Wort auf dunklem Grund.
    kb = int(min(w * 0.19, h * 0.32))
    kh = int(kb * 1.36)                      # Hochformat wie eine Karteikarte
    return kb, kh


def _draw_stapel(screen, cx, cy, kb, kh, rest):
    """Die Karten HINTER der aktuellen — der Stapel, der sichtbar abnimmt."""
    sichtbar = max(0, min(5, rest))
    for i in range(sichtbar, 0, -1):
        versatz = i * 11
        rect = pygame.Rect(0, 0, kb - i * 4, kh - i * 2)
        rect.center = (cx + versatz, cy - versatz)
        pygame.draw.rect(screen, KARTE_STAPEL, rect, border_radius=14)
        pygame.draw.rect(screen, KARTE_RAND, rect, 1, border_radius=14)


def _karte_malen(kb, kh, rueckseite, wort, uebersetzung, kategorie, fonts):
    """Eine Karte als eigene Flaeche zeichnen (damit sie sich drehen laesst)."""
    surf = pygame.Surface((kb, kh), pygame.SRCALPHA)
    rect = surf.get_rect()
    pygame.draw.rect(surf, KARTE_RUECK if rueckseite else KARTE_BG, rect,
                     border_radius=16)
    pygame.draw.rect(surf, KARTE_RAND, rect, 2, border_radius=16)

    if rueckseite:
        kopf = fonts['hud'].render('BEDEUTUNG', True, KARTE_SUB)
        surf.blit(kopf, (kb // 2 - kopf.get_width() // 2, int(kh * 0.16)))
        f = _hand(int(kb * 0.13))
        zeilen = _umbrechen(uebersetzung or '…', f, kb - 48)[:3]
        schritt = int(kb * 0.17)
        oben = kh // 2 - (len(zeilen) - 1) * schritt // 2
        for i, zeile in enumerate(zeilen):
            _blit_optisch_mittig(surf, f.render(zeile, True, KARTE_INK),
                                 kb // 2, oben + i * schritt)
    else:
        if kategorie:
            k = fonts['hud'].render(kategorie.upper(), True, KARTE_SUB)
            surf.blit(k, (kb // 2 - k.get_width() // 2, int(kh * 0.16)))
        # Wortgroesse an die Kartenbreite anpassen, damit auch lange Vokabeln
        # hineinpassen statt ueber den Rand zu laufen.
        groesse = int(kb * 0.22)
        while groesse > 14:
            f = _hand(groesse)
            if f.size(wort or '')[0] <= kb - 44:
                break
            groesse -= 4
        r = _hand(groesse).render(wort or '', True, KARTE_INK)
        _blit_optisch_mittig(surf, r, kb // 2, kh // 2)
    return surf


def _blit_optisch_mittig(ziel, text_surf, cx, cy):
    """Text so setzen, dass die TINTE mittig sitzt — nicht die Textflaeche.

    Eine gerenderte Zeile ist immer so hoch wie die ganze Schrift (Oberlaengen,
    Unterlaengen, Akzente), auch wenn das Wort davon nur einen Teil nutzt.
    »saber« fuellt in Permanent Marker bei 143 px Flaechenhoehe nur y=50..115 —
    zentriert man die Flaeche, sitzt das Wort sichtbar zu tief. Und weil der
    Versatz je nach Wort anders ist (»la mañana« mit Tilde faengt viel weiter
    oben an), wandert es zwischen zwei Karten auch noch hin und her.

    Deshalb wird der wirklich bemalte Bereich gemessen und DER zentriert.
    """
    box = text_surf.get_bounding_rect()
    if box.width == 0 or box.height == 0:
        ziel.blit(text_surf, (cx - text_surf.get_width() // 2,
                              cy - text_surf.get_height() // 2))
        return
    ziel.blit(text_surf, (cx - box.x - box.width // 2,
                          cy - box.y - box.height // 2))


def _umbrechen(text, font, breite):
    """Text auf mehrere Zeilen umbrechen, damit er auf die Karte passt."""
    worte, zeilen, jetzt = (text or '').split(), [], ''
    for wort in worte:
        probe = (jetzt + ' ' + wort).strip()
        if font.size(probe)[0] <= breite or not jetzt:
            jetzt = probe
        else:
            zeilen.append(jetzt); jetzt = wort
    if jetzt:
        zeilen.append(jetzt)
    return zeilen or ['']


def _draw_karte(screen, fonts, asv, cx, cy, kb, kh, cur):
    """Die aktuelle Karte, ggf. mitten im Drehen oder auf dem Weg nach hinten."""
    flip = asv.get('flip')
    weg = asv.get('weg')
    rueck = (asv.get('sub') == 'learn') or (asv.get('blick') is not None)

    if flip:
        # Drehung: die Karte wird schmaler, kippt durch und kommt als
        # Rueckseite wieder heraus. cos() gibt die perspektivische Breite.
        t = max(0.0, min(1.0, flip.get('t', 0.0)))
        breite_faktor = abs(math.cos(math.pi * t))
        rueck = t >= 0.5 if flip.get('nach') == 'rueck' else t < 0.5
    else:
        breite_faktor = 1.0

    surf = _karte_malen(kb, kh, rueck, cur.get('word', ''), cur.get('de', ''),
                        _CAT_DE.get(cur.get('category', ''), ''), fonts)

    if weg:
        # Zurueck in den Stapel: schrumpfen und nach hinten rutschen.
        t = max(0.0, min(1.0, weg.get('t', 0.0)))
        skala = 1.0 - 0.35 * t
        cx = int(cx + 26 * t)
        cy = int(cy - 26 * t)
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(kb * skala * breite_faktor)),
                   max(1, int(kh * skala))))
        surf.set_alpha(int(255 * (1.0 - 0.75 * t)))
    elif breite_faktor < 0.999:
        surf = pygame.transform.smoothscale(
            surf, (max(1, int(kb * breite_faktor)), kh))

    screen.blit(surf, (cx - surf.get_width() // 2, cy - surf.get_height() // 2))


def _stand_zeilen(asv):
    """Die Auswahl-Zeilen: vorhandene Spielstaende, danach »neu anfangen«.

    Vorhandene zuerst, weil Weiterspielen der Normalfall ist — neu anfaengt man
    einmal. Die Liste kommt vom Backend; solange sie laedt, gibt es nur den
    neuen Stand, damit der Schirm nie leer und unbedienbar dasteht.
    """
    zeilen = [{'art': 'stand', 'stand': st} for st in (asv.get('staende') or [])]
    zeilen.append({'art': 'neu'})
    return zeilen


def _draw_loesch_frage(screen, w, fonts, asv):
    """Sicherheitsabfrage vor dem Loeschen.

    Ein Spielstand ist Stunden an Arbeit — der darf nicht auf einen einzelnen
    Tastendruck hin verschwinden. Deshalb steht die Rueckfrage MITTIG ueber
    allem, nennt den Namen des Standes beim Wort und ist mit Esc weg. Die
    ungefaehrliche Antwort (Abbrechen) liegt auf der bequemeren Taste.
    """
    weg = asv['stand_weg']
    h = screen.get_height()

    # Hoehe aus dem Inhalt rechnen statt raten — sonst haengt die Tastenzeile
    # halb aus dem Kasten heraus, sobald die Schrift anders ausfaellt.
    zeilen = [(fonts['big'], 'Spielstand löschen?', ASSESS_GOLD, 14),
              (fonts['bubble'], '»%s«' % weg.get('name', ''), ASSESS_INK, 10),
              (fonts['hud'], weg.get('unter') or '', HUD_DIM, 4),
              (fonts['hud'], 'Das Gelernte darin ist dann weg — endgültig.',
               HUD_DIM, 18)]
    rand = 26
    bh = rand * 2 + sum(f.get_height() + luft for f, _, _, luft in zeilen) \
        + fonts['hud'].get_height() + 10
    bw = min(680, w - 120)
    bx = w // 2 - bw // 2
    by = max(20, h // 2 - bh // 2)          # mittig, nicht ueber der Ueberschrift

    schatten = pygame.Surface((w, h), pygame.SRCALPHA)
    schatten.fill((0, 0, 0, 170))
    screen.blit(schatten, (0, 0))

    pygame.draw.rect(screen, ASSESS_BAR_BG, (bx, by, bw, bh), border_radius=12)
    pygame.draw.rect(screen, ASSESS_GOLD, (bx, by, bw, bh), 2, border_radius=12)

    y = by + rand
    for f, text, farbe, luft in zeilen:
        surf = f.render(text, True, farbe)
        screen.blit(surf, (w // 2 - surf.get_width() // 2, y))
        y += f.get_height() + luft
    _hint_row(screen, fonts['hud'], w, y,
              [('Entf', 'ja, löschen'), ('Esc', 'abbrechen')])


def _draw_stand_wahl(screen, w, fonts, asv, top_y, ctr):
    """Spielstand waehlen, bevor das Drill losgeht."""
    zeilen = _stand_zeilen(asv)
    idx = max(0, min(len(zeilen) - 1, int(asv.get('stand_idx', 0))))
    aktiv = asv.get('stand_aktiv')

    ctr(fonts['hud'].render('SPIELSTAND', True, ASSESS_ACC), top_y)

    # Zeilenhoehe aus den Schriften rechnen, nicht raten: Titel + Unterzeile +
    # Luft. Mit festen Pixelwerten lag die Unterzeile auf der Grundlinie des
    # Titels, sobald die Schrift etwas groesser ausfiel als beim Entwurf.
    h_titel = fonts['big'].get_height()
    h_unter = fonts['hud'].get_height()
    innen = 10
    hoehe = h_titel + h_unter + 2 * innen + 4
    abstand = 10

    y = top_y + fonts['hud'].get_height() + 14
    bw = min(620, w - 160)
    bx = w // 2 - bw // 2

    for i, z in enumerate(zeilen):
        if i == idx:
            pygame.draw.rect(screen, ASSESS_BAR_BG, (bx, y, bw, hoehe),
                             border_radius=8)
            pygame.draw.rect(screen, ASSESS_ACC, (bx, y, 4, hoehe),
                             border_radius=2)
        if z['art'] == 'neu':
            titel = 'Neuer Spielstand'
            unter = 'von vorn anfangen — die anderen Stände bleiben erhalten'
            farbe = ASSESS_GOLD
        else:
            st = z['stand']
            titel = st.get('name') or st.get('id')
            if st.get('id') == aktiv:
                titel += '   (zuletzt gespielt)'
            unter = _stand_unterzeile(st)
            farbe = ASSESS_INK
        screen.blit(fonts['big'].render(titel, True, farbe), (bx + 20, y + innen))
        screen.blit(fonts['hud'].render(unter, True, HUD_DIM),
                    (bx + 20, y + innen + h_titel + 4))
        y += hoehe + abstand

    tasten = [('↑↓', 'wählen'), ('Enter', 'los geht’s')]
    if zeilen[idx]['art'] == 'stand':
        tasten.append(('Entf', 'löschen'))
    _hint_row(screen, fonts['hud'], w, y + 16, tasten)

    if asv.get('stand_weg'):
        _draw_loesch_frage(screen, w, fonts, asv)


def _stand_unterzeile(st):
    """Woran man einen Stand wiedererkennt: Sprachen, Woerter, Muenzen."""
    teile = []
    for lang, d in sorted((st.get('sprachen') or {}).items()):
        stueck = _sym('%s · %d Wörter' % (lang, d.get('woerter', 0)))
        if d.get('muenzen'):
            stueck += ' · %d Münzen' % d['muenzen']
        teile.append(stueck)
    if not teile:
        return 'noch nichts gelernt'
    return '   |   '.join(teile)


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

    # Fortschrittsleiste (Track mit Kisten-Symbolen) + Münz-HUD (immer, außer Willkommen)
    if phase != 'welcome':
        bw = min(520, w - 220); bx = 60; by = 56; bh = 12
        pygame.draw.rect(screen, ASSESS_BAR_BG, (bx, by, bw, bh), border_radius=6)
        fw = int(bw * max(0.0, min(1.0, ratio)))
        if fw > 0:
            pygame.draw.rect(screen, ASSESS_ACC, (bx, by, fw, bh), border_radius=6)
        # Kisten-Meilensteine als kleine Symbole auf dem Track (erreichte golden)
        for m in (asv.get('crate_at') or []):
            if not total or m > total:
                continue
            mxp = bx + int(bw * (m / total))
            _draw_crate_icon(screen, mxp, by + bh // 2, 14, got >= m)
        # Ziel-Marke ganz rechts = Lucía (komplett)
        pygame.draw.circle(screen, ASSESS_GOLD, (bx + bw, by + bh // 2), 4)
        screen.blit(fonts['hud'].render(_sym(f'{got} / {total} · {int(round(100*ratio))}%'), True, HUD_FG),
                    (bx, by - fonts['hud'].get_height() - 6))
        gl = fonts['hud'].render(_sym('alle Wörter → Lucía'), True, ASSESS_GOLD)
        screen.blit(gl, (bx + bw - gl.get_width(), by - fonts['hud'].get_height() - 6))

    if phase == 'welcome':
        ctr(fonts['word'].render('Hola', True, ASSESS_INK), cy - 250)
        ctr(fonts['big'].render('Ich bin Lucía.', True, ASSESS_INK), cy - 178)
        for i, ln in enumerate(['Zuerst gehen wir zusammen die wichtigsten Wörter durch — hak ab, was du kannst.',
                                'Dabei sammelst du Münzen und puzzelst mich Stück für Stück zusammen.']):
            ctr(fonts['log'].render(ln, True, HUD_DIM), cy - 122 + i * 26)
        _draw_stand_wahl(screen, w, fonts, asv, cy - 46, ctr)
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
        ctr(fonts['big'].render('Lucía ist da.', True, ASSESS_INK), cy - 18)
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

    # Karte + Stapel. Die Karte sitzt etwas höher als die Mitte, darunter ist
    # Platz für die Tastenzeile.
    kb, kh = _karte_flaeche(w, h)
    kcy = cy - 34
    _draw_stapel(screen, ccx, kcy, kb, kh, len(asv.get('work') or []) - 1)
    _draw_karte(screen, fonts, asv, ccx, kcy, kb, kh, cur)

    unten = kcy + kh // 2
    if speaking:
        ctl(fonts['hud'].render(_sym('◗ Lucía spricht …'), True, ASSESS_ACC), unten + 14)

    sub = asv.get('sub')
    if asv.get('blick') is not None:        # Rückblick: nur anschauen, nichts wird gewertet
        ctl(fonts['hud'].render(_sym('— Rückblick, zählt nicht —'), True, HUD_DIM), unten + 44)
        _hint_row(screen, fonts['hud'], w, unten + 72,
                  [('←', 'weiter zurück'), ('→', 'zurück zur Abfrage')], center_x=ccx)
    elif sub == 'learn':                    # aufgedeckt: zählt nicht mehr als gewusst
        ctl(fonts['hud'].render(_sym('— merk’s dir, kommt gleich nochmal —'), True, HUD_DIM),
            unten + 44)
        _hint_row(screen, fonts['hud'], w, unten + 72,
                  [('↓', 'nochmal hören'), ('→', 'weiter')], center_x=ccx)
    else:                                   # ask — nur das Wort, keine Übersetzung
        ctl(fonts['hud'].render('Kennst du das Wort?', True, ASSESS_INK2), unten + 44)
        _hint_row(screen, fonts['hud'], w, unten + 72,
                  [('↓', 'umdrehen'), ('→', 'kann ich ✓'), ('←', 'zurück')],
                  center_x=ccx)

    # Münz-Konto direkt unter die Tastenzeile, Zugewinn faellt an der Karte —
    # aber an ihrer RECHTEN Kante, sonst liegt die Münze auf dem Wort.
    _draw_coin_hud(screen, fonts, asv, ccx, unten + 118)
    _draw_coin_drop(screen, fonts, ccx + kb // 2 + 26, kcy - kh // 4, asv)
    _draw_reveal(screen, fonts, w, h, asv)
    _draw_geschenk(screen, fonts, w, h, asv)     # Meilenstein: über allem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--url', default=os.environ.get('ZENTRALE_URL', 'http://localhost:5000'))
    ap.add_argument('--w', type=int, default=920)
    ap.add_argument('--h', type=int, default=600)
    # Vollbild ist der Normalfall: das Zimmer haengt an der Wand, dort gibt es
    # keine Fensterleiste und niemanden, der ein Fenster zurechtzieht. Am
    # Schreibtisch holt --fenster das alte Verhalten zurueck.
    ap.add_argument('--fenster', action='store_true',
                    help='im Fenster statt im Vollbild starten')
    # Stimme: Sprecher-ID (vits-zh-aishell3 hat 174 — Wert durchprobieren) + Tempo.
    ap.add_argument('--speaker', type=int, default=int(os.environ.get('TUTOR_TTS_SPEAKER', '66')))
    ap.add_argument('--speed', type=float, default=float(os.environ.get('TUTOR_TTS_SPEED', '1.0')))
    ap.add_argument('--mute', action='store_true', help='ohne Stimme starten')
    ap.add_argument('--no-mic', action='store_true', help='ohne Immer-Zuhören (STT) starten')
    a = ap.parse_args()

    pygame.init()
    pygame.display.set_caption('ZENTRALE — Persona')

    # Wie gross ist der Bildschirm wirklich? Nicht raten: der Pi an der Wand
    # haengt an einem anderen Geraet als der Laptop, und ein festes 920x600
    # sieht dort verloren aus. get_desktop_sizes() gibt die echte Groesse des
    # Desktops; wo es die nicht gibt (aeltere pygame), tut es display.Info().
    def _bildschirm():
        try:
            groessen = pygame.display.get_desktop_sizes()
            if groessen:
                return groessen[0]
        except Exception:
            pass
        try:
            i = pygame.display.Info()
            if i.current_w > 0 and i.current_h > 0:
                return i.current_w, i.current_h
        except Exception:
            pass
        return a.w, a.h

    fenster = a.fenster or os.environ.get('TUTOR_ROOM_FENSTER') == '1'
    if fenster:
        screen = pygame.display.set_mode((a.w, a.h), pygame.RESIZABLE)
    else:
        bw, bh = _bildschirm()
        # Vollbild in der Groesse des Desktops: kein Hochskalieren, keine
        # verzerrten Proportionen — das Zimmer wird einfach fuer die Flaeche
        # gezeichnet, die da ist.
        screen = pygame.display.set_mode((bw, bh), pygame.FULLSCREEN)
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
        'theme_want': 'night', # gewünschter Theme-Modus (an ZENTRALE gekoppelt)
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
    # wenn ALLE Wörter durch sind (100 %), wird die Persona (run_stream) gestartet.
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

    # Session-SR (Working-Memory, Sasha) — Due-Time-Scheduler (stabile Abstände,
    # kein Positions-Drift): jede Karte hat ein `due` = „ab dieser Karten-Zahl (seen)
    # wieder fällig". Fällige Karten kommen zuerst (kleinstes due), bei Gleichstand
    # haben schon gesehene (Review) Vorrang vor neuen. Gewusst → wachsende Abstände
    # (7/14/25), nicht gewusst → in 3 Karten wieder; neue Wörter (due=Index)
    # interleaven dazwischen. STATUSLEISTE hängt am ersten Wissen (Backend confirmed
    # → got), NICHT am SR. Streak > Ladder → Wort graduiert aus der Runde.
    def _pick(v):
        work = v.get('work') or []
        if not work:
            return None
        seen = v.get('seen', 0)
        due = [c for c in work if c.get('due', 0) <= seen]
        pool = sorted(due or work, key=lambda c: (c.get('due', 0), 0 if c.get('shown') else 1))
        return pool[0]

    def asv_show():
        """Nächste fällige Karte wählen, zeigen, vorlesen. ERSTE Sicht eines Worts
        (`shown` noch False) → Übersetzung automatisch (sub='learn', nicht abhakbar),
        danach kommt es per SR gleich nochmal zum echten Abfragen. Sonst normale
        Abfrage (sub='ask')."""
        with S['lock']:
            v = S['asv']
            if not v or not v.get('work'):
                return
            cur = _pick(v)
            if cur is not None:
                cur['shown'] = True     # nur fürs _pick-Tie-Break (Review vor Neu)
            # Immer normale Abfrage (nur Wort). Die Bedeutung kommt NUR über Repeat.
            v['sub'] = 'ask'
            v['learn_hold'] = None
            v['cur'] = cur
            v['seen'] = v.get('seen', 0) + 1        # eine Karte mehr gezeigt
            v['blick'] = None                      # frische Karte -> kein Rueckblick
            if cur is not None:
                # Verlauf fuer den Rueckblick (←). Gedeckelt: wir wollen die
                # letzten Karten nachschlagen koennen, kein Sitzungsprotokoll.
                verlauf = v.setdefault('verlauf', [])
                verlauf.append(cur)
                del verlauf[:-VERLAUF_MAX]
            word = cur['word'] if cur else None
        if word:
            asv_speak(word)

    def asv_weglegen():
        """Die Karte nach hinten in den Stapel legen — dann erst die naechste.

        Sichtbar wegzulegen ist der halbe Reiz am Stapel: man SIEHT, dass das
        Wort wiederkommt (oder eben nicht). Die naechste Karte holt der
        Render-Takt, sobald die Bewegung durch ist — in einem eigenen Thread,
        weil asv_show() das Wort vorlesen laesst und dabei aufs Netz wartet.
        """
        with S['lock']:
            v = S['asv']
            if v and not v.get('weg'):
                v['weg'] = {'t': 0.0}

    def asv_advance():
        """Stapel leer / alle durch → Freischaltung, sonst nächste Karte."""
        with S['lock']:
            v = S['asv']
            if not v:
                return
            if not v.get('work'):
                v['phase'] = 'unlock'; v['cur'] = None; return
        asv_show()

    def asv_abhaken():
        """ABHAKEN (gewusst) — Review verbuchen (REST → Leiste/Münzen/Kisten), dann
        per SR wieder fällig setzen (1×→+7, 2×→+14, 3×→+25 Karten); nach genug
        korrekten Reviews graduiert das Wort. Ökonomie vom Backend (persistiert)."""
        with S['lock']:
            v = S['asv']
            if (not v or v.get('busy') or not v.get('cur') or v.get('reveal')
                    or v.get('sub') == 'learn'):      # nach Repeat NICHT abhakbar
                return
            v['busy'] = True; cur = v['cur']; word = cur['word']
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
                        v['coin_drop'] = {'n': gain, 't': 1.0}   # fällt AM Wort runter
                    if isinstance(res.get('parts'), list):
                        v['parts'] = res['parts']
                    crate = res.get('crate')
                    if crate:
                        # Meilenstein: die Geschenk-Sequenz uebernimmt den Schirm.
                        # Sie laeuft NICHT von selbst durch — der erste Pfeil
                        # macht auf, der zweite geht weiter. Ein Gewinn, den man
                        # wegklicken muss, fuehlt sich nach Gewinn an; einer, der
                        # nach 2 Sekunden verschwindet, nach Systemmeldung.
                        v['geschenk'] = {'phase': 'zu', 't': 0.0,
                                         'kind': crate.get('kind'),
                                         'amount': int(crate.get('amount', 0) or 0),
                                         'part': crate.get('part'),
                                         'konfetti': [], 'winkel': 0.0}
                        if crate.get('kind') == 'part' and crate.get('part'):
                            v['new_part'] = {'name': crate['part'], 't': 0.0}   # schwebt herein
                    # SR: nur bei bestätigtem Save — Streak hoch, neu fällig setzen
                    # (oder graduieren, wenn Streak über die Ladder hinaus ist).
                    if (res.get('assessed') or res.get('mastered')) and cur is not None:
                        cur['streak'] = int(cur.get('streak', 0)) + 1
                        if cur['streak'] >= FERTIG_NACH:
                            # Durch: die Karte kommt NICHT mehr in den Stapel.
                            v['work'] = [c for c in (v.get('work') or []) if c is not cur]
                            cur['fertig'] = True
                        else:
                            stufe = min(cur['streak'], len(SR_LADDER)) - 1
                            cur['due'] = v.get('seen', 0) + SR_LADDER[stufe]
                    unlocked = bool(res.get('unlocked'))
        if unlocked:
            with S['lock']:
                if S['asv']:
                    S['asv']['phase'] = 'unlock'; S['asv']['cur'] = None
            return
        asv_weglegen()

    def asv_lapse():
        """Nach Repeat (nicht gewusst): in ~3 Karten wieder fällig, Streak zurück
        auf 0 (Working-Memory-Auffrischung), dann weiter."""
        with S['lock']:
            v = S['asv']
            if not v:
                return
            v['learn_hold'] = None
            cur = v.get('cur')
            if cur is not None:
                cur['due'] = v.get('seen', 0) + SR_LAPSE
                cur['streak'] = 0
        asv_weglegen()

    def asv_aufdecken():
        """AUFDECKEN (↓) — Bedeutung zeigen + nochmal vorlesen.

        Wer aufdeckt, hat das Wort nicht gewusst: die Karte ist danach nicht
        mehr abhakbar und kommt per SR in ein paar Karten wieder. Frueher lief
        nach 3 Sekunden automatisch weiter; jetzt bleibt sie stehen, bis man →
        drueckt — man soll selbst entscheiden, wie lange man draufschaut.
        """
        with S['lock']:
            v = S['asv']
            if not v or v.get('reveal') or not v.get('cur'):
                return
            schon_offen = v.get('sub') == 'learn'
            v['sub'] = 'learn'
            v['learn_hold'] = None
            if not schon_offen:
                # Die Karte dreht sich auf die Rueckseite. Beim zweiten ↓
                # (nochmal hoeren) liegt sie schon offen — dann nicht erneut
                # drehen, sonst zappelt sie.
                v['flip'] = {'t': 0.0, 'nach': 'rueck'}
            cur = v.get('cur')
        if cur:
            # NEBENHER sprechen. asv_speak() holt das WAV vom Backend und
            # wartet dabei aufs Netz — direkt aufgerufen blockiert das die
            # Ereignisschleife, und die Drehung war vorbei, bevor ein einziges
            # Bild davon gezeichnet wurde. Genau deshalb sah Sasha keine
            # Animation.
            threading.Thread(target=asv_speak, args=(cur['word'],),
                             daemon=True).start()

    def asv_rueckblick(schritt):
        """RUECKBLICK (←/→) — vorige Karten nachschlagen, ohne zu werten.

        Praktisch, wenn man beim Weiterklicken merkt, dass man das Wort davor
        doch nicht sicher hatte. Es wird dabei NICHTS verbucht — der Rueckblick
        ist ein Nachschauen, kein Wiederholen; sonst koennte man sich durch
        Zurueckblaettern Muenzen holen.

        Rueckgabe: True = Rueckblick aktiv/behandelt, False = normal weiter.
        """
        with S['lock']:
            v = S['asv']
            if not v:
                return False
            verlauf = v.get('verlauf') or []
            blick = v.get('blick')
            if blick is None:
                if schritt >= 0 or len(verlauf) < 2:
                    return False          # vorwaerts/kein Vorgaenger -> normal
                blick = len(verlauf) - 2  # erster Schritt zurueck
            else:
                blick += schritt
            if blick >= len(verlauf) - 1 or blick < 0:
                # ueber das Ende hinaus (oder ganz zurueck) -> zurueck zur Abfrage
                v['blick'] = None
                v['cur'] = verlauf[-1] if verlauf else None
                v['sub'] = 'ask'
                return True
            v['blick'] = blick
            v['cur'] = verlauf[blick]
            v['sub'] = 'ask'
            wort = v['cur'].get('word')
        if wort:
            threading.Thread(target=asv_speak, args=(wort,), daemon=True).start()
        return True

    def asv_next():
        """NEXT — ohne Wertung überspringen: in ein paar Karten wieder fällig."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('busy') or not v.get('cur') or v.get('reveal'):
                return
            v['learn_hold'] = None
            cur = v.get('cur')
            if cur is not None:
                cur['due'] = v.get('seen', 0) + SR_SKIP     # streak unverändert
        asv_weglegen()

    def asv_key(ev):
        """Tastendruck im Abfrage-Modus (kein Text-Input dahinter).
        ask:   Leer/Enter = Abhaken · R = Repeat · N/→ = Next
        learn: (nach Repeat, nicht abhakbar) R = nochmal hören · sonst = weiter"""
        with S['lock']:
            v = S['asv']
            if not v:
                return
            phase = v.get('phase'); sub = v.get('sub')
        if phase == 'welcome':
            # Steht die Loesch-Rueckfrage offen, beantwortet sie ALLE Tasten —
            # sonst waehlt man im Hintergrund weiter und loescht am Ende den
            # falschen Stand.
            with S['lock']:
                offen = bool(S['asv'] and S['asv'].get('stand_weg'))
            if offen:
                if ev.key == pygame.K_DELETE:
                    threading.Thread(target=stand_loeschen, daemon=True).start()
                elif ev.key in (pygame.K_ESCAPE, pygame.K_n):
                    with S['lock']:
                        if S['asv']:
                            S['asv']['stand_weg'] = None
                return
            # Erst Spielstand waehlen, dann geht das Drill los.
            if ev.key == pygame.K_DELETE:
                stand_loesch_fragen()
            elif ev.key in (pygame.K_UP, pygame.K_DOWN):
                with S['lock']:
                    v = S['asv']
                    if v:
                        n = len(_stand_zeilen(v))
                        schritt = -1 if ev.key == pygame.K_UP else 1
                        v['stand_idx'] = (int(v.get('stand_idx', 0)) + schritt) % n
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                threading.Thread(target=stand_bestaetigen, daemon=True).start()
            return
        if phase == 'unlock':
            if ev.key == pygame.K_RETURN:
                with S['lock']:
                    S['asv'] = None; foc = S['focused']       # Abfrage aus → Persona
                threading.Thread(target=run_stream,
                                 args=('/api/tutor/start', {'focus': foc}), daemon=True).start()
            return
        # Ein offenes Geschenk bekommt die Tasten zuerst — sonst blaettert man
        # hinter dem Vorhang weiter, ohne es zu sehen.
        if v.get('geschenk'):
            g = v['geschenk']
            if ev.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_SPACE):
                with S['lock']:
                    gg = S['asv'].get('geschenk') if S['asv'] else None
                    if gg and gg['phase'] == 'zu':
                        gg['phase'] = 'wackeln'; gg['t'] = 0.0
                    elif gg and gg['phase'] == 'teil':
                        S['asv']['geschenk'] = None
            return

        # phase == 'card' — Steuerung:
        #   ↓          aufdecken (wer aufdeckt, wusste es nicht)
        #   → / Enter  weiter. NICHT aufgedeckt = gewusst, aufgedeckt = nochmal.
        #   ←          zurueckblaettern und nachschauen (zaehlt nicht)
        if ev.key == pygame.K_LEFT:
            asv_rueckblick(-1)
            return
        if v.get('blick') is not None:      # im Rueckblick wird nichts gewertet
            if ev.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_SPACE):
                asv_rueckblick(+1)
            return
        if ev.key == pygame.K_DOWN:
            asv_aufdecken()                 # auch im 'learn': nochmal hören
            return
        if ev.key in (pygame.K_RIGHT, pygame.K_RETURN, pygame.K_SPACE, pygame.K_n):
            if sub == 'learn':
                asv_lapse()                 # war aufgedeckt -> kommt wieder
            else:
                # Ohne Aufdecken weiter heisst: konnte ich. Genau so hat Sasha
                # es sich gewuenscht — ein Tastendruck fuer den Normalfall.
                threading.Thread(target=asv_abhaken, daemon=True).start()

    def staende_laden():
        """Spielstaende im Hintergrund holen und in den Willkommens-Schirm legen.

        Im Hintergrund, weil das Fenster sofort da sein soll: der Schirm zeigt
        so lange nur »Neuer Spielstand« und fuellt sich, wenn die Antwort da
        ist. Ein blockierender Aufruf im Render-Thread wuerde das Zimmer beim
        Oeffnen haengen lassen.
        """
        d = be.staende()
        if not isinstance(d, dict):
            return
        liste = d.get('staende') or []
        aktiv = d.get('aktiv')
        with S['lock']:
            v = S['asv']
            if not v or v.get('phase') != 'welcome':
                return
            v['staende'] = liste
            v['stand_aktiv'] = aktiv
            # Auf dem zuletzt gespielten Stand stehen bleiben — wer weiterspielt,
            # drueckt dann nur Enter.
            v['stand_idx'] = next((i for i, st in enumerate(liste)
                                   if st.get('id') == aktiv), 0)
            # Nach einem Loeschen kann der alte Index ins Leere zeigen.
            v['stand_idx'] = max(0, min(len(liste), v['stand_idx']))

    def stand_loesch_fragen():
        """Entf auf einem vorhandenen Stand -> Rueckfrage stellen."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('stand_weg'):
                return
            zeilen = _stand_zeilen(v)
            idx = max(0, min(len(zeilen) - 1, int(v.get('stand_idx', 0))))
            z = zeilen[idx]
            if z['art'] != 'stand':
                return                     # »Neuer Spielstand« kann man nicht loeschen
            st = z['stand']
            v['stand_weg'] = {'id': st.get('id'),
                              'name': st.get('name') or st.get('id'),
                              'unter': _stand_unterzeile(st)}

    def stand_loeschen():
        """Rueckfrage bejaht: Stand weg, Liste neu holen."""
        with S['lock']:
            v = S['asv']
            weg = v.get('stand_weg') if v else None
            if not weg or v.get('busy'):
                return
            v['busy'] = True
        try:
            be.stand_loeschen(weg['id'])
        finally:
            with S['lock']:
                if S['asv']:
                    S['asv']['stand_weg'] = None
                    S['asv']['busy'] = False
        staende_laden()                    # frische Liste + evtl. neuer aktiver Stand

    def stand_bestaetigen():
        """Gewaehlten Spielstand aktivieren (oder neu anlegen) und ins Drill."""
        with S['lock']:
            v = S['asv']
            if not v or v.get('busy'):
                return
            zeilen = _stand_zeilen(v)
            idx = max(0, min(len(zeilen) - 1, int(v.get('stand_idx', 0))))
            wahl = zeilen[idx]
            v['busy'] = True
        try:
            if wahl['art'] == 'neu':
                be.stand_neu()
            else:
                sid = wahl['stand'].get('id')
                # Der aktive Stand braucht keinen Wechsel — das wuerde nur die
                # Sitzung unnoetig beenden.
                if sid != v.get('stand_aktiv'):
                    be.stand_waehlen(sid)
            # Der Stand bestimmt, WAS gelernt ist: Queue und Spielstand neu holen.
            if not asv_init():
                # Kein Gate mehr (z.B. frisch gewaehlter, schon fertiger Stand)
                with S['lock']:
                    S['asv'] = None; foc = S['focused']
                threading.Thread(target=run_stream,
                                 args=('/api/tutor/start', {'focus': foc}),
                                 daemon=True).start()
                return
            with S['lock']:
                if S['asv']:
                    S['asv']['phase'] = 'card'
            asv_show()
        finally:
            with S['lock']:
                if S['asv']:
                    S['asv']['busy'] = False

    def asv_init():
        """Abfrage starten, falls die Sprache im Assessment-Gate steckt: Queue +
        Spielstand holen, Willkommen zeigen. True = Drill übernimmt (KEIN LLM);
        False = kein Gate → normaler Persona-Start."""
        data = be.assessment()
        if not isinstance(data, dict) or data.get('mode') != 'assessment':
            return False
        game = data.get('game') or {}
        # neue Wörter: due = Einführungs-Index (spreizt sie, statt alle sofort fällig);
        # Priorität steckt schon in der Queue-Reihenfolge.
        raw = [e for e in (data.get('queue') or []) if not e.get('assessed')]
        work = [{'word': e['word'], 'de': e.get('de', ''),
                 'category': e.get('category', ''), 'priority': e.get('priority', 'medium'),
                 'streak': 0, 'due': i, 'shown': False}
                for i, e in enumerate(raw)]
        with S['lock']:
            S['asv'] = {'phase': 'welcome', 'sub': 'ask', 'cur': None,
                        'work': work, 'learn_hold': None, 'seen': 0,
                        'got': data.get('got', 0), 'total': data.get('total', 0),
                        'ratio': data.get('ratio', 0.0), 'busy': False,
                        'coins': int(game.get('coins', 0)),
                        'parts': list(game.get('parts', [])),
                        'parts_total': int(game.get('parts_total', 7)),
                        'crate_at': list(game.get('crate_at', [])),
                        'reveal': None, 'coin_drop': None, 'new_part': None,
                        'staende': [], 'stand_aktiv': None, 'stand_idx': 0,
                        'stand_weg': None, 'verlauf': [], 'blick': None,
                        'flip': None, 'weg': None, 'geschenk': None}
        threading.Thread(target=staende_laden, daemon=True).start()
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

    def watch_theme():
        """ZENTRALE-Theme (~/.config/zentrale/theme) nachpollen und den Wunsch-Modus
        ablegen. Angewandt wird im RENDER-Thread (kein Farb-Race mitten im Frame).
        Fängt auch die 05/21-Auto-Rotation, während das Fenster offen ist."""
        while True:
            m = resolve_theme_mode()
            with S['lock']:
                S['theme_want'] = m
            pygame.time.wait(3000)

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
                # Deckung von außen auf 100 % gesprungen → Drill auf Freischaltung.
                # ALLE Wörter durch = Lucía (kein 75%-Frühstart mehr, GRADUATE_AT=1.0).
                if (S['asv'] and S['core_ratio'] >= 0.999
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

    theme_now = resolve_theme_mode()          # gleich richtig starten (nicht erst dunkel)
    apply_theme(theme_now)
    with S['lock']:
        S['theme_want'] = theme_now
        S['last_user_ms'] = pygame.time.get_ticks()   # Stille-Uhr ab Fenster-Öffnen
    threading.Thread(target=kickoff, daemon=True).start()
    threading.Thread(target=watch_status, daemon=True).start()
    threading.Thread(target=watch_theme, daemon=True).start()
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
        # Theme an ZENTRALE koppeln: gewünschten Modus (vom watch_theme-Poll) hier
        # im Render-Thread anwenden, damit nie mitten im Frame umgefärbt wird.
        with S['lock']:
            want = S['theme_want']
        if want != theme_now:
            theme_now = want
            apply_theme(theme_now)
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
            # Spiel-Animationen tickern (Kisten-Reveal, Münz-Pop, einschwebendes Teil,
            # Auto-Next nach Repeat)
            if S['asv']:
                a2 = S['asv']
                if a2.get('reveal'):
                    a2['reveal']['t'] -= dt
                    if a2['reveal']['t'] <= 0:
                        a2['reveal'] = None
                if a2.get('coin_drop'):
                    a2['coin_drop']['t'] -= dt
                    if a2['coin_drop']['t'] <= 0:
                        a2['coin_drop'] = None
                if a2.get('new_part'):
                    a2['new_part']['t'] = min(1.0, a2['new_part']['t'] + dt / 0.6)
                    if a2['new_part']['t'] >= 1.0:
                        a2['new_part'] = None
                # Frueher lief eine aufgedeckte Karte nach 3 s von selbst weiter
                # (learn_hold). Das ist raus: seit ↓/→ getrennt sind, entscheidet
                # der Mensch, wie lange er auf die Uebersetzung schaut.
                #
                # Karten-Bewegungen. Beide laufen im Render-Takt, damit sie
                # unabhaengig von Netz und Sprachausgabe fluessig bleiben.
                g = a2.get('geschenk')
                if g:
                    g['t'] = g.get('t', 0.0) + dt
                    g['winkel'] = g.get('winkel', 0.0) + dt * 0.9
                    if g.get('konfetti'):
                        _konfetti_takt(g['konfetti'], dt)
                    # Die beiden mittleren Stufen laufen von selbst weiter;
                    # 'zu' und 'teil' warten auf einen Tastendruck.
                    if g['phase'] == 'wackeln' and g['t'] >= GESCHENK_DAUER['wackeln']:
                        g['phase'] = 'auf'; g['t'] = 0.0
                        g['konfetti'] = _konfetti_streuen(
                            w // 2, int(h * 0.46) - int(min(w, h) * 0.10))
                    elif g['phase'] == 'auf' and g['t'] >= GESCHENK_DAUER['auf']:
                        g['phase'] = 'teil'; g['t'] = 0.0
                if a2.get('flip'):                        # Karte dreht sich um
                    a2['flip']['t'] += dt / 0.42
                    if a2['flip']['t'] >= 1.0:
                        a2['flip'] = None
                if a2.get('weg'):                         # Karte geht in den Stapel
                    a2['weg']['t'] += dt / 0.26
                    if a2['weg']['t'] >= 1.0:
                        a2['weg'] = None
                        threading.Thread(target=asv_advance, daemon=True).start()
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
            # Modal bewusst IMMER dunkel (fester Panel-Look) → Text fix hell, damit
            # es auch im Day-Theme lesbar bleibt (nicht an die Palette gekoppelt).
            M_FG, M_DIM = (232, 226, 236), (160, 152, 166)
            pygame.draw.rect(screen, (34, 30, 40), (mx, my, mw, mh), border_radius=12)
            pygame.draw.rect(screen, (96, 86, 104), (mx, my, mw, mh), width=1, border_radius=12)
            screen.blit(fonts['big'].render('Sprache', True, M_FG), (mx + 18, my + 14))
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
                            M_FG if i == sel else M_DIM), (mx + 20, yy))
                yy += rh
            screen.blit(fonts['hud'].render(_sym('↑/↓ · Enter · 1–9 · Esc'), True, M_DIM),
                        (mx + 18, yy + 6))

        pygame.display.flip()

    pygame.quit()


if __name__ == '__main__':
    main()
