"""
Die zwei Schienen: welcher Prompt und welches Tool-Set gehen an welches Modell.

Ein 9B-Modell und ein Frontier-Modell teilten sich bis hierher EINEN Prompt.
Jede Anpassung für das eine war Ballast oder Gift für das andere. Jetzt hat
jedes seine eigene Schiene — und diese Tests halten drei Dinge fest:

  1. Der Umzug nach profil/klein.py war WÖRTLICH. Der lokale Pfad ist gerade
     nicht live testbar (unterwegs läuft kein Ollama); ein stiller Zeichen-
     verlust dort fiele erst daheim auf, Wochen später.
  2. Beide Schienen bieten dasselbe an, damit der Kern nicht wissen muss, auf
     welcher er fährt.
  3. Ein umbenanntes Tool rutscht nicht am Erlaubnis-Gate vorbei. Das wäre der
     stillste denkbare Fehler: die KI schreibt in den Kalender, ohne zu fragen.
"""
import re

import pytest

import ai
import profil
from profil import gross, klein


# ── Die Schnittstelle ──────────────────────────────────────────────────

@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_jede_schiene_bietet_dasselbe_an(p):
    """Sonst müsste der Kern für jede Schiene einen Sonderfall kennen — und
    genau das soll die Aufteilung ja verhindern."""
    assert isinstance(p.NAME, str) and p.NAME
    assert isinstance(p.SYSTEM, str) and p.SYSTEM
    assert isinstance(p.TOOLS, list) and p.TOOLS
    assert isinstance(p.TERMINAL, set)
    assert isinstance(p.MERKMALE, dict)
    kopf = p.system()
    assert isinstance(kopf, str) and p.SYSTEM in kopf


@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_system_nimmt_eine_fremde_persona_an(p):
    """Der Tutor bringt seinen eigenen Prompt mit."""
    kopf = p.system("ICH BIN WER ANDERS")
    assert "ICH BIN WER ANDERS" in kopf
    assert p.SYSTEM not in kopf


def test_dashview_laesst_sich_abschalten():
    """ZENTRALE_DASHVIEW=0 ist der A/B-Vergleich für das Dashboard-Sicht-
    Experiment — der muss weiter gehen."""
    assert klein._DASHBOARD_VIEW in klein.system(dashview=True)
    assert klein._DASHBOARD_VIEW not in klein.system(dashview=False)


# ── Der Umzug war wörtlich ─────────────────────────────────────────────

def test_ai_zeigt_auf_die_kleine_schiene():
    """Der lokale Pfad, die vier scripts/bench_*.py und die bestehenden Tests
    greifen weiter über ai.* zu. Die Namen dürfen nicht ins Leere zeigen."""
    assert ai._SYSTEM_PROMPT is klein._SYSTEM_PROMPT
    assert ai._CAPABILITIES_PROMPT is klein._CAPABILITIES_PROMPT
    assert ai.ANTWORT_SUFFIX is klein.ANTWORT_SUFFIX
    assert ai._ASCII_MARKER_PROMPT is klein._ASCII_MARKER_PROMPT
    assert ai._DASHBOARD_VIEW is klein._DASHBOARD_VIEW
    assert ai._MIC_INPUT_HINT is klein._MIC_INPUT_HINT
    assert ai.TOOLS is klein.TOOLS


def test_der_kopf_hat_alle_teile_in_der_alten_reihenfolge():
    """Die Reihenfolge ist nicht Geschmack: der statische Kopf muss über alle
    Turns byte-identisch sein, und was das Modell zuletzt liest, wiegt am
    schwersten."""
    kopf = klein.system(dashview=True)
    stellen = [kopf.index(t) for t in (
        klein._SYSTEM_PROMPT,
        klein._CAPABILITIES_PROMPT,
        klein.ANTWORT_SUFFIX,
        klein._ASCII_MARKER_PROMPT,
        klein._DASHBOARD_VIEW,
    )]
    assert stellen == sorted(stellen)


def test_klein_behaelt_seine_kruecken():
    """Sie sind der Grund, warum es zwei Schienen gibt. Verschwinden sie hier
    aus Versehen mit, war die ganze Trennung umsonst."""
    namen = {t["function"]["name"] for t in klein.TOOLS}
    assert "antwort" in namen
    assert klein.MERKMALE["antwort_tool"] is True
    assert klein.ANTWORT_SUFFIX in klein.system()
    assert klein._ASCII_MARKER_PROMPT in klein.system()


# ── Kanonische Namen ───────────────────────────────────────────────────

def test_deutsche_namen_werden_uebersetzt():
    assert profil.kanonisch("lies_news") == "read_news"
    assert profil.kanonisch("web_suche") == "web_search"
    assert profil.kanonisch("frage_knopf") == "ask_choice"


def test_kanonisch_ist_idempotent_und_tolerant():
    """Zweimal übersetzen darf nichts kaputtmachen, und ein unbekannter Name
    muss durchrutschen — der fällt weiter unten als 'unbekanntes Tool' auf,
    nicht hier als KeyError mitten im Gespräch."""
    for name in ("read_news", "read_calendar", "voellig_ausgedacht"):
        assert profil.kanonisch(name) == name
    assert profil.kanonisch(profil.kanonisch("hole_url")) == "fetch_url"


# ── Auswahl ────────────────────────────────────────────────────────────

def test_cloud_faehrt_gross_lokal_faehrt_klein(monkeypatch):
    monkeypatch.delenv("ZENTRALE_PROMPT_PROFIL", raising=False)
    monkeypatch.setattr(profil, "_aus_config", lambda: None)
    assert profil.fuer_backend("cloud") is gross
    assert profil.fuer_backend("local") is klein


def test_env_taucht_die_schiene_zurueck(monkeypatch):
    """»Die andere kann man schnell wieder reintauschen« — eine Zeile."""
    monkeypatch.setenv("ZENTRALE_PROMPT_PROFIL", "klein")
    assert profil.fuer_backend("cloud") is klein


def test_unbekannte_schiene_faellt_auf_klein_zurueck(monkeypatch):
    """Klein ist die vorsichtigere: sie hat die Krücken drin. Ein Tippfehler
    in der Config macht die KI dann höchstens geschwätzig, nicht kaputt."""
    monkeypatch.setenv("ZENTRALE_PROMPT_PROFIL", "kruemelmonster")
    assert profil.fuer_backend("cloud") is klein


# ── Kein Tool rutscht am Kern (oder am Gate) vorbei ────────────────────

def _dispatchbare_namen() -> set:
    """Die Namen, die _dispatch_tool tatsächlich kennt — aus dem Quelltext
    gelesen, damit der Test nicht die Tools ausführt."""
    import inspect
    quelle = inspect.getsource(ai._dispatch_tool)
    return set(re.findall(r'name == "([a-z_]+)"', quelle))


@pytest.mark.parametrize("p", [klein, gross], ids=["klein", "gross"])
def test_jedes_angebotene_tool_kann_der_kern_auch_ausfuehren(p):
    """Der teuerste Fehler beim Umbenennen: das Modell ruft ein Tool, das es
    im Schema sieht, und der Kern antwortet '[Unbekanntes Tool]'. Kostet eine
    volle Runde und macht die KI vor Sasha zum Lügner."""
    kennt = _dispatchbare_namen()
    # Terminale Tools laufen nicht über _dispatch_tool, sondern werden im Loop
    # abgefangen (siehe cloud.run_tool).
    terminal = {profil.kanonisch(t) for t in p.TERMINAL}
    for t in p.TOOLS:
        name = profil.kanonisch(t["function"]["name"])
        if name in terminal or name == "ask_choice":
            continue
        assert name in kennt, f"{p.NAME}: {name} wird angeboten, aber nicht ausgeführt"


@pytest.mark.parametrize("alias,kanon", sorted(profil.ALIASE.items()))
def test_das_gate_kennt_beide_schreibweisen(alias, kanon):
    """Ein Schreib-Tool, das unter seinem Alias am Gate vorbeikommt, würde
    ungefragt in Sashas Kalender schreiben. Der Fehler wäre völlig lautlos."""
    assert ai.braucht_erlaubnis(alias) == ai.braucht_erlaubnis(kanon)


def test_gate_greift_bei_den_schreibenden_tools():
    for name in ("add_calendar_entry", "delete_calendar_entry",
                 "web_suche", "web_search", "hole_url", "fetch_url"):
        assert ai.braucht_erlaubnis(name), name
    for name in ("read_calendar", "read_file", "list_files", "lies_news"):
        assert not ai.braucht_erlaubnis(name), name
