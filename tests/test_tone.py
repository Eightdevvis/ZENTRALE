"""Tests für core/tone.py — den Ton-Erzeuger des TUI-Klaviers.

Geprüft wird die RECHNUNG (Voice: Halbton → Wellenform), nicht die Soundkarte:
Frequenzen, Hüllkurve, Aussteuerung, Abbruchbedingung. Ein Gerät braucht davon
nichts — die Tests laufen auf jedem Knoten, auch headless im CI.

Dazu die Wiedergabe (Playback) gegen einen Attrappen-Synth: spielt sie wirklich
jede Note mit ihrer eigenen Länge und in der richtigen Reihenfolge, und lässt
sie sich mittendrin abbrechen?
"""
import time

import pytest

import tone

np = pytest.importorskip("numpy", reason="numpy ist Pflicht-Dependency (requirements.txt)")


# ── Frequenzen ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("midi,hz", [
    (69, 440.0),      # a' — der Bezugston
    (57, 220.0),      # eine Oktave drunter
    (81, 880.0),      # eine drüber
    (60, 261.6256),   # c' (mittleres C)
])
def test_midi_to_freq_bekannte_toene(midi, hz):
    assert tone.midi_to_freq(midi) == pytest.approx(hz, rel=1e-4)


def test_oktave_verdoppelt_die_frequenz():
    for n in range(21, 97):
        assert tone.midi_to_freq(n + 12) == pytest.approx(2 * tone.midi_to_freq(n))


# ── Voice: die eigentliche Wellenform ───────────────────────────────────────
def _render(voice, blocks=8, frames=256):
    out = []
    for _ in range(blocks):
        buf = np.zeros(frames, dtype=np.float32)
        voice.render(buf, np)
        out.append(buf.copy())
    return np.concatenate(out)


def test_voice_klingt_und_bleibt_im_rahmen():
    sig = _render(tone.Voice(60, dur_ms=400))
    assert np.isfinite(sig).all()
    assert np.abs(sig).max() > 0.05          # es kommt wirklich Ton raus
    assert np.abs(sig).max() <= 2.0          # und nichts absurd Lautes


def test_voice_faengt_bei_null_an_und_klingt_ab():
    """Anschlag wird angerampt (sonst knackst es) und fällt danach ab."""
    sig = _render(tone.Voice(60, dur_ms=400), blocks=16)
    assert abs(sig[0]) < 1e-6
    erste = np.abs(sig[:1024]).max()
    spaete = np.abs(sig[-1024:]).max()
    assert spaete < erste


def test_voice_ist_nach_seiner_dauer_fertig():
    v = tone.Voice(60, dur_ms=100, samplerate=44100)
    # 100 ms * 1.6 Ausklang ≈ 7056 Samples → nach 12 Blöcken à 1024 sicher durch
    for _ in range(12):
        v.render(np.zeros(1024, dtype=np.float32), np)
    assert v.done


def test_fertige_voice_rechnet_nicht_weiter():
    v = tone.Voice(60, dur_ms=20)
    for _ in range(20):
        v.render(np.zeros(1024, dtype=np.float32), np)
    assert v.done
    buf = np.zeros(1024, dtype=np.float32)
    v.render(buf, np)
    assert not buf.any()


def test_hohe_toene_lassen_teiltoene_ueber_nyquist_weg():
    """Sonst falten sie als Alias-Pfeifen zurück — hörbar falsch."""
    hoch = tone.Voice(108)            # C8 ≈ 4186 Hz
    tief = tone.Voice(36)
    assert len(hoch.parts) < len(tief.parts)
    for mult, _amp in hoch.parts:
        assert hoch.freq * mult < hoch.sr / 2


def test_laengere_dauer_klingt_laenger():
    kurz = _render(tone.Voice(60, dur_ms=150), blocks=16)
    lang = _render(tone.Voice(60, dur_ms=900), blocks=16)
    assert np.abs(lang[-512:]).max() > np.abs(kurz[-512:]).max()


def test_voices_addieren_sich_zum_akkord():
    """Mehrere Voices schreiben in DENSELBEN Puffer (Polyphonie)."""
    buf = np.zeros(512, dtype=np.float32)
    for n in (60, 64, 67):
        tone.Voice(n, dur_ms=400).render(buf, np)
    einzeln = np.zeros(512, dtype=np.float32)
    tone.Voice(60, dur_ms=400).render(einzeln, np)
    assert np.abs(buf).max() > np.abs(einzeln).max()


# ── Synth ohne Gerät: darf nie werfen, bleibt einfach still ─────────────────
def test_synth_ohne_geraet_ist_still_aber_harmlos():
    s = tone.Synth()
    assert s.strike(60) is False          # nicht gestartet → kein Ton, kein Fehler
    s.silence()
    s.close()


def test_available_wirft_nicht():
    assert tone.available() in (True, False)


@pytest.mark.parametrize("raw,erwartet", [
    (None, None), ("", None), ("   ", None),
    ("0", 0), ("2", 2),
    ("hw:0,0", "hw:0,0"), ("pipewire", "pipewire"),
])
def test_geraet_aus_der_umgebung(monkeypatch, raw, erwartet):
    """ZENTRALE_AUDIO_DEVICE: Zahl = Index, Text = Name, leer = System-Default.
    Nötig auf Knoten, deren Default über einen toten Audio-Server läuft (dort
    BLOCKIERT PortAudio beim Öffnen)."""
    if raw is None:
        monkeypatch.delenv("ZENTRALE_AUDIO_DEVICE", raising=False)
    else:
        monkeypatch.setenv("ZENTRALE_AUDIO_DEVICE", raw)
    assert tone.Synth().device == erwartet


def test_explizites_geraet_schlaegt_die_umgebung(monkeypatch):
    monkeypatch.setenv("ZENTRALE_AUDIO_DEVICE", "7")
    assert tone.Synth(device="hw:1,0").device == "hw:1,0"


# ── Playback: Melodie abspielen ─────────────────────────────────────────────
class FakeSynth:
    """Merkt sich nur, was angeschlagen wurde (kein Gerät, keine Rechnung)."""

    def __init__(self):
        self.hits = []

    def strike(self, midi, dur_ms=0, gain=1.0):
        self.hits.append((midi, dur_ms, time.time()))
        return True

    def silence(self):
        pass


def test_playback_spielt_jede_note_mit_ihrer_eigenen_laenge():
    syn = FakeSynth()
    notes = [{"n": 60, "t": 0, "d": 120}, {"n": 64, "t": 30, "d": 700},
             {"n": 67, "t": 60, "d": 90}]
    seen = []
    pb = tone.play_sequence(syn, notes, on_note=lambda n, d: seen.append((n, d)))
    for _ in range(200):
        if not pb.running:
            break
        time.sleep(0.01)
    assert [h[0] for h in syn.hits] == [60, 64, 67]
    assert [h[1] for h in syn.hits] == [120, 700, 90]     # echte Haltedauern
    assert seen == [(60, 120), (64, 700), (67, 90)]


def test_playback_haelt_die_pausen_ein():
    syn = FakeSynth()
    pb = tone.play_sequence(syn, [{"n": 60, "t": 0, "d": 50},
                                  {"n": 62, "t": 150, "d": 50}])
    for _ in range(200):
        if not pb.running:
            break
        time.sleep(0.01)
    assert len(syn.hits) == 2
    assert syn.hits[1][2] - syn.hits[0][2] > 0.10        # ~150 ms Abstand


def test_playback_laesst_sich_abbrechen():
    syn = FakeSynth()
    pb = tone.play_sequence(syn, [{"n": 60 + i, "t": i * 400, "d": 100}
                                  for i in range(10)])
    time.sleep(0.05)
    pb.stop()
    time.sleep(0.1)
    assert not pb.running
    assert len(syn.hits) <= 2


def test_playback_sortiert_und_uebersteht_muell():
    syn = FakeSynth()
    notes = [{"n": 67, "t": 40, "d": 50}, {"n": 60, "t": 0, "d": 50},
             "kein dict", {"kein": "n"}, None]
    pb = tone.play_sequence(syn, notes)
    for _ in range(200):
        if not pb.running:
            break
        time.sleep(0.01)
    assert [h[0] for h in syn.hits] == [60, 67]


def test_playback_meldet_das_ende():
    syn = FakeSynth()
    fertig = []
    pb = tone.play_sequence(syn, [{"n": 60, "t": 0, "d": 50}],
                            on_done=lambda: fertig.append(1))
    for _ in range(200):
        if not pb.running:
            break
        time.sleep(0.01)
    time.sleep(0.05)
    assert fertig == [1]


def test_playback_ohne_noten_endet_sofort():
    syn = FakeSynth()
    pb = tone.play_sequence(syn, [])
    time.sleep(0.05)
    assert not pb.running
    assert syn.hits == []
