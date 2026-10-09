"""Audio- und Abgleich-Schalter laufen über ai_config.setting (2026-10-08).

Vorher lasen core/audio.py (WHISPER_URL, TTS_URL, DEFAULT_LANG), brain.py
(TUTOR_PRESENCE_REACT) und datasync.py (ZENTRALE_AUTOPUSH) die Umgebung
selbst — beim Import, an der Rangfolge vorbei, nicht live umschaltbar.
"""
import io
import json

import pytest

import ai_config
import audio
import brain
import datasync
import events


@pytest.fixture
def ohne_override(monkeypatch):
    monkeypatch.setattr(ai_config, "_overrides", {})
    for n in ("WHISPER_URL", "TTS_URL", "DEFAULT_LANG", "TUTOR_PRESENCE_REACT",
              "ZENTRALE_WHISPER_URL", "ZENTRALE_TTS_URL", "ZENTRALE_DEFAULT_LANG",
              "ZENTRALE_TUTOR_PRESENCE_REACT", "ZENTRALE_AUTOPUSH"):
        monkeypatch.delenv(n, raising=False)


class _Antwort(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _fang_urlopen(monkeypatch, antwort=b'{"text": "hola"}'):
    gesehen = []

    def fake(req, timeout=None):
        gesehen.append(req if isinstance(req, str) else req.full_url)
        if isinstance(req, str):
            return _Antwort(b"{}")
        gesehen.append(req.data)
        return _Antwort(antwort)
    monkeypatch.setattr(audio.urllib.request, "urlopen", fake)
    return gesehen


def test_whisper_adresse_und_sprache_aus_der_einstellung(ohne_override, monkeypatch):
    g = _fang_urlopen(monkeypatch)
    ai_config.set_override("whisper_url", "http://pc:5050/")
    ai_config.set_override("default_lang", "es")
    assert audio.transcribe(b"RIFF") == "hola"
    assert g[0] == "http://pc:5050/transcribe"
    assert b'name="lang"\r\n\r\nes' in g[1]


def test_live_umschalten_ohne_neustart(ohne_override, monkeypatch):
    g = _fang_urlopen(monkeypatch, antwort=b"WAV")
    ai_config.set_override("tts_url", "http://a:1")
    audio.synthesize("hola", lang="es")
    ai_config.set_override("tts_url", "http://b:2")
    audio.synthesize("hola", lang="es")
    assert [u for u in g if isinstance(u, str)] == ["http://a:1/speak", "http://b:2/speak"]
    assert json.loads(g[1])["lang"] == "es"


def test_neuer_env_name_gilt(ohne_override, monkeypatch):
    g = _fang_urlopen(monkeypatch)
    monkeypatch.setenv("ZENTRALE_WHISPER_URL", "http://neu:5050")
    audio.transcribe(b"RIFF", lang="de")
    assert g[0] == "http://neu:5050/transcribe"


def test_alter_env_name_gilt_noch_mit_hinweis(ohne_override, monkeypatch, capsys):
    g = _fang_urlopen(monkeypatch)
    monkeypatch.setattr(ai_config, "_alt_gemeldet", set())
    monkeypatch.setenv("WHISPER_URL", "http://alt:5050")
    audio.transcribe(b"RIFF", lang="de")
    assert g[0] == "http://alt:5050/transcribe"
    assert "ZENTRALE_WHISPER_URL" in capsys.readouterr().out


def test_neuer_name_schlaegt_alten(ohne_override, monkeypatch):
    g = _fang_urlopen(monkeypatch)
    monkeypatch.setenv("WHISPER_URL", "http://alt:5050")
    monkeypatch.setenv("ZENTRALE_WHISPER_URL", "http://neu:5050")
    audio.transcribe(b"RIFF", lang="de")
    assert g[0] == "http://neu:5050/transcribe"


def test_anwesenheit_geht_als_ereignis_an_die_apps(ohne_override, monkeypatch):
    """Seit 2026-10-09 ruft brain.py keinen Tutor-Code mehr, sondern schickt
    das Ereignis „anwesenheit" an die Apps (core/hub_ereignisse.py). Ob die
    App reagiert, ist ihre Einstellung (beim Tutor: presence_react)."""
    import hub_ereignisse
    gesendet = []
    monkeypatch.setattr(hub_ereignisse, "senden", lambda name, *a, **k: gesendet.append(name) or 1)
    _brain(events.PRESENCE_DETECTED)
    assert gesendet == ["anwesenheit"]


def _brain(ev):
    return brain.process_event(ev)


def test_autopush_ueber_die_einstellung(ohne_override, monkeypatch):
    angestossen = []
    monkeypatch.setattr(ai_config, "_config", {})   # kein abgleich_weg=mitte
    monkeypatch.setattr(datasync.shutil, "which", lambda n: angestossen.append(n) or None)
    datasync.notify_change()
    assert angestossen == [], "ohne autopush passiert nichts"
    ai_config.set_override("autopush", "1")
    try:
        datasync.notify_change()
    finally:
        ai_config.set_override("autopush", "")
    assert angestossen, "mit autopush=1 wird der Helfer gesucht"
