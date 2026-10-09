"""Wann, wozu und wie schwer die Persona spricht (2026-10-08).

Sasha: „momentan quatschen die literally RANDOM ZEUG teilweise
ununterbrochen … stattdessen überwälzt sie einen mit fremden vokabular …
dann sag ich »que?«". Jeder Test hier ist eine dieser Beschwerden, gegen ein
gefälschtes Modell (kein Geld): es nimmt auf, was es bekommt, und sagt, was
der Test will.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "core"))

from tutor import (ansprache, anbieter, config, langs, memory, session,   # noqa: E402
                   skills, srs, staende, tools)


class FakeModell:
    """Ersetzt die Straße: merkt sich jeden Aufruf, antwortet mit dem
    nächsten Text aus `antworten` (und führt optional Werkzeuge aus)."""

    def __init__(self, monkeypatch):
        self.aufrufe = []
        self.antworten = []
        self.werkzeuge = []      # [(name, args)] je Aufruf, vor dem Text
        monkeypatch.setattr(anbieter, "fahren", self.fahren)

    def fahren(self, pname, model, verlauf, *, system, tools, tool_executor, max_tokens=None):
        self.aufrufe.append({"system": system, "verlauf": list(verlauf)})
        for name, args in (self.werkzeuge.pop(0) if self.werkzeuge else []):
            tool_executor(name, args)
        yield self.antworten.pop(0) if self.antworten else "vale."


@pytest.fixture
def welt(tmp_path, monkeypatch):
    root = str(tmp_path)
    monkeypatch.setattr(tools, "_DATA_ROOT", root)
    monkeypatch.setattr(memory, "_DATA_DIR", root)
    monkeypatch.setattr(srs, "_DATA_ROOT", root)
    monkeypatch.setattr(config, "_overrides", {})
    monkeypatch.setattr(memory, "remember", lambda *a, **k: None)
    sid = staende.anlegen(root, "T", lang="es", level=0)
    staende.waehlen(root, sid)
    config.set_override("provider", "qwen")
    session.deactivate()
    session.activate()
    yield root
    session.deactivate()


@pytest.fixture
def modell(monkeypatch):
    return FakeModell(monkeypatch)


def _sag(text):
    return "".join(session.respond_stream(text))


def _anstoss(**kw):
    return "".join(session.respond_stream(nudge=True, **kw))


# ── Ruhe: nicht ununterbrochen ──────────────────────────────────────────

class Uhr:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_ruhe_hoechstens_zwei_ohne_antwort():
    uhr = Uhr()
    r = ansprache.Ruhe(uhr)
    r.gesprochen(von_sich_aus=False)               # ihre Antwort
    uhr.t += 15
    assert r.art(False) == "nachhaken"
    assert r.darf("nachhaken")[0]
    r.gesprochen(von_sich_aus=True)
    uhr.t += 600
    ok, grund = r.darf(r.art(False))
    assert not ok and "ohne Antwort" in grund, "danach wartet sie, bis Sasha etwas sagt"
    r.sasha_sagte()
    assert r.darf("stille")[0]


def test_ruhe_abstand_zwischen_anstoessen():
    uhr = Uhr()
    r = ansprache.Ruhe(uhr)
    r.gesprochen(von_sich_aus=True)
    r.sasha_sagte()
    uhr.t += 30
    assert not r.darf("stille")[0]
    uhr.t += ansprache.MIN_ABSTAND_S
    assert r.darf("stille")[0]


def test_ankunft_nur_nach_ruhe():
    uhr = Uhr()
    r = ansprache.Ruhe(uhr)
    assert r.darf("ankunft")[0], "erste Ankunft darf immer"
    r.gesprochen(von_sich_aus=True)
    uhr.t += 60
    assert not r.darf("ankunft")[0]
    uhr.t += ansprache.ANKUNFT_RUHE_S
    assert r.darf("ankunft")[0]


def test_nachhaken_veraltet_wird_stille():
    uhr = Uhr()
    r = ansprache.Ruhe(uhr)
    r.gesprochen(von_sich_aus=False)
    uhr.t += ansprache.NACHHAKEN_FRISCH_S + 1
    assert r.art(False) == "stille"


def test_session_dritter_anstoss_ruft_das_modell_nicht(welt, modell):
    modell.antworten = ["¿quieres agua?", "¿agua?"]
    _sag("hola")
    assert _anstoss() == "¿agua?"          # Nachhaken
    n = len(modell.aufrufe)
    assert _anstoss() == "", "dritte Äußerung ohne Antwort: still"
    assert _anstoss(arrival=False) == ""
    assert len(modell.aufrufe) == n, "und es kostet nichts"


def test_zwei_fenster_verdoppeln_nichts(welt, modell):
    """Pi-Kiosk + Laptop schicken beide ihren Anstoß — der Server lässt einen durch."""
    modell.antworten = ["hola", "¿y tú?"]
    _sag("hola")
    assert _anstoss() and not _anstoss()


# ── Absicht statt Zufall ────────────────────────────────────────────────

def test_nachhaken_bezieht_sich_auf_ihren_letzten_satz(welt, modell):
    modell.antworten = ["¿Te gusta el café?", "¿café?"]
    _sag("hola")
    _anstoss()
    lage = modell.aufrufe[-1]["verlauf"][-1]["content"]
    assert "¿Te gusta el café?" in lage and "No cambies de tema" in lage


def test_stille_hat_ein_lernziel(welt, modell, monkeypatch):
    monkeypatch.setattr(srs, "due_words", lambda lang=None, limit=None: [])
    ziel = tools.core_todo("es", 1)[0]["word"]
    _anstoss()
    lage = modell.aufrufe[-1]["verlauf"][-1]["content"]
    assert f"«{ziel}»" in lage, "EIN Wort als Ziel, nicht irgendwas"


def test_ankunft_hat_eine_absicht(welt, modell):
    _anstoss(arrival=True)
    lage = modell.aufrufe[-1]["verlauf"][-1]["content"]
    assert "UNA pregunta muy fácil" in lage


def test_skizze_ohne_absichten_stuerzt_nicht():
    prof = dict(langs.get("es"), absichten={})
    assert ansprache.anstoss_text(prof, "stille", "es") == ""


# ── Niveau ──────────────────────────────────────────────────────────────

def test_anfaenger_bekommt_die_unterste_stufe(welt, modell):
    _sag("hola")
    sys_ = modell.aufrufe[-1]["system"]
    assert "empieza casi desde cero" in sys_
    import re
    m = re.search(r"Aún por enseñar, por orden: ([^.]*)\.", sys_)
    assert m and "," not in m.group(1), "am Anfang EIN Grundwort, nicht sechs"


def test_niveau_waechst_mit_dem_was_er_kennt(welt, modell):
    for w in ("agua", "café", "casa", "mesa", "silla", "libro", "perro", "gato",
              "sol", "luna", "pan", "leche", "calle", "coche", "tren", "flor",
              "mano", "pie", "ojo", "boca", "rojo", "azul", "verde", "grande",
              "uno", "dos", "tres", "hoy", "ayer", "mañana", "noche", "día",
              "bien", "mal", "sí", "no", "hola", "adiós", "gracias", "vale"):
        tools.introduce_new(w, lang="es")
        tools.note_spoken(w, "es"); tools.note_spoken(w, "es")
    _sag("hola")
    sys_ = modell.aufrufe[-1]["system"]
    assert "empieza casi desde cero" not in sys_
    assert "Frases sencillas" in sys_


# ── „que?" → einfacher, langsamer, mit Übersetzung ──────────────────────

@pytest.mark.parametrize("frage", ["¿qué?", "que?", "was?", "hä?", "no entiendo", "?"])
def test_nachfrage_wird_erkannt(frage):
    v = skills.Verstaendnis()
    v.antwort_merken("¿Quieres agua?")
    assert v.pruefen(frage, "es")["erkannt"], frage


def test_que_wiederholt_das_schluesselwort_langsam(welt, modell):
    tools.introduce_new("agua", lang="es", meaning="water")
    modell.antworten = ["¿Quieres agua fresquita del grifo?", "agua."]
    _sag("hola")
    normal = session.room_state()["tts_speed"]
    _sag("¿qué?")
    sys_ = modell.aufrufe[-1]["system"]
    assert "NO ha entendido" in sys_ and "«agua»" in sys_ and "water" in sys_
    assert session.room_state()["tts_speed"] < normal, "langsamer sprechen"
    rs = session.room_state()
    assert rs["thought_word"] == "agua" and rs["thought_meaning"] == "water", \
        "ohne show_thought vom Modell reicht das Programm die Übersetzung nach"


def test_que_ohne_bekannte_bedeutung_erfindet_nichts(welt, modell):
    modell.antworten = ["Zzzblub fantástico.", "zzzblub."]
    _sag("hola")
    vorher = session.room_state()["thought_id"]
    _sag("¿qué?")
    assert session.room_state()["thought_id"] == vorher


def test_que_zeigt_den_gedanken_des_modells_nicht_doppelt(welt, modell):
    tools.introduce_new("agua", lang="es", meaning="water")
    modell.antworten = ["¿Quieres agua?", "agua."]
    _sag("hola")
    modell.werkzeuge = [[("show_thought", {"word": "agua", "meaning": "Wasser"})]]
    _sag("¿qué?")
    assert session.room_state()["thought_meaning"] == "water", \
        "die gespeicherte Bedeutung gilt (show_thought), kein zweiter Gedanke"


# ── Vokabeln: gehört zählt jetzt auch im Gespräch ───────────────────────

def _eintrag(w):
    return next(e for e in tools._load_raw("es") if e["word"] == w)


def test_gehoert_zaehlt_nach_sinnvoller_antwort(welt, modell):
    tools.introduce_new("agua", lang="es")
    modell.antworten = ["¿Quieres agua?", "vale."]
    _sag("hola")
    _sag("sí, por favor")
    assert _eintrag("agua")["listened"] == 1


def test_gehoert_zaehlt_nicht_nach_que(welt, modell):
    tools.introduce_new("agua", lang="es")
    modell.antworten = ["¿Quieres agua?", "agua."]
    _sag("hola")
    _sag("¿qué?")
    assert _eintrag("agua")["listened"] == 0


# ── Nachkontrolle ───────────────────────────────────────────────────────

def test_zu_viele_fremde_woerter_geben_einen_hinweis(welt, modell):
    modell.antworten = ["Hoy la meteorología anuncia precipitaciones abundantes "
                        "en la península ibérica.", "vale."]
    _sag("hola")
    _sag("sí")
    sys_ = modell.aufrufe[-1]["system"]
    assert "palabras que Sasha aún no conoce" in sys_ and "meteorología" in sys_
    _sag("sí")
    assert "aún no conoce" not in modell.aufrufe[-1]["system"], "nur einmal"


def test_kurze_leichte_antwort_gibt_keinen_hinweis(welt, modell):
    modell.antworten = ["hola.", "vale."]
    _sag("hola")
    _sag("sí")
    assert "aún no conoce" not in modell.aufrufe[-1]["system"]


def test_woerter_ohne_regie_und_mit_cjk():
    assert ansprache.woerter("(sonríe) ¡Hola, Sasha! *wave*") == ["hola", "sasha"]
    assert ansprache.woerter("你好吗") == ["你", "好", "吗"]


def test_zwei_kurze_antworten_sind_kein_unverstaendnis(welt, modell):
    """Regel 3 (»redet an ihr vorbei«) bleibt Beobachtung: bei fast leerer
    Liste träfe sie jeden Anfänger-Satz."""
    modell.antworten = ["¿Qué tal?", "¡Qué bien!", "vale."]
    _sag("hola")
    _sag("estoy bien")
    _sag("muy bien gracias")
    assert "NO ha entendido" not in modell.aufrufe[-1]["system"]
