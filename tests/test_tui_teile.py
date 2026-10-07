"""Charakterisierungs-Tests für Teile, die beim Zerlegen von run_ui eigene
Klassen wurden (06.10.2026, memory/system/tui_bauplan.md): sie halten fest,
was die alte Hauptschleife an diesen Stellen tat — ohne curses-Bildschirm.
"""
from tui.ansichten import befehle, erinnerung


class _Z:
    """Ein Kontext, der nur mitschreibt."""

    def __init__(self):
        self.modus = "auto"
        self.gesetzt = []
        self.C = {k: 0 for k in ("acc", "num", "dim", "faint", "bright", "warn")}

    def theme_mode_now(self):
        return self.modus

    def set_theme_mode(self, neu, quelle="tui"):
        self.gesetzt.append(neu)


def _tippe(bz, text):
    for c in text:
        assert bz.taste(ord(c)) is None


def test_befehlszeile_enter_gibt_das_ergebnis_zurueck():
    bz = befehle.Befehlszeile(_Z())
    bz.oeffnen()
    assert (bz.cmd_mode, bz.cmd_buf, bz.cmd_msg) == (True, "/", "")
    _tippe(bz, "quit")
    assert bz.taste(10) == "QUIT"
    assert (bz.cmd_mode, bz.cmd_buf) == (False, "")


def test_befehlszeile_theme_schreibt_den_wunsch():
    z = _Z()
    bz = befehle.Befehlszeile(z)
    bz.oeffnen()
    _tippe(bz, "theme dunkel")
    bz.taste(13)
    assert z.gesetzt == ["night"]


def test_help_bleibt_stehen():
    bz = befehle.Befehlszeile(_Z())
    bz.oeffnen()
    _tippe(bz, "help")
    assert bz.taste(10) == "HELP"
    assert bz.help_latched is True


def test_backspace_ueber_den_slash_schliesst():
    bz = befehle.Befehlszeile(_Z())
    bz.oeffnen()
    _tippe(bz, "x")
    bz.taste(127)
    assert bz.cmd_mode is True and bz.cmd_buf == "/"
    bz.taste(127)
    assert bz.cmd_mode is False


def test_esc_bricht_ab_ohne_ergebnis():
    bz = befehle.Befehlszeile(_Z())
    bz.oeffnen()
    _tippe(bz, "quit")
    assert bz.taste(27) is None
    assert bz.cmd_mode is False and bz.cmd_buf == ""


class _Store:
    def __init__(self, faellig):
        self.faellig = faellig

    def reminders_snapshot(self):
        return list(self.faellig)


class _Graphen:
    def __init__(self):
        self.G = {"active": False, "view": "view", "msg": "x", "gscroll": 9}
        self.geladen = 0

    def g_load(self):
        self.geladen += 1


def test_erinnerung_einmal_pro_sitzung():
    e = erinnerung.Erinnerung(_Z(), _Graphen())
    store = _Store([{"id": "a", "name": "schlaf"}, "müll"])
    e.pruefen(store)
    assert e.nag_active and [r["id"] for r in e.nag_items] == ["a"]
    e.taste(ord("x"))                      # wegklicken
    assert not e.nag_active
    e.pruefen(store)                       # dieselbe fällige → Ruhe
    assert not e.nag_active


def test_erinnerung_kein_tastendruck_tut_nichts():
    e = erinnerung.Erinnerung(_Z(), _Graphen())
    e.pruefen(_Store([{"id": "a"}]))
    e.taste(-1)                            # Timeout der Schleife, keine Taste
    assert e.nag_active


def test_erinnerung_g_springt_ins_graph_werkzeug():
    g = _Graphen()
    e = erinnerung.Erinnerung(_Z(), g)
    e.pruefen(_Store([{"id": "a"}]))
    e.taste(ord("g"))
    assert g.G == {"active": True, "view": "list", "msg": "", "gscroll": 0}
    assert g.geladen == 1
