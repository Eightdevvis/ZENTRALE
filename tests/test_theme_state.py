"""
Tag/Nacht-Zustand (core/theme.py) — die Datei ist die einzige Wahrheit.

Diese Tests halten fest, was die alte Fassung falsch machte. Dort lag der Modus
doppelt vor (Variable in der TUI + Datei), abgeglichen ueber drei Hilfspuffer;
zwischen "Taste aendert die Variable" und "Schleife schreibt die Datei" konnte
ein Lesevorgang die Variable ueberschreiben. Sichtbar wurde das als Theme, das
kurz umsprang und wieder zurueck, und als Fremd-Eintraege im Protokoll mit
genau den Werten, die die TUI selbst eine Zeile vorher geschrieben hatte.

Entsprechend pruefen die Tests nicht nur "setzen funktioniert", sondern:
  * ein eigener Schreibvorgang kommt NIE als "fremd" zurueck (kein Selbst-Echo)
  * schnelle Folgen (Tastenwiederholung) landen deterministisch, ohne Ruecksprung
  * eine Fremdaenderung wird uebernommen, aber nicht zurueckgeschrieben
"""
import os
import sys
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "core"))
import theme as T  # noqa: E402


@pytest.fixture
def st(tmp_path):
    """ThemeState auf einer Wegwerf-Datei; Sashas Konfiguration bleibt unberuehrt."""
    return T.ThemeState(path=str(tmp_path / "theme"),
                        log_path=str(tmp_path / "changes.log"))


def _log(st):
    try:
        with open(st.log_path) as fh:
            return fh.read()
    except OSError:
        return ""


# ── Grundverhalten ────────────────────────────────────────────────────────
def test_fehlende_datei_ist_auto(st):
    assert st.mode() == "auto"


def test_muell_ist_auto(tmp_path):
    f = tmp_path / "theme"
    f.write_text("voelliger-muell\n")
    assert T.ThemeState(path=str(f), log_path=None).mode() == "auto"


def test_setzen_schreibt_die_datei(st):
    assert st.set("night") is True
    assert open(st.path).read().strip() == "night"
    assert st.mode() == "night"


def test_setzen_auf_denselben_wert_tut_nichts(st):
    st.set("day")
    vorher = os.stat(st.path).st_mtime_ns
    time.sleep(0.01)
    assert st.set("day") is False
    assert os.stat(st.path).st_mtime_ns == vorher, "Datei ohne Not neu geschrieben"


def test_unbekannter_modus_wird_abgelehnt(st):
    assert st.set("tuerkis") is False
    assert st.mode() == "auto"


@pytest.mark.parametrize("mode,stunde,erwartet", [
    ("day", 3, "day"), ("night", 12, "night"),       # feste Modi ignorieren die Uhr
    ("auto", 4, "night"), ("auto", 5, "day"),        # Grenze morgens
    ("auto", 20, "day"), ("auto", 21, "night"),      # Grenze abends
])
def test_auto_loest_nach_der_uhrzeit_auf(mode, stunde, erwartet):
    assert T.resolve(mode, stunde) == erwartet


def test_zyklus_geht_im_kreis(st):
    assert st.mode() == "auto"
    for erwartet in ("day", "night", "auto", "day"):
        st.cycle()
        assert st.mode() == erwartet


# ── Genau die Fehler, die den Glitch verursacht haben ─────────────────────
def test_eigenes_schreiben_kommt_nie_als_fremd_zurueck(st):
    """DER Kernfall: die TUI las ihr eigenes Echo als Fremdaenderung.

    Nach jedem Setzen wird der Modus mehrfach gelesen — dabei darf keine
    einzige `fremd`-Zeile entstehen.
    """
    for neu in ("day", "night", "auto", "night"):
        st.set(neu)
        for _ in range(5):
            assert st.mode() == neu
    assert "fremd" not in _log(st), _log(st)


def test_schnelle_folge_landet_deterministisch(st):
    """Tastenwiederholung: 12 Zyklen sind 4 volle Runden — wieder am Anfang.

    Die alte Fassung konnte hier zurueckspringen, weil ein Lesevorgang den
    gerade getippten Wunsch ueberschrieb. Gerechnet wird jetzt auf dem
    Datei-Stand, also ist die Folge exakt.
    """
    start = st.mode()
    for _ in range(12):
        st.cycle()
    assert st.mode() == start
    assert "fremd" not in _log(st), _log(st)


def test_lesen_zwischen_zwei_schaltungen_verschluckt_nichts(st):
    """Zwischen zwei Tastendruecken zeichnet die TUI — das darf nichts kosten."""
    st.set("day")
    for _ in range(20):
        st.mode()
        st.resolved()
    st.cycle()
    assert st.mode() == "night"


def test_fremdaenderung_wird_uebernommen_und_protokolliert(st):
    """Schreibt ein anderer Prozess, ziehen wir nach — und merken es an."""
    st.set("day")
    with open(st.path + ".x", "w") as fh:      # atomar, wie alle Schreiber
        fh.write("night\n")
    os.replace(st.path + ".x", st.path)
    assert st.mode() == "night"
    assert "fremd  day -> night" in _log(st), _log(st)


def test_fremdaenderung_wird_nicht_zurueckgeschrieben(st):
    """Mitziehen heisst mitziehen — die Datei bleibt die Wahrheit."""
    st.set("day")
    with open(st.path + ".x", "w") as fh:
        fh.write("night\n")
    os.replace(st.path + ".x", st.path)
    stamp = os.stat(st.path).st_mtime_ns
    for _ in range(10):
        st.mode()
        st.resolved()
    assert os.stat(st.path).st_mtime_ns == stamp, "wir haben zurueckgeschrieben"


def test_zyklus_nach_fremdaenderung_rechnet_auf_dem_dateistand(st):
    """Nach einer Fremdaenderung zykliert 't' von DEREN Wert weiter."""
    st.set("day")
    with open(st.path + ".x", "w") as fh:
        fh.write("night\n")
    os.replace(st.path + ".x", st.path)
    st.cycle()                                  # night -> auto, nicht day -> night
    assert st.mode() == "auto"


def test_zwei_zustaende_auf_derselben_datei_bleiben_einig(tmp_path):
    """Zwei TUIs (oder TUI + Tutor) duerfen sich nicht gegenseitig aufschaukeln."""
    a = T.ThemeState(path=str(tmp_path / "theme"), log_path=None)
    b = T.ThemeState(path=str(tmp_path / "theme"), log_path=None)
    a.set("night")
    assert b.mode() == "night"
    b.cycle()                                   # night -> auto
    assert a.mode() == "auto"
    a.cycle()                                   # auto -> day
    assert b.mode() == "day"
    assert open(a.path).read().strip() == "day"


def test_env_override_wird_beachtet(tmp_path, monkeypatch):
    """Ohne das wuerden Tests in Sashas echte Konfiguration schreiben."""
    ziel = tmp_path / "anderswo"
    monkeypatch.setenv("ZENTRALE_THEME_FILE", str(ziel))
    assert T.theme_file() == str(ziel)
    st = T.ThemeState(log_path=None)
    st.set("night")
    assert ziel.read_text().strip() == "night"


def test_schreibt_atomar(st):
    """Kein Zwischenzustand mit leerer Datei — nvims fs_event liest sonst nichts.

    Geprueft am Ergebnis: nach dem Schreiben liegt keine .tmp-Datei mehr herum
    und der Inhalt ist vollstaendig.
    """
    st.set("night")
    assert not os.path.exists(st.path + ".tmp")
    assert open(st.path).read() == "night\n"
