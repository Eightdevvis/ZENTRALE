"""Spielstände bluten nicht ineinander — die Tests, die das beweisen.

Sasha 2026-09-18: »vor allem, dass die Vokabelstates der gelernten Vokabeln
jeweils nur zum Spielstand gehören und nicht übereinander fließen.« Jeder Test
hier ist eine konkrete Art, wie Stände früher ineinander laufen konnten —
und zeigt, dass sie es nicht mehr tun. Alles gegen echte Dateien in tmp_path,
mit den echten Modulen (tools, memory, srs, session, tutor_port); nur das
Sprachmodell wird ersetzt.
"""

import hashlib
import json
import os
import sys
import threading
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "core"))

from tutor import staende, tools, memory, srs, session, config   # noqa: E402


@pytest.fixture
def welt(tmp_path, monkeypatch):
    """Frische Daten-Welt: alle Speicherorte zeigen auf tmp_path, keine Session."""
    root = str(tmp_path)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    monkeypatch.setattr(config, "_overrides", {})
    session.deactivate()
    return root


def _stand(root, name, lang, level=0):
    sid = staende.anlegen(root, name, lang=lang, level=level)
    staende.waehlen(root, sid)
    return sid


def _baum_hash(pfad):
    """Fingerabdruck eines Stand-Ordners: jede Datei, jeder Inhalt."""
    h = hashlib.sha256()
    for dp, dn, fn in sorted(os.walk(pfad)):
        for f in sorted(fn):
            p = os.path.join(dp, f)
            h.update(os.path.relpath(p, pfad).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


# ── 1. Vokabeln: gleiche Sprache, zwei Stände ────────────────────────────

def test_gesprochene_woerter_bleiben_im_eigenen_stand(welt):
    """Zwei Spanisch-Stände. Was in A gesprochen wird, zählt nur in A."""
    a = _stand(welt, "A", "es")
    tools.introduce_new("agua", lang="es")
    tools.note_spoken("quiero agua", "es")
    tools.note_spoken("agua agua", "es")
    st_a = {e["word"]: e for e in tools._load_raw("es")}
    assert st_a["agua"]["spoken"] >= 2

    b = _stand(welt, "B", "es")
    assert tools._load_raw("es") == [], "B beginnt leer — nichts aus A"
    tools.note_spoken("agua", "es")      # in B ist 'agua' nicht getrackt → kein Treffer
    assert tools._load_raw("es") == []

    staende.waehlen(welt, a)
    assert {e["word"]: e["spoken"] for e in tools._load_raw("es")}["agua"] >= 2, "A unverändert"


def test_status_derselben_vokabel_ist_pro_stand(welt):
    """'agua' kann in A 'learned' und in B 'new' sein — gleichzeitig."""
    a = _stand(welt, "A", "es")
    tools.introduce_new("agua", lang="es")
    for _ in range(4):
        tools.note_spoken("agua", "es")
    assert tools.word_status({e["word"]: e for e in tools._load_raw("es")}["agua"]) == "learned"

    b = _stand(welt, "B", "es")
    tools.introduce_new("agua", lang="es")
    assert tools.word_status({e["word"]: e for e in tools._load_raw("es")}["agua"]) == "new"

    staende.waehlen(welt, a)
    assert tools.word_status({e["word"]: e for e in tools._load_raw("es")}["agua"]) == "learned"


def test_drill_muenzen_und_kisten_bleiben_im_stand(welt):
    a = _stand(welt, "A", "es")
    for c in tools._core_list("es")[:20]:
        tools.assessment_answer("es", c["word"], "known")
    ga = tools.game_state("es")
    got_a = tools.core_coverage("es")[0]
    assert got_a == 20

    b = _stand(welt, "B", "es")
    assert tools.core_coverage("es")[0] == 0
    assert tools.game_state("es").get("coins", 0) == 0
    assert tools.game_state("es").get("parts", []) == []

    staende.waehlen(welt, a)
    assert tools.game_state("es") == ga and tools.core_coverage("es")[0] == 20


def test_srs_faelligkeiten_pro_stand(welt):
    if not srs._OK:
        pytest.skip("fsrs-Bibliothek fehlt")
    a = _stand(welt, "A", "es")
    for w in ("agua", "mesa", "silla"):
        tools.introduce_new(w, lang="es"); srs.ensure(w, "es")
    assert set(srs._load("es")) == {"agua", "mesa", "silla"}
    assert srs.stats("es")["tracked"] == 3

    b = _stand(welt, "B", "es")
    assert srs._load("es") == {} and srs.stats("es")["tracked"] == 0

    staende.waehlen(welt, a)
    assert srs.stats("es")["tracked"] == 3


def test_persona_notizen_pro_stand(welt):
    a = _stand(welt, "A", "es")
    memory._save_notes({"facts": ["mag Kaffee"], "topics": ["Kaffee"]}, "es")
    assert "Kaffee" in json.dumps(memory._load_notes("es"), ensure_ascii=False)

    b = _stand(welt, "B", "es")
    assert "Kaffee" not in json.dumps(memory._load_notes("es"), ensure_ascii=False)

    staende.waehlen(welt, a)
    assert "Kaffee" in json.dumps(memory._load_notes("es"), ensure_ascii=False)


# ── 2. Wechsel mitten in einer langen Operation ──────────────────────────

def test_notiz_wird_verworfen_wenn_stand_waehrenddessen_wechselt(welt, monkeypatch):
    """memory.remember: Laden → LLM (~1 s) → Speichern. Wechselt der Stand
    dazwischen, wird NICHT in den neuen Stand geschrieben."""
    a = _stand(welt, "A", "es")
    b = staende.anlegen(welt, "B", lang="es")
    verworfen = []

    import ai_backends
    monkeypatch.setattr(ai_backends, "status", lambda: {"local": True})

    def fake_distill(backend, provider, model, user_msg):
        staende.waehlen(welt, b)              # Sasha klickt mitten im LLM-Aufruf um
        return json.dumps({"facts": ["Geheimnis aus A"], "topics": []})
    monkeypatch.setattr(memory, "_distill", fake_distill)
    monkeypatch.setattr(memory, "_parse_notes", lambda raw: json.loads(raw))
    monkeypatch.setattr("builtins.print", lambda *a, **k: verworfen.append(" ".join(map(str, a))))

    memory.remember("hola", "hola qué tal", "es")

    assert any("verworfen" in v for v in verworfen), verworfen
    assert staende.aktiv(welt) == b
    assert "Geheimnis" not in json.dumps(memory._load_notes("es"), ensure_ascii=False), "B blieb sauber"
    staende.waehlen(welt, a)
    assert "Geheimnis" not in json.dumps(memory._load_notes("es"), ensure_ascii=False), "A auch (Write verworfen)"


def test_antwort_wird_verworfen_wenn_stand_waehrend_des_streams_wechselt(welt, monkeypatch):
    """session.respond_stream: der Stand wechselt, während die Persona noch
    antwortet → weder Verlauf noch Gedächtnis des neuen Stands bekommen den Turn."""
    a = _stand(welt, "A", "es")
    b = staende.anlegen(welt, "B", lang="es")
    session.activate()
    assert session.active_lang() == "es"

    def fake_stream(messages, system=None, tools=None, tool_executor=None, **kw):
        yield "hola "
        staende.waehlen(welt, b)              # Wechsel mitten im Stream
        yield "guapa"
    import ai
    monkeypatch.setattr(ai, "chat_stream", fake_stream)
    monkeypatch.setattr(session, "_resolve",
                        lambda: (session.langs.get("es"), "ollama", {"kind": "ollama"}, "x"))
    monkeypatch.setattr(memory, "remember", lambda *a, **k: pytest.fail("remember darf nicht laufen"))

    toks = list(session.respond_stream("hola"))
    assert "".join(toks) == "hola guapa"
    hist = session.get_history()
    assert not any(m["role"] == "assistant" for m in hist), "Antwort nicht in den Verlauf"
    session.deactivate()


def test_wechsel_wartet_auf_tools_schreibfolge(welt):
    """tools hält stand_lock während Lesen-Ändern-Schreiben; ein Wechsel kommt
    erst danach dran — die Schreibfolge landet im alten Stand."""
    a = _stand(welt, "A", "es")
    b = staende.anlegen(welt, "B", lang="es")
    ablauf = []

    orig_write = tools._write_raw

    def langsam_write(entries, lang=None):
        ablauf.append("schreibe-start"); time.sleep(0.3); orig_write(entries, lang); ablauf.append("schreibe-ende")
    tools._write_raw = langsam_write
    try:
        t = threading.Thread(target=lambda: tools.introduce_new("mesa", lang="es")); t.start()
        time.sleep(0.05)
        staende.waehlen(welt, b); ablauf.append("gewechselt")
        t.join()
    finally:
        tools._write_raw = orig_write
    assert ablauf == ["schreibe-start", "schreibe-ende", "gewechselt"]
    assert tools._load_raw("es") == [], "B leer"
    staende.waehlen(welt, a)
    assert [e["word"] for e in tools._load_raw("es")] == ["mesa"], "mesa liegt in A"


# ── 3. Sprache: Stand entscheidet, nichts anderes ────────────────────────

def test_session_sprache_folgt_dem_stand_nicht_der_config(welt, monkeypatch):
    _stand(welt, "Spanisch", "es")
    monkeypatch.setattr(config, "_overrides", {"lang": "zh"})     # alter Config-Key, muss egal sein
    monkeypatch.setenv("TUTOR_LANG", "zh")
    assert session.active_lang() == "es"
    session.activate()
    assert session.active_lang() == "es" and session.passt_zum_stand()
    _stand(welt, "Deutsch", "de")
    assert not session.passt_zum_stand(), "laufende es-Session passt nicht zum de-Stand"
    session.deactivate()
    assert session.active_lang() == "de"


def test_fremdsprachiger_zugriff_legt_nichts_an(welt):
    d = _stand(welt, "Deutsch", "de")
    for fn in (lambda: tools._dir("es"), lambda: memory.mem_path("es"), lambda: srs._file("es")):
        with pytest.raises(staende.StandSprache):
            fn()
    assert sorted(os.listdir(os.path.join(welt, "staende", d))) == ["de", "stand.json"]


def test_prompt_vokabel_kommt_aus_dem_stand(welt):
    """prompt_vocab: Kernwörter (Paket) + User-Wörter des STANDS — nie die eines anderen."""
    a = _stand(welt, "A", "es")
    tools.introduce_new("churros", lang="es")
    woerter_a = {w for w, _ in tools.prompt_vocab("es")}
    assert "churros" in woerter_a
    _stand(welt, "B", "es")
    woerter_b = {w for w, _ in tools.prompt_vocab("es")}
    assert "churros" not in woerter_b and "agua" in woerter_b, "B: nur Kernwörter"


# ── 4. Löschen / Anlegen: Nachbarn unberührt ─────────────────────────────

def test_loeschen_laesst_nachbarn_bytegleich(welt):
    a = _stand(welt, "A", "es")
    tools.introduce_new("agua", lang="es"); tools.note_spoken("agua", "es")
    memory._save_notes({"facts": ["A"], "topics": []}, "es")
    tools.assessment_answer("es", "yo", "known")
    fingerabdruck = _baum_hash(os.path.join(welt, "staende", a))

    b = _stand(welt, "B", "es")
    tools.introduce_new("mesa", lang="es")
    staende.loeschen(welt, b)

    assert _baum_hash(os.path.join(welt, "staende", a)) == fingerabdruck, "A ist bis aufs Byte unverändert"
    assert staende.aktiv(welt) == a


def test_level_beim_anlegen_trifft_nur_den_neuen_stand(welt):
    a = _stand(welt, "A", "es", level=0)
    assert tools.core_coverage("es")[0] == 0
    b = _stand(welt, "B", "es", level=2)
    tools.level_anwenden("es", 2)
    assert tools.core_graduated("es")
    staende.waehlen(welt, a)
    assert tools.core_coverage("es")[0] == 0 and not tools.core_graduated("es")


# ── 5. Über den Kern (tutor_port), wie die Fronten es tun ────────────────

def test_tutor_port_end_to_end_zwei_sprachen(welt):
    import tutor_port
    r = tutor_port.stand_anlegen("Lucía", lang="es", level=1)
    assert r["ok"]
    assert tutor_port.config()["lang"] == "es" and tutor_port.config()["persona_name"] == "Lucía"
    es_got = tutor_port.assessment()["got"]
    assert es_got > 0                                       # Level 1 hat Kernwörter markiert

    r = tutor_port.stand_anlegen("Lena", lang="de", level=0)
    assert r["ok"]
    cf = tutor_port.config()
    assert cf["lang"] == "de" and cf["persona_name"] == "Lena"
    assert tutor_port.assessment()["got"] == 0 and tutor_port.assessment()["lang"] == "de"
    assert tutor_port.debug_snapshot()["lang"] == "de"

    # Drill-Antwort über den Port landet im de-Stand, nicht in es
    tutor_port.assessment_answer(tools._core_list("de")[0]["word"], "known")
    assert tutor_port.assessment()["got"] == 1
    es_id = [s["id"] for s in r["staende"] if s["lang"] == "es"][0]
    assert tutor_port.stand_waehlen(es_id)["ok"]
    assert tutor_port.assessment()["got"] == es_got, "es-Stand hat die de-Antwort nicht gesehen"

    # Sprache ist keine Einstellung mehr
    assert "error" in tutor_port.config({"lang": "zh"})
    assert tutor_port.stand_anlegen("X", lang="fr")["ok"] is False, "Skizzen-Sprache nicht anlegbar"
