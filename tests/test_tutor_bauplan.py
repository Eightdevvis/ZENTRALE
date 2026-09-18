"""Der Bauplan (memory/tutor/bauplan.md) gegen den Code — damit er nicht driftet.

Sasha 2026-09-17: das Dokument muss kontinuierlich synchron bleiben, alle
Verzeichnisse und Artefakte enthalten. Hoffen reicht nicht: dieser Test liest
die Tabellen des Bauplans und wird rot, wenn Doku und Code auseinanderlaufen —
in BEIDE Richtungen (Pfad im Bauplan fehlt im Repo / Route im Code fehlt im
Bauplan).
"""

import json
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BAUPLAN = os.path.join(ROOT, "memory", "tutor", "bauplan.md")


def _text():
    with open(BAUPLAN, encoding="utf-8") as f:
        return f.read()


def _abschnitt(text, ueberschrift):
    """Der Text eines '## N. …'-Abschnitts bis zur nächsten '## '-Überschrift."""
    m = re.search(r"^## [^\n]*" + re.escape(ueberschrift) + r"[^\n]*\n", text, re.M)
    assert m, "Abschnitt fehlt im Bauplan: " + ueberschrift
    rest = text[m.end():]
    n = re.search(r"^## ", rest, re.M)
    return rest[:n.start()] if n else rest


def _erste_zellen(abschnitt):
    """Der Inhalt der ersten `code`-Zelle jeder Tabellenzeile."""
    raus = []
    for line in abschnitt.splitlines():
        if not line.startswith("| `"):
            continue
        m = re.match(r"\| `([^`]+)` \|", line)
        if m:
            raus.append(m.group(1))
    return raus


# ── 2. Artefakte ─────────────────────────────────────────────────────────

def test_jeder_pfad_im_bauplan_existiert():
    pfade = _erste_zellen(_abschnitt(_text(), "Verzeichnisbaum"))
    assert len(pfade) > 20, "Artefakt-Tabelle wirkt leer"
    fehlend = [p for p in pfade if not os.path.exists(os.path.join(ROOT, p))]
    assert not fehlend, "im Bauplan gelistet, aber nicht im Repo: %s" % fehlend


def test_jedes_tutor_modul_steht_im_bauplan():
    pfade = set(_erste_zellen(_abschnitt(_text(), "Verzeichnisbaum")))
    module = sorted(f for f in os.listdir(os.path.join(ROOT, "tutor"))
                    if f.endswith(".py"))
    fehlend = ["tutor/" + m for m in module if "tutor/" + m not in pfade]
    assert not fehlend, "Modul ohne Zeile im Bauplan: %s" % fehlend


# ── 3. Routen ────────────────────────────────────────────────────────────

def _routen_im_code():
    with open(os.path.join(ROOT, "ui", "app.py"), encoding="utf-8") as f:
        src = f.read()
    return set(re.findall(r"@app\.route\('(/api/(?:tutor[^']*|speak|transcribe))'", src))


def test_routen_stimmen_in_beide_richtungen():
    doku = set(_erste_zellen(_abschnitt(_text(), "Routen")))
    code = _routen_im_code()
    assert doku == code, ("nur im Bauplan: %s / nur im Code: %s"
                          % (sorted(doku - code), sorted(code - doku)))


# ── 4. Sprachpakete ──────────────────────────────────────────────────────

PFLICHT_DATEIEN = ["__init__.py", "prompt.md", "vocab_hint.md", "expect.json",
                   "core_vocab.json", "tool_texts.json",
                   os.path.join("seeds", "news.json"), os.path.join("seeds", "tv.json")]
PFLICHT_FELDER = ["name", "persona_name", "country", "enabled", "reading",
                  "stt_lang", "tts_lang", "provider", "model", "system_prompt",
                  "vocab_hint", "core_vocab", "core_hint", "situation",
                  "status_labels", "vocab_labels", "phrases", "native_names", "seeds"]
SITUATION_KEYS = ["prefix", "suffix", "join", "open", "open_focus", "nudge_idle",
                  "nudge_focus_yes", "nudge_focus_no", "nudge_sound"]
STATUS_KEYS = ["new", "understood", "learning", "learned", "intuitive"]
LEBENDE_TOOLS = ["introduce_new", "express", "get_structures", "introduce_structure",
                 "increment_structure", "watch_tv", "turn_off_tv", "play_music",
                 "stop_music", "get_local_news", "get_due_reviews", "show_thought"]
LEGACY_TOOLS = ["mark_known", "get_confirmed_vocab", "get_testing_vocab",
                "increment_correct_use"]


def _pakete():
    from tutor import langs
    return [(c, langs.PROFILES[c]) for c in langs.enabled()]


@pytest.mark.parametrize("code,prof", _pakete(), ids=lambda x: x if isinstance(x, str) else "")
def test_aktives_paket_ist_vollstaendig(code, prof):
    d = os.path.join(ROOT, "tutor", "langs", code)
    fehlend = [f for f in PFLICHT_DATEIEN if not os.path.exists(os.path.join(d, f))]
    assert not fehlend, "%s: Dateien fehlen: %s" % (code, fehlend)
    leer = [k for k in PFLICHT_FELDER if not prof.get(k)]
    assert not leer, "%s: Profil-Felder leer: %s" % (code, leer)
    sit = prof["situation"]
    assert all(k in sit for k in SITUATION_KEYS), "%s: situation unvollständig" % code
    assert all(k in prof["status_labels"] for k in STATUS_KEYS), "%s: status_labels" % code
    from tutor import tools
    fehl_phr = [k for k in tools._DEFAULT_PHRASES if k not in prof["phrases"]]
    assert not fehl_phr, "%s: phrases fehlen (deutsche Defaults würden leaken): %s" % (code, fehl_phr)
    tt = prof.get("tool_texts") or {}
    fehl_tt = [t for t in LEBENDE_TOOLS if t not in tt]
    assert not fehl_tt, "%s: tool_texts fehlen: %s" % (code, fehl_tt)
    tot = [t for t in LEGACY_TOOLS if t in tt]
    assert not tot, "%s: Legacy-Tool-Texte raus: %s" % (code, tot)
    assert "{native}" in prof["system_prompt"], "%s: prompt.md braucht {native}" % code
    assert "{words}" in prof["vocab_hint"], "%s: vocab_hint.md braucht {words}" % code
    for e in prof["core_vocab"]:
        assert e.get("word") and isinstance(e.get("gloss"), dict) and e["gloss"].get("en"), \
            "%s: core_vocab-Eintrag ohne gloss.en: %s" % (code, e)
        assert e.get("priority") in ("critical", "high", "medium", "low"), e
    assert len(prof["core_vocab"]) >= 60, "%s: core_vocab zu klein" % code
    assert "{words}" in prof["core_hint"] and "{got}" in prof["core_hint"], code


def test_kategorien_der_kernwoerter_kennt_das_zimmer():
    """Das Zimmer beschriftet Kategorien (room._CAT_DE); eine unbekannte
    Kategorie stünde roh auf der Karte."""
    src = open(os.path.join(ROOT, "tutor", "room.py"), encoding="utf-8").read()
    m = re.search(r"_CAT_DE\s*=\s*\{(.*?)\n\}", src, re.S)
    assert m, "_CAT_DE nicht gefunden"
    bekannt = set(re.findall(r"'([a-z_]+)':", m.group(1)))
    for code, prof in _pakete():
        fremd = sorted({e.get("category") for e in prof["core_vocab"]} - bekannt)
        assert not fremd, "%s: Kategorien ohne Beschriftung im Zimmer: %s" % (code, fremd)


def test_tts_engine_fuer_jede_aktive_sprache():
    src = open(os.path.join(ROOT, "services", "tts_service.py"), encoding="utf-8").read()
    for code, prof in _pakete():
        assert re.search(r"_engines\[['\"]%s['\"]\]|['\"]%s['\"]\s*:" % (code, code), src) \
            or ("_try_load_%s" % code) in src, "%s: keine TTS-Engine in tts_service.py" % code
