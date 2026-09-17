"""Skill-Auslöser »no_entiendo« (tutor/skills.py): greift der hart kodierte
Catcher bei Unverständnis — und NICHT bei Gruß/normalem Reden?"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tutor import skills


@pytest.mark.parametrize("text,lang,erwartet", [
    # explizit
    ("no entiendo", "es", True),
    ("No lo entiendo.", "es", True),
    ("¿Qué?", "es", True),
    ("qué", "es", True),
    ("?", "es", True),
    ("más despacio", "es", True),
    ("Ich verstehe nicht", "de", True),
    ("Was?", "de", True),
    ("wie bitte", "de", True),
    ("听不懂", "zh", True),
    ("什么？", "zh", True),
    # kurze Rückfrage mit ?
    ("otra vez?", "es", True),
    ("perdón?", "es", True),
    # KEIN Unverständnis
    ("¿Qué tal?", "es", False),
    ("hola", "es", False),
    ("hola lucía", "es", False),
    ("¿y tú?", "es", False),
    ("qué haces hoy en la tarde?", "es", False),
    ("was machst du heute", "de", False),
    ("Und du?", "de", False),
    ("你好吗", "zh", False),
    ("estoy bien, gracias", "es", False),
])
def test_phrasen(text, lang, erwartet):
    v = skills.Verstaendnis()
    lage = v.pruefen(text, lang, hits=[])
    assert lage['erkannt'] is erwartet, (text, lage)


def test_zweimal_vorbei_geredet():
    """Regel 3: zwei Äußerungen in Folge ohne bekannte Vokabel und ohne ein Wort
    aus ihrer Antwort → erkannt. Eine allein noch nicht."""
    v = skills.Verstaendnis()
    v.antwort_merken("¿Quieres un café?")
    a = v.pruefen("mmh bueno", "es", hits=[])
    assert a['erkannt'] is False and a['vorbei'] == 1
    b = v.pruefen("bla bla", "es", hits=[])
    assert b['erkannt'] is True and 'anschluss' in b['grund']
    assert b['uebergang'] == 'an' and v.aktiv


def test_anschluss_setzt_zurueck_und_beendet():
    """Benutzt er ein Wort aus ihrer Antwort, ist der Zustand aus (und der
    Vorbei-Zähler null)."""
    v = skills.Verstaendnis()
    v.antwort_merken("¿Quieres un café?")
    v.pruefen("no entiendo", "es", hits=[])
    assert v.aktiv
    lage = v.pruefen("sí, café", "es", hits=[])
    assert lage['erkannt'] is False and lage['uebergang'] == 'aus'
    assert 'café' in lage['anschluss'] and not v.aktiv


def test_bekannte_vokabel_beendet():
    v = skills.Verstaendnis()
    v.antwort_merken("Hola, ¿qué tal?")
    v.pruefen("?", "es", hits=[])
    assert v.aktiv
    lage = v.pruefen("yo bien", "es", hits=["yo", "bien"])
    assert lage['uebergang'] == 'aus' and not v.aktiv


def test_phrase_waehrend_aktiv_bleibt_an():
    v = skills.Verstaendnis()
    v.antwort_merken("¿Quieres un café?")
    v.pruefen("no entiendo", "es", hits=[])
    lage = v.pruefen("qué?", "es", hits=[])
    assert lage['erkannt'] and lage['uebergang'] is None and v.aktiv
