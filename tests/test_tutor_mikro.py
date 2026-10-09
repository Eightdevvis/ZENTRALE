"""tutor/mikro.py — das Ohr des Zimmers, ohne Hardware.

Künstliche Frames statt Mikro: geprüft wird die Zählerei (wann ist eine
Äußerung fertig, was ist Geräusch, was wird verworfen) und dass das echte
Mikro nur geöffnet wird, wenn Zuhören an ist (2026-10-08: vorher immer, auch
mit --no-mic — PortAudio riss die Zimmer-Tests beim Beenden ab).
"""
import os
import sys
import threading
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tutor import mikro   # noqa: E402

FRAME = b"\x00\x00" * int(mikro.MIC_RATE * mikro.MIC_FRAME_MS / 1000)


def _fuettern(ohr, folge):
    """folge: [(anzahl, is_sp, rms)] → alle Ereignisse."""
    ev = []
    for n, sp, rms in folge:
        for _ in range(n):
            ev += ohr.frame(FRAME, sp, rms=rms)
    return ev


def _ms(n):
    return n // mikro.MIC_FRAME_MS


def test_aeusserung_nach_pause_fertig():
    ohr = mikro.Ohr()
    ev = _fuettern(ohr, [(_ms(600), True, 1000), (_ms(mikro.MIC_SILENCE_MS), False, 10)])
    arten = [a for a, _ in ev]
    assert arten.count("aeusserung") == 1
    assert ("hoert", True) in ev and ("hoert", False) in ev


def test_zu_kurz_wird_verworfen():
    ohr = mikro.Ohr()
    ev = _fuettern(ohr, [(_ms(200), True, 1000), (_ms(mikro.MIC_SILENCE_MS), False, 10)])
    assert "aeusserung" not in [a for a, _ in ev], "Husten/Blips gehen nicht an Whisper"


def test_harte_obergrenze_schneidet():
    ohr = mikro.Ohr()
    ev = _fuettern(ohr, [(_ms(mikro.MIC_MAX_MS) + 5, True, 1000)])
    assert [a for a, _ in ev].count("aeusserung") == 1


def test_geraeusch_ueber_grundrauschen():
    ohr = mikro.Ohr()
    _fuettern(ohr, [(50, False, 50)])                       # leiser Raum
    ev = _fuettern(ohr, [(_ms(mikro.PRES_NOISE_MS) + 1, False, 3000)])
    assert "geraeusch" in [a for a, _ in ev]


def test_musik_ist_kein_geraeusch():
    ohr = mikro.Ohr()
    _fuettern(ohr, [(50, False, 50)])
    ev = []
    for _ in range(_ms(mikro.PRES_NOISE_MS) + 5):
        ev += ohr.frame(FRAME, False, musik=True, rms=3000)
    assert "geraeusch" not in [a for a, _ in ev]


def test_gate_verwirft_angefangene_aeusserung():
    ohr = mikro.Ohr()
    _fuettern(ohr, [(_ms(400), True, 1000)])
    assert ohr.zuruecksetzen() == [("hoert", False)]
    ev = _fuettern(ohr, [(_ms(mikro.MIC_SILENCE_MS), False, 10)])
    assert "aeusserung" not in [a for a, _ in ev]


def test_pcm_to_wav_ist_wav():
    assert mikro.pcm_to_wav(FRAME)[:4] == b"RIFF"


def _zimmer(mic):
    return {"lock": threading.Lock(), "mic": mic, "pause": False, "pmenu": None,
            "speaking": False, "busy": False, "streaming": False, "music": None,
            "hearing": False, "mic_err": "", "activity_ms": 0, "noise_floor": 0.0}


def test_ohne_zuhoeren_wird_das_mikro_nie_geoeffnet(monkeypatch):
    geoeffnet = []
    sd = types.SimpleNamespace(RawInputStream=lambda **k: geoeffnet.append(k))
    monkeypatch.setitem(sys.modules, "sounddevice", sd)
    monkeypatch.setitem(sys.modules, "webrtcvad", types.SimpleNamespace(Vad=lambda n: None))
    S = _zimmer(mic=False)
    t = threading.Thread(target=mikro.hoeren, args=(S, lambda w: None, lambda: 0))
    t.start()
    t.join(timeout=0.5)
    with S["lock"]:
        S["ende"] = True
    t.join(timeout=2)
    assert not t.is_alive(), "ende muss die Schleife beenden"
    assert geoeffnet == [], "mit --no-mic darf kein Mikro aufgehen"


def test_ende_schliesst_den_strom(monkeypatch):
    zu = []

    class Strom:
        def __init__(self, **k): pass
        def start(self): pass
        def read(self, n):
            return FRAME, False
        def stop(self): zu.append("stop")
        def close(self): zu.append("close")

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawInputStream=Strom))
    monkeypatch.setitem(sys.modules, "webrtcvad", types.SimpleNamespace(
        Vad=lambda n: types.SimpleNamespace(is_speech=lambda f, r: False)))
    S = _zimmer(mic=True)
    t = threading.Thread(target=mikro.hoeren, args=(S, lambda w: None, lambda: 0))
    t.start()
    with S["lock"]:
        S["ende"] = True
    t.join(timeout=2)
    assert zu == ["stop", "close"]
